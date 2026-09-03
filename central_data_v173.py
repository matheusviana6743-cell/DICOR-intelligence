# -*- coding: utf-8 -*-
"""Ponte segura de dados para a Central oficial.

Mantém o layout/auth existentes e consolida dados persistidos, incluindo URLs
externas de mídia quando disponíveis.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

MEDIA_CACHE_NAME = "fivemanage_uploads_v1.json"


def _load_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ V173: não foi possível ler {path.name}: {exc}", flush=True)
        return None


def _as_records(value: Any, kind: str) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get(kind, value.get("records", []))
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _media_map(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in data.values():
        if not isinstance(item, dict) or not item.get("url"):
            continue
        message_id = item.get("message_id")
        attachment_id = item.get("attachment_id")
        result[f"{message_id}:{attachment_id}"] = item
        if message_id:
            result[f"msg:{message_id}"] = item
        if attachment_id:
            result[f"att:{attachment_id}"] = item
    return result


def _enrich_record(record: Dict[str, Any], media: dict[str, dict[str, Any]]) -> Dict[str, Any]:
    out = dict(record)
    message_id = record.get("message_id") or record.get("mensagem_id") or record.get("mensagem_original_id")
    direct = media.get(f"msg:{message_id}") if message_id else None
    if direct and direct.get("url"):
        out.setdefault("external_url", direct["url"])
        out.setdefault("fivemanage_url", direct["url"])

    for collection_key in ("attachments", "anexos", "arquivos", "fotos", "evidencias", "evidências"):
        collection = out.get(collection_key)
        if not isinstance(collection, list):
            continue
        enriched = []
        for entry in collection:
            if not isinstance(entry, dict):
                enriched.append(entry)
                continue
            item = dict(entry)
            aid = item.get("attachment_id") or item.get("id")
            mid = item.get("message_id") or message_id
            hit = media.get(f"{mid}:{aid}") if mid and aid else None
            hit = hit or (media.get(f"att:{aid}") if aid else None)
            if hit and hit.get("url"):
                item.setdefault("external_url", hit["url"])
                item.setdefault("fivemanage_url", hit["url"])
            enriched.append(item)
        out[collection_key] = enriched
    return out


def install(bot_module) -> None:
    try:
        state = getattr(bot_module, "_v172_central_state", None)
        if not isinstance(state, dict):
            print("ℹ️ V173: estado V172 ainda indisponível; Central segue com fallback.", flush=True)
            return

        data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
        archive = _load_json(data_dir / "central_discord_archive.json") or {}
        cache = _load_json(data_dir / "central_dados_v172.json") or {}
        media = _media_map(_load_json(data_dir / MEDIA_CACHE_NAME) or {})

        for kind in ("procurados", "boletins", "pericias"):
            current = _as_records(state.get(kind, []), kind)
            cached = _as_records(cache.get(kind, []), kind)
            historical = _as_records(archive.get(kind, []), kind)
            merged: List[Dict[str, Any]] = []
            seen = set()
            for item in current + cached + historical:
                item = _enrich_record(item, media)
                key = str(item.get("message_id") or item.get("id") or item.get("mensagem_url") or "")
                if not key:
                    key = repr(sorted(item.items()))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
            state[kind] = merged

        bot_module._v43_procurados_ativos = lambda: list(state.get("procurados", []))
        bot_module._v44_boletins_ativos_snapshot = lambda: list(state.get("boletins", []))
        bot_module._v173_central_data_state = state
        bot_module._v173_resolver_midia = lambda registro: (
            registro.get("external_url") or registro.get("fivemanage_url") or registro.get("arquivo_local_url") or registro.get("discord_url")
            if isinstance(registro, dict) else None
        )
        print(
            "✅ V173: dados conectados à Central oficial "
            f"(procurados={len(state.get('procurados', []))}, "
            f"boletins={len(state.get('boletins', []))}, "
            f"pericias={len(state.get('pericias', []))}, mídia={len(media)}).",
            flush=True,
        )
    except Exception as exc:
        print(f"⚠️ V173 desativado por segurança: {exc}", flush=True)
