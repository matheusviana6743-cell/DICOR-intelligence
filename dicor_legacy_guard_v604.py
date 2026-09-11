# -*- coding: utf-8 -*-
"""Guarda o runtime contra listeners automáticos antigos.

Remove somente listeners de abertura automática de BO/Perícia do módulo bot,
sem mexer em listeners gerais do restante do sistema.
"""


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
    bad_names = (
        "atendimento_boletim_automatico",
        "boletim_automatico",
        "bo_mensal",
        "bo_v1",
        "bo_v2",
        "bo_v165",
        "bo_v166",
        "bo_v200",
        "bo_v205",
        "pericia_automatica",
        "pericia_automatica",
    )
    for fn in listeners:
        name = str(getattr(fn, "__name__", "")).casefold()
        module = str(getattr(fn, "__module__", "")).casefold()
        if module == str(getattr(bot_module, "__name__", "bot")).casefold() and any(x in name for x in bad_names):
            removed += 1
            continue
        kept.append(fn)
    events["on_message"] = kept
    print(f"✅ V604 Legacy Guard | listeners automáticos removidos={removed}", flush=True)
    return removed
