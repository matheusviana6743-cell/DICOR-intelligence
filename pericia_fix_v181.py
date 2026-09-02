# -*- coding: utf-8 -*-
"""V181 - correção definitiva do vínculo das Views de Perícia.

A View persistente é acionada a partir de uma mensagem específica. O callback
antigo tentava descobrir o atendimento somente pelo channel_id. Quando o ID
salvo e o canal da interação divergem, o callback devolve "Atendimento não
encontrado" mesmo existindo um registro válido.
"""

import contextvars
import re
import traceback

_FINAL = {"CONCLUIDA_PEGO", "CONCLUIDA_COM_BO", "CONCLUIDA", "FINALIZADA"}
_CTX = contextvars.ContextVar("dicor_pericia_lookup_id", default="")


def _sid(value):
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def _active(item):
    return str(item.get("status") or "").upper() not in _FINAL


def _numero_do_texto(texto):
    texto = str(texto or "")
    for padrao in (
        r"PER[IÍ]CIA(?:\s+EXTERNA)?\s*(?:N[º°O.]|NÚMERO|NUMERO)?\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
        r"N[º°O.]?\s*(?:DA\s+)?PER[IÍ]CIA\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
    ):
        m = re.search(padrao, texto, flags=re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1)).strip("-/: ")
    return ""


def install(bot_module):
    original_lookup = getattr(bot_module, "_pericia_por_topico", None)
    carregar = getattr(bot_module, "_pericia_carregar", None)
    if not callable(original_lookup) or not callable(carregar):
        print("⚠️ V181: funções da Perícia não encontradas; patch não aplicado.", flush=True)
        return False

    def robust_lookup(topico_id):
        # Se estamos dentro de uma View, o ID da mensagem do painel é a chave
        # mais confiável e não depende do canal em que o Discord entregou a
        # interação.
        contexto = _CTX.get()
        candidatos_ids = []
        if contexto:
            candidatos_ids.append(contexto)
        alvo = _sid(topico_id)
        if alvo:
            candidatos_ids.append(alvo)

        try:
            lista = carregar()
        except Exception:
            traceback.print_exc()
            lista = []
        if not isinstance(lista, list):
            lista = []

        chaves_id = (
            "topico_id", "thread_id", "painel_msg_id", "mensagem_painel_id",
            "mensagem_abertura_id", "mensagem_tarefa_id", "atendimento_id",
            "canal_atendimento_id", "canal_id", "canal_pai_id", "parent_id",
            "thread_parent_id",
        )
        for chave_id in candidatos_ids:
            for item in reversed(lista):
                if isinstance(item, dict) and any(_sid(item.get(chave)) == chave_id for chave in chaves_id):
                    return item

        # Mantém compatibilidade com a função original.
        try:
            encontrado = original_lookup(topico_id)
            if encontrado:
                return encontrado
        except Exception:
            traceback.print_exc()

        # Se a interação estiver no canal-pai e houver exatamente um atendimento
        # ativo, não há ambiguidade para fazer a associação.
        if alvo:
            pais = [
                item for item in lista
                if isinstance(item, dict) and _active(item)
                and alvo in {_sid(item.get("canal_pai_id")), _sid(item.get("parent_id"))}
            ]
            if len(pais) == 1:
                return pais[0]

        # Último fallback: número no nome do canal/thread.
        client = getattr(bot_module, "bot", None)
        channel = None
        try:
            channel = client.get_channel(int(alvo)) if client is not None and alvo else None
        except Exception:
            pass
        numero = _numero_do_texto(getattr(channel, "name", ""))
        if numero:
            normalizar = getattr(bot_module, "_pericia_numero_chave", None)
            alvo_num = normalizar(numero) if callable(normalizar) else numero
            encontrados = []
            for item in lista:
                if not isinstance(item, dict) or not _active(item):
                    continue
                valor = normalizar(item.get("numero")) if callable(normalizar) else str(item.get("numero") or "")
                if valor and valor == alvo_num:
                    encontrados.append(item)
            if len(encontrados) == 1:
                return encontrados[0]
        return None

    bot_module._pericia_por_topico = robust_lookup

    # Patch direto do UserSelect. Isso torna o vínculo determinístico: antes de
    # executar o callback original, passamos o ID exato da mensagem que contém
    # o seletor. O contextvar evita interferência entre duas interações simultâneas.
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    if cls is not None and hasattr(cls, "callback"):
        current = getattr(cls, "callback")
        if not getattr(current, "_dicor_v181_wrapper", False):
            async def callback_wrapper(self, interaction):
                message = getattr(interaction, "message", None)
                message_id = _sid(getattr(message, "id", 0))
                token = _CTX.set(message_id)
                try:
                    return await current(self, interaction)
                finally:
                    _CTX.reset(token)
            callback_wrapper._dicor_v181_wrapper = True
            cls.callback = callback_wrapper
            print("✅ V181 Perícia: callback do UserSelect vinculado ao ID da mensagem.", flush=True)

    bot_module._V181_PERICIA_PATCHED = True
    print("✅ V181 Perícia ativo: tópico + thread + painel + tarefa + canal-pai + número.", flush=True)
    return True
