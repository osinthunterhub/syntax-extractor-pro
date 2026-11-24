# v0.3.1 activation attempt — no secrets
New bot-only MTProto authorization successfully verified matching new bot identity
on its working DC5. Bot API still times out/429; upstream community issue reports
match symptoms. Official MTProto is an alternate legitimate bot transport, not a
provider paid-access bypass and not a personal-user login.
159 local tests pass; production pyflakes clean. CI and hosting activation for this
revision pending at commit. Only NEW Render service will be changed; FREE plan only.
No old sessions or services touched. No ZIP is being presented or requested.
