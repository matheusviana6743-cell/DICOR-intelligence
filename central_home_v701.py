# -*- coding: utf-8 -*-
"""DICOR Central V701 - mesma composição visual da Central aprovada, refinada.

A V701 mantém toda a lógica da V700 e altera apenas o renderer/estilos da Central,
com uma leitura IMAP mais resistente e indicadores reais de conexão.
"""
from __future__ import annotations

import email
import imaplib
import time
from typing import Any

import central_home_v700 as v700

MAIL_STATUS = {"state": "CONFIGURANDO", "detail": ""}

CSS_701 = r'''
:root{--bg:#03070b;--bg2:#07111a;--panel:#0a151f;--panel2:#0d1b27;--line:#254056;--gold:#dfbb55;--gold2:#f2d77f;--blue:#5fa8db;--text:#f1f5f8;--muted:#91a4b3;--dim:#607687;--ok:#6ed3a4;--warn:#e1bd58}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 72% 12%,#0f3148 0,transparent 34%),radial-gradient(circle at 14% 0,#13283b 0,transparent 28%),#03070b;color:var(--text)}body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}
.top{position:sticky;top:0;z-index:80;min-height:86px;display:flex;align-items:center;gap:28px;padding:10px 42px;background:rgba(3,10,16,.93);border-bottom:1px solid #294255;backdrop-filter:blur(18px)}
.brand{display:flex;align-items:center;gap:14px;min-width:410px}.brand img{width:54px;height:54px;object-fit:contain;mix-blend-mode:screen;filter:drop-shadow(0 7px 14px #0008)}.brand b{display:block;font-size:16px;letter-spacing:1.7px;line-height:1.1}.brand span{display:block;color:var(--gold);font-size:10px;font-weight:900;letter-spacing:3.2px;margin-top:5px}
.nav{display:flex;align-items:center;gap:23px;margin-left:auto}.nav a{color:#9aabb8;font-size:10px;font-weight:900;letter-spacing:1.1px;transition:.16s}.nav a:hover{color:#f2f5f7}.top-actions{display:flex;align-items:center;gap:14px}.user{display:flex;align-items:center;gap:8px}.dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 13px var(--ok)}.user b{font-size:10px}.user small{display:block;color:#668096;font-size:8px;margin-top:3px}.logout{border:1px solid #29475c;background:#07141e;color:#9fb0bc;border-radius:8px;padding:8px 11px;font-size:8px;font-weight:900;cursor:pointer}
.wrap{position:relative;z-index:1;width:min(1240px,calc(100% - 46px));margin:auto;padding:42px 0 68px}.panel{border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,rgba(12,25,36,.96),rgba(5,13,20,.97));box-shadow:0 28px 80px #0009}
.hero-grid{display:grid;grid-template-columns:1.12fr .88fr;gap:18px;align-items:stretch}.hero-panel{padding:50px 42px 44px}.k{color:#4fa7df;font-size:10px;font-weight:900;letter-spacing:3px}.hero-panel h1{font-family:Georgia,'Times New Roman',serif;font-size:52px;line-height:1.05;font-weight:500;margin:15px 0 19px;letter-spacing:.1px}.hero-panel h1 span{color:var(--gold2)}.sub{color:#a0afba;font-size:14px;line-height:1.8;margin:0;max-width:690px}.operator-line{margin-top:23px;color:#d9b95d;font-size:11px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase}
.hero-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.statusbar{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}.statuschip{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #223b4f;border-radius:999px;background:#07131d;color:#8298a8;font-size:9px;font-weight:900;letter-spacing:1px}.statuschip i{width:7px;height:7px;border-radius:50%;background:#657b89}.statuschip.ok{color:#9fdcbc;border-color:#2c5d4a}.statuschip.ok i{background:var(--ok);box-shadow:0 0 10px var(--ok)}.statuschip.warn{color:#e4cb78;border-color:#665323}.statuschip.warn i{background:var(--warn);box-shadow:0 0 10px var(--warn)}
.hero-mark{min-height:360px;display:grid;place-items:center;position:relative;overflow:hidden;background:radial-gradient(circle at 50% 45%,#173e59 0,#0b1d2b 42%,#061019 78%)}.hero-mark:before{content:"";position:absolute;width:275px;height:275px;border:1px solid #5ba8dc66;border-radius:50%;box-shadow:0 0 0 38px #5ba8dc0c,0 0 0 76px #5ba8dc06,0 0 90px #0c77ad18}.hero-mark img{position:relative;width:190px;height:190px;object-fit:contain;mix-blend-mode:screen;filter:drop-shadow(0 18px 32px #000b)}
.section-title{margin:39px 0 15px}.section-title span{display:block;color:#4fa7df;font-size:9px;font-weight:900;letter-spacing:2.7px}.section-title h2{font-size:20px;letter-spacing:1.6px;margin:5px 0 0}
.modules{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.module{min-height:240px;display:flex;flex-direction:column;padding:24px;border:1px solid #254057;border-radius:17px;background:linear-gradient(155deg,#0b1925,#07111a);transition:.18s}.module:hover{transform:translateY(-3px);border-color:#4a6d86;box-shadow:0 16px 40px #0007}.module .icon{width:42px;height:42px;display:grid;place-items:center;border:1px solid #31546e;border-radius:10px;color:#cce1ef;background:#0a1c2a;margin-bottom:20px;font-weight:900;font-size:14px}.module h3{margin:0;color:#f0f4f6;font-size:18px;letter-spacing:.2px}.module .count{margin-top:13px;color:var(--gold2);font-size:31px;font-weight:850}.module p{margin:9px 0 0;color:#8ea0ad;font-size:12px;line-height:1.65;max-width:340px}.module .btnrow{margin-top:auto;padding-top:20px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:43px;padding:0 16px;border:1px solid #34566f;border-radius:9px;background:#0a1a27;color:#c8d9e3;font-size:10px;font-weight:950;letter-spacing:.9px;transition:.15s;cursor:pointer}.btn:hover{border-color:#5b83a0;background:#102438}.btn.gold,.primary{border:0;background:linear-gradient(135deg,#f1d271,#a77618);color:#080a0d;box-shadow:0 10px 24px #0007}.btn.gold:hover,.primary:hover{filter:brightness(1.06)}
.secondary-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:16px}.secondary{min-height:150px;padding:22px;border:1px solid #203a4e;border-radius:16px;background:linear-gradient(155deg,#091720,#06101a);display:flex;align-items:center;justify-content:space-between;gap:18px}.secondary .copy h3{font-size:17px;margin:0 0 7px}.secondary .copy p{margin:0;color:#8194a2;font-size:11px;line-height:1.6}.lock{display:inline-flex;padding:6px 8px;border:1px solid #68521f;border-radius:999px;color:#dfbd62;font-size:8px;font-weight:900;letter-spacing:1px;margin-bottom:10px}.access-strip{margin-top:18px;padding:20px 22px;border:1px solid #806423;border-radius:16px;background:linear-gradient(110deg,#17150e,#0a1118);display:flex;align-items:center;justify-content:space-between;gap:20px}.access-strip strong{display:block;color:#efd26e;font-size:15px;letter-spacing:.3px}.access-strip small{display:block;color:#948763;font-size:10px;margin-top:5px}.primary{display:inline-flex;align-items:center;justify-content:center;min-height:43px;padding:0 16px;border-radius:9px;font-size:10px;font-weight:950;letter-spacing:.9px;cursor:pointer}
.head{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:30px 2px 13px}.head span{display:block;color:#4fa7df;font-size:9px;font-weight:900;letter-spacing:2px}.head h2{margin:6px 0 0;font-size:20px}.head a{font-size:9px;color:#8ab4cf;font-weight:900}.records{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.record{padding:20px;border:1px solid #234058;border-radius:15px;background:#07131e}.rhead{display:flex;justify-content:space-between;gap:10px}.rhead b{font-size:15px}.badge{font-size:8px;font-weight:900;padding:5px 8px;border-radius:7px;background:#10324a;color:#8bc2df}.meta{margin-top:7px;color:#6f8798;font-size:9px}.fields{display:grid;gap:10px;margin-top:14px}.f{border-top:1px solid #173043;padding-top:9px}.f label{display:block;color:#668197;font-size:8px;font-weight:900;letter-spacing:1px;margin-bottom:4px}.f div{font-size:11px;line-height:1.55;color:#d0dbe2;overflow-wrap:anywhere}.full{white-space:pre-wrap;margin-top:15px;padding:13px;border:1px solid #19364b;border-radius:9px;background:#050c13;color:#9fb1bd;font-size:10px;line-height:1.7}.photo-upload{padding:25px;text-align:center;border:1px dashed #395d76;border-radius:14px;background:#07131e}.photo-upload input{max-width:100%;margin:12px auto;color:#a1b0bc}.copy{display:flex;gap:8px;margin-top:12px}.copy input{flex:1;height:41px;border:1px solid #24465e;border-radius:8px;background:#06111a;color:#dce8ef;padding:0 10px;font-size:10px}
.users{display:grid;gap:12px;margin-top:20px}.urow{display:grid;grid-template-columns:1fr .9fr 1.35fr;gap:18px;padding:17px;border:1px solid #234057;border-radius:14px;background:#07131e}.urow b{font-size:13px}.urow small{display:block;color:#678095;font-size:8px;margin-top:4px;letter-spacing:.4px}.pill{display:inline-block;padding:5px 7px;border-radius:7px;font-size:7px;font-weight:900;margin-right:4px;margin-top:5px}.pill.o{background:#0e3025;color:#83ddb0}.pill.x{background:#1b2329;color:#82949f}.pill.a{background:#14354a;color:#91c9e9}.pill.p{background:#302312;color:#e4c268}.uform{display:grid;grid-template-columns:1fr 1fr auto;gap:7px;margin-top:10px}.uform input{height:39px;border:1px solid #29465d;background:#06111a;color:#eef3f6;border-radius:8px;padding:0 9px;font-size:9px}.uform button{border:0;border-radius:8px;background:linear-gradient(135deg,#efcf68,#a9781b);color:#080b0d;font-size:8px;font-weight:950;padding:0 12px;cursor:pointer}
.login{max-width:590px;margin:55px auto}.login .panel{text-align:center;padding:42px}.logo{width:118px;height:118px;object-fit:contain;mix-blend-mode:screen;filter:drop-shadow(0 15px 25px #0009)}.form{display:grid;gap:11px;text-align:left;margin-top:25px}.field label{display:block;font-size:9px;color:#899dac;font-weight:900;letter-spacing:1.2px;margin-bottom:6px}.field input{width:100%;height:50px;border:1px solid #27475e;border-radius:9px;background:#06111a;color:#eef3f7;padding:0 13px;outline:none;font-size:13px}.field input:focus{border-color:#d6b657;box-shadow:0 0 0 3px #d6b65722}.status{margin-top:12px;padding:10px;border:1px solid #1b3a50;border-radius:9px;color:#85a0b3;font-size:9px}.status.ok{border-color:#2b6a53;color:#83dcae}.status.pend{border-color:#73581e;color:#e1c25f}
.wanted-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.wanted-card{border:1px solid #234058;border-radius:16px;overflow:hidden;background:linear-gradient(155deg,#0b1824,#06101a);box-shadow:0 18px 45px #0007}.wanted-photo{height:270px;background:#03080d;display:grid;place-items:center;position:relative;overflow:hidden}.wanted-photo img{width:100%;height:100%;object-fit:cover}.wanted-badge{position:absolute;left:12px;top:12px;padding:6px 8px;border-radius:7px;border:1px solid #d9b85855;background:#040a10de;color:#f0d478;font-size:7px;font-weight:950;letter-spacing:1px}.wanted-body{padding:18px}.wanted-title{font-size:18px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wanted-id{color:#d6b75c;font-size:8px;font-weight:900;letter-spacing:1px;margin-top:5px}.wanted-row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #173043;margin-top:11px;padding-top:10px}.wanted-row span{color:#617b8f;font-size:7px;font-weight:900;letter-spacing:1px}.wanted-row b{max-width:68%;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right}.wanted-open{display:block;margin-top:14px;padding:11px;text-align:center;border:1px solid #2e5771;border-radius:8px;color:#b8d3e2;font-size:8px;font-weight:950;letter-spacing:1px}.no-photo{height:100%;display:grid;place-items:center;color:#60798c}.no-photo span{font-size:14px;font-weight:900;letter-spacing:2px}.no-photo small{font-size:8px;margin-top:-70px}
.footer{text-align:center;border-top:1px solid #173044;color:#536c7f;font-size:8px;padding:18px}
@media(max-width:1050px){.top{padding:10px 22px}.brand{min-width:300px}.nav{gap:14px}.modules,.wanted-grid{grid-template-columns:repeat(2,1fr)}.hero-grid{grid-template-columns:1fr}.hero-panel{padding:40px 0 22px}.records{grid-template-columns:1fr}.urow{grid-template-columns:1fr 1fr}}
@media(max-width:720px){.top{min-height:74px;flex-wrap:wrap;gap:12px;padding:10px 14px}.brand{min-width:0;flex:1}.brand img{width:44px;height:44px}.brand b{font-size:11px}.brand span{font-size:8px}.top-actions{margin-left:auto}.nav{order:3;width:100%;overflow:auto;padding-bottom:3px}.wrap{width:calc(100% - 20px);padding:20px 0 35px}.hero-panel h1{font-size:39px}.sub{font-size:12px}.hero-mark{min-height:280px}.hero-mark img{width:145px;height:145px}.modules,.wanted-grid,.secondary-grid{grid-template-columns:1fr}.module{min-height:210px}.secondary{min-height:130px}.access-strip{align-items:stretch;flex-direction:column}.head{align-items:flex-start;flex-direction:column}.rhead{align-items:flex-start;flex-direction:column}.login{margin:25px auto}.login .panel{padding:27px 20px}.urow{grid-template-columns:1fr}.uform{grid-template-columns:1fr}.hero-actions{flex-direction:column}.primary,.hero-actions .btn{width:100%}.footer{font-size:7px}}
'''

