# Syntax Extractor Pro v0.3.2 — TELEGRAM LIVE; PROVIDERS NOT LIVE-CERTIFIED

Bot https://t.me/SyntaxExtractProBot , exact bot ID9049794072.
Repo https://github.com/osinthunterhub/syntax-extractor-pro
Deployed source 7d6a873f12231a9bf6cfcc2d26ea39394e485900
Final deploy dep-dc2kt3e7bikc73909ipg LIVE, FREE Singapore. Auto-deploy OFF.
CI 45358523496: Python3.12 and3.13 SUCCESS;204 synthetic regression tests.
Live /readyz200: identity verified, handlers installed, official bot-only MTProto.
HTTP webhook=false intentional. No personal-user/phone/OTP login or old bot/session.

## Completed in this release
Guided private setup, own tokens, five-minute wizard expiry, best-effort deletion;
full paged course-selection callbacks bound to user/provider/expiry; rechecks at
job execution; protected flags case-insensitive; AppX known partial pages fail
closed; cross-provider token sending blocked; selected-channel-only outputs.
Both full provider->channel flows exercised with synthetic accounts/HTTP/TG stubs.
Secret-authenticated /ops/quiesce for future controlled stop-first updates.

## Actual live scope, not extrapolation
Previous v0.3.1 deployment observed real incoming commands/replies. New v0.3.2
identity/socket/handler readiness now verified. That does not establish live
AppX/Classplus course listing, provider traversal or channel document delivery.
AppX still disabled: no approved coaching API host. Public vendor marketing site
was checked, but provides no authenticated course contract. RWA official site
rendered publicly via page tool; direct HTML/script research got403, NOT bypassed.
No API host was guessed from image CDN or untrusted third-party host directory.
Classplus official fixed endpoint returned401 JSON without a token; real
account/course entitlement schemas remain unverified. No support for protected
key/decryption/signing access; no shared-account credentials copied from reference.
49 login +16 public screenshot labels remain research catalog, NOT65 providers.
Reference every-line repository/interactive bot audit remains incomplete.

## Deployment safety evidence
Suspend/resume initially retained old deployment env snapshot, so that attempted
bridge was STOPPED before any new MTProto deployment. Corrected transition:
1. Deploy same revision TELEGRAM_START_PAUSED=true: health200, NO Telegram connect.
2. Verified old deployment deactivated; waited60seconds for process retirement.
3. Final deploy same code TELEGRAM_START_PAUSED=false; identity/handlers READY.
Only one process could use the live bot session. No local StringSession reuse.
Final saved env explicitly verified unpaused/MTProto, owner notice=false.
For future runtime deploys, wait for idle, authenticate /ops/quiesce, verify
quiesced503, then deploy. Do not blindly run either old scratch activation script.

## Limits
Free Render sleeps; MTProto messages do NOT HTTP-wake a sleeping instance.
No24/7/permanent third-party compatibility promise or keep-awake hack.
RAM-only accounts, wizard, destination, queue reset on restarts. User must set
his chosen channel again after this deployment; no fallback to DM/support/logs.
All ordinary users allowed; owner-only admin stats. No paid changes. No ZIP made.
