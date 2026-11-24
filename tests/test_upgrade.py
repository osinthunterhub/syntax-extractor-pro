import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from app.state import Connection, State
from app.providers import Classplus, ProviderRouter, ProviderError, Export, Course
from app.destinations import Destinations, Destination
from app.web import Bot, COMMANDS
from test_core import env, Config, FakeAppX, TG, update, run, Response, Session


def cpconn(account='self', token='synthetic-cp-token'):
    return Connection('api.classplusapp.com', account, token, 'classplus')


class CP(Classplus):
    def __init__(self, pages=None, courses=None):
        super().__init__(None)
        self.responses = pages or {}
        self.course_rows = courses if courses is not None else [{'id': 7, 'name': 'Owned', 'isPurchased': True}]
        self.calls = []
    async def request(self, connection, operation, params):
        self.calls.append((connection.token, operation, params))
        if operation == 'courses':
            return {'data': {'courses': self.course_rows, 'hasMore': False}}
        return self.responses.get((str(params['folderId']), params['offset']), {'data': {'courseContent': [], 'hasMore': False}})


def test_two_providers_same_user_separate_tokens():
    s = State()
    a = Connection('academy.example.invalid', '42', 'appx-own-token')
    c = cpconn()
    s.put(1, a); s.put(1, c)
    assert s.get(1, 'appx') is a and s.get(1, 'classplus') is c
    s.drop(1, 'appx')
    assert s.get(1) is None and s.get(1, 'classplus') is c
    s.drop(1); assert s.get(1, 'classplus') is None


def test_router_unknown_provider_fails():
    with pytest.raises(ProviderError, match='NOT_ENABLED'):
        ProviderRouter({}).adapter('unknown')


def test_cp_owned_list_and_export_skip_protected():
    async def case():
        p = CP(pages={('0',0): {'data': {'courseContent': [
            {'id': 8, 'contentType': 1}, {'id': 1, 'name': 'PDF', 'url': 'https://cdn.example.invalid/a.pdf'},
            {'id': 2, 'name': 'DRM', 'url': 'https://cdn.example.invalid/a.mp4', 'isDrm': True}], 'hasMore': False}},
            ('8',0): {'data': {'courseContent': [{'id': 8, 'contentType': 1},
                {'id': 3, 'name': 'Again', 'url': 'https://cdn.example.invalid/a.pdf'}], 'hasMore': False}}})
        result = await p.export(cpconn(), '7', asyncio.Event())
        assert result.count == 1 and result.skipped == 1
        assert result.text == 'PDF: https://cdn.example.invalid/a.pdf\n'
        assert len(p.calls) == 3
    run(case())


def test_cp_reference_account_list_does_not_require_invented_purchase_fields():
    async def case():
        p = CP(courses=[{'id': 7, 'name': 'Reference My Courses row'}])
        courses = await p.courses(cpconn())
        assert [c.id for c in courses] == ['7']
        assert p.calls[0][2]['tabCategoryId'] == 1
    run(case())


def test_cp_unowned_course_cannot_traverse():
    async def case():
        p = CP(courses=[{'id':7, 'isPurchased':False}])
        with pytest.raises(ProviderError, match='NOT_IN_YOUR_ACCOUNT'):
            await p.export(cpconn(), '7', asyncio.Event())
        assert [x[1] for x in p.calls] == ['courses']
    run(case())


def test_cp_pagination_supports_explicit_metadata():
    async def case():
        p = CP(pages={('0',0): {'data': {'courseContent': [{'id':1}], 'hasMore':True}},
                      ('0',1): {'data': {'courseContent': [{'id':2}], 'hasMore':False}}})
        rows = await p.pages(cpconn(), 'content', {'folderId':'0'}, 'courseContent')
        assert [r['id'] for r in rows] == [1,2]
    run(case())


def test_cp_repeated_pagination_rejected():
    async def case():
        value = {'data': {'courseContent': [{'id':1}], 'hasMore':True}}
        p = CP(pages={('0',0): value, ('0',1):value})
        with pytest.raises(ProviderError, match='REPEATED'):
            await p.pages(cpconn(), 'content', {'folderId':'0'}, 'courseContent')
    run(case())


