"""Reference-format compatibility tests; no embedded upstream tokens or live accounts."""
import asyncio
import json
import pytest
from app.providers import ProviderError, Classplus
from test_core import run, Session, Response, TG, Config, env, update, FakeAppX
from test_upgrade import CP, cpconn, ChannelTG
from app.web import Bot


def test_legacy_reference_rows_without_flags_can_export_clear_authorized_response():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'My Courses legacy row'}], pages={('0', 0): {'data': {'courseContent': [{'id': 8, 'name': 'My notes', 'url': 'https://cdn.example.invalid/notes.pdf'}]}}})
        result = await p.export(cpconn(), '7', asyncio.Event())
        assert result.count == 1 and 'My notes:' in result.text
        assert p.calls[0][1] == 'courses' and p.calls[0][2]['tabCategoryId'] == 1
        assert p.calls[1][2]['courseId'] == '7'
    run(case())


def test_arbitrary_course_id_never_reaches_content_endpoint():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Legacy row'}])
        with pytest.raises(ProviderError, match='NOT_IN_YOUR_ACCOUNT'):
            await p.export(cpconn(), '999', asyncio.Event())
        assert all(call[1] == 'courses' for call in p.calls)
    run(case())


@pytest.mark.parametrize('flags', [{'isPurchased': False}, {'isEnrolled': 'false'}, {'isLocked': True}, {'isBlocked': 'YES'}, {'canAccess': 0}, {'isAccessible': False}])
def test_explicit_course_denial_still_blocks_legacy_fallback(flags):
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Denied', **flags}])
        assert await p.courses(cpconn()) == []
    run(case())


@pytest.mark.parametrize('value', ['mystery', None, {}, [], 7])
def test_invalid_explicit_purchase_flag_not_promoted_to_access(value):
    async def case():
        with pytest.raises(ProviderError, match='ACCESS_FLAG_SCHEMA'):
            await CP(courses=[{'id': 7, 'isPurchased': value}]).courses(cpconn())
    run(case())


def test_manually_enrolled_course_does_not_require_paid_purchase_flag():
    async def case():
        rows = await CP(courses=[{'id': 7, 'isPurchased': False, 'isEnrolled': 'TRUE'}]).courses(cpconn())
        assert [x.id for x in rows] == ['7']
    run(case())


def test_reference_api_version_header_is_per_request_not_global_state():
    async def case():
        session = Session(Response(200, b'{"status":"success","data":{"courses":[]}}'))
        p = Classplus(session)
        await p.courses(cpconn(token='synthetic-token-one'))
        await p.courses(cpconn(token='synthetic-token-two'))
        assert [x[1]['headers']['x-access-token'] for x in session.calls] == ['synthetic-token-one', 'synthetic-token-two']
        assert all(x[1]['headers']['Api-Version'] == '29' for x in session.calls)
        assert all('device-id' not in x[1]['headers'] for x in session.calls)
    run(case())


@pytest.mark.parametrize('payload', [{'status': 'failure'}, {'status': 'failed'}, {'status': 'error'}, {'status': 401}, {'status': 403}])
def test_provider_rejection_envelope_not_misparsed_as_courses(payload):
    async def case():
        p = Classplus(Session(Response(200, json.dumps(payload).encode())))
        with pytest.raises(ProviderError, match='REQUEST_REJECTED'):
            await p.courses(cpconn())
    run(case())


def test_total_count_pagination_advances_by_rows_not_assumed_page_size():
    async def case():
        p = CP(pages={('0', 0): {'data': {'courseContent': [{'id': 1}], 'totalCount': 2}},
                      ('0', 1): {'data': {'courseContent': [{'id': 2}], 'totalCount': 2}}})
        rows = await p.pages(cpconn(), 'content', {'folderId': '0'}, 'courseContent')
        assert [r['id'] for r in rows] == [1, 2]
        assert [c[2]['offset'] for c in p.calls] == [0, 1]
    run(case())


