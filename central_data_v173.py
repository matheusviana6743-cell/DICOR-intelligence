# -*- coding: utf-8 -*-
"""V173 — dados enriquecidos sem substituir o layout oficial da Central.

V172 continua responsável pela coleta/indexação. Este módulo só enriquece os
registros com o arquivo histórico e, no final, restaura a camada visual oficial
V163 + autenticação V164/V165. Nada aqui cria mensagens ou altera o Discord.
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
        return

    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    archive_path = data_dir / "central_discord_archive.json"
    cache_path = data_dir / "central_dados_v172.json"

    def norm(v: Any) -> str:
        s = str(v or "").casefold()
        s = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", s)
        return " ".join(s.split())

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
                for f in e.get("fields", []) if isinstance(e.get("fields", []), list) else []:
                    if not isinstance(f, dict):
                        continue
                    n = str(f.get("name") or "").strip()
                    v = str(f.get("value") or "").strip()
                    if n and v:
                        parts.append(f"{n}: {v}")
                    elif v:
                        parts.append(v)
        return "\n".join(parts).strip()

    def field(r: Dict[str, Any], aliases: Iterable[str]) -> str:
        wanted = [norm(x) for x in aliases]
        embeds = r.get("embeds", [])
        if isinstance(embeds, list):
            for e in embeds:
                if not isinstance(e, dict):
                    continue
                fs = e.get("fields", [])
                if not isinstance(fs, list):
                    continue
                for f in fs:
                    if not isinstance(f, dict):
                        continue
                    name = norm(f.get("name"))
                    value = str(f.get("value") or "").strip()
                    if value and any(a == name or a in name or name in a for a in wanted):
                        return value
        for line in str(r.get("content") or "").splitlines():
            if ":" not in line:
                continue
            n, v = line.split(":", 1)
            nn = norm(n)
            if v.strip() and any(a == nn or a in nn or nn in a for a in wanted):
                return v.strip()
        return ""

    def images(r: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for a in r.get("attachments", []) if isinstance(r.get("attachments", []), list) else []:
            if not isinstance(a, dict):
                continue
            url = str(a.get("source_url") or a.get("url") or "").strip()
            fn = str(a.get("filename") or "").lower()
            ct = str(a.get("content_type") or "").lower()
            if url and (ct.startswith("image/") or fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))) and url not in out:
                out.append(url)
        for e in r.get("embeds", []) if isinstance(r.get("embeds", []), list) else []:
            if not isinstance(e, dict):
                continue
            for key in ("image", "thumbnail"):
                obj = e.get(key)
                if isinstance(obj, dict):
                    url = str(obj.get("url") or "").strip()
                    if url and url not in out:
                        out.append(url)
        return out

    def convert(r: Dict[str, Any], kind: str) -> Dict[str, Any]:
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
            "texto_discord": embed_text(r),
            "fotos": images(r),
            "autor": str(r.get("author_name") or r.get("author") or "Não informado"),
            "autor_id": int(r.get("author_id") or 0),
            "data": str(r.get("created_at") or ""),
            "canal": str(r.get("channel_name") or ""),
        }

    def merge(current: List[Dict[str, Any]], historical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for x in historical + current:
            if not isinstance(x, dict):
                continue
            mid = str(x.get("mensagem_id") or x.get("message_id") or "")
            key = mid if mid and mid != "0" else str(hash(json.dumps(x, ensure_ascii=False, default=str)))
            if key not in by_id:
                by_id[key] = dict(x)
            else:
                old = by_id[key]
                for k, v in x.items():
                    if v not in ("", [], None, "Não informado"):
                        old[k] = v
        return list(by_id.values())

    def enrich() -> None:
        arc = archive()
        if arc:
            state["procurados"] = merge(state.get("procurados", []), [convert(r, "procurado") for r in records("procurados")])
            state["boletins"] = merge(state.get("boletins", []), [convert(r, "boletim") for r in records("boletins")])
            state["pericias"] = merge(state.get("pericias", []), [convert(r, "pericia") for r in records("pericias")])
        # V163 consulta estes providers. Assim os dados do V172 entram no layout oficial.
        bot_module._v43_procurados_ativos = lambda: list(state.get("procurados", []))
        bot_module._v44_boletins_ativos_snapshot = lambda: list(state.get("boletins", []))
        try:
            payload = {k: v for k, v in state.items() if k != "task"}
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(cache_path)
        except Exception:
            pass
        print(f"✅ V173 Central: {len(state.get('procurados', []))} procurados, {len(state.get('boletins', []))} boletins, {len(state.get('pericias', []))} perícias enriquecidos.", flush=True)

    enrich()

    # V172 criou páginas experimentais e acabou substituindo o layout oficial V163.
    # Restaura V163 no final do pipeline, sem mexer no Discord.
    try:
        import central_pf_v163
        central_pf_v163.install(bot_module)
        try:
            import central_auth_v164
            central_auth_v164.install(bot_module)
        except Exception as exc:
            print(f"⚠️ V173: autenticação V164 preservada parcialmente: {type(exc).__name__}: {exc}", flush=True)
        try:
            import central_auth_v165
            central_auth_v165.install(bot_module)
        except Exception as exc:
            print(f"⚠️ V173: autenticação V165 preservada parcialmente: {type(exc).__name__}: {exc}", flush=True)
        print("✅ V173: layout oficial V163 restaurado; dados V172/V173 conectados.", flush=True)
    except Exception as exc:
        print(f"❌ V173: não foi possível restaurar V163: {type(exc).__name__}: {exc}", flush=True)

    client = bot_module.bot

    async def on_ready():
        await asyncio.sleep(4)
        enrich()

    if hasattr(client, "add_listener"):
        client.add_listener(on_ready, "on_ready")
