const { useEffect, useMemo, useRef, useState } = React;

const emptyProfile = {
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
  flow_docs: "Order status, cancel order, refund status, complaint, agent handoff, fallback recovery.",
};

const defaultChatAutomationScript = `## Greeting and scope

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

const languageContinuityAutomationScript = `## Language continuity during active flow

#### Conversation Flow

###### Turn 1
**User:**
>> Hindi

**Bot:**
>> Bot confirms Hindi language preference and asks how it can help.

###### Turn 2
**User:**
>> mujhe installation karvana hai

**Bot:**
>> Bot continues in Hindi and asks the next installation-related question.

###### Turn 3
**User:**
>> So I was testing it.

**Bot:**
>> Bot should not switch to English only because this message is English. It should keep the selected Hindi language or ask a clarification without restarting the conversation.
`;

const installationE2EAutomationScript = `## Installation E2E happy path

#### Conversation Flow

###### Turn 1
**User:**
>> 🆕 New Installation

**Bot:**
>> Bot starts the installation flow and asks whether the machine has been delivered.

###### Turn 2
**User:**
>> Delivered

**Bot:**
>> Bot asks for the user's name.

###### Turn 3
**User:**
>> Test User

**Bot:**
>> Bot asks where the product was purchased from.

###### Turn 4
**User:**
>> Amazon

**Bot:**
>> Bot asks for the order ID or offers an unavailable-order fallback.

###### Turn 5
**User:**
>> Not Available

**Bot:**
>> Bot asks for the product category.

###### Turn 6
**User:**
>> Water Purifier

**Bot:**
>> Bot asks for the product name.

###### Turn 7
**User:**
>> Kent Grand Plus

**Bot:**
>> Bot asks for the installation pincode or location details.

###### Turn 8
**User:**
>> 560102

**Bot:**
>> Bot should continue collecting installation details such as address or contact information, or explain clearly if service is unavailable for the pincode.
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
  return <span className={cx("pill", tone)}>{children}</span>;
}

function Icon({ name, filled = false }) {
  return (
    <span className="material-symbols-outlined" style={{ fontVariationSettings: `'FILL' ${filled ? 1 : 0}` }}>
      {name}
    </span>
  );
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
    const nextProjectId =
      options.projectId ||
      (activeProjectId && nextProjects.some((project) => project.id === activeProjectId) ? activeProjectId : projectsPayload.active_project_id || nextProjects[0]?.id || "");

    const [chatsPayload, suitesPayload, runsPayload, docsPayload, snapshotsPayload, accessPayload, docsPagesPayload, configPayload] = await Promise.all([
      api(projectQuery("/api/chats", nextProjectId)),
      api(projectQuery("/api/suites", nextProjectId)),
      api(projectQuery("/api/runs", nextProjectId)),
      api(projectQuery("/api/documents", nextProjectId)),
      api(projectQuery("/api/platform-snapshots", nextProjectId)),
      api(projectQuery("/api/project-access", nextProjectId)),
      api("/api/docs/pages"),
      api("/api/config"),
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
    setDocsPages(docsPagesPayload.pages || []);
    setConfig(configPayload);

    const nextProject = nextProjects.find((project) => project.id === nextProjectId) || nextProjects[0];
    setProfile({ ...emptyProfile, ...(nextProject?.bot_profile || {}) });
    const preferredAnalyzerId = options.activeChatId || activeChatId;
    const preferredDocsChatId = options.activeDocsChatId || activeDocsChatId;
    const analyzer =
      (chatsPayload.chats || []).find((chat) => chat.id === preferredAnalyzerId && chat.mode === "analyzer") ||
      (chatsPayload.chats || []).find((chat) => chat.mode === "analyzer");
    const docs =
      (chatsPayload.chats || []).find((chat) => chat.id === preferredDocsChatId && chat.mode === "docs") ||
      (chatsPayload.chats || []).find((chat) => chat.mode === "docs");
    setActiveChatId(analyzer?.id || "");
    setActiveDocsChatId(docs?.id || "");
    if (!options.keepReport) setLatestReport(null);
  }

  useEffect(() => {
    api("/api/auth/session")
      .then(async (session) => {
        setAuth({ loading: false, authenticated: !!session.authenticated, user: session.user || null });
        if (session.authenticated) {
          await refresh({ keepReport: false });
        }
      })
      .catch((err) => {
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
        body: JSON.stringify({ name, bot_profile: profile }),
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
      body: JSON.stringify({ project_id: activeProjectId, mode }),
    });
    await refresh({
      keepReport: true,
      activeChatId: mode === "analyzer" ? chat.id : activeChatId,
      activeDocsChatId: mode === "docs" ? chat.id : activeDocsChatId,
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
        body: JSON.stringify({ content: content.trim() }),
      });
      setChats((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      await refresh({
        keepReport: true,
        activeChatId: mode === "analyzer" ? updated.id : activeChatId,
        activeDocsChatId: mode === "docs" ? updated.id : activeDocsChatId,
      });
      if (mode === "docs") setActiveDocsChatId(updated.id);
      else setActiveChatId(updated.id);
    });
  }

  async function saveProjectProfile() {
    await guarded("save-profile", async () => {
      await api(`/api/projects/${activeProjectId}`, {
        method: "PATCH",
        body: JSON.stringify({ bot_profile: profile }),
      });
      await refresh({ keepReport: true });
    });
  }

  async function generateSuite(extraChatContext = false) {
    await guarded("generate-suite", async () => {
      const profilePayload = { ...profile };
      if (extraChatContext && analyzerChat?.messages?.length) {
        profilePayload.flow_docs = `${profilePayload.flow_docs}\n\nAnalyzer chat context:\n${analyzerChat.messages
          .slice(-8)
          .map((message) => `${message.role}: ${message.content}`)
          .join("\n")}`;
      }
      await api("/api/generate-suite", {
        method: "POST",
        body: JSON.stringify({ project_id: activeProjectId, bot_profile: profilePayload }),
      });
      setActiveTab("testing");
      await refresh({ keepReport: true });
    });
  }

  async function runSuite(suiteId, channel) {
    await guarded(`run-${suiteId}`, async () => {
      const output = await api("/api/run-suite", {
        method: "POST",
        body: JSON.stringify({ suite_id: suiteId, channel }),
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
        body: JSON.stringify({ project_id: activeProjectId, bot_profile: profile, script }),
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
          options: goalPayload,
        }),
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
        body: JSON.stringify({ project_id: activeProjectId, bot_profile: profile, options }),
      });
      await refresh({ keepReport: true });
    });
  }

  async function saveYellowAccess(access) {
    await guarded("yellow-access", async () => {
      await api("/api/project-access", {
        method: "POST",
        body: JSON.stringify({ project_id: activeProjectId, ...access }),
      });
      await refresh({ keepReport: true });
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
        body: JSON.stringify({ project_id: activeProjectId, document_id: documentId, bot_profile: profile }),
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
        body: JSON.stringify({ chat_id: activeChatId }),
      });
      if (output.project?.id) {
        setProjects((current) => current.map((project) => (project.id === output.project.id ? output.project : project)));
      }
      setActiveTab("testing");
      await refresh({ keepReport: true });
    });
  }

  if (auth.loading) {
    return <SplashScreen />;
  }

  if (!auth.authenticated) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="appShell">
      <Sidebar
        user={auth.user}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        projects={projects}
        activeProjectId={activeProjectId}
        setProject={(projectId) => {
          setActiveProjectId(projectId);
          setActiveChatId("");
          setActiveDocsChatId("");
          refresh({ projectId, keepReport: false }).catch((err) => setError(err.message));
        }}
        chats={chats}
        activeChatId={activeTab === "docs" ? activeDocsChatId : activeChatId}
        setChat={(chat) => (chat.mode === "docs" ? setActiveDocsChatId(chat.id) : setActiveChatId(chat.id))}
        search={search}
        setSearch={setSearch}
        createProject={createProject}
        createChat={() => createChat(activeTab === "docs" ? "docs" : "analyzer").catch((err) => setError(err.message))}
        openSettings={() => document.querySelector("#settingsDialog")?.showModal()}
        refresh={() => refresh({ keepReport: true }).catch((err) => setError(err.message))}
        logout={logout}
      />
      <main className="workspace">
        <TopBar activeTab={activeTab} activeProject={activeProject} loading={loading} error={error} />
        {activeTab === "analyzer" && (
          <AnalyzerTab
            chat={analyzerChat}
            sendMessage={(content) => sendMessage("analyzer", content)}
            createSuite={() => generateSuite(true)}
            attachReport={attachReport}
            prepareGoalBrief={prepareGoalBrief}
            activeProject={activeProject}
            documents={documents}
            changePlans={changePlans}
            suites={suites}
            runs={runs}
            platformSnapshots={platformSnapshots}
            yellowAccess={yellowAccess}
            saveYellowAccess={saveYellowAccess}
            runPlatformSnapshot={runPlatformSnapshot}
            config={config}
            loading={loading}
          />
        )}
        {activeTab === "testing" && (
          <TestingTab
            profile={profile}
            setProfile={setProfile}
            saveProfile={saveProjectProfile}
            generateSuite={(channel) => generateSuite(false, channel)}
            suites={suites}
            runs={runs}
            latestReport={latestReport}
            runSuite={runSuite}
            runChatAutomation={runChatAutomation}
            runGoalChatAutomation={runGoalChatAutomation}
            goalBrief={activeProject?.goal_test_brief}
            openReport={openReport}
            config={config}
            loading={loading}
          />
        )}
        {activeTab === "docs" && (
          <DocsTab
            docsPages={docsPages}
            documents={documents}
            changePlans={changePlans}
            uploadDocument={uploadDocument}
            analyzeDocument={analyzeDocument}
            approvePlan={approvePlan}
            activeProjectId={activeProjectId}
            chat={docsChat}
            sendMessage={(content) => sendMessage("docs", content)}
            createDocsChat={() => createChat("docs").catch((err) => setError(err.message))}
            loading={loading}
          />
        )}
      </main>
      <SettingsDialog config={config} setConfig={setConfig} setError={setError} />
    </div>
  );
}

