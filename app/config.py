from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit

class ConfigError(ValueError):
    pass

@dataclass(frozen=True)
class Config:
    bot_token: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    public_url: str
    expected_username: str
    appx_hosts: frozenset[str]
    port: int = 10000
    set_webhook: bool = False
    owner_id: int = 0
    transport: str = 'botapi'
    telegram_api_id: int = field(default=0, repr=False)
    telegram_api_hash: str = field(default='', repr=False)
    mtproto_session: str = field(default='', repr=False)
    owner_ready_notice: bool = False
    startup_paused: bool = False
    classplus_otp_enabled: bool = False

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        token = e.get('BOT_TOKEN', '').strip()
        secret = e.get('WEBHOOK_SECRET', '').strip()
        username = e.get('EXPECTED_BOT_USERNAME', '').strip().lstrip('@')
        url = e.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
        hosts = frozenset(h.strip().lower() for h in e.get('APPX_API_HOSTS', '').split(',') if h.strip())
        if not re.fullmatch(r'\d{5,15}:[A-Za-z0-9_-]{20,}', token):
            raise ConfigError('BOT_TOKEN is required; use the NEW extractor bot token.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', secret):
            raise ConfigError('WEBHOOK_SECRET must be 32–128 URL-safe characters.')
        if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
            raise ConfigError('EXPECTED_BOT_USERNAME is required.')
        if username.lower() == 'turboforwarderpro_bot':
            raise ConfigError('Existing forwarding bot is explicitly protected. Use a different bot.')
        p = urlsplit(url)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/') or p.port not in (None, 443):
            raise ConfigError('PUBLIC_BASE_URL must be an HTTPS origin without path or credentials.')
        # Empty allowlist intentionally disables AppX until its coaching host is approved.
        for h in hosts:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', h) or '.' not in h or '..' in h or h.endswith('.') or all(c.isdigit() or c == '.' for c in h):
                raise ConfigError('APPX_API_HOSTS must contain bare DNS hostnames, not URLs/IPs.')
        try:
            port = int(e.get('PORT', '10000'))
        except ValueError:
            raise ConfigError('PORT must be a valid TCP port.') from None
        if not 1 <= port <= 65535:
            raise ConfigError('PORT must be a valid TCP port.')
        try:
            owner = int(e.get('OWNER_ID', '0'))
        except ValueError:
            raise ConfigError('OWNER_ID must be a numeric Telegram user ID.') from None
        if owner < 0:
            raise ConfigError('OWNER_ID cannot be negative.')
        transport = e.get('TELEGRAM_TRANSPORT', 'botapi').strip().lower()
        if transport not in ('botapi', 'mtproto'):
            raise ConfigError('TELEGRAM_TRANSPORT must be botapi or mtproto.')
        api_id, api_hash, bot_session = 0, '', ''
        if transport == 'mtproto':
            try:
                api_id = int(e.get('TELEGRAM_API_ID', '0'))
            except ValueError:
                raise ConfigError('TELEGRAM_API_ID must be numeric.') from None
            api_hash = e.get('TELEGRAM_API_HASH', '').strip()
            bot_session = e.get('TELEGRAM_BOT_SESSION', '').strip()
            if api_id <= 0 or not re.fullmatch(r'[a-fA-F0-9]{32}', api_hash) or not 100 <= len(bot_session) <= 2048:
                raise ConfigError('Explicit authorized bot-only MTProto credentials/session required.')
        return cls(token, secret, url, username, hosts, port, e.get('SET_WEBHOOK', 'false').lower() == 'true', owner,
                   transport, api_id, api_hash, bot_session, e.get('OWNER_READY_NOTICE', 'false').lower() == 'true',
                   e.get('TELEGRAM_START_PAUSED', 'false').lower() == 'true',
                   e.get('CLASSPLUS_OTP_ENABLED', 'false').lower() == 'true')
