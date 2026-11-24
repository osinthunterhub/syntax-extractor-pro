from collections import OrderedDict
from dataclasses import dataclass, field
import time

@dataclass(frozen=True)
class Connection:
    host: str
    account_id: str
    token: str = field(repr=False)
    provider: str = 'appx'

class State:
    """Process-local only. No passwords, database, account sharing, or resume claims."""
    def __init__(self, max_users=250, ttl=3600):
        self.max_users, self.ttl = max_users, ttl
        self.connections = {}
        self.seen = OrderedDict()

    def purge(self):
        now = time.monotonic()
        self.connections = {u: v for u, v in self.connections.items() if v[0] > now}

    def put(self, user_id, connection):
        self.purge()
        key = (user_id, connection.provider)
        if key not in self.connections and len(self.connections) >= self.max_users:
            raise ValueError('Session capacity reached; try again later.')
        self.connections[key] = (time.monotonic() + self.ttl, connection)

    def get(self, user_id, provider='appx'):
        self.purge()
        entry = self.connections.get((user_id, provider))
        return entry[1] if entry else None

    def drop(self, user_id, provider=None):
        for key in list(self.connections):
            if key[0] == user_id and (provider is None or key[1] == provider):
                self.connections.pop(key, None)

    def mark_seen(self, update_id):
        if update_id in self.seen:
            return False
        self.seen[update_id] = None
        while len(self.seen) > 2000:
            self.seen.popitem(last=False)
        return True
