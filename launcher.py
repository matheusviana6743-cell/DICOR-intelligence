# -*- coding: utf-8 -*-
"""Launcher de produção do DICOR."""
import asyncio

import bot
import hierarquia_dicor
import start_safe


def install_gestao_v5() -> None:
    """Substitui implementações legadas pelo painel V5."""
    try:
        import gestao_v4
        import gestao_v5
        gestao_v4.install = gestao_v5.install
        print("✅ [GESTAO] V5 registrada como implementação principal.", flush=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] não foi possível registrar V5: {type(exc).__name__}: {exc}", flush=True)


def disable_gestao_auto_publish() -> None:
    """Impede implementações antigas de recriarem o painel."""
    try:
        import gestao_v3

        async def _install_without_publish(*_args, **_kwargs):
            return True

        gestao_v3.install = _install_without_publish
    except Exception as exc:
        print(f"⚠️ [GESTAO] legado V3: {type(exc).__name__}: {exc}", flush=True)


async def main():
    client = getattr(bot, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord não encontrado")

    install_gestao_v5()
    disable_gestao_auto_publish()
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
