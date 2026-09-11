# -*- coding: utf-8 -*-
"""DICOR Central V607 — leitura direta do Discord.

A Central não usa snapshot/JSON para montar os registros. Ela consulta os
canais e tópicos reais do Discord sempre que uma página é aberta.
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from typing import Any

import discord
from aiohttp import web

BO_TARGET_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
PERICIA_CHANNEL_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
PORT = int(os.getenv("PORT", os.getenv("DICOR_CENTRAL_PORT", "8080")))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def clean(text: str) -> str:
    return " ".join(str(text or "").split())


def message_text(message: discord.Message) -> str:
    parts = [message.content or ""]
    for embed in message.embeds or []:
        parts.extend([embed.title or "", embed.description or ""])
        for field in embed.fields or []:
            parts.extend([field.name or "", field.value or ""])
    return clean(" ".join(x for x in parts if x))


def is_closed(name: str, text: str) -> bool:
    value = clean(f"{name} {text}").casefold()
    return any(x in value for x in ("concluído", "concluido", "finalizado", "encerrado", "fechado", "cancelado"))


def number_from(text: str) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        match = re.search(pattern, text, re.I)
        if match:
            return f"{int(match.group(1)):04d}"
    return "S/N"


async def channel(client: discord.Client, channel_id: int):
    value = client.get_channel(channel_id)
    if value:
        return value
    try:
        return await client.fetch_channel(channel_id)
    except Exception:
        return None


async def all_threads(parent: Any) -> list[discord.Thread]:
    if not isinstance(parent, discord.TextChannel):
        return []
    items = list(getattr(parent, "threads", []) or [])
    known = {t.id for t in items}
    try:
        async for thread in parent.archived_threads(limit=None):
            if thread.id not in known:
                items.append(thread)
                known.add(thread.id)
    except Exception:
        pass
    return items


async def first_messages(thread: discord.Thread, limit: int = 8) -> list[discord.Message]:
    result: list[discord.Message] = []
    try:
        async for message in thread.history(limit=limit, oldest_first=True):
            result.append(message)
    except Exception:
        pass
    return result


async def live_boletins(client: discord.Client) -> list[dict[str, Any]]:
    parent = await channel(client, BO_TARGET_ID)
    rows: list[dict[str, Any]] = []
    for thread in await all_threads(parent):
        if thread.archived or thread.locked:
            continue
        messages = await first_messages(thread)
        text = " ".join(message_text(m) for m in messages)
        if is_closed(thread.name, text):
            continue
        number = number_from(thread.name)
        agent = "Aguardando responsável"
        for m in messages:
            match = re.search(r"Responsável:\s*(?:<@!?(\d+)>|([^|\n]+))", message_text(m), re.I)
            if match:
                agent = match.group(1) or clean(match.group(2))
                break
        rows.append({"number": number, "name": thread.name, "agent": agent, "created": thread.created_at, "url": f"https://discord.com/channels/{thread.guild.id}/{thread.id}"})
    rows.sort(key=lambda x: x["created"], reverse=True)
    return rows


async def live_pericias(client: discord.Client) -> list[dict[str, Any]]:
    parent = await channel(client, PERICIA_CHANNEL_ID)
    rows: list[dict[str, Any]] = []
    for thread in await all_threads(parent):
        if thread.archived or thread.locked:
            continue
        messages = await first_messages(thread, 12)
        text = " ".join(message_text(m) for m in messages)
        if is_closed(thread.name, text):
            continue
        agent = "Aguardando agente"
        match = re.search(r"Responsável:\s*(?:<@!?(\d+)>|([^|\n]+))", text, re.I)
        if match:
            agent = match.group(1) or clean(match.group(2))
        rows.append({"number": number_from(thread.name), "name": thread.name, "agent": agent, "created": thread.created_at, "url": f"https://discord.com/channels/{thread.guild.id}/{thread.id}"})
    rows.sort(key=lambda x: x["created"], reverse=True)
    return rows


async def live_procurados(client: discord.Client) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Descobre a fonte no próprio Discord por nome; não cria nem altera nada.
    channels = []
    for guild in getattr(client, "guilds", []):
        for ch in getattr(guild, "text_channels", []):
            name = clean(getattr(ch, "name", "")).casefold()
            if any(key in name for key in ("procurad", "foragid", "mandado")):
                channels.append(ch)
    for ch in channels:
        try:
            async for message in ch.history(limit=100):
                text = message_text(message)
                if not text or is_closed("", text):
                    continue
                rows.append({"number": number_from(text), "name": text[:110], "agent": str(message.author), "created": message.created_at, "url": message.jump_url})
        except Exception:
            continue
    rows.sort(key=lambda x: x["created"], reverse=True)
    return rows[:30]


CSS = '''
:root{--bg:#080a0d;--panel:#11151a;--panel2:#171c22;--line:#2c333b;--gold:#c9a44c;--gold2:#f0d27a;--text:#f3f3f2;--muted:#8d959e;--green:#75b987}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -15%,#242a31 0,#080a0d 48%);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}header{background:rgba(8,10,13,.96);border-bottom:1px solid #292f36;position:sticky;top:0;z-index:10;backdrop-filter:blur(12px)}.head{max-width:1220px;margin:auto;padding:18px 24px 14px;display:flex;gap:15px;align-items:center}.crest{width:58px;height:58px;border:1px solid var(--gold);border-radius:50%;display:grid;place-items:center;color:var(--gold2);font-weight:900;line-height:.85;text-align:center;box-shadow:0 0 28px #c9a44c22}.crest small{font-size:8px;letter-spacing:1px}.brand h1{margin:0;font-size:19px;letter-spacing:1.7px}.brand small{color:var(--muted);font-size:10px;letter-spacing:2px}nav{max-width:1220px;margin:auto;display:flex;gap:2px;padding:0 24px;overflow:auto}nav a{color:#9da5ad;text-decoration:none;padding:13px 16px;border-bottom:2px solid transparent;font-size:11px;font-weight:900;letter-spacing:1px;white-space:nowrap}nav a:hover,nav a.on{color:var(--gold2);border-bottom-color:var(--gold)}nav b{margin-left:7px;color:#606871}main{max-width:1220px;margin:auto;padding:30px 24px 60px}.hero{background:linear-gradient(135deg,#171c22,#0d1014);border:1px solid #30363e;border-radius:15px;padding:31px;box-shadow:0 18px 60px #0008;margin-bottom:18px}.eyebrow{color:var(--gold);font-size:10px;font-weight:900;letter-spacing:2.6px}.hero h2{font-size:34px;margin:8px 0}.hero p{color:var(--muted);max-width:760px;margin:0}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:25px}.stat{display:block;text-decoration:none;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:20px}.stat span{display:block;color:var(--muted);font-size:10px;letter-spacing:1.3px;text-transform:uppercase}.stat b{display:block;color:var(--gold2);font-size:31px;margin-top:5px}.section{display:flex;justify-content:space-between;align-items:center;margin:22px 0 12px}.section h3{font-size:11px;letter-spacing:1.8px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.card{background:linear-gradient(145deg,#151a20,#0f1216);border:1px solid var(--line);border-radius:13px;padding:19px}.top{display:flex;justify-content:space-between;gap:8px}.tag{color:var(--gold2);border:1px solid #67552e;border-radius:20px;padding:5px 8px;font-size:9px;font-weight:900;letter-spacing:1px}.status{color:var(--green);font-size:9px;font-weight:900;letter-spacing:.8px}.card h3{font-size:22px;margin:13px 0}.meta{display:flex;justify-content:space-between;border-top:1px solid #22282e;padding:9px 0;font-size:11px;gap:10px}.meta span{color:var(--muted)}.open{display:block;color:var(--gold2);text-decoration:none;font-size:11px;font-weight:900;margin-top:8px}.empty{border:1px dashed #363d45;border-radius:13px;padding:36px;text-align:center;color:var(--muted);grid-column:1/-1}footer{max-width:1220px;margin:auto;padding:0 24px 35px;color:#555d65;font-size:9px;letter-spacing:1px}@media(max-width:720px){.grid,.stats{grid-template-columns:1fr}.hero h2{font-size:27px}}
'''


def page(title: str, active: str, body: str, bo: int, proc: int, per: int) -> str:
    nav = "".join(f'<a class="{"on" if active==key else ""}" href="{href}">{label}<b>{count}</b></a>' for key,href,label,count in (("central","/","Central",bo+proc+per),("bo","/boletins","Boletins",bo),("proc","/procurados","Procurados",proc),("per","/pericias","Perícias",per)))
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • {esc(title)}</title><style>{CSS}</style></head><body><header><div class="head"><div class="crest">PF<br><small>DICOR</small></div><div class="brand"><h1>DICOR • CENTRAL DE INTELIGÊNCIA</h1><small>POLÍCIA FEDERAL • CONSULTA INTERNA • SOMENTE LEITURA</small></div></div><nav>{nav}</nav></header><main>{body}</main><footer>DICOR • POLÍCIA FEDERAL • DADOS CONSULTADOS DIRETAMENTE DO DISCORD</footer></body></html>'


def cards(rows: list[dict[str, Any]], kind: str) -> str:
    if not rows:
        return '<div class="empty">Nenhum registro ativo encontrado no Discord.</div>'
    label = "BOLETIM" if kind == "bo" else "PERÍCIA"
    out=[]
    for row in rows:
        dt=row["created"]
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        date=dt.astimezone().strftime("%d/%m/%Y %H:%M")
        out.append(f'<article class="card"><div class="top"><span class="tag">{label}</span><span class="status">ATIVO</span></div><h3>Nº {esc(row["number"])}</h3><div class="meta"><span>Tópico</span><b>{esc(row["name"][:70])}</b></div><div class="meta"><span>Responsável</span><b>{esc(row["agent"])}</b></div><div class="meta"><span>Abertura</span><b>{esc(date)}</b></div><a class="open" href="{esc(row["url"])}" target="_blank">Abrir no Discord →</a></article>')
    return ''.join(out)


async def dashboard(client: discord.Client) -> str:
    bo=await live_boletins(client); pe=await live_pericias(client); pr=await live_procurados(client)
    body=f'<section class="hero"><div class="eyebrow">PAINEL OPERACIONAL</div><h2>Central de Inteligência</h2><p>A Central voltou a consultar os registros diretamente do Discord. Nenhum snapshot local é usado para montar os cards.</p></section><section class="stats"><a class="stat" href="/boletins"><span>Boletins ativos</span><b>{len(bo)}</b></a><a class="stat" href="/procurados"><span>Procurados</span><b>{len(pr)}</b></a><a class="stat" href="/pericias"><span>Perícias pendentes</span><b>{len(pe)}</b></a></section><div class="section"><h3>MÓDULOS ATIVOS</h3></div><section class="grid"><article class="card"><span class="tag">BOLETINS</span><h3>Boletins de ocorrência</h3><p style="color:#8d959e">Registros ativos lidos dos tópicos reais.</p><a class="open" href="/boletins">Ver boletins →</a></article><article class="card"><span class="tag">PROCURADOS</span><h3>Procurados</h3><p style="color:#8d959e">Consulta dos canais do Discord identificados como procurados/mandados.</p><a class="open" href="/procurados">Ver procurados →</a></article><article class="card"><span class="tag">PERÍCIAS</span><h3>Perícias externas</h3><p style="color:#8d959e">Perícias abertas e ainda não encerradas.</p><a class="open" href="/pericias">Ver perícias →</a></article></section>'
    return page("Central", "central", body, len(bo), len(pr), len(pe))


class CentralV607:
    def __init__(self, client: discord.Client):
        self.client=client; self.runner=None; self.site=None; self.started=False

    async def start(self):
        if self.started: return
        self.started=True
        app=web.Application()
        async def home(_): return web.Response(text=await dashboard(self.client),content_type="text/html")
        async def bos(_):
            rows=await live_boletins(self.client); return web.Response(text=page("Boletins","bo",f'<section class="hero"><div class="eyebrow">ÚLTIMOS BOLETINS ATIVOS</div><h2>Boletins</h2><p>Fonte: tópicos reais do Discord.</p></section><section class="grid">{cards(rows,"bo")}</section>',len(rows),0,len(await live_pericias(self.client))),content_type="text/html")
        async def pes(_):
            rows=await live_pericias(self.client); return web.Response(text=page("Perícias","per",f'<section class="hero"><div class="eyebrow">CONTROLE DA PERÍCIA EXTERNA</div><h2>Perícias</h2><p>Fonte: canal e tópicos reais do Discord.</p></section><section class="grid">{cards(rows,"per")}</section>',len(await live_boletins(self.client)),0,len(rows)),content_type="text/html")
        async def prs(_):
            rows=await live_procurados(self.client); body=f'<section class="hero"><div class="eyebrow">CADASTRO OPERACIONAL</div><h2>Procurados</h2><p>Fonte: canais do Discord encontrados pelo próprio bot.</p></section><section class="grid">{cards(rows,"proc")}</section>'; return web.Response(text=page("Procurados","proc",body, len(await live_boletins(self.client)),len(rows),len(await live_pericias(self.client))),content_type="text/html")
        app.router.add_get("/",home); app.router.add_get("/boletins",bos); app.router.add_get("/procurados",prs); app.router.add_get("/pericias",pes)
        self.runner=web.AppRunner(app); await self.runner.setup(); self.site=web.TCPSite(self.runner,"0.0.0.0",PORT); await self.site.start()
        print(f"🌐 Central DICOR V607 online | porta={PORT} | fonte=Discord",flush=True)

    async def on_ready(self):
        await self.start()


def install(bot_module: Any) -> CentralV607:
    client=getattr(bot_module,"bot",None)
    if client is None or not hasattr(client,"add_listener"):
        raise RuntimeError("cliente Discord inválido")
    existing=getattr(client,"_dicor_central_v607",None)
    if existing is not None: return existing
    central=CentralV607(client); client._dicor_central_v607=central; client.add_listener(central.on_ready,"on_ready"); return central
