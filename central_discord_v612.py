# -*- coding: utf-8 -*-
"""DICOR Central V612 - painel somente leitura, rápido e tolerante a falhas."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import discord
from aiohttp import web

BO_ID = 1525762770253910136
PERICIA_ID = 1490200524367200297
PROCURADOS_ID = 1490200533980545097
PORT = int(os.getenv("PORT", "8080"))
COOKIE = "dicor_operador_v612"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v612"))
LOGO = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?ex=6aa4a8de&is=6aa3575e&hm=95ab0f8951a7c48c3c2aff35c5cfdec8cef0af8add90348445dc7093b7d841d3&=&format=webp&quality=lossless"
CACHE: dict[str, Any] = {"bo": [], "pe": [], "pr": [], "updated": 0.0, "busy": False}


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def clean(v: Any) -> str:
    return " ".join(str(v or "").split())


def text_of(m: Any) -> str:
    out = [getattr(m, "content", "") or ""]
    for e in getattr(m, "embeds", []) or []:
        out += [getattr(e, "title", "") or "", getattr(e, "description", "") or ""]
        for f in getattr(e, "fields", []) or []:
            out.append(f"{getattr(f,'name','')}: {getattr(f,'value','')}")
    return clean(" ".join(x for x in out if x))


def closed(name: str, text: str = "") -> bool:
    s = clean(name + " " + text).casefold()
    return any(x in s for x in ("concluído", "concluido", "finalizado", "encerrado", "fechado", "cancelado"))


def num(s: str) -> str:
    for p in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(p, s or "", re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return "S/N"


def cookie(qra: str, passport: str) -> str:
    payload = f"{clean(qra)[:45]}|{clean(passport)[:12]}|{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig


def auth(req: web.Request) -> tuple[str, str] | None:
    token = req.cookies.get(COOKIE, "")
    if "." not in token:
        return None
    try:
        raw, sig = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        good = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        qra, passport, issued = payload.split("|", 2)
        if time.time() - int(issued) > 30 * 86400:
            return None
        return qra, passport
    except Exception:
        return None


def login(error: str = "", next_url: str = "/") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • Central</title><style>{LOGIN_CSS}</style><body><form class="login" method="post" action="/cadastro-operador"><img src="{LOGO}" class="logo"><div class="ey">POLÍCIA FEDERAL • DICOR</div><h1>CENTRAL DE INTELIGÊNCIA</h1><p>Identificação operacional para acesso ao painel interno.</p>{err}<input type="hidden" name="next" value="{esc(next_url)}"><label>QRA OPERACIONAL</label><input name="qra" maxlength="45" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="12" inputmode="numeric" placeholder="Digite seu passaporte" required><div class="note">A Central é somente leitura e não altera BOs ou perícias.</div><button>ACESSAR CENTRAL</button></form></body></html>'''


LOGIN_CSS = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0,#80602033,transparent 45%),#050706;color:#f5f1e6;font-family:Inter,Segoe UI,Arial}.login{width:min(480px,calc(100% - 34px));padding:36px;border:1px solid #655021;border-radius:25px;background:linear-gradient(145deg,#121610,#080a09);box-shadow:0 35px 100px #000d;text-align:center}.logo{width:118px;height:118px;object-fit:contain;filter:drop-shadow(0 0 22px #d7a93d33)}.ey{color:#d7a93d;font-size:10px;letter-spacing:3px;font-weight:900}.login h1{font-size:28px;margin:9px 0}.login p{color:#8b948e;font-size:12px}.login label{display:block;text-align:left;color:#cfc7ae;font-size:10px;letter-spacing:1.4px;margin:18px 0 7px}.login input{width:100%;padding:14px;border-radius:12px;border:1px solid #30372f;background:#050706;color:#fff;font-size:15px;outline:none}.login button{width:100%;margin-top:22px;padding:15px;border:0;border-radius:12px;background:linear-gradient(135deg,#f3d57b,#d7a93d);font-weight:900;cursor:pointer}.note{margin-top:15px;padding:11px;border-left:2px solid #d7a93d;background:#d7a93d0c;color:#727b75;font-size:10px}.err{padding:10px;border-radius:10px;background:#401919;color:#ffcaca;font-size:12px;margin:12px 0}
"""


async def channel(client: Any, cid: int):
    try:
        c = client.get_channel(cid)
        return c if c is not None else await client.fetch_channel(cid)
    except Exception:
        return None


