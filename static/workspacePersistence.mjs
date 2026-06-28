export const WORKSPACE_STATE_KEY = "botqa.workspace.v1";

const VALID_TABS = new Set(["analyzer", "testing", "docs"]);

function defaultStorage() {
  try {
    return globalThis.localStorage;
  } catch (_error) {
    return null;
  }
}

function defaultLocation() {
  try {
    return globalThis.location;
  } catch (_error) {
    return null;
  }
}

function defaultHistory() {
  try {
    return globalThis.history;
  } catch (_error) {
    return null;
  }
}

function safeString(value) {
  return typeof value === "string" ? value : "";
}

export function sanitizeWorkspaceState(value = {}) {
  const state = value && typeof value === "object" ? value : {};
  return {
    activeTab: VALID_TABS.has(state.activeTab) ? state.activeTab : "analyzer",
    activeProjectId: safeString(state.activeProjectId),
    activeChatId: safeString(state.activeChatId),
    activeDocsChatId: safeString(state.activeDocsChatId),
  };
}

function readHashState(locationLike = defaultLocation()) {
  try {
    const hash = safeString(locationLike?.hash).replace(/^#/, "");
    if (!hash) return null;
    const params = new URLSearchParams(hash);
    if (!params.has("tab") && !params.has("project") && !params.has("chat") && !params.has("docs")) {
      return null;
    }
    return sanitizeWorkspaceState({
      activeTab: params.get("tab"),
      activeProjectId: params.get("project"),
      activeChatId: params.get("chat"),
      activeDocsChatId: params.get("docs"),
    });
  } catch (_error) {
    return null;
  }
}

export function readWorkspaceState(storage = defaultStorage(), locationLike = defaultLocation()) {
  const hashState = readHashState(locationLike);
  if (hashState) return hashState;
  try {
    if (!storage?.getItem) return sanitizeWorkspaceState();
    const raw = storage.getItem(WORKSPACE_STATE_KEY);
    return raw ? sanitizeWorkspaceState(JSON.parse(raw)) : sanitizeWorkspaceState();
  } catch (_error) {
    return sanitizeWorkspaceState();
  }
}

function buildHash(state) {
  const params = new URLSearchParams();
  if (state.activeTab) params.set("tab", state.activeTab);
  if (state.activeProjectId) params.set("project", state.activeProjectId);
  if (state.activeChatId) params.set("chat", state.activeChatId);
  if (state.activeDocsChatId) params.set("docs", state.activeDocsChatId);
  return params.toString();
}

function writeHashState(state, historyLike = defaultHistory(), locationLike = defaultLocation()) {
  try {
    if (!historyLike?.replaceState || !locationLike) return;
    const hash = buildHash(state);
    const nextUrl = `${locationLike.pathname || "/"}${locationLike.search || ""}${hash ? `#${hash}` : ""}`;
    historyLike.replaceState(null, "", nextUrl);
  } catch (_error) {
    // Hash persistence is best effort, just like localStorage.
  }
}

export function writeWorkspaceState(state, storage = defaultStorage(), historyLike = defaultHistory(), locationLike = defaultLocation()) {
  const sanitized = sanitizeWorkspaceState(state);
  try {
    if (storage?.setItem) {
      storage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(sanitized));
    }
  } catch (_error) {
    // Private browsing or blocked storage should not break the app shell.
  }
  writeHashState(sanitized, historyLike, locationLike);
  return sanitized;
}
