# -*- coding: utf-8 -*-
"""V182 - último nível de recuperação do atendimento de Perícia.

Se a View antiga chegar com um ID que não está mais gravado no registro,
mas existir apenas uma perícia ativa, essa perícia é o único candidato seguro.
Isso evita o falso "Atendimento da perícia não encontrado" causado por IDs
antigos de tópicos/views persistentes.
"""


def install(bot_module):
    carregar = getattr(bot_module, "_pericia_carregar", None)
    lookup = getattr(bot_module, "_pericia_por_topico", None)
    if not callable(carregar) or not callable(lookup):
        print("⚠️ V182: funções da Perícia não disponíveis.", flush=True)
        return False
    if getattr(bot_module, "_V182_PERICIA_PATCHED", False):
        return True

    finalizados = {
        "CONCLUIDA", "CONCLUÍDA", "CONCLUIDA_PEGO", "CONCLUIDA_COM_BO",
        "FINALIZADA", "FINALIZADO", "FECHADA", "FECHADO", "ENCERRADA", "ENCERRADO",
    }

    def robust_lookup(value):
        found = lookup(value)
        if found is not None:
            return found
        try:
            registros = carregar()
        except Exception:
            return None
        if not isinstance(registros, list):
            return None

        ativos = []
        for registro in registros:
            if not isinstance(registro, dict):
                continue
            status = str(registro.get("status") or "").strip().upper()
            if status not in finalizados:
                ativos.append(registro)

        # Último fallback: quando há exatamente uma perícia ativa, não existe
        # ambiguidade possível. É exatamente o atendimento que a View antiga
        # precisa recuperar.
        if len(ativos) == 1:
            return ativos[0]
        return None

    bot_module._pericia_por_topico = robust_lookup
    bot_module._V182_PERICIA_PATCHED = True
    print("✅ V182 Perícia: fallback único atendimento ativo habilitado.", flush=True)
    return True
