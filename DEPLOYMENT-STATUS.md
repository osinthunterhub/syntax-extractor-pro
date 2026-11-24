# Exact deployment result — credentials excluded

Public source: https://github.com/osinthunterhub/syntax-extractor-pro
User delegated automatic decision after Render could not fetch private repo.
Full reachable Git history scanned for supplied keys before publication.

NEW service: srv-dc2j83uc6qcc73f732fg — FREE plan, Singapore, Python3.12.12.
Dashboard: https://dashboard.render.com/web/srv-dc2j83uc6qcc73f732fg
HTTP: https://syntax-extract-pro.onrender.com
LIVE deploy: dep-dc2jce6k1f9s7386gbi0
Deployed code: 3760b1a345d7dd9eddf999d5e7994062b4b362bb
CI: https://github.com/osinthunterhub/syntax-extractor-pro/actions/runs/45344759182
Python3.12 and3.13 checks SUCCESS. Local86 tests PASS; production pyflakes clean.

BOT NOT ACTIVE: Telegram getMe returned429 after bounded retries; observed
TELEGRAM_RATE_LIMITED_RETRY_AFTER_32. Health reports ready=false,
identity_verified=false, webhook_configured=false. /readyz503.
Secretless webhook401 and authenticated-but-unready webhook503 verified.
No incoming updates acknowledged or workers started before identity verification.
Runtime SET_WEBHOOK=true is gated behind exact getMe username/is_bot validation;
no setWebhook was reached. Existing bots/services untouched.

Service remains running, not suspended, with no further in-process Telegram retry
loop. Cooldown then a controlled restart is needed to retry activation. Do not
repeat deployment/requests aggressively or claim Telegram is online.

AppX disabled pending authorized coaching API host. Classplus mock-tested, not
live-verified. No real provider extraction or channel-delivery test. Public user
access remains enabled by design; owner metadata stats runtime-configured.
RAM state resets on restart. No paid resource/card requirement accepted.
