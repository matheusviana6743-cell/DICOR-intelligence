# -*- coding: utf-8 -*-
"""DICOR Central V708.

Correcoes sobre a V707:
- sincronizacao direta com canais do Discord do DICOR para Procurados, BO,
  Pericias e Operacoes, sem depender exclusivamente do cache intermediario;
- preservacao de dados do Discord quando o Gmail falhar ou vier vazio;
- upload Foto -> FiveM usando a API v3 oficial do Fivemanage;
- filtros mais rigorosos contra mensagens internas de tarefa/recuperacao;
- rotas dos modulos usando o cache direto da Central.
"""
from __future__ import annotations

import asyncio
import email
import email.header
import hashlib
import html
import imaplib
import json
import mimetypes
import os
import re
from pathlib import Path

import aiohttp
from aiohttp import web

import central_home_v700 as v700
import central_home_v707 as v707

BO_CHANNEL_ID = 1490200514837745754
PERICIA_CHANNEL_ID = 1490200524367200297
PROCURADOS_CHANNEL_ID = 1490200533980545097
ACCESS_CHANNEL_ID = 1548072610447884399

NOISE_MARKERS = (
    "recuperação assistida", "recuperacao assistida",
    "recuperação automática", "recuperacao automatica",
    "recuperação órf", "recuperacao orf",
    "tarefa pendente", "tarefa concluída", "tarefa concluida",
    "registre no painel", "canal foi encontrado",
    "sistema de procurados", "gerenciamento dos procurados",
    "painel de procurados", "compat-tarefas",
)


def clean(value) -> str:
    return " ".join(str(value or "").split())


def clean_source(value) -> str:
    try:
        return v700.clean_source(value)
    except Exception:
        s = str(value or "")
        s = re.sub(r"https?://[^\s)>]+", "", s)
        s = s.replace("**", "").replace("__", "").replace("`", "")
        out = []
        for line in re.split(r"\r?\n+", s):
            line = clean(line)
            if not line:
                continue
            low = line.casefold()
            if any(marker in low for marker in NOISE_MARKERS):
                continue
            out.append(line)
        return "\n".join(out)


def is_noise(text: str) -> bool:
    low = clean(text).casefold()
    return any(marker in low for marker in NOISE_MARKERS)


def message_text(message) -> str:
    parts = [getattr(message, "content", "") or ""]
    for embed in getattr(message, "embeds", []) or []:
        parts.append(getattr(embed, "title", "") or "")
        parts.append(getattr(embed, "description", "") or "")
        for field in getattr(embed, "fields", []) or []:
            parts.append(f"{getattr(field, 'name', '')}: {getattr(field, 'value', '')}")
    return clean_source("\n".join(x for x in parts if x))


def message_image(message) -> str:
    try:
        return str(v700.source.media_url(message) or "").strip()
    except Exception:
        pass
    for embed in getattr(message, "embeds", []) or []:
        image = getattr(embed, "image", None)
        url = getattr(image, "url", "") if image else ""
        if url:
            return str(url)
        thumb = getattr(embed, "thumbnail", None)
        url = getattr(thumb, "url", "") if thumb else ""
        if url:
            return str(url)
    for attachment in getattr(message, "attachments", []) or []:
        url = getattr(attachment, "url", "")
        if url:
            return str(url)
    return ""


def number_from(text: str) -> str:
    try:
        return v700.number(text)
    except Exception:
        match = re.search(r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", text or "", re.I)
        return f"{int(match.group(1)):04d}" if match else "S/N"


def field_from(text: str, labels: tuple[str, ...]) -> str:
    try:
        return v700.field(text, labels)
    except Exception:
        wanted = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{wanted})\s*[:=-]\s*([^|•\n]+)", text or "", re.I)
        return clean(match.group(1))[:260] if match else "Não informado"


def first_meaningful_line(text: str) -> str:
    for line in str(text or "").splitlines():
        line = clean(line)
        if not line or is_noise(line):
            continue
        if line.casefold().startswith(("atendimento", "responsável", "responsavel", "tópico")):
            continue
        return line[:100]
    return "Registro sem identificação"


