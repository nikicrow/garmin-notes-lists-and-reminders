# Product Brief

## Working title

Garmin Notes, Lists and Reminders

## Status

Discovery / pre-MVP

## Product purpose

A private family capture system that lets Niki and Ben quickly create, organise, share, and receive reminders, notes, and list items from a Garmin watch, Android phone, or computer.

The product is not intended to compete with general-purpose note-taking applications. Its primary value is reducing the effort between remembering something and capturing it:

> Capture something before it disappears, from whichever device is currently easiest.

## Problem

Thoughts and small commitments often occur when opening a phone or laptop is inconvenient. A Garmin watch is immediately available, but it is not a practical place to enter or organise detailed information. Existing tools also split notes, lists, reminders, sharing, and voice capture across separate workflows.

Niki and Ben need one private system where they can:

- initiate a capture from a Garmin watch;
- record or type the content on an Android phone;
- create and review content from a phone or laptop;
- maintain shared lists;
- assign reminder notifications to Niki, Ben, or both;
- trust that reminders survive restarts and are delivered once;
- keep the primary application inside their home Tailscale network.

## Users

### Niki

- Primary product owner and initial power user.
- Uses a Garmin Venu 3-family device, Android phone, and laptop.
- Wants rapid voice capture and a richer desktop review experience.
- Needs personal and shared notes, lists, and reminders.

### Ben

- Household collaborator.
- Uses an Android phone and laptop.
- Needs to receive shared reminders and update shared lists.
- Should not need a Garmin watch to use the application.

## Product principles

1. **Capture first, organise second.** A thought should never be lost because classification takes too long.
2. **The watch initiates; the phone completes.** The Garmin interaction should take only a few taps.
3. **Confirm uncertain interpretation.** Speech or date parsing must not silently create the wrong reminder.
4. **Private by default.** Notes are personal unless deliberately shared.
5. **Reliable reminders over clever reminders.** Durable scheduling and visible delivery state matter more than advanced natural-language features.
6. **One product across devices.** Phone and desktop use the same PWA and backend.
7. **Useful without the watch.** Garmin integration enhances a complete notes/lists/reminders application rather than becoming its only entry point.

## Core user journeys

### 1. Capture from the Garmin watch

1. Niki opens the Connect IQ application.
2. She chooses **Note**, **List**, **Reminder**, or **Quick capture**.
3. The watch sends an authenticated capture event.
4. Niki's Android phone receives a push notification.
5. She taps the notification and the installed PWA opens directly to the relevant recorder.
6. She speaks, reviews the transcript and interpreted fields, then saves.
7. The watch or phone shows a clear success or failure result.

The MVP does not depend on direct microphone access from Monkey C. The selected fallback is to use the watch as a trigger and the phone as the audio capture device.

### 2. Capture from the phone

1. Niki or Ben opens the installed PWA.
2. They tap the primary capture action.
3. They record speech or type text.
4. The application proposes a note, list item, or reminder.
5. They confirm or correct the result.
6. The item becomes available on all their devices.

### 3. Create and manage a reminder

1. A user enters or speaks a reminder.
2. The application extracts a title, time, optional recurrence, and recipients.
3. The user confirms the interpretation.
4. The reminder is stored durably.
5. At the due time, each selected recipient receives a push notification.
6. The reminder records delivery attempts and can be completed, snoozed, or rescheduled.

### 4. Maintain a shared list

1. Niki or Ben opens a shared list such as **Shopping**.
2. Either user adds, edits, checks, or unchecks an item.
3. Updates synchronise across devices.
4. The interface shows who added or completed an item where useful.

### 5. Review from a laptop

The desktop view supports:

- recent capture inbox;
- notes;
- lists and list items;
- upcoming reminders;
- shared-with-me content;
- completed and archived items;
- search and filtering;
- editing dates, recurrence, and recipients.

## Product model

### Capture

The durable record of what the user originally entered. It may contain:

- source device and entry mode;
- raw text or transcript;
- optional audio reference;
- interpretation status and confidence;
- resulting note, list item, or reminder;
- processing errors.

A capture remains available if transcription or classification fails, preventing the original thought from being lost.

### Note

Unstructured text with an owner and optional sharing.

Default: private.

### List and list item

A named collection of checkable items. Lists may be private or shared with household members.

Default for a new list: private, with an explicit sharing choice.

### Reminder

A time-based commitment containing:

- title and optional detail;
- due date/time and timezone;
- optional recurrence;
- recipients: Niki, Ben, or both;
- status such as pending, completed, or cancelled;
- notification delivery history.

### Device

A registered browser, phone, or Garmin watch credential. Device registration enables push delivery, watch pairing, and credential revocation.

## MVP scope

### Included

- Two application users: Niki and Ben.
- Responsive Android/desktop PWA.
- Installable PWA manifest and service worker.
- Notes with private-by-default sharing.
- Private and shared lists.
- Checkable list items.
- One-time reminders.
- Reminder recipients: me, Ben/Niki, or both.
- Web Push subscriptions per browser/device.
- Reminder delivery worker with durable delivery records.
- Typed capture from phone and desktop.
- Phone audio recording and server-side transcription.
- Transcript review before saving.
- Garmin watch trigger for phone capture.
- Pairing and revoking a Garmin watch.
- Tailscale-only main application.
- Narrow authenticated ingress for the watch.
- Basic backup, health check, and structured logs.

### Explicitly deferred