def status_chip():
    d=v700.CLIENT is not None and getattr(v700.CLIENT, 'is_ready', lambda: False)()
    dhtml='<span class="statuschip ok"><i></i>DISCORD ONLINE</span>' if d else '<span class="statuschip warn"><i></i>DISCORD OFFLINE</span>'
    m=MAIL_STATUS.get('state') == 'CONECTADO'
    if m:mhtml='<span class="statuschip ok"><i></i>GMAIL CONECTADO</span>'
    elif MAIL_STATUS.get('state') == 'ERRO':mhtml='<span class="statuschip warn"><i></i>GMAIL EM FALHA</span>'
    else:mhtml='<span class="statuschip warn"><i></i>GMAIL AGUARDANDO</span>'
    return dhtml+mhtml

def module_card(icon,title,count,desc,href,button):
    return f'<a class="module" href="{v700.esc(href)}"><div class="icon">{v700.esc(icon)}</div><h3>{v700.esc(title)}</h3><div class="count">{v700.esc(count)}</div><p>{v700.esc(desc)}</p><div class="btnrow"><span class="btn gold">{v700.esc(button)} →</span></div></a>'

def home_701(u):
    bo=len(v700.C.get('boletins',[]) or []) if u.get('authorized') else '—'; pe=len(v700.C.get('pericias',[]) or []) if u.get('authorized') else '—'; pr=len(v700.C.get('procurados',[]) or [])
    auth=bool(u.get('authorized')); pending=bool(u.get('access_request_pending'))
    if auth:access='<a class="primary" href="/central">ABRIR CENTRAL OPERACIONAL →</a>'; access_text='Acesso operacional aprovado. Boletins, Perícias e Operações estão disponíveis.'
    elif pending:access='<span class="btn lock">SOLICITAÇÃO EM ANÁLISE</span>'; access_text='Sua solicitação já foi enviada ao canal interno de autorização.'
    else:access='<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="'+v700.esc(v700.csrf(u))+'"><button class="primary">SOLICITAR ACESSO RESTRITO →</button></form>'; access_text='A abertura da área restrita gera um pedido de autorização para o administrador.'
    body=f'''<section class="hero-grid"><section class="panel hero-copy"><div class="k">CENTRAL OPERACIONAL • DICOR</div><h1>Toda operação começa<br>com <span>informação.</span></h1><p class="sub">Acompanhe ocorrências, consulte Procurados, revise Perícias e organize informações operacionais em um único ambiente. A Central apresenta apenas os dados relevantes, sem mensagens automáticas ou tarefas internas do Discord.</p><div class="operator-line">OPERADOR: {v700.esc(u.get('qra'))} • PASSAPORTE {v700.esc(u.get('passaporte'))}</div><div class="statusbar">{status_chip()}</div></section><section class="panel hero-mark"><img src="{v700.esc(v700.LOGO)}" alt="Brasão DICOR" onerror="this.style.display='none'"></section></section><div class="section-title"><span>MÓDULOS DA CENTRAL</span><h2>CONSULTA RÁPIDA</h2></div><section class="modules">{module_card('01','Boletins Ativos',bo,'Ocorrências e registros completos disponíveis para consulta.','/boletins','ABRIR BOLETINS')}{module_card('02','Procurados Ativos',pr,'Lista oficial de indivíduos em situação ativa no sistema.','/procurados','CONSULTAR PROCURADOS')}{module_card('03','Perícias Pendentes',pe,'Laudos, coletas e registros periciais recebidos pela Central.','/pericias','ABRIR PERÍCIAS')}</section><section class="secondary-grid"><article class="secondary"><div class="copy"><span class="lock">ÁREA OPERACIONAL</span><h3>Operações</h3><p>Consulte registros operacionais autorizados e acompanhe informações reunidas pela Central.</p></div><a class="btn" href="/operacoes">ABRIR →</a></article><article class="secondary"><div class="copy"><span class="lock">FERRAMENTA</span><h3>Foto → FiveM</h3><p>Envie uma imagem e receba um link direto, pronto para copiar e utilizar no ambiente do servidor.</p></div><a class="btn" href="/fotos">GERAR LINK →</a></article></section><section class="access-strip"><div><strong>ACESSO À CENTRAL COMPLETA</strong><small>{v700.esc(access_text)}</small></div><div>{access}</div></section><div class="foot">PCPT POLÍCIA MORADA - POLÍCIA FEDERAL &nbsp;•&nbsp; DICOR • CENTRAL DE INTELIGÊNCIA</div>'''
    return _shell('DICOR • Central de Inteligência',body,u,v700.is_admin(u))

