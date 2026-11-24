# Deployment handoff — no secrets

Bot target: @SyntaxExtractProBot. Bot API identity not verified yet: sandbox
requests encountered Telegram 429 retry-after responses and timeouts.
Startup getMe identity check remains mandatory before any webhook registration.

Private repository: https://github.com/osinthunterhub/syntax-extractor-pro
Initial commit: a46ed4ffd6da9cdd94218cb1a3b6a466c26248b5
CI: https://github.com/osinthunterhub/syntax-extractor-pro/actions/runs/45343096784
Python 3.12 and 3.13 jobs both SUCCESS; local suite 74 PASS.

Render credentials authenticated. Existing services untouched. A NEW free
Singapore web service request was rejected HTTP 400: private repository
unfetchable. No new service ID/deploy exists. No paid request attempted.
Next: allow Render GitHub app access to only syntax-extractor-pro, or obtain
user permission to publish secret-free code repository publicly.
https://github.com/apps/render/installations/new
https://dashboard.render.com/u/settings#account-security

Planned service name syntax-extract-pro; region Singapore; free plan only;
start python -m app; health /healthz. Use actual assigned HTTPS URL, not an
assumed hostname, for PUBLIC_BASE_URL. SET_WEBHOOK false until identity verified.
APPX_API_HOSTS empty intentionally disables AppX until coaching host approved.
All ordinary users allowed; owner-only metadata stats configured at runtime.
No live provider extraction or channel delivery has been tested.
