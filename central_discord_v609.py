# -*- coding: utf-8 -*-
"""DICOR Central V609.

Painel clássico da Central, com identificação QRA/passaporte e leitura direta
dos registros ativos do Discord. Somente leitura: não altera BOs ou perícias.
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
COOKIE = "dicor_operador_v609"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v609"))
COOKIE_DAYS = 30


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def msg_text(message: discord.Message) -> str:
    parts = [message.content or ""]
    for embed in message.embeds or []:
        parts.extend([embed.title or "", embed.description or ""])
        for field in embed.fields or []:
            parts.append(f"{field.name}: {field.value}")
    return clean(" ".join(x for x in parts if x))


def is_closed(name: str, text: str) -> bool:
    value = clean(f"{name} {text}").casefold()
    return any(x in value for x in ("concluído", "concluido", "finalizado", "encerrado", "fechado", "cancelado"))


def number_from(text: str) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        match = re.search(pattern, text or "", re.I)
        if match:
            return f"{int(match.group(1)):04d}"
    return "S/N"


def make_cookie(qra: str, passport: str) -> str:
    payload = f"{qra}|{passport}|{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def get_operator(request: web.Request) -> tuple[str, str] | None:
    token = request.cookies.get(COOKIE, "")
    if "." not in token:
        return None
    try:
        raw, supplied = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            return None
        qra, passport, issued = payload.split("|", 2)
        if time.time() - int(issued) > COOKIE_DAYS * 86400:
            return None
        return qra, passport
    except Exception:
        return None


LOGIN_CSS = """
body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% -20%,#4b391266,transparent 45%),#070806;color:#f7f1db;font-family:Inter,Arial}.box{width:min(470px,calc(100% - 40px));background:linear-gradient(145deg,#14160f,#0b0c09);border:1px solid #493b1d;border-radius:24px;padding:34px;box-shadow:0 28px 90px #000b}.top{display:flex;gap:16px;align-items:center}.mark{width:72px;height:80px;border:1px solid #d7a93d;border-radius:50%;display:grid;place-items:center;color:#f2d47d;font-weight:900}.small{color:#d7a93d;letter-spacing:1.8px;font-size:11px}h1{font:31px Georgia;margin:5px 0}p{color:#a39c87;line-height:1.55}label{display:block;color:#d5c89d;font-size:12px;margin-top:16px}input{width:100%;margin-top:7px;padding:14px;background:#080906;color:#fff5d0;border:1px solid #40361d;border-radius:11px;font-size:16px;outline:0}button{width:100%;margin-top:22px;border:0;border-radius:11px;padding:14px;background:linear-gradient(135deg,#f2d47d,#d7a93d);font-weight:900;cursor:pointer}.aviso{border-left:3px solid #d7a93d;background:#18160d;padding:12px;margin-top:18px;color:#c9c0a5;font-size:13px}.erro{background:#381717;border:1px solid #7c3939;color:#ffd0d0;padding:11px;border-radius:10px;margin:13px 0}
"""


def login_page(next_url: str = "/", error: str = "") -> str:
    err = f'<div class="erro">{esc(error)}</div>' if error else ""
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Identificação Operacional • DICOR</title><style>{LOGIN_CSS}</style></head><body><form class="box" method="post" action="/cadastro-operador"><div class="top"><div class="mark">PF<br><small>DICOR</small></div><div><div class="small">IDENTIFICAÇÃO OPERACIONAL</div><h1>Registro de agente</h1></div></div><p>Identifique seu personagem para entrar na Central.</p>{err}<input type="hidden" name="next" value="{esc(next_url)}"><label>QRA</label><input name="qra" maxlength="45" placeholder="QRA do agente" required><label>Passaporte</label><input name="passaporte" maxlength="12" inputmode="numeric" placeholder="Passaporte" required><div class="aviso">A identificação é usada apenas para a sessão da Central.</div><button>ENTRAR EM SERVIÇO</button></form></body></html>'''


async def get_channel(client: discord.Client, channel_id: int):
    channel = client.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        return await client.fetch_channel(channel_id)
    except Exception:
        return None


async def get_threads(parent: Any) -> list[discord.Thread]:
    if not isinstance(parent, discord.TextChannel):
        return []
    result = list(getattr(parent, "threads", []) or [])
    seen = {thread.id for thread in result}
    try:
        async for thread in parent.archived_threads(limit=100):
            if thread.id not in seen:
                result.append(thread)
                seen.add(thread.id)
    except Exception:
        pass
    return result


async def live_threads(client: discord.Client, channel_id: int, kind: str) -> list[dict[str, Any]]:
    parent = await get_channel(client, channel_id)
    if parent is None:
        return []
    rows: list[dict[str, Any]] = []
    for thread in await get_threads(parent):
        if thread.archived or thread.locked:
            continue
        messages: list[discord.Message] = []
        try:
            async for message in thread.history(limit=12, oldest_first=True):
                messages.append(message)
        except Exception:
            continue
        text = " ".join(msg_text(message) for message in messages)
        if is_closed(thread.name, text):
            continue
        agent = "Aguardando responsável" if kind == "bo" else "Aguardando agente"
        for message in messages:
            match = re.search(r"(?:Responsável|Responsavel|Agente)\s*:\s*(?:<@!?(\d+)>|([^|\n]+))", msg_text(message), re.I)
            if match:
                agent = match.group(1) or clean(match.group(2))
                break
        guild_id = getattr(getattr(thread, "guild", None), "id", 0)
        rows.append({"number": number_from(thread.name), "name": thread.name, "agent": agent, "created": thread.created_at, "url": f"https://discord.com/channels/{guild_id}/{thread.id}"})
    rows.sort(key=lambda row: row["created"], reverse=True)
    return rows


async def live_procurados(client: discord.Client) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ids = [PROCURADOS_CHANNEL_ID]
    for guild in getattr(client, "guilds", []):
        for channel in getattr(guild, "text_channels", []):
            name = clean(getattr(channel, "name", "")).casefold()
            if any(key in name for key in ("procurad", "foragid", "mandado")) and channel.id not in ids:
                ids.append(channel.id)
    for channel_id in ids:
        channel = await get_channel(client, channel_id)
        if channel is None:
            continue
        try:
            async for message in channel.history(limit=100):
                text = msg_text(message)
                if text and not is_closed("", text):
                    rows.append({"number": number_from(text), "name": text[:140], "agent": str(message.author), "created": message.created_at, "url": message.jump_url})
        except Exception:
            continue
    rows.sort(key=lambda row: row["created"], reverse=True)
    return rows[:50]


CSS = """
:root{--g:#d7a93d;--g2:#f2d47d;--bg:#070806;--l:#3b321a;--t:#f7f1db;--m:#96917e}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -20%,#3a2d0c55,transparent 42%),var(--bg);color:var(--t);font-family:Inter,Arial;min-height:100vh}header{min-height:108px;border-bottom:1px solid var(--l);display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:15px 4vw;background:#090a07f4}.brand{grid-column:2;display:flex;align-items:center;gap:15px}.brand .img{width:74px;height:80px;border:1px solid var(--g);border-radius:50%;display:grid;place-items:center;color:var(--g2);font-weight:900}.brand h1{margin:0;font-size:20px;letter-spacing:2px}.brand small{color:var(--g);letter-spacing:1.5px}.nav{justify-self:end;display:flex;gap:16px;flex-wrap:wrap}.nav a{color:#e8dcab;text-decoration:none;font-size:13px}.nav a:hover,.nav .active{color:var(--g2)}main{max-width:1250px;margin:auto;padding:58px 24px 75px}.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:34px;align-items:center;margin-bottom:44px}.label{font-size:11px;letter-spacing:2px;color:var(--g)}.hero h2{font:52px/1.04 Georgia;margin:10px 0 18px}.hero h2 span{color:var(--g2)}.hero p{color:#bbb49c;font-size:17px;line-height:1.65}.mark{height:260px;border:1px solid var(--l);border-radius:28px;background:linear-gradient(145deg,#17180f,#0b0c09);display:grid;place-items:center}.mark b{font-size:55px;color:var(--g2)}.operator{margin-bottom:22px;color:#d2bd73;font-size:11px;letter-spacing:1.1px}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:40px}.summary a{display:flex;justify-content:space-between;align-items:center;text-decoration:none;color:var(--t);border:1px solid var(--l);background:#0d0f0b;border-radius:14px;padding:16px 18px}.summary b{font-size:25px;color:var(--g2)}.section{font-size:11px;letter-spacing:2px;color:var(--g);margin-bottom:15px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:17px}.grid article{min-height:225px;padding:25px;border:1px solid #2e2919;border-radius:18px;background:linear-gradient(155deg,#15170f,#0c0d0a);position:relative}.grid article:hover{border-color:#8b712d;transform:translateY(-3px)}.ico{font-size:30px}.grid h3{margin:18px 0 7px}.grid strong{display:block;font-size:36px;color:var(--g2)}.grid p{color:var(--m);line-height:1.5;min-height:48px}.grid a{display:inline-flex;text-decoration:none;color:#111;background:linear-gradient(135deg,var(--g2),var(--g));padding:10px 14px;border-radius:9px;font-weight:800}.private:after{content:'ACESSO RESTRITO';position:absolute;right:15px;top:15px;color:#bfa85d;font-size:9px;letter-spacing:1.2px;border:1px solid #5b4b22;border-radius:99px;padding:5px 8px}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card{padding:20px;border:1px solid #2e2919;border-radius:14px;background:linear-gradient(145deg,#14160f,#0d0e0b)}.tag{color:var(--g2);font-size:9px;border:1px solid #5b4b22;border-radius:20px;padding:5px 8px;letter-spacing:1px}.card h3{font-size:20px}.meta{display:flex;justify-content:space-between;border-top:1px solid #282319;padding:9px 0;font-size:11px;gap:12px}.meta span{color:var(--m)}.open{color:var(--g2);text-decoration:none;font-size:11px;font-weight:900}.empty{text-align:center;border:1px dashed #40381f;padding:30px;color:var(--m);border-radius:14px;grid-column:1/-1}footer{text-align:center;color:#625f52;font-size:11px;padding:0 20px 42px}@media(max-width:900px){header{grid-template-columns:1fr}.brand{grid-column:1}.nav{justify-self:start;margin-top:12px}.hero{grid-template-columns:1fr}.mark{display:none}.grid,.cards{grid-template-columns:1fr}}@media(max-width:650px){.summary{grid-template-columns:1fr}.hero h2{font-size:36px}}
"""


def card(row: dict[str, Any], kind: str) -> str:
    label = "BOLETIM" if kind == "bo" else "PERÍCIA" if kind == "pe" else "PROCURADO"
    dt = row["created"]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    date = dt.astimezone().strftime("%d/%m/%Y %H:%M")
    return f'<article class="card"><span class="tag">{label}</span><h3>Nº {esc(row["number"])}</h3><div class="meta"><span>Registro</span><b>{esc(row["name"][:75])}</b></div><div class="meta"><span>Responsável</span><b>{esc(row["agent"])}</b></div><div class="meta"><span>Data</span><b>{date}</b></div><a class="open" href="{esc(row["url"])}" target="_blank">Abrir no Discord →</a></article>'


def page(title: str, active: str, body: str, bo: int, pr: int, pe: int, op: tuple[str, str] | None = None) -> str:
    operator_line = f'<div class="operator">OPERADOR: {esc(op[0])} • PASSAPORTE {esc(op[1])}</div>' if op else ""
    nav = ''.join([
        f'<a class="{"active" if active == "central" else ""}" href="/">Central</a>',
        f'<a class="{"active" if active == "bo" else ""}" href="/boletins">Boletins</a>',
        f'<a class="{"active" if active == "pr" else ""}" href="/procurados">Procurados</a>',
        f'<a class="{"active" if active == "pe" else ""}" href="/pericias">Perícias</a>',
        '<a href="/fichas">Banco de Dados</a>',
        '<a href="/arvore">Árvore</a>',
    ])
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • {esc(title)}</title><style>{CSS}</style></head><body><header><div></div><div class="brand"><div class="img">PF</div><div><h1>DICOR • CENTRAL DE INTELIGÊNCIA</h1><small>CONSULTA INTERNA • SISTEMA INTEGRADO</small></div></div><nav class="nav">{nav}</nav></header><main>{operator_line}{body}</main><footer>DICOR • POLÍCIA FEDERAL • AMBIENTE FICTÍCIO DE GTA RP</footer></body></html>'


async def safe_data(client: discord.Client):
    try:
        bo, pe, pr = await __import__('asyncio').gather(
            live_threads(client, BO_TARGET_ID, "bo"),
            live_threads(client, PERICIA_CHANNEL_ID, "pe"),
            live_procurados(client),
        )
        return bo, pe, pr
    except Exception:
        return [], [], []


async def dashboard(client: discord.Client, op: tuple[str, str] | None) -> str:
    bo, pe, pr = await safe_data(client)
    modules = ''.join([
        f'<article><div class="ico">📋</div><h3>Boletins Ativos</h3><strong>{len(bo)}</strong><p>Ocorrências ainda em aberto ou atendimento.</p><a href="/boletins">Abrir módulo</a></article>',
        f'<article><div class="ico">🎯</div><h3>Procurados Ativos</h3><strong>{len(pr)}</strong><p>Lista oficial dos registros encontrados no Discord.</p><a href="/procurados">Abrir módulo</a></article>',
        f'<article><div class="ico">🧪</div><h3>Perícias Pendentes</h3><strong>{len(pe)}</strong><p>Perícias que ainda exigem conclusão.</p><a href="/pericias">Abrir módulo</a></article>',
        '<article class="private"><div class="ico">🗃️</div><h3>Banco de Dados</h3><p>Fichas, evidências, pesquisas e inteligência investigativa.</p><a href="/fichas">Abrir módulo</a></article>',
        '<article class="private"><div class="ico">🧬</div><h3>Árvore de Inteligência</h3><p>Vínculos entre pessoas, veículos e organizações.</p><a href="/arvore">Abrir módulo</a></article>',
    ])
    body = f'<section class="hero"><div><div class="label">DASHBOARD OPERACIONAL</div><h2>Inteligência centralizada com identidade <span>DICOR</span>.</h2><p>Dashboard clássico com os módulos operacionais e investigativos. Os registros são consultados diretamente do Discord.</p></div><div class="mark"><b>PF</b></div></section><section class="summary"><a href="/boletins"><span>Boletins ativos</span><b>{len(bo)}</b></a><a href="/procurados"><span>Procurados ativos</span><b>{len(pr)}</b></a><a href="/pericias"><span>Perícias pendentes</span><b>{len(pe)}</b></a></section><div class="section">MÓDULOS DA CENTRAL</div><section class="grid">{modules}</section>'
    return page("Central de Inteligência", "central", body, len(bo), len(pr), len(pe), op)


class CentralV609:
    def __init__(self, client: discord.Client):
        self.client = client
        self.runner = None
        self.site = None
        self.started = False

    async def start(self):
        if self.started:
            return
        app = web.Application()

        @web.middleware
        async def auth_middleware(request: web.Request, handler):
            if request.path in ("/health", "/cadastro-operador"):
                return await handler(request)
            if get_operator(request) is None:
                target = request.path or "/"
                raise web.HTTPFound("/cadastro-operador?next=" + web.Request.query_string.__get__(request, type(request)) if False else "/cadastro-operador?next=" + target)
            try:
                return await handler(request)
            except Exception:
                return web.Response(text="Central temporariamente indisponível para esta consulta.", status=503, content_type="text/plain")

        async def health(_request):
            return web.Response(text="OK", content_type="text/plain")

        async def login(request):
            return web.Response(text=login_page(request.query.get("next", "/")), content_type="text/html")

        async def login_post(request):
            try:
                form = await request.post()
            except Exception:
                form = {}
            qra = clean(form.get("qra"))[:45]
            passport = re.sub(r"\D+", "", str(form.get("passaporte") or ""))[:12]
            target = str(form.get("next") or "/")
            if not target.startswith("/"):
                target = "/"
            if len(qra) < 2 or not passport:
                return web.Response(text=login_page(target, "Informe QRA e passaporte válidos."), status=400, content_type="text/html")
            response = web.HTTPFound(target)
            response.set_cookie(COOKIE, make_cookie(qra, passport), max_age=COOKIE_DAYS * 86400, httponly=True, samesite="Lax", secure=False, path="/")
            return response

        async def home(request):
            return web.Response(text=await dashboard(self.client, get_operator(request)), content_type="text/html")

        async def listing(request, kind: str):
            bo, pe, pr = await safe_data(self.client)
            rows = {"bo": bo, "pe": pe, "pr": pr}[kind]
            title = {"bo": "Boletins", "pe": "Perícias", "pr": "Procurados"}[kind]
            label = {"bo": "ÚLTIMOS BOLETINS ATIVOS", "pe": "PERÍCIAS PENDENTES", "pr": "CADASTRO OPERACIONAL"}[kind]
            body = f'<section class="hero"><div><div class="label">{label}</div><h2>{title}</h2><p>Fonte: informações atuais do Discord. Somente leitura.</p></div></section><section class="cards">{"".join(card(row, kind) for row in rows) or "<div class=empty>Nenhum registro ativo encontrado.</div>"}</section>'
            return web.Response(text=page(title, kind, body, len(bo), len(pr), len(pe), get_operator(request)), content_type="text/html")

        async def reserved(request, title: str, heading: str, text: str):
            bo, pe, pr = await safe_data(self.client)
            body = f'<section class="hero"><div><div class="label">{esc(heading)}</div><h2>{esc(title)}</h2><p>{esc(text)}</p></div></section><div class="empty">Módulo reservado. A estrutura da Central clássica está ativa e pronta para receber os dados do Discord.</div>'
            return web.Response(text=page(title, "", body, len(bo), len(pr), len(pe), get_operator(request)), content_type="text/html")

        app.router.add_get("/health", health)
        app.router.add_get("/cadastro-operador", login)
        app.router.add_post("/cadastro-operador", login_post)
        app.router.add_get("/", home)
        app.router.add_get("/boletins", lambda request: listing(request, "bo"))
        app.router.add_get("/procurados", lambda request: listing(request, "pr"))
        app.router.add_get("/pericias", lambda request: listing(request, "pe"))
        app.router.add_get("/fichas", lambda request: reserved(request, "Banco de Dados", "BANCO DE DADOS", "Fichas, evidências e inteligência investigativa."))
        app.router.add_get("/arvore", lambda request: reserved(request, "Árvore de Inteligência", "INTELIGÊNCIA", "Vínculos entre pessoas, veículos e organizações."))
        app.middlewares.append(auth_middleware)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", PORT)
        await self.site.start()
        self.started = True
        print(f"🌐 Central DICOR V609 online | porta={PORT} | fonte=Discord | dashboard clássico", flush=True)

    async def on_ready(self):
        await self.start()


def install(bot_module):
    client = getattr(bot_module, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord inválido")
    old = getattr(client, "_dicor_central_v609", None)
    if old:
        return old
    central = CentralV609(client)
    client._dicor_central_v609 = central
    client.add_listener(central.on_ready, "on_ready")
    return central
