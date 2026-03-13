# Quality Experience (QX) Report — SummaryBot NG
**Date:** March 13, 2026
**Analyst:** QE QX Partner (Agentic QE v3)
**Scope:** Full product — Discord bot commands, web dashboard, API layer, frontend UX
**Method:** Static code analysis of command handlers, dashboard routes, frontend components, and error handling patterns

---

## Executive Summary

**Overall QX Grade: B- (72/100)**

SummaryBot NG has a solid technical foundation with well-structured error handling, clear embed formatting in Discord, and a modern React dashboard with good skeleton loading states. The product delivers genuine value: multi-perspective AI summaries, schedule automation, webhook integration, and retrospective analysis.

However, a cluster of friction points significantly degrades first-run experience and ongoing usability. The most impactful issues are: a setup journey with no in-product guidance, task IDs that must be memorized for Discord schedule management, a dashboard "Generate Summary" flow that silently discards `perspective` from the API request, an incomplete Settings page with disabled inputs, and an onboarding gap where new guild admins have no clear next step after OAuth.

**Critical Issues (user-blocking):**
1. The dashboard Generate Summary dialog omits the selected `perspective` from the API request body
2. `/schedule delete|pause|resume` require users to know opaque task IDs with no autocomplete
3. No onboarding flow: new guilds land on an empty dashboard with no guided setup

**High-Impact Issues:**
4. `/config reset` has no confirmation — destructive with no undo
5. Dashboard Settings page has permanently disabled inputs with "Coming soon" copy — erodes trust
6. The `list_guilds` route fetches up to 10,000 stored summaries per guild in a loop — will degrade at scale and slow the first page users see
7. Time inputs for schedules assume UTC, but there is no clear timezone indicator in the Discord bot UI

**Positive Highlights:**
- Consistent embed formatting across Discord (error red, success green, info blue)
- Comprehensive loading skeletons throughout the dashboard
- Thoughtful empty states with direct CTAs
- Good rate-limit messaging with specific reset times
- Error page with badge count in sidebar and bulk resolve — excellent operational UX

---

## 1. User Journey Analysis

### Journey 1: Setting Up the Bot in a Guild

**User goal:** Add the bot to their Discord server and start getting summaries.

**Mapped steps:**
1. Visit landing page
2. Click "Login with Discord" — OAuth redirect
3. Land on `/guilds` — see their servers listed
4. Click into a guild
5. Navigate to Channels → enable channels
6. Return to Summaries → generate first summary

**Pain Points:**

**P1 — No onboarding wizard or guided setup.** A new guild that has never configured the bot shows `config_status: needs_setup` but nothing in the dashboard explains what to do. The `GuildDashboard` shows four stat cards (all zeros), two Quick Action links, and an empty "Recent Summaries" state that says "No summaries yet. Generate your first one!" The "Generate Summary" button is visible but clicking it without enabled channels produces either an empty result or a confusing API-level error with no user-friendly explanation. There is no step-by-step "Get Started" checklist.

**P2 — The Guilds page loads `DefaultPromptsCard` before the guild list.** The prompts feature is an advanced capability that means nothing to a new user who has not yet configured a single channel. It occupies prominent visual real estate on the server-selection page — the wrong moment in the journey.

**P3 — The Header has no guild-level breadcrumb.** Inside `/guilds/:id/*`, the header shows only "SummaryBot" logo and user avatar. There is no indication of which server the user is managing. On the guilds list page, `Header` is imported separately inside `Guilds` component, creating a double-render of the Header element (lines 58 and 304 of `App.tsx` vs `Guilds.tsx`).

**Friction score: HIGH**

---

### Journey 2: Configuring Summarization Options

**User goal:** Set the bot to summarize only certain channels with the right default options.

**Mapped steps:**
1. Channels page → toggle switches per channel → Save Changes
2. Settings page → set default length, perspective, action items toggle → Save Changes

**Pain Points:**

**P4 — Channels page uses `useMemo` with side effects for state initialization (line 36-40 of `Channels.tsx`).** `useMemo` is documented to not guarantee stable behavior for side effects; `useEffect` should be used instead. This can cause the enabled-channel state to reset unexpectedly when parent re-renders occur, making users lose unsaved toggle changes without feedback.

**P5 — "Save Changes" button only appears when `hasChanges === true`.** This is good progressive disclosure, but if the user reloads and has no pending changes, there is no way to know the current state was persisted. No "Last saved" timestamp or confirmation is shown.

