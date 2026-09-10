# -*- coding: utf-8 -*-
"""DICOR V401 - gerador independente de documentos das mesas.

Usa a arte-base PF/DICOR já versionada como fundo visual. Não chama nenhum dos
renderizadores antigos. A coleta é feita sobre tarefas, tópicos, mensagens,
autores, datas e anexos; o documento mantém 18 páginas na mesma ordem do modelo.
"""
from __future__ import annotations
import base64, io, json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

PW, PH = 768, 1056
FONT, FB = "Courier", "Courier-Bold"
BLACK = (0.08, 0.08, 0.08)
TEMPLATE_B64_FILE = "dicor_template_v301.b64"

RULES = {
1:("Foto do painel da organização.",("painel","fotos líderes","fotos lideres","liderança","lideranca")),
2:("Foto dos principais membros da organização.",("fotos dos membros","fotos membros","principais membros","membros","integrantes","gerentes")),
3:("Localização da organização.",("localização","localizacao","coordenadas","endereço","endereco")),
4:("Foto de cima da organização para realizar estratégia de pacificação:",("foto de cima","visão aérea","visao aerea","aérea","aerea","vista aérea","vista aerea")),
5:("Material que vendem.",("material que vendem","materiais","ingredientes base","produtos","mercadorias","vendas")),
6:("Registrar compra do ilícito em frente ou dentro da comunidade/organização.",("registrar compra","compra do ilícito","compra do ilicito","compra","negociação","negociacao")),
7:("Foto do informante da organização.",("informante","foto do informante","informações do informante","informacoes do informante")),
8:("Foto do baú de membros.",("baú de membros","bau de membros","baú membros","bau membros")),
9:("Foto do baú de líder.",("baú de líder","bau de lider","baú líder","bau lider")),
10:("Foto e localização do local de fabricação.",("local de fabricação","local de fabricacao","fabricação","fabricacao","rota de farm","farm")),
11:("Foto e localização do local de produção.",("local de produção","local de producao","produção","producao","rota de produção","rota de producao","escoamento")),
12:("Informações gerais.",("informações gerais","informacoes gerais","informação geral","informacao geral","geral","rádio","radio","crimes da comunidade")),
}

def norm(v: Any) -> str:
    s = str(v or "").casefold().translate(str.maketrans("áàâãéêíóôõúç","aaaaeeiooouc"))
    return " ".join(re.sub(r"[^0-9a-z]+"," ",s).split())

def clean(v: Any) -> str:
    if v is None:return ""
    if isinstance(v,str):return v.strip()
    if isinstance(v,(int,float,bool)):return str(v)
    try:return json.dumps(v,ensure_ascii=False,default=str)
    except Exception:return str(v)

def walk(v: Any, path: str = "") -> Iterable[Tuple[str,Any]]:
    if isinstance(v,dict):
        yield path,v
        for k,c in v.items():yield from walk(c,f"{path}.{k}" if path else str(k))
    elif isinstance(v,(list,tuple,set)):
        for i,c in enumerate(v):yield from walk(c,f"{path}[{i}]")
    else:yield path,v

def pick(d: Dict[str,Any], keys: Sequence[str]) -> str:
    wanted={norm(k) for k in keys}
    for k,v in d.items():
        if norm(k) in wanted and clean(v):return clean(v)
    return ""

def urls(v: Any) -> List[str]:
    out=[]
    for _,x in walk(v):
        vals=re.findall(r"https?://[^\s<>\]\)]+",x) if isinstance(x,str) else []
        if isinstance(x,dict):vals += [x.get(k,"") for k in ("url","proxy_url","attachment_url","image_url","thumbnail_url","media_url","video_url")]
        for u in vals:
            if isinstance(u,str) and u.startswith("http"):
                u=u.rstrip(".,);]")
                if u not in out:out.append(u)
    return out

