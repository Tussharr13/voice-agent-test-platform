# Yellow.ai Platform Deep Dive

Date: 2026-06-06  
Scope: Read-only inspection of the open Yellow.ai Chrome sessions plus existing local scrape artifacts in this project.

## Executive Summary

Yellow.ai currently appears split across two related product surfaces:

- **Nexus**: the newer AI-agent-native workbench for agent creation, agentic workflows, tools, evaluators, testing, and action triage.
- **Cloud**: the broader enterprise bot operations platform that contains build modules, knowledge/data modules, analytics, inbox operations, campaigns, extensions, settings, and a Copilot-style assistant.

For our voice-agent QA platform, Nexus is the closest conceptual match for **agent design, tool wiring, evaluation, and debugging**, while Cloud is the closest match for **production operations, analytics, conversations, KB, user data, and live support workflows**.

## Inspection Notes And Limits

I did not edit anything in Yellow.ai. I avoided mutation controls such as Publish, Save, Run, Execute, Send message, Delete, Retry, feedback, and any form submission.

Nexus module inspection worked through authenticated pages and temporary read-only tabs. Cloud started from an authenticated conversation/overview page, but direct module navigation redirected to `cloud.yellow.ai/auth/login`. Because of that, the Cloud section combines:

- the captured authenticated Cloud overview/conversation content,
- the visible Cloud sidebar/module map,
- the existing local scrape files in `yellow_ai_agent_documenter/output/`,
- the existing `jfl_voice_x_spec.md` document.

## Product Model

At a product level, Yellow.ai is not just a bot builder. It is a full lifecycle platform:

1. **Design**: define agent identity, rules, tools, workflows, channels, and knowledge.
2. **Build**: create flows, workflows, functions, API integrations, and business objects.
3. **Test**: run test cases, evaluators, safety checks, and action triage.
4. **Deploy**: publish agents, connect channels, route conversations, and run campaigns.
5. **Operate**: inspect conversations, inbox tickets, live chats, user profiles, dashboards, and analytics.
6. **Improve**: use traces, failed checks, unresolved topics, fallback events, API errors, and conversation quality metrics to update agents and workflows.

That lifecycle is exactly what our local QA tool should mirror, even if we stay lightweight.

## Nexus Platform

### What Nexus Seems To Be

Nexus is the AI-agent-forward control plane. It feels designed around a modern "agent plus tools plus evaluation" mental model:

- Agents are goal-oriented workers with prompts, categories, status, and routing triggers.
- Tools/workflows provide executable capability.
- Evaluators and rules define success/failure criteria.
- Testing Lab and Action Center create a QA loop around agent behavior.
- Copilot/Nexus chat sits alongside the product and can reason over traces and platform state.

### Nexus Main Navigation

The inspected Nexus bot was:

- Bot ID: `x1779341669482`
- Open workflow: `Order Lookup`
- URL family: `https://nexus.yellow.ai/bot/x1779341669482/...`

Observed module groups:

- **AI Agents**
  - Agents
  - Configuration
  - Widgets
  - Tools
  - Voice
- **Automation**
  - Flows
  - Workflows
  - Functions
  - API
  - Scheduler
- **AI Trust Center**
  - Overview
  - Testing lab
  - Evaluators & rules
  - Action center

Top-level areas also included overview, knowledge base/Atlas, fabric, growth, inbox, engage, app store, and settings.

### Nexus Overview

The overview page reads like an onboarding and operating dashboard. It showed:

- Setup progress:
  - Set up AI Agents
  - Add Knowledge
  - Create Agentic Workflows
  - Setup Business Objects
- Usage trends for the last 30 days:
  - Users
  - Conversations
  - Messages
- Connected channels:
  - WhatsApp
  - Voice
  - SMS
  - Microsoft Teams
  - Slack
  - Email
- Quick links:
  - Studio for automation
  - Inbox for agents
  - Knowledge base
  - Engage

Product interpretation: Nexus wants the builder to think in terms of production readiness. The platform treats channels, knowledge, workflows, business objects, and agents as one deployment surface rather than separate tools.

### Agents

The Nexus Agents page showed a V3 agent list with:

- `Order Assistant`
  - Category: Customer Support
  - Trigger: order tracking, returns/refunds, shipping, payments, store policies
  - Status: Draft
- `ShopEase`
  - Category: shopping/ecommerce assistance
  - Status: Live

