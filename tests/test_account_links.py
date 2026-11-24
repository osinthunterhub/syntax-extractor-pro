"""Fake native QR/2FA clients only; never authorizes a real Telegram user account."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import pytest
from telethon import errors, types, functions
from telethon.sessions import MemorySession
from app.account_link import AccountLinks, qr_svg
from app.web import Bot, create_app
from app.config import Config, ConfigError
from app.providers import ProviderError
from test_core import run, TG, env, update, FakeAppX
from test_upgrade import CP, ChannelTG
from aiohttp.test_utils import TestClient, TestServer


def config():
    return replace(Config.from_env(env()), telegram_link_enabled=True, access_consent_enabled=True,
                   telegram_api_id=1234, telegram_api_hash='a'*32, owner_id=77)


class QR:
    url = 'tg://login?token=syntheticQRtoken12345678'
    def __init__(self, client):
        self.client = client; self.expires = datetime.now(timezone.utc) + timedelta(seconds=30)
    async def wait(self, timeout):
        self.client.wait_started.set(); await self.client.scan.wait()
        if self.client.needs_2fa: raise errors.SessionPasswordNeededError(request=None)
        self.client.authorized = True
        return self.client.me


class UserClient:
    def __init__(self, uid=1, needs_2fa=False):
        self.me = NS(id=uid, bot=False); self.needs_2fa = needs_2fa
        self.scan, self.wait_started = asyncio.Event(), asyncio.Event()
        self.connected, self.authorized, self.revoked, self.updates = False, False, False, True
        self.calls, self.channel_rows = [], []
    async def connect(self): self.connected = True
    async def disconnect(self): self.connected = False
    def is_connected(self): return self.connected
    async def is_user_authorized(self): return self.authorized
    async def log_out(self): self.revoked = True; self.authorized = False; return True
    async def get_me(self): return self.me if self.authorized else None
    async def qr_login(self): self.calls.append('QR'); return QR(self)
    async def set_receive_updates(self, value): self.updates = value
    async def sign_in(self, password):
        if password != 'synthetic-correct-password': raise errors.PasswordHashInvalidError(request=None)
        self.authorized = True; return self.me
    async def __call__(self, request):
        assert isinstance(request, functions.channels.GetAdminedPublicChannelsRequest)
        self.calls.append(type(request).__name__); return NS(chats=self.channel_rows)


async def linked(uid=1, scanner=None, needs_2fa=False):
    client = UserClient(uid if scanner is None else scanner, needs_2fa)
    manager = AccountLinks(config(), factory=lambda: client)
    token = await manager.invite(uid); data = await manager.start(token, True)
    assert data['stage'] == 'qr' and client.wait_started.is_set()
    client.scan.set(); await asyncio.wait_for(manager.flows[token].task, 1)
    return manager, client, token


def channel(cid=5, username='MyPublicChannel', broadcast=True, creator=True):
    return types.Channel(id=cid, title='Own public channel', username=username,
        photo=types.ChatPhotoEmpty(), date=None, broadcast=broadcast, creator=creator, access_hash=123)


def test_no_connection_or_qr_before_explicit_consent():
    async def case():
        calls=[]; manager=AccountLinks(config(), factory=lambda: calls.append(1))
        token=await manager.invite(1)
        assert manager.snapshot(token)['stage']=='consent' and not calls
        with pytest.raises(ProviderError,match='EXPLICIT_CONSENT'): await manager.start(token,False)
        assert not calls
    run(case())


def test_successful_qr_verifies_same_user_disables_updates_and_unlinks_only_new_key():
    async def case():
        m,c,t=await linked()
        assert m.status(1)=='linked' and not c.updates and m.snapshot(t)['stage']=='linked'
        assert m.flows[t].client is None and not m.flows[t].qr_url
        assert 'qr_image' not in m.snapshot(t)
        assert await m.unlink(1) is True
        assert c.revoked and not c.connected and not m.linked
    run(case())


def test_wrong_scanning_account_is_revoked_not_adopted():
    async def case():
        m,c,t=await linked(uid=1,scanner=2)
        assert not m.linked and c.revoked and not c.connected
        assert m.snapshot(t)['error']=='LINK_ACCOUNT_MUST_MATCH_YOUR_TELEGRAM_ID'
        await m.close()
    run(case())


def test_bot_or_wrong_identity_never_adopted():
    async def case():
        c=UserClient(1);c.me.bot=True;m=AccountLinks(config(),factory=lambda:c)
        t=await m.invite(1);await m.start(t,True);c.scan.set();await m.flows[t].task
        assert not m.linked and c.revoked
        await m.close()
    run(case())


def test_qr_double_click_reuses_single_pending_client():
    async def case():
        c=UserClient();calls=[]
        def factory():calls.append(1);return c
        m=AccountLinks(config(),factory=factory);t=await m.invite(1)
        await m.start(t,True);await m.start(t,True)
        assert len(calls)==1 and c.calls==['QR']
        await m.close();assert not c.connected
    run(case())


def test_2fa_password_only_in_private_portal_transiently_then_identity_rechecked():
    async def case():
        m,c,t=await linked(needs_2fa=True)
        assert m.snapshot(t)['stage']=='password' and not m.linked
        data=await m.password(t,'synthetic-correct-password')
        assert data['stage']=='linked' and 1 in m.linked and not c.updates
        assert 'password' not in str(data) and 'session' not in str(data)
        await m.close()
    run(case())


def test_three_wrong_2fa_attempts_stop_link_flow():
    async def case():
        m,c,t=await linked(needs_2fa=True)
        for _ in range(3):data=await m.password(t,'synthetic-wrong-password')
        assert data['stage']=='error' and not m.linked and not c.connected
        assert 'synthetic-wrong-password' not in str(data)
        await m.close()
    run(case())


def test_no_old_bot_session_imported_by_native_user_client_factory():
    c=replace(config(),mtproto_session='NEVER_IMPORT_THIS_BOT_SESSION')
    m=AccountLinks(c);client=m.new_client()
    assert isinstance(client.session,MemorySession) and not client.is_connected()
    assert client.session.auth_key is None


@pytest.mark.parametrize('bad',['http://evil.invalid','tg://login?token=<script>','javascript:alert(1)','tg://login?token=short'])
def test_qr_uri_cannot_inject_svg_or_other_url(bad):
    with pytest.raises(ProviderError,match='QR_FORMAT'):qr_svg(bad)


def test_svg_is_generated_without_external_urls_or_markup_payload():
    image=qr_svg('tg://login?token=syntheticQRtoken1234')
    assert image.startswith(b'<svg') and b'<script' not in image and b'foreignObject' not in image
    assert b'tg://login' not in image


def test_flow_expiry_and_hour_link_expiry_disconnect_and_revoke():
    async def case():
        now=[1000.0];c=UserClient();m=AccountLinks(config(),factory=lambda:c,clock=lambda:now[0])
        t=await m.invite(1);now[0]+=301
        with pytest.raises(ProviderError,match='EXPIRED'):m.snapshot(t)
        await m.purge();assert not m.flows
        t=await m.invite(1);await m.start(t,True);c.scan.set();await m.flows[t].task
        now[0]+=3601;await m.purge()
        assert not m.linked and c.revoked
    run(case())


def test_link_capacity_is_bounded_without_connecting_any_account():
    async def case():
        m=AccountLinks(config())
        for uid in range(5):await m.invite(uid+1)
        with pytest.raises(ProviderError,match='CAPACITY'):await m.invite(99)
        await m.close()
    run(case())


def test_public_admin_channels_only_no_inbox_or_dialog_reads():
    async def case():
        m,c,t=await linked();c.channel_rows=[channel(),channel(6,'GroupExample',False),channel(7,None),channel(8,'NotMyChannel',True,False)]
        nonce,rows=await m.channels(1)
        assert rows==[('Own public channel','@MyPublicChannel')]
        assert m.choose(1,nonce,0)=='@MyPublicChannel'
        with pytest.raises(ProviderError):m.choose(2,nonce,0)
        assert c.calls==['QR','GetAdminedPublicChannelsRequest']
        await m.close()
    run(case())


def test_channel_list_requires_own_link_not_another_users():
    async def case():
        m,c,t=await linked()
        with pytest.raises(ProviderError,match='LINK_YOUR_OWN'):await m.channels(2)
        await m.close()
    run(case())


def test_registration_gate_precedes_every_account_or_provider_side_effect():
    async def case():
        t=TG();p=CP();b=Bot(config(),t,{'classplus':p})
        await b.handle(update('/linktelegram'));assert not b.account_links.flows and 'CONSENT_REQUIRED' in t.sent[-1][1]
        await b.handle(update('/connect classplus synthetic-own-token'));assert not p.calls
        await b.handle(update('/start'));assert 'BOT ACCESS' in t.sent[-1][1]
        await b.handle(update('/accept'));assert b.access.users[1]['consent']
        await b.handle(update('/linktelegram'));assert 1 in b.account_links.by_user and not b.account_links.linked
        await b.close()
    run(case())


def test_admin_blocking_and_maintenance_not_exposed_to_other_users():
    async def case():
        t=TG();b=Bot(config(),t,{'classplus':CP()})
        await b.handle(update('/start'));await b.handle(update('/accept'))
        await b.handle(update('/ban 77'));assert t.sent[-1][1]=='OWNER_ONLY'
        await b.handle(update('/ban 1',uid=77));assert b.access.users[1]['blocked']
        await b.handle(update('/linktelegram'));assert 'ACCESS_BLOCKED' in t.sent[-1][1]
        await b.handle(update('/unlinktelegram'));assert 'disconnected' in t.sent[-1][1]
        await b.handle(update('/unban 1',uid=77));assert not b.access.users[1]['blocked']
        await b.handle(update('/maintenance on',uid=77));assert b.access.maintenance
        await b.handle(update('/dashboard'));assert 'MAINTENANCE' in t.sent[-1][1]
        await b.handle(update('/logoutall'));assert 'forgotten' in t.sent[-1][1]
        await b.handle(update('/maintenance off',uid=77));assert not b.access.maintenance
        await b.close()
    run(case())


def test_owner_cannot_be_banned_and_registry_does_not_contain_credentials():
    async def case():
        t=TG();b=Bot(config(),t,{'classplus':CP()})
        await b.handle(update('/start',uid=77));await b.handle(update('/ban 77',uid=77))
        assert 'CANNOT_BLOCK_OWNER' in t.sent[-1][1]
        await b.handle(update('/users',uid=77));assert 'USER REGISTRY' in t.sent[-1][1]
        assert all(set(value)<= {'consent','blocked','last'} for value in b.access.users.values())
    run(case())


def test_private_portal_requires_fragment_token_header_same_origin_and_consent():
    async def case():
        c=config();b=Bot(c,TG(),{'classplus':CP()});b.access.consent(1)
        fake=UserClient();b.account_links=AccountLinks(c,factory=lambda:fake)
        token=await b.account_links.invite(1)
        async with TestClient(TestServer(create_app(c,b))) as client:
            r=await client.get('/account-link');text=await r.text()
            assert r.status==200 and 'FULL Telegram client authorization' in text
            assert token not in text and 'localStorage' not in text and 'https://cdn' not in text
            assert r.headers['Cache-Control'].startswith('no-store') and r.headers['X-Frame-Options']=='DENY'
            assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']
            r=await client.post('/account-link/api/status',json={});assert r.status==403
            head={'Origin':c.public_url,'X-Link-Token':token}
            r=await client.post('/account-link/api/status',json={},headers=head);assert r.status==200 and (await r.json())['uid']==1
            r=await client.post('/account-link/api/start',json={'consent':False},headers=head);assert r.status==400 and not fake.connected
            r=await client.post('/account-link/api/start',json={'consent':True,'uid':2},headers=head);assert r.status==200
            assert (await r.json())['uid']==1
            r=await client.post('/account-link/api/session',json={},headers=head);assert r.status==400
            r=await client.post('/account-link/api/cancel',json={},headers=head);assert r.status==200
        assert not fake.connected
        await b.close()
    run(case())


def test_link_feature_in_botapi_mode_requires_explicit_app_credentials_not_old_session():
    data=env();data['TELEGRAM_ACCOUNT_LINK_ENABLED']='true'
    with pytest.raises(ConfigError):Config.from_env(data)
    data.update(TELEGRAM_API_ID='1234',TELEGRAM_API_HASH='a'*32)
    c=Config.from_env(data);assert c.telegram_link_enabled and not c.mtproto_session


def test_privacy_button_and_home_work_before_registration_without_side_effects():
    async def case():
        t=ChannelTG();b=Bot(config(),t,{'classplus':CP()})
        def cb(data):return {'callback_query':{'id':'123','data':data,'from':{'id':1},'message':{'chat':{'id':1,'type':'private'},'message_id':5}}}
        await b.handle(cb('ui:privacy'));assert 'PRIVACY & LIMITS' in t.sent[-1][1]
        await b.handle(cb('ui:home'));assert 'BOT ACCESS' in t.sent[-1][1]
        assert not b.access.users[1]['consent'] and not b.account_links.flows
    run(case())


def test_owner_retains_admin_access_when_public_registry_is_full():
    from app.access import Access
    a=Access(77)
    for uid in range(1000,3000):a.touch(uid)
    a.touch(77);a.owner(77)
    assert 77 in a.users
    with pytest.raises(ProviderError,match='CAPACITY'):a.touch(99999)


def test_maintenance_cancels_inflight_provider_login_before_it_can_restore_session():
    async def case():
        started,release=asyncio.Event(),asyncio.Event()
        class Slow(CP):
            async def courses(self,conn):started.set();await release.wait();return await super().courses(conn)
        t=TG();b=Bot(config(),t,{'classplus':Slow()});b.access.consent(1)
        task=asyncio.create_task(b.handle(update('/connect classplus synthetic-own-token')))
        await started.wait();await b.handle(update('/maintenance on',uid=77));release.set();await task
        assert b.state.get(1,'classplus') is None
        assert any('LOGIN_CANCELLED' in text for _,text in t.sent)
    run(case())


def test_unlink_cancels_inflight_password_request_without_leaving_live_client():
    async def case():
        m,c,t=await linked(needs_2fa=True)
        started=asyncio.Event()
        async def slow(password):started.set();await asyncio.Event().wait()
        c.sign_in=slow
        pending=asyncio.create_task(m.password(t,'synthetic-correct-password'))
        await started.wait();await m.unlink(1)
        assert pending.cancelled() and not c.connected and not m.linked and not m.flows
    run(case())


def test_cancel_during_connect_does_not_later_display_or_authorize_qr():
    async def case():
        started=asyncio.Event();c=UserClient()
        async def slow():c.connected=True;started.set();await asyncio.Event().wait()
        c.connect=slow;m=AccountLinks(config(),factory=lambda:c);t=await m.invite(1)
        pending=asyncio.create_task(m.start(t,True));await started.wait();await m.unlink(1)
        assert pending.cancelled() and not c.connected and c.calls==[] and not m.flows
    run(case())


def test_owner_user_panel_buttons_route_and_recheck_actor_authorization():
    from app.ui import callback_command
    async def case():
        t=ChannelTG();b=Bot(config(),t,{'classplus':CP()});b.access.consent(1)
        assert callback_command('admin:ban:1')=='/ban 1'
        assert callback_command('admin:unban:1')=='/unban 1'
        assert callback_command('admin:users:0')=='/users 0'
        def cb(uid):return {'callback_query':{'id':'a','data':'admin:ban:1','from':{'id':uid},'message':{'chat':{'id':uid,'type':'private'},'message_id':5}}}
        await b.handle(cb(1));assert not b.access.users[1]['blocked'] and t.sent[-1][1]=='OWNER_ONLY'
        await b.handle(cb(77));assert b.access.users[1]['blocked']
        await b.close()
    run(case())
