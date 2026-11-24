"""Shared safe provider models, URL filters and public-only DNS resolver.
No embedded accounts, decryption, DRM/key processing, entitlement bypass or media download.
"""
from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlsplit
import aiohttp
from aiohttp.abc import AbstractResolver

MAX_RESPONSE = 2 * 1024 * 1024

class ProviderError(Exception):
    """Messages are safe public error codes, never raw URLs/responses/tokens."""

class PublicResolver(AbstractResolver):
    def __init__(self):
        self.inner = aiohttp.resolver.ThreadedResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        answers = await self.inner.resolve(host, port, family)
        if not answers:
            raise OSError('DNS_EMPTY')
        for answer in answers:
            try:
                if not ipaddress.ip_address(answer['host']).is_global:
                    raise OSError('NON_PUBLIC_DESTINATION')
            except ValueError:
                raise OSError('INVALID_DNS_ANSWER') from None
        return answers

    async def close(self):
        await self.inner.close()

@dataclass(frozen=True)
class Course:
    id: str
    name: str
    folder_mode: bool

@dataclass
class Export:
    text: str
    count: int
    skipped: int


def safe_title(value):
    s = ''.join(c for c in str(value or 'Untitled') if c.isprintable()).replace(':', ' ').strip()
    return s[:160] or 'Untitled'


def clear_url(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        return None
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        if p.hostname in ('localhost',) or p.hostname.endswith(('.local', '.internal')):
            return None
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                return None
        except ValueError:
            if '.' not in p.hostname:
                return None
        # Protected manifests are deliberately not processed by this MVP.
        if p.path.lower().endswith(('.mpd', '.videoid', '.testbook')):
            return None
        return value
    except ValueError:
        return None