function SplashScreen() {
  return (
    <main className="authShell">
      <section className="authCard compact">
        <div className="authBrand">
          <div className="brandMark">QA</div>
          <div>
            <h1>QA Workbench</h1>
            <p>Loading workspace</p>
          </div>
        </div>
      </section>
    </main>
  );
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
        body: JSON.stringify({ email, password, full_name: fullName }),
      });
      await onAuthenticated(session);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authShell">
      <section className="authCard">
        <div className="authBrand">
          <div className="brandMark">QA</div>
          <div>
            <h1>QA Workbench</h1>
            <p>Sign in to your projects, chats, tests, and reports.</p>
          </div>
        </div>
        <div className="authTabs">
          <button className={cx(mode === "login" && "active")} type="button" onClick={() => setMode("login")}>
            Login
          </button>
          <button className={cx(mode === "signup" && "active")} type="button" onClick={() => setMode("signup")}>
            Sign up
          </button>
        </div>
        <form className="authForm" onSubmit={submit}>
          {mode === "signup" && (
            <Field label="Name">
              <input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your name" />
            </Field>
          )}
          <Field label="Email">
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" autoComplete="email" />
          </Field>
          <Field label="Password">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Minimum 8 characters"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
            />
          </Field>
          {error && <div className="authError">{error}</div>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait" : mode === "signup" ? "Create account" : "Login"}
          </button>
        </form>
      </section>
    </main>
  );
}

