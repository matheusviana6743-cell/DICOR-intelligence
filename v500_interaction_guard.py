# -*- coding: utf-8 -*-
"""V500 — corrige o timeout de interação do painel de fechamento."""
from __future__ import annotations
import discord
from discord.ui import View, Button


def install(bot_module):
    local_get = getattr(bot_module, '_v147_local_get', None)
    local_modal = getattr(bot_module, 'V147LocalPacificacaoModal', None)
    confirm_view = getattr(bot_module, 'ConfirmacaoFecharMesaView', None)
    if not callable(local_get) or local_modal is None:
        print('⚠️ V500 Interaction Guard: dependências do painel não encontradas.', flush=True)
        return

    class V500PrepararFechamentoView(View):
        def __init__(self, mesa_id: int, dados_mesa=None):
            super().__init__(timeout=300)
            self.mesa_id = int(mesa_id or 0)
            self.dados_mesa = dict(dados_mesa or {})

        @discord.ui.button(label='Definir / Editar Local', emoji='📍', style=discord.ButtonStyle.primary, custom_id='dic_v147_local_pacificacao', row=0)
        async def definir_local(self, interaction: discord.Interaction, button: Button):
            try:
                await interaction.response.send_modal(local_modal(self.mesa_id, local_get(self.mesa_id)))
            except discord.NotFound:
                return
            except Exception as exc:
                try:
                    if interaction.response.is_done(): await interaction.followup.send(f'❌ Erro: {exc}', ephemeral=True)
                    else: await interaction.response.send_message(f'❌ Erro: {exc}', ephemeral=True)
                except Exception: pass

        @discord.ui.button(label='Continuar fechamento', emoji='✅', style=discord.ButtonStyle.green, custom_id='dic_v147_continuar_fechamento', row=0)
        async def continuar(self, interaction: discord.Interaction, button: Button):
            # Primeiro ato: ACK. Nenhum I/O acontece antes disso.
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(thinking=False)
            except discord.NotFound:
                return
            except Exception:
                return
            try:
                local = local_get(self.mesa_id)
                if not local:
                    await interaction.followup.send('📍 Informe primeiro o Local da Pacificação. Use Definir / Editar Local.', ephemeral=True)
                    return
                dados = dict(self.dados_mesa or {})
                dados['local_pacificacao_manual'] = local
                req = dict(dados.get('requisitos_pacificacao') or {})
                req['local_pacificacao'] = local
                req['endereco_exato'] = local
                dados['requisitos_pacificacao'] = req
                self.dados_mesa = dados
                content = ('⚠️ **Confirmação DICOR**\n\n'
                           f'📍 **Local da Pacificação:** {local}\n\n'
                           'As tarefas obrigatórias estão concluídas. Deseja encerrar esta mesa e consolidar o Dossiê Operacional?')
                if confirm_view is None:
                    await interaction.followup.send(content, ephemeral=True)
                else:
                    await interaction.message.edit(content=content, view=confirm_view(dados))
            except discord.NotFound:
                try: await interaction.followup.send('⚠️ O painel não está mais disponível. Abra o fechamento novamente.', ephemeral=True)
                except Exception: pass
            except Exception as exc:
                try: await interaction.followup.send(f'❌ Falha ao avançar o fechamento: {type(exc).__name__}: {exc}', ephemeral=True)
                except Exception: pass

        @discord.ui.button(label='Cancelar', emoji='❌', style=discord.ButtonStyle.secondary, custom_id='dic_v147_cancelar_pre_fechamento', row=0)
        async def cancelar(self, interaction: discord.Interaction, button: Button):
            try:
                if not interaction.response.is_done():
                    await interaction.response.edit_message(content='❌ Encerramento cancelado. A mesa continua aberta.', view=None)
                else:
                    await interaction.message.edit(content='❌ Encerramento cancelado. A mesa continua aberta.', view=None)
            except Exception:
                pass

    bot_module.V147PrepararFechamentoView = V500PrepararFechamentoView
    print('✅ V500 Interaction Guard ativo — ACK imediato no Continuar fechamento.', flush=True)
