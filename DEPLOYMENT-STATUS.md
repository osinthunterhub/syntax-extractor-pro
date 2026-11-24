# v0.4.0 — TOKEN + CLASSPLUS OTP / USER DASHBOARD / OWNER OVERVIEW LIVE

Bot https://t.me/SyntaxExtractProBot ; same isolated new bot9049794072.
Scope explicitly ONLY extractor; old forwarding bot untouched.
User chose BOTH Classplus own-token and own mobile/provider-OTP login options.
Deployed source 162d155134ee3e3f279a873db6c803bb2e805674
Deploy dep-dc2lakcs728c73auom80: LIVE. FREE Singapore srv-dc2j83uc6qcc73f732fg.
CI45363068720: Python3.12/3.13 SUCCESS;319synthetic regression tests PASS0.57s.
Production app Pyflakes clean; diff whitespace clean.
/readyz200, identity_verified=true, updates_configured=true, transport=mtproto-bot.
Hosted feature flags confirmed: token=true,OTP=true,user_dashboard=true,
owner_panel=true,priority_controls=true,display_cache_seconds20.
Final saved env verified OTPenabled/unpaused/MTProto; owner8841527686 unchanged,
owner notice false, auto-deploy OFF, service not suspended. No local bot-session use.

## Actual user-facing changes
/cplogin or /cp: token OR existing Classplus org-code/mobile/OTP selection.
/cptoken: own existing token. /cpotp: org -> own Indian number -> masked-number
confirmation -> explicit Send OTP -> provider OTP -> account course list.
No SMS auto-sent by choosing a method/phone input/startup. No auto-resend, no
password/new-account fake registration.5-minute per-step expiry,3verify attempts,
bounded request quotas/capacity, fixed official API origin, deadlines/response caps.
OTP/phone/provider challenge only in process RAM; raw OTP/token never logged or
copied to global/log channel. Telegram message deletion best-effort, NOT erasure.

/dashboard for EVERY ordinary user: only their accounts, channel, job, setup stage.
/admin or /stats: OWNER ONLY READ-ONLY aggregates/queue status and health controls.
No broadcast/global user deletion/settings features are pretended or exposed.
Command guide grouped/spaced. All registered command handlers exercised offline;
owner denial, usage errors and disconnected status are legitimate expected routes.
Inactive AppX hidden from public slash menu/main login; /appx reports setup status.
Catalog and /free remain honest INFORMATION pages, not working extra providers.

Performance fixes: bounded dedicated control queue/worker;4regular workers;
per-user locks cleaned after use (no lifetime250-user lockout);20s display cache,
explicit /refreshcourses;ALL up to500courses paged8at a time instead of long
message/sleep bursts. Export always re-fetches account membership and destination
rights; no cached authorization. Input deletion/callback ACK bounded2s. Login and
course-list requests have deadlines. Late cancelled requests cannot restore login.
Verified OTP token retained if course listing temporarily fails; user can refresh
without requesting a second SMS. No network/SMS instant-speed claim.

## Verified vs NOT verified
319 SYNTHETIC tests, including complete fake OTP->course->chosen-channel stub TXT,
all command routes, owner isolation, rate/expiry/registration rejection, cache
safety, cancel races,1000sequential users, independent queue capacity/dedup, control
responses while4regular provider requests deliberately stall. NO real SMS sent.
One deliberately nonexistent-org actual GET returned expected rejection using
source-derived authApiVersion51; course API uses reference29. No valid user
account/SMS/OTP success has been verified. Real course extraction and actual
chosen-channel file delivery remain unverified. These are not implied by readiness.
Current source details: LOGIN-DASHBOARD-v0.4.0-STATUS.md and command routing ledger.

## Deployment and limitations
CI-gated authenticated stop-first /ops/quiesce confirmed old socket disconnected,
no active jobs, oldready503/quiescedtrue BEFORE new deploy. Same bot StringSession
never connected concurrently/local, no reauthorization or logout.
Free Render can sleep; MTProto updates do NOT HTTP-wake a sleeping instance.
No24/7/permanent API compatibility/instant-SMS guarantee. RAM sessions, OTP setups,
destinations/jobs/cache reset on deployment. User-selected channel must be set
again, with user+bot admin checks; no DM fallback. AppX still disabled/no approved
host. No paid changes, old bot/services untouched. No ZIP made/presented.
