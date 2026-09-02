# -*- coding: utf-8 -*-
"""V186 — reparo direto de painéis antigos de Perícia.

Reassocia o painel existente ao registro e, quando o registro foi perdido,
reconstrói um registro mínimo a partir do próprio tópico/mensagem do painel.
"""
from __future__ import annotations

import re
import traceback
from typing import Any, Optional

TARGET_TOPIC_ID = 1541978969035771916
TARGET_PANEL_MESSAGE_ID = 1541979014372139050
TARGET_NUMBER = "0026"


def _sid(value: Any) -> str:
    try:
        return str(int(value)) if value is not None and str(value).strip() else ""
    except Exception:
        return str(value or "").strip()


def _normalize_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    m = re.search(r"\d{1,8}(?:\s*[-/]\s*\d{2,4})?", text)
    return re.sub(r"\s+", "", m.group(0)) if m else text


def _record_matches(record: dict, topic_id: str, panel_id: str, number: str) -> bool:
    ids = {
        _sid(record.get("topico_id")), _sid(record.get("thread_id")),
        _sid(record.get("canal_atendimento_id")), _sid(record.get("canal_id")),
        _sid(record.get("atendimento_canal_id")),
        _sid(record.get("painel_msg_id")), _sid(record.get("mensagem_painel_id")),
        _sid(record.get("mensagem_abertura_id")), _sid(record.get("mensagem_tarefa_id")),
        _sid(record.get("mensagem_original_id")),
    }
    if topic_id in ids or panel_id in ids:
        return True
    return _normalize_number(record.get("numero")) == number


def _extract_number(channel: Any, message: Any = None) -> str:
    chunks = []
    try:
        chunks.append(str(getattr(channel, "name", "") or ""))
        chunks.append(str(getattr(message, "content", "") or ""))
        for embed in list(getattr(message, "embeds", []) or []):
            chunks.extend([
                str(getattr(embed, "title", "") or ""),
                str(getattr(embed, "description", "") or ""),
            ])
            for field in list(getattr(embed, "fields", []) or []):
                chunks += [str(getattr(field, "name", "") or ""), str(getattr(field, "value", "") or "")]
    except Exception:
        pass
    text = " ".join(chunks)
    for pattern in (
        r"PER[IÍ]CIA(?:\s+EXTERNA)?[^0-9]{0,30}(\d{1,8}(?:\s*[-/]\s*\d{2,4})?)",
        r"N[º°O.]?[^0-9]{0,10}(\d{1,8})",
    ):
        m = re.search(pattern, text, flags=re.I)
        if m:
            return _normalize_number(m.group(1))
    return ""


def _load_records(bot_module) -> list[dict]:
    fn = getattr(bot_module, "_pericia_carregar", None)
    if not callable(fn):
        return []
    try:
        data = fn()
    except Exception:
        traceback.print_exc()
        return []
    if isinstance(data, dict):
        data = list(data.values())
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _persist(bot_module, record: dict) -> None:
    fn = getattr(bot_module, "_pericia_atualizar", None)
    if not callable(fn):
        return
    try:
        fn(record)
    except Exception:
        traceback.print_exc()


def _find_record(bot_module, topic_id: str, panel_id: str, number: str) -> Optional[dict]:
    for record in reversed(_load_records(bot_module)):
        if _record_matches(record, topic_id, panel_id, number):
            return record
    return None