The page exposes filters such as status, category, updated by, and last updated. It also exposes `Publish` and `New agent`, which are mutation controls and were not touched.

Engineering interpretation:

- Agents are routable entities with lifecycle state.
- Draft vs Live matters for runtime behavior.
- The agent trigger text is a critical selection surface; weak trigger descriptions can cause wrong routing.
- QA should treat each agent as a separate contract with expected intents, allowed topics, escalation rules, and tool dependencies.

### Order Lookup Workflow

The original Nexus tab was open on:

`/studio/build/flows/order-lookup_vyszir`

Observed workflow elements:

- Start node
- API node: `GetOrderDetails`
- Output node: `Return variable: {{orderResponse}}`
- Failed output branch
- Success and Failure connectors
- Editor, Execute, Logs controls
- Node search

The visible trace/debug history strongly suggests the current workflow problem domain:

- The agent sometimes chooses KB instead of the Order Lookup tool for order tracking.
- The Order Lookup tool was invoked with empty args `{}` in at least one trace.
- The Function/API layer failed when input data was missing or malformed.
- The workflow produced no consumable Skill Output in some traces.
- There was repeated discussion of mapping `orderId` correctly and returning a stable `result`.

Product interpretation:

- Yellow.ai separates "agent selected the right skill" from "skill executed correctly" from "skill returned consumable output".
- A successful test therefore needs to validate all three layers:
  - routing decision,
  - tool/workflow invocation arguments,
  - final user-facing response.

Engineering interpretation:

- A workflow can be graphically valid but functionally broken if its input mapping or output mapping is wrong.
- Tool contracts should be explicit:
  - required input keys,
  - fallback behavior when keys are missing,
  - output schema,
  - success/error branches,
  - user-safe error response.
- Our QA reports should include "tool invocation contract" failures, not only conversation score failures.

### Workflows, Functions, API, And Scheduler

Nexus exposes build primitives separately:

- **Flows**: conversation/control-flow logic.
- **Workflows**: skill-like executable process graphs.
- **Functions**: code execution units.
- **API**: external integration configuration.
- **Scheduler**: event or scheduled automation hub.

In the Order Lookup case, the platform appears to use these layers together:

1. Agent detects tracking intent.
2. Agent invokes Order Lookup tool/workflow.
3. Workflow passes order ID into API/function step.
4. Function/API fetches status.
5. Output node returns a variable/result.
6. Agent converts result into a response.

QA implication: our tool should represent this as a dependency graph. A failed response might be caused by any layer, so test results should classify failures into routing, parameter extraction, integration/API, output mapping, prompt formatting, or fallback logic.

### Testing Lab

Nexus Testing Lab showed:

- Run history
- New test case
- Filters
- Add to dataset
- Categorize
- Delete
- Run selected tests

There were no selected tests during inspection. I did not run anything.

Product interpretation:

- Yellow.ai is moving toward in-product regression datasets.
- Tests are likely first-class objects that can be categorized and re-run.
- The platform is not just validating static flows; it is validating AI-agent behavior against examples.

QA implication:

- Our app should eventually export generated suites into a format that can map to Yellow.ai test cases.
- Our "suite" object should include category, channel, persona, expected outcome, metric bundle, and target agent/tool.

### Evaluators And Rules

Nexus Evaluators & Rules showed:

- 10/10 evaluators enabled.
- 7 quality checks.
- 3 safety checks.
- Average threshold around 57.

Quality evaluators observed:

- Empathy
- Accuracy / Quality Score
- Response Variability
- Strictness
- Hallucination
- Clear Communication
- Follow-up Handling

Safety evaluators observed:

- Language Filter for toxicity and bias
- PII Detector
- Jailbreak Evaluator

Product interpretation:

- Yellow.ai evaluator design combines subjective conversational quality with safety and policy checks.
- Each evaluator has a threshold, category, output type, and "what this measures" description.
- Evaluators are platform governance primitives, not just reporting widgets.

QA implication:

- Our local evaluator metrics should keep matching these categories:
  - empathy,
  - instruction following/strictness,
  - accuracy,
  - hallucination,
  - context/follow-up handling,
  - PII/safety,
  - jailbreak resistance.
- For voice, we should add operational metrics Yellow.ai evaluators may not fully cover:
  - call pickup,
  - no-input handling,
  - STT/TTS latency,
  - talk ratio,
  - early termination,
  - interruption handling.

### Action Center

Nexus Action Center showed:

- Status: nominal.
- Open issues: 0.
- Checks passed: 24/24.
- Last run: 2 min ago.
- Export and Retry all failing controls.

Product interpretation:

- The Action Center is a triage queue for failed tests/evaluator checks.
- It converts QA findings into operational work.
- It is the bridge between "testing found something" and "builder must fix something".

QA implication:

- Our report recommendations should not only say "score is low"; they should produce action-center-like tasks:
  - affected flow,
  - suspected root cause,
  - failing metric,
  - suggested Yellow.ai area to inspect,
  - whether it is prompt, routing, API, workflow, KB, or voice infra.

### Nexus Copilot / Trace Debugging

The Nexus page included a long Copilot-style debug conversation. It referenced trace analysis, message IDs, tool calls, args, routing, and workflow output errors.

Important observed debugging pattern:

1. User reports symptom: order ID entered but details not shown.
2. Trace shows whether the agent routed correctly.
3. Tool call args are inspected.
4. Workflow/function errors are inspected.
5. Output mapping is checked.
6. Fix suggestions are produced.

This is a useful blueprint for our future report detail view. A high-quality QA tool should explain failures like:

- "The bot failed to answer" is too vague.
- "The agent selected KB instead of Order Lookup after receiving order ID 12345" is actionable.
- "Order Lookup was invoked with empty args and produced no consumable output" is even better.

## Cloud Platform

### What Cloud Seems To Be

Cloud is the broader enterprise operations console. It is less narrowly focused on agentic workflow authoring and more focused on the total bot estate:

- bot overview,
- agents and tools,
- test suites,
- knowledge/data,
- analytics,
- campaigns,
- inbox operations,
- settings,
- playground,
- extensions.

The inspected Cloud bot was:

- Bot ID: `x1770124708141`
- Bot name: `JFL Voice X`
- Environment: Staging
- Channel emphasis: IVR / voice
- URL family: `https://cloud.yellow.ai/bot/x1770124708141/...`

### Cloud Main Navigation

Observed navigation:

- **Home**
- **Build**
  - Agents
  - Tools
  - Test suites
- **Data & Knowledge**
  - Knowledge base
  - User 360
  - Database
- **Analytics**
  - Overview
  - Conversations
  - Dashboards
  - Data explorer
- **Engage**
  - Campaigns
  - Templates
- **Inbox**
  - Dashboard
  - Chats
  - Tickets
  - Contacts
- Playground
- Extensions
- Settings

Product interpretation:

- Cloud is organized around operating the bot in production, not only building it.
- The Cloud module map covers the complete post-deployment lifecycle: knowledge, data, analytics, inbox, campaigns, and settings.
- The presence of "Try Nexus" and "Discover the full power of Nexus" suggests Nexus is the newer companion surface or migration path for AI-agent-first work.

### Cloud Super Agent Model

Local scrape output showed a Super Agent profile for `JFL Voice X`:

- Company: JFL
- Model: `gpt-4_1-2025-04-14`
- Persona: Empathetic and helpful
- Channel: IVR
- Role: Domino's virtual assistant for pre-order and post-order support

The Super Agent profile describes:

- identity,
- company,
- model,
- persona,
- channels,
- role,
- welcome behavior,
- fallback behavior,
- live agent transfer path,
- rules,
- AI Safety & Conduct.

Product interpretation:

- Cloud represents the bot as a Super Agent with specialist agents/tools underneath.
- The Super Agent is the orchestrator responsible for routing, fallback, tone, safety, and top-level behavior.
- Channel-specific constraints matter; for JFL Voice X, IVR/voice is not a secondary detail.

### JFL Voice X Agent Architecture

The existing local spec identifies these core elements:

- Super Agent: Domino's virtual assistant.
- Welcome Journey: `welcome-journey_txpbvr`.
- Fallback Journey: `fallback-journey_pxlrnc`.
- KB Agent: enabled for factual FAQ responses.
- Safety guardrails:
  - user input moderation,
  - bot output moderation,
  - toxicity/bias/sensitive-info controls.

Specialist agents:

- Language Selection Assistant: live.
- Order Status Flow: live.
- Concern Handling Agent: live.
- Delivery Instruction Agent: live.
- Refund Agent: live.
- Post Resolution Agent: live.
- Disconnection Agent: live.
- Cancellation Agent: draft.
- Feedback Agent: draft.

Core skills/workflows:

