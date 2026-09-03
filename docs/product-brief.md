# Product Brief

## Working title

Notes, Lists and Reminders

## Status

Discovery / pre-MVP.

## Product purpose

A private family capture system that lets Niki and Ben quickly create, organise, share, and receive notes, list items, and reminders from an Android phone or computer.

The primary value is reducing the effort between remembering something and capturing it:

> Capture something before it disappears, in natural language, and let the app work out where it belongs.

## Product direction

- The PWA remains the source of truth and the management surface.
- Gemini on Android supplies the voice interaction and transcript.
- Gemini sends the raw user message to a narrow integration endpoint when a supported direct integration is available.
- A Python LangGraph workflow owns domain interpretation: what operation is requested, whether it is a note, list change, or reminder, and which validated fields are required.
- Deterministic application services—not the language model—perform authorised database writes.
- Ambiguous or unsafe requests are retained as captures for review rather than guessed.

## Problem

Thoughts and small commitments often occur when opening and navigating a full application is inconvenient. Existing tools split notes, lists, reminders, sharing, and natural-language capture across separate workflows.

Niki and Ben need one private system where they can:

- say or type a natural-language request;
- have the app determine the intended operation and structure;
- create and review content from a phone or laptop;
- maintain shared lists;
- assign reminder notifications to Niki, Ben, or both;
- trust that reminders survive restarts and are delivered idempotently;
- keep the main application inside their home Tailscale network.

## Users

### Niki

- Primary product owner and initial power user.
- Uses an Android phone and laptop.
- Uses Gemini on her phone for voice interaction and transcription.
- Wants low-friction capture and a richer desktop review experience.
- Needs personal and shared notes, lists, and reminders.

### Ben

- Household collaborator.
- Uses an Android phone and laptop.
- Needs to receive shared reminders and update shared lists.
- Does not need Gemini integration to use the application.

## Product principles

1. **Capture first, organise second.** Preserve the original message before interpretation.
2. **One natural-language entry point.** The user should not have to choose Note, List, or Reminder before speaking.
3. **One domain brain.** PWA text, Gemini, and future adapters all call the same LangGraph command workflow.
4. **AI proposes; application code validates and writes.** The model never receives unrestricted database or SQL access.
5. **Confirm meaningful ambiguity.** Do not silently choose a date, recipient, list, or destructive operation.
6. **Private by default.** Notes and new lists remain personal unless explicitly shared.
7. **Reliable reminders over clever reminders.** Durable scheduling and visible delivery state matter more than sophisticated language behaviour.
8. **Useful without Gemini.** Typed PWA capture and manual CRUD remain complete, reliable product paths.
9. **Keep integrations replaceable.** Gemini is an input adapter, not the owner of domain rules or stored data.

## Core user journeys

### 1. Natural-language capture through Gemini

Target experience, subject to the Gemini integration feasibility gate:

1. Niki opens or invokes Gemini on Android and speaks naturally.
2. Gemini transcribes the request.
3. Gemini invokes the app's connected tool with the raw message.
4. The backend authenticates the integration identity and stores an immutable capture record.
5. The LangGraph workflow loads Niki's timezone, household members, and available lists.
6. It produces and validates a structured command plan.
7. The application either executes the plan or puts it in **Needs review**.
8. Gemini receives a concise receipt such as:
   - “Added milk and bananas to Shopping.”
   - “Reminder created for Ben tomorrow at 7:00 pm.”
   - “Saved as a note.”
   - “I need you to choose which birthday list you meant.”

The raw transcript—not a Gemini-selected note/list/reminder schema—is passed into the domain workflow. This keeps classification and structure in one testable place.

### 2. Natural-language capture in the PWA

1. Niki or Ben opens the PWA.
2. They enter a natural-language request.
3. The PWA calls the same command endpoint used by external adapters.
4. The agent proposes and validates an operation.
5. The result is executed or shown for correction.

This path is implemented before relying on Gemini and becomes the agent's development and evaluation surface.

### 3. Manual PWA use

Users can always bypass the agent and directly:

- create or edit a note;
- create, rename, share, or archive a list;
- add, edit, reorder, check, or uncheck list items;
- create, reschedule, snooze, complete, or cancel a reminder.

