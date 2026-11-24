# Current release: v0.5.0 — own Telegram QR linking and owner access controls

`/start` → explicit bot-access consent → own `/dashboard`. Additional account login
is OPTIONAL: `/linktelegram` → private HTTPS risk-consent + QR/2FA → `/mychannels`.
`/tgstatus`, `/unlinktelegram`, `/logoutall`; full Telegram authorization, not
channel-scoped permission. Only link if you trust the hosting operator. One-hour
RAM-only sessions; Telegram Settings → Devices can revoke the new authorization.
Owner `/admin` now has user block/unblock and maintenance controls; RAM-only.
Old forwarding bot/session untouched. Classplus token+OTP remains separate.

356 offline synthetic tests pass. Actual QR/2FA/account-channel workflows and real
Classplus SMS/OTP/course export remain live-unverified. See
TELEGRAM-LINK-v0.5.0-STATUS.md for concrete scope, safety and limits. Free hosting
can sleep; AppX remains disabled. Deployment evidence recorded separately.

--- Historical release notes, superseded by the current report where different ---

# Current release: v0.4.0 — Classplus token + own-account OTP

User dashboard `/dashboard`; login options `/cplogin`; arranged guide `/help`.
OTP is for an existing CLASSPLUS account, NEVER Telegram. Explicit confirmation
before SMS; no automatic resend/registration. Own token option remains available.
Owner `/admin` is read-only aggregate operations; other users see only their own
account/channel/jobs. Public access does not grant global owner privileges.

319 synthetic tests pass; real valid-account OTP/course export/channel delivery
remain live-unverified. AppX still disabled/no approved host. FREE hosting can
sleep; this is not an always-on or instant-provider/SMS guarantee. See
LOGIN-DASHBOARD-v0.4.0-STATUS.md for scope, safety limits and verification evidence.

--- Earlier release documentation (superseded where current report differs) ---

# Independent Extractor — v0.3.1-dev

**Separate new project. AppX + Classplus adapters. 159 local/mock tests. Telegram bot active through official bot-only MTProto,
not a claim of A–Z parity, real provider compatibility or fastest performance.**

The existing `@TurboForwarderPro_Bot`, its credentials, sessions, settings and hosting
are out of scope and untouched. This code refuses that bot username. No old-account
credentials are bundled or automatically reused. The default Bot API transport needs no API ID/hash. The optional deployed MTProto
bot transport uses the user-provided API ID/hash plus a NEW bot-only session, never
a personal account or phone-number login.

## What's implemented and tested locally

- Separate `app/adapters/appx.py` and `app/adapters/classplus.py`, shared safe interfaces.
- Separate immutable `(Telegram user ID, provider)` connections; switching provider
  leaves the other connection intact. No global authentication headers or cookies.
- AppX token + actual account user ID: account course list; folder and flat
  subject/topic metadata walkers; clear HTTPS-link TXT export.
- Classplus own-token adapter: account course list, explicit purchased/enrolled marker
  check, folder traversal, bounded/defensive pagination; clear HTTPS-link TXT export.
- **Classplus's `isPurchased` / `isEnrolled` and pagination schemas are assumed from
  reference-informed mock fixtures, NOT official verified contracts.** If missing,
  the adapter fails closed with an explicit unsupported-schema error. It may require
  legitimate redacted fixture/schema changes before working for a real account.
- Both recheck course entitlement before traversal. No fixed provider accounts,
  protected access bypass, DRM/key retrieval, decryption or media downloading.
- Separate AppX/Classplus inline menus + organized Telegram command registration.
- Each user explicitly selects their own destination channel. Verify bot admin/post
  permission, then user admin/creator permission; recheck before every delivery.
- Export job snapshots destination; changed/removed/revoked destinations block delivery.
  **No silent fallback to bot DM, Saved Messages or operator/log channel.** Progress
  and error notices still appear privately. This is export-file delivery, not a new
  general-purpose Telegram source-message/user-session forwarding engine.
- One worker, three waiting jobs, one active job per user across both providers;
  whole-job 180-second deadline, progress/cancel, bounded HTTP/traversal/output.
- Default provider connection concurrency is three; shared connector limit six.
  Walkers remain sequential. No real speed/throughput benchmark has been run.
- Private-only account operations, best-effort connect-message deletion, no password
  collection, no raw credential logs, no central output copies.
- TLS verification, public-only DNS resolution, exact allowed origins, no redirects,
  response limits, no aggressive 429 retry loops. Clear-URL filter is not a playback
  guarantee, a rights certification or a promise that all HTTPS URLs are accessible.
- Owner-only metadata `/stats` (disabled when OWNER_ID=0). Ordinary use is not owner-only.
- HTTP health endpoint, secret-authenticated webhook, bounded intake/dedup, safe errors,
  startup/shutdown cleanup and bot identity check before webhook modification.

