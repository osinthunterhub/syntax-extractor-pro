import asyncio
import json
from types import SimpleNamespace as NS
import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Config, ConfigError
from app.state import State, Connection
from app.providers import AppX, Course, Export, ProviderError, clear_url, safe_title
from app.jobs import Jobs
from app.web import Bot, create_app


def run(coro):
    return asyncio.run(coro)


def env():
    return {'BOT_TOKEN': '123456:' + 'a' * 30, 'WEBHOOK_SECRET': 's' * 40,
            'PUBLIC_BASE_URL': 'https://new-extractor.example.invalid',
            'EXPECTED_BOT_USERNAME': 'IndependentTestBot', 'APPX_API_HOSTS': 'academy.example.invalid'}


def test_config_no_defaults():
    with pytest.raises(ConfigError):
        Config.from_env({})


def test_existing_forwarder_blocked():
    e = env(); e['EXPECTED_BOT_USERNAME'] = 'TurboForwarderPro_Bot'
    with pytest.raises(ConfigError):
        Config.from_env(e)


def test_config_repr_hides_secrets():
    e = env(); c = Config.from_env(e)
    assert e['BOT_TOKEN'] not in repr(c)
    assert e['WEBHOOK_SECRET'] not in repr(c)


@pytest.mark.parametrize('bad', ['http://host.example', 'localhost', '127.0.0.1', 'host.example/path', 'a..example'])
def test_host_config_rejects(bad):
    e = env(); e['APPX_API_HOSTS'] = bad
    with pytest.raises(ConfigError):
        Config.from_env(e)


def test_user_connections_isolated():
    s = State(); a = Connection('a.example', '1', 'secret-a'); b = Connection('b.example', '2', 'secret-b')
    s.put(1, a); s.put(2, b)
    assert s.get(1) is a and s.get(2) is b
    assert 'secret-a' not in repr(a)
    s.drop(1); assert s.get(1) is None and s.get(2) is b


def test_session_expiry_and_capacity():
    s = State(max_users=1); s.put(1, Connection('a.example', '1', 'a'))
    with pytest.raises(ValueError): s.put(2, Connection('b.example', '2', 'b'))
    s.connections[(1, 'appx')] = (0, Connection('a.example', '1', 'a')); assert s.get(1) is None
    s.put(2, Connection('b.example', '2', 'b')); assert s.get(2).token == 'b'


def test_update_dedup_bounded():
    s = State(); assert s.mark_seen(1); assert not s.mark_seen(1)
    for i in range(3000): s.mark_seen(i)
    assert len(s.seen) == 2000


@pytest.mark.parametrize('value', ['http://example.invalid/a', 'https://127.0.0.1/a', 'https://u:p@example.invalid/a', 'javascript:alert(1)', 'https://example.invalid/a.mpd', 'encrypted-not-a-url', 'https://example.invalid/a\ncmd'])
def test_unsafe_or_protected_link_not_exported(value):
    assert clear_url(value) is None


def test_title_and_clear_link():
    assert safe_title('हिन्दी\nपाठ:1') == 'हिन्दीपाठ 1'
    assert clear_url('https://cdn.example.invalid/notes.pdf?sig=demo') is not None


class FakeAppX(AppX):
    def __init__(self, courses=None, folders=None):
        super().__init__(None, {'academy.example.invalid'})
        self.course_rows = courses if courses is not None else [{'id': 5, 'course_name': 'हिन्दी', 'folder_wise_course': 1}]
        self.folders, self.calls = folders or {}, []

    async def request(self, conn, path, params):
        self.calls.append((conn.account_id, path, params))
        if path == 'mycoursev2': return {'data': self.course_rows}
        if path == 'folder_contentsv2':
            return {'data': self.folders.get(params['parent_id'], [])}
        return {'data': []}


def conn():
    return Connection('academy.example.invalid', '42', 'test-token-only')


def test_numeric_ids_normalized():
    async def case():
        courses = await FakeAppX().courses(conn())
        assert courses[0].id == '5' and courses[0].folder_mode
    run(case())


def test_entitlement_rechecked_before_traversal():
    async def case():
        p = FakeAppX()
        with pytest.raises(ProviderError, match='COURSE_NOT_IN_YOUR_ACCOUNT'):
            await p.export(conn(), '999', asyncio.Event())
        assert [x[1] for x in p.calls] == ['mycoursev2']
    run(case())


def test_export_dedup_cycles_and_encrypted_skip():
    async def case():
        p = FakeAppX(folders={
            '-1': [{'id': 1, 'material_type': 'FOLDER'}, {'Title': 'PDF', 'pdf_link': 'https://cdn.example.invalid/a.pdf'}, {'Title': 'Protected', 'download_link': 'encrypted'}],
            '1': [{'id': 1, 'material_type': 'FOLDER'}, {'Title': 'Duplicate', 'url': 'https://cdn.example.invalid/a.pdf'}]})
        result = await p.export(conn(), '5', asyncio.Event())
        assert result.count == 1 and result.skipped == 1
        assert result.text == 'PDF: https://cdn.example.invalid/a.pdf\n'
        assert len(p.calls) == 3
    run(case())