def records(data: Any) -> List[Dict[str,Any]]:
    out=[];seen=set()
    for path,obj in walk(data):
        if not isinstance(obj,dict):continue
        r={
            "id":pick(obj,("id","message_id","thread_id","task_id","record_id")),
            "title":pick(obj,("titulo","título","title","nome","name","assunto","subject")),
            "topic":pick(obj,("topico","tópico","topic","thread","thread_name","nome_topico","nome_tópico")),
            "task":pick(obj,("tarefa","task","task_name","nome_tarefa")),
            "source":pick(obj,("origem","source","canal","channel","channel_name","parent_name")),
            "content":pick(obj,("conteudo","conteúdo","content","texto","text","mensagem","message","descricao","descrição","description","observacao","observação","valor","value","resultado","result")),
            "author":pick(obj,("autor","author","autor_nome","author_name","usuario","user","membro")),
            "date":pick(obj,("data","date","timestamp","created_at","criado_em","created","quando")),
            "raw":obj,"urls":urls(obj)
        }
        r["image_urls"]=[u for u in r["urls"] if Path(u.split("?",1)[0]).suffix.casefold() in (".png",".jpg",".jpeg",".webp",".gif",".bmp")]
        if not any(r[k] for k in ("title","topic","task","source","content","author","date","image_urls")):continue
        sig=r["id"] or f"{path}|{r['title']}|{r['topic']}|{r['content'][:400]}"
        if sig in seen:continue
        seen.add(sig);out.append(r)
    return out

def classify(r: Dict[str,Any]) -> int:
    head=norm(" ".join((r["task"],r["topic"],r["title"],r["source"])));body=norm(r["content"]);best,bscore=12,0
    for n,(_,aliases) in RULES.items():
        score=sum(8 if norm(a) in head else 1 if norm(a) in body else 0 for a in aliases)
        if score>bscore:bscore,best=score,n
    return best

def first(rows,keys,default):
    for r in rows:
        if isinstance(r.get("raw"),dict):
            v=pick(r["raw"],keys)
            if v:return v
    return default

def meta(rows):
    ident=next((r["id"] for r in rows if str(r.get("id","")).isdigit()),"MESA")
    return {
        "pedido":first(rows,("nº do pedido de pacificação","numero do pedido","numero_pedido","pedido"),f"INV-{str(ident)[-6:]}"),
        "data":first(rows,("data de expedição","data de expedicao","data_expedicao"),datetime.now().strftime("%d/%m/%Y")),
        "processo":first(rows,("nº do processo","numero processo","numero_processo","processo","protocolo"),f"PF-DICOR-{ident}"),
        "requerente":first(rows,("requerente","solicitante","responsavel","responsável","autoridade"),"Polícia Federal - DICOR"),
        "organizacao":first(rows,("organização","organizacao","comunidade","grupo","alvo","investigado"),"Não identificado")
    }

def template_path() -> Path:
    return Path(__file__).with_name(TEMPLATE_B64_FILE)

def template_image() -> Image.Image:
    p=template_path()
    raw=base64.b64decode(p.read_text(encoding="utf-8").strip(),validate=True)
    return Image.open(io.BytesIO(raw)).convert("RGB")

def bg(c):
    c.drawImage(ImageReader(template_image()),0,0,width=PW,height=PH)

def wrap(text,size,maxw):
    s=re.sub(r"/tmp/[^\s]+","",str(text or ""));out=[]
    for para in s.splitlines() or [""]:
        cur=""
        for w in para.split():
            cand=w if not cur else f"{cur} {w}"
            if stringWidth(cand,FONT,size)<=maxw:cur=cand
            else:
                if cur:out.append(cur)
                cur=w
        if cur:out.append(cur)
    return out

def put(c,text,x,y,size=11.2,bold=False,maxw=680,leading=16.5,limit=30):
    c.setFillColorRGB(*BLACK);c.setFont(FB if bold else FONT,size)
    for line in wrap(text,size,maxw)[:limit]:c.drawString(x,y,line);y-=leading
    return y

def label(c,text,x,y,size=12):c.setFillColorRGB(*BLACK);c.setFont(FB,size);c.drawString(x,y,text)

def fetch_image(url,cache):
    cache.mkdir(parents=True,exist_ok=True);p=cache/(str(abs(hash(url)))+".jpg")
    if p.exists() and p.stat().st_size:return p
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"DICOR-V401"})
        with urllib.request.urlopen(req,timeout=8) as r:data=r.read(10*1024*1024)
        im=Image.open(io.BytesIO(data)).convert("RGB");im.thumbnail((1600,1600));im.save(p,"JPEG",quality=90);return p
    except Exception:return None

