# -*- coding: utf-8 -*-
"""V172 — ponte leve de dados da Central.

Este módulo NÃO cria páginas nem substitui o layout oficial V163.
Discord é a fonte de dados; V163 continua responsável pela interface.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROCURADOS_ID = 1490200533980545097


def install(bot_module) -> None:
    client = bot_module.bot
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_path = data_dir / "central_dados_v172.json"

    state: Dict[str, Any] = {
        "procurados": [],
        "boletins": [],
        "pericias": [],
        "updated": 0,
        "task": None,
        "syncing": False,
        "ready": False,
    }

    def norm(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", text)
        return " ".join(text.split())

    def first(record: Dict[str, Any], keys: Iterable[str], default: str = "Não informado") -> str:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return str(value)
        return default

    def blob(message: Any) -> str:
        parts: List[str] = []
        content = str(getattr(message, "content", "") or "").strip()
        if content:
            parts.append(content)
        for embed in list(getattr(message, "embeds", []) or []):
            title = str(getattr(embed, "title", "") or "").strip()
            description = str(getattr(embed, "description", "") or "").strip()
            if title:
                parts.append(title)
            if description:
                parts.append(description)
            for field in list(getattr(embed, "fields", []) or []):
                name = str(getattr(field, "name", "") or "").strip()
                value = str(getattr(field, "value", "") or "").strip()
                if name or value:
                    parts.append(f"{name}: {value}" if name else value)
        return "\n".join(parts).strip()

    def field(text: str, aliases: Iterable[str]) -> str:
        wanted = {norm(x) for x in aliases}
        for line in str(text or "").splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            if norm(name.strip(" *_`~•-")) in wanted and value.strip():
                return value.strip(" *_`~•-")
        return ""

    def images(message: Any) -> List[str]:
        out: List[str] = []
        for attachment in list(getattr(message, "attachments", []) or []):
            url = str(getattr(attachment, "url", "") or "").strip()
            filename = str(getattr(attachment, "filename", "") or "").lower()
            content_type = str(getattr(attachment, "content_type", "") or "").lower()
            if url and (content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))):
                if url not in out:
                    out.append(url)
        for embed in list(getattr(message, "embeds", []) or []):
            for attr in ("image", "thumbnail"):
                obj = getattr(embed, attr, None)
                url = str(getattr(obj, "url", "") or "").strip() if obj else ""
                if url and url not in out:
                    out.append(url)
        return out

    def parse_message(message: Any, kind: str) -> Dict[str, Any]:
        text = blob(message)
        author = getattr(message, "author", None)
        created = getattr(message, "created_at", None)
        return {
            "tipo": kind,
            "mensagem_id": int(getattr(message, "id", 0) or 0),
            "mensagem_url": str(getattr(message, "jump_url", "") or ""),
            "nome": field(text, ("nome", "nome completo", "indivíduo", "individuo", "suspeito", "envolvido", "solicitante")) or str(getattr(author, "display_name", "") or "Não informado"),
            "rg": field(text, ("rg", "passaporte", "rg/passaporte", "registro geral", "id")),
            "crime": field(text, ("crime", "crimes", "acusação", "acusacao", "infração", "infracao")),
            "descricao": field(text, ("descrição", "descricao", "detalhes", "observações", "observacoes", "resumo")),
            "local": field(text, ("local", "localização", "localizacao", "último avistamento", "ultimo avistamento", "endereço", "endereco")),
            "numero_boletim": field(text, ("boletim", "número do boletim", "numero do boletim", "protocolo", "bo", "nº")),
            "texto_discord": text,
            "fotos": images(message),
            "autor": str(getattr(author, "display_name", "") or "Não informado"),
            "autor_id": int(getattr(author, "id", 0) or 0),
            "data": created.isoformat() if hasattr(created, "isoformat") else "",
        }

    async def resolve(channel_id: int):
        if not channel_id:
            return None
        channel = client.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await client.fetch_channel(channel_id)
        except Exception:
            return None

    def candidate_channels(kind: str) -> List[int]:
        attrs = {
            "boletins": ("BOLETINS_CHANNEL_ID", "BOLETIM_CHANNEL_ID", "BOLETINS_ATIVOS_CHANNEL_ID", "BOLETIM_ATENDIMENTO_CHANNEL_ID"),
            "pericias": ("PERICIAS_CHANNEL_ID", "PERICIA_FLUXO_CHANNEL_ID", "BANCO_PERICIA_CHANNEL_ID", "PERICIA_CHANNEL_ID"),
        }[kind]
        terms = {
            "boletins": ("boletim", "ocorrencia", "ocorrência", "relatorio", "relatório"),
            "pericias": ("pericia", "perícia", "laudo", "evidencia", "evidência", "forense"),
        }[kind]
        ids = set()
        for attr in attrs:
            try:
                value = int(getattr(bot_module, attr, 0) or 0)
                if value:
                    ids.add(value)
            except Exception:
                pass
        for guild in list(getattr(client, "guilds", []) or []):
            for channel in list(getattr(guild, "channels", []) or []):
                name = norm(getattr(channel, "name", ""))
                if any(term in name for term in terms):
                    try:
                        ids.add(int(channel.id))
                    except Exception:
                        pass
        return list(ids)[:12]

    async def scan(channel: Any, kind: str, limit: int = 150) -> List[Dict[str, Any]]:
        if channel is None or not hasattr(channel, "history"):
            return []
        result: List[Dict[str, Any]] = []
        seen = set()
        try:
            async for message in channel.history(limit=limit, oldest_first=False):
                mid = int(getattr(message, "id", 0) or 0)
                if mid in seen:
                    continue
                if not (getattr(message, "content", "") or getattr(message, "embeds", None) or getattr(message, "attachments", None)):
                    continue
                result.append(parse_message(message, kind))
                seen.add(mid)
        except Exception as exc:
            print(f"⚠️ V172 {kind}: {type(exc).__name__}: {exc}", flush=True)
        return result

    def merge(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            key = str(record.get("mensagem_id") or record.get("id") or hash(record.get("texto_discord", "")))
            old = unique.get(key)
            if old is None:
                unique[key] = dict(record)
            else:
                old.update({k: v for k, v in record.items() if v not in (None, "", [], "Não informado")})
        return list(unique.values())[:500]

    async def sync() -> None:
        if state["syncing"]:
            return
        state["syncing"] = True
        try:
            # Procurados: V171 já faz a sincronização completa do Discord.
            existing_wanted = getattr(bot_module, "_v43_procurados_ativos", None)
            wanted = list(existing_wanted() or []) if callable(existing_wanted) else list(state["procurados"])

            boletins: List[Dict[str, Any]] = []
            official_boletins = getattr(bot_module, "_v44_boletins_ativos_snapshot", None)
            if callable(official_boletins):
                try:
                    boletins.extend(dict(x) for x in (official_boletins() or []) if isinstance(x, dict))
                except Exception:
                    pass
            for channel_id in candidate_channels("boletins"):
                boletins.extend(await scan(await resolve(channel_id), "boletim"))

            pericias: List[Dict[str, Any]] = []
            for channel_id in candidate_channels("pericias"):
                pericias.extend(await scan(await resolve(channel_id), "pericia"))

            state["procurados"] = merge(wanted)
            state["boletins"] = merge(boletins)
            state["pericias"] = merge(pericias)
            state["updated"] = int(time.time())
            state["ready"] = True
            payload = {k: v for k, v in state.items() if k not in ("task", "syncing")}
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(cache_path)
            print(f"✅ V172 dados: {len(state['procurados'])} procurados, {len(state['boletins'])} boletins, {len(state['pericias'])} perícias.", flush=True)
        except Exception as exc:
            print(f"⚠️ V172 sync protegido: {type(exc).__name__}: {exc}", flush=True)
        finally:
            state["syncing"] = False

    def load_cache() -> None:
        try:
            if not cache_path.exists():
                return
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            for key in ("procurados", "boletins", "pericias"):
                if isinstance(raw.get(key), list):
                    state[key] = raw[key]
            state["updated"] = int(raw.get("updated") or 0)
        except Exception:
            pass

    async def periodic() -> None:
        while True:
            await asyncio.sleep(90)
            await sync()

    async def on_message(message: Any) -> None:
        channel = getattr(message, "channel", None)
        channel_id = int(getattr(channel, "id", 0) or 0)
        name = norm(getattr(channel, "name", ""))
        if channel_id == PROCURADOS_ID or any(term in name for term in ("boletim", "pericia", "perícia", "laudo")):
            asyncio.create_task(sync())

    load_cache()
    bot_module._v172_central_state = state
    bot_module._v172_sync_central = sync

    if hasattr(client, "add_listener"):
        client.add_listener(on_message, "on_message")

    # O instalador roda depois do READY; portanto dispara a primeira carga imediatamente.
    try:
        state["task"] = asyncio.create_task(periodic())
        asyncio.create_task(sync())
    except Exception as exc:
        print(f"⚠️ V172: tarefas de sincronização não iniciadas: {type(exc).__name__}: {exc}", flush=True)

    print("✅ V172 Data Bridge instalado — layout V163 preservado.", flush=True)
