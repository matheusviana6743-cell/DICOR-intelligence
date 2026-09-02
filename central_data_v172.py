# -*- coding: utf-8 -*-
"""V172 - camada de dados completa da Central DICOR.

Mantém o visual/autorização das versões anteriores, mas transforma as publicações
Discord em registros estruturados para Procurados, Boletins, Perícias, Banco e Árvore.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import quote

PROCURADOS_ID = 1490200533980545097


def install(bot_module) -> None:
    web = bot_module.web
    client = bot_module.bot
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_path = data_dir / "central_dados_v172.json"
    state: Dict[str, Any] = {"procurados": [], "boletins": [], "pericias": [], "updated": 0, "task": None, "ready": False}

    def esc(v: Any) -> str:
        return html.escape(str(v if v is not None else ""))

    def norm(v: Any) -> str:
        s = str(v or "").casefold()
        s = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", s)
        return " ".join(s.split())

    def first(r: Dict[str, Any], keys: Iterable[str], default: str = "Não informado") -> str:
        for k in keys:
            v = r.get(k)
            if v not in (None, "", [], {}):
                return str(v)
        return default

    def clean_label(s: str) -> str:
        s = re.sub(r"[*_`~]", "", str(s or ""))
        s = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", s)
        return s.strip().casefold()

    def parse_blob(blob: str, labels: Iterable[str]) -> str:
        wanted = {norm(x) for x in labels}
        for line in str(blob or "").splitlines():
            raw = line.strip()
            if not raw:
                continue
            if ":" in raw:
                label, value = raw.split(":", 1)
                if norm(clean_label(label)) in wanted:
                    value = re.sub(r"^[*_`~\s]+|[*_`~\s]+$", "", value).strip()
                    if value:
                        return value
            for label in wanted:
                m = re.match(rf"^\s*[*_`~\-•]*\s*{re.escape(label)}\s*[-–—]\s*(.+)$", norm(raw), re.I)
                if m:
                    return m.group(1).strip()
        return ""

    def message_blob(message) -> str:
        parts: List[str] = []
        content = str(getattr(message, "content", "") or "").strip()
        if content:
            parts.append(content)
        for embed in list(getattr(message, "embeds", []) or []):
            title = str(getattr(embed, "title", "") or "").strip()
            desc = str(getattr(embed, "description", "") or "").strip()
            if title:
                parts.append(title)
            if desc:
                parts.append(desc)
            for field in list(getattr(embed, "fields", []) or []):
                n = str(getattr(field, "name", "") or "").strip()
                v = str(getattr(field, "value", "") or "").strip()
                if n or v:
                    parts.append(f"{n}: {v}" if n else v)
        return "\n".join(parts).strip()

    def message_images(message) -> List[str]:
        out: List[str] = []
        exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        for a in list(getattr(message, "attachments", []) or []):
            url = str(getattr(a, "url", "") or "")
            fn = str(getattr(a, "filename", "") or "").lower()
            ct = str(getattr(a, "content_type", "") or "").lower()
            if url and (ct.startswith("image/") or fn.endswith(exts)) and url not in out:
                out.append(url)
        for e in list(getattr(message, "embeds", []) or []):
            for attr in ("image", "thumbnail"):
                obj = getattr(e, attr, None)
                url = str(getattr(obj, "url", "") or "") if obj else ""
                if url and url not in out:
                    out.append(url)
        return out

    def parse_message(message, kind: str) -> Dict[str, Any]:
        blob = message_blob(message)
        imgs = message_images(message)
        author = getattr(message, "author", None)
        nome = parse_blob(blob, ("nome", "nome completo", "indivíduo", "individuo", "suspeito", "envolvido", "solicitante"))
        rg = parse_blob(blob, ("rg", "passaporte", "rg/passaporte", "registro geral", "id"))
        crime = parse_blob(blob, ("crime", "crimes", "acusação", "acusacao", "infração", "infracao"))
        descricao = parse_blob(blob, ("descrição", "descricao", "detalhes", "observações", "observacoes", "resumo"))
        local = parse_blob(blob, ("local", "localização", "localizacao", "último avistamento", "ultimo avistamento", "endereço", "endereco"))
        numero = parse_blob(blob, ("boletim", "número do boletim", "numero do boletim", "protocolo", "bo", "nº"))
        data = getattr(message, "created_at", None)
        return {
            "tipo": kind,
            "mensagem_id": int(getattr(message, "id", 0) or 0),
            "mensagem_url": str(getattr(message, "jump_url", "") or ""),
            "nome": nome or str(getattr(author, "display_name", "") or "Não informado"),
            "rg": rg,
            "crime": crime,
            "descricao": descricao,
            "local": local,
            "numero_boletim": numero,
            "texto_discord": blob,
            "fotos": imgs,
            "autor": str(getattr(author, "display_name", "") or "Não informado"),
            "autor_id": int(getattr(author, "id", 0) or 0),
            "data": data.isoformat() if hasattr(data, "isoformat") else "",
        }

    async def resolve(cid: int):
        if not cid:
            return None
        c = client.get_channel(cid)
        if c is not None:
            return c
        try:
            return await client.fetch_channel(cid)
        except Exception:
            return None

    def candidate_channels(kind: str):
        attrs = {
            "boletins": ("BOLETINS_CHANNEL_ID", "BOLETIM_CHANNEL_ID", "BOLETINS_ATIVOS_CHANNEL_ID", "BOLETIM_ATENDIMENTO_CHANNEL_ID"),
            "pericias": ("PERICIAS_CHANNEL_ID", "PERICIA_FLUXO_CHANNEL_ID", "BANCO_PERICIA_CHANNEL_ID", "PERICIA_CHANNEL_ID"),
        }[kind]
        ids = set()
        for a in attrs:
            try:
                v = int(getattr(bot_module, a, 0) or 0)
                if v:
                    ids.add(v)
            except Exception:
                pass
        terms = {"boletins": ("boletim", "ocorrencia", "ocorrência", "relatorio", "relatório"), "pericias": ("pericia", "perícia", "laudo", "evidencia", "evidência", "forense")}[kind]
        for guild in list(getattr(client, "guilds", []) or []):
            for c in list(getattr(guild, "channels", []) or []):
                name = norm(getattr(c, "name", ""))
                if any(t in name for t in terms):
                    try: ids.add(int(c.id))
                    except Exception: pass
        return list(ids)[:20]

    async def scan_channel(channel, kind: str, limit: int = 300) -> List[Dict[str, Any]]:
        if channel is None:
            return []
        out: List[Dict[str, Any]] = []
        seen = set()
        try:
            if hasattr(channel, "history"):
                async for m in channel.history(limit=limit, oldest_first=False):
                    if not (getattr(m, "content", "") or getattr(m, "embeds", None) or getattr(m, "attachments", None)):
                        continue
                    rec = parse_message(m, kind)
                    out.append(rec); seen.add(rec["mensagem_id"])
            for thread in list(getattr(channel, "threads", []) or []):
                try:
                    async for m in thread.history(limit=100, oldest_first=True):
                        if int(getattr(m, "id", 0) or 0) in seen:
                            continue
                        if not (getattr(m, "content", "") or getattr(m, "embeds", None) or getattr(m, "attachments", None)):
                            continue
                        rec = parse_message(m, kind)
                        rec["thread"] = str(getattr(thread, "name", "") or "")
                        out.append(rec); seen.add(rec["mensagem_id"])
                except Exception:
                    pass
        except Exception as exc:
            print(f"⚠️ V172 {kind}: {type(exc).__name__}: {exc}", flush=True)
        return out

    async def sync():
        try:
            wanted = []
            ch = await resolve(PROCURADOS_ID)
            if ch is not None and hasattr(ch, "history"):
                async for m in ch.history(limit=None, oldest_first=True):
                    if getattr(m, "content", "") or getattr(m, "embeds", None) or getattr(m, "attachments", None):
                        wanted.append(parse_message(m, "procurado"))
            # O sincronizador V171 continua sendo a fonte principal dos procurados; aqui enriquecemos os campos.
            v171 = getattr(bot_module, "_v43_procurados_ativos", None)
            if callable(v171):
                try:
                    existing = list(v171() or [])
                    by_id = {int(x.get("mensagem_id")): x for x in wanted if x.get("mensagem_id")}
                    for x in existing:
                        try:
                            mid = int(x.get("mensagem_id") or 0)
                        except Exception:
                            mid = 0
                        if mid and mid in by_id:
                            merged = dict(x); merged.update({k:v for k,v in by_id[mid].items() if v not in ("", [], None)})
                            by_id[mid] = merged
                    wanted = list(by_id.values())
                except Exception:
                    pass

            boletins: List[Dict[str, Any]] = []
            # Reaproveita o snapshot oficial do bot quando disponível.
            fn = getattr(bot_module, "_v44_boletins_ativos_snapshot", None)
            if callable(fn):
                try:
                    raw = fn() or []
                    if isinstance(raw, list): boletins.extend(dict(x) for x in raw if isinstance(x, dict))
                except Exception: pass
            for cid in candidate_channels("boletins"):
                boletins.extend(await scan_channel(await resolve(cid), "boletim"))
            # deduplicação por mensagem/número/texto
            uniq = {}
            for r in boletins:
                key = str(r.get("mensagem_id") or r.get("numero_boletim") or r.get("id") or hash(r.get("texto_discord", "")))
                uniq[key] = r
            boletins = list(uniq.values())[:500]

            pericias: List[Dict[str, Any]] = []
            for cid in candidate_channels("pericias"):
                pericias.extend(await scan_channel(await resolve(cid), "pericia"))
            uniqp = {}
            for r in pericias:
                uniqp[str(r.get("mensagem_id") or hash(r.get("texto_discord", "")))] = r
            pericias = list(uniqp.values())[:500]

            state["procurados"] = wanted
            state["boletins"] = boletins
            state["pericias"] = pericias
            state["updated"] = int(time.time())
            state["ready"] = True
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({k:v for k,v in state.items() if k not in ("task",)}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(cache_path)
            print(f"✅ V172 Central: {len(wanted)} procurados, {len(boletins)} boletins, {len(pericias)} perícias sincronizados.", flush=True)
        except Exception as exc:
            print(f"⚠️ V172 Central sync: {type(exc).__name__}: {exc}", flush=True)

    def load_cache():
        try:
            if cache_path.exists():
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                for k in ("procurados", "boletins", "pericias"):
                    if isinstance(raw.get(k), list): state[k] = raw[k]
                state["updated"] = int(raw.get("updated") or 0)
        except Exception:
            pass

    def shell(title: str, body: str) -> str:
        css = """
        body{background:#050505;color:#f4efdf;font-family:Inter,Arial,sans-serif;margin:0}a{color:inherit}.vwrap{max-width:1320px;margin:auto;padding:42px 22px 70px}.vhero{text-align:center;margin-bottom:32px}.ey{color:#d9b941;font-size:10px;letter-spacing:2px}.vhero h1{font-family:Georgia,serif;font-size:42px;margin:9px 0}.muted{color:#9e9887}.vgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.vcard{background:#0d0d09;border:1px solid #403519;border-radius:16px;padding:20px}.vcard h2,.vcard h3{font-family:Georgia,serif}.vcard p{color:#b9b19b;line-height:1.55;white-space:pre-wrap}.tag{display:inline-block;border:1px solid #5a4718;color:#e4c85f;padding:5px 8px;border-radius:99px;font-size:9px;margin:2px}.photo{width:100%;height:260px;object-fit:cover;border-radius:10px;background:#020202}.btn{display:inline-block;background:#d8b63f;color:#090804;text-decoration:none;padding:10px 13px;border-radius:8px;font-weight:bold;margin-top:10px}.back{color:#e2c65e;text-decoration:none}.search{width:100%;padding:13px;border-radius:10px;border:1px solid #4b3d1b;background:#090906;color:#fff;margin:16px 0 24px}.stat{font-size:28px;color:#f0d878}.two{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}@media(max-width:900px){.vgrid,.two{grid-template-columns:1fr}}"""
        return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><main class="vwrap">{body}</main></body></html>'

    def record_card(r: Dict[str, Any], kind: str) -> str:
        imgs = list(r.get("fotos") or [])
        nome = first(r, ("nome", "nome_completo", "suspeito"))
        rg = first(r, ("rg", "passaporte", "registro_geral"))
        numero = first(r, ("numero_boletim", "boletim", "protocolo", "numero"), "—")
        crime = first(r, ("crime", "crimes", "acusacao", "acusação"))
        local = first(r, ("local", "localizacao", "localização", "ultimo_avistamento", "último avistamento"))
        desc = first(r, ("descricao", "descrição", "detalhes", "texto_discord"))
        photo = f'<img class="photo" src="{esc(imgs[0])}" loading="lazy">' if imgs else '<div class="photo" style="display:grid;place-items:center;color:#716b5c">SEM IMAGEM</div>'
        return f'''<article class="vcard" data-search="{esc(norm(json.dumps(r,ensure_ascii=False,default=str)))}">{photo}<div class="ey" style="margin-top:15px">{esc(kind.upper())}</div><h2>{esc(nome)}</h2><div><span class="tag">RG: {esc(rg)}</span><span class="tag">BO: {esc(numero)}</span></div><p><b>Crime/assunto:</b> {esc(crime)}</p><p><b>Local:</b> {esc(local)}</p><p><b>Descrição:</b> {esc(desc)}</p>{f'<a class="btn" target="_blank" href="{esc(r.get("mensagem_url"))}">Abrir publicação Discord</a>' if r.get("mensagem_url") else ''}</article>'''

    async def portal(request):
        p, b, pe = len(state["procurados"]), len(state["boletins"]), len(state["pericias"])
        body = f'''<section class="vhero"><div class="ey">POLÍCIA FEDERAL • DICOR</div><h1>Central de Inteligência</h1><p class="muted">Dados reais sincronizados do Discord e preservados no volume do Railway.</p></section><section class="vgrid"><article class="vcard"><div class="ey">PROCURADOS</div><div class="stat">{p}</div><p>Fichas com nome, RG, crimes, descrição, localização e fotografias.</p><a class="btn" href="/catalogo">Abrir catálogo</a></article><article class="vcard"><div class="ey">BOLETINS</div><div class="stat">{b}</div><p>Registros operacionais, envolvidos, números, textos e anexos.</p><a class="btn" href="/boletins">Consultar boletins</a></article><article class="vcard"><div class="ey">PERÍCIAS</div><div class="stat">{pe}</div><p>Registros, laudos, evidências, fotografias e publicações.</p><a class="btn" href="/pericias">Consultar perícias</a></article><article class="vcard"><div class="ey">BANCO DE DADOS</div><div class="stat">{p+b+pe}</div><p>Índice unificado de pessoas, documentos, ocorrências e evidências.</p><a class="btn" href="/fichas">Abrir banco</a></article><article class="vcard"><div class="ey">ÁRVORE DE INTELIGÊNCIA</div><div class="stat">{len({norm(first(x,("nome",))) for x in state["procurados"] if first(x,("nome",),"")})}</div><p>Relações derivadas dos registros sincronizados.</p><a class="btn" href="/arvore">Abrir árvore</a></article></section>'''
        return web.Response(text=shell("Central DICOR", body), content_type="text/html", charset="utf-8")

    async def catalogo(request):
        cards = "".join(record_card(x, "Procurado") for x in state["procurados"]) or '<div class="vcard">Nenhum registro encontrado.</div>'
        body = f'<a class="back" href="/">← Central</a><section class="vhero"><div class="ey">CATÁLOGO OFICIAL</div><h1>Procurados</h1><p class="muted">Cada publicação é transformada em ficha completa.</p></section><input id="q" class="search" placeholder="Pesquisar nome, RG, crime, local..."> <section class="vgrid" id="list">{cards}</section><script>q.oninput=()=>{{let v=q.value.toLowerCase();document.querySelectorAll("[data-search]").forEach(x=>x.style.display=x.dataset.search.includes(v)?"block":"none")}}</script>'
        return web.Response(text=shell("Procurados • DICOR", body), content_type="text/html", charset="utf-8")

    async def generic_page(request, kind: str):
        records = state[kind]
        label = {"boletins":"Boletins", "pericias":"Perícias"}[kind]
        cards = "".join(record_card(x, label[:-1] if label.endswith("s") else label) for x in records) or '<div class="vcard">Nenhum registro sincronizado ainda.</div>'
        body = f'<a class="back" href="/">← Central</a><section class="vhero"><div class="ey">ÁREA OPERACIONAL</div><h1>{label}</h1><p class="muted">Conteúdo estruturado a partir das publicações e registros do Discord.</p></section><input id="q" class="search" placeholder="Pesquisar em {label.lower()}..."> <section class="vgrid">{cards}</section><script>q.oninput=()=>{{let v=q.value.toLowerCase();document.querySelectorAll("[data-search]").forEach(x=>x.style.display=x.dataset.search.includes(v)?"block":"none")}}</script>'
        return web.Response(text=shell(label + " • DICOR", body), content_type="text/html", charset="utf-8")

    async def fichas(request):
        merged = []
        for r in state["procurados"] + state["boletins"] + state["pericias"]:
            merged.append(r)
        cards = "".join(record_card(x, "Registro") for x in merged) or '<div class="vcard">Banco vazio.</div>'
        body = f'<a class="back" href="/">← Central</a><section class="vhero"><div class="ey">NÍVEL RESERVADO</div><h1>Banco de Dados</h1><p class="muted">Índice unificado dos registros sincronizados.</p></section><input id="q" class="search" placeholder="Nome, RG, BO, crime, local..."> <section class="vgrid">{cards}</section><script>q.oninput=()=>{{let v=q.value.toLowerCase();document.querySelectorAll("[data-search]").forEach(x=>x.style.display=x.dataset.search.includes(v)?"block":"none")}}</script>'
        return web.Response(text=shell("Banco de Dados • DICOR", body), content_type="text/html", charset="utf-8")

    async def arvore(request):
        nodes: Dict[str, Dict[str, Any]] = {}
        for r in state["procurados"] + state["boletins"] + state["pericias"]:
            nome = first(r, ("nome", "nome_completo", "suspeito"), "").strip()
            rg = first(r, ("rg", "passaporte"), "").strip()
            bo = first(r, ("numero_boletim", "boletim", "protocolo"), "").strip()
            local = first(r, ("local", "localizacao", "localização"), "").strip()
            if nome and nome != "Não informado": nodes.setdefault(norm(nome), {"nome":nome,"rg":rg,"bo":bo,"local":local})
        cards = "".join(f'<article class="vcard"><div class="ey">NÓ DE INTELIGÊNCIA</div><h2>{esc(x["nome"])}</h2><p><b>RG:</b> {esc(x["rg"] or "Não informado")}</p><p><b>BO:</b> {esc(x["bo"] or "Não informado")}</p><p><b>Local:</b> {esc(x["local"] or "Não informado")}</p></article>' for x in nodes.values()) or '<div class="vcard">Nenhum vínculo estruturado encontrado.</div>'
        body = f'<a class="back" href="/">← Central</a><section class="vhero"><div class="ey">NÍVEL RESERVADO</div><h1>Árvore de Inteligência</h1><p class="muted">Nós gerados dos registros sincronizados; sem inventar vínculos ausentes.</p></section><section class="vgrid">{cards}</section>'
        return web.Response(text=shell("Árvore • DICOR", body), content_type="text/html", charset="utf-8")

    async def on_ready():
        load_cache()
        await sync()
        if state.get("task") is None or state["task"].done():
            async def loop():
                while True:
                    await asyncio.sleep(60)
                    await sync()
            state["task"] = asyncio.create_task(loop())

    async def on_message(message):
        cid = int(getattr(getattr(message, "channel", None), "id", 0) or 0)
        if cid == PROCURADOS_ID or any(str(getattr(message.channel, "name", "")).lower().find(x) >= 0 for x in ("boletim", "pericia", "perícia", "laudo")):
            asyncio.create_task(sync())

    load_cache()
    if hasattr(client, "add_listener"):
        client.add_listener(on_ready, "on_ready")
        client.add_listener(on_message, "on_message")

    bot_module.central_portal_http = portal
    bot_module.pagina_inicial = catalogo
    bot_module.central_boletins_http = lambda request: generic_page(request, "boletins")
    bot_module.central_pericias_http = lambda request: generic_page(request, "pericias")
    bot_module.central_fichas_http = fichas
    bot_module.central_arvore_http = arvore
    bot_module._v172_central_state = state
    print("✅ V172 Central Data instalado: Procurados + Boletins + Perícias + Banco + Árvore.", flush=True)
