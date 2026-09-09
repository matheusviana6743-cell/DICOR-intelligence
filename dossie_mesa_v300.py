# -*- coding: utf-8 -*-
"""
DICOR V300 — GERADOR NOVO DE DOCUMENTO DE MESA

Implementação nova e independente:
- não usa Platypus/Flowables, evitando o erro de Space/altura;
- usa o layout visual aprovado da mesa como fundo fixo;
- lê tarefas, tópicos, mensagens, anexos e registros estruturados;
- classifica o conteúdo pelas tarefas/tópicos da mesa;
- coloca mídias na seção correspondente;
- mantém rastreabilidade por origem;
- usa exclusivamente identidade POLÍCIA FEDERAL / DICOR.

Interface mantida para o restante do bot:
    gerar_pdf_dossie(bot_module, dados, caminho)
    gerar_pdf(bot_module, dados, caminho)
    install(bot_module)
"""
from __future__ import annotations

import base64
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.request import Request, urlopen

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W = 768.0
PAGE_H = 1056.0
BASE64_TEMPLATE = "__TEMPLATE_B64__"

SOURCE_CHANNEL_HINTS = {
    "source": ("origem", "source", "canal", "channel", "channel_name", "parent_name"),
    "topic": ("topico", "tópico", "topic", "thread", "thread_name", "nome_topico", "nome_tópico"),
    "title": ("titulo", "título", "title", "nome", "name", "assunto", "subject"),
    "content": ("conteudo", "conteúdo", "content", "texto", "text", "mensagem", "message", "descricao", "descrição", "description"),
    "author": ("autor", "author", "autor_nome", "author_name", "usuario", "user"),
    "date": ("data", "date", "timestamp", "created_at", "criado_em", "created"),
}

SECTION_RULES: Dict[int, Tuple[str, Tuple[str, ...]]] = {
    1: ("PAINEL DA ORGANIZAÇÃO", ("painel", "fotos líderes", "fotos lideres", "liderança", "lideranca")),
    2: ("PRINCIPAIS MEMBROS", ("fotos dos membros", "fotos membros", "principais membros", "membros", "integrantes")),
    3: ("LOCALIZAÇÃO DA ORGANIZAÇÃO", ("localização", "localizacao", "coordenadas", "endereço", "endereco")),
    4: ("FOTO DE CIMA DA ORGANIZAÇÃO", ("foto de cima", "visão aérea", "visao aerea", "aérea", "aerea", "visão superior", "visao superior")),
    5: ("MATERIAL QUE VENDEM", ("material que vendem", "materiais", "ingredientes base", "produtos", "mercadorias", "vendas")),
    6: ("REGISTRAR COMPRA DO ILÍCITO", ("registrar compra", "compra do ilícito", "compra do ilicito", "compra", "negociação", "negociacao")),
    7: ("FOTO DO INFORMANTE DA ORGANIZAÇÃO", ("informante", "foto do informante", "informações do informante", "informacoes do informante")),
    8: ("FOTO DO BAÚ DE MEMBROS", ("baú de membros", "bau de membros", "baú membros", "bau membros")),
    9: ("FOTO DO BAÚ DE LÍDER", ("baú de líder", "bau de lider", "baú líder", "bau lider")),
    10: ("FOTO E LOCALIZAÇÃO DO LOCAL DE FABRICAÇÃO", ("local de fabricação", "local de fabricacao", "fabricação", "fabricacao", "rota de farm", "farm")),
    11: ("FOTO E LOCALIZAÇÃO DO LOCAL DE PRODUÇÃO", ("local de produção", "local de producao", "produção", "producao", "rota de produção", "rota de producao", "escoamento")),
    12: ("INFORMAÇÕES GERAIS", ("informações gerais", "informacoes gerais", "informação geral", "informacao geral", "geral")),
}

PAGE_TO_SECTION = {
    4: 1,
    7: 2,
    8: 3,
    9: 4,
    10: 5,
    11: 6,
    12: 7,
    13: 8,
    14: 9,
    15: 10,
    16: 11,
}