def direct_row(kind: str, message, channel_name: str) -> dict:
    text = message_text(message)
    name = field_from(text, ("nome", "indivíduo", "individuo", "procurado", "envolvido"))
    if name in ("", "Não informado"):
        name = first_meaningful_line(text)
    return {
        "id": str(getattr(message, "id", "") or hashlib.sha256(text.encode()).hexdigest()[:20]),
        "number": number_from(text),
        "name": name,
        "kind": kind,
        "source": "DISCORD",
        "subject": "",
        "date": str(getattr(message, "created_at", "") or ""),
        "image": message_image(message),
        "url": str(getattr(message, "jump_url", "") or ""),
        "fields": {
            "Número do registro": number_from(text),
            "Nome": name,
            "RG / Passaporte": field_from(text, ("rg", "passaporte", "rg/passaporte")),
            "Crimes": field_from(text, ("crime", "crimes", "acusação", "acusacao")),
            "Localização": field_from(text, ("localização", "localizacao", "local", "último avistamento", "ultimo avistamento")),
            "Situação": field_from(text, ("status", "situação", "situacao", "resultado")),
            "Canal": clean(channel_name) or "DICOR",
        },
        "full_text": text or "Sem informações adicionais.",
    }


async def get_channel(client, channel_id: int):
    if not client or not channel_id:
        return None
    try:
        channel = client.get_channel(channel_id)
        return channel if channel is not None else await client.fetch_channel(channel_id)
    except Exception:
        return None


async def scan_channel(channel, kind: str, limit: int = 500, procurado_filter: bool = False) -> list[dict]:
    if channel is None:
        return []
    rows: list[dict] = []
    try:
        async for message in channel.history(limit=limit, oldest_first=False):
            text = message_text(message)
            if not text:
                continue
            if procurado_filter and is_noise(text):
                continue
            row = direct_row(kind, message, getattr(channel, "name", "DICOR"))
            if procurado_filter:
                low = row["name"].casefold()
                if low in {"registro sem identificação", "não informado", "registro sem identificacao"} and not row.get("image"):
                    continue
            rows.append(row)
    except Exception:
        return []
    unique = {}
    for row in rows:
        unique[row["id"]] = row
    return list(unique.values())


async def scan_named_channels(client, keywords: tuple[str, ...], kind: str, limit: int = 500) -> list[dict]:
    if not client or not getattr(client, "is_ready", lambda: False)():
        return []
    rows: list[dict] = []
    seen: set[int] = set()
    for guild in getattr(client, "guilds", []) or []:
        for channel in getattr(guild, "text_channels", []) or []:
            name = clean(getattr(channel, "name", "")).casefold()
            if not any(keyword in name for keyword in keywords):
                continue
            channel_id = int(getattr(channel, "id", 0) or 0)
            if channel_id in seen:
                continue
            seen.add(channel_id)
            rows.extend(await scan_channel(channel, kind, limit=limit, procurado_filter=(kind == "procurados")))
    unique = {}
    for row in rows:
        unique[row["id"]] = row
    return list(unique.values())


