import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse


RELEVANT_LINK_PATTERN = re.compile(
    r"(agent|automation|workflow|flow|tool|skill|function|knowledge|kb|test|suite|integration|setting)",
    re.I,
)

AUTH_PATTERN = re.compile(r"(login|sign in|signin|authenticate|auth)", re.I)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def playwright_status() -> Dict[str, Any]:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as exc:
        return {
            "available": False,
            "package": "missing",
            "message": f"Python Playwright is not available: {exc}",
        }
    return {
        "available": True,
        "package": "python-playwright",
        "message": "Ready for read-only Yellow.ai platform snapshots when a logged-in session is available.",
    }


def safe_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


def snapshot_config(profile: Dict[str, Any], setting_value: Callable[[str, str], str], root: Path) -> Dict[str, Any]:
    ui_base_url = str(
        profile.get("yellow_ai_ui_base_url")
        or setting_value("YELLOW_AI_UI_BASE_URL", "https://cloud.yellow.ai")
        or "https://cloud.yellow.ai"
    ).strip().rstrip("/")
    bot_id = str(profile.get("yellow_ai_bot_id") or setting_value("YELLOW_AI_BOT_ID", "")).strip()
    start_url = str(profile.get("yellow_ai_console_url") or "").strip()
    if not start_url and bot_id:
        start_url = f"{ui_base_url}/bot/{bot_id}/overview"
    max_pages = safe_int(profile.get("platform_snapshot_max_pages"), 10)
    return {
        "bot_id": bot_id,
        "ui_base_url": ui_base_url,
        "start_url": start_url,
        "headless": safe_bool(profile.get("platform_snapshot_headless"), True),
        "max_pages": max(1, min(max_pages, 25)),
        "session_dir": str(root / "data" / "yellow_ai_platform_session"),
    }