**P6 — Settings page: custom prompt repository input is disabled with a `Coming soon` note.** The input placeholder, sync button, and text are all visible but non-interactive. This violates the principle that UI elements should not exist if they cannot be used. The label `Configure via Discord: /config prompts repo:URL` points to a command that does not appear in the `/help` output in `commands.py`.

**Friction score: MEDIUM**

---

### Journey 3: Triggering a Manual Summary (Discord)

**User goal:** Run `/summarize` in a channel and receive a useful summary.

**Mapped steps:**
1. User types `/summarize` — Discord autocomplete shows parameters
2. User sets options (length, perspective, optional channel/category)
3. Bot defers response immediately (`await interaction.response.defer(ephemeral=False)`)
4. Summary is generated asynchronously
5. Result posted as embed in channel

**Pain Points:**

**P7 — No progress feedback during generation.** After deferring, Discord shows the "Bot is thinking..." indicator, but users have no idea how long to wait. For large channels with comprehensive summaries, this can take 30+ seconds. There is no estimate or progress message.

**P8 — `channel` and `category` are mutually exclusive, but validated only at runtime.** The error `"Please specify either a channel OR a category, not both."` is sent as a plain string `❌ ...`, not as a proper embed. This breaks the consistent embed-based error formatting used everywhere else (compare `format_error_response` in `utils.py`).

**P9 — The `perspective` parameter in `/summarize` has seven options in the autocomplete, but the `summarize_command` does not validate that the value is one of the valid choices before passing it downstream.** A typo or unexpected value passed programmatically would fail silently inside the AI prompt selection layer.

**P10 — `hourly` frequency maps to `ScheduleType.CUSTOM` in `schedule.py` line 184.** There is no cron expression being set for hourly schedules; the code maps hourly to CUSTOM and presumably relies on some default — but no cron expression is populated. This is a silent misconfiguration path that would result in a schedule created but never running.

**Friction score: MEDIUM**

---

### Journey 4: Scheduling Automatic Summaries (Discord)

**User goal:** Set up a daily summary of #announcements at 9am UTC every weekday.

**Mapped steps:**
1. `/schedule create` with channel, frequency=daily, time=09:00
2. `/schedule list` to verify it was created
3. Task runs automatically
4. `/schedule pause task_id` to pause
5. `/schedule resume task_id` to resume

**Pain Points:**

**P11 — Task ID management is the single largest UX failure in the Discord interface.** `/schedule pause`, `/schedule resume`, and `/schedule delete` all require the user to pass a raw `task_id` string (e.g., `sched_abc123xyz`). Users must first run `/schedule list`, read the ID from the `🆔 **ID:** \`...\`` field in the embed, then manually copy-paste it into the next command. Discord slash commands support autocomplete; implementing autocomplete that fetches the guild's schedules and presents them by name would eliminate this entirely. There is no current implementation of this pattern.

**P12 — `/schedule list` shows only 10 tasks maximum** (hardcoded on line 319: `for i, task in enumerate(summary_tasks[:10], 1)`). If a guild has more than 10 schedules, the embed footer says "Showing 10 of N" but provides no way to see the rest from Discord. Users cannot paginate.

**P13 — No timezone context in Discord schedule creation.** The time parameter is stated as `HH:MM format, UTC` in the describe annotation, but there is no explanation of what UTC means relative to the user's local time. A user in New York setting `09:00` expects 9am New York time but gets 9am UTC (4am or 5am New York). No conversion or warning is provided.

**P14 — Schedule create success embed shows `Task ID` in the fields.** This is good — users can copy the ID immediately after creation — but the footer says "Use /schedule list to view all scheduled summaries" without explaining that the list is needed to get IDs for future management operations.

**Friction score: HIGH**

---

### Journey 5: Scheduling Automatic Summaries (Dashboard)

**User goal:** Create and manage a recurring daily schedule from the web dashboard.

**Mapped steps:**
1. Navigate to Schedules page
2. Click "Create Schedule"
3. Fill in ScheduleForm inside a Dialog
4. Submit → schedule appears in list
5. Toggle active/paused via card switch
6. View run history

**Pain Points:**

**P15 — ScheduleForm timezone default is `America/Toronto` as a hardcoded fallback**, and the TIMEZONES list has only 14 entries. Users in Africa, South America (except implicitly UTC), or the Middle East cannot find their timezone. The browser's detected timezone falls back to Toronto if it is not in the limited list. The Settings page separately has a comprehensive timezone selector backed by a full `TIMEZONE_OPTIONS` list — but the ScheduleForm uses its own restricted list, creating inconsistency.