async def thread_row(t: Any, kind: str):
    try:
        msgs = [m async for m in t.history(limit=6, oldest_first=True)]
        txt = " ".join(text_of(m) for m in msgs)
        if closed(getattr(t, "name", ""), txt):
            return None
        agent = "Aguardando responsável" if kind == "bo" else "Aguardando agente"
        for m in msgs:
            mt = text_of(m)
            hit = re.search(r"(?:Responsável|Responsavel|Agente)\s*:\s*(?:<@!?\d+>|([^|\n]+))", mt, re.I)
            if hit and hit.group(1):
                agent = clean(hit.group(1))
                break
        created = getattr(t, "created_at", None) or datetime.now(timezone.utc)
        gid = getattr(getattr(t, "guild", None), "id", 0)
        return {"number":num(getattr(t,"name","")),"name":clean(getattr(t,"name","")),"agent":agent,"created":created,"url":f"https://discord.com/channels/{gid}/{t.id}"}
    except Exception:
        return None


async def collect_threads(client: Any, cid: int, kind: str):
    c = await channel(client, cid)
    if c is None:
        return []
    threads = [t for t in (getattr(c, "threads", []) or []) if not getattr(t,"archived",False) and not getattr(t,"locked",False)]
    if not threads:
        return []
    rows = await asyncio.gather(*(thread_row(t, kind) for t in threads), return_exceptions=True)
    return sorted([r for r in rows if isinstance(r,dict)], key=lambda r:r["created"], reverse=True)


async def collect_procurados(client: Any):
    c = await channel(client, PROCURADOS_ID)
    if c is None:
        return []
    out=[]
    try:
        async for m in c.history(limit=60):
            t=text_of(m)
            if t and not closed("",t):
                out.append({"number":num(t),"name":t[:150],"agent":str(getattr(m,"author","")),"created":getattr(m,"created_at",datetime.now(timezone.utc)),"url":getattr(m,"jump_url", "#")})
    except Exception:
        pass
    return out


async def refresh(client: Any):
    if CACHE["busy"]:
        return
    CACHE["busy"] = True
    try:
        bo, pe, pr = await asyncio.gather(collect_threads(client,BO_ID,"bo"),collect_threads(client,PERICIA_ID,"pe"),collect_procurados(client),return_exceptions=True)
        CACHE["bo"] = bo if isinstance(bo,list) else []
        CACHE["pe"] = pe if isinstance(pe,list) else []
        CACHE["pr"] = pr if isinstance(pr,list) else []
        CACHE["updated"] = time.time()
    finally:
        CACHE["busy"] = False


async def refresher(client: Any):
    await asyncio.sleep(2)
    while True:
        try:
            if time.time()-CACHE["updated"] >= 15:
                await refresh(client)
        except Exception:
            pass
        await asyncio.sleep(15)