def _shell(title,body,u=None,admin=False):
    who=''
    if u:
        who=f'<div class="user"><i class="dot"></i><div><b>{v700.esc(u.get("nome") or u.get("qra"))}</b><small>PASSAPORTE {v700.esc(u.get("passaporte"))}</small></div></div><form method="post" action="/logout"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><button class="logout">SAIR</button></form>'
    links='<a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTO → FIVE M</a><a href="/central">ÁREA RESTRITA</a>' + ('<a href="/admin">USUÁRIOS</a>' if admin else '')
    csp="default-src 'self';img-src 'self' data: https:;connect-src 'self';style-src 'self' 'unsafe-inline';script-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'self';form-action 'self';object-src 'none'"
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{v700.esc(csp)}"><meta name="theme-color" content="#06111c"><title>{v700.esc(title)}</title><style>{CSS_701}</style></head><body><header class="top"><div class="top-inner" style="width:100%;display:flex;align-items:center;gap:28px"><a class="brand" href="/"><img src="{v700.esc(v700.LOGO)}" alt="DICOR" onerror="this.style.display=\'none\'"><div><b>DICOR • CENTRAL DE INTELIGÊNCIA</b><span>PCPT POLÍCIA FEDERAL • CAPITAL MORADA DO VALLEY</span></div></a><nav class="nav">{links}</nav><div class="top-actions">{who}</div></div></header><main class="wrap">{body}</main><footer class="footer">DICOR • CENTRAL DE INTELIGÊNCIA &nbsp;|&nbsp; PCPT POLÍCIA MORADA - POLÍCIA FEDERAL</footer><script>setInterval(function(){fetch('/api/heartbeat',{method:'POST',credentials:'same-origin',cache:'no-store'}).catch(function(){});},60000);function cp(v,b){if(!navigator.clipboard)return;navigator.clipboard.writeText(v).then(function(){var t=b.innerText;b.innerText='COPIADO';setTimeout(function(){b.innerText=t},1100)});}</script></body></html>'