**P16 — Schedule create error toast is generic**: `"Failed to create schedule."` with no detail. API errors (503 scheduler unavailable, 403 no permission) have structured `detail` objects with `code` and `message`, but the `handleCreate` catch block discards them entirely. The same pattern exists for `handleEdit`, `handleDelete`, and `handleRunNow`.

**P17 — "Run now" does not confirm success with the result location.** When a user clicks "Run Now" on a schedule, the toast says "The schedule is running now." but does not tell users where the output will appear (e.g., which channel, or to check the Summaries tab). The `ScheduleRunResponse` returns an `execution_id` that is never surfaced to the user.

**Friction score: MEDIUM-HIGH**

---

### Journey 6: Viewing and Managing Summaries (Dashboard)

**User goal:** Find a specific summary from last Tuesday, view it, push it to a channel.

**Mapped steps:**
1. Navigate to Summaries → All Summaries tab
2. Filter/search for Tuesday's summary
3. Click to view full content
4. Use "Push to Channel" to post it to Discord

**Pain Points:**

**P18 — The `perspective` field is not included in the `GenerateRequest` sent from `Summaries.tsx`.** Looking at `handleGenerate` (lines 132-153), the `request.options` object has `summary_length`, `include_action_items`, and `include_technical_terms` — but not `perspective`, despite the fact that the user just selected a perspective in the dialog. The selected `perspective` state variable is collected but never used in the request. This means every dashboard-generated summary uses the server default perspective regardless of user selection.

**P19 — The "Recent Summaries" card on GuildDashboard only shows "Last summary: [date]"** even when `total_summaries > 0`. There is no inline list of recent summaries — just one date field. Users who want to quickly access recent content must navigate away to the Summaries page. The card has a "View All" link but no preview.

**P20 — `list_guilds` fetches `limit=10000` stored summaries per guild on every page load.** This runs inside a loop over all user guilds. For a guild with 500 summaries this is manageable; for a production guild with years of scheduled summaries this query will be extremely slow and will block the guilds page from rendering. A simple `COUNT(*)` or a capped `limit=1` with a separate count endpoint would be far more appropriate.

**Friction score: HIGH**

---

### Journey 7: Managing Webhooks and Feeds

**Mapped steps:**
1. Navigate to Webhooks
2. Create webhook (name, URL, type)
3. Test webhook
4. Enable/disable

**Pain Points:**

**P21 — Webhook URL validation is purely "not empty" on the frontend.** The form shows an Input for the URL but nothing prevents submitting a malformed non-HTTPS URL. The backend does POST test requests, which would fail, but the error feedback path from test failure back to the user is through a generic toast, not inline field validation.

**P22 — Webhook `type` options are `generic`, `slack`, `discord`** — useful distinctions, but there is no explanation of what format each produces. A user adding a Slack webhook and selecting `generic` would receive an unexpected payload format. No tooltip or help text is present.

**Friction score: LOW-MEDIUM**

---

### Journey 8: Error States and Recovery

**User goal:** Something went wrong — figure out what happened and fix it.

**Pain Points:**

**P23 — The Errors page is an excellent operational tool**, but the distinction between `discord_permission` errors (hidden by default via "Show Missing Access" toggle) and other errors is not explained. A new user seeing the error page may not understand that permission errors are suppressed by default and may incorrectly believe there are no errors.

**P24 — Error detail drawer exposes raw `context` fields** (user_id, guild_id, channel_id) with no explanation of what they mean. Technical metadata is shown before the human-readable context that would help an admin understand what was happening.

**P25 — `CriticalError` always shows "The development team has been notified"** (base.py, line 139), but there is no notification mechanism visible in the codebase. This is a false promise that erodes trust if users discover errors are not actually being escalated anywhere.

**Friction score: MEDIUM (mitigated by strong error page design)**

---

## 2. Error Handling UX Assessment

### Discord Bot (Python)

**Strengths:**
- Consistent three-tier error coloring: red (error), green (success), blue (info)
- Rate limit feedback includes exact seconds until reset — specific and actionable
- `UserError` vs `RecoverableError` vs `CriticalError` distinction cleanly separates user-caused vs system errors
- Retry hint is only shown when `retryable=True` — not shown for user errors
- Error code in footer (e.g., `Error Code: INVALID_TIME_FORMAT`) provides a reference for bug reports

