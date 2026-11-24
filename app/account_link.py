"""NEW per-user QR authorizations, separate from the bot and old forwarder sessions.
No session export, phone/OTP chat input, inbox reading or arbitrary RPC interface.
Full Telegram authorizations remain sensitive to the server operator; disclose this.
"""
import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
import secrets
import time
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import MemorySession
import qrcode
from .provider_common import ProviderError, safe_title


@dataclass
class LinkFlow:
    uid: int
    expires: float
    stage: str = 'consent'
    error: str = ''
    attempts: int = 0
    client: object = field(default=None, repr=False)
    task: object = field(default=None, repr=False)
    qr_url: str = field(default='', repr=False)
    operation: object = field(default=None, repr=False)


@dataclass
class Linked:
    uid: int
    expires: float
    client: object = field(repr=False)


def qr_svg(value):
    if not isinstance(value, str) or not re.fullmatch(r'tg://login\?token=[A-Za-z0-9_-]{8,1024}', value):
        raise ProviderError('TELEGRAM_QR_FORMAT_REJECTED')
    code = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(value); code.make(fit=True)
    matrix = code.get_matrix(); n = len(matrix)
    path = ''.join(f'M{x},{y}h1v1h-1z' for y, row in enumerate(matrix) for x, dark in enumerate(row) if dark)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges"><path fill="white" d="M0 0h{n}v{n}H0z"/><path fill="black" d="{path}"/></svg>'.encode()


