import asyncio
import json
import re
import aiohttp
from ..provider_common import MAX_RESPONSE, Course, Export, ProviderError, safe_title, clear_url

class AppX:
    name = 'appx'
    def __init__(self, session, allowed_hosts, concurrency=3):
        self.session = session
        self.allowed_hosts = frozenset(allowed_hosts)
        self.semaphore = asyncio.Semaphore(concurrency)

    async def request(self, conn, path, params):
        if conn.host not in self.allowed_hosts or path not in ('mycoursev2', 'folder_contentsv2', 'allsubjectfrmlivecourseclass', 'alltopicfrmlivecourseclass', 'livecourseclassbycoursesubtopconceptapiv3'):
            raise ProviderError('APPX_HOST_OR_OPERATION_NOT_ALLOWED')
        headers = {'Client-Service': 'Appx', 'Auth-Key': 'appxapi', 'source': 'website',
                   'Authorization': conn.token, 'User-ID': conn.account_id}
        # Deliberately no retry for login/access errors and no redirects to other origins.
        async with self.semaphore:
            try:
                async with self.session.get(f'https://{conn.host}/get/{path}', params=params,
                        headers=headers, allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=25, connect=8, sock_read=15)) as resp:
                    if resp.status in (401, 403):
                        raise ProviderError('APPX_ACCESS_DENIED_RECONNECT')
                    if resp.status == 429:
                        raise ProviderError('APPX_RATE_LIMITED_TRY_LATER')
                    if resp.status != 200:
                        raise ProviderError('APPX_UNAVAILABLE')
                    chunks, size = [], 0
                    async for chunk in resp.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise ProviderError('APPX_RESPONSE_TOO_LARGE')
                        chunks.append(chunk)
                    data = json.loads(b''.join(chunks))
                    if not isinstance(data, dict):
                        raise ProviderError('APPX_SCHEMA_UNSUPPORTED')
                    status = data.get('status')
                    if status not in (None, 200, '200'):
                        raise ProviderError('APPX_REJECTED_REQUEST')
                    return data
            except ProviderError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
                raise ProviderError('APPX_REQUEST_FAILED') from None

    async def courses(self, conn):
        result = await self.request(conn, 'mycoursev2', {'userid': conn.account_id})
        rows = result.get('data')
        if not isinstance(rows, list):
            raise ProviderError('APPX_COURSE_SCHEMA_UNSUPPORTED')
        if len(rows) > 500:
            raise ProviderError('APPX_COURSE_LIMIT_EXCEEDED')
        courses = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ProviderError('APPX_COURSE_SCHEMA_UNSUPPORTED')
            cid = str(row.get('id', ''))
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', cid):
                continue
            courses[cid] = Course(cid, safe_title(row.get('course_name')), str(row.get('folder_wise_course')) == '1')
        return list(courses.values())

    async def export(self, conn, course_id, cancelled, progress=None):
        # Re-fetch user's purchased list for every job. Never trust a pasted course ID alone.
        course = next((c for c in await self.courses(conn) if c.id == course_id), None)
        if not course:
            raise ProviderError('COURSE_NOT_IN_YOUR_ACCOUNT')
        if not course.folder_mode:
            return await self.export_flat(conn, course_id, cancelled, progress)
        pending, visited = [('-1', 0)], set()
        lines, seen, skipped, out_size = [], set(), 0, 0
        while pending:
            if cancelled.is_set():
                raise ProviderError('JOB_CANCELLED')
            folder_id, depth = pending.pop(0)
            if folder_id in visited:
                continue
            if depth > 12 or len(visited) >= 120:
                raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
            visited.add(folder_id)
            result = await self.request(conn, 'folder_contentsv2', {'course_id': course_id, 'parent_id': folder_id})
            rows = result.get('data')
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ProviderError('APPX_FOLDER_SCHEMA_OR_LIMIT_UNSUPPORTED')
            for row in rows:
                if not isinstance(row, dict):
                    raise ProviderError('APPX_FOLDER_SCHEMA_OR_LIMIT_UNSUPPORTED')
                kind = str(row.get('material_type', '')).upper()
                if kind == 'FOLDER':
                    fid = str(row.get('id', ''))
                    if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', fid):
                        pending.append((fid, depth + 1))
                    else:
                        skipped += 1
                    continue
                title = safe_title(row.get('Title') or row.get('title'))
                found = False
                # Only URLs already present in authorized folder response; encrypted fields skipped.
                for key in ('download_link', 'pdf_link', 'pdf_link2', 'url'):
                    url = clear_url(row.get(key))
                    if not url:
                        continue
                    found = True
                    if url in seen:
                        continue
                    seen.add(url)
                    line = f'{title}: {url}'
                    out_size += len(line.encode('utf-8')) + 1
                    if len(lines) >= 5000 or out_size > 2 * 1024 * 1024:
                        raise ProviderError('EXPORT_SIZE_LIMIT_EXCEEDED')
                    lines.append(line)
                if not found:
                    skipped += 1
            if len(pending) > 500:
                raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
            if progress:
                await progress(len(visited), len(lines))
        if not lines:
            raise ProviderError('NO_CLEAR_AUTHORIZED_LINKS_FOUND')
        return Export('\n'.join(lines) + '\n', len(lines), skipped)


    async def export_flat(self, conn, course_id, cancelled, progress=None):
        """Already-entitled flat course: subjects -> topics -> clear metadata links.
        No detail/key/decryption endpoints. Schemas are reference-informed, live-unverified.
        """
        async def rows(path, params):
            if cancelled.is_set():
                raise ProviderError('JOB_CANCELLED')
            result = await self.request(conn, path, params)
            values = result.get('data')
            if not isinstance(values, list) or len(values) > 1000 or any(not isinstance(r, dict) for r in values):
                raise ProviderError('APPX_FLAT_SCHEMA_UNSUPPORTED')
            return values
        base = {'courseid': course_id, 'start': -1}
        subjects = await rows('allsubjectfrmlivecourseclass', base)
        if len(subjects) > 100:
            raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
        seen_topics, urls = set(), set()
        lines, skipped, size = [], 0, 0
        for subject in subjects:
            sid = str(subject.get('subjectid', ''))
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', sid):
                raise ProviderError('APPX_FLAT_SCHEMA_UNSUPPORTED')
            topics = await rows('alltopicfrmlivecourseclass', {**base, 'subjectid': sid})
            for topic in topics:
                tid = str(topic.get('topicid', ''))
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', tid):
                    raise ProviderError('APPX_FLAT_SCHEMA_UNSUPPORTED')
                if (sid, tid) in seen_topics:
                    continue
                if len(seen_topics) >= 120:
                    raise ProviderError('COURSE_TRAVERSAL_LIMIT_EXCEEDED')
                seen_topics.add((sid, tid))
                items = await rows('livecourseclassbycoursesubtopconceptapiv3',
                    {**base, 'subjectid': sid, 'topicid': tid, 'conceptid': ''})
                for item in items:
                    found = False
                    for key in ('download_link', 'pdf_link', 'pdf_link2', 'url'):
                        url = clear_url(item.get(key))
                        if not url:
                            continue
                        found = True
                        if url in urls:
                            continue
                        urls.add(url)
                        line = f"{safe_title(item.get('Title') or item.get('title'))}: {url}"
                        size += len(line.encode('utf-8')) + 1
                        if len(lines) >= 5000 or size > 2 * 1024 * 1024:
                            raise ProviderError('EXPORT_SIZE_LIMIT_EXCEEDED')
                        lines.append(line)
                    if not found:
                        skipped += 1
                if progress:
                    await progress(len(seen_topics), len(lines))
        if not lines:
            raise ProviderError('NO_CLEAR_AUTHORIZED_LINKS_FOUND')
        return Export('\n'.join(lines) + '\n', len(lines), skipped)
