# -*- coding: utf-8 -*-
"""Central DICOR V608.

Replica o painel clássico aprovado da Central, mas lê os registros vivos do
Discord. A Central é somente leitura: não cria, renomeia, fecha ou reabre BOs.
Identificação operacional usa QRA + passaporte, como no painel anterior.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import html
import os
import re
import time
from datetime import timezone
from typing import Any
import discord
from aiohttp import web

BO_TARGET_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
PERICIA_CHANNEL_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
PROCURADOS_CHANNEL_ID = int(os.getenv("DICOR_PROCURADOS_CHANNEL_ID", "1490200533980545097"))
PORT = int(os.getenv("PORT", "8080"))
COOKIE = "dicor_operador_v608"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v608"))
COOKIE_DAYS = 30


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def clean(v: Any) -> str:
    return " ".join(str(v or "").split())


def msg_text(m: discord.Message) -> str:
    parts = [m.content or ""]
    for e in m.embeds or []:
        parts += [e.title or "", e.description or ""]
        parts += [f"{f.name}: {f.value}" for f in e.fields or []]
    return clean(" ".join(x for x in parts if x))


def closed(name: str, text: str) -> bool:
    s = clean(name + " " + text).casefold()
    return any(x in s for x in ("concluído", "concluido", "finalizado", "encerrado", "fechado", "cancelado"))


def num(text: str) -> str:
    for p in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(p, text, re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return "S/N"


def sign(payload: str) -> str:
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def cookie_value(qra: str, passport: str) -> str:
    payload = f"{qra}|{passport}|{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return raw + "." + sign(payload)


def operator(request: web.Request) -> tuple[str, str] | None:
    token = request.cookies.get(COOKIE, "")
    if "." not in token:
        return None
    try:
        raw, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, sign(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())):
            return None
        qra, passport, issued = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode().split("|", 2)
        if time.time() - int(issued) > COOKIE_DAYS * 86400:
            return None
        return qra, passport
    except Exception:
        return None


LOGIN_CSS = '''body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% -20%,#4b391266,transparent 45%),#070806;color:#f7f1db;font-family:Inter,Arial}.box{width:min(470px,calc(100% - 40px));background:linear-gradient(145deg,#14160f,#0b0c09);border:1px solid #493b1d;border-radius:24px;padding:34px;box-shadow:0 28px 90px #000b}.top{display:flex;gap:16px;align-items:center}.mark{width:72px;height:80px;border:1px solid #d7a93d;border-radius:50%;display:grid;place-items:center;color:#f2d47d;font-weight:900}.small{color:#d7a93d;letter-spacing:1.8px;font-size:11px}h1{font:31px Georgia;margin:5px 0}p{color:#a39c87;line-height:1.55}label{display:block;color:#d5c89d;font-size:12px;margin-top:16px}input{width:100%;margin-top:7px;padding:14px;background:#080906;color:#fff5d0;border:1px solid #40361d;border-radius:11px;font-size:16px;outline:0}button{width:100%;margin-top:22px;border:0;border-radius:11px;padding:14px;background:linear-gradient(135deg,#f2d47d,#d7a93d);font-weight:900;cursor:pointer}.aviso{border-left:3px solid #d7a93d;background:#18160d;padding:12px;margin-top:18px;color:#c9c0a5;font-size:13px}.erro{background:#381717;border:1px solid #7c3939;color:#ffd0d0;padding:11px;border-radius:10px;margin:13px 0}'''


def login_page(next_url: str, error: str = "") -> str:
    err = f'<div class="erro">{esc(error)}</div>' if error else ""
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Identificação Operacional • DICOR</title><style>{LOGIN_CSS}</style></head><body><form class="box" method="post" action="/cadastro-operador"><div class="top"><div class="mark">PF<br><small>DICOR</small></div><div><div class="small">IDENTIFICAÇÃO OPERACIONAL</div><h1>Registro de agente</h1></div></div><p>Antes de acessar os registros da Central, identifique seu personagem. A identificação fica salva neste navegador.</p>{err}<input type="hidden" name="next" value="{esc(next_url)}"><label>QRA</label><input name="qra" maxlength="45" placeholder="Ex.: Baiano" required><label>Passaporte</label><input name="passaporte" maxlength="12" inputmode="numeric" placeholder="Ex.: 6027" required><div class="aviso">Os acessos ficam registrados para controle interno da Polícia Federal.</div><button>ENTRAR EM SERVIÇO</button></form></body></html>'''


async def get_channel(client: discord.Client, cid: int):
    c = client.get_channel(cid)
    if c: return c
    try: return await client.fetch_channel(cid)
    except Exception: return None


async def threads(parent: Any):
    if not isinstance(parent, discord.TextChannel): return []
    result = list(getattr(parent, "threads", []) or [])
    seen = {x.id for x in result}
    try:
        async for t in parent.archived_threads(limit=None):
            if t.id not in seen: result.append(t); seen.add(t.id)
    except Exception: pass
    return result


async def live_threads(client: discord.Client, cid: int, kind: str):
    parent = await get_channel(client, cid)
    out=[]
    for t in await threads(parent):
        if t.archived or t.locked: continue
        messages=[]
        try:
            async for m in t.history(limit=12, oldest_first=True): messages.append(m)
        except Exception: pass
        text=" ".join(msg_text(m) for m in messages)
        if closed(t.name,text): continue
        agent="Aguardando responsável" if kind=="bo" else "Aguardando agente"
        for m in messages:
            mt=msg_text(m)
            hit=re.search(r"(?:Responsável|Responsavel|Agente)\s*:\s*(?:<@!?(\d+)>|([^|\n]+))",mt,re.I)
            if hit: agent=hit.group(1) or clean(hit.group(2)); break
        out.append({"number":num(t.name),"name":t.name,"agent":agent,"created":t.created_at,"url":f"https://discord.com/channels/{t.guild.id}/{t.id}"})
    out.sort(key=lambda x:x["created"],reverse=True)
    return out


async def live_procurados(client: discord.Client):
    rows=[]
    ids=[PROCURADOS_CHANNEL_ID]
    channels=[]
    for g in getattr(client,"guilds",[]):
        for c in getattr(g,"text_channels",[]):
            n=clean(getattr(c,"name","")).casefold()
            if any(k in n for k in ("procurad","foragid","mandado")) and c.id not in ids: ids.append(c.id)
    for cid in ids:
        c=await get_channel(client,cid)
        if not c: continue
        try:
            async for m in c.history(limit=100):
                text=msg_text(m)
                if text and not closed("",text): rows.append({"number":num(text),"name":text[:140],"agent":str(m.author),"created":m.created_at,"url":m.jump_url})
        except Exception: pass
    rows.sort(key=lambda x:x["created"],reverse=True)
    return rows[:50]


CSS=''' :root{--g:#d7a93d;--g2:#f2d47d;--bg:#070806;--l:#3b321a;--t:#f7f1db;--m:#96917e}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -20%,#3a2d0c55,transparent 42%),var(--bg);color:var(--t);font-family:Inter,Arial;min-height:100vh}header{height:108px;border-bottom:1px solid var(--l);display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 4vw;background:#090a07f4}.brand{grid-column:2;display:flex;align-items:center;gap:15px}.brand .img{width:74px;height:80px;border:1px solid var(--g);border-radius:50%;display:grid;place-items:center;color:var(--g2);font-weight:900}.brand h1{margin:0;font-size:20px;letter-spacing:2px}.brand small{color:var(--g);letter-spacing:1.5px}.nav{justify-self:end;display:flex;gap:16px;flex-wrap:wrap}.nav a{color:#e8dcab;text-decoration:none;font-size:13px}.nav a:hover,.nav .active{color:var(--g2)}main{max-width:1250px;margin:auto;padding:58px 24px 75px}.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:34px;align-items:center;margin-bottom:44px}.label{font-size:11px;letter-spacing:2px;color:var(--g)}.hero h2{font:52px/1.04 Georgia;margin:10px 0 18px}.hero h2 span{color:var(--g2)}.hero p{color:#bbb49c;font-size:17px;line-height:1.65}.mark{height:260px;border:1px solid var(--l);border-radius:28px;background:linear-gradient(145deg,#17180f,#0b0c09);display:grid;place-items:center}.mark b{font-size:55px;color:var(--g2)}.operator{margin-top:15px;color:#d2bd73;font-size:11px;letter-spacing:1.1px}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:40px}.summary a{display:flex;justify-content:space-between;align-items:center;text-decoration:none;color:var(--t);border:1px solid var(--l);background:#0d0f0b;border-radius:14px;padding:16px 18px}.summary b{font-size:25px;color:var(--g2)}.section{font-size:11px;letter-spacing:2px;color:var(--g);margin-bottom:15px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:17px}.grid article{min-height:225px;padding:25px;border:1px solid #2e2919;border-radius:18px;background:linear-gradient(155deg,#15170f,#0c0d0a);position:relative}.grid article:hover{border-color:#8b712d;transform:translateY(-3px)}.ico{font-size:30px}.grid h3{margin:18px 0 7px}.grid strong{display:block;font-size:36px;color:var(--g2)}.grid p{color:var(--m);line-height:1.5;min-height:48px}.grid a{display:inline-flex;text-decoration:none;color:#111;background:linear-gradient(135deg,var(--g2),var(--g));padding:10px 14px;border-radius:9px;font-weight:800}.private:after{content:'ACESSO RESTRITO';position:absolute;right:15px;top:15px;color:#bfa85d;font-size:9px;letter-spacing:1.2px;border:1px solid #5b4b22;border-radius:99px;padding:5px 8px}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card{padding:20px;border:1px solid #2e2919;border-radius:14px;background:linear-gradient(145deg,#14160f,#0d0e0b)}.tag{color:var(--g2);font-size:9px;border:1px solid #5b4b22;border-radius:20px;padding:5px 8px;letter-spacing:1px}.card h3{font-size:20px}.meta{display:flex;justify-content:space-between;border-top:1px solid #282319;padding:9px 0;font-size:11px}.meta span{color:var(--m)}.open{color:var(--g2);text-decoration:none;font-size:11px;font-weight:900}.empty{text-align:center;border:1px dashed #40381f;padding:30px;color:var(--m);border-radius:14px}footer{text-align:center;color:#625f52;font-size:11px;padding:0 20px 42px}@media(max-width:900px){header{height:auto;grid-template-columns:1fr;padding:15px}.brand{grid-column:1}.nav{justify-self:start;margin-top:12px}.hero{grid-template-columns:1fr}.mark{display:none}.grid,.cards{grid-template-columns:1fr}}@media(max-width:650px){.summary{grid-template-columns:1fr}.hero h2{font-size:36px}}'''


def card(row, kind):
    label="BOLETIM" if kind=="bo" else "PERÍCIA" if kind=="per" else "PROCURADO"
    dt=row["created"]
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    d=dt.astimezone().strftime("%d/%m/%Y %H:%M")
    return f'<article class="card"><span class="tag">{label}</span><h3>Nº {esc(row["number"])}</h3><div class="meta"><span>Registro</span><b>{esc(row["name"][:75])}</b></div><div class="meta"><span>Responsável</span><b>{esc(row["agent"])}</b></div><div class="meta"><span>Data</span><b>{d}</b></div><a class="open" href="{esc(row["url"])}" target="_blank">Abrir no Discord →</a></article>'


def page(title, active, body, bo, pr, pe, op=None):
    operator_line=f'<div class="operator">OPERADOR: {esc(op[0])} • PASSAPORTE {esc(op[1])}</div>' if op else ''
    nav=f'<a class="{"active" if active=="central" else ""}" href="/">Central</a><a class="{"active" if active=="bo" else ""}" href="/boletins">Boletins</a><a class="{"active" if active=="pr" else ""}" href="/procurados">Procurados</a><a class="{"active" if active=="pe" else ""}" href="/pericias">Perícias</a><a class="private" href="/fichas">Banco de Dados</a><a class="private" href="/arvore">Árvore</a>'
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • {esc(title)}</title><style>{CSS}</style></head><body><header><div></div><div class="brand"><div class="img">PF</div><div><h1>DICOR • CENTRAL DE INTELIGÊNCIA</h1><small>CONSULTA INTERNA • SISTEMA INTEGRADO</small></div></div><nav class="nav">{nav}</nav></header><main>{operator_line}{body}</main><footer>DICOR • POLÍCIA FEDERAL • AMBIENTE FICTÍCIO DE GTA RP</footer></body></html>'


async def dashboard(client, op):
    bo=await live_threads(client,BO_TARGET_ID,"bo"); pe=await live_threads(client,PERICIA_CHANNEL_ID,"per"); pr=await live_procurados(client)
    cards=''.join([f'<article><div class="ico">📋</div><h3>Boletins Ativos</h3><strong>{len(bo)}</strong><p>Ocorrências ainda em aberto ou atendimento.</p><a href="/boletins">Abrir módulo</a></article>',f'<article><div class="ico">🎯</div><h3>Procurados Ativos</h3><strong>{len(pr)}</strong><p>Lista oficial do canal de procurados ativos.</p><a href="/procurados">Abrir módulo</a></article>',f'<article><div class="ico">🧪</div><h3>Perícias Pendentes</h3><strong>{len(pe)}</strong><p>Perícias que ainda exigem conclusão.</p><a href="/pericias">Abrir módulo</a></article>','<article class="private"><div class="ico">🗃️</div><h3>Banco de Dados</h3><p>Fichas, evidências, pesquisas e inteligência investigativa.</p><a href="/fichas">Abrir módulo</a></article>','<article class="private"><div class="ico">🧬</div><h3>Árvore de Inteligência</h3><p>Vínculos entre pessoas, veículos e organizações.</p><a href="/arvore">Abrir módulo</a></article>'])
    body=f'<section class="hero"><div><div class="label">DASHBOARD OPERACIONAL</div><h2>Inteligência centralizada com identidade <span>DICOR</span>.</h2><p>Dashboard inicial com os módulos operacionais e investigativos em abas separadas. Os registros são consultados diretamente do Discord.</p></div><div class="mark"><b>PF</b></div></section><section class="summary"><a href="/boletins"><span>Boletins ativos</span><b>{len(bo)}</b></a><a href="/procurados"><span>Procurados ativos</span><b>{len(pr)}</b></a><a href="/pericias"><span>Perícias pendentes</span><b>{len(pe)}</b></a></section><div class="section">MÓDULOS DA CENTRAL</div><section class="grid">{cards}</section>'
    return page("Central de Inteligência","central",body,len(bo),len(pr),len(pe),op)


class CentralV608:
    def __init__(self,client): self.client=client; self.runner=None; self.site=None; self.started=False
    async def start(self):
        if self.started:return
        self.started=True; app=web.Application()
        async def protected(req, handler):
            if req.path in ('/health','/cadastro-operador'): return await handler(req)
            op=operator(req)
            if not op: raise web.HTTPFound('/cadastro-operador?next='+web.utils.quote(req.path))
            return await handler(req)
        async def health(req): return web.Response(text='OK',content_type='text/plain')
        async def login(req): return web.Response(text=login_page(req.query.get('next','/')),content_type='text/html')
        async def login_post(req):
            form=await req.post(); qra=clean(form.get('qra'))[:45]; pas=re.sub(r'\D+','',str(form.get('passaporte') or ''))[:12]; nxt=str(form.get('next') or '/')
            if len(qra)<2 or not pas: return web.Response(text=login_page(nxt,'Informe QRA e passaporte válidos.'),content_type='text/html',status=400)
            resp=web.HTTPFound(nxt if nxt.startswith('/') else '/')
            resp.set_cookie(COOKIE,cookie_value(qra,pas),max_age=COOKIE_DAYS*86400,httponly=True,samesite='Lax',secure=False,path='/')
            return resp
        async def home(req): return web.Response(text=await dashboard(self.client,operator(req)),content_type='text/html')
        async def listing(req,kind):
            bo=await live_threads(self.client,BO_TARGET_ID,'bo'); pe=await live_threads(self.client,PERICIA_CHANNEL_ID,'per'); pr=await live_procurados(self.client)
            rows={'bo':bo,'pe':pe,'pr':pr}[kind]; title={'bo':'Boletins','pe':'Perícias','pr':'Procurados'}[kind]; label={'bo':'ÚLTIMOS BOLETINS ATIVOS','pe':'PERÍCIAS PENDENTES','pr':'CADASTRO OPERACIONAL'}[kind]
            body=f'<section class="hero"><div><div class="label">{label}</div><h2>{title}</h2><p>Fonte: informações atuais do Discord. Somente leitura.</p></div></section><section class="cards">{("".join(card(x,kind) for x in rows) or "<div class=empty>Nenhum registro ativo encontrado.</div>")}</section>'
            return web.Response(text=page(title,kind if kind!='pr' else 'pr',body,len(bo),len(pr),len(pe),operator(req)),content_type='text/html')
        async def fichas(req):
            return web.Response(text=page('Banco de Dados','', '<section class="hero"><div class="label">BANCO DE DADOS</div><h2>Fichas e inteligência</h2><p>Módulo reservado. A estrutura do painel clássico foi preservada.</p></section><div class="empty">Módulo disponível para integração com as fichas já existentes do Discord.</div>',len(await live_threads(self.client,BO_TARGET_ID,'bo')),len(await live_procurados(self.client)),len(await live_threads(self.client,PERICIA_CHANNEL_ID,'per')),operator(req)),content_type='text/html')
        async def arvore(req):
            return web.Response(text=page('Árvore de Inteligência','', '<section class="hero"><div class="label">INTELIGÊNCIA</div><h2>Árvore de vínculos</h2><p>Módulo reservado para cruzamento de pessoas, veículos e organizações.</p></section><div class="empty">Módulo disponível para integração com os registros investigativos existentes.</div>',len(await live_threads(self.client,BO_TARGET_ID,'bo')),len(await live_procurados(self.client)),len(await live_threads(self.client,PERICIA_CHANNEL_ID,'per')),operator(req)),content_type='text/html')
        app.router.add_get('/health',health); app.router.add_get('/cadastro-operador',login); app.router.add_post('/cadastro-operador',login_post); app.router.add_get('/',home); app.router.add_get('/boletins',lambda r:listing(r,'bo')); app.router.add_get('/procurados',lambda r:listing(r,'pr')); app.router.add_get('/pericias',lambda r:listing(r,'pe')); app.router.add_get('/fichas',fichas); app.router.add_get('/arvore',arvore)
        # Middleware is intentionally installed after route registration; it only protects operational pages.
        app.middlewares.append(protected)
        self.runner=web.AppRunner(app); await self.runner.setup(); self.site=web.TCPSite(self.runner,'0.0.0.0',PORT); await self.site.start(); print(f'🌐 Central DICOR V608 online | porta={PORT} | fonte=Discord | dashboard clássico',flush=True)
    async def on_ready(self): await self.start()


def install(bot_module):
    client=getattr(bot_module,'bot',None)
    if client is None: raise RuntimeError('cliente Discord inválido')
    old=getattr(client,'_dicor_central_v608',None)
    if old:return old
    c=CentralV608(client); client._dicor_central_v608=c; client.add_listener(c.on_ready,'on_ready'); return c
