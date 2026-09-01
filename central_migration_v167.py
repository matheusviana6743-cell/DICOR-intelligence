# -*- coding: utf-8 -*-
"""V167 - Integra os dados importados do Discord à Central DICOR.

Não reexecuta a migração. Apenas lê /data/central_discord_archive.json e usa
os registros já importados como fallback da Central quando os bancos antigos
estiverem vazios após a troca de volume.
"""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

ARCHIVE_NAME = "central_discord_archive.json"


def install(bot_module) -> None:
    web = getattr(bot_module, "web", None)
    if web is None:
        return

    data_dir = Path(str(getattr(bot_module, "DATA_DIR", "/data")))
    archive_path = data_dir / ARCHIVE_NAME

    def _esc(value: Any) -> str:
        return html.escape(str(value or ""), quote=True)

    def _norm(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", text)
        return " ".join(text.split())

    def _archive() -> Dict[str, Any]:
        try:
            raw = json.loads(archive_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _records(kind: str) -> List[Dict[str, Any]]:
        raw = _archive().get("records", [])
        return [x for x in raw if isinstance(x, dict) and str(x.get("kind")) == kind]

    def _embed_text(record: Dict[str, Any]) -> str:
        parts: List[str] = []
        for embed in record.get("embeds", []) if isinstance(record.get("embeds"), list) else []:
            if not isinstance(embed, dict):
                continue
            if embed.get("title"):
                parts.append(str(embed["title"]))
            if embed.get("description"):
                parts.append(str(embed["description"]))
            for field in embed.get("fields", []) if isinstance(embed.get("fields"), list) else []:
                if isinstance(field, dict):
                    name = str(field.get("name") or "").strip()
                    value = str(field.get("value") or "").strip()
                    if name and value:
                        parts.append(f"{name}: {value}")
                    elif value:
                        parts.append(value)
        content = str(record.get("content") or "").strip()
        if content:
            parts.insert(0, content)
        return "\n".join(x for x in parts if x).strip()

    def _first_field(record: Dict[str, Any], aliases: Iterable[str]) -> str:
        wanted = [_norm(x) for x in aliases]
        for embed in record.get("embeds", []) if isinstance(record.get("embeds"), list) else []:
            if not isinstance(embed, dict):
                continue
            for field in embed.get("fields", []) if isinstance(embed.get("fields"), list) else []:
                if not isinstance(field, dict):
                    continue
                name = _norm(field.get("name"))
                value = str(field.get("value") or "").strip()
                if value and any(alias in name or name in alias for alias in wanted):
                    return value
        text = str(record.get("content") or "")
        for line in text.splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            name_n = _norm(name)
            if value.strip() and any(alias in name_n or name_n in alias for alias in wanted):
                return value.strip()
        return ""

    def _images(record: Dict[str, Any]) -> List[str]:
        result: List[str] = []
        attachments = record.get("attachments", [])
        if isinstance(attachments, list):
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("source_url") or "").strip()
                filename = str(item.get("filename") or "").lower()
                if url and (item.get("content_type", "").startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))):
                    if url not in result:
                        result.append(url)
        for embed in record.get("embeds", []) if isinstance(record.get("embeds"), list) else []:
            if not isinstance(embed, dict):
                continue
            for key in ("image", "thumbnail"):
                obj = embed.get(key)
                if isinstance(obj, dict):
                    url = str(obj.get("url") or "").strip()
                    if url and url not in result:
                        result.append(url)
        return result

    def _migrated_procurados() -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for raw in _records("procurados"):
            item = dict(raw)
            item["message_id"] = int(raw.get("message_id") or 0)
            item["nome"] = _first_field(raw, ("nome", "nome completo", "individuo", "procurado")) or "Registro migrado do Discord"
            item["rg"] = _first_field(raw, ("rg", "passaporte", "registro geral"))
            item["crimes"] = _first_field(raw, ("crime", "crimes", "acusacao", "acusação", "infrações", "infracoes"))
            item["ultimo_avistamento"] = _first_field(raw, ("ultimo avistamento", "último avistamento", "localizacao", "localização", "local"))
            item["informacoes"] = _embed_text(raw)
            item["foto_url"] = (_images(raw) or [""])[0]
            item["fotos"] = _images(raw)
            item["mensagem_url"] = str(raw.get("jump_url") or "")
            output.append(item)
        return output

    original_wanted = getattr(bot_module, "_v43_procurados_ativos", None)

    def merged_wanted() -> List[Dict[str, Any]]:
        current: List[Dict[str, Any]] = []
        if callable(original_wanted):
            try:
                current = list(original_wanted() or [])
            except Exception:
                current = []
        if current:
            return current
        return _migrated_procurados()

    bot_module._v43_procurados_ativos = merged_wanted
    bot_module._dicor_migrated_archive = archive_path
    bot_module._dicor_migrated_records = _records

    def _page(title: str, subtitle: str, cards: str) -> str:
        return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(title)}</title><style>