## Commands

```
/start                         Open menu
/appx                          Select AppX
/classplus                     Select Classplus (alias /cp)
/connect appx HOST USERID TOKEN Connect your own AppX token/account ID
/connect classplus TOKEN       Connect your own Classplus token
/courses                       List selected account's courses
/setdestination @YourChannel   Verify/select your channel (or numeric -100... ID)
/destination                   Show your channel
/export COURSE_ID              Queue selected provider's supported TXT export
/status                        Check your current job
/cancel                        Request cancellation
/disconnect                    Logout selected provider and cancel your job
/logoutall                     Logout both providers and cancel your job
/cleardestination              Forget channel and cancel your job
/help                          Show help/limitations
/stats                         Owner-only runtime counts; not a public admin command
```

No command accepts passwords. Do not put tokens in groups. Deletion is best-effort;
Telegram clients/history may retain copies. Signed URLs in TXT files are sensitive.
Do not share files publicly unless you have permission to distribute the content.

## Important limits / not yet production

**Public source repository: osinthunterhub/syntax-extractor-pro. New FREE Render service created; Telegram identity and MTProto transport now verified; HTTP webhook intentionally disabled.**
No real provider login, OTP, Telegram bot integration or course export was performed.
The API protocols are reference-informed, not verified with provider developer docs.
Search did not establish an authoritative public Classplus/AppX purchased-course API
contract; unrelated similarly named products' docs were NOT used as verification.

RAM-only sessions/destinations/queue/dedup; restart loses settings and jobs and requires
reconnect/reselecting the channel. Already-acknowledged webhook updates can be lost
on a process crash. No durable resume is implemented. Connection validity TTL is one
hour, checked on access and minute housekeeping; job snapshots survive until stopped.
Python strings cannot be securely zeroed. Last consumed updates/completed job references
are cleared when workers idle, but this is not a memory-erasure guarantee.

Maximum 250 connection records across providers (not 250 simultaneous exports), 250
conversation metadata slots, 32 queued incoming updates, 2 MiB HTTP provider responses,
2 MiB output / 5,000 links / 120 folders or topics / depth 12. A full/ambiguous/unsupported
response fails explicitly, not as “complete success”. AppX listing has a 500-course cap;
Classplus pagination stops at limits or unknown metadata. No universal provider coverage.

Cancellation is cooperative. In-flight network operations can finish before the next
check; if Telegram already accepted a file, cancellation cannot retract that delivery.
There is no retry of a possibly accepted upload. Exported metadata does not guarantee
playable video or authorization to redistribute it.

## Reference-feature coverage

See `REFERENCE-FEATURE-MATRIX.csv` and `RESEARCH-NOTES.md`.
TXT/HTML converters, API catalog/discovery, password/OTP flows, premium administration,
broadcasts, durable storage/resume and additional providers are **not implemented yet**.
The fixed-key “only our bot can decrypt” claim, embedded/shared-token login-free access,
bulk credential checking and eval/shell admin surfaces are deliberately not reproduced.
Licensed/authorized public-free content can be considered separately; “without login”
UI is not evidence of authorization.

## Local checks

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

159 tests pass under local Python 3.13. Production module Pyflakes check is clean.
GitHub CI passed for Python 3.12 + 3.13 (130-test revision, run 45350989017).
Render Python 3.12.12 build and HTTP liveness/auth/readiness were verified.
Telegram identity and provider APIs remain unverified. `TEST-RESULTS.txt` records actual local
results. All provider requests are mocked; local webhook HTTP tests run only locally.

## Zero-cost deployment configuration — Free service created

- New repository only. Upload extracted contents at repository root; never `.env`.
- New Telegram bot only. Put secrets in the NEW Render service environment, not chat,
  source, README, CI logs or the old forwarding project's configuration.
- New Render Python **Web Service**, **Free** plan. No paid worker/database/disk.
  If payment/card verification is demanded, stop; no charge is authorized.
- Build: `pip install -r requirements.txt`; start: `python -m app`.
- `.python-version`: 3.12.12; bind `0.0.0.0:$PORT`; health path `/healthz`.
- Configure `.env.example` variables: BOT_TOKEN, EXPECTED_BOT_USERNAME,
  WEBHOOK_SECRET (32–128 URL-safe random characters), PUBLIC_BASE_URL (new HTTPS
  origin), APPX_API_HOSTS (explicit bare DNS allowlist), optional NEW OWNER_ID.
- SET_WEBHOOK=false initially. When identity/origin is verified, set true and redeploy
  to register webhook + commands on that NEW bot. Startup first calls getMe and refuses
  an identity mismatch. No old webhook/session reset is authorized.
