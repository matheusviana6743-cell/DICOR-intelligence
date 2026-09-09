# -*- coding: utf-8 -*-
"""DICOR V212 — camada de recuperação do gerador de dossiês.

Impede que uma falha localizada na montagem do PDF deixe a mesa travada.
Primeiro tenta o gerador oficial V210. Se ocorrer a falha conhecida de
construtor Space/altura (ou outra falha durante a renderização), cria um PDF
seguro de contingência com os dados disponíveis e retorna normalmente.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any


def _flat_strings(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, child
            yield from _flat_strings(child, path)
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            yield f"{prefix}[{i}]", child
            yield from _flat_strings(child, f"{prefix}[{i}]")
    elif isinstance(value, str) and value.strip():
        yield prefix, value.strip()


def _text_lines(dados):
    lines = []
    seen = set()
    for key, value in _flat_strings(dados or {}):
        text = str(value).strip()
        if len(text) < 2:
            continue
        item = f"{key}: {text}"
        if item not in seen:
            seen.add(item)
            lines.append(item)
    return lines


def _fallback_pdf(dados, caminho):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm

    path = Path(caminho)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    gold = colors.HexColor("#C79A37")
    dark = colors.HexColor("#121212")
    gray = colors.HexColor("#555555")

    page = 1
    def frame():
        c.setStrokeColor(colors.HexColor("#8A8A8A"))
        c.setLineWidth(1.2)
        c.rect(0.65*cm, 0.65*cm, w-1.3*cm, h-1.3*cm)
        c.setStrokeColor(gold)
        c.setLineWidth(0.7)
        c.rect(0.9*cm, 0.9*cm, w-1.8*cm, h-1.8*cm)
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(w/2, h-1.25*cm, "POLÍCIA FEDERAL")
        c.setFillColor(gold)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(w/2, h-1.7*cm, "DICOR - DIVISÃO DE INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO")
        c.setFillColor(gray)
        c.setFont("Helvetica", 7)
        c.drawCentredString(w/2, 0.98*cm, f"Documento de contingência DICOR | Página {page}")

    frame()
    y = h - 2.35*cm
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(w/2, y, "REGISTRO OPERACIONAL CONSOLIDADO")
    y -= 1.0*cm

    c.setFont("Helvetica", 8.8)
    c.setFillColor(gray)
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.drawString(1.7*cm, y, f"Gerado em: {stamp}")
    y -= 0.65*cm

    lines = _text_lines(dados)
    max_width = 96
    for line in lines:
        chunks = [line[i:i+max_width] for i in range(0, len(line), max_width)] or [line]
        for chunk in chunks:
            if y < 1.7*cm:
                c.showPage(); page += 1; frame(); y = h - 2.35*cm
            c.setFillColor(dark)
            c.setFont("Courier", 7.7)
            c.drawString(1.7*cm, y, chunk)
            y -= 0.42*cm
        y -= 0.08*cm

    if not lines:
        c.setFont("Helvetica", 9)
        c.drawString(1.7*cm, y, "Nenhum dado textual disponível no momento da consolidação.")

    c.save()
    return path


def gerar_pdf_seguro(bot_module, dados, caminho):
    try:
        import dossie_v210
        return dossie_v210.gerar_pdf_dossie(bot_module, dados, caminho)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        try:
            bot_module.enviar_log(f"⚠️ V212 Dossiê: geração oficial falhou; usando contingência. Erro: {msg}")
        except Exception:
            pass
        print(f"⚠️ V212 Dossiê: fallback acionado: {msg}", flush=True)
        return _fallback_pdf(dados, caminho)


def install(bot_module):
    print("✅ V212 Dossiê: recuperação segura de geração de PDF ativa.", flush=True)
