"""Stable public adapter imports; no account state in provider instances."""
from .provider_common import (MAX_RESPONSE, Course, Export, ProviderError, PublicResolver, clear_url, safe_title)
from .adapters.appx import AppX
from .adapters.classplus import Classplus

__all__ = ['MAX_RESPONSE', 'Course', 'Export', 'ProviderError', 'PublicResolver', 'clear_url', 'safe_title', 'AppX', 'Classplus', 'ProviderRouter']

class ProviderRouter:
    def __init__(self, providers):
        self.providers = dict(providers)

    def adapter(self, name):
        provider = self.providers.get(name)
        if provider is None:
            raise ProviderError('PROVIDER_NOT_ENABLED')
        return provider

    async def export(self, conn, course_id, cancelled, progress=None):
        return await self.adapter(conn.provider).export(conn, course_id, cancelled, progress)
