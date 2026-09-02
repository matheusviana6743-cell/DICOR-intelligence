# -*- coding: utf-8 -*-
"""V181 - correção definitiva do vínculo das Views de Perícia."""

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


def _build_lookup(bot_module, original_lookup, carregar):
    def robust_lookup(topico_id):
        contexto = _CTX.get()
        ids = []
        if contexto:
            ids.append(contexto)
        alvo = _sid(topico_id)
        if alvo:
            ids.append(alvo)

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
        for chave_id in ids:
            for item in reversed(lista):
                if isinstance(item, dict) and any(_sid(item.get(chave)) == chave_id for chave in chaves_id):
                    return item

        try:
            encontrado = original_lookup(topico_id)
            if encontrado:
                return encontrado
        except Exception:
            traceback.print_exc()

        if alvo:
            pais = [
                item for item in lista
                if isinstance(item, dict) and _active(item)
                and alvo in {_sid(item.get("canal_pai_id")), _sid(item.get("parent_id"))}
            ]
            if len(pais) == 1:
                return pais[0]

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
    return robust_lookup


def _wrap_callback(original_callback):
    if not callable(original_callback) or getattr(original_callback, "_dicor_v181_wrapper", False):
        return original_callback

    async def callback_wrapper(self, interaction):
        message = getattr(interaction, "message", None)
        token = _CTX.set(_sid(getattr(message, "id", 0)))
        try:
            return await original_callback(self, interaction)
        finally:
            _CTX.reset(token)

    callback_wrapper._dicor_v181_wrapper = True
    return callback_wrapper


def install(bot_module):
    carregar = getattr(bot_module, "_pericia_carregar", None)
    atual = getattr(bot_module, "_pericia_por_topico", None)
    if not callable(carregar) or not callable(atual):
        print("⚠️ V181: funções da Perícia não encontradas; patch não aplicado.", flush=True)
        return False

    bot_module._pericia_por_topico = _build_lookup(bot_module, atual, carregar)

    # Views novas.
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    if cls is not None and hasattr(cls, "callback"):
        cls.callback = _wrap_callback(cls.callback)

    # Views persistentes já existentes. Patching apenas a classe não basta:
    # cada item já criado guarda seu callback bound, portanto substituímos o
    # callback no objeto real que está registrado no Client.
    client = getattr(bot_module, "bot", None)
    corrigidos = 0
    try:
        for view in list(getattr(client, "persistent_views", []) or []):
            for item in list(getattr(view, "children", []) or []):
                cid = str(getattr(item, "custom_id", "") or "")
                if cid.startswith("dicor_pericia_"):
                    wrapped = _wrap_callback(getattr(item, "callback", None))
                    if wrapped is not None:
                        item.callback = wrapped
                        corrigidos += 1
    except Exception:
        traceback.print_exc()

    bot_module._V181_PERICIA_PATCHED = True
    print(f"✅ V181 Perícia: {corrigidos} controles persistentes corrigidos; vínculo por mensagem do painel ativo.", flush=True)
    return True