def test_export_cancelled_and_empty_flat_mode():
    async def case():
        stop = asyncio.Event(); stop.set()
        with pytest.raises(ProviderError, match='JOB_CANCELLED'):
            await FakeAppX().export(conn(), '5', stop)
        p = FakeAppX(courses=[{'id': '5', 'folder_wise_course': 0}])
        with pytest.raises(ProviderError, match='NO_CLEAR'):
            await p.export(conn(), '5', asyncio.Event())
    run(case())


def test_empty_export_not_success():
    async def case():
        with pytest.raises(ProviderError, match='NO_CLEAR'):
            await FakeAppX().export(conn(), '5', asyncio.Event())
    run(case())


def test_jobs_capacity_duplicate_and_cancel():
    async def case():
        async def noop(*args): pass
        jobs = Jobs(FakeAppX(), noop, noop, capacity=1)
        j = jobs.submit(1, 1, conn(), '5')
        with pytest.raises(ProviderError, match='ALREADY'): jobs.submit(1, 1, conn(), '5')
        with pytest.raises(ProviderError, match='QUEUE_FULL'): jobs.submit(2, 2, conn(), '5')
        assert jobs.cancel(1) and j.cancelled.is_set()
        assert not jobs.cancel(2)
    run(case())


def test_job_worker_delivers_and_cleans_active():
    async def case():
        p = FakeAppX(folders={'-1': [{'Title': 'PDF', 'url': 'https://cdn.example.invalid/a.pdf'}]})
        delivered = []
        async def notify(*args): pass
        async def deliver(job, result): delivered.append((job.user_id, result.count))
        jobs = Jobs(p, deliver, notify)
        jobs.start(); jobs.submit(1, 1, conn(), '5')
        await asyncio.wait_for(jobs.queue.join(), 1)
        assert delivered == [(1, 1)] and not jobs.active
        await jobs.close()
    run(case())


class TG:
    def __init__(self): self.sent, self.deleted = [], []
    async def send(self, chat, text): self.sent.append((chat, text))
    async def delete(self, chat, mid): self.deleted.append((chat, mid))
    async def document(self, *args): pass


def update(text, uid=1, chat_type='private', chat_id=None, update_id=1):
    return {'update_id': update_id, 'message': {'message_id': 7, 'text': text, 'from': {'id': uid}, 'chat': {'id': chat_id if chat_id is not None else uid, 'type': chat_type}}}


def test_group_credentials_never_reach_provider():
    async def case():
        t, p = TG(), FakeAppX(); b = Bot(Config.from_env(env()), t, p)
        await b.handle(update('/connect academy.example.invalid 42 secret-token', chat_type='group', chat_id=-10))
        assert not p.calls and t.deleted == [(-10, 7)]
        assert 'secret-token' not in str(t.sent)
    run(case())


def test_connect_no_secret_echo_and_per_user_state():
    async def case():
        t, p = TG(), FakeAppX(); b = Bot(Config.from_env(env()), t, p)
        await b.handle(update('/connect academy.example.invalid 42 first-token'))
        await b.handle(update('/connect academy.example.invalid 43 second-token', uid=2))
        assert b.state.get(1).account_id == '42' and b.state.get(2).account_id == '43'
        assert 'first-token' not in str(t.sent) and 'second-token' not in str(t.sent)
        assert len(t.deleted) == 2
    run(case())


def test_classplus_separate_menu():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, FakeAppX())
        await b.handle(update('/classplus'))
        assert 'Classplus' in t.sent[-1][1] and b.selected[1] == 'classplus'
    run(case())


def test_webhook_auth_validation_dedup_and_queue_limit():
    async def case():
        c = Config.from_env(env()); b = Bot(c, TG(), FakeAppX())
        async with TestClient(TestServer(create_app(c, b))) as client:
            r = await client.post('/telegram/webhook', json=update('/help')); assert r.status == 401
            headers = {'X-Telegram-Bot-Api-Secret-Token': c.webhook_secret}
            r = await client.post('/telegram/webhook', data='{', headers=headers); assert r.status == 400
            r = await client.post('/telegram/webhook', json=update('/help'), headers=headers); assert r.status == 200
            r = await client.post('/telegram/webhook', json=update('/help'), headers=headers); assert r.status == 200
            assert b.updates.qsize() == 1
            for i in range(2, 33):
                r = await client.post('/telegram/webhook', json=update('/help', update_id=i), headers=headers)
                assert r.status == 200
            r = await client.post('/telegram/webhook', json=update('/help', update_id=33), headers=headers)
            assert r.status == 503 and 33 not in b.state.seen
            r = await client.get('/healthz'); data = await r.json()
            assert data['persistent_jobs'] is False and 'process-alive' == data['status']
    run(case())


