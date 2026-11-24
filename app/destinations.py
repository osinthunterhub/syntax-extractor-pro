from dataclasses import dataclass
import re
from .providers import ProviderError

@dataclass(frozen=True)
class Destination:
    owner_id: int
    chat_id: int
    title: str

class Destinations:
    def __init__(self, telegram, bot_id):
        self.tg, self.bot_id = telegram, bot_id
        self.values = {}

    async def verify(self, user_id, target):
        if not self.bot_id:
            raise ProviderError('BOT_IDENTITY_NOT_READY')
        if not (re.fullmatch(r'@[A-Za-z0-9_]{5,32}', str(target)) or re.fullmatch(r'-100\d{5,20}', str(target))):
            raise ProviderError('DESTINATION_MUST_BE_CHANNEL_USERNAME_OR_ID')
        chat = await self.tg.call('getChat', {'chat_id': target})
        if not isinstance(chat, dict) or chat.get('type') != 'channel' or not isinstance(chat.get('id'), int):
            raise ProviderError('DESTINATION_MUST_BE_A_CHANNEL')
        cid = chat['id']
        # Establish bot admin status before querying another user's membership.
        me = await self.tg.call('getChatMember', {'chat_id': cid, 'user_id': self.bot_id})
        if not isinstance(me, dict) or me.get('status') != 'administrator' or me.get('can_post_messages') is not True:
            raise ProviderError('BOT_NEEDS_CHANNEL_ADMIN_POST_PERMISSION')
        member = await self.tg.call('getChatMember', {'chat_id': cid, 'user_id': user_id})
        if not isinstance(member, dict) or member.get('status') not in ('creator', 'administrator'):
            raise ProviderError('YOU_MUST_ADMINISTER_DESTINATION')
        return Destination(user_id, cid, str(chat.get('title') or 'Channel')[:160])

    async def set(self, user_id, target):
        value = await self.verify(user_id, target)
        self.values[user_id] = value
        return value

    async def check_delivery(self, user_id, snapshot):
        if not isinstance(snapshot, Destination) or snapshot.owner_id != user_id:
            raise ProviderError('INVALID_JOB_DESTINATION')
        current = self.values.get(user_id)
        if current != snapshot:
            raise ProviderError('DESTINATION_CHANGED_REQUEUE_JOB_NO_FALLBACK')
        checked = await self.verify(user_id, str(snapshot.chat_id))
        if checked.chat_id != snapshot.chat_id:
            raise ProviderError('DESTINATION_CHANGED_NO_FALLBACK')
        return snapshot.chat_id
