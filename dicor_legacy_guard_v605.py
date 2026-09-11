# -*- coding: utf-8 -*-
"""Remove listeners antigos de abertura automática antes do Core V605."""


def install(bot_module):
    client = getattr(bot_module, "bot", None)
    if client is None:
        return 0
    events = getattr(client, "extra_events", None)
    if not isinstance(events, dict):
        return 0

    listeners = list(events.get("on_message", []))
    kept = []
    removed = 0
    blocked_modules = {
        "dicor_core_v603",
        "dicor_core_v604",
        "bo_sistema_v200",
        "bo_mensal_v166",
        "bo_mensal_v165",
    }
    blocked_names = {
        "atendimento_boletim_automatico",
        "boletim_automatico",
        "pericia_automatica",
    }

    for fn in listeners:
        name = str(getattr(fn, "__name__", "")).casefold()
        module = str(getattr(fn, "__module__", "")).casefold()
        if module in blocked_modules or name in blocked_names:
            removed += 1
            continue
        kept.append(fn)

    events["on_message"] = kept
    print(f"✅ V605 Legacy Guard | listeners antigos removidos={removed}", flush=True)
    return removed
