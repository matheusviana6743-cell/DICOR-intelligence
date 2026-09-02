# -*- coding: utf-8 -*-
"""V168 - restaura as Views persistentes da Central de Dados no Discord.

O painel antigo pode continuar visível no Discord depois de um restart, mas a
View que recebia os cliques deixa de existir em memória. Este módulo procura
em runtime a classe de View original do bot pelos labels/custom_ids e a
registra novamente com timeout=None.

Se a View original não puder ser reconstruída, o módulo instala uma View de
resgate no painel existente, garantindo que os cinco botões pelo menos
respondam e que o painel não fique com interação expirada.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any, Optional, Tuple

TARGET_LABELS = {
    "criar ficha",
    "pesquisar fichas",
    "buscar por imagem",
    "painel",
    "atualizar índice visual",
    "atualizar indice visual",
}
TARGET_WORDS = ("ficha", "imagem", "índice", "indice", "painel")


def _children(view: Any):
    try:
        return list(getattr(view, "children", []) or [])
    except Exception:
        return []


def _score_view(view: Any) -> int:
    score = 0
    labels = []
    for item in _children(view):
        label = str(getattr(item, "label", "") or "").strip().casefold()
        custom_id = str(getattr(item, "custom_id", "") or "").strip().casefold()
        if label:
            labels.append(label)
        if label in TARGET_LABELS:
            score += 10
        elif any(word in label for word in TARGET_WORDS):
            score += 2
        if any(word in custom_id for word in TARGET_WORDS):
            score += 2
    if len(labels) >= 4:
        score += 2
    return score


def _instantiate(cls: type) -> Optional[Any]:
    try:
        signature = inspect.signature(cls)
        required = [
            p for p in signature.parameters.values()
            if p.name != "self"
            and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
        ]
        if required:
            return None
    except Exception:
        pass
    try:
        return cls()
    except Exception:
        return None


def _find_best_view(bot_module: Any) -> Tuple[Optional[Any], int, str]:
    discord = getattr(bot_module, "discord", None)
    view_base = getattr(getattr(discord, "ui", None), "View", None)
    if view_base is None:
        return None, 0, "discord.ui.View indisponível"

    best = None
    best_score = 0
    best_name = ""
    for name, cls in list(vars(bot_module).items()):
        try:
            if not inspect.isclass(cls) or cls is view_base or not issubclass(cls, view_base):
                continue
        except Exception:
            continue
        view = _instantiate(cls)
        if view is None:
            continue
        score = _score_view(view)
        if score > best_score:
            best = view
            best_score = score
            best_name = name
    return best, best_score, best_name


def _fallback_view(bot_module: Any):
    discord = getattr(bot_module, "discord", None)
    if discord is None or not hasattr(discord, "ui"):
        return None
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    fichas_path = data_dir / "central_rescue_fichas_v168.json"

    def _load():
        try:
            raw = json.loads(fichas_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except Exception:
            return []

    def _save(data):
        try:
            fichas_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"⚠️ V168: não foi possível salvar ficha de resgate: {exc}", flush=True)

    class FichaModal(discord.ui.Modal, title="Nova ficha — Central DICOR"):
        nome = discord.ui.TextInput(label="Nome", placeholder="Nome completo", max_length=120)
        rg = discord.ui.TextInput(label="RG / Passaporte", placeholder="Identificação", max_length=60)
        informacoes = discord.ui.TextInput(
            label="Informações",
            placeholder="Observações da ficha",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1500,
        )

        async def on_submit(self, interaction):
            data = _load()
            data.append({
                "nome": str(self.nome.value).strip(),
                "rg": str(self.rg.value).strip(),
                "informacoes": str(self.informacoes.value).strip(),
                "autor_id": int(getattr(interaction.user, "id", 0) or 0),
                "autor": str(getattr(interaction.user, "display_name", interaction.user)),
            })
            _save(data)
            await interaction.response.send_message(
                "✅ Ficha criada e salva na Central. O módulo principal poderá sincronizá-la depois.",
                ephemeral=True,
            )

    class BuscaModal(discord.ui.Modal, title="Pesquisar fichas"):
        termo = discord.ui.TextInput(label="Nome ou RG", placeholder="Digite o termo", max_length=120)

        async def on_submit(self, interaction):
            termo = str(self.termo.value).strip().casefold()
            resultados = []
            for ficha in _load():
                hay = json.dumps(ficha, ensure_ascii=False).casefold()
                if termo and termo in hay:
                    resultados.append(ficha)
            if not resultados:
                texto = "🔎 Nenhuma ficha encontrada no índice de resgate."
            else:
                linhas = [f"• {x.get('nome','—')} — RG {x.get('rg','—')}" for x in resultados[:10]]
                texto = "🔎 Resultados:\n" + "\n".join(linhas)
            await interaction.response.send_message(texto, ephemeral=True)

    class RescueView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Criar ficha", style=discord.ButtonStyle.primary, custom_id="dicor_v168_criar_ficha")
        async def criar(self, interaction, button):
            await interaction.response.send_modal(FichaModal())

        @discord.ui.button(label="Pesquisar fichas", style=discord.ButtonStyle.secondary, custom_id="dicor_v168_pesquisar_fichas")
        async def pesquisar(self, interaction, button):
            await interaction.response.send_modal(BuscaModal())

        @discord.ui.button(label="Buscar por imagem", style=discord.ButtonStyle.secondary, custom_id="dicor_v168_buscar_imagem")
        async def imagem(self, interaction, button):
            await interaction.response.send_message(
                "🖼️ O botão está ativo. Envie a imagem no canal e use o módulo de busca visual da Central.",
                ephemeral=True,
            )

        @discord.ui.button(label="Painel", style=discord.ButtonStyle.secondary, custom_id="dicor_v168_painel")
        async def painel(self, interaction, button):
            url = str(getattr(bot_module, "CENTRAL_PUBLIC_URL", "https://dicor.up.railway.app") or "https://dicor.up.railway.app")
            await interaction.response.send_message(f"🌐 Central DICOR: {url}", ephemeral=True)

        @discord.ui.button(label="Atualizar índice visual", style=discord.ButtonStyle.secondary, custom_id="dicor_v168_atualizar_indice")
        async def atualizar(self, interaction, button):
            await interaction.response.defer(ephemeral=True)
            fn = getattr(bot_module, "_v162_refresh_procurados_ativos", None)
            if callable(fn):
                try:
                    await fn("botão V168")
                    await interaction.followup.send("✅ Índice visual atualizado.", ephemeral=True)
                    return
                except Exception as exc:
                    await interaction.followup.send(f"⚠️ Atualização não concluída: {type(exc).__name__}", ephemeral=True)
                    return
            await interaction.followup.send("ℹ️ O sincronizador visual ainda não está disponível.", ephemeral=True)

    return RescueView()


async def _find_panel_message(bot_module: Any):
    client = getattr(bot_module, "bot", None)
    if client is None:
        return None
    me = getattr(client, "user", None)
    for guild in list(getattr(client, "guilds", []) or []):
        for channel in list(getattr(guild, "text_channels", []) or []):
            if str(getattr(channel, "name", "") or "").casefold() != "banco-de-dados":
                continue
            try:
                async for message in channel.history(limit=25, oldest_first=False):
                    if me is not None and getattr(getattr(message, "author", None), "id", None) != getattr(me, "id", None):
                        continue
                    for embed in list(getattr(message, "embeds", []) or []):
                        title = str(getattr(embed, "title", "") or "").casefold()
                        if "central de dados" in title:
                            return message
            except Exception as exc:
                print(f"⚠️ V168: falha ao localizar painel: {type(exc).__name__}: {exc}", flush=True)
    return None


async def _restore_after_ready(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    await asyncio.sleep(1.5)

    view, score, name = _find_best_view(bot_module)
    if view is not None and score >= 10:
        try:
            view.timeout = None
            client.add_view(view)
            labels = [str(getattr(item, "label", "") or "").strip() for item in _children(view) if getattr(item, "label", None)]
            print(f"✅ V168: View original da Central restaurada: {name} | score={score} | botões={labels}", flush=True)
            bot_module._DICOR_V168_VIEW_RESTORED = True
            return
        except Exception as exc:
            print(f"⚠️ V168: View original encontrada, mas não pôde ser registrada: {type(exc).__name__}: {exc}", flush=True)

    try:
        fallback = _fallback_view(bot_module)
        if fallback is None:
            return
        client.add_view(fallback)
        message = await _find_panel_message(bot_module)
        if message is not None:
            await message.edit(view=fallback)
            bot_module._DICOR_V168_FALLBACK_ACTIVE = True
            print("✅ V168: painel da Central recebeu View de resgate persistente.", flush=True)
        else:
            print("⚠️ V168: View de resgate registrada, mas painel existente não foi localizado.", flush=True)
    except Exception as exc:
        print(f"❌ V168: falha no resgate dos botões: {type(exc).__name__}: {exc}", flush=True)


def install(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None or not hasattr(client, "add_listener"):
        print("⚠️ V168: cliente Discord indisponível; módulo ignorado.", flush=True)
        return

    async def _on_ready_v168() -> None:
        if getattr(bot_module, "_DICOR_V168_RESTORE_STARTED", False):
            return
        bot_module._DICOR_V168_RESTORE_STARTED = True
        asyncio.create_task(_restore_after_ready(bot_module))

    client.add_listener(_on_ready_v168, "on_ready")
    print("V168: restaurador de Views persistentes da Central armado.", flush=True)
