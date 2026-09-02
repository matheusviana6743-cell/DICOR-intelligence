# -*- coding: utf-8 -*-
"""V169 - correção cirúrgica do painel de Relatórios.

Mantém os custom_id existentes e substitui somente os callbacks de Tocaia/OLB
por callbacks mínimos, sem trabalho antes do primeiro request ao Discord.
Também evita que o handler de erro tente responder uma interação já expirada.
"""

import traceback


def _patch_button(view_cls, attr_name, modal_cls, label):
    button = getattr(view_cls, attr_name, None)
    if button is None:
        return False

    async def _callback(self, interaction, item):
        # NÃO faça qualquer operação de banco/OCR/canal antes daqui.
        try:
            await interaction.response.send_modal(modal_cls())
        except Exception as exc:
            # Uma interação 10062 já expirou e não aceita segunda resposta.
            # Não transforme o erro original em outro erro no on_error.
            try:
                import discord
                if isinstance(exc, discord.NotFound) and getattr(exc, 'code', None) == 10062:
                    print(f'⚠️ V169 {label}: interação Discord expirou antes do ACK.', flush=True)
                    return
            except Exception:
                pass
            print(f'❌ V169 {label}: {type(exc).__name__}: {exc}', flush=True)
            traceback.print_exc()

    # discord.py transforma os callbacks dos botões em callbacks de instância
    # quando a View é criada; trocar o callback do Button de classe preserva os
    # custom_id e faz a correção valer também para Views persistentes.
    try:
        button.callback = _callback
    except Exception:
        try:
            button._callback = _callback
        except Exception:
            return False
    return True


def _blindar_on_error(view_cls):
    original = getattr(view_cls, 'on_error', None)

    async def _safe_on_error(self, interaction, error, item):
        try:
            import discord
            if isinstance(error, discord.NotFound) and getattr(error, 'code', None) == 10062:
                print('⚠️ V169: Unknown interaction ignorada sem segunda tentativa de resposta.', flush=True)
                return
        except Exception:
            pass

        # Se já houve resposta, use followup somente quando disponível.
        try:
            if getattr(interaction.response, 'is_done', lambda: False)():
                try:
                    await interaction.followup.send(
                        '⚠️ Não foi possível concluir esta ação. Tente novamente.',
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

        if original is not None:
            try:
                await original(self, interaction, error, item)
                return
            except Exception:
                pass

        try:
            await interaction.response.send_message(
                '⚠️ Não foi possível concluir esta ação. Tente novamente.',
                ephemeral=True,
            )
        except Exception:
            pass


def install(bot_module):
    view_cls = getattr(bot_module, 'RelatoriosPainelView', None)
    tocaia = getattr(bot_module, 'TocaiaModal', None)
    olb = getattr(bot_module, 'OlbModal', None)

    if view_cls is None:
        print('⚠️ V169: RelatoriosPainelView não encontrado; patch não aplicado.', flush=True)
        return False

    ok_tocaia = _patch_button(view_cls, 'btn_tocaia', tocaia, 'TOCAIA') if tocaia else False
    ok_olb = _patch_button(view_cls, 'btn_olb', olb, 'OLB') if olb else False
    _blindar_on_error(view_cls)

    print(
        f'✅ V169 Interaction Core: painel de relatórios blindado '
        f'(Tocaia={ok_tocaia}, OLB={ok_olb}, custom_id preservado).',
        flush=True,
    )
    return ok_tocaia or ok_olb