**Weaknesses:**
- The mutual-exclusivity validation in `summarize_command` (line 86-91) sends a plain string `"❌ Please specify either a channel OR a category, not both."` — bypasses the embed system. Visually inconsistent.
- Unexpected errors expose the raw Python exception string: `f"❌ An error occurred: {str(e)}"` (line 124). This can leak stack traces or internal service names to end users.
- `InsufficientContentError` and `ChannelAccessError` are imported in `summarize.py` but the user-facing messages for these are not visible in the command handler file reviewed — needs verification that they produce helpful guidance.
- `CriticalError.user_message` is static: "A critical error occurred. The development team has been notified." — no variation based on context, no actionable next step.

### Dashboard (React + FastAPI)

**Strengths:**
- 401 responses automatically log the user out and redirect to `/` — correct security behavior
- Structured error objects from FastAPI (`{"code": "...", "message": "..."}`) enable differentiated error handling
- Toast notifications for all CRUD operations

**Weaknesses:**
- API client `handleResponse` throws the raw error object (`throw error`) rather than a normalized Error instance. Catch blocks in components receive the raw FastAPI `detail` object, but most component-level catches use generic messages like `"Failed to create schedule."` — discarding the structured `detail.message` that the API provides.
- `delete` method in `ApiClient` has its own inline 401 handling (lines 72-76) that duplicates the logic from `handleResponse`, creating two code paths that could diverge.
- No global error boundary in `App.tsx`. An unhandled exception in any route component will crash the entire application with a blank screen.
- `loginFailed` path on Landing: if `api.get("/auth/login")` throws, the catch only logs to console — the user sees nothing and the button appears to do nothing.

---

## 3. Command and API Consistency Review

### Discord Command Naming

The command structure follows a consistent Group + Subcommand pattern:
- `/summarize` (flat)
- `/schedule list | create | delete | pause | resume`
- `/prompt-config set | status | remove | refresh | test`
- `/config view | set-cross-channel-role | permissions | reset`

**Inconsistency:** `/config` is missing a `set-channels` subcommand visible from the Discord interface, even though `ConfigCommandHandler.handle_config_set_channels()` exists in `config.py`. Channel configuration appears to have been moved to the dashboard exclusively, but the handler still exists, suggesting incomplete migration.

**Inconsistency:** `/help` lists `/config` subcommands as `"view, set-cross-channel-role, reset"` — it omits `permissions`, which is registered as a command. The help text is manually maintained and has drifted from the actual command tree.

**Inconsistency:** `/schedule create` uses `frequency` as a free-text string (no autocomplete choices), while `/summarize length` uses properly defined `discord.app_commands.choices`. A user typing `half weekly` instead of `half-weekly` gets a confusing `"Frequency must be one of: hourly, daily, weekly, half-weekly, monthly"` error that could have been prevented with a choices list.

### Dashboard API

**Strengths:**
- REST-ful resource structure: `/guilds/{id}/schedules/{schedule_id}`
- Consistent `ErrorResponse` model with `code` and `message` fields
- PATCH semantics used correctly for partial updates (schedules, config)
- `200` for reads, `503` for service unavailability are appropriate

**Weaknesses:**
- `list_guilds` silently returns an empty list when repository initialization fails (line 88). A 503 with an explanation would be more appropriate than an empty list that looks like "you have no servers."
- `run_schedule` returns `{"execution_id": "...", "status": "started"}` but the execution ID is generated locally with `secrets.token_urlsafe(16)` (line 514) — it is never stored or retrievable. The history endpoint returns real execution IDs from the database, creating a mismatch that makes the "started" response's ID useless.
- Schedule delete returns `{"success": True}` as an untyped dict (line 476), while all other endpoints use Pydantic response models — breaks OpenAPI schema generation.

---

## 4. Frontend UX Assessment

### Loading and Skeleton States

**Positive:** Every page has a matching `*Skeleton` component with appropriately sized placeholders. `ChannelsSkeleton`, `SchedulesSkeleton`, `ErrorsSkeleton`, `SettingsSkeleton` — all implemented. The skeleton granularity matches the actual content shape (e.g., schedules skeleton has the right proportions for a schedule card).

**Gap:** `GuildDashboard` has a `DashboardSkeleton` but the "Guild not found" state (`!guild` after loading completes) shows only a centered `<p>Guild not found</p>` with no guidance, no back link, and no explanation of why the guild might not be found (bot not present, no permission).

### State Management

**Positive:** React Query is used throughout for server state. Cache invalidation (`queryClient.invalidateQueries`) is called after mutations, keeping the UI fresh.

**Gap:** `Channels.tsx` uses `useMemo` to initialize local state (`setEnabledChannels`) as a side effect. `useMemo` does not guarantee execution timing and is documented as an optimization hint, not a guaranteed effect. This should be `useEffect` with `guild` as a dependency to ensure correct initialization.

