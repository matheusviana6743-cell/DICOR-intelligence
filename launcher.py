# -*- coding: utf-8 -*-
"""Launcher de produção: mantém o start_safe intacto e instala a hierarquia DICOR."""
import asyncio
import os

import bot
import hierarquia_dicor
import start_safe


async def main():
    client = getattr(bot, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord não encontrado")

    installed = False

    async def install_hierarchy_once():
        nonlocal installed
        if installed:
            return
        installed = True
        try:
            await hierarquia_dicor.install(bot)
        except Exception as exc:
            installed = False
            print(f"⚠️ Hierarquia DICOR: {type(exc).__name__}: {exc}", flush=True)

    client.add_listener(install_hierarchy_once, "on_ready")
    await start_safe.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
