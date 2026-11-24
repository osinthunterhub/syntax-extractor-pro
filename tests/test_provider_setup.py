"""Synthetic setup/integration regression tests. NOT live provider-account evidence."""
import asyncio
from types import SimpleNamespace as NS
import pytest
from app.conversation import Conversations
from app.providers import AppX, ProviderError, Course
from app.provider_common import complete_appx_rows, protected_row
from app.state import Connection
from app.ui import callback_command
from app.web import Bot
from app.mtproto import incoming_message
from test_core import run, TG, Config, env, FakeAppX, conn, update, Session, Response
from test_upgrade import CP, cpconn


@pytest.mark.parametrize('value', [True, 1, '1', 'true', 'TRUE', ' True ', 'yes'])
def test_protected_flags_case_insensitive(value):
    assert protected_row({'isEncrypted': value})


@pytest.mark.parametrize('value', [False, 0, '0', 'false', None])
def test_unprotected_flags(value):
    assert not protected_row({'isEncrypted': value})


@pytest.mark.parametrize('meta', [{'hasMore': True}, {'pagination': {'total': 2}}, {'meta': {'has_next': True, 'totalCount': 3}}, {'total_count': 'unknown'}])
def test_appx_known_partial_response_not_success(meta):
    with pytest.raises(ProviderError, match='PAGINATION'):
        complete_appx_rows({'data': [{'id': 1}], **meta}, 'BAD')


def test_appx_complete_response():
    rows = [{'id': 1}]
    assert complete_appx_rows({'data': rows, 'pagination': {'total': '1', 'hasMore': False}}, 'BAD') == rows


def test_appx_cross_provider_connection_denied_before_network():
    async def case():
        p = AppX(None, {'api.classplusapp.com'})
        with pytest.raises(ProviderError, match='NOT_ALLOWED'):
            await p.request(cpconn(), 'mycoursev2', {})
    run(case())


def test_appx_folder_explicit_protection_not_exported():
    async def case():
        p = FakeAppX(folders={'-1': [{'title': 'Protected', 'url': 'https://cdn.example.invalid/a.mp4', 'isDRM': 'TRUE'}, {'title': 'Notes', 'pdf_link': 'https://cdn.example.invalid/b.pdf'}]})
        result = await p.export(conn(), '5', asyncio.Event())
        assert result.count == 1 and result.skipped == 1 and 'Protected' not in result.text
    run(case())


def test_cp_explicit_case_insensitive_protection():
    async def case():
        p = CP(pages={('0', 0): {'data': {'courseContent': [{'id': 1, 'url': 'https://cdn.example.invalid/a.pdf', 'isEncrypted': 'True'}], 'hasMore': False}}})
        with pytest.raises(ProviderError, match='NO_CLEAR_AUTHORIZED'):
            await p.export(cpconn(), '7', asyncio.Event())
    run(case())


def test_wizard_does_not_request_appx_token_without_host():
    c = Conversations()
    with pytest.raises(ProviderError, match='NO_TOKEN_REQUESTED'):
        c.begin(1, 'appx', set())
    assert not c.steps


def test_wizard_appx_two_stages_and_no_secret_retention():
    c = Conversations(); c.begin(1, 'appx', {'a.example', 'b.example'})
    command, prompt = c.accept(1, 'b.example', {'a.example', 'b.example'})
    assert command is None and 'ACTUAL_USER_ID' in prompt
    command, prompt = c.accept(1, '42 synthetic-own-token', {'a.example', 'b.example'})
    assert command == '/connect appx b.example 42 synthetic-own-token' and prompt is None
    assert not c.steps and 'synthetic-own-token' not in repr(vars(c))


def test_wizard_rejects_unapproved_host_without_sending_token():
    c = Conversations(); c.begin(1, 'appx', {'a.example', 'b.example'})
    with pytest.raises(ProviderError, match='NOT_APPROVED'):
        c.accept(1, 'attacker.example', {'a.example', 'b.example'})
    assert not c.steps


