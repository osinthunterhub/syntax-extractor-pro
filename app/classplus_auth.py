"""User-initiated Classplus OTP login. Fixed official origin, never Telegram-user login.
No automatic retry, registration, raw response/credential logging or log-channel copies.
"""
import asyncio
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
import aiohttp
from .provider_common import ProviderError


@dataclass
class Challenge:
    stage: str = 'org'
    expires: float = 0
    org_code: str = field(default='', repr=False)
    org_id: object = field(default=None, repr=False)
    phone: str = field(default='', repr=False)
    device: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False)
    session: str = field(default='', repr=False)
    attempts: int = 0


@dataclass
class LoginResult:
    prompt: str = ''
    token: str = field(default='', repr=False)
    confirm: bool = False


class ClassplusLogin:
    def __init__(self, session, clock=time.monotonic):
        self.session, self.clock = session, clock
        self.pending = {}
        self.rates = {}
        self._rate_key = secrets.token_bytes(32)
        self.semaphore = asyncio.Semaphore(2)

    def purge(self):
        now = self.clock()
        self.pending = {uid: d for uid, d in self.pending.items() if d.expires > now}
        self.rates = {k: [t for t in values if t > now - 86400] for k, values in self.rates.items()}
        self.rates = {k: v for k, v in self.rates.items() if v}

    def cancel(self, uid):
        return self.pending.pop(uid, None) is not None

    def begin(self, uid):
        self.purge()
        if uid not in self.pending and len(self.pending) >= 250:
            raise ProviderError('CLASSPLUS_LOGIN_CAPACITY_TRY_LATER')
        self.pending[uid] = Challenge(expires=self.clock() + 300)
        return LoginResult('CLASSPLUS • MOBILE + OTP\n\nStep 1 / 3 — Send your institute org code.\nExample format: ABCD\n\nUse only your OWN existing account. This is NOT a Telegram login.\nNo SMS is sent until you confirm your number.\n\n/cancel exits. Setup expires after 5 minutes of inactivity.')

    def current(self, uid, draft):
        if self.pending.get(uid) is not draft:
            raise ProviderError('CLASSPLUS_LOGIN_EXPIRED_OR_CANCELLED')
        if draft.expires <= self.clock():
            self.cancel(uid)
            raise ProviderError('CLASSPLUS_LOGIN_EXPIRED_OR_CANCELLED')

    @asynccontextmanager
    async def slot(self):
        try:
            await asyncio.wait_for(self.semaphore.acquire(), 3)
        except asyncio.TimeoutError:
            raise ProviderError('CLASSPLUS_AUTH_BUSY_TRY_LATER') from None
        try:
            yield
        finally:
            self.semaphore.release()

    async def request(self, operation, draft, payload=None):
        if operation not in ('org', 'generate', 'verify'):
            raise ProviderError('CLASSPLUS_AUTH_OPERATION_NOT_ALLOWED')
        path = {'org': '/v2/orgs/' + draft.org_code,
                'generate': '/v2/otp/generate', 'verify': '/v2/users/verify'}[operation]
        if operation == 'org' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', draft.org_code):
            raise ProviderError('CLASSPLUS_ORG_CODE_FORMAT_INVALID')
        if self.session is None:
            raise ProviderError('CLASSPLUS_AUTH_UNAVAILABLE_USE_TOKEN')
        method = self.session.get if operation == 'org' else self.session.post
        kwargs = {'headers': {'Accept': 'application/json', 'Api-Version': '51', 'device-id': draft.device},
                  'allow_redirects': False, 'timeout': aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)}
        if operation != 'org':
            kwargs['json'] = payload
        async with self.slot():
            try:
                async with method('https://api.classplusapp.com' + path, **kwargs) as response:
                    if response.status == 429:
                        raise ProviderError('CLASSPLUS_OTP_PROVIDER_RATE_LIMITED_WAIT')
                    if operation == 'verify' and response.status in (201, 409):
                        raise ProviderError('CLASSPLUS_REGISTRATION_REQUIRED_USE_OFFICIAL_APP')
                    if operation == 'verify' and response.status in (400, 401, 403):
                        raise ProviderError('CLASSPLUS_OTP_INVALID_OR_EXPIRED')
                    if response.status != 200:
                        raise ProviderError('CLASSPLUS_AUTH_REQUEST_REJECTED')
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(16384):
                        size += len(chunk)
                        if size > 65536:
                            raise ProviderError('CLASSPLUS_AUTH_RESPONSE_TOO_LARGE')
                        chunks.append(chunk)
                    result = json.loads(b''.join(chunks))
                    if not isinstance(result, dict) or not isinstance(result.get('data'), dict):
                        raise ProviderError('CLASSPLUS_AUTH_SCHEMA_UNSUPPORTED')
                    if result.get('status') not in (None, 'success', 'SUCCESS', 200, '200', True):
                        code = 'CLASSPLUS_OTP_INVALID_OR_EXPIRED' if operation == 'verify' else 'CLASSPLUS_AUTH_REQUEST_REJECTED'
                        raise ProviderError(code)
                    return result['data']
            except ProviderError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
                raise ProviderError('CLASSPLUS_AUTH_NETWORK_ERROR_NO_AUTORETRY') from None

    def reserve_sms(self, uid, phone):
        self.purge()
        now = self.clock()
        digest = hmac.new(self._rate_key, phone.encode('ascii'), hashlib.sha256).hexdigest()
        keys = ['user:' + str(uid), 'phone:' + digest, 'global']
        for key, day_limit in zip(keys, (3, 5, 100)):
            times = self.rates.get(key, [])
            if len(times) >= day_limit:
                raise ProviderError('CLASSPLUS_OTP_DAILY_LIMIT_USE_TOKEN_OR_WAIT')
            minute = sum(t > now - 60 for t in times)
            if minute >= (10 if key == 'global' else 1):
                raise ProviderError('CLASSPLUS_OTP_COOLDOWN_WAIT_60_SECONDS')
        if len(set(keys) - self.rates.keys()) + len(self.rates) > 1000:
            raise ProviderError('CLASSPLUS_OTP_CAPACITY_TRY_LATER')
        # Reserve BEFORE POST: ambiguous/time-out responses are never retried automatically.
        for key in keys:
            self.rates.setdefault(key, []).append(now)

    def reserve_lookup(self, uid):
        self.purge()
        now = self.clock()
        keys = ('lookup:' + str(uid), 'lookup:global')
        for key, limit in zip(keys, (5, 30)):
            times = [t for t in self.rates.get(key, []) if t > now - 60]
            if len(times) >= limit:
                raise ProviderError('CLASSPLUS_ORG_LOOKUP_RATE_LIMITED_WAIT')
        if len(set(keys) - self.rates.keys()) + len(self.rates) > 1000:
            raise ProviderError('CLASSPLUS_OTP_CAPACITY_TRY_LATER')
        for key in keys:
            self.rates[key] = [t for t in self.rates.get(key, []) if t > now - 60] + [now]

    async def input(self, uid, text):
        draft = self.pending.get(uid)
        if draft is None:
            raise ProviderError('CLASSPLUS_LOGIN_EXPIRED_OR_CANCELLED')
        self.current(uid, draft)
        text = text.strip()
        if draft.stage == 'org':
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', text):
                raise ProviderError('CLASSPLUS_ORG_CODE_FORMAT_INVALID')
            self.reserve_lookup(uid)
            draft.org_code, draft.stage = text, 'resolving'
            try:
                data = await self.request('org', draft)
                self.current(uid, draft)
                org_id = data.get('orgId')
                if isinstance(org_id, bool) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(org_id or '')):
                    raise ProviderError('CLASSPLUS_AUTH_SCHEMA_UNSUPPORTED')
                draft.org_id, draft.stage, draft.expires = org_id, 'phone', self.clock() + 300
                return LoginResult('CLASSPLUS • MOBILE + OTP\n\nStep 2 / 3 — Send your OWN 10-digit Indian mobile number linked to that institute.\n+91 format is also accepted.\n\nNo OTP has been requested yet. Message deletion is best-effort.\n/cancel exits.')
            except ProviderError:
                if self.pending.get(uid) is draft:
                    draft.stage = 'org'
                raise
        if draft.stage == 'phone':
            phone = re.sub(r'[\s-]', '', text)
            if phone.startswith('+91'):
                phone = phone[3:]
            elif len(phone) == 12 and phone.startswith('91'):
                phone = phone[2:]
            if not re.fullmatch(r'[6-9][0-9]{9}', phone):
                raise ProviderError('CLASSPLUS_OWN_INDIAN_MOBILE_REQUIRED')
            draft.phone, draft.stage, draft.expires = phone, 'confirm', self.clock() + 300
            return LoginResult('CLASSPLUS • CONFIRM SMS\n\nNumber: +91 ••••••' + phone[-4:] + '\n\nTap Send OTP ONLY if this is your OWN account number.\nOne request, no automatic resend.\n\nLimits: 1 per minute, 3 per day per Telegram user (RAM-only).\n/cancel exits.', confirm=True)
        if draft.stage == 'otp':
            if not re.fullmatch(r'[0-9]{4,8}', text):
                raise ProviderError('CLASSPLUS_OTP_FORMAT_4_TO_8_DIGITS')
            draft.stage, draft.attempts = 'verifying', draft.attempts + 1
            try:
                data = await self.request('verify', draft, {'otp': text, 'countryExt': '91',
                    'sessionId': draft.session, 'orgId': draft.org_id,
                    'fingerprintId': draft.device, 'mobile': draft.phone})
                self.current(uid, draft)
                user = data.get('user')
                if isinstance(user, dict) and (user.get('exists') is False or user.get('signedUp') is False):
                    raise ProviderError('CLASSPLUS_REGISTRATION_REQUIRED_USE_OFFICIAL_APP')
                token = data.get('token')
                if not isinstance(token, str) or not 10 <= len(token) <= 4096 or any(c.isspace() or ord(c) < 33 for c in token) or '*' in token:
                    raise ProviderError('CLASSPLUS_AUTH_TOKEN_SCHEMA_UNSUPPORTED')
                self.cancel(uid)
                return LoginResult(token=token)
            except ProviderError as exc:
                if self.pending.get(uid) is draft:
                    if draft.attempts >= 3 or str(exc) in ('CLASSPLUS_REGISTRATION_REQUIRED_USE_OFFICIAL_APP', 'CLASSPLUS_AUTH_TOKEN_SCHEMA_UNSUPPORTED'):
                        self.cancel(uid)
                    else:
                        draft.stage = 'otp'
                raise
        raise ProviderError('CLASSPLUS_LOGIN_USE_BUTTON_OR_WAIT_CURRENT_STEP')

    async def send(self, uid):
        draft = self.pending.get(uid)
        if draft is None:
            raise ProviderError('CLASSPLUS_LOGIN_EXPIRED_OR_CANCELLED')
        self.current(uid, draft)
        if draft.stage != 'confirm':
            raise ProviderError('CLASSPLUS_OTP_CONFIRM_NUMBER_FIRST_NO_AUTORESEND')
        self.reserve_sms(uid, draft.phone)
        draft.stage = 'sending'
        try:
            data = await self.request('generate', draft, {'countryExt': '91', 'orgId': draft.org_id,
                'mobile': draft.phone, 'viaSms': 1, 'viaEmail': 0})
            self.current(uid, draft)
            session = data.get('sessionId')
            if not isinstance(session, (str, int)) or isinstance(session, bool) or not 1 <= len(str(session)) <= 512:
                raise ProviderError('CLASSPLUS_AUTH_SESSION_SCHEMA_UNSUPPORTED')
            draft.session, draft.stage, draft.expires = str(session), 'otp', self.clock() + 300
            return LoginResult('CLASSPLUS • ENTER OTP\n\nThe provider accepted the OTP request for +91 ••••••' + draft.phone[-4:] + '.\nDelivery time is controlled by Classplus/SMS network.\n\nStep 3 / 3 — Send that CLASSPLUS OTP here in private chat.\nMaximum 3 verification attempts; expires after 5 minutes.\nNever send a Telegram login code.\n\n/cancel exits.')
        except ProviderError:
            if self.pending.get(uid) is draft:
                self.cancel(uid)  # ambiguous send: explicit fresh flow + cooldown required
            raise