def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def run_platform_snapshot(
    profile: Dict[str, Any],
    setting_value: Callable[[str, str], str],
    root: Path,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise ValueError(f"Python Playwright is required for platform snapshots: {exc}") from exc

    config = snapshot_config(profile, setting_value, root)
    options = options or {}
    if "headless" in options:
        config["headless"] = safe_bool(options.get("headless"), config["headless"])
    if "start_url" in options and str(options.get("start_url") or "").strip():
        config["start_url"] = str(options["start_url"]).strip()
    if not config["start_url"]:
        raise ValueError("Add Yellow.ai Bot ID or Console URL before running a platform snapshot.")

    pages: List[Dict[str, Any]] = []
    network_events: List[Dict[str, Any]] = []
    notes: List[str] = []

    def on_response(response: Any) -> None:
        if len(network_events) >= 80:
            return
        try:
            request = response.request
            resource_type = request.resource_type
            url = response.url
            if resource_type not in {"xhr", "fetch"}:
                return
            if "yellow.ai" not in url and urlparse(url).netloc != urlparse(config["ui_base_url"]).netloc:
                return
            if not RELEVANT_LINK_PATTERN.search(url):
                return
            network_events.append(
                {
                    "url": redact_url(url),
                    "status": response.status,
                    "method": request.method,
                    "resource_type": resource_type,
                }
            )
        except Exception:
            return

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=config["session_dir"],
            headless=config["headless"],
            viewport={"width": 1440, "height": 920},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", on_response)
        try:
            safe_goto(page, config["start_url"])
            pages.append(collect_page(page, "start"))
            if is_auth_page(page, pages[-1]):
                if safe_bool(options.get("wait_for_login"), False):
                    notes.append("Waiting for Yellow.ai login in the opened browser session.")
                    try:
                        page.wait_for_function(
                            """() => {
                                const body = document.body ? document.body.innerText : '';
                                return !/(login|sign in|signin|authenticate|auth)/i.test(location.href + ' ' + body.slice(0, 1500));
                            }""",
                            timeout=180000,
                        )
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        pages = [collect_page(page, "start after login")]
                    except Exception:
                        notes.append("Login was not completed before the snapshot timeout.")
                        return build_snapshot(config, pages, network_events, notes, "auth_required")
                else:
                    notes.append("Yellow.ai login is required. Use Connect session once, then rerun the snapshot.")
                    return build_snapshot(config, pages, network_events, notes, "auth_required")

            links = discover_links(page, config["ui_base_url"], config["max_pages"])
            for target in targeted_platform_pages(config):
                if len(pages) >= config["max_pages"]:
                    break
                if any(existing.get("url") == redact_url(target["url"]) for existing in pages):
                    continue
                try:
                    safe_goto(page, target["url"])
                    pages.append(collect_page(page, target["label"]))
                except PlaywrightTimeoutError:
                    notes.append(f"Timed out reading {target['label']}")
                except Exception as exc:
                    notes.append(f"Could not read {target['label']}: {exc}")

            for link in links:
                if len(pages) >= config["max_pages"]:
                    break
                try:
                    safe_goto(page, link["url"])
                    pages.append(collect_page(page, link["label"] or "linked page"))
                except PlaywrightTimeoutError:
                    notes.append(f"Timed out reading {link['url']}")
                except Exception as exc:
                    notes.append(f"Could not read {link['url']}: {exc}")

            if len(pages) < config["max_pages"]:
                for label in ["Agents", "Automation", "Workflows", "Tools", "Knowledge", "Test suites", "Settings"]:
                    if len(pages) >= config["max_pages"]:
                        break
                    if click_text_if_present(page, label):
                        pages.append(collect_page(page, label))
        finally:
            context.close()

    status = "ok" if pages else "empty"
    return build_snapshot(config, pages, network_events, notes, status)


def safe_goto(page: Any, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass


def targeted_platform_pages(config: Dict[str, Any]) -> List[Dict[str, str]]:
    bot_id = config.get("bot_id", "")
    if not bot_id:
        return []
    base = config["ui_base_url"].rstrip("/")
    paths = [
        ("super agent profile", f"/bot/{bot_id}/studio/ai-agent/profile"),
        ("agents inventory", f"/bot/{bot_id}/studio/ai-agent/agents"),
        ("flows inventory", f"/bot/{bot_id}/studio/build/flows"),
        ("functions inventory", f"/bot/{bot_id}/studio/build/functions"),
        ("knowledge base", f"/bot/{bot_id}/kb/files/knowledge-base"),
        ("conversation logs", f"/bot/{bot_id}/growth/analysis/chat-logs"),
        ("call logs", f"/bot/{bot_id}/growth/analysis/call-logs"),
        ("test suites", f"/bot/{bot_id}/studio/test-ai-agent"),
    ]
    return [{"label": label, "url": base + path} for label, path in paths]


def collect_page(page: Any, label: str) -> Dict[str, Any]:
    try:
        body_text = page.locator("body").inner_text(timeout=8000)
    except Exception:
        body_text = ""
    extracted = page.evaluate(
        """() => {
            const text = (node) => (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
            const take = (selector, limit) => Array.from(document.querySelectorAll(selector))
              .map((el) => ({
                text: text(el).slice(0, 220),
                href: el.href || '',
                role: el.getAttribute('role') || '',
                aria: el.getAttribute('aria-label') || '',
                id: el.id || '',
                cls: typeof el.className === 'string' ? el.className.slice(0, 100) : ''
              }))
              .filter((item) => item.text || item.href || item.aria)
              .slice(0, limit);
            const tables = Array.from(document.querySelectorAll('table')).map((table) =>
              Array.from(table.querySelectorAll('tr')).map((row) =>
                Array.from(row.querySelectorAll('th,td')).map((cell) => text(cell).slice(0, 700)).filter(Boolean)
              ).filter((row) => row.length).slice(0, 35)
            ).filter((rows) => rows.length).slice(0, 5);
            const codeSnippets = take('pre,code,textarea,[class*="monaco"],[class*="editor"]', 12)
              .map((item) => item.text)
              .filter(Boolean)
              .slice(0, 8);
            return {
              title: document.title || '',
              url: location.href,
              headings: take('h1,h2,h3,[role="heading"]', 30),
              buttons: take('button,[role="button"]', 60),
              links: take('a[href]', 80),
              inputs: take('label,input,textarea,select,[contenteditable="true"]', 80),
              tables,
              code_snippets: codeSnippets
            };
        }"""
    )
    clean_text = re.sub(r"\s+", " ", body_text).strip()
    return {
        "label": label,
        "title": extracted.get("title", ""),
        "url": redact_url(extracted.get("url", "")),
        "text_preview": clean_text[:12000],
        "signals": extracted,
    }


def discover_links(page: Any, ui_base_url: str, max_pages: int) -> List[Dict[str, str]]:
    links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
          .map((a) => ({ label: (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim(), url: a.href }))
          .filter((item) => item.url)
          .slice(0, 250)"""
    )
    base_host = urlparse(ui_base_url).netloc
    seen = set()
    relevant: List[Dict[str, str]] = []
    for item in links:
        absolute_url = urljoin(ui_base_url, item.get("url", ""))
        parsed = urlparse(absolute_url)
        if parsed.netloc != base_host:
            continue
        haystack = f"{item.get('label', '')} {parsed.path}"
        if not RELEVANT_LINK_PATTERN.search(haystack):
            continue
        normalized = parsed._replace(fragment="", query="").geturl()
        if normalized in seen:
            continue
        seen.add(normalized)
        relevant.append({"label": item.get("label", ""), "url": normalized})
        if len(relevant) >= max_pages:
            break
    return relevant


def click_text_if_present(page: Any, label: str) -> bool:
    try:
        locator = page.get_by_text(label, exact=True)
        if locator.count() != 1:
            return False
        locator.click(timeout=3000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        return True
    except Exception:
        return False


def is_auth_page(page: Any, first_page: Dict[str, Any]) -> bool:
    url = page.url or ""
    text = first_page.get("text_preview", "")[:1500]
    return bool(AUTH_PATTERN.search(url) or AUTH_PATTERN.search(text))


def redact_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def build_snapshot(
    config: Dict[str, Any],
    pages: List[Dict[str, Any]],
    network_events: List[Dict[str, Any]],
    notes: List[str],
    status: str,
) -> Dict[str, Any]:
    page_text = "\n".join(page.get("text_preview", "") for page in pages)
    return {
        "id": f"snapshot_{uuid.uuid4().hex[:10]}",
        "created_at": now_iso(),
        "source": "yellow_ai_platform_readonly",
        "status": status,
        "bot_id": config.get("bot_id", ""),
        "ui_base_url": config.get("ui_base_url", ""),
        "start_url": redact_url(config.get("start_url", "")),
        "headless": config.get("headless", True),
        "page_count": len(pages),
        "network_event_count": len(network_events),
        "summary": summarize_snapshot_text(page_text, status, notes),
        "pages": pages,
        "network_events": network_events,
        "notes": notes,
    }


def summarize_snapshot_text(text: str, status: str, notes: List[str]) -> str:
    if status == "auth_required":
        return "Yellow.ai platform snapshot could not read Studio because login is required."
    tokens = [
        ("agents", len(re.findall(r"\bagent\b", text, flags=re.I))),
        ("workflows", len(re.findall(r"\bworkflow\b", text, flags=re.I))),
        ("tools", len(re.findall(r"\b(tool|skill|function)\b", text, flags=re.I))),
        ("knowledge", len(re.findall(r"\b(knowledge|kb)\b", text, flags=re.I))),
        ("tests", len(re.findall(r"\b(test|suite)\b", text, flags=re.I))),
    ]
    found = ", ".join(f"{name}: {count}" for name, count in tokens if count)
    base = f"Read-only Yellow.ai platform snapshot captured {found or 'general platform context'}."
    if notes:
        base += " Notes: " + " ".join(notes[:3])
    return base
