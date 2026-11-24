# v0.5.0 — explicit bot-access consent, own-account QR and owner moderation

Scope ONLY @SyntaxExtractProBot. Existing @TurboForwarderPro_Bot, sessions and
checkpoints remain untouched. New per-user MemorySession only; no imported old,
personal or hosted bot StringSession. No phone/Telegram-OTP input through bot chat.
Classplus token/OTP authorization remains separate and unchanged.

## Implemented controls
- /start displays Telegram-supplied sender ID and basic bot-access consent.
  /accept opens own /dashboard. No second login needed for ordinary bot use.
- /linktelegram creates a private five-minute HTTPS fragment-bearer setup page.
  Explicit FULL Telegram-client authorization/operator-risk disclosure before QR.
  Only a scanning account matching the requesting Telegram sender ID is accepted;
  wrong account/bot authorization is rejected and revocation attempted.
- /tgstatus, /unlinktelegram, /logoutall; /cancel cancels a pending setup.
  Active own-account link expires in one hour; RAM-only and lost on restart.
  Cleanup every <=60 seconds attempts native logout/revocation. Crashes/network
  outages may prevent revocation: Telegram Settings > Devices is authoritative.
- /mychannels lists up to 200 own admin PUBLIC broadcast channels, ten per page;
  oversized results fail explicitly, never silently truncated. No inbox, history,
  arbitrary RPC, session download, account messaging or forwarding interface.
  Private channels are not enumerated; existing /setdestination remains available.
  Channel choice is bound to the requesting user, nonce and two-minute expiry.
  Selection uses existing bot+user channel-admin checks; exports remain BOT sends
  ONLY to the user's verified selected destination. No Saved Messages/log channel.
- Owner-only /admin: aggregate health, clickable user registry, block/unblock,
  paged user list, maintenance on/off. Also /users [zero-based page], /ban ID,
  /unban ID and /maintenance on|off. Actor authorization rechecked on callbacks.
  Banning cancels jobs/login and drops provider/new user-link state. Maintenance
  cancels pending login/link setups and exports; unlink/logout remain available.
  Owner cannot be banned and retains access when public registry is full.
  No credentials, phone numbers or sessions exposed in registry. No broadcast,
  permanent bans, arbitrary settings or universal admin powers are claimed.

## Session and portal safety
FULL Telegram user authorizations are NOT technically channel-scoped. Hosting
operator can access process memory; link only if deployment is trusted. Disclosure
appears BOTH in private bot panel and HTTPS portal before explicit consent.
Optional 2FA password is handled transiently by the HTTPS endpoint, never stored
in challenge fields/logged; three invalid attempts terminate setup. Server operator
still receives it transiently; this is not end-to-end or operator-proof secrecy.
QR waiter installed before QR display; QR expires <=60 seconds, no auto reissue.
Up to five flows/ten combined clients, invite cooldown 30 seconds, registry 2000
ordinary users plus owner. RAM quotas/moderation reset on restart/deploy.
Cancellation tracks in-flight connect/password tasks, not only QR waiter, to avoid
late authorization resurrection. Identity and flow lifetime rechecked on adoption.
Own linked identity rechecked before channel enumeration; no shared user session.
Portal bearer is 256-bit random, URL fragment removed from browser history and
sent in X-Link-Token POST header. Same-origin exact Origin validation, JSON-only,
CSP nonce/no third-party assets/no cookies/local storage/analytics, no-store,
no-referrer and frame-ancestors none. Request body cap and generic internal errors.
As with any bearer, do not share private link or QR. Telegram/cloud chat may retain
bot link messages; RAM-only does not erase Telegram's copies.

## Executed verification
355 offline synthetic regression tests pass locally (Python 3.13); app Pyflakes,
git diff whitespace and embedded portal JavaScript syntax checks pass. Dedicated
fake native QR/2FA tests cover consent-before-connect, own-ID/bot rejection,
success/unlink, no old-session import, two-step success/failure, capacity/expiry,
no inbox RPC, own-channel isolation, portal origin/header/feature/JSON rules,
owner denial/clickable moderation, full-registry owner access, maintenance races,
and cancellation during connect/password. Existing Classplus/export tests retained.
These tests do NOT authorize any real Telegram user account or send real SMS.
CI/deployment results recorded separately, only after actually observed.

## Explicitly NOT yet certified
No real user QR scan, 2FA acceptance, account channel enumeration or actual selected
channel delivery was performed in this release. Telegram readiness verifies only
the hosted bot identity/socket, NOT these user workflows. Real Classplus SMS/OTP,
valid-account courses/TXT/channel delivery also remain unverified. AppX disabled
without approved host. Free Render may sleep; no 24/7 or instant-response claim.
No payment/card/UPI, extra infrastructure, old-bot changes, or ZIP handoff.
