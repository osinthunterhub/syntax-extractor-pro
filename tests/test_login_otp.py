"""Only fake HTTP responses and synthetic inputs. Never sends an actual SMS."""
import asyncio
from collections import deque
from dataclasses import replace
import json
import pytest
from app.classplus_auth import ClassplusLogin, Challenge, LoginResult
from app.providers import ProviderError
from app.config import Config
from app.web import Bot
from test_core import run, Response, TG, env, update, FakeAppX
from test_upgrade import CP, ChannelTG

PHONE = '9876500000'
OTP = '123456'
TOKEN = 'synthetic-own-classplus-token'


class HTTP:
    def __init__(self, *responses): self.responses, self.calls = deque(responses), []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert url.startswith('https://api.classplusapp.com/v2/')
        return self.responses.popleft()
    def get(self, url, **kwargs): return self.request('GET', url, **kwargs)
    def post(self, url, **kwargs): return self.request('POST', url, **kwargs)


def response(data, status=200):
    return Response(status, json.dumps({'status': 'success', 'data': data}).encode())


def login(clock=None):
    h = HTTP(response({'orgId': 42, 'orgName': 'Synthetic institute'}),
             response({'sessionId': 'synthetic-otp-challenge'}), response({'token': TOKEN, 'user': {'exists': True, 'signedUp': True}}))
    return (ClassplusLogin(h) if clock is None else ClassplusLogin(h, clock)), h


async def confirmation(a, uid=1):
    a.begin(uid); await a.input(uid, 'ABCD'); return await a.input(uid, PHONE)


def test_entire_otp_sequence_has_explicit_sms_confirmation_and_no_secret_repr():
    async def case():
        a, h = login(); result = await confirmation(a)
        assert result.confirm and PHONE not in result.prompt and PHONE[-4:] in result.prompt
        assert len(h.calls) == 1 and h.calls[0][0] == 'GET'
        draft = a.pending[1]
        assert PHONE not in repr(draft) and draft.device not in repr(draft)
        result = await a.send(1)
        assert 'provider accepted' in result.prompt and len(h.calls) == 2
        result = await a.input(1, OTP)
        assert result.token == TOKEN and TOKEN not in repr(result) and 1 not in a.pending
        assert [m for m, _, _ in h.calls] == ['GET', 'POST', 'POST']
        assert h.calls[1][2]['json']['viaSms'] == 1
        assert h.calls[2][2]['json']['sessionId'] == 'synthetic-otp-challenge'
        assert h.calls[2][2]['json']['fingerprintId'] == draft.device
        assert all(k['headers']['Api-Version'] == '51' and k['allow_redirects'] is False and k['timeout'].total == 15 for _, _, k in h.calls)
        assert 'orgs/ABCD' in h.calls[0][1]
    run(case())


@pytest.mark.parametrize('bad', ['https://evil.invalid', '../admin', 'a/b', '', 'a' * 65])
def test_org_input_never_changes_fixed_origin(bad):
    async def case():
        a, h = login(); a.begin(1)
        with pytest.raises(ProviderError, match='ORG_CODE_FORMAT'): await a.input(1, bad)
        assert not h.calls
    run(case())


@pytest.mark.parametrize('bad', ['123', '5555555555', '+441234567890', 'my password', '123456789012345'])
def test_invalid_phone_does_not_send_sms(bad):
    async def case():
        a, h = login(); a.begin(1); await a.input(1, 'ABCD')
        with pytest.raises(ProviderError, match='MOBILE_REQUIRED'): await a.input(1, bad)
        assert len(h.calls) == 1 and a.pending[1].stage == 'phone'
    run(case())


@pytest.mark.parametrize('phone', [PHONE, '+91 ' + PHONE, '91' + PHONE])
def test_indian_number_normalization_without_automatic_sms(phone):
    async def case():
        a, h = login(); a.begin(1); await a.input(1, 'ABCD'); result = await a.input(1, phone)
        assert result.confirm and a.pending[1].phone == PHONE and len(h.calls) == 1
    run(case())


def test_sms_before_confirmation_rejected():
    async def case():
        a, h = login(); a.begin(1)
        with pytest.raises(ProviderError, match='CONFIRM_NUMBER_FIRST'): await a.send(1)
        assert not h.calls
    run(case())