async def collect_discord_data() -> dict[str, list[dict]]:
    client = v700.CLIENT
    result = {"procurados": [], "boletins": [], "pericias": [], "operacoes": []}
    if not client or not getattr(client, "is_ready", lambda: False)():
        return result

    for channel_id, kind, limit, wanted in (
        (PROCURADOS_CHANNEL_ID, "procurados", 500, True),
        (BO_CHANNEL_ID, "boletins", 500, False),
        (PERICIA_CHANNEL_ID, "pericias", 500, False),
    ):
        result[kind].extend(await scan_channel(await get_channel(client, channel_id), kind, limit=limit, procurado_filter=wanted))

    result["procurados"].extend(await scan_named_channels(client, ("procurad", "foragid", "mandado"), "procurados", 300))
    result["boletins"].extend(await scan_named_channels(client, ("boletim", "b.o", "ocorrencia", "ocorrência"), "boletins", 300))
    result["pericias"].extend(await scan_named_channels(client, ("pericia", "perícia", "pericial", "laudo"), "pericias", 300))
    result["operacoes"].extend(await scan_named_channels(client, ("operacao", "operação", "operacoes", "operações", "mesa"), "operacoes", 300))

    ops_channel_id = int(os.getenv("DICOR_OPERACOES_CHANNEL_ID", "0") or 0)
    if ops_channel_id:
        result["operacoes"].extend(await scan_channel(await get_channel(client, ops_channel_id), "operacoes", limit=500))

    for kind in result:
        unique = {}
        for row in result[kind]:
            if kind == "procurados" and is_noise(row.get("full_text", "")):
                continue
            unique[row["id"]] = row
        result[kind] = list(unique.values())[:1000]
    return result


def mail_body_message(msg):
    parts = []
    files = []
    parts_iter = msg.walk() if msg.is_multipart() else [msg]
    for part in parts_iter:
        filename = part.get_filename()
        if filename:
            decoded = []
            for value, charset in email.header.decode_header(str(filename)):
                decoded.append(value.decode(charset or "utf-8", errors="replace") if isinstance(value, bytes) else str(value))
            files.append(clean("".join(decoded)))
        if "attachment" in str(part.get("Content-Disposition", "")).lower():
            continue
        ctype = part.get_content_type().lower()
        if ctype not in ("text/plain", "text/html"):
            continue
        raw = part.get_payload(decode=True)
        if not raw:
            continue
        text = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        parts.append(re.sub(r"<[^>]+>", "\n", html.unescape(text)) if ctype == "text/html" else text)
    return "\n".join(parts), files


def decode_header_value(value) -> str:
    if not value:
        return ""
    out = []
    for raw, charset in email.header.decode_header(str(value)):
        out.append(raw.decode(charset or "utf-8", errors="replace") if isinstance(raw, bytes) else str(raw))
    return clean("".join(out))


def mail_kind(subject: str, body: str):
    text = f"{subject}\n{body}".casefold()
    if any(key in text for key in ("procurado", "foragido", "mandado")):
        return "procurados"
    if any(key in text for key in ("boletim", "b.o.", "ocorrência", "ocorrencia")):
        return "boletins"
    if any(key in text for key in ("perícia", "pericia", "laudo pericial")):
        return "pericias"
    if any(key in text for key in ("operação", "operacao")):
        return "operacoes"
    return None


def mail_row(kind: str, msg, uid, body: str, files: list[str]) -> dict:
    subject = decode_header_value(msg.get("Subject", ""))
    full = clean_source(body)
    message_id = clean(msg.get("Message-ID", "")) or f"{uid}|{subject}|{msg.get('Date', '')}"
    name = field_from(full, ("nome", "indivíduo", "individuo", "procurado", "envolvido", "autor"))
    if name in ("", "Não informado"):
        name = first_meaningful_line(full)
    fields = {
        "Assunto": subject or "Sem assunto",
        "Remetente": decode_header_value(msg.get("From", "")) or "Não informado",
        "Data do e-mail": decode_header_value(msg.get("Date", "")) or "Não informado",
        "Número do registro": number_from(f"{subject}\n{full}"),
        "Nome": name,
        "RG / Passaporte": field_from(full, ("rg", "passaporte", "rg/passaporte")),
        "Crimes": field_from(full, ("crime", "crimes", "acusação", "acusacao")),
        "Localização": field_from(full, ("localização", "localizacao", "local", "último avistamento", "ultimo avistamento")),
        "Situação": field_from(full, ("status", "situação", "situacao", "resultado")),
    }
    if files:
        fields["Anexos do e-mail"] = ", ".join(files)
    for line in full.splitlines():
        match = re.match(r"^([^:]{2,70})\s*:\s*(.+)$", clean(line))
        if match:
            fields.setdefault(clean(match.group(1)).strip("•-"), clean(match.group(2)))
    return {
        "id": hashlib.sha256(message_id.encode()).hexdigest()[:20],
        "number": fields["Número do registro"],
        "name": clean(name),
        "kind": kind,
        "source": "E-MAIL",
        "subject": subject,
        "date": decode_header_value(msg.get("Date", "")),
        "image": "",
        "url": "",
        "fields": fields,
        "full_text": full or "Sem informações adicionais.",
    }


