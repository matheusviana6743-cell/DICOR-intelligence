# -*- coding: utf-8 -*-
"""V181 - recuperação robusta dos atendimentos de Perícia.

Resolve atendimentos tanto pelo tópico/thread quanto pela mensagem do painel,
que é onde o UserSelect persistente realmente recebe a interação.
"""

import re
import traceback

_FINAL = {"CONCLUIDA_PEGO", "CONCLUIDA_COM_BO", "CONCLUIDA", "FINALIZADA"}


def _sid(value):
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def _active(item):
    return str(item.get("status") or "").upper() not in _FINAL


def _numero_do_texto(texto):
    texto = str(texto or "")
    padroes = (
        r"PER[IÍ]CIA(?:\s+EXTERNA)?\s*(?:N[º°O.]|NÚMERO|NUMERO)?\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
        r"N[º°O.]?\s*(?:DA\s+)?PER[IÍ]CIA\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
    )
    for padrao in padroes:
        m = re.search(padrao, texto, flags=re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1)).strip("-/: ")
    return ""


def install(bot_module):
    original = getattr(bot_module, "_pericia_por_topico", None)
    carregar = getattr(bot_module, "_pericia_carregar", None)
    if not callable(original) or not callable(carregar):
        print("⚠️ V181: funções da Perícia não encontradas; patch não aplicado.", flush=True)
        return False

    # Reaplica sempre a versão atual para sobreviver a módulos legados que
    # possam ter reinstalado a função depois de uma atualização do processo.
    def robust_lookup(topico_id):
        alvo = _sid(topico_id)
        if not alvo:
            return None

        try:
            encontrado = original(topico_id)
            if encontrado:
                return encontrado
        except Exception:
            traceback.print_exc()

        try:
            lista = carregar()
        except Exception:
            traceback.print_exc()
            return None
        if not isinstance(lista, list):
            return None

        # O UserSelect é enviado dentro de uma mensagem. Em muitos casos a
        # interação chega com o ID da mensagem/painel, não com o ID da thread.
        chaves_id = (
            "topico_id", "thread_id", "painel_msg_id", "mensagem_painel_id",
            "mensagem_abertura_id", "mensagem_tarefa_id", "atendimento_id",
            "canal_atendimento_id", "canal_id", "canal_pai_id", "parent_id",
            "thread_parent_id",
        )
        for item in reversed(lista):
            if not isinstance(item, dict):
                continue
            for chave in chaves_id:
                if _sid(item.get(chave)) == alvo:
                    return item

        # Se a interação ocorreu no canal-pai, só associa quando há um único
        # atendimento ativo naquele canal.
        candidatos = []
        for item in lista:
            if not isinstance(item, dict) or not _active(item):
                continue
            pais = {_sid(item.get("canal_pai_id")), _sid(item.get("parent_id"))}
            pais.discard("")
            if alvo in pais:
                candidatos.append(item)
        if len(candidatos) == 1:
            return candidatos[0]

        # Recuperação por nome do canal/thread + número da perícia.
        client = getattr(bot_module, "bot", None)
        channel = None
        try:
            channel = client.get_channel(int(alvo)) if client is not None else None
        except Exception:
            channel = None
        numero = _numero_do_texto(getattr(channel, "name", ""))
        if numero:
            normalizar = getattr(bot_module, "_pericia_numero_chave", None)
            alvo_num = normalizar(numero) if callable(normalizar) else numero
            por_numero = []
            for item in lista:
                if not isinstance(item, dict) or not _active(item):
                    continue
                valor = normalizar(item.get("numero")) if callable(normalizar) else str(item.get("numero") or "")
                if valor and valor == alvo_num:
                    por_numero.append(item)
            if len(por_numero) == 1:
                return por_numero[0]

        return None

    bot_module._pericia_por_topico = robust_lookup
    bot_module._V181_PERICIA_PATCHED = True
    print("✅ V181 Perícia: lookup por tópico, painel, tarefa, canal-pai e número ativo.", flush=True)
    return True
