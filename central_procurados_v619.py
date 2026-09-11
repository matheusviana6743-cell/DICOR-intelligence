# -*- coding: utf-8 -*-
"""Central DICOR V619 - correção de estabilidade da V618.

Mantém o layout da V617/V618, mas corrige dois pontos que podiam derrubar o
processo: a coleta não entra mais em recursão e install() devolve o objeto
Central com .start(), como a Central original.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import central_procurados_v617 as v617
import central_discord_v613 as base

SCAN_LIMIT = 1000
base.web.URLEncode = quote
base.quote = quote


def clean(v: Any) -> str:
    s = str(v or "")
    s = re.sub(r"[*_~`]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" |•-—:;\t\r\n")


def text_of(m: Any) -> str:
    parts = [getattr(m, "content", "") or ""]
    for e in getattr(m, "embeds", []) or []:
        parts.extend([getattr(e, "title", "") or "", getattr(e, "description", "") or ""])
        for f in getattr(e, "fields", []) or []:
            parts.append(f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}")
    return clean(" ".join(x for x in parts if x))


def image_url(m: Any) -> str:
    for e in getattr(m, "embeds", []) or []:
        image = getattr(e, "image", None)
        url = getattr(image, "url", "") if image else ""
        if url:
            return url
        thumb = getattr(e, "thumbnail", None)
        url = getattr(thumb, "url", "") if thumb else ""
        if url:
            return url
        author = getattr(e, "author", None)
        icon = getattr(author, "icon_url", "") if author else ""
        if icon:
            return icon
    for a in getattr(m, "attachments", []) or []:
        url = getattr(a, "url", "")
        if url:
            return url
    return ""


def extract_label(text: str, labels: tuple[str, ...], default: str = "Não informado") -> str:
    label = "|".join(re.escape(x) for x in labels)
    m = re.search(rf"(?:{label})\s*[:=-]\s*([^|•\n]+)", text, re.I)
    return clean(m.group(1))[:180] if m else default


def normalize_name(value: Any) -> str:
    s = clean(value)
    s = re.sub(r"^(?:nome\s*(?:completo)?|indiv[ií]duo|procurado)\s*[:=-]\s*", "", s, flags=re.I)
    s = re.sub(r"^(?:n[ºo]|registro)\s*[:#-]?\s*\d+\s*[-|•:]\s*", "", s, flags=re.I)
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    return s[:90] or "Indivíduo não identificado"


def is_closed(text: str) -> bool:
    s = clean(text).casefold()
    return any(x in s for x in ("capturado", "capturada", "preso", "presa", "encerrado", "encerrada", "cancelado", "cancelada", "finalizado", "finalizada"))


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channel = await base.get_channel(client, base.PROCURADOS_ID)
    if channel is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        async for m in channel.history(limit=SCAN_LIMIT, oldest_first=False):
            text = text_of(m)
            if not text or is_closed(text):
                continue
            created = getattr(m, "created_at", None) or datetime.now(timezone.utc)
            rows.append({
                "number": base.number_from(text),
                "name": normalize_name(extract_label(text, ("nome completo", "nome", "indivíduo", "individuo", "procurado"), "Indivíduo não identificado")),
                "rg": extract_label(text, ("rg", "registro geral", "passaporte", "identidade", "id")),
                "crime": extract_label(text, ("crimes", "crime", "acusação", "acusacao")),
                "status": extract_label(text, ("status", "situação", "situacao"), "ATIVO"),
                "created": created,
                "url": getattr(m, "jump_url", "#"),
                "image": image_url(m),
                "preview": text[:500],
                "source_id": getattr(m, "id", 0),
            })
    except Exception as exc:
        print(f"⚠️ Central V619 Procurados: {type(exc).__name__}: {exc}", flush=True)
        return []
    unique: dict[int | str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("source_id") or row.get("url") or f"{row.get('name')}|{row.get('rg')}"
        unique[key] = row
    return sorted(unique.values(), key=lambda r: r.get("created") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


# Substitui os coletores mutados pela V617 e mantém o dashboard/detalhes já aprovados.
base.collect_procurados = collect_procurados
v617.collect_procurados = collect_procurados
v617.v616.collect_procurados = collect_procurados
base.dashboard = v617.dashboard_v617
v617.v616.dashboard = v617.dashboard_v617

# start_server_v617 já registra a página individual e usa o servidor V616.
# O helper URLEncode acima corrige a autenticação da V616.
base.start_server = v617.start_server_v617


def install(bot_module: Any):
    """Contrato igual ao CentralV613: retorna objeto com .start()."""
    return base.install(bot_module)
