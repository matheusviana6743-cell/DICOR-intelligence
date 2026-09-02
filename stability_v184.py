# -*- coding: utf-8 -*-
"""V184 — estabilidade antes do Gateway.

Correção da seleção de responsável da Perícia: o atendimento pode estar
vinculado ao tópico, à mensagem do painel ou ao canal pai. O resolvedor tenta
primeiro o resolvedor oficial já instalado e depois aplica fallbacks seguros.
"""
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
                parts.extend([str(getattr(field, "name", "") or ""), str(getattr(field, "value", "") or "")])
        channel = getattr(message, "channel", None)
        parts.append(str(getattr(channel, "name", "") or ""))
    except Exception:
        pass
    text = " ".join(parts)
    patterns = (
        r"PER[IÍ]CIA(?:\s+EXTERNA)?\s*(?:N[º°O.]|NÚMERO|NUMERO)?\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
        r"N[º°O.]?\s*(?:DA\s+)?PER[IÍ]CIA\s*[:#-]?\s*([0-9]{1,8}(?:\s*[-/]\s*[0-9]{2,4})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return re.sub(r"\s+", "", match.group(1)).strip("-/: ")
    return ""


def _candidate_channel_ids(interaction: Any) -> list[str]:
    ids = []
    message = getattr(interaction, "message", None)
    channel = getattr(message, "channel", None)
    for value in (
        getattr(interaction, "channel_id", None),
        getattr(channel, "id", None),
        getattr(channel, "parent_id", None),
        getattr(getattr(channel, "parent", None), "id", None),
        getattr(message, "channel_id", None),
    ):
        sid = _sid(value)
        if sid and sid not in ids:
            ids.append(sid)
    return ids


def install(bot_module) -> bool:
    discord = getattr(bot_module, "discord", None)
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    carregar = getattr(bot_module, "_pericia_carregar", None)
    if discord is None or cls is None or not callable(carregar):
        print("⚠️ V184: componentes da Perícia indisponíveis; patch não aplicado.", flush=True)
        return False

    def resolve(interaction: Any) -> Optional[dict]:
        message = getattr(interaction, "message", None)
        mid = _sid(getattr(message, "id", None))
        channel_ids = _candidate_channel_ids(interaction)

        # 0. Usa o resolvedor oficial/mais recente se algum patch anterior já o instalou.
        # Isso evita manter dois critérios diferentes para o mesmo atendimento.
        official = getattr(bot_module, "_pericia_por_topico", None)
        if callable(official):
            for cid in channel_ids:
                try:
                    record = official(cid)
                    if isinstance(record, dict):
                        return record
                except Exception:
                    pass

        try:
            records = carregar()
        except Exception:
            traceback.print_exc()
            records = []
        if isinstance(records, dict):
            # Alguns formatos antigos podem retornar {id: registro}.
            records = list(records.values())
        if not isinstance(records, list):
            records = []

        # 1. Mensagem do painel: identidade inequívoca.
        if mid:
            keys = {
                "painel_msg_id", "mensagem_painel_id", "mensagem_tarefa_id",
                "mensagem_abertura_id", "mensagem_original_id", "painel_id",
            }
            for record in reversed(records):
                if isinstance(record, dict) and any(_sid(record.get(key)) == mid for key in keys):
                    return record

        # 2. Tópico/thread/canal do atendimento e seus pais.
        keys = {
            "topico_id", "thread_id", "canal_atendimento_id", "canal_id",
            "canal_pai_id", "parent_id", "thread_parent_id", "atendimento_canal_id",
        }
        for cid in channel_ids:
            for record in reversed(records):
                if isinstance(record, dict) and any(_sid(record.get(key)) == cid for key in keys):
                    return record

        # 3. Número mostrado no painel.
        number = _number_from_message(message)
        if number:
            normalize = getattr(bot_module, "_pericia_numero_chave", None)
            wanted = normalize(number) if callable(normalize) else number
            matches = []
            for record in records:
                if not isinstance(record, dict) or not _active(record):
                    continue
                value = record.get("numero_chave") or record.get("numero") or ""
                value = normalize(value) if callable(normalize) else str(value)
                if value and value == wanted:
                    matches.append(record)
            if len(matches) == 1:
                return matches[0]

        # 4. Se houver um único atendimento ativo relacionado a algum canal pai.
        pais = set(channel_ids)
        if pais:
            matches = [
                r for r in records
                if isinstance(r, dict) and _active(r)
                and pais.intersection({
                    _sid(r.get("canal_pai_id")),
                    _sid(r.get("parent_id")),
                    _sid(r.get("thread_parent_id")),
                })
            ]
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

            registro = resolve(interaction)
            if not registro:
                ids = ",".join(_candidate_channel_ids(interaction)) or "sem-id"
                print(f"⚠️ V184 Perícia: atendimento não localizado; canais={ids}; mensagem={_sid(getattr(getattr(interaction, 'message', None), 'id', None))}", flush=True)
                return await reply("❌ Não foi possível localizar o atendimento desta perícia. Abra uma nova atualização do painel para continuar.")

            finais = getattr(bot_module, "_PERICIA_STATUS_FINAIS", set())
            if str(registro.get("status") or "").upper() in finais:
                return await reply("⚠️ Esta perícia já foi concluída.")

            escolhido = self.values[0] if self.values else None
            if interaction.guild and escolhido is not None and not isinstance(escolhido, discord.Member):
                try:
                    escolhido = interaction.guild.get_member(int(escolhido.id)) or await interaction.guild.fetch_member(int(escolhido.id))
                except Exception:
                    escolhido = None
            if not isinstance(escolhido, discord.Member) or escolhido.bot:
                return await reply("❌ Selecione um agente válido.")

            equipe = getattr(bot_module, "usuario_tem_equipe", None)
            inspetor = getattr(bot_module, "_membro_inspetor_mais", None)
            if (callable(equipe) and callable(inspetor)) and not equipe(escolhido) and not inspetor(escolhido):
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
                await asyncio.to_thread(atualizar, registro)

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
                    await atualizar_painel(registro)
                except Exception:
                    pass

            await reply(f"✅ {escolhido.mention} foi definido como responsável pela Perícia Nº **{registro.get('numero')}**.")
            log = getattr(bot_module, "enviar_log", None)
            if callable(log):
                try:
                    await log(f"👤 Responsável da Perícia `{registro.get('numero')}` definido: {escolhido.mention} por {interaction.user.mention}.")
                except Exception:
                    pass
        except Exception as exc:
            traceback.print_exc()
            await reply("❌ Não foi possível concluir a atribuição desta perícia. O bot continua online.")

    cls.callback = callback

    view_cls = getattr(bot_module, "PericiaAtendimentoView", None)
    if view_cls is not None:
        for name in ("pego", "nao_pego", "informar_bo"):
            original = getattr(view_cls, name, None)
            if original is None:
                continue
            try:
                setattr(original, "_dicor_v184_safe", True)
            except Exception:
                pass

    bot_module._V184_STABILITY_INSTALLED = True
    print("✅ V184 estabilidade aplicada ANTES do Gateway — seleção de Perícia vinculada à mensagem/painel.", flush=True)
    return True