**Gap:** `QueryClient` in `App.tsx` (line 42) is created with default options — no `staleTime`, no `gcTime` configuration, no `retry` count. Network failures will retry 3 times by default (React Query default), which means a 503 error from the backend will trigger 3 requests before showing an error. For a bot-unavailable scenario during restart, this creates a 4-request burst from every user.

### Form UX

**Positive:** Channel search in the Generate Summary dialog is a good progressive disclosure pattern for large servers.

**Gap:** The Generate Summary dialog uses `<label>` elements without `htmlFor` attributes for the scope selector and time range — these labels are not programmatically associated with their controls, breaking accessibility.

**Gap:** Schedule name field is required (`disabled={!formData.name || ...}`), but there is no visible required indicator (`*`) or inline validation message telling users why the Create button is disabled when the name is blank.

**Gap:** The `ScheduleForm` timezone list (14 entries) and the Settings page timezone list (comprehensive, grouped by region) are different data sources. A user who sets "Asia/Kolkata" in Settings cannot select it in a schedule form — it defaults to America/Toronto.

### Animation

**Positive:** Framer Motion is used tastefully — entrance animations on page elements with staggered delays (`transition={{ delay: index * 0.1 }}`). Non-intrusive and adds polish.

**Gap:** Animation delays up to `0.4s` on dashboard cards means content takes 400ms to appear even when data is already loaded. On fast connections, this creates a perception of slowness. Animation should be conditional: only animate if the data was not previously cached.

---

## 5. Accessibility Review

**Note:** This review is based on static code analysis; no automated accessibility scanner was run against a live instance. Issues identified are structural concerns from code patterns.

**P26 — Form labels are not associated with controls.** In `Summaries.tsx` dialog (lines 201, 318, 335, 349), labels are plain `<label className="text-sm font-medium">` without `htmlFor`. The corresponding inputs and selects have no `id` attributes linking back to labels. Screen readers cannot announce which label belongs to which control.

**P27 — Icon-only buttons lack accessible names.** In `StoredSummaryCard`, `MoreVertical` icon triggers a dropdown. The trigger button presumably has no `aria-label`. Users relying on screen readers would encounter an unnamed button.

**P28 — Switch components lack context labels in some locations.** The `Channels.tsx` switches have no associated `<label>` — only the channel name text adjacent to the switch. Without an `id`/`htmlFor` pair or `aria-label`, the switch's accessible name may be empty.

**P29 — Color is used as the only differentiator for error severity.** The `ErrorCard` component uses color badges for severity levels (critical = red, warning = yellow, etc.). Users with color vision deficiency may not distinguish severity without additional text or icon cues.

**P30 — The `Landing.tsx` hero section's "S" logo in the `<div>` is not marked as decorative.** The Discord SVG logo in the login button has no `aria-hidden` or `aria-label`, which may cause screen readers to announce the SVG path data.

**P31 — Focus management on modals.** When dialogs open (Generate Summary, Create Schedule), focus should move to the first interactive element inside. Radix UI Dialog handles this by default, so this may be addressed — but it requires runtime verification.

**Accessibility Grade: C (estimated)**

---

## 6. Information Architecture

### Navigation Hierarchy

The sidebar navigation in `GuildSidebar.tsx` has 9 items:
`Overview > Channels > Summaries > Schedules > Webhooks > Feeds > Errors > Retrospective > Settings`

**Issue:** "Retrospective" in the sidebar links to `/archive`, but "Retrospective" also appears as a tab inside the Summaries page. The Summaries page `Retrospective` tab does not contain retrospective summaries — it explains how to go to the Archive page. This is a disorienting two-step indirection: Summaries → Retrospective tab → Archive page. The tab should either be the Archive content inline, or the sidebar item should be the only entry point.

**Issue:** "Errors" is the 7th item in a 9-item list, positioned between "Feeds" and "Retrospective." Operationally, errors are high-priority content. The error badge in the sidebar is the only proactive signal. Consider positioning "Errors" earlier, or making it a bottom-pinned item like a "Health" status section.

**Issue:** The Summaries page has three tabs: "All Summaries", "Jobs", "Retrospective." The "Jobs" tab contains background task status. First-time users have no context for what a "Job" is. "Job" is an internal technical term; from a user perspective, this is "Generation Status" or "Processing Queue."

### Naming Inconsistencies

