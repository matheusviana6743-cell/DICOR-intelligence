# -*- coding: utf-8 -*-
"""V184 — vínculo robusto das Views de Perícia ao registro correto."""
from __future__ import annotations

import asyncio
import re
import traceback
from typing import Any, Optional


def _sid(value: Any) -> str:
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def _active(record: dict) -> bool:
    return str(record.get("status") or "").upper() not in {
        "CONCLUIDA", "CONCLUÍDA", "CONCLUIDA_PEGO", "CONCLUIDA_COM_BO",
        "FINALIZADA", "FINALIZADO", "FECHADA", "FECHADO", "ENCERRADA", "ENCERRADO",
    }


def _number_from_message(message: Any) -> str:
    parts = []
    try:
        parts.append(str(getattr(message, "content", "") or ""))
        for embed in list(getattr(message, "embeds", []) or []):
            parts.extend([
                str(getattr(embed, "title", "") or ""),
                str(getattr(embed, "description", "") or ""),
            ])
            for field in list(getattr(embed, "fields", []) or []):
                parts.extend([
                    str(getattr(field, "name", "") or ""),
                    str(getattr(field, "value", "") or ""),
                ])
        channel = getattr(message, "channel", None)
        parts.append(str(getattr(channel, "name", "") or ""))
    except Exception:
        pass
    text = " ".join(parts)
    patterns = (
        r"PER[IÍ]CIA(?:\s+EXTERNA)?\s*(?:N[º°O.]|NÚMERO|NUMERO)?\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
        r"N[º°O.]?\s*(?:DA\s+)?PER[IÍ]CIA\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
        r"(?:PER[IÍ]CIA|PER[IÍ]CIA-EXTERNA|ATENDIMENTO[-_ ]?PER[IÍ]CIA)[^0-9]{0,20}([0-9]{1,8})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return re.sub(r"\s+", "", match.group(1)).strip("-/: ")
    return ""


def _channel_ids(interaction: Any) -> list[str]:
    message = getattr(interaction, "message", None)
    channel = getattr(message, "channel", None)
    result = []
    for value in (
        getattr(interaction, "channel_id", None),
        getattr(channel, "id", None),
        getattr(channel, "parent_id", None),
        getattr(getattr(channel, "parent", None), "id", None),
        getattr(message, "channel_id", None),
    ):
        sid = _sid(value)
        if sid and sid not in result:
            result.append(sid)
    return result


def install(bot_module) -> bool:
    discord = getattr(bot_module, "discord", None)
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    view_cls = getattr(bot_module, "PericiaAtendimentoView", None)
    carregar = getattr(bot_module, "_pericia_carregar", None)
    if discord is None or cls is None or not callable(carregar):
        print("⚠️ V184: componentes da Perícia indisponíveis; patch não aplicado.", flush=True)
        return False

    def records() -> list[dict]:
        try:
            data = carregar()
        except Exception:
            traceback.print_exc()
            return []
        if isinstance(data, dict):
            data = list(data.values())
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []

    def find_by_id(record_id: Any) -> Optional[dict]:
        wanted = str(record_id or "").strip()
        if not wanted:
            return None
        for record in reversed(records()):
            if str(record.get("id") or "").strip() == wanted:
                return record
        return None

    def resolve(interaction: Any, bound_id: Any = None) -> Optional[dict]:
        record = find_by_id(bound_id)
        if record:
            return record

        message = getattr(interaction, "message", None)
        mid = _sid(getattr(message, "id", None))
        channel_ids = _channel_ids(interaction)
        data = records()

        if mid:
            keys = {
                "painel_msg_id", "mensagem_painel_id", "mensagem_tarefa_id",
                "mensagem_abertura_id", "mensagem_original_id", "painel_id",
            }
            for record in reversed(data):
                if any(_sid(record.get(key)) == mid for key in keys):
                    return record

        keys = {
            "topico_id", "thread_id", "canal_atendimento_id", "canal_id",
            "atendimento_canal_id",
        }
        for cid in channel_ids:
            for record in reversed(data):
                if any(_sid(record.get(key)) == cid for key in keys):
                    return record

        number = _number_from_message(message)
        if number:
            normalize = getattr(bot_module, "_pericia_numero_chave", None)
            wanted = normalize(number) if callable(normalize) else number
            matches = []
            for record in data:
                if not _active(record):
                    continue
                value = record.get("numero_chave") or record.get("numero") or ""
                value = normalize(value) if callable(normalize) else str(value)
                if value and value == wanted:
                    matches.append(record)
            if len(matches) == 1:
                return matches[0]

        parents = set(channel_ids[1:])
        if parents:
            matches = []
            for record in data:
                if not _active(record):
                    continue
                rel = {
                    _sid(record.get("canal_pai_id")),
                    _sid(record.get("parent_id")),
                    _sid(record.get("thread_parent_id")),
                }
                if parents.intersection(rel):
                    matches.append(record)
            if len(matches) == 1:
                return matches[0]
        return None

    async def callback(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

        async def reply(text: str):
            try:
                await interaction.followup.send(text, ephemeral=True)
            except Exception:
                pass

        try:
            membro_check = getattr(bot_module, "_membro_inspetor_mais", None)
            if not isinstance(getattr(interaction, "user", None), discord.Member) or not callable(membro_check) or not membro_check(interaction.user):
                return await reply("❌ Apenas Inspetor+ pode escolher o responsável pela perícia.")

            bound_id = getattr(self, "_dicor_pericia_registro_id", "")
            registro = resolve(interaction, bound_id)
            if not registro:
                ids = ",".join(_channel_ids(interaction)) or "sem-id"
                print(
                    f"⚠️ V184 Perícia: atendimento não localizado; registro={bound_id or 'sem-vinculo'}; "
                    f"canais={ids}; mensagem={_sid(getattr(getattr(interaction, 'message', None), 'id', None))}; "
                    f"numero={_number_from_message(getattr(interaction, 'message', None)) or 'sem-numero'}",
                    flush=True,
                )
                return await reply("❌ Não foi possível localizar o atendimento desta perícia.")

            finais = getattr(bot_module, "_PERICIA_STATUS_FINAIS", set())
            if str(registro.get("status") or "").upper() in finais:
                return await reply("⚠️ Esta perícia já foi concluída.")

            escolhido = self.values[0] if self.values else None
            if escolhido is None:
                return await reply("❌ Selecione um agente válido.")
            if interaction.guild and not isinstance(escolhido, discord.Member):
                try:
                    escolhido = interaction.guild.get_member(int(escolhido.id)) or await interaction.guild.fetch_member(int(escolhido.id))
                except Exception:
                    escolhido = None
            if not isinstance(escolhido, discord.Member) or escolhido.bot:
                return await reply("❌ Selecione um agente válido.")

            equipe = getattr(bot_module, "usuario_tem_equipe", None)
            if callable(equipe) and callable(membro_check) and not equipe(escolhido) and not membro_check(escolhido):
                return await reply("❌ O membro selecionado não possui cargo da equipe DICOR.")

            registro.update({
                "agente_id": escolhido.id,
                "agente_nome": str(escolhido),
                "agente_escolhido_por_id": interaction.user.id,
                "agente_escolhido_por_nome": str(interaction.user),
                "agente_escolhido_em": getattr(bot_module, "agora_br", lambda: "")(),
                "status": "AGUARDANDO_BO" if str(registro.get("status") or "").upper() == "AGUARDANDO_BO" else "PENDENTE",
            })

            atualizar = getattr(bot_module, "_pericia_atualizar", None)
            if callable(atualizar):
                resultado = atualizar(registro)
                if hasattr(resultado, "__await__"):
                    await resultado

            obter_topico = getattr(bot_module, "_pericia_obter_topico", None)
            topico = await obter_topico(registro) if callable(obter_topico) else None
            if topico:
                try:
                    await topico.add_user(escolhido)
                except Exception:
                    pass
                try:
                    await topico.send(
                        f"{escolhido.mention}\n📌 **TAREFA PENDENTE — PERÍCIA Nº {registro.get('numero')}**\n"
                        "Você foi definido como responsável. Analise a perícia e responda pelo painel abaixo.",
                        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                    )
                except Exception:
                    pass

            atualizar_painel = getattr(bot_module, "_pericia_atualizar_painel", None)
            if callable(atualizar_painel):
                try:
                    resultado = atualizar_painel(registro)
                    if hasattr(resultado, "__await__"):
                        await resultado
                except Exception:
                    traceback.print_exc()

            await reply(f"✅ {escolhido.mention} foi definido como responsável pela Perícia Nº **{registro.get('numero')}**.")
            log = getattr(bot_module, "enviar_log", None)
            if callable(log):
                try:
                    resultado = log(f"👤 Responsável da Perícia `{registro.get('numero')}` definido: {escolhido.mention} por {interaction.user.mention}.")
                    if hasattr(resultado, "__await__"):
                        await resultado
                except Exception:
                    pass
        except Exception as exc:
            traceback.print_exc()
            await reply(f"❌ Ocorreu um erro ao processar a perícia. ({type(exc).__name__})")

    cls.callback = callback

    if view_cls is not None and not getattr(view_cls, "_dicor_v184_init_patched", False):
        original_init = view_cls.__init__

        def patched_init(self, registro=None, *args, **kwargs):
            original_init(self, registro, *args, **kwargs)
            rid = str((registro or {}).get("id") or "")
            for item in list(getattr(self, "children", []) or []):
                if isinstance(item, cls):
                    item._dicor_pericia_registro_id = rid
                    break

        view_cls.__init__ = patched_init
        view_cls._dicor_v184_init_patched = True

    client = getattr(bot_module, "bot", None)
    corrigidos = 0
    try:
        stores = [getattr(client, "persistent_views", None)]
        connection = getattr(client, "_connection", None)
        stores.extend([
            getattr(connection, "_view_store", None),
            getattr(client, "_view_store", None),
        ])
        seen = set()
        for store in stores:
            if store is None:
                continue
            views = getattr(store, "_views", store if isinstance(store, (list, tuple, set)) else [])
            candidates = list(views.values()) if isinstance(views, dict) else list(views or [])
            for view in candidates:
                if id(view) in seen:
                    continue
                seen.add(id(view))
                for item in list(getattr(view, "children", []) or []):
                    cid = str(getattr(item, "custom_id", "") or "")
                    if isinstance(item, cls) or cid.startswith("dicor_pericia_selecionar_agente"):
                        item.callback = callback.__get__(item, item.__class__)
                        corrigidos += 1
    except Exception:
        traceback.print_exc()

    bot_module._V184_STABILITY_INSTALLED = True
    print(f"✅ V184 Perícia: vínculo direto + recuperação de painéis antigos ativo; {corrigidos} controles persistentes corrigidos.", flush=True)
    return True