- Order Status Check: `active-order-check_wjesnh`
- Refund Status Check: `refund-status-check_hllfim`
- Delivery Instruction For Order: `delivery-instruction-for-order_xtqzvd`
- Order Status Check For Concern: `order-status-check-for-concern_xdmsaf`
- Update User Number: `updateusernumber_yhorck`
- Language update: `language-update_aebbqq`

Product interpretation:

- This is a multi-agent voice bot, not a single monolithic flow.
- Each specialist agent has routing triggers, tool dependencies, and channel-specific response rules.
- Draft/live status is important; QA must distinguish what is routable now from what exists but is not published.

### Cloud Conversation / Copilot Page

The open Cloud page showed a Copilot-style conversation about how to test the JFL Voice X voice bot. It produced a detailed agent description and metric model.

Important testing metric groups captured from the page:

- Adoption and volume:
  - total sessions,
  - total users,
  - new vs returning users,
  - sessions by source/channel,
  - peak hour distribution.
- Outcome:
  - AI Agent Resolution Rate,
  - containment,
  - resolved/unresolved/resolution_attempted/user_drop_off,
  - drop-off points,
  - top unresolved topics.
- Conversation quality:
  - sentiment,
  - topic trends,
  - fallback rate,
  - rephrase/repair rate,
  - CSAT and verbatims.
- Voice-specific:
  - call volume,
  - call duration,
  - STT latency,
  - TTS latency,
  - platform latency,
  - total latency,
  - silence/no-input events,
  - unidentified utterances,
  - interruption/barge-in,
  - hangup source.
- Reliability and integrations:
  - bot health,
  - API success/failure,
  - API latency,
  - failure clusters by journey/step.
- Knowledge Base:
  - KB hit rate,
  - articles used,
  - no-answer/low-confidence retrieval.
- LLM and GenAI:
  - LLM calls,
  - tokens,
  - cost,
  - cost per resolved conversation,
  - model performance by topic/agent.
- Compliance and safety:
  - PII leakage,
  - toxicity/unsafe content,
  - escalation correctness.

This metric list aligns strongly with our local app's intended direction.

### Cloud Knowledge And Data Model

Cloud exposes:

- Knowledge base,
- User 360,
- Database.

Product interpretation:

- Knowledge base likely handles articles/docs/RAG content.
- User 360 likely centralizes customer profiles and attributes.
- Database likely exposes structured data tables or business data used by flows/tools.

QA implication:

- A bot answer can fail because of missing knowledge, stale knowledge, bad retrieval, or bad structured data lookup.
- Our QA tool should distinguish:
  - "retrieval failed",
  - "retrieval was irrelevant",
  - "data lookup failed",
  - "agent ignored retrieved data",
  - "agent hallucinated without data".

### Cloud Analytics And Operations Model

Cloud exposes analytics modules:

- Overview,
- Conversations,
- Dashboards,
- Data explorer.

It also exposes inbox operations:

- Dashboard,
- Chats,
- Tickets,
- Contacts.

Product interpretation:

- Cloud is where production bot performance is measured and operationally handled.
- Analytics likely answers "what is happening at scale?"
- Conversations answers "what happened in this user session?"
- Dashboards answer "what should leaders monitor?"
- Data explorer answers "how can analysts slice raw event data?"
- Inbox answers "what needs a human agent?"

QA implication:

- Our local app should eventually ingest or link to production conversations.
- Regression tests should be generated from real failure clusters:
  - unresolved topics,
  - high fallback journeys,
  - long-latency APIs,
  - high handoff intents,
  - negative sentiment examples,
  - missed utterances in voice.

## How The Two Surfaces Fit Together

### Nexus vs Cloud

| Area | Nexus | Cloud |
|---|---|---|
| Primary job | Build/test AI agents and workflows | Operate the full bot estate |
| Strongest surface | Agentic workflows, evaluators, action center | Analytics, KB/data, inbox, campaigns |
| Builder model | Agents + tools + workflows + evaluators | Super Agent + agents + tools + ops modules |
| QA model | Testing Lab, evaluators, action center | Test suites, analytics, conversation review |
| Best for debugging | Trace/tool/workflow failure analysis | Conversation analytics and operational context |
| Best for voice ops | Voice module and evaluators | IVR bot profile, call metrics, inbox/escalation |

### End-To-End Runtime Mental Model

For a voice bot like JFL Voice X:

