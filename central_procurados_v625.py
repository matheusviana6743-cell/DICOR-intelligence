# -*- coding: utf-8 -*-
"""Central DICOR V625 - upload maior + Procurados completos + Fivemanage."""
from __future__ import annotations
import html, os, re
from typing import Any
from urllib.parse import quote
import aiohttp
import central_discord_v613 as base
import central_procurados_v624 as v624

MAX_BODY = 12 * 1024 * 1024
MAX_IMAGE = 10 * 1024 * 1024
FIVEMANAGE_API = "https://api.fivemanage.com/api/v3/file"
_ORIGINAL_START = v624._ORIGINAL_START_SERVER
_CLIENT = None

collect_procurados = v624.collect_procurados if hasattr(v624, "collect_procurados") else getattr(base, "collect_procurados")


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def card(row: dict[str, Any]) -> str:
    name = esc(row.get("name", "Indivíduo não identificado"))
    rg = esc(row.get("rg", "Não informado"))
    crime = esc(row.get("crime", "Não informado"))
    seen = esc(row.get("last_seen", "Não informado"))
    image = row.get("image") or ""
    rid = esc(row.get("source_id", ""))
    photo = f'<img src="{esc(image)}" alt="Foto" loading="lazy">' if image else '<div class="no-photo">SEM FOTO</div>'
    return f'''<a class="wanted-card" href="/procurado/{rid}"><div class="wanted-photo">{photo}</div><div class="wanted-info"><div class="wanted-name">{name}</div><div class="wanted-meta"><b>RG/PASSAPORTE</b><span>{rg}</span></div><div class="wanted-meta"><b>CRIMES</b><span>{crime}</span></div><div class="wanted-meta"><b>ÚLTIMO AVISTAMENTO</b><span>{seen}</span></div><div class="open-record">VER REGISTRO COMPLETO →</div></div></a>'''


