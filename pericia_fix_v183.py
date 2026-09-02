# -*- coding: utf-8 -*-
"""V183 - correção definitiva da resolução do painel da Perícia.

A interação do UserSelect contém o ID da mensagem que realmente recebeu a
View. O callback antigo procurava somente pelo channel_id. Em Views
persistentes/threads isso pode falhar mesmo com o atendimento salvo.
"""

from contextvars import ContextVar

_INTERACTION = ContextVar("dicor_pericia_interaction", default=None)


def _sid(value):
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def install(bot_module):
    carregar = getattr(bot_module, "_pericia_carregar", None)
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    original_lookup = getattr(bot_module, "_pericia_por_topico", None)
    if not callable(carregar) or cls is None or not callable(original_lookup):
        print("⚠️ V183: componentes da Perícia não encontrados.", flush=True)
        return False
    if getattr(bot_module, "_V183_PERICIA_PATCHED", False):
        return True

    def lookup(value):
        # Primeiro, usa o contexto da interação: message.id é o identificador
        # mais confiável porque a View veio exatamente dessa mensagem.
        interaction = _INTERACTION.get()
        if interaction is not None:
            mid = _sid(getattr(getattr(interaction, "message", None), "id", None))
            cid = _sid(getattr(interaction, "channel_id", None))
            if mid:
                for registro in carregar():
                    if not isinstance(registro, dict):
                        continue
                    ids = {
                        _sid(registro.get("painel_msg_id")),
                        _sid(registro.get("mensagem_tarefa_id")),
                        _sid(registro.get("mensagem_abertura_id")),
                        _sid(registro.get("mensagem_original_id")),
                    }
                    ids.discard("")
                    if mid in ids:
                        return registro
            # Depois tenta o canal/thread da própria interação.
            if cid:
                encontrado = original_lookup(cid)
                if encontrado:
                    return encontrado

        return original_lookup(value)

    bot_module._pericia_por_topico = lookup

    old_callback = getattr(cls, "callback", None)
    if not callable(old_callback):
        print("⚠️ V183: callback do seletor não encontrado.", flush=True)
        return False

    async def callback(self, interaction):
        token = _INTERACTION.set(interaction)
        try:
            return await old_callback(self, interaction)
        finally:
            _INTERACTION.reset(token)

    cls.callback = callback
    bot_module._V183_PERICIA_PATCHED = True
    print("✅ V183 Perícia: seleção agora resolve pelo ID da mensagem do painel + tópico.", flush=True)
    return True
