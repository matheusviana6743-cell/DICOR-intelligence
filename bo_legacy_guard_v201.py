# -*- coding: utf-8 -*-
"""Desativa somente o listener automático antigo de BO.
Não altera comandos, armazenamento ou demais módulos do bot.
"""

def install(botmod):
    client = getattr(botmod, "bot", None)
    if client is None:
        return
    extra = getattr(client, "extra_events", None)
    if not isinstance(extra, dict):
        return
    listeners = extra.get("on_message", [])
    removidos = 0
    mantidos = []
    for fn in list(listeners):
        nome = str(getattr(fn, "__name__", ""))
        modulo = str(getattr(fn, "__module__", ""))
        if nome == "atendimento_boletim_automatico" and modulo == getattr(botmod, "__name__", "bot"):
            removidos += 1
            continue
        mantidos.append(fn)
    extra["on_message"] = mantidos
    print(f"✅ V201 Legacy Guard: listeners BO antigos removidos={removidos}", flush=True)
