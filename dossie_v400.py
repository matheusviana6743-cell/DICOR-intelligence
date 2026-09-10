# -*- coding: utf-8 -*-
"""DICOR V400 - gerador de documentos das mesas.

Gerador independente, sem reaproveitar os renderizadores anteriores.
O layout usa exclusivamente a arte-base limpa PF/DICOR versionada no repositório.
Os dados variáveis são coletados de tarefas, tópicos, mensagens, autores, datas,
anexos e registros estruturados fornecidos pelo fluxo da mesa.
"""
from __future__ import annotations

import io
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Dict, List, Sequence, Tuple

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W, PAGE_H = 768, 1056
TEMPLATE_FILE = "dicor_template_clean3.png"
FONT = "Courier"
FONT_BOLD = "Courier-Bold"
BLACK = (0.08, 0.08, 0.08)

SECTION_RULES = {
    1: ("Foto do painel da organização.", ("painel", "fotos líderes", "fotos lideres", "liderança", "lideranca")),
    2: ("Foto dos principais membros da organização.", ("fotos dos membros", "fotos membros", "principais membros", "membros", "integrantes", "gerentes")),
    3: ("Localização da organização.", ("localização", "localizacao", "coordenadas", "endereço", "endereco")),
    4: ("Foto de cima da organização para realizar estratégia de pacificação:", ("foto de cima", "visão aérea", "visao aerea", "aérea", "aerea", "vista aérea", "vista aerea")),
    5: ("Material que vendem.", ("material que vendem", "materiais", "ingredientes base", "produtos", "mercadorias", "vendas")),
    6: ("Registrar compra do ilícito em frente ou dentro da comunidade/organização.", ("registrar compra", "compra do ilícito", "compra do ilicito", "compra", "negociação", "negociacao")),
    7: ("Foto do informante da organização.", ("informante", "foto do informante", "informações do informante", "informacoes do informante")),
    8: ("Foto do baú de membros.", ("baú de membros", "bau de membros", "baú membros", "bau membros")),
    9: ("Foto do baú de líder.", ("baú de líder", "bau de lider", "baú líder", "bau lider")),
    10: ("Foto e localização do local de fabricação.", ("local de fabricação", "local de fabricacao", "fabricação", "fabricacao", "rota de farm", "farm")),
    11: ("Foto e localização do local de produção.", ("local de produção", "local de producao", "produção", "producao", "rota de produção", "rota de producao", "escoamento")),
    12: ("Informações gerais.", ("informações gerais", "informacoes gerais", "informação geral", "informacao geral", "geral", "rádio", "radio", "crimes da comunidade")),
}

def norm(v: Any) -> str:
    s = str(v or "").casefold().translate(str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc"))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s).split())

def clean(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float, bool)):
        return str(v)
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        return str(v)

