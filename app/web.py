import asyncio
import hmac
import logging
import re
import time
from aiohttp import web
import aiohttp
from .config import Config
from .state import State, Connection
from .providers import AppX, Classplus, ProviderRouter, ProviderError, PublicResolver
from .destinations import Destinations
from .jobs import Jobs
from .telegram import Telegram, verified_identity

HELP = '''Syntax Extractor Pro — v0.2.1-dev, mock-tested; live verification pending.
AppX and Classplus have separate account connections.
/appx — select AppX
/classplus or /cp — select Classplus
/connect appx API_HOST ACTUAL_USER_ID TOKEN
/connect classplus YOUR_OWN_TOKEN
/courses — selected provider's account courses
/setdestination @YourChannel — you and bot must be channel admins
/destination — current export destination
/cleardestination — forget destination and cancel your job
/export COURSE_ID — send supported clear-link TXT ONLY to selected channel
/status | /cancel
/disconnect — selected provider logout + job cancellation
/logoutall — forget both provider connections + cancel
/help
No passwords, fixed accounts, DRM decryption or protected-access bypass.
Sessions, destinations, jobs and dedup are RAM-only; restart loses them.
Connection map TTL: one hour. Job snapshots retained until stopped.
Connection messages deleted best-effort. Keep signed-link files private.'''

COMMANDS = [
    ('start', 'Open extractor menu'), ('appx', 'Select AppX account'),
    ('classplus', 'Select Classplus account'), ('connect', 'Connect your own authorized token'),
    ('courses', 'List selected account courses'), ('setdestination', 'Set your export channel'),
    ('destination', 'Show your selected channel'), ('export', 'Queue authorized course TXT export'),
    ('status', 'Check your current job'), ('cancel', 'Cancel your current job'),
    ('disconnect', 'Forget selected account'), ('logoutall', 'Forget all connected accounts'),
    ('cleardestination', 'Forget channel and cancel job'), ('help', 'Show commands and limitations')]

