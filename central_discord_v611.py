# -*- coding: utf-8 -*-
"""DICOR Central V611.
Painel rápido, cacheado e somente leitura. Os dados são coletados do Discord em
segundo plano; abrir uma página nunca dispara uma varredura pesada.
"""
from __future__ import annotations

import asyncio
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
COOKIE = "dicor_operador_v611"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v611"))
LOGO_URL = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?ex=6aa4a8de&is=6aa3575e&hm=95ab0f8951a7c48c3c2aff35c5cfdec8cef0af8add90348445dc7093b7d841d3&=&format=webp&quality=lossless"


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def message_text(message: discord.Message) -> str:
    parts = [message.content or ""]
    for embed in getattr(message, "embeds", []) or []:
        parts.extend([embed.title or "", embed.description or ""])
        for field in getattr(embed, "fields", []) or []:
            parts.append(f"{field.name}: {field.value}")
    return clean(" ".join(x for x in parts if x))


def is_closed(name: str, text: str = "") -> bool:
    value = clean(f"{name} {text}").casefold()
    return any(x in value for x in ("concluído", "concluido", "finalizado", "encerrado", "fechado", "cancelado"))


def number_from(text: str) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        match = re.search(pattern, text or "", re.I)
        if match:
            return f"{int(match.group(1)):04d}"
    return "S/N"


def make_cookie(qra: str, passport: str) -> str:
    payload = f"{clean(qra)[:45]}|{clean(passport)[:12]}|{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def operator(request: web.Request) -> tuple[str, str] | None:
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
        if time.time() - int(issued) > 30 * 86400:
            return None
        return qra, passport
    except Exception:
        return None


