# -*- coding: utf-8 -*-
"""V163 - Central DICOR: visual PF preto/dourado, mídia ao vivo e acesso em camadas.

Instala uma camada web nova sem reescrever o bot.py gigante e sem tocar no dossiê.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

APPROVAL_PATHS = ("/boletins", "/pericias")
STRATEGIC_PATHS = ("/fichas", "/arvore")
PUBLIC_PREFIXES = (
    "/central/", "/uploads/", "/public/", "/catalogo-media/", "/favicon",
    "/health", "/healthz",
)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def install(bot_module) -> None:
    web = bot_module.web
    discord = bot_module.discord
    client = bot_module.bot

    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    access_file = data_dir / "central_access_v163.json"

    state: Dict[str, Any] = {
        "wanted_media": {},
        "pericias": [],
        "pericias_ready": False,
        "refresh_task": None,
        "loop_task": None,
        "pending_views_restored": False,
    }

    def _now() -> int:
        return int(time.time())

    def _escape(value: Any) -> str:
        return html.escape(str(value or ""))

    def _norm(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç]+", " ", text)
        return " ".join(text.split())

    def _record_message_id(registro: Dict[str, Any]) -> int:
        for key in (
            "mensagem_id", "publicacao_mensagem_id", "message_id",
            "discord_message_id", "procurado_mensagem_id",
        ):
            try:
                value = int(registro.get(key) or 0)
                if value:
                    return value
            except Exception:
                pass
        for key in ("mensagem_url", "jump_url", "publicacao_url", "url"):
            found = re.findall(r"(?<!\d)(\d{15,25})(?!\d)", str(registro.get(key) or ""))
            if found:
                try:
                    return int(found[-1])
                except Exception:
                    pass
        return 0

    def _flatten_dicts(value: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from _flatten_dicts(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from _flatten_dicts(child)

    def _first(record: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return str(value)
        return default

    def _candidate_image(value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, dict):
            for key in ("url", "proxy_url", "caminho", "path", "arquivo"):
                found = _candidate_image(value.get(key))
                if found:
                    return found
            return ""
        text = str(value).strip()
        low = text.lower().split("?", 1)[0]
        if text.startswith(("https://", "http://", "/")) and low.endswith(IMAGE_EXTS):
            return text
        if text.startswith(("https://", "http://")) and "cdn.discordapp.com/attachments/" in text:
            return text
        return ""

    def _record_images(record: Dict[str, Any]) -> List[str]:
        results: List[str] = []
        keys = (
            "foto", "foto_url", "imagem", "imagem_url", "foto_individuo", "foto_pessoa",
            "foto_rg", "rg_foto", "documento", "documento_url", "rg_url",
            "fotos", "imagens", "anexos", "attachments",
        )
        for key in keys:
            value = record.get(key)
            if isinstance(value, (list, tuple)):
                for item in value:
                    candidate = _candidate_image(item)
                    if candidate and candidate not in results:
                        results.append(candidate)
            else:
                candidate = _candidate_image(value)
                if candidate and candidate not in results:
                    results.append(candidate)
        return results

    def _message_images(message) -> List[str]:
        results: List[str] = []
        for attachment in list(getattr(message, "attachments", []) or []):
            url = str(getattr(attachment, "url", "") or "")
            content_type = str(getattr(attachment, "content_type", "") or "").lower()
            filename = str(getattr(attachment, "filename", "") or "").lower()
            if url and (content_type.startswith("image/") or filename.endswith(IMAGE_EXTS)):
                if url not in results:
                    results.append(url)
        for embed in list(getattr(message, "embeds", []) or []):
            for obj_name in ("image", "thumbnail"):
                obj = getattr(embed, obj_name, None)
                url = str(getattr(obj, "url", "") or "") if obj is not None else ""
                if url and url not in results:
                    results.append(url)
        return results

    async def _resolve_channel(channel_id: int):
        if not channel_id:
            return None
        channel = client.get_channel(int(channel_id))
        if channel is not None:
            return channel
        try:
            return await client.fetch_channel(int(channel_id))
        except Exception:
            return None

    def _guild_id() -> int:
        try:
            value = int(getattr(bot_module, "GUILD_ID", 0) or 0)
            if value:
                return value
        except Exception:
            pass
        guilds = list(getattr(client, "guilds", []) or [])
        return int(guilds[0].id) if guilds else 0

    async def _refresh_wanted_media() -> None:
        channel_id = int(getattr(bot_module, "PROCURADOS_CHANNEL_ID", 1490200533980545097) or 1490200533980545097)
        channel = await _resolve_channel(channel_id)
        if channel is None or not hasattr(channel, "history"):
            return
        mapping: Dict[int, Dict[str, Any]] = {}
        try:
            async for message in channel.history(limit=None, oldest_first=False):
                mapping[int(message.id)] = {
                    "images": _message_images(message),
                    "content": str(getattr(message, "content", "") or ""),
                    "jump_url": str(getattr(message, "jump_url", "") or ""),
                    "created_at": getattr(message, "created_at", None),
                }
        except Exception as exc:
            print(f"⚠️ V163: falha ao atualizar mídia dos procurados: {type(exc).__name__}: {exc}", flush=True)
            return
        state["wanted_media"] = mapping

    def _active_wanted() -> List[Dict[str, Any]]:
        base = getattr(bot_module, "_v43_procurados_ativos", None)
        try:
            records = list(base() if callable(base) else (bot_module.carregar_procurados() or []))
        except Exception:
            records = []
        enriched: List[Dict[str, Any]] = []
        for original in records:
            if not isinstance(original, dict):
                continue
            record = dict(original)
            message_id = _record_message_id(record)
            live = state["wanted_media"].get(message_id, {})
            live_images = list(live.get("images") or [])
            fallback_images = _record_images(record)
            images: List[str] = []
            for url in live_images + fallback_images:
                if url and url not in images:
                    images.append(url)
            record["_v163_images"] = images
            record["_v163_jump_url"] = live.get("jump_url") or _first(record, ("mensagem_url", "jump_url", "publicacao_url"))
            enriched.append(record)
        return enriched

    def _boletim_records() -> List[Dict[str, Any]]:
        fn = getattr(bot_module, "_v44_boletins_ativos_snapshot", None)
        if callable(fn):
            try:
                data = fn() or []
                if isinstance(data, list):
                    return [dict(x) for x in data if isinstance(x, dict)]
            except Exception:
                pass
        path = getattr(bot_module, "BOLETINS_JSON", None)
        if path:
            try:
                raw = bot_module.carregar_json(path, [])
                return list(_flatten_dicts(raw))
            except Exception:
                pass
        return []

    def _boletim_number(record: Dict[str, Any]) -> str:
        return _first(record, ("numero_boletim", "boletim_numero", "numero", "boletim", "bo", "protocolo"))

    def _discord_link_from_record(record: Dict[str, Any]) -> str:
        for key in (
            "mensagem_url", "jump_url", "url", "thread_url", "area_url",
            "boletim_url", "boletim_mensagem_url", "publicacao_url",
        ):
            value = str(record.get(key) or "").strip()
            if value.startswith("http"):
                return value
        guild_id = _guild_id()
        channel_id = 0
        message_id = 0
        for key in ("area_id", "thread_id", "canal_id", "channel_id"):
            try:
                channel_id = int(record.get(key) or 0)
            except Exception:
                channel_id = 0
            if channel_id:
                break
        for key in ("mensagem_id", "message_id", "publicacao_mensagem_id"):
            try:
                message_id = int(record.get(key) or 0)
            except Exception:
                message_id = 0
            if message_id:
                break
        if guild_id and channel_id:
            return f"https://discord.com/channels/{guild_id}/{channel_id}" + (f"/{message_id}" if message_id else "")
        return ""

    def _find_boletim(record: Dict[str, Any]) -> Tuple[str, str]:
        direct_number = _boletim_number(record)
        direct_link = _discord_link_from_record(record)
        if direct_number and direct_link:
            return direct_number, direct_link

        target_number = _norm(direct_number)
        target_rg = _norm(_first(record, ("rg", "passaporte", "registro_geral")))
        target_name = _norm(_first(record, ("nome", "nome_completo", "procurado")))
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        for item in _boletim_records():
            score = 0
            number = _norm(_boletim_number(item))
            rg = _norm(_first(item, ("rg", "passaporte", "suspeito_rg", "procurado_rg")))
            name = _norm(_first(item, ("nome", "suspeito", "suspeito_nome", "procurado")))
            hay = _norm(json.dumps(item, ensure_ascii=False, default=str))
            if target_number and target_number == number:
                score += 10
            elif target_number and target_number in hay:
                score += 7
            if target_rg and (target_rg == rg or target_rg in hay):
                score += 5
            if target_name and len(target_name) >= 4 and (target_name == name or target_name in hay):
                score += 3
            if score > best_score:
                best, best_score = item, score
        if best is not None and best_score >= 5:
            return _boletim_number(best) or direct_number, _discord_link_from_record(best) or direct_link
        return direct_number, direct_link

    async def _scan_thread(thread) -> Optional[Dict[str, Any]]:
        messages = []
        try:
            async for message in thread.history(limit=100, oldest_first=True):
                messages.append(message)
        except Exception:
            return None
        text_parts: List[str] = []
        images: List[str] = []
        jump_url = ""
        for message in messages:
            content = str(getattr(message, "content", "") or "").strip()
            if content:
                text_parts.append(content)
            for url in _message_images(message):
                if url not in images:
                    images.append(url)
            if not jump_url:
                jump_url = str(getattr(message, "jump_url", "") or "")
        if not text_parts and not images:
            return None
        return {
            "title": str(getattr(thread, "name", "") or "Perícia"),
            "content": "\n\n".join(text_parts),
            "images": images,
            "jump_url": jump_url or f"https://discord.com/channels/{_guild_id()}/{getattr(thread, 'id', 0)}",
        }

    async def _refresh_pericias() -> None:
        channel_ids: List[int] = []
        for attr in ("PERICIAS_CHANNEL_ID", "PERICIA_FLUXO_CHANNEL_ID", "BANCO_PERICIA_CHANNEL_ID"):
            try:
                value = int(getattr(bot_module, attr, 0) or 0)
                if value and value not in channel_ids:
                    channel_ids.append(value)
            except Exception:
                pass

        records: List[Dict[str, Any]] = []
        seen_threads = set()
        seen_links = set()

        async def add_channel(channel) -> None:
            if channel is None:
                return
            threads = list(getattr(channel, "threads", []) or [])
            for thread in threads:
                try:
                    seen_threads.add(int(thread.id))
                except Exception:
                    pass
                item = await _scan_thread(thread)
                if item and item.get("jump_url") not in seen_links:
                    seen_links.add(item.get("jump_url"))
                    records.append(item)

            archived = getattr(channel, "archived_threads", None)
            if callable(archived):
                try:
                    count = 0
                    async for thread in archived(limit=50):
                        if int(getattr(thread, "id", 0) or 0) in seen_threads:
                            continue
                        item = await _scan_thread(thread)
                        if item and item.get("jump_url") not in seen_links:
                            seen_links.add(item.get("jump_url"))
                            records.append(item)
                        count += 1
                        if count >= 50:
                            break
                except Exception:
                    pass

            if not threads and hasattr(channel, "history"):
                try:
                    async for message in channel.history(limit=120, oldest_first=False):
                        content = str(getattr(message, "content", "") or "").strip()
                        images = _message_images(message)
                        if not content and not images:
                            continue
                        jump = str(getattr(message, "jump_url", "") or "")
                        if jump and jump in seen_links:
                            continue
                        if jump:
                            seen_links.add(jump)
                        title = content.splitlines()[0][:90] if content else "Perícia externa"
                        records.append({
                            "title": title,
                            "content": content,
                            "images": images,
                            "jump_url": jump,
                        })
                except Exception as exc:
                    print(f"⚠️ V163: falha ao ler perícias: {type(exc).__name__}: {exc}", flush=True)

        for channel_id in channel_ids:
            await add_channel(await _resolve_channel(channel_id))

        state["pericias"] = records[:100]
        state["pericias_ready"] = True
        print(f"✅ V163: perícias sincronizadas com {len(state['pericias'])} registro(s) e mídia do Discord.", flush=True)

    async def _refresh_all(reason: str = "") -> None:
        try:
            await _refresh_wanted_media()
            await _refresh_pericias()
        except Exception as exc:
            print(f"⚠️ V163 refresh ({reason}): {type(exc).__name__}: {exc}", flush=True)

    async def _refresh_loop() -> None:
        while True:
            await asyncio.sleep(45)
            await _refresh_all("loop")

    access_lock = asyncio.Lock()

    def _load_access() -> List[Dict[str, Any]]:
        try:
            if access_file.exists():
                raw = json.loads(access_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [x for x in raw if isinstance(x, dict)]
        except Exception:
            pass
        return []

    def _save_access(items: List[Dict[str, Any]]) -> None:
        tmp = access_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, access_file)

    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _find_access_by_id(request_id: str) -> Optional[Dict[str, Any]]:
        async with access_lock:
            for item in _load_access():
                if str(item.get("id")) == str(request_id):
                    return item
        return None

    async def _find_approved_token(token: str, module: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        digest = _token_hash(token)
        now = _now()
        async with access_lock:
            items = _load_access()
        for item in reversed(items):
            if item.get("token_hash") != digest:
                continue
            if item.get("module") != module:
                continue
            if item.get("status") != "approved":
                continue
            if int(item.get("expires_at") or 0) < now:
                continue
            return item
        return None

    async def _update_access(request_id: str, status: str, approver: str = "") -> Optional[Dict[str, Any]]:
        async with access_lock:
            items = _load_access()
            found = None
            for item in items:
                if str(item.get("id")) == str(request_id):
                    item["status"] = status
                    item["decided_at"] = _now()
                    item["decided_by"] = approver
                    found = dict(item)
                    break
            _save_access(items)
        return found

    def _approval_channel_id() -> int:
        for attr in ("AUTORIZACOES_CHANNEL_ID", "SET_APROVACAO_CHANNEL_ID", "LOGS_CHANNEL_ID", "BOLETIM_ATENDIMENTO_CHANNEL_ID"):
            try:
                value = int(getattr(bot_module, attr, 0) or 0)
                if value:
                    return value
            except Exception:
                pass
        return 0

    def _is_approver(member) -> bool:
        allowed_ids = set()
        for attr in ("INSPETOR_BAIANO_USER_ID", "DIRETOR_GERAL_USER_ID", "DIRETOR_DICOR_USER_ID"):
            try:
                value = int(getattr(bot_module, attr, 0) or 0)
                if value:
                    allowed_ids.add(value)
            except Exception:
                pass
        member_id = int(getattr(member, "id", 0) or 0)
        if allowed_ids:
            return member_id in allowed_ids
        fn = getattr(bot_module, "usuario_e_administrador", None)
        if callable(fn):
            try:
                return bool(fn(member))
            except Exception:
                pass
        return False

    def _module_label(module: str) -> str:
        return {"boletins": "Boletins", "pericias": "Perícias"}.get(module, module.title())

    class ApprovalView(discord.ui.View):
        def __init__(self, request_id: str):
            super().__init__(timeout=None)
            self.request_id = str(request_id)
            approve = discord.ui.Button(
                label="Aprovar acesso", emoji="✅", style=discord.ButtonStyle.success,
                custom_id=f"dicor_v163_access_approve:{self.request_id}",
            )
            deny = discord.ui.Button(
                label="Negar acesso", emoji="⛔", style=discord.ButtonStyle.danger,
                custom_id=f"dicor_v163_access_deny:{self.request_id}",
            )

            async def approve_cb(interaction):
                if not _is_approver(interaction.user):
                    return await interaction.response.send_message("❌ Você não pode autorizar acessos da Central.", ephemeral=True)
                updated = await _update_access(self.request_id, "approved", str(interaction.user))
                if not updated:
                    return await interaction.response.send_message("❌ Solicitação não encontrada.", ephemeral=True)
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed(title="Acesso aprovado")
                embed.color = discord.Color.green()
                embed.add_field(name="DECISÃO", value=f"✅ APROVADO por {interaction.user.mention}", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)

            async def deny_cb(interaction):
                if not _is_approver(interaction.user):
                    return await interaction.response.send_message("❌ Você não pode negar acessos da Central.", ephemeral=True)
                updated = await _update_access(self.request_id, "denied", str(interaction.user))
                if not updated:
                    return await interaction.response.send_message("❌ Solicitação não encontrada.", ephemeral=True)
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed(title="Acesso negado")
                embed.color = discord.Color.red()
                embed.add_field(name="DECISÃO", value=f"⛔ NEGADO por {interaction.user.mention}", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)

            approve.callback = approve_cb
            deny.callback = deny_cb
            self.add_item(approve)
            self.add_item(deny)

    async def _send_approval(record: Dict[str, Any]) -> bool:
        channel = await _resolve_channel(_approval_channel_id())
        if channel is None or not hasattr(channel, "send"):
            return False
        embed = discord.Embed(
            title="🔐 Solicitação de acesso à Central DICOR",
            description=f"Pedido para acessar **{_module_label(record['module'])}**.",
            color=discord.Color.from_rgb(201, 162, 39),
        )
        embed.add_field(name="QRA / NOME", value=str(record.get("qra") or "Não informado")[:1024], inline=True)
        embed.add_field(name="PASSAPORTE", value=str(record.get("passaporte") or "Não informado")[:1024], inline=True)
        embed.add_field(name="DISCORD", value=str(record.get("discord") or "Não informado")[:1024], inline=True)
        embed.add_field(name="MOTIVO", value=str(record.get("motivo") or "Não informado")[:1024], inline=False)
        embed.set_footer(text=f"Central DICOR • Solicitação {record['id']}")
        try:
            message = await channel.send(embed=embed, view=ApprovalView(record["id"]))
        except Exception as exc:
            print(f"⚠️ V163: falha ao enviar aprovação: {type(exc).__name__}: {exc}", flush=True)
            return False
        async with access_lock:
            items = _load_access()
            for item in items:
                if str(item.get("id")) == str(record["id"]):
                    item["discord_message_id"] = int(message.id)
                    item["approval_channel_id"] = int(channel.id)
                    break
            _save_access(items)
        return True

    def _strategic_password() -> str:
        return (
            os.getenv("CENTRAL_ESTRATEGICA_PASSWORD", "").strip()
            or os.getenv("PLATAFORMA_DONO_PASSWORD", "").strip()
            or os.getenv("CENTRAL_DICOR_PASSWORD", "").strip()
        )

    def _cookie_secret() -> bytes:
        secret = (
            os.getenv("CENTRAL_DICOR_COOKIE_SECRET", "").strip()
            or os.getenv("PLATAFORMA_DONO_PASSWORD", "").strip()
            or os.getenv("CENTRAL_DICOR_PASSWORD", "").strip()
            or "dicor-v163-fallback-secret-change-me"
        )
        return secret.encode("utf-8")

    def _make_strategic_cookie() -> str:
        expiry = _now() + 12 * 3600
        payload = f"strategic:{expiry}"
        sig = hmac.new(_cookie_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{expiry}.{sig}"

    def _valid_strategic_cookie(value: str) -> bool:
        try:
            expiry_text, sig = str(value or "").split(".", 1)
            expiry = int(expiry_text)
            if expiry < _now():
                return False
            payload = f"strategic:{expiry}"
            expected = hmac.new(_cookie_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    BASE_CSS = """
