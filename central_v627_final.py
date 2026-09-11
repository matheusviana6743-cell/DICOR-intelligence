# -*- coding: utf-8 -*-
"""DICOR Central V627.

Patch final sobre V625:
- remove temporariamente o sistema de senha/cadastro da Central;
- abre Boletins e Perícias dentro da própria Central, nunca pelo Discord;
- usa exclusivamente os canais oficiais configurados;
- registra acessos e ações HTTP da Central no canal de auditoria.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

import central_procurados_v625 as v625

base = v625.base
_CLIENT = None
BO_CHANNEL_ID = 1490200514837745754
PERICIA_CHANNEL_ID = 1490200524367200297
CENTRAL_LOG_CHANNEL_ID = 1515054190215430406
_ORIGINAL_START = v625._ORIGINAL_START

CSS = r'''
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#eaf0f5}body{background:#050b12;overflow-x:hidden}body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 75% -10%,#21466b55 0,transparent 38%),linear-gradient(135deg,#08121d 0,#050a10 52%,#070c12 100%)}.wrap{position:relative;z-index:1;width:min(1240px,calc(100% - 26px));margin:auto;padding:16px 0 48px}.bar{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:14px 17px;background:#0a1521ee;border:1px solid #203b54;border-radius:17px;box-shadow:0 18px 50px #0008}.brand{display:flex;align-items:center;gap:12px}.brand img{width:45px;height:45px;object-fit:contain;filter:drop-shadow(0 7px 15px #0009)}.brand strong{display:block;font-size:11px;letter-spacing:1.7px}.brand span{display:block;color:#d1a54a;font-size:8px;letter-spacing:1.4px;margin-top:4px}.user{font-size:9px;color:#7e94a8}.tabs{display:flex;gap:8px;overflow:auto;padding:12px 0 0}.tab{flex:0 0 auto;text-decoration:none;color:#8ba0b3;font-size:8px;font-weight:950;letter-spacing:1.3px;padding:10px 13px;border:1px solid #1f364a;border-radius:9px;background:#09131e}.tab.on{color:#f0cb66;border-color:#6b5327;background:#17170f}.hero{margin-top:12px;padding:24px;border-radius:19px;border:1px solid #27435d;background:linear-gradient(135deg,#102234f5,#08111cf5);box-shadow:0 24px 65px #0008}.eyebrow{color:#d1a54a;font-size:8px;letter-spacing:2px;font-weight:950}.hero h1{margin:7px 0 7px;font-size:29px}.hero p{margin:0;color:#8297aa;font-size:11px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:17px}.stat{padding:12px;border:1px solid #1d3448;background:#07111b;border-radius:10px}.stat b{display:block;font-size:19px}.stat span{font-size:7px;color:#667e93;letter-spacing:1px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin-top:12px}.card{display:flex;flex-direction:column;padding:17px;border-radius:15px;border:1px solid #1e374e;background:linear-gradient(145deg,#0a1723,#07101a);min-height:225px}.top{display:flex;justify-content:space-between;gap:12px}.kind{font-size:8px;color:#6d859b;letter-spacing:1.5px;font-weight:950}.num{font-size:22px;color:#f0c85e;font-weight:950;margin-top:4px}.status{font-size:7px;letter-spacing:1px;font-weight:950;color:#65bf94;background:#10281f;border:1px solid #2c6c51;border-radius:999px;padding:7px 9px;height:max-content}.preview{margin-top:13px;color:#becbd6;font-size:10px;line-height:1.65;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:15px}.chip{font-size:7px;color:#7891a5;border:1px solid #1c3348;border-radius:7px;padding:6px 8px;background:#09131c}.btn{display:inline-flex;text-decoration:none;margin-top:10px;width:max-content;padding:9px 12px;border-radius:8px;background:linear-gradient(135deg,#e3bf5b,#9c6f17);color:#090b0d;font-size:8px;font-weight:950;letter-spacing:1px}.detail{margin-top:12px;padding:24px;border:1px solid #24415a;background:#08131e;border-radius:17px}.detail h2{font-size:26px;margin:6px 0 16px}.detail .row{padding:11px 0;border-bottom:1px solid #172c3f}.detail .label{font-size:7px;color:#658099;letter-spacing:1.4px;font-weight:950;margin-bottom:5px}.detail .value{font-size:11px;color:#d0d8df;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.search{margin-top:18px;display:flex;gap:8px}.search input{flex:1;height:42px;background:#07111b;color:#eef3f6;border:1px solid #25435b;border-radius:9px;padding:0 12px;outline:0}.search button{border:0;border-radius:9px;background:#cda247;color:#090b0d;font-weight:950;padding:0 16px}.empty{text-align:center;padding:42px;border:1px dashed #2a455d;border-radius:14px;color:#6f8497;font-size:10px;grid-column:1/-1}@media(max-width:820px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}@media(max-width:520px){.wrap{width:calc(100% - 16px);padding-top:8px}.bar{padding:12px}.brand img{width:38px;height:38px}.user{display:none}.hero{padding:20px}.hero h1{font-size:24px}.stats{grid-template-columns:1fr}.search{flex-direction:column}.search button{height:42px}.card{min-height:205px}}
'''


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def text_of(message: Any) -> str:
    parts = [getattr(message, "content", "") or ""]
    for e in getattr(message, "embeds", []) or []:
        parts.append(getattr(e, "title", "") or "")
        parts.append(getattr(e, "description", "") or "")
        for f in getattr(e, "fields", []) or []:
            parts.append(f"{getattr(f,'name','')}: {getattr(f,'value','')}")
    return "\n".join(p for p in parts if p).strip()


def clean_markdown(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "")


def number_from(text: str, fallback: int = 0) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(pattern, text or "", re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return f"{fallback:04d}" if fallback else "S/N"


def excerpt(text: str, n: int = 700) -> str:
    text = clean_markdown(text)
    return text if len(text) <= n else text[: n - 3] + "..."


def is_closed(text: str) -> bool:
    s = text.casefold()
    return any(x in s for x in ("capturado", "capturada", "finalizado", "finalizada", "encerrado", "encerrada", "cancelado", "cancelada"))


async def channel_history(channel_id: int, limit: int = 80) -> list[Any]:
    if _CLIENT is None:
        return []
    try:
        channel = _CLIENT.get_channel(channel_id) or await _CLIENT.fetch_channel(channel_id)
        out = []
        async for message in channel.history(limit=limit):
            out.append(message)
        return out
    except Exception as exc:
        print(f"⚠️ V627 leitura canal {channel_id}: {type(exc).__name__}: {exc}", flush=True)
        return []


async def log_central(action: str, request: Any = None, extra: str = "") -> None:
    if _CLIENT is None:
        return
    try:
        channel = _CLIENT.get_channel(CENTRAL_LOG_CHANNEL_ID) or await _CLIENT.fetch_channel(CENTRAL_LOG_CHANNEL_ID)
        sess = base.read_session(request) if request is not None else None
        who = f"QRA={sess[0]} PASS={sess[1]}" if sess else "ACESSO SEM IDENTIDADE"
        ip = ""
        try:
            peer = request.transport.get_extra_info("peername") if request and request.transport else None
            ip = str(peer[0]) if peer else ""
        except Exception:
            pass
        stamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")
        content = f"🖥️ CENTRAL | {stamp}\nAção: {action}\nOperador: {who}\nIP: {ip or 'indisponível'}"
        if extra:
            content += f"\nDetalhes: {extra}"
        await channel.send(content[:1900])
    except Exception as exc:
        print(f"⚠️ V627 log Central: {type(exc).__name__}: {exc}", flush=True)


def shell(request: Any, title: str, kind: str, content: str, stats: tuple[str,str,str] = ("—","—","ATIVO")) -> str:
    sess = base.read_session(request)
    qra, passport = sess or ("ACESSO LIVRE", "—")
    nav = "".join([
        f'<a class="tab {"on" if kind=="BOLETINS" else ""}" href="/boletins">BOLETINS</a>',
        f'<a class="tab {"on" if kind=="PERÍCIAS" else ""}" href="/pericias">PERÍCIAS</a>',
        '<a class="tab" href="/procurados">PROCURADOS</a>',
        '<a class="tab" href="/fotos">FOTOS</a>',
    ])
    body = f'''<div class="wrap"><header class="bar"><div class="brand">{base.img(base.DICOR_LOGO,"logo","DICOR")}<div><strong>PCPT — POLÍCIA CAPITAL / POLÍCIA FEDERAL</strong><span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div></div><div class="user">{esc(qra)} • {esc(passport)}</div></header><nav class="tabs">{nav}</nav><section class="hero"><div class="eyebrow">CENTRAL DICOR • PAINEL OPERACIONAL</div><h1>{esc(kind)}</h1><p>{esc(title)}</p><div class="stats"><div class="stat"><b>{esc(stats[0])}</b><span>REGISTROS</span></div><div class="stat"><b>{esc(stats[1])}</b><span>FONTE DISCORD</span></div><div class="stat"><b>{esc(stats[2])}</b><span>MONITORAMENTO</span></div></div></section>{content}</div>'''
    return base.page("DICOR • " + kind, body, CSS)


def field_preview(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:=-]\s*([^\n|•]+)", text, re.I)
        if m:
            return clean_markdown(m.group(1).strip())[:180]
    return "Não informado"


async def source_rows(channel_id: int) -> list[dict[str, Any]]:
    messages = await channel_history(channel_id, 120)
    rows = []
    for idx, m in enumerate(messages):
        text = text_of(m)
        if not text:
            continue
        rows.append({
            "message_id": getattr(m,"id",0),
            "number": number_from(text, idx+1),
            "text": text,
            "created": getattr(m,"created_at",None),
            "author": getattr(getattr(m,"author",None),"display_name", "Não informado"),
            "status": field_preview(text,("status","situação","situacao")) or "EM ABERTO",
        })
    return rows


async def records_page(request: Any, kind: str) -> str:
    channel_id = BO_CHANNEL_ID if kind == "BOLETINS" else PERICIA_CHANNEL_ID
    rows = await source_rows(channel_id)
    q = str(request.query.get("q","")).strip().casefold()
    if q:
        rows = [r for r in rows if q in r["text"].casefold() or q in r["number"].casefold()]
    cards = []
    for r in rows:
        closed = is_closed(r["text"])
        label = "BOLETIM DE OCORRÊNCIA" if kind == "BOLETINS" else "REGISTRO DE PERÍCIA"
        cards.append(f'''<article class="card"><div class="top"><div><div class="kind">{label}</div><div class="num">Nº {esc(r['number'])}</div></div><span class="status">{'ENCERRADO' if closed else 'EM ABERTO'}</span></div><div class="preview">{esc(excerpt(r['text']))}</div><div class="chips"><span class="chip">{esc(r['author'])}</span><span class="chip">{esc(r['created'])}</span></div><a class="btn" href="/{'boletim' if kind=='BOLETINS' else 'pericia'}/{r['message_id']}">VER REGISTRO →</a></article>''')
    content = f'''<form class="search" method="get"><input name="q" value="{esc(q)}" placeholder="Pesquisar por número, nome ou conteúdo"><button type="submit">PESQUISAR</button></form><div class="grid">{''.join(cards) if cards else '<div class="empty">Nenhum registro encontrado.</div>'}</div>'''
    await log_central(f"consulta {kind.lower()}", request, f"filtro={q or 'nenhum'} registros={len(rows)}")
    return base.web.Response(text=shell(request, "Dados consultados diretamente do canal oficial do Discord.", kind, content, (str(len(rows)), str(channel_id), "ONLINE")), content_type="text/html")


async def record_detail(request: Any, kind: str, message_id: int) -> str:
    channel_id = BO_CHANNEL_ID if kind == "BOLETINS" else PERICIA_CHANNEL_ID
    messages = await channel_history(channel_id, 150)
    target = next((m for m in messages if int(getattr(m,"id",0)) == int(message_id)), None)
    if target is None:
        raise base.web.HTTPNotFound(text="Registro não encontrado no canal oficial.")
    text = clean_markdown(text_of(target))
    number = number_from(text)
    author = getattr(getattr(target,"author",None),"display_name","Não informado")
    created = getattr(target,"created_at",None)
    attachments = getattr(target,"attachments",[]) or []
    embeds = getattr(target,"embeds",[]) or []
    media = ''.join(f'<div class="row"><div class="label">ANEXO</div><div class="value"><a class="btn" href="{esc(getattr(a,"url",""))}" target="_blank" rel="noopener">ABRIR ARQUIVO</a></div></div>' for a in attachments)
    emb = ''.join(f'<div class="row"><div class="label">EMBED</div><div class="value">{esc((getattr(e,"title","") or "") + "\n" + (getattr(e,"description","") or ""))}</div></div>' for e in embeds)
    content = f'''<div class="detail"><a class="back" href="/{'boletins' if kind=='BOLETINS' else 'pericias'}">← VOLTAR</a><div class="eyebrow">{'BOLETIM DE OCORRÊNCIA' if kind=='BOLETINS' else 'REGISTRO DE PERÍCIA'}</div><h2>Nº {esc(number)}</h2><div class="row"><div class="label">AUTOR</div><div class="value">{esc(author)}</div></div><div class="row"><div class="label">DATA DE RECEBIMENTO</div><div class="value">{esc(created)}</div></div><div class="row"><div class="label">CONTEÚDO COMPLETO</div><div class="value">{esc(text)}</div></div>{emb}{media}</div>'''
    await log_central(f"abriu {kind.lower()}", request, f"numero={number} message_id={message_id}")
    return base.web.Response(text=shell(request, "Registro completo dentro da Central.", kind, content), content_type="text/html")


async def central_middleware(app: Any, handler: Any):
    async def mw(request: Any):
        path = request.path or "/"
        # Retira temporariamente toda a exigência de login/senha.
        if path in ("/acesso","/cadastro-operador","/criar-senha"):
            await log_central("tentativa de acesso à área de senha redirecionada — sistema de senha DESATIVADO", request)
            raise base.web.HTTPFound("/")
        if path in ("/boletins","/boletins.html"):
            return await records_page(request,"BOLETINS")
        if path in ("/pericias","/pericias.html"):
            return await records_page(request,"PERÍCIAS")
        m = re.fullmatch(r"/boletim/(\d+)", path)
        if m:
            return await record_detail(request,"BOLETINS",int(m.group(1)))
        m = re.fullmatch(r"/pericia/(\d+)", path)
        if m:
            return await record_detail(request,"PERÍCIAS",int(m.group(1)))
        if path not in ("/health","/healthz"):
            await log_central(f"acesso HTTP {request.method} {path}", request)
        return await handler(request)
    return mw


class ApplicationPatch(v625.ApplicationPatch):
    def __init__(self,*args: Any,**kwargs: Any):
        middlewares = list(kwargs.pop("middlewares",[]) or [])
        middlewares.insert(0,central_middleware)
        kwargs["middlewares"] = middlewares
        super().__init__(*args,**kwargs)


async def start_server_v627(client: Any):
    global _CLIENT
    _CLIENT = client
    v625._CLIENT = client
    original_app = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        return await _ORIGINAL_START(client)
    finally:
        base.web.Application = original_app

base.start_server = start_server_v627

def install(bot_module: Any):
    return base.install(bot_module)