def _rebuild_record(bot_module, channel: Any, panel_message: Any, topic_id: str, panel_id: str) -> dict:
    number = _extract_number(channel, panel_message) or TARGET_NUMBER
    guild = getattr(channel, "guild", None)
    parent = getattr(channel, "parent", None)
    parent_id = getattr(channel, "parent_id", None) or getattr(parent, "id", 0)
    original_id = 0
    try:
        refs = []
        refs.append(getattr(getattr(panel_message, "reference", None), "message_id", None))
        original_id = next((int(x) for x in refs if x), 0)
    except Exception:
        pass
    record = {
        "id": f"PERICIA-RECUPERADA-{number}-{topic_id}",
        "numero": number,
        "numero_chave": _normalize_number(number),
        "mensagem_original_id": original_id,
        "mensagens_origem_ids": [int(x) for x in [original_id, int(panel_id)] if x],
        "canal_pai_id": int(parent_id or 0),
        "guild_id": int(getattr(guild, "id", 0) or 0),
        "topico_id": int(topic_id),
        "thread_id": int(topic_id),
        "canal_atendimento_id": int(topic_id),
        "painel_msg_id": int(panel_id),
        "mensagem_painel_id": int(panel_id),
        "mensagem_abertura_id": int(panel_id),
        "mensagem_tarefa_id": None,
        "topico_privado": True,
        "status": "AGUARDANDO_AGENTE",
        "agente_id": None,
        "anexos_copiados": 0,
        "reconstruida_em": getattr(bot_module, "agora_br", lambda: "")(),
        "reconstruida_por_v186": True,
    }
    _persist(bot_module, record)
    print(f"✅ V186: registro reconstruído para Perícia {number} no tópico {topic_id}.", flush=True)
    return record


def _resolve_sync(bot_module, interaction: Any, bound_id: str = "") -> Optional[dict]:
    message = getattr(interaction, "message", None)
    channel = getattr(message, "channel", None)
    topic_id = _sid(getattr(interaction, "channel_id", None) or getattr(channel, "id", None))
    panel_id = _sid(getattr(message, "id", None))
    number = _extract_number(channel, message)

    if bound_id:
        rec = _find_record(bot_module, "", "", bound_id)
        if rec:
            return rec
    rec = _find_record(bot_module, topic_id, panel_id, number)
    if rec:
        return rec
    if topic_id == _sid(TARGET_TOPIC_ID) or panel_id == _sid(TARGET_PANEL_MESSAGE_ID) or _normalize_number(number) == TARGET_NUMBER:
        return _rebuild_record(bot_module, channel, message, topic_id or _sid(TARGET_TOPIC_ID), panel_id or _sid(TARGET_PANEL_MESSAGE_ID))
    return None


def _role_name_is_dicor(member: Any) -> bool:
    """Fallback para instalações onde os IDs de cargo não estão sincronizados.
    O nome do cargo continua sendo validado estritamente contra a equipe DICOR.
    """
    allowed = {
        "dicor", "estagiario", "estagiário", "investigador", "inspetor",
        "agente", "agente 1 classe", "agente 2 classe", "agente 3 classe",
        "escrivao", "escrivão", "delegado", "coordenador",
    }
    try:
        for role in list(getattr(member, "roles", []) or []):
            name = re.sub(r"\s+", " ", str(getattr(role, "name", "") or "").strip().lower())
            name = name.replace("º", "").replace("°", "")
            if name in allowed or ("dicor" in name and "estagi" in name):
                return True
    except Exception:
        pass
    return False


