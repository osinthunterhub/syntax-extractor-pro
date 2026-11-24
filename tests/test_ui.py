import pytest
from app.ui import (LOGIN_NAMES, PUBLIC_NAMES, PAGE_SIZE, callback_command, render_panel,
                    catalog_panel, item_panel, provider_panel, SUPPORT_URL)
from app.web import Bot, COMMANDS
from app.telegram import Telegram, TelegramRateLimited
from app.providers import ProviderError
from test_core import Config, env, TG, FakeAppX, run, update, Session, Response


class PanelTG(TG):
    def __init__(self):
        super().__init__(); self.panels=[]
    async def panel(self,chat,text,rows,message_id=None):
        self.panels.append((chat,text,rows,message_id))
    async def call(self,method,payload=None):
        assert method=='answerCallbackQuery'
        return True


def callback(data,uid=1,chat=1,message_id=123):
    return {'callback_query':{'id':'query-test','from':{'id':uid},'data':data,
        'message':{'message_id':message_id,'from':{'id':999,'is_bot':True},
                   'chat':{'id':chat,'type':'private'}}}}


def test_reference_names_recorded_without_duplicate_claims():
    assert len(LOGIN_NAMES)==49 and len(PUBLIC_NAMES)==16
    assert LOGIN_NAMES.count('RWA')==1
    assert {'Classplus','AppX V2','AppX V3','VMR Logics','Cadets Defence Academy'} <= set(LOGIN_NAMES)


@pytest.mark.parametrize('name',['home','login','public','tools','support','guide','privacy','coverage'])
def test_every_static_panel_has_only_valid_bounded_buttons(name):
    panel=render_panel([name])
    assert len(panel.text)<3900 and panel.rows
    for row in panel.rows:
        assert 1<=len(row)<=2
        for b in row:
            assert 1<=len(b['text'])<=64
            if 'callback_data' in b:
                assert len(b['callback_data'].encode())<=64
                assert callback_command(b['callback_data'])
            else:assert b['url']==SUPPORT_URL


@pytest.mark.parametrize('kind,names',[('login',LOGIN_NAMES),('public',PUBLIC_NAMES)])
def test_catalog_pagination_reaches_all_entries_with_no_dead_callbacks(kind,names):
    found=[]
    pages=(len(names)+PAGE_SIZE-1)//PAGE_SIZE
    for page in range(pages):
        panel=catalog_panel(kind,page)
        assert f'{page+1}/{pages}' in panel.text and 'NOT connected' in panel.text
        for row in panel.rows:
            for b in row:
                command=callback_command(b['callback_data']);assert command
                if b['callback_data'].startswith('ui:item:'):
                    _,_,k,index=b['callback_data'].split(':');found.append(names[int(index)])
                    item=item_panel(k,int(index))
                    assert names[int(index)] in item.text and 'extraction unavailable' in item.text
                elif b['callback_data']=='provider:classplus':found.append('Classplus')
    assert found==list(names)


@pytest.mark.parametrize('value',[None,[],{},123,'ui:catalog:login:99','ui:item:login:99',
    'ui:catalog:evil:0','ui:item:public:-1','ui:home /connect secret','/connect secret',
    'ui:home'+'x'*65,'💥','\ud800','action:stats'])
def test_untrusted_callbacks_never_become_commands(value):
    assert callback_command(value) is None


@pytest.mark.parametrize('kind,page',[('unknown',0),('login',-1),('login',99),('public',True)])
def test_catalog_rejects_invalid_page_or_family(kind,page):
    with pytest.raises(ValueError):catalog_panel(kind,page)


def test_provider_panels_do_not_claim_live_support():
    panel=provider_panel('appx',False,False)
    assert 'setup pending' in panel.text and 'not connected' in panel.text
    assert '/connect appx API_HOST USER_ID TOKEN' in panel.text
    cp=provider_panel('classplus',True,True)
    assert 'connected' in cp.text and 'real provider verification pending' in cp.text


def test_without_login_panel_never_claims_premium_unlock():
    panel=render_panel(['public'])
    assert 'No public-content sources are connected' in panel.text
    assert 'No shared account tokens' in panel.text


def test_home_commands_and_callback_edit_same_panel():
    async def case():
        tg=PanelTG();b=Bot(Config.from_env(env()),tg,FakeAppX())
        await b.handle(update('/start'))
        assert 'SYNTAX EXTRACTOR PRO' in tg.panels[-1][1] and tg.panels[-1][3] is None
        await b.handle(callback('ui:login'))
        assert 'ACCOUNT ACCESS' in tg.panels[-1][1] and tg.panels[-1][3]==123
        await b.handle(callback('ui:catalog:login:4'))
        assert '5/5' in tg.panels[-1][1]
        await b.handle(callback('ui:home'))
        assert 'SYNTAX EXTRACTOR PRO' in tg.panels[-1][1]
    run(case())


