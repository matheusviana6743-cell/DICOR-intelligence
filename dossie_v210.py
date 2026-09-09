# -*- coding: utf-8 -*-
"""DICOR V210 — gerador profissional de dossiês operacionais.

Reescrito do zero a partir do modelo PDF fornecido pelo responsável.
Objetivos:
- manter o fluxo de geração de PDF do bot;
- usar tarefas, tópicos e mensagens já coletados pelo sistema;
- organizar evidências por seção, sem sobreposição;
- preservar mídia local e tentar baixar anexos HTTP quando disponíveis;
- aplicar identidade POLÍCIA FEDERAL / DICOR, sem a nomenclatura antiga.

Compatibilidade de entrada:
    gerar_pdf_dossie(bot_module, dados, caminho)
    gerar_pdf(bot_module, dados, caminho)
    install(bot_module)
"""
from __future__ import annotations

import io
import json
import os
import re
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Identidade visual
# ---------------------------------------------------------------------------
NAVY = colors.HexColor("#0D1721")
NAVY_2 = colors.HexColor("#142635")
GOLD = colors.HexColor("#C79A37")
GOLD_2 = colors.HexColor("#E2C06A")
INK = colors.HexColor("#171B1F")
MUTED = colors.HexColor("#66717A")
LIGHT = colors.HexColor("#F5F6F7")
LINE = colors.HexColor("#D6DBDF")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN_X = 1.65 * cm
MARGIN_TOP = 4.15 * cm
MARGIN_BOTTOM = 1.65 * cm

SECTION_DEFS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("01", "PAINEL DA ORGANIZAÇÃO", ("painel", "painel da organização", "painel da organizacao", "painel organização")),
    ("02", "PRINCIPAIS MEMBROS", ("fotos dos membros", "membros", "principais membros", "fotos membros", "gerentes", "lider")),
    ("03", "LOCALIZAÇÃO", ("localização", "localizacao", "coordenadas", "endereço", "endereco")),
    ("04", "VISÃO AÉREA", ("foto de cima", "visão aérea", "visao aerea", "aerea", "aérea")),
    ("05", "MATERIAIS / PRODUTOS", ("materiais", "material que vendem", "ingredientes base", "produtos", "vendas")),
    ("06", "REGISTRO DE COMPRA", ("compra", "compra do ilícito", "compra do ilicito", "registro de compra")),
    ("07", "INFORMANTE", ("informante", "informações do informante", "informacoes do informante")),
    ("08", "BAÚ DE MEMBROS", ("baú de membros", "bau de membros", "baú membros", "bau membros")),
    ("09", "BAÚ DE LÍDER", ("baú de líder", "bau de lider", "baú líder", "bau lider")),
    ("10", "ROTA DE FABRICAÇÃO / FARM", ("fabricação", "fabricacao", "rota de farm", "local de fabricação", "local de fabricacao")),
    ("11", "ROTA DE PRODUÇÃO", ("produção", "producao", "rota de produção", "rota de producao", "escoamento")),
    ("12", "INFORMAÇÕES GERAIS", ("informações gerais", "informacoes gerais", "informação geral", "informacao geral")),
]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value).strip()


def _norm(value: Any) -> str:
    text = _clean(value).casefold()
    text = re.sub(r"[^0-9a-záàâãéèêíìîóòôõúùûç]+", " ", text)
    return " ".join(text.split())