CY = {
    "black": colors.HexColor("#121212"),
    "gray": colors.HexColor("#4A4A4A"),
    "lightgray": colors.HexColor("#8D8D8D"),
    "gold": colors.HexColor("#B88C32"),
}

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def _template_image() -> ImageReader:
    raw = base64.b64decode(BASE64_TEMPLATE)
    return ImageReader(io.BytesIO(raw))


_TEMPLATE_READER: Optional[ImageReader] = None


def _get_template() -> ImageReader:
    global _TEMPLATE_READER
    if _TEMPLATE_READER is None:
        _TEMPLATE_READER = _template_image()
    return _TEMPLATE_READER


def _norm(text: Any) -> str:
    s = str(text or "").casefold()
    for a, b in (("á", "a"), ("à", "a"), ("â", "a"), ("ã", "a"), ("é", "e"), ("ê", "e"),
                 ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c")):
        s = s.replace(a, b)
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s).split())


def _clean(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, (int, float, bool)):
        return str(text)
    try:
        return json.dumps(text, ensure_ascii=False, default=str)
    except Exception:
        return str(text)


def _get_first(mapping: Dict[str, Any], aliases: Sequence[str]) -> str:
    wanted = {_norm(a) for a in aliases}
    for key, value in mapping.items():
        if _norm(key) in wanted:
            value_s = _clean(value)
            if value_s:
                return value_s
    return ""