def walk(v: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(v, dict):
        yield path, v
        for k, child in v.items():
            yield from walk(child, f"{path}.{k}" if path else str(k))
    elif isinstance(v, (list, tuple, set)):
        for i, child in enumerate(v):
            yield from walk(child, f"{path}[{i}]")
    else:
        yield path, v

def pick(d: Dict[str, Any], aliases: Sequence[str]) -> str:
    wanted = {norm(x) for x in aliases}
    for k, v in d.items():
        if norm(k) in wanted and clean(v):
            return clean(v)
    return ""

def all_urls(v: Any) -> List[str]:
    found: List[str] = []
    for _, obj in walk(v):
        vals = re.findall(r"https?://[^\s<>\]\)]+", obj) if isinstance(obj, str) else []
        if isinstance(obj, dict):
            vals += [obj.get(k, "") for k in ("url", "proxy_url", "attachment_url", "image_url", "thumbnail_url", "media_url", "video_url")]
        for u in vals:
            if isinstance(u, str) and u.startswith("http"):
                u = u.rstrip(".,);]")
                if u not in found:
                    found.append(u)
    return found

def image_urls(v: Any) -> List[str]:
    out: List[str] = []
    hints = ("attachment", "attachments", "image", "images", "photo", "photos", "media", "thumbnail", "embed", "arquivo", "anexo", "foto")
    for path, obj in walk(v):
        hint = norm(path)
        if isinstance(obj, str):
            candidates = re.findall(r"https?://[^\s<>\]\)]+", obj)
        elif isinstance(obj, dict):
            candidates = [obj.get(k, "") for k in ("url", "proxy_url", "attachment_url", "image_url", "thumbnail_url", "media_url")]
        else:
            candidates = []
        for u in candidates:
            if not isinstance(u, str) or not u.startswith("http"):
                continue
            u = u.rstrip(".,);]")
            ext = Path(u.split("?", 1)[0]).suffix.casefold()
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp") or any(k in hint for k in hints):
                if u not in out:
                    out.append(u)
    return out

def record_list(data: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for path, obj in walk(data):
        if not isinstance(obj, dict):
            continue
        row = {
            "id": pick(obj, ("id", "message_id", "thread_id", "task_id", "record_id")),
            "title": pick(obj, ("titulo", "título", "title", "nome", "name", "assunto", "subject")),
            "topic": pick(obj, ("topico", "tópico", "topic", "thread", "thread_name", "nome_topico", "nome_tópico")),
            "task": pick(obj, ("tarefa", "task", "task_name", "nome_tarefa")),
            "source": pick(obj, ("origem", "source", "canal", "channel", "channel_name", "parent_name")),
            "content": pick(obj, ("conteudo", "conteúdo", "content", "texto", "text", "mensagem", "message", "descricao", "descrição", "description", "observacao", "observação", "valor", "value", "resultado", "result")),
            "author": pick(obj, ("autor", "author", "autor_nome", "author_name", "usuario", "user", "membro")),
            "date": pick(obj, ("data", "date", "timestamp", "created_at", "criado_em", "created", "quando")),
            "raw": obj,
            "urls": all_urls(obj),
            "image_urls": image_urls(obj),
        }
        if not any(row[k] for k in ("title", "topic", "task", "source", "content", "author", "date", "image_urls")):
            continue
        sig = row["id"] or f"{path}|{row['title']}|{row['topic']}|{row['content'][:500]}"
        if sig in seen:
            continue
        seen.add(sig)
        rows.append(row)
    return rows

def classify(row: Dict[str, Any]) -> int:
    head = norm(" ".join((row["task"], row["topic"], row["title"], row["source"])))
    body = norm(row["content"])
    best, best_score = 12, 0
    for number, (_, aliases) in SECTION_RULES.items():
        score = 0
        for alias in aliases:
            a = norm(alias)
            if a and a in head:
                score += 8
            elif a and a in body:
                score += 1
        if score > best_score:
            best_score, best = score, number
    return best

def first_value(rows: List[Dict[str, Any]], keys: Sequence[str], default: str) -> str:
    for row in rows:
        raw = row.get("raw", {})
        if isinstance(raw, dict):
            v = pick(raw, keys)
            if v:
                return v
    return default

def metadata(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    ids = [r["id"] for r in rows if str(r.get("id", "")).isdigit()]
    ident = next((x for x in ids if len(str(x)) >= 6), "MESA")
    return {
        "pedido": first_value(rows, ("nº do pedido de pacificação", "numero do pedido", "numero_pedido", "pedido"), f"INV-{str(ident)[-6:]}"),
        "data": first_value(rows, ("data de expedição", "data de expedicao", "data_expedicao"), datetime.now().strftime("%d/%m/%Y")),
        "processo": first_value(rows, ("nº do processo", "numero processo", "numero_processo", "processo", "protocolo"), f"PF-DICOR-{ident}"),
        "requerente": first_value(rows, ("requerente", "solicitante", "responsavel", "responsável", "autoridade"), "Polícia Federal - DICOR"),
        "organizacao": first_value(rows, ("organização", "organizacao", "comunidade", "grupo", "alvo", "investigado"), "Não identificado"),
        "local": first_value(rows, ("localização", "localizacao", "endereco", "endereço", "local", "cidade"), "Não informado"),
    }

def template_image() -> Image.Image:
    return Image.open(Path(__file__).with_name(TEMPLATE_FILE)).convert("RGB")

def draw_background(c: canvas.Canvas) -> None:
    c.drawImage(ImageReader(template_image()), 0, 0, width=PAGE_W, height=PAGE_H)

def wrap(text: str, size: float, max_width: float) -> List[str]:
    safe = re.sub(r"/tmp/[^\s]+", "", str(text or ""))
    out: List[str] = []
    for paragraph in safe.splitlines() or [""]:
        cur = ""
        for word in paragraph.split():
            cand = word if not cur else f"{cur} {word}"
            if stringWidth(cand, FONT, size) <= max_width:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = word
        if cur:
            out.append(cur)
    return out

def write_block(c: canvas.Canvas, text: str, x: float, y: float, size: float = 11.2, bold: bool = False,
                max_width: float = 680, leading: float = 16.5, max_lines: int = 30) -> float:
    c.setFillColorRGB(*BLACK)
    c.setFont(FONT_BOLD if bold else FONT, size)
    for line in wrap(text, size, max_width)[:max_lines]:
        c.drawString(x, y, line)
        y -= leading
    return y

def write_label(c: canvas.Canvas, label: str, x: float, y: float, size: float = 12) -> None:
    c.setFillColorRGB(*BLACK)
    c.setFont(FONT_BOLD, size)
    c.drawString(x, y, label)

def download_one(url: str, cache: Path) -> Path | None:
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / (str(abs(hash(url))) + ".jpg")
    if p.exists() and p.stat().st_size:
        return p
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DICOR-V400"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read(12 * 1024 * 1024)
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((1800, 1800))
        im.save(p, "JPEG", quality=90)
        return p
    except Exception:
        return None

def download_images(urls: Sequence[str], cache: Path) -> List[Path]:
    result: List[Path] = []
    unique = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(download_one, u, cache) for u in unique]
        for f in as_completed(futures):
            try:
                p = f.result()
                if p:
                    result.append(p)
            except Exception:
                pass
    return result

def place_image(c: canvas.Canvas, path: Path, x: float, y: float, w: float, h: float) -> None:
    try:
        im = Image.open(path)
        iw, ih = im.size
        scale = min(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(str(path), x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, preserveAspectRatio=True, mask="auto")
    except Exception:
        pass

def grid(c: canvas.Canvas, imgs: List[Path], x: float, y: float, w: float, h: float, cols: int) -> None:
    if not imgs:
        return
    gap = 10
    rows = (len(imgs) + cols - 1) // cols
    cw = (w - gap * (cols - 1)) / cols
    ch = (h - gap * (rows - 1)) / rows
    for i, img in enumerate(imgs):
        rr, cc = divmod(i, cols)
        place_image(c, img, x + cc * (cw + gap), y + h - (rr + 1) * ch - rr * gap, cw, ch)

def evidence_page(c: canvas.Canvas, n: int, title: str, rows: List[Dict[str, Any]], cache: Path, images_max: int = 4) -> None:
    draw_background(c)
    write_block(c, f"{n}. {title}", 40, 830, 11.7, True, 680, 17, 2)
    dates = "; ".join(dict.fromkeys(r["date"] for r in rows if r["date"])) or "Data e local conforme registros."
    desc = " ".join(r["content"] for r in rows if r["content"]) or "Nenhuma informação textual localizada."
    write_label(c, "Data e Local:", 40, 780); write_block(c, "• " + dates, 58, 756, 10.8, False, 640, 16, 4)
    write_label(c, "Descrição:", 40, 705); write_block(c, "• " + desc, 58, 681, 10.4, False, 640, 15.5, 6)
    write_label(c, "Relação com o Processo:", 40, 575); write_block(c, "• Informação consolidada a partir das tarefas, tópicos e mensagens vinculadas à etapa.", 58, 551, 10.4, False, 640, 15.5, 4)
    write_label(c, "Mídia de Apoio:", 40, 470); write_block(c, f"• Registros de mídia encontrados: {sum(len(r['image_urls']) for r in rows)}.", 58, 446, 10.5, False, 640, 16, 2)
    imgs = download_images([u for r in rows for u in r["image_urls"]], cache)
    if imgs:
        if n == 4:
            grid(c, imgs[:6], 195, 90, 430, 300, 3)
        else:
            place_image(c, imgs[0], 150, 80, 470, 330)
    c.showPage()

def generate(bot_module: Any, dados: Any, caminho: Any) -> str:
    rows = record_list(dados)
    sections = {n: [] for n in SECTION_RULES}
    for row in rows:
        sections[classify(row)].append(row)
    m = metadata(rows)
    cache = Path(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")) / "dossie_media_cache_v400"
    out = Path(caminho)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(PAGE_W, PAGE_H))

    # 18 páginas seguindo a composição do modelo de referência.
    page1 = c
    draw_background(page1)
    y = 800
    write_block(page1, f"N° do Pedido de Pacificação:   {m['pedido']}", 40, y, 12.3, True, 690, 18, 1); y -= 33
    write_block(page1, f"Data de Expedição:      {m['data']}", 40, y, 12.0, False, 690, 18, 1); y -= 33
    write_block(page1, f"N° do Processo:   {m['processo']}", 40, y, 12.3, True, 690, 18, 1); y -= 58
    write_label(page1, "Requerente:", 40, y); y -= 28
    y = write_block(page1, "• " + m["requerente"], 58, y, 11.3, False, 650, 17, 2) - 25
    write_label(page1, "Localização:", 40, y); y -= 28
    intro1 = f"• {m['requerente']}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento."
    intro2 = f"• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{m['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional."
    y = write_block(page1, intro1, 58, y, 11.2, False, 650, 17, 7) - 8
    write_block(page1, intro2, 58, y, 11.2, False, 650, 17, 5); page1.showPage()

    draw_background(c); y=830; write_block(c,"DISPOSIÇÕES DO MANDADO",205,y,14,True,360,18,1); y-=55
    for item in [
        "Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.",
        "Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.",
        "Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.",
        "Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.",
        "Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.",
        "O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente.",
    ]:
        c.drawString(40,y,"•"); y=write_block(c,item,56,y,11.4,False,650,17,5)-8
    c.showPage()

    draw_background(c); write_block(c,"PLANEJAMENTO OPERACIONAL",185,830,14,True,400,18,1); y=780
    write_block(c,"Para garantir o sucesso da pacificação, a operação contará com:",40,y,12,True,680,18,2); y-=38
    for label, keys in [("Efetivo envolvido:",("efetivo","equipe","agente","membro")),("Recursos utilizados:",("recurso","viatura","drone","helicoptero","helicóptero")),("Estratégia de abordagem:",("estrategia","estratégia","abordagem","setor","acesso")),("Medidas serão tomadas pra proteger a população local, incluindo:",("proteção","protecao","morador","direitos humanos"))]:
        write_label(c,label,40,y); y-=24
        vals=[r["content"] for r in rows if r["content"] and any(norm(k) in norm(r["content"]) for k in keys)]
        y=write_block(c,"• "+("; ".join(dict.fromkeys(vals)) if vals else "Informação conforme registros da mesa."),58,y,10.8,False,640,16,4)-16
    c.showPage()

    evidence_page(c,1,SECTION_RULES[1][0],sections[1],cache)

    draw_background(c); write_label(c,"Mídia de Apoio:",40,830); write_label(c,"Líder:",40,775)
    entries=[]
    for r in sections[1]:
        for line in r["content"].splitlines():
            mrg=re.search(r"(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)",line,re.I)
            if mrg: entries.append((mrg.group(1).strip(" *:-"),mrg.group(2)))
    y=735; write_block(c,f"• {entries[0][0]}        RG: {entries[0][1]}" if entries else "• Não identificado",58,y,11.3,False,640,17,2); write_label(c,"Gerentes:",40,680); y=640
    for name,rg in entries[1:9]: y=write_block(c,f"• {name}        RG: {rg}",58,y,11.1,False,640,16.5,2)-4
    c.showPage()

    draw_background(c); write_label(c,"Painel:",40,830)
    imgs=download_images([u for r in sections[1] for u in r["image_urls"]],cache)
    if imgs: place_image(c,imgs[0],205,150,360,650)
    c.showPage()
    draw_background(c); write_block(c,"2. Foto dos principais membros da organização.",40,830,12,True,680,17,2); write_label(c,"Data e Local:",40,780); write_block(c,"• Conforme registros e mensagens vinculadas à etapa.",58,756,10.9,False,640,16,2); write_label(c,"Descrição:",40,715); write_block(c,"• Imagens identificando os principais membros envolvidos nos registros da mesa.",58,691,10.7,False,640,16,4); write_label(c,"Relação com o Processo:",40,620); write_block(c,"• Contribui para a identificação dos envolvidos.",58,596,10.7,False,640,16,3); write_label(c,"Mídia de Apoio:",40,540); write_block(c,"• Fotos anexadas.",58,516,10.7,False,640,16,2); imgs=download_images([u for r in sections[2] for u in r["image_urls"]],cache); grid(c,imgs[:4],70,80,640,350,4); c.showPage()

    for n in range(3,12):
        evidence_page(c,n,SECTION_RULES[n][0],sections[n],cache)

    # Motivação
    draw_background(c); write_block(c,"MOTIVAÇÃO",270,830,14,True,260,18,1); relevant=[r["content"] for r in rows if r["content"] and any(k in norm(r["content"]) for k in ("art.","ameaça","ameaca","violencia","violência","prisao","prisão","controle territorial"))]; write_block(c,"\n".join("• "+x for x in dict.fromkeys(relevant)) or "• Fundamentação conforme os registros da mesa operacional.",40,780,11.1,False,680,16.5,30); c.showPage()

    # Encerramento
    draw_background(c); write_block(c,"PROVAS E DOCUMENTAÇÕES",40,830,14,True,680,18,1); write_block(c,f"Com base nas informações apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada de {m['organizacao']}.",40,780,11.2,False,680,16.5,7); write_label(c,"RESPONSÁVEL PELA CONSOLIDAÇÃO:",40,650); write_block(c,"Polícia Federal - DICOR",58,623,11.2,False,640,17,2); write_label(c,"AUTORIDADE RESPONSÁVEL:",40,535); write_block(c,m["requerente"],58,508,11.2,False,640,17,2); write_block(c,"______________________________",90,390,11,False,270,17,1); write_block(c,"______________________________",440,390,11,False,270,17,1); write_block(c,"Responsável pela consolidação",88,365,9.4,False,270,14,1); write_block(c,"Autoridade DICOR",454,365,9.4,False,220,14,1); c.showPage()

    c.save()
    return str(out)

gerar_pdf_dossie = generate
gerar_pdf = generate

def install(bot_module: Any) -> None:
    print("✅ V400 Dossiê instalado: gerador independente PF/DICOR, template visual fixo e coleta de tarefas/tópicos/mensagens.", flush=True)