LOGIN_CSS = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#050606;color:#f4f0e4;font-family:Inter,Arial;display:grid;place-items:center}body:before{content:"";position:fixed;inset:0;background:radial-gradient(circle at 50% 0,#8a681f30,transparent 43%);pointer-events:none}.login{width:min(480px,calc(100% - 34px));padding:36px;border:1px solid #6b5524;border-radius:25px;background:linear-gradient(145deg,#121510f5,#080a09f8);box-shadow:0 35px 110px #000d;text-align:center}.logo{width:112px;height:112px;object-fit:contain;margin:0 auto 10px;filter:drop-shadow(0 0 24px #d7a93d35)}.k{color:#d7a93d;font-size:10px;letter-spacing:3px;font-weight:900}.login h1{font-size:28px;margin:8px 0}.login p{color:#8e958e;font-size:12px}.field{text-align:left}label{display:block;color:#cfc7ae;font-size:10px;letter-spacing:1.5px;margin:18px 0 7px}input{width:100%;padding:14px;border-radius:12px;border:1px solid #30372f;background:#050706;color:#fff;font-size:15px;outline:none}input:focus{border-color:#d7a93d;box-shadow:0 0 0 2px #d7a93d18}.login button{width:100%;margin-top:23px;padding:15px;border:0;border-radius:12px;background:linear-gradient(135deg,#f3d57b,#d7a93d);color:#111;font-weight:900;cursor:pointer}.note{margin-top:16px;padding:11px;border-left:2px solid #d7a93d;background:#d7a93d0b;color:#747d76;font-size:10px}.err{padding:10px;border-radius:10px;background:#401919;color:#ffcaca;font-size:12px;margin:12px 0}
"""


def login_page(next_url: str = "/", error: str = "") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • Central</title><style>{LOGIN_CSS}</style></head><body><form class="login" method="post" action="/cadastro-operador"><img class="logo" src="{LOGO_URL}" alt="DICOR"><div class="k">POLÍCIA FEDERAL • DICOR</div><h1>CENTRAL DE INTELIGÊNCIA</h1><p>Identificação operacional para acesso ao painel interno.</p>{err}<input type="hidden" name="next" value="{esc(next_url)}"><div class="field"><label>QRA OPERACIONAL</label><input name="qra" maxlength="45" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="12" inputmode="numeric" placeholder="Digite seu passaporte" required></div><div class="note">Sessão vinculada ao operador informado. A Central funciona em modo somente leitura.</div><button>ACESSAR CENTRAL</button></form></body></html>'''


async def get_channel(client: discord.Client, channel_id: int):
    channel = client.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        return await client.fetch_channel(channel_id)
    except Exception:
        return None


async def get_active_threads(parent: Any) -> list[Any]:
    active = list(getattr(parent, "threads", []) or []) if parent is not None else []
    # Não percorre histórico de threads arquivadas. Isso é deliberado para manter a Central rápida.
    return [thread for thread in active if not getattr(thread, "archived", False) and not getattr(thread, "locked", False)]


async def read_thread(thread: Any, kind: str) -> dict[str, Any] | None:
    try:
        messages = [message async for message in thread.history(limit=8, oldest_first=True)]
    except Exception:
        return None
    text = " ".join(message_text(message) for message in messages)
    if is_closed(getattr(thread, "name", ""), text):
        return None
    agent = "Aguardando responsável" if kind == "bo" else "Aguardando agente"
    for message in messages:
        match = re.search(r"(?:Responsável|Responsavel|Agente)\s*:\s*(?:<@!?(\d+)>|([^|\n]+))", message_text(message), re.I)
        if match:
            agent = match.group(1) or clean(match.group(2))
            break
    created = getattr(thread, "created_at", None)
    guild_id = getattr(getattr(thread, "guild", None), "id", 0)
    return {"number": number_from(getattr(thread, "name", "")), "name": clean(getattr(thread, "name", "")), "agent": agent, "created": created, "url": f"https://discord.com/channels/{guild_id}/{thread.id}", "kind": kind}


async def live_threads(client: discord.Client, channel_id: int, kind: str) -> list[dict[str, Any]]:
    parent = await get_channel(client, channel_id)
    if parent is None:
        return []
    threads = await get_active_threads(parent)
    if not threads:
        return []
    rows = await asyncio.gather(*(read_thread(thread, kind) for thread in threads), return_exceptions=True)
    return sorted([row for row in rows if isinstance(row, dict)], key=lambda row: row["created"] or 0, reverse=True)


async def live_procurados(client: discord.Client) -> list[dict[str, Any]]:
    ids = [PROCURADOS_CHANNEL_ID]
    for guild in getattr(client, "guilds", []):
        for channel in getattr(guild, "text_channels", []):
            name = clean(getattr(channel, "name", "")).casefold()
            if any(key in name for key in ("procurad", "foragid", "mandado")) and channel.id not in ids:
                ids.append(channel.id)
    results: list[dict[str, Any]] = []
    for channel_id in ids:
        channel = await get_channel(client, channel_id)
        if channel is None:
            continue
        try:
            async for message in channel.history(limit=60):
                text = message_text(message)
                if text and not is_closed("", text):
                    results.append({"number": number_from(text), "name": text[:150], "agent": str(message.author), "created": message.created_at, "url": message.jump_url, "kind": "proc"})
        except Exception:
            continue
    results.sort(key=lambda row: row["created"] or 0, reverse=True)
    return results[:40]


CSS = """
:root{--g:#d7a93d;--g2:#f5d77d;--bg:#050707;--line:#26302c;--text:#edf0e9;--muted:#7f8982;--green:#42d58a;--red:#ff4d55;--purple:#a879ff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -10%,#6a4e171c,transparent 34%),linear-gradient(180deg,#050706,#070a09 55%,#050606);color:var(--text);font-family:Inter,Segoe UI,Arial;min-height:100vh}a{color:inherit;text-decoration:none}.shell{display:grid;grid-template-columns:242px 1fr;min-height:100vh}.side{position:sticky;top:0;height:100vh;border-right:1px solid #1d2522;background:linear-gradient(180deg,#080b0a,#060807);padding:18px 13px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:9px;padding:3px 7px 18px;border-bottom:1px solid #1c2421}.brand img{width:56px;height:56px;object-fit:contain;filter:drop-shadow(0 0 13px #d7a93d22)}.brand b{display:block;letter-spacing:2px}.brand span{display:block;color:var(--g);font-size:9px;letter-spacing:2px}.nav{padding-top:16px;display:grid;gap:5px}.nav a{display:flex;gap:11px;align-items:center;padding:12px;border:1px solid transparent;border-radius:10px;color:#9ba49e;font-size:12px}.nav a:hover,.nav a.active{color:#f5df9c;border-color:#58481f;background:#d7a93d18}.nav i{font-style:normal;width:19px;text-align:center;font-size:15px}.bottom{margin-top:auto;padding:11px;border:1px solid #202823;border-radius:11px;background:#0a0e0c}.online{color:#8d978f;font-size:10px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:6px;box-shadow:0 0 12px #42d58a77}.op{margin-top:7px;color:var(--g);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.main{min-width:0;padding:20px 26px 40px}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1d2522;padding-bottom:16px;margin-bottom:18px}.title{display:flex;align-items:center;gap:11px}.title img{width:48px;height:48px;object-fit:contain}.title b{font-size:15px;letter-spacing:1.5px}.title span{display:block;color:#77817a;font-size:9px;letter-spacing:1.4px;margin-top:4px}.clock{color:#7e8881;font-size:9px;text-align:right}.hero{position:relative;overflow:hidden;border:1px solid #5a4820;border-radius:15px;padding:25px 27px;background:linear-gradient(110deg,#11150f,#0a0e0c 58%,#0b0d0c);box-shadow:inset 0 -1px #d7a93d55}.heroLogo{position:absolute;right:28px;top:0;width:175px;height:150px;object-fit:contain;opacity:.78;filter:drop-shadow(0 0 25px #d7a93d22)}.eyebrow{color:var(--g);font-size:10px;letter-spacing:2.5px;font-weight:800}.hero h1{font-size:31px;margin:8px 0 5px;letter-spacing:1px}.hero p{margin:0;color:#89928c;font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin:15px 0}.stat{display:block;border:1px solid var(--line);border-radius:11px;background:#0b100e;padding:14px}.stat .lab{color:#79847d;font-size:9px;letter-spacing:1.2px}.stat .r{display:flex;justify-content:space-between;align-items:end;margin-top:7px}.stat strong{font-size:28px}.stat em{font-style:normal;color:var(--green);font-size:8px}.layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(250px,.7fr);gap:14px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,#0c1110,#080c0b);overflow:hidden}.ph{display:flex;justify-content:space-between;align-items:center;padding:13px 14px;border-bottom:1px solid #1d2522}.ph b{font-size:10px;letter-spacing:1.2px}.ph a{color:var(--g2);font-size:8px}.list{padding:3px 9px}.item{display:grid;grid-template-columns:7px 1fr auto;gap:10px;align-items:center;padding:11px 4px;border-bottom:1px solid #17201d}.item:last-child{border:0}.bar{width:3px;height:33px;border-radius:3px;background:var(--g)}.bar.red{background:var(--red)}.bar.purple{background:var(--purple)}.item h3{margin:0;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.item p{margin:4px 0 0;color:#68736c;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.num{color:#d9c47c;font-size:8px}.right{display:grid;gap:14px;align-content:start}.q{display:flex;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #18211e;color:#aeb6b0;font-size:10px}.q:last-child{border:0}.q span{color:var(--g2)}.mini{padding:13px}.mr{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #18211e;color:#7d8880;font-size:9px}.mr:last-child{border:0}.mr b{color:#e4e8e1}.pagehead{display:flex;justify-content:space-between;align-items:end;margin:12px 0 16px}.pagehead h1{margin:0;font-size:23px}.pagehead p{margin:5px 0 0;color:#6f7972;font-size:10px}.tag{border:1px solid #59491f;color:#d9bf69;border-radius:20px;padding:4px 7px;font-size:8px}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:11px}.card{border:1px solid var(--line);border-radius:12px;background:#0b100e;padding:14px}.card h3{margin:10px 0;font-size:14px}.meta{display:flex;justify-content:space-between;gap:10px;border-top:1px solid #18211e;padding:8px 0;font-size:8px}.meta span{color:#68736c}.meta b{max-width:72%;text-align:right;overflow:hidden;text-overflow:ellipsis}.open{display:inline-block;margin-top:7px;color:#111;background:linear-gradient(135deg,var(--g2),var(--g));padding:8px 10px;border-radius:7px;font-size:8px;font-weight:900}.empty{padding:35px;text-align:center;color:#68736c;border:1px dashed #26302c;border-radius:12px;grid-column:1/-1}.footer{text-align:right;color:#4e5852;font-size:8px;padding-top:14px}@media(max-width:1050px){.shell{grid-template-columns:76px 1fr}.brand div,.nav span,.bottom .op{display:none}.brand{justify-content:center}.nav a{justify-content:center}.layout{grid-template-columns:1fr}.right{grid-template-columns:1fr 1fr}}@media(max-width:760px){.shell{display:block}.side{position:static;height:auto;padding:9px}.brand{border:0;padding:0}.brand div,.bottom{display:none}.nav{display:flex;overflow:auto;padding:7px 0}.nav a{white-space:nowrap}.nav span{display:inline}.main{padding:13px}.stats{grid-template-columns:1fr 1fr}.columns,.cards{grid-template-columns:1fr}.right{grid-template-columns:1fr}.heroLogo{display:none}}
"""


class CentralV611:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.cache: dict[str, Any] = {"bo": [], "pe": [], "proc": [], "updated": 0.0}
        self.runner: web.AppRunner | None = None
        self.task: asyncio.Task | None = None
        self.request: web.Request | None = None

    async def refresh(self):
        if not self.bot.is_ready():
            return
        bo, pe, proc = await asyncio.gather(
            live_threads(self.bot, BO_TARGET_ID, "bo"),
            live_threads(self.bot, PERICIA_CHANNEL_ID, "pe"),
            live_procurados(self.bot),
            return_exceptions=True,
        )
        if isinstance(bo, list):
            self.cache["bo"] = bo
        if isinstance(pe, list):
            self.cache["pe"] = pe
        if isinstance(proc, list):
            self.cache["proc"] = proc
        self.cache["updated"] = time.time()

    async def refresh_loop(self):
        while not self.bot.is_ready():
            await asyncio.sleep(1)
        await self.refresh()
        while True:
            await asyncio.sleep(15)
            try:
                await self.refresh()
            except Exception:
                pass

    def counts(self):
        return {"bo": len(self.cache["bo"]), "proc": len(self.cache["proc"]), "pe": len(self.cache["pe"]), "total": len(self.cache["bo"]) + len(self.cache["proc"]) + len(self.cache["pe"])}

    def shell(self, title: str, active: str, body: str) -> str:
        op = operator(self.request) if self.request else None
        qra, passport = op or ("—", "—")
        links = [("⌂", "Dashboard", "/"), ("▤", "Boletins", "/boletins"), ("◎", "Procurados", "/procurados"), ("⚗", "Perícias", "/pericias"), ("▦", "Banco de Dados", "/fichas"), ("⌘", "Árvore de Inteligência", "/arvore")]
        nav = "".join(f'<a class="{"active" if active == url else ""}" href="{url}"><i>{icon}</i><span>{label}</span></a>' for icon, label, url in links)
        return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} • DICOR</title><style>{CSS}</style></head><body><div class="shell"><aside class="side"><div class="brand"><img src="{LOGO_URL}" alt="DICOR"><div><b>DICOR</b><span>INTELIGÊNCIA</span></div></div><nav class="nav">{nav}</nav><div class="bottom"><div class="online"><span class="dot"></span>CENTRAL ONLINE</div><div class="op">QRA {esc(qra)} • PASS {esc(passport)}</div></div></aside><main class="main"><div class="top"><div class="title"><img src="{LOGO_URL}" alt=""><div><b>CENTRAL DE INTELIGÊNCIA</b><span>POLÍCIA FEDERAL • DICOR • CONSULTA OPERACIONAL</span></div></div><div class="clock">SISTEMA LIVE<br><span id="clock">--:--:--</span></div></div>{body}<div class="footer">DICOR • CENTRAL DE INTELIGÊNCIA • SOMENTE LEITURA</div></main></div><script>function tick(){{var e=document.getElementById('clock');if(e)e.textContent=new Date().toLocaleTimeString('pt-BR')}}tick();setInterval(tick,1000)</script></body></html>'''

    def item(self, row: dict[str, Any], kind: str) -> str:
        label = "PROCURADO" if kind == "proc" else "PERÍCIA" if kind == "pe" else "BOLETIM"
        bar = "red" if kind == "proc" else "purple" if kind == "pe" else ""
        return f'<a class="item" href="{esc(row["url"])}" target="_blank"><span class="bar {bar}"></span><div><h3>{esc(row["name"][:78])}</h3><p>{label} • {esc(row["agent"])}</p></div><span class="num">#{esc(row["number"])}</span></a>'

    def cards(self, rows: list[dict[str, Any]], kind: str) -> str:
        if not rows:
            return '<div class="empty">Nenhum registro ativo encontrado no Discord.</div>'
        label = "PROCURADO" if kind == "proc" else "PERÍCIA" if kind == "pe" else "BOLETIM"
        out = []
        for row in rows:
            dt = row["created"]
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            date = dt.astimezone().strftime("%d/%m/%Y %H:%M") if dt else "—"
            out.append(f'<article class="card"><span class="tag">{label}</span><h3>Nº {esc(row["number"])}</h3><div class="meta"><span>Registro</span><b>{esc(row["name"][:90])}</b></div><div class="meta"><span>Responsável</span><b>{esc(row["agent"])}</b></div><div class="meta"><span>Data</span><b>{date}</b></div><a class="open" href="{esc(row["url"])}" target="_blank">ABRIR NO DISCORD →</a></article>')
        return "".join(out)

    def dashboard(self) -> str:
        c = self.counts(); bo = self.cache["bo"][:6]; proc = self.cache["proc"][:5]; pe = self.cache["pe"][:5]
        bi = "".join(self.item(row, "bo") for row in bo) or '<div class="empty">Nenhum BO ativo.</div>'
        pi = "".join(self.item(row, "proc") for row in proc) or '<div class="empty">Nenhum procurado ativo.</div>'
        ei = "".join(self.item(row, "pe") for row in pe) or '<div class="empty">Nenhuma perícia pendente.</div>'
        return f'''<section class="hero"><div><div class="eyebrow">DICOR • OPERAÇÕES ESPECIAIS</div><h1>PAINEL OPERACIONAL</h1><p>Visão consolidada dos registros ativos, sincronizados diretamente do Discord.</p></div><img class="heroLogo" src="{LOGO_URL}" alt="DICOR"></section><section class="stats"><a class="stat" href="/boletins"><div class="lab">BOLETINS ATIVOS</div><div class="r"><strong>{c["bo"]}</strong><em>LIVE</em></div></a><a class="stat" href="/procurados"><div class="lab">PROCURADOS ATIVOS</div><div class="r"><strong>{c["proc"]}</strong><em>LIVE</em></div></a><a class="stat" href="/pericias"><div class="lab">PERÍCIAS PENDENTES</div><div class="r"><strong>{c["pe"]}</strong><em>LIVE</em></div></a><div class="stat"><div class="lab">TOTAL DE REGISTROS</div><div class="r"><strong>{c["total"]}</strong><em>SYNC</em></div></div></section><div class="layout"><div class="columns"><section class="panel"><div class="ph"><b>▤ BOLETINS RECENTES</b><a href="/boletins">VER TODOS →</a></div><div class="list">{bi}</div></section><section class="panel"><div class="ph"><b>◎ PROCURADOS RECENTES</b><a href="/procurados">VER TODOS →</a></div><div class="list">{pi}</div></section><section class="panel"><div class="ph"><b>⚗ PERÍCIAS RECENTES</b><a href="/pericias">VER TODAS →</a></div><div class="list">{ei}</div></section><section class="panel"><div class="ph"><b>⌘ ÁRVORE DE INTELIGÊNCIA</b><a href="/arvore">ABRIR →</a></div><div class="mini"><div class="mr"><span>BOs ativos</span><b>{c["bo"]}</b></div><div class="mr"><span>Procurados</span><b>{c["proc"]}</b></div><div class="mr"><span>Perícias</span><b>{c["pe"]}</b></div></div></section></div><aside class="right"><section class="panel"><div class="ph"><b>⚡ ACESSO RÁPIDO</b></div><a class="q" href="/boletins">Consultar boletins <span>→</span></a><a class="q" href="/procurados">Consultar procurados <span>→</span></a><a class="q" href="/pericias">Consultar perícia <span>→</span></a><a class="q" href="/fichas">Banco de dados <span>→</span></a><a class="q" href="/arvore">Árvore de inteligência <span>→</span></a></section><section class="panel"><div class="ph"><b>◈ INFORMAÇÕES OPERACIONAIS</b></div><div class="mini"><div class="mr"><span>Fonte</span><b>DISCORD LIVE</b></div><div class="mr"><span>Atualização</span><b>15s</b></div><div class="mr"><span>Modo</span><b>SOMENTE LEITURA</b></div><div class="mr"><span>Operador</span><b>{esc(qra)}</b></div></div></section></aside></div>'''

    async def auth(self, request: web.Request, handler):
        if request.path in ("/health", "/cadastro-operador") or request.path.startswith("/api/"):
            return await handler(request)
        if not operator(request):
            raise web.HTTPFound("/cadastro-operador?next=" + (request.path or "/"))
        return await handler(request)

    async def index(self, request: web.Request):
        self.request = request
        return web.Response(text=self.shell("Dashboard", "/", self.dashboard()), content_type="text/html")

    async def listing(self, request: web.Request, kind: str):
        self.request = request
        labels = {"bo": "BOLETINS", "pe": "PERÍCIAS", "proc": "PROCURADOS"}
        active = {"bo": "/boletins", "pe": "/pericias", "proc": "/procurados"}[kind]
        body = f'<div class="pagehead"><div><h1>{labels[kind]}</h1><p>Registros ativos sincronizados diretamente do Discord.</p></div><div class="tag">{len(self.cache[kind])} ATIVOS</div></div><div class="cards">{self.cards(self.cache[kind], kind)}</div>'
        return web.Response(text=self.shell(labels[kind], active, body), content_type="text/html")

    async def placeholder(self, request: web.Request, title: str, active: str):
        self.request = request
        c = self.counts()
        body = f'<div class="pagehead"><div><h1>{title}</h1><p>Módulo integrado ao painel DICOR.</p></div></div><section class="panel"><div class="mini"><div class="mr"><span>Boletins ativos</span><b>{c["bo"]}</b></div><div class="mr"><span>Procurados ativos</span><b>{c["proc"]}</b></div><div class="mr"><span>Perícias pendentes</span><b>{c["pe"]}</b></div></div></section>'
        return web.Response(text=self.shell(title, active, body), content_type="text/html")

    async def api(self, request: web.Request):
        def serial(rows):
            result = []
            for row in rows:
                data = dict(row)
                dt = data.get("created")
                if dt is not None:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    data["created"] = dt.isoformat()
                result.append(data)
            return result
        return web.json_response({"ok": True, "updated": self.cache["updated"], "counts": self.counts(), "bo": serial(self.cache["bo"][:30]), "pe": serial(self.cache["pe"][:30]), "proc": serial(self.cache["proc"][:30])})

    async def cadastro(self, request: web.Request):
        if request.method == "GET":
            return web.Response(text=login_page(request.query.get("next", "/")), content_type="text/html")
        data = await request.post()
        qra = clean(data.get("qra", "")); passport = clean(data.get("passaporte", "")); next_url = str(data.get("next", "/"))
        if not qra or not passport:
            return web.Response(text=login_page(next_url, "Informe QRA e passaporte."), content_type="text/html", status=400)
        if not next_url.startswith("/"):
            next_url = "/"
        response = web.Response(status=303, headers={"Location": next_url})
        response.set_cookie(COOKIE, make_cookie(qra, passport), max_age=30 * 86400, httponly=True, samesite="Lax", secure=False, path="/")
        return response

    async def error_page(self, request: web.Request, exc: Exception):
        return web.Response(text=f"<h1>DICOR Central</h1><p>Erro interno controlado. Atualize a página.</p><small>{esc(type(exc).__name__)}</small>", content_type="text/html", status=500)

    async def start(self):
        if self.runner:
            return
        self.app = web.Application(middlewares=[self.auth])
        self.app.router.add_get("/health", lambda request: web.json_response({"ok": True, "service": "dicor-central-v611", "cache_updated": self.cache["updated"]}))
        self.app.router.add_get("/cadastro-operador", self.cadastro)
        self.app.router.add_post("/cadastro-operador", self.cadastro)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/boletins", lambda request: self.listing(request, "bo"))
        self.app.router.add_get("/procurados", lambda request: self.listing(request, "proc"))
        self.app.router.add_get("/pericias", lambda request: self.listing(request, "pe"))
        self.app.router.add_get("/fichas", lambda request: self.placeholder(request, "BANCO DE DADOS", "/fichas"))
        self.app.router.add_get("/arvore", lambda request: self.placeholder(request, "ÁRVORE DE INTELIGÊNCIA", "/arvore"))
        self.app.router.add_get("/api/data", self.api)
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, "0.0.0.0", PORT).start()
        self.task = asyncio.create_task(self.refresh_loop())
        print(f"🌐 Central V611 online na porta {PORT} | cache Discord ativo", flush=True)


def install(bot_module):
    client = bot_module.bot if hasattr(bot_module, "bot") else bot_module
    central = CentralV611(client)
    bot_module.central_v611 = central
    return central