def _iter_objects(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for key, child in obj.items():
            p = f"{path}.{key}" if path else str(key)
            yield p, child
            yield from _iter_objects(child, p)
    elif isinstance(obj, (list, tuple, set)):
        for idx, child in enumerate(obj):
            p = f"{path}[{idx}]"
            yield p, child
            yield from _iter_objects(child, p)
    else:
        attrs = {}
        for name in ("id", "name", "content", "url", "proxy_url", "filename", "title", "description"):
            try:
                if hasattr(obj, name):
                    val = getattr(obj, name)
                    if not callable(val):
                        attrs[name] = val
            except Exception:
                pass
        if attrs:
            yield path, attrs


def _urls_from_value(value: Any) -> List[str]:
    found: List[str] = []
    def add(text: str) -> None:
        for url in re.findall(r"https?://[^\s<>\]\)]+", text or ""):
            url = url.rstrip(".,);]")
            if url not in found:
                found.append(url)
    if isinstance(value, str):
        add(value)
    elif isinstance(value, dict):
        for child in value.values():
            for u in _urls_from_value(child):
                if u not in found:
                    found.append(u)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            for u in _urls_from_value(child):
                if u not in found:
                    found.append(u)
    return found


def _is_image_url(url: str, key_hint: str = "") -> bool:
    low = url.casefold()
    ext = Path(low.split("?", 1)[0]).suffix
    if ext in IMAGE_EXTS:
        return True
    hint = _norm(key_hint)
    return any(token in hint for token in ("foto", "imagem", "image", "anexo", "attachment", "midia", "media"))


def _image_urls_from_value(value: Any, key_hint: str = "") -> List[str]:
    result: List[str] = []
    if isinstance(value, str):
        for url in _urls_from_value(value):
            if _is_image_url(url, key_hint) and url not in result:
                result.append(url)
    elif isinstance(value, dict):
        for key, child in value.items():
            result.extend([u for u in _image_urls_from_value(child, f"{key_hint} {key}") if u not in result])
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            result.extend([u for u in _image_urls_from_value(child, key_hint) if u not in result])
    return result


def _local_image_paths(value: Any) -> List[str]:
    result: List[str] = []
    for _, child in _iter_objects(value):
        if isinstance(child, str):
            s = child.strip()
            if Path(s).suffix.casefold() in IMAGE_EXTS and Path(s).exists() and s not in result:
                result.append(s)
    return result


def _record_from_dict(d: Dict[str, Any], path: str) -> Dict[str, Any]:
    title = _get_first(d, SOURCE_CHANNEL_HINTS["title"])
    topic = _get_first(d, SOURCE_CHANNEL_HINTS["topic"])
    source = _get_first(d, SOURCE_CHANNEL_HINTS["source"])
    content = _get_first(d, SOURCE_CHANNEL_HINTS["content"])
    author = _get_first(d, SOURCE_CHANNEL_HINTS["author"])
    date = _get_first(d, SOURCE_CHANNEL_HINTS["date"])
    return {
        "path": path, "source": source, "topic": topic, "title": title,
        "content": content, "author": author, "date": date,
        "raw": d,
        "urls": _urls_from_value(d),
        "image_urls": _image_urls_from_value(d),
        "local_images": _local_image_paths(d),
    }


def _collect_records(dados: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen = set()
    if isinstance(dados, dict):
        for path, obj in _iter_objects(dados):
            if not isinstance(obj, dict):
                continue
            rec = _record_from_dict(obj, path)
            signature = (
                _norm(rec["topic"] or rec["title"] or rec["source"]),
                _norm(rec["content"])[:500],
                rec["date"],
                tuple(sorted(rec["image_urls"])),
            )
            if signature not in seen and any(rec[k] for k in ("source", "topic", "title", "content", "image_urls")):
                seen.add(signature)
                records.append(rec)
    return records


def _combined_text(record: Dict[str, Any]) -> str:
    return _norm(" ".join([record.get("source", ""), record.get("topic", ""), record.get("title", ""), record.get("content", ""), record.get("path", "")]))


def _classify(record: Dict[str, Any]) -> Optional[int]:
    hay = _combined_text(record)
    if not hay:
        return None
    topic_hay = _norm(" ".join([record.get("topic", ""), record.get("title", ""), record.get("source", "")]))
    scores: Dict[int, int] = {}
    for number, (_, aliases) in SECTION_RULES.items():
        score = 0
        for alias in aliases:
            a = _norm(alias)
            if a and a in hay:
                score += 4 if a in topic_hay else 1
        if score:
            scores[number] = score
    return max(scores, key=scores.get) if scores else None


def _build_sections(records: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    sections = {k: [] for k in SECTION_RULES}
    for rec in records:
        sec = _classify(rec)
        if sec is not None:
            sections[sec].append(rec)
    return sections


def _all_text_for(records: Sequence[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    seen = set()
    for rec in records:
        for text in (rec.get("content", ""), rec.get("title", ""), rec.get("topic", "")):
            s = _clean(text)
            if s and _norm(s) not in seen:
                seen.add(_norm(s))
                values.append(s)
        raw = rec.get("raw", {})
        if isinstance(raw, dict):
            for key, value in raw.items():
                if _norm(key) in {"content", "conteudo", "conteúdo", "text", "texto", "message", "mensagem", "description", "descricao", "descrição", "observacao", "observação", "valor", "value", "result", "resultado"}:
                    s = _clean(value)
                    if s and _norm(s) not in seen:
                        seen.add(_norm(s))
                        values.append(s)
    return values


def _section_images(records: Sequence[Dict[str, Any]]) -> List[str]:
    result: List[str] = []
    for rec in records:
        for p in rec.get("local_images", []):
            if p not in result:
                result.append(p)
        for url in rec.get("image_urls", []):
            if url not in result:
                result.append(url)
    return result


def _meta(records: Sequence[Dict[str, Any]], dados: Any) -> Dict[str, str]:
    meta = {"pedido": "", "data": "", "processo": "", "requerente": "", "local": "", "organizacao": ""}
    aliases = {
        "pedido": ("nº do pedido de pacificação", "numero do pedido", "numero_pedido", "pedido", "referencia", "referência"),
        "data": ("data de expedição", "data_expedicao", "data", "expedicao", "expedição"),
        "processo": ("nº do processo", "numero processo", "numero_processo", "processo"),
        "requerente": ("requerente", "solicitante", "responsável", "responsavel"),
        "local": ("localização", "localizacao", "endereco", "endereço", "local"),
        "organizacao": ("organização", "organizacao", "comunidade", "grupo", "alvo"),
    }
    dicts = [rec.get("raw") for rec in records if isinstance(rec.get("raw"), dict)]
    if isinstance(dados, dict):
        dicts.append(dados)
    for dest, keys in aliases.items():
        for d in dicts:
            value = _get_first(d, keys)
            if value:
                meta[dest] = value
                break
    if not meta["data"]:
        meta["data"] = datetime.now().strftime("%d/%m/%Y")
    if not meta["requerente"]:
        meta["requerente"] = "Polícia Federal - DICOR"
    if not meta["local"]:
        loc_lines = _all_text_for([r for r in records if _classify(r) == 3])
        meta["local"] = loc_lines[0] if loc_lines else "Não informado"
    if not meta["organizacao"]:
        panel_lines = _all_text_for([r for r in records if _classify(r) == 1])
        if panel_lines:
            meta["organizacao"] = panel_lines[0]
    return meta


def _wrap(text: str, font: str, size: float, max_width: float) -> List[str]:
    words = re.split(r"\s+", _clean(text))
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            if stringWidth(word, font, size) > max_width:
                chunk = ""
                for ch in word:
                    cand = chunk + ch
                    if stringWidth(cand, font, size) <= max_width:
                        chunk = cand
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                current = chunk
            else:
                current = word
    if current:
        lines.append(current)
    return lines


def _write_wrapped(c: canvas.Canvas, text: str, x: float, y: float, width: float,
                   font: str = "Courier", size: float = 12.5, leading: float = 19,
                   max_lines: Optional[int] = None) -> float:
    lines = _wrap(text, font, size, width)
    if max_lines is not None:
        lines = lines[:max_lines]
    c.setFont(font, size)
    c.setFillColor(CY["black"])
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def _write_bullet(c: canvas.Canvas, text: str, x: float, y: float, width: float,
                  size: float = 12.0, leading: float = 18.0) -> float:
    c.setFont("Courier-Bold", size)
    c.setFillColor(CY["black"])
    c.drawString(x, y, "•")
    return _write_wrapped(c, text, x + 18, y, width - 18, "Courier", size, leading)


def _draw_page_background(c: canvas.Canvas) -> None:
    c.drawImage(_get_template(), 0, 0, PAGE_W, PAGE_H, preserveAspectRatio=False, mask="auto")


def _title(c: canvas.Canvas, text: str, y: float = 790, size: float = 20) -> float:
    c.setFillColor(CY["black"])
    c.setFont("Courier-Bold", size)
    lines = _wrap(text, "Courier-Bold", size, PAGE_W - 80)
    yy = y
    for line in lines[:2]:
        c.drawCentredString(PAGE_W / 2, yy, line)
        yy -= size + 8
    return yy


def _safe_download(url: str) -> Optional[bytes]:
    try:
        req = Request(url, headers={"User-Agent": "DICOR-V300/1.0"})
        with urlopen(req, timeout=6) as response:
            data = response.read(12 * 1024 * 1024)
        return data or None
    except Exception:
        return None


def _download_many(urls: Sequence[str]) -> Dict[str, bytes]:
    result: Dict[str, bytes] = {}
    unique = list(dict.fromkeys(urls))
    if not unique:
        return result
    with ThreadPoolExecutor(max_workers=min(6, len(unique))) as pool:
        futures = {pool.submit(_safe_download, u): u for u in unique}
        for future in as_completed(futures):
            u = futures[future]
            try:
                data = future.result()
            except Exception:
                data = None
            if data:
                result[u] = data
    return result


def _image_reader(source: str, downloaded: Dict[str, bytes]) -> Optional[ImageReader]:
    try:
        if source in downloaded:
            return ImageReader(io.BytesIO(downloaded[source]))
        p = Path(source)
        if p.exists():
            return ImageReader(str(p))
    except Exception:
        return None
    return None


def _fit_image(c: canvas.Canvas, reader: ImageReader, x: float, y_top: float,
               box_w: float, box_h: float) -> Tuple[float, float]:
    iw, ih = reader.getSize()
    if not iw or not ih:
        return 0.0, 0.0
    scale = min(box_w / iw, box_h / ih)
    w = iw * scale
    h = ih * scale
    x2 = x + (box_w - w) / 2
    y2 = y_top - h
    c.drawImage(reader, x2, y2, w, h, preserveAspectRatio=True, mask="auto")
    return w, h


def _draw_contact_sheet(c: canvas.Canvas, images: Sequence[str], labels: Sequence[str],
                        downloaded: Dict[str, bytes], x0: float, y_top: float,
                        cols: int = 4, box_w: float = 155, box_h: float = 190,
                        gap_x: float = 18, gap_y: float = 20, max_rows: int = 2) -> float:
    shown = 0
    for row in range(max_rows):
        for col in range(cols):
            if shown >= len(images):
                return y_top - (row + 1) * (box_h + gap_y)
            src = images[shown]
            reader = _image_reader(src, downloaded)
            x = x0 + col * (box_w + gap_x)
            top = y_top - row * (box_h + gap_y)
            if reader:
                _fit_image(c, reader, x, top - 20, box_w, box_h - 45)
            label = labels[shown] if shown < len(labels) else ""
            if label:
                c.setFont("Courier-Bold", 9)
                c.setFillColor(CY["black"])
                c.drawCentredString(x + box_w / 2, top - box_h + 8, label[:24])
            shown += 1
    return y_top - max_rows * (box_h + gap_y)


def _labels_for_records(records: Sequence[Dict[str, Any]], count: int) -> List[str]:
    labels: List[str] = []
    for rec in records:
        text = " ".join([rec.get("title", ""), rec.get("topic", ""), rec.get("content", "")])
        found = re.findall(r"(?:nome|name)\s*[:\-]\s*([A-Za-zÀ-ÿ0-9 _'-]{2,40})", text, flags=re.I)
        if found:
            labels.append(found[0].strip())
        elif rec.get("title"):
            labels.append(rec["title"])
        else:
            labels.append("")
        if len(labels) >= count:
            break
    while len(labels) < count:
        labels.append("")
    return labels


def _draw_meta_page(c: canvas.Canvas, meta: Dict[str, str]) -> None:
    c.setFillColor(CY["black"])
    c.setFont("Courier-Bold", 13.0)
    c.drawString(74, 805, "Nº do Pedido de Pacificação:")
    c.setFont("Courier", 13.0)
    c.drawString(405, 805, meta["pedido"] or "A definir")
    c.setFont("Courier-Bold", 13.0)
    c.drawString(74, 773, "Data de Expedição:")
    c.setFont("Courier", 13.0)
    c.drawString(305, 773, meta["data"] or "A definir")
    c.setFont("Courier-Bold", 13.0)
    c.drawString(74, 741, "Nº do Processo:")
    c.setFont("Courier", 13.0)
    c.drawString(270, 741, meta["processo"] or "A definir")
    c.setFont("Courier-Bold", 14)
    c.drawString(74, 678, "Requerente:")
    _write_bullet(c, meta["requerente"], 74, 646, 645, size=12.0, leading=18)
    c.setFont("Courier-Bold", 14)
    c.drawString(74, 593, "Localização:")
    local = meta["local"] or "Não informado"
    intro = (
        f"A Polícia Federal de Capital Morada do Valley, por intermédio da DICOR, "
        f"requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção "
        f"da ordem e o cumprimento das determinações aplicáveis ao procedimento."
    )
    _write_bullet(c, intro, 74, 563, 645, size=12.0, leading=18)
    second = (
        f"Dessa forma, solicita-se a autorização para proceder com a busca e pacificação "
        f"no local denominado “{local}”, incluindo os pontos e instalações documentados "
        f"no dossiê operacional."
    )
    _write_bullet(c, second, 74, 467, 645, size=12.0, leading=18)


def _draw_dispositions(c: canvas.Canvas) -> None:
    _title(c, "DISPOSIÇÕES DO MANDADO", 790, 18)
    y = 735
    items = [
        "Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.",
        "Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.",
        "Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.",
        "Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.",
        "Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.",
        "O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente.",
    ]
    for item in items:
        y = _write_bullet(c, item, 38, y, 690, 12.2, 17)
        y -= 8


def _find_field_text(records: Sequence[Dict[str, Any]], needles: Sequence[str], fallback: str = "") -> str:
    wanted = [_norm(x) for x in needles]
    for rec in records:
        hay = _combined_text(rec)
        if any(w and w in hay for w in wanted):
            return rec.get("content") or rec.get("title") or fallback
    return fallback


def _draw_planning(c: canvas.Canvas, records: Sequence[Dict[str, Any]]) -> None:
    _title(c, "PLANEJAMENTO OPERACIONAL", 790, 18)
    c.setFont("Courier-Bold", 14)
    c.drawString(38, 730, "Para garantir o sucesso da operação, a investigação contará com:")
    blocks = [
        ("Efetivo envolvido:", ("efetivo", "equipe", "agentes", "participantes"), "Equipe registrada nas tarefas e tópicos da mesa."),
        ("Recursos utilizados:", ("recursos", "viaturas", "drones", "helicópteros", "helicopteros"), "Recursos descritos nos registros da mesa."),
        ("Estratégia de abordagem:", ("estrategia", "estratégia", "abordagem", "barreiras", "acesso"), "Estratégia encontrada nas mensagens e tarefas operacionais."),
        ("Medidas serão tomadas pra proteger a população local, incluindo:", ("proteção", "protecao", "moradores", "população", "populacao"), "Medidas e observações registradas nas informações gerais."),
    ]
    y = 685
    for label, needles, fallback in blocks:
        c.setFont("Courier-Bold", 13.2)
        c.drawString(38, y, label)
        y -= 27
        value = _find_field_text(records, needles, fallback)
        y = _write_bullet(c, value, 38, y, 690, 12.0, 17)
        y -= 20


def _draw_proof_page(c: canvas.Canvas, section_records: Sequence[Dict[str, Any]], downloaded: Dict[str, bytes]) -> None:
    _title(c, "PROVAS E DOCUMENTAÇÕES", 790, 18)
    y = 735
    intro = ("As provas e documentações gerais relativas ao processo permanecerão de uso restrito das autoridades competentes. "
             "Todas as evidências abaixo são consolidadas a partir das tarefas, tópicos e mensagens associadas à mesa.")
    y = _write_bullet(c, intro, 38, y, 690, 11.5, 16)
    y -= 15
    c.setFont("Courier-Bold", 13.2)
    c.drawString(38, y, "1. Foto do painel da organização.")
    y -= 28
    panel_text = _find_field_text(section_records, ("painel", "organização", "organizacao"), "Registro do painel da organização.")
    y = _write_bullet(c, panel_text, 38, y, 690, 11.2, 16)
    y -= 8
    c.setFont("Courier-Bold", 13.2)
    c.drawString(38, y, "Data e Local:")
    y -= 24
    y = _write_bullet(c, (section_records[0].get("date") if section_records and section_records[0].get("date") else "Conforme registro de origem da mesa."), 38, y, 690, 11.2, 16)
    y -= 10
    c.setFont("Courier-Bold", 13.2)
    c.drawString(38, y, "Descrição:")
    y -= 24
    y = _write_bullet(c, panel_text, 38, y, 690, 11.2, 16)
    y -= 10
    c.setFont("Courier-Bold", 13.2)
    c.drawString(38, y, "Relação com o Processo:")
    y -= 24
    y = _write_bullet(c, "Evidência vinculada aos registros de liderança e organização coletados na mesa.", 38, y, 690, 11.2, 16)
    y -= 12
    c.setFont("Courier-Bold", 13.2)
    c.drawString(38, y, "Mídia de Apoio:")
    y -= 22
    imgs = _section_images(section_records)
    if imgs:
        _draw_contact_sheet(c, imgs[:1], [""], downloaded, 245, y, cols=1, box_w=300, box_h=250, gap_x=0, gap_y=0, max_rows=1)


def _draw_generic_section(c: canvas.Canvas, section_num: int, title: str,
                          records: Sequence[Dict[str, Any]], downloaded: Dict[str, bytes],
                          max_images: int = 8) -> None:
    _title(c, f"{section_num}. {title}", 790, 17)
    y = 724
    texts = _all_text_for(records)
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Data e Local:")
    y -= 24
    date_text = next((r.get("date") for r in records if r.get("date")), "")
    y = _write_bullet(c, date_text or "Conforme registros da mesa.", 38, y, 690, 11.3, 16)
    y -= 12
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Descrição:")
    y -= 24
    desc = texts[0] if texts else "Informação registrada na tarefa/tópico correspondente."
    y = _write_bullet(c, desc, 38, y, 690, 11.3, 16)
    y -= 10
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Relação com o Processo:")
    y -= 24
    relation = texts[1] if len(texts) > 1 else "Registro vinculado ao conjunto de evidências da mesa."
    y = _write_bullet(c, relation, 38, y, 690, 11.3, 16)
    y -= 10
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Mídia de Apoio:")
    y -= 23
    imgs = _section_images(records)
    if imgs:
        subset = imgs[:max_images]
        labels = _labels_for_records(records, len(subset))
        if section_num == 2:
            _draw_contact_sheet(c, subset, labels, downloaded, 40, y, cols=4, box_w=145, box_h=200, gap_x=18, gap_y=20, max_rows=2)
        else:
            cols = 3 if len(subset) >= 6 else 2
            box_w = 205 if cols == 3 else 280
            gap_x = 30 if cols == 3 else 50
            _draw_contact_sheet(c, subset, labels, downloaded, 38, y, cols=cols, box_w=box_w, box_h=190, gap_x=gap_x, gap_y=18, max_rows=2)
    elif texts:
        y -= 10
        for line in texts[2:8]:
            y = _write_bullet(c, line, 38, y, 690, 10.8, 15)
            y -= 5


def _draw_leadership(c: canvas.Canvas, records: Sequence[Dict[str, Any]]) -> None:
    _title(c, "LIDERANÇA E INTEGRANTES IDENTIFICADOS", 790, 16.5)
    y = 720
    texts = _all_text_for(records)
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Líder:")
    y -= 26
    pairs = []
    blob = "\n".join(texts)
    rg_lines = re.findall(r"(?:nome|name)\s*[:\-]\s*([A-Za-zÀ-ÿ0-9 _'-]{2,40}).{0,80}?(?:rg|qra)\s*[:\-]\s*(\d+)", blob, flags=re.I|re.S)
    for name, rg in rg_lines:
        pairs.append((name.strip(), rg.strip()))
    if pairs:
        name, rg = pairs[0]
        y = _write_bullet(c, f"{name}   RG: {rg}", 38, y, 690, 12.0, 17)
        c.setFont("Courier-Bold", 13)
        c.drawString(38, y-5, "Gerentes:")
        y -= 30
        for name, rg in pairs[1:8]:
            y = _write_bullet(c, f"{name}   RG: {rg}", 38, y, 690, 11.4, 16)
            y -= 3
    else:
        c.setFont("Courier-Bold", 13)
        c.drawString(38, y, "Gerentes:")
        y -= 28
        for text in texts[:12]:
            y = _write_bullet(c, text, 38, y, 690, 11.2, 16)
            y -= 3


def _draw_motivation(c: canvas.Canvas, records: Sequence[Dict[str, Any]]) -> None:
    _title(c, "MOTIVAÇÃO", 790, 18)
    y = 735
    text = "\n".join(_all_text_for(records))
    articles = re.findall(r"Art\.?\s*\d+(?:\.\d+)?(?:\s*[-–]\s*[^\n,.]+)?", text, flags=re.I)
    c.setFont("Courier-Bold", 13)
    if articles:
        for art in articles[:8]:
            c.drawString(38, y, art[:90])
            y -= 22
    else:
        c.drawString(38, y, "Fundamentação:")
        y -= 26
    for reason in _all_text_for(records)[:10]:
        y = _write_bullet(c, reason, 38, y, 690, 11.3, 16)
        y -= 3
        if y < 220:
            break


def _draw_final(c: canvas.Canvas, meta: Dict[str, str], all_records: Sequence[Dict[str, Any]]) -> None:
    _title(c, "PROVAS E DOCUMENTAÇÕES", 790, 18)
    y = 735
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "DELEGADO RESPONSÁVEL:")
    y -= 28
    y = _write_bullet(c, meta["requerente"] or "Autoridade responsável", 38, y, 690, 11.6, 17)
    y -= 8
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Unidade:")
    y -= 26
    y = _write_bullet(c, "Polícia Federal - DICOR.", 38, y, 690, 11.6, 17)
    y -= 8
    c.setFont("Courier-Bold", 13)
    c.drawString(38, y, "Local / Data:")
    y -= 26
    y = _write_bullet(c, f"{meta['local'] or 'Não informado'} — {meta['data'] or 'Não informado'}", 38, y, 690, 11.6, 17)
    y -= 12
    summary = _all_text_for(all_records)
    if summary:
        c.setFont("Courier-Bold", 13)
        c.drawString(38, y, "Síntese:")
        y -= 24
        for item in summary[:8]:
            y = _write_bullet(c, item, 38, y, 690, 10.7, 15)
            y -= 2
            if y < 250:
                break
    c.setFont("Courier-Oblique", 13)
    c.drawString(150, 155, "____________________________")
    c.drawString(445, 155, "____________________________")
    c.setFont("Courier-Bold", 10.5)
    c.drawCentredString(225, 136, "RESPONSÁVEL")
    c.drawCentredString(520, 136, "DELEGADO GERAL DICOR")


def _page(c: canvas.Canvas, page_number: int, meta: Dict[str, str], sections: Dict[int, List[Dict[str, Any]]],
          all_records: List[Dict[str, Any]], downloaded: Dict[str, bytes]) -> None:
    _draw_page_background(c)
    if page_number == 1:
        _draw_meta_page(c, meta)
    elif page_number == 2:
        _draw_dispositions(c)
    elif page_number == 3:
        _draw_planning(c, all_records)
    elif page_number == 4:
        _draw_proof_page(c, sections[1], downloaded)
    elif page_number == 5:
        _draw_leadership(c, sections[1])
    elif page_number == 6:
        _draw_generic_section(c, 1, "Painel", sections[1], downloaded, max_images=1)
    elif page_number == 7:
        _draw_generic_section(c, 2, "Foto dos principais membros da organização", sections[2], downloaded, max_images=8)
    elif page_number == 17:
        _draw_motivation(c, sections[12] or all_records)
    elif page_number == 18:
        _draw_final(c, meta, all_records)
    else:
        sec = PAGE_TO_SECTION.get(page_number)
        if sec is None:
            _draw_generic_section(c, 12, SECTION_RULES[12][0], sections[12], downloaded)
        else:
            _draw_generic_section(c, sec, SECTION_RULES[sec][0], sections[sec], downloaded)


def gerar_pdf_dossie(bot_module: Any, dados: Any, caminho: Any) -> str:
    """Entrada estável para o bot. O gerador é inteiramente novo."""
    target = Path(str(caminho))
    target.parent.mkdir(parents=True, exist_ok=True)
    records = _collect_records(dados)
    sections = _build_sections(records)
    meta = _meta(records, dados)
    image_urls: List[str] = []
    for rec in records:
        image_urls.extend(rec.get("image_urls", []))
    downloaded = _download_many(list(dict.fromkeys(image_urls)))
    c = canvas.Canvas(str(target), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Dossiê Operacional — Polícia Federal / DICOR")
    c.setAuthor("POLÍCIA FEDERAL - DICOR")
    for page_number in range(1, 19):
        _page(c, page_number, meta, sections, records, downloaded)
        c.showPage()
    c.save()
    return str(target)


def gerar_pdf(bot_module: Any, dados: Any, caminho: Any) -> str:
    return gerar_pdf_dossie(bot_module, dados, caminho)


def install(bot_module: Any) -> None:
    print("✅ V300 Documento de Mesa instalado — layout PF/DICOR + tarefas/tópicos/mensagens + mídia.", flush=True)


__all__ = ["gerar_pdf_dossie", "gerar_pdf", "install"]