def test_cp_ambiguous_full_page_not_claimed_complete():
    async def case():
        p = CP(pages={('0',0): {'data': {'courseContent':[{'id':i} for i in range(100)]}}})
        with pytest.raises(ProviderError, match='PAGINATION_UNKNOWN'):
            await p.pages(cpconn(), 'content', {'folderId':'0'}, 'courseContent')
    run(case())


@pytest.mark.parametrize('status, expected', [(302,'UNAVAILABLE'), (401,'ACCESS_DENIED'), (403,'ACCESS_DENIED'), (429,'RATE_LIMITED')])
def test_cp_http_errors_no_redirects_or_retry(status, expected):
    async def case():
        session = Session(Response(status))
        with pytest.raises(ProviderError, match=expected):
            await Classplus(session).courses(cpconn())
        assert len(session.calls)==1 and session.calls[0][1]['allow_redirects'] is False
    run(case())


def test_cp_headers_per_request_not_globally_mutated():
    async def case():
        session = Session(Response(200, b'{"data":{"courses":[],"hasMore":false}}'))
        p = Classplus(session)
        await asyncio.gather(p.courses(cpconn(token='token-one')),p.courses(cpconn(token='token-two')))
        assert {x[1]['headers']['x-access-token'] for x in session.calls} == {'token-one','token-two'}
    run(case())


class ChannelTG(TG):
    def __init__(self):
        super().__init__(); self.user_status='administrator'; self.post=True; self.documents=[]; self.answered=[]
    async def call(self, method, payload=None, form=None):
        if method=='getChat':return {'id':-1001234567,'type':'channel','title':'Chosen'}
        if method=='getChatMember':
            if payload['user_id']==999:return {'status':'administrator','can_post_messages':self.post}
            return {'status':self.user_status}
        if method=='answerCallbackQuery':self.answered.append(payload);return True
        raise AssertionError(method)
    async def document(self, channel, job_id, result, provider='appx'):
        self.documents.append((channel,job_id,provider,result.count))


def test_destination_requires_both_admin_and_bot_post_right():
    async def case():
        t=ChannelTG(); d=Destinations(t,999)
        value=await d.set(1,'@MyChannel'); assert value.chat_id==-1001234567
        t.user_status='member'
        with pytest.raises(ProviderError, match='YOU_MUST'):await d.set(2,'@MyChannel')
        assert 2 not in d.values
        t.user_status='administrator';t.post=False
        with pytest.raises(ProviderError, match='BOT_NEEDS'):await d.set(2,'@MyChannel')
    run(case())


@pytest.mark.parametrize('target',['123','https://t.me/channel','@bad','-123456'])
def test_destination_rejects_unexpected_target_format(target):
    async def case():
        with pytest.raises(ProviderError, match='MUST_BE_CHANNEL'):
            await Destinations(ChannelTG(),999).set(1,target)
    run(case())


def test_destination_change_rejected_no_output_fallback():
    async def case():
        t=ChannelTG(); b=Bot(Config.from_env(env()),t,FakeAppX(),999)
        dest=await b.destinations.set(1,'@MyChannel')
        job=NS(user_id=1,chat_id=1,id='job',connection=cpconn(),destination=dest,cancelled=asyncio.Event())
        b.destinations.values.pop(1)
        with pytest.raises(ProviderError, match='CHANGED_REQUEUE'):
            await b.deliver(job,Export('PDF: https://cdn.example.invalid/a.pdf\n',1,0))
        assert not t.documents
    run(case())


def test_destination_permission_rechecked_and_no_silent_dm():
    async def case():
        t=ChannelTG(); b=Bot(Config.from_env(env()),t,FakeAppX(),999)
        dest=await b.destinations.set(1,'@MyChannel')
        job=NS(user_id=1,chat_id=1,id='job',connection=cpconn(),destination=dest,cancelled=asyncio.Event())
        t.post=False
        with pytest.raises(ProviderError, match='BOT_NEEDS'):await b.deliver(job,Export('demo',1,0))
        assert not t.documents
        t.post=True;await b.deliver(job,Export('demo',1,0))
        assert t.documents==[(-1001234567,'job','classplus',1)]
    run(case())