def poll_mail_sync_resilient():
    out = {key: [] for key in ("procurados", "boletins", "pericias", "operacoes")}
    host = str(v700.MAIL_HOST or "").strip()
    user = str(v700.MAIL_USER or "").strip()
    password = str(v700.MAIL_PASS or "").replace(" ", "")
    folder = str(v700.MAIL_FOLDER or "INBOX").strip() or "INBOX"
    if not (host and user and password):
        return out
    connection = None
    try:
        connection = imaplib.IMAP4_SSL(host, int(v700.MAIL_PORT or 993), timeout=45)
        connection.login(user, password)
        ok, _ = connection.select(folder, readonly=True)
        if ok != "OK":
            return out
        ok, data = connection.uid("search", None, "ALL")
        if ok != "OK" or not data or not data[0]:
            return out
        limit = max(20, min(250, int(os.getenv("DICOR_MAIL_LIMIT", "120") or 120)))
        for uid in reversed(data[0].split()[-limit:]):
            ok, fetched = connection.uid("fetch", uid, "(BODY.PEEK[])")
            raw = b"".join(item[1] for item in (fetched or []) if isinstance(item, tuple) and isinstance(item[1], bytes))
            if ok != "OK" or not raw:
                continue
            msg = email.message_from_bytes(raw)
            body, files = mail_body_message(msg)
            kind = mail_kind(decode_header_value(msg.get("Subject", "")), body)
            if kind:
                out[kind].append(mail_row(kind, msg, uid, body, files))
        return out
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


async def poll_mail_resilient():
    try:
        return await asyncio.to_thread(poll_mail_sync_resilient)
    except Exception as exc:
        print(f"⚠️ [CENTRAL MAIL] {type(exc).__name__}", flush=True)
        return {key: [] for key in ("procurados", "boletins", "pericias", "operacoes")}


def merge_rows(discord_rows: list[dict], mail_rows: list[dict], kind: str) -> list[dict]:
    combined = {}
    for row in discord_rows + mail_rows:
        if not isinstance(row, dict):
            continue
        if kind == "procurados" and is_noise(row.get("full_text", "")):
            continue
        key = str(row.get("id") or hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20])
        combined[key] = row
    return list(combined.values())[:1000]


async def refresh_data_v708():
    if v700.C.get("refreshing"):
        return
    v700.C["refreshing"] = True
    try:
        discord_data = await collect_discord_data()
        mail_data = await poll_mail_resilient()
        for kind in ("procurados", "boletins", "pericias", "operacoes"):
            v700.C[kind] = merge_rows(discord_data.get(kind, []), mail_data.get(kind, []), kind)
        v700.C["updated"] = __import__("time").time()
        print(
            "✅ V708 sincronizacao Central: "
            f"procurados={len(v700.C['procurados'])} "
            f"boletins={len(v700.C['boletins'])} "
            f"pericias={len(v700.C['pericias'])} "
            f"operacoes={len(v700.C['operacoes'])}",
            flush=True,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"⚠️ [CENTRAL V708] {type(exc).__name__}", flush=True)
    finally:
        v700.C["refreshing"] = False