- Generate a webhook secret locally:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Run a scoped authorized AppX smoke test, then Classplus schema/entitlement/pagination
  checks and two-user/channel-permission tests before describing anything as live-ready.

Render Free docs: https://render.com/docs/free
15-minute idle spin-down, cold starts, ephemeral filesystem, 750 free instance-hours
per workspace/month, usage quotas and high outbound-traffic suspension risks apply.
Render says Free is for hobby/testing, not production. No self-ping/quota-evasion hack
is included. Separate services isolate workloads; they do not prevent suspension.

## Licensing / provenance

Newly written adapter/core code; no upstream source or exposed account credentials
bundled. Reference snapshot is GPL-3.0. If upstream implementation is later copied,
review its license obligations before distributing combined code. Endpoint names and
mock fixture assumptions are documented as unverified rather than vendor-endorsed.

## Syntax deployment configuration
Name: Syntax Extractor Pro. Expected new identity: @SyntaxExtractProBot.
An empty APPX_API_HOSTS now starts safely with AppX disabled; its menu reports setup
pending until an authorized coaching host is approved. No wildcard or guessed host.
Owner is configured only in runtime environment; ordinary user access remains open.
Provider live verification remains pending.

Startup getMe retries Telegram 429 at most three attempts, honoring retry_after
(up to 120 seconds); sending messages/files is never automatically retried.
Full Git history was scanned for supplied secrets before publication.

Liveness /healthz binds before background Telegram identity verification.
It reports ready/identity_verified/webhook_configured separately; /readyz is503
until bootstrap succeeds. Unready webhook returns503 without acknowledging updates.
At most three startup getMe attempts, then stop until next process startup: no
crash-loop retry. A live Render web service does not mean an active Telegram bot.

## Previous v0.2.1 deployment result (history)
Code commit3760b1a345d7dd9eddf999d5e7994062b4b362bb deployed successfully to
https://syntax-extract-pro.onrender.com on Render Free (Singapore).
Health200 is process-only. Bot startup stopped after bounded Telegram429 retries:
ready=false, identity_verified=false, webhook_configured=false. /readyz503,
unauthenticated webhook401, authenticated-unready webhook503 verified remotely.
No further in-process retry loop. After external cooldown, one controlled restart
will retry identity/bootstrap; no guarantee that Telegram accepts it.
See DEPLOYMENT-STATUS.md for actual service/deploy/CI IDs.

## v0.3 reference-inspired navigation upgrade

- Home, Account Access, Public/Free availability, Tools, Support, Guide, Privacy,
  Capabilities; `/xtract` and `/home` are home aliases.
- AppX/Classplus selection, course/channel/status/cancel/logout controls preserved.
- Callback panels edit the same message; expired edit can create one fresh panel.
  Ambiguous network failures and429 are never retried as another send.
- Five login-directory pages with49 distinct screenshot labels (RWA deduplicated),
  two public-directory pages with16 labels. **These are research catalog entries,
  NOT65 working providers.** Classplus has an existing mock-tested adapter; the
  other named institute/version entries request no credentials and export nothing.
- No guessed provider mappings, hosts or login-free premium/unlock features.
- Support links to the user's supplied public handle @SyntaxError_2. It is NOT an
  export destination. User-selected destination delivery remains separate.
-159 local/mock tests; Python3.12/3.13 CI passed. Web service deployed; Telegram activation blocked.

Reference public profile https://t.me/pro_extractorbot was fetched. Its interactive
bot was NOT driven or authenticated into. Menu content came from the user's seven
screenshots, not a claim of end-to-end reference-function verification. No copied
branding/banner, embedded credentials or protected media API calls are included.

## Verified v0.3 release result
Deployed code `6dd558d2545faabcb89f955a816bda49c358bbc3`; Render deploy `dep-dc2k3b3ncjis73d7cqbg` is LIVE
(web process only), Free plan verified. CI run `45350989017`: Python3.12 and3.13
both SUCCESS,130 local tests PASS.
Telegram startup still ends TELEGRAM_RATE_LIMITED_RETRY_AFTER_32:
ready=false, identity_verified=false, webhook_configured=false, /readyz503.
No Telegram-online claim; startup retries stopped. Provider exports still live-unverified.

## v0.3.1 optional official MTProto bot transport

Cloud Bot API cold-login symptoms match community reports in upstream issues:
https://github.com/tdlib/telegram-bot-api/issues/1103
https://github.com/tdlib/telegram-bot-api/issues/1110
These are incident reports, not a maintainer-confirmed explanation for every bot.
A bounded isolated test successfully verified THIS new bot directly on its working
DC via official MTProto; no personal account/phone/OTP or old session was used.

