"""Public command routing, owner isolation and deterministic no-head-of-line checks."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from app.web import Bot, COMMANDS, published_commands
from app.ui import classplus_login_panel, dashboard_panel, owner_panel, callback_command
from app.config import Config
from app.state import Connection
from test_core import run, TG, Config, env, FakeAppX, update
from test_upgrade import CP, ChannelTG
from test_mtproto import Client, config as mtconfig, runtime, message
from app.mtproto import MTProtoTelegram
from app.classplus_auth import Challenge


def config():
    return replace(Config.from_env(env()), classplus_otp_enabled=True, owner_id=77)


@pytest.mark.parametrize('name', [n for n, _ in COMMANDS])
def test_every_registered_command_has_real_handler_not_unknown(name):
    async def case():
        t = TG(); b = Bot(config(), t, {'appx': FakeAppX(), 'classplus': CP()})
        await b.handle(update('/' + name, uid=77))
        assert t.sent, name
        assert all('Unknown command.' not in text for _, text in t.sent), name
        assert not b.locks and not b.lock_refs
    run(case())


def test_published_commands_hide_owner_actions_and_disabled_providers():
    c = replace(config(), appx_hosts=frozenset(), classplus_otp_enabled=False)
    names = {n for n, _ in published_commands(c)}
    assert not {'admin', 'stats', 'appx', 'cpotp'} & names
    assert {'dashboard', 'courses', 'refreshcourses', 'cptoken', 'help'} <= names


def test_each_new_panel_button_routes_and_fits_telegram_limit():
    panels = [classplus_login_panel(), dashboard_panel('classplus', 'private', 'None', 'None', 'None', True), owner_panel('Counts only')]
    for panel in panels:
        assert '\n\n' in panel.text and len(panel.text) < 3900
        for row in panel.rows:
            for button in row:
                data = button['callback_data']
                assert len(data.encode()) <= 64 and callback_command(data), data


@pytest.mark.parametrize('cmd', ['/admin', '/stats'])
def test_owner_commands_not_available_to_ordinary_user(cmd):
    async def case():
        t = TG(); b = Bot(config(), t, {'classplus': CP()})
        await b.handle(update(cmd, uid=1)); assert t.sent[-1][1] == 'OWNER_ONLY'
        await b.handle(update(cmd, uid=77)); assert 'OWNER ADMIN' in t.sent[-1][1]
    run(case())


def test_dashboard_shows_only_own_data_not_other_user_or_secrets():
    async def case():
        t = TG(); b = Bot(config(), t, {'classplus': CP()})
        b.state.put(2, Connection('api.classplusapp.com', 'self', 'other-user-private-token', 'classplus'))
        b.destinations.values[2] = NS(title='Other secret channel', chat_id=-1002222222)
        b.classplus_login.pending[2] = Challenge(stage='otp', phone='9876500000', session='private-challenge')
        await b.handle(update('/dashboard', uid=1)); text = t.sent[-1][1]
        assert 'MY DASHBOARD' in text and 'not connected' in text
        assert 'Other secret channel' not in text and 'other-user-private-token' not in text and '9876500000' not in text
        assert 'Owner admin' not in text
    run(case())


def test_locks_are_released_not_permanent_250_user_lockout():
    async def case():
        t = TG(); b = Bot(config(), t, {'classplus': CP()})
        for uid in range(1, 1001): await b.handle(update('/help', uid=uid))
        assert len(t.sent) == 1000 and not b.locks and not b.lock_refs
    run(case())


def test_cached_courses_do_not_refetch_or_force_two_second_wait():
    async def case():
        t = TG(); p = CP(); b = Bot(config(), t, {'classplus': p})
        await b.handle(update('/connect classplus synthetic-own-token'))
        assert len(p.calls) == 1
        await b.handle(update('/courses'))
        assert len(p.calls) == 1 and 'Please wait' not in t.sent[-1][1]
        b.last.clear(); await b.handle(update('/refreshcourses'))
        assert len(p.calls) == 2
    run(case())


def test_cache_does_not_bypass_fresh_account_membership_for_export():
    async def case():
        t = ChannelTG(); p = CP(); b = Bot(config(), t, {'classplus': p}, 999)
        await b.handle(update('/connect classplus synthetic-own-token'))
        b.last.clear(); await b.handle(update('/setdestination @MyChannel'))
        nonce = b.conversations.choices[1][2]
        b.last.clear(); await b.handle(update('/choose ' + nonce + ' 0'))
        p.course_rows = []
        b.jobs.start(); await asyncio.wait_for(b.jobs.queue.join(), 2)
        assert not t.documents and any('COURSE_NOT_IN_YOUR_ACCOUNT' in text for _, text in t.sent)
        await b.close()
    run(case())


def test_control_queue_handles_cancel_and_dashboard_while_all_regular_workers_wait():
    async def case():
        entered = asyncio.Event(); release = asyncio.Event()
        class Slow(CP):
            count = 0
            async def courses(self, conn):
                self.count += 1
                if self.count == 4: entered.set()
                await release.wait()
                return await super().courses(conn)
        t = TG(); p = Slow(); b = Bot(config(), t, {'classplus': p})
        b.start()
        try:
            for uid in range(1, 5): b.updates.put_nowait(update('/connect classplus synthetic-token-' + str(uid), uid=uid))
            await asyncio.wait_for(entered.wait(), 2)
            for item in [update('/dashboard', uid=99), update('/cancel', uid=1)]: b.queue_for(item).put_nowait(item)
            await asyncio.wait_for(b.fast_updates.join(), 1)
            assert not release.is_set()
            assert any(cid == 99 and 'MY DASHBOARD' in text for cid, text in t.sent)
            release.set(); await asyncio.wait_for(b.updates.join(), 2)
            assert b.state.get(1, 'classplus') is None
            assert all(b.state.get(uid, 'classplus') for uid in (2, 3, 4))
            assert not b.locks
        finally:
            release.set(); await b.close()
    run(case())


def test_mtproto_accepts_private_otp_reply_only_for_own_pending_challenge():
    async def case():
        c = mtconfig(); state = runtime(); client = Client(); tg = MTProtoTelegram(c, state, client)
        b = Bot(c, tg, {'classplus': CP()})
        b.classplus_login.pending[1] = Challenge(stage='otp', expires=999999999)
        tg.start_receiving(b)
        await tg.handlers[0][0](message(raw_text='123456'))
        assert b.updates.qsize() == 1
        await tg.handlers[0][0](message(sender_id=2, chat_id=2, id=8, raw_text='123456'))
        assert b.updates.qsize() == 1
        await tg.close()
    run(case())


def test_fast_queue_overload_does_not_consume_regular_capacity():
    b = Bot(config(), TG(), {'classplus': CP()})
    for _ in range(16): b.fast_updates.put_nowait(update('/dashboard'))
    assert b.fast_updates.full() and not b.updates.full()
    assert b.queue_for(update('/cpotp')) is b.updates
    assert b.queue_for(update('/cancel')) is b.fast_updates


def test_webhook_priority_queue_capacity_and_dedup_are_independent():
    from aiohttp.test_utils import TestClient, TestServer
    from app.web import create_app
    async def case():
        c = config(); b = Bot(c, TG(), {'classplus': CP()})
        headers = {'X-Telegram-Bot-Api-Secret-Token': c.webhook_secret}
        async with TestClient(TestServer(create_app(c, b))) as client:
            for i in range(16):
                r = await client.post('/telegram/webhook', json=update('/cancel', update_id=i), headers=headers)
                assert r.status == 200
            assert b.fast_updates.qsize() == 16 and b.updates.qsize() == 0
            r = await client.post('/telegram/webhook', json=update('/cancel', update_id=99), headers=headers)
            assert r.status == 503 and 99 not in b.state.seen
            r = await client.post('/telegram/webhook', json=update('/help', update_id=100), headers=headers)
            assert r.status == 200 and b.updates.qsize() == 1
            r = await client.post('/telegram/webhook', json=update('/cancel', update_id=0), headers=headers)
            assert r.status == 200 and b.fast_updates.qsize() == 16
    run(case())


def test_mtproto_control_can_enqueue_when_regular_queue_is_full():
    async def case():
        c = mtconfig(); state = runtime(); tg = MTProtoTelegram(c, state, Client()); b = Bot(c, tg, {'classplus': CP()})
        for i in range(32): b.updates.put_nowait(update('/help', update_id=i))
        assert await tg.enqueue(b, update('/cancel', update_id=99), ('m', 99))
        assert b.fast_updates.qsize() == 1 and b.updates.qsize() == 32
        assert state['received_updates'] == 1
    run(case())