def test_sms_double_click_never_resends():
    async def case():
        a, h = login(); await confirmation(a); await a.send(1)
        with pytest.raises(ProviderError, match='NO_AUTORESEND'): await a.send(1)
        assert len(h.calls) == 2
    run(case())


def test_expired_challenge_is_removed():
    async def case():
        clock = [1000.0]; a, h = login(lambda: clock[0]); a.begin(1); clock[0] += 301
        with pytest.raises(ProviderError, match='EXPIRED_OR_CANCELLED'): await a.input(1, 'ABCD')
        assert not a.pending and not h.calls
    run(case())


def test_other_user_cannot_use_challenge_or_send_sms():
    async def case():
        a, h = login(); await confirmation(a, 1)
        with pytest.raises(ProviderError, match='EXPIRED_OR_CANCELLED'): await a.send(2)
        assert a.pending[1].stage == 'confirm' and len(h.calls) == 1
    run(case())


def test_rate_limit_survives_cancel_and_new_wizard_no_phone_in_rate_keys():
    a = ClassplusLogin(None, lambda: 1000)
    a.reserve_sms(1, PHONE); a.cancel(1); a.begin(1)
    with pytest.raises(ProviderError, match='COOLDOWN'): a.reserve_sms(1, PHONE)
    with pytest.raises(ProviderError, match='COOLDOWN'): a.reserve_sms(2, PHONE)
    assert PHONE not in repr(a.rates)


def test_sms_daily_limit_per_user_is_not_bypassed_by_changing_phone():
    clock = [1000.0]; a = ClassplusLogin(None, lambda: clock[0])
    for i in range(3): a.reserve_sms(1, '987650000' + str(i)); clock[0] += 61
    with pytest.raises(ProviderError, match='DAILY_LIMIT'): a.reserve_sms(1, '9876500009')


def test_lookup_rate_limit_survives_new_flow():
    a = ClassplusLogin(None, lambda: 1000)
    for i in range(5): a.reserve_lookup(1); a.begin(1)
    with pytest.raises(ProviderError, match='LOOKUP_RATE_LIMITED'): a.reserve_lookup(1)


def test_five_minute_pending_capacity_is_bounded():
    a = ClassplusLogin(None)
    for i in range(250): a.begin(i)
    with pytest.raises(ProviderError, match='CAPACITY'): a.begin(999)


@pytest.mark.parametrize('status,code', [(201, 'REGISTRATION_REQUIRED'), (409, 'REGISTRATION_REQUIRED'), (400, 'INVALID_OR_EXPIRED'), (401, 'INVALID_OR_EXPIRED'), (429, 'PROVIDER_RATE_LIMITED'), (500, 'REQUEST_REJECTED'), (302, 'REQUEST_REJECTED')])
def test_verification_failures_never_register_retry_or_expose_response(status, code):
    async def case():
        h = HTTP(Response(status, b'{"secret":"never-echo-this"}')); a = ClassplusLogin(h)
        draft = Challenge(stage='otp', expires=a.clock() + 300, phone=PHONE, session='private-session')
        a.pending[1] = draft
        with pytest.raises(ProviderError, match=code) as e: await a.input(1, OTP)
        assert 'never-echo-this' not in str(e.value) and len(h.calls) == 1
        assert '/users/register' not in h.calls[0][1]
    run(case())


def test_three_invalid_otp_attempts_discard_challenge():
    async def case():
        a = ClassplusLogin(HTTP(Response(400), Response(400), Response(400)))
        a.pending[1] = Challenge(stage='otp', expires=a.clock() + 300, phone=PHONE, session='s')
        for i in range(3):
            with pytest.raises(ProviderError, match='INVALID_OR_EXPIRED'): await a.input(1, OTP)
        assert 1 not in a.pending
        with pytest.raises(ProviderError, match='EXPIRED_OR_CANCELLED'): await a.input(1, OTP)
    run(case())


def test_auth_response_stream_cap():
    async def case():
        a = ClassplusLogin(HTTP(Response(200, b'x' * 65537))); a.begin(1)
        with pytest.raises(ProviderError, match='TOO_LARGE'): await a.input(1, 'ABCD')
    run(case())


