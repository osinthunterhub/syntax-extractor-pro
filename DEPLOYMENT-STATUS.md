# Deployment status (no secrets)

Public https://github.com/osinthunterhub/syntax-extractor-pro
NEW FREE Render service srv-dc2j83uc6qcc73f732fg; Singapore; Python3.12.12.
https://syntax-extract-pro.onrender.com
Initial build succeeded; startup rejected by Telegram. Bounded retry patch
dep-dc2j9rbrjlhs73ctgt30 also failed: TELEGRAM_RATE_LIMITED_RETRY_AFTER_32.
Service paused to prevent restart-driven Telegram requests.

Readiness patch separates /healthz liveness and /readyz readiness. Identity and
webhook flags are explicit. Startup attempts are bounded; unready intake503,
no updates acknowledged, no identity bypass. Deployment verification pending.
SET_WEBHOOK will be enabled only for this NEW service; getMe exact-name gate
still runs before any setWebhook. Ordinary users allowed; owner stats private.
AppX disabled until approved coaching API host provided. No provider/channel
verification. No old services modified; no paid resource selected.

CI run45344075591:82-test revision passed Python3.12+3.13; new86-test CI pending.
