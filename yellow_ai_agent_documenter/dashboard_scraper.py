import os
import json
import time
from playwright.sync_api import sync_playwright

from api_client import BOT_ID


UI_BASE_URL = os.environ.get("YELLOW_AI_UI_BASE_URL", "https://cloud.yellow.ai").rstrip("/")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_session")

def scrape_full_dashboard():
    if not BOT_ID:
        print("YELLOW_AI_BOT_ID is required in .env")
        return

    print("🔍 Starting Full Dashboard Scraper...")
    
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate directly to the bot dashboard
        url = f"{UI_BASE_URL}/bot/{BOT_ID}/overview"
        print(f"📍 Navigating to bot dashboard: {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(5)
        
        if "login" in page.url or "auth" in page.url:
            print("❌ Session failed. We are on the login page.")
            context.close()
            return
            
        scraped_data = {"bot_id": BOT_ID, "super_agent": "", "agents": []}
        
        try:
            print("   Clicking Agents tab...")
            # Click the main Agents tab on the left sidebar
            page.locator('div[data-tour="agents-sidebar"]').click(timeout=5000)
            time.sleep(3)
        except Exception:
            try:
                # Fallback if specific data-tour selector is missing
                page.click('a:has-text("Agents")', timeout=5000)
                time.sleep(3)
            except Exception as e:
                print("   ⚠️ Could not click main Agents tab.")
                
        # 1. Scrape Super Agent Profile
        print("🤖 Scraping Super Agent profile...")
        scraped_data["super_agent"] = page.locator("body").inner_text()[:15000]
        
        # 2. Navigate to sub-agents list
        try:
            print("   Clicking Sub-Agents menu...")
            # Usually there is an "Agents" sub-menu under "Super agent"
            agents_submenu = page.locator('div:text-is("Agents")')
            if agents_submenu.count() > 0:
                # Click the second one if the first is the main nav
                target = agents_submenu.nth(1) if agents_submenu.count() > 1 else agents_submenu.first()
                target.click()
            else:
                page.click('span:text-is("Agents")')
            time.sleep(3)
        except Exception as e:
            print(f"   ⚠️ Could not click sub-agents menu: {e}")

        # 3. Iterate through all agents
        print("🕵️  Finding all sub-agents...")
        # Find all agent cards/rows. Usually they have a specific class, or we can look for role elements
        agent_elements = page.locator('td[role="cell"] a, div[class*="agentName"], div:has-text("Agent name") + div')
        
        # If specific selectors fail, grab all links that look like agent names (often inside a table or grid)
        if agent_elements.count() == 0:
            agent_elements = page.locator('table tbody tr')
            
        num_agents = agent_elements.count()
        print(f"   Found {num_agents} potential agents.")
        
        for i in range(num_agents):
            try:
                # Need to re-query the locators because DOM might change after going back
                current_elements = page.locator('table tbody tr')
                if current_elements.count() <= i:
                    break
                    
                agent_row = current_elements.nth(i)
                agent_name = agent_row.inner_text().split("\n")[0]
                
                print(f"   👉 Scraping Agent: {agent_name}")
                
                # Click the agent
                agent_row.click()
                time.sleep(4)
                
                # Scrape the agent configuration (Role, Prompt, etc.)
                agent_text = page.locator("body").inner_text()[:15000]
                
                scraped_data["agents"].append({
                    "name": agent_name,
                    "configuration": agent_text
                })
                
                # Go back to the agents list
                page.go_back()
                time.sleep(3)
                
            except Exception as e:
                print(f"   ❌ Failed to scrape agent {i}: {e}")

        # 4. Save the full dump
        out_file = os.path.join(OUTPUT_DIR, "full_agents_scrape.json")
        with open(out_file, "w") as f:
            json.dump(scraped_data, f, indent=2)
            
        print(f"\n🎉 Done! Full scrape saved to {out_file}")
        
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    scrape_full_dashboard()