def test_cancel_inflight_response_cannot_resurrect_or_delete_new_login():
    async def case():
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow(Response):
            async def __aenter__(self): entered.set(); await release.wait(); return self
        a = ClassplusLogin(HTTP(Slow(200, b'{"data":{"orgId":42}}')))
        a.begin(1); task = asyncio.create_task(a.input(1, 'ABCD')); await entered.wait()
        a.cancel(1); a.begin(1); new = a.pending[1]; release.set()
        with pytest.raises(ProviderError, match='CANCELLED'): await task
        assert a.pending[1] is new and new.stage == 'org'
    run(case())


def test_ambiguous_generate_failure_is_not_retried_and_cooldown_reserved():
    async def case():
        h = HTTP(response({'orgId': 42}), Response(500)); a = ClassplusLogin(h)
        await confirmation(a)
        with pytest.raises(ProviderError, match='REQUEST_REJECTED'): await a.send(1)
        assert len(h.calls) == 2 and 1 not in a.pending
        with pytest.raises(ProviderError, match='COOLDOWN'): a.reserve_sms(1, PHONE)
    run(case())


def test_synthetic_bot_otp_login_through_selected_channel_delivery():
    async def case():
        t = ChannelTG(); p = CP(courses=[{'id': 7, 'name': 'Own synthetic course'}], pages={('0', 0): {'data': {'courseContent': [{'id': 8, 'name': 'Notes', 'url': 'https://cdn.example.invalid/a.pdf'}]}}})
        c = replace(Config.from_env(env()), classplus_otp_enabled=True)
        b = Bot(c, t, {'classplus': p}, 999); a, h = login(); b.classplus_login = a
        await b.handle(update('/cpotp')); await b.handle(update('ABCD')); await b.handle(update(PHONE))
        assert len(h.calls) == 1 and a.pending[1].stage == 'confirm'
        await b.handle(update('/sendotp')); await b.handle(update(OTP))
        assert b.state.get(1, 'classplus').token == TOKEN and not a.pending
        assert all(TOKEN not in text and PHONE not in text and OTP not in text for _, text in t.sent)
        b.last.clear(); await b.handle(update('/setdestination @MyChannel'))
        nonce = b.conversations.choices[1][2]; b.last.clear()
        await b.handle(update('/choose ' + nonce + ' 0')); b.jobs.start()
        await asyncio.wait_for(b.jobs.queue.join(), 2)
        assert len(t.documents) == 1 and t.documents[0][0] == -1001234567
        await b.close()
    run(case())


def test_successful_otp_is_not_discarded_when_course_listing_temporarily_fails():
    async def case():
        class Unavailable(CP):
            async def courses(self, conn): raise ProviderError('CLASSPLUS_UNAVAILABLE')
        t = TG(); b = Bot(replace(Config.from_env(env()), classplus_otp_enabled=True), t, {'classplus': Unavailable()})
        await b.auth_result(1, 1, LoginResult(token=TOKEN))
        assert b.state.get(1, 'classplus').token == TOKEN
        assert '/refreshcourses without requesting another OTP' in t.sent[-1][1]
        assert TOKEN not in str(t.sent)
    run(case())


def test_unverified_token_is_not_saved_when_course_authentication_fails():
    async def case():
        class Unavailable(CP):
            async def courses(self, conn): raise ProviderError('CLASSPLUS_ACCESS_DENIED_RECONNECT')
        t = TG(); b = Bot(Config.from_env(env()), t, {'classplus': Unavailable()})
        await b.handle(update('/connect classplus ' + TOKEN))
        assert b.state.get(1, 'classplus') is None
    run(case())


@pytest.mark.parametrize('data', [{'user': {'exists': False}}, {'user': {'signedUp': False}}])
def test_verify_requiring_registration_never_creates_fake_user(data):
    async def case():
        a = ClassplusLogin(HTTP(response(data)))
        a.pending[1] = Challenge(stage='otp', expires=a.clock() + 300)
        with pytest.raises(ProviderError, match='REGISTRATION_REQUIRED'): await a.input(1, OTP)
        assert not a.pending
    run(case())


@pytest.mark.parametrize('token', [None, 'short', 'has a long password', '*' * 15])
def test_malformed_token_from_provider_never_becomes_connection(token):
    async def case():
        a = ClassplusLogin(HTTP(response({'token': token})))
        a.pending[1] = Challenge(stage='otp', expires=a.clock() + 300)
        with pytest.raises(ProviderError, match='TOKEN_SCHEMA'): await a.input(1, OTP)
        assert not a.pending
    run(case())