def _flatten(value: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            p = f"{path}.{key}" if path else str(key)
            yield p, child
            yield from _flatten(child, p)
    elif isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            p = f"{path}[{idx}]"
            yield p, child
            yield from _flatten(child, p)


def _all_strings(value: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for _, child in _flatten(value):
        if isinstance(child, str):
            text = child.strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _record_dicts(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for _, child in _flatten(value):
        if isinstance(child, dict):
            out.append(child)
    return out


def _pick(d: Dict[str, Any], aliases: Sequence[str], default: str = "") -> str:
    wanted = {_norm(x) for x in aliases}
    for key, value in d.items():
        nk = _norm(key)
        if nk in wanted and _clean(value):
            return _clean(value)
    return default


def _extract_url_list(value: Any) -> List[str]:
    urls: List[str] = []
    if isinstance(value, str):
        for u in re.findall(r"https?://[^\s>]+", value):
            if u not in urls:
                urls.append(u.rstrip(")],"))
    elif isinstance(value, dict):
        for child in value.values():
            urls.extend([u for u in _extract_url_list(child) if u not in urls])
    elif isinstance(value, (list, tuple)):
        for child in value:
            urls.extend([u for u in _extract_url_list(child) if u not in urls])
    return urls


def _extract_local_files(value: Any) -> List[str]:
    results: List[str] = []
    exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf")
    candidates: List[str] = []
    for _, child in _flatten(value):
        if isinstance(child, str):
            candidates.append(child.strip())
    for text in candidates:
        if text.lower().endswith(exts) and Path(text).exists() and text not in results:
            results.append(text)
    return results


def _section_for_text(text: str) -> Optional[str]:
    n = _norm(text)
    for code, _, aliases in SECTION_DEFS:
        if any(_norm(alias) in n for alias in aliases):
            return code
    return None


def _collect_section_payload(dados: Dict[str, Any], code: str) -> Dict[str, Any]:
    definition = next(x for x in SECTION_DEFS if x[0] == code)
    _, title, aliases = definition
    alias_norm = [_norm(x) for x in aliases]
    buckets: List[Dict[str, Any]] = []
    strings: List[str] = []
    urls: List[str] = []
    local_files: List[str] = []

    for path, child in _flatten(dados):
        hay = _norm(path + " " + _clean(child)[:900])
        if any(a and a in hay for a in alias_norm):
            if isinstance(child, dict):
                buckets.append(child)
            elif isinstance(child, (list, tuple)):
                buckets.extend(x for x in child if isinstance(x, dict))
            elif isinstance(child, str) and child.strip():
                strings.append(child.strip())
            urls.extend([u for u in _extract_url_list(child) if u not in urls])
            for p in _extract_local_files(child):
                if p not in local_files:
                    local_files.append(p)

    # Também usa objetos explicitamente marcados como tarefa/tópico/mensagem.
    for item in _record_dicts(dados):
        scope_text = " ".join(
            _clean(item.get(k, ""))
            for k in ("titulo", "title", "nome", "name", "topico", "topic", "tarefa", "task", "assunto", "categoria")
        )
        if _section_for_text(scope_text) == code:
            buckets.append(item)
            strings.extend(
                _clean(item.get(k, ""))
                for k in ("conteudo", "content", "descricao", "description", "texto", "mensagem", "message", "observacao", "observação")
                if _clean(item.get(k, ""))
            )
            urls.extend([u for u in _extract_url_list(item) if u not in urls])
            for p in _extract_local_files(item):
                if p not in local_files:
                    local_files.append(p)

    # Fallback para conteúdo geral ainda não categorizado.
    if not buckets and not strings and code == "12":
        strings.extend(s for s in _all_strings(dados) if len(s) >= 20)
        urls.extend([u for u in _extract_url_list(dados) if u not in urls])

    return {"code": code, "title": title, "records": buckets, "strings": strings, "urls": urls, "local_files": local_files}


def _global_meta(dados: Dict[str, Any]) -> Dict[str, str]:
    records = _record_dicts(dados)
    meta: Dict[str, str] = {}
    aliases = {
        "requerente": ("requerente", "solicitante", "responsavel", "responsável", "autor"),
        "local": ("localizacao", "localização", "local", "endereco", "endereço", "cidade"),
        "pedido": ("pedido", "numero_pedido", "nº do pedido", "numero da pacificacao", "nº da pacificação", "numero da pacificacao"),
        "processo": ("processo", "numero_processo", "nº do processo", "protocolo"),
        "data": ("data", "data_expedicao", "data de expedicao", "data de expedição", "criado_em", "created_at"),
        "investigado": ("investigado", "organização", "organizacao", "comunidade", "nome_alvo", "alvo"),
        "responsavel": ("delegado", "autoridade", "responsavel", "responsável", "responsavel_id"),
    }
    for dest, keys in aliases.items():
        found = ""
        for d in records + [dados]:
            for k in keys:
                found = _pick(d, (k,), "")
                if found:
                    break
            if found:
                break
        if found:
            meta[dest] = found
    if "data" not in meta:
        meta["data"] = datetime.now().strftime("%d/%m/%Y")
    if "pedido" not in meta:
        meta["pedido"] = "A definir"
    if "processo" not in meta:
        meta["processo"] = "A definir"
    if "requerente" not in meta:
        meta["requerente"] = "POLÍCIA FEDERAL • DICOR"
    if "local" not in meta:
        meta["local"] = "Não informado"
    if "investigado" not in meta:
        meta["investigado"] = "Não identificado"
    if "responsavel" not in meta:
        meta["responsavel"] = "Autoridade responsável"
    return meta


def _fmt_date(value: str) -> str:
    text = value.strip()
    patterns = [
        (r"(\d{4})[-/](\d{2})[-/](\d{2})", lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}"),
        (r"(\d{2})[-/](\d{2})[-/](\d{4})", lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}"),
    ]
    for pattern, fn in patterns:
        m = re.search(pattern, text)
        if m:
            return fn(m)
    return text or "Não informado"


def _download_url(url: str, cache_dir: Path) -> Optional[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", url.split("/", 3)[-1] or "midia")[:90]
    if not Path(name).suffix:
        name += ".bin"
    target = cache_dir / name
    if target.exists() and target.stat().st_size > 0:
        return target
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DICOR-Dossie/210"})
        with urllib.request.urlopen(req, timeout=8) as response:
            data = response.read(8 * 1024 * 1024)
        if not data:
            return None
        target.write_bytes(data)
        return target
    except Exception:
        return None


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br/>")
    return Paragraph(safe, style)


def _bullets(lines: Sequence[str], style: ParagraphStyle) -> List[Paragraph]:
    out: List[Paragraph] = []
    for text in lines:
        clean = re.sub(r"^[•·\-]\s*", "", text.strip())
        if not clean:
            continue
        out.append(_paragraph("• " + clean, style))
        out.append(Spacer(1, 0.11 * cm))
    return out


def _record_text(record: Dict[str, Any]) -> str:
    keys = ("conteudo", "content", "descricao", "description", "texto", "mensagem", "message", "resultado", "observacao", "observação", "assunto", "title", "titulo")
    parts: List[str] = []
    for k in keys:
        value = _clean(record.get(k, ""))
        if value and value not in parts:
            parts.append(value)
    return " — ".join(parts)


def _section_lines(payload: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for record in payload["records"]:
        text = _record_text(record)
        if text:
            lines.append(text)
        author = _pick(record, ("autor", "autor_nome", "responsavel", "responsável"), "")
        when = _pick(record, ("data", "timestamp", "created_at", "criado_em"), "")
        if author or when:
            lines.append(" | ".join(x for x in (author, _fmt_date(when)) if x))
    for s in payload["strings"]:
        if s and s not in lines:
            lines.append(s)
    # limita repetições sem perder evidência
    unique: List[str] = []
    seen = set()
    for line in lines:
        key = _norm(line)
        if key and key not in seen:
            seen.add(key)
            unique.append(line)
    return unique[:18]


def _cover_story(meta: Dict[str, str], dados: Dict[str, Any]) -> List[Paragraph]:
    styles = _styles()
    story: List[Paragraph] = []
    story += [Spacer(1, 1.0 * cm)]
    story += [_paragraph("DOSSIÊ OPERACIONAL", styles["cover_title"]), Spacer(1, 0.16 * cm)]
    story += [_paragraph("INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO", styles["cover_sub"]), Spacer(0.8 * cm)]
    card = Table([
        [_paragraph("REFERÊNCIA", styles["label"]), _paragraph(meta["pedido"], styles["value"] )],
        [_paragraph("PROCESSO", styles["label"]), _paragraph(meta["processo"], styles["value"])],
        [_paragraph("ALVO / ORGANIZAÇÃO", styles["label"]), _paragraph(meta["investigado"], styles["value"])],
        [_paragraph("LOCAL", styles["label"]), _paragraph(meta["local"], styles["value"])],
        [_paragraph("EXPEDIÇÃO", styles["label"]), _paragraph(_fmt_date(meta["data"]), styles["value"])],
    ], colWidths=[4.2 * cm, 11.0 * cm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (0, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.8, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(card)
    story += [Spacer(1, 1.1 * cm)]
    story += [_paragraph("Documento interno de consolidação de evidências. Conteúdo compilado exclusivamente a partir das tarefas, tópicos e mensagens associados à mesa operacional.", styles["body"])]
    story += [Spacer(1, 0.65 * cm)]
    story += [_paragraph("POLÍCIA FEDERAL", styles["footer_brand"]), _paragraph("DICOR", styles["footer_brand"])]
    return story


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle("cover_title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=21, leading=25, alignment=TA_CENTER, textColor=NAVY, spaceAfter=5),
        "cover_sub": ParagraphStyle("cover_sub", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=TA_CENTER, textColor=GOLD, tracking=1.2),
        "section": ParagraphStyle("section", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, spaceAfter=9),
        "section_no": ParagraphStyle("section_no", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=GOLD, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=4),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.8, leading=10.5, textColor=MUTED),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.7, leading=9, textColor=WHITE),
        "value": ParagraphStyle("value", parent=base["Normal"], fontName="Helvetica", fontSize=8.4, leading=10.5, textColor=INK),
        "photo_cap": ParagraphStyle("photo_cap", parent=base["Normal"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=MUTED, alignment=TA_CENTER),
        "quote": ParagraphStyle("quote", parent=base["BodyText"], fontName="Helvetica-Oblique", fontSize=8.5, leading=12, textColor=NAVY_2, leftIndent=8, rightIndent=8, borderColor=GOLD, borderWidth=0.6, borderPadding=7),
        "footer_brand": ParagraphStyle("footer_brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=TA_CENTER, textColor=NAVY),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    # faixa superior
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 2.75 * cm, PAGE_W, 2.75 * cm, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, PAGE_H - 2.80 * cm, PAGE_W, 0.05 * cm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(MARGIN_X, PAGE_H - 1.25 * cm, "POLÍCIA FEDERAL")
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(GOLD_2)
    canvas.drawString(MARGIN_X, PAGE_H - 1.75 * cm, "DICOR • DOCUMENTO INTERNO")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(PAGE_W - MARGIN_X, 0.78 * cm, f"Página {doc.page}")
    canvas.drawString(MARGIN_X, 0.78 * cm, "DICOR • POLÍCIA FEDERAL • AMBIENTE FICTÍCIO")
    canvas.restoreState()


def _image_flowables(paths: Sequence[str], styles: Dict[str, ParagraphStyle], max_images: int = 4) -> List[Any]:
    out: List[Any] = []
    valid = 0
    for path in paths:
        try:
            p = Path(path)
            if not p.exists() or p.stat().st_size <= 0:
                continue
            img = Image(str(p))
            img._restrictSize(14.3 * cm, 8.7 * cm)
            out.extend([Spacer(1, 0.18 * cm), img, Spacer(1, 0.08 * cm), _paragraph(p.name, styles["photo_cap"])])
            valid += 1
            if valid >= max_images:
                break
        except Exception:
            continue
    return out


def _write_section(story: List[Any], payload: Dict[str, Any], styles: Dict[str, ParagraphStyle], cache_dir: Path) -> None:
    story.append(_paragraph(f"PARTE {payload['code']}", styles["section_no"]))
    story.append(_paragraph(payload["title"], styles["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=0, spaceAfter=10))

    lines = _section_lines(payload)
    urls = payload["urls"]
    local_files = payload["local_files"]

    downloaded: List[str] = []
    for url in urls[:8]:
        path = _download_url(url, cache_dir)
        if path:
            downloaded.append(str(path))
    images = local_files + downloaded

    if lines:
        # primeiro parágrafo como síntese, restante como itens objetivos
        story.append(_paragraph(lines[0], styles["body"]))
        if len(lines) > 1:
            story.extend(_bullets(lines[1:10], styles["body"]))
    else:
        story.append(_paragraph("Nenhuma informação textual estruturada foi localizada nas tarefas, tópicos ou mensagens desta etapa.", styles["small"]))

    if urls:
        story.append(Spacer(1, 0.12 * cm))
        story.append(_paragraph(f"Mídia / evidência vinculada: {len(urls)} referência(s) encontradas.", styles["small"]))
    if images:
        story.extend(_image_flowables(images, styles))
    story.append(Spacer(1, 0.28 * cm))
    rel = Table([
        [_paragraph("RELAÇÃO COM O PROCESSO", styles["label"]), _paragraph("Consolidado automaticamente a partir dos registros da mesa operacional.", styles["value"])],
        [_paragraph("DATA / ORIGEM", styles["label"]), _paragraph("Tarefas, tópicos e mensagens associadas ao fluxo da mesa.", styles["value"])],
    ], colWidths=[4.3 * cm, 10.9 * cm])
    rel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (0, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(rel)


def _planning_page(story: List[Any], dados: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> None:
    story.append(_paragraph("PLANEJAMENTO OPERACIONAL", styles["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=0, spaceAfter=12))
    texts = [
        "Objetivo operacional: consolidar o material produzido durante a investigação e organizar a mesa para análise e decisão.",
        "Efetivo envolvido: registros de usuários, responsáveis e participantes identificados nas tarefas e tópicos.",
        "Recursos utilizados: mídias, mensagens, localizações, documentos e demais elementos anexados ao fluxo.",
        "Estratégia: reunir evidências por assunto, registrar origem e preservar rastreabilidade das mensagens.",
        "Medidas de proteção: acesso restrito ao documento e uso interno conforme as regras da unidade.",
    ]
    story.extend(_bullets(texts, styles["body"]))
    # mostra nomes de tarefas encontradas
    task_names: List[str] = []
    for d in _record_dicts(dados):
        for key in ("titulo", "title", "tarefa", "task", "nome"):
            val = _clean(d.get(key, ""))
            if val and _norm(val) not in {_norm(x) for x in task_names}:
                task_names.append(val)
                break
    if task_names:
        story.append(Spacer(1, 0.18 * cm))
        story.append(_paragraph("TAREFAS / TÓPICOS IDENTIFICADOS", styles["section_no"]))
        story.extend(_bullets(task_names[:15], styles["body"]))


def _motivation_page(story: List[Any], dados: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> None:
    story.append(_paragraph("MOTIVAÇÃO E CONTEXTO", styles["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=0, spaceAfter=12))
    parts: List[str] = []
    for d in _record_dicts(dados):
        candidate = _pick(d, ("motivo", "motivação", "motivacao", "fundamentação", "fundamentacao", "justificativa", "contexto"), "")
        if candidate and candidate not in parts:
            parts.append(candidate)
    if not parts:
        parts = [
            "Este dossiê foi consolidado para registrar, de forma organizada, os elementos produzidos durante a apuração e subsidiar a análise operacional da DICOR.",
            "A motivação específica deve ser lida em conjunto com as evidências reunidas nas partes anteriores e com os registros originais da mesa.",
        ]
    story.extend(_bullets(parts[:12], styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    arts = []
    for s in _all_strings(dados):
        for match in re.findall(r"(?:Art\.?\s*\d+(?:\.\d+)?(?:\s*[-–]\s*[^\n,.]+)?)", s, flags=re.I):
            if match not in arts:
                arts.append(match)
    if arts:
        story.append(_paragraph("REFERÊNCIAS REGISTRADAS", styles["section_no"]))
        story.extend(_bullets(arts[:10], styles["body"]))


def _signature_page(story: List[Any], meta: Dict[str, str], styles: Dict[str, ParagraphStyle]) -> None:
    story.append(_paragraph("ENCERRAMENTO E RESPONSABILIDADE", styles["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=0, spaceAfter=14))
    story.append(_paragraph("Com base nos registros consolidados, o presente documento reúne as informações disponíveis na mesa operacional, preservando a vinculação entre evidências, tarefas, tópicos e mensagens.", styles["body"]))
    story.append(Spacer(1, 0.55 * cm))
    box = Table([
        [_paragraph("RESPONSÁVEL", styles["label"]), _paragraph(meta["responsavel"], styles["value"])],
        [_paragraph("REQUERENTE", styles["label"]), _paragraph(meta["requerente"], styles["value"])],
        [_paragraph("LOCAL", styles["label"]), _paragraph(meta["local"], styles["value"])],
        [_paragraph("DATA", styles["label"]), _paragraph(_fmt_date(meta["data"]), styles["value"])],
    ], colWidths=[4.2 * cm, 11.0 * cm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (0, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.7, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(box)
    story.append(Spacer(1, 2.0 * cm))
    sig = Table([["____________________________", "____________________________"], ["RESPONSÁVEL PELA CONSOLIDAÇÃO", "AUTORIDADE DICOR"]], colWidths=[7.5 * cm, 7.5 * cm])
    sig.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig)


def gerar_pdf_dossie(bot_module: Any, dados: Dict[str, Any], caminho: Any) -> str:
    """Gera o PDF principal do dossiê.

    ``dados`` é tratado de forma tolerante porque mesas antigas podem ter
    estruturas diferentes. Tarefas, tópicos e mensagens podem aparecer em
    qualquer nível do dicionário e são classificados por assunto.
    """
    if not isinstance(dados, dict):
        dados = {"dados": dados}
    target = Path(caminho)
    target.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = target.parent / ".dossie_media_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    meta = _global_meta(dados)

    doc = BaseDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"Dossiê Operacional — {meta['investigado']}",
        author="POLÍCIA FEDERAL • DICOR",
        subject="Consolidação operacional",
    )
    frame = Frame(MARGIN_X, MARGIN_BOTTOM, PAGE_W - 2 * MARGIN_X, PAGE_H - MARGIN_TOP - MARGIN_BOTTOM, id="normal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="dicor", frames=[frame], onPage=_header_footer)])

    story: List[Any] = []
    story.extend(_cover_story(meta, dados))
    story.append(PageBreak())
    _planning_page(story, dados, styles)
    story.append(PageBreak())

    for idx, (code, _, _) in enumerate(SECTION_DEFS):
        payload = _collect_section_payload(dados, code)
        _write_section(story, payload, styles, cache_dir)
        story.append(PageBreak())

    _motivation_page(story, dados, styles)
    story.append(PageBreak())
    _signature_page(story, meta, styles)

    # Documento final: capa + planejamento + 12 partes + motivação + encerramento.
    doc.build(story)
    return str(target)


def gerar_pdf(bot_module: Any, dados: Dict[str, Any], caminho: Any) -> str:
    return gerar_pdf_dossie(bot_module, dados, caminho)


def install(bot_module: Any) -> None:
    print("✅ V210 Dossiê profissional carregado — PF/DICOR; tarefas, tópicos e mensagens como fonte de preenchimento.", flush=True)


__all__ = ["gerar_pdf_dossie", "gerar_pdf", "install"]