def test_wizard_expiry_and_user_isolation():
    c = Conversations(); c.begin(1, 'classplus', set()); c.steps[1].expires = 0
    with pytest.raises(ProviderError, match='EXPIRED'):
        c.accept(1, 'not-retained-token', set())
    c.begin(2, 'classplus', set())
    with pytest.raises(ProviderError, match='EXPIRED'):
        c.accept(1, 'not-retained-token', set())
    assert 2 in c.steps


def test_wizard_bounded_capacity():
    c = Conversations()
    for uid in range(250): c.begin(uid, 'classplus', set())
    with pytest.raises(ProviderError, match='CAPACITY'):
        c.begin(999, 'classplus', set())


def test_course_nonce_user_provider_bound_and_expiry():
    c = Conversations(); nonce = c.course_page(1, 'appx', [Course('5', 'Own', True)])
    assert c.choose(1, 'appx', nonce, 0) == '5'
    for args in [(2, 'appx', nonce, 0), (1, 'classplus', nonce, 0), (1, 'appx', 'wrong', 0), (1, 'appx', nonce, 99), (1, 'appx', nonce, -1)]:
        with pytest.raises(ProviderError): c.choose(*args)
    item = c.choices[1]; c.choices[1] = (0, *item[1:])
    with pytest.raises(ProviderError, match='EXPIRED'): c.choose(1, 'appx', nonce, 0)


@pytest.mark.parametrize('data', ['course:aaaaaaaa:0 extra', 'course:../../..:0', 'course:aaaaaaaa:-1', 'course:aaaaaaaa:10000', 'course:AAAAAAAA:0'])
def test_bad_course_callback_rejected(data):
    assert callback_command(data) is None


def test_course_callback_maps_no_raw_course_id():
    assert callback_command('course:1234abcd:7') == '/choose 1234abcd 7'
    assert callback_command('nav:connect') == '/connect'


def test_wizard_bot_classplus_private_plain_reply_deleted_and_connected():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, {'appx': FakeAppX(), 'classplus': CP()})
        await b.handle(update('/connect classplus'))
        assert b.conversations.steps[1].provider == 'classplus'
        b.last.clear()
        await b.handle(update('synthetic-private-token'))
        assert b.state.get(1, 'classplus').token == 'synthetic-private-token'
        assert not b.conversations.steps
        assert all('synthetic-private-token' not in msg for _, msg in t.sent)
        assert t.deleted
    run(case())


def test_wizard_cancel_then_plain_secret_ignored():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, {'appx': FakeAppX(), 'classplus': CP()})
        await b.handle(update('/connect classplus')); await b.handle(update('/cancel'))
        before = len(t.sent); await b.handle(update('synthetic-token-must-be-ignored'))
        assert len(t.sent) == before and b.state.get(1, 'classplus') is None
    run(case())


def test_wizard_switch_provider_invalidates_pending_token_prompt():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, {'appx': FakeAppX(), 'classplus': CP()})
        await b.handle(update('/connect classplus')); await b.handle(update('/appx'))
        assert not b.conversations.steps
        await b.handle(update('private-token'))
        assert not b.state.connections
    run(case())


def test_mtproto_plaintext_only_for_active_private_wizard():
    e = NS(sender_id=1, chat_id=1, is_private=True, out=False, sender=NS(bot=False), raw_text='synthetic-token', id=7)
    assert incoming_message(e) is None
    assert incoming_message(e, True)['message']['text'] == 'synthetic-token'
    e.is_private = False
    assert incoming_message(e, True) is None


def test_mtproto_oversized_plain_input_rejected():
    e = NS(sender_id=1, chat_id=1, is_private=True, out=False, sender=NS(bot=False), raw_text='a' * 5001, id=7)
    assert incoming_message(e, True) is None


