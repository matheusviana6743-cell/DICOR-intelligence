# -*- coding: utf-8 -*-
"""V171 — sincronização leve Discord -> Procurados -> Central DICOR.

A sincronização é limitada para não consumir toda a memória do Railway.
O Discord continua sendo a fonte de verdade; o snapshot local mantém os
registros já conhecidos entre reinícios.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List

ACTIVE_WANTED_CHANNEL_ID = 1490200533980545097
# Limite deliberadamente baixo: evita OOM em canais muito grandes.
SYNC_LIMIT = 150
SYNC_INTERVAL = 120


def install(bot_module) -> None:
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = data_dir / "procurados_discord.json"

    state = {"message_ids": set(), "records": {}, "ready": False, "sync_task": None, "loop_task": None, "last_error": ""}

    def _load_snapshot() -> None:
        try:
            if not snapshot_path.exists(): return
            raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
            registros = raw.get("records", raw) if isinstance(raw, dict) else raw
            if isinstance(registros, list):
                registros = {str(r.get("mensagem_id")): r for r in registros if isinstance(r, dict) and r.get("mensagem_id")}
            if isinstance(registros, dict):
                state["records"] = {str(k): v for k, v in registros.items() if isinstance(v, dict)}
                state["message_ids"] = {int(k) for k in state["records"] if str(k).isdigit()}
        except Exception as exc:
            state["last_error"] = f"snapshot: {type(exc).__name__}: {exc}"
            print(f"⚠️ V171: snapshot não carregado: {exc}", flush=True)

    def _save_snapshot() -> None:
        try:
            tmp = snapshot_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": 171, "records": state["records"]}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(snapshot_path)
        except Exception as exc:
            print(f"⚠️ V171: falha ao salvar snapshot: {exc}", flush=True)

    def _extract_fields(message) -> Dict[str, Any]:
        text = str(getattr(message, "content", "") or "").strip()
        embeds = getattr(message, "embeds", []) or []
        parts = [text]
        for embed in embeds:
            title = str(getattr(embed, "title", "") or "").strip()
            desc = str(getattr(embed, "description", "") or "").strip()
            if title: parts.append(title)
            if desc: parts.append(desc)
            for field in getattr(embed, "fields", []) or []:
                n = str(getattr(field, "name", "") or "").strip()
                v = str(getattr(field, "value", "") or "").strip()
                if n or v: parts.append(f"{n}: {v}".strip(": "))
        blob = "\n".join(x for x in parts if x)

        def pick(*names):
            for name in names:
                m = re.search(rf"(?im)^\s*{re.escape(name)}\s*[:\-]\s*(.+?)\s*$", blob)
                if m: return m.group(1).strip()
            return ""

        fotos = []
        for a in getattr(message, "attachments", []) or []:
            url = str(getattr(a, "url", "") or "")
            if url: fotos.append(url)
        for embed in embeds:
            image = getattr(embed, "image", None)
            url = str(getattr(image, "url", "") or "") if image else ""
            if url: fotos.append(url)

        author = getattr(message, "author", None)
        created = getattr(message, "created_at", None)
        return {
            "mensagem_id": int(message.id),
            "mensagem_url": str(getattr(message, "jump_url", "") or ""),
            "nome": pick("nome", "nome completo", "indivíduo", "individuo") or str(getattr(author, "display_name", "") or "") or "Não informado",
            "rg": pick("rg", "passaporte", "id"),
            "descricao": pick("descrição", "descricao"),
            "crime": pick("crime", "crimes", "acusação", "acusacao"),
            "texto_discord": blob,
            "fotos": list(dict.fromkeys(fotos))[:4],
            "autor_id": int(getattr(author, "id", 0) or 0),
            "data_discord": created.isoformat() if created else "",
        }

    async def _resolve_channel():
        client = getattr(bot_module, "bot", None)
        if client is None: return None
        channel = client.get_channel(ACTIVE_WANTED_CHANNEL_ID)
        if channel is not None: return channel
        try: return await client.fetch_channel(ACTIVE_WANTED_CHANNEL_ID)
        except Exception as exc:
            state["last_error"] = f"canal: {type(exc).__name__}: {exc}"
            return None

    async def _sync_full(reason=""):
        channel = await _resolve_channel()
        if channel is None or not hasattr(channel, "history"):
            state["last_error"] = "canal_indisponivel"
            return
        try:
            fresh = {}
            # Somente as publicações mais recentes. Nunca usar limit=None.
            async for message in channel.history(limit=SYNC_LIMIT, oldest_first=False):
                if not (getattr(message, "content", "") or getattr(message, "embeds", None) or getattr(message, "attachments", None)):
                    continue
                registro = _extract_fields(message)
                fresh[str(message.id)] = registro

            # Mantém registros antigos do snapshot, mas limita o total em memória.
            old = state["records"]
            merged = dict(old)
            merged.update(fresh)
            if len(merged) > 500:
                ordered = sorted(merged.values(), key=lambda r: int(r.get("mensagem_id", 0) or 0), reverse=True)[:500]
                merged = {str(r.get("mensagem_id")): r for r in ordered if r.get("mensagem_id")}

            state["records"] = merged
            state["message_ids"] = {int(k) for k in merged if k.isdigit()}
            state["ready"] = True
            state["last_error"] = ""
            _save_snapshot()
            _invalidate_cache()
            print(f"✅ V171 Procurados: {len(fresh)} lidos / {len(merged)} mantidos ({reason}).", flush=True)
        except Exception as exc:
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"⚠️ V171 Procurados: sincronização falhou: {type(exc).__name__}: {exc}", flush=True)

    def _invalidate_cache():
        try: bot_module._V17_CATALOGO_CACHE_HTML = ""
        except Exception: pass
        try: bot_module._V17_CATALOGO_CACHE_KEY = None
        except Exception: pass

    def _records() -> List[Dict[str, Any]]: return list(state["records"].values())
    async def _refresh(reason):
        task = state.get("sync_task")
        if task is not None and not task.done(): return
        async def run():
            await asyncio.sleep(0.5)
            await _sync_full(reason)
        state["sync_task"] = asyncio.create_task(run())

    async def _on_ready():
        _load_snapshot()
        _invalidate_cache()
        await _sync_full("on_ready")
        if state.get("loop_task") is None or state["loop_task"].done():
            state["loop_task"] = asyncio.create_task(_loop())

    async def _on_message(message):
        try:
            if int(getattr(getattr(message, "channel", None), "id", 0) or 0) == ACTIVE_WANTED_CHANNEL_ID:
                await _refresh("nova publicação")
        except Exception: pass

    async def _on_raw_message_delete(payload):
        if int(getattr(payload, "channel_id", 0) or 0) == ACTIVE_WANTED_CHANNEL_ID:
            await _refresh("mensagem removida")

    async def _loop():
        while True:
            try:
                await asyncio.sleep(SYNC_INTERVAL)
                await _sync_full("sincronização periódica")
            except asyncio.CancelledError: raise
            except Exception as exc:
                print(f"⚠️ V171 loop: {exc}", flush=True)

    def _active_records(): return _records()
    def _is_active(registro):
        try: return int(registro.get("mensagem_id") or 0) in state["message_ids"]
        except Exception: return False

    bot_module.PROCURADOS_CHANNEL_ID = ACTIVE_WANTED_CHANNEL_ID
    bot_module._v43_procurados_ativos = _active_records
    bot_module._v43_procurado_esta_no_canal_ativo = _is_active
    bot_module._V162_PROCURADOS_STATE = state
    bot_module._v162_refresh_procurados_ativos = _sync_full
    bot_module._v171_snapshot_path = str(snapshot_path)

    client = getattr(bot_module, "bot", None)
    if client is not None and hasattr(client, "add_listener"):
        client.add_listener(_on_ready, "on_ready")
        client.add_listener(_on_message, "on_message")
        client.add_listener(_on_raw_message_delete, "on_raw_message_delete")

    _load_snapshot()
    print(f"✅ V171 Procurados: sincronização limitada a {SYNC_LIMIT} mensagens; intervalo {SYNC_INTERVAL}s.", flush=True)