Manual operations use the same domain services and authorization rules as agent tools.

### 4. Create and deliver a reminder

1. A user enters or speaks a request.
2. The agent extracts title, date/time, timezone, recipients, and optional details.
3. Deterministic validation rejects missing or contradictory required fields.
4. If confidence and policy allow, the reminder is stored durably; otherwise it enters review.
5. At the due time, each selected recipient receives a push notification.
6. Delivery attempts are recorded and idempotent.

### 5. Maintain a shared list

1. Niki or Ben opens a shared list such as **Shopping**, or asks the agent to change it.
2. Either user adds, edits, checks, or unchecks items.
3. Updates synchronise across devices.
4. The interface shows who made the change where useful.

### 6. Review from a laptop

The desktop view supports:

- recent capture inbox;
- items needing review;
- agent execution receipts and errors;
- notes;
- lists and list items;
- upcoming reminders;
- shared-with-me content;
- completed and archived items;
- search and filtering;
- editing dates, recurrence, and recipients.

## Product model

### Capture

The durable record of the user's original input and its processing lifecycle:

- source: PWA, Gemini MCP, share target, or future adapter;
- raw text;
- authenticated user;
- source request/idempotency key;
- received-at timestamp and timezone context;
- status: received, interpreting, needs_review, executing, completed, failed;
- proposed command plan and validation findings;
- resulting resource identifiers;
- safe error summary.

A capture remains available if interpretation or execution fails.

### Command plan

A versioned, validated representation of intended actions. The first supported action types are:

- `create_note`;
- `create_list`;
- `add_list_items`;
- `create_reminder`.

A single utterance may produce several actions, but they execute as one explicit plan with clear partial-failure semantics. Edit, completion, deletion, and bulk operations are added only after the create flows are reliable.

### Note

Unstructured text with an owner, creation timestamp, update timestamp, and optional sharing. Default: private.

### List and list item

A named collection of checkable items with creation and update timestamps. Lists may be private or shared. New lists default to private unless the request explicitly says otherwise. Each list item also records when it was created.

### Reminder

A time-based commitment containing:

- title and optional detail;
- due date/time and timezone;
- optional recurrence, deferred initially;
- recipients: creator, Niki, Ben, or both as authorised;
- whether it is urgent;
- status;
- creation and update timestamps;
- notification delivery history.

### Agent execution

An auditable record linking a capture to:

- graph and prompt/schema version;
- model/provider identifier;
- structured plan;
- validation result;
- tool calls and outcomes;
- review decision, if any;
- latency and token metadata without storing hidden reasoning.

## MVP scope

### Included

- Two application users: Niki and Ben.
- Responsive Android/desktop PWA.
- Installable PWA manifest and service worker.
- Notes with private-by-default sharing.
- Private and shared lists with checkable items.
- One-time reminders and household recipients.
- Web Push subscriptions and durable reminder delivery.
- Typed natural-language capture in the PWA.
- Python LangGraph command workflow with structured output.
- Versioned command schemas and deterministic validation.
- A capture inbox and **Needs review** flow.
- Idempotent domain tools for creating notes, lists, list items, and reminders.
- A narrow external integration boundary suitable for remote MCP.
- Gemini custom Connected App feasibility spike on Niki's real account and phone.
- Gemini MCP integration only if the feasibility gate passes.
- PWA share-target fallback if direct Gemini invocation is unavailable but Gemini can share text into the installed PWA.
- Tailscale-only main PWA and API.
- PostgreSQL on `fedora-1` as the application database and reminder scheduling source of truth.
- Basic backups, health checks, structured logs, and agent evaluation fixtures.

### Explicitly deferred

- A full native Android application.
- Android AppFunctions production integration until Gemini access is generally available for this app/device/account.
- Browser audio recording and server-side speech-to-text unless the Gemini path proves inadequate.
- Automatic execution of destructive commands.
- Complex recurrence and location-triggered reminders.
- More than one household.
- Collaborative rich-text editing.
- Email, SMS, or calendar integration.
- A general-purpose autonomous personal assistant.

## Functional requirements

