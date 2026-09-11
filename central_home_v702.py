# -*- coding: utf-8 -*-
"""DICOR Central V702.

Renderer estável baseado diretamente na composição visual aprovada pelo usuário.
Não altera o núcleo V700: autenticação, autorização, persistência, Discord,
Gmail, Procurados, Boletins, Perícias, Operações e FiveM continuam no módulo base.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import time
from typing import Any

import central_home_v700 as v700

CSS_702 = r'''
:root{--bg:#03070b;--bg2:#07131d;--panel:#0b1823;--panel2:#0e1d29;--line:#2a4051;--line-soft:#1b3040;--gold:#e0bb52;--gold2:#f0d477;--blue:#55a7dc;--text:#f3f6f8;--muted:#a0afba;--dim:#708391;--ok:#5bd39b;--warn:#dfbe61}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:radial-gradient(circle at 77% 9%,#143e59 0,transparent 30%),radial-gradient(circle at 18% 0,#142b3e 0,transparent 26%),#03070b;color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}
.top{position:sticky;top:0;z-index:100;min-height:90px;border-bottom:1px solid #294253;background:rgba(3,9,14,.94);backdrop-filter:blur(18px)}
.top-inner{width:min(1420px,calc(100% - 44px));min-height:90px;margin:auto;display:flex;align-items:center;gap:28px}
.brand{display:flex;align-items:center;gap:15px;min-width:430px}.brand img{width:60px;height:60px;object-fit:contain;filter:drop-shadow(0 8px 16px #0008)}
.brand b{display:block;font-size:17px;letter-spacing:1.6px;line-height:1.1}.brand span{display:block;color:#d9b451;font-size:10px;font-weight:900;letter-spacing:2.8px;margin-top:6px}
.nav{display:flex;align-items:center;gap:22px;margin-left:auto}.nav a{color:#9cafbd;font-size:10px;font-weight:900;letter-spacing:1px;white-space:nowrap}.nav a:hover{color:#f0f4f7}
.top-actions{display:flex;align-items:center;gap:11px;margin-left:4px}.user{display:flex;align-items:center;gap:8px}.dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 13px var(--ok)}.user b{font-size:10px}.user small{display:block;color:#657f91;font-size:8px;margin-top:3px}.logout{border:1px solid #29475a;background:#07151e;color:#a7b6c0;border-radius:8px;padding:9px 11px;font-size:8px;font-weight:900;cursor:pointer}
.wrap{width:min(1120px,calc(100% - 42px));margin:auto;padding:42px 0 70px}
.hero{display:grid;grid-template-columns:1.08fr .92fr;gap:20px;align-items:stretch}.panel{border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,rgba(11,24,35,.97),rgba(5,13,20,.98));box-shadow:0 25px 75px #0009}
.hero-copy{padding:54px 46px 45px}.eyebrow{color:var(--blue);font-size:10px;font-weight:900;letter-spacing:2.6px}.hero-copy h1{font-family:Georgia,'Times New Roman',serif;font-size:53px;line-height:1.04;font-weight:500;margin:15px 0 18px;letter-spacing:.1px}.hero-copy h1 span{color:var(--gold2)}.hero-copy>p{color:#a6b2bb;font-size:14px;line-height:1.85;max-width:650px;margin:0}.operator{margin-top:24px;color:#d8b85d;font-size:11px;font-weight:900;letter-spacing:1.2px;text-transform:uppercase}
.statusbar{display:flex;gap:9px;flex-wrap:wrap;margin-top:19px}.chip{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #294152;border-radius:999px;background:#07141d;color:#8fa4b1;font-size:9px;font-weight:900;letter-spacing:.8px}.chip i{width:7px;height:7px;border-radius:50%;background:#637887}.chip.ok{border-color:#2c5d4a;color:#a1dfc1}.chip.ok i{background:var(--ok);box-shadow:0 0 9px var(--ok)}.chip.warn{border-color:#685727;color:#e4cb7a}.chip.warn i{background:var(--warn);box-shadow:0 0 9px var(--warn)}
.hero-mark{min-height:365px;display:grid;place-items:center;position:relative;overflow:hidden;background:radial-gradient(circle at 50% 45%,#173e58 0,#0b1f2e 42%,#061019 76%)}.hero-mark:before{content:"";position:absolute;width:278px;height:278px;border:1px solid #53a8dd65;border-radius:50%;box-shadow:0 0 0 39px #53a8dd0c,0 0 0 78px #53a8dd06,0 0 85px #0c75ae1d}.hero-mark img{position:relative;width:205px;height:205px;object-fit:contain;filter:drop-shadow(0 18px 32px #000c)}
.section-title{margin:38px 0 14px}.section-title span{display:block;color:var(--blue);font-size:9px;font-weight:900;letter-spacing:2.6px}.section-title h2{font-size:20px;letter-spacing:1.5px;margin:6px 0 0}
.modules{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.module{min-height:260px;padding:24px;display:flex;flex-direction:column;border:1px solid #294458;border-radius:17px;background:linear-gradient(155deg,#0b1926,#07111a);transition:.18s;cursor:pointer}.module:hover{transform:translateY(-3px);border-color:#4e718a;box-shadow:0 16px 40px #0008}.module .module-top{display:flex;justify-content:space-between;align-items:center}.module .icon{width:44px;height:44px;display:grid;place-items:center;border:1px solid #32566f;border-radius:10px;background:#091c2a;color:#d4e8f5;font-size:14px;font-weight:900}.module .badge{padding:6px 8px;border:1px solid #2f5166;border-radius:999px;color:#8db8d2;background:#08141e;font-size:8px;font-weight:900;letter-spacing:.8px}.module h3{font-size:18px;margin:21px 0 0}.module .count{font-size:33px;color:var(--gold2);font-weight:900;margin-top:10px}.module p{color:#91a0aa;font-size:12px;line-height:1.65;margin:9px 0 0}.module .btnrow{margin-top:auto;padding-top:22px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 15px;border:1px solid #355872;border-radius:9px;background:#0a1b29;color:#d2e0e8;font-size:10px;font-weight:950;letter-spacing:.8px}.btn.gold{border:0;background:linear-gradient(135deg,#f0d16c,#a87819);color:#080b0d;box-shadow:0 9px 22px #0008}
.secondary-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:16px}.secondary{min-height:148px;padding:23px;border:1px solid #243e50;border-radius:16px;background:linear-gradient(155deg,#091720,#06101a);display:flex;align-items:center;justify-content:space-between;gap:18px}.secondary .label{display:inline-flex;padding:6px 9px;border:1px solid #66511f;border-radius:999px;color:#debd63;font-size:8px;font-weight:900;letter-spacing:1px}.secondary h3{font-size:18px;margin:10px 0 6px}.secondary p{margin:0;color:#8396a4;font-size:11px;line-height:1.6;max-width:440px}
.access-strip{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:18px;padding:20px 23px;border:1px solid #826620;border-radius:16px;background:linear-gradient(110deg,#16140d,#08111a)}.access-strip strong{display:block;color:#f0d271;font-size:15px}.access-strip small{display:block;color:#948766;font-size:10px;margin-top:5px}.pending{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 16px;border:1px solid #705a22;border-radius:9px;color:#e4c76e;background:#17150d;font-size:10px;font-weight:900}
.wanted-wrap{margin-top:18px}.wanted-head{display:flex;align-items:end;justify-content:space-between;margin:29px 2px 13px}.wanted-head span{display:block;color:var(--blue);font-size:9px;font-weight:900;letter-spacing:2px}.wanted-head h2{font-size:20px;margin:6px 0 0}.wanted-head a{font-size:9px;color:#8db8d0;font-weight:900}.wanted-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.wanted-card{overflow:hidden;border:1px solid #294458;border-radius:16px;background:#07121b}.wanted-photo{height:265px;background:#02070b;display:grid;place-items:center;position:relative}.wanted-photo img{width:100%;height:100%;object-fit:cover}.wanted-badge{position:absolute;left:12px;top:12px;padding:6px 8px;border:1px solid #dfbb5255;border-radius:7px;background:#03090edb;color:#f1d477;font-size:7px;font-weight:950;letter-spacing:1px}.wanted-body{padding:17px}.wanted-title{font-size:18px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wanted-id{color:#d9bb60;font-size:8px;font-weight:900;letter-spacing:1px;margin-top:5px}.wanted-row{display:flex;justify-content:space-between;gap:12px;padding-top:10px;margin-top:10px;border-top:1px solid #173044}.wanted-row span{font-size:7px;font-weight:900;color:#627b8d;letter-spacing:1px}.wanted-row b{max-width:66%;font-size:9px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wanted-open{display:block;text-align:center;margin-top:14px;padding:11px;border:1px solid #2f5872;border-radius:8px;color:#bfd8e6;font-size:8px;font-weight:950;letter-spacing:1px}.no-photo{display:grid;place-items:center;color:#5e7587}.no-photo b{font-size:14px;letter-spacing:2px}.no-photo small{font-size:8px;margin-top:4px}
.footer{text-align:center;border-top:1px solid #173044;color:#536c7c;font-size:8px;padding:18px}
.login{max-width:590px;margin:55px auto}.login .panel{padding:42px;text-align:center}.login .logo{width:130px;height:130px;object-fit:contain}.login h1{font-size:28px}.form{display:grid;gap:12px;text-align:left;margin-top:25px}.field label{display:block;font-size:9px;color:#899daa;font-weight:900;letter-spacing:1.1px;margin-bottom:6px}.field input{width:100%;height:51px;background:#06111a;color:#eef3f7;border:1px solid #28465b;border-radius:9px;padding:0 13px;font-size:13px}.field input:focus{border-color:#d8b95c;box-shadow:0 0 0 3px #d8b95c22;outline:none}
@media(max-width:1120px){.top{padding:0 20px}.top-inner{width:100%}.brand{min-width:315px}.nav{gap:14px}.modules,.wanted-grid{grid-template-columns:repeat(2,1fr)}.hero{grid-template-columns:1fr}.hero-copy{padding:42px}.hero-mark{min-height:300px}.records{grid-template-columns:1fr}}
@media(max-width:760px){.top{min-height:78px}.top-inner{min-height:78px;flex-wrap:wrap;padding:10px 0}.brand{min-width:0;flex:1}.brand img{width:45px;height:45px}.brand b{font-size:12px}.brand span{font-size:8px}.nav{order:3;width:100%;overflow:auto;padding-bottom:2px}.wrap{width:calc(100% - 20px);padding:22px 0 42px}.hero-copy{padding:31px 25px}.hero-copy h1{font-size:39px}.hero-copy>p{font-size:12px}.hero-mark{min-height:275px}.hero-mark img{width:150px;height:150px}.modules,.wanted-grid,.secondary-grid{grid-template-columns:1fr}.module{min-height:220px}.access-strip{flex-direction:column;align-items:stretch}.access-strip .btn,.access-strip .pending{width:100%}.wanted-head{align-items:flex-start;flex-direction:column;gap:10px}.secondary{align-items:stretch;flex-direction:column}.secondary .btn{width:100%}}
'''

def _status_chips() -> str:
    discord_online=bool(v700.CLIENT is not None and getattr(v700.CLIENT,'is_ready',lambda:False)())
    d='<span class="chip ok"><i></i>DISCORD ONLINE</span>' if discord_online else '<span class="chip warn"><i></i>DISCORD OFFLINE</span>'
    state=str(getattr(v700,'MAIL_STATUS',{}).get('state',''))
    if state=='CONECTADO':m='<span class="chip ok"><i></i>GMAIL CONECTADO</span>'
    elif state=='ERRO':m='<span class="chip warn"><i></i>GMAIL EM FALHA</span>'
    else:m='<span class="chip warn"><i></i>GMAIL AGUARDANDO</span>'
    return d+m

def _module(icon,title,count,desc,href,button,locked=False):
    badge='RESTRITO' if locked else 'DISPONÍVEL'
    return f'''<a class="module" href="{v700.esc(href)}"><div class="module-top"><span class="icon">{icon}</span><span class="badge">{badge}</span></div><h3>{v700.esc(title)}</h3><div class="count">{v700.esc(count)}</div><p>{v700.esc(desc)}</p><div class="btnrow"><span class="btn gold">{v700.esc(button)} →</span></div></a>'''

def _shell702(title,body,u):
    who=''
    if u:
        who=f'''<div class="user"><i class="dot"></i><div><b>{v700.esc(u.get("nome") or u.get("qra"))}</b><small>PASSAPORTE {v700.esc(u.get("passaporte"))}</small></div></div><form method="post" action="/logout"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><button class="logout">SAIR</button></form>'''
    admin=v700.is_admin(u) if u else False
    links='<a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTO → FIVE M</a><a href="/central">ÁREA RESTRITA</a>'+('<a href="/admin">USUÁRIOS</a>' if admin else '')
    csp="default-src 'self';img-src 'self' data: https:;connect-src 'self';style-src 'self' 'unsafe-inline';script-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'self';form-action 'self';object-src 'none'"
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{v700.esc(csp)}"><meta name="theme-color" content="#06111c"><title>{v700.esc(title)}</title><style>{CSS_702}</style></head><body><header class="top"><div class="top-inner"><a class="brand" href="/"><img src="{v700.esc(v700.LOGO)}" alt="Brasão DICOR" onerror="this.style.display='none'"><div><b>DICOR • CENTRAL DE INTELIGÊNCIA</b><span>PCPT POLÍCIA FEDERAL • CAPITAL MORADA DO VALLEY</span></div></a><nav class="nav">{links}</nav><div class="top-actions">{who}</div></div></header><main class="wrap">{body}</main><footer class="footer">DICOR • CENTRAL DE INTELIGÊNCIA &nbsp;|&nbsp; PCPT POLÍCIA MORADA - POLÍCIA FEDERAL</footer></body></html>'''

def home_702(u):
    rs=list(v700.C.get('procurados',[]) or []); bs=list(v700.C.get('boletins',[]) or []); ps=list(v700.C.get('pericias',[]) or [])
    auth=bool(u.get('authorized')); pending=bool(u.get('access_request_pending'))
    bo=len(bs) if auth else '—'; pe=len(ps) if auth else '—'
    if auth: access='<a class="btn gold" href="/central">ABRIR CENTRAL OPERACIONAL →</a>'; access_text='Acesso autorizado. Boletins, Perícias e Operações estão disponíveis.'
    elif pending: access='<span class="pending">SOLICITAÇÃO EM ANÁLISE</span>'; access_text='Seu pedido já foi enviado ao canal interno de autorização.'
    else: access='<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="'+v700.esc(v700.csrf(u))+'"><button class="btn gold">SOLICITAR ACESSO RESTRITO →</button></form>'; access_text='A abertura da área restrita exige aprovação do administrador.'
    cards=[]
    for r in rs[:3]:
        fs=r.get('fields') or {}
        image=f'<img src="{v700.esc(r.get("image"))}" alt="Foto do procurado" loading="lazy">' if r.get('image') else '<div class="no-photo"><b>DICOR</b><small>SEM FOTO</small></div>'
        cards.append(f'''<article class="wanted-card"><div class="wanted-photo">{image}<span class="wanted-badge">PROCURADO ATIVO</span></div><div class="wanted-body"><div class="wanted-title">{v700.esc(r.get('name') or 'Indivíduo não identificado')}</div><div class="wanted-id">REGISTRO {v700.esc(r.get('number') or 'S/N')}</div><div class="wanted-row"><span>CRIMES</span><b>{v700.esc(fs.get('Crimes') or 'Não informado')}</b></div><div class="wanted-row"><span>LOCALIZAÇÃO</span><b>{v700.esc(fs.get('Localização') or 'Não informado')}</b></div><a class="wanted-open" href="/registro/procurados/{v700.esc(r.get('id'))}">ABRIR FICHA COMPLETA →</a></div></article>''')
    body=f'''<section class="hero"><section class="panel hero-copy"><div class="eyebrow">CENTRAL OPERACIONAL</div><h1>Toda operação começa<br>com <span>informação.</span></h1><p>Acompanhe ocorrências, consulte Procurados, revise Perícias e organize informações operacionais em um único ambiente. A Central apresenta apenas os dados relevantes, sem mensagens automáticas ou tarefas internas do Discord.</p><div class="operator">OPERADOR: {v700.esc(u.get('qra'))} • PASSAPORTE {v700.esc(u.get('passaporte'))}</div><div class="statusbar">{_status_chips()}</div></section><section class="panel hero-mark"><img src="{v700.esc(v700.LOGO)}" alt="Brasão DICOR" onerror="this.style.display='none'"></section></section><div class="section-title"><span>MÓDULOS DA CENTRAL</span><h2>CONSULTA RÁPIDA</h2></div><section class="modules">{_module('01','Boletins Ativos',bo,'Ocorrências e registros completos disponíveis para consulta.','/boletins','ABRIR BOLETINS',not auth)}{_module('02','Procurados Ativos',len(rs),'Lista oficial dos indivíduos em situação ativa no sistema.','/procurados','CONSULTAR PROCURADOS')}{_module('03','Perícias Pendentes',pe,'Laudos, coletas e registros periciais recebidos pela Central.','/pericias','ABRIR PERÍCIAS',not auth)}</section><div class="wanted-wrap"><div class="wanted-head"><div><span>MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div><a href="/procurados">ABRIR TODOS →</a></div><section class="wanted-grid">{''.join(cards) or '<div class="empty">Nenhum Procurado ativo encontrado.</div>'}</section></div><section class="secondary-grid"><article class="secondary"><div><span class="label">ÁREA OPERACIONAL</span><h3>Operações</h3><p>Consulte registros operacionais e acompanhe as informações reunidas pela Central.</p></div><a class="btn" href="/operacoes">ABRIR →</a></article><article class="secondary"><div><span class="label">FERRAMENTA</span><h3>Foto → FiveM</h3><p>Envie uma imagem e receba um link direto pronto para copiar e utilizar no servidor.</p></div><a class="btn" href="/fotos">GERAR LINK →</a></article></section><section class="access-strip"><div><strong>ACESSO À CENTRAL COMPLETA</strong><small>{v700.esc(access_text)}</small></div><div>{access}</div></section>'''
    return _shell702('DICOR • Central de Inteligência',body,u)

def mail_poll_sync_702():
    out={x:[] for x in ('procurados','boletins','pericias','operacoes')}
    host,user,password=v700.MAIL_HOST,v700.MAIL_USER,v700.MAIL_PASS
    if not(host and user and password):
        v700.MAIL_STATUS={'state':'AGUARDANDO','detail':'Variáveis de e-mail incompletas.'}
        return out
    last=''
    for attempt in range(1,4):
        conn=None
        try:
            conn=imaplib.IMAP4_SSL(host,v700.MAIL_PORT,timeout=45);conn.login(user,password);ok,_=conn.select(v700.MAIL_FOLDER,readonly=True)
            if ok!='OK':raise RuntimeError(f'IMAP select: {ok}')
            ok,data=conn.uid('search',None,'ALL')
            if ok!='OK' or not data or not data[0]:
                v700.MAIL_STATUS={'state':'CONECTADO','detail':'Caixa conectada • nenhuma mensagem encontrada'}
                return out
            for uid in reversed(data[0].split()[-v700.MAIL_LIMIT:]):
                try:
                    ok,fetched=conn.uid('fetch',uid,'(BODY.PEEK[])')
                    raw=b''.join(part[1] for part in (fetched or []) if isinstance(part,tuple) and len(part)>1 and isinstance(part[1],bytes))
                    if ok!='OK' or not raw:continue
                    msg=email.message_from_bytes(raw);body,files=v700.mail_body(msg);kind=v700.mail_kind(v700.dh(msg.get('Subject','')),v700.clean_source(body))
                    if kind:out[kind].append(v700.mail_row(kind,msg,uid,v700.clean_source(body),files))
                except Exception:continue
            v700.MAIL_STATUS={'state':'CONECTADO','detail':f'Gmail conectado • {sum(len(v) for v in out.values())} registro(s) lido(s)'}
            return out
        except Exception as exc:
            last=f'{type(exc).__name__}: {exc}'
            if attempt<3:time.sleep(2*attempt)
        finally:
            if conn:
                try:conn.logout()
                except Exception:pass
    v700.MAIL_STATUS={'state':'ERRO','detail':f'Gmail indisponível • {last}'}
    print(f'⚠️ [CENTRAL MAIL V702] {last}',flush=True)
    return out

def install(bot_module: Any):
    v700.home=home_702
    v700.poll_mail_sync=mail_poll_sync_702
    v700.poll_mail=lambda: asyncio.to_thread(mail_poll_sync_702)
    return v700.install(bot_module)