:root{--gold:#c9a227;--gold2:#f0d878;--gold3:#806714;--black:#050505;--panel:#0b0b09;--panel2:#10100c;--line:#3b3219;--text:#f5f0df;--muted:#aaa48f;--danger:#8e2d27}
*{box-sizing:border-box}html{background:var(--black)}body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -10%,#7e641527,transparent 32%),linear-gradient(180deg,#070705,#030303 58%,#050504);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
a{color:inherit}.topbar{min-height:106px;border-bottom:1px solid #4a3c1b;background:#050504ef;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:12px 5vw;position:sticky;top:0;z-index:20;backdrop-filter:blur(15px)}.brand{grid-column:2;display:flex;align-items:center;gap:17px}.brand img{width:72px;height:72px;object-fit:contain;filter:drop-shadow(0 0 20px #c9a2271d)}.brand h1{font-family:Georgia,serif;font-size:20px;letter-spacing:2px;margin:0}.brand small{display:block;color:var(--gold);letter-spacing:1.7px;font-size:10px;margin-top:5px}.top-right{justify-self:end;color:#8f8974;font-size:10px;letter-spacing:1.3px}.wrap{max-width:1360px;margin:0 auto;padding:54px 24px 76px}.eyebrow{font-size:10px;letter-spacing:2.4px;color:var(--gold)}.hero{text-align:center;max-width:950px;margin:6px auto 48px}.hero h2{font-family:Georgia,serif;font-size:50px;line-height:1.05;margin:12px 0 14px;font-weight:600}.hero h2 span{color:var(--gold2)}.hero p{color:#bbb49f;line-height:1.65;font-size:16px}.gold-rule{width:96px;height:2px;background:linear-gradient(90deg,transparent,var(--gold2),transparent);margin:22px auto}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.module{min-height:230px;padding:27px 27px 25px;border:1px solid #373018;border-radius:18px;background:linear-gradient(150deg,#11110d,#090906);position:relative;overflow:hidden;transition:.18s}.module:before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(var(--gold2),#7f6414)}.module:hover{transform:translateY(-3px);border-color:#6e5719;box-shadow:0 18px 50px #0009}.module .icon{font-size:26px}.module h3{font-family:Georgia,serif;font-size:22px;margin:19px 0 8px}.module p{color:#a9a28f;line-height:1.55;min-height:70px}.badge{position:absolute;right:15px;top:15px;border:1px solid #5c4a1c;border-radius:99px;padding:5px 8px;color:#d8c26d;font-size:8px;letter-spacing:1.2px}.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid #a9841c;background:linear-gradient(135deg,#f0d878,#c79c22);color:#0b0a05;text-decoration:none;padding:11px 15px;border-radius:9px;font-weight:900}.btn.dark{background:#14130c;color:#f0d878;border-color:#70591b}.section{margin-top:48px}.section-title{font-family:Georgia,serif;font-size:30px;margin:0 0 20px}.search{width:100%;background:#0b0b08;border:1px solid #4d401c;border-radius:11px;padding:13px 15px;color:#fff;font-size:15px;outline:none}.search:focus{border-color:var(--gold)}.empty{border:1px dashed #4a3d1a;border-radius:18px;padding:55px;text-align:center;color:#8e8875}.back{display:inline-flex;margin-bottom:24px;color:#d9c46f;text-decoration:none;font-size:13px}.form-shell{max-width:560px;margin:55px auto;padding:0 20px}.form-card{border:1px solid #493a18;border-radius:22px;background:linear-gradient(155deg,#11110d,#090906);padding:34px;box-shadow:0 30px 90px #000a}.form-card .seal{width:82px;height:82px;margin:0 auto 22px;display:grid;place-items:center}.form-card .seal img{width:100%;height:100%;object-fit:contain}.form-card h2{font-family:Georgia,serif;font-size:30px;text-align:center;margin:5px 0}.form-card>p{text-align:center;color:#aaa38e;line-height:1.55}.field{margin-top:15px}.field label{display:block;color:#c7b46a;font-size:10px;letter-spacing:1.4px;margin-bottom:7px}.field input,.field textarea{width:100%;background:#050504;border:1px solid #3d341c;color:#fff;border-radius:9px;padding:13px 14px;font-size:15px;outline:none}.field textarea{min-height:95px;resize:vertical}.field input:focus,.field textarea:focus{border-color:var(--gold)}button.btn{cursor:pointer;font-size:14px;margin-top:20px}.notice{border:1px solid #4f421d;background:#151208;border-radius:11px;padding:13px;margin:18px 0;color:#d9cfac;line-height:1.5}.notice.danger{border-color:#73332f;background:#1f0e0c;color:#f2c3bf}.notice.ok{border-color:#4c5a2b;background:#11180c;color:#d3e6b9}.cards-2{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
@media(max-width:950px){.grid{grid-template-columns:1fr 1fr}.top-right{display:none}.cards-2{grid-template-columns:1fr}}@media(max-width:620px){.topbar{grid-template-columns:1fr}.brand{grid-column:1}.grid{grid-template-columns:1fr}.hero h2{font-size:36px}.wrap{padding:38px 15px}.form-card{padding:25px}.brand img{width:58px;height:58px}}
"""

    def _shell(title: str, body: str, *, top_right: str = "SISTEMA OPERACIONAL") -> str:
        return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_escape(title)}</title><style>{BASE_CSS}</style></head><body>
<header class="topbar"><div></div><div class="brand"><img src="/central/brasao-dicor.png" alt="Brasão DICOR"><div><h1>POLÍCIA FEDERAL — DICOR</h1><small>CENTRAL DE INTELIGÊNCIA</small></div></div><div class="top-right">{_escape(top_right)}</div></header>{body}</body></html>'''

    async def central_portal_http(request):
        wanted_count = len(_active_wanted())
        cards = [
            ("🎯", "Procurados", f"{wanted_count} registro(s) confirmado(s) no canal oficial.", "/catalogo", "Consultar procurados", "PÚBLICO"),
            ("🗃️", "Banco de Dados", "Fichas, veículos, organizações, evidências e histórico investigativo.", "/fichas", "Acessar banco", "SENHA RESERVADA"),
            ("🧬", "Árvore de Inteligência", "Conexões entre indivíduos, veículos, ocorrências e organizações.", "/arvore", "Abrir inteligência", "SENHA RESERVADA"),
            ("📋", "Boletins", "Consulta interna dos boletins e anexos operacionais.", "/boletins", "Solicitar acesso", "AUTORIZAÇÃO"),
            ("🧪", "Perícias", "Relatórios, laudos e fotografias vinculadas às perícias.", "/pericias", "Solicitar acesso", "AUTORIZAÇÃO"),
        ]
        rendered = "".join(
            f'''<article class="module"><span class="badge">{badge}</span><div class="icon">{icon}</div><h3>{_escape(name)}</h3><p>{_escape(desc)}</p><a class="btn" href="{link}">{_escape(button)}</a></article>'''
            for icon, name, desc, link, button, badge in cards
        )
        body = f'''<main class="wrap"><section class="hero"><div class="eyebrow">DEPARTAMENTO DE INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</div><h2>Central Operacional <span>DICOR</span></h2><div class="gold-rule"></div><p>Ambiente unificado da Polícia Federal — DICOR, com acesso separado de acordo com o nível de sensibilidade de cada módulo.</p></section><section class="grid">{rendered}</section></main>'''
        return web.Response(text=_shell("Central DICOR", body), content_type="text/html", charset="utf-8")

    def _catalog_card(record: Dict[str, Any]) -> str:
        images = list(record.get("_v163_images") or [])
        photo = images[0] if len(images) > 0 else ""
        doc = images[1] if len(images) > 1 else ""
        nome = _first(record, ("nome", "nome_completo", "procurado"), "Não informado")
        rg = _first(record, ("rg", "passaporte", "registro_geral"), "Não informado")
        crimes = _first(record, ("crimes", "crime", "infracoes", "infrações"), "Não informado")
        last = _first(record, ("ultimo_avistamento", "informacoes", "localizacao"), "Não informado")
        case = _first(record, ("numero_caso", "caso", "id", "codigo"), "—")
        bo_number, bo_link = _find_boletim(record)
        photo_html = f'<img src="{_escape(photo)}" alt="Foto de {_escape(nome)}" loading="lazy">' if photo else '<div class="no-photo">SEM IMAGEM<br><small>FOTO DO INDIVÍDUO</small></div>'
        doc_html = f'<img src="{_escape(doc)}" alt="Documento de {_escape(nome)}" loading="lazy">' if doc else '<div class="no-photo">SEM IMAGEM<br><small>DOCUMENTO / RG</small></div>'
        bo_html = f'<a class="bo-link" href="{_escape(bo_link)}" target="_blank" rel="noopener">📋 {_escape(bo_number or "Abrir boletim vinculado")}</a>' if bo_link else f'<span class="bo-missing">📋 {_escape(bo_number or "Boletim não localizado")}</span>'
        search = _escape(_norm(" ".join((nome, rg, crimes, last, bo_number))))
        return f'''<article class="wanted" data-search="{search}"><div class="case"><div><small>NÚMERO DO CASO</small><b>{_escape(case)}</b></div><span>A PROCURAR</span></div><div class="wanted-grid"><div class="media"><figure><figcaption>01 • FOTO DO INDIVÍDUO</figcaption>{photo_html}</figure><figure><figcaption>02 • DOCUMENTO / RG</figcaption>{doc_html}</figure></div><div class="wanted-info"><small>IDENTIFICAÇÃO DO PROCURADO</small><h2>{_escape(nome)}</h2><strong class="rg">RG • {_escape(rg)}</strong><div class="danger-box"><small>CRIMES REGISTRADOS</small><p>{_escape(crimes)}</p>{bo_html}</div><div class="info-box"><small>ÚLTIMO AVISTAMENTO</small><p>{_escape(last)}</p></div></div></div></article>'''

    async def pagina_inicial(request):
        records = _active_wanted()
        cards = "".join(_catalog_card(x) for x in records) or '<div class="empty">Nenhum procurado ativo no canal oficial.</div>'
        extra = """
<style>.catalog-head{display:flex;gap:16px;align-items:end;justify-content:space-between;margin-bottom:22px}.catalog-head h2{font-family:Georgia,serif;font-size:38px;margin:5px 0}.wanted-list{display:grid;gap:22px}.wanted{border:1px solid #393019;border-radius:18px;overflow:hidden;background:#0a0a07}.case{display:flex;justify-content:space-between;align-items:center;padding:15px 20px;border-bottom:1px solid #3c3218;background:#0d0d09}.case small,.wanted-info>small,.danger-box small,.info-box small{display:block;color:#d7a93d;font-size:9px;letter-spacing:1.6px}.case b{font-size:13px}.case>span{font-size:9px;letter-spacing:1.4px;border:1px solid #763d33;background:#24100e;color:#f1c0b8;border-radius:99px;padding:7px 10px}.wanted-grid{display:grid;grid-template-columns:1.7fr .8fr}.media{display:grid;grid-template-columns:1fr 1fr;min-height:480px;border-right:1px solid #393019}.media figure{margin:0;position:relative;background:#030303;min-width:0;overflow:hidden;border-right:1px solid #393019}.media figure:last-child{border-right:0}.media figcaption{position:absolute;top:14px;left:14px;z-index:3;background:#0b0a06e8;border:1px solid #5d4a1d;border-radius:7px;padding:7px 9px;color:#e7cf73;font-size:9px;letter-spacing:1.2px}.media img{width:100%;height:100%;object-fit:cover}.media figure:nth-child(2) img{object-fit:contain}.no-photo{height:100%;display:grid;place-items:center;text-align:center;color:#716b5c;font-size:12px;letter-spacing:2px}.no-photo small{font-size:8px}.wanted-info{padding:28px}.wanted-info h2{font-family:Georgia,serif;font-size:34px;margin:7px 0 10px}.rg{display:inline-block;border:1px solid #6b551d;background:#171207;color:#f0d878;padding:8px 10px;border-radius:8px}.danger-box,.info-box{margin-top:17px;border:1px solid #4d2520;border-radius:12px;background:#1b0c0a;padding:15px}.info-box{border-color:#393019;background:#10100c}.danger-box p,.info-box p{color:#d9d2bd;line-height:1.55}.bo-link,.bo-missing{display:block;margin-top:13px;color:#f0d878;text-decoration:none}.bo-link:hover{text-decoration:underline}.bo-missing{color:#8f8874}@media(max-width:950px){.wanted-grid{grid-template-columns:1fr}.media{border-right:0;border-bottom:1px solid #393019}}@media(max-width:620px){.media{grid-template-columns:1fr;min-height:760px}.catalog-head{display:block}.media figure{min-height:380px;border-right:0;border-bottom:1px solid #393019}}</style>
<script>document.addEventListener('DOMContentLoaded',()=>{const q=document.getElementById('q');q.addEventListener('input',()=>{const v=q.value.toLowerCase();document.querySelectorAll('.wanted').forEach(c=>c.style.display=c.dataset.search.includes(v)?'block':'none')})})</script>"""
        body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><div class="catalog-head"><div><div class="eyebrow">CONSULTA PÚBLICA OFICIAL</div><h2>Procurados</h2><p style="color:#aaa38e">Somente indivíduos presentes no canal oficial ativo.</p></div><div style="min-width:min(430px,100%)"><input id="q" class="search" placeholder="Pesquisar por nome, RG, crime ou boletim"></div></div><section class="wanted-list">{cards}</section></main>{extra}'''
        return web.Response(text=_shell("Procurados • DICOR", body), content_type="text/html", charset="utf-8")

    def _boletim_card(record: Dict[str, Any]) -> str:
        numero = _boletim_number(record) or "Boletim"
        status = _first(record, ("status", "situacao", "estado"), "EM ACOMPANHAMENTO")
        summary = _first(record, ("resumo", "descricao", "texto", "relato", "conteudo"), "Sem resumo disponível.")
        link = _discord_link_from_record(record)
        open_link = f'<a class="btn dark" href="{_escape(link)}" target="_blank" rel="noopener">Abrir no Discord</a>' if link else ''
        return f'''<article class="module" style="min-height:250px"><span class="badge">{_escape(status)}</span><div class="icon">📋</div><h3>{_escape(numero)}</h3><p>{_escape(summary[:650])}</p>{open_link}</article>'''

    async def central_boletins_http(request):
        records = _boletim_records()
        useful = []
        seen = set()
        for item in records:
            number = _boletim_number(item)
            link = _discord_link_from_record(item)
            summary = _first(item, ("resumo", "descricao", "texto", "relato", "conteudo"))
            key = (_norm(number), link)
            if key in seen or (not number and not summary and not link):
                continue
            seen.add(key)
            useful.append(item)
        cards = "".join(_boletim_card(x) for x in useful[:60]) or '<div class="empty">Nenhum boletim disponível.</div>'
        body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><section class="hero" style="margin-bottom:30px"><div class="eyebrow">ÁREA AUTORIZADA</div><h2>Boletins <span>Operacionais</span></h2><p>Consulta interna dos registros e links oficiais no Discord.</p></section><section class="grid">{cards}</section></main>'''
        return web.Response(text=_shell("Boletins • DICOR", body), content_type="text/html", charset="utf-8")

    def _pericia_card(item: Dict[str, Any]) -> str:
        title = str(item.get("title") or "Perícia")
        content = str(item.get("content") or "Sem descrição disponível.")
        images = list(item.get("images") or [])[:8]
        link = str(item.get("jump_url") or "")
        gallery = "".join(f'<button class="photo" type="button" onclick="openImg(this.dataset.src)" data-src="{_escape(url)}"><img src="{_escape(url)}" loading="lazy" alt="Anexo de perícia"></button>' for url in images)
        if not gallery:
            gallery = '<div class="no-media">Nenhuma foto vinculada a esta perícia.</div>'
        open_link = f'<a class="btn dark" href="{_escape(link)}" target="_blank" rel="noopener">Abrir perícia no Discord</a>' if link else ''
        return f'''<article class="pericia-card"><div class="pericia-text"><small>RELATÓRIO DE PERÍCIA</small><h2>{_escape(title)}</h2><div class="pericia-body">{_escape(content)}</div>{open_link}</div><div class="gallery">{gallery}</div></article>'''

    async def central_pericias_http(request):
        if not state["pericias_ready"]:
            await _refresh_pericias()
        cards = "".join(_pericia_card(x) for x in state["pericias"]) or '<div class="empty">Nenhuma perícia localizada no canal oficial.</div>'
        extra = """
<style>.pericia-list{display:grid;gap:20px}.pericia-card{display:grid;grid-template-columns:.9fr 1.1fr;border:1px solid #393019;border-radius:18px;background:#0b0b08;overflow:hidden}.pericia-text{padding:24px}.pericia-text small{color:#d7a93d;letter-spacing:1.5px;font-size:9px}.pericia-text h2{font-family:Georgia,serif;font-size:25px}.pericia-body{white-space:pre-wrap;color:#d1cab5;line-height:1.55;max-height:420px;overflow:auto;margin-bottom:18px}.gallery{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;padding:15px;background:#050504}.photo{padding:0;border:1px solid #4c401f;border-radius:10px;overflow:hidden;background:#030303;min-height:190px;cursor:zoom-in}.photo img{width:100%;height:100%;object-fit:cover;display:block}.no-media{grid-column:1/-1;min-height:220px;display:grid;place-items:center;color:#77705e;border:1px dashed #3c3219;border-radius:10px}.lightbox{position:fixed;inset:0;background:#000e;display:none;place-items:center;z-index:100;padding:25px}.lightbox.open{display:grid}.lightbox img{max-width:95vw;max-height:92vh;border:1px solid #7b611b;border-radius:10px}.lightbox button{position:absolute;top:20px;right:25px;background:#11100b;color:#f0d878;border:1px solid #6c551a;padding:9px 12px;border-radius:8px}@media(max-width:900px){.pericia-card{grid-template-columns:1fr}}@media(max-width:620px){.gallery{grid-template-columns:1fr}}</style>
<div id="lb" class="lightbox" onclick="closeImg()"><button>FECHAR</button><img id="lbimg"></div><script>function openImg(src){document.getElementById('lbimg').src=src;document.getElementById('lb').classList.add('open')}function closeImg(){document.getElementById('lb').classList.remove('open')}</script>"""
        body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><section class="hero" style="margin-bottom:30px"><div class="eyebrow">ÁREA AUTORIZADA</div><h2>Perícias <span>Operacionais</span></h2><p>Laudos, registros e fotografias recuperadas diretamente do canal oficial.</p></section><section class="pericia-list">{cards}</section></main>{extra}'''
        return web.Response(text=_shell("Perícias • DICOR", body), content_type="text/html", charset="utf-8")

    async def central_dossies_http(request):
        return web.Response(status=404, text="Módulo removido da Central DICOR.")

    def _target_module(next_path: str) -> Tuple[str, str]:
        clean = str(next_path or "/").split("?", 1)[0]
        if clean.startswith("/boletins"):
            return "approval", "boletins"
        if clean.startswith("/pericias"):
            return "approval", "pericias"
        if clean.startswith("/fichas"):
            return "strategic", "fichas"
        if clean.startswith("/arvore"):
            return "strategic", "arvore"
        return "public", ""

    async def central_login_get(request):
        next_path = str(request.query.get("next") or "/")
        mode, module = _target_module(next_path)
        if mode == "public":
            raise web.HTTPFound(next_path)

        if mode == "strategic":
            if _valid_strategic_cookie(request.cookies.get("dicor_strategic", "")):
                raise web.HTTPFound(next_path)
            error = _escape(request.query.get("erro") or "")
            alert = f'<div class="notice danger">{error}</div>' if error else ''
            body = f'''<div class="form-shell"><a class="back" href="/">← Voltar à Central</a><form class="form-card" method="post" action="/acesso"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="eyebrow" style="text-align:center">COFRE ESTRATÉGICO</div><h2>Acesso reservado</h2><p>Este módulo não utiliza solicitação pública. Digite a senha estratégica fornecida exclusivamente aos operadores autorizados.</p>{alert}<input type="hidden" name="mode" value="strategic"><input type="hidden" name="next" value="{_escape(next_path)}"><div class="field"><label>SENHA ESTRATÉGICA</label><input name="senha" type="password" autocomplete="current-password" required autofocus></div><button class="btn" type="submit">AUTORIZAR ACESSO</button></form></div>'''
            return web.Response(text=_shell("Acesso estratégico • DICOR", body, top_right="NÍVEL RESERVADO"), content_type="text/html", charset="utf-8")

        request_id = str(request.query.get("request") or "")
        if request_id:
            item = await _find_access_by_id(request_id)
            token = request.cookies.get("dicor_approval", "")
            if item and token and item.get("token_hash") == _token_hash(token):
                status = item.get("status")
                if status == "approved":
                    raise web.HTTPFound(next_path)
                if status == "denied":
                    body = f'''<div class="form-shell"><div class="form-card"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="notice danger">⛔ Seu acesso a {_escape(_module_label(module))} foi negado.</div><a class="btn" href="/">Voltar à Central</a></div></div>'''
                    return web.Response(text=_shell("Acesso negado • DICOR", body), content_type="text/html", charset="utf-8")
                body = f'''<div class="form-shell"><div class="form-card"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="eyebrow" style="text-align:center">SOLICITAÇÃO ENVIADA</div><h2>Aguardando autorização</h2><p>O pedido de acesso a <b>{_escape(_module_label(module))}</b> foi enviado para a área de aprovação no Discord.</p><div class="notice">A página verifica automaticamente a decisão. Não é necessário enviar outro pedido.</div><a class="btn dark" href="/">Voltar à Central</a><script>setTimeout(()=>location.reload(),3000)</script></div></div>'''
                return web.Response(text=_shell("Aguardando aprovação • DICOR", body), content_type="text/html", charset="utf-8")

        body = f'''<div class="form-shell"><a class="back" href="/">← Voltar à Central</a><form class="form-card" method="post" action="/acesso"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="eyebrow" style="text-align:center">CONTROLE DE ACESSO</div><h2>Solicitar {_escape(_module_label(module))}</h2><p>Informe seus dados. A solicitação será enviada para aprovação no Discord e somente após a liberação este navegador poderá entrar.</p><input type="hidden" name="mode" value="approval"><input type="hidden" name="module" value="{_escape(module)}"><input type="hidden" name="next" value="{_escape(next_path)}"><div class="field"><label>QRA / NOME</label><input name="qra" maxlength="100" required></div><div class="field"><label>PASSAPORTE / RG FUNCIONAL</label><input name="passaporte" maxlength="50" required></div><div class="field"><label>USUÁRIO DO DISCORD</label><input name="discord" maxlength="100" placeholder="Ex.: baiano"></div><div class="field"><label>MOTIVO DO ACESSO</label><textarea name="motivo" maxlength="500" required></textarea></div><button class="btn" type="submit">ENVIAR PARA APROVAÇÃO</button></form></div>'''
        return web.Response(text=_shell("Solicitar acesso • DICOR", body), content_type="text/html", charset="utf-8")

    async def central_login_post(request):
        data = await request.post()
        mode = str(data.get("mode") or "")
        next_path = str(data.get("next") or "/")
        target_mode, module = _target_module(next_path)
        if mode == "strategic" and target_mode == "strategic":
            expected = _strategic_password()
            supplied = str(data.get("senha") or "")
            if not expected or not hmac.compare_digest(supplied, expected):
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Senha estratégica inválida.')}")
            response = web.HTTPFound(next_path)
            response.set_cookie("dicor_strategic", _make_strategic_cookie(), max_age=12 * 3600, httponly=True, secure=True, samesite="Lax", path="/")
            raise response

        if mode == "approval" and target_mode == "approval":
            token = secrets.token_urlsafe(32)
            request_id = secrets.token_hex(5).upper()
            record = {
                "id": request_id,
                "module": module,
                "status": "pending",
                "qra": str(data.get("qra") or "").strip()[:100],
                "passaporte": str(data.get("passaporte") or "").strip()[:50],
                "discord": str(data.get("discord") or "").strip()[:100],
                "motivo": str(data.get("motivo") or "").strip()[:500],
                "created_at": _now(),
                "expires_at": _now() + 12 * 3600,
                "token_hash": _token_hash(token),
            }
            async with access_lock:
                items = [x for x in _load_access() if int(x.get("expires_at") or 0) > _now() - 86400]
                items.append(record)
                _save_access(items)
            sent = await _send_approval(record)
            if not sent:
                await _update_access(request_id, "error", "sistema")
                body = '<div class="form-shell"><div class="form-card"><div class="notice danger">Não foi possível entregar a solicitação ao canal de aprovação. Tente novamente em instantes.</div><a class="btn" href="/">Voltar</a></div></div>'
                return web.Response(text=_shell("Falha de aprovação • DICOR", body), content_type="text/html", charset="utf-8")
            response = web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&request={request_id}")
            response.set_cookie("dicor_approval", token, max_age=12 * 3600, httponly=True, secure=True, samesite="Lax", path="/")
            raise response

        raise web.HTTPFound("/")

    async def central_logout_http(request):
        response = web.HTTPFound("/")
        response.del_cookie("dicor_approval", path="/")
        response.del_cookie("dicor_strategic", path="/")
        raise response

    @web.middleware
    async def central_auth_middleware(request, handler):
        path = str(request.path or "/")
        if path in {"/", "/index.html", "/catalogo", "/acesso", "/sair"} or path.startswith(PUBLIC_PREFIXES):
            return await handler(request)
        if path.startswith("/dossies-central"):
            return web.Response(status=404, text="Módulo removido da Central DICOR.")

        mode, module = _target_module(path)
        if mode == "strategic":
            if _valid_strategic_cookie(request.cookies.get("dicor_strategic", "")):
                return await handler(request)
            raise web.HTTPFound(f"/acesso?next={quote(path, safe='/')}")
        if mode == "approval":
            token = request.cookies.get("dicor_approval", "")
            if await _find_approved_token(token, module):
                return await handler(request)
            raise web.HTTPFound(f"/acesso?next={quote(path, safe='/')}")

        if path.startswith("/api/"):
            low = path.casefold()
            approval_module = "pericias" if "pericia" in low else ("boletins" if "bolet" in low else "")
            if approval_module:
                if await _find_approved_token(request.cookies.get("dicor_approval", ""), approval_module):
                    return await handler(request)
                return web.json_response({"ok": False, "erro": "Acesso aguardando autorização."}, status=401)
            if _valid_strategic_cookie(request.cookies.get("dicor_strategic", "")):
                return await handler(request)
            return web.json_response({"ok": False, "erro": "Senha estratégica necessária."}, status=401)

        return await handler(request)

    async def _restore_pending_views() -> None:
        if state["pending_views_restored"]:
            return
        state["pending_views_restored"] = True
        for item in _load_access():
            if item.get("status") != "pending" or int(item.get("expires_at") or 0) < _now():
                continue
            message_id = int(item.get("discord_message_id") or 0)
            if not message_id:
                continue
            try:
                client.add_view(ApprovalView(str(item["id"])), message_id=message_id)
            except Exception:
                pass

    async def _on_ready() -> None:
        await _restore_pending_views()
        await _refresh_all("on_ready")
        task = state.get("loop_task")
        if task is None or task.done():
            state["loop_task"] = asyncio.create_task(_refresh_loop())

    async def _on_message(message) -> None:
        channel_id = int(getattr(getattr(message, "channel", None), "id", 0) or 0)
        watched = {
            int(getattr(bot_module, "PROCURADOS_CHANNEL_ID", 0) or 0),
            int(getattr(bot_module, "PERICIAS_CHANNEL_ID", 0) or 0),
            int(getattr(bot_module, "BOLETINS_CHANNEL_ID", 0) or 0),
        }
        if channel_id in watched:
            task = state.get("refresh_task")
            if task is None or task.done():
                async def delayed():
                    await asyncio.sleep(1)
                    await _refresh_all("discord_update")
                state["refresh_task"] = asyncio.create_task(delayed())

    if hasattr(client, "add_listener"):
        client.add_listener(_on_ready, "on_ready")
        client.add_listener(_on_message, "on_message")

    bot_module.central_portal_http = central_portal_http
    bot_module.pagina_inicial = pagina_inicial
    bot_module.central_login_get = central_login_get
    bot_module.central_login_post = central_login_post
    bot_module.central_logout_http = central_logout_http
    bot_module.central_auth_middleware = central_auth_middleware
    bot_module.central_boletins_http = central_boletins_http
    bot_module.central_pericias_http = central_pericias_http
    bot_module.central_dossies_http = central_dossies_http

    for name in ("boletins_pagina_http", "central_boletins_pagina_http"):
        if hasattr(bot_module, name):
            setattr(bot_module, name, central_boletins_http)
    for name in ("pericias_pagina_http", "central_pericias_pagina_http"):
        if hasattr(bot_module, name):
            setattr(bot_module, name, central_pericias_http)

    print("✅ V163 Central PF: preto/dourado, fotos ao vivo, boletins vinculados, aprovação e senha estratégica ativos; Dossiês removidos da Central.", flush=True)
