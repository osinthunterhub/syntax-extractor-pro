"""Small public-access/consent policy. RAM-only: never claim durable bans/settings."""
import time
from .provider_common import ProviderError


class Access:
    def __init__(self, owner_id):
        self.owner_id, self.users, self.maintenance = owner_id, {}, False

    def touch(self, uid):
        if uid != self.owner_id and uid not in self.users and len(self.users) >= 2000:
            raise ProviderError('BOT_USER_REGISTRY_CAPACITY_TRY_LATER')
        self.users.setdefault(uid, {'consent': False, 'blocked': False})['last'] = time.monotonic()

    def consent(self, uid):
        self.touch(uid)
        if self.users[uid]['blocked']:
            raise ProviderError('BOT_ACCESS_BLOCKED_CONTACT_OWNER')
        self.users[uid]['consent'] = True

    def check(self, uid, require_consent=True):
        if self.owner_id and uid == self.owner_id:
            return
        user = self.users.get(uid, {})
        if user.get('blocked'):
            raise ProviderError('BOT_ACCESS_BLOCKED_CONTACT_OWNER')
        if self.maintenance:
            raise ProviderError('BOT_MAINTENANCE_UNLINK_AND_LOGOUT_STILL_AVAILABLE')
        if require_consent and not user.get('consent'):
            raise ProviderError('BOT_ACCESS_CONSENT_REQUIRED_USE_START')

    def block(self, actor, target, blocked):
        self.owner(actor)
        if target == self.owner_id:
            raise ProviderError('CANNOT_BLOCK_OWNER')
        if target not in self.users:
            raise ProviderError('USER_MUST_START_BOT_FIRST')
        self.users[target]['blocked'] = blocked

    def owner(self, uid):
        if not self.owner_id or uid != self.owner_id:
            raise ProviderError('OWNER_ONLY')
