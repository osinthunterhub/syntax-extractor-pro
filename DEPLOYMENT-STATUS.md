# v0.5.0 — Telegram own-account linking and owner access controls LIVE

Bot: https://t.me/SyntaxExtractProBot (9049794072).
Scope ONLY this extractor. Old forwarding bot and its authorizations untouched.
Deployed source: c6bd5e2dbe31d540d6bfe550190a148527b07a99
Render deploy: dep-dc2lncbrjlhs73d40ir0 — LIVE. FREE / Singapore; auto-deploy OFF.
CI: 45367396594 — both Python3.12 and3.13 SUCCESS. Local356 synthetic tests PASS.
Hosted /readyz200; bot identity verified, MTProto socket ready, updates configured.
Feature flags checked live: Telegram account link + bot-access consent + Classplus
OTP/token + owner/user panels enabled. Owner8841527686 unchanged; AppX disabled.
Authenticated stop-first handoff confirmed before deploying; old socket disconnected
and no active jobs. No hosted bot StringSession connected from local tools.

## What changed
/start -> basic Telegram sender-ID consent -> own /dashboard. No extra Telegram
login required for ordinary bot access. Optional /linktelegram opens private HTTPS
FULL-session risk consent + native QR + optional two-step password. New RAM-only
MemorySession per consenting user, own sender ID required, one-hour link lifetime.
No old/personal/bot session imported. /tgstatus /mychannels /unlinktelegram and
/logoutall implemented. /mychannels lists OWN public admin broadcast channels;
selection still verifies user+BOT channel rights before exporting only there.
Private channels not enumerated; /setdestination remains the manual target option.

Owner /admin -> paged user registry, block/unblock buttons, maintenance controls;
/users /ban /unban /maintenance commands also implemented. No credential viewing,
no general Telegram account RPC/inbox/forwarding interface or session export.
Bans/settings/links/quotas are RAM-only and reset on restart/deployment.
Classplus own-token + own-mobile/OTP workflow is separate and retained.
See TELEGRAM-LINK-v0.5.0-STATUS.md for exact limits/security/test scope.

## Actual hosted portal checks
GET /account-link200; full-session disclosure, CSP nonce, no-store, no-referrer,
frame-ancestors none / X-Frame-Options DENY. Missing/wrong Origin403; missing/invalid
link bearer400. These probes do NOT create an account link or authorize a user.
355 initial offline cases plus privacy disclosure regression =356 tests; fake
QR/2FA/login/authorization/race/channel clients only. Pyflakes+JS syntax+diff clean.

## Explicit verification limits
No actual user QR scan, Telegram two-step password acceptance, public-channel
account enumeration or real chosen-channel TXT delivery has been performed.
Classplus real valid-account SMS/OTP/course extraction/delivery remains UNVERIFIED.
Hosted readiness and fake tests must not be described as those end-to-end proofs.
Telegram user linking is FULL authorization: server operator can access sessions
and transient 2FA. Use only a trusted deployment. Revoke the NEW authorization in
Telegram Settings > Devices; crashes/network outages may prevent automatic revoke.
RAM-only does not erase copies retained by Telegram. Free hosting can sleep;
no24/7 or instant-provider guarantee. No paid changes or ZIP handoff.