def get_images(rows,cache):
    urls_all=[]
    for r in rows:
        for u in r["image_urls"]:
            if u not in urls_all:urls_all.append(u)
    out=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs=[pool.submit(fetch_image,u,cache) for u in urls_all]
        for f in as_completed(fs):
            try:
                p=f.result()
                if p:out.append(p)
            except Exception:pass
    return out

def place(c,p,x,y,w,h):
    if not p:return
    try:
        im=Image.open(p);iw,ih=im.size;s=min(w/iw,h/ih);dw,dh=iw*s,ih*s;c.drawImage(str(p),x+(w-dw)/2,y+(h-dh)/2,dw,dh,preserveAspectRatio=True,mask="auto")
    except Exception:pass

def grid(c,ims,x,y,w,h,cols):
    if not ims:return
    gap=10;rows=(len(ims)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
    for i,p in enumerate(ims):
        rr,cc=divmod(i,cols);place(c,p,x+cc*(cw+gap),y+h-(rr+1)*ch-rr*gap,cw,ch)

def evidence(c,n,title,rows,cache):
    bg(c);put(c,f"{n}. {title}",40,830,11.7,True,680,17,2)
    dates="; ".join(dict.fromkeys(r["date"] for r in rows if r["date"])) or "Data e local conforme registros."
    desc=" ".join(r["content"] for r in rows if r["content"]) or "Nenhuma informação textual localizada."
    label(c,"Data e Local:",40,780);put(c,"• "+dates,58,756,10.8,False,640,16,4)
    label(c,"Descrição:",40,705);put(c,"• "+desc,58,681,10.4,False,640,15.5,6)
    label(c,"Relação com o Processo:",40,575);put(c,"• Informação consolidada a partir das tarefas, tópicos e mensagens vinculadas à etapa.",58,551,10.4,False,640,15.5,4)
    label(c,"Mídia de Apoio:",40,470);put(c,f"• {sum(len(r['image_urls']) for r in rows)} mídia(s) encontrada(s).",58,446,10.5,False,640,16,2)
    ims=get_images(rows,cache)
    if ims:
        if n==4:grid(c,ims[:6],195,90,430,300,3)
        else:place(c,ims[0],150,80,470,330)
    c.showPage()

def generate(bot_module:Any,dados:Any,caminho:Any)->str:
    rows=records(dados);sec={n:[] for n in RULES}
    for r in rows:sec[classify(r)].append(r)
    m=meta(rows);cache=Path(getattr(bot_module,"DATA_DIR",Path(__file__).parent/"data"))/"dossie_media_cache_v401";out=Path(caminho);out.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(out),pagesize=(PW,PH))
    # 1
    bg(c);y=800;put(c,f"N° do Pedido de Pacificação:   {m['pedido']}",40,y,12.3,True,690,18,1);y-=33;put(c,f"Data de Expedição:      {m['data']}",40,y,12,False,690,18,1);y-=33;put(c,f"N° do Processo:   {m['processo']}",40,y,12.3,True,690,18,1);y-=58;label(c,"Requerente:",40,y);y-=28;y=put(c,"• "+m["requerente"],58,y,11.3,False,650,17,2)-25;label(c,"Localização:",40,y);y-=28;y=put(c,f"• {m['requerente']}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.",58,y,11.2,False,650,17,7)-8;put(c,f"• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{m['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional.",58,y,11.2,False,650,17,5);c.showPage()
    # 2
    bg(c);put(c,"DISPOSIÇÕES DO MANDADO",205,830,14,True,360,18,1);y=775
    for t in ("Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.","Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.","Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.","Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.","Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.","O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente."):
        c.drawString(40,y,"•");y=put(c,t,56,y,11.4,False,650,17,5)-8
    c.showPage()
    # 3
    bg(c);put(c,"PLANEJAMENTO OPERACIONAL",185,830,14,True,400,18,1);y=780;put(c,"Para garantir o sucesso da pacificação, a operação contará com:",40,y,12,True,680,18,2);y-=38
    for lab,ks in (("Efetivo envolvido:",("efetivo","equipe","agente","membro")),("Recursos utilizados:",("recurso","viatura","drone","helicoptero","helicóptero")),("Estratégia de abordagem:",("estrategia","estratégia","abordagem","setor","acesso")),("Medidas serão tomadas pra proteger a população local, incluindo:",("proteção","protecao","morador","direitos humanos"))):
        label(c,lab,40,y);y-=24;vals=[r["content"] for r in rows if r["content"] and any(norm(k) in norm(r["content"]) for k in ks)];y=put(c,"• "+("; ".join(dict.fromkeys(vals)) if vals else "Informação conforme registros da mesa."),58,y,10.8,False,640,16,4)-16
    c.showPage()
    # 4
    evidence(c,1,RULES[1][0],sec[1],cache)
    # 5
    bg(c);label(c,"Mídia de Apoio:",40,830);label(c,"Líder:",40,775);entries=[]
    for r in sec[1]:
        for line in r["content"].splitlines():
            z=re.search(r"(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)",line,re.I)
            if z:entries.append((z.group(1).strip(" *:-"),z.group(2)))
    put(c,f"• {entries[0][0]}        RG: {entries[0][1]}" if entries else "• Não identificado",58,735,11.3,False,640,17,2);label(c,"Gerentes:",40,680);y=640
    for nrg,rg in entries[1:9]:y=put(c,f"• {nrg}        RG: {rg}",58,y,11.1,False,640,16.5,2)-4
    c.showPage()
    # 6 painel
    bg(c);label(c,"Painel:",40,830);ims=get_images(sec[1],cache)
    if ims:place(c,ims[0],205,150,360,650)
    c.showPage()
    # 7 membros
    bg(c);put(c,"2. Foto dos principais membros da organização.",40,830,12,True,680,17,2);label(c,"Data e Local:",40,780);put(c,"• Conforme registros e mensagens vinculadas à etapa.",58,756,10.9,False,640,16,2);label(c,"Descrição:",40,715);put(c,"• Imagens identificando os principais membros envolvidos nos registros da mesa.",58,691,10.7,False,640,16,4);label(c,"Relação com o Processo:",40,620);put(c,"• Contribui para a identificação dos envolvidos.",58,596,10.7,False,640,16,3);label(c,"Mídia de Apoio:",40,540);put(c,"• Fotos anexadas.",58,516,10.7,False,640,16,2);grid(c,get_images(sec[2],cache)[:4],70,80,640,350,4);c.showPage()
    # 8-16
    for n in range(3,12):evidence(c,n,RULES[n][0],sec[n],cache)
    # 17
    bg(c);put(c,"MOTIVAÇÃO",270,830,14,True,260,18,1);vals=[r["content"] for r in rows if r["content"] and any(k in norm(r["content"]) for k in ("art.","ameaça","ameaca","violencia","violência","prisao","prisão","controle territorial"))];put(c,"\n".join("• "+x for x in dict.fromkeys(vals)) or "• Fundamentação conforme os registros da mesa operacional.",40,780,11.1,False,680,16.5,30);c.showPage()
    # 18
    bg(c);put(c,"PROVAS E DOCUMENTAÇÕES",40,830,14,True,680,18,1);put(c,f"Com base nas informações apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada de {m['organizacao']}.",40,780,11.2,False,680,16.5,7);label(c,"RESPONSÁVEL PELA CONSOLIDAÇÃO:",40,650);put(c,"Polícia Federal - DICOR",58,623,11.2,False,640,17,2);label(c,"AUTORIDADE RESPONSÁVEL:",40,535);put(c,m["requerente"],58,508,11.2,False,640,17,2);put(c,"______________________________",90,390,11,False,270,17,1);put(c,"______________________________",440,390,11,False,270,17,1);put(c,"Responsável pela consolidação",88,365,9.4,False,270,14,1);put(c,"Autoridade DICOR",454,365,9.4,False,220,14,1);c.showPage()
    c.save();return str(out)

gerar_pdf_dossie=generate
gerar_pdf=generate

def install(bot_module:Any)->None:
    print("✅ V401 Dossiê instalado: gerador independente PF/DICOR e sem renderizador antigo.",flush=True)
