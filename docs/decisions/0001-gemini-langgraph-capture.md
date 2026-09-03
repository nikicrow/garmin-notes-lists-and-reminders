# ADR 0001: Use Gemini as a voice adapter and LangGraph as the domain command workflow

- **Status:** Proposed, with Gemini transport feasibility gate
- **Date:** 2026-09-03
- **Decision owners:** Niki and Bugsy

## Context

The original architecture used a Garmin Connect IQ app to trigger an Android notification, which opened a PWA audio recorder. The server then transcribed the recording and interpreted it as a note, list item, or reminder.

Niki already has Gemini on Android and wants Gemini to handle voice transcription, then send the message directly to a Python LangGraph agent. The LangGraph workflow should decide what the application must do and what structure is required.

This removes a long watch-trigger chain and makes the product's intelligent capture path useful without Garmin. It also creates a cleaner separation:

- Gemini: microphone experience and speech-to-text;
- LangGraph: domain interpretation and orchestration;
- application services: authorization, validation, transactions, and writes;
- PWA: source-of-truth UI, review, and manual operation.

## Current platform constraint

Gemini supports Connected Apps, and some supported apps can be used from Gemini Live, but availability varies by account, app, device, country, and language.[1]

Google's documented custom MCP connection currently works only inside Gemini Spark. It requires eligible Spark access, English, a personal Google Account, and—at present—an adult user in the US. Custom apps are linked by MCP URL from the Gemini web app and can then be used in Spark on mobile or web.[2]

That means a remote MCP server is the right architectural seam, but it is not yet safe to assume Niki can invoke it directly from her normal Gemini Android/Live experience in Australia.

Android AppFunctions are another future path: they let native Android apps expose MCP-like tools to agents such as Gemini. However, Gemini integration is currently a private preview and AppFunctions require Android 16 or later.[3] They also require a native Android component, while Phase 1 is deliberately a PWA.

## Decision

1. **Keep Phase 1 unchanged:** build a useful PWA with accounts, notes, lists, reminders, and private Tailscale deployment.
2. **Remove Garmin from the active MVP roadmap.** Garmin becomes a possible future capture adapter, not an architectural dependency.
3. **Build one channel-neutral Python LangGraph workflow** that accepts a persisted raw message and produces a versioned structured command plan.
4. **Let the model propose; let deterministic code decide and write.** The graph may use an LLM for interpretation, but only typed domain tools can mutate data.
5. **Use PWA typed capture first** to build, test, and evaluate the command workflow without waiting for Gemini platform eligibility.
6. **Treat Gemini remote MCP as feasibility-gated.** Test Niki's actual account and Android flow after the command agent exists.
7. **If the gate passes, expose one narrow public MCP tool:** `capture_message(raw_text)`. Do not expose separate note/list/reminder tools because classification belongs in LangGraph.
8. **If the gate fails, use a PWA text-share target if real-device testing proves Gemini can share usable text.** Otherwise retain PWA typed capture and wait for Connected Apps/AppFunctions support.
9. **Do not reintroduce server-side speech-to-text unless actual use shows Gemini is inadequate.**

## Why LangGraph

LangGraph explicitly supports workflows that mix deterministic nodes with model-driven nodes, persistence, and human review boundaries.[4] Those properties fit a capture workflow where interpretation is probabilistic but authorization, date validation, idempotency, and database writes must be predictable. LangChain's agent layer can return schema-validated structured output, which gives the graph a typed interpretation boundary before application validation.[5]

The first graph is intentionally constrained:

```text
persist capture
  → load authorised context
  → interpret to versioned schema
  → resolve and validate deterministically
  → policy gate
  → execute typed domain tools OR needs review
  → read committed state
  → return factual receipt
```

## Why one raw-message MCP tool

The desired responsibility boundary is:

```text
Gemini transcript: "Add milk and nappies to shopping"
                         │
                         ▼
MCP capture_message(raw_text=<unchanged transcript>)
                         │
                         ▼
LangGraph decides: add_list_items(list=Shopping, items=[...])
```

If MCP instead exposes `create_note`, `add_list_item`, and `create_reminder`, Gemini must select the operation and construct domain fields. That duplicates the LangGraph role, makes behaviour channel-specific, and weakens our ability to evaluate one domain interpreter.

## Safety policy

