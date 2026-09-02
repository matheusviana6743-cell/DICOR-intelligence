# -*- coding: utf-8 -*-
"""V171 - sincronização persistente Discord -> Procurados -> Central DICOR.

Fonte de verdade: canal oficial de Procurados no Discord.
O snapshot local serve para persistência entre reinícios do Railway.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set

ACTIVE_WANTED_CHANNEL_ID = 1490200533980545097


def install(bot_module) -> None:
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = data_dir / "procurados_discord.json"

    state = {
        "message_ids": set(),
        "records": {},
        "ready": False,
        "sync_task": None,
        "loop_task": None,
        "last_error": "",
    }

    def _load_snapshot() -> None:
        try:
            if not snapshot_path.exists():
                return
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
        tmp = snapshot_path.with_suffix(".tmp")
        payload = {"version": 171, "records": state["records"]}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(snapshot_path)

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

        attachments = []
        for a in getattr(message, "attachments", []) or []:
            url = str(getattr(a, "url", "") or "")
            if url: attachments.append(url)
        for embed in embeds:
            image = getattr(embed, "image", None)
            url = str(getattr(image, "url", "") or "") if image else ""
            if url: attachments.append(url)

        nome = pick("nome", "nome completo", "indivíduo", "individuo")
        rg = pick("rg", "passaporte", "id")
        descricao = pick("descrição", "descricao")
        crime = pick("crime", "crimes", "acusação", "acusacao")
        return {
            "mensagem_id": int(message.id),
            "mensagem_url": str(getattr(message, "jump_url", "") or ""),
            "nome": nome or str(getattr(getattr(message, "author", None), "display_name", "") or "") or "Não informado",
            "rg": rg,
            "descricao": descricao,
            "crime": crime,
            "texto_discord": blob,
            "fotos": list(dict.fromkeys(attachments)),
            "autor_id": int(getattr(getattr(message, "author", None), "id", 0) or 0),
            "data_discord": getattr(getattr(message, "created_at", None), "isoformat", lambda: "")(),
        }

    async def _resolve_channel():
        client = getattr(bot_module, "bot", None)
        if client is None: return None
        channel = client.get_channel(ACTIVE_WANTED_CHANNEL_ID)
        if channel is not None: return channel
        try: return await client.fetch_channel(ACTIVE_WANTED_CHANNEL_ID)
        except Exception: return None

    async def _sync_full(reason=""):
        channel = await _resolve_channel()
        if channel is None or not hasattr(channel, "history"):
            state["last_error"] = "canal_indisponivel"
            return
        try:
            fresh = {}
            async for message in channel.history(limit=None, oldest_first=True):
                # Mensagens sem conteúdo/embeds/anexos não são registros úteis.
                if not (getattr(message, "content", "") or getattr(message, "embeds", None) or getattr(message, "attachments", None)):
                    continue
                registro = _extract_fields(message)
                fresh[str(message.id)] = registro
            state["records"] = fresh
            state["message_ids"] = {int(k) for k in fresh if k.isdigit()}
            state["ready"] = True
            state["last_error"] = ""
            _save_snapshot()
            _invalidate_cache()
            print(f"✅ V171 Procurados: Discord → snapshot atualizado com {len(fresh)} registros ({reason}).", flush=True)
        except Exception as exc:
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"⚠️ V171 Procurados: sincronização falhou: {type(exc).__name__}: {exc}", flush=True)

    def _invalidate_cache():
        for name, value in (("_V17_CATALOGO_CACHE_HTML", ""), ("_V17_CATALOGO_CACHE_KEY", None)):
            try: setattr(bot_module, name, value)
            except Exception: pass

    def _records() -> List[Dict[str, Any]]:
        return list(state["records"].values())

    async def _refresh(reason):
        task = state.get("sync_task")
        if task is not None and not task.done(): return
        async def run():
            await asyncio.sleep(0.4)
            await _sync_full(reason)
        state["sync_task"] = asyncio.create_task(run())

    async def _on_ready():
        # Carrega primeiro para a Central nunca ficar permanentemente vazia após restart.
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
                await asyncio.sleep(30)
                await _sync_full("sincronização periódica")
            except asyncio.CancelledError: raise
            except Exception as exc:
                print(f"⚠️ V171 loop: {exc}", flush=True)

    def _active_records():
        # Compatibilidade com o restante do bot: a Central passa a usar o snapshot Discord.
        return _records()

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

    async def _central_normal_http(request):
        registros = _active_records()
        # Reaproveita a página visual do V162, mas com a contagem real do snapshot Discord.
        qtd = len(registros)
        cards = f'''<article class="card"><div class="ico">🎯</div><h3>Procurados</h3><p>{qtd} indivíduo(s) sincronizado(s) diretamente do Discord.</p><a href="/catalogo">Abrir catálogo</a></article>'''
        cards += '''<article class="card private"><div class="ico">🗃️</div><h3>Banco de Dados</h3><p>Fichas e registros investigativos.</p><a href="/fichas">Acessar banco</a></article>'''
        cards += '''<article class="card private"><div class="ico">🧬</div><h3>Árvore de Inteligência</h3><p>Conexões e vínculos.</p><a href="/arvore">Abrir vínculos</a></article>'''
        page = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Central DICOR</title><style>body{{margin:0;background:#070806;color:#f7f1db;font-family:Arial,sans-serif}}main{{max-width:1100px;margin:auto;padding:60px 25px}}h1{{letter-spacing:3px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}}.card{{padding:28px;border:1px solid #4a3c1d;border-radius:18px;background:#11130e}}.ico{{font-size:30px}}h3{{font-size:23px}}p{{color:#aaa58f;line-height:1.5}}a{{display:inline-block;padding:11px 16px;background:#d7a93d;color:#111;text-decoration:none;border-radius:8px;font-weight:bold}}</style></head><body><main><small>DICOR • CENTRAL DE INTELIGÊNCIA</small><h1>Central DICOR</h1><p>Dados sincronizados diretamente do canal oficial de Procurados do Discord.</p><section class="grid">{cards}</section></main></body></html>'''
        return bot_module.web.Response(text=page, content_type="text/html", charset="utf-8")

    bot_module.central_portal_http = _central_normal_http
    _load_snapshot()
    print(f"✅ V171 Procurados: fonte Discord + persistência em {snapshot_path}.", flush=True)
