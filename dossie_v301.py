# -*- coding: utf-8 -*-
"""
DICOR V301 — gerador novo de documento de mesa.

Motor independente do gerador anterior.
O PDF é desenhado diretamente no canvas usando o layout visual aprovado
como fundo fixo. O conteúdo vem das tarefas, tópicos e mensagens da mesa.

Interface compatível:
    gerar_pdf_dossie(bot_module, dados, caminho)
    gerar_pdf(bot_module, dados, caminho)
    install(bot_module)
"""
from __future__ import annotations

import base64
import io
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W, PAGE_H = A4
TEMPLATE_B64 = "__TEMPLATE_B64__"

SOURCE_ALIASES = (
    "origem", "source", "canal", "channel", "channel_name", "parent_name",
    "parent", "categoria", "category"
)
TOPIC_ALIASES = (
    "topico", "tópico", "topic", "thread", "thread_name", "nome_topico",
    "nome_tópico", "nome", "name", "titulo", "título", "title", "assunto"
)
CONTENT_ALIASES = (
    "conteudo", "conteúdo", "content", "texto", "text", "mensagem",
    "message", "descricao", "descrição", "description", "resultado",
    "observacao", "observação", "valor", "value"
)
AUTHOR_ALIASES = ("autor", "author", "autor_nome", "author_name", "usuario", "user")
DATE_ALIASES = ("data", "date", "timestamp", "created_at", "criado_em", "created")

SECTIONS: Dict[int, Tuple[str, Tuple[str, ...]]] = {
    1: ("Foto do painel da organização.", ("painel", "fotos líderes", "fotos lideres", "liderança", "lideranca")),
    2: ("Foto dos principais membros da organização.", ("fotos dos membros", "fotos membros", "principais membros", "membros", "integrantes")),
    3: ("Localização da organização.", ("localização", "localizacao", "coordenadas", "endereço", "endereco")),
    4: ("Foto de cima da organização para realizar estratégia de pacificação.", ("foto de cima", "visão aérea", "visao aerea", "aérea", "aerea", "visão superior", "visao superior")),
    5: ("Material que vendem.", ("material que vendem", "materiais", "ingredientes base", "produtos", "mercadorias", "vendas")),
    6: ("Registrar compra do ilícito em frente ou dentro da comunidade/organização.", ("registrar compra", "compra do ilícito", "compra do ilicito", "compra", "negociação", "negociacao")),
    7: ("Foto do informante da organização.", ("informante", "foto do informante", "informações do informante", "informacoes do informante")),
    8: ("Foto do baú de membros.", ("baú de membros", "bau de membros", "baú membros", "bau membros")),
    9: ("Foto do baú de líder.", ("baú de líder", "bau de lider", "baú líder", "bau lider")),
    10: ("Foto e localização do local de fabricação.", ("local de fabricação", "local de fabricacao", "fabricação", "fabricacao", "rota de farm", "farm")),
    11: ("Foto e localização do local de produção.", ("local de produção", "local de producao", "produção", "producao", "rota de produção", "rota de producao", "escoamento")),
    12: ("Informações gerais.", ("informações gerais", "informacoes gerais", "informação geral", "informacao geral", "geral")),
}


def _norm(value: Any) -> str:
    s = str(value or "").casefold()
    for a, b in (("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),
                 ("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")):
        s = s.replace(a, b)
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s).split())


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _first(d: Dict[str, Any], aliases: Sequence[str]) -> str:
    wanted = {_norm(x) for x in aliases}
    for k, v in d.items():
        if _norm(k) in wanted and _clean(v):
            return _clean(v)
    return ""


def _walk(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield from _walk(v, p)
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _urls(value: Any) -> List[str]:
    out: List[str] = []
    def add(s: str) -> None:
        for u in re.findall(r"https?://[^\s<>\]\)]+", s or ""):
            u = u.rstrip(".,);]")
            if u not in out:
                out.append(u)
    if isinstance(value, str):
        add(value)
    elif isinstance(value, dict):
        for v in value.values():
            for u in _urls(v):
                if u not in out:
                    out.append(u)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            for u in _urls(v):
                if u not in out:
                    out.append(u)
    return out


def _records(dados: Any) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for path, obj in _walk(dados):
        if not isinstance(obj, dict):
            continue
        source = _first(obj, SOURCE_ALIASES)
        topic = _first(obj, TOPIC_ALIASES)
        content = _first(obj, CONTENT_ALIASES)
        author = _first(obj, AUTHOR_ALIASES)
        date = _first(obj, DATE_ALIASES)
        urls = _urls(obj)
        if not any((source, topic, content, author, date, urls)):
            continue
        sig = (_norm(topic), _norm(content)[:700], date, tuple(urls))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"path":path,"source":source,"topic":topic,"title":topic,
                    "content":content,"author":author,"date":date,"urls":urls,"raw":obj})
    return out


