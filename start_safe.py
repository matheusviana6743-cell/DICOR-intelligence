# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V606 + Central V607.

BO e Perícia continuam com gatilho imediato. A recuperação após restart fica
limitada a uma janela curta para nunca reabrir BOs muito antigos. A Central é
somente leitura e consulta os dados diretamente do Discord.
"""
import asyncio
import os
import traceback

import bot
import dicor_legacy_guard_v605
import dicor_core_v605
import dicor_recovery_guard_v606
import central_discord_v607


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    # Remove somente listeners automáticos antigos.
    dicor_legacy_guard_v605.install(bot)

    # Mantém o núcleo V605 (incluindo a seleção de agentes) e troca somente
    # a recuperação histórica por uma janela curta e segura.
    core = dicor_core_v605.install(bot)
    dicor_recovery_guard_v606.install(core)

    # Central restaurada: leitura direta dos canais/tópicos do Discord.
    # O servidor HTTP sobe ANTES do login do Discord, evitando depender do
    # primeiro on_ready para que a porta pública do Railway fique disponível.
    central = central_discord_v607.install(bot)
    await central.start()

    print("✅ DICOR Core V606 ativo | BO + Perícia | recuperação limitada | Central V607 Discord", flush=True)
    await client.start(token, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
