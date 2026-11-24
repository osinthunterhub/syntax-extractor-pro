"""Optional official MTProto transport for the SAME bot, never a personal user session.
No passwords/phone login, arbitrary RPC endpoint, session export, or token logging.
"""
import asyncio
import io
import logging
import re
import time
from telethon import TelegramClient, Button, events, functions, types, utils, errors
from telethon.sessions import StringSession
from .telegram import Telegram, TelegramRateLimited
from .providers import ProviderError
from .ui import SUPPORT_URL


def buttons(rows):
    return [[Button.url(b['text'], b['url']) if 'url' in b else
             Button.inline(b['text'], b['callback_data'].encode('ascii')) for b in row] for row in rows]


def incoming_message(event, allow_plain=False):
    uid, cid = event.sender_id, event.chat_id
    if (not event.is_private or getattr(event, 'out', False) or not isinstance(uid, int)
            or isinstance(uid, bool) or uid <= 0 or uid != cid
            or getattr(getattr(event, 'sender', None), 'bot', False)):
        return None
    text = event.raw_text
    if not isinstance(text, str) or len(text) > 5000 or not (text.startswith('/') or allow_plain):
        return None
    return {'message': {'from': {'id': uid, 'is_bot': False},
            'chat': {'id': cid, 'type': 'private'}, 'message_id': event.id, 'text': text}}


def incoming_callback(event):
    uid, cid = event.sender_id, event.chat_id
    if (not event.is_private or not isinstance(uid, int) or isinstance(uid, bool)
            or uid <= 0 or uid != cid):
        return None
    try:
        data = event.data.decode('ascii')
    except (UnicodeError, AttributeError):
        return None
    if len(data) > 64:
        return None
    return {'callback_query': {'id': str(event.id), 'from': {'id': uid, 'is_bot': False},
        'data': data, 'message': {'message_id': event.message_id,
                               'chat': {'id': cid, 'type': 'private'}}}}


def participant_status(participant):
    if isinstance(participant, types.ChannelParticipantCreator):
        return {'status': 'creator', 'can_post_messages': True}
    if isinstance(participant, types.ChannelParticipantAdmin):
        return {'status': 'administrator',
                'can_post_messages': bool(participant.admin_rights.post_messages)}
    if isinstance(participant, types.ChannelParticipant):
        return {'status': 'member', 'can_post_messages': False}
    return {'status': 'left', 'can_post_messages': False}


