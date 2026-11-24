# AppX + Classplus focused upgrade — v0.3.2

## What was actually reviewed
Reference snapshot princepiamotox/Extractor_Pro_x@f4ac41b2903242f99dd914b1e7db9a484bc9e0bb.
Eight provider/setup source files fetched and parsed without importing/executing.
Classplus function bodies read in sanitized AST form, including shared session,
login/logging, course list and recursive content traversal. AppX reference endpoint
construction inspected and compared to our fixed allowlist adapter. AppX V1/V2/V3
have empty ASTs: their source implementations are commented out. This targeted
review is NOT a claim that every repository source line, compiled artifact or
interactive reference-bot button was audited. The screenshot catalog remains49+16
names, not65 enabled adapters. No accounts/tokens embedded in upstream were used.

Official Classplus web client index and main JS were fetched PUBLICLY, without
login/cookies. It confirms official API origin and x-access-token usage, but its
main bundle did not confirm our legacy student course schemas or entitlement
flags. One bounded NO-AUTH request to official /v2/courses returned401 JSON.
This establishes reachability/auth rejection, NOT working authenticated exports.

## Implemented, tested
- Guided /connect flow; private chat only; no passwords/OTPs/new account creation.
  AppX uses an explicitly approved host, actual user ID and own access token.
  Classplus uses only user's own existing token. Plain text is accepted over
  MTProto ONLY while that user's setup is active. Other text is ignored.
- Five-minute setup expiry, capacity bound, token-free wizard state; credential
  messages deleted best-effort. No secure-erasure promise, raw logging or copies.
- Full course list retained; eight buttons per page across ALL up to500 courses.
  Opaque per-user/per-provider expiring nonce; no sensitive callback data.
  Reconnect/provider switch/logout/cancel invalidates old pending choices.
- Selecting a course uses the existing queued job, re-fetches entitlement, and
  rechecks selected channel user/bot admin rights. Never deliver to arbitrary DM.
- AppX cross-provider connections rejected before any HTTP request/token send.
- Explicit protected flags recognized case-insensitively for BOTH adapters.
  Clear-looking URLs in explicitly protected rows are skipped, never decrypted.
- Known AppX partial pagination metadata fails closed instead of silently
  claiming complete output. Unknown schemas remain errors, never guessed.
- Secret-authenticated /ops/quiesce enables stop-first MTProto deployments.
  Refuses active jobs; stops workers and socket; clears RAM state; idempotent.
  This initial deployment requires a one-time TWO-DEPLOY safe bridge because old
  code lacks this route: first deploy with TELEGRAM_START_PAUSED=true (binds HTTP
  without opening Telegram); wait until old process is retired; final deployment
  with TELEGRAM_START_PAUSED=false. Suspend/resume does NOT apply changed env
  variables to old deployed snapshots, so that approach was stopped before any
  overlapping-session deployment. Never run one bot session from two machines at the same time.

204 synthetic regression tests PASS; production app pyflakes clean.
Two full synthetic flows run setup -> courses -> selected course -> entitlement
recheck -> queued traversal -> rights recheck -> selected-channel document.
These use synthetic accounts/responses/Telegram stubs, NOT live paid accounts.

## Remaining non-code requirements — DO NOT CLAIM FINISHED
APPX_API_HOSTS is still EMPTY in production. No particular coaching API has been
provided/independently approved. A third-party host directory or institute label
is NOT evidence that sending user credentials there is safe or authorized.
Classplus course/content schema and entitlement flags still require an actual
user-authorized account/contract or properly redacted response fixtures.
No real AppX/Classplus course export and channel-document round-trip was verified.
No paid accounts, shared tokens, OTP, decryption/key/signing bypass, or mystery
institute mappings were introduced to manufacture a success claim.

## Operational limits
Free Render idle/sleep remains. MTProto socket messages do not HTTP-wake a sleeping
instance. RAM setup/accounts/destinations/jobs reset on restart/deploy. Always-on
and permanent third-party API compatibility are NOT promised. No keep-awake hack.
New version is not evidence that these remaining live requirements disappeared.