Initial automatic execution is limited to creation operations with complete, unambiguous fields:

- private note;
- new explicitly named list;
- items added to one exact authorised list;
- reminder with a resolvable date/time and valid recipient.

Ambiguous dates, multiple matching lists, unknown recipients, edits, completions, deletions, and unsupported requests enter **Needs review**. The model never receives unrestricted SQL, filesystem, shell, web, or arbitrary HTTP tools.

Gemini's current custom Connected App flow also asks for manual confirmation before writes.[2] That confirmation is useful but does not replace backend authorization and validation.

## Consequences

### Positive

- Removes Monkey C, watch pairing, watch ingress, capture-notification, audio upload, codec, and transcription complexity from the MVP.
- The intelligent workflow can be built and evaluated entirely through the PWA.
- All future channels reuse the same interpretation and domain tools.
- Raw captures survive model failures and ambiguity.
- The language model is replaceable without redesigning the product.
- A public endpoint is deployed only if there is a proven client that can use it.

### Negative

- Direct Gemini integration may not currently be available to Niki.
- Gemini Spark may add eligibility constraints and a write-confirmation tap.
- A remote MCP adapter requires a deliberately public OAuth/MCP surface even though the main app remains tailnet-only.
- Voice transcript data is processed by Google before reaching the application.
- The LangGraph workflow adds model cost, latency, evaluation work, and operational failure modes.
- A share-target fallback is less direct and must be tested against Gemini's actual sharing behaviour.

### Neutral / follow-up

- The repository name remains Garmin-oriented until a separate rename decision.
- Ben can use all PWA features without Gemini.
- Native Android AppFunctions remain an option after platform availability improves, but they are not required to validate the product.

## Feasibility gate

After Phase 3, run a disposable, non-sensitive spike on Niki's real account and phone.

### Must prove

- custom Connected App/Spark is visible and eligible;
- a remote MCP URL can be connected with supportable authentication;
- spoken input on Android invokes the custom tool;
- the backend receives the raw intended message with acceptable fidelity;
- the confirmation interaction is acceptable;
- retries can be made idempotent;
- round-trip latency is acceptable;
- the feature works in an invocation mode Niki will actually use.

### Go decision

Build the production MCP adapter only if every must-prove item passes.

### No-go decision

Do not deploy a permanent public MCP service. Test the installed-PWA share target, keep PWA natural-language capture as the supported path, and revisit Connected Apps/AppFunctions availability later.

## Alternatives considered

### Continue Garmin-first integration

Rejected for the active roadmap. It introduces multiple bespoke components while still requiring the phone to complete capture. It can be reconsidered later if watch initiation remains valuable after the Gemini workflow is in daily use.

### Let Gemini create structured note/list/reminder calls directly

Rejected. It puts domain classification in the external channel and duplicates agent logic. The integration should send raw text to one backend interpreter.

### Build a native Android app now

Deferred. It conflicts with the Phase 1 PWA goal and does not currently guarantee Gemini AppFunctions access because that integration is still private preview.[3]

### Keep browser recording and local Whisper

Deferred as a fallback only. It duplicates a voice/transcription experience Niki already has and adds audio upload, codec, retention, and inference operations.

### Make the whole API public for Gemini

Rejected. Only the narrow MCP/OAuth adapter may be public. The PWA, general CRUD API, search, and household content remain tailnet-only.

## Revisit conditions

Revisit this decision when any of these occur:

- Gemini custom Connected Apps become generally available in Australia and normal Gemini/Live chats;
- AppFunctions become generally available to third-party Android apps and Niki's phone supports the required Android version;
- real usage shows the share-target flow is too slow;
- Gemini transcript quality or privacy is unacceptable;
- watch initiation still solves a meaningful capture problem after the phone workflow is established.

## Sources

[1] https://support.google.com/gemini/answer/13695044?hl=en&co=GENIE.Platform%3DAndroid — Use and manage Connected Apps in Gemini
[2] https://support.google.com/gemini/answer/17209137?hl=en&co=GENIE.Platform%3DDesktop — Connect custom apps for Gemini Spark
[3] https://developer.android.com/ai/appfunctions — Overview of Android AppFunctions
[4] https://docs.langchain.com/oss/python/langgraph/overview — LangGraph overview
[5] https://docs.langchain.com/oss/python/langchain/agents — LangChain agents
