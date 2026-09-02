# -*- coding: utf-8 -*-
"""V173 - enriquecimento final da Central usando o arquivo histórico migrado."""
from __future__ import annotations

import asyncio
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


def install(bot_module) -> None:
    state = getattr(bot_module, "_v172_central_state", None)
    if not isinstance(state, dict):
        return
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    archive_path = data_dir / "central_discord_archive.json"

    def norm(v: Any) -> str:
        s = str(v or "").casefold()
        s = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", s)
        return " ".join(s.split())

    def esc(v: Any) -> str:
        return html.escape(str(v or ""), quote=True)

    def archive() -> Dict[str, Any]:
        try:
            raw = json.loads(archive_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def records(kind: str) -> List[Dict[str, Any]]:
        raw = archive().get("records", [])
        if not isinstance(raw, list):
            return []
        return [dict(x) for x in raw if isinstance(x, dict) and str(x.get("kind")) == kind]

    def embed_text(r: Dict[str, Any]) -> str:
        parts: List[str] = []
        content = str(r.get("content") or "").strip()
        if content:
            parts.append(content)
        embeds = r.get("embeds", [])
        if isinstance(embeds, list):
            for e in embeds:
                if not isinstance(e, dict):
                    continue
                for key in ("title", "description"):
                    if e.get(key):
                        parts.append(str(e[key]))
                fields = e.get("fields", [])
                if isinstance(fields, list):
                    for f in fields:
                        if not isinstance(f, dict):
                            continue
                        n, v = str(f.get("name") or "").strip(), str(f.get("value") or "").strip()
                        if n and v: parts.append(f"{n}: {v}")
                        elif v: parts.append(v)
        return "\n".join(parts).strip()

    def field(r: Dict[str, Any], aliases: Iterable[str]) -> str:
        wanted = [norm(x) for x in aliases]
        embeds = r.get("embeds", [])
        if isinstance(embeds, list):
            for e in embeds:
                if not isinstance(e, dict): continue
                fs = e.get("fields", [])
                if isinstance(fs, list):
                    for f in fs:
                        if not isinstance(f, dict): continue
                        name = norm(f.get("name")); value = str(f.get("value") or "").strip()
                        if value and any(a in name or name in a for a in wanted): return value
        for line in str(r.get("content") or "").splitlines():
            if ":" not in line: continue
            n, v = line.split(":", 1)
            nn = norm(n)
            if v.strip() and any(a in nn or nn in a for a in wanted): return v.strip()
        return ""

    def images(r: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        ats = r.get("attachments", [])
        if isinstance(ats, list):
            for a in ats:
                if not isinstance(a, dict): continue
                url = str(a.get("source_url") or a.get("url") or "").strip()
                fn = str(a.get("filename") or "").lower()
                ct = str(a.get("content_type") or "").lower()
                if url and (ct.startswith("image/") or fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))) and url not in out: out.append(url)
        embeds = r.get("embeds", [])
        if isinstance(embeds, list):
            for e in embeds:
                if not isinstance(e, dict): continue
                for k in ("image", "thumbnail"):
                    obj = e.get(k)
                    if isinstance(obj, dict):
                        url = str(obj.get("url") or "").strip()
                        if url and url not in out: out.append(url)
        return out

    def convert(r: Dict[str, Any], kind: str) -> Dict[str, Any]:
        text = embed_text(r)
        return {
            "tipo": kind,
            "mensagem_id": int(r.get("message_id") or 0),
            "mensagem_url": str(r.get("jump_url") or ""),
            "nome": field(r, ("nome", "nome completo", "individuo", "indivíduo", "procurado", "suspeito", "envolvido", "solicitante")),
            "rg": field(r, ("rg", "passaporte", "registro geral", "rg funcional")),
            "crime": field(r, ("crime", "crimes", "acusacao", "acusação", "infração", "infracao")),
            "descricao": field(r, ("descrição", "descricao", "detalhes", "observações", "observacoes", "resumo")),
            "local": field(r, ("local", "localização", "localizacao", "último avistamento", "ultimo avistamento", "endereço", "endereco")),
            "numero_boletim": field(r, ("número do boletim", "numero do boletim", "boletim", "protocolo", "bo", "nº")),
            "texto_discord": text,
            "fotos": images(r),
            "autor": str(r.get("author_name") or r.get("author") or "Não informado"),
            "autor_id": int(r.get("author_id") or 0),
            "data": str(r.get("created_at") or ""),
            "canal": str(r.get("channel_name") or ""),
        }

    def enrich() -> None:
        arc = archive()
        if not arc: return
        # Migração histórica: preserva dados ricos mesmo que o novo snapshot só tenha a foto.
        hist_w = [convert(r, "procurado") for r in records("procurados")]
        hist_b = [convert(r, "boletim") for r in records("boletins")]
        hist_p = [convert(r, "pericia") for r in records("pericias")]

        def merge(current: List[Dict[str, Any]], historical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            by_id: Dict[str, Dict[str, Any]] = {}
            for x in historical + current:
                mid = str(x.get("mensagem_id") or "")
                key = mid if mid and mid != "0" else str(hash(json.dumps(x, ensure_ascii=False, default=str)))
                if key not in by_id: by_id[key] = dict(x)
                else:
                    old = by_id[key]; old.update({k:v for k,v in x.items() if v not in ("", [], None, "Não informado")})
            return list(by_id.values())

        state["procurados"] = merge(state.get("procurados", []), hist_w)
        state["boletins"] = merge(state.get("boletins", []), hist_b)
        state["pericias"] = merge(state.get("pericias", []), hist_p)
        print(f"✅ V173 Central: histórico enriquecido — {len(state['procurados'])} procurados, {len(state['boletins'])} boletins, {len(state['pericias'])} perícias.", flush=True)

    enrich()
    client = bot_module.bot

    async def on_ready():
        await asyncio.sleep(1)
        enrich()

    if hasattr(client, "add_listener"):
        client.add_listener(on_ready, "on_ready")

    # Rotas estratégicas: caso versões anteriores não tenham exposto aliases, o V172 fornece as páginas.
    for target, source in (("central_fichas_http", "central_fichas_http"), ("fichas_pagina_http", "central_fichas_http"), ("central_arvore_http", "central_arvore_http"), ("arvore_pagina_http", "central_arvore_http")):
        if hasattr(bot_module, source):
            setattr(bot_module, target, getattr(bot_module, source))