def test_cross_user_destination_snapshot_rejected():
    async def case():
        with pytest.raises(ProviderError, match='INVALID_JOB_DESTINATION'):
            await Destinations(ChannelTG(),999).check_delivery(2,Destination(1,-1001234567,'Chosen'))
    run(case())


def test_cp_connect_menu_does_not_destroy_appx_connection():
    async def case():
        t=ChannelTG(); b=Bot(Config.from_env(env()),t,{'appx':FakeAppX(),'classplus':CP()},999)
        await b.handle(update('/connect appx academy.example.invalid 42 appx-secret'))
        b.last[1]=0
        await b.handle(update('/connect classplus classplus-secret'))
        assert b.state.get(1,'appx').token=='appx-secret'
        assert b.state.get(1,'classplus').token=='classplus-secret'
        assert b.selected[1]=='classplus'
        await b.handle(update('/disconnect'))
        assert b.state.get(1,'appx') and not b.state.get(1,'classplus')
        assert 'appx-secret' not in str(t.sent) and 'classplus-secret' not in str(t.sent)
    run(case())


def test_export_blocked_without_selected_destination():
    async def case():
        t=ChannelTG(); b=Bot(Config.from_env(env()),t,FakeAppX(),999)
        b.state.put(1,Connection('academy.example.invalid','42','synthetic-token'))
        await b.handle(update('/export 5'))
        assert not b.jobs.active and 'SET_DESTINATION' in t.sent[-1][1]
    run(case())


def test_menu_callback_uses_clicker_identity_not_bot_author():
    async def case():
        t=ChannelTG();b=Bot(Config.from_env(env()),t,FakeAppX(),999)
        await b.handle({'callback_query': {'id':'test-query','data':'provider:classplus','from':{'id':1},
                'message':{'from':{'id':999,'is_bot':True},'chat':{'id':1,'type':'private'},'message_id':7}}})
        assert b.selected[1]=='classplus' and len(t.answered)==1
    run(case())


def test_owner_stats_fail_closed():
    async def case():
        t=ChannelTG();cfg=replace(Config.from_env(env()),owner_id=77)
        b=Bot(cfg,t,FakeAppX(),999)
        await b.handle(update('/stats',uid=1));assert t.sent[-1][1]=='OWNER_ONLY'
        await b.handle(update('/stats',uid=77));assert 'Connected account sessions:' in t.sent[-1][1]
    run(case())


def test_command_menu_unique_and_valid():
    names=[x[0] for x in COMMANDS]
    assert len(names)==len(set(names)) and 'setdestination' in names and 'classplus' in names
    assert all(1<=len(desc)<=256 for _,desc in COMMANDS)


def test_webhook_non_ascii_secret_rejected_not_500():
    async def case():
        from aiohttp.test_utils import TestClient, TestServer
        from app.web import create_app
        cfg=Config.from_env(env());b=Bot(cfg,TG(),FakeAppX())
        async with TestClient(TestServer(create_app(cfg,b))) as client:
            r=await client.post('/telegram/webhook',json=update('/help'),headers={'X-Telegram-Bot-Api-Secret-Token':'é'*40})
            assert r.status==401 and b.updates.empty()
    run(case())


def test_entire_job_including_delivery_has_deadline():
    async def case():
        from app.jobs import Jobs
        class Provider:
            async def export(self,*args):return Export('demo',1,0)
        async def deliver(*args):await asyncio.sleep(10)
        notified=[]
        async def notify(job,text):notified.append(text)
        jobs=Jobs(Provider(),deliver,notify,deadline=0.01)
        jobs.start();jobs.submit(1,1,cpconn(),'7')
        await asyncio.wait_for(jobs.queue.join(),1)
        assert 'JOB_TIME_LIMIT_EXCEEDED' in notified and not jobs.active
        await jobs.close()
    run(case())