function Sidebar(props) {
  const mode = props.activeTab === "docs" ? "docs" : "analyzer";
  const filteredChats = props.chats
    .filter((chat) => chat.mode === mode)
    .filter((chat) => !props.search.trim() || chat.title.toLowerCase().includes(props.search.trim().toLowerCase()));
  return (
    <aside className="sidebar">
      <div className="sideBrand">
        <div className="brandMark">QA</div>
        <div>
          <strong>QA Workbench</strong>
          <span>V2.4.0</span>
        </div>
      </div>
      <button className="primarySideButton" type="button" onClick={props.createProject}>
        <Icon name="add" /> New project
      </button>
      <button className="sideAction" type="button" onClick={props.createChat}>
        <Icon name="chat" /> New chat
      </button>
      <label className="sideSearch">
        Search
        <input value={props.search} onChange={(event) => props.setSearch(event.target.value)} placeholder="Search chats" />
      </label>
      <nav className="sideNav">
        {[
          ["analyzer", "analytics", "Analyzer"],
          ["testing", "science", "Testing"],
          ["docs", "description", "Docs"],
        ].map(([tab, icon, label]) => (
          <button key={tab} className={cx("navButton", props.activeTab === tab && "active")} type="button" onClick={() => props.setActiveTab(tab)}>
            <Icon name={icon} filled={props.activeTab === tab} /> {label}
          </button>
        ))}
      </nav>
      <SectionTitle label="Projects" />
      <div className="sideList projectList">
        {props.projects.map((project) => (
          <button
            key={project.id}
            className={cx("sideListItem", project.id === props.activeProjectId && "active")}
            type="button"
            onClick={() => props.setProject(project.id)}
          >
            <span>{project.name}</span>
            <small>{project.yellow_ai_target?.platform || "local"}</small>
          </button>
        ))}
      </div>
      <SectionTitle label="Chats" />
      <div className="sideList chatList">
        {filteredChats.length ? (
          filteredChats.map((chat) => (
            <button key={chat.id} className={cx("sideListItem", chat.id === props.activeChatId && "active")} type="button" onClick={() => props.setChat(chat)}>
              <span>{chat.title}</span>
              <small>{chat.mode}</small>
            </button>
          ))
        ) : (
          <div className="sideEmpty">No {mode} chats yet</div>
        )}
      </div>
      <div className="sidebarBottom">
        <div className="userBadge">
          <Icon name="account_circle" />
          <span>{props.user?.email || "Signed in"}</span>
        </div>
        <button className="sideAction ghost" type="button" onClick={props.openSettings}>
          <Icon name="settings" /> Settings
        </button>
        <button className="sideAction ghost" type="button" onClick={props.refresh}>
          <Icon name="refresh" /> Refresh
        </button>
        <button className="sideAction ghost" type="button" onClick={props.logout}>
          <Icon name="logout" /> Logout
        </button>
      </div>
    </aside>
  );
}

function SectionTitle({ label }) {
  return <div className="sideSectionHeader">{label}</div>;
}

function TopBar({ activeTab, activeProject, loading, error }) {
  return (
    <header className="topBar">
      <div>
        <h1>{activeTab === "analyzer" ? "QA Analyzer" : activeTab === "testing" ? "Test Execution Board" : "Documentation Hub"}</h1>
        <p>{activeProject?.name || "Yellow.ai Chat QA Workbench"}</p>
      </div>
      <div className="topBarMeta">
        {error && <span className="statusPill error">{error}</span>}
        {loading && <span className="statusPill warn">Working</span>}
        <span className="statusPill">Local MVP</span>
      </div>
    </header>
  );
}

