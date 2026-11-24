import asyncio
import hmac
import logging
import re
import time
from contextlib import asynccontextmanager
from aiohttp import web
import aiohttp
from .config import Config
from .state import State, Connection
from .providers import AppX, Classplus, ProviderRouter, ProviderError, PublicResolver
from .destinations import Destinations
from .jobs import Jobs
from .telegram import Telegram, verified_identity
from .ui import callback_command, render_panel, provider_panel, Panel, button
from .conversation import Conversations
from .classplus_auth import ClassplusLogin
from .ui import classplus_login_panel, dashboard_panel, owner_panel, login_error

HELP = """⚡ SYNTAX EXTRACTOR PRO
━━━━━━━━━━━━━━━━━━━━

👤 HOME & ACCOUNT
/start — home
/dashboard — your accounts, channel and jobs
/login — provider access panel
/cp or /cplogin — Classplus login options
/cptoken — connect your own existing token
/cpotp — Classplus org code + own mobile + OTP
/connect — guided existing-token setup

📚 COURSES & EXPORT
/courses — account courses (20-second display cache)
/refreshcourses — reload courses from provider
/setdestination @YourChannel — verify user + bot admin rights
/destination — your selected channel
/export COURSE_ID — queue clear-link TXT to that channel only

⚙️ CONTROL & PRIVACY
/status — your job
/cancel — cancel your job/login setup
/disconnect — forget selected provider account
/logoutall — forget both your provider accounts
/cleardestination — forget channel and cancel job
/health — bot and provider availability

🧭 HELP
/tools | /guide | /privacy | /capabilities | /support
/free — public-source availability (none connected yet)
/help — this arranged guide

🛠 OWNER
/admin or /stats — owner-only read-only operations panel

Classplus OTP requires explicit SMS confirmation; never send a Telegram code.
No passwords, shared accounts, automatic registration or DRM bypass.
RAM-only settings reset on restart. Secret-message deletion is best-effort.
Real provider-account exports remain live-unverified. AppX needs an approved host.
"""

COMMANDS = [
    ('start', 'Home'), ('dashboard', 'Your accounts, channel and jobs'),
    ('login', 'Provider account access'), ('cplogin', 'Classplus login options'),
    ('cptoken', 'Classplus: use your own token'), ('cpotp', 'Classplus: org code + mobile + OTP'),
    ('classplus', 'Open Classplus'), ('connect', 'Guided own-token setup'),
    ('courses', 'Your account courses'), ('refreshcourses', 'Refresh account courses from provider'),
    ('setdestination', 'Verify your export channel'), ('destination', 'Your selected channel'),
    ('export', 'Export course TXT to selected channel'),
    ('status', 'Your current job'), ('cancel', 'Cancel your job or login setup'),
    ('disconnect', 'Forget selected provider account'), ('logoutall', 'Forget all your accounts'),
    ('cleardestination', 'Forget channel and cancel job'), ('health', 'Bot and provider availability'),
    ('tools', 'Account and job controls'), ('guide', 'Step-by-step guide'),
    ('privacy', 'Privacy and session limits'), ('capabilities', 'Honest feature availability'),
    ('support', 'Safe support contact'), ('free', 'Public-source availability'),
    ('appx', 'AppX setup/status'), ('help', 'Arranged command guide'),
    ('admin', 'Owner-only read-only admin panel'), ('stats', 'Owner-only operations statistics')]


def published_commands(config):
    return [(name, description) for name, description in COMMANDS
            if name not in ('admin', 'stats')
            and (name != 'appx' or config.appx_hosts)
            and (name != 'cpotp' or config.classplus_otp_enabled)]


