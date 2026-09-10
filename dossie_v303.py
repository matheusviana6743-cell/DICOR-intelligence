# -*- coding: utf-8 -*-
"""DICOR V303 — gerador de dossiê de mesa, refeito do zero.

O layout é desenhado diretamente no canvas para reproduzir o modelo aprovado:
moldura ornamental, marca d'água discreta, cabeçalho PF/DICOR e blocos de
conteúdo nas posições do modelo. O preenchimento usa somente dados úteis das
tarefas, tópicos, mensagens, anexos e registros da mesa.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.request import Request, urlopen

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = 768.0, 1056.0
FONT = "Courier"
FONT_B = "Courier-Bold"
FONT_I = "Courier-Oblique"
FONT_BI = "Courier-BoldOblique"
BLACK = colors.HexColor("#171717")
BORDER = colors.HexColor("#6E909B")
BORDER_2 = colors.HexColor("#A8BCC2")
GOLD = colors.HexColor("#B48A36")

# Brasões fornecidos pelo responsável; dois emblemas empilhados na imagem original.
LOGOS_B64 = "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"

RULES = {
    1:("Foto do painel da organização.",("painel","fotos lideres","fotos líderes","lideranca","liderança")),
    2:("Foto dos principais membros da organização.",("fotos dos membros","fotos membros","principais membros","membros","integrantes","gerentes")),
    3:("Localização da organização.",("localizacao","localização","coordenadas","endereco","endereço")),
    4:("Foto de cima da organização para realizar estratégia de pacificação:",("foto de cima","visao aerea","visão aérea","aerea","aérea","vista superior")),
    5:("Material que vendem.",("material que vendem","materiais","ingredientes base","produtos","mercadorias","vendas")),
    6:("Registrar compra do ilícito em frente ou dentro da comunidade/organização.",("registrar compra","compra do ilícito","compra do ilicito","compra","negociacao","negociação")),
    7:("Foto do informante da organização.",("informante","foto do informante","informacoes do informante","informações do informante")),
    8:("Foto do baú de membros.",("bau de membros","baú de membros","bau membros","baú membros")),
    9:("Foto do baú de líder.",("bau de lider","baú de líder","bau líder","baú líder")),
    10:("Foto e localização do local de fabricação.",("local de fabricacao","local de fabricação","fabricacao","fabricação","rota de farm","farm")),
    11:("Foto e localização do local de produção.",("local de producao","local de produção","producao","produção","rota de producao","rota de produção","escoamento")),
    12:("Informações gerais.",("informacoes gerais","informações gerais","informacao geral","informação geral","geral","radio","rádio","crimes da comunidade")),
}


def _norm(v:Any)->str:
    s=str(v or "").casefold()
    for a,b in (("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")):
        s=s.replace(a,b)
    return " ".join(re.sub(r"[^0-9a-z]+"," ",s).split())


def _clean_text(v:Any)->str:
    if v is None:return ""
    if isinstance(v,str): return v.strip()
    if isinstance(v,(int,float,bool)): return str(v)
    return ""


def _walk(v:Any,p:str=""):
    if isinstance(v,dict):
        yield p,v
        for k,c in v.items():
            q=f"{p}.{k}" if p else str(k)
            yield from _walk(c,q)
    elif isinstance(v,(list,tuple,set)):
        for i,c in enumerate(v): yield from _walk(c,f"{p}[{i}]")
    else: yield p,v


def _field(d:Dict[str,Any],aliases:Sequence[str])->str:
    wanted={_norm(x) for x in aliases}
    for k,v in d.items():
        if _norm(k) in wanted:
            s=_clean_text(v)
            if s and not _looks_internal(s): return s
    return ""


def _looks_internal(s:str)->bool:
    t=s.lower()
    return t.startswith("/tmp/") or t.startswith("/mnt/") or t.startswith("c:\\") or t.startswith("d:\\")


def _records(dados:Any)->List[Dict[str,Any]]:
    out=[];seen=set()
    for path,obj in _walk(dados):
        if not isinstance(obj,dict): continue
        r={
            "id":_field(obj,("message_id","mensagem_original_id","id","thread_id","task_id")),
            "title":_field(obj,("titulo","título","title","nome","name","assunto","subject")),
            "topic":_field(obj,("topico","tópico","topic","thread_name","nome_topico","nome_tópico")),
            "task":_field(obj,("tarefa","task","task_name","nome_tarefa")),
            "source":_field(obj,("origem","source","canal","channel_name","parent_name")),
            "content":_field(obj,("conteudo","conteúdo","content","texto","text","mensagem","message","descricao","descrição","description","observacao","observação","resultado","result")),
            "author":_field(obj,("autor","author","autor_nome","author_name","usuario","user","membro")),
            "date":_field(obj,("data","date","timestamp","created_at","criado_em","created","quando")),
            "raw":obj,
        }
        # Mídias: considera explicitamente URLs e objetos de anexos/embeds.
        urls=[]
        for _,x in _walk(obj):
            if isinstance(x,str):
                urls += re.findall(r"https?://[^\s<>\]\)]+",x)
            elif isinstance(x,dict):
                for k in ("url","proxy_url","attachment_url","image_url","thumbnail_url","media_url","video_url"):
                    u=_clean_text(x.get(k))
                    if u.startswith("http"): urls.append(u)
        r["urls"]=list(dict.fromkeys(u.rstrip(".,);]") for u in urls))
        sig=(r["id"] or path)+"|"+_norm(r["content"])[:500]+"|"+"|".join(r["urls"][:4])
        if not any((r["title"],r["topic"],r["task"],r["source"],r["content"],r["urls"])) or sig in seen: continue
        seen.add(sig); out.append(r)
    return out


def _classify(r:Dict[str,Any])->Optional[int]:
    head=_norm(" ".join((r["task"],r["topic"],r["title"],r["source"])))
    body=_norm(r["content"])
    scores={}
    for n,(_,aliases) in RULES.items():
        score=sum(5 if _norm(a) in head else (1 if _norm(a) in body else 0) for a in aliases if _norm(a))
        if score:scores[n]=score
    return max(scores,key=scores.get) if scores else None


def _meta(rs:List[Dict[str,Any]],dados:Any)->Dict[str,str]:
    dicts=[r["raw"] for r in rs if isinstance(r.get("raw"),dict)]
    if isinstance(dados,dict): dicts.append(dados)
    def find(aliases):
        for d in dicts:
            v=_field(d,aliases)
            if v:return v
        return ""
    ident=next((r["id"] for r in rs if str(r["id"]).isdigit() and len(str(r["id"]))>5),"MESA")
    return {
        "pedido":find(("nº do pedido de pacificação","numero do pedido","numero_pedido","pedido","referencia","referência")) or f"INV-{str(ident)[-6:]}",
        "data":find(("data de expedição","data de expedicao","data_expedicao","data")) or datetime.now().strftime("%d/%m/%Y"),
        "processo":find(("nº do processo","numero_processo","numero processo","processo","protocolo")) or f"PF-DICOR-{ident}",
        "requerente":find(("requerente","solicitante","responsavel","responsável","autoridade")) or "Polícia Federal - DICOR",
        "local":find(("localização","localizacao","endereco","endereço","cidade")) or "Não informado",
        "organizacao":find(("organização","organizacao","comunidade","grupo","alvo","investigado")) or "Não identificada",
    }


def _load_logos():
    im=PILImage.open(io.BytesIO(base64.b64decode(LOGOS_B64))).convert("RGBA")
    w,h=im.size
    top=im.crop((0,0,w,h//2)); bottom=im.crop((0,h//2,w,h))
    return ImageReader(top),ImageReader(bottom)


LOGO_PF, LOGO_DICOR = _load_logos()


def _bg(c:canvas.Canvas):
    c.setFillColor(colors.white);c.rect(0,0,PAGE_W,PAGE_H,fill=1,stroke=0)
    for off,col,lw in ((8,BORDER_2,0.9),(15,BORDER,1.4),(22,BORDER_2,0.9),(29,BORDER,1.2)):
        c.setStrokeColor(col);c.setLineWidth(lw);c.rect(off,off,PAGE_W-off*2,PAGE_H-off*2,fill=0,stroke=1)
    c.setStrokeColor(BORDER);c.setLineWidth(1)
    step=34
    for x in range(31,736,step):
        c.line(x,29,x+17,11);c.line(x+17,11,x+34,29);c.line(x,1027,x+17,1045);c.line(x+17,1045,x+34,1027)
    for y in range(42,1014,step):
        c.line(29,y,11,y+17);c.line(11,y+17,29,y+34);c.line(739,y,757,y+17);c.line(757,y+17,739,y+34)
    # marca d'água vetorial muito suave, sem caixa cinza.
    c.saveState();c.setStrokeColor(colors.Color(.80,.80,.80,alpha=.18));c.setFillColor(colors.Color(.92,.92,.92,alpha=.10));c.setLineWidth(4)
    c.circle(384,515,180,stroke=1,fill=0);c.roundRect(330,340,108,270,17,stroke=1,fill=1);c.line(384,610,384,658);c.line(384,658,430,688);c.restoreState()
    c.drawImage(LOGO_PF,60,875,width=105,height=130,mask="auto")
    c.drawImage(LOGO_DICOR,605,875,width=105,height=130,mask="auto")
    c.setFillColor(BLACK);c.setFont(FONT_BI,30);c.drawCentredString(384,972,"POLÍCIA FEDERAL - DICOR")
    c.setFont(FONT_BI,28);c.drawCentredString(384,932,"DO ESTADO DA CAPITAL")
    c.setFont(FONT_BI,27);c.drawCentredString(384,892,"MORADA DO VALLEY")


def _wrap(text:str,max_chars:int)->List[str]:
    clean=" ".join(str(text or "").replace("\r","").split())
    if not clean:return []
    lines=[];cur=""
    for word in clean.split():
        candidate=(cur+" "+word).strip()
        if len(candidate)<=max_chars:cur=candidate
        else:
            if cur:lines.append(cur)
            cur=word
    if cur:lines.append(cur)
    return lines


def _write(c,text,x,y,max_chars=78,size=11.5,leading=17,font=FONT):
    c.setFillColor(BLACK);c.setFont(font,size)
    for raw in str(text or "").splitlines():
        for line in _wrap(raw,max_chars):
            c.drawString(x,y,line);y-=leading
    return y


def _label_value(c,label,value,y):
    c.setFillColor(BLACK);c.setFont(FONT_B,12.5);c.drawString(39,y,label)
    return _write(c,value,56,y-20,78,11.5,17,FONT)


def _date(v:str)->str:
    s=str(v or "")
    m=re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})",s)
    if m:return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m=re.search(r"(\d{2})[-/](\d{2})[-/](\d{4})",s)
    if m:return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return s or "Não informado"


def _download(url:str,cache:Path)->Optional[Path]:
    cache.mkdir(parents=True,exist_ok=True)
    ext=Path(url.split("?",1)[0]).suffix.lower()
    if ext not in (".png",".jpg",".jpeg",".webp",".gif",".bmp"):ext=".jpg"
    p=cache/(hashlib.sha1(url.encode()).hexdigest()+ext)
    if p.exists() and p.stat().st_size: return p
    try:
        req=Request(url,headers={"User-Agent":"DICOR-Dossie/303"})
        with urlopen(req,timeout=7) as r:data=r.read(12*1024*1024)
        im=PILImage.open(io.BytesIO(data)).convert("RGB")
        if max(im.size)>1500:
            ratio=1500/max(im.size);im=im.resize((max(1,int(im.width*ratio)),max(1,int(im.height*ratio))))
        im.save(p,"JPEG",quality=88)
        return p
    except Exception:return None


def _images(rs:Sequence[Dict[str,Any]],cache:Path)->List[Path]:
    urls=[]
    for r in rs:
        for u in r.get("urls",[]):
            low=u.lower()
            if any(x in low for x in (".png",".jpg",".jpeg",".webp",".gif","/attachments/","/embed")) and u not in urls:urls.append(u)
    out=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs=[pool.submit(_download,u,cache) for u in urls]
        for f in as_completed(fs):
            try:
                p=f.result()
                if p:out.append(p)
            except Exception:pass
    return out


def _grid(c,paths:Sequence[Path],x,y,w,h,cols=4):
    if not paths:return
    gap=10;cols=max(1,cols);rows=(len(paths)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
    for i,p in enumerate(paths):
        row,col=divmod(i,cols)
        bx=x+col*(cw+gap);by=y+h-(row+1)*ch-row*gap
        try:
            im=PILImage.open(p);iw,ih=im.size;scale=min((cw-4)/iw,(ch-4)/ih);dw,dh=iw*scale,ih*scale
            c.drawImage(str(p),bx+(cw-dw)/2,by+(ch-dh)/2,width=dw,height=dh,preserveAspectRatio=True,mask="auto")
        except Exception:pass


def _summary(rs:Sequence[Dict[str,Any]])->Tuple[str,str,str]:
    dates=[];texts=[]
    for r in rs:
        if r.get("date"):dates.append(_date(r["date"]))
        if r.get("content"):
            t=r["content"]
            if not _looks_internal(t):texts.append(t)
    dates=list(dict.fromkeys(dates))
    texts=list(dict.fromkeys(texts))
    desc=" ".join(texts)
    return ", ".join(dates) or "Data não localizada nos registros.", desc[:1800] or "Nenhuma descrição textual localizada.", f"Registros consolidados: {len(texts)}."


def _cover(c,m):
    _bg(c);y=790
    c.setFont(FONT_B,12.8);c.setFillColor(BLACK);c.drawString(39,y,f"Nº do Pedido de Pacificação:   {m['pedido']}");y-=32
    c.setFont(FONT,12);c.drawString(39,y,f"Data de Expedição:      {_date(m['data'])}");y-=32
    c.setFont(FONT_B,12.8);c.drawString(39,y,f"Nº do Processo:   {m['processo']}");y-=58
    y=_label_value(c,"Requerente:",m["requerente"],y)-22
    c.setFont(FONT_B,12.5);c.drawString(39,y,"Localização:");y-=20
    # Não imprime caminhos internos nem objetos; somente informação humana.
    y=_write(c,m["local"],56,y,78,11.5,17,FONT)-14
    c.drawString(39,y,"•");y=_write(c,f"{m['requerente']}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.",56,y,78,11.5,17,FONT)-15
    c.drawString(39,y,"•");_write(c,f"Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{m['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional.",56,y,78,11.5,17,FONT)
    c.showPage()


def _dispositions(c):
    _bg(c);y=_write(c,"DISPOSIÇÕES DO MANDADO",384,830,60,14,FONT_B,18,FONT_B)-22
    for t in (
        "Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.",
        "Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.",
        "Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.",
        "Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.",
        "Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.",
        "O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente."):
        c.setFont(FONT,11.7);c.drawString(39,y,"•");y=_write(c,t,55,y,77,11.7,17,FONT)-4
    c.showPage()


def _planning(c,rs):
    _bg(c);y=_write(c,"PLANEJAMENTO OPERACIONAL",384,830,60,14,FONT_B,18,FONT_B)-18
    y=_write(c,"Para garantir o sucesso da pacificação, a operação contará com:",39,y,78,12,FONT_B,17,FONT_B)-14
    groups=(("Efetivo envolvido:",("efetivo","equipe","agente","membro")),("Recursos utilizados:",("recurso","viatura","drone","helicoptero","helicóptero")),("Estratégia de abordagem:",("estrategia","estratégia","abordagem","setor","acesso")),("Medidas serão tomadas pra proteger a população local, incluindo:",("protecao","proteção","morador","medica","médica","oab","direitos humanos")))
    for label,keys in groups:
        c.setFont(FONT_B,12);c.drawString(39,y,label);y-=19
        vals=[]
        for r in rs:
            s=r.get("content","")
            if s and any(_norm(k) in _norm(s) for k in keys) and not _looks_internal(s):vals.append(s)
        vals=list(dict.fromkeys(vals))[:5]
        for v in vals:
            c.setFont(FONT,11.3);c.drawString(39,y,"•");y=_write(c,v,55,y,77,11.3,16,FONT)-3
        y-=9
    c.showPage()


def _evidence(c,n,rs,imgs):
    _bg(c);y=_write(c,f"{n}. {RULES[n][0]}",39,815,78,12.1,17,FONT_B)-9
    data,desc,rel=_summary(rs)
    y=_label_value(c,"Data e Local:",data,y)-4
    y=_label_value(c,"Descrição:",desc,y)-4
    y=_label_value(c,"Relação com o Processo:",rel,y)-4
    c.setFont(FONT_B,12);c.drawString(39,y,"Mídia de Apoio:");y-=22
    if imgs:
        c.setFont(FONT,11.3);c.drawString(55,y,f"{len(imgs)} mídia(s) incorporada(s) a partir dos registros da mesa.")
        _grid(c,imgs[:4],39,100,691,355,4)
    else:
        c.setFont(FONT,11.3);c.drawString(55,y,"Nenhuma mídia anexada/localizada para esta etapa.")
    c.showPage()


def _panel(c,rs,imgs):
    _bg(c);y=815
    c.setFont(FONT_B,12);c.drawString(39,y,"Mídia de Apoio:");y-=38;c.drawString(39,y,"Líder:");y-=22
    lines=[]
    for r in rs:
        for ln in str(r.get("content","")).splitlines():
            m=re.search(r"(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)",ln,re.I)
            if m:lines.append(f"{m.group(1).strip(' *:-')}    RG: {m.group(2)}")
    lines=list(dict.fromkeys(lines))
    y=_write(c,"\n".join("• "+x for x in (lines[:1] or ["Não identificado"])),55,y,74,11.4,17,FONT)-22
    c.setFont(FONT_B,12);c.drawString(39,y,"Gerentes:");y-=22
    managers=lines[1:15]
    y=_write(c,"\n".join("• "+x for x in managers),55,y,74,11.4,17,FONT)
    c.showPage();_bg(c);c.setFont(FONT,12.5);c.drawString(39,815,"Painel:")
    if imgs:_grid(c,imgs[:1],110,115,548,650,1)
    c.showPage()


def _motivation(c,rs):
    _bg(c);y=_write(c,"MOTIVAÇÃO",384,830,60,14,FONT_B,18,FONT_B)-22
    vals=[]
    for r in rs:
        s=r.get("content","")
        if s and any(k in _norm(s) for k in ("art ","tráfico","trafico","quadrilha","ameaça","violencia","violência","prisao","prisão","controle territorial")) and not _looks_internal(s):vals.append(s)
    y=_write(c,"\n".join("• "+x for x in list(dict.fromkeys(vals))[:12]),39,y,78,11.5,17,FONT);c.showPage()


def _end(c,m):
    _bg(c);y=_write(c,"PROVAS E DOCUMENTAÇÕES",39,830,60,14,FONT_B,18,FONT_B)-22
    y=_write(c,"Com base nas provas apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada.",39,y,78,11.5,17,FONT)-40
    c.setFont(FONT_B,11.8);c.drawString(39,y,"DELEGADO RESPONSÁVEL:");y-=24;y=_write(c,m["requerente"],39,y,78,11.3,17,FONT)-34
    c.setFont(FONT_BI,10.5);c.drawString(39,y,"DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR");y-=70
    c.setFont(FONT_B,11.2);c.drawCentredString(220,y,"RESPONSÁVEL PELA CONSOLIDAÇÃO");c.drawCentredString(550,y,"AUTORIDADE DICOR");y-=32
    c.setFont(FONT,11);c.drawCentredString(220,y,"____________________________");c.drawCentredString(550,y,"____________________________");c.showPage()


def gerar_pdf_dossie(bot_module:Any,dados:Any,caminho:Any)->str:
    target=Path(caminho);target.parent.mkdir(parents=True,exist_ok=True)
    rs=_records(dados);sections={n:[] for n in RULES}
    for r in rs: sections[_classify(r) or 12].append(r)
    m=_meta(rs,dados)
    c=canvas.Canvas(str(target),pagesize=(PAGE_W,PAGE_H),pageCompression=1,title=f"Dossiê Operacional — {m['organizacao']}",author="POLÍCIA FEDERAL - DICOR")
    _cover(c,m);_dispositions(c);_planning(c,rs)
    _bg(c);y=_write(c,"PROVAS E DOCUMENTAÇÕES",384,830,60,14,FONT_B,18,FONT_B)-22
    y=_write(c,"As provas e documentações gerais relativas ao processo serão anexadas ao mandado e permanecerão de uso restrito das autoridades competentes. Todas as evidências foram obtidas por meio dos registros da mesa operacional e documentadas para comprovar a necessidade da incursão.",39,y,78,11.5,17,FONT);c.showPage()
    cache=target.parent/".dossie_media_v303";cache.mkdir(exist_ok=True)
    images={n:_images(sections[n],cache) for n in sections}
    _panel(c,sections[1],images[1]);_evidence(c,2,sections[2],images[2])
    for n in (3,4,5,6,7,8,9,10,11):_evidence(c,n,sections[n],images[n])
    _motivation(c,sections[12]);_end(c,m);c.save();return str(target)


def gerar_pdf(bot_module:Any,dados:Any,caminho:Any)->str:return gerar_pdf_dossie(bot_module,dados,caminho)

def install(bot_module:Any)->None:print("✅ V303 Dossiê instalado — layout PF/DICOR fixo; preenchimento por tarefas, tópicos, mensagens e mídias.",flush=True)

__all__=["gerar_pdf_dossie","gerar_pdf","install"]