@pytest.mark.parametrize('data', [{'courseContent': [], 'hasMore': True}, {'courseContent': [{'id': 1}], 'totalCount': 2, 'hasMore': False}, {'courseContent': [{'id': 1}], 'totalCount': 0}, {'courseContent': [{'id': 1}], 'totalCount': 1, 'hasMore': True}])
def test_contradictory_pagination_never_reported_complete(data):
    async def case():
        p = CP(pages={('0', 0): {'data': data}})
        with pytest.raises(ProviderError, match='PAGINATION'):
            await p.pages(cpconn(), 'content', {'folderId': '0'}, 'courseContent')
    run(case())


def test_folder_paths_preserved_and_locked_hash_items_not_exported():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Legacy'}], pages={('0', 0): {'data': {'courseContent': [
            {'id': 10, 'contentType': 1, 'name': 'Chapter'},
            {'id': 11, 'name': 'Locked', 'url': 'https://cdn.example.invalid/locked.pdf', 'isLocked': True},
            {'id': 12, 'name': 'Hash video', 'url': 'https://cdn.example.invalid/video.mp4', 'contentHashId': 'synthetic-non-secret-hash'}]}},
            ('10', 0): {'data': {'courseContent': [{'id': 20, 'name': 'Notes', 'url': 'https://cdn.example.invalid/notes.pdf'}]}}})
        result = await p.export(cpconn(), '7', asyncio.Event())
        assert result.text == 'Chapter / Notes: https://cdn.example.invalid/notes.pdf\n'
        assert result.count == 1 and result.skipped == 2
    run(case())


def test_connect_classplus_immediately_presents_courses_without_second_api_fetch():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Legacy course'}]); t = TG()
        b = Bot(Config.from_env(env()), t, {'appx': FakeAppX(), 'classplus': p})
        await b.handle(update('/connect classplus synthetic-own-token'))
        assert b.state.get(1, 'classplus')
        assert any('Legacy course' in text for _, text in t.sent)
        assert len(p.calls) == 1
        assert 1 in b.conversations.choices
        assert all('synthetic-own-token' not in text for _, text in t.sent)
    run(case())


def test_classplus_legacy_whole_flow_to_only_user_selected_channel():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Own account legacy response'}], pages={('0', 0): {'data': {'courseContent': [{'id': 8, 'name': 'Notes', 'url': 'https://cdn.example.invalid/notes.pdf'}]}}})
        t = ChannelTG(); b = Bot(Config.from_env(env()), t, {'classplus': p}, 999)
        await b.handle(update('/connect classplus'))
        await b.handle(update('synthetic-private-own-token'))
        b.last.clear(); await b.handle(update('/setdestination @MyChannel'))
        nonce = b.conversations.choices[1][2]
        b.last.clear(); await b.handle(update('/choose ' + nonce + ' 0'))
        b.jobs.start(); await asyncio.wait_for(b.jobs.queue.join(), 2)
        assert len(t.documents) == 1 and t.documents[0][0] == -1001234567
        assert t.documents[0][2] == 'classplus'
        await b.close()
    run(case())


def test_cp_shortcut_starts_private_own_token_prompt_immediately():
    async def case():
        t = TG(); p = CP(); b = Bot(Config.from_env(env()), t, {'classplus': p})
        await b.handle(update('/cp'))
        assert b.conversations.steps[1].provider == 'classplus'
        assert 'own existing access token' in t.sent[-1][1]
        assert not p.calls
    run(case())


def test_cp_shortcut_in_group_does_not_start_setup_or_request_tokens():
    async def case():
        t = TG(); b = Bot(Config.from_env(env()), t, {'classplus': CP()})
        await b.handle(update('/cp', chat_type='group', chat_id=-1001234567))
        assert not b.conversations.steps
        assert 'private chat only' in t.sent[-1][1]
    run(case())


def test_course_capacity_is_explicit_not_a_silently_truncated_list():
    async def case():
        p = CP(courses=[{'id': i, 'name': 'Course'} for i in range(501)])
        with pytest.raises(ProviderError, match='LIMIT_EXCEEDED_NO_TRUNCATION'):
            await p.courses(cpconn())
    run(case())