def test_catalog_and_menu_navigation_do_not_change_accounts():
    from app.state import Connection
    async def case():
        tg=PanelTG();b=Bot(Config.from_env(env()),tg,FakeAppX())
        a=Connection('academy.example.invalid','42','synthetic-appx-token')
        c=Connection('api.classplusapp.com','self','synthetic-cp-token','classplus')
        b.state.put(1,a);b.state.put(1,c);b.selected[1]='classplus'
        for route in ['ui:home','ui:public','ui:item:public:0','ui:catalog:login:2','ui:privacy']:
            await b.handle(callback(route))
        assert b.state.get(1,'appx') is a and b.state.get(1,'classplus') is c
        assert b.selected[1]=='classplus'
        assert all(a.token not in text and c.token not in text for _,text,_,_ in tg.panels)
    run(case())


def test_cross_user_private_panel_callback_rejected():
    async def case():
        tg=PanelTG();b=Bot(Config.from_env(env()),tg,FakeAppX())
        await b.handle(callback('ui:tools',uid=2,chat=1))
        assert not tg.panels and any('private chat only' in t for _,t in tg.sent)
    run(case())


def test_invalid_typed_panel_has_specific_error_not_session_capacity():
    async def case():
        tg=PanelTG();b=Bot(Config.from_env(env()),tg,FakeAppX())
        await b.handle(update('/panel catalog login 99'))
        assert tg.sent[-1][1]=='INVALID_MENU_SELECTION_USE_START'
    run(case())


def test_telegram_panel_prefers_edit_and_unchanged_is_success():
    async def case():
        session=Session(Response(200,b'{"ok":true,"result":{}}'))
        await Telegram(session,'synthetic-token').panel(1,'Hello',(),123)
        assert session.calls[0][0].endswith('/editMessageText')
        assert session.calls[0][1]['json']['message_id']==123
        session=Session(Response(400,b'{"ok":false,"description":"Bad Request: message is not modified"}'))
        assert await Telegram(session,'synthetic-token').panel(1,'Hello',(),123) is True
        assert len(session.calls)==1
    run(case())


def test_inaccessible_edit_can_send_one_fresh_panel():
    async def case():
        class Recording(Telegram):
            def __init__(self):self.calls=[]
            async def call(self,method,payload=None,form=None):
                self.calls.append((method,dict(payload)))
                if method=='editMessageText':raise ProviderError('TELEGRAM_HTTP_400_REQUEST_REJECTED')
                return True
        tg=Recording();await tg.panel(1,'Hello',(),123)
        assert [m for m,_ in tg.calls]==['editMessageText','sendMessage']
        assert 'message_id' not in tg.calls[1][1]
    run(case())


@pytest.mark.parametrize('error',[TelegramRateLimited(10),ProviderError('TELEGRAM_REQUEST_FAILED')])
def test_panel_never_retries_timeout_or_rate_limit(error):
    async def case():
        class Recording(Telegram):
            def __init__(self):self.calls=[]
            async def call(self,method,payload=None,form=None):self.calls.append(method);raise error
        tg=Recording()
        with pytest.raises(ProviderError):await tg.panel(1,'Hello',(),123)
        assert tg.calls==['editMessageText']
    run(case())


def test_registered_ui_commands_and_existing_exports_remain():
    names={name for name,_ in COMMANDS}
    assert {'start','login','free','tools','guide','privacy','capabilities','support','export','setdestination','cancel'} <= names
    assert len(names)==len(COMMANDS)


@pytest.mark.parametrize('command',['/start','/home','/Xtract'])
def test_reference_home_aliases(command):
    async def case():
        tg=PanelTG();b=Bot(Config.from_env(env()),tg,FakeAppX())
        await b.handle(update(command))
        assert 'SYNTAX EXTRACTOR PRO' in tg.panels[-1][1]
    run(case())


def test_callback_ack_failure_does_not_drop_local_cancellation():
    from app.state import Connection
    async def case():
        class Expired(PanelTG):
            async def call(self,method,payload=None):raise ProviderError('TELEGRAM_HTTP_400_REQUEST_REJECTED')
        tg=Expired();b=Bot(Config.from_env(env()),tg,FakeAppX())
        job=b.jobs.submit(1,1,Connection('academy.example.invalid','42','synthetic-token'),'5')
        await b.handle(callback('action:cancel'))
        assert job.cancelled.is_set()
    run(case())
