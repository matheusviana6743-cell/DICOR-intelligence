# -*- coding: utf-8 -*-
"""V173 - bridge leve entre os sincronizadores Discord e a Central V163."""
from __future__ import annotations
import asyncio


def install(bot_module) -> None:
    state = getattr(bot_module, "_v172_central_state", None)
    if not isinstance(state, dict):
        return

    # Captura as fontes instaladas antes do bridge.
    wanted_source = getattr(bot_module, "_v43_procurados_ativos", None)
    boletins_source = getattr(bot_module, "_v44_boletins_ativos_snapshot", None)

    def wanted():
        # V171 e o snapshot V172 continuam sendo as fontes reais.
        if callable(wanted_source):
            try:
                data = wanted_source() or []
                if data:
                    return list(data)
            except Exception:
                pass
        data = state.get("procurados", [])
        return list(data) if isinstance(data, list) else []

    def boletins():
        if callable(boletins_source):
            try:
                data = boletins_source() or []
                if data:
                    return list(data)
            except Exception:
                pass
        data = state.get("boletins", [])
        return list(data) if isinstance(data, list) else []

    bot_module._v43_procurados_ativos = wanted
    bot_module._v44_boletins_ativos_snapshot = boletins
    bot_module._v173_central_bridge = True

    async def refresh():
        # Garante que o primeiro sync do Gateway tenha tempo de terminar.
        for delay in (2, 5, 10, 20, 40):
            await asyncio.sleep(delay)
            try:
                if callable(wanted_source):
                    data = wanted_source() or []
                    if data:
                        state["procurados"] = list(data)
                if callable(boletins_source):
                    data = boletins_source() or []
                    if data:
                        state["boletins"] = list(data)
            except Exception as exc:
                print(f"⚠️ V173 bridge: {type(exc).__name__}: {exc}", flush=True)
        print(f"✅ V173 bridge ativo: {len(wanted())} procurados / {len(boletins())} boletins.", flush=True)

    try:
        asyncio.create_task(refresh())
    except Exception as exc:
        print(f"⚠️ V173: refresh não iniciado: {type(exc).__name__}: {exc}", flush=True)

    print("✅ V173 bridge instalado — Central V163 permanece como layout oficial.", flush=True)
