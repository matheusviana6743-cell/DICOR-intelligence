# -*- coding: utf-8 -*-
"""DICOR Central V626 - Boletins + Perícias com interface profissional.

Mantém toda a lógica existente da Central V613/V625 e intercepta somente as
rotas visuais /boletins e /pericias. Procurados/Fotos permanecem intocados.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import central_procurados_v625 as v625

base = v625.base
_ORIGINAL_START = v625.start_server_v625


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _session(request: Any):
    try:
        return base.read_session(request)
    except Exception:
        return None


def _value(row: Any, *keys: str, default: str = "") -> str:
    if isinstance(row, dict):
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
    else:
        for key in keys:
            value = getattr(row, key, None)
            if value not in (None, ""):
                return str(value)
    return default


def _date(value: Any) -> str:
    if not value:
        return "Data não informada"
    try:
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y • %H:%M")
        return str(value)[:40]
    except Exception:
        return str(value)[:40]


def _number(row: Any, fallback: int) -> str:
    raw = _value(row, "numero", "number", "boletim", "id", default="")
    if raw:
        return raw
    return f"{fallback:04d}"


CSS = r'''
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#eaf0f5}body{background:#050b12;overflow-x:hidden}body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 75% -10%,#21466b55 0,transparent 38%),linear-gradient(135deg,#08121d 0,#050a10 52%,#070c12 100%)}
.app-shell{position:relative;z-index:1;width:min(1240px,calc(100% - 32px));margin:0 auto;padding:26px 0 50px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:16px 20px;border:1px solid #20384f;background:linear-gradient(135deg,#0d1a28f5,#08111bf5);border-radius:18px;box-shadow:0 18px 50px #0008}.brand{display:flex;align-items:center;gap:14px}.brand img{width:48px;height:48px;object-fit:contain;filter:drop-shadow(0 8px 15px #0009)}.brand-title{font-size:11px;font-weight:950;letter-spacing:1.8px;color:#f0f4f7}.brand-title span{display:block;color:#cda54b;font-size:9px;letter-spacing:1.5px;margin-top:4px}.operator{font-size:9px;color:#7890a5;letter-spacing:.7px}.online{display:inline-block;width:7px;height:7px;border-radius:50%;background:#54b889;box-shadow:0 0 10px #54b88988;margin-right:6px}.tabs{display:flex;gap:8px;margin:15px 0 0}.tab{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;color:#8499ad;border:1px solid #20384e;background:#09131e;border-radius:10px;padding:10px 16px;font-size:9px;font-weight:950;letter-spacing:1.2px}.tab.active{color:#f0cc69;border-color:#6c5427;background:linear-gradient(135deg,#17170f,#101a23);box-shadow:inset 0 -2px 0 #c79b3c}.hero{margin-top:15px;padding:31px 32px;border:1px solid #29445d;border-radius:20px;background:linear-gradient(135deg,#102033ee,#09121cef);box-shadow:0 25px 65px #0008;position:relative;overflow:hidden}.hero:after{content:"";position:absolute;width:230px;height:230px;right:-90px;top:-100px;border:1px solid #c79b3c22;border-radius:50%;box-shadow:0 0 0 28px #c79b3c08,0 0 0 58px #c79b3c05}.eyebrow{font-size:8px;font-weight:950;letter-spacing:2px;color:#caa44d}.hero h1{margin:7px 0 8px;font-size:31px;letter-spacing:1px}.hero p{margin:0;max-width:760px;color:#8195a8;font-size:12px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:22px}.stat{padding:13px 15px;border:1px solid #1e354a;border-radius:12px;background:#07101a}.stat b{display:block;font-size:20px;color:#edf2f6}.stat span{font-size:8px;letter-spacing:1px;color:#647b90;font-weight:850}.section-head{display:flex;justify-content:space-between;align-items:center;margin:23px 2px 11px}.section-head b{font-size:10px;letter-spacing:1.3px}.section-head span{font-size:8px;color:#63798e;letter-spacing:.8px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.record{border:1px solid #20384d;border-radius:16px;background:linear-gradient(145deg,#0b1723,#07101a);padding:19px;min-height:225px;display:flex;flex-direction:column;box-shadow:0 15px 35px #0005;transition:.18s}.record:hover{border-color:#45647d;transform:translateY(-2px)}.record-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.record-kind{font-size:8px;color:#6d859b;letter-spacing:1.6px;font-weight:950}.record-number{font-size:23px;font-weight:950;margin-top:4px;color:#f0c960}.status{font-size:8px;font-weight:950;letter-spacing:1px;color:#62bf93;border:1px solid #2b6c51;background:#10271e;padding:7px 9px;border-radius:999px;white-space:nowrap}.status.closed{color:#d7a5a5;border-color:#62393e;background:#251518}.preview{margin-top:15px;color:#bac7d2;font-size:11px;line-height:1.6;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}.meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:auto;padding-top:17px}.chip{font-size:8px;color:#7890a5;border:1px solid #1c3348;background:#09131d;border-radius:8px;padding:7px 9px}.open{display:inline-flex;text-decoration:none;margin-top:12px;width:max-content;max-width:100%;padding:10px 13px;border-radius:9px;background:linear-gradient(135deg,#e2bd59,#9c6f17);color:#080b0e;font-size:8px;font-weight:950;letter-spacing:1px}.empty{grid-column:1/-1;padding:45px;text-align:center;border:1px dashed #2b4359;border-radius:15px;color:#667e92;font-size:11px}.detail{margin-top:16px;border:1px solid #20384d;border-radius:18px;background:#08131e;padding:26px}.detail h2{margin:5px 0 15px;font-size:25px}.detail pre{white-space:pre-wrap;word-break:break-word;font:12px/1.7 Inter,Segoe UI,Arial,sans-serif;color:#c6d1da;margin:0}.back{display:inline-block;margin-bottom:10px;color:#d0aa51;text-decoration:none;font-size:9px;font-weight:900;letter-spacing:1px}
@media(max-width:800px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.topbar{align-items:flex-start}.operator{display:none}.hero{padding:25px 21px}.hero h1{font-size:26px}}
@media(max-width:520px){.app-shell{width:min(100% - 20px,1240px);padding-top:10px}.topbar{padding:13px 14px}.brand img{width:40px;height:40px}.tabs{overflow-x:auto}.tab{white-space:nowrap}.stats{grid-template-columns:1fr}.record{min-height:205px}.record-number{font-size:20px}}
'''


def _record(row: Any, index: int, kind: str) -> str:
    number = esc(_number(row, index))
    text = _value(row, "texto", "content", "description", "preview", "resumo", "body", default="Conteúdo não informado.")
    text = text.replace("**", "").replace("__", "").replace("`", "")
    if len(text) > 900:
        text = text[:897] + "..."
    created = _date(_value(row, "created", "created_at", "data", "date", default=""))
    status_raw = _value(row, "status", "situacao", "situação", default="EM ABERTO")
    status = status_raw.upper()[:24] or "EM ABERTO"
    closed = any(x in status.casefold() for x in ("fech", "final", "conclu", "encerr", "arquiv"))
    jump = _value(row, "mensagem_url", "jump_url", "url", "message_url", default="")
    # Some cache rows store the source message URL under source_url.
    jump = jump or _value(row, "source_url", default="")
    link = f'<a class="open" href="{esc(jump)}" target="_blank" rel="noopener">ABRIR REGISTRO NO DISCORD →</a>' if jump else '<a class="open" href="/boletins">ABRIR REGISTRO →</a>'
    return f'''<article class="record"><div class="record-top"><div><div class="record-kind">{kind}</div><div class="record-number">Nº {number}</div></div><span class="status{' closed' if closed else ''}">{esc(status)}</span></div><div class="preview">{esc(text)}</div><div class="meta"><span class="chip">{esc(created)}</span><span class="chip">CONSULTA CENTRAL</span></div>{link}</article>'''


def _page(request: Any, kind: str, rows: list[Any]) -> str:
    sess = _session(request)
    qra, passport = sess or ("OPERADOR", "—")
    is_bo = kind == "BOLETINS"
    title = "DICOR • Boletins" if is_bo else "DICOR • Perícias"
    desc = "Painel operacional dos boletins recebidos, organizados por registro, situação e data." if is_bo else "Painel operacional das perícias recebidas, organizado para consulta rápida das análises e registros."
    tab_bo = "active" if is_bo else ""
    tab_pe = "active" if not is_bo else ""
    cards = "".join(_record(r, i + 1, "BOLETIM DE OCORRÊNCIA" if is_bo else "REGISTRO DE PERÍCIA") for i, r in enumerate(rows))
    if not cards:
        cards = '<div class="empty">Nenhum registro disponível no momento.</div>'
    body = f'''<div class="app-shell"><header class="topbar"><div class="brand">{base.img(base.DICOR_LOGO, "logo", "DICOR")}<div class="brand-title">PCPT — POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div></div><div class="operator"><i class="online"></i>{esc(qra)} • {esc(passport)}</div></header><nav class="tabs"><a class="tab {tab_bo}" href="/boletins">BOLETINS</a><a class="tab {tab_pe}" href="/pericias">PERÍCIAS</a><a class="tab" href="/procurados">PROCURADOS</a><a class="tab" href="/fotos">FOTOS</a></nav><section class="hero"><div class="eyebrow">CENTRAL DICOR • PAINEL OPERACIONAL</div><h1>{kind}</h1><p>{desc}</p><div class="stats"><div class="stat"><b>{len(rows)}</b><span>REGISTROS DISPONÍVEIS</span></div><div class="stat"><b>100%</b><span>CONSULTA CENTRALIZADA</span></div><div class="stat"><b>ATIVO</b><span>MONITORAMENTO DO BANCO</span></div></div></section><div class="section-head"><b>REGISTROS RECENTES</b><span>{len(rows)} ITEM(NS)</span></div><section class="grid">{cards}</section></div>'''
    return base.page(title, body, CSS)


async def central_records_middleware(app: Any, handler: Any):
    async def middleware_handler(request: Any):
        path = request.path or "/"
        if path in ("/boletins", "/boletins.html", "/pericias", "/pericias.html"):
            if not _session(request):
                raise base.web.HTTPFound("/cadastro-operador?next=" + path)
            rows = base.CACHE.get("bo" if path.startswith("/bolet") else "pericia", [])
            if not isinstance(rows, list):
                rows = list(rows or [])
            return base.web.Response(text=_page(request, "BOLETINS" if path.startswith("/bolet") else "PERÍCIAS", rows), content_type="text/html")
        return await handler(request)
    return middleware_handler


class ApplicationPatch(v625.ApplicationPatch):
    def __init__(self, *args: Any, **kwargs: Any):
        middlewares = list(kwargs.pop("middlewares", []) or [])
        middlewares.insert(0, central_records_middleware)
        kwargs["middlewares"] = middlewares
        super().__init__(*args, **kwargs)


async def start_server_v626(client: Any):
    v625.ApplicationPatch = ApplicationPatch
    return await _ORIGINAL_START(client)

v625.start_server_v625 = start_server_v626
base.start_server = start_server_v626


def install(bot_module: Any):
    return base.install(bot_module)