### Capture and agent

- Accept raw natural-language text from the authenticated PWA.
- Accept raw natural-language text from a separately authenticated external adapter.
- Persist the raw capture before invoking a model.
- Resolve relative dates using the authenticated user's timezone and an explicit reference timestamp.
- Load only authorised household context.
- Produce a versioned structured command plan.
- Validate every plan deterministically before execution.
- Never expose SQL or unrestricted persistence access to the agent.
- Use idempotency keys to make retries safe.
- Retain ambiguous, invalid, or failed requests in **Needs review**.
- Return a concise, factual receipt based on committed database state.
- Support a dry-run/evaluation mode that cannot write production data.

### Notes

- Create, view, edit, archive, and search notes.
- Share or unshare a note with another user.
- Enforce private-by-default access.

### Lists

- Create, rename, archive, and share lists.
- Add, edit, reorder, check, uncheck, and delete list items.
- Resolve list names conservatively; never silently choose between plausible matches.
- Synchronise changes across devices.

### Reminders

- Create, edit, complete, cancel, snooze, and reschedule a reminder.
- Select one or both household recipients.
- Store dates in UTC while preserving intended timezone.
- Allow a reminder to be marked urgent.
- Recover scheduling state after process or server restart.
- Avoid duplicate delivery through idempotent delivery records.
- Expose delivery status to the creator.

### Notifications

- Register and revoke Web Push subscriptions per browser/device.
- Send due-reminder notifications to selected recipients.
- Open the correct PWA route when a notification is tapped.
- Use minimal notification content when the device is locked.

### Gemini integration

- Expose only narrowly scoped integration tools; the first tool accepts one raw capture message.
- Authenticate and map every integration request to an application user.
- Keep the main application API inaccessible from the public internet.
- Support token revocation and per-user rate limits.
- Return no household content beyond the minimum receipt required for the current request.
- Treat Gemini-supplied text as untrusted input.
- Preserve Google-side write confirmation where the Connected App flow requires it.

## Non-functional requirements

### Privacy and security

- The PWA and general API remain tailnet-only.
- Any remote MCP ingress is deployed as a separate public listener and process.
- Public integration tools cannot read or enumerate household content.
- No application secrets or private infrastructure identifiers are committed.
- OAuth credentials and tokens are revocable and never logged.
- Authorization is checked inside domain services, regardless of caller.
- Model prompts contain only the minimum household context needed for the command.
- Raw captures and agent traces have explicit retention rules.

### Reliability

- Restarting processes does not lose captures, notes, lists, reminders, or pending schedules.
- Capture execution and notification delivery are idempotent.
- A model outage leaves the capture recoverable and retryable.
- Failed notification deliveries use bounded retries.
- Database backups are automated and restorable.

### Agent quality

- A versioned evaluation set covers representative notes, lists, reminders, compound requests, ambiguous dates, recipient ambiguity, and adversarial input.
- Schema-valid output is necessary but not sufficient; tests also assert the intended resource changes.
- Prompt/schema/model changes run against the evaluation set before deployment.
- Logs record decisions and tool outcomes, not hidden chain-of-thought.

### Performance

Initial targets for the two-user deployment:

- Normal CRUD responses under 500 ms on the home network.
- Agent capture acknowledgement immediately after durable persistence.
- Typical one-action interpretation and execution under 8 seconds.
- Due reminders offered to the push provider within 60 seconds of their scheduled time.

## Success criteria

The first complete release is successful when:

1. Niki can type a natural-language request in the PWA and the correct note, list item, or reminder is created.
2. Niki can speak through Gemini and deliver the resulting raw message to the same workflow, if the direct integration feasibility gate passes.
3. If that gate does not pass, the product remains complete and a documented share-to-PWA path preserves most of the voice-capture value.
4. Niki can assign a reminder to Ben and his Android device receives it.
5. Niki and Ben can maintain a shared shopping list from phone and laptop.
6. Ambiguous requests are held for review rather than silently misfiled.
7. Retrying the same integration request does not create duplicate resources.
8. A server restart does not lose or duplicate pending reminders.
9. The general application remains unavailable outside the tailnet.
10. The public integration endpoint cannot read or enumerate household content.