def poll_mail_sync_robust():
    global MAIL_STATUS
    host,port,user,password,folder=v700.MAIL_HOST,v700.MAIL_PORT,v700.MAIL_USER,v700.MAIL_PASS,v700.MAIL_FOLDER
    out={x:[] for x in ('procurados','boletins','pericias','operacoes')}
    if not(host and user and password):MAIL_STATUS={'state':'AGUARDANDO','detail':'Variáveis de e-mail incompletas.'};return out
    last=''
    for attempt in range(1,4):
        conn=None
        try:
            conn=imaplib.IMAP4_SSL(host,port,timeout=45);conn.login(user,password);ok,_=conn.select(folder,readonly=True)
            if ok!='OK':raise RuntimeError(f'IMAP select: {ok}')
            ok,data=conn.uid('search',None,'ALL')
            if ok!='OK' or not data or not data[0]:MAIL_STATUS={'state':'CONECTADO','detail':'Caixa vazia ou sem mensagens.'};return out
            uids=list(reversed(data[0].split()[-v700.MAIL_LIMIT:]))
            for uid in uids:
                try:
                    ok,fetched=conn.uid('fetch',uid,'(BODY.PEEK[])');raw=b''.join(part[1] for part in (fetched or []) if isinstance(part,tuple) and len(part)>1 and isinstance(part[1],bytes))
                    if ok!='OK' or not raw:continue
                    msg=email.message_from_bytes(raw);body,files=v700.mail_body(msg);body=_clean_source(body);kind=v700.mail_kind(v700.dh(msg.get('Subject','')),body)
                    if kind:out[kind].append(v700.mail_row(kind,msg,uid,body,files))
                except Exception:continue
            MAIL_STATUS={'state':'CONECTADO','detail':f'{sum(len(v) for v in out.values())} registro(s) lido(s)'};return out
        except Exception as exc:
            last=f'{type(exc).__name__}: {exc}'
            if attempt<3:time.sleep(2*attempt)
        finally:
            if conn:
                try:conn.logout()
                except Exception:pass
    MAIL_STATUS={'state':'ERRO','detail':last};print(f'⚠️ [CENTRAL MAIL V701] {last}',flush=True);return out

def _clean_source(v):
    return v700.clean_source(v) if hasattr(v700,'clean_source') else str(v or '')

v700.home=home_701
v700.CSS=CSS_701
v700.poll_mail_sync=poll_mail_sync_robust
v700.poll_mail=lambda: __import__('asyncio').to_thread(poll_mail_sync_robust)

def install(bot_module: Any):
    return v700.install(bot_module)
