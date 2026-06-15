# Yellow.ai V3 RAG Analyzer Alignment

Source reviewed: `yellow-ai-v3-quick-guide.docx`

## Executive Read

Yellow.ai V3 changes the testing model from explicit V2 journey wiring to LLM-led agent execution. The analyzer should therefore behave less like an intent-flow checklist and more like a product engineer reviewing agent instructions, router descriptions, memory contracts, tool inputs, KB grounding, and migration traps.

The core V3 model is:

1. Context Expert chooses exactly one agent using the agent's `WHEN TO USE THIS` description, recent history, and the latest user message.
2. The selected main agent runs with its instructions, memory, and selected tools/skills/agents.
3. Continuity wins unless the user clearly changes topic.
4. Important data must be remembered explicitly with `{{memory}}` or it can be lost after later turns or summarized history.
5. Tools, agents, and KB references are called with `[tool]`, `[agent]`, or `[kb: topic]`.

## What This Means For Our Analyzer

The analyzer must be Yellow.ai V3-aware. It should not judge the bot only by legacy intent names or V2 flow start triggers. It should inspect documents, generated suites, transcripts, and future Yellow.ai exports through these lenses:

- Agent routing quality: one goal per agent, concise `WHEN TO USE THIS`, keyword coverage, synonyms, exclusions, anti-triggers, and continuity behavior.
- Agent instruction quality: clear procedure, one action per step, branch handling, example responses for tone, explicit close condition, and no hardcoded volatile data.
- Memory quality: important user inputs and tool outputs are remembered as `{{variables}}` when needed later.
- Tool/workflow quality: every flow-as-skill declares inputs, handles no-data/tool failure/timeout, and consumes outputs cleanly.
- RAG/KB quality: KB answers are grounded, unanswerable questions produce safe no-answer behavior, and retrieval failures are classified separately from workflow/API failures.
- Migration quality: V2 patterns that V3 ignores are flagged before they reach production.
- Deployment quality: live vs draft status and safe duplicate-test-promote workflows are checked.

## Analyzer Modules To Build

### 1. V3 Context Expert Routing Analyzer

Purpose: predict and test whether the correct specialist agent is selected.

Checks:

- `WHEN TO USE THIS` exists and is 2-4 focused sentences.
- Description includes customer language and synonyms.
- Description includes exclusions for nearby domains.
- Agent has one primary goal.
- Overlapping agents have clear anti-triggers.
- Tests include ambiguous turns where continuity should keep the current agent.
- Tests include topic-shift turns where routing should switch agents.

Suggested test generation:

- Overlap prompts: "I want a refund but also need delivery status."
- Continuity prompts: answer a question the active agent just asked.
- Topic shift prompts: move clearly from one specialist domain to another.

### 2. V3 Memory And State Analyzer

Purpose: catch values that work for one turn but disappear later.

Checks:

- Customer inputs needed later are stored as `{{variables}}`.
- Tool results needed later are explicitly remembered.
- Agent-switch handoffs pass the needed context.
- Long conversations retest after summary windows.

Suggested tests:

- Capture email/order ID, then ask later whether the bot still uses it.
- Fetch account details, then move through branches before confirming the same account state.
- Switch agents and verify the next agent receives the relevant context.

### 3. Flow-As-Skill Contract Analyzer

Purpose: prevent V3 skill calls from silently receiving undefined values.

Checks:

- Every variable read by a flow-as-skill is declared in skill inputs.
- Bot-scope/session variables are not assumed to auto-inject.
- Missing, malformed, and valid input cases are tested.
- Tool failure and no-data branches exist.
- Tool output is mapped into response or memory.

Migration flags:

- Authorization checks that rely on bot-scope arrays.
- Flow B reading a variable set by Flow A without explicit input or memory.
- Any flow that depends on start trigger variables once attached as a V3 skill.

### 4. V2-To-V3 Migration Analyzer

Purpose: identify platform features that appear configured but do not execute in V3.

High-risk patterns:

- Flow start triggers used for V3 skills.
- `ym.triggerJourney=<slug>` deep links.
- Lifecycle hooks other than `onConversationStart`.
- `staticWorkflow` and `triggerWelcome`.
- NLU training assumed as the primary router.

Expected recommendation:

- Replace deep link and startup routing with `onConversationStart`.
- Store startup context in memory.
- Move route decisions into agent trigger descriptions and explicit skill invocation.

### 5. RAG And Knowledge Base Analyzer

Purpose: make the tool useful for Yellow.ai KB-backed agents, not just workflows.

Checks:

- Knowledge questions map to `[kb: topic]` rather than copied policy text.
- Answers cite or clearly ground to KB material when available.
- No-answer behavior avoids hallucination.
- Low-confidence/ambiguous questions trigger clarification.
- KB failure is classified separately from tool/API failure.
- Stale or conflicting document evidence is visible in the report.

Suggested tests:

- Answerable KB question.
- Unanswerable but tempting question.
- Ambiguous policy question.
- Outdated policy question from an older uploaded document.
- Similar-policy collision where retrieval can pick the wrong source.

### 6. Deployment Safety Analyzer

Purpose: prevent accidental production routing issues.

Checks:

- New or duplicated agents start as draft and are not assumed live.
- Live agent changes follow duplicate -> edit draft -> preview -> promote -> demote original.
- Existing conversations are understood to continue after toggling an agent to draft.
- Large bots warn near many agents, especially around routing ambiguity.

## Required Data Model For Our Tool

The RAG analyzer should store uploaded docs as retrieval sources with metadata:

- Document name, type, uploaded time, version, and owner.
- Yellow.ai platform, bot ID, environment, agent, workflow/tool, and KB target.
- Extracted chunks with headings and source offsets.
- Analyzer tags: routing, memory, workflow, KB, migration, voice, deployment.
- Generated recommendations with approval status.
- Suggested tests tied back to source chunks.

For now, the app stores document previews and plans locally. The next version should add chunk-level retrieval so generated test cases can quote the exact guide/source section used for the recommendation.

## Recommendation For Current Product Direction

Build the analyzer as an approval-gated assistant, not an auto-editor first.

Phase 1:

- Upload docs.
- Extract and chunk text.
- Analyze with Yellow.ai V3 rubric.
- Generate recommendations and test cases.
- Let the user approve local plans only.

Phase 2:

- Add RAG retrieval over uploaded docs.
- Use retrieved source chunks during suite generation and report explanation.
- Add exportable change plans for Yellow.ai operators.

Phase 3:

- Add read-only Yellow.ai inspection.
- Compare platform configuration against analyzer findings.
- Highlight exact agents, tools, workflows, and KBs to update.

Phase 4:

- Add guarded execution after explicit user approval.
- Execute only small scoped changes.
- Keep before/after snapshots and rollback notes.

## Product Principle

The analyzer should be strict about V3 behavior and conservative about execution. It should explain what to change, why it matters in Yellow.ai terms, what test proves it, and what platform object is affected. It should never claim a Yellow.ai change has been made unless a real platform adapter executed it and the user approved that exact action.
