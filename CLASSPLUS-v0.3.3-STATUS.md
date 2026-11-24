# v0.3.3 — Classplus-first compatibility correction

User narrowed task to Classplus, AppX paused unchanged.
Reference https://github.com/princepiamotox/Extractor_Pro_x
Current/pinned HEAD f4ac41b2903242f99dd914b1e7db9a484bc9e0bb confirmed again.
Classplus source519 lines re-fetched, parsed without importing or executing;
request/header/response field usage compared to our adapter. No upstream accounts,
OTP/password login, shared requests-session state or log-channel copies reused.

## Concrete compatibility defect fixed
Our v0.3.2 wrongly REQUIRED isPurchased/isEnrolled on every course row. The
reference's account flow does not read those fields: it calls authenticated
/v2/courses?tabCategoryId=1 and reads data.courses[].id/name. Missing optional
fields could reject an otherwise reference-format course-list response.

Now that EXACT account route is parsed with id/name. Explicit provided purchase
or enrollment flags are respected; explicit locked/blocked/cannot-access courses
are excluded. Malformed provided access flags fail closed. Export re-fetches the
account list using the initiating user's token, rejects a pasted ID not present,
and uses only the same official content endpoint with that same user's token.
The API server remains authorization authority. Account-list membership is NOT
an independent purchase receipt or proof that all current production schemas
have been verified. No /store list, arbitrary account ID, copied token or access
bypass has been introduced. Header Api-Version29 is source-derived, not certified
as permanently current. No borrowed hardcoded device ID or app-account secrets.

## Other completed changes
/cp (or Classplus provider selection) starts private own-token setup if disconnected.
After successful account request, already-fetched courses appear immediately—no
extra /courses command/HTTP request required. Existing pagination/buttons remain.
No AppX coaching host/org-code mapping required for Classplus own-token workflow.
Known totalCount/hasMore pagination is checked for contradictions. Offset advances
by actual rows returned; never silently skips short pages or reports a known
incomplete list as finished. Course cap500 reports an error, never silent truncation.
Folder names retained in TXT titles. Explicit locked/blocked/inaccessible content,
DRM/encrypted flags and contentHashId-dependent rows skipped; no signing, keys,
partial URL encoding or decryption. Selected-channel-only delivery unchanged.

## Verification scope
235 synthetic regression tests PASS; production app Pyflakes clean.
Includes reference-format no-purchase-flags connect -> list -> select -> re-fetch
account membership -> folder traversal -> chosen-channel stub document delivery.
Includes denied/malformed flags, unknown IDs, pagination changes/contradictions,
per-user header isolation, locked/hash rows and private /cp startup.
One bounded ACTUAL HTTP call through our adapter with Api-Version29 and a
SYNTHETIC INVALID token returned CLASSPLUS_ACCESS_DENIED_RECONNECT as expected.
This checks network/error handling, NOT a successful real account/course export.

## Still unverified, not hidden
No user's real Classplus token has been supplied to this agent or tested here.
User can connect their OWN existing token ONLY in bot private chat, never in a
public message/support channel. Then the actual returned schema/course export can
be evaluated. Passwords/OTPs and borrowed tokens are not requested.
Live provider exports and actual chosen-channel document delivery remain untested.
The interactive reference Telegram bot itself has not been driven/logged into.
AppX remains disabled pending an approved coaching host (out of current scope).

## Hosting and safety
FREE Render, no payment/card changes. Existing forwarding bot untouched.
CI gate before deployment; authenticated /ops/quiesce stops the old socket first,
refuses active jobs, then new deployment may reuse the isolated SAME BOT session.
No local StringSession connection or bot reauthorization. Free idle/sleep and
RAM-only setup/account/destination/job reset limits still apply. No24/7 or permanent
third-party compatibility promise. No ZIP made or presented.
