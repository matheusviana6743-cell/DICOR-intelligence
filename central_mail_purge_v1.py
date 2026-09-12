# -*- coding: utf-8 -*-
"""Limpeza única de todas as mensagens da conta IMAP configurada para a Central.

Executa uma única vez por /data/.dicor_mail_purged_v1 para evitar apagar e-mails
novos a cada reinício do bot. Varre todas as caixas IMAP selecionáveis e marca
as mensagens para exclusão definitiva (EXPUNGE).
"""
from __future__ import annotations

import imaplib
import os
from pathlib import Path

MARKER = Path(os.getenv("DICOR_DATA_DIR", "/data")) / ".dicor_mail_purged_v1"


def _flag_all(connection: imaplib.IMAP4_SSL, mailbox: str) -> int:
    status, _ = connection.select(mailbox, readonly=False)
    if status != "OK":
        return 0
    status, data = connection.uid("search", None, "ALL")
    if status != "OK" or not data or not data[0]:
        return 0
    uids = data[0].split()
    deleted = 0
    for start in range(0, len(uids), 500):
        batch = b",".join(uids[start:start + 500])
        ok, _ = connection.uid("store", batch, "+FLAGS.SILENT", "\\Deleted")
        if ok == "OK":
            deleted += len(uids[start:start + 500])
    try:
        connection.expunge()
    except Exception:
        pass
    return deleted


def purge_all_mail_once() -> None:
    if MARKER.exists():
        print("✅ [CENTRAL MAIL] limpeza total já realizada anteriormente.", flush=True)
        return

    host = str(os.getenv("DICOR_MAIL_HOST", "")).strip()
    port = int(os.getenv("DICOR_MAIL_PORT", "993") or 993)
    user = str(os.getenv("DICOR_MAIL_USER", "")).strip()
    password = str(os.getenv("DICOR_MAIL_PASSWORD", "")).replace(" ", "")
    if not (host and user and password):
        print("⚠️ [CENTRAL MAIL] limpeza total não executada: credenciais IMAP ausentes.", flush=True)
        return

    conn = None
    total = 0
    folders = 0
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=45)
        conn.login(user, password)
        status, boxes = conn.list()
        if status != "OK":
            raise RuntimeError("não foi possível listar as caixas IMAP")

        names: list[str] = []
        for raw in boxes or []:
            line = raw.decode("utf-8", errors="replace")
            if ' "/" ' in line:
                name = line.rsplit(' "/" ', 1)[-1].strip().strip('"')
            else:
                name = line.split()[-1].strip('"') if line.split() else ""
            if name and name not in names:
                names.append(name)

        for name in names:
            try:
                count = _flag_all(conn, name)
                total += count
                if count:
                    folders += 1
                    print(f"🧹 [CENTRAL MAIL] apagados {count} e-mail(s) de {name}", flush=True)
            except Exception as exc:
                print(f"⚠️ [CENTRAL MAIL] não foi possível limpar {name}: {type(exc).__name__}", flush=True)

        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text("purged\n", encoding="utf-8")
        print(f"✅ [CENTRAL MAIL] limpeza TOTAL concluída: {total} e-mail(s) em {folders} caixa(s).", flush=True)
    except Exception as exc:
        print(f"❌ [CENTRAL MAIL] falha na limpeza total: {type(exc).__name__}: {exc}", flush=True)
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass


def install() -> None:
    # Executa em background para não atrasar o login do Discord/HTTP.
    import threading
    threading.Thread(target=purge_all_mail_once, name="dicor-mail-purge", daemon=True).start()
