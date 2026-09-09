# -*- coding: utf-8 -*-
"""DICOR V211 - coleta integral de dados e mídias para dossiês.

Camada de compatibilidade sobre dossie_v210:
- não altera o fluxo do bot;
- coleta recursivamente tarefas, tópicos, mensagens, campos e anexos;
- reconhece objetos Discord Attachment/Embed mesmo quando não são dicts;
- garante fotos de informante e demais mídias;
- remove limites artificiais de 8 URLs / 4 imagens por seção;
- mantém a geração PDF existente do V210.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import dossie_v210 as base

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
_SCOPE_KEYS = ("titulo", "title", "nome", "name", "topico", "topic", "tarefa", "task", "assunto", "categoria", "canal", "channel", "mensagem", "message", "tipo", "type")


def _txt(v: Any) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, str): return v.strip()
        if isinstance(v, (int, float, bool)): return str(v)
        if isinstance(v, (dict, list, tuple)): return json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        pass
    return str(v).strip()


def _norm(v: Any) -> str:
    s = _txt(v).casefold()
    s = re.sub(r"[^0-9a-záàâãéèêíìîóòôõúùûç]+", " ", s)
    return " ".join(s.split())


def _is_model_object(obj: Any) -> bool:
    return any(hasattr(obj, x) for x in ("url", "proxy_url", "filename", "attachments"))


def _object_mapping(obj: Any) -> Dict[str, Any]:
    if obj is None: return {}
    data: Dict[str, Any] = {}
    for name in ("id", "name", "title", "content", "description", "url", "proxy_url", "filename", "content_type", "width", "height", "jump_url", "channel_id", "message_id", "author", "created_at"):
        try:
            value = getattr(obj, name, None)
            if value not in (None, "", [], {}): data[name] = value
        except Exception:
            pass
    for child_name in ("image", "thumbnail", "video"):
        try:
            child = getattr(obj, child_name, None)
            if child:
                d = {}
                for k in ("url", "proxy_url", "width", "height"):
                    value = getattr(child, k, None)
                    if value not in (None, ""): d[k] = value
                if d: data[child_name] = d
        except Exception:
            pass
    return data


def _walk(value: Any, path: str = "", seen=None, budget: int = 250000) -> Iterable[Tuple[str, Any]]:
    if budget <= 0: return
    if seen is None: seen = set()
    if not isinstance(value, (str, int, float, bool, type(None))):
        ident = id(value)
        if ident in seen: return
        seen.add(ident)
    yield path, value
    if isinstance(value, dict):
        for k, child in value.items():
            yield from _walk(child, f"{path}.{k}" if path else str(k), seen, budget - 1)
    elif isinstance(value, (list, tuple, set)):
        for i, child in enumerate(value):
            yield from _walk(child, f"{path}[{i}]", seen, budget - 1)
    elif _is_model_object(value):
        for k, child in _object_mapping(value).items():
            yield from _walk(child, f"{path}.{k}" if path else k, seen, budget - 1)


def _collect_media(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    def add(url="", filename="", content_type="", source="", source_id="", kind=""):
        url = str(url or "").strip(); filename = str(filename or "").strip(); content_type = str(content_type or "").strip()
        if not (url or filename): return
        key = (url, filename, source_id, content_type)
        if key in seen: return
        seen.add(key)
        out.append({"url": url, "filename": filename, "content_type": content_type, "source": source, "source_id": source_id, "kind": kind})
    for path, obj in _walk(value):
        if isinstance(obj, dict):
            sid = str(obj.get("id") or obj.get("message_id") or obj.get("attachment_id") or "")
            for k in ("attachments", "anexos", "fotos", "imagens", "media", "mídia", "midia", "arquivos", "documentos"):
                items = obj.get(k)
                if items is None: continue
                items = items if isinstance(items, (list, tuple)) else [items]
                for item in items:
                    m = item if isinstance(item, dict) else _object_mapping(item)
                    add(m.get("url") or m.get("proxy_url"), m.get("filename") or m.get("name"), m.get("content_type") or m.get("type"), path, sid, k)
            if any(k in obj for k in ("url", "proxy_url")) and any(k in obj for k in ("filename", "content_type", "attachment_id")):
                add(obj.get("url") or obj.get("proxy_url"), obj.get("filename") or obj.get("name"), obj.get("content_type") or obj.get("type"), path, sid, "attachment")
        elif _is_model_object(obj):
            m = _object_mapping(obj)
            add(m.get("url") or m.get("proxy_url"), m.get("filename") or m.get("name"), m.get("content_type") or m.get("type"), path, str(m.get("message_id") or m.get("id") or ""), "object")
    return out


def _scope_text(record: Dict[str, Any]) -> str:
    return " ".join(_txt(record.get(k, "")) for k in _SCOPE_KEYS if _txt(record.get(k, "")))


def _make_complete_records(dados: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    all_media = _collect_media(dados)
    raw_records = []
    for path, obj in _walk(dados):
        if not isinstance(obj, dict): continue
        keys = {_norm(k) for k in obj.keys()}
        if any(x in keys for x in ("content", "conteudo", "texto", "mensagem", "message", "descricao", "description")) or any(x in keys for x in ("titulo", "title", "topico", "topic", "tarefa", "task", "assunto", "categoria")):
            raw_records.append((path, obj))
    enriched = []
    for path, rec in raw_records:
        scope = _scope_text(rec)
        media_here = _collect_media(rec)
        content_parts = []
        for k in ("content", "conteudo", "texto", "mensagem", "message", "descricao", "description", "resultado", "observacao", "observação"):
            v = _txt(rec.get(k))
            if v and v not in content_parts: content_parts.append(v)
        for k, v in rec.items():
            if k in ("content", "conteudo", "texto", "mensagem", "message", "descricao", "description", "resultado", "observacao", "observação"): continue
            sv = _txt(v)
            if sv and len(sv) < 6000: content_parts.append(f"{k}: {sv}")
        attachments = [{"url": m.get("url") or m.get("proxy_url") or "", "filename": m.get("filename") or "", "content_type": m.get("content_type") or ""} for m in media_here]
        images = [m.get("url") or m.get("proxy_url") for m in media_here if (str(m.get("content_type") or "").casefold().startswith("image/") or str(m.get("filename") or "").casefold().endswith(_IMAGE_EXTS) or any(e in str(m.get("url") or "").casefold() for e in _IMAGE_EXTS))]
        images = [x for x in images if x]
        ns = _norm(scope)
        enriched.append({
            "titulo": _txt(rec.get("titulo") or rec.get("title") or rec.get("tarefa") or rec.get("task") or rec.get("nome") or path),
            "title": _txt(rec.get("title") or rec.get("titulo") or ""),
            "topico": _txt(rec.get("topico") or rec.get("topic") or ""),
            "tarefa": _txt(rec.get("tarefa") or rec.get("task") or ""),
            "content": "\n".join(content_parts),
            "descricao": _txt(rec.get("descricao") or rec.get("description") or ""),
            "message_id": _txt(rec.get("message_id") or rec.get("id") or ""),
            "channel_id": _txt(rec.get("channel_id") or rec.get("canal_id") or ""),
            "source_path": path,
            "all_attachments": attachments,
            "fotos": images,
            "imagens": images,
            "informante": " ".join(content_parts) if "informante" in ns else "",
            "painel": scope if "painel" in ns else "",
            "membros": scope if any(x in ns for x in ("membro", "gerente", "lider")) else "",
            "localizacao": scope if any(x in ns for x in ("localização", "localizacao", "coordenadas", "endereco", "endereço")) else "",
            "visao_aerea": scope if any(x in ns for x in ("aerea", "aérea", "foto de cima")) else "",
            "materiais": scope if any(x in ns for x in ("material", "produto", "ingrediente")) else "",
            "compra": scope if any(x in ns for x in ("compra", "negociacao", "negociação")) else "",
            "bau_membros": scope if "bau de membros" in ns or "baú de membros" in ns else "",
            "bau_lider": scope if "bau de lider" in ns or "baú de líder" in ns else "",
            "fabricacao": scope if any(x in ns for x in ("fabricacao", "fabricação", "rota de farm")) else "",
            "producao": scope if any(x in ns for x in ("producao", "produção", "rota de producao")) else "",
            "informacoes_gerais": scope if any(x in ns for x in ("informações gerais", "informacoes gerais")) else "",
        })
    clone = dict(dados)
    clone["_v211_complete_records"] = enriched
    clone["_v211_all_media"] = all_media
    informants = [r for r in enriched if "informante" in _norm(r.get("titulo")) or "informante" in _norm(r.get("topico")) or "informante" in _norm(r.get("tarefa"))]
    clone["_v211_informante"] = {"registros": informants, "fotos": [u for r in informants for u in r.get("fotos", [])], "anexos": [a for r in informants for a in r.get("all_attachments", [])]}
    return clone, all_media


def _download_all(urls: Sequence[str], cache_dir: Path) -> List[str]:
    paths = []
    for url in urls:
        try:
            p = base._download_url(url, cache_dir)
            if p and str(p) not in paths: paths.append(str(p))
        except Exception: pass
    return paths


def _complete_section_payload(dados: Dict[str, Any], code: str) -> Dict[str, Any]:
    payload = base._collect_section_payload(dados, code)
    complete = dados.get("_v211_complete_records", []) if isinstance(dados, dict) else []
    _, title, aliases = next(x for x in base.SECTION_DEFS if x[0] == code)
    keys = [_norm(title)] + [_norm(a) for a in aliases]
    extras = []
    urls = list(payload.get("urls", []))
    for rec in complete:
        scope = _norm(_scope_text(rec) + " " + rec.get("titulo", ""))
        hit = any(k and k in scope for k in keys)
        if code == "07" and "informante" in scope: hit = True
        if not hit: continue
        if rec not in payload["records"]: extras.append(rec)
        for a in rec.get("all_attachments", []):
            if a.get("url") and a["url"] not in urls: urls.append(a["url"])
    payload["records"] = list(payload.get("records", [])) + extras
    payload["urls"] = urls
    if code == "07":
        for rec in complete:
            scope = _norm(_scope_text(rec) + " " + rec.get("titulo", ""))
            if "informante" in scope:
                for u in rec.get("fotos", []):
                    if u not in payload["urls"]: payload["urls"].append(u)
                for a in rec.get("all_attachments", []):
                    if a.get("url") and a["url"] not in payload["urls"]: payload["urls"].append(a["url"])
    return payload


def _write_section_complete(story: List[Any], payload: Dict[str, Any], styles: Dict[str, Any], cache_dir: Path) -> None:
    story.append(base._paragraph(f"PARTE {payload['code']}", styles["section_no"]))
    story.append(base._paragraph(payload["title"], styles["section"]))
    story.append(base.HRFlowable(width="100%", thickness=1, color=base.GOLD, spaceBefore=0, spaceAfter=10))
    lines = base._section_lines(payload)
    if lines:
        story.append(base._paragraph(lines[0], styles["body"]))
        if len(lines) > 1: story.extend(base._bullets(lines[1:], styles["body"]))
    else:
        story.append(base._paragraph("Nenhuma informação textual estruturada foi localizada nas tarefas, tópicos ou mensagens desta etapa.", styles["small"]))
    downloaded = _download_all(payload.get("urls", []), cache_dir)
    all_paths = list(dict.fromkeys([str(p) for p in (payload.get("local_files", []) or []) + downloaded if p]))
    if all_paths:
        story.append(base._paragraph(f"Mídias incorporadas: {len(all_paths)} arquivo(s).", styles["small"]))
        story.extend(base._image_flowables(all_paths, styles, max_images=max(1, len(all_paths))))
    elif payload.get("urls"):
        story.append(base._paragraph(f"Referências de mídia/anexo encontradas: {len(payload['urls'])}. As URLs permanecem vinculadas quando o download não foi possível.", styles["small"]))
    story.append(base.Spacer(1, 0.22 * base.cm))
    rel = base.Table([
        [base._paragraph("RELAÇÃO COM O PROCESSO", styles["label"]), base._paragraph("Consolidado automaticamente a partir de todas as tarefas, tópicos, mensagens e anexos vinculados à mesa.", styles["value"])],
        [base._paragraph("DATA / ORIGEM", styles["label"]), base._paragraph("Origem preservada nos registros da mesa operacional.", styles["value"])],
    ], colWidths=[4.3 * base.cm, 10.9 * base.cm])
    rel.setStyle(base.TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), base.NAVY), ("TEXTCOLOR", (0, 0), (0, -1), base.WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, base.LINE), ("INNERGRID", (0, 0), (-1, -1), 0.35, base.LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(rel)

_original_generate = base.gerar_pdf_dossie

def gerar_pdf_dossie(bot_module: Any, dados: Dict[str, Any], caminho: Any) -> str:
    dados2, _ = _make_complete_records(dados if isinstance(dados, dict) else {"dados": dados})
    old_collect = base._collect_section_payload
    old_write = base._write_section
    try:
        base._collect_section_payload = _complete_section_payload
        base._write_section = _write_section_complete
        return _original_generate(bot_module, dados2, caminho)
    finally:
        base._collect_section_payload = old_collect
        base._write_section = old_write


def gerar_pdf(bot_module: Any, dados: Dict[str, Any], caminho: Any) -> str:
    return gerar_pdf_dossie(bot_module, dados, caminho)


def install(bot_module: Any) -> None:
    print("✅ V211 Dossiê integral instalado — todos os campos, tarefas, tópicos, mensagens e mídias; informante reforçado.", flush=True)

__all__ = ["gerar_pdf_dossie", "gerar_pdf", "install"]