def _section_match(rec: Dict[str, Any]) -> Optional[int]:
    hay = _norm(" ".join((rec.get("source",""), rec.get("topic",""), rec.get("title",""), rec.get("content",""), rec.get("path",""))))
    topic_hay = _norm(" ".join((rec.get("source",""), rec.get("topic",""), rec.get("title",""))))
    scores: Dict[int, int] = {}
    for n, (_, aliases) in SECTIONS.items():
        score = 0
        for a in aliases:
            na = _norm(a)
            if na and na in hay:
                score += 5 if na in topic_hay else 1
        if score:
            scores[n] = score
    return max(scores, key=scores.get) if scores else None


def _split_lines(text: str, width: float, font: str, size: float) -> List[str]:
    words = re.sub(r"\s+", " ", str(text or "").strip()).split(" ")
    lines, current = [], ""
    for word in words:
        candidate = word if not current else current + " " + word
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _date(value: str) -> str:
    s = str(value or "").strip()
    for pat, fn in (
        (r"(\d{4})[-/](\d{2})[-/](\d{2})", lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}"),
        (r"(\d{2})[-/](\d{2})[-/](\d{4})", lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}"),
    ):
        m = re.search(pat, s)
        if m:
            return fn(m)
    return s or "Não informado"


def _meta(records: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    vals = {"pedido":"","data":"","processo":"","requerente":"","local":"","organizacao":"","responsavel":""}
    mapping = {
        "pedido":("nº do pedido de pacificação","numero do pedido","numero_pedido","pedido","referência","referencia"),
        "data":("data de expedição","data_expedicao","data","expedicao"),
        "processo":("nº do processo","numero processo","numero_processo","processo"),
        "requerente":("requerente","solicitante"),
        "local":("localização","localizacao","endereço","endereco","local"),
        "organizacao":("organização","organizacao","comunidade","grupo","alvo"),
        "responsavel":("delegado","autoridade","responsavel","responsável")}
    raws = [r.get("raw") for r in records if isinstance(r.get("raw"), dict)]
    for dest, aliases in mapping.items():
        for raw in raws:
            v = _first(raw, aliases)
            if v:
                vals[dest] = v
                break
    vals["data"] = _date(vals["data"] or datetime.now().strftime("%d/%m/%Y"))
    vals["pedido"] = vals["pedido"] or "A definir"
    vals["processo"] = vals["processo"] or "PF-DICOR-A DEFINIR"
    vals["requerente"] = vals["requerente"] or "Polícia Federal - DICOR"
    vals["local"] = vals["local"] or "Não informado"
    vals["organizacao"] = vals["organizacao"] or "Não identificada"
    vals["responsavel"] = vals["responsavel"] or "Autoridade DICOR"
    return vals

_TEMPLATE: Optional[ImageReader] = None

def _template() -> ImageReader:
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = ImageReader(io.BytesIO(base64.b64decode(TEMPLATE_B64)))
    return _TEMPLATE


def _bg(c: canvas.Canvas):
    c.drawImage(_template(), 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=False, mask="auto")


def _text(c, x, y, text, size=10.2, bold=False, maxw=505, leading=13):
    font = "Courier-Bold" if bold else "Courier"
    lines = _split_lines(text, maxw, font, size)
    c.setFillColor(colors.HexColor("#101010"))
    c.setFont(font, size)
    yy = y
    for line in lines:
        c.drawString(x, yy, line)
        yy -= leading
    return yy


def _evidence(records: Sequence[Dict[str, Any]]) -> Tuple[str,str,str,List[str]]:
    texts, dates, urls = [], [], []
    for r in records:
        for v in (r.get("content"), r.get("title"), r.get("source")):
            s = _clean(v)
            if s and s not in texts:
                texts.append(s)
        if r.get("date"):
            d = _date(r["date"])
            if d not in dates:
                dates.append(d)
        for u in r.get("urls",[]):
            if u not in urls:
                urls.append(u)
    desc = " ".join(texts[:4]).strip() or "Informação registrada nas tarefas e mensagens da mesa."
    proc = "Evidência vinculada ao processo por meio dos registros originais da mesa operacional."
    when = " / ".join(dates[:3]) if dates else "Conforme registro da mesa."
    return desc, proc, when, urls


def _download(url: str, cache: Path) -> Optional[Path]:
    try:
        cache.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^0-9A-Za-z._-]", "_", url.rsplit("/",1)[-1] or "midia")[:90]
        if "." not in name:
            name += ".jpg"
        p = cache/name
        if not p.exists():
            req = urllib.request.Request(url, headers={"User-Agent":"DICOR-V301"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data = r.read(6*1024*1024)
            if data:
                p.write_bytes(data)
        return p if p.exists() and p.stat().st_size else None
    except Exception:
        return None


def _draw_images(c, urls: Sequence[str], x: float, y: float, maxw: float, maxh: float, cache: Path):
    shown = 0
    for url in urls:
        if shown >= 4:
            break
        p = _download(url, cache)
        if not p:
            continue
        try:
            img = ImageReader(str(p)); iw, ih = img.getSize()
            scale = min(maxw/iw, maxh/ih)
            dw, dh = iw*scale, ih*scale
            c.drawImage(img, x+(maxw-dw)/2, y, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
            x += maxw+8
            shown += 1
        except Exception:
            continue


def gerar_pdf_dossie(bot_module: Any, dados: Any, caminho: Any) -> str:
    if not isinstance(dados,(dict,list,tuple)):
        dados = {"dados":dados}
    target = Path(caminho); target.parent.mkdir(parents=True, exist_ok=True)
    cache = target.parent/".dossie_v301_media"
    recs = _records(dados); meta = _meta(recs)
    sections = {n:[] for n in SECTIONS}
    for r in recs:
        sec = _section_match(r)
        if sec: sections[sec].append(r)

    c = canvas.Canvas(str(target), pagesize=A4, pageCompression=1)
    c.setTitle(f"Dossiê DICOR - {meta['organizacao']}"); c.setAuthor("POLÍCIA FEDERAL - DICOR")

    # Página 1 — capa/pedido
    _bg(c); y = PAGE_H-170
    y = _text(c,45,y,f"Nº do Pedido de Pacificação:  {meta['pedido']}",10.2,True)
    y -= 12; y = _text(c,45,y,f"Data de Expedição:           {meta['data']}",10.2)
    y -= 12; y = _text(c,45,y,f"Nº do Processo:             {meta['processo']}",10.2,True)
    y -= 35; y = _text(c,45,y,"Requerente:",11,True); y -= 22
    y = _text(c,58,y,f"• {meta['requerente']}.",10)
    y -= 38; y = _text(c,45,y,"Localização:",11,True); y -= 22
    y = _text(c,58,y,"• A Polícia Federal - DICOR requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.",9.6,maxw=510,leading=13)
    y -= 30; _text(c,58,y,f"• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{meta['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional.",9.6,maxw=510,leading=13)
    c.showPage()

    # Página 2 — disposições
    _bg(c); y = PAGE_H-170; _text(c,170,y,"DISPOSIÇÕES DO MANDADO",12,True,maxw=420); y -= 42
    for item in (
        "Fica autorizada a busca nos locais diretamente relacionados ao objeto da investigação.",
        "Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, sem relação com os fatos apurados, deverá ser apreendido.",
        "Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser registrada a extensão necessária da diligência.",
        "A documentação e as mídias deverão permanecer vinculadas ao respectivo processo.",
        "Os investigados identificados deverão ser apresentados à autoridade competente conforme o procedimento do servidor."):
        y = _text(c,45,y,"• "+item,9.5,maxw=520,leading=14)-8
    c.showPage()

    # Página 3 — planejamento
    _bg(c); y = PAGE_H-170; _text(c,170,y,"PLANEJAMENTO OPERACIONAL",12,True,maxw=420); y -= 42
    y = _text(c,45,y,"Para garantir o sucesso da pacificação, a operação contará com:",10.2,True,maxw=520); y -= 28
    for lab, val in (
        ("Efetivo envolvido:","Registros de usuários, responsáveis e equipes encontrados nas tarefas e tópicos da mesa."),
        ("Recursos utilizados:","Fotografias, vídeos, documentos, localizações e demais evidências efetivamente registradas."),
        ("Estratégia de abordagem:","Organização da área por pontos, acessos e informações encontradas nos registros da mesa."),
        ("Medidas serão tomadas pra proteger a população local, incluindo:","Medidas de preservação e controle registradas no planejamento operacional.")):
        y = _text(c,45,y,lab,10.0,True,maxw=520)-5
        y = _text(c,58,y,"• "+val,9.4,maxw=505,leading=13)-16
    c.showPage()

    # Páginas 4–15: Provas e as 12 tarefas da mesa
    for n in range(1,13):
        _bg(c); y = PAGE_H-170
        title = SECTIONS[n][0]
        y = _text(c,45,y,f"{n}. {title}",10.4,True,maxw=520,leading=14)-35
        desc, proc, when, urls = _evidence(sections[n])
        for lab, val in (("Data e Local:",when),("Descrição:",desc),("Relação com o Processo:",proc)):
            y = _text(c,45,y,lab,10.0,True,maxw=515)-5
            y = _text(c,58,y,"• "+val,9.3,maxw=505,leading=13)-13
        y = _text(c,45,y,"Mídia de Apoio:",10.0,True,maxw=515)-4
        if n == 7:
            info=[]
            for r in sections[n]:
                raw=r.get("raw",{})
                if isinstance(raw,dict):
                    nome=_first(raw,("nome","nome_informante","informante"))
                    rg=_first(raw,("rg","passaporte","id"))
                    if nome and nome not in info: info.append(nome)
                    if rg and ("RG: "+rg) not in info: info.append("RG: "+rg)
            if info:
                y=_text(c,58,y,"• "+" | ".join(info[:3]),9.3,maxw=505)-8
        if urls:
            y=_text(c,58,y,f"• {len(urls)} mídia(s) localizada(s) nas mensagens/tópicos.",9.2,maxw=505)-8
            _draw_images(c,urls,45,max(60,y-205),120,185,cache)
        else:
            _text(c,58,y,"• Nenhuma mídia válida foi recuperada para esta seção.",9.2,maxw=505)
        c.showPage()

    # Página 16 — motivação
    _bg(c); y=PAGE_H-170; _text(c,45,y,"MOTIVAÇÃO",12,True,maxw=500); y-=45
    candidates=[]
    for r in recs:
        raw=r.get("raw",{})
        if isinstance(raw,dict):
            v=_first(raw,("motivo","motivação","motivacao","justificativa","fundamentação","fundamentacao","contexto"))
            if v and v not in candidates: candidates.append(v)
    if not candidates:
        candidates=["A motivação é composta pelas evidências efetivamente registradas nas tarefas, tópicos e mensagens da mesa operacional."]
    for v in candidates[:7]:
        y=_text(c,58,y,"• "+v,9.5,maxw=505,leading=13)-8
    c.showPage()

    # Página 17 — encerramento e assinatura
    _bg(c); y=PAGE_H-170; _text(c,45,y,"PROVAS E DOCUMENTAÇÕES",12,True,maxw=500); y-=42
    _text(c,45,y,"DELEGADO RESPONSÁVEL:",10.5,True,maxw=500); y-=28
    _text(c,58,y,meta["responsavel"],10,maxw=500); y-=25
    _text(c,58,y,"Polícia Federal - DICOR.",10,maxw=500); y-=45
    _text(c,45,y,"Com base nas provas apresentadas, registra-se a consolidação das evidências da mesa e a adoção das medidas operacionais cabíveis.",9.5,maxw=510,leading=13)
    y-=110; c.setFont("Courier-Bold",9); c.setFillColor(colors.HexColor("#101010"))
    c.drawCentredString(PAGE_W*0.30,y,"____________________________"); c.drawCentredString(PAGE_W*0.70,y,"____________________________")
    y-=18; c.setFont("Courier",8.5)
    c.drawCentredString(PAGE_W*0.30,y,"DELEGADO RESPONSÁVEL"); c.drawCentredString(PAGE_W*0.70,y,"DELEGADO GERAL / AUTORIDADE DICOR")
    c.save()
    return str(target)


def gerar_pdf(bot_module: Any, dados: Any, caminho: Any) -> str:
    return gerar_pdf_dossie(bot_module, dados, caminho)


def install(bot_module: Any) -> None:
    print("✅ V301 Dossiê: novo gerador canvas-only carregado; layout PF/DICOR e coleta por tarefas/tópicos/mensagens.", flush=True)

__all__ = ["gerar_pdf_dossie", "gerar_pdf", "install"]