| Location | Term Used | Alternative Term Used Elsewhere |
|---|---|---|
| Discord `/schedule` command | "Scheduled Summary" | Dashboard: "Schedule" |
| Discord `/config view` | "Configuration" | Dashboard: "Settings" |
| Discord embed | "Task ID" | Dashboard list item: `schedule.id` |
| Dashboard sidebar | "Retrospective" | Summaries tab: also "Retrospective" |
| Dashboard "Generate Summary" | "Scope" | Discord: "channel", "category" |
| Error page | "Missing Access" | Discord: "Permission Denied" |

---

## 7. Friction Points and Pain Points (Consolidated)

### Priority 1 — User-Blocking

| ID | Issue | Location | Impact |
|---|---|---|---|
| P1 | No onboarding flow for new guilds | Dashboard | First-run failure |
| P11 | Task ID required for schedule management | Discord bot | Workflow barrier |
| P18 | `perspective` silently dropped from Generate Summary API request | Dashboard | Feature non-functional |
| P8 | Mutual exclusivity error uses plain string, not embed | Discord bot | Visual inconsistency |

### Priority 2 — High Friction

| ID | Issue | Location | Impact |
|---|---|---|---|
| P2 | Default Prompts card shown before guild list | Dashboard Guilds page | Confusing onboarding |
| P4 | `useMemo` for state initialization may reset unsaved channel changes | Dashboard Channels | Data loss risk |
| P6 | Settings page has disabled inputs with "Coming soon" | Dashboard Settings | Trust erosion |
| P13 | No UTC-to-local timezone indication for schedule times | Discord bot | Silent misconfiguration |
| P15 | ScheduleForm timezone list (14 entries) diverges from Settings timezone list | Dashboard | Inconsistency |
| P16 | Schedule error toasts discard structured API error details | Dashboard | Unhelpful feedback |
| P20 | `list_guilds` fetches 10,000 summaries per guild on page load | Backend API | Performance degradation |
| P25 | "Development team has been notified" message is false | Both | Trust erosion |

### Priority 3 — Moderate Friction

| ID | Issue | Location | Impact |
|---|---|---|---|
| P3 | No guild breadcrumb in header inside guild routes | Dashboard | Orientation confusion |
| P7 | No progress indication during summary generation (Discord) | Discord bot | Uncertainty |
| P10 | `hourly` frequency maps to CUSTOM with no cron expression set | Discord bot | Silent schedule failure |
| P12 | `/schedule list` hardcoded to 10 tasks with no pagination | Discord bot | Incomplete information |
| P17 | "Run now" toast gives no output location | Dashboard | No feedback loop |
| P19 | Dashboard Recent Summaries shows only last date, no preview | Dashboard | Missed engagement |
| P21 | No URL format validation for webhooks | Dashboard | User error |
| P22 | Webhook type has no explanation | Dashboard | Incorrect configuration |
| P24 | Error detail drawer leads with raw IDs | Dashboard Errors | Poor information hierarchy |

---

## 8. Positive UX Patterns Found

These are patterns done well and worth preserving.

**Discord embed consistency:** The `format_error_response` / `format_success_response` / `format_info_response` utility functions enforce consistent color coding and structure across all command responses. Red/green/blue color semantics are applied uniformly.

**Rate limit feedback quality:** `send_rate_limit_response` tells users exactly how many seconds to wait (`f"Please wait {reset_seconds} seconds"`) and shows the rate limit policy (`5 requests per 60 seconds`). This is far better than a generic "too many requests" message.

**Comprehensive skeleton loading:** Every page in the dashboard has a thoughtfully implemented skeleton that matches the shape of the actual content. This prevents layout shift and sets appropriate expectations.

**Empty states with direct CTAs:** The Schedules page empty state shows a large calendar icon, "No schedules yet," an explanation, and a "Create Schedule" button that opens the creation dialog directly. This is textbook empty state design.

**Error page with sidebar badge:** The unresolved error count badge in the sidebar navigation is a proactive signal that draws admin attention without interrupting the primary workflow. The badge caps at "99+" to prevent layout disruption.

**Bulk resolve with confirmation:** The bulk resolve flow on the Errors page uses `DropdownMenu` to select error type, then an `AlertDialog` for confirmation, then shows a count of resolved items in the success toast. The destructive action pattern is well-implemented.

**Ephemeral responses for sensitive data:** Discord bot consistently sends configuration, permission errors, and diagnostic info as `ephemeral=True`. Users' sensitive configuration is not exposed to other channel members.

**Deferred responses for long operations:** `summarize_command` correctly defers immediately before processing. The defer-then-followup pattern prevents Discord's 3-second timeout.