CSS = """
:root{--g:#d7a93d;--g2:#f5d77d;--bg:#050706;--line:#26302c;--txt:#edf0e9;--muted:#7f8982;--ok:#42d58a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -10%,#6a4e171c,transparent 34%),#050706;color:var(--txt);font-family:Inter,Segoe UI,Arial}.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}.side{position:sticky;top:0;height:100vh;border-right:1px solid #1d2522;background:#070a09;padding:18px 13px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:9px;padding:2px 7px 18px;border-bottom:1px solid #1c2421}.brand img{width:55px;height:55px;object-fit:contain}.brand b{display:block;letter-spacing:2px}.brand span{display:block;color:var(--g);font-size:9px;letter-spacing:2px}.nav{padding-top:15px;display:grid;gap:5px}.nav a{padding:12px;border:1px solid transparent;border-radius:10px;color:#9ba49e;font-size:12px}.nav a:hover,.nav a.active{color:#f5df9c;border-color:#58481f;background:#d7a93d18}.bottom{margin-top:auto;padding:11px;border:1px solid #202823;border-radius:11px;background:#0a0e0c;font-size:10px;color:#8d978f}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);margin-right:6px}.op{margin-top:7px;color:var(--g);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.main{padding:20px 26px 45px;min-width:0}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1d2522;padding-bottom:15px}.title{display:flex;gap:10px;align-items:center}.title img{width:45px;height:45px;object-fit:contain}.title b{letter-spacing:1.5px;font-size:15px}.title span{display:block;color:#77817a;font-size:9px;letter-spacing:1.3px;margin-top:4px}.clock{color:#7e8881;font-size:9px}.hero{margin-top:18px;position:relative;overflow:hidden;border:1px solid #5a4820;border-radius:15px;padding:25px 27px;background:linear-gradient(110deg,#11150f,#0a0e0c 60%,#0b0d0c);box-shadow:inset 0 -1px #d7a93d55}.hero img{position:absolute;right:28px;top:0;width:170px;height:150px;object-fit:contain;opacity:.65}.eyebrow{color:var(--g);font-size:10px;letter-spacing:2.5px;font-weight:800}.hero h1{font-size:31px;margin:8px 0}.hero p{margin:0;color:#89928c;font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin:15px 0}.stat{border:1px solid var(--line);border-radius:11px;background:#0b100e;padding:14px}.stat span{display:block;color:#79847d;font-size:9px;letter-spacing:1.2px}.stat b{display:block;font-size:28px;margin-top:7px;color:var(--g2)}.layout{display:grid;grid-template-columns:1.7fr .7fr;gap:14px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{border:1px solid var(--line);border-radius:13px;background:#0a0e0c;overflow:hidden}.ph{display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #1d2522}.ph b{font-size:10px;letter-spacing:1.2px}.ph a{color:var(--g2);font-size:9px}.item{display:grid;grid-template-columns:5px 1fr auto;gap:10px;align-items:center;padding:11px 13px;border-bottom:1px solid #17201d}.bar{width:3px;height:30px;background:var(--g);border-radius:3px}.item strong{font-size:11px}.item small{display:block;color:#78827b;font-size:9px;margin-top:4px}.item a{color:var(--g2);font-size:9px}.empty{padding:28px;text-align:center;color:#68716c;font-size:11px}.module{display:block;padding:18px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,#0c1110,#080c0b);margin-bottom:12px}.module b{font-size:12px}.module strong{display:block;font-size:34px;color:var(--g2);margin:9px 0}.module span{color:#758078;font-size:10px}.foot{text-align:center;color:#56605a;font-size:9px;margin-top:24px}@media(max-width:900px){.shell{grid-template-columns:1fr}.side{position:relative;height:auto}.nav{grid-template-columns:repeat(4,1fr)}.bottom{display:none}.layout,.columns{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.main{padding:14px}.nav{grid-template-columns:1fr 1fr}.hero h1{font-size:25px}.hero img{opacity:.2}}
"""


def item(row: dict[str,Any], label: str) -> str:
    dt=row.get("created")
    try: date=dt.astimezone().strftime("%d/%m %H:%M")
    except Exception: date="--"
    return f'<div class="item"><div class="bar"></div><div><strong>{esc(row.get("name",""))}</strong><small>Nº {esc(row.get("number","S/N"))} • {esc(row.get("agent",""))} • {date}</small></div><a href="{esc(row.get("url","#"))}" target="_blank">ABRIR</a></div>'


def panel(title: str, rows: list[dict[str,Any]], label: str, url: str) -> str:
    body="".join(item(r,label) for r in rows[:8]) or '<div class="empty">Nenhum registro ativo encontrado.</div>'
    return f'<section class="panel"><div class="ph"><b>{title}</b><a href="{url}">VER TODOS →</a></div>{body}</section>'


