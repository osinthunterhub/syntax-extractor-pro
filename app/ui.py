"""Stateless reference-inspired navigation. Catalog entries are NOT working adapters."""
from dataclasses import dataclass
import re

SUPPORT_URL = 'https://t.me/SyntaxError_2'
# Transcribed from the seven user-supplied reference screenshots. RWA appeared twice.
LOGIN_NAMES = tuple(dict.fromkeys([
    'Khan Sir', 'Exampur', 'Utkarsh', 'Classplus', 'Physics Wallah', 'KD Live',
    'Study IQ', 'Adda 247', 'Vision IAS', 'AppX V3', 'RG Vikram Jeet', 'ContentWork',
    'AppX V2', 'Abhinay Maths', 'RWA', 'Allen Live', 'Sarvam', 'Toppers Wing',
    'CDS Journey', 'Sahil Sir', 'Cadets Defence Academy', 'E1 Coaching', 'GVK Aksha',
    'Gyan Bindu', 'GK Cafe', 'ICS Coaching', 'Jobs Target', 'Kautilya APL',
    'Mawana Classes', 'MD Classes', 'Notebook', 'Parmar Academy', 'Phoenix Academy',
    'Prakash Sir Maths', 'RBE', 'RK Sir Office', 'SC MAGNET', 'SSC Gurukul',
    'Study Lab', 'Think SSC', 'TTGK', 'UC Live', 'The Winner Institute',
    'Yes Officer', 'Top Trending GK', 'Aasha Classes', 'Aman Sir English',
    'Dixit Sir', 'VMR Logics']))
PUBLIC_NAMES = (
    'Exampur', 'Awadh Ojha', 'Pinnacle', 'Quality Edu', 'Abhinay', 'Toppers Wing',
    'CopyRight', 'Selection Way', 'Study IQ', 'DAMS Delhi', 'Khan Sir 2',
    'FUTURE KUL', 'My Pathshala', 'Mind Map', 'Eduteria', 'Abhyam Academy')
PAGE_SIZE = 10

@dataclass(frozen=True)
class Panel:
    text: str
    rows: tuple


def button(text, data):
    return {'text': text, 'callback_data': data}


def navigation(back='home'):
    return (button('⬅️ Back', 'ui:' + back), button('🏠 Home', 'ui:home'))


def home_panel():
    return Panel('⚡ SYNTAX EXTRACTOR PRO\n━━━━━━━━━━━━━━━━━━━━\n'
        '\nApna account • Apna destination channel\n\n'
        '🔐 Classplus account access\n\n'
        '🌐 Public/free — availability and reference directory\n\n'
        '🧰 Tools — jobs, channel setup, privacy and help\n\n'
        'Development preview: provider APIs are live-unverified.\n'
        'No login-free premium access or DRM decryption.', (
        (button('👤 My dashboard', 'nav:dashboard'),),
        (button('🔐 Account access', 'ui:login'),),
        (button('🌐 Public / Free', 'ui:public'),),
        (button('🧰 Tools', 'ui:tools'), button('📋 Coverage', 'ui:coverage')),
        (button('💬 Support', 'ui:support'),)))


def login_panel():
    return Panel('🔐 ACCOUNT ACCESS\n━━━━━━━━━━━━━━━━━━━━\n'
        'Select a provider. Your AppX and Classplus sessions stay separate.\n\n'
        '🧪 Adapter code exists; real account verification is pending.\n'
        'AppX also needs an operator-approved coaching API host.\n'
        'Other institute names are a research directory, not working integrations.', (
        (button('🔷 AppX', 'provider:appx'), button('🟣 Classplus', 'provider:classplus')),
        (button('📋 Institute research directory', 'ui:catalog:login:0'),),
        navigation()))


def public_panel():
    return Panel('🌐 PUBLIC / FREE CONTENT\n━━━━━━━━━━━━━━━━━━━━\n'
        'No public-content sources are connected yet.\n\n'
        'Only legitimately public/free sources can be supported here.\n'
        'No shared account tokens, premium access without entitlement, or protected-media decryption.\n\n'
        'Reference names below are unverified catalog entries, not downloadable courses.', (
        (button('📋 Reference names (unverified)', 'ui:catalog:public:0'),),
        (button('🔐 Use my own account', 'ui:login'),), navigation()))