class AccountLinks:
    def __init__(self, config, factory=None, clock=time.monotonic):
        self.config, self.factory, self.clock = config, factory, clock
        self.flows, self.by_user, self.linked, self.choices, self.last = {}, {}, {}, {}, {}

    def enabled(self):
        return self.config.telegram_link_enabled and self.config.telegram_api_id > 0 and bool(self.config.telegram_api_hash)

    def new_client(self):
        if self.factory:
            return self.factory()
        logger = logging.getLogger('syntax.userlink.private')
        logger.setLevel(logging.CRITICAL + 1); logger.propagate = False
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        # NEVER use config.mtproto_session / a saved forwarder session here.
        return TelegramClient(MemorySession(), self.config.telegram_api_id, self.config.telegram_api_hash,
            request_retries=0, raise_last_call_error=True, connection_retries=1, timeout=10,
            flood_sleep_threshold=0, auto_reconnect=True, base_logger=logger,
            device_model='Syntax Extractor Linked Account', app_version='0.5.0', entity_cache_limit=256)

    async def dispose(self, client, revoke=True):
        if client is None:
            return True
        revoked = not revoke
        try:
            if revoke and await asyncio.wait_for(client.is_user_authorized(), 3):
                result = await asyncio.wait_for(client.log_out(), 5)
                revoked = result is True
            elif revoke:
                revoked = True
        except Exception:
            pass
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), 3)
            except Exception:
                pass
        return revoked

    async def cancel_flow(self, uid):
        token = self.by_user.pop(uid, None)
        flow = self.flows.pop(token, None) if token else None
        if flow:
            pending = {task for task in (flow.task, flow.operation)
                       if task and task is not asyncio.current_task() and not task.done()}
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await self.dispose(flow.client)
            flow.client, flow.qr_url = None, ''

    async def invite(self, uid):
        if not self.enabled():
            raise ProviderError('TELEGRAM_ACCOUNT_LINK_NOT_CONFIGURED')
        if uid in self.linked and self.linked[uid].expires > self.clock():
            return None
        await self.cancel_flow(uid)
        if len(self.flows) >= 5 or len(self.linked) >= 10:
            raise ProviderError('TELEGRAM_LINK_CAPACITY_TRY_LATER')
        now = self.clock()
        if self.last.get(uid, 0) and now - self.last[uid] < 30:
            raise ProviderError('TELEGRAM_LINK_COOLDOWN_30_SECONDS')
        self.last[uid] = now
        token = secrets.token_urlsafe(32)
        self.flows[token] = LinkFlow(uid, now + 300)
        self.by_user[uid] = token
        return token

    def flow(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ProviderError('LINK_INVALID_OR_EXPIRED')
        flow = self.flows.get(token)
        if flow is None or flow.expires <= self.clock():
            raise ProviderError('LINK_INVALID_OR_EXPIRED')
        return flow

    def snapshot(self, token):
        flow = self.flow(token)
        data = {'uid': flow.uid, 'stage': flow.stage, 'error': flow.error,
                'seconds_left': max(0, int(flow.expires - self.clock()))}
        if flow.stage == 'qr' and flow.qr_url:
            data['qr_image'] = base64.b64encode(qr_svg(flow.qr_url)).decode('ascii')
        return data

    async def start(self, token, consent):
        flow = self.flow(token)
        if consent is not True:
            raise ProviderError('LINK_EXPLICIT_CONSENT_REQUIRED')
        if flow.stage != 'consent':
            return self.snapshot(token)  # double click must not authorize another client
        if sum(f.client is not None for f in self.flows.values()) + len(self.linked) >= 10:
            raise ProviderError('TELEGRAM_LINK_CAPACITY_TRY_LATER')
        flow.operation = asyncio.current_task()
        flow.stage = 'connecting'
        client = self.new_client(); flow.client = client
        try:
            await asyncio.wait_for(client.connect(), 15)
            self.flow(token)
            qr = await asyncio.wait_for(client.qr_login(), 15)
            self.flow(token)
            if self.flows.get(token) is not flow:
                raise ProviderError('LINK_INVALID_OR_EXPIRED')
            qr_svg(qr.url)  # strict URI validation before exposing a scannable token
            flow.qr_url, flow.stage = qr.url, 'qr'
            flow.task = asyncio.create_task(self.wait_for_login(token, flow, qr))
            await asyncio.sleep(0)  # wait() installs its update handler BEFORE QR display
            return self.snapshot(token)
        except asyncio.CancelledError:
            await self.dispose(client); raise
        except Exception:
            if self.flows.get(token) is flow:
                flow.stage, flow.error, flow.qr_url = 'error', 'TELEGRAM_QR_START_FAILED_NO_AUTORETRY', ''
            await self.dispose(client); flow.client = None
            return self.snapshot(token)
        finally:
            flow.operation = None

    async def wait_for_login(self, token, flow, qr):
        try:
            seconds = min(60, max(1, (qr.expires - datetime.now(timezone.utc)).total_seconds()))
            await asyncio.wait_for(qr.wait(timeout=seconds), seconds + 3)
            await self.adopt(token, flow)
        except errors.SessionPasswordNeededError:
            if self.flows.get(token) is flow and flow.expires > self.clock():
                flow.stage, flow.qr_url = 'password', ''
            else:
                await self.dispose(flow.client); flow.client = None
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.flows.get(token) is flow:
                flow.stage, flow.error, flow.qr_url = 'error', 'TELEGRAM_QR_EXPIRED_OR_UNAVAILABLE_RESTART_LINK', ''
            await self.dispose(flow.client); flow.client = None

    async def adopt(self, token, flow):
        client = flow.client
        me = await asyncio.wait_for(client.get_me(), 10)
        if (self.flows.get(token) is not flow or flow.expires <= self.clock()
                or me is None or isinstance(me.id, bool) or me.id != flow.uid or getattr(me, 'bot', True)):
            await self.dispose(client); flow.client = None
            flow.stage, flow.error, flow.qr_url = 'error', 'LINK_ACCOUNT_MUST_MATCH_YOUR_TELEGRAM_ID', ''
            return
        await asyncio.wait_for(client.set_receive_updates(False), 10)
        if self.flows.get(token) is not flow or flow.expires <= self.clock():
            await self.dispose(client); flow.client = None; return
        self.linked[flow.uid] = Linked(flow.uid, self.clock() + 3600, client)
        flow.client, flow.qr_url, flow.stage, flow.error = None, '', 'linked', ''

    async def password(self, token, password):
        flow = self.flow(token)
        if flow.stage != 'password' or not isinstance(password, str) or not 1 <= len(password) <= 512:
            raise ProviderError('LINK_PASSWORD_STEP_NOT_AVAILABLE')
        flow.attempts += 1; flow.stage = 'verifying'
        flow.operation = asyncio.current_task()
        client = flow.client
        try:
            await asyncio.wait_for(client.sign_in(password=password), 20)
            await self.adopt(token, flow)
        except asyncio.CancelledError:
            await self.dispose(client); flow.client = None
            raise
        except errors.PasswordHashInvalidError:
            if flow.attempts < 3:
                flow.stage, flow.error = 'password', 'LINK_2FA_PASSWORD_NOT_ACCEPTED'
            else:
                await self.dispose(flow.client); flow.client = None
                flow.stage, flow.error = 'error', 'LINK_2FA_ATTEMPTS_EXCEEDED'
        except Exception:
            await self.dispose(flow.client); flow.client = None
            flow.stage, flow.error = 'error', 'LINK_2FA_UNAVAILABLE_NO_AUTORETRY'
        finally:
            flow.operation = None
            password = None
        return self.snapshot(token)

    def status(self, uid):
        record = self.linked.get(uid)
        if record and record.expires > self.clock():
            return 'linked' if record.client.is_connected() else 'linked; reconnect needed'
        return 'not linked'

    async def own_client(self, uid):
        record = self.linked.get(uid)
        if not record or record.uid != uid or record.expires <= self.clock():
            raise ProviderError('LINK_YOUR_OWN_TELEGRAM_ACCOUNT_FIRST')
        try:
            if not record.client.is_connected():
                await asyncio.wait_for(record.client.connect(), 15)
            me = await asyncio.wait_for(record.client.get_me(), 10)
            if me is None or isinstance(me.id, bool) or me.id != uid or getattr(me, 'bot', True):
                await self.unlink(uid)
                raise ProviderError('LINKED_ACCOUNT_IDENTITY_REJECTED')
            return record.client
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('LINKED_ACCOUNT_UNAVAILABLE_NO_NEW_LOGIN_AUTOMATICALLY') from None

    async def channels(self, uid):
        client = await self.own_client(uid)
        try:
            result = await asyncio.wait_for(client(functions.channels.GetAdminedPublicChannelsRequest()), 20)
            rows = result.chats
        except Exception:
            raise ProviderError('LINKED_PUBLIC_CHANNEL_LIST_UNAVAILABLE') from None
        if len(rows) > 200:
            raise ProviderError('LINKED_CHANNEL_LIMIT_EXCEEDED_NO_TRUNCATION')
        channels = []
        for channel in rows:
            username = getattr(channel, 'username', None)
            if (isinstance(channel, types.Channel) and channel.broadcast
                    and (channel.creator or channel.admin_rights) and isinstance(username, str)
                    and re.fullmatch(r'[A-Za-z0-9_]{5,32}', username)):
                channels.append((safe_title(channel.title), '@' + username))
        nonce = secrets.token_hex(4)
        self.choices[uid] = (self.clock() + 120, nonce, channels)
        return nonce, channels

    def choose(self, uid, nonce, index):
        item = self.choices.get(uid)
        if (not item or item[0] <= self.clock() or item[1] != nonce or uid not in self.linked
                or self.linked[uid].expires <= self.clock() or not 0 <= index < len(item[2])):
            raise ProviderError('LINKED_CHANNEL_CHOICE_EXPIRED_USE_MYCHANNELS')
        return item[2][index][1]

    async def unlink(self, uid):
        await self.cancel_flow(uid)
        self.choices.pop(uid, None)
        record = self.linked.pop(uid, None)
        return await self.dispose(record.client) if record else True

    async def purge(self):
        for uid, token in list(self.by_user.items()):
            flow = self.flows.get(token)
            if not flow or flow.expires <= self.clock():
                await self.cancel_flow(uid)
        for uid, record in list(self.linked.items()):
            if record.expires <= self.clock():
                await self.unlink(uid)
        self.choices = {u: v for u, v in self.choices.items() if v[0] > self.clock()}
        self.last = {u: t for u, t in self.last.items() if t > self.clock() - 3600}

    async def close(self):
        users = set(self.by_user) | set(self.linked)
        await asyncio.gather(*(self.unlink(uid) for uid in users), return_exceptions=True)
