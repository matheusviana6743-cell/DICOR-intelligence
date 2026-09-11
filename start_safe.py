# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V606 + Central V616 + Rate Guards V615."""
import asyncio
import os
import traceback

import discord

import bot
import dicor_legacy_guard_v605
import dicor_core_v605
import dicor_recovery_guard_v606
import dicor_rate_guard_v615
import central_procurados_v616
import central_rate_guard_v615


async def start_discord_with_retry(client, token):
    """Mantém o processo vivo quando o Discord aplicar HTTP 429 temporário."""
    attempt = 0
    while True:
        try:
            attempt += 1
            print(f"🔌 Conectando ao Discord (tentativa {attempt})...", flush=True)
            await client.start(token, reconnect=True)
            print("⚠️ Conexão Discord encerrada; aguardando 15s para reconectar...", flush=True)
            await asyncio.sleep(15)
        except discord.errors.HTTPException as exc:
            if getattr(exc, "status", None) == 429:
                retry_after = 60
                try:
                    headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
                    retry_after = float(headers.get("Retry-After", retry_after))
                except Exception:
                    pass
                retry_after = max(30, min(int(retry_after) + 5, 300))
                print(f"🛑 Discord HTTP 429 global. Central permanece online; nova tentativa em {retry_after}s.", flush=True)
                await asyncio.sleep(retry_after)
            else:
                print(f"⚠️ Discord HTTP {getattr(exc, 'status', '?')}: {exc}. Nova tentativa em 30s.", flush=True)
                await asyncio.sleep(30)
        except discord.LoginFailure:
            raise
        except Exception as exc:
            print(f"⚠️ Falha de conexão Discord: {type(exc).__name__}: {exc}. Nova tentativa em 30s.", flush=True)
            await asyncio.sleep(30)


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    dicor_legacy_guard_v605.install(bot)
    core = dicor_core_v605.install(bot)
    dicor_recovery_guard_v606.install(core)
    dicor_rate_guard_v615.install(core)

    central = central_procurados_v616.install(bot)
    central_rate_guard_v615.install(central)
    await central.start()

    print("DICOR Core V606 ativo | BO + Perícia | Rate Guards V615 | Central V616 Procurados", flush=True)
    print("🔎 Central integrada ao Discord | pesquisa por nome ou RG/passaporte", flush=True)
    print("🌐 Central HTTP iniciada antes do gateway Discord", flush=True)
    await start_discord_with_retry(client, token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
