# -*- coding: utf-8 -*-
"""V173 — ponte segura de dados para a Central oficial.

Importante: este módulo NÃO inicializa tarefas, NÃO registra novas rotas e
NÃO altera o layout/auth da Central. O Discord/bot deve continuar iniciando
mesmo que os dados da Central estejam indisponíveis.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


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


def install(bot_module) -> None:
    """Expõe dados persistidos sem interferir no boot do bot."""
    try:
        state = getattr(bot_module, "_v172_central_state", None)
        if not isinstance(state, dict):
            print("ℹ️ V173: estado V172 ainda indisponível; Central segue com fallback.", flush=True)
            return

        data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
        archive = _load_json(data_dir / "central_discord_archive.json") or {}
        cache = _load_json(data_dir / "central_dados_v172.json") or {}

        for kind in ("procurados", "boletins", "pericias"):
            current = _as_records(state.get(kind, []), kind)
            cached = _as_records(cache.get(kind, []), kind)
            historical = _as_records(archive.get(kind, []), kind)

            # Prioriza dados atuais; usa cache/histórico somente como complemento.
            merged: List[Dict[str, Any]] = []
            seen = set()
            for item in current + cached + historical:
                key = str(item.get("message_id") or item.get("id") or item.get("mensagem_url") or "")
                if not key:
                    key = repr(sorted(item.items()))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)

            state[kind] = merged

        # Providers consumidos pela Central V163, sem substituir suas rotas.
        bot_module._v43_procurados_ativos = lambda: list(state.get("procurados", []))
        bot_module._v44_boletins_ativos_snapshot = lambda: list(state.get("boletins", []))
        bot_module._v173_central_data_state = state
        print(
            "✅ V173: dados conectados à Central oficial "
            f"(procurados={len(state.get('procurados', []))}, "
            f"boletins={len(state.get('boletins', []))}, "
            f"pericias={len(state.get('pericias', []))}).",
            flush=True,
        )
    except Exception as exc:
        # Falha da Central jamais pode derrubar o Discord.
        print(f"⚠️ V173 desativado por segurança: {exc}", flush=True)
