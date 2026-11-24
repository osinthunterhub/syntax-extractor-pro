import asyncio
import json
import aiohttp
from .providers import ProviderError

class Telegram:
    def __init__(self, session, token):
        self.session, self._token = session, token

    async def call(self, method, payload=None, form=None):
        if method not in {'getMe', 'sendMessage', 'sendDocument', 'deleteMessage', 'setWebhook', 'getChat', 'getChatMember', 'answerCallbackQuery', 'setMyCommands'}:
            raise ProviderError('TELEGRAM_OPERATION_NOT_ALLOWED')
        try:
            # No access logging, no exception text, no token-bearing URLs in diagnostics.
            async with self.session.post(f'https://api.telegram.org/bot{self._token}/{method}',
                    json=payload if form is None else None, data=form,
                    allow_redirects=False, timeout=aiohttp.ClientTimeout(total=35, connect=8)) as response:
                if response.status != 200:
                    raise ProviderError('TELEGRAM_REQUEST_REJECTED')
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(16384):
                    size += len(chunk)
                    if size > 262144:
                        raise ProviderError('TELEGRAM_RESPONSE_TOO_LARGE')
                    chunks.append(chunk)
                result = json.loads(b''.join(chunks))
                if not result.get('ok'):
                    raise ProviderError('TELEGRAM_REQUEST_REJECTED')
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
        keyboard = {'inline_keyboard': [
            [{'text': '🔷 AppX', 'callback_data': 'provider:appx'}, {'text': '🟣 Classplus', 'callback_data': 'provider:classplus'}],
            [{'text': '📚 My courses', 'callback_data': 'nav:courses'}, {'text': '📤 Destination', 'callback_data': 'nav:destination'}],
            [{'text': '📊 Job status', 'callback_data': 'nav:status'}, {'text': '❔ Help', 'callback_data': 'nav:help'}]]}
        return await self.call('sendMessage', {'chat_id': chat, 'text': text[:3900], 'reply_markup': keyboard})
