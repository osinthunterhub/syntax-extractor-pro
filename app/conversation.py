"""Bounded private-chat setup and opaque course choices. No secrets in wizard state."""
from dataclasses import dataclass
import re
import time
import secrets
from .provider_common import ProviderError

@dataclass
class Step:
    provider: str
    stage: str
    expires: float
    host: str = ''

class Conversations:
    def __init__(self):
        self.steps = {}
        self.choices = {}

    def purge(self):
        now = time.monotonic()
        self.steps = {uid: step for uid, step in self.steps.items() if step.expires > now}
        self.choices = {uid: item for uid, item in self.choices.items() if item[0] > now}

    def clear(self, uid):
        self.steps.pop(uid, None)
        self.choices.pop(uid, None)

    def begin(self, uid, provider, hosts):
        self.purge()
        if uid not in self.steps and len(self.steps) >= 250:
            raise ProviderError('SETUP_CAPACITY_REACHED')
        self.clear(uid)
        if provider == 'classplus':
            self.steps[uid] = Step(provider, 'token', time.monotonic() + 300)
            return 'Classplus: send ONLY your own existing access token in this private chat. Do not send a password/OTP. Message deletion is best-effort. Expires in5 minutes; /cancel exits.'
        if not hosts:
            raise ProviderError('APPX_SETUP_NEEDS_APPROVED_COACHING_API_HOST_NO_TOKEN_REQUESTED')
        host = next(iter(hosts)) if len(hosts) == 1 else ''
        self.steps[uid] = Step(provider, 'credentials' if host else 'host', time.monotonic() + 300, host)
        return ('AppX host: ' + host + '. Send ACTUAL_USER_ID TOKEN on one line; own account only. No password/OTP. Best-effort deletion; /cancel exits.' if host else 'Select your approved AppX API host by sending its hostname: ' + ', '.join(sorted(hosts)))

    def accept(self, uid, text, hosts):
        step = self.steps.pop(uid, None)
        if step is None or step.expires <= time.monotonic():
            raise ProviderError('SETUP_EXPIRED_USE_CONNECT')
        args = text.strip().split()
        if step.stage == 'host':
            if len(args) != 1 or args[0].lower() not in hosts:
                raise ProviderError('APPX_HOST_NOT_APPROVED_USE_CONNECT')
            step.host, step.stage = args[0].lower(), 'credentials'
            self.steps[uid] = step
            return None, 'Now send ACTUAL_USER_ID TOKEN from your own AppX account; no password/OTP. /cancel exits.'
        if step.provider == 'classplus':
            if len(args) != 1:
                raise ProviderError('INVALID_SETUP_INPUT_USE_CONNECT_NO_PASSWORDS')
            return '/connect classplus ' + args[0], None
        if len(args) != 2:
            raise ProviderError('INVALID_SETUP_INPUT_USE_CONNECT_NO_PASSWORDS')
        return '/connect appx ' + step.host + ' ' + ' '.join(args), None

    def course_page(self, uid, provider, courses):
        self.purge()
        if uid not in self.choices and len(self.choices) >= 250:
            raise ProviderError('COURSE_SELECTION_CAPACITY_REACHED')
        nonce = secrets.token_hex(4)
        self.choices[uid] = (time.monotonic() + 300, provider, nonce, tuple(courses))
        return nonce

    def choose(self, uid, provider, nonce, index):
        self.purge()
        item = self.choices.get(uid)
        if not item or item[1] != provider or item[2] != nonce or not 0 <= index < len(item[3]):
            raise ProviderError('COURSE_SELECTION_EXPIRED_OR_CHANGED_USE_COURSES')
        course = item[3][index]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', course.id):
            raise ProviderError('INVALID_COURSE_ID')
        return course.id

    def page(self, uid, provider, nonce, page):
        self.purge()
        item = self.choices.get(uid)
        if not item or item[1] != provider or item[2] != nonce:
            raise ProviderError('COURSE_SELECTION_EXPIRED_OR_CHANGED_USE_COURSES')
        courses = item[3]
        pages = (len(courses) + 7) // 8
        if not 0 <= page < pages:
            raise ProviderError('INVALID_COURSE_PAGE')
        return courses[page * 8:(page + 1) * 8], pages
