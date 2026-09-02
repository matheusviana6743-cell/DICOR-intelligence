# -*- coding: utf-8 -*-
"""V173 — enriquecimento leve dos dados da Central.

V163/V164/V165 continuam donos do layout e da autenticação.
V172 coleta dados do Discord; este módulo apenas une o arquivo histórico
quando existir e expõe os providers consumidos pela Central oficial.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


def install(bot_module) -> None:
    state = getattr(bot_module, "_v172_central_state", None)
    if not isinstance(state, dict):
        print("⚠️ V173: estado V172 ausente; mantendo Central oficial intacta.", flush=True)
        return

    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    archive_path = data_dir / "central_discord_archive.json"
    cache_path = data_dir / "central_dados_v172.json"

    def norm(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", text)
        return " ".join(text.split())

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

    def embed_text(record: Dict[str, Any]) -> str:
        parts: List[str] = []
        content = str(record.get("content") or "").strip()
        if content:
            parts.append(content)
        for embed in record.get("embeds", []) if isinstance(record.get("embeds", []), list) else []:
            if not isinstance(embed, dict):
                continue
            for key in ("title", "description"):
                if embed.get(key):
                    parts.append(str(embed[key]))
            for item in embed.get("fields", []) if isinstance(embed.get("fields", []), list) else []:
                if isinstance(item, dict) and item.get("value"):
                    name = str(item.get("name") or "").strip()
                    value = str(item.get("value") or "").strip()
                    parts.append(f"{name}: {value}" if name else value)
        return "\n".join(parts).strip()

    def field(record: Dict[str, Any], aliases: Iterable[str]) -> str:
        wanted = [norm(x) for x in aliases]
        embeds = record.get("embeds", [])
        if isinstance(embeds, list):
            for embed in embeds:
                if not isinstance(embed, dict):
                    continue
                fields = embed.get("fields", [])
                if not isinstance(fields, list):
                    continue
                for item in fields:
                    if not isinstance(item, dict):
                        continue
                    name = norm(item.get("name"))
                    value = str(item.get("value") or "").strip()
                    if value and any(alias == name or alias in name or name in alias for alias in wanted):
                        return value
        for line in str(record.get("content") or "").splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            name = norm(name)
            if value.strip() and any(alias == name or alias in name or name in alias for alias in wanted):
                return value.strip()
        return ""

    def images(record: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        attachments = record.get("attachments", [])
        if isinstance(attachments, list):
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("source_url") or item.get("url") or "").strip()
                filename = str(item.get("filename") or "").lower()
                content_type = str(item.get("content_type") or "").lower()
                if url and (content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))) and url not in out:
                    out.append(url)
        return out

    def convert(record: Dict[str, Any], kind: str) -> Dict[str, Any]:
        return {
            "tipo": kind,
            "mensagem_id": int(record.get("message_id") or 0),
            "mensagem_url": str(record.get("jump_url") or ""),
            "nome": field(record, ("nome", "nome completo", "individuo", "indivíduo", "procurado", "suspeito", "envolvido", "solicitante")),
            "rg": field(record, ("rg", "passaporte", "registro geral", "rg funcional")),
            "crime": field(record, ("crime", "crimes", "acusacao", "acusação", "infração", "infracao")),
            "descricao": field(record, ("descrição", "descricao", "detalhes", "observações", "observacoes", "resumo")),
            "local": field(record, ("local", "localização", "localizacao", "último avistamento", "ultimo avistamento", "endereço", "endereco")),
            "numero_boletim": field(record, ("número do boletim", "numero do boletim", "boletim", "protocolo", "bo", "nº")),
            "texto_discord": embed_text(record),
            "fotos": images(record),
            "autor": str(record.get("author_name") or record.get("author") or "Não informado"),
            "autor_id": int(record.get("author_id") or 0),
            "data": str(record.get("created_at") or ""),
            "canal": str(record.get("channel_name") or ""),
        }

    def merge(current: List[Dict[str, Any]], historical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in historical + current:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("mensagem_id") or item.get("message_id") or "")
            key = mid if mid and mid != "0" else str(hash(json.dumps(item, ensure_ascii=False, default=str)))
            if key not in merged:
                merged[key] = dict(item)
            else:
                merged[key].update({k: v for k, v in item.items() if v not in ("", [], None, "Não informado")})
        return list(merged.values())[:500]

    def enrich() -> None:
        historical = archive()
        if historical:
            state["procurados"] = merge(state.get("procurados", []), [convert(x, "procurado") for x in records("procurados")])
            state["boletins"] = merge(state.get("boletins", []), [convert(x, "boletim") for x in records("boletins")])
            state["pericias"] = merge(state.get("pericias", []), [convert(x, "pericia") for x in records("pericias")])

        # V163 lê estes providers dinamicamente. Não substituímos nenhuma rota.
        bot_module._v43_procurados_ativos = lambda: list(state.get("procurados", []))
        bot_module._v44_boletins_ativos_snapshot = lambda: list(state.get("boletins", []))

        try:
            payload = {k: v for k, v in state.items() if k not in ("task", "syncing")}
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(cache_path)
        except Exception:
            pass

        print(f"✅ V173 dados: {len(state.get('procurados', []))} procurados, {len(state.get('boletins', []))} boletins, {len(state.get('pericias', []))} perícias conectados à Central oficial.", flush=True)

    enrich()

    async def delayed_enrich() -> None:
        # Dá tempo para a primeira sincronização V172 terminar após o READY.
        await asyncio.sleep(6)
        enrich()

    try:
        asyncio.create_task(delayed_enrich())
    except Exception as exc:
        print(f"⚠️ V173: enriquecimento atrasado não iniciado: {type(exc).__name__}: {exc}", flush=True)
