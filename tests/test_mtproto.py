import asyncio
from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from aiohttp.test_utils import TestClient,TestServer
from telethon import types,functions,errors
from app.mtproto import MTProtoTelegram,incoming_message,incoming_callback,participant_status,buttons
from app.web import Bot,bootstrap_bot,create_app
from app.config import Config,ConfigError
from app.telegram import TelegramRateLimited
from app.providers import ProviderError,Export
from test_core import env,FakeAppX,run


def config():
    data=env();data.update(TELEGRAM_TRANSPORT='mtproto',TELEGRAM_API_ID='1234',
        TELEGRAM_API_HASH='a'*32,TELEGRAM_BOT_SESSION='S'*200)
    return Config.from_env(data)


def runtime():
    return {'ready':False,'identity_verified':False,'webhook_configured':False,
            'updates_configured':False,'transport':'mtproto-bot','startup':'pending'}


def message(**changes):
    data={'is_private':True,'out':False,'sender_id':1,'chat_id':1,'id':7,
          'sender':NS(bot=False),'raw_text':'/start'};data.update(changes);return NS(**data)


def query(**changes):
    data={'is_private':True,'sender_id':1,'chat_id':1,'id':12345,
          'message_id':11,'data':b'ui:tools'};data.update(changes);return NS(**data)


class Client:
    def __init__(self):
        self.connected=False;self.handlers=[];self.sent=[];self.edited=[];self.calls=[];self.resolved=[];self.files=[]
        self.me=NS(id=123456,username='IndependentTestBot',bot=True)
        self.channel=types.Channel(id=5,title='Test Channel',photo=types.ChatPhotoEmpty(),date=None,broadcast=True,access_hash=99)
    async def connect(self):self.connected=True
    async def disconnect(self):self.connected=False
    def is_connected(self):return self.connected
    async def get_me(self):return self.me
    def add_event_handler(self,h,b):self.handlers.append((h,b))
    def remove_event_handler(self,h,b):self.handlers.remove((h,b))
    async def send_message(self,entity,text,**kwargs):self.sent.append((entity,text,kwargs));return NS(id=11)
    async def edit_message(self,entity,mid,text,**kwargs):self.edited.append((entity,mid,text,kwargs));return NS(id=mid)
    async def delete_messages(self,entity,ids):self.calls.append(('delete',entity,ids))
    async def get_entity(self,target):self.resolved.append(target);return self.channel
    async def send_file(self,entity,data,**kwargs):self.files.append((entity,data.read(),data.name,kwargs))
    async def __call__(self,request):
        self.calls.append(request)
        if isinstance(request,functions.channels.GetParticipantRequest):
            if request.participant==123456:
                p=types.ChannelParticipantAdmin(user_id=123456,promoted_by=1,date=None,
                    admin_rights=types.ChatAdminRights(post_messages=True))
            else:p=types.ChannelParticipantCreator(user_id=1,admin_rights=types.ChatAdminRights())
            return NS(participant=p)
        return True


def test_config_hides_mtproto_session_and_hash_and_defaults_to_botapi():
    c=config();assert c.transport=='mtproto'
    assert c.mtproto_session not in repr(c) and c.telegram_api_hash not in repr(c)
    assert Config.from_env(env()).transport=='botapi'


@pytest.mark.parametrize('key,value',[('TELEGRAM_TRANSPORT','userbot'),('TELEGRAM_API_ID','bad'),
    ('TELEGRAM_API_ID','0'),('TELEGRAM_API_HASH','wrong'),('TELEGRAM_BOT_SESSION','short')])
def test_invalid_mtproto_configuration_fails_closed(key,value):
    data=env();data.update(TELEGRAM_TRANSPORT='mtproto',TELEGRAM_API_ID='1234',
        TELEGRAM_API_HASH='a'*32,TELEGRAM_BOT_SESSION='S'*200);data[key]=value
    with pytest.raises(ConfigError):Config.from_env(data)


@pytest.mark.parametrize('changes',[{'is_private':False},{'out':True},{'sender_id':2},
    {'sender_id':True},{'sender':NS(bot=True)},{'raw_text':'hello'}])
def test_nonprivate_outgoing_cross_user_bot_and_noncommand_messages_ignored(changes):
    assert incoming_message(message(**changes)) is None


def test_real_telegram_event_shape_translates_without_token_data():
    assert incoming_message(message())['message']['from']['id']==1
    item=incoming_callback(query())['callback_query']
    assert item['id']=='12345' and item['data']=='ui:tools' and item['message']['message_id']==11


@pytest.mark.parametrize('changes',[{'is_private':False},{'sender_id':2},{'data':b'\xff'},{'data':b'a'*65}])
def test_untrusted_mtproto_callback_ignored(changes):
    assert incoming_callback(query(**changes)) is None


def test_buttons_have_actual_mtproto_inline_data_and_url():
    rows=buttons([[{'text':'Home','callback_data':'ui:home'},{'text':'Support','url':'https://t.me/SyntaxError_2'}]])
    assert rows[0][0].data==b'ui:home' and rows[0][1].url=='https://t.me/SyntaxError_2'