`TELEGRAM_TRANSPORT=mtproto` uses an explicitly provisioned, secret BOT-ONLY
StringSession, Telegram API ID/hash and the existing new bot token. Startup validates
both bot username/is_bot and token's numeric bot ID before any commands/handlers.
Session/API credentials are never committed, returned in health or logged. Invalid,
wrong-bot or personal sessions fail closed. No arbitrary RPC interface is exposed.

New adapter maps existing menu editing, commands, callback acknowledgements, TXT
uploads and channel/admin checks to the SAME bot's official MTProto methods.
Readiness requires identity + active transport + installed incoming handlers.
`webhook_configured=false` is intentional in MTProto mode; `updates_configured=true`
identifies its inbound transport. HTTP webhook intake is disabled to avoid duplicates.

**Run one instance only. Do not run local and hosted clients concurrently with the
same session. Future MTProto deployments must use stop-first handoff to prevent
simultaneous session use on different IPs.** Do not regenerate or log out the session
as an attempted outage fix. Reconnection uses this bot's saved authorization only.
No general user-account chat access or media-forwarding engine has been added.

Public @channel targets resolve normally; private numeric IDs require Telegram to
have supplied the entity/access-hash in this process. An unresolved channel fails
explicitly; no guessed hash or DM fallback. Use the channel username when available.
Incoming updates are RAM/bounded/best-effort; overflow may require resending a command.
Optional OWNER_READY_NOTICE sends only to the configured owner after matching the
public support handle to its numeric ID; inability to initiate a private chat does
not falsely mark the bot unusable. Default false to avoid repeated startup notices.

159 local tests pass, including transport-to-worker command/callback integration,
wrong/personal-session rejection, live-socket readiness, permission checks, numeric
ID normalization and overload/dedup. Real provider exports remain live-unverified.

## LIVE v0.3.1 result
Telegram connection is ready, identity verified, incoming handlers installed.
Official bot-only MTProto; HTTP webhook=false is intentional.
Deployed code `f32a7042c28be757113b670546d70245f3d1d2af`; deploy `dep-dc2kcaec6qcc73fa44r0`.
CI 45353541407: Python3.12 and3.13 SUCCESS;159 local tests PASS.
Observed actual incoming updates and successful outgoing Telegram operations,
not just a liveness check or mocked test. Provider exports remain unverified.

**Free-host limitation:** Render can idle/suspend Free web services. In MTProto
mode an incoming Telegram socket message does NOT make an HTTP request to wake a
sleeping Render instance. This workaround is therefore not an always-on guarantee.
No self-ping/quota-evasion service is included. Prefer restoring Bot API webhook
mode (after verifying cloud recovery) for webhook-triggered wake-up.

## v0.3.2 guided-provider upgrade
Choose provider -> **Connect my account** -> follow private prompts. Own existing
tokens only, no password/OTP. `/connect appx` or `/connect classplus` starts setup;
`/cancel` exits. Five-minute expiry. AppX fails safely before asking for credentials
when no approved coaching host exists. `/courses` includes paged selection buttons
for the full returned course list. Selection binds to your own current provider,
expires in5 minutes, and rechecks entitlement and selected channel rights.

204 synthetic tests pass (including both provider->channel mock workflows).
This is not authenticated live provider certification. See PROVIDER-UPGRADE-v0.3.2.md
for exact review scope, completed changes and remaining required live inputs.

### Subsequent MTProto deployment handoff
Keep Render auto-deploy OFF. Wait for CI and no active jobs. POST `/ops/quiesce`
with the private webhook-secret header (same name as webhook auth); verify503
readiness and quiesced=true BEFORE starting new version. This disconnects the old
socket without logOut, blocks updates, clears volatile user state. If deployment
fails, an explicitly controlled restart/rollback is needed; quiesced old process
will not reconnect itself. NEVER run the bot StringSession in local diagnostics
while hosting is active. Never expose the secret header in logs or public URLs.

Maintenance bootstrap uses TELEGRAM_START_PAUSED=true only for a temporary
HTTP-only staged deployment. Final production must deploy with false so ordinary
restarts do not require manual activation. Saved env edits alone do not change
Render existing deployment snapshots.

## v0.3.3 Classplus-first correction (supersedes missing-flag blocker above)
Send `/cp` in private chat to start own-existing-token setup. Successful connection
immediately presents account courses. The reference's exact authenticated My Courses
route no longer incorrectly requires undocumented per-row purchase flags; explicit
denials and server authentication still apply. Same-user account-list membership
is re-fetched on every export; no arbitrary-ID/store-catalog workflow. Api-Version29
matches the pinned reference. This is source-compatible code, NOT a claim that a
real user's live account/course/channel export was verified. See CLASSPLUS-v0.3.3-STATUS.md.
235 synthetic regression tests pass. AppX untouched/out of this focused release.