body{{margin:0;background:#070706;color:#eee8d6;font-family:Inter,Segoe UI,Arial,sans-serif}}header{{padding:22px 5vw;border-bottom:1px solid #3c321a;background:#050504}}header b{{font-family:Georgia,serif;letter-spacing:2px}}main{{max-width:1200px;margin:auto;padding:42px 22px}}h1{{font-family:Georgia,serif;font-size:42px;margin:8px 0}}.gold{{color:#e4c95f}}.sub{{color:#aaa38e;line-height:1.6}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:30px}}.card{{border:1px solid #413619;border-radius:16px;background:linear-gradient(145deg,#13130f,#090907);padding:22px}}.card h2{{font-family:Georgia,serif;margin:0 0 10px;font-size:21px}}.meta{{color:#c9aa3d;font-size:11px;letter-spacing:1px;margin-bottom:12px}}.text{{white-space:pre-wrap;color:#b7b09c;line-height:1.6}}.pics{{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}}.pics img{{width:180px;height:130px;object-fit:cover;border-radius:10px;border:1px solid #4b3d1b}}a{{color:#e4c95f}}.empty{{padding:50px;text-align:center;color:#8f8876;border:1px dashed #4b3d1c;border-radius:15px}}@media(max-width:750px){{.grid{{grid-template-columns:1fr}}h1{{font-size:34px}}}}
</style></head><body><header><b>POLÍCIA FEDERAL — <span class="gold">DICOR</span></b></header><main><div class="meta">CENTRAL DE INTELIGÊNCIA • DADOS MIGRADOS DO DISCORD</div><h1>{_esc(title)}</h1><p class="sub">{_esc(subtitle)}</p><section class="grid">{cards or '<div class="empty">Nenhum registro encontrado no arquivo de migração.</div>'}</section></main></body></html>'''

    def _card(record: Dict[str, Any], title: str = "Registro") -> str:
        text = _embed_text(record)
        imgs = _images(record)
        jump = str(record.get("jump_url") or "")
        pics = "".join(f'<img src="{_esc(url)}" loading="lazy">' for url in imgs[:8])
        link = f'<p><a href="{_esc(jump)}" target="_blank">Abrir mensagem original no Discord</a></p>' if jump else ""
        return f'<article class="card"><div class="meta">{_esc(record.get("channel_name") or "DISCORD")}</div><h2>{_esc(title)}</h2><div class="text">{_esc(text[:10000])}</div>{link}<div class="pics">{pics}</div></article>'

    async def migrated_boletins_http(request):
        records = _records("boletins")
        cards = []
        for record in records:
            number = _first_field(record, ("numero boletim", "boletim", "número", "numero", "protocolo"))
            title = f"Boletim {number}" if number else "Boletim migrado"
            cards.append(_card(record, title))
        return web.Response(text=_page("Boletins", f"{len(records)} registro(s) recuperado(s) do histórico do Discord.", "".join(cards)), content_type="text/html", charset="utf-8")

    async def migrated_pericias_http(request):
        records = _records("pericias")
        cards = []
        for record in records:
            title = "Perícia migrada"
            if record.get("embeds") and isinstance(record["embeds"], list) and isinstance(record["embeds"][0], dict):
                title = str(record["embeds"][0].get("title") or title)
            if title == "Perícia migrada":
                title = str(record.get("content") or title).splitlines()[0][:120]
            cards.append(_card(record, title))
        return web.Response(text=_page("Perícias", f"{len(records)} registro(s) recuperado(s) do histórico do Discord.", "".join(cards)), content_type="text/html", charset="utf-8")

    # Substitui somente as páginas dos módulos migrados. A autenticação já instalada
    # continua sendo aplicada pelo middleware da Central.
    bot_module.central_boletins_http = migrated_boletins_http
    bot_module.central_pericias_http = migrated_pericias_http

    archive = _archive()
    print(
        f"✅ V167: Central integrada ao arquivo de migração — "
        f"{len(_records('procurados'))} procurados, {len(_records('boletins'))} boletins e {len(_records('pericias'))} perícias.",
        flush=True,
    )