def dashboard(op: tuple[str,str], active: str="central") -> str:
    bo=CACHE["bo"]; pe=CACHE["pe"]; pr=CACHE["pr"]
    updated=datetime.fromtimestamp(CACHE["updated"],timezone.utc).astimezone().strftime("%H:%M:%S") if CACHE["updated"] else "aguardando"
    links=[("⌂","Central","/"),("▣","Boletins","/boletins"),("◉","Procurados","/procurados"),("⌁","Perícias","/pericias"),("▤","Banco de Dados","/fichas"),("⌘","Árvore","/arvore")]
    nav="".join(f'<a class="{"active" if active==path else ""}" href="{path}">{ico} &nbsp;{name}</a>' for ico,name,path in links)
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • Central</title><style>{CSS}</style><body><div class="shell"><aside class="side"><div class="brand"><img src="{LOGO}"><div><b>DICOR</b><span>INTELIGÊNCIA</span></div></div><nav class="nav">{nav}</nav><div class="bottom"><span class="dot"></span>SISTEMA ONLINE<div class="op">QRA {esc(op[0])} • PASSAPORTE {esc(op[1])}</div></div></aside><main class="main"><div class="top"><div class="title"><img src="{LOGO}"><div><b>CENTRAL DE INTELIGÊNCIA</b><span>POLÍCIA FEDERAL • DICOR • CONSULTA INTERNA</span></div></div><div class="clock">DADOS ATUALIZADOS<br>{updated}</div></div><section class="hero"><img src="{LOGO}"><div class="eyebrow">SISTEMA INTEGRADO</div><h1>Centro de comando operacional</h1><p>Monitoramento dos registros ativos diretamente do Discord.</p></section><div class="stats"><a class="stat" href="/boletins"><span>BOLETINS ATIVOS</span><b>{len(bo)}</b></a><a class="stat" href="/procurados"><span>PROCURADOS</span><b>{len(pr)}</b></a><a class="stat" href="/pericias"><span>PERÍCIAS ATIVAS</span><b>{len(pe)}</b></a><div class="stat"><span>STATUS</span><b style="color:#42d58a">ONLINE</b></div></div><div class="layout"><div class="columns">{panel("BOLETINS EM ABERTO",bo,"BOLETIM","/boletins")}{panel("PERÍCIAS PENDENTES",pe,"PERÍCIA","/pericias")}</div><div><a class="module" href="/procurados"><b>PROCURADOS</b><strong>{len(pr)}</strong><span>Registros acompanhados</span></a><a class="module" href="/fichas"><b>BANCO DE DADOS</b><strong>→</strong><span>Consulta operacional</span></a><a class="module" href="/arvore"><b>ÁRVORE</b><strong>→</strong><span>Relacionamentos e estrutura</span></a></div></div><div class="foot">DICOR • CENTRAL DE INTELIGÊNCIA • SOMENTE LEITURA</div></main></div></body></html>'''


def listing(op: tuple[str,str], kind: str) -> str:
    rows=CACHE["bo"] if kind=="bo" else CACHE["pe"] if kind=="pe" else CACHE["pr"]
    title="BOLETINS" if kind=="bo" else "PERÍCIAS" if kind=="pe" else "PROCURADOS"
    body="".join(item(r,title) for r in rows) or '<div class="empty">Nenhum registro ativo encontrado.</div>'
    return dashboard(op,kind).replace('<div class="layout"><div class="columns">',f'<div class="layout"><div class="columns"><section class="panel" style="grid-column:1/-1"><div class="ph"><b>{title} • TODOS OS REGISTROS</b></div>{body}</section></div><div>')


async def safe_data(client: Any):
    if not CACHE["updated"]:
        await refresh(client)


def install(bot_module: Any):
    client=getattr(bot_module,"bot",None)
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    app=web.Application()

    async def health(request):
        return web.json_response({"ok":True,"central":"V612","updated":CACHE["updated"]})

    async def get_login(request):
        if auth(request):
            return web.HTTPFound("/")
        return web.Response(text=login(next_url=request.query.get("next","/")),content_type="text/html")

    async def post_login(request):
        try:
            data=await request.post()
            qra=clean(data.get("qra",""))
            passport=clean(data.get("passaporte", ""))
            nxt=clean(data.get("next","/")) or "/"
            if not qra or not passport:
                return web.Response(text=login("Informe QRA e passaporte.",nxt),content_type="text/html")
            resp=web.HTTPFound(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
            resp.set_cookie(COOKIE,cookie(qra,passport),max_age=30*86400,httponly=True,samesite="Lax")
            return resp
        except Exception:
            return web.Response(text=login("Não foi possível iniciar a sessão. Tente novamente."),content_type="text/html")

    async def protected(request, kind="central"):
        op=auth(request)
        if not op:
            raise web.HTTPFound("/cadastro-operador?next="+request.path)
        try:
            await safe_data(client)
            return web.Response(text=dashboard(op,kind) if kind=="central" else listing(op,kind),content_type="text/html")
        except Exception:
            return web.Response(text=dashboard(op,kind),content_type="text/html")

    async def health_catch(request):
        return await health(request)

    app.router.add_get("/health",health_catch)
    app.router.add_get("/cadastro-operador",get_login)
    app.router.add_post("/cadastro-operador",post_login)
    app.router.add_get("/",lambda r: protected(r,"central"))
    app.router.add_get("/boletins",lambda r: protected(r,"bo"))
    app.router.add_get("/procurados",lambda r: protected(r,"pr"))
    app.router.add_get("/pericias",lambda r: protected(r,"pe"))
    app.router.add_get("/fichas",lambda r: protected(r,"central"))
    app.router.add_get("/arvore",lambda r: protected(r,"central"))

    class Central:
        def __init__(self):
            self.runner=None
            self.task=None
            self.started=False
        async def start(self):
            if self.started:
                return
            self.started=True
            self.runner=web.AppRunner(app)
            await self.runner.setup()
            site=web.TCPSite(self.runner,"0.0.0.0",PORT)
            await site.start()
            self.task=asyncio.create_task(refresher(client))
            try:
                await refresh(client)
            except Exception:
                pass
            print(f"🌐 DICOR Central V612 em 0.0.0.0:{PORT}",flush=True)
    return Central()