def catalog_panel(kind, page):
    if kind not in ('login', 'public') or not isinstance(page, int) or isinstance(page, bool):
        raise ValueError('INVALID_PANEL')
    names = LOGIN_NAMES if kind == 'login' else PUBLIC_NAMES
    pages = (len(names) + PAGE_SIZE - 1) // PAGE_SIZE
    if not 0 <= page < pages:
        raise ValueError('INVALID_PANEL_PAGE')
    entries = []
    for index in range(page * PAGE_SIZE, min(len(names), (page + 1) * PAGE_SIZE)):
        name = names[index]
        if kind == 'login' and name == 'Classplus':
            entries.append(button('🧪 ' + name, 'provider:classplus'))
        else:
            entries.append(button('⏳ ' + name, f'ui:item:{kind}:{index}'))
    rows = [tuple(entries[i:i+2]) for i in range(0, len(entries), 2)]
    paging = []
    if page:
        paging.append(button('⬅️ Previous', f'ui:catalog:{kind}:{page-1}'))
    if page + 1 < pages:
        paging.append(button('Next ➡️', f'ui:catalog:{kind}:{page+1}'))
    if paging:
        rows.append(tuple(paging))
    rows.append(navigation('login' if kind == 'login' else 'public'))
    return Panel(f'📋 REFERENCE DIRECTORY • {page+1}/{pages}\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '⏳ Research pending — NOT connected\n'
        '🧪 Adapter exists — live verification pending\n\n'
        'Names come from your screenshots. A listing is not proof of working extraction.\n'
        'Provider family, host, schema and authorization are not guessed.', tuple(rows))


def item_panel(kind, index):
    names = LOGIN_NAMES if kind == 'login' else PUBLIC_NAMES if kind == 'public' else ()
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(names):
        raise ValueError('INVALID_CATALOG_ITEM')
    return Panel(f'⏳ {names[index]}\n━━━━━━━━━━━━━━━━━━━━\n'
        'Status: reference catalog only; extraction unavailable.\n\n'
        'No verified provider mapping/API contract or authorized account fixture is configured.\n'
        'No password/token is requested for this entry.\n'
        'AppX V2/V3 labels do not imply version parity with our generic AppX adapter.', (
        (button('⬅️ Return to directory', f'ui:catalog:{kind}:{index//PAGE_SIZE}'),),
        (button('💬 Ask support', 'ui:support'), button('🏠 Home', 'ui:home'))))


def provider_panel(provider, configured, connected):
    if provider not in ('appx', 'classplus'):
        raise ValueError('INVALID_PROVIDER')
    title = 'AppX' if provider == 'appx' else 'Classplus'
    hint = '/connect appx API_HOST USER_ID TOKEN' if provider == 'appx' else 'Tap Connect my account below, or /connect classplus. Your existing own token is enough; no AppX coaching host/org mapping is required.'
    readiness = ('Operator setup pending: no approved coaching API host configured.'
                 if provider == 'appx' and not configured else 'Adapter mock-tested; real provider verification pending.')
    return Panel(f'{title} selected. Your other provider session is unchanged.\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        f'Account: {"connected" if connected else "not connected"}\n{readiness}\n\n'
        f'{hint}\n\n'
        'Use your own token in private chat only. Never share passwords.\n'
        'Export: /setdestination @YourChannel → /export COURSE_ID', (
        (button('🔑 Connect my account', 'nav:cplogin' if provider == 'classplus' else 'nav:connect'),),
        (button('📚 My courses', 'nav:courses'), button('📤 Destination', 'nav:destination')),
        (button('📊 Job status', 'nav:status'), button('✖️ Cancel job', 'action:cancel')),
        (button('🚪 Logout selected account', 'action:disconnect'),),
        navigation('login')))


def tools_panel():
    return Panel('🧰 TOOLS & CONTROLS\n━━━━━━━━━━━━━━━━━━━━\n'
        'Your own jobs, account controls and selected destination.\n'
        'TXT/HTML converters and media downloads are not implemented.', (
        (button('📊 Job status', 'nav:status'), button('✖️ Cancel job', 'action:cancel')),
        (button('📤 My destination', 'nav:destination'), button('🪜 Export guide', 'ui:guide')),
        (button('🛡️ Privacy', 'ui:privacy'), button('📋 Capabilities', 'ui:coverage')),
        (button('🚪 Logout all my accounts', 'action:logoutall'),), navigation()))