def test_old_course_button_invalid_after_reconnect():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, {'appx': FakeAppX(), 'classplus': CP()})
        nonce = b.conversations.course_page(1, 'appx', [Course('5', 'Own', True)])
        await b.handle(update('/connect appx'))
        b.last.clear(); await b.handle(update('/choose ' + nonce + ' 0'))
        assert 'EXPIRED_OR_CHANGED' in t.sent[-1][1] and not b.jobs.active
    run(case())


def test_all_500_course_choices_have_pages_not_first_eight_only():
    c = Conversations(); courses = [Course(str(i), 'Course' + str(i), True) for i in range(500)]
    nonce = c.course_page(1, 'appx', courses)
    found = []
    for page in range(63):
        rows, count = c.page(1, 'appx', nonce, page)
        assert count == 63
        found.extend(rows)
    assert found == courses
    with pytest.raises(ProviderError): c.page(1, 'appx', nonce, 63)
    with pytest.raises(ProviderError): c.page(2, 'appx', nonce, 0)


def test_pagination_callbacks_strict_and_bounded():
    assert callback_command('coursepage:1234abcd:62') == '/coursepage 1234abcd 62'
    assert callback_command('coursepage:1234abcd:123') is None


@pytest.mark.parametrize('provider', ['appx', 'classplus'])
def test_synthetic_full_setup_to_chosen_channel(provider):
    from test_upgrade import ChannelTG
    async def case():
        t = ChannelTG()
        appx = FakeAppX(folders={'-1': [{'title': 'Own notes', 'pdf_link': 'https://cdn.example.invalid/own.pdf'}]})
        cp = CP(pages={('0', 0): {'data': {'courseContent': [{'id': 1, 'name': 'Own notes', 'url': 'https://cdn.example.invalid/own.pdf'}], 'hasMore': False}}})
        b = Bot(Config.from_env(env()), t, {'appx': appx, 'classplus': cp}, 999)
        await b.handle(update('/connect ' + provider))
        # Immediate reply is not throttled by the non-network prompt.
        await b.handle(update('42 synthetic-own-token' if provider == 'appx' else 'synthetic-own-token'))
        assert b.state.get(1, provider)
        b.last.clear(); await b.handle(update('/setdestination @MyChannel'))
        b.last.clear(); await b.handle(update('/courses'))
        nonce = b.conversations.choices[1][2]
        b.last.clear(); await b.handle(update('/choose ' + nonce + ' 0'))
        assert len(b.jobs.active) == 1
        b.jobs.start()
        await asyncio.wait_for(b.jobs.queue.join(), 2)
        assert len(t.documents) == 1 and t.documents[0][0] == -1001234567
        assert t.documents[0][2] == provider and t.documents[0][3] == 1
        await b.close()
    run(case())


def test_quiesce_requires_secret_stops_socket_and_rejects_new_updates():
    from aiohttp.test_utils import TestClient, TestServer
    from app.web import create_app
    async def case():
        class Transport(TG):
            connected = True
            async def close(self): self.connected = False
        t = Transport(); c = Config.from_env(env()); b = Bot(c, t, FakeAppX())
        runtime = {'ready': True, 'identity_verified': True, 'updates_configured': True, 'transport': 'mtproto-bot'}
        async with TestClient(TestServer(create_app(c, b, runtime))) as client:
            r = await client.post('/ops/quiesce'); assert r.status == 401 and t.connected
            headers = {'X-Telegram-Bot-Api-Secret-Token': c.webhook_secret}
            b.jobs.active[1] = object()
            r = await client.post('/ops/quiesce', headers=headers); assert r.status == 409 and t.connected
            b.jobs.active.clear()
            r = await client.post('/ops/quiesce', headers=headers); assert r.status == 200 and not t.connected
            r = await client.get('/readyz'); assert r.status == 503
            r = await client.post('/telegram/webhook', headers=headers, json=update('/start')); assert r.status == 503
            r = await client.post('/ops/quiesce', headers=headers); assert r.status == 200
    run(case())
