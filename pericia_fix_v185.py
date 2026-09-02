# -*- coding: utf-8 -*-
"""V185 — corrige callbacks de Perícia já registrados no ViewStore."""
from __future__ import annotations

import traceback
from typing import Any


def _sid(value: Any) -> str:
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def install(bot_module) -> bool:
    discord = getattr(bot_module, "discord", None)
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    carregar = getattr(bot_module, "_pericia_carregar", None)
    if discord is None or cls is None or not callable(carregar):
        print("⚠️ V185: componentes da Perícia indisponíveis.", flush=True)
        return False

    # Usa o callback já corrigido pelo V184, quando disponível.
    callback = getattr(cls, "callback", None)
    if not callable(callback):
        print("⚠️ V185: callback da Perícia indisponível.", flush=True)
        return False

    def patch_item(item) -> bool:
        try:
            custom_id = str(getattr(item, "custom_id", "") or "")
            if not (isinstance(item, cls) or custom_id.startswith("dicor_pericia_selecionar_agente")):
                return False
            # O ViewStore mantém ITEMs diretamente em _views, não View objects.
            # Portanto o patch precisa ser aplicado em cada item registrado.
            bound = getattr(item, "callback", None)
            if getattr(bound, "__func__", None) is callback:
                return False
            item.callback = callback.__get__(item, item.__class__)
            return True
        except Exception:
            return False

    client = getattr(bot_module, "bot", None)
    total = 0
    stores = []
    try:
        connection = getattr(client, "_connection", None)
        store = getattr(connection, "_view_store", None)
        if store is not None:
            stores.append(store)
        store2 = getattr(client, "_view_store", None)
        if store2 is not None and store2 is not store:
            stores.append(store2)
    except Exception:
        pass

    for store in stores:
        try:
            raw = getattr(store, "_views", None)
            if isinstance(raw, dict):
                # discord.py: _views[(message_id, custom_id)] = item
                for item in list(raw.values()):
                    if patch_item(item):
                        total += 1
            elif raw:
                for item in list(raw):
                    if patch_item(item):
                        total += 1
        except Exception:
            traceback.print_exc()

        # Alguns builds/patches podem manter views em _synced_message_views.
        try:
            raw = getattr(store, "_synced_message_views", None)
            if isinstance(raw, dict):
                for view in list(raw.values()):
                    for item in list(getattr(view, "children", []) or []):
                        if patch_item(item):
                            total += 1
        except Exception:
            pass

    # Também corrige a classe para qualquer view criada depois.
    try:
        cls.callback = callback
    except Exception:
        pass

    bot_module._V185_PERICIA_STORE_PATCH = True
    print(f"✅ V185 Perícia: callbacks antigos do ViewStore corrigidos; {total} controles atualizados.", flush=True)
    return True