def test_bot_bootstrap_and_command_callback_pipeline_without_http_webhook():
    async def case():
        c=config();state=runtime();client=Client();tg=MTProtoTelegram(c,state,client);bot=Bot(c,tg,FakeAppX())
        try:
            await bootstrap_bot(c,tg,bot,state)
            assert state['ready'] and state['identity_verified'] and state['updates_configured']
            assert not state['webhook_configured'] and len(tg.handlers)==2
            assert all(not isinstance(x,str) for x in client.calls)
            await tg.handlers[0][0](message());await asyncio.wait_for(bot.updates.join(),1)
            assert 'SYNTAX EXTRACTOR PRO' in client.sent[-1][1] and state['received_updates']==1
            await tg.handlers[1][0](query());await asyncio.wait_for(bot.updates.join(),1)
            assert 'TOOLS & CONTROLS' in client.edited[-1][2] and client.edited[-1][1]==11
            assert state['outbound_messages']==2
        finally:await bot.close();await tg.close()
        assert not client.connected and not client.handlers
    run(case())


@pytest.mark.parametrize('bad_me',[NS(id=999999,username='IndependentTestBot',bot=True),
    NS(id=123456,username='WrongBot',bot=True),NS(id=123456,username='IndependentTestBot',bot=False)])
def test_mismatched_session_or_personal_account_cannot_start(bad_me):
    async def case():
        c=config();state=runtime();client=Client();client.me=bad_me
        tg=MTProtoTelegram(c,state,client);bot=Bot(c,tg,FakeAppX())
        await bootstrap_bot(c,tg,bot,state)
        assert not state['ready'] and not client.handlers and not client.calls and not bot.workers
        await tg.close()
    run(case())


def test_mtproto_ready_endpoint_checks_socket_and_disables_http_intake():
    async def case():
        c=config();state=runtime();client=Client();client.connected=True;tg=MTProtoTelegram(c,state,client);b=Bot(c,tg,FakeAppX())
        state.update(ready=True,identity_verified=True,updates_configured=True,startup='verified-mtproto-bot')
        async with TestClient(TestServer(create_app(c,b,state))) as http:
            r=await http.get('/readyz');assert r.status==200
            r=await http.post('/telegram/webhook',json={'update_id':1},headers={'X-Telegram-Bot-Api-Secret-Token':c.webhook_secret});assert r.status==503
            assert not b.state.seen
            client.connected=False
            r=await http.get('/readyz');assert r.status==503 and (await r.json())['startup']=='TELEGRAM_TRANSPORT_DISCONNECTED'
    run(case())


def test_channel_permission_checks_and_numeric_string_normalization():
    async def case():
        c=config();state=runtime();client=Client();tg=MTProtoTelegram(c,state,client);b=Bot(c,tg,FakeAppX(),123456)
        dest=await b.destinations.set(1,'@ExampleChannel')
        assert dest.chat_id==-1000000000005
        assert await b.destinations.check_delivery(1,dest)==dest.chat_id
        assert dest.chat_id in client.resolved  # not treated as a phone/username string
    run(case())


def test_channel_without_bot_post_permission_stays_blocked():
    async def case():
        class NoPost(Client):
            async def __call__(self,request):return NS(participant=types.ChannelParticipantAdmin(
                user_id=123456,promoted_by=1,date=None,admin_rights=types.ChatAdminRights(post_messages=False)))
        c=config();client=NoPost();tg=MTProtoTelegram(c,runtime(),client);b=Bot(c,tg,FakeAppX(),123456)
        with pytest.raises(ProviderError,match='POST_PERMISSION'):await b.destinations.set(1,'@ExampleChannel')
        assert not b.destinations.values
    run(case())


def test_document_sent_to_explicit_chat_only_with_plain_txt():
    async def case():
        client=Client();tg=MTProtoTelegram(config(),runtime(),client)
        await tg.document(-1000000000005,'abc',Export('Title: https://cdn.example.invalid/a.pdf\n',1,0),'classplus')
        entity,data,name,kwargs=client.files[0]
        assert entity==-1000000000005 and name=='classplus-abc.txt' and data.startswith(b'Title:')
        assert kwargs['force_document'] and kwargs['parse_mode'] is None
    run(case())


def test_flood_wait_has_no_automatic_send_retry_and_safe_error():
    async def case():
        class Flood(Client):
            async def send_message(self,*args,**kwargs):self.sent.append(True);raise errors.FloodWaitError(request=None,capture=9)
        client=Flood();tg=MTProtoTelegram(config(),runtime(),client)
        with pytest.raises(TelegramRateLimited) as e:await tg.send(1,'Hello')
        assert e.value.retry_after==9 and len(client.sent)==1
    run(case())


def test_queue_dedup_and_overload_bound_without_marking_dropped_updates():
    async def case():
        c=config();state=runtime();tg=MTProtoTelegram(c,state,Client());b=Bot(c,tg,FakeAppX())
        update=incoming_message(message())
        assert await tg.enqueue(b,update,('m',1))
        assert not await tg.enqueue(b,update,('m',1))
        for i in range(2,33):assert await tg.enqueue(b,update,('m',i))
        assert not await tg.enqueue(b,update,('m',33))
        assert ('m',33) not in b.state.seen and b.updates.qsize()==32 and state['overload_drops']==1
    run(case())


def test_arbitrary_rpc_and_http_webhook_not_exposed_by_mtproto_adapter():
    async def case():
        client=Client();tg=MTProtoTelegram(config(),runtime(),client)
        for method in ['setWebhook','arbitrary','logOut','deleteAccount']:
            with pytest.raises(ProviderError,match='NOT_ALLOWED'):await tg.call(method)
        assert not client.calls
    run(case())
