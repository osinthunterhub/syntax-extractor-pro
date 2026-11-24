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
        'Apna account • Apna destination channel\n\n'
        '🔐 Account access — AppX / Classplus\n'
        '🌐 Public/free — availability and reference directory\n'
        '🧰 Tools — jobs, channel setup, privacy and help\n\n'
        'Development preview: provider APIs are live-unverified.\n'
        'No login-free premium access or DRM decryption.', (
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
        (button('🔑 Connect my account', 'nav:connect'),),
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
        '4. Choose AppX or Classplus; connect your own account token.\n'
        '5. /courses then /export COURSE_ID.\n'
        '6. /status or /cancel.\n\n'
        'TXT goes ONLY to your selected verified channel. No silent DM fallback.\n'
        'AppX needs an approved host. Both providers remain live-unverified.\n'
        'Restart loses sessions, jobs and channel settings.', (navigation('tools'),))


def privacy_panel():
    return Panel('🛡️ PRIVACY & LIMITS\n━━━━━━━━━━━━━━━━━━━━\n'
        '• Own-token connections; no passwords or shared accounts.\n'
        '• Sessions isolated by user and provider; RAM-only, one-hour connection TTL.\n'
        '• Connect-message deletion is best-effort, not secure erasure.\n'
        '• Jobs retain a token snapshot until stopped.\n'
        '• No raw token logs, log-channel copies or central export archive.\n'
        '• Signed URLs are sensitive; share only with permission.\n'
        '• /disconnect selected account; /logoutall both accounts.\n'
        '• /cleardestination forgets channel and requests job cancellation.', (navigation('tools'),))


def coverage_panel():
    return Panel('📋 HONEST CAPABILITY STATUS\n━━━━━━━━━━━━━━━━━━━━\n'
        '🧪 AppX: folder/flat clear-link TXT adapter; host setup + live verification pending.\n'
        '🧪 Classplus: own-token folder adapter; entitlement schema live-unverified.\n'
        '✅ Local logic: separate accounts, channel checks, queue, cancel/progress and navigation.\n'
        '⏳ Other institutes/public sources: catalog only, no adapters enabled.\n'
        '❌ Not included: DRM decryption, login-free premium, OTP/password login, general Telegram media relay, DB/resume.\n\n'
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
        'nav:connect': '/connect', 'nav:courses': '/courses', 'nav:destination': '/destination', 'nav:status': '/status',
        'nav:help': '/help', 'action:cancel': '/cancel', 'action:disconnect': '/disconnect',
        'action:logoutall': '/logoutall'}
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