function AnalyzerTab({ chat, sendMessage, createSuite, attachReport, prepareGoalBrief, activeProject, documents, changePlans, suites, runs, platformSnapshots, yellowAccess, saveYellowAccess, runPlatformSnapshot, config, loading }) {
  const [message, setMessage] = useState("");
  const [showReportPicker, setShowReportPicker] = useState(false);
  function chooseReport(reportId) {
    setShowReportPicker(false);
    attachReport(reportId);
  }
  return (
    <div className="mainGrid analyzerGrid">
      <section className="workPanel chatPanel">
        <PanelHeader
          title="Analyzer Session"
          meta="SESSION ID: PROJECT-CONTEXT"
          actions={
            <>
              <button className="secondaryButton" type="button" onClick={() => setShowReportPicker(true)}>
                <Icon name="troubleshoot" /> Pinpoint report
              </button>
              <button className="secondaryButton" type="button" disabled={loading === "goal-brief"} onClick={prepareGoalBrief}>
                <Icon name="assignment" /> Prepare test brief
              </button>
              <button className="secondaryButton" type="button" onClick={createSuite}>
                <Icon name="science" /> Create suite
              </button>
              <button className="secondaryButton" type="button" disabled={loading === "platform-snapshot"} onClick={() => runPlatformSnapshot({ headless: false, wait_for_login: true })}>
                <Icon name="login" /> Connect session
              </button>
              <button className="secondaryButton" type="button" disabled={loading === "platform-snapshot"} onClick={() => runPlatformSnapshot()}>
                <Icon name="travel_explore" /> Run snapshot
              </button>
            </>
          }
        />
        <YellowAccessPrompt access={yellowAccess} saveYellowAccess={saveYellowAccess} loading={loading} />
        <ChatMessages chat={chat} empty="Start an analyzer chat for Yellow.ai docs, reports, RAG checks, or test planning." />
        <form
          className="chatComposer"
          onSubmit={(event) => {
            event.preventDefault();
            sendMessage(message);
            setMessage("");
          }}
        >
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask the analyzer what to inspect, test, or improve..." />
          <button type="submit" disabled={loading === "analyzer-chat"}>
            Send
          </button>
        </form>
        {showReportPicker && (
          <ReportPickerDialog
            runs={runs}
            suites={suites}
            loading={loading}
            onChoose={chooseReport}
            onClose={() => setShowReportPicker(false)}
          />
        )}
      </section>
      <aside className="workPanel contextPanel">
        <PanelHeader title="Project Context" meta="ATTACHED KNOWLEDGE" />
        <ContextPanel activeProject={activeProject} documents={documents} changePlans={changePlans} suites={suites} runs={runs} platformSnapshots={platformSnapshots} yellowAccess={yellowAccess} config={config} />
      </aside>
    </div>
  );
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
  return (
    <div className="modalOverlay" role="presentation" onMouseDown={onClose}>
      <section className="reportPickerDialog" role="dialog" aria-modal="true" aria-labelledby="report-picker-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialogHeader">
          <div>
            <h2 id="report-picker-title">Pinpoint Report</h2>
            <p>Pick the report Analyzer should inspect for exact Yellow.ai failure points.</p>
          </div>
          <button className="iconButton" type="button" aria-label="Close report picker" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="reportPickerBody">
          <Field label="Search reports">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="report id, run id, or suite name" autoFocus />
          </Field>
          <div className="reportChoiceList">
            {filteredRuns.map((run) => {
              const suite = suiteById[run.suite_id];
              return (
                <button className="reportChoice" type="button" key={`${run.id}-${run.report_id}`} disabled={loading === "analyzer-chat"} onClick={() => onChoose(run.report_id)}>
                  <div>
                    <strong>{run.report_id || "No report id"}</strong>
                    <span>{suite?.name || run.suite_id || "Generated report"}</span>
                    <small>{run.created_at || "No timestamp"} · {run.id}</small>
                  </div>
                  <div className="reportChoiceMeta">
                    <Pill tone={run.average_score >= 0.78 ? "ok" : "warn"}>{run.average_score ?? "-"}</Pill>
                    <Pill>{run.total_cases ?? 0} cases</Pill>
                    <Icon name="add_link" />
                  </div>
                </button>
              );
            })}
            {!filteredRuns.length && (
              <EmptyState
                title={runs.length ? "No matching reports" : "No reports yet"}
                text={runs.length ? "Try another report id, run id, or suite name." : "Run a chat test first, then attach the generated report here."}
              />
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function YellowAccessPrompt({ access, saveYellowAccess, loading }) {
  const accessReady = Boolean(access?.bot_id && access?.api_key_configured);
  const [expanded, setExpanded] = useState(!accessReady);
  const [values, setValues] = useState({
    bot_id: "",
    api_key: "",
    ui_base_url: "https://cloud.yellow.ai",
    console_url: "",
    chat_widget_url: "",
    environment: "",
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
      environment: access.environment || "",
    }));
    setExpanded(!(access.bot_id && access.api_key_configured));
  }, [access]);
  const update = (key, value) => setValues((current) => ({ ...current, [key]: value }));
  function submit(event) {
    event.preventDefault();
    saveYellowAccess(values).then(() => setExpanded(false));
  }
  if (accessReady && !expanded) {
    return (
      <div className="chatAccessPrompt ready compact">
        <div className="assistantBubble">
          <Icon name="verified" />
          <div>
            <strong>Yellow.ai access is saved for this project.</strong>
            <p>Bot {access.bot_id} is ready for platform snapshots and failure analysis context.</p>
          </div>
        </div>
        <div className="accessActions">
          <div className="pillRow">
            <Pill tone="ok">API key saved</Pill>
            <Pill tone="ok">{access.environment || "environment optional"}</Pill>
          </div>
          <button className="secondaryButton" type="button" onClick={() => setExpanded(true)}>
            <Icon name="edit" /> Update access
          </button>
        </div>
      </div>
    );
  }
  return (
    <form className={cx("chatAccessPrompt", accessReady && "ready")} onSubmit={submit}>
      <div className="assistantBubble">
        <Icon name={accessReady ? "verified" : "vpn_key"} />
        <div>
          <strong>{accessReady ? "Yellow.ai access is saved for this project." : "Share this bot's Yellow.ai access here."}</strong>
          <p>{accessReady ? "You can update it here whenever this project points to a different bot." : "Analyzer uses this project-level access for platform snapshots and failure root-cause context."}</p>
        </div>
      </div>
      <div className="accessGrid">
        <Field label="Bot ID">
          <input value={values.bot_id} onChange={(event) => update("bot_id", event.target.value)} placeholder="x177..." />
        </Field>
        <Field label="Bot API key">
          <input type="password" value={values.api_key} onChange={(event) => update("api_key", event.target.value)} placeholder={access?.api_key_configured ? "Saved. Leave blank to keep current key." : "Yellow.ai bot API key"} />
        </Field>
        <Field label="Yellow.ai UI base">
          <input value={values.ui_base_url} onChange={(event) => update("ui_base_url", event.target.value)} placeholder="https://cloud.yellow.ai" />
        </Field>
        <Field label="Console URL">
          <input value={values.console_url} onChange={(event) => update("console_url", event.target.value)} placeholder="Optional direct Studio/Automation URL" />
        </Field>
        <Field label="Chat widget URL">
          <input value={values.chat_widget_url} onChange={(event) => update("chat_widget_url", event.target.value)} placeholder="Optional liveBot/widget URL" />
        </Field>
        <Field label="Environment">
          <input value={values.environment} onChange={(event) => update("environment", event.target.value)} placeholder="staging / prod" />
        </Field>
      </div>
      <div className="accessActions">
        <div className="pillRow">
          <Pill tone={access?.api_key_configured ? "ok" : "warn"}>{access?.api_key_configured ? "API key saved" : "API key needed"}</Pill>
          <Pill tone={access?.bot_id ? "ok" : "warn"}>{access?.bot_id ? "Bot ID saved" : "Bot ID needed"}</Pill>
        </div>
        <button type="submit" disabled={loading === "yellow-access"}>
          <Icon name="save" /> Save access
        </button>
      </div>
    </form>
  );
}

function ContextPanel({ activeProject, documents, changePlans, suites, runs, platformSnapshots, yellowAccess, config }) {
  const target = activeProject?.yellow_ai_target || {};
  const latestSnapshot = platformSnapshots[0];
  const goalBrief = activeProject?.goal_test_brief;
  return (
    <div className="contextStack">
      <div className="metricGrid">
        <Metric label="Docs" value={documents.length} />
        <Metric label="Plans" value={changePlans.length} />
        <Metric label="Suites" value={suites.length} />
        <Metric label="Snapshots" value={platformSnapshots.length} />
      </div>
      <div className="contextBlock">
        <h3>Yellow.ai Target</h3>
        <div className="pillRow">
          {Object.keys(target).length ? Object.entries(target).map(([key, value]) => <Pill key={key}>{key.replaceAll("_", " ")}: {value}</Pill>) : <Pill>No target saved</Pill>}
        </div>
      </div>
      <div className="contextBlock">
        <h3>Provider Status</h3>
        <div className="statusRows">
          <StatusRow label="OpenAI" ready={config?.openai?.configured} value={config?.openai?.provider || "openai"} />
          <StatusRow label="Playwright" ready={config?.playwright?.available} value={config?.playwright?.package || "browser runner"} />
          <StatusRow label="Yellow.ai Access" ready={Boolean(yellowAccess?.bot_id && yellowAccess?.api_key_configured)} value={yellowAccess?.bot_id || "ask in chat"} />
          <StatusRow label="Platform Snapshot" ready={config?.platform_snapshot?.available} value={config?.platform_snapshot?.package || "crawler"} />
          <StatusRow label="Storage" ready={config?.storage?.configured} value={config?.storage?.provider || "local_json"} />
        </div>
      </div>
      <div className="contextBlock">
        <h3>Latest Platform Snapshot</h3>
        {latestSnapshot ? (
          <div className="snapshotSummary">
            <div className="pillRow">
              <Pill tone={latestSnapshot.status === "ok" ? "ok" : "warn"}>{latestSnapshot.status}</Pill>
              <Pill>{latestSnapshot.page_count || 0} pages</Pill>
              <Pill>{latestSnapshot.network_event_count || 0} network signals</Pill>
            </div>
            <p>{latestSnapshot.summary}</p>
          </div>
        ) : (
          <EmptyState title="No platform snapshot" text="Run a read-only Yellow.ai snapshot to attach agents, workflows, tools, and KB context automatically." />
        )}
      </div>
      <div className="contextBlock">
        <h3>Goal Test Brief</h3>
        {goalBrief?.id ? (
          <div className="snapshotSummary">
            <div className="pillRow">
              <Pill tone="ok">ready</Pill>
              <Pill>{goalBrief.max_turns || 10} turns</Pill>
            </div>
            <p>{goalBrief.title || goalBrief.goal}</p>
          </div>
        ) : (
          <EmptyState title="No goal brief" text="Use Analyzer to prepare an adaptive test brief for the Testing tab." />
        )}
      </div>
      <div className="contextBlock">
        <h3>Suggested Next Actions</h3>
        <ul className="compactList">
          <li>{latestSnapshot ? `Use ${latestSnapshot.id} for failure root-cause analysis.` : "Run a platform snapshot to attach Studio context automatically."}</li>
          <li>{goalBrief?.id ? `Run prepared goal brief ${goalBrief.id}.` : "Prepare a goal-driven test brief from Analyzer."}</li>
          <li>{changePlans[0] ? `Review ${changePlans[0].id} from ${changePlans[0].document_name}` : "Upload a Yellow.ai guide, flow spec, or transcript if API access is incomplete."}</li>
          <li>{suites[0] ? `Run or inspect ${suites[0].name}` : "Generate a first regression suite."}</li>
          <li>{runs[0] ? `Open latest report ${runs[0].report_id}` : "Run a real web-widget chat automation script."}</li>
        </ul>
      </div>
    </div>
  );
}

function suiteChannelCount(suite, channel) {
  return (suite.test_cases || []).filter((item) => item.channel === channel).length;
}

function suiteHasChannel(suite, channel) {
  return suiteChannelCount(suite, channel) > 0;
}

function suiteScenarioCounts(suite, channel) {
  return (suite.test_cases || [])
    .filter((item) => item.channel === channel)
    .reduce((counts, item) => {
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

function TestingTab({ profile, setProfile, saveProfile, generateSuite, suites, runs, latestReport, runSuite, runChatAutomation, runGoalChatAutomation, goalBrief, openReport, config, loading }) {
  const testChannel = "chat";
  const activeSuites = suites.filter((suite) => suiteHasChannel(suite, testChannel));
  const activeRuns = runs.filter((run) => runMatchesChannel(run, testChannel));
  const runsScrollRef = useRef(null);
  const activeCaseCount = activeSuites.reduce((total, suite) => total + suiteChannelCount(suite, testChannel), 0);
  const activeReport = reportHasChannel(latestReport, testChannel) ? latestReport : null;
  useEffect(() => {
    runsScrollRef.current?.scrollTo({ top: 0 });
  }, [activeRuns[0]?.id]);
  return (
    <div className="testingStack">
      <section className="workPanel testingModePanel">
        <PanelHeader title="Testing Workspace" meta="YELLOW.AI CHAT TESTING" />
        <div className="testingChannelTabs single">
          <button className="active" type="button">
            <Icon name="chat" filled /> Chat Testing
          </button>
        </div>
        <div className="testingModeSummary">
          <Metric label="Suites" value={activeSuites.length} />
          <Metric label="Cases" value={activeCaseCount} />
          <Metric label="Runs" value={activeRuns.length} />
          <Metric label="Reports" value={activeRuns.filter((run) => run.report_id).length} />
        </div>
      </section>
      <div className="mainGrid testingGrid">
        <section className="workPanel">
          <PanelHeader title="Bot Core Config" meta="CHAT SUITE INPUTS" />
          <BotCoreConfig
            profile={profile}
            setProfile={setProfile}
            saveProfile={saveProfile}
            generateSuite={() => generateSuite("chat")}
            generateSuiteLabel="Generate Chat Suite"
            loading={loading}
          />
        </section>
        <section className="workPanel">
          <PanelHeader title="Run Chat Tests" meta="REAL WEB-WIDGET AUTOMATION" />
          <ChatAutomationPanel
            profile={profile}
            setProfile={setProfile}
            runChatAutomation={runChatAutomation}
            runGoalChatAutomation={runGoalChatAutomation}
            goalBrief={goalBrief}
            config={config}
            loading={loading}
          />
        </section>
      </div>
      <div className="mainGrid testingGrid">
        <section className="workPanel scrollPanel">
          <PanelHeader title="Chat Suites" meta={`${activeSuites.length} TOTAL`} />
          <div className="scrollRegion">
            <SuiteList suites={activeSuites} channel={testChannel} runSuite={runSuite} loading={loading} />
          </div>
        </section>
        <section className="workPanel scrollPanel">
          <PanelHeader title="Chat Runs" meta={`${activeRuns.length} RECENT`} />
          <div className="scrollRegion" ref={runsScrollRef}>
            <RunList runs={activeRuns} channel={testChannel} openReport={openReport} />
          </div>
        </section>
      </div>
      <section className="workPanel reportPanel">
        <PanelHeader title="Chat Report" meta={activeReport?.id || "NO REPORT SELECTED"} />
        <ReportView report={activeReport} channel={testChannel} />
      </section>
    </div>
  );
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
  return (
    <div className="automationPanel">
      <div className="automationHeader">
        <div>
          <h3>Chat Automation</h3>
          <p>Goal-driven exploration or Markdown scripts run through the configured web widget and produce scenario-level project reports.</p>
        </div>
        <div className="pillRow">
          <Pill tone={playwright.available ? "ok" : "warn"}>{playwright.available ? "Playwright ready" : "Playwright setup"}</Pill>
          <Pill tone={endpointReady ? "ok" : "warn"}>{endpointReady ? "URL ready" : "URL missing"}</Pill>
        </div>
      </div>
      <section className="goalRunnerPanel">
        <div className="sectionTitleRow">
          <div>
            <h4>Goal-Driven Test</h4>
            <p>Describe the journey once. The tester observes bot replies, chooses clicks/messages adaptively, and stops on success, loop, or failure.</p>
          </div>
          <Pill tone="ok">Adaptive</Pill>
        </div>
        {goalBrief?.id && (
          <div className="briefNotice">
            <Icon name="assignment_turned_in" />
            <div>
              <strong>{goalBrief.title || "Analyzer test brief loaded"}</strong>
              <span>{goalBrief.reasoning || "Prepared from the current analyzer chat, reports, docs, and platform context."}</span>
            </div>
            <button className="secondaryButton compactButton" type="button" onClick={() => applyGoalBrief(goalBrief)}>
              Reload fields
            </button>
          </div>
        )}
        <Field label="Test goal">
          <textarea className="compactTextarea" value={goal} onChange={(event) => setGoal(event.target.value)} />
        </Field>
        <div className="twoCol">
          <Field label="Constraints">
            <textarea className="compactTextarea" value={constraints} onChange={(event) => setConstraints(event.target.value)} />
          </Field>
          <Field label="Test data">
            <textarea className="compactTextarea" value={testData} onChange={(event) => setTestData(event.target.value)} />
          </Field>
        </div>
        <div className="twoCol">
          <Field label="Success criteria">
            <textarea className="compactTextarea" value={successCriteria} onChange={(event) => setSuccessCriteria(event.target.value)} />
          </Field>
          <Field label="Max adaptive turns">
            <input type="number" min="2" max="20" inputMode="numeric" value={maxTurns} onChange={(event) => setMaxTurns(event.target.value)} />
          </Field>
        </div>
        <div className="automationActions">
          <button
            type="button"
            disabled={loading === "goal-chat-automation" || !endpointReady || !goal.trim()}
            onClick={() => runGoalChatAutomation({ goal, constraints, test_data: testData, success_criteria: successCriteria, max_turns: maxTurns })}
          >
            <Icon name="psychology" /> {loading === "goal-chat-automation" ? "Running adaptive test..." : "Run Goal-Driven Test"}
          </button>
        </div>
      </section>
      <details className="testAdvancedDetails">
        <summary>Widget setup</summary>
        <div className="twoCol">
          <Field label="Launcher selector">
            <input value={profile.chat_launcher_selector || ""} onChange={(event) => update("chat_launcher_selector", event.target.value)} placeholder="#ymDivBar" />
          </Field>
          <Field label="Input selector">
            <input value={profile.chat_input_selector || ""} onChange={(event) => update("chat_input_selector", event.target.value)} placeholder="textarea, input[type='text']" />
          </Field>
          <Field label="Message selector">
            <input value={profile.chat_message_selector || ""} onChange={(event) => update("chat_message_selector", event.target.value)} placeholder="[class*='message']" />
          </Field>
          <Field label="Send button selector">
            <input value={profile.chat_send_selector || ""} onChange={(event) => update("chat_send_selector", event.target.value)} placeholder="Optional" />
          </Field>
          <Field label="Iframe hint">
            <input value={profile.chat_frame_hint || ""} onChange={(event) => update("chat_frame_hint", event.target.value)} placeholder="Optional frame URL/name" />
          </Field>
          <Field label="Ready selector">
            <input value={profile.chat_ready_selector || ""} onChange={(event) => update("chat_ready_selector", event.target.value)} placeholder="Optional" />
          </Field>
          <Field label="Timeout seconds">
            <input value={profile.chat_response_timeout_seconds || "40"} onChange={(event) => update("chat_response_timeout_seconds", event.target.value)} inputMode="numeric" />
          </Field>
        </div>
        <label className="checkField automationCheck">
          <input
            type="checkbox"
            checked={(profile.chat_playwright_headless || "true") !== "false"}
            onChange={(event) => update("chat_playwright_headless", event.target.checked ? "true" : "false")}
          />
          <span>Headless browser</span>
        </label>
      </details>
      <details className="testAdvancedDetails">
        <summary>Scripted regression runner</summary>
        <Field label="Markdown script">
          <textarea className="automationScript" value={script} onChange={(event) => setScript(event.target.value)} />
        </Field>
        <div className="scriptMetaRow">
          <Pill tone={turnsInScript >= 6 ? "ok" : "warn"}>{turnsInScript || 0} turns</Pill>
          <span>{scriptTitle(script)}</span>
        </div>
        {scriptIsShort && (
          <p className="fieldHint warnText">
            This script is short. It will stop after {turnsInScript} user turns. Add more User/Bot turns for deeper regression coverage.
          </p>
        )}
        <p className="fieldHint">
          Use exact <code>User:</code> / <code>Bot:</code> turn blocks. For quick replies, make the User value exactly match the visible option.
        </p>
        <div className="automationActions">
          <input className="scriptFileInput" type="file" accept=".md,.txt" onChange={(event) => loadScriptFile(event.target.files[0])} />
          <button type="button" disabled={loading === "chat-automation" || !endpointReady} onClick={() => runChatAutomation(script)}>
            <Icon name="play_arrow" /> Run Scripted Test
          </button>
        </div>
      </details>
    </div>
  );
}

function BotCoreConfig({ profile, setProfile, saveProfile, generateSuite, generateSuiteLabel = "Generate Test Suite", loading }) {
  const update = (key, value) => setProfile((current) => ({ ...current, [key]: value }));
  return (
    <div className="configForm">
      <div className="twoCol">
        <Field label="Bot name">
          <input value={profile.bot_name || ""} onChange={(event) => update("bot_name", event.target.value)} />
        </Field>
        <Field label="Chat cases to generate">
          <input
            type="number"
            min="1"
            max="60"
            inputMode="numeric"
            value={profile.chat_case_count || "12"}
            onChange={(event) => update("chat_case_count", event.target.value)}
          />
        </Field>
      </div>
      <Field label="Chat endpoint / widget URL">
        <input value={profile.chat_endpoint || ""} onChange={(event) => update("chat_endpoint", event.target.value)} placeholder="https://..." />
      </Field>
      <Field label="Business goal">
        <textarea value={profile.business_goal || ""} onChange={(event) => update("business_goal", event.target.value)} />
      </Field>
      <Field label="Journeys / risks to cover">
        <textarea value={profile.flow_docs || ""} onChange={(event) => update("flow_docs", event.target.value)} />
      </Field>
      <div className="buttonRow">
        <button type="button" onClick={generateSuite} disabled={loading === "generate-suite"}>
          <Icon name="play_arrow" /> {generateSuiteLabel}
        </button>
        <button className="secondaryButton" type="button" onClick={saveProfile} disabled={loading === "save-profile"}>
          Save Project Profile
        </button>
      </div>
    </div>
  );
}

function DocsTab({ docsPages, documents, changePlans, uploadDocument, analyzeDocument, approvePlan, activeProjectId, chat, sendMessage, createDocsChat, loading }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState("");
  async function searchDocs(event) {
    event.preventDefault();
    const payload = await api("/api/docs/search", {
      method: "POST",
      body: JSON.stringify({ project_id: activeProjectId, query }),
    });
    setResults(payload.results || []);
  }
  return (
    <div className="docsStack">
      <section className="workPanel">
        <PanelHeader title="Knowledge Base" meta="HANDBOOK + PROJECT DOCS" />
        <form className="searchHero" onSubmit={searchDocs}>
          <Icon name="search" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search V3 routing, RAG testing, provider setup..." />
          <button type="submit">Search</button>
        </form>
        <div className="docGrid">
          {(results.length ? results : docsPages.slice(0, 8)).map((page) => (
            <article className="docCard" key={`${page.type || "page"}-${page.id}`}>
              <div className="docIcon"><Icon name={page.type === "document" ? "article" : "description"} /></div>
              <h3>{page.title}</h3>
              <Pill>{page.category}</Pill>
              <p>{(page.excerpt || page.body || "").slice(0, 260)}</p>
            </article>
          ))}
        </div>
      </section>
      <div className="mainGrid docsGrid">
        <section className="workPanel">
          <PanelHeader title="Project Knowledge" meta={`${documents.length} DOCS`} />
          <input className="fileInput" type="file" accept=".pdf,.docx,.md,.txt,.json,.csv" onChange={(event) => uploadDocument(event.target.files[0])} />
          <DocumentList documents={documents} analyzeDocument={analyzeDocument} loading={loading} />
        </section>
        <section className="workPanel">
          <PanelHeader title="Change Plans" meta={`${changePlans.length} PLANS`} />
          <ChangePlans plans={changePlans} approvePlan={approvePlan} loading={loading} />
        </section>
      </div>
      <section className="workPanel">
        <PanelHeader title="Docs Assistant" meta="SOURCE-GROUNDED HELP" actions={<button className="secondaryButton" type="button" onClick={createDocsChat}>New docs chat</button>} />
        <ChatMessages chat={chat} empty="Ask about this tool, Yellow.ai V2/V3, RAG, chat testing, or setup." compact />
        <form
          className="chatComposer"
          onSubmit={(event) => {
            event.preventDefault();
            sendMessage(message);
            setMessage("");
          }}
        >
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask the docs assistant..." />
          <button type="submit" disabled={loading === "docs-chat"}>Ask</button>
        </form>
      </section>
    </div>
  );
}

function PanelHeader({ title, meta, actions }) {
  return (
    <div className="panelHeader">
      <div>
        <h2>{title}</h2>
        {meta && <span>{meta}</span>}
      </div>
      {actions && <div className="buttonRow">{actions}</div>}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metricCard">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusRow({ label, value, ready }) {
  return (
    <div className="statusRow">
      <span>{label}</span>
      <Pill tone={ready ? "ok" : "warn"}>{ready ? "Ready" : "Needs setup"}</Pill>
      <code>{value}</code>
    </div>
  );
}

function ChatMessages({ chat, empty, compact = false }) {
  const messages = chat?.messages || [];
  if (!messages.length) {
    return (
      <div className={cx("chatCanvas", compact && "compact")}>
        <div className="emptyChat">
          <h3>{empty}</h3>
          <p>Project docs, test suites, reports, and Yellow.ai target metadata are available as context.</p>
        </div>
      </div>
    );
  }
  return (
    <div className={cx("chatCanvas", compact && "compact")}>
      {messages.map((message) => (
        <article className={cx("message", message.role)} key={message.id}>
          <span className="messageRole">{message.role}</span>
          <MarkdownText content={message.content} />
        </article>
      ))}
    </div>
  );
}

function MarkdownText({ content }) {
  const blocks = parseMarkdown(String(content || ""));
  if (!blocks.length) return <div className="markdownBody"><p /></div>;
  return (
    <div className="markdownBody">
      {blocks.map((block, index) => renderMarkdownBlock(block, index))}
    </div>
  );
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
    return <Tag key={index}>{renderInlineMarkdown(block.text)}</Tag>;
  }
  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
        ))}
      </Tag>
    );
  }
  if (block.type === "code") {
    return (
      <pre key={index} className="markdownCode">
        {block.language && <span>{block.language}</span>}
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === "quote") {
    return <blockquote key={index}>{renderInlineMarkdown(block.text)}</blockquote>;
  }
  if (block.type === "rule") {
    return <hr key={index} />;
  }
  return <p key={index}>{renderInlineMarkdown(block.text)}</p>;
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
      parts.push(<code key={parts.length}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      parts.push(<strong key={parts.length}>{token.slice(2, -2)}</strong>);
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      parts.push(
        <a key={parts.length} href={safeMarkdownHref(link?.[2] || "")} target="_blank" rel="noreferrer">
          {link?.[1] || token}
        </a>
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
  const label = "chat";
  if (!suites.length) return <EmptyState title={`No ${label} suites yet`} text={`Generate a ${label} suite from Bot Core Config.`} />;
  return (
    <div className="cardList">
      {suites.map((suite) => (
        <article className="dataCard" key={suite.id}>
          <div>
            <h3>{suite.name}</h3>
            <p>{suite.id} - {suite.source}</p>
          </div>
          <div className="pillRow">
            <Pill tone="ok">{suiteChannelCount(suite, channel)} {label} cases</Pill>
            <Pill>{(suite.test_cases || []).length} total cases</Pill>
            {Object.entries(suiteScenarioCounts(suite, channel)).slice(0, 3).map(([key, value]) => <Pill key={key}>{key}: {value}</Pill>)}
          </div>
          <div className="buttonRow">
            <button
              className="secondaryButton"
              type="button"
              disabled={loading === `run-${suite.id}`}
              title="Run this generated chat suite through Playwright and create a report."
              onClick={() => runSuite(suite.id, channel)}
            >
              <Icon name="play_arrow" /> {loading === `run-${suite.id}` ? "Running..." : "Run Playwright"}
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function RunList({ runs, channel, openReport }) {
  const label = "chat";
  if (!runs.length) return <EmptyState title={`No ${label} runs yet`} text={`Run a ${label} suite to create reports.`} />;
  return (
    <div className="cardList">
      {runs.map((run) => (
        <article className="dataCard compact" key={run.id}>
          <div>
            <h3>{run.id}</h3>
            <p>{run.created_at} - {label}</p>
          </div>
          <div className="pillRow">
            <Pill tone={run.average_score >= 0.78 ? "ok" : "warn"}>{run.average_score}</Pill>
            <Pill>{run.total_cases} cases</Pill>
          </div>
          <button className="secondaryButton" type="button" onClick={() => openReport(run.report_id)}>Open Report</button>
        </article>
      ))}
    </div>
  );
}

function ReportView({ report, channel = "" }) {
  const label = "chat";
  if (!report) return <EmptyState title={`No ${label} report open`} text={`Run a ${label} suite or open a previous ${label} report.`} />;
  const visibleCases = (report.case_results || []).filter((item) => !channel || item.channel === channel);
  const visibleRecommendations = (report.yellow_ai_recommendations || []).filter((item) => !channel || item.channel === channel);
  const statusCounts = visibleCases.reduce((counts, item) => {
    const status = item.score?.status || "unknown";
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
  const averageScore = visibleCases.length
    ? (visibleCases.reduce((total, item) => total + Number(item.score?.overall_score || 0), 0) / visibleCases.length).toFixed(3)
    : "-";
  return (
    <div className="reportView">
      <div className="metricGrid five">
        <Metric label="Average" value={averageScore} />
        <Metric label="Cases" value={visibleCases.length} />
        <Metric label="Passed" value={statusCounts.pass || 0} />
        <Metric label="Bot review" value={statusCounts.review || 0} />
        <Metric label="Setup issues" value={statusCounts.setup_error || 0} />
      </div>
      <div className="contextBlock">
        <h3>Yellow.ai Recommendations</h3>
        {visibleRecommendations.slice(0, 8).map((item, index) => (
          <div className="recommendation" key={`${item.area}-${index}`}>
            <strong>{item.area}</strong>
            <p>{item.recommendation}</p>
            <small>{item.yellow_ai_hint}</small>
          </div>
        ))}
        {!visibleRecommendations.length && <EmptyState title="No recommendations yet" text={`Run ${label} tests to generate channel-specific recommendations.`} />}
      </div>
      <div className="contextBlock">
        <h3>Case Results</h3>
        {visibleCases.slice(0, 8).map((item) => <CaseResultCard item={item} key={item.case_id} />)}
        {!visibleCases.length && <EmptyState title="No case results" text={`This report has no ${label} cases.`} />}
      </div>
    </div>
  );
}

function CaseResultCard({ item }) {
  const transcript = item.result?.transcript || [];
  const issues = item.score?.issues || [];
  return (
    <article className="caseResultCard">
      <div className="caseResultHeader">
        <div>
          <strong>{item.flow_name}</strong>
          <span>{item.channel} - {item.scenario_type} - {item.result?.adapter || "adapter"}</span>
        </div>
        <Pill tone={item.score?.status === "pass" ? "ok" : "warn"}>{item.score?.status === "setup_error" ? "setup" : item.score?.overall_score}</Pill>
      </div>
      {item.result?.adapter_status && <p className="mutedLine">Status: {item.result.adapter_status}</p>}
      {!!issues.length && (
        <ul className="compactList">
          {issues.slice(0, 3).map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      )}
      {!!transcript.length && (
        <details className="transcriptDetails">
          <summary>Transcript <span>{transcript.length} turns</span></summary>
          <div className="transcriptList">
            {transcript.map((turn, index) => (
              <div className={cx("transcriptTurn", turn.speaker)} key={`${turn.turn}-${index}`}>
                <span>{turn.speaker}</span>
                <p>{turn.text}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </article>
  );
}

function DocumentList({ documents, analyzeDocument, loading }) {
  if (!documents.length) return <EmptyState title="No documents yet" text="Upload project knowledge for analyzer context." />;
  return (
    <div className="cardList">
      {documents.map((doc) => (
        <article className="dataCard" key={doc.id}>
          <div>
            <h3>{doc.filename}</h3>
            <p>{doc.id} - {Math.round((doc.size_bytes || 0) / 1024)} KB - {doc.analysis_status}</p>
          </div>
          <p>{(doc.text_preview || "No readable preview extracted.").slice(0, 220)}</p>
          <button className="secondaryButton" type="button" disabled={loading === "analyze-doc"} onClick={() => analyzeDocument(doc.id)}>Analyze</button>
        </article>
      ))}
    </div>
  );
}

function ChangePlans({ plans, approvePlan, loading }) {
  if (!plans.length) return <EmptyState title="No plans yet" text="Analyze a project document to create change plans." />;
  return (
    <div className="cardList">
      {plans.map((plan) => (
        <article className="dataCard" key={plan.id}>
          <div>
            <h3>{plan.document_name}</h3>
            <p>{plan.id} - {plan.analysis_source || "local_rules"} - {plan.status}</p>
          </div>
          <p>{plan.summary}</p>
          <div className="pillRow">
            <Pill tone="warn">approval required</Pill>
            <Pill>{(plan.suggested_changes || []).length} changes</Pill>
            <Pill>{(plan.suggested_test_cases || []).length} tests</Pill>
          </div>
          <button className="secondaryButton" type="button" disabled={plan.status === "approved" || loading === "approve-plan"} onClick={() => approvePlan(plan.id)}>
            Approve Plan
          </button>
        </article>
      ))}
    </div>
  );
}

function EmptyState({ title, text }) {
  return (
    <div className="emptyState">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
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
  return (
    <dialog id="settingsDialog" className="settingsDialog">
      <form onSubmit={save} className="settingsForm">
        <div className="dialogHeader">
          <div>
            <h2>Runtime Settings</h2>
            <p>Saved locally so each bot can be tested without editing environment files.</p>
          </div>
          <button className="iconButton" type="button" onClick={() => document.querySelector("#settingsDialog")?.close()}>x</button>
        </div>
        <SettingsSection title="Defaults" keys={["DEFAULT_BOT_NAME", "DEFAULT_CHAT_ENDPOINT"]} values={values} update={update} config={config} />
        <SettingsSection title="AI Generation" keys={["OPENAI_API_KEY", "OPENAI_MODEL"]} values={values} update={update} config={config} />
        <div className="dialogActions">
          <button className="secondaryButton" type="button" onClick={() => document.querySelector("#settingsDialog")?.close()}>Cancel</button>
          <button type="submit">Save Settings</button>
        </div>
      </form>
    </dialog>
  );
}

function SettingsSection({ title, keys, values, update, config }) {
  return (
    <section className="settingsSection">
      <h3>{title}</h3>
      <div className="settingsGrid">
        {keys.map((key) => {
          const item = config.settings[key] || {};
          return (
            <Field label={key.replaceAll("_", " ").toLowerCase()} key={key}>
              <input
                type={item.secret ? "password" : "text"}
                value={values[key] || ""}
                onChange={(event) => update(key, event.target.value)}
                placeholder={item.secret && item.configured ? "Saved. Leave blank to keep current value." : ""}
              />
            </Field>
          );
        })}
      </div>
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