def test_job_deadline_and_queued_cancellation():
    async def case():
        notified, deliveries = [], []
        class Slow:
            async def export(self, *args): await asyncio.sleep(10)
        async def notify(job, text): notified.append(text)
        async def deliver(*args): deliveries.append(args)
        jobs = Jobs(Slow(), deliver, notify, deadline=0.01)
        jobs.submit(1, 1, conn(), '5'); jobs.submit(2, 2, conn(), '5'); jobs.cancel(2)
        jobs.start()
        await asyncio.wait_for(jobs.queue.join(), 1)
        assert 'JOB_TIME_LIMIT_EXCEEDED' in notified and 'JOB_CANCELLED' in notified
        assert not deliveries and not jobs.active
        await jobs.close()
    run(case())


def test_deep_folders_are_bounded():
    async def case():
        folders = {'-1': [{'id': '0', 'material_type': 'FOLDER'}]}
        folders.update({str(i): [{'id': str(i+1), 'material_type': 'FOLDER'}] for i in range(20)})
        with pytest.raises(ProviderError, match='TRAVERSAL_LIMIT'):
            await FakeAppX(folders=folders).export(conn(), '5', asyncio.Event())
    run(case())


def test_invalid_course_schema_fails_closed():
    async def case():
        with pytest.raises(ProviderError, match='SCHEMA'):
            await FakeAppX(courses=['unexpected']).courses(conn())
    run(case())


class Response:
    def __init__(self, status, payload=b'{}', error=None):
        self.status, self.content, self.payload, self.error = status, self, payload, error
    async def __aenter__(self):
        if self.error: raise self.error
        return self
    async def __aexit__(self, *args): pass
    async def iter_chunked(self, n):
        # Streaming chunk simulation: not a full response read.
        for i in range(0, len(self.payload), n): yield self.payload[i:i+n]


class Session:
    def __init__(self, response): self.response, self.calls = response, []
    def get(self, url, **kwargs): self.calls.append((url, kwargs)); return self.response
    def post(self, url, **kwargs): self.calls.append((url, kwargs)); return self.response


@pytest.mark.parametrize('status,code', [(302,'UNAVAILABLE'), (401,'ACCESS_DENIED'), (403,'ACCESS_DENIED'), (429,'RATE_LIMITED'), (500,'UNAVAILABLE')])
def test_provider_http_failures_not_retried(status, code):
    async def case():
        session = Session(Response(status))
        with pytest.raises(ProviderError, match=code): await AppX(session, {conn().host}).courses(conn())
        assert len(session.calls) == 1 and session.calls[0][1]['allow_redirects'] is False
    run(case())


def test_provider_response_cap_and_host_gate():
    async def case():
        session = Session(Response(200, b'x' * (2 * 1024 * 1024 + 1)))
        with pytest.raises(ProviderError, match='TOO_LARGE'): await AppX(session, {conn().host}).courses(conn())
        session.calls.clear()
        with pytest.raises(ProviderError, match='NOT_ALLOWED'): await AppX(session, set()).courses(conn())
        assert not session.calls
    run(case())


def test_provider_exception_details_not_leaked():
    async def case():
        import aiohttp
        session = Session(Response(200, error=aiohttp.ClientError('test-secret-never-repeat')))
        with pytest.raises(ProviderError) as caught:
            await AppX(session, {conn().host}).courses(conn())
        assert str(caught.value) == 'APPX_REQUEST_FAILED' and 'test-secret' not in str(caught.value)
    run(case())


def test_dns_private_destination_rejected():
    async def case():
        from app.providers import PublicResolver
        resolver = PublicResolver()
        # Replace resolver before DNS: no real DNS/network request.
        original = resolver.inner
        class Inner:
            async def resolve(self, *args): return [{'host': '127.0.0.1'}]
            async def close(self): pass
        resolver.inner = Inner()
        with pytest.raises(OSError, match='NON_PUBLIC'): await resolver.resolve('example.invalid', 443)
        await resolver.close(); await original.close()
    run(case())


def test_telegram_streaming_and_redacted_error():
    async def case():
        from app.telegram import Telegram
        import aiohttp
        session = Session(Response(200, b'{"ok":true,"result":{"id":123}}'))
        assert await Telegram(session, 'synthetic-token').call('getMe') == {'id':123}
        session = Session(Response(200, error=aiohttp.ClientError('synthetic-token')))
        with pytest.raises(ProviderError) as caught: await Telegram(session, 'synthetic-token').call('getMe')
        assert str(caught.value) == 'TELEGRAM_REQUEST_FAILED'
    run(case())
