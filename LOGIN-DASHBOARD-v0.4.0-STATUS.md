# v0.4.0 — Both Classplus login options, public user dashboard, owner-only operations

## Explicit user choice
Scope ONLY SyntaxExtractProBot. Old forwarding bot remains untouched.
Classplus existing-token PLUS org-code / own-mobile / provider-OTP login authorized.
Every ordinary user gets their own dashboard. Global operations stay owner-only.

## Login implementation
New app/classplus_auth.py, fixed https://api.classplusapp.com origin only.
Reference snapshot f4ac41b2903242f99dd914b1e7db9a484bc9e0bb Classplus source;
official public web client main.6ca29153.chunk.js also inspected for org/OTP/verify
route and payload field usage. This is source-informed, NOT current contract or
real-account certification. Reference auth Api-Version51; account course API29.
No shared headers or copied hardcoded device ID. Fresh per-flow device/fingerprint.

/cplogin or /cp -> choose own token OR own existing Classplus OTP account.
Token option remains /cptoken or /connect classplus YOUR_OWN_TOKEN in PRIVATE chat.
OTP: /cpotp -> org code -> own Indian number (+91 or10digits) -> MASKED number
confirmation -> explicit Send OTP button -> Classplus OTP -> account course list.
No SMS on /cpotp, org resolution, phone input, startup, tests, or public probes.
No auto resend/retry of POST, no Telegram-user login/OTP, no password, borrowed
account, fake-email registration, log-channel copies, signing/decryption or DRM.
Registration-required responses tell user to complete official-app signup/profile.

Per-step inactivity expiry5minutes; stale challenges periodically purged<=60s
later. Phone/provider challenge live only in process RAM until flow ends/expires;
never printed in repr, logs, global panel, callbacks or support messages. OTP is
not retained as a challenge field; verification request frame expires normally.
Telegram may retain messages; deletion is best-effort, NOT secure erasure.
Send rate reservations occur BEFORE POST to prevent ambiguous-response resend:
1/minute+3/day per Telegram UID;1/minute+5/day per HMAC-hashed phone; global10/minute
and100/day, capacity1000rate keys. RAM-only counters reset on restart; provider may
impose stricter limits. Cancel/restart wizard does NOT reset current-process quota.
Org lookup5/minute per UID and30/minute global.3provider OTP verify attempts.
Auth HTTP total15s, connect5s, read10s, semaphore acquisition<=3s,64KiB response cap,
redirects disabled, public DNS resolver, shared cookie jar disabled in application.
Late/cancelled requests cannot resurrect login or delete a newer user's flow.
After verified OTP, temporary course-list failure retains the resulting account
connection and offers /refreshcourses, avoiding another SMS just to reload data.

## Responsiveness/command fixes
Separate bounded control queue16 for cancel/status/dashboard/admin/health/logout;
4regular workers +1control worker. Provider requests can be slow without occupying
that dedicated control worker. Regular queue32, provider/HTTP concurrency still
bounded. No arbitrary thread spawning or external keep-awake/paid infrastructure.
Per-user locks reference-counted and removed after use; fixed lifetime250-user
lockout risk. Session/setup/account capacity limits remain documented/bounded.
Best-effort input deletion/callback ACK each<=2seconds, not35second login blockers.
Whole account-course check bounded35seconds; safe timeout/recovery response.
Full course list no longer streamed in many messages with1second pauses: ALL up to
500courses remain reachable through8-item pages, names/IDs spaced clearly.
20-second per-user/provider/connection display cache; /refreshcourses bypasses it.
EVERY export still re-fetches provider account membership and rechecks destination
rights. No stale-cache authorization or arbitrary course-ID/store-catalog workflow.

## User / owner panels
/dashboard: OWN provider status, OWN destination, OWN job, OWN login stage; actual
buttons for login/courses/refresh/channel/status/cancel/logout. No other-user data.
/admin or /stats: OWNER ONLY, READ-ONLY aggregate counts/queues plus health controls.
Owner shortcut appears on owner's home/dashboard, not public Telegram command menu.
No broadcast/global user deletion/system settings claimed or exposed as fake UI.
/help grouped with blank lines; public slash menu ordered by actual task flow.
Disabled AppX hidden from published slash menu/main login buttons; direct /appx
still honestly returns setup status, not pretend export. Catalog/public-source
panels are INFORMATION, not implemented extra-provider integrations.
Every COMMANDS registry entry has an exercised handler (success/appropriate usage,
not-connected or owner denial); this is not proof every external provider works.

## Verification evidence
319 synthetic regression tests PASS0.57s; production app Pyflakes clean;
git diff --check clean. Old235tests retained (one stats-label assertion updated).
Complete synthetic OTP -> authenticated account -> course selection -> chosen
channel stub TXT delivery, with NO real SMS/token/account used. Token path and
membership/permission safety regressions retained.
Tests cover cancel race, per-user isolation, phone/OTP expiry, POST non-retry,
registration rejection, malformed tokens/HTTP/schema/caps, cooldown cannot be
reset by logout, owner denial, all registered command routes and callback sizes,
1000sequential users without stale lock exhaustion, independent overload/dedup,
and dashboard/cancel completion while all4regular workers are deliberately stalled.
500-course SYNTHETIC display check:1provider stub request+3fake Telegram messages;
~1.57ms LOCAL Python only, NO network latency. NOT a public speed/uptime benchmark.
One ACTUAL non-SMS GET for deliberately nonexistent org using authAPI51 returned
CLASSPLUS_AUTH_REQUEST_REJECTED, expected. No real phone, SMS or OTP used.

## Important remaining limits
Actual valid-account SMS delivery, OTP acceptance, live provider course extraction
and actual chosen-channel document delivery still UNVERIFIED. Do not claim they
passed from mocks, invalid-org probe or Telegram readiness. Real provider schemas
may differ; safe errors/own-token fallback are available. Indian mobile OTP only.
APPX_API_HOSTS remains empty/AppX disabled; not part of this scope. No permanent
third-party API compatibility or24/7/free-host wake guarantee. Free Render sleeps;
MTProto socket messages do not HTTP-wake a sleeping web instance. Accounts, OTP
flows, display cache, destinations and jobs are RAM-only and reset on deployment.
Single hosted bot-only session, never used locally. Auto-deploy remainsOFF.
CI-gated authenticated stop-first /ops/quiesce handoff required before deployment.
No ZIP made/presented, no paid changes, old bot/services untouched.
