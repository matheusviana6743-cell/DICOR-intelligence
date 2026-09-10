# -*- coding: utf-8 -*-
"""V501 - fechamento de mesa persistente e resiliente.

Corrige o painel "Preparação para fechamento" que podia ficar indisponível
após timeout/restart e evitava interações 10062/404 quando o processamento
começava antes do ACK.

Não substitui a lógica do dossiê. Apenas troca o painel intermediário por uma
View persistente que reutiliza os helpers já existentes no bot.
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Optional

import discord
from discord.ui import View, Button, Modal, TextInput


CUSTOM_LOCAL = "dic_v147_local_pacificacao"
CUSTOM_CONTINUAR = "dic_v147_continuar_fechamento"
CUSTOM_CANCELAR = "dic_v147_cancelar_pre_fechamento"


def _bot():
    import bot
    return bot


def _local_get(mesa_id: int) -> str:
    mod = _bot()
    getter = getattr(mod, "_v147_local_get", None)
    if callable(getter):
        try:
            return str(getter(int(mesa_id or 0)) or "").strip()
        except Exception:
            return ""
    return ""


def _local_set(mesa_id: int, local: str, user: Any) -> str:
    mod = _bot()
    setter = getattr(mod, "_v147_local_set", None)
    if not callable(setter):
        raise RuntimeError("rotina de persistência do Local da Pacificação não encontrada")
    return str(setter(int(mesa_id or 0), str(local or ""), user) or "").strip()


async def _defer(interaction: discord.Interaction) -> bool:
    """ACK imediato; evita Unknown interaction 10062."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        return True
    except discord.NotFound:
        return False
    except Exception:
        return False


async def _send(interaction: discord.Interaction, content: str, *, view: Optional[View] = None) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content=content, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(content, view=view, ephemeral=True)
    except discord.NotFound:
        # A interação já expirou; não tenta uma segunda resposta HTTP.
        return
    except Exception as exc:
        print(f"⚠️ V501 envio seguro falhou: {type(exc).__name__}: {exc}", flush=True)


class V501LocalModal(Modal):
    def __init__(self, mesa_id: int, atual: str = ""):
        super().__init__(title="Local da Pacificação", timeout=300)
        self.mesa_id = int(mesa_id or 0)
        self.local_input = TextInput(
            label="Local da Pacificação",
            placeholder="Informe o local que deverá aparecer no documento",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
            default=atual[:500] or None,
        )
        self.add_item(self.local_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Modal submit precisa responder em até 3 s; não executa trabalho pesado antes do ACK.
        try:
            local = _local_set(self.mesa_id, str(self.local_input.value or ""), interaction.user)
            await _send(
                interaction,
                "✅ **Local da Pacificação salvo.**\n"
                f"📍 {local}\n\n"
                "O painel de fechamento continua disponível abaixo.",
                view=V501PrepararFechamentoView(self.mesa_id),
            )
        except Exception as exc:
            traceback.print_exc()
            await _send(interaction, f"❌ Não foi possível salvar o Local da Pacificação: {exc}")


class V501PrepararFechamentoView(View):
    """View persistente: timeout=None e estado mínimo baseado no canal atual."""

    def __init__(self, mesa_id: int = 0, dados_mesa: Optional[dict] = None):
        super().__init__(timeout=None)
        self.mesa_id = int(mesa_id or 0)
        self.dados_mesa = dict(dados_mesa or {})

    @discord.ui.button(
        label="Definir / Editar Local",
        emoji="📍",
        style=discord.ButtonStyle.primary,
        custom_id=CUSTOM_LOCAL,
        row=0,
    )
    async def definir_local(self, interaction: discord.Interaction, button: Button):
        # Use o canal real para sobreviver a restart e a instâncias antigas da View.
        mesa_id = int(getattr(getattr(interaction, "channel", None), "id", 0) or self.mesa_id or 0)
        atual = _local_get(mesa_id)
        try:
            await interaction.response.send_modal(V501LocalModal(mesa_id, atual))
        except discord.NotFound:
            return
        except Exception as exc:
            await _send(interaction, f"❌ Não foi possível abrir o campo de local: {exc}")

    @discord.ui.button(
        label="Continuar fechamento",
        emoji="✅",
        style=discord.ButtonStyle.green,
        custom_id=CUSTOM_CONTINUAR,
        row=0,
    )
    async def continuar(self, interaction: discord.Interaction, button: Button):
        # PRIMEIRO ato: ACK.
        if not await _defer(interaction):
            return

        try:
            mod = _bot()
            mesa_id = int(getattr(getattr(interaction, "channel", None), "id", 0) or self.mesa_id or 0)
            if not mesa_id:
                return await _send(interaction, "❌ Não foi possível identificar a mesa.")

            local = _local_get(mesa_id)
            if not local:
                return await _send(
                    interaction,
                    "📍 **Informe primeiro o Local da Pacificação.**\n"
                    "Use **Definir / Editar Local** e tente novamente.",
                    view=V501PrepararFechamentoView(mesa_id, self.dados_mesa),
                )

            dados = dict(self.dados_mesa or {})
            dados["local_pacificacao_manual"] = local
            req = dict(dados.get("requisitos_pacificacao") or {})
            req["local_pacificacao"] = local
            req["endereco_exato"] = local
            dados["requisitos_pacificacao"] = req

            confirm_view_cls = getattr(mod, "ConfirmacaoFecharMesaView", None)
            if confirm_view_cls is None:
                return await _send(interaction, "❌ Painel de confirmação indisponível no momento.")

            await _send(
                interaction,
                "⚠️ **Confirmação DICOR**\n\n"
                f"📍 **Local da Pacificação:** {local}\n\n"
                "As tarefas obrigatórias estão concluídas. Deseja encerrar esta mesa e consolidar o Dossiê Operacional?",
                view=confirm_view_cls(dados),
            )
        except Exception as exc:
            traceback.print_exc()
            await _send(interaction, f"❌ Erro ao preparar o encerramento: {type(exc).__name__}: {exc}")

    @discord.ui.button(
        label="Cancelar",
        emoji="❌",
        style=discord.ButtonStyle.secondary,
        custom_id=CUSTOM_CANCELAR,
        row=0,
    )
    async def cancelar(self, interaction: discord.Interaction, button: Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Encerramento cancelado. A mesa continua aberta.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Encerramento cancelado. A mesa continua aberta.", ephemeral=True)
        except Exception:
            pass


def install(bot_module: Any) -> None:
    """Instala a View persistente e substitui o construtor usado pelo fluxo V147."""
    # O fluxo V147 instancia esse nome em runtime. Substituí-lo aqui faz com
    # que o botão antigo e os novos fechamentos usem a View persistente.
    try:
        bot_module.V147PrepararFechamentoView = V501PrepararFechamentoView
    except Exception:
        pass

    client = getattr(bot_module, "bot", None)
    if client is None:
        print("⚠️ V501: cliente Discord indisponível durante instalação.", flush=True)
        return

    # Registro global persistente: continua funcionando após restart/reconnect.
    try:
        client.add_view(V501PrepararFechamentoView(0, {}))
        print("✅ V501 Fechamento: View persistente registrada (ACK imediato + recuperação após restart).", flush=True)
    except Exception as exc:
        # add_view pode já ter sido registrado; não quebra o restante do bot.
        print(f"⚠️ V501 Fechamento: registro da View não concluído: {type(exc).__name__}: {exc}", flush=True)