def test_appx_flat_course_clear_links_and_skip_encrypted():
    async def case():
        class Flat(FakeAppX):
            async def request(self, connection, path, params):
                if path=='mycoursev2':return {'data':[{'id':5,'course_name':'Flat','folder_wise_course':0}]}
                if path=='allsubjectfrmlivecourseclass':return {'data':[{'subjectid':1}]}
                if path=='alltopicfrmlivecourseclass':return {'data':[{'topicid':2},{'topicid':2}]}
                if path=='livecourseclassbycoursesubtopconceptapiv3':return {'data':[
                    {'Title':'Notes','pdf_link':'https://cdn.example.invalid/notes.pdf'},
                    {'Title':'Encrypted','download_link':'encrypted-string-not-url'}]}
                raise AssertionError(path)
        result=await Flat().export(Connection('academy.example.invalid','42','synthetic-token'),'5',asyncio.Event())
        assert result.count==1 and result.skipped==1 and result.text.startswith('Notes: https://')
    run(case())


def test_appx_flat_schema_failure_not_silent_success():
    async def case():
        class BadFlat(FakeAppX):
            async def request(self, connection, path, params):
                if path=='mycoursev2':return {'data':[{'id':5,'folder_wise_course':0}]}
                return {'data':{'unexpected':'object'}}
        with pytest.raises(ProviderError,match='FLAT_SCHEMA'):
            await BadFlat().export(Connection('academy.example.invalid','42','synthetic-token'),'5',asyncio.Event())
    run(case())


def test_empty_appx_allowlist_disables_without_preventing_startup():
    from app.config import Config
    from test_core import env
    values=env(); values['APPX_API_HOSTS']=''
    assert Config.from_env(values).appx_hosts==frozenset()


def test_unconfigured_appx_menu_gives_setup_status():
    from app.config import Config
    from app.web import Bot
    from test_core import env
    async def case():
        class TG:
            def __init__(self): self.messages=[]
            async def send(self,chat,text): self.messages.append(text)
        values=env();values['APPX_API_HOSTS']=''
        tg=TG();bot=Bot(Config.from_env(values),tg,FakeAppX())
        await bot.handle({'message':{'from':{'id':77},'chat':{'id':77,'type':'private'},'text':'/appx'}})
        assert any('setup pending' in text for text in tg.messages)
    run(case())


def test_telegram_rate_limit_safe_error_without_description_or_secret():
    from app.telegram import Telegram, TelegramRateLimited
    async def case():
        response=Response(429,b'{"ok":false,"description":"never-echo-this-secret","parameters":{"retry_after":10}}')
        with pytest.raises(TelegramRateLimited) as error:
            await Telegram(Session(response),'synthetic-token').call('getMe')
        assert error.value.retry_after==10
        assert str(error.value)=='TELEGRAM_RATE_LIMITED_RETRY_AFTER_10'
    run(case())


def test_telegram_non_success_safe_status_diagnostic():
    from app.telegram import Telegram
    async def case():
        with pytest.raises(ProviderError,match='HTTP_401') as error:
            await Telegram(Session(Response(401,b'{"ok":false,"description":"secret"}')),'synthetic-token').call('getMe')
        assert 'secret' not in str(error.value)
    run(case())


def test_telegram_identity_retry_honors_server_wait_and_is_bounded():
    from app.telegram import verified_identity, TelegramRateLimited
    async def case():
        class Limited:
            def __init__(self):self.calls=[]
            async def call(self,method):self.calls.append(method);raise TelegramRateLimited(10)
        tg=Limited();waits=[]
        async def sleep(delay):waits.append(delay)
        with pytest.raises(TelegramRateLimited):await verified_identity(tg,'IndependentTestBot',sleep=sleep)
        assert tg.calls==['getMe']*3 and waits==[11,11]
    run(case())


def test_telegram_identity_retry_success_and_mismatch_guard():
    from app.telegram import verified_identity, TelegramRateLimited
    async def case():
        class Identity:
            def __init__(self,name):self.name=name;self.calls=0
            async def call(self,method):
                self.calls+=1
                if self.calls==1:raise TelegramRateLimited(1)
                return {'id':55,'username':self.name,'is_bot':True}
        async def sleep(delay):assert delay==2
        assert (await verified_identity(Identity('IndependentTestBot'),'IndependentTestBot',sleep=sleep))['id']==55
        with pytest.raises(ProviderError,match='IDENTITY_MISMATCH'):
            await verified_identity(Identity('WrongBot'),'IndependentTestBot',sleep=sleep)
    run(case())