class MTProtoTelegram(Telegram):
    def __init__(self, config, runtime, client=None):
        self.config, self.runtime, self.handlers = config, runtime, []
        self._last_busy = 0.0
        if client is None:
            private_logger = logging.getLogger('syntax.mtproto.private')
            private_logger.setLevel(logging.CRITICAL + 1)
            private_logger.addHandler(logging.NullHandler())
            private_logger.propagate = False
            try:
                session = StringSession(config.mtproto_session)
                client = TelegramClient(session, config.telegram_api_id, config.telegram_api_hash,
                    request_retries=0, raise_last_call_error=True, connection_retries=3,
                    timeout=10, flood_sleep_threshold=0, auto_reconnect=True,
                    base_logger=private_logger, device_model='Syntax Extractor Bot',
                    app_version='0.3.1', entity_cache_limit=1000)
            except Exception:
                raise ProviderError('INVALID_BOT_ONLY_MTPROTO_CONFIGURATION') from None
        self.client = client

    @property
    def connected(self):
        return self.client.is_connected()

    async def connect(self):
        try:
            await asyncio.wait_for(self.client.connect(), 25)
        except Exception:
            raise ProviderError('TELEGRAM_MTPROTO_CONNECT_FAILED') from None

    async def close(self):
        for handler, builder in self.handlers:
            self.client.remove_event_handler(handler, builder)
        self.handlers.clear()
        await self.client.disconnect()  # never logOut: preserves this bot-only authorization

    def sent(self):
        self.runtime['outbound_messages'] = self.runtime.get('outbound_messages', 0) + 1
        self.runtime['last_outbound_at'] = int(time.time())

    async def call(self, method, payload=None, form=None):
        if form is not None:
            raise ProviderError('MTPROTO_FORM_OPERATION_NOT_SUPPORTED')
        p = payload or {}
        async def execute():
            if method == 'getMe':
                me = await self.client.get_me()
                if me is None:
                    raise ProviderError('BOT_SESSION_NOT_AUTHORIZED')
                return {'id': me.id, 'username': me.username, 'is_bot': me.bot}
            if method in ('sendMessage', 'editMessageText'):
                kwargs = {'buttons': buttons(p.get('reply_markup', {}).get('inline_keyboard', [])),
                          'parse_mode': None, 'link_preview': False}
                if method == 'sendMessage':
                    msg = await self.client.send_message(p['chat_id'], p['text'], **kwargs)
                else:
                    msg = await self.client.edit_message(p['chat_id'], p['message_id'], p['text'], **kwargs)
                self.sent()
                return {'message_id': msg.id}
            if method == 'deleteMessage':
                await self.client.delete_messages(p['chat_id'], [p['message_id']]); return True
            if method == 'answerCallbackQuery':
                return await self.client(functions.messages.SetBotCallbackAnswerRequest(
                    query_id=int(p['callback_query_id']), cache_time=0))
            if method == 'setMyCommands':
                return await self.client(functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopeDefault(), lang_code='',
                    commands=[types.BotCommand(x['command'], x['description']) for x in p['commands']]))
            if method == 'getChat':
                target = p['chat_id']
                if isinstance(target, str) and re.fullmatch(r'-?\d{1,20}', target):
                    target = int(target)
                entity = await self.client.get_entity(target)
                kind = ('channel' if isinstance(entity, types.Channel) and entity.broadcast else
                        'supergroup' if isinstance(entity, types.Channel) else
                        'group' if isinstance(entity, types.Chat) else 'private')
                return {'id': utils.get_peer_id(entity), 'type': kind,
                        'title': getattr(entity, 'title', '')}
            if method == 'getChatMember':
                target = p['chat_id']
                if isinstance(target, str) and re.fullmatch(r'-?\d{1,20}', target):
                    target = int(target)
                entity = await self.client.get_entity(target)
                if not isinstance(entity, types.Channel) or not entity.broadcast:
                    raise ProviderError('DESTINATION_MUST_BE_A_CHANNEL')
                participant = await self.client(functions.channels.GetParticipantRequest(
                    channel=entity, participant=p['user_id']))
                return participant_status(participant.participant)
            # No HTTP webhook, remote eval or arbitrary RPC exposure in this adapter.
            raise ProviderError('TELEGRAM_OPERATION_NOT_ALLOWED')
        try:
            return await asyncio.wait_for(execute(), 35)
        except errors.MessageNotModifiedError:
            if method == 'editMessageText':
                return True
            raise ProviderError('TELEGRAM_MTPROTO_REQUEST_REJECTED') from None
        except errors.UserNotParticipantError:
            if method == 'getChatMember':
                return {'status': 'left', 'can_post_messages': False}
            raise ProviderError('TELEGRAM_MTPROTO_REQUEST_REJECTED') from None
        except errors.FloodWaitError as exc:
            raise TelegramRateLimited(exc.seconds) from None
        except ProviderError:
            raise
        except errors.RPCError as exc:
            raise ProviderError('TELEGRAM_MTPROTO_' + type(exc).__name__.upper()) from None
        except (ValueError, TypeError, KeyError):
            raise ProviderError('TELEGRAM_MTPROTO_ENTITY_OR_INPUT_UNRESOLVED') from None
        except (OSError, asyncio.TimeoutError):
            raise ProviderError('TELEGRAM_MTPROTO_REQUEST_FAILED') from None

    async def document(self, chat, job_id, result, provider='appx'):
        data = io.BytesIO(result.text.encode('utf-8'))
        data.name = f'{provider}-{job_id}.txt'
        try:
            await asyncio.wait_for(self.client.send_file(chat, data, force_document=True,
                caption=f'Export: {result.count} clear links. Skipped/unsupported: {result.skipped}. Treat signed links as private.',
                parse_mode=None), 90)
            self.sent()
        except errors.FloodWaitError as exc:
            raise TelegramRateLimited(exc.seconds) from None
        except Exception:
            raise ProviderError('TELEGRAM_MTPROTO_DOCUMENT_FAILED_NO_RETRY') from None
        finally:
            data.close()

    async def enqueue(self, bot, update, key):
        if update is None or key in bot.state.seen:
            return False
        if bot.updates.full():
            self.runtime['overload_drops'] = self.runtime.get('overload_drops', 0) + 1
            now = time.monotonic()
            if now - self._last_busy > 10:
                self._last_busy = now
                part = update.get('message') or update['callback_query']['message']
                try:
                    await asyncio.wait_for(self.send(part['chat']['id'], 'BOT_BUSY_RETRY_YOUR_COMMAND_SHORTLY'), 5)
                except (ProviderError, asyncio.TimeoutError):
                    pass
            return False
        bot.state.mark_seen(key)
        bot.updates.put_nowait(update)
        self.runtime['received_updates'] = self.runtime.get('received_updates', 0) + 1
        return True

    def start_receiving(self, bot):
        async def message(event):
            await self.enqueue(bot, incoming_message(event, event.sender_id in getattr(getattr(bot, 'conversations', None), 'steps', {})), ('mtp-msg', event.chat_id, event.id))
        async def callback(event):
            await self.enqueue(bot, incoming_callback(event), ('mtp-cb', event.id))
        for handler, builder in [(message, events.NewMessage(incoming=True)), (callback, events.CallbackQuery())]:
            self.client.add_event_handler(handler, builder)
            self.handlers.append((handler, builder))

    async def owner_notice(self):
        # One optional activation notice, fixed configured owner only; never arbitrary recipients.
        try:
            entity = await asyncio.wait_for(self.client.get_entity(SUPPORT_URL.rsplit('/', 1)[-1]), 10)
            if entity.id != self.config.owner_id or getattr(entity, 'bot', False):
                self.runtime['owner_notice'] = 'owner-identity-mismatch-not-sent'; return
            await self.menu(entity, '✅ Syntax Extractor Pro connected via its own verified bot session.\n'
                'Menus are active. Provider APIs remain live-unverified.\n/start opens the home panel.')
            self.runtime['owner_notice'] = 'sent'
        except Exception:
            self.runtime['owner_notice'] = 'not-sent-private-chat-may-require-start'