1. Caller enters through IVR/voice channel.
2. Super Agent or orchestrator handles initial routing.
3. Language agent may set English/Hindi.
4. Specialist agent handles the caller's intent.
5. Tool/workflow/API may be invoked.
6. KB may answer informational queries.
7. Response is spoken back through voice stack.
8. If the bot fails, escalates, or caller asks for human, inbox/ticketing takes over.
9. Analytics and conversation traces record performance.
10. Test suites/evaluators/action center convert issues into improvements.

## What This Means For Our QA Tool

Our local voice-agent QA platform should model Yellow.ai's lifecycle explicitly.

### Data We Should Capture Per Bot

Bot-level:

- bot name,
- platform surface,
- bot ID,
- environment,
- channel,
- phone number,
- provider,
- language policy,
- timezone,
- connected channels.

Agent-level:

- agent name,
- status: live/draft,
- trigger,
- goal,
- persona,
- response constraints,
- safety constraints,
- escalation behavior,
- specialist domain.

Tool/workflow-level:

- tool name,
- workflow ID,
- required inputs,
- output schema,
- API dependencies,
- success branch,
- failure branch,
- fallback user response.

Knowledge-level:

- KB name,
- scope,
- retrieval behavior,
- no-answer behavior,
- language rules,
- citation/link policy.

### Test Suite Generation Should Follow This Structure

For Yellow.ai-style bots, generated tests should cover:

- Routing:
  - correct specialist selected,
  - no wrong KB/tool selection,
  - draft agents not assumed routable.
- Slot/input capture:
  - order ID,
  - phone number,
  - language,
  - issue category,
  - refund/order fields.
- Tool invocation:
  - correct tool selected,
  - correct args passed,
  - missing args handled safely.
- Workflow output:
  - result produced,
  - error output produced,
  - agent consumes output properly.
- KB:
  - relevant answer,
  - no hallucination,
  - no answer handled correctly.
- Voice:
  - pickup,
  - latency,
  - no-input,
  - barge-in,
  - interruption,
  - talk ratio,
  - early termination,
  - hangup source.
- Safety:
  - PII,
  - prompt injection,
  - toxicity/bias,
  - out-of-scope refusal,
  - escalation correctness.

### Report Recommendations Should Be Yellow.ai-Aware

Recommendations should point to likely Yellow.ai modules:

- Wrong intent/routing: Agents, trigger, Super Agent routing, specialist descriptions.
- Tool not called: agent goal, tool description, tool selection rules.
- Empty args: workflow input mapping, memory variable, slot capture.
- API failure: API node, function code, external endpoint, timeout/retry.
- No output: workflow output node, skill output schema, result mapping.
- Generic answer: KB priority, tool-vs-KB routing, prompt instruction.
- Long voice answer: agent response constraint, voice prompt copy, TTS pacing.
- Repeated fallback: training examples, clarification copy, language/STT handling.
- Bad handoff: live agent transfer flow, inbox/ticket mapping.
- Safety failure: AI Safety & Conduct, evaluators, guardrails.

## Suggested Next Product Steps For Our App

1. Add a **Yellow.ai platform profile** section to runtime settings:
   - platform: Nexus or Cloud,
   - bot ID,
   - environment,
   - agent names,
   - relevant workflow/tool IDs,
   - KB names,
   - phone/channel targets.

2. Add a **module-aware report taxonomy**:
   - Agent routing,
   - Tool invocation,
   - Workflow/API,
   - Knowledge retrieval,
   - Voice infrastructure,
   - Safety/compliance,
   - Analytics/ops.

3. Add a **trace-inspired failure explanation**:
   - user utterance,
   - expected route,
   - observed route,
   - expected tool,
   - observed tool,
   - args passed,
   - output returned,
   - final response,
   - recommended Yellow.ai module to inspect.

4. Add **voice-first Cekura-style test templates** for:
   - language selection,
   - order status,
   - refund status,
   - delivery instruction,
   - concern handling,
   - disconnection,
   - fallback,
   - escalation.

5. Add **import/export hooks**:
   - import bot profile/spec Markdown,
   - export test suites as JSON,
   - later export to Yellow.ai Testing Lab format if an API or upload format is available.

## Practical Takeaway

Nexus teaches us how the builder thinks: agents, tools, workflows, evaluators, and action triage.

Cloud teaches us how the operator thinks: bot profile, knowledge, analytics, conversations, inbox, campaigns, and settings.

Our QA platform should sit between those two views. It should generate tests like a QA engineer, explain failures like a workflow engineer, and summarize risk like a product owner.
