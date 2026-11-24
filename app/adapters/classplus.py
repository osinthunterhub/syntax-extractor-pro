"""Reference-compatible Classplus account adapter, not live-account certified.
Uses only the initiating user's token and exact authenticated My Courses route. No shared auth headers,
OTP/account registration, public-store scraping, key/decryption or signing endpoint.
"""
import asyncio
import json
import re
import aiohttp
from ..provider_common import MAX_RESPONSE, Course, Export, ProviderError, clear_url, safe_title, protected_row

class Classplus:
    name = 'classplus'
    def __init__(self, session):
        self.session = session
        self.semaphore = asyncio.Semaphore(3)

    async def request(self, conn, operation, params):
        paths = {'courses': '/v2/courses', 'content': '/v2/course/content/get'}
        if conn.provider != 'classplus' or conn.host != 'api.classplusapp.com' or operation not in paths:
            raise ProviderError('CLASSPLUS_HOST_OR_OPERATION_NOT_ALLOWED')
        # Version29 comes from the pinned reference's student course requests.
        # No shared headers, hardcoded device ID or copied app-account credentials.
        headers = {'x-access-token': conn.token, 'Accept': 'application/json', 'Api-Version': '29'}
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
                    if not isinstance(result, dict):
                        raise ProviderError('CLASSPLUS_SCHEMA_UNSUPPORTED')
                    status = result.get('status')
                    if status is not None and status not in ('success', 'SUCCESS', 200, '200', True):
                        raise ProviderError('CLASSPLUS_REQUEST_REJECTED')
                    return result
            except ProviderError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
                raise ProviderError('CLASSPLUS_REQUEST_FAILED') from None

    async def pages(self, conn, operation, base, key):
        output, signatures, expected_total = [], set(), None
        for page in range(12):
            result = await self.request(conn, operation, {**base, 'limit': 100, 'offset': len(output)})
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
            if 'totalCount' in data:
                total = data['totalCount']
                if isinstance(total, bool) or not str(total).isdigit() or int(total) > 1000:
                    raise ProviderError('CLASSPLUS_PAGINATION_METADATA_UNSUPPORTED')
                total = int(total)
                if expected_total is not None and total != expected_total:
                    raise ProviderError('CLASSPLUS_COURSE_CONTENT_CHANGED_RETRY')
                expected_total = total
            more = self.flag(data['hasMore']) if 'hasMore' in data else None
            if expected_total is not None:
                if len(output) > expected_total or more is False and len(output) != expected_total:
                    raise ProviderError('CLASSPLUS_PAGINATION_INCOMPLETE')
                if len(output) == expected_total:
                    if more is True:
                        raise ProviderError('CLASSPLUS_PAGINATION_METADATA_UNSUPPORTED')
                    return output
                if not rows:
                    raise ProviderError('CLASSPLUS_PAGINATION_INCOMPLETE')
                continue
            if not rows:
                if more is True:
                    raise ProviderError('CLASSPLUS_PAGINATION_INCOMPLETE')
                return output
            if more is False:
                return output
            if more is None and len(rows) < 100:
                return output
            if more is None:
                raise ProviderError('CLASSPLUS_PAGINATION_UNKNOWN_NOT_CLAIMING_COMPLETE')
        raise ProviderError('CLASSPLUS_PAGE_LIMIT_EXCEEDED')

    @staticmethod
    def flag(value):
        if value is True or value == 1 or isinstance(value, str) and value.strip().lower() in ('true', '1', 'yes'):
            return True
        if value is False or value == 0 or isinstance(value, str) and value.strip().lower() in ('false', '0', 'no'):
            return False
        raise ProviderError('CLASSPLUS_ACCESS_FLAG_SCHEMA_UNSUPPORTED')

    @classmethod
    def denied(cls, row):
        for key in ('isLocked', 'isBlocked'):
            if key in row and cls.flag(row[key]):
                return True
        for key in ('canAccess', 'isAccessible'):
            if key in row and not cls.flag(row[key]):
                return True
        return False

    async def courses(self, conn):
        rows = await self.pages(conn, 'courses', {'tabCategoryId': 1}, 'courses')
        if len(rows) > 500:
            raise ProviderError('CLASSPLUS_COURSE_LIMIT_EXCEEDED_NO_TRUNCATION')
        result = {}
        for row in rows:
            cid = str(row.get('id', ''))
            if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', cid):
                # The reference's exact account-list route returns id/name without
                # guaranteed purchase flags. Never require invented mandatory fields.
                # This is NOT the /store catalog route and no arbitrary ID is trusted.
                if self.denied(row):
                    continue
                flags = [self.flag(row[k]) for k in ('isPurchased', 'isEnrolled') if k in row]
                if flags and not any(flags):
                    continue
                result[cid] = Course(cid, safe_title(row.get('name')), True)
        return list(result.values())

    async def export(self, conn, course_id, cancelled, progress=None):
        if not any(c.id == course_id for c in await self.courses(conn)):
            raise ProviderError('COURSE_NOT_IN_YOUR_ACCOUNT')
        pending, visited = [('0', 0, '')], set()
        lines, seen, skipped, size = [], set(), 0, 0
        while pending:
            if cancelled.is_set():
                raise ProviderError('JOB_CANCELLED')
            folder, depth, folder_path = pending.pop(0)
            if folder in visited:
                continue
            if depth > 12 or len(visited) >= 120:
                raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
            visited.add(folder)
            rows = await self.pages(conn, 'content', {'courseId': course_id, 'folderId': folder}, 'courseContent')
            for row in rows:
                if self.denied(row):
                    skipped += 1
                    continue
                title = safe_title(row.get('name'))
                if str(row.get('contentType')) == '1':
                    fid = str(row.get('id', ''))
                    if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', fid):
                        pending.append((fid, depth + 1, safe_title(folder_path + title) + ' / '))
                    else:
                        skipped += 1
                    continue
                # Hash/signing metadata is not a playable clear link contract.
                protected = protected_row(row) or bool(row.get('contentHashId'))
                url = None if protected else clear_url(row.get('url'))
                if not url:
                    skipped += 1
                    continue
                if url in seen:
                    continue
                seen.add(url)
                line = f"{safe_title(folder_path + title)}: {url}"
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