## Delivery plan

### Phase 1: Useful PWA without AI integration

Build the useful product before any AI or external integration:

- Niki and Ben accounts;
- manual notes;
- private and shared lists;
- list items;
- one-time reminders;
- responsive phone/desktop UI;
- Tailscale Serve deployment;
- database migrations, backups, and basic health checks.

**Exit criterion:** both users can reliably manage notes, lists, and reminders from phone and laptop without Gemini.

### Phase 2: Reliable reminders and sharing

- Web Push subscription management;
- reminder worker;
- recipients;
- retries and delivery history;
- notification deep links;
- sharing authorization tests;
- restart and duplicate-delivery tests.

**Exit criterion:** a reminder to either or both users is durable, observable, and idempotent across restarts.

### Phase 3: LangGraph command workflow

- Add durable captures and agent execution records.
- Define versioned Pydantic command schemas.
- Implement agent-safe domain tools over application services.
- Build the graph: persist → load context → interpret → validate → policy gate → execute/review → receipt.
- Route PWA natural-language text through the graph.
- Add the review inbox and correction flow.
- Build and automate a representative evaluation suite.

**Exit criterion:** PWA text requests create the right resources or enter review, with no direct model access to persistence.

### Phase 4: Gemini connection feasibility gate

Time-box a real-device spike after the command workflow exists:

- verify Niki's Gemini account, country, language, mobile app, and Spark/Connected App availability;
- expose a disposable authenticated MCP tool that echoes a non-sensitive test value;
- connect it from Gemini and invoke it by voice on Android;
- measure required taps, write confirmation behaviour, latency, retries, and idempotency metadata;
- verify whether the flow works in normal Gemini chat, Gemini Live, or only Gemini Spark;
- delete the disposable endpoint after the decision.

**Go:** proceed only if voice invocation is available to Niki, the flow is acceptably short, authentication is supportable, and raw message text reaches the backend reliably.

**No-go:** keep the PWA complete, implement the installed-PWA share target if viable, and monitor custom Connected Apps/AppFunctions availability. Do not build a permanent public MCP service around an unavailable client feature.

### Phase 5A: Production Gemini MCP adapter — only after a go decision

- Separate public integration process/listener.
- Standards-compliant remote MCP transport.
- OAuth account linking, token rotation, and revocation.
- One narrow `capture_message` tool accepting raw text and an idempotency key where the client permits.
- Mapping from OAuth identity to application user.
- Rate limits, minimal responses, audit logging, and replay tests.
- End-to-end Android voice tests with notes, lists, reminders, ambiguity, and retries.

**Exit criterion:** Niki can speak a request to Gemini, approve the connected-app write if required, and receive a receipt matching committed app state.

### Phase 5B: Share-to-PWA fallback — if direct MCP is unavailable

- Register the installed PWA as a text share target where supported.
- Accept shared transcript text into a prefilled capture review screen.
- Submit it to the same LangGraph endpoint.
- Document the shortest reliable Gemini-to-share flow on Niki's phone.

This is a fallback, not a second domain implementation.

### Phase 6: Refinement

Use actual capture and review data to prioritise:

- safe agent-supported edits and completion actions;
- recurrence;
- improved list/entity resolution;
- richer offline behaviour;
- search improvements;
- lower-friction confirmations;
- native Android AppFunctions only when generally available and clearly better than remote MCP/share flow;
- future capture adapters only if they add enough value.

## Open product questions

- What exact spoken prefix or app name should reliably route a request to our Connected App?
- Is Gemini Spark available on Niki's personal account in Australia, and does its mobile flow meet the capture-speed goal?
- Is one Google-side confirmation tap acceptable for writes?
- Should unambiguous note/list/reminder creation auto-execute after that confirmation, or should reminders always receive an in-app review?
- What should the default reminder recipient be: creator only or both users?
- Should a named **Shopping** list be shared by default while other lists remain private?
- How long should raw captures and agent execution payloads be retained?
- Which LLM provider/model should the LangGraph workflow use initially, and what cost/privacy constraints should govern that choice?
- What should the product and repository be named?