class Bot:
    def __init__(self, config, tg, provider, bot_id=0):
        self.config, self.tg = config, tg
        self.router = ProviderRouter(provider if isinstance(provider, dict) else {'appx': provider})
        self.state = State()
        self.selected = {}
        self.conversations = Conversations()
        self.classplus_login = ClassplusLogin(getattr(self.router.providers.get('classplus'), 'session', None))
        self.course_cache, self.revisions, self.lock_refs = {}, {}, {}
        self.destinations = Destinations(tg, bot_id)
        self.updates = asyncio.Queue(maxsize=32)
        self.fast_updates = asyncio.Queue(maxsize=16)
        self.locks, self.last, self.workers = {}, {}, []
        self.jobs = Jobs(self.router, self.deliver, self.notify)

    async def deliver(self, job, result):
        destination = await self.destinations.check_delivery(job.user_id, job.destination)
        if job.cancelled.is_set():
            raise ProviderError('JOB_CANCELLED')
        # No silent fallback to DM/log channel if selected channel cannot receive output.
        await self.tg.document(destination, job.id, result, provider=job.connection.provider)
        await self.tg.send(job.chat_id, f'Delivered {result.count} clear links to your selected channel. Skipped: {result.skipped}.')

    async def notify(self, job, text):
        await self.tg.send(job.chat_id, text)

    async def menu(self, chat, text):
        if hasattr(self.tg, 'menu'):
            await self.tg.menu(chat, text)
        else:
            await self.tg.send(chat, text)

    async def delete_input(self, chat, message_id):
        try:
            await asyncio.wait_for(self.tg.delete(chat, message_id), 2)
        except (ProviderError, asyncio.TimeoutError):
            pass  # best-effort deletion must not hold every login behind a 35s RPC

    async def show_panel(self, chat, panel, message_id=None):
        if hasattr(self.tg, 'panel'):
            await self.tg.panel(chat, panel.text, panel.rows, message_id)
        else:
            await self.menu(chat, panel.text)

    async def show_course_page(self, uid, cid, provider, nonce, page, message_id=None):
        courses, pages = self.conversations.page(uid, provider, nonce, page)
        rows = [(button(c.name[:48], f'course:{nonce}:{page * 8 + i}'),) for i, c in enumerate(courses)]
        nav = []
        if page:
            nav.append(button('⬅️ Previous', f'coursepage:{nonce}:{page - 1}'))
        if page + 1 < pages:
            nav.append(button('Next ➡️', f'coursepage:{nonce}:{page + 1}'))
        if nav:
            rows.append(tuple(nav))
        body = '\n\n'.join(f'{page * 8 + i + 1}. {c.name}\nID: {c.id}' for i, c in enumerate(courses))
        await self.show_panel(cid, Panel(f'📚 {provider.upper()} • COURSES {page + 1}/{pages}\n━━━━━━━━━━━━━━━━━━━━\n\n{body}\n\nTap a course to export, or /export COURSE_ID.\nChoices expire in 5 minutes. Account membership and channel rights are rechecked.', tuple(rows)), message_id)

    async def present_courses(self, uid, cid, selected, courses):
        if not courses:
            self.conversations.choices.pop(uid, None)
            await self.tg.send(cid, 'No courses returned by your account.')
            return
        nonce = self.conversations.course_page(uid, selected, courses)
        await self.show_course_page(uid, cid, selected, nonce, 0)

    def queue_for(self, update):
        item = update.get('message') or {}
        text = item.get('text', '')
        callback = update.get('callback_query')
        if isinstance(callback, dict):
            text = callback_command(callback.get('data')) or ''
        cmd = text.split()[0].split('@')[0].lower() if isinstance(text, str) and text.split() else ''
        return self.fast_updates if cmd in {'/cancel', '/disconnect', '/logoutall', '/dashboard', '/admin', '/stats', '/health', '/status'} else self.updates

    @asynccontextmanager
    async def user_lock(self, uid):
        if uid not in self.locks and len(self.locks) >= 250:
            raise ProviderError('USER_CAPACITY_REACHED_TRY_LATER')
        lock = self.locks.setdefault(uid, asyncio.Lock())
        self.lock_refs[uid] = self.lock_refs.get(uid, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self.lock_refs[uid] -= 1
            if not self.lock_refs[uid]:
                self.lock_refs.pop(uid, None)
                self.locks.pop(uid, None)

    def clear_login(self, uid):
        self.revisions[uid] = self.revisions.get(uid, 0) + 1
        self.classplus_login.cancel(uid)
        self.conversations.clear(uid)
        for key in list(self.course_cache):
            if key[0] == uid:
                self.course_cache.pop(key, None)

    async def finish_login(self, uid, cid, connection, otp_verified=False):
        revision = self.revisions.get(uid, 0)
        await self.tg.send(cid, '⏳ Checking your provider account…\n\nNo automatic retry. /cancel stops this login. Provider response time can vary.')
        if revision != self.revisions.get(uid, 0):
            raise ProviderError('LOGIN_CANCELLED_NO_SESSION_SAVED')
        try:
            courses = await asyncio.wait_for(self.router.adapter(connection.provider).courses(connection), 35)
        except (asyncio.TimeoutError, ProviderError) as exc:
            if revision != self.revisions.get(uid, 0):
                raise ProviderError('LOGIN_CANCELLED_NO_SESSION_SAVED') from None
            if otp_verified:
                self.state.put(uid, connection)
                self.selected[uid] = connection.provider
                code = str(exc) if isinstance(exc, ProviderError) else 'PROVIDER_TIMEOUT_TRY_LATER_NO_AUTORETRY'
                await self.tg.send(cid, '✅ Classplus OTP verified; your account connection is saved in RAM.\n\nCourse listing could not complete. Try /refreshcourses without requesting another OTP.\n\n' + code)
                return
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError('LOGIN_TIMEOUT_TRY_LATER_NO_AUTORETRY') from None
        if revision != self.revisions.get(uid, 0):
            raise ProviderError('LOGIN_CANCELLED_NO_SESSION_SAVED')
        self.state.put(uid, connection)
        self.selected[uid] = connection.provider
        self.course_cache[(uid, connection.provider)] = (time.monotonic() + 20, connection, courses)
        await self.tg.send(cid, f'✅ {connection.provider.upper()} CONNECTED\n\n{len(courses)} account courses returned.\nToken/OTP not logged. Sessions are private and RAM-only.')
        if connection.provider == 'classplus':
            await self.present_courses(uid, cid, connection.provider, courses)

    async def auth_result(self, uid, cid, result):
        if result.token:
            if uid in self.jobs.active:
                raise ProviderError('CANCEL_EXISTING_JOB_BEFORE_RECONNECT')
            await self.finish_login(uid, cid, Connection('api.classplusapp.com', 'self', result.token, 'classplus'), otp_verified=True)
        elif result.confirm:
            await self.show_panel(cid, Panel(result.prompt, ((button('📨 Send OTP to MY number', 'auth:sendotp'),), (button('✖️ Cancel', 'action:cancel'),))))
        else:
            await self.tg.send(cid, result.prompt)

    async def local_control(self, uid, cid, cmd, message_id=None):
        selected = self.selected.get(uid, 'classplus' if self.config.classplus_otp_enabled else 'appx')
        if cmd in ('/cancel', '/disconnect', '/logoutall'):
            had_setup = uid in self.classplus_login.pending or uid in self.conversations.steps
            self.clear_login(uid)
            cancelled = self.jobs.cancel(uid)
            if cmd != '/cancel':
                self.state.drop(uid, None if cmd == '/logoutall' else selected)
                text = 'Connection forgotten; cancellation requested. In-flight requests stop at deadline.'
            else:
                text = 'Cancellation requested.' if cancelled or had_setup else 'No active job.'
            await self.tg.send(cid, text)
        elif cmd == '/status':
            job = self.jobs.active.get(uid)
            await self.tg.send(cid, f'Job {job.id} ({job.connection.provider}): queued/running; cancel={job.cancelled.is_set()}' if job else 'No active job.')
        elif cmd == '/dashboard':
            accounts = '\n'.join(f'• {p}: ' + ('connected' if self.state.get(uid, p) else 'not connected') for p in ('classplus', 'appx'))
            dest = self.destinations.values.get(uid)
            job = self.jobs.active.get(uid)
            setup = self.classplus_login.pending.get(uid) or self.conversations.steps.get(uid)
            await self.show_panel(cid, dashboard_panel(selected, accounts, f'{dest.title} ({dest.chat_id})' if dest else 'Not set — /setdestination @YourChannel', f'{job.connection.provider}: queued/running' if job else 'No active job', setup.stage if setup else 'Not active', bool(self.config.owner_id and uid == self.config.owner_id)), message_id)
        elif cmd in ('/admin', '/stats'):
            if not self.config.owner_id or uid != self.config.owner_id:
                raise ProviderError('OWNER_ONLY')
            self.state.purge()
            summary = (f'Connected account sessions: {len(self.state.connections)}\n\n'
                f'Active/queued exports: {len(self.jobs.active)}\nWaiting: {self.jobs.queue.qsize()}\n\n'
                f'Classplus OTP setups: {len(self.classplus_login.pending)}\n'
                f'Provider accounts live-certified: no\nDurable jobs: no\n\n'
                f'Update queues: {self.updates.qsize()} regular / {self.fast_updates.qsize()} control')
            await self.show_panel(cid, owner_panel(summary), message_id)
        elif cmd == '/health':
            connected = bool(getattr(self.tg, 'connected', True))
            await self.tg.send(cid, '🩺 BOT HEALTH\n\nVersion: 0.4.0-dev\nTelegram socket: ' + ('connected' if connected else 'disconnected') + '\n\nClassplus token: enabled\nClassplus OTP: ' + ('enabled; real account verification pending' if self.config.classplus_otp_enabled else 'disabled') + '\nAppX: ' + ('configured; live-unverified' if self.config.appx_hosts else 'disabled; host pending') + '\n\nFree hosting can sleep. Provider/SMS latency is external. Settings are RAM-only.')
        else:
            return False
        return True

    async def handle(self, update):
        callback = update.get('callback_query')
        if isinstance(callback, dict):
            qid = callback.get('id')
            if isinstance(qid, str) and len(qid) <= 256:
                try:
                    await asyncio.wait_for(self.tg.call('answerCallbackQuery', {'callback_query_id': qid}), 2)
                except (ProviderError, asyncio.TimeoutError):
                    pass  # expired/rate-limited acknowledgement must not drop a local cancel action
            command = callback_command(callback.get('data'))
            original = callback.get('message')
            if not command or not isinstance(original, dict):
                return
            message = {'from': callback.get('from', {}), 'chat': original.get('chat', {}),
                       'message_id': original.get('message_id'), 'text': command}
        else:
            message = update.get('message')
        if not isinstance(message, dict):
            return
        sender, chat = message.get('from', {}), message.get('chat', {})
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            return
        uid, cid = sender.get('id'), chat.get('id')
        if not isinstance(uid, int) or isinstance(uid, bool) or not isinstance(cid, int) or sender.get('is_bot'):
            return
        text = message.get('text', '')
        already_deleted = False
        if not isinstance(text, str) or not text.strip():
            return
        if not text.startswith('/'):
            if chat.get('type') != 'private' or uid != cid or not (uid in self.conversations.steps or uid in self.classplus_login.pending):
                return
            await self.delete_input(cid, message.get('message_id'))
            already_deleted = True
            if uid in self.classplus_login.pending:
                text = '/authinput ' + text
            else:
                try:
                    text, prompt = self.conversations.accept(uid, text, self.config.appx_hosts)
                    if prompt:
                        await self.tg.send(cid, prompt)
                        return
                except ProviderError as exc:
                    await self.tg.send(cid, login_error(str(exc)))
                    return
        parts = text.split()
        cmd = parts[0].split('@')[0].lower()
        panel_message_id = message.get('message_id') if isinstance(callback, dict) else None
        if chat.get('type') != 'private' or uid != cid:
            if cmd in ('/connect', '/authinput') and not already_deleted and not isinstance(callback, dict):
                await self.delete_input(cid, message.get('message_id'))
            await self.tg.send(cid, 'For account security, use this bot in private chat only.')
            return
        if cmd in ('/connect', '/authinput') and not already_deleted and not isinstance(callback, dict):
            await self.delete_input(cid, message.get('message_id'))
        try:
            if await self.local_control(uid, cid, cmd, panel_message_id):
                return
        except ProviderError as exc:
            await self.tg.send(cid, login_error(str(exc)))
            return
        if uid not in self.locks and len(self.locks) >= 250:
            await self.tg.send(cid, 'USER_CAPACITY_REACHED_TRY_LATER')
            return
        async with self.user_lock(uid):
            now = time.monotonic()
            cheap = {'/start', '/home', '/xtract', '/help', '/appx', '/classplus', '/cp', '/cancel', '/disconnect', '/logoutall', '/status', '/destination', '/cleardestination', '/panel', '/login', '/free', '/tools', '/support', '/guide', '/privacy', '/capabilities', '/coursepage', '/cplogin', '/cptoken', '/cpotp', '/sendotp', '/authinput'}
            selected = self.selected.get(uid, 'classplus' if self.config.classplus_otp_enabled else 'appx')
            cached = self.course_cache.get((uid, selected))
            is_cached_courses = cmd == '/courses' and cached and cached[0] > now and cached[1] is self.state.get(uid, selected)
            is_setup_prompt = cmd == '/connect' and (len(parts) == 1 or len(parts) == 2 and parts[1].lower() in ('appx', 'classplus'))
            if cmd not in cheap and not is_setup_prompt and not is_cached_courses and now - self.last.get(uid, 0) < 2:
                await self.tg.send(cid, 'Please wait two seconds between API commands.')
                return
            if cmd not in cheap and not is_setup_prompt and not is_cached_courses:
                self.last[uid] = now
            selected = self.selected.get(uid, 'classplus' if self.config.classplus_otp_enabled else 'appx')
            if cmd == '/choose':
                try:
                    if len(parts) != 3 or not parts[2].isdigit():
                        raise ProviderError('INVALID_COURSE_SELECTION')
                    parts = ['/export', self.conversations.choose(uid, selected, parts[1], int(parts[2]))]
                    cmd = '/export'
                except ProviderError as exc:
                    await self.tg.send(cid, login_error(str(exc)))
                    return
            try:
                if cmd in ('/start', '/home', '/xtract', '/login', '/free', '/tools', '/support', '/guide', '/privacy', '/capabilities', '/panel'):
                    aliases = {'/start':'home','/home':'home','/xtract':'home','/login':'login','/free':'public','/tools':'tools',
                               '/support':'support','/guide':'guide','/privacy':'privacy','/capabilities':'coverage'}
                    try:
                        panel = render_panel(parts[1:] if cmd == '/panel' else [aliases[cmd]])
                    except ValueError:
                        raise ProviderError('INVALID_MENU_SELECTION_USE_START') from None
                    if cmd == '/login' and not self.config.appx_hosts:
                        rows = tuple(tuple(b for b in row if b.get('callback_data') != 'provider:appx') for row in panel.rows)
                        panel = Panel(panel.text, tuple(row for row in rows if row))
                    if cmd in ('/start', '/home', '/xtract') and self.config.owner_id and uid == self.config.owner_id:
                        panel = Panel(panel.text, panel.rows + ((button('🛠 Owner admin', 'nav:admin'),),))
                    await self.show_panel(cid, panel, panel_message_id)
                elif cmd in ('/cplogin', '/cptoken', '/cpotp', '/sendotp', '/authinput'):
                    if uid in self.jobs.active:
                        raise ProviderError('CANCEL_EXISTING_JOB_BEFORE_RECONNECT')
                    self.selected[uid] = 'classplus'
                    if cmd == '/cplogin':
                        self.clear_login(uid)
                        if self.config.classplus_otp_enabled:
                            await self.show_panel(cid, classplus_login_panel(), panel_message_id)
                        else:
                            await self.tg.send(cid, self.conversations.begin(uid, 'classplus', self.config.appx_hosts))
                    elif cmd == '/cptoken':
                        self.clear_login(uid)
                        await self.tg.send(cid, self.conversations.begin(uid, 'classplus', self.config.appx_hosts))
                    else:
                        if not self.config.classplus_otp_enabled:
                            raise ProviderError('CLASSPLUS_OTP_DISABLED_USE_CPTOKEN')
                        if cmd == '/cpotp':
                            self.clear_login(uid)
                            await self.auth_result(uid, cid, self.classplus_login.begin(uid))
                        elif cmd == '/sendotp':
                            await self.auth_result(uid, cid, await self.classplus_login.send(uid))
                        else:
                            await self.auth_result(uid, cid, await self.classplus_login.input(uid, text.partition(' ')[2]))
                elif cmd == '/coursepage':
                    if len(parts) != 3 or not re.fullmatch(r'[a-f0-9]{8}', parts[1]) or not re.fullmatch(r'\d{1,2}', parts[2]):
                        raise ProviderError('INVALID_COURSE_PAGE')
                    await self.show_course_page(uid, cid, selected, parts[1], int(parts[2]), panel_message_id)
                elif cmd == '/help':
                    await self.menu(cid, HELP)
                elif cmd in ('/appx', '/classplus', '/cp'):
                    selected = 'appx' if cmd == '/appx' else 'classplus'
                    self.clear_login(uid)
                    self.selected[uid] = selected
                    connected = self.state.get(uid, selected) is not None
                    panel = provider_panel(selected, bool(self.config.appx_hosts), connected)
                    if selected == 'classplus' and not connected and uid not in self.jobs.active and self.config.classplus_otp_enabled:
                        await self.show_panel(cid, classplus_login_panel(), panel_message_id)
                    else:
                        await self.show_panel(cid, panel, panel_message_id)
                        if selected == 'classplus' and not connected and uid not in self.jobs.active:
                            prompt = self.conversations.begin(uid, selected, self.config.appx_hosts)
                            await self.tg.send(cid, prompt)
                elif cmd == '/connect':
                    self.classplus_login.cancel(uid)
                    args = parts[1:]
                    if not args or len(args) == 1 and args[0].lower() in ('appx', 'classplus'):
                        if args:
                            selected = args[0].lower()
                        if uid in self.jobs.active:
                            raise ProviderError('CANCEL_EXISTING_JOB_BEFORE_RECONNECT')
                        self.selected[uid] = selected
                        prompt = self.conversations.begin(uid, selected, self.config.appx_hosts)
                        await self.tg.send(cid, prompt)
                        return
                    self.clear_login(uid)
                    if args and args[0].lower() in ('appx', 'classplus'):
                        selected, args = args[0].lower(), args[1:]
                    if selected == 'appx' and len(args) == 3:
                        host, account, token = args
                        host = host.lower()
                        if host not in self.config.appx_hosts:
                            raise ProviderError('API_HOST_NOT_CONFIGURED_BY_OPERATOR')
                        if not re.fullmatch(r'\d{1,20}', account):
                            raise ProviderError('ACTUAL_ACCOUNT_USER_ID_REQUIRED')
                    elif selected == 'classplus' and len(args) == 1:
                        host, account, token = 'api.classplusapp.com', 'self', args[0]
                    else:
                        raise ProviderError('USE_CONNECT_APPX_HOST_USERID_TOKEN_OR_CONNECT_CLASSPLUS_TOKEN')
                    if not 10 <= len(token) <= 4096 or any(c.isspace() or ord(c) < 33 for c in token) or '*' in token:
                        raise ProviderError('INVALID_TOKEN_FORMAT_NO_PASSWORDS')
                    if uid in self.jobs.active:
                        raise ProviderError('CANCEL_EXISTING_JOB_BEFORE_RECONNECT')
                    self.state.drop(uid, selected)
                    connection = Connection(host, account, token, selected)
                    await self.finish_login(uid, cid, connection)
                elif cmd == '/setdestination':
                    if len(parts) != 2:
                        raise ProviderError('USE_SETDESTINATION_CHANNEL_USERNAME_OR_ID')
                    if uid in self.jobs.active:
                        raise ProviderError('CANCEL_EXISTING_JOB_BEFORE_CHANGING_DESTINATION')
                    value = await self.destinations.set(uid, parts[1])
                    await self.tg.send(cid, f'Destination verified: {value.title} ({value.chat_id}). Export files go ONLY there. This setting resets on restart.')
                elif cmd == '/destination':
                    value = self.destinations.values.get(uid)
                    await self.tg.send(cid, f'Destination: {value.title} ({value.chat_id})' if value else 'No destination selected. /setdestination @YourChannel')
                elif cmd == '/cleardestination':
                    self.jobs.cancel(uid)
                    self.destinations.values.pop(uid, None)
                    await self.tg.send(cid, 'Destination forgotten; cancellation requested. No output fallback.')
                elif cmd in ('/courses', '/refreshcourses', '/export'):
                    connection = self.state.get(uid, selected)
                    if not connection:
                        raise ProviderError('CONNECT_SELECTED_PROVIDER_FIRST_SESSION_EXPIRED_OR_RESTARTED')
                    if cmd in ('/courses', '/refreshcourses'):
                        cached = self.course_cache.get((uid, selected))
                        if cmd == '/courses' and cached and cached[0] > time.monotonic() and cached[1] is connection:
                            courses = cached[2]
                        else:
                            courses = await asyncio.wait_for(self.router.adapter(selected).courses(connection), 35)
                            self.course_cache[(uid, selected)] = (time.monotonic() + 20, connection, courses)
                        await self.present_courses(uid, cid, selected, courses)
                    else:
                        if len(parts) != 2 or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', parts[1]):
                            raise ProviderError('USE_EXPORT_COURSE_ID')
                        destination = self.destinations.values.get(uid)
                        if not destination:
                            raise ProviderError('SET_DESTINATION_BEFORE_EXPORT_NO_SILENT_DM_FALLBACK')
                        job = self.jobs.submit(uid, cid, connection, parts[1], destination)
                        await self.tg.send(cid, f'Queued: {job.id} ({selected}). Destination: {destination.title}. /status | /cancel')
                else:
                    await self.tg.send(cid, 'Unknown command. /help')
            except ProviderError as exc:
                await self.tg.send(cid, login_error(str(exc)))
            except asyncio.TimeoutError:
                await self.tg.send(cid, 'PROVIDER_TIMEOUT_TRY_LATER_NO_AUTORETRY')
            except ValueError:
                await self.tg.send(cid, 'SESSION_CAPACITY_REACHED')

    async def consume(self, queue=None):
        queue = self.updates if queue is None else queue
        while True:
            update = await queue.get()
            try:
                await self.handle(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.warning('UPDATE_FAILED')
            finally:
                queue.task_done()
                update = None  # do not retain last credential-bearing update while idle

    async def housekeeping(self):
        while True:
            await asyncio.sleep(60)
            self.state.purge()
            self.conversations.purge()
            self.classplus_login.purge()
            now = time.monotonic()
            self.course_cache = {k: v for k, v in self.course_cache.items() if v[0] > now}
            active = {u for u, _ in self.state.connections} | set(self.jobs.active) | set(self.conversations.steps) | set(self.classplus_login.pending) | set(self.locks)
            self.last = {u: t for u, t in self.last.items() if t > now - 600 or u in active}
            self.selected = {u: v for u, v in self.selected.items() if u in active or u in self.last}
            self.revisions = {u: v for u, v in self.revisions.items() if u in active or u in self.last}

    def start(self):
        self.jobs.start()
        self.workers = [asyncio.create_task(self.consume()) for _ in range(4)]
        self.workers.append(asyncio.create_task(self.consume(self.fast_updates)))
        self.workers.append(asyncio.create_task(self.housekeeping()))

    async def close(self):
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        await self.jobs.close()
        while not self.updates.empty():
            self.updates.get_nowait()
            self.updates.task_done()
        while not self.fast_updates.empty():
            self.fast_updates.get_nowait()
            self.fast_updates.task_done()
        self.classplus_login.pending.clear()
        self.classplus_login.rates.clear()
        self.course_cache.clear()
        self.conversations.steps.clear()
        self.conversations.choices.clear()
        self.state.connections.clear()
        self.destinations.values.clear()

def create_app(config, bot, runtime=None):
    runtime = runtime if runtime is not None else {'ready': True, 'identity_verified': False, 'webhook_configured': False, 'startup': 'test-harness'}
    app = web.Application(client_max_size=65536)
    def readiness():
        current = dict(runtime)
        if current.get('transport') == 'mtproto-bot' and current['ready'] and not bot.tg.connected:
            current['ready'] = False
            current['startup'] = 'TELEGRAM_TRANSPORT_DISCONNECTED'
        return current
    async def health(request):
        return web.json_response({'service': 'independent-extractor', 'version': '0.4.0-dev', 'status': 'process-alive', 'providers': {'appx': 'limited-test-mvp' if config.appx_hosts else 'disabled-no-approved-host', 'classplus': 'reference-compatible-live-account-unverified'}, 'persistent_jobs': False, 'features': {'classplus_token': True, 'classplus_otp': config.classplus_otp_enabled, 'user_dashboard': True, 'owner_panel': bool(config.owner_id), 'priority_controls': True, 'course_display_cache_seconds': 20}, **readiness()})
    async def ready(request):
        current = readiness()
        return web.json_response(current, status=200 if current['ready'] else 503)
    async def webhook(request):
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', supplied) or not hmac.compare_digest(supplied, config.webhook_secret):
            raise web.HTTPUnauthorized()
        if not runtime['ready'] or runtime.get('transport') == 'mtproto-bot':
            raise web.HTTPServiceUnavailable(headers={'Retry-After': '30'})
        try:
            update = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest() from None
        if not isinstance(update, dict) or not isinstance(update.get('update_id'), int) or isinstance(update.get('update_id'), bool):
            raise web.HTTPBadRequest()
        if update['update_id'] in bot.state.seen:
            return web.json_response({'ok': True})
        queue = bot.queue_for(update)
        if queue.full():
            raise web.HTTPServiceUnavailable(headers={'Retry-After': '10'})
        bot.state.mark_seen(update['update_id'])
        queue.put_nowait(update)
        return web.json_response({'ok': True})
    async def quiesce(request):
        # Secret-authenticated, idempotent stop-first handoff. NEVER exports a session.
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', supplied) or not hmac.compare_digest(supplied, config.webhook_secret):
            raise web.HTTPUnauthorized()
        if runtime.get('quiesced'):
            return web.json_response({'quiesced': True})
        if runtime.get('transport') != 'mtproto-bot' or not runtime.get('ready'):
            raise web.HTTPConflict(text='TRANSPORT_NOT_READY_FOR_HANDOFF')
        if bot.jobs.active:
            raise web.HTTPConflict(text='ACTIVE_JOBS_WAIT_OR_CANCEL_BEFORE_HANDOFF')
        runtime['ready'] = False
        runtime['startup'] = 'MAINTENANCE_STOP_FIRST_HANDOFF'
        await bot.close()
        await bot.tg.close()
        runtime['updates_configured'] = False
        runtime['identity_verified'] = False
        runtime['quiesced'] = True
        return web.json_response({'quiesced': True})
    app.router.add_post('/ops/quiesce', quiesce)
    app.router.add_get('/healthz', health)
    app.router.add_get('/readyz', ready)
    app.router.add_get('/', health)
    app.router.add_post('/telegram/webhook', webhook)
    return app

async def bootstrap_bot(config, tg, bot, runtime):
    if config.startup_paused:
        runtime['startup'] = 'MAINTENANCE_TELEGRAM_START_PAUSED'
        return  # health binds, but no session connect/getMe/handlers/actions
    try:
        if config.transport == 'mtproto':
            await tg.connect()
        me = await verified_identity(tg, config.expected_username)
        if config.transport == 'mtproto' and me['id'] != int(config.bot_token.split(':', 1)[0]):
            raise ProviderError('BOT_SESSION_ID_MISMATCH_NO_ACTIONS')
        bot.destinations.bot_id = me['id']
        runtime['identity_verified'] = True
        if config.transport == 'mtproto':
            confirmed = await tg.call('setMyCommands', {
                'commands': [{'command': name, 'description': description} for name, description in published_commands(config)]})
            if confirmed is not True:
                raise ProviderError('TELEGRAM_COMMANDS_NOT_CONFIRMED')
            tg.start_receiving(bot)
            runtime['transport'] = 'mtproto-bot'
            runtime['updates_configured'] = True
        elif config.set_webhook:
            confirmed = await tg.call('setWebhook', {
                'url': config.public_url + '/telegram/webhook',
                'secret_token': config.webhook_secret,
                'allowed_updates': ['message', 'callback_query'],
                'max_connections': 2, 'drop_pending_updates': False})
            if confirmed is not True:
                raise ProviderError('TELEGRAM_WEBHOOK_NOT_CONFIRMED')
            runtime['webhook_configured'] = True
            confirmed = await tg.call('setMyCommands', {
                'commands': [{'command': name, 'description': description} for name, description in published_commands(config)]})
            if confirmed is not True:
                raise ProviderError('TELEGRAM_COMMANDS_NOT_CONFIRMED')
        bot.start()
        runtime['ready'] = True
        runtime['startup'] = ('verified-mtproto-bot' if config.transport == 'mtproto' else
                              'verified' if config.set_webhook else 'verified-webhook-disabled')
        if config.transport == 'mtproto' and config.owner_ready_notice and config.owner_id:
            await tg.owner_notice()
    except asyncio.CancelledError:
        raise
    except ProviderError as exc:
        runtime['startup'] = str(exc)
        logging.warning('BOT_NOT_READY %s', str(exc))
    except Exception:
        runtime['startup'] = 'STARTUP_FAILED_NO_SECRET_DETAILS_LOGGED'
        logging.warning('BOT_NOT_READY STARTUP_FAILED_NO_SECRET_DETAILS_LOGGED')


async def application():
    config = Config.from_env()
    # Bind health separately from Telegram readiness. No webhook intake before verification.
    resolver = PublicResolver()
    connector = aiohttp.TCPConnector(limit=6, limit_per_host=3, resolver=resolver, ttl_dns_cache=60)
    session = aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.DummyCookieJar(), trust_env=False)
    bot = None
    try:
        runtime = {'ready': False, 'identity_verified': False, 'webhook_configured': False,
                   'updates_configured': False, 'startup': 'identity-check-pending',
                   'transport': 'mtproto-bot' if config.transport == 'mtproto' else 'botapi-webhook'}
        if config.transport == 'mtproto':
            from .mtproto import MTProtoTelegram
            tg = MTProtoTelegram(config, runtime)
        else:
            tg = Telegram(session, config.bot_token)
        providers = {'appx': AppX(session, config.appx_hosts), 'classplus': Classplus(session)}
        bot = Bot(config, tg, providers, 0)
        app = create_app(config, bot, runtime)
        startup_task = None
        async def startup(_):
            nonlocal startup_task
            startup_task = asyncio.create_task(bootstrap_bot(config, tg, bot, runtime))
        async def cleanup(_):
            if startup_task:
                startup_task.cancel()
                await asyncio.gather(startup_task, return_exceptions=True)
            await bot.close()
            if config.transport == 'mtproto':
                await tg.close()
            await session.close()
            await resolver.close()
        app.on_startup.append(startup)
        app.on_cleanup.append(cleanup)
        return app
    except BaseException:
        if bot:
            await bot.close()
        await session.close()
        await resolver.close()
        raise
