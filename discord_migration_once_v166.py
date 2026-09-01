# -*- coding: utf-8 -*-
"""Migração única e não destrutiva dos históricos do Discord para o /data novo.

A migração procura automaticamente canais de Procurados, Boletins e Perícias,
exporta mensagens/embeds e baixa os anexos para o volume persistente. Ela só
marca a execução como concluída depois de salvar todo o arquivo de controle.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE_NAME = "discord_migration_once.json"
ARCHIVE_NAME = "central_discord_archive.json"
MEDIA_DIR_NAME = "central_discord_media"


def _data_dir() -> Path:
    configured = os.getenv("DICOR_DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    railway_data = Path("/data")
    if railway_data.exists():
        return railway_data
    return Path("data")


def _norm(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", text)
    return " ".join(text.split())


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _channel_kind(channel) -> Optional[str]:
    name = _norm(getattr(channel, "name", ""))
    channel_id = str(getattr(channel, "id", "") or "")

    explicit = {
        "procurados": os.getenv("DICOR_MIGRATION_PROCURADOS_CHANNEL_ID", "").strip(),
        "boletins": os.getenv("DICOR_MIGRATION_BOLETINS_CHANNEL_ID", "").strip(),
        "pericias": os.getenv("DICOR_MIGRATION_PERICIAS_CHANNEL_ID", "").strip(),
    }
    for kind, value in explicit.items():
        if value and value == channel_id:
            return kind

    if "procurado" in name:
        return "procurados"
    if "boletim" in name:
        return "boletins"
    if "pericia" in name or "perícias" in name or "perícia" in name:
        return "pericias"
    return None


def _embed_dict(embed) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for attr in ("title", "description", "url"):
        value = getattr(embed, attr, None)
        if value:
            result[attr] = str(value)

    fields = []
    for field in list(getattr(embed, "fields", []) or []):
        fields.append({
            "name": str(getattr(field, "name", "") or ""),
            "value": str(getattr(field, "value", "") or ""),
            "inline": bool(getattr(field, "inline", False)),
        })
    if fields:
        result["fields"] = fields

    for parent in ("image", "thumbnail", "author", "footer"):
        obj = getattr(embed, parent, None)
        if obj is None:
            continue
        item = {}
        for attr in ("url", "name", "text", "icon_url"):
            value = getattr(obj, attr, None)
            if value:
                item[attr] = str(value)
        if item:
            result[parent] = item

    timestamp = getattr(embed, "timestamp", None)
    if timestamp:
        result["timestamp"] = timestamp.isoformat()
    return result


def install(bot_module) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None or not hasattr(client, "add_listener"):
        print("⚠️ V166: cliente Discord indisponível; migração não instalada.", flush=True)
        return

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / STATE_NAME
    archive_path = data_dir / ARCHIVE_NAME
    media_dir = data_dir / MEDIA_DIR_NAME
    media_dir.mkdir(parents=True, exist_ok=True)
    running = False

    async def save_attachment(attachment, message_id: int, index: int) -> Dict[str, Any]:
        filename = str(getattr(attachment, "filename", "arquivo") or "arquivo")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "arquivo"
        source_url = str(getattr(attachment, "url", "") or "")
        digest = hashlib.sha256(f"{message_id}:{index}:{source_url}:{safe_name}".encode()).hexdigest()[:16]
        target = media_dir / f"{message_id}_{digest}_{safe_name}"

        if not target.exists():
            try:
                target.write_bytes(await attachment.read())
            except Exception as exc:
                return {
                    "filename": filename,
                    "source_url": source_url,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        return {
            "filename": filename,
            "source_url": source_url,
            "local_path": str(target.relative_to(data_dir)).replace("\\", "/"),
            "content_type": str(getattr(attachment, "content_type", "") or ""),
            "size": int(getattr(attachment, "size", 0) or 0),
        }

    async def serialize_message(message, kind: str) -> Dict[str, Any]:
        attachments = []
        for index, attachment in enumerate(list(getattr(message, "attachments", []) or [])):
            attachments.append(await save_attachment(attachment, int(message.id), index))

        author = getattr(message, "author", None)
        created_at = getattr(message, "created_at", None)
        return {
            "kind": kind,
            "message_id": int(message.id),
            "channel_id": int(getattr(getattr(message, "channel", None), "id", 0) or 0),
            "channel_name": str(getattr(getattr(message, "channel", None), "name", "") or ""),
            "guild_id": int(getattr(getattr(message, "guild", None), "id", 0) or 0),
            "author_id": int(getattr(author, "id", 0) or 0),
            "author_name": str(getattr(author, "display_name", "") or getattr(author, "name", "") or ""),
            "created_at": created_at.isoformat() if created_at else "",
            "content": str(getattr(message, "content", "") or ""),
            "jump_url": str(getattr(message, "jump_url", "") or ""),
            "embeds": [_embed_dict(embed) for embed in list(getattr(message, "embeds", []) or [])],
            "attachments": attachments,
        }

    def candidate_channels() -> List[Tuple[str, Any]]:
        found: Dict[Tuple[str, int], Any] = {}
        for guild in list(getattr(client, "guilds", []) or []):
            for channel in list(getattr(guild, "channels", []) or []):
                kind = _channel_kind(channel)
                if kind:
                    found[(kind, int(channel.id))] = channel
        return sorted(found.values(), key=lambda c: (_channel_kind(c) or "", int(c.id)))

    async def scan_channel(channel, kind: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if not hasattr(channel, "history"):
            return records
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                records.append(await serialize_message(message, kind))
        except Exception as exc:
            print(
                f"⚠️ V166: não foi possível ler #{getattr(channel, 'name', '?')}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
        return records

    async def run_once() -> None:
        nonlocal running
        if running:
            return
        running = True
        try:
            state = _read_json(state_path)
            if state.get("status") == "completed":
                print("ℹ️ V166: migração Discord já concluída; ignorando nova execução.", flush=True)
                return

            channels = candidate_channels()
            if not channels:
                print("⚠️ V166: nenhum canal de Procurados, Boletins ou Perícias encontrado. A migração ficará pendente.", flush=True)
                return

            old_archive = _read_json(archive_path)
            records_by_id: Dict[int, Dict[str, Any]] = {}
            for item in old_archive.get("records", []) if isinstance(old_archive, dict) else []:
                if isinstance(item, dict) and int(item.get("message_id", 0) or 0):
                    records_by_id[int(item["message_id"])] = item

            channel_summary = []
            for channel in channels:
                kind = _channel_kind(channel)
                if not kind:
                    continue
                records = await scan_channel(channel, kind)
                for record in records:
                    records_by_id[int(record["message_id"])] = record
                channel_summary.append({
                    "kind": kind,
                    "channel_id": int(channel.id),
                    "channel_name": str(channel.name),
                    "records_imported": len(records),
                })

            if not channel_summary:
                print("⚠️ V166: nenhum canal elegível pôde ser processado. A migração ficará pendente.", flush=True)
                return

            now = datetime.now(timezone.utc).isoformat()
            archive = {
                "version": 1,
                "purpose": "Migração única do histórico Discord para a Central DICOR",
                "started_at": old_archive.get("started_at", now),
                "completed_at": now,
                "channels": channel_summary,
                "records": sorted(records_by_id.values(), key=lambda x: str(x.get("created_at", ""))),
            }
            _atomic_json(archive_path, archive)
            _atomic_json(state_path, {
                "status": "completed",
                "completed_at": now,
                "records": len(archive["records"]),
                "channels": channel_summary,
                "archive": ARCHIVE_NAME,
                "media_directory": MEDIA_DIR_NAME,
            })
            print(
                f"✅ V166: migração concluída — {len(archive['records'])} mensagens e "
                f"anexos preservados no /data para a Central.",
                flush=True,
            )
        except Exception as exc:
            print(f"❌ V166: migração interrompida sem marcar como concluída: {type(exc).__name__}: {exc}", flush=True)
        finally:
            running = False

    async def on_ready():
        # Dá tempo para os módulos da Central terminarem a inicialização.
        await asyncio.sleep(10)
        await run_once()

    client.add_listener(on_ready, "on_ready")
    bot_module._dicor_discord_migration_run_once = run_once
    bot_module._dicor_discord_migration_archive = archive_path
    print("✅ V166: migração única Discord → Central instalada.", flush=True)
