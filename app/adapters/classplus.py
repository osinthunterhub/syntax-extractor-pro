"""Reference-informed Classplus adapter. Mock-tested; NOT live/API-contract verified.
Uses only the initiating user's token and entitled course list. No shared auth headers,
OTP/account registration, public-store scraping, key/decryption or signing endpoint.
"""
import asyncio
import json
import re
import aiohttp
from ..provider_common import MAX_RESPONSE, Course, Export, ProviderError, clear_url, safe_title

class Classplus:
    name = 'classplus'
    def __init__(self, session):
        self.session = session
        self.semaphore = asyncio.Semaphore(3)

    async def request(self, conn, operation, params):
        paths = {'courses': '/v2/courses', 'content': '/v2/course/content/get'}
        if conn.provider != 'classplus' or conn.host != 'api.classplusapp.com' or operation not in paths:
            raise ProviderError('CLASSPLUS_HOST_OR_OPERATION_NOT_ALLOWED')
        headers = {'x-access-token': conn.token, 'Accept': 'application/json'}
        async with self.semaphore:
            try:
                async with self.session.get('https://api.classplusapp.com' + paths[operation],
                        params=params, headers=headers, allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=25, connect=8, sock_read=15)) as response:
                    if response.status in (401, 403):
                        raise ProviderError('CLASSPLUS_ACCESS_DENIED_RECONNECT')
                    if response.status == 429:
                        raise ProviderError('CLASSPLUS_RATE_LIMITED_TRY_LATER')
                    if response.status != 200:
                        raise ProviderError('CLASSPLUS_UNAVAILABLE')
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise ProviderError('CLASSPLUS_RESPONSE_TOO_LARGE')
                        chunks.append(chunk)
                    result = json.loads(b''.join(chunks))
                    if not isinstance(result, dict) or result.get('status') in ('failure', 'error', False):
                        raise ProviderError('CLASSPLUS_REQUEST_REJECTED')
                    return result
            except ProviderError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
                raise ProviderError('CLASSPLUS_REQUEST_FAILED') from None

    async def pages(self, conn, operation, base, key):
        output, signatures = [], set()
        for page in range(12):
            result = await self.request(conn, operation, {**base, 'limit': 100, 'offset': page * 100})
            data = result.get('data')
            rows = data.get(key) if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) > 1000 or any(not isinstance(r, dict) for r in rows):
                raise ProviderError('CLASSPLUS_SCHEMA_UNSUPPORTED')
            signature = tuple(str(r.get('id', '')) for r in rows)
            if rows and signature in signatures:
                raise ProviderError('CLASSPLUS_PAGINATION_REPEATED')
            signatures.add(signature)
            output.extend(rows)
            if len(output) > 1000:
                raise ProviderError('CLASSPLUS_PAGE_LIMIT_EXCEEDED')
            more = data.get('hasMore')
            if more is False or not rows:
                return output
            if more is not True and len(rows) < 100:
                return output
            if more is not True:
                raise ProviderError('CLASSPLUS_PAGINATION_UNKNOWN_NOT_CLAIMING_COMPLETE')
        raise ProviderError('CLASSPLUS_PAGE_LIMIT_EXCEEDED')

    async def courses(self, conn):
        rows = await self.pages(conn, 'courses', {'tabCategoryId': 1}, 'courses')
        result = {}
        for row in rows:
            cid = str(row.get('id', ''))
            if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', cid):
                flags = [row[k] for k in ('isPurchased', 'isEnrolled') if k in row]
                if not flags:
                    # Account-scoped listing alone is not proof that a store course is entitled.
                    raise ProviderError('CLASSPLUS_ENTITLEMENT_SCHEMA_UNVERIFIED')
                if not any(value in (True, 1, '1', 'true') for value in flags):
                    continue
                result[cid] = Course(cid, safe_title(row.get('name')), True)
        return list(result.values())

    async def export(self, conn, course_id, cancelled, progress=None):
        if not any(c.id == course_id for c in await self.courses(conn)):
            raise ProviderError('COURSE_NOT_IN_YOUR_ACCOUNT')
        pending, visited = [('0', 0)], set()
        lines, seen, skipped, size = [], set(), 0, 0
        while pending:
            if cancelled.is_set():
                raise ProviderError('JOB_CANCELLED')
            folder, depth = pending.pop(0)
            if folder in visited:
                continue
            if depth > 12 or len(visited) >= 120:
                raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
            visited.add(folder)
            rows = await self.pages(conn, 'content', {'courseId': course_id, 'folderId': folder}, 'courseContent')
            for row in rows:
                if str(row.get('contentType')) == '1':
                    fid = str(row.get('id', ''))
                    if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', fid):
                        pending.append((fid, depth + 1))
                    else:
                        skipped += 1
                    continue
                protected = any(row.get(k) in (True, 1, '1', 'true') for k in ('isDrm', 'isDRM', 'isEncrypted'))
                url = None if protected else clear_url(row.get('url'))
                if not url:
                    skipped += 1
                    continue
                if url in seen:
                    continue
                seen.add(url)
                line = f"{safe_title(row.get('name'))}: {url}"
                size += len(line.encode('utf-8')) + 1
                if len(lines) >= 5000 or size > 2 * 1024 * 1024:
                    raise ProviderError('EXPORT_SIZE_LIMIT_EXCEEDED')
                lines.append(line)
            if len(pending) > 500:
                raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
            if progress:
                await progress(len(visited), len(lines))
        if not lines:
            raise ProviderError('NO_CLEAR_AUTHORIZED_LINKS_FOUND')
        return Export('\n'.join(lines) + '\n', len(lines), skipped)
