# -*- coding: utf-8 -*-
"""Ponte de mídia: Discord -> Fivemanage, com fallback local e dedupe."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

UPLOAD_URL = "https://api.fivemanage.com/api/v3/file"
API_KEY = os.getenv("FIVEMANAGE_API_KEY", "").strip()
TIMEOUT = max(5, int(os.getenv("FIVEMANAGE_TIMEOUT_SECONDS", "20") or 20))
MAX_BYTES = max(1, int(os.getenv("FIVEMANAGE_MAX_BYTES", str(25 * 1024 * 1024)) or 25 * 1024 * 1024))
CONCURRENCY = max(1, min(4, int(os.getenv("FIVEMANAGE_CONCURRENCY", "2") or 2)))
CACHE_NAME = "fivemanage_uploads_v1.json"
LOCAL_DIR = "fivemanage_backup_local"
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _safe_name(name: Any) -> str:
    text = Path(str(name or "arquivo")).name
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "arquivo"
    return text[:140]


def _cache_path(bot_module: Any) -> Path:
    return Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data"))) / CACHE_NAME


def _load_cache(bot_module: Any) -> dict[str, dict[str, Any]]:
    path = _cache_path(bot_module)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(bot_module: Any, data: dict[str, dict[str, Any]]) -> None:
    path = _cache_path(bot_module)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        print(f"⚠️ [MEDIA] não foi possível salvar índice: {type(exc).__name__}: {exc}", flush=True)


def _is_image(attachment: Any) -> bool:
    content_type = str(getattr(attachment, "content_type", "") or "").lower()
    filename = str(getattr(attachment, "filename", "") or "")
    return content_type.startswith("image/") or Path(filename).suffix.lower() in _ALLOWED_EXT


def _local_path(bot_module: Any, attachment: Any, data: bytes) -> Optional[str]:
    try:
        base = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data"))) / LOCAL_DIR
        base.mkdir(parents=True, exist_ok=True)
        aid = str(getattr(attachment, "id", "anexo"))
        target = base / f"{aid}_{_safe_name(getattr(attachment, 'filename', 'arquivo'))}"
        target.write_bytes(data)
        return str(target)
    except Exception:
        return None


def _key(message_id: Any, attachment_id: Any) -> str:
    return f"{message_id}:{attachment_id}"


async def upload_attachment(bot_module: Any, attachment: Any, *, message_id: Any = None, channel_id: Any = None, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Upload seguro. Nunca propaga exceções para o chamador."""
    result = {
        "external_url": None,
        "discord_url": getattr(attachment, "url", None),
        "arquivo_local": None,
        "message_id": str(message_id or ""),
        "attachment_id": str(getattr(attachment, "id", "") or ""),
        "channel_id": str(channel_id or ""),
        "filename": str(getattr(attachment, "filename", "") or "arquivo"),
        "erro": None,
    }
    key = _key(message_id, getattr(attachment, "id", None))
    cache = _load_cache(bot_module)
    cached = cache.get(key)
    if isinstance(cached, dict) and cached.get("url"):
        result["external_url"] = cached["url"]
        result["arquivo_local"] = cached.get("arquivo_local")
        return result

    try:
        data = await asyncio.wait_for(attachment.read(), timeout=TIMEOUT)
    except Exception as exc:
        result["erro"] = f"download Discord falhou: {type(exc).__name__}: {exc}"
        return result

    if len(data) > MAX_BYTES:
        result["arquivo_local"] = _local_path(bot_module, attachment, data)
        result["erro"] = f"arquivo excede {MAX_BYTES} bytes"
        return result

    result["arquivo_local"] = _local_path(bot_module, attachment, data)
    if not API_KEY:
        result["erro"] = "FIVEMANAGE_API_KEY não configurada"
        return result

    try:
        import aiohttp
        form = aiohttp.FormData()
        form.add_field("file", data, filename=_safe_name(getattr(attachment, "filename", "arquivo")), content_type=str(getattr(attachment, "content_type", None) or "application/octet-stream"))
        if metadata:
            form.add_field("metadata", json.dumps(metadata, ensure_ascii=False))
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(UPLOAD_URL, data=form, headers={"Authorization": API_KEY}) as resp:
                try:
                    body = await resp.json(content_type=None)
                except Exception:
                    body = {}
                if resp.status != 200 or not isinstance(body, dict) or body.get("status") != "ok":
                    result["erro"] = f"Fivemanage HTTP {resp.status}: {body.get('error', '') if isinstance(body, dict) else body}"
                    return result
                url = str(((body.get("data") or {}).get("url")) or "").strip()
                if not url:
                    result["erro"] = "Fivemanage respondeu sem URL"
                    return result
                result["external_url"] = url
                cache[key] = {
                    "url": url,
                    "arquivo_local": result["arquivo_local"],
                    "message_id": result["message_id"],
                    "attachment_id": result["attachment_id"],
                    "channel_id": result["channel_id"],
                    "filename": result["filename"],
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "metadata": metadata or {},
                }
                _save_cache(bot_module, cache)
                return result
    except Exception as exc:
        result["erro"] = f"Fivemanage indisponível: {type(exc).__name__}: {exc}"
        return result


def resolver_midia(registro: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(registro, dict):
        return None
    return registro.get("external_url") or registro.get("fivemanage_url") or registro.get("arquivo_local_url") or registro.get("discord_url")


async def install(bot_module: Any) -> None:
    bot = getattr(bot_module, "bot", None)
    if bot is None or getattr(bot_module, "_DICOR_FIVEMANAGE_INSTALLED", False):
        return
    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(message: Any) -> None:
        if getattr(message.author, "bot", False):
            return
        channel = getattr(message, "channel", None)
        name = str(getattr(channel, "name", "") or "").lower()
        relevant_words = ("procurad", "boletim", "pericia", "perícia", "ficha", "evid", "mesa", "investig")
        allowed_env = {x.strip() for x in os.getenv("DICOR_MEDIA_CHANNEL_IDS", "").replace(";", ",").split(",") if x.strip().isdigit()}
        channel_id = str(getattr(channel, "id", "") or "")
        relevant = channel_id in allowed_env or any(word in name for word in relevant_words)
        if not relevant:
            return
        for attachment in list(getattr(message, "attachments", []) or []):
            if not _is_image(attachment):
                continue
            async with sem:
                result = await upload_attachment(
                    bot_module,
                    attachment,
                    message_id=getattr(message, "id", None),
                    channel_id=channel_id,
                    metadata={"guild_id": str(getattr(getattr(message, "guild", None), "id", "") or ""), "channel_name": name},
                )
            if result.get("external_url"):
                print(f"✅ [MEDIA] {result['filename']} -> Fivemanage", flush=True)
            elif result.get("erro"):
                print(f"⚠️ [MEDIA] {result['filename']}: {result['erro']}", flush=True)

    async def on_message(message: Any) -> None:
        try:
            await worker(message)
        except Exception as exc:
            print(f"⚠️ [MEDIA] listener isolado: {type(exc).__name__}: {exc}", flush=True)

    bot.add_listener(on_message, "on_message")
    bot_module.enviar_para_fivemanage_v1 = upload_attachment
    bot_module.resolver_midia_v1 = resolver_midia
    bot_module._DICOR_FIVEMANAGE_INSTALLED = True
    print("✅ [MEDIA] backup permanente de imagens ativo", flush=True)
