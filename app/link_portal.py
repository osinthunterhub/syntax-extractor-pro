"""Same-origin private QR/2FA portal. Bearer lives in URL fragment, never access URL.
No third-party scripts, cookies, analytics, storage or session-export endpoint.
"""
import secrets
from aiohttp import web
from .provider_common import ProviderError


PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Syntax Extractor • Link your Telegram</title>
<style nonce="NONCE">*{box-sizing:border-box}body{margin:0;background:#101827;color:#e8efff;font:16px/1.6 system-ui,sans-serif;padding:24px}main{max-width:640px;margin:auto;background:#172338;border:1px solid #334765;border-radius:20px;padding:28px}h1{line-height:1.25}p{color:#c4d0e5}button{padding:14px 20px;border:0;border-radius:10px;background:#72ddc5;color:#09211c;font-weight:700;cursor:pointer}button:disabled{opacity:.45;cursor:default}input[type=password]{width:100%;padding:14px;background:#0c1421;border:1px solid #526b8f;border-radius:9px;color:white;font-size:16px}label{display:block;margin:20px 0}#qr{display:none;width:min(100%,320px);margin:24px auto;border:12px solid white;border-radius:8px}.warn{background:#422d18;padding:16px;border-radius:10px}.muted{font-size:14px;color:#a7b8d0}#passwordBox{display:none}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}#status{white-space:pre-wrap;padding:14px 0}a{color:#8be3ff}</style>
<main><div class="muted">SYNTAX EXTRACTOR PRO • OWN ACCOUNT ONLY</div><h1>Link your Telegram account</h1>
<p id="identity">Validating your private link…</p><div class="warn"><strong>Read before linking</strong><p>This creates a FULL Telegram client authorization on this bot's server, not a narrowly scoped channel-only permission. The hosting operator can access server-side sessions and could access your account. Link ONLY if you trust this deployment.</p><p>The implemented controls list your admin PUBLIC channels and verify your selected export destination. They do not provide inbox/history browsing or session downloads.</p><p>Link is RAM-only, expires after one hour, and is lost on restart. Revoke “Syntax Extractor Linked Account” from Telegram → Settings → Devices whenever needed. Automatic revocation may fail during crashes/network outages.</p></div>
<label><input type="checkbox" id="consent"> I own the Telegram account ID shown above, trust this server, and understand the full-session risk and RAM-only limit.</label>
<div class="actions"><button id="start" disabled>Create private QR</button><button id="cancel">Cancel this setup</button></div><img id="qr" alt="Private Telegram device-linking QR"><p class="muted">Scan using YOUR Telegram: Settings → Devices → Link Desktop Device. A second screen may be needed. Never share this QR/private link. No Telegram login code should be sent to the bot.</p>
<div id="passwordBox"><h2>Telegram two-step verification</h2><p>Your account requires its 2FA password. This trusted server will process it transiently over HTTPS; it is not stored or logged by this implementation. Never submit it if you do not trust the operator.</p><input id="password" type="password" maxlength="512" autocomplete="off" aria-label="Telegram two-step password"><div class="actions"><button id="verify">Verify two-step password</button></div></div>
<div id="status" role="status"></div><p class="muted">This portal does not grant Classplus/AppX access. Return to your bot for /tgstatus, /mychannels or /unlinktelegram.</p></main>
<script nonce="NONCE">'use strict';const token=location.hash.slice(1);history.replaceState(null,'',location.pathname);const el=id=>document.getElementById(id);let timer=null,busy=false;
async function call(action,data={}){const r=await fetch('/account-link/api/'+action,{method:'POST',credentials:'omit',cache:'no-store',headers:{'Content-Type':'application/json','X-Link-Token':token},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error||'LINK_REQUEST_REJECTED');return d;}
function show(d){el('identity').textContent='Required account ID: '+d.uid+' • private setup expires in '+d.seconds_left+' seconds';el('status').textContent='Status: '+d.stage+(d.error?'\n'+d.error:'');el('qr').style.display=d.qr_image?'block':'none';if(d.qr_image)el('qr').src='data:image/svg+xml;base64,'+d.qr_image;else el('qr').removeAttribute('src');el('passwordBox').style.display=d.stage==='password'?'block':'none';el('start').disabled=!el('consent').checked||d.stage!=='consent';if(['linked','error'].includes(d.stage)){clearTimeout(timer);timer=null;el('password').value='';if(d.stage==='linked'){el('cancel').disabled=true;el('cancel').textContent='Linked — unlink from your bot';el('status').textContent='Linked successfully. Return to your bot → /mychannels. Account actions still require your private bot identity.';}}else{clearTimeout(timer);timer=setTimeout(refresh,2000);}}
async function refresh(){if(busy)return;try{show(await call('status'));}catch(e){el('status').textContent=e.message;clearTimeout(timer);timer=null;el('start').disabled=true;el('passwordBox').style.display='none';el('qr').style.display='none';}}
el('consent').onchange=()=>{if(!busy)el('start').disabled=!el('consent').checked;};
el('start').onclick=async()=>{if(!el('consent').checked||busy)return;busy=true;el('start').disabled=true;clearTimeout(timer);try{show(await call('start',{consent:true}));}catch(e){el('status').textContent=e.message;}finally{busy=false;timer=setTimeout(refresh,1000);}};
el('verify').onclick=async()=>{if(busy)return;busy=true;el('verify').disabled=true;const password=el('password').value;el('password').value='';try{show(await call('password',{password}));}catch(e){el('status').textContent=e.message;}finally{busy=false;el('verify').disabled=false;}};
el('cancel').onclick=async()=>{clearTimeout(timer);busy=true;try{await call('cancel');el('status').textContent='Setup cancelled. Return to your bot.';}catch(e){el('status').textContent=e.message;}el('qr').style.display='none';el('passwordBox').style.display='none';el('password').value='';el('start').disabled=true;};
if(/^[A-Za-z0-9_-]{43}$/.test(token))refresh();else{el('identity').textContent='Open a fresh private link from /linktelegram in your bot.';el('status').textContent='Missing or invalid private link';el('cancel').disabled=true;}
</script></html>'''


def security(nonce=None):
    headers = {'Cache-Control': 'no-store, max-age=0', 'Pragma': 'no-cache',
               'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY'}
    if nonce:
        headers['Content-Security-Policy'] = ("default-src 'none'; script-src 'nonce-" + nonce + "'; style-src 'nonce-" + nonce + "'; img-src data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    return headers


def add_link_portal(app, config, bot):
    async def page(request):
        nonce = secrets.token_urlsafe(18)
        return web.Response(text=PAGE.replace('NONCE', nonce), content_type='text/html', headers=security(nonce))

    async def api(request):
        if not config.telegram_link_enabled or request.headers.get('Origin') != config.public_url:
            return web.json_response({'error': 'LINK_ORIGIN_OR_FEATURE_REJECTED'}, status=403, headers=security())
        try:
            if request.content_type != 'application/json' or request.content_length is not None and request.content_length > 2048:
                raise ProviderError('LINK_REQUEST_FORMAT_REJECTED')
            token = request.headers.get('X-Link-Token', '')
            flow = bot.account_links.flow(token)
            action = request.match_info['action']
            if action not in ('status', 'start', 'password', 'cancel'):
                raise ProviderError('LINK_OPERATION_NOT_ALLOWED')
            if action != 'cancel':
                bot.access.check(flow.uid, require_consent=config.access_consent_enabled)
            data = await request.json()
            if not isinstance(data, dict):
                raise ProviderError('LINK_REQUEST_FORMAT_REJECTED')
            if action == 'start':
                result = await bot.account_links.start(token, data.get('consent'))
            elif action == 'password':
                result = await bot.account_links.password(token, data.get('password'))
            elif action == 'cancel':
                await bot.account_links.cancel_flow(flow.uid)
                result = {'cancelled': True}
            else:
                result = bot.account_links.snapshot(token)
            return web.json_response(result, headers=security())
        except ProviderError as exc:
            return web.json_response({'error': str(exc)}, status=400, headers=security())
        except (ValueError, UnicodeDecodeError):
            return web.json_response({'error': 'LINK_REQUEST_FORMAT_REJECTED'}, status=400, headers=security())
        except Exception:
            return web.json_response({'error': 'LINK_INTERNAL_ERROR_NO_SECRET_DETAILS'}, status=503, headers=security())

    app.router.add_get('/account-link', page)
    app.router.add_post('/account-link/api/{action}', api)