@pytest.mark.parametrize('value',[True,-1,0,'10'])
def test_telegram_malformed_retry_metadata_not_trusted(value):
    from app.telegram import Telegram
    import json
    async def case():
        response=Response(429,json.dumps({'ok':False,'parameters':{'retry_after':value}}).encode())
        with pytest.raises(ProviderError,match='RATE_LIMITED_RETRY_LATER'):
            await Telegram(Session(response),'synthetic-token').call('getMe')
    run(case())


def test_liveness_never_means_readiness_and_pending_webhook_not_acknowledged():
    from aiohttp.test_utils import TestClient, TestServer
    from app.web import create_app
    async def case():
        c=Config.from_env(env());b=Bot(c,TG(),FakeAppX())
        runtime={'ready':False,'identity_verified':False,'webhook_configured':False,'startup':'identity-check-pending'}
        async with TestClient(TestServer(create_app(c,b,runtime))) as client:
            r=await client.get('/healthz');assert r.status==200 and (await r.json())['ready'] is False
            r=await client.get('/readyz');assert r.status==503
            r=await client.post('/telegram/webhook',json=update('/help'),headers={'X-Telegram-Bot-Api-Secret-Token':c.webhook_secret})
            assert r.status==503 and b.updates.qsize()==0 and not b.state.seen
            runtime['ready']=True
            r=await client.get('/readyz');assert r.status==200
    run(case())


def test_bootstrap_identity_mismatch_never_sets_webhook_or_starts_workers():
    from app.web import bootstrap_bot
    async def case():
        class Identity:
            def __init__(self):self.calls=[]
            async def call(self,method,payload=None):
                self.calls.append(method)
                return {'id':1,'is_bot':True,'username':'WrongBot'}
        tg=Identity();c=replace(Config.from_env(env()),set_webhook=True);b=Bot(c,tg,FakeAppX())
        runtime={'ready':False,'identity_verified':False,'webhook_configured':False,'startup':'pending'}
        await bootstrap_bot(c,tg,b,runtime)
        assert tg.calls==['getMe'] and not b.workers and not runtime['ready']
        assert runtime['startup']=='BOT_IDENTITY_MISMATCH_NO_WEBHOOK_CHANGED'
    run(case())


def test_bootstrap_verifies_before_webhook_and_confirms_registration():
    from app.web import bootstrap_bot
    async def case():
        class Identity:
            def __init__(self):self.calls=[]
            async def call(self,method,payload=None):
                self.calls.append(method)
                if method=='getMe':return {'id':77,'is_bot':True,'username':'IndependentTestBot'}
                return True
        tg=Identity();c=replace(Config.from_env(env()),set_webhook=True);b=Bot(c,tg,FakeAppX())
        runtime={'ready':False,'identity_verified':False,'webhook_configured':False,'startup':'pending'}
        try:
            await bootstrap_bot(c,tg,b,runtime)
            assert tg.calls==['getMe','setWebhook','setMyCommands']
            assert runtime['ready'] and runtime['webhook_configured'] and b.destinations.bot_id==77
        finally:await b.close()
    run(case())


def test_bootstrap_failed_webhook_confirmation_stays_unready():
    from app.web import bootstrap_bot
    async def case():
        class Identity:
            async def call(self,method,payload=None):
                if method=='getMe':return {'id':77,'is_bot':True,'username':'IndependentTestBot'}
                return False
        tg=Identity();c=replace(Config.from_env(env()),set_webhook=True);b=Bot(c,tg,FakeAppX())
        runtime={'ready':False,'identity_verified':False,'webhook_configured':False,'startup':'pending'}
        await bootstrap_bot(c,tg,b,runtime)
        assert runtime['identity_verified'] and not runtime['ready'] and not runtime['webhook_configured']
        assert runtime['startup']=='TELEGRAM_WEBHOOK_NOT_CONFIRMED'
    run(case())