async def upload_route_v708(req):
    user = v700.current(req)
    if not user:
        return web.HTTPFound("/cadastro-operador")
    reader = await req.multipart()
    token = ""
    data = b""
    filename = "foto.png"
    content_type = "image/png"
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "csrf":
            token = (await part.text())[:200]
        elif part.name == "foto":
            filename = Path(part.filename or "foto.png").name
            content_type = getattr(part, "headers", {}).get("Content-Type", "") or "application/octet-stream"
            data = await part.read(decode=False)
    if not v700.hmac.compare_digest(token, v700.csrf(user)):
        raise web.HTTPForbidden(text="Token de segurança inválido.")
    ext = Path(filename).suffix.lower()
    signatures = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".gif": data.startswith((b"GIF87a", b"GIF89a")),
        ".webp": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    }
    if not data or len(data) > v700.MAX_IMAGE:
        return web.Response(text=v700.photos(user, error="A imagem deve ter até 10 MB."), status=413, content_type="text/html")
    if ext not in signatures or not signatures[ext]:
        return web.Response(text=v700.photos(user, error="Arquivo de imagem inválido."), status=400, content_type="text/html")
    api_key = str(os.getenv("FIVEMANAGE_API_KEY", "")).strip()
    if not api_key:
        return web.Response(text=v700.photos(user, error="Fivemanage não configurado."), status=503, content_type="text/html")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:120]
    form = aiohttp.FormData()
    form.add_field("file", data, filename=safe_name, content_type=content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream")
    form.add_field("filename", safe_name)
    form.add_field("path", "dicor-central")
    form.add_field("retentionExempt", "true")
    try:
        timeout = aiohttp.ClientTimeout(total=60, connect=20, sock_connect=20, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.fivemanage.com/api/v3/file", headers={"Authorization": api_key}, data=form) as response:
                raw_text = await response.text()
                try:
                    payload = json.loads(raw_text)
                except Exception:
                    payload = {}
                obj = payload.get("data") if isinstance(payload, dict) else {}
                url = str((obj or {}).get("url") or (obj or {}).get("originalUrl") or "").strip()
                if not (200 <= response.status < 300 and url):
                    if response.status == 401:
                        message = "A chave do Fivemanage foi recusada."
                    elif response.status == 413:
                        message = "O Fivemanage recusou o tamanho do arquivo."
                    else:
                        message = "O Fivemanage não aceitou o arquivo."
                    print(f"⚠️ [CENTRAL FOTO] HTTP {response.status}", flush=True)
                    return web.Response(text=v700.photos(user, error=message), status=502, content_type="text/html")
        v700.audit("UPLOAD_FIVEMANAGE", user, safe_name)
        return web.Response(text=v700.photos(user, result=url), content_type="text/html")
    except Exception as exc:
        print(f"⚠️ [CENTRAL FOTO] {type(exc).__name__}", flush=True)
        return web.Response(text=v700.photos(user, error="Não foi possível gerar o link agora."), status=502, content_type="text/html")


async def module_route_v708(req, kind: str, title: str, desc: str):
    user = v700.current(req)
    if not user:
        return web.HTTPFound("/cadastro-operador")
    user = v700.touch(user)
    if not user.get("authorized"):
        return web.Response(text=v707.v706.restricted(user), status=403, content_type="text/html")
    import time
    if time.time() - float(v700.C.get("updated", 0.0) or 0.0) > 45 and not v700.C.get("refreshing"):
        await refresh_data_v708()
    return web.Response(text=v707.v706.list_page(user, kind, title, desc, ""), content_type="text/html")


async def procurados_route_v708(req):
    user = v700.current(req)
    if not user:
        return web.HTTPFound("/cadastro-operador")
    user = v700.touch(user)
    import time
    if time.time() - float(v700.C.get("updated", 0.0) or 0.0) > 45 and not v700.C.get("refreshing"):
        await refresh_data_v708()
    query = clean(req.query.get("q", "")).casefold()
    return web.Response(text=v707.v706.list_page(user, "procurados", "Procurados", "Catálogo de indivíduos procurados.", query), content_type="text/html")


def install(bot_module):
    central = v707.install(bot_module)
    v700.refresh_data = refresh_data_v708
    v700.upload_route = upload_route_v708
    v700.module_route = module_route_v708
    v700.procurados_route = procurados_route_v708
    return central