**Channel search in Generate Summary dialog:** The inline search box for channel selection in the generate dialog is well-placed for servers with many channels. Empty state for filtered results is handled gracefully.

**Timezone persistence in Settings:** The `TimezoneContext` and `TimezoneProvider` pattern persists the user's display timezone across the session. Schedule times are rendered in the user's selected timezone via `parseAsUTC`. This is a thoughtful touch for global teams.

**Run History Drawer on Schedules:** The ability to view the execution history of a specific schedule from the schedule card is well-placed. Contextual history rather than a global log is the right approach.

---

## 9. Recommendations (Prioritized by User Impact)

### Priority 1 — Fix Immediately

**R1: Fix the `perspective` bug in Generate Summary**
In `Summaries.tsx` `handleGenerate`, add `perspective` to the request options:
```
options: {
  summary_length: summaryLength,
  perspective: perspective,   // add this
  include_action_items: true,
  include_technical_terms: true,
}
```
**Effort:** 5 minutes. **Impact:** Users' perspective selection actually works.

**R2: Add autocomplete to Discord schedule management commands**
Implement an `autocomplete` callback for `task_id` parameters in `/schedule pause`, `/schedule resume`, and `/schedule delete`. The callback fetches `scheduler.get_scheduled_tasks(guild_id)` and returns choices as `[Choice(name=task.name, value=task.id)]`. This eliminates the ID-memorization requirement entirely.
**Effort:** 2–3 hours. **Impact:** Eliminates the single largest Discord UX barrier.

**R3: Fix mutual-exclusivity error to use embed format**
In `summarize_command` (line 87-91), replace the plain string response with `format_error_response(error_message, "MUTUAL_EXCLUSIVITY_ERROR")` embed.
**Effort:** 30 minutes. **Impact:** Visual consistency.

**R4: Add confirmation dialog to `/config reset`**
Either implement a Discord `Modal` confirmation asking users to type "RESET" to confirm, or add a `confirm: bool` parameter with `describe` text explaining what will be lost.
**Effort:** 1–2 hours. **Impact:** Prevents accidental destructive action.

---

### Priority 2 — Address Within Sprint

**R5: Add guild onboarding flow**
When `config_status === "needs_setup"`, render a prominent "Get Started" card on `GuildDashboard` with three numbered steps: (1) Enable channels, (2) Generate your first summary, (3) Set up a schedule. Link each step to the relevant page. This replaces the disconnected empty stat cards.
**Effort:** 1 day. **Impact:** First-run experience transforms from confusing to guided.

**R6: Fix `useMemo` in `Channels.tsx` to `useEffect`**
Replace `useMemo(() => { setEnabledChannels(...) }, [guild])` with `useEffect(() => { if (guild) setEnabledChannels(new Set(guild.config.enabled_channels)) }, [guild])`.
**Effort:** 10 minutes. **Impact:** Prevents potential data loss on channel toggle.

**R7: Replace "Coming soon" UI in Settings with honest placeholder**
Remove the disabled input and Sync button. Replace with: "Custom prompt configuration is managed via Discord commands. Use `/prompt-config set repo_url:URL` to configure." This is truthful and actionable rather than teasing unavailable UI.
**Effort:** 30 minutes. **Impact:** Trust preservation.

**R8: Fix `list_guilds` summary count query**
Replace `find_by_guild(guild_id=guild_id, limit=10000)` with a dedicated count method. If no count method exists, add one (`SELECT COUNT(*) FROM stored_summaries WHERE guild_id = ?`). The separate `find_by_guild(limit=1, sort_by="created_at", sort_order="desc")` call for `last_summary_at` is fine.
**Effort:** 2–4 hours. **Impact:** Dashboard home page loads dramatically faster at scale.

**R9: Surface structured API errors in error toasts**
In each mutation `catch` block in Schedules, Webhooks, Feeds pages, extract the `detail.message` from the API error and use it in the toast description:
```typescript
catch (error: unknown) {
  const detail = (error as { message?: string; detail?: { message?: string } });
  toast({ title: "Error", description: detail?.detail?.message || detail?.message || "Failed to create schedule.", variant: "destructive" });
}
```
**Effort:** 2 hours across all pages. **Impact:** Users receive actionable error information.

**R10: Add UTC note to schedule time in Discord**
In `handle_schedule_create`, after accepting `time_of_day`, echo back the time explicitly as UTC in the success embed: `"Schedule: Daily at 09:00 UTC"` and add a note: "⏰ Times are always in UTC. Your local time may differ." Consider adding an optional `timezone` parameter to the Discord command that mirrors the dashboard capability.
**Effort:** 1 hour. **Impact:** Eliminates timezone misconfigurations.

