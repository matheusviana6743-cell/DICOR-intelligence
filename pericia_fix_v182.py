# -*- coding: utf-8 -*-
"""V182 - recuperação final de atendimentos de Perícia.

O erro "Atendimento da perícia não encontrado" pode ocorrer quando uma View
persistente carrega um ID antigo e existem registros ativos sem o ID atual.
Este módulo resolve o atendimento por identidade, pai e, como último recurso,
pelo atendimento ativo mais recente.
"""

from datetime import datetime


def _sid(value):
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def _timestamp(registro):
    for chave in (
        "atualizado_em", "updated_at", "ultima_atualizacao", "criado_em",
        "created_at", "timestamp", "data_hora", "inicio_em",
    ):
        valor = registro.get(chave)
        if not valor:
            continue
        try:
            return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return 0.0


def install(bot_module):
    carregar = getattr(bot_module, "_pericia_carregar", None)
    lookup = getattr(bot_module, "_pericia_por_topico", None)
    if not callable(carregar) or not callable(lookup):
        print("⚠️ V182: funções da Perícia não disponíveis.", flush=True)
        return False

    # Não bloqueia uma reinstalação: V183/V181 podem atualizar o resolver.
    finalizados = {
        "CONCLUIDA", "CONCLUÍDA", "CONCLUIDA_PEGO", "CONCLUIDA_COM_BO",
        "FINALIZADA", "FINALIZADO", "FECHADA", "FECHADO", "ENCERRADA", "ENCERRADO",
    }

    def robust_lookup(value):
        try:
            found = lookup(value)
            if found is not None:
                return found
        except Exception:
            pass

        try:
            registros = carregar()
        except Exception:
            return None
        if not isinstance(registros, list):
            return None

        ativos = []
        alvo = _sid(value)
        for registro in registros:
            if not isinstance(registro, dict):
                continue
            status = str(registro.get("status") or "").strip().upper()
            if status in finalizados:
                continue
            ids = {
                _sid(registro.get("topico_id")),
                _sid(registro.get("thread_id")),
                _sid(registro.get("painel_msg_id")),
                _sid(registro.get("mensagem_painel_id")),
                _sid(registro.get("mensagem_abertura_id")),
                _sid(registro.get("mensagem_tarefa_id")),
                _sid(registro.get("atendimento_id")),
                _sid(registro.get("canal_atendimento_id")),
                _sid(registro.get("canal_id")),
                _sid(registro.get("canal_pai_id")),
                _sid(registro.get("parent_id")),
            }
            ids.discard("")
            if alvo and alvo in ids:
                return registro
            ativos.append(registro)

        if not ativos:
            return None

        # Se houver vários registros, tenta primeiro o mesmo pai/canal.
        pais = []
        for registro in ativos:
            if alvo and alvo in {
                _sid(registro.get("canal_pai_id")),
                _sid(registro.get("parent_id")),
            }:
                pais.append(registro)
        if len(pais) == 1:
            return pais[0]
        if pais:
            ativos = pais

        # Último fallback: o atendimento ativo mais recentemente criado/alterado.
        # Isso é intencional para Views antigas: a interação atual normalmente
        # pertence ao atendimento que acabou de ser aberto.
        return max(ativos, key=_timestamp)

    bot_module._pericia_por_topico = robust_lookup
    bot_module._V182_PERICIA_PATCHED = True
    print("✅ V182 Perícia: resolver tolerante a IDs legados + atendimento ativo mais recente.", flush=True)
    return True