def guide_panel():
    return Panel('🪜 EXPORT GUIDE\n━━━━━━━━━━━━━━━━━━━━\n'
        '1. Add this bot to your channel as admin with Post Messages permission.\n'
        '2. You must also be the channel creator/admin.\n'
        '3. /setdestination @YourChannel (or numeric channel ID).\n'
        '4. Classplus: /cplogin → own token OR org code + own mobile + provider OTP.\n\n'
        '5. /courses then /export COURSE_ID.\n'
        '6. /status or /cancel.\n\n'
        'TXT goes ONLY to your selected verified channel. No silent DM fallback.\n'
        'AppX needs an approved host. Both providers remain live-unverified.\n'
        'Restart loses sessions, jobs and channel settings.', (navigation('tools'),))


def privacy_panel():
    return Panel('🛡️ PRIVACY & LIMITS\n━━━━━━━━━━━━━━━━━━━━\n'
        '• Provider login: own token or Classplus OTP; no provider passwords/shared accounts.\n\n'
        '• Sessions isolated by user and provider; RAM-only, one-hour connection TTL.\n'
        '• Login-message deletion is best-effort, not secure erasure.\n\n'
        '• OTP setup: own phone/challenge in RAM; 5-minute step expiry, periodic cleanup.\n'
        '• No raw OTP/token logs. SMS requires explicit confirmation; no auto-resend.\n'
        '• Jobs retain a token snapshot until stopped.\n'
        '• No raw token logs, log-channel copies or central export archive.\n'
        '• Signed URLs are sensitive; share only with permission.\n'
        '• Optional /linktelegram creates a FULL Telegram authorization, not channel-only permissions. Trust the server operator before linking.\n'
        '• QR/2FA uses the private HTTPS portal only. Operator can access server sessions and processes 2FA transiently. Never send Telegram codes/passwords in bot chat.\n'
        '• Telegram links are RAM-only for one hour; crash/network logout can fail. Revoke in Telegram Settings → Devices.\n'
        '• Bot-access registry and owner moderation are RAM-only and reset on restart.\n'
        '• /disconnect selected provider; /logoutall provider accounts + extra Telegram link.\n'
        '• /cleardestination forgets channel and requests job cancellation.', (navigation('tools'),))


def coverage_panel():
    return Panel('📋 HONEST CAPABILITY STATUS\n━━━━━━━━━━━━━━━━━━━━\n'
        '🧪 AppX: folder/flat clear-link TXT adapter; host setup + live verification pending.\n'
        '🧪 Classplus: own-token folder adapter; entitlement schema live-unverified.\n'
        '✅ Local logic: separate accounts, channel checks, queue, cancel/progress and navigation.\n'
        '⏳ Other institutes/public sources: catalog only, no adapters enabled.\n'
        '🧪 Classplus OTP: org/mobile/OTP flow implemented; real account verification pending.\n\n'
        '🧪 Optional Telegram QR/2FA + own public admin channels: implemented; real login unverified.\n\n'
        '❌ Not included: DRM decryption, login-free premium, provider-password login, general Telegram media relay, DB/resume.\n\n'
        'No A–Z parity or speed claim. Mock tests are not live integration certification.', (
        (button('🔐 Account access', 'ui:login'), button('🌐 Public / Free', 'ui:public')),
        navigation('tools')))


def support_panel():
    return Panel('💬 SUPPORT\n━━━━━━━━━━━━━━━━━━━━\n'
        'Contact @SyntaxError_2.\n'
        'Send provider/app name, safe error code and redacted screenshots.\n'
        'Never send passwords, OTPs or access tokens to support.\n'
        'Your selected export channel is separate from support.', (
        ({'text': '💬 Contact owner', 'url': SUPPORT_URL},), navigation()))