async def all_procurados(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/procurados")
    qra, passport = session
    rows = await collect_procurados(_CLIENT)
    q = str(req.query.get("q", "")).strip().casefold()
    if q:
        rows = [r for r in rows if q in str(r.get("name", "")).casefold() or q in str(r.get("rg", "")).casefold() or q in str(r.get("crime", "")).casefold()]
    rows = sorted(rows, key=lambda r: r.get("created") or 0, reverse=True)
    cards = "".join(card(r) for r in rows) or '<div class="empty">Nenhum procurado encontrado.</div>'
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="central-tabs"><a class="tab active" href="/procurados">PROCURADOS</a><a class="tab" href="/fotos">FOTOS</a></div><section class="hero"><div class="eyebrow">CENTRAL DICOR • BANCO OPERACIONAL</div><h1>PROCURADOS</h1><p>Consulta completa dos registros ativos. Clique em um registro para abrir todos os dados sem sair da Central.</p><form class="search-box" method="get" action="/procurados"><input name="q" value="{esc(req.query.get("q", ""))}" placeholder="Pesquisar por nome, RG ou crime"><button type="submit">PESQUISAR</button></form></section><section class="wanted"><div class="wanted-head"><b>TODOS OS PROCURADOS</b><span>{len(rows)} REGISTRO(S)</span></div><div class="wanted-grid">{cards}</div></section></main></div>'''
    css = base.APP_CSS + '''.central-tabs{display:flex;gap:8px;margin-top:16px}.tab{padding:10px 16px;border:1px solid #20384e;border-radius:10px;color:#7890a6;font-size:9px;font-weight:900;letter-spacing:1.2px}.tab.active{background:#102b43;color:#e5b84e;border-color:#315979}.search-box{display:flex;gap:8px;margin-top:18px}.search-box input{flex:1;min-width:0;height:44px;border:1px solid #25425d;background:#07111c;color:#eef4f8;border-radius:10px;padding:0 13px;outline:none}.search-box button{border:0;border-radius:10px;padding:0 18px;background:#c99b32;color:#080b0e;font-weight:900;cursor:pointer}.wanted-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wanted-card{display:grid;grid-template-columns:150px 1fr;min-height:210px;border:1px solid #1e354a;border-radius:15px;overflow:hidden;background:#08111b;transition:.18s}.wanted-card:hover{border-color:#3d6b91;transform:translateY(-2px)}.wanted-photo{background:#05090f;min-height:210px;display:grid;place-items:center}.wanted-photo img{width:100%;height:100%;min-height:210px;object-fit:cover}.no-photo{color:#53697d;font-size:9px;font-weight:900;letter-spacing:1px}.wanted-info{padding:16px;min-width:0}.wanted-name{font-size:18px;font-weight:900;margin-bottom:13px;color:#edf3f7}.wanted-meta{margin:9px 0}.wanted-meta b{display:block;font-size:8px;letter-spacing:1px;color:#62819b;margin-bottom:3px}.wanted-meta span{display:block;font-size:11px;color:#c4d0da;line-height:1.4;overflow-wrap:anywhere}.open-record{margin-top:14px;color:#d5ad52;font-size:8px;font-weight:900;letter-spacing:1px}.empty{padding:30px;text-align:center;color:#71869b;border:1px dashed #294057;border-radius:12px}@media(max-width:850px){.wanted-grid{grid-template-columns:1fr}}@media(max-width:600px){.main{padding:14px}.wanted-card{grid-template-columns:105px 1fr}.wanted-photo,.wanted-photo img{min-height:180px}.wanted-name{font-size:15px}.search-box{flex-direction:column}.search-box button{height:42px}}'''
    return base.web.Response(text=base.page("DICOR • Procurados", body, css), content_type="text/html")


async def upload_to_fivemanage(data: bytes, filename: str) -> str:
    api_key = os.getenv("FIVEMANAGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FIVEMANAGE_API_KEY não configurada no ambiente")
    form = aiohttp.FormData()
    form.add_field("file", data, filename=filename, content_type="application/octet-stream")
    form.add_field("filename", filename)
    form.add_field("path", "dicor-central")
    form.add_field("retentionExempt", "true")
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(FIVEMANAGE_API, headers={"Authorization": api_key}, data=form) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"Fivemanage HTTP {resp.status}: {text[:500]}")
            try:
                payload = await resp.json(content_type=None)
            except Exception as exc:
                raise RuntimeError(f"Resposta inválida do Fivemanage: {text[:500]}") from exc
            url = (((payload or {}).get("data") or {}).get("url") or ((payload or {}).get("data") or {}).get("originalUrl") or "").strip()
            if not url:
                raise RuntimeError(f"Fivemanage não retornou URL: {text[:500]}")
            return url


async def upload_photo(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/fotos")
    reader = await req.multipart()
    part = await reader.next()
    if part is None or part.name != "foto":
        raise base.web.HTTPBadRequest(text="Imagem não enviada.")
    filename = os.path.basename(part.filename or "foto.png")
    if not re.search(r"\.(?:png|jpe?g|webp|gif)$", filename, re.I):
        raise base.web.HTTPBadRequest(text="Use PNG, JPG, WEBP ou GIF.")
    data = await part.read(decode=False)
    if not data or len(data) > MAX_IMAGE:
        raise base.web.HTTPBadRequest(text="A imagem deve ter até 10 MB.")
    try:
        direct_url = await upload_to_fivemanage(data, filename)
        body = f'''<main class="auth"><div class="eyebrow">CENTRAL DICOR • ARQUIVO VISUAL</div><h1>FOTO ENVIADA</h1><p class="sub">A imagem foi enviada para o Fivemanage e recebeu um link direto, pronto para colar no FiveM.</p><div class="photo-msg"><img src="{esc(direct_url)}" style="max-width:100%;max-height:420px;border-radius:12px;object-fit:contain;margin:10px 0 18px"><b>LINK DIRETO DA IMAGEM</b><div class="stable-link" style="word-break:break-all">{esc(direct_url)}</div><button class="upload-btn" onclick="navigator.clipboard.writeText('{esc(direct_url)}');return false;">COPIAR LINK DIRETO</button></div><a class="primary gold" style="display:block;text-decoration:none;padding-top:16px" href="/fotos">VOLTAR AO BANCO DE FOTOS</a></main>'''
        return base.web.Response(text=base.page("DICOR • Foto", body, base.AUTH_CSS), content_type="text/html")
    except Exception as exc:
        print(f"⚠️ V625 Fivemanage upload: {type(exc).__name__}: {exc}", flush=True)
        raise base.web.HTTPBadGateway(text="Não foi possível enviar a imagem para o Fivemanage. Verifique a chave FIVEMANAGE_API_KEY.")


class ApplicationPatch(base.web.Application):
    def __init__(self, *args: Any, **kwargs: Any):
        kwargs["client_max_size"] = MAX_BODY
        super().__init__(*args, **kwargs)
        self.router.add_get("/procurados", all_procurados, name="v625_all_procurados")
        self.router.add_get("/procurado/{source_id}", v624.v622.detail_route, name="v625_detail")
        self.router.add_get("/imagem-procurado/{message_id}", v624.v622.procurado_photo, name="v625_wanted_photo")
        self.router.add_get("/fotos", v624.v622.photos_page, name="v625_photos")
        self.router.add_get("/foto/{message_id}", v624.v622.stable_photo, name="v625_stable_photo")
        self.router.add_post("/fotos/upload", upload_photo, name="v625_upload")


async def start_server_v625(client: Any):
    global _CLIENT
    _CLIENT = client
    v624.v622._CLIENT = client
    original_app = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        return await _ORIGINAL_START(client)
    finally:
        base.web.Application = original_app

base.start_server = start_server_v625
base.collect_procurados = collect_procurados


def install(bot_module: Any):
    return base.install(bot_module)
