import asyncio
import json
import aiohttp
from .providers import ProviderError

class TelegramRateLimited(ProviderError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__(f'TELEGRAM_RATE_LIMITED_RETRY_AFTER_{retry_after}')


async def verified_identity(tg, expected_username, attempts=3, sleep=asyncio.sleep):
    # Only idempotent getMe is retried, never a possibly accepted file/message send.
    for attempt in range(attempts):
        try:
            me = await tg.call('getMe')
            break
        except TelegramRateLimited as exc:
            if attempt + 1 >= attempts or not 1 <= exc.retry_after <= 120:
                raise
            await sleep(exc.retry_after + 1)
    if (not isinstance(me, dict) or not isinstance(me.get('id'), int)
            or isinstance(me.get('id'), bool) or me.get('is_bot') is not True
            or str(me.get('username', '')).lower() != expected_username.lower()):
        raise ProviderError('BOT_IDENTITY_MISMATCH_NO_WEBHOOK_CHANGED')
    return me


class Telegram:
    def __init__(self, session, token):
        self.session, self._token = session, token

    async def call(self, method, payload=None, form=None):
        if method not in {'getMe', 'sendMessage', 'sendDocument', 'deleteMessage', 'setWebhook', 'getChat', 'getChatMember', 'answerCallbackQuery', 'setMyCommands', 'editMessageText'}:
            raise ProviderError('TELEGRAM_OPERATION_NOT_ALLOWED')
        try:
            # No access logging, no exception text, no token-bearing URLs in diagnostics.
            async with self.session.post(f'https://api.telegram.org/bot{self._token}/{method}',
                    json=payload if form is None else None, data=form,
                    allow_redirects=False, timeout=aiohttp.ClientTimeout(total=35, connect=8)) as response:
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(16384):
                    size += len(chunk)
                    if size > 262144:
                        raise ProviderError('TELEGRAM_RESPONSE_TOO_LARGE')
                    chunks.append(chunk)
                result = json.loads(b''.join(chunks))
                if not isinstance(result, dict):
                    raise ProviderError('TELEGRAM_SCHEMA_UNSUPPORTED')
                if response.status == 429:
                    params = result.get('parameters')
                    retry = params.get('retry_after', 0) if isinstance(params, dict) else 0
                    if not isinstance(retry, int) or isinstance(retry, bool) or retry < 1:
                        raise ProviderError('TELEGRAM_RATE_LIMITED_RETRY_LATER')
                    raise TelegramRateLimited(retry)
                if (method == 'editMessageText' and response.status == 400
                        and result.get('description') == 'Bad Request: message is not modified'):
                    return True
                if response.status != 200 or not result.get('ok'):
                    raise ProviderError(f'TELEGRAM_HTTP_{response.status}_REQUEST_REJECTED')
                return result.get('result')
        except ProviderError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            raise ProviderError('TELEGRAM_REQUEST_FAILED') from None

    async def send(self, chat, text):
        # Plain text only; never interpolate secrets or accept provider text as markup.
        return await self.call('sendMessage', {'chat_id': chat, 'text': text[:3900], 'link_preview_options': {'is_disabled': True}})

    async def delete(self, chat, mid):
        try:
            await self.call('deleteMessage', {'chat_id': chat, 'message_id': mid})
        except ProviderError:
            pass

    async def document(self, chat, job_id, result, provider='appx'):
        form = aiohttp.FormData()
        form.add_field('chat_id', str(chat))
        form.add_field('caption', f'Export: {result.count} clear links. Skipped/unsupported: {result.skipped}. Treat signed links as private.')
        form.add_field('document', result.text.encode('utf-8'), filename=f'{provider}-{job_id}.txt', content_type='text/plain; charset=utf-8')
        return await self.call('sendDocument', form=form)

    async def menu(self, chat, text):
        from .ui import home_panel
        return await self.panel(chat, text, home_panel().rows)

    async def panel(self, chat, text, rows, message_id=None):
        payload = {'chat_id': chat, 'text': text[:3900],
                   'reply_markup': {'inline_keyboard': [list(row) for row in rows]},
                   'link_preview_options': {'is_disabled': True}}
        if isinstance(message_id, int) and not isinstance(message_id, bool) and message_id > 0:
            payload['message_id'] = message_id
            try:
                return await self.call('editMessageText', payload)
            except ProviderError as exc:
                # A rejected/inaccessible edit may open a fresh panel; never retry timeouts/429.
                if str(exc) != 'TELEGRAM_HTTP_400_REQUEST_REJECTED':
                    raise
                payload.pop('message_id', None)
        return await self.call('sendMessage', payload)
