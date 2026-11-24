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



def protected_row(row):
    """Explicit protected flags fail closed, including case-insensitive API strings."""
    for key in ('isDrm', 'isDRM', 'isEncrypted', 'is_encrypted', 'is_drm'):
        value = row.get(key)
        if value is True or value == 1 or isinstance(value, str) and value.strip().lower() in ('1', 'true', 'yes'):
            return True
    return False


def complete_appx_rows(result, error, limit=1000):
    """Never label a known partial response as a complete export; no guessed pagination."""
    rows = result.get('data')
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, dict) for row in rows):
        raise ProviderError(error)
    containers = [result]
    for key in ('pagination', 'meta'):
        if isinstance(result.get(key), dict):
            containers.append(result[key])
    for meta in containers:
        if any(meta.get(key) in (True, 1, '1', 'true') for key in ('hasMore', 'has_more', 'hasNextPage')):
            raise ProviderError('APPX_PAGINATION_UNVERIFIED_NOT_CLAIMING_COMPLETE')
        for key in ('total', 'totalCount', 'total_count'):
            value = meta.get(key)
            if value is not None:
                if isinstance(value, bool) or not str(value).isdigit() or int(value) != len(rows):
                    raise ProviderError('APPX_PAGINATION_UNVERIFIED_NOT_CLAIMING_COMPLETE')
    return rows