class Bot:
    def __init__(self, config, tg, provider, bot_id=0):
        self.config, self.tg = config, tg
        self.router = ProviderRouter(provider if isinstance(provider, dict) else {'appx': provider})
        self.state = State()
        self.selected = {}
        self.destinations = Destinations(tg, bot_id)
        self.updates = asyncio.Queue(maxsize=32)
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

    async def handle(self, update):
        callback = update.get('callback_query')
        if isinstance(callback, dict):
            qid = callback.get('id')
            if isinstance(qid, str) and len(qid) <= 256:
                await self.tg.call('answerCallbackQuery', {'callback_query_id': qid})
            mapping = {'provider:appx': '/appx', 'provider:classplus': '/classplus', 'nav:courses': '/courses',
                       'nav:destination': '/destination', 'nav:status': '/status', 'nav:help': '/help'}
            command = mapping.get(callback.get('data'))
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
        if not isinstance(text, str) or not text.startswith('/'):
            return
        parts = text.split()
        cmd = parts[0].split('@')[0].lower()
        if chat.get('type') != 'private' or uid != cid:
            if cmd == '/connect':
                await self.tg.delete(cid, message.get('message_id'))
            await self.tg.send(cid, 'For account security, use this bot in private chat only.')
            return
        if cmd == '/connect':
            await self.tg.delete(cid, message.get('message_id'))
        if uid not in self.locks and len(self.locks) >= 250:
            await self.tg.send(cid, 'USER_CAPACITY_REACHED_TRY_AFTER_RESTART')
            return
        lock = self.locks.setdefault(uid, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cheap = {'/start', '/help', '/appx', '/classplus', '/cp', '/cancel', '/disconnect', '/logoutall', '/status', '/destination', '/cleardestination'}
            if cmd not in cheap and now - self.last.get(uid, 0) < 2:
                await self.tg.send(cid, 'Please wait two seconds between API commands.')
                return
            if cmd not in cheap:
                self.last[uid] = now
            selected = self.selected.get(uid, 'appx')
            try:
                if cmd in ('/start', '/help'):
                    await self.menu(cid, HELP)
                elif cmd in ('/appx', '/classplus', '/cp'):
                    selected = 'appx' if cmd == '/appx' else 'classplus'
                    self.selected[uid] = selected
                    title = 'AppX' if selected == 'appx' else 'Classplus'
                    hint = '/connect appx API_HOST USER_ID TOKEN' if selected == 'appx' else '/connect classplus YOUR_OWN_TOKEN'
                    if selected == 'appx' and not self.config.appx_hosts:
                        await self.menu(cid, 'AppX selected. Operator setup pending: no approved coaching API host configured. Classplus remains separate. /classplus')
                        return
                    await self.menu(cid, f'{title} selected. Your other provider session is unchanged.\n{hint}\n/courses | /destination | /export COURSE_ID\nMock-tested adapter; real provider verification pending.')
                elif cmd == '/connect':
                    args = parts[1:]
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
                    courses = await self.router.adapter(selected).courses(connection)
                    self.state.put(uid, connection)
                    self.selected[uid] = selected
                    await self.tg.send(cid, f'{selected}: connected. {len(courses)} account courses returned. Token not logged. /courses')
                elif cmd in ('/disconnect', '/logoutall'):
                    self.jobs.cancel(uid)
                    self.state.drop(uid, None if cmd == '/logoutall' else selected)
                    await self.tg.send(cid, 'Connection forgotten; cancellation requested. In-flight requests stop at deadline.')
                elif cmd == '/cancel':
                    await self.tg.send(cid, 'Cancellation requested.' if self.jobs.cancel(uid) else 'No active job.')
                elif cmd == '/status':
                    job = self.jobs.active.get(uid)
                    await self.tg.send(cid, f'Job {job.id} ({job.connection.provider}): queued/running; cancel={job.cancelled.is_set()}' if job else 'No active job.')
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
                elif cmd == '/stats':
                    if not self.config.owner_id or uid != self.config.owner_id:
                        raise ProviderError('OWNER_ONLY')
                    await self.tg.send(cid, f'RAM connections: {len(self.state.connections)}\nActive/queued jobs: {len(self.jobs.active)}\nWaiting: {self.jobs.queue.qsize()}\nProvider adapters: {", ".join(sorted(self.router.providers))}\nLive verification: pending\nDurable jobs: no')
                elif cmd in ('/courses', '/export'):
                    connection = self.state.get(uid, selected)
                    if not connection:
                        raise ProviderError('CONNECT_SELECTED_PROVIDER_FIRST_SESSION_EXPIRED_OR_RESTARTED')
                    if cmd == '/courses':
                        courses = await self.router.adapter(selected).courses(connection)
                        if not courses:
                            await self.tg.send(cid, 'No courses returned by your account.')
                            return
                        buf = f'{selected}: your account courses\n'
                        for course in courses:
                            row = f'{course.id} — {course.name}' + ('' if course.folder_mode else ' [flat course; schema-dependent]') + '\n'
                            if len(buf) + len(row) > 3200:
                                await self.tg.send(cid, buf)
                                buf = ''
                                await asyncio.sleep(1)
                            buf += row
                        if buf:
                            await self.tg.send(cid, buf)
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
                await self.tg.send(cid, str(exc))
            except ValueError:
                await self.tg.send(cid, 'SESSION_CAPACITY_REACHED')

    async def consume(self):
        while True:
            update = await self.updates.get()
            try:
                await self.handle(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.warning('UPDATE_FAILED')
            finally:
                self.updates.task_done()
                update = None  # do not retain last credential-bearing update while idle

    async def housekeeping(self):
        while True:
            await asyncio.sleep(60)
            self.state.purge()

    def start(self):
        self.jobs.start()
        self.workers = [asyncio.create_task(self.consume()) for _ in range(2)]
        self.workers.append(asyncio.create_task(self.housekeeping()))

    async def close(self):
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        await self.jobs.close()
        self.state.connections.clear()
        self.destinations.values.clear()

def create_app(config, bot, runtime=None):
    runtime = runtime if runtime is not None else {'ready': True, 'identity_verified': False, 'webhook_configured': False, 'startup': 'test-harness'}
    app = web.Application(client_max_size=65536)
    async def health(request):
        return web.json_response({'service': 'independent-extractor', 'version': '0.2.1-dev', 'status': 'process-alive', 'providers': {'appx': 'limited-test-mvp' if config.appx_hosts else 'disabled-no-approved-host', 'classplus': 'mock-tested-live-unverified'}, 'persistent_jobs': False, **runtime})
    async def ready(request):
        return web.json_response(dict(runtime), status=200 if runtime['ready'] else 503)
    async def webhook(request):
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', supplied) or not hmac.compare_digest(supplied, config.webhook_secret):
            raise web.HTTPUnauthorized()
        if not runtime['ready']:
            raise web.HTTPServiceUnavailable(headers={'Retry-After': '30'})
        try:
            update = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest() from None
        if not isinstance(update, dict) or not isinstance(update.get('update_id'), int) or isinstance(update.get('update_id'), bool):
            raise web.HTTPBadRequest()
        if update['update_id'] in bot.state.seen:
            return web.json_response({'ok': True})
        if bot.updates.full():
            raise web.HTTPServiceUnavailable(headers={'Retry-After': '10'})
        bot.state.mark_seen(update['update_id'])
        bot.updates.put_nowait(update)
        return web.json_response({'ok': True})
    app.router.add_get('/healthz', health)
    app.router.add_get('/readyz', ready)
    app.router.add_get('/', health)
    app.router.add_post('/telegram/webhook', webhook)
    return app

async def bootstrap_bot(config, tg, bot, runtime):
    try:
        me = await verified_identity(tg, config.expected_username)
        bot.destinations.bot_id = me['id']
        runtime['identity_verified'] = True
        if config.set_webhook:
            confirmed = await tg.call('setWebhook', {
                'url': config.public_url + '/telegram/webhook',
                'secret_token': config.webhook_secret,
                'allowed_updates': ['message', 'callback_query'],
                'max_connections': 2, 'drop_pending_updates': False})
            if confirmed is not True:
                raise ProviderError('TELEGRAM_WEBHOOK_NOT_CONFIRMED')
            runtime['webhook_configured'] = True
            confirmed = await tg.call('setMyCommands', {
                'commands': [{'command': name, 'description': description} for name, description in COMMANDS]})
            if confirmed is not True:
                raise ProviderError('TELEGRAM_COMMANDS_NOT_CONFIRMED')
        bot.start()
        runtime['ready'] = True
        runtime['startup'] = 'verified' if config.set_webhook else 'verified-webhook-disabled'
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
        tg = Telegram(session, config.bot_token)
        providers = {'appx': AppX(session, config.appx_hosts), 'classplus': Classplus(session)}
        bot = Bot(config, tg, providers, 0)
        runtime = {'ready': False, 'identity_verified': False,
                   'webhook_configured': False, 'startup': 'identity-check-pending'}
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