---

### Priority 3 — Plan for Next Quarter

**R11: Add `/schedule create` frequency as a choices list**
Convert the free-text `frequency` parameter to `discord.app_commands.choices` with the five valid values. Eliminates the validation error class entirely.

**R12: Expand ScheduleForm timezone list to match Settings**
Move the TIMEZONES list to a shared constant and use `TIMEZONE_OPTIONS` from `TimezoneContext` (or a superset of it) in `ScheduleForm`. Alternatively, allow typing/searching in a combobox.

**R13: Move "Errors" higher in sidebar or pin it**
Move "Errors" to position 4 (after Summaries) or pin it to the bottom of the sidebar as a health indicator. The error badge is the most important proactive signal; it should be in a prominent location.

**R14: Add global React error boundary**
Wrap the entire router in an `ErrorBoundary` component that catches unhandled React errors and shows a user-friendly recovery screen with a "Reload" button rather than a blank page.

**R15: Remove or replace the false "development team notified" message**
Either implement actual alerting (Sentry, PagerDuty webhook) so the message is true, or replace the `CriticalError` user message with: "An unexpected error occurred. Please try again or contact your server administrator."

**R16: Add `aria-label` to icon-only interactive elements**
Audit all instances of icon-only buttons and dropdowns (MoreVertical, RefreshCw used as standalone buttons) and add `aria-label` attributes.

**R17: Associate form labels with controls using `htmlFor`**
In `Summaries.tsx` dialog and `ScheduleForm`, add `id` attributes to all inputs/selects and matching `htmlFor` to their labels.

**R18: Unify the "Retrospective" navigation entry point**
Remove the "Retrospective" tab from the Summaries page tabs. The tab currently only links to the Archive page — it is a dead-end tab. Users should access retrospective analysis directly from the sidebar "Retrospective" link.

**R19: Rename "Jobs" tab to "Generation Status"**
The "Jobs" label is an internal technical term. "Generation Status" or "Processing Queue" better communicates the purpose to non-technical server administrators.

**R20: Add progress estimate to Discord summary generation**
After deferring, consider sending an intermediate followup (if generation exceeds 10 seconds) such as "Still generating — processing N messages..." This requires timing instrumentation in the summarization engine but would dramatically reduce user uncertainty for large channels.

---

## Appendix: Heuristic Scores

| Heuristic | Area | Score | Notes |
|---|---|---|---|
| H1.1 Problem Understanding | Setup journey | 45/100 | No guided onboarding |
| H1.2 User Goal Alignment | Summary generation | 70/100 | Perspective bug undermines intent |
| H2.1 Error Message Quality | Discord | 80/100 | Strong; one plain-string outlier |
| H2.2 Error Message Quality | Dashboard | 55/100 | Generic toasts discard API detail |
| H2.3 Empty State Quality | Dashboard | 85/100 | CTAs present; excellent |
| H2.4 Loading State Quality | Dashboard | 90/100 | Comprehensive skeletons |
| H2.5 Command Discoverability | Discord | 60/100 | `/help` outdated; no autocomplete for IDs |
| H2.6 Feedback Immediacy | Discord | 70/100 | Defer+thinking good; no progress |
| H3.1 Task Completion Efficiency | Schedule management | 40/100 | ID requirement is high-friction |
| H3.2 Information Architecture | Dashboard | 65/100 | Retrospective duplication, Jobs naming |
| H3.3 Consistency | Cross-system | 60/100 | Naming diverges bot vs dashboard |
| H3.4 Error Recovery | Dashboard | 55/100 | No guidance on how to fix issues |
| H4.1 Accessibility | Dashboard | 40/100 | Labels not associated, color-only severity |
| H4.2 Mobile/Responsive | Dashboard | 75/100 | Responsive grid, sidebar close on mobile |
| H5.1 Performance Perception | Dashboard | 65/100 | 10k summary query on guild list |
| H5.2 Trust Signals | Both | 55/100 | False "team notified", disabled inputs |
| H6.1 Progressive Disclosure | Dashboard | 70/100 | Prompts card shown too early |
| H6.2 Destructive Action Safety | Discord | 35/100 | `/config reset` has no confirmation |

---

*Report generated by QE QX Partner — Agentic QE v3*
*Coverage: All primary user journeys; 8 route files; 13 page components; 6 command handler files; 2 API client files*
