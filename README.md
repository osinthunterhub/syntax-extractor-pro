# Independent Extractor — v0.2.1-dev

**Separate new project. AppX + Classplus adapters. 86 local/mock tests. Not deployed,
not a claim of A–Z parity, real provider compatibility or fastest performance.**

The existing `@TurboForwarderPro_Bot`, its credentials, sessions, settings and hosting
are out of scope and untouched. This code refuses that bot username. No old-account
credentials are bundled or automatically reused. This Bot API design does not need
Telegram API ID/hash or a phone-number login.

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

**Public source repository: osinthunterhub/syntax-extractor-pro. New FREE Render service created; Telegram startup identity verification pending; no webhook changed.**
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

86 tests pass under local Python 3.13. Production module Pyflakes check is clean.
GitHub CI passed for Python 3.12 + 3.13 (run 45343096784). Python 3.12 hosted deployment runtime,
Render build and live APIs remain unverified. `TEST-RESULTS.txt` records actual local
results. All provider requests are mocked; local webhook HTTP tests run only locally.

## Zero-cost deployment template — Render access pending

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