def install(bot_module) -> bool:
    discord = getattr(bot_module, "discord", None)
    cls = getattr(bot_module, "PericiaSelecionarAgente", None)
    if discord is None or cls is None:
        print("⚠️ V186: componentes da Perícia indisponíveis.", flush=True)
        return False

    # Corrige a validação global de equipe para instalações antigas onde os IDs
    # dos cargos não acompanham os cargos reais do servidor.
    original_equipe = getattr(bot_module, "usuario_tem_equipe", None)
    if callable(original_equipe) and not getattr(bot_module, "_V186_EQUIP_PATCHED", False):
        def usuario_tem_equipe_compat(member):
            try:
                if original_equipe(member):
                    return True
            except Exception:
                pass
            return _role_name_is_dicor(member)
        bot_module.usuario_tem_equipe = usuario_tem_equipe_compat
        bot_module._V186_EQUIP_PATCHED = True

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
            check = getattr(bot_module, "_membro_inspetor_mais", None)
            if not isinstance(getattr(interaction, "user", None), discord.Member) or not callable(check) or not check(interaction.user):
                return await reply("❌ Apenas Inspetor+ pode escolher o responsável pela perícia.")

            bound_id = str(getattr(self, "_dicor_pericia_registro_id", "") or "")
            registro = _resolve_sync(bot_module, interaction, bound_id)
            if not registro:
                return await reply("❌ Não foi possível recuperar esta perícia. O painel foi preservado para nova tentativa.")

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
            if callable(equipe) and not equipe(escolhido) and callable(check) and not check(escolhido):
                return await reply("❌ O membro selecionado não possui cargo da equipe DICOR.")

            registro.update({
                "agente_id": int(escolhido.id),
                "agente_nome": str(escolhido),
                "agente_escolhido_por_id": int(interaction.user.id),
                "agente_escolhido_por_nome": str(interaction.user),
                "agente_escolhido_em": getattr(bot_module, "agora_br", lambda: "")(),
                "status": "PENDENTE",
            })
            _persist(bot_module, registro)

            obter = getattr(bot_module, "_pericia_obter_topico", None)
            topico = await obter(registro) if callable(obter) else None
            if topico:
                try:
                    await topico.add_user(escolhido)
                except Exception:
                    pass
                try:
                    await topico.send(
                        f"{escolhido.mention}\n📌 **TAREFA PENDENTE — PERÍCIA Nº {registro.get('numero')}**\n"
                        "Você foi definido como responsável. Analise a perícia pelo painel abaixo.",
                        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                    )
                except Exception:
                    pass

            atualizar = getattr(bot_module, "_pericia_atualizar_painel", None)
            if callable(atualizar):
                try:
                    await atualizar(registro)
                except Exception:
                    traceback.print_exc()

            await reply(f"✅ {escolhido.mention} foi definido como responsável pela Perícia Nº **{registro.get('numero')}**.")
        except Exception as exc:
            traceback.print_exc()
            await reply(f"❌ Falha controlada ao atribuir a perícia: {type(exc).__name__}")

    cls.callback = callback

    view_cls = getattr(bot_module, "PericiaAtendimentoView", None)
    if view_cls is not None and not getattr(view_cls, "_v186_init_patched", False):
        original_init = view_cls.__init__
        def patched_init(self, registro=None, *args, **kwargs):
            original_init(self, registro, *args, **kwargs)
            rid = str((registro or {}).get("id") or "")
            for item in list(getattr(self, "children", []) or []):
                if isinstance(item, cls):
                    item._dicor_pericia_registro_id = rid
        view_cls.__init__ = patched_init
        view_cls._v186_init_patched = True

    async def repair_existing():
        client = getattr(bot_module, "bot", None)
        if client is None:
            return
        try:
            channel = client.get_channel(TARGET_TOPIC_ID)
            if channel is None:
                channel = await client.fetch_channel(TARGET_TOPIC_ID)
            message = await channel.fetch_message(TARGET_PANEL_MESSAGE_ID)
            record = _find_record(bot_module, _sid(TARGET_TOPIC_ID), _sid(TARGET_PANEL_MESSAGE_ID), TARGET_NUMBER)
            if not record:
                record = _rebuild_record(bot_module, channel, message, _sid(TARGET_TOPIC_ID), _sid(TARGET_PANEL_MESSAGE_ID))
            view = view_cls(record) if view_cls is not None else None
            if view is not None:
                for item in list(getattr(view, "children", []) or []):
                    if isinstance(item, cls):
                        item._dicor_pericia_registro_id = str(record.get("id") or "")
                        item.callback = callback.__get__(item, item.__class__)
                await message.edit(view=view)
                print(f"✅ V186: painel antigo da Perícia {TARGET_NUMBER} reanexado ao registro correto.", flush=True)
        except Exception as exc:
            print(f"⚠️ V186 reparo automático: {type(exc).__name__}: {exc}", flush=True)

    bot_module._V186_REPAIR_EXISTING_PERICIA = repair_existing
    bot_module._V186_PERICIA_INSTALLED = True
    print("✅ V186 Perícia instalado — equipe aceita por ID ou nome de cargo (inclui Estagiário).", flush=True)
    return True
