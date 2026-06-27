var BotQAApp = (() => {
  // static/App.jsx
  var { useEffect, useMemo, useRef, useState } = React;
  var emptyProfile = {
    bot_name: "Yellow.ai Support Bot",
    chat_endpoint: "",
    chat_launcher_selector: "",
    chat_input_selector: "",
    chat_message_selector: "",
    chat_send_selector: "",
    chat_frame_hint: "",
    chat_ready_selector: "",
    chat_response_timeout_seconds: "40",
    chat_stability_seconds: "2",
    chat_playwright_headless: "true",
    chat_case_count: "12",
    yellow_ai_ui_base_url: "https://cloud.yellow.ai",
    yellow_ai_console_url: "",
    platform_snapshot_headless: "true",
    platform_snapshot_max_pages: "10",
    yellow_ai_platform: "nexus",
    yellow_ai_bot_id: "",
    yellow_ai_environment: "",
    yellow_ai_super_agent: "",
    yellow_ai_agent_name: "",
    yellow_ai_tool_name: "",
    yellow_ai_workflow_name: "",
    yellow_ai_workflow_id: "",
    yellow_ai_kb_name: "",
    business_goal: "Help users resolve support requests without needing a human agent unless the issue is complex.",
    flow_docs: "Order status, cancel order, refund status, complaint, agent handoff, fallback recovery."
  };
  function localDateInputValue(offsetDays = 0) {
    const date = /* @__PURE__ */ new Date();
    date.setDate(date.getDate() + offsetDays);
    return new Date(date.getTime() - date.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
  }
  function defaultDateFrom(daysBack = 7) {
    const parsed = Math.max(1, Number.parseInt(daysBack, 10) || 7);
    return localDateInputValue(-(parsed - 1));
  }
  var defaultChatAutomationScript = `## Greeting and scope

#### Conversation Flow

###### Turn 1
**User:**
>> Hi, what can you help me with?

**Bot:**
>> Bot greets the user and explains the support scope or asks what help is needed.

------
## Product recommendation

#### Conversation Flow

###### Turn 1
**User:**
>> I am looking for a water purifier for a small family. Can you guide me?

**Bot:**
>> Bot asks about user needs or recommends relevant product categories, features, or next steps.

------
## Service issue

#### Conversation Flow

###### Turn 1
**User:**
>> My purifier is not working and I need service support.

**Bot:**
>> Bot acknowledges the service issue and asks for product, location, contact, warranty, or service booking details.

------
## Installation request

#### Conversation Flow

###### Turn 1
**User:**
>> I bought a purifier and need installation help.

**Bot:**
>> Bot guides installation scheduling or asks for contact, address, and product details.

------
## Unsupported order tracking

#### Conversation Flow

###### Turn 1
**User:**
>> Track my order ID ORD12345.

**Bot:**
>> If order tracking is unavailable, bot explains the limitation and offers a useful next step or support handoff.

------
## Customer care handoff

#### Conversation Flow

###### Turn 1
**User:**
>> I want to speak to a human customer care agent.

**Bot:**
>> Bot offers customer care details, escalation, or asks enough information to route the user to support.

------
## Fallback clarification

#### Conversation Flow

###### Turn 1
**User:**
>> blorpy invoice magic banana.

**Bot:**
>> Bot handles the unclear request with a clarification question and does not invent unsupported information.
`;
  async function api(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
    const response = await fetch(path, { credentials: "same-origin", headers, ...options });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ error: response.statusText }));
      const error = new Error(body.error || response.statusText);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  function projectQuery(path, projectId) {
    const sep = path.includes("?") ? "&" : "?";
    return `${path}${sep}project_id=${encodeURIComponent(projectId || "")}`;
  }
  function prependUniqueById(items, item) {
    if (!item?.id) return items;
    return [item, ...items.filter((current) => current.id !== item.id)];
  }
  function cx(...parts) {
    return parts.filter(Boolean).join(" ");
  }
  function Pill({ children, tone = "" }) {
    return /* @__PURE__ */ React.createElement("span", { className: cx("pill", tone) }, children);
  }
  function Icon({ name, filled = false }) {
    return /* @__PURE__ */ React.createElement("span", { className: "material-symbols-outlined", style: { fontVariationSettings: `'FILL' ${filled ? 1 : 0}` } }, name);
  }
  function App() {
    const [auth, setAuth] = useState({ loading: true, authenticated: false, user: null });
    const [activeTab, setActiveTab] = useState("analyzer");
    const [activeProjectId, setActiveProjectId] = useState("");
    const [activeChatId, setActiveChatId] = useState("");
    const [activeDocsChatId, setActiveDocsChatId] = useState("");
    const [projects, setProjects] = useState([]);
    const [chats, setChats] = useState([]);
    const [suites, setSuites] = useState([]);
    const [runs, setRuns] = useState([]);
    const [documents, setDocuments] = useState([]);
    const [changePlans, setChangePlans] = useState([]);
    const [platformSnapshots, setPlatformSnapshots] = useState([]);
    const [yellowAccess, setYellowAccess] = useState(null);
    const [voiceData, setVoiceData] = useState(null);
    const [docsPages, setDocsPages] = useState([]);
    const [config, setConfig] = useState(null);
    const [profile, setProfile] = useState(emptyProfile);
    const [latestReport, setLatestReport] = useState(null);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState("");
    const [error, setError] = useState("");
    const activeProject = useMemo(
      () => projects.find((project) => project.id === activeProjectId) || projects[0] || null,
      [projects, activeProjectId]
    );
    const analyzerChat = useMemo(() => chats.find((chat) => chat.id === activeChatId), [chats, activeChatId]);
    const docsChat = useMemo(() => chats.find((chat) => chat.id === activeDocsChatId), [chats, activeDocsChatId]);
    function resetWorkspace() {
      setActiveProjectId("");
      setActiveChatId("");
      setActiveDocsChatId("");
      setProjects([]);
      setChats([]);
      setSuites([]);
      setRuns([]);
      setDocuments([]);
      setChangePlans([]);
      setPlatformSnapshots([]);
      setYellowAccess(null);
      setVoiceData(null);
      setDocsPages([]);
      setConfig(null);
      setProfile(emptyProfile);
      setLatestReport(null);
      setSearch("");
    }
    async function refresh(options = {}) {
      let projectsPayload;
      try {
        projectsPayload = await api("/api/projects");
      } catch (err) {
        if (err.status === 401) {
          resetWorkspace();
          setAuth({ loading: false, authenticated: false, user: null });
        }
        throw err;
      }
      const nextProjects = projectsPayload.projects || [];
      const nextProjectId = options.projectId || (activeProjectId && nextProjects.some((project) => project.id === activeProjectId) ? activeProjectId : projectsPayload.active_project_id || nextProjects[0]?.id || "");
      const [chatsPayload, suitesPayload, runsPayload, docsPayload, snapshotsPayload, accessPayload, voicePayload, docsPagesPayload, configPayload] = await Promise.all([
        api(projectQuery("/api/chats", nextProjectId)),
        api(projectQuery("/api/suites", nextProjectId)),
        api(projectQuery("/api/runs", nextProjectId)),
        api(projectQuery("/api/documents", nextProjectId)),
        api(projectQuery("/api/platform-snapshots", nextProjectId)),
        api(projectQuery("/api/project-access", nextProjectId)),
        api(projectQuery("/api/voice", nextProjectId)),
        api("/api/docs/pages"),
        api("/api/config")
      ]);
      setProjects(nextProjects);
      setActiveProjectId(nextProjectId);
      setChats(chatsPayload.chats || []);
      setSuites(suitesPayload || []);
      setRuns(runsPayload || []);
      setDocuments(docsPayload.documents || []);
      setChangePlans(docsPayload.change_plans || []);
      setPlatformSnapshots(snapshotsPayload.snapshots || []);
      setYellowAccess(accessPayload);
      setVoiceData(voicePayload);
      setDocsPages(docsPagesPayload.pages || []);
      setConfig(configPayload);
      const nextProject = nextProjects.find((project) => project.id === nextProjectId) || nextProjects[0];
      setProfile({ ...emptyProfile, ...nextProject?.bot_profile || {} });
      const preferredAnalyzerId = options.activeChatId || activeChatId;
      const preferredDocsChatId = options.activeDocsChatId || activeDocsChatId;
      const analyzer = (chatsPayload.chats || []).find((chat) => chat.id === preferredAnalyzerId && chat.mode === "analyzer") || (chatsPayload.chats || []).find((chat) => chat.mode === "analyzer");
      const docs = (chatsPayload.chats || []).find((chat) => chat.id === preferredDocsChatId && chat.mode === "docs") || (chatsPayload.chats || []).find((chat) => chat.mode === "docs");
      setActiveChatId(analyzer?.id || "");
      setActiveDocsChatId(docs?.id || "");
      if (!options.keepReport) setLatestReport(null);
    }
    useEffect(() => {
      api("/api/auth/session").then(async (session) => {
        setAuth({ loading: false, authenticated: !!session.authenticated, user: session.user || null });
        if (session.authenticated) {
          await refresh({ keepReport: false });
        }
      }).catch((err) => {
        setAuth({ loading: false, authenticated: false, user: null });
        setError(err.message);
      });
    }, []);
    async function handleAuthenticated(session) {
      setAuth({ loading: false, authenticated: true, user: session.user });
      setError("");
      await refresh({ keepReport: false });
    }
    async function logout() {
      await guarded("logout", async () => {
        await api("/api/auth/logout", { method: "POST" });
        resetWorkspace();
        setAuth({ loading: false, authenticated: false, user: null });
      });
    }
    async function guarded(label, fn) {
      setLoading(label);
      setError("");
      try {
        await fn();
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading("");
      }
    }
    async function createProject() {
      const name = window.prompt("Project name", "New bot project");
      if (!name) return;
      await guarded("project", async () => {
        const project = await api("/api/projects", {
          method: "POST",
          body: JSON.stringify({ name, bot_profile: profile })
        });
        setActiveProjectId(project.id);
        setActiveChatId("");
        setActiveDocsChatId("");
        await refresh({ projectId: project.id, keepReport: false });
      });
    }
    async function createChat(mode) {
      const chat = await api("/api/chats", {
        method: "POST",
        body: JSON.stringify({ project_id: activeProjectId, mode })
      });
      await refresh({
        keepReport: true,
        activeChatId: mode === "analyzer" ? chat.id : activeChatId,
        activeDocsChatId: mode === "docs" ? chat.id : activeDocsChatId
      });
      if (mode === "docs") setActiveDocsChatId(chat.id);
      else setActiveChatId(chat.id);
      return chat;
    }
    async function ensureChat(mode) {
      const id = mode === "docs" ? activeDocsChatId : activeChatId;
      const existing = chats.find((chat) => chat.id === id && chat.mode === mode);
      return existing || createChat(mode);
    }
    async function sendMessage(mode, content) {
      if (!content.trim()) return;
      await guarded(mode === "docs" ? "docs-chat" : "analyzer-chat", async () => {
        const chat = await ensureChat(mode);
        const updated = await api(`/api/chats/${chat.id}/messages`, {
          method: "POST",
          body: JSON.stringify({ content: content.trim() })
        });
        setChats((current) => current.map((item) => item.id === updated.id ? updated : item));
        await refresh({
          keepReport: true,
          activeChatId: mode === "analyzer" ? updated.id : activeChatId,
          activeDocsChatId: mode === "docs" ? updated.id : activeDocsChatId
        });
        if (mode === "docs") setActiveDocsChatId(updated.id);
        else setActiveChatId(updated.id);
      });
    }
    async function saveProjectProfile() {
      await guarded("save-profile", async () => {
        await api(`/api/projects/${activeProjectId}`, {
          method: "PATCH",
          body: JSON.stringify({ bot_profile: profile })
        });
        await refresh({ keepReport: true });
      });
    }
    async function generateSuite(extraChatContext = false) {
      await guarded("generate-suite", async () => {
        const profilePayload = { ...profile };
        if (extraChatContext && analyzerChat?.messages?.length) {
          profilePayload.recent_analyzer_context = analyzerChat.messages.slice(-8).map((message) => `${message.role}: ${message.content}`).join("\n");
        }
        await api("/api/generate-suite", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, bot_profile: profilePayload })
        });
        setActiveTab("testing");
        await refresh({ keepReport: true });
      });
    }
    async function runSuite(suiteId, channel) {
      await guarded(`run-${suiteId}`, async () => {
        const output = await api("/api/run-suite", {
          method: "POST",
          body: JSON.stringify({ suite_id: suiteId, channel })
        });
        mergeRunOutput(output);
        await refresh({ keepReport: true });
        mergeRunOutput(output);
      });
    }
    async function runChatAutomation(script) {
      await guarded("chat-automation", async () => {
        const output = await api("/api/chat-automation/run", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, bot_profile: profile, script })
        });
        mergeRunOutput(output);
        await refresh({ keepReport: true });
        mergeRunOutput(output);
      });
    }
    async function runGoalChatAutomation(goalPayload) {
      await guarded("goal-chat-automation", async () => {
        const output = await api("/api/chat-automation/goal-run", {
          method: "POST",
          body: JSON.stringify({
            project_id: activeProjectId,
            bot_profile: profile,
            goal: goalPayload.goal,
            options: goalPayload
          })
        });
        mergeRunOutput(output);
        await refresh({ keepReport: true });
        mergeRunOutput(output);
      });
    }
    function mergeRunOutput(output) {
      if (!output) return;
      const suite = output.suite?.id ? { ...output.suite, project_id: output.suite.project_id || activeProjectId } : null;
      const run = output.run?.id ? { ...output.run, project_id: output.run.project_id || activeProjectId } : null;
      const report = output.report?.id ? { ...output.report, project_id: output.report.project_id || activeProjectId } : null;
      if (suite) setSuites((current) => prependUniqueById(current, suite));
      if (run) setRuns((current) => prependUniqueById(current, run));
      if (report) setLatestReport(report);
    }
    async function runPlatformSnapshot(options = {}) {
      await guarded("platform-snapshot", async () => {
        await api("/api/platform-snapshots/run", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, bot_profile: profile, options })
        });
        await refresh({ keepReport: true });
      });
    }
    async function runBotDiscovery(options = {}) {
      await guarded("bot-discovery", async () => {
        const output = await api("/api/bot-discovery/run", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, bot_profile: profile, options })
        });
        if (output.project?.id) {
          setProjects((current) => current.map((project) => project.id === output.project.id ? output.project : project));
          setProfile(output.project.bot_profile || profile);
        }
        await refresh({ keepReport: true });
      });
    }
    async function saveYellowAccess(access) {
      await guarded("yellow-access", async () => {
        const savedAccess = await api("/api/project-access", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, ...access })
        });
        if (savedAccess?.bot_id) {
          const discoveredProfile = {
            ...profile,
            yellow_ai_bot_id: savedAccess.bot_id,
            yellow_ai_environment: savedAccess.environment || profile.yellow_ai_environment,
            yellow_ai_ui_base_url: savedAccess.ui_base_url || profile.yellow_ai_ui_base_url || "https://cloud.yellow.ai",
            yellow_ai_console_url: savedAccess.console_url || profile.yellow_ai_console_url,
            chat_endpoint: savedAccess.chat_widget_url || profile.chat_endpoint
          };
          try {
            await api("/api/bot-discovery/run", {
              method: "POST",
              body: JSON.stringify({ project_id: activeProjectId, bot_profile: discoveredProfile, options: { headless: true } })
            });
          } catch (discoveryError) {
            console.warn("Bot discovery could not complete after saving access", discoveryError);
          }
        }
        await refresh({ keepReport: true });
      });
    }
    async function saveVoiceAccess(access) {
      await guarded("voice-access", async () => {
        const output = await api("/api/voice/access", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, ...access })
        });
        setVoiceData((current) => ({ ...current || {}, access: output }));
        await refresh({ keepReport: true });
      });
    }
    async function syncVoiceCalls(options) {
      await guarded("voice-sync", async () => {
        const output = await api("/api/voice/sync", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, ...options })
        });
        if (output.voice) setVoiceData(output.voice);
        mergeRunOutput(output);
        await refresh({ keepReport: true });
        mergeRunOutput(output);
      });
    }
    async function openReport(reportId) {
      await guarded("report", async () => {
        setLatestReport(await api(`/api/reports/${reportId}`));
      });
    }
    async function uploadDocument(file) {
      if (!file) return;
      await guarded("upload", async () => {
        const payload = new FormData();
        payload.append("document", file);
        payload.append("project_id", activeProjectId);
        await fetch("/api/documents/upload", { method: "POST", credentials: "same-origin", body: payload }).then(async (response) => {
          if (!response.ok) {
            const body = await response.json().catch(() => ({ error: response.statusText }));
            throw new Error(body.error || response.statusText);
          }
        });
        await refresh({ keepReport: true });
      });
    }
    async function analyzeDocument(documentId) {
      await guarded("analyze-doc", async () => {
        await api("/api/documents/analyze", {
          method: "POST",
          body: JSON.stringify({ project_id: activeProjectId, document_id: documentId, bot_profile: profile })
        });
        await refresh({ keepReport: true });
      });
    }
    async function approvePlan(planId) {
      await guarded("approve-plan", async () => {
        await api(`/api/change-plans/${planId}/approve`, { method: "POST" });
        await refresh({ keepReport: true });
      });
    }
    async function attachReport(reportId) {
      const selectedReportId = reportId || runs[0]?.report_id;
      if (!selectedReportId) {
        setError("Run a suite first so there is a report to attach.");
        return;
      }
      await sendMessage(
        "analyzer",
        `Pinpoint failures in report ${selectedReportId}. Do not give a generic summary first. For each failed or review case, tell me the exact failed turn, expected vs actual behavior, likely Yellow.ai agent/step/workflow/API/function/KB location, concrete root cause, exact fix, and the regression test to rerun. Use platform snapshots when available and name the exact missing Yellow.ai page or debug log if evidence is not enough.`
      );
    }
    async function prepareGoalBrief() {
      if (!activeProjectId) return;
      await guarded("goal-brief", async () => {
        const output = await api(`/api/projects/${activeProjectId}/goal-brief`, {
          method: "POST",
          body: JSON.stringify({ chat_id: activeChatId })
        });
        if (output.project?.id) {
          setProjects((current) => current.map((project) => project.id === output.project.id ? output.project : project));
        }
        setActiveTab("testing");
        await refresh({ keepReport: true });
      });
    }
    if (auth.loading) {
      return /* @__PURE__ */ React.createElement(SplashScreen, null);
    }
    if (!auth.authenticated) {
      return /* @__PURE__ */ React.createElement(AuthScreen, { onAuthenticated: handleAuthenticated });
    }
    return /* @__PURE__ */ React.createElement("div", { className: "appShell" }, /* @__PURE__ */ React.createElement(
      Sidebar,
      {
        user: auth.user,
        activeTab,
        setActiveTab,
        projects,
        activeProjectId,
        setProject: (projectId) => {
          setActiveProjectId(projectId);
          setActiveChatId("");
          setActiveDocsChatId("");
          refresh({ projectId, keepReport: false }).catch((err) => setError(err.message));
        },
        chats,
        activeChatId: activeTab === "docs" ? activeDocsChatId : activeChatId,
        setChat: (chat) => chat.mode === "docs" ? setActiveDocsChatId(chat.id) : setActiveChatId(chat.id),
        search,
        setSearch,
        createProject,
        createChat: () => createChat(activeTab === "docs" ? "docs" : "analyzer").catch((err) => setError(err.message)),
        openSettings: () => document.querySelector("#settingsDialog")?.showModal(),
        refresh: () => refresh({ keepReport: true }).catch((err) => setError(err.message)),
        logout
      }
    ), /* @__PURE__ */ React.createElement("main", { className: "workspace" }, /* @__PURE__ */ React.createElement(TopBar, { activeTab, activeProject, loading, error }), activeTab === "analyzer" && /* @__PURE__ */ React.createElement(
      AnalyzerTab,
      {
        chat: analyzerChat,
        sendMessage: (content) => sendMessage("analyzer", content),
        createSuite: () => generateSuite(true),
        attachReport,
        prepareGoalBrief,
        activeProject,
        documents,
        changePlans,
        suites,
        runs,
        platformSnapshots,
        yellowAccess,
        saveYellowAccess,
        runBotDiscovery,
        runPlatformSnapshot,
        config,
        loading
      }
    ), activeTab === "testing" && /* @__PURE__ */ React.createElement(
      TestingTab,
      {
        profile,
        setProfile,
        saveProfile: saveProjectProfile,
        generateSuite: (channel) => generateSuite(false, channel),
        suites,
        runs,
        latestReport,
        runSuite,
        runChatAutomation,
        runGoalChatAutomation,
        voiceData,
        saveVoiceAccess,
        syncVoiceCalls,
        goalBrief: activeProject?.goal_test_brief,
        openReport,
        config,
        loading
      }
    ), activeTab === "docs" && /* @__PURE__ */ React.createElement(
      DocsTab,
      {
        docsPages,
        documents,
        changePlans,
        uploadDocument,
        analyzeDocument,
        approvePlan,
        activeProjectId,
        chat: docsChat,
        sendMessage: (content) => sendMessage("docs", content),
        createDocsChat: () => createChat("docs").catch((err) => setError(err.message)),
        loading
      }
    )), /* @__PURE__ */ React.createElement(SettingsDialog, { config, setConfig, setError }));
  }
  function SplashScreen() {
    return /* @__PURE__ */ React.createElement("main", { className: "authShell" }, /* @__PURE__ */ React.createElement("section", { className: "authCard compact" }, /* @__PURE__ */ React.createElement("div", { className: "authBrand" }, /* @__PURE__ */ React.createElement("div", { className: "brandMark" }, "QA"), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", null, "QA Workbench"), /* @__PURE__ */ React.createElement("p", null, "Loading workspace")))));
  }
  function AuthScreen({ onAuthenticated }) {
    const [mode, setMode] = useState("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    async function submit(event) {
      event.preventDefault();
      setBusy(true);
      setError("");
      try {
        const session = await api(mode === "signup" ? "/api/auth/signup" : "/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName })
        });
        await onAuthenticated(session);
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }
    return /* @__PURE__ */ React.createElement("main", { className: "authShell" }, /* @__PURE__ */ React.createElement("section", { className: "authCard" }, /* @__PURE__ */ React.createElement("div", { className: "authBrand" }, /* @__PURE__ */ React.createElement("div", { className: "brandMark" }, "QA"), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", null, "QA Workbench"), /* @__PURE__ */ React.createElement("p", null, "Sign in to your projects, chats, tests, and reports."))), /* @__PURE__ */ React.createElement("div", { className: "authTabs" }, /* @__PURE__ */ React.createElement("button", { className: cx(mode === "login" && "active"), type: "button", onClick: () => setMode("login") }, "Login"), /* @__PURE__ */ React.createElement("button", { className: cx(mode === "signup" && "active"), type: "button", onClick: () => setMode("signup") }, "Sign up")), /* @__PURE__ */ React.createElement("form", { className: "authForm", onSubmit: submit }, mode === "signup" && /* @__PURE__ */ React.createElement(Field, { label: "Name" }, /* @__PURE__ */ React.createElement("input", { value: fullName, onChange: (event) => setFullName(event.target.value), placeholder: "Your name" })), /* @__PURE__ */ React.createElement(Field, { label: "Email" }, /* @__PURE__ */ React.createElement("input", { type: "email", value: email, onChange: (event) => setEmail(event.target.value), placeholder: "you@company.com", autoComplete: "email" })), /* @__PURE__ */ React.createElement(Field, { label: "Password" }, /* @__PURE__ */ React.createElement(
      "input",
      {
        type: "password",
        value: password,
        onChange: (event) => setPassword(event.target.value),
        placeholder: "Minimum 8 characters",
        autoComplete: mode === "signup" ? "new-password" : "current-password"
      }
    )), error && /* @__PURE__ */ React.createElement("div", { className: "authError" }, error), /* @__PURE__ */ React.createElement("button", { type: "submit", disabled: busy }, busy ? "Please wait" : mode === "signup" ? "Create account" : "Login"))));
  }
  function Sidebar(props) {
    const mode = props.activeTab === "docs" ? "docs" : "analyzer";
    const filteredChats = props.chats.filter((chat) => chat.mode === mode).filter((chat) => !props.search.trim() || chat.title.toLowerCase().includes(props.search.trim().toLowerCase()));
    return /* @__PURE__ */ React.createElement("aside", { className: "sidebar" }, /* @__PURE__ */ React.createElement("div", { className: "sideBrand" }, /* @__PURE__ */ React.createElement("div", { className: "brandMark" }, "QA"), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, "QA Workbench"), /* @__PURE__ */ React.createElement("span", null, "V2.4.0"))), /* @__PURE__ */ React.createElement("button", { className: "primarySideButton", type: "button", onClick: props.createProject }, /* @__PURE__ */ React.createElement(Icon, { name: "add" }), " New project"), /* @__PURE__ */ React.createElement("button", { className: "sideAction", type: "button", onClick: props.createChat }, /* @__PURE__ */ React.createElement(Icon, { name: "chat" }), " New chat"), /* @__PURE__ */ React.createElement("label", { className: "sideSearch" }, "Search", /* @__PURE__ */ React.createElement("input", { value: props.search, onChange: (event) => props.setSearch(event.target.value), placeholder: "Search chats" })), /* @__PURE__ */ React.createElement("nav", { className: "sideNav" }, [
      ["analyzer", "analytics", "Analyzer"],
      ["testing", "science", "Testing"],
      ["docs", "description", "Docs"]
    ].map(([tab, icon, label]) => /* @__PURE__ */ React.createElement("button", { key: tab, className: cx("navButton", props.activeTab === tab && "active"), type: "button", onClick: () => props.setActiveTab(tab) }, /* @__PURE__ */ React.createElement(Icon, { name: icon, filled: props.activeTab === tab }), " ", label))), /* @__PURE__ */ React.createElement(SectionTitle, { label: "Projects" }), /* @__PURE__ */ React.createElement("div", { className: "sideList projectList" }, props.projects.map((project) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: project.id,
        className: cx("sideListItem", project.id === props.activeProjectId && "active"),
        type: "button",
        onClick: () => props.setProject(project.id)
      },
      /* @__PURE__ */ React.createElement("span", null, project.name),
      /* @__PURE__ */ React.createElement("small", null, project.yellow_ai_target?.platform || "local")
    ))), /* @__PURE__ */ React.createElement(SectionTitle, { label: "Chats" }), /* @__PURE__ */ React.createElement("div", { className: "sideList chatList" }, filteredChats.length ? filteredChats.map((chat) => /* @__PURE__ */ React.createElement("button", { key: chat.id, className: cx("sideListItem", chat.id === props.activeChatId && "active"), type: "button", onClick: () => props.setChat(chat) }, /* @__PURE__ */ React.createElement("span", null, chat.title), /* @__PURE__ */ React.createElement("small", null, chat.mode))) : /* @__PURE__ */ React.createElement("div", { className: "sideEmpty" }, "No ", mode, " chats yet")), /* @__PURE__ */ React.createElement("div", { className: "sidebarBottom" }, /* @__PURE__ */ React.createElement("div", { className: "userBadge" }, /* @__PURE__ */ React.createElement(Icon, { name: "account_circle" }), /* @__PURE__ */ React.createElement("span", null, props.user?.email || "Signed in")), /* @__PURE__ */ React.createElement("button", { className: "sideAction ghost", type: "button", onClick: props.openSettings }, /* @__PURE__ */ React.createElement(Icon, { name: "settings" }), " Settings"), /* @__PURE__ */ React.createElement("button", { className: "sideAction ghost", type: "button", onClick: props.refresh }, /* @__PURE__ */ React.createElement(Icon, { name: "refresh" }), " Refresh"), /* @__PURE__ */ React.createElement("button", { className: "sideAction ghost", type: "button", onClick: props.logout }, /* @__PURE__ */ React.createElement(Icon, { name: "logout" }), " Logout")));
  }
  function SectionTitle({ label }) {
    return /* @__PURE__ */ React.createElement("div", { className: "sideSectionHeader" }, label);
  }
  function TopBar({ activeTab, activeProject, loading, error }) {
    return /* @__PURE__ */ React.createElement("header", { className: "topBar" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", null, activeTab === "analyzer" ? "QA Analyzer" : activeTab === "testing" ? "Test Execution Board" : "Documentation Hub"), /* @__PURE__ */ React.createElement("p", null, activeProject?.name || "Yellow.ai Chat QA Workbench")), /* @__PURE__ */ React.createElement("div", { className: "topBarMeta" }, error && /* @__PURE__ */ React.createElement("span", { className: "statusPill error" }, error), loading && /* @__PURE__ */ React.createElement("span", { className: "statusPill warn" }, "Working"), /* @__PURE__ */ React.createElement("span", { className: "statusPill" }, "Local MVP")));
  }
  function AnalyzerTab({ chat, sendMessage, createSuite, attachReport, prepareGoalBrief, activeProject, documents, changePlans, suites, runs, platformSnapshots, yellowAccess, saveYellowAccess, runBotDiscovery, runPlatformSnapshot, config, loading }) {
    const [message, setMessage] = useState("");
    const [showReportPicker, setShowReportPicker] = useState(false);
    function chooseReport(reportId) {
      setShowReportPicker(false);
      attachReport(reportId);
    }
    return /* @__PURE__ */ React.createElement("div", { className: "mainGrid analyzerGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel chatPanel" }, /* @__PURE__ */ React.createElement(
      PanelHeader,
      {
        title: "Analyzer Session",
        meta: "SESSION ID: PROJECT-CONTEXT",
        actions: /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: () => setShowReportPicker(true) }, /* @__PURE__ */ React.createElement(Icon, { name: "troubleshoot" }), " Pinpoint report"), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "goal-brief", onClick: prepareGoalBrief }, /* @__PURE__ */ React.createElement(Icon, { name: "assignment" }), " Prepare test brief"), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: createSuite }, /* @__PURE__ */ React.createElement(Icon, { name: "science" }), " Create suite"), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "platform-snapshot", onClick: () => runPlatformSnapshot({ headless: false, wait_for_login: true }) }, /* @__PURE__ */ React.createElement(Icon, { name: "login" }), " Connect session"), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "platform-snapshot", onClick: () => runPlatformSnapshot() }, /* @__PURE__ */ React.createElement(Icon, { name: "travel_explore" }), " Run snapshot"))
      }
    ), /* @__PURE__ */ React.createElement(YellowAccessPrompt, { access: yellowAccess, saveYellowAccess, runBotDiscovery, loading }), /* @__PURE__ */ React.createElement(ChatMessages, { chat, empty: "Start an analyzer chat for Yellow.ai docs, reports, RAG checks, or test planning." }), /* @__PURE__ */ React.createElement(
      "form",
      {
        className: "chatComposer",
        onSubmit: (event) => {
          event.preventDefault();
          sendMessage(message);
          setMessage("");
        }
      },
      /* @__PURE__ */ React.createElement("textarea", { value: message, onChange: (event) => setMessage(event.target.value), placeholder: "Ask the analyzer what to inspect, test, or improve..." }),
      /* @__PURE__ */ React.createElement("button", { type: "submit", disabled: loading === "analyzer-chat" }, "Send")
    ), showReportPicker && /* @__PURE__ */ React.createElement(
      ReportPickerDialog,
      {
        runs,
        suites,
        loading,
        onChoose: chooseReport,
        onClose: () => setShowReportPicker(false)
      }
    )), /* @__PURE__ */ React.createElement("aside", { className: "workPanel contextPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Project Context", meta: "ATTACHED KNOWLEDGE" }), /* @__PURE__ */ React.createElement(ContextPanel, { activeProject, documents, changePlans, suites, runs, platformSnapshots, yellowAccess, config })));
  }
  function ReportPickerDialog({ runs, suites, loading, onChoose, onClose }) {
    const [query, setQuery] = useState("");
    const suiteById = useMemo(() => {
      const lookup = {};
      suites.forEach((suite) => {
        lookup[suite.id] = suite;
      });
      return lookup;
    }, [suites]);
    const filteredRuns = runs.filter((run) => {
      const suiteName = suiteById[run.suite_id]?.name || "";
      const haystack = `${run.report_id || ""} ${run.id || ""} ${run.suite_id || ""} ${suiteName}`.toLowerCase();
      return haystack.includes(query.trim().toLowerCase());
    });
    return /* @__PURE__ */ React.createElement("div", { className: "modalOverlay", role: "presentation", onMouseDown: onClose }, /* @__PURE__ */ React.createElement("section", { className: "reportPickerDialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "report-picker-title", onMouseDown: (event) => event.stopPropagation() }, /* @__PURE__ */ React.createElement("div", { className: "dialogHeader" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h2", { id: "report-picker-title" }, "Pinpoint Report"), /* @__PURE__ */ React.createElement("p", null, "Pick the report Analyzer should inspect for exact Yellow.ai failure points.")), /* @__PURE__ */ React.createElement("button", { className: "iconButton", type: "button", "aria-label": "Close report picker", onClick: onClose }, /* @__PURE__ */ React.createElement(Icon, { name: "close" }))), /* @__PURE__ */ React.createElement("div", { className: "reportPickerBody" }, /* @__PURE__ */ React.createElement(Field, { label: "Search reports" }, /* @__PURE__ */ React.createElement("input", { value: query, onChange: (event) => setQuery(event.target.value), placeholder: "report id, run id, or suite name", autoFocus: true })), /* @__PURE__ */ React.createElement("div", { className: "reportChoiceList" }, filteredRuns.map((run) => {
      const suite = suiteById[run.suite_id];
      return /* @__PURE__ */ React.createElement("button", { className: "reportChoice", type: "button", key: `${run.id}-${run.report_id}`, disabled: loading === "analyzer-chat", onClick: () => onChoose(run.report_id) }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, run.report_id || "No report id"), /* @__PURE__ */ React.createElement("span", null, suite?.name || run.suite_id || "Generated report"), /* @__PURE__ */ React.createElement("small", null, run.created_at || "No timestamp", " \xB7 ", run.id)), /* @__PURE__ */ React.createElement("div", { className: "reportChoiceMeta" }, /* @__PURE__ */ React.createElement(Pill, { tone: run.average_score >= 0.78 ? "ok" : "warn" }, run.average_score ?? "-"), /* @__PURE__ */ React.createElement(Pill, null, run.total_cases ?? 0, " cases"), /* @__PURE__ */ React.createElement(Icon, { name: "add_link" })));
    }), !filteredRuns.length && /* @__PURE__ */ React.createElement(
      EmptyState,
      {
        title: runs.length ? "No matching reports" : "No reports yet",
        text: runs.length ? "Try another report id, run id, or suite name." : "Run a chat test first, then attach the generated report here."
      }
    )))));
  }
  function YellowAccessPrompt({ access, saveYellowAccess, runBotDiscovery, loading }) {
    const accessReady = Boolean(access?.bot_id && access?.api_key_configured);
    const [expanded, setExpanded] = useState(!accessReady);
    const [values, setValues] = useState({
      bot_id: "",
      api_key: "",
      ui_base_url: "https://cloud.yellow.ai",
      console_url: "",
      chat_widget_url: "",
      environment: ""
    });
    useEffect(() => {
      if (!access) return;
      setValues((current) => ({
        ...current,
        bot_id: access.bot_id || "",
        api_key: "",
        ui_base_url: access.ui_base_url || "https://cloud.yellow.ai",
        console_url: access.console_url || "",
        chat_widget_url: access.chat_widget_url || "",
        environment: access.environment || ""
      }));
      setExpanded(!(access.bot_id && access.api_key_configured));
    }, [access]);
    const update = (key, value) => setValues((current) => ({ ...current, [key]: value }));
    function submit(event) {
      event.preventDefault();
      saveYellowAccess(values).then(() => setExpanded(false));
    }
    if (accessReady && !expanded) {
      return /* @__PURE__ */ React.createElement("div", { className: "chatAccessPrompt ready compact" }, /* @__PURE__ */ React.createElement("div", { className: "assistantBubble" }, /* @__PURE__ */ React.createElement(Icon, { name: "verified" }), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, "Yellow.ai access is saved for this project."), /* @__PURE__ */ React.createElement("p", null, "Bot ", access.bot_id, " is ready for platform snapshots and failure analysis context."))), /* @__PURE__ */ React.createElement("div", { className: "accessActions" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, "API key saved"), /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, access.environment || "environment optional")), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: () => setExpanded(true) }, /* @__PURE__ */ React.createElement(Icon, { name: "edit" }), " Update access"), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "bot-discovery", onClick: () => runBotDiscovery({ headless: true }) }, /* @__PURE__ */ React.createElement(Icon, { name: "auto_awesome" }), " ", loading === "bot-discovery" ? "Discovering..." : "Discover bot")));
    }
    return /* @__PURE__ */ React.createElement("form", { className: cx("chatAccessPrompt", accessReady && "ready"), onSubmit: submit }, /* @__PURE__ */ React.createElement("div", { className: "assistantBubble" }, /* @__PURE__ */ React.createElement(Icon, { name: accessReady ? "verified" : "vpn_key" }), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, accessReady ? "Yellow.ai access is saved for this project." : "Share this bot's Yellow.ai access here."), /* @__PURE__ */ React.createElement("p", null, accessReady ? "You can update it here whenever this project points to a different bot." : "Analyzer uses this project-level access for platform snapshots and failure root-cause context."))), /* @__PURE__ */ React.createElement("div", { className: "accessGrid" }, /* @__PURE__ */ React.createElement(Field, { label: "Bot ID" }, /* @__PURE__ */ React.createElement("input", { value: values.bot_id, onChange: (event) => update("bot_id", event.target.value), placeholder: "x177..." })), /* @__PURE__ */ React.createElement(Field, { label: "Bot API key" }, /* @__PURE__ */ React.createElement("input", { type: "password", value: values.api_key, onChange: (event) => update("api_key", event.target.value), placeholder: access?.api_key_configured ? "Saved. Leave blank to keep current key." : "Yellow.ai bot API key" })), /* @__PURE__ */ React.createElement(Field, { label: "Yellow.ai UI base" }, /* @__PURE__ */ React.createElement("input", { value: values.ui_base_url, onChange: (event) => update("ui_base_url", event.target.value), placeholder: "https://cloud.yellow.ai" })), /* @__PURE__ */ React.createElement(Field, { label: "Console URL" }, /* @__PURE__ */ React.createElement("input", { value: values.console_url, onChange: (event) => update("console_url", event.target.value), placeholder: "Optional direct Studio/Automation URL" })), /* @__PURE__ */ React.createElement(Field, { label: "Chat widget URL" }, /* @__PURE__ */ React.createElement("input", { value: values.chat_widget_url, onChange: (event) => update("chat_widget_url", event.target.value), placeholder: "Optional liveBot/widget URL" })), /* @__PURE__ */ React.createElement(Field, { label: "Environment" }, /* @__PURE__ */ React.createElement("input", { value: values.environment, onChange: (event) => update("environment", event.target.value), placeholder: "staging / prod" }))), /* @__PURE__ */ React.createElement("div", { className: "accessActions" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: access?.api_key_configured ? "ok" : "warn" }, access?.api_key_configured ? "API key saved" : "API key needed"), /* @__PURE__ */ React.createElement(Pill, { tone: access?.bot_id ? "ok" : "warn" }, access?.bot_id ? "Bot ID saved" : "Bot ID needed")), /* @__PURE__ */ React.createElement("button", { type: "submit", disabled: loading === "yellow-access" }, /* @__PURE__ */ React.createElement(Icon, { name: "save" }), " Save access")));
  }
  function ContextPanel({ activeProject, documents, changePlans, suites, runs, platformSnapshots, yellowAccess, config }) {
    const target = activeProject?.yellow_ai_target || {};
    const latestSnapshot = platformSnapshots[0];
    const goalBrief = activeProject?.goal_test_brief;
    const botDiscovery = activeProject?.bot_discovery;
    return /* @__PURE__ */ React.createElement("div", { className: "contextStack" }, /* @__PURE__ */ React.createElement("div", { className: "metricGrid" }, /* @__PURE__ */ React.createElement(Metric, { label: "Docs", value: documents.length }), /* @__PURE__ */ React.createElement(Metric, { label: "Plans", value: changePlans.length }), /* @__PURE__ */ React.createElement(Metric, { label: "Suites", value: suites.length }), /* @__PURE__ */ React.createElement(Metric, { label: "Snapshots", value: platformSnapshots.length })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock specialistModeBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Analyzer Mode"), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, "Read-only"), /* @__PURE__ */ React.createElement(Pill, null, "Diagnose"), /* @__PURE__ */ React.createElement(Pill, null, "Recommend"), /* @__PURE__ */ React.createElement(Pill, null, "Test")), /* @__PURE__ */ React.createElement("p", null, "Analyzer can pinpoint Yellow.ai issues and suggest exact fixes, but it will not edit Studio, publish, or mutate production.")), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Yellow.ai Target"), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, Object.keys(target).length ? Object.entries(target).map(([key, value]) => /* @__PURE__ */ React.createElement(Pill, { key }, key.replaceAll("_", " "), ": ", value)) : /* @__PURE__ */ React.createElement(Pill, null, "No target saved"))), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Bot Discovery"), botDiscovery?.id ? /* @__PURE__ */ React.createElement("div", { className: "snapshotSummary" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, "discovered"), /* @__PURE__ */ React.createElement(Pill, null, botDiscovery.id)), /* @__PURE__ */ React.createElement("p", null, botDiscovery.summary)) : /* @__PURE__ */ React.createElement(EmptyState, { title: "No bot discovery", text: "Save bot access, then run Discover bot to build project context automatically." })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Provider Status"), /* @__PURE__ */ React.createElement("div", { className: "statusRows" }, /* @__PURE__ */ React.createElement(StatusRow, { label: "OpenAI", ready: config?.openai?.configured, value: config?.openai?.provider || "openai" }), /* @__PURE__ */ React.createElement(StatusRow, { label: "Playwright", ready: config?.playwright?.available, value: config?.playwright?.package || "browser runner" }), /* @__PURE__ */ React.createElement(StatusRow, { label: "Yellow.ai Access", ready: Boolean(yellowAccess?.bot_id && yellowAccess?.api_key_configured), value: yellowAccess?.bot_id || "ask in chat" }), /* @__PURE__ */ React.createElement(StatusRow, { label: "Platform Snapshot", ready: config?.platform_snapshot?.available, value: config?.platform_snapshot?.package || "crawler" }), /* @__PURE__ */ React.createElement(StatusRow, { label: "Storage", ready: config?.storage?.configured, value: config?.storage?.provider || "local_json" }))), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Latest Platform Snapshot"), latestSnapshot ? /* @__PURE__ */ React.createElement("div", { className: "snapshotSummary" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: latestSnapshot.status === "ok" ? "ok" : "warn" }, latestSnapshot.status), /* @__PURE__ */ React.createElement(Pill, null, latestSnapshot.page_count || 0, " pages"), /* @__PURE__ */ React.createElement(Pill, null, latestSnapshot.network_event_count || 0, " network signals")), /* @__PURE__ */ React.createElement("p", null, latestSnapshot.summary)) : /* @__PURE__ */ React.createElement(EmptyState, { title: "No platform snapshot", text: "Run a read-only Yellow.ai snapshot to attach agents, workflows, tools, and KB context automatically." })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Goal Test Brief"), goalBrief?.id ? /* @__PURE__ */ React.createElement("div", { className: "snapshotSummary" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, "ready"), /* @__PURE__ */ React.createElement(Pill, null, goalBrief.max_turns || 10, " turns")), /* @__PURE__ */ React.createElement("p", null, goalBrief.title || goalBrief.goal)) : /* @__PURE__ */ React.createElement(EmptyState, { title: "No goal brief", text: "Use Analyzer to prepare an adaptive test brief for the Testing tab." })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Suggested Next Actions"), /* @__PURE__ */ React.createElement("ul", { className: "compactList" }, /* @__PURE__ */ React.createElement("li", null, latestSnapshot ? `Use ${latestSnapshot.id} for failure root-cause analysis.` : "Run a platform snapshot to attach Studio context automatically."), /* @__PURE__ */ React.createElement("li", null, botDiscovery?.id ? `Use discovered bot profile ${botDiscovery.id} for suite generation.` : "Run bot discovery after attaching Yellow.ai access."), /* @__PURE__ */ React.createElement("li", null, goalBrief?.id ? `Run prepared goal brief ${goalBrief.id}.` : "Prepare a goal-driven test brief from Analyzer."), /* @__PURE__ */ React.createElement("li", null, changePlans[0] ? `Review ${changePlans[0].id} from ${changePlans[0].document_name}` : "Upload a Yellow.ai guide, flow spec, or transcript if API access is incomplete."), /* @__PURE__ */ React.createElement("li", null, suites[0] ? `Run or inspect ${suites[0].name}` : "Generate a first regression suite."), /* @__PURE__ */ React.createElement("li", null, runs[0] ? `Open latest report ${runs[0].report_id}` : "Run a real web-widget chat automation script."))));
  }
  function suiteChannelCount(suite, channel) {
    return (suite.test_cases || []).filter((item) => item.channel === channel).length;
  }
  function suiteHasChannel(suite, channel) {
    return suiteChannelCount(suite, channel) > 0;
  }
  function suiteScenarioCounts(suite, channel) {
    return (suite.test_cases || []).filter((item) => item.channel === channel).reduce((counts, item) => {
      const scenario = item.scenario_type || "custom";
      counts[scenario] = (counts[scenario] || 0) + 1;
      return counts;
    }, {});
  }
  function reportHasChannel(report, channel) {
    if (!report) return false;
    return (report.case_results || []).some((item) => item.channel === channel);
  }
  function runMatchesChannel(run, channel) {
    if (run.channel_filter === channel) return true;
    if (channel === "chat" && !run.channel_filter && run.adapter === "playwright_web_widget") return true;
    return false;
  }
  function scriptTurnCount(script) {
    const turnHeaders = String(script || "").match(/^\s*#{3,6}\s*Turn\b/gim);
    if (turnHeaders?.length) return turnHeaders.length;
    const userBlocks = String(script || "").match(/^\s*\*{0,4}\s*User\s*:?\s*\*{0,4}\s*$/gim);
    return userBlocks?.length || 0;
  }
  function scriptTitle(script) {
    const match = String(script || "").match(/^\s*##\s+(.+)$/m);
    return match ? match[1].trim() : "Custom script";
  }
  function TestingTab({ profile, setProfile, saveProfile, generateSuite, suites, runs, latestReport, runSuite, runChatAutomation, runGoalChatAutomation, voiceData, saveVoiceAccess, syncVoiceCalls, goalBrief, openReport, config, loading }) {
    const [testMode, setTestMode] = useState("chat");
    const testChannel = "chat";
    const activeSuites = suites.filter((suite) => suiteHasChannel(suite, testChannel));
    const activeRuns = runs.filter((run) => runMatchesChannel(run, testChannel));
    const voiceRuns = runs.filter((run) => runMatchesChannel(run, "voice"));
    const runsScrollRef = useRef(null);
    const activeCaseCount = activeSuites.reduce((total, suite) => total + suiteChannelCount(suite, testChannel), 0);
    const activeReport = reportHasChannel(latestReport, testChannel) ? latestReport : null;
    const activeVoiceReport = reportHasChannel(latestReport, "voice") ? latestReport : null;
    const voiceSummary = voiceData?.summary || {};
    const modeSummary = testMode === "chat" ? [
      ["Suites", activeSuites.length],
      ["Cases", activeCaseCount],
      ["Runs", activeRuns.length],
      ["Reports", activeRuns.filter((run) => run.report_id).length]
    ] : [
      ["Calls", voiceSummary.total_calls || 0],
      ["Failed", voiceSummary.failed_calls || 0],
      ["Categorized", voiceSummary.categorized || 0],
      ["Pending", voiceSummary.pending_deep_analysis || 0]
    ];
    useEffect(() => {
      runsScrollRef.current?.scrollTo({ top: 0 });
    }, [activeRuns[0]?.id]);
    return /* @__PURE__ */ React.createElement("div", { className: "testingStack" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel testingModePanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Testing Workspace", meta: testMode === "chat" ? "YELLOW.AI CHAT TESTING" : "YELLOW.AI VOICE ANALYSIS" }), /* @__PURE__ */ React.createElement("div", { className: "testingChannelTabs" }, /* @__PURE__ */ React.createElement("button", { className: testMode === "chat" ? "active" : "", type: "button", onClick: () => setTestMode("chat") }, /* @__PURE__ */ React.createElement(Icon, { name: "chat", filled: true }), " Chat Testing"), /* @__PURE__ */ React.createElement("button", { className: testMode === "voice" ? "active" : "", type: "button", onClick: () => setTestMode("voice") }, /* @__PURE__ */ React.createElement(Icon, { name: "call", filled: true }), " Voice Call Analysis")), /* @__PURE__ */ React.createElement("div", { className: "testingModeSummary" }, modeSummary.map(([label, value]) => /* @__PURE__ */ React.createElement(Metric, { key: label, label, value })))), testMode === "chat" ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "mainGrid testingGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Bot Core Config", meta: "CHAT SUITE INPUTS" }), /* @__PURE__ */ React.createElement(
      BotCoreConfig,
      {
        profile,
        setProfile,
        saveProfile,
        generateSuite: () => generateSuite("chat"),
        generateSuiteLabel: "Generate Chat Suite",
        loading
      }
    )), /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Run Chat Tests", meta: "REAL WEB-WIDGET AUTOMATION" }), /* @__PURE__ */ React.createElement(
      ChatAutomationPanel,
      {
        profile,
        setProfile,
        runChatAutomation,
        runGoalChatAutomation,
        goalBrief,
        config,
        loading
      }
    ))), /* @__PURE__ */ React.createElement("div", { className: "mainGrid testingGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel scrollPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Chat Suites", meta: `${activeSuites.length} TOTAL` }), /* @__PURE__ */ React.createElement("div", { className: "scrollRegion" }, /* @__PURE__ */ React.createElement(SuiteList, { suites: activeSuites, channel: testChannel, runSuite, loading }))), /* @__PURE__ */ React.createElement("section", { className: "workPanel scrollPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Chat Runs", meta: `${activeRuns.length} RECENT` }), /* @__PURE__ */ React.createElement("div", { className: "scrollRegion", ref: runsScrollRef }, /* @__PURE__ */ React.createElement(RunList, { runs: activeRuns, channel: testChannel, openReport })))), /* @__PURE__ */ React.createElement("section", { className: "workPanel reportPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Chat Report", meta: activeReport?.id || "NO REPORT SELECTED" }), /* @__PURE__ */ React.createElement(ReportView, { report: activeReport, channel: testChannel }))) : /* @__PURE__ */ React.createElement(
      VoiceAnalysisWorkspace,
      {
        voiceData,
        saveVoiceAccess,
        syncVoiceCalls,
        voiceRuns,
        openReport,
        activeVoiceReport,
        loading
      }
    ));
  }
  function VoiceAnalysisWorkspace({ voiceData, saveVoiceAccess, syncVoiceCalls, voiceRuns, openReport, activeVoiceReport, loading }) {
    const access = voiceData?.access || {};
    const summary = voiceData?.summary || {};
    const calls = voiceData?.calls || [];
    const syncRuns = voiceData?.sync_runs || [];
    const categories = voiceData?.categories || {};
    const [form, setForm] = useState({
      bot_name: access.bot_name || "",
      bot_id: access.bot_id || "",
      ui_base_url: access.ui_base_url || "https://cloud.yellow.ai",
      days_back: String(access.days_back || "7"),
      range_mode: access.range_mode || "preset",
      date_from: access.date_from || defaultDateFrom(access.days_back || 7),
      date_to: access.date_to || localDateInputValue(),
      api_key: "",
      cookie: ""
    });
    const [selectedCallId, setSelectedCallId] = useState("");
    const selectedCall = calls.find((call) => call.id === selectedCallId) || calls[0] || null;
    useEffect(() => {
      setForm((current) => ({
        ...current,
        bot_name: access.bot_name || current.bot_name || "",
        bot_id: access.bot_id || current.bot_id || "",
        ui_base_url: access.ui_base_url || current.ui_base_url || "https://cloud.yellow.ai",
        days_back: String(access.days_back || current.days_back || "7"),
        range_mode: access.range_mode || current.range_mode || "preset",
        date_from: access.date_from || current.date_from || defaultDateFrom(access.days_back || current.days_back || 7),
        date_to: access.date_to || current.date_to || localDateInputValue(),
        api_key: "",
        cookie: ""
      }));
    }, [access.project_id, access.bot_id, access.cookie_configured, access.api_key_configured, access.range_mode, access.date_from, access.date_to]);
    useEffect(() => {
      if (!selectedCallId && calls[0]?.id) setSelectedCallId(calls[0].id);
    }, [calls[0]?.id, selectedCallId]);
    const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
    const usingCustomRange = form.range_mode === "custom";
    const dateRangeReady = form.date_from && form.date_to && form.date_from <= form.date_to;
    const syncCurrentRange = () => syncVoiceCalls({
      ...form,
      date_from: usingCustomRange ? form.date_from : "",
      date_to: usingCustomRange ? form.date_to : "",
      failed_only: false
    });
    const categoryCounts = summary.category_counts || {};
    return /* @__PURE__ */ React.createElement("div", { className: "voiceWorkspace" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Voice Bot Access", meta: "YELLOW.AI CDR + MESSAGES" }), /* @__PURE__ */ React.createElement("div", { className: "voiceAccessGrid" }, /* @__PURE__ */ React.createElement(Field, { label: "Voice bot name" }, /* @__PURE__ */ React.createElement("input", { value: form.bot_name, onChange: (event) => update("bot_name", event.target.value), placeholder: "Kent RO Inbound" })), /* @__PURE__ */ React.createElement(Field, { label: "Voice bot ID" }, /* @__PURE__ */ React.createElement("input", { value: form.bot_id, onChange: (event) => update("bot_id", event.target.value), placeholder: "x173..." })), /* @__PURE__ */ React.createElement(Field, { label: "Yellow.ai base URL" }, /* @__PURE__ */ React.createElement("input", { value: form.ui_base_url, onChange: (event) => update("ui_base_url", event.target.value), placeholder: "https://cloud.yellow.ai" })), /* @__PURE__ */ React.createElement(Field, { label: "Platform API key" }, /* @__PURE__ */ React.createElement("input", { type: "password", value: form.api_key, onChange: (event) => update("api_key", event.target.value), placeholder: access.api_key_configured ? "Saved. Leave blank to keep." : "Paste key for CDR/traces" })), /* @__PURE__ */ React.createElement(Field, { label: "Cookie header" }, /* @__PURE__ */ React.createElement("input", { type: "password", value: form.cookie, onChange: (event) => update("cookie", event.target.value), placeholder: access.cookie_configured ? "Saved. Leave blank to keep." : "Paste cookie for messages" }))), /* @__PURE__ */ React.createElement("div", { className: "voiceDateRangeBar" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, "Call-record range"), /* @__PURE__ */ React.createElement("span", null, "Fetch all CDR rows in the selected window, then classify failures locally.")), /* @__PURE__ */ React.createElement("div", { className: "rangeModeToggle", "aria-label": "Voice sync range mode" }, /* @__PURE__ */ React.createElement("button", { className: form.range_mode === "preset" ? "active" : "", type: "button", onClick: () => update("range_mode", "preset") }, "Days back"), /* @__PURE__ */ React.createElement("button", { className: form.range_mode === "custom" ? "active" : "", type: "button", onClick: () => update("range_mode", "custom") }, "Custom")), /* @__PURE__ */ React.createElement(Field, { label: "Days back" }, /* @__PURE__ */ React.createElement("input", { type: "number", min: "1", max: "31", inputMode: "numeric", disabled: usingCustomRange, value: form.days_back, onChange: (event) => update("days_back", event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "From" }, /* @__PURE__ */ React.createElement("input", { type: "date", disabled: !usingCustomRange, value: form.date_from, onChange: (event) => update("date_from", event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "To" }, /* @__PURE__ */ React.createElement("input", { type: "date", disabled: !usingCustomRange, value: form.date_to, onChange: (event) => update("date_to", event.target.value) }))), /* @__PURE__ */ React.createElement("div", { className: "voiceActionRow" }, /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: access.api_key_configured ? "ok" : "warn" }, access.api_key_configured ? "API key saved" : "API key missing"), /* @__PURE__ */ React.createElement(Pill, { tone: access.cookie_configured ? "ok" : "warn" }, access.cookie_configured ? "Cookie saved" : "Cookie missing")), /* @__PURE__ */ React.createElement("div", { className: "buttonRow" }, /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "voice-access", onClick: () => saveVoiceAccess(form) }, /* @__PURE__ */ React.createElement(Icon, { name: "save" }), " Save access"), /* @__PURE__ */ React.createElement("button", { type: "button", disabled: loading === "voice-sync" || !form.bot_id.trim() || usingCustomRange && !dateRangeReady, onClick: syncCurrentRange }, /* @__PURE__ */ React.createElement(Icon, { name: usingCustomRange ? "date_range" : "sync" }), " ", loading === "voice-sync" ? "Syncing..." : usingCustomRange ? "Sync custom range" : `Sync last ${form.days_back || 7} days`)))), /* @__PURE__ */ React.createElement("section", { className: "workPanel voiceOverviewPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Voice Failure Overview", meta: "PROJECT-SCOPED ANALYSIS" }), /* @__PURE__ */ React.createElement("div", { className: "metricGrid five" }, /* @__PURE__ */ React.createElement(Metric, { label: "Total calls", value: summary.total_calls || 0 }), /* @__PURE__ */ React.createElement(Metric, { label: "Failed calls", value: summary.failed_calls || 0 }), /* @__PURE__ */ React.createElement(Metric, { label: "Failure rate", value: `${summary.failure_rate || 0}%` }), /* @__PURE__ */ React.createElement(Metric, { label: "Categorized", value: summary.categorized || 0 }), /* @__PURE__ */ React.createElement(Metric, { label: "Pending", value: summary.pending_deep_analysis || 0 })), /* @__PURE__ */ React.createElement("div", { className: "voiceCategoryGrid" }, Object.entries(categories).filter(([code]) => code !== "pending_deep_analysis").map(([code, meta]) => /* @__PURE__ */ React.createElement("div", { className: "voiceCategory", key: code }, /* @__PURE__ */ React.createElement("strong", null, meta.label), /* @__PURE__ */ React.createElement("span", null, categoryCounts[code] || 0), /* @__PURE__ */ React.createElement("p", null, meta.description)))), /* @__PURE__ */ React.createElement("div", { className: "voiceSyncStrip" }, /* @__PURE__ */ React.createElement(Pill, { tone: summary.unidentified_turns ? "warn" : "ok" }, summary.unidentified_turns || 0, " unidentified turns"), /* @__PURE__ */ React.createElement("span", null, summary.total_user_turns || 0, " total user turns"), /* @__PURE__ */ React.createElement("span", null, "Avg low confidence: ", summary.avg_low_confidence ?? "-"))), /* @__PURE__ */ React.createElement("div", { className: "mainGrid voiceGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel voiceListPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Voice Calls", meta: `${calls.length} TOTAL / ${summary.failed_calls || 0} FAILED` }), /* @__PURE__ */ React.createElement("div", { className: "scrollRegion voiceCallScroll" }, /* @__PURE__ */ React.createElement(VoiceCallList, { calls, selectedCallId: selectedCall?.id, onSelect: setSelectedCallId }))), /* @__PURE__ */ React.createElement("section", { className: "workPanel voiceDetailPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Call Detail", meta: selectedCall?.id || "NO CALL SELECTED" }), /* @__PURE__ */ React.createElement(VoiceCallDetail, { call: selectedCall }))), /* @__PURE__ */ React.createElement("div", { className: "mainGrid voiceBottomGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel voiceListPanel compact" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Voice Runs", meta: `${voiceRuns.length} RECENT` }), /* @__PURE__ */ React.createElement("div", { className: "scrollRegion" }, /* @__PURE__ */ React.createElement(RunList, { runs: voiceRuns, channel: "voice", openReport }))), /* @__PURE__ */ React.createElement("section", { className: "workPanel voiceDetailPanel compact" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Latest Sync", meta: syncRuns[0]?.range_label || syncRuns[0]?.status || "NO SYNC" }), syncRuns[0] ? /* @__PURE__ */ React.createElement("div", { className: "voiceSyncCard" }, /* @__PURE__ */ React.createElement("strong", null, syncRuns[0].created_at), /* @__PURE__ */ React.createElement("p", null, syncRuns[0].message), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, null, syncRuns[0].range_label || `${syncRuns[0].days_back || 7} days`), /* @__PURE__ */ React.createElement(Pill, null, syncRuns[0].calls_pulled, " pulled"), /* @__PURE__ */ React.createElement(Pill, null, syncRuns[0].failed_calls, " failed"), /* @__PURE__ */ React.createElement(Pill, null, syncRuns[0].messages_loaded, " with turns"), /* @__PURE__ */ React.createElement(Pill, { tone: syncRuns[0].pending_deep_analysis ? "warn" : "ok" }, syncRuns[0].pending_deep_analysis, " pending"))) : /* @__PURE__ */ React.createElement(EmptyState, { title: "No voice sync yet", text: "Save voice access, then sync call records from Yellow.ai." }))), /* @__PURE__ */ React.createElement("section", { className: "workPanel reportPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Voice Report", meta: activeVoiceReport?.id || "NO REPORT SELECTED" }), /* @__PURE__ */ React.createElement(ReportView, { report: activeVoiceReport, channel: "voice" })));
  }
  function VoiceCallList({ calls, selectedCallId, onSelect }) {
    if (!calls.length) return /* @__PURE__ */ React.createElement(EmptyState, { title: "No voice calls yet", text: "Sync call records from Yellow.ai to populate call analysis." });
    return /* @__PURE__ */ React.createElement("div", { className: "cardList voiceCallList" }, calls.map((call) => /* @__PURE__ */ React.createElement("button", { className: cx("voiceCallItem", call.id === selectedCallId && "active"), type: "button", key: call.id, onClick: () => onSelect(call.id) }, /* @__PURE__ */ React.createElement("span", null, /* @__PURE__ */ React.createElement("strong", null, call.started_at || call.created_at || call.id), /* @__PURE__ */ React.createElement("small", null, call.from_number || "unknown caller", " - ", call.hangup_reason || "no hangup reason")), /* @__PURE__ */ React.createElement(Pill, { tone: call.classification_status === "pending_deep_analysis" ? "warn" : call.issues?.length ? "warn" : "ok" }, call.primary_issue || call.classification_status || "ok"))));
  }
  function VoiceCallDetail({ call }) {
    if (!call) return /* @__PURE__ */ React.createElement(EmptyState, { title: "No call selected", text: "Select a voice call to inspect evidence." });
    const turns = call.turns || [];
    return /* @__PURE__ */ React.createElement("div", { className: "voiceCallDetail" }, /* @__PURE__ */ React.createElement("div", { className: "voiceCallMeta" }, /* @__PURE__ */ React.createElement(Pill, { tone: call.severity === "High" ? "warn" : "" }, call.severity || "Low", " severity"), /* @__PURE__ */ React.createElement(Pill, null, call.call_duration_s || 0, "s call"), /* @__PURE__ */ React.createElement(Pill, null, call.bot_duration_s || 0, "s bot"), /* @__PURE__ */ React.createElement(Pill, null, call.language || "language unknown")), /* @__PURE__ */ React.createElement("p", null, call.summary), /* @__PURE__ */ React.createElement("div", { className: "contextBlock compactBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Issue Evidence"), (call.issues || []).map((issue, index) => /* @__PURE__ */ React.createElement("div", { className: "recommendation", key: `${issue.category}-${index}` }, /* @__PURE__ */ React.createElement("strong", null, issue.label || issue.category), /* @__PURE__ */ React.createElement("p", null, issue.evidence))), !call.issues?.length && /* @__PURE__ */ React.createElement(EmptyState, { title: "No mapped issues", text: call.classification_status === "pending_deep_analysis" ? "Turn data is missing. Refresh cookie and re-sync messages/traces." : "No deterministic failure rule fired." })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock compactBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Transcript"), turns.length ? /* @__PURE__ */ React.createElement("div", { className: "transcriptList voiceTranscript" }, turns.slice(0, 30).map((turn, index) => /* @__PURE__ */ React.createElement("div", { className: "transcriptTurn", key: `${turn.timestamp}-${index}` }, /* @__PURE__ */ React.createElement("strong", null, turn.speaker), /* @__PURE__ */ React.createElement("span", null, turn.text || "(empty)"), /* @__PURE__ */ React.createElement("small", null, turn.confidence != null ? `conf ${turn.confidence}` : turn.message_type || "", " ", turn.slug ? `- ${turn.slug}` : "")))) : /* @__PURE__ */ React.createElement(EmptyState, { title: "No turn data", text: "Yellow.ai messages were not available for this call. Refresh cookie and re-sync." })));
  }
  function ChatAutomationPanel({ profile, setProfile, runChatAutomation, runGoalChatAutomation, goalBrief, config, loading }) {
    const [script, setScript] = useState(defaultChatAutomationScript);
    const [goal, setGoal] = useState("Complete a new installation booking journey without losing context.");
    const [constraints, setConstraints] = useState("Use realistic user replies. Do not switch language unless the user explicitly asks. Continue until the journey reaches success, a clear bot-side failure, a loop, or a restart.");
    const [testData, setTestData] = useState("Name: Test User. Purchase source: Amazon. Order ID: Not Available. Product category: Water Purifier. Product: Kent Grand Plus. Pincode: 560102. Address: Flat 101, Test Apartments, HSR Layout, Bengaluru. Confirmation: Confirm. Date preference: Tomorrow.");
    const [successCriteria, setSuccessCriteria] = useState("The bot should keep the same journey, collect required details one by one, ask for confirmation when needed, and give a positive closure after confirmation.");
    const [maxTurns, setMaxTurns] = useState("18");
    const lastAppliedBriefId = useRef("");
    const playwright = config?.playwright || {};
    const turnsInScript = scriptTurnCount(script);
    const scriptIsShort = turnsInScript > 0 && turnsInScript < 6;
    const update = (key, value) => setProfile((current) => ({ ...current, [key]: value }));
    function applyGoalBrief(brief) {
      if (!brief) return;
      setGoal(brief.goal || "");
      setConstraints(brief.constraints || "");
      setTestData(brief.test_data || "");
      setSuccessCriteria(brief.success_criteria || "");
      setMaxTurns(String(brief.max_turns || "10"));
    }
    useEffect(() => {
      if (!goalBrief?.id || goalBrief.id === lastAppliedBriefId.current) return;
      applyGoalBrief(goalBrief);
      lastAppliedBriefId.current = goalBrief.id;
    }, [goalBrief?.id]);
    function loadScriptFile(file) {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setScript(String(reader.result || ""));
      reader.readAsText(file);
    }
    const endpointReady = Boolean((profile.chat_endpoint || "").trim());
    return /* @__PURE__ */ React.createElement("div", { className: "automationPanel" }, /* @__PURE__ */ React.createElement("div", { className: "automationHeader" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, "Chat Automation"), /* @__PURE__ */ React.createElement("p", null, "Goal-driven exploration or Markdown scripts run through the configured web widget and produce scenario-level project reports.")), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: playwright.available ? "ok" : "warn" }, playwright.available ? "Playwright ready" : "Playwright setup"), /* @__PURE__ */ React.createElement(Pill, { tone: endpointReady ? "ok" : "warn" }, endpointReady ? "URL ready" : "URL missing"))), /* @__PURE__ */ React.createElement("section", { className: "goalRunnerPanel" }, /* @__PURE__ */ React.createElement("div", { className: "sectionTitleRow" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h4", null, "Goal-Driven Test"), /* @__PURE__ */ React.createElement("p", null, "Describe the journey once. The tester observes bot replies, chooses clicks/messages adaptively, and stops on success, loop, or failure.")), /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, "Adaptive")), goalBrief?.id && /* @__PURE__ */ React.createElement("div", { className: "briefNotice" }, /* @__PURE__ */ React.createElement(Icon, { name: "assignment_turned_in" }), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, goalBrief.title || "Analyzer test brief loaded"), /* @__PURE__ */ React.createElement("span", null, goalBrief.reasoning || "Prepared from the current analyzer chat, reports, docs, and platform context.")), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton compactButton", type: "button", onClick: () => applyGoalBrief(goalBrief) }, "Reload fields")), /* @__PURE__ */ React.createElement(Field, { label: "Test goal" }, /* @__PURE__ */ React.createElement("textarea", { className: "compactTextarea", value: goal, onChange: (event) => setGoal(event.target.value) })), /* @__PURE__ */ React.createElement("div", { className: "twoCol" }, /* @__PURE__ */ React.createElement(Field, { label: "Constraints" }, /* @__PURE__ */ React.createElement("textarea", { className: "compactTextarea", value: constraints, onChange: (event) => setConstraints(event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "Test data" }, /* @__PURE__ */ React.createElement("textarea", { className: "compactTextarea", value: testData, onChange: (event) => setTestData(event.target.value) }))), /* @__PURE__ */ React.createElement("div", { className: "twoCol" }, /* @__PURE__ */ React.createElement(Field, { label: "Success criteria" }, /* @__PURE__ */ React.createElement("textarea", { className: "compactTextarea", value: successCriteria, onChange: (event) => setSuccessCriteria(event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "Max adaptive turns" }, /* @__PURE__ */ React.createElement("input", { type: "number", min: "2", max: "20", inputMode: "numeric", value: maxTurns, onChange: (event) => setMaxTurns(event.target.value) }))), /* @__PURE__ */ React.createElement("div", { className: "automationActions" }, /* @__PURE__ */ React.createElement(
      "button",
      {
        type: "button",
        disabled: loading === "goal-chat-automation" || !endpointReady || !goal.trim(),
        onClick: () => runGoalChatAutomation({ goal, constraints, test_data: testData, success_criteria: successCriteria, max_turns: maxTurns })
      },
      /* @__PURE__ */ React.createElement(Icon, { name: "psychology" }),
      " ",
      loading === "goal-chat-automation" ? "Running adaptive test..." : "Run Goal-Driven Test"
    ))), /* @__PURE__ */ React.createElement("details", { className: "testAdvancedDetails" }, /* @__PURE__ */ React.createElement("summary", null, "Widget setup"), /* @__PURE__ */ React.createElement("div", { className: "twoCol" }, /* @__PURE__ */ React.createElement(Field, { label: "Launcher selector" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_launcher_selector || "", onChange: (event) => update("chat_launcher_selector", event.target.value), placeholder: "#ymDivBar" })), /* @__PURE__ */ React.createElement(Field, { label: "Input selector" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_input_selector || "", onChange: (event) => update("chat_input_selector", event.target.value), placeholder: "textarea, input[type='text']" })), /* @__PURE__ */ React.createElement(Field, { label: "Message selector" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_message_selector || "", onChange: (event) => update("chat_message_selector", event.target.value), placeholder: "[class*='message']" })), /* @__PURE__ */ React.createElement(Field, { label: "Send button selector" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_send_selector || "", onChange: (event) => update("chat_send_selector", event.target.value), placeholder: "Optional" })), /* @__PURE__ */ React.createElement(Field, { label: "Iframe hint" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_frame_hint || "", onChange: (event) => update("chat_frame_hint", event.target.value), placeholder: "Optional frame URL/name" })), /* @__PURE__ */ React.createElement(Field, { label: "Ready selector" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_ready_selector || "", onChange: (event) => update("chat_ready_selector", event.target.value), placeholder: "Optional" })), /* @__PURE__ */ React.createElement(Field, { label: "Timeout seconds" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_response_timeout_seconds || "40", onChange: (event) => update("chat_response_timeout_seconds", event.target.value), inputMode: "numeric" }))), /* @__PURE__ */ React.createElement("label", { className: "checkField automationCheck" }, /* @__PURE__ */ React.createElement(
      "input",
      {
        type: "checkbox",
        checked: (profile.chat_playwright_headless || "true") !== "false",
        onChange: (event) => update("chat_playwright_headless", event.target.checked ? "true" : "false")
      }
    ), /* @__PURE__ */ React.createElement("span", null, "Headless browser"))), /* @__PURE__ */ React.createElement("details", { className: "testAdvancedDetails" }, /* @__PURE__ */ React.createElement("summary", null, "Scripted regression runner"), /* @__PURE__ */ React.createElement(Field, { label: "Markdown script" }, /* @__PURE__ */ React.createElement("textarea", { className: "automationScript", value: script, onChange: (event) => setScript(event.target.value) })), /* @__PURE__ */ React.createElement("div", { className: "scriptMetaRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: turnsInScript >= 6 ? "ok" : "warn" }, turnsInScript || 0, " turns"), /* @__PURE__ */ React.createElement("span", null, scriptTitle(script))), scriptIsShort && /* @__PURE__ */ React.createElement("p", { className: "fieldHint warnText" }, "This script is short. It will stop after ", turnsInScript, " user turns. Add more User/Bot turns for deeper regression coverage."), /* @__PURE__ */ React.createElement("p", { className: "fieldHint" }, "Use exact ", /* @__PURE__ */ React.createElement("code", null, "User:"), " / ", /* @__PURE__ */ React.createElement("code", null, "Bot:"), " turn blocks. For quick replies, make the User value exactly match the visible option."), /* @__PURE__ */ React.createElement("div", { className: "automationActions" }, /* @__PURE__ */ React.createElement("input", { className: "scriptFileInput", type: "file", accept: ".md,.txt", onChange: (event) => loadScriptFile(event.target.files[0]) }), /* @__PURE__ */ React.createElement("button", { type: "button", disabled: loading === "chat-automation" || !endpointReady, onClick: () => runChatAutomation(script) }, /* @__PURE__ */ React.createElement(Icon, { name: "play_arrow" }), " Run Scripted Test"))));
  }
  function BotCoreConfig({ profile, setProfile, saveProfile, generateSuite, generateSuiteLabel = "Generate Test Suite", loading }) {
    const update = (key, value) => setProfile((current) => ({ ...current, [key]: value }));
    return /* @__PURE__ */ React.createElement("div", { className: "configForm" }, /* @__PURE__ */ React.createElement("div", { className: "twoCol" }, /* @__PURE__ */ React.createElement(Field, { label: "Bot name" }, /* @__PURE__ */ React.createElement("input", { value: profile.bot_name || "", onChange: (event) => update("bot_name", event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "Chat cases to generate" }, /* @__PURE__ */ React.createElement(
      "input",
      {
        type: "number",
        min: "1",
        max: "60",
        inputMode: "numeric",
        value: profile.chat_case_count || "12",
        onChange: (event) => update("chat_case_count", event.target.value)
      }
    ))), /* @__PURE__ */ React.createElement(Field, { label: "Chat endpoint / widget URL" }, /* @__PURE__ */ React.createElement("input", { value: profile.chat_endpoint || "", onChange: (event) => update("chat_endpoint", event.target.value), placeholder: "https://..." })), /* @__PURE__ */ React.createElement(Field, { label: "Business goal" }, /* @__PURE__ */ React.createElement("textarea", { value: profile.business_goal || "", onChange: (event) => update("business_goal", event.target.value) })), /* @__PURE__ */ React.createElement(Field, { label: "Journeys / risks to cover" }, /* @__PURE__ */ React.createElement("textarea", { value: profile.flow_docs || "", onChange: (event) => update("flow_docs", event.target.value) })), /* @__PURE__ */ React.createElement("div", { className: "buttonRow" }, /* @__PURE__ */ React.createElement("button", { type: "button", onClick: generateSuite, disabled: loading === "generate-suite" }, /* @__PURE__ */ React.createElement(Icon, { name: "play_arrow" }), " ", generateSuiteLabel), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: saveProfile, disabled: loading === "save-profile" }, "Save Project Profile")));
  }
  function DocsTab({ docsPages, documents, changePlans, uploadDocument, analyzeDocument, approvePlan, activeProjectId, chat, sendMessage, createDocsChat, loading }) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [message, setMessage] = useState("");
    async function searchDocs(event) {
      event.preventDefault();
      const payload = await api("/api/docs/search", {
        method: "POST",
        body: JSON.stringify({ project_id: activeProjectId, query })
      });
      setResults(payload.results || []);
    }
    return /* @__PURE__ */ React.createElement("div", { className: "docsStack" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Knowledge Base", meta: "HANDBOOK + PROJECT DOCS" }), /* @__PURE__ */ React.createElement("form", { className: "searchHero", onSubmit: searchDocs }, /* @__PURE__ */ React.createElement(Icon, { name: "search" }), /* @__PURE__ */ React.createElement("input", { value: query, onChange: (event) => setQuery(event.target.value), placeholder: "Search V3 routing, RAG testing, provider setup..." }), /* @__PURE__ */ React.createElement("button", { type: "submit" }, "Search")), /* @__PURE__ */ React.createElement("div", { className: "docGrid" }, (results.length ? results : docsPages.slice(0, 8)).map((page) => /* @__PURE__ */ React.createElement("article", { className: "docCard", key: `${page.type || "page"}-${page.id}` }, /* @__PURE__ */ React.createElement("div", { className: "docIcon" }, /* @__PURE__ */ React.createElement(Icon, { name: page.type === "document" ? "article" : "description" })), /* @__PURE__ */ React.createElement("h3", null, page.title), /* @__PURE__ */ React.createElement(Pill, null, page.category), /* @__PURE__ */ React.createElement("p", null, (page.excerpt || page.body || "").slice(0, 260)))))), /* @__PURE__ */ React.createElement("div", { className: "mainGrid docsGrid" }, /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Project Knowledge", meta: `${documents.length} DOCS` }), /* @__PURE__ */ React.createElement("input", { className: "fileInput", type: "file", accept: ".pdf,.docx,.md,.txt,.json,.csv", onChange: (event) => uploadDocument(event.target.files[0]) }), /* @__PURE__ */ React.createElement(DocumentList, { documents, analyzeDocument, loading })), /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Change Plans", meta: `${changePlans.length} PLANS` }), /* @__PURE__ */ React.createElement(ChangePlans, { plans: changePlans, approvePlan, loading }))), /* @__PURE__ */ React.createElement("section", { className: "workPanel" }, /* @__PURE__ */ React.createElement(PanelHeader, { title: "Docs Assistant", meta: "SOURCE-GROUNDED HELP", actions: /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: createDocsChat }, "New docs chat") }), /* @__PURE__ */ React.createElement(ChatMessages, { chat, empty: "Ask about this tool, Yellow.ai V2/V3, RAG, chat testing, or setup.", compact: true }), /* @__PURE__ */ React.createElement(
      "form",
      {
        className: "chatComposer",
        onSubmit: (event) => {
          event.preventDefault();
          sendMessage(message);
          setMessage("");
        }
      },
      /* @__PURE__ */ React.createElement("textarea", { value: message, onChange: (event) => setMessage(event.target.value), placeholder: "Ask the docs assistant..." }),
      /* @__PURE__ */ React.createElement("button", { type: "submit", disabled: loading === "docs-chat" }, "Ask")
    )));
  }
  function PanelHeader({ title, meta, actions }) {
    return /* @__PURE__ */ React.createElement("div", { className: "panelHeader" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h2", null, title), meta && /* @__PURE__ */ React.createElement("span", null, meta)), actions && /* @__PURE__ */ React.createElement("div", { className: "buttonRow" }, actions));
  }
  function Field({ label, children }) {
    return /* @__PURE__ */ React.createElement("label", { className: "field" }, /* @__PURE__ */ React.createElement("span", null, label), children);
  }
  function Metric({ label, value }) {
    return /* @__PURE__ */ React.createElement("div", { className: "metricCard" }, /* @__PURE__ */ React.createElement("span", null, label), /* @__PURE__ */ React.createElement("strong", null, value));
  }
  function StatusRow({ label, value, ready }) {
    return /* @__PURE__ */ React.createElement("div", { className: "statusRow" }, /* @__PURE__ */ React.createElement("span", null, label), /* @__PURE__ */ React.createElement(Pill, { tone: ready ? "ok" : "warn" }, ready ? "Ready" : "Needs setup"), /* @__PURE__ */ React.createElement("code", null, value));
  }
  function ChatMessages({ chat, empty, compact = false }) {
    const messages = chat?.messages || [];
    if (!messages.length) {
      return /* @__PURE__ */ React.createElement("div", { className: cx("chatCanvas", compact && "compact") }, /* @__PURE__ */ React.createElement("div", { className: "emptyChat" }, /* @__PURE__ */ React.createElement("h3", null, empty), /* @__PURE__ */ React.createElement("p", null, "Project docs, test suites, reports, and Yellow.ai target metadata are available as context.")));
    }
    return /* @__PURE__ */ React.createElement("div", { className: cx("chatCanvas", compact && "compact") }, messages.map((message) => /* @__PURE__ */ React.createElement("article", { className: cx("message", message.role), key: message.id }, /* @__PURE__ */ React.createElement("span", { className: "messageRole" }, message.role), /* @__PURE__ */ React.createElement(MarkdownText, { content: message.content }))));
  }
  function MarkdownText({ content }) {
    const blocks = parseMarkdown(String(content || ""));
    if (!blocks.length) return /* @__PURE__ */ React.createElement("div", { className: "markdownBody" }, /* @__PURE__ */ React.createElement("p", null));
    return /* @__PURE__ */ React.createElement("div", { className: "markdownBody" }, blocks.map((block, index) => renderMarkdownBlock(block, index)));
  }
  function parseMarkdown(content) {
    const lines = content.replace(/\r\n/g, "\n").split("\n");
    const blocks = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();
      if (!trimmed) {
        index += 1;
        continue;
      }
      if (trimmed.startsWith("```")) {
        const language = trimmed.replace(/^```/, "").trim();
        const code = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith("```")) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        blocks.push({ type: "code", language, text: code.join("\n") });
        continue;
      }
      const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
        index += 1;
        continue;
      }
      if (/^[-*_]{3,}$/.test(trimmed)) {
        blocks.push({ type: "rule" });
        index += 1;
        continue;
      }
      const unordered = trimmed.match(/^[-*]\s+(.+)$/);
      if (unordered) {
        const items = [];
        while (index < lines.length) {
          const item = lines[index].trim().match(/^[-*]\s+(.+)$/);
          if (!item) break;
          items.push(item[1]);
          index += 1;
        }
        blocks.push({ type: "list", ordered: false, items });
        continue;
      }
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (ordered) {
        const items = [];
        while (index < lines.length) {
          const item = lines[index].trim().match(/^\d+[.)]\s+(.+)$/);
          if (!item) break;
          items.push(item[1]);
          index += 1;
        }
        blocks.push({ type: "list", ordered: true, items });
        continue;
      }
      const quote = trimmed.match(/^>\s+(.+)$/);
      if (quote) {
        const parts = [];
        while (index < lines.length) {
          const item = lines[index].trim().match(/^>\s+(.+)$/);
          if (!item) break;
          parts.push(item[1]);
          index += 1;
        }
        blocks.push({ type: "quote", text: parts.join(" ") });
        continue;
      }
      const paragraph = [trimmed];
      index += 1;
      while (index < lines.length) {
        const next = lines[index].trim();
        if (!next || next.startsWith("```") || /^(#{1,4})\s+/.test(next) || /^[-*]\s+/.test(next) || /^\d+[.)]\s+/.test(next) || /^>\s+/.test(next) || /^[-*_]{3,}$/.test(next)) {
          break;
        }
        paragraph.push(next);
        index += 1;
      }
      blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    }
    return blocks;
  }
  function renderMarkdownBlock(block, index) {
    if (block.type === "heading") {
      const Tag = block.level <= 2 ? "h3" : "h4";
      return /* @__PURE__ */ React.createElement(Tag, { key: index }, renderInlineMarkdown(block.text));
    }
    if (block.type === "list") {
      const Tag = block.ordered ? "ol" : "ul";
      return /* @__PURE__ */ React.createElement(Tag, { key: index }, block.items.map((item, itemIndex) => /* @__PURE__ */ React.createElement("li", { key: itemIndex }, renderInlineMarkdown(item))));
    }
    if (block.type === "code") {
      return /* @__PURE__ */ React.createElement("pre", { key: index, className: "markdownCode" }, block.language && /* @__PURE__ */ React.createElement("span", null, block.language), /* @__PURE__ */ React.createElement("code", null, block.text));
    }
    if (block.type === "quote") {
      return /* @__PURE__ */ React.createElement("blockquote", { key: index }, renderInlineMarkdown(block.text));
    }
    if (block.type === "rule") {
      return /* @__PURE__ */ React.createElement("hr", { key: index });
    }
    return /* @__PURE__ */ React.createElement("p", { key: index }, renderInlineMarkdown(block.text));
  }
  function renderInlineMarkdown(text) {
    const parts = [];
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
    let lastIndex = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
      const token = match[0];
      if (token.startsWith("`")) {
        parts.push(/* @__PURE__ */ React.createElement("code", { key: parts.length }, token.slice(1, -1)));
      } else if (token.startsWith("**")) {
        parts.push(/* @__PURE__ */ React.createElement("strong", { key: parts.length }, token.slice(2, -2)));
      } else {
        const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        parts.push(
          /* @__PURE__ */ React.createElement("a", { key: parts.length, href: safeMarkdownHref(link?.[2] || ""), target: "_blank", rel: "noreferrer" }, link?.[1] || token)
        );
      }
      lastIndex = pattern.lastIndex;
    }
    if (lastIndex < text.length) parts.push(text.slice(lastIndex));
    return parts;
  }
  function safeMarkdownHref(value) {
    const href = String(value || "").trim();
    if (/^(https?:|mailto:)/i.test(href)) return href;
    if (href.startsWith("#")) return href;
    return "#";
  }
  function SuiteList({ suites, channel, runSuite, loading }) {
    const label = channel || "chat";
    if (!suites.length) return /* @__PURE__ */ React.createElement(EmptyState, { title: `No ${label} suites yet`, text: `Generate a ${label} suite from Bot Core Config.` });
    return /* @__PURE__ */ React.createElement("div", { className: "cardList" }, suites.map((suite) => /* @__PURE__ */ React.createElement("article", { className: "dataCard", key: suite.id }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, suite.name), /* @__PURE__ */ React.createElement("p", null, suite.id, " - ", suite.source)), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "ok" }, suiteChannelCount(suite, channel), " ", label, " cases"), /* @__PURE__ */ React.createElement(Pill, null, (suite.test_cases || []).length, " total cases"), Object.entries(suiteScenarioCounts(suite, channel)).slice(0, 3).map(([key, value]) => /* @__PURE__ */ React.createElement(Pill, { key }, key, ": ", value))), /* @__PURE__ */ React.createElement("div", { className: "buttonRow" }, /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "secondaryButton",
        type: "button",
        disabled: loading === `run-${suite.id}`,
        title: "Run this generated chat suite through Playwright and create a report.",
        onClick: () => runSuite(suite.id, channel)
      },
      /* @__PURE__ */ React.createElement(Icon, { name: "play_arrow" }),
      " ",
      loading === `run-${suite.id}` ? "Running..." : "Run Playwright"
    )))));
  }
  function RunList({ runs, channel, openReport }) {
    const label = channel || "chat";
    if (!runs.length) return /* @__PURE__ */ React.createElement(EmptyState, { title: `No ${label} runs yet`, text: `Run a ${label} suite to create reports.` });
    return /* @__PURE__ */ React.createElement("div", { className: "cardList" }, runs.map((run) => /* @__PURE__ */ React.createElement("article", { className: "dataCard compact", key: run.id }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, run.id), /* @__PURE__ */ React.createElement("p", null, run.created_at, " - ", label)), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: run.average_score >= 0.78 ? "ok" : "warn" }, run.average_score), /* @__PURE__ */ React.createElement(Pill, null, run.total_cases, " cases")), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: () => openReport(run.report_id) }, "Open Report"))));
  }
  function ReportView({ report, channel = "" }) {
    const label = channel || "chat";
    if (!report) return /* @__PURE__ */ React.createElement(EmptyState, { title: `No ${label} report open`, text: `Run a ${label} suite or open a previous ${label} report.` });
    const visibleCases = (report.case_results || []).filter((item) => !channel || item.channel === channel);
    const visibleRecommendations = (report.yellow_ai_recommendations || []).filter((item) => !channel || item.channel === channel);
    const statusCounts = visibleCases.reduce((counts, item) => {
      const status = item.score?.status || "unknown";
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {});
    const averageScore = visibleCases.length ? (visibleCases.reduce((total, item) => total + Number(item.score?.overall_score || 0), 0) / visibleCases.length).toFixed(3) : "-";
    return /* @__PURE__ */ React.createElement("div", { className: "reportView" }, /* @__PURE__ */ React.createElement("div", { className: "metricGrid five" }, /* @__PURE__ */ React.createElement(Metric, { label: "Average", value: averageScore }), /* @__PURE__ */ React.createElement(Metric, { label: "Cases", value: visibleCases.length }), /* @__PURE__ */ React.createElement(Metric, { label: "Passed", value: statusCounts.pass || 0 }), /* @__PURE__ */ React.createElement(Metric, { label: "Bot review", value: statusCounts.review || 0 }), /* @__PURE__ */ React.createElement(Metric, { label: "Setup issues", value: statusCounts.setup_error || 0 })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Yellow.ai Recommendations"), visibleRecommendations.slice(0, 8).map((item, index) => /* @__PURE__ */ React.createElement("div", { className: "recommendation", key: `${item.area}-${index}` }, /* @__PURE__ */ React.createElement("strong", null, item.area), /* @__PURE__ */ React.createElement("p", null, item.recommendation), /* @__PURE__ */ React.createElement("small", null, item.yellow_ai_hint))), !visibleRecommendations.length && /* @__PURE__ */ React.createElement(EmptyState, { title: "No recommendations yet", text: `Run ${label} tests to generate channel-specific recommendations.` })), /* @__PURE__ */ React.createElement("div", { className: "contextBlock" }, /* @__PURE__ */ React.createElement("h3", null, "Case Results"), visibleCases.slice(0, 8).map((item) => /* @__PURE__ */ React.createElement(CaseResultCard, { item, key: item.case_id })), !visibleCases.length && /* @__PURE__ */ React.createElement(EmptyState, { title: "No case results", text: `This report has no ${label} cases.` })));
  }
  function CaseResultCard({ item }) {
    const transcript = item.result?.transcript || [];
    const issues = item.score?.issues || [];
    return /* @__PURE__ */ React.createElement("article", { className: "caseResultCard" }, /* @__PURE__ */ React.createElement("div", { className: "caseResultHeader" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, item.flow_name), /* @__PURE__ */ React.createElement("span", null, item.channel, " - ", item.scenario_type, " - ", item.result?.adapter || "adapter")), /* @__PURE__ */ React.createElement(Pill, { tone: item.score?.status === "pass" ? "ok" : "warn" }, item.score?.status === "setup_error" ? "setup" : item.score?.overall_score)), item.result?.adapter_status && /* @__PURE__ */ React.createElement("p", { className: "mutedLine" }, "Status: ", item.result.adapter_status), !!issues.length && /* @__PURE__ */ React.createElement("ul", { className: "compactList" }, issues.slice(0, 3).map((issue) => /* @__PURE__ */ React.createElement("li", { key: issue }, issue))), !!transcript.length && /* @__PURE__ */ React.createElement("details", { className: "transcriptDetails" }, /* @__PURE__ */ React.createElement("summary", null, "Transcript ", /* @__PURE__ */ React.createElement("span", null, transcript.length, " turns")), /* @__PURE__ */ React.createElement("div", { className: "transcriptList" }, transcript.map((turn, index) => /* @__PURE__ */ React.createElement("div", { className: cx("transcriptTurn", turn.speaker), key: `${turn.turn}-${index}` }, /* @__PURE__ */ React.createElement("span", null, turn.speaker), /* @__PURE__ */ React.createElement("p", null, turn.text))))));
  }
  function DocumentList({ documents, analyzeDocument, loading }) {
    if (!documents.length) return /* @__PURE__ */ React.createElement(EmptyState, { title: "No documents yet", text: "Upload project knowledge for analyzer context." });
    return /* @__PURE__ */ React.createElement("div", { className: "cardList" }, documents.map((doc) => /* @__PURE__ */ React.createElement("article", { className: "dataCard", key: doc.id }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, doc.filename), /* @__PURE__ */ React.createElement("p", null, doc.id, " - ", Math.round((doc.size_bytes || 0) / 1024), " KB - ", doc.analysis_status)), /* @__PURE__ */ React.createElement("p", null, (doc.text_preview || "No readable preview extracted.").slice(0, 220)), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: loading === "analyze-doc", onClick: () => analyzeDocument(doc.id) }, "Analyze"))));
  }
  function ChangePlans({ plans, approvePlan, loading }) {
    if (!plans.length) return /* @__PURE__ */ React.createElement(EmptyState, { title: "No plans yet", text: "Analyze a project document to create change plans." });
    return /* @__PURE__ */ React.createElement("div", { className: "cardList" }, plans.map((plan) => /* @__PURE__ */ React.createElement("article", { className: "dataCard", key: plan.id }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, plan.document_name), /* @__PURE__ */ React.createElement("p", null, plan.id, " - ", plan.analysis_source || "local_rules", " - ", plan.status)), /* @__PURE__ */ React.createElement("p", null, plan.summary), /* @__PURE__ */ React.createElement("div", { className: "pillRow" }, /* @__PURE__ */ React.createElement(Pill, { tone: "warn" }, "approval required"), /* @__PURE__ */ React.createElement(Pill, null, (plan.suggested_changes || []).length, " changes"), /* @__PURE__ */ React.createElement(Pill, null, (plan.suggested_test_cases || []).length, " tests")), /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", disabled: plan.status === "approved" || loading === "approve-plan", onClick: () => approvePlan(plan.id) }, "Approve Plan"))));
  }
  function EmptyState({ title, text }) {
    return /* @__PURE__ */ React.createElement("div", { className: "emptyState" }, /* @__PURE__ */ React.createElement("h3", null, title), /* @__PURE__ */ React.createElement("p", null, text));
  }
  function SettingsDialog({ config, setConfig, setError }) {
    const [values, setValues] = useState({});
    const visibleKeys = ["DEFAULT_BOT_NAME", "DEFAULT_CHAT_ENDPOINT", "OPENAI_API_KEY", "OPENAI_MODEL"];
    useEffect(() => {
      if (!config?.settings) return;
      const next = {};
      Object.entries(config.settings).forEach(([key, item]) => {
        next[key] = item.secret ? "" : item.value || "";
      });
      setValues(next);
    }, [config]);
    if (!config) return null;
    const update = (key, value) => setValues((current) => ({ ...current, [key]: value }));
    async function save(event) {
      event.preventDefault();
      try {
        const payload = {};
        visibleKeys.forEach((key) => {
          payload[key] = values[key] || "";
        });
        setConfig(await api("/api/config", { method: "POST", body: JSON.stringify({ settings: payload }) }));
        document.querySelector("#settingsDialog")?.close();
      } catch (err) {
        setError(err.message);
      }
    }
    return /* @__PURE__ */ React.createElement("dialog", { id: "settingsDialog", className: "settingsDialog" }, /* @__PURE__ */ React.createElement("form", { onSubmit: save, className: "settingsForm" }, /* @__PURE__ */ React.createElement("div", { className: "dialogHeader" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h2", null, "Runtime Settings"), /* @__PURE__ */ React.createElement("p", null, "Saved locally so each bot can be tested without editing environment files.")), /* @__PURE__ */ React.createElement("button", { className: "iconButton", type: "button", onClick: () => document.querySelector("#settingsDialog")?.close() }, "x")), /* @__PURE__ */ React.createElement(SettingsSection, { title: "Defaults", keys: ["DEFAULT_BOT_NAME", "DEFAULT_CHAT_ENDPOINT"], values, update, config }), /* @__PURE__ */ React.createElement(SettingsSection, { title: "AI Generation", keys: ["OPENAI_API_KEY", "OPENAI_MODEL"], values, update, config }), /* @__PURE__ */ React.createElement("div", { className: "dialogActions" }, /* @__PURE__ */ React.createElement("button", { className: "secondaryButton", type: "button", onClick: () => document.querySelector("#settingsDialog")?.close() }, "Cancel"), /* @__PURE__ */ React.createElement("button", { type: "submit" }, "Save Settings"))));
  }
  function SettingsSection({ title, keys, values, update, config }) {
    return /* @__PURE__ */ React.createElement("section", { className: "settingsSection" }, /* @__PURE__ */ React.createElement("h3", null, title), /* @__PURE__ */ React.createElement("div", { className: "settingsGrid" }, keys.map((key) => {
      const item = config.settings[key] || {};
      return /* @__PURE__ */ React.createElement(Field, { label: key.replaceAll("_", " ").toLowerCase(), key }, /* @__PURE__ */ React.createElement(
        "input",
        {
          type: item.secret ? "password" : "text",
          value: values[key] || "",
          onChange: (event) => update(key, event.target.value),
          placeholder: item.secret && item.configured ? "Saved. Leave blank to keep current value." : ""
        }
      ));
    })));
  }
  ReactDOM.createRoot(document.getElementById("root")).render(/* @__PURE__ */ React.createElement(App, null));
})();