- Native Android companion application.
- Direct recording through the Garmin microphone.
- iPhone/iPad support beyond standards-compatible best effort.
- More than one household.
- Complex roles or enterprise permissions.
- Collaborative rich-text editing.
- Attachments other than short capture audio.
- Location-triggered reminders.
- Calendar integration.
- Email or SMS delivery.
- AI agents acting autonomously on reminders.
- Automatic creation when transcription or parsing confidence is low.

## Functional requirements

### Capture requirements

- A user can create a capture from phone or desktop using text.
- A user can record a short audio capture from an Android PWA.
- The backend can transcribe the audio and retain the raw transcript.
- Failed or uncertain captures remain visible in an inbox.
- A user can convert a capture to a note, list item, or reminder.

### Notes

- Create, view, edit, archive, and search notes.
- Share or unshare a note with another user.
- Enforce private-by-default access.

### Lists

- Create, rename, archive, and share lists.
- Add, edit, reorder, check, uncheck, and delete list items.
- Synchronise changes across devices.

### Reminders

- Create, edit, complete, cancel, snooze, and reschedule a reminder.
- Select one or both household recipients.
- Store dates in UTC while preserving the user's intended timezone.
- Recover scheduling state after application or server restart.
- Avoid duplicate notification delivery through idempotent delivery records.
- Expose delivery status to the creator.

### Notifications

- Register and revoke Web Push subscriptions per browser/device.
- Send a capture notification after a valid watch trigger.
- Send due-reminder notifications to all selected recipients.
- Open the correct PWA route when a notification is tapped.
- Use minimal notification content when the device is locked.

### Garmin

- Pair a watch without entering a long secret on the watch.
- Store a revocable, device-specific credential.
- Offer Note, List, Reminder, and Quick capture actions.
- Send an authenticated, replay-resistant event to the watch ingress.
- Show clear queued, sent, and failed states.

## Non-functional requirements

### Privacy and security

- The main PWA and general API remain accessible only inside the tailnet.
- Public watch ingress exposes only the minimum watch-event API.
- No application secrets are committed to Git.
- Credentials can be revoked per watch or browser.
- Authorization is checked for every shared resource.
- Notification payloads avoid unnecessary sensitive content.
- Audio retention is configurable and defaults to deletion after successful confirmation unless product testing shows a need to retain it.

### Reliability

- Restarting any application process does not lose notes, lists, reminders, or pending reminder schedules.
- Notification attempts are recorded and idempotent.
- Failed notification deliveries are retryable with bounded backoff.
- Database backups are automated and restorable.

### Performance

Initial targets for the two-user deployment:

- Interactive API responses under 500 ms for normal CRUD operations on the home network.
- Watch trigger acknowledged within 3 seconds under normal connectivity.
- Android capture notification delivered within 10 seconds under normal connectivity.
- A short audio capture transcribed quickly enough that review feels conversational; the exact target will be set after benchmarking `fedora-1`.

### Accessibility and usability

- Large phone capture controls usable one-handed.
- Keyboard-accessible desktop interface.
- Visible labels in addition to colour and icons.
- Clear timezone and recipient display before saving reminders.
- Errors preserve the user's entered or spoken content.

## Success criteria

The MVP is successful when:

1. Niki can initiate a reminder from the Garmin, finish speaking it on Android, and receive the reminder later.
2. Niki can assign a reminder to Ben and his Android device receives it.
3. Niki and Ben can maintain a shared shopping list from phone and laptop.
4. A server restart does not lose or duplicate pending reminders.
5. A failed transcription remains recoverable from the capture inbox.
6. The general application remains unavailable outside the tailnet.
7. The public watch endpoint cannot read or enumerate household content.

## Delivery stages

### Stage 0: Integration feasibility spike

Prove the riskiest path end to end:

1. Minimal Monkey C application on the target Garmin.
2. Authenticated HTTPS event through a narrow Tailscale Funnel ingress.
3. Backend receipt and validation.
4. Web Push to an Android device.
5. Notification tap deep-links into a test PWA recording route.

### Stage 1: Useful PWA without Garmin

Implement accounts, typed capture, notes, shared lists, one-time reminders, and private Tailscale deployment.

### Stage 2: Reliable notifications and sharing

Implement push subscription management, the reminder delivery worker, recipients, retries, delivery history, and notification deep links.

### Stage 3: Voice capture

Implement browser audio recording, local transcription, transcript review, capture inbox, and conservative intent/date extraction.

### Stage 4: Garmin integration

Implement pairing, watch menus, production watch ingress, phone capture notifications, and real-device testing.

### Stage 5: Refinement

Consider recurrence, richer offline behaviour, search improvements, templates, and better natural-language interpretation based on actual usage.

## Open product questions

- Confirm the exact Garmin model variant and target Connect IQ API level.
- Should all newly created lists remain private, or should a named household list such as **Shopping** be shared by default?
- What should the default reminder recipient be: creator only or both users?
- How long should confirmed audio be retained, if at all?
- Which reminder recurrence patterns are important enough for the first post-MVP release?
- Should quick capture always enter the inbox, or should high-confidence interpretations be saved automatically later?
- What wording and information are acceptable on the Android lock screen?

## References

- [Garmin Connect IQ `Toybox.Communications`](https://developer.garmin.com/connect-iq/api-docs/Toybox/Communications.html)
- [Garmin Connect IQ `WatchUi.TextPicker`](https://developer.garmin.com/connect-iq/api-docs/Toybox/WatchUi/TextPicker.html)
- [Garmin: Communicating with Mobile Apps](https://developer.garmin.com/connect-iq/core-topics/communicating-with-mobile-apps/)
- [MDN Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)
- [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve)
