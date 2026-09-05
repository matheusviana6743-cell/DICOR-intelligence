# -*- coding: utf-8 -*-
"""Launcher de produção.

Garante que o boot não publique automaticamente o painel de Gestão DICOR.
O painel pode continuar existindo e seus botões continuam registrados para
mensagens já existentes; o boot apenas não cria uma nova mensagem.
"""
import asyncio

import bot
import hierarquia_dicor
import start_safe


def disable_gestao_auto_publish() -> None:
    """Impede qualquer instalador legado de enviar o painel durante o boot."""
    try:
        import gestao_v3

        async def _install_without_publish(*_args, **_kwargs):
            # O painel não é criado/enviado automaticamente.
            # gestao_panel_fix.py continua responsável por registrar a View
            # persistente dos botões das mensagens que já existem.
            return True

        gestao_v3.install = _install_without_publish
        print("✅ [GESTAO] publicação automática bloqueada no launcher.", flush=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] não foi possível bloquear publicação automática: {type(exc).__name__}: {exc}", flush=True)


async def main():
    client = getattr(bot, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord não encontrado")

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

    # Registrado antes do listener do start_safe para a hierarquia aplicar seus
    # patches antes de qualquer integração de pós-READY.
    client.add_listener(install_hierarchy_once, "on_ready")
    await start_safe.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