def callback_command(data):
    """Strict bounded callback language; no eval, arbitrary commands or pasted credentials."""
    if not isinstance(data, str) or len(data) > 64 or not data.isascii():
        return None
    commands = {'provider:appx': '/appx', 'provider:classplus': '/classplus',
        'nav:dashboard': '/dashboard', 'nav:admin': '/admin', 'nav:stats': '/stats', 'nav:health': '/health',
        'nav:cplogin': '/cplogin', 'nav:refreshcourses': '/refreshcourses',
        'auth:token': '/cptoken', 'auth:otp': '/cpotp', 'auth:sendotp': '/sendotp',
        'nav:connect': '/connect', 'nav:courses': '/courses', 'nav:destination': '/destination', 'nav:status': '/status',
        'nav:help': '/help', 'action:cancel': '/cancel', 'action:disconnect': '/disconnect',
        'action:logoutall': '/logoutall'}
    commands.update({'access:accept': '/accept', 'nav:linktelegram': '/linktelegram',
        'nav:tgstatus': '/tgstatus', 'nav:mychannels': '/mychannels',
        'action:unlinktelegram': '/unlinktelegram', 'nav:users': '/users',
        'nav:maintenance': '/maintenance', 'admin:maintenance:on': '/maintenance on',
        'admin:maintenance:off': '/maintenance off'})
    match_admin = re.fullmatch(r'admin:(ban|unban|users):([0-9]{1,16})', data)
    if match_admin:
        return '/' + match_admin[1] + ' ' + match_admin[2]
    match_link = re.fullmatch(r'tgchan:([a-f0-9]{8}):(\d{1,3})', data)
    if match_link:
        return '/usechannel ' + match_link[1] + ' ' + match_link[2]
    match_link = re.fullmatch(r'tgpage:([a-f0-9]{8}):(\d{1,2})', data)
    if match_link:
        return '/channelpage ' + match_link[1] + ' ' + match_link[2]
    if data in commands:
        return commands[data]
    match = re.fullmatch(r'coursepage:([a-f0-9]{8}):(\d{1,2})', data)
    if match:
        return '/coursepage ' + match[1] + ' ' + match[2]
    match = re.fullmatch(r'course:([a-f0-9]{8}):(\d{1,3})', data)
    if match:
        return '/choose ' + match[1] + ' ' + match[2]
    if data in {'ui:'+key for key in ('home','login','public','tools','support','guide','privacy','coverage')}:
        return '/panel ' + data[3:]
    match = re.fullmatch(r'ui:(catalog|item):(login|public):(\d{1,2})', data)
    if match:
        action, kind, number = match.groups(); number = int(number)
        names = LOGIN_NAMES if kind == 'login' else PUBLIC_NAMES
        bound = (len(names)+PAGE_SIZE-1)//PAGE_SIZE if action == 'catalog' else len(names)
        if number < bound:
            return f'/panel {action} {kind} {number}'
    return None


def render_panel(args):
    static = {'home':home_panel,'login':login_panel,'public':public_panel,'tools':tools_panel,
              'support':support_panel,'guide':guide_panel,'privacy':privacy_panel,'coverage':coverage_panel}
    if len(args) == 1 and args[0] in static:
        return static[args[0]]()
    if len(args) == 3 and args[0] in ('catalog','item') and re.fullmatch(r'\d{1,2}', args[2]):
        return (catalog_panel if args[0]=='catalog' else item_panel)(args[1],int(args[2]))
    raise ValueError('INVALID_PANEL')


def classplus_login_panel():
    return Panel('🟣 CLASSPLUS • LOGIN\n━━━━━━━━━━━━━━━━━━━━\n\n'
        'Choose how to connect YOUR existing account.\n\n'
        '🔑 Token — use your own existing access token.\n\n'
        '📱 Mobile + OTP — institute org code, your Indian mobile number, then Classplus OTP. SMS is sent only after confirmation.\n\n'
        'No Telegram login codes, passwords, borrowed accounts or automatic registration.\n'
        'Credentials deleted best-effort; login/session state is RAM-only.', (
        (button('🔑 Use my token', 'auth:token'),),
        (button('📱 Org code + mobile + OTP', 'auth:otp'),),
        (button('✖️ Cancel setup', 'action:cancel'), button('🏠 Home', 'ui:home'))))


def dashboard_panel(selected, accounts, destination, job, login_stage, owner=False):
    text = ('👤 MY DASHBOARD\n━━━━━━━━━━━━━━━━━━━━\n\n'
        f'Provider: {selected}\n\n'
        f'Accounts\n{accounts}\n\n'
        f'Export destination\n{destination}\n\n'
        f'Job\n{job}\n\n'
        f'Login setup\n{login_stage}\n\n'
        'Only YOUR account, channel and jobs appear here. Settings reset after restart.')
    rows = [(button('🟣 Classplus login', 'nav:cplogin'),),
        (button('📚 My courses', 'nav:courses'), button('🔄 Refresh courses', 'nav:refreshcourses')),
        (button('📤 Destination', 'nav:destination'), button('📊 Job status', 'nav:status')),
        (button('✖️ Cancel job / setup', 'action:cancel'),),
        (button('🚪 Logout selected', 'action:disconnect'), button('🚪 Logout all mine', 'action:logoutall'))]
    if owner:
        rows.append((button('🛠 Owner admin', 'nav:admin'),))
    rows.append(navigation())
    return Panel(text, tuple(rows))


def owner_panel(summary):
    return Panel('🛠 OWNER ADMIN\n━━━━━━━━━━━━━━━━━━━━\n\n' + summary + '\n\n'
        'Read-only operations panel. No user tokens, phone numbers or OTPs displayed.\n'
        'User exports still require their own selected channel.', (
        (button('📈 Refresh statistics', 'nav:stats'), button('🩺 Health', 'nav:health')),
        (button('👤 My dashboard', 'nav:dashboard'),), navigation()))


def login_error(code):
    hints = {
        'CLASSPLUS_OTP_INVALID_OR_EXPIRED': 'Classplus did not accept this OTP. Recheck the CLASSPLUS code; at most 3 provider attempts. If expired, restart /cpotp after cooldown or use /cptoken.',
        'CLASSPLUS_LOGIN_EXPIRED_OR_CANCELLED': 'Login setup expired or was cancelled. Restart /cplogin. No automatic SMS resend.',
        'CLASSPLUS_AUTH_NETWORK_ERROR_NO_AUTORETRY': 'Provider/network request failed. An SMS may already have been requested; no automatic retry. Wait before restarting or use /cptoken.',
        'CLASSPLUS_OTP_COOLDOWN_WAIT_60_SECONDS': 'Wait at least 60 seconds before another SMS request. Cancel/restart does not bypass cooldown.',
        'CLASSPLUS_OTP_DAILY_LIMIT_USE_TOKEN_OR_WAIT': 'Local SMS request limit reached. Use your own existing token via /cptoken or wait. Limits are RAM-only and provider limits may be stricter.',
        'CLASSPLUS_REGISTRATION_REQUIRED_USE_OFFICIAL_APP': 'Complete account signup/profile in the official Classplus/institute app first. This bot will not invent an email or auto-register.',
        'CLASSPLUS_OWN_INDIAN_MOBILE_REQUIRED': 'Send your OWN 10-digit Indian number, or +91 followed by it. No OTP has been sent by this input.',
        'CLASSPLUS_ORG_CODE_FORMAT_INVALID': 'Send only your institute org code, not a URL or phone number. /cancel exits.',
        'CLASSPLUS_OTP_FORMAT_4_TO_8_DIGITS': 'Send the 4–8 digit CLASSPLUS account OTP only. Never send a Telegram login code.',
        'CLASSPLUS_OTP_CONFIRM_NUMBER_FIRST_NO_AUTORESEND': 'Confirm your own number first using Send OTP. After a request is accepted, enter that OTP; the button will not resend it.',
        'CLASSPLUS_AUTH_REQUEST_REJECTED': 'Classplus rejected this login request. Check org code/account in the official app, or use /cptoken. No automatic retry or registration.',
        'CLASSPLUS_AUTH_BUSY_TRY_LATER': 'Login request capacity is busy. Try again later; /cptoken is the existing-token option.',
        'LOGIN_CANCELLED_NO_SESSION_SAVED': 'That login was cancelled. No resulting connection/course cache was saved.',
    }
    return ('⚠️ LOGIN HELP\n\n' + hints[code] + '\n\nCode: ' + code) if code in hints else code


def access_panel(uid):
    return Panel('👤 BOT ACCESS • TELEGRAM IDENTITY\n━━━━━━━━━━━━━━━━━━━━\n\n'
        f'Telegram supplied your sender ID: {uid}\n\n'
        'You are already signed into Telegram to open this bot. No Telegram phone/OTP/password is needed for basic bot access.\n\n'
        'Accept to use your own provider accounts, jobs and selected channel. Those settings are held on this server in RAM. Extra Telegram account authorization is OPTIONAL and separate, only for account-level channel controls.\n\n'
        'Read /privacy first if needed. No other user gets your private controls.', (
        (button('✅ Accept & open my dashboard', 'access:accept'),),
        (button('🛡 Privacy', 'ui:privacy'),)))
