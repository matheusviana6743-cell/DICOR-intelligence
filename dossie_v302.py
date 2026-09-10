# -*- coding: utf-8 -*-
"""DICOR V302 — novo gerador de documentos de mesa.

Não reutiliza os geradores anteriores. O motor trabalha diretamente com
canvas, paginação fixa e dados reais de tarefas, tópicos, mensagens e mídia.
A página segue a geometria do modelo aprovado: borda ornamental, cabeçalho
central em três linhas, marca d'água, blocos textuais e páginas de evidência.
"""
from __future__ import annotations

import hashlib, io, json, re
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
BLACK = colors.HexColor("#151515")
BORDER = colors.HexColor("#6E909B")
BORDER_LIGHT = colors.HexColor("#A9BDC3")
GOLD = colors.HexColor("#AF8739")
WATERMARK = colors.Color(0.90, 0.90, 0.90, alpha=0.55)
FONT = "Courier"
FONT_BOLD = "Courier-Bold"
FONT_ITALIC = "Courier-Oblique"
FONT_BI = "Courier-BoldOblique"

RULES: Dict[int, Tuple[str, Tuple[str, ...]]] = {
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


def _norm(v:Any)->str:
 s=str(v or "").casefold(); return " ".join(re.sub(r"[^0-9a-záàâãéèêíìîóòôõúùûç]+"," ",s).split())


def _clean(v:Any)->str:
 if v is None:return ""
 if isinstance(v,str):return v.strip()
 if isinstance(v,(int,float,bool)):return str(v)
 try:return json.dumps(v,ensure_ascii=False,default=str)
 except Exception:return str(v)


def _walk(v:Any,p:str="")->Iterable[Tuple[str,Any]]:
 yield p,v
 if isinstance(v,dict):
  for k,c in v.items(): yield from _walk(c,f"{p}.{k}" if p else str(k))
 elif isinstance(v,(list,tuple,set)):
  for i,c in enumerate(v): yield from _walk(c,f"{p}[{i}]")


def _get(d:Dict[str,Any], aliases:Sequence[str])->str:
 wanted={_norm(x) for x in aliases}
 for k,v in d.items():
  if _norm(k) in wanted and _clean(v): return _clean(v)
 return ""


def _urls(v:Any)->List[str]:
 out=[]
 for _,x in _walk(v):
  if isinstance(x,str):
   vals=re.findall(r"https?://[^\s<>\]\)]+",x)
   for u in vals:
    u=u.rstrip(".,);]")
    if u not in out:out.append(u)
  elif isinstance(x,dict):
   for k in ("url","proxy_url","attachment_url","image_url","thumbnail_url","media_url","video_url"):
    u=x.get(k)
    if isinstance(u,str) and u.startswith("http") and u not in out:out.append(u)
 return out


def _image_urls(v:Any)->List[str]:
 out=[]; hints=("foto","imagem","image","anexo","attachment","media","midia","thumbnail","embed")
 for p,x in _walk(v):
  hint=_norm(p)
  if isinstance(x,str):
   for u in re.findall(r"https?://[^\s<>\]\)]+",x):
    u=u.rstrip(".,);]"); ext=Path(u.split("?",1)[0]).suffix.lower()
    if ext in (".png",".jpg",".jpeg",".webp",".gif",".bmp") or any(h in hint for h in hints):
     if u not in out:out.append(u)
  elif isinstance(x,dict):
   for k in ("url","proxy_url","attachment_url","image_url","thumbnail_url","media_url"):
    u=x.get(k)
    if isinstance(u,str) and u.startswith("http") and u not in out:out.append(u)
 return out


def _records(dados:Any)->List[Dict[str,Any]]:
 out=[];seen=set()
 for p,d in _walk(dados):
  if not isinstance(d,dict):continue
  r={
   "id":_get(d,("id","message_id","thread_id","task_id","record_id")),
   "title":_get(d,("titulo","título","title","nome","name","assunto","subject")),
   "topic":_get(d,("topico","tópico","topic","thread","thread_name","nome_topico","nome_tópico")),
   "task":_get(d,("tarefa","task","task_name","nome_tarefa")),
   "source":_get(d,("origem","source","canal","channel","channel_name","parent_name")),
   "content":_get(d,("conteudo","conteúdo","content","texto","text","mensagem","message","descricao","descrição","description","observacao","observação","valor","value","resultado","result")),
   "author":_get(d,("autor","author","autor_nome","author_name","usuario","user","membro")),
   "date":_get(d,("data","date","timestamp","created_at","criado_em","created","quando")),
   "raw":d, "urls":_urls(d), "image_urls":_image_urls(d)
  }
  if not any((r["title"],r["topic"],r["task"],r["source"],r["content"],r["author"],r["date"],r["image_urls"])):continue
  sig=r["id"] or p+"|"+r["title"]+"|"+r["topic"]+"|"+r["content"][:400]
  if sig in seen:continue
  seen.add(sig);out.append(r)
 return out


def _classify(r:Dict[str,Any])->Optional[int]:
 topic=_norm(" ".join((r["task"],r["topic"],r["title"],r["source"]))); body=_norm(r["content"]); scores={}
 for n,(_,aliases) in RULES.items():
  score=0
  for a in aliases:
   aa=_norm(a)
   if aa and aa in topic:score+=5
   elif aa and aa in body:score+=1
  if score:scores[n]=score
 return max(scores,key=scores.get) if scores else None


def _meta(records:List[Dict[str,Any]],dados:Any)->Dict[str,str]:
 all_d=[r["raw"] for r in records]+([dados] if isinstance(dados,dict) else [])
 def find(a):
  for d in all_d:
   v=_get(d,a)
   if v:return v
  return ""
 ids=[r["id"] for r in records if r["id"].isdigit()]
 ident=next((x for x in ids if len(x)>=6),"MESA")
 return {
  "pedido":find(("nº do pedido de pacificação","numero do pedido","numero_pedido","pedido","referencia","referência")) or f"INV-{ident[-6:]}",
  "data":find(("data de expedição","data de expedicao","data_expedicao","data")) or datetime.now().strftime("%d/%m/%Y"),
  "processo":find(("nº do processo","numero processo","numero_processo","processo","protocolo")) or f"PF-DICOR-{ident}",
  "requerente":find(("requerente","solicitante","responsavel","responsável","autoridade")) or "Polícia Federal - DICOR",
  "local":find(("localização","localizacao","endereco","endereço","local","cidade")) or "Não informado",
  "organizacao":find(("organização","organizacao","comunidade","grupo","alvo","investigado")) or "Não identificado"
 }


def _bg(c:canvas.Canvas):
 # Moldura inspirada no modelo aprovado: linhas múltiplas + serrilhado em triângulos.
 c.setFillColor(colors.white);c.rect(0,0,PAGE_W,PAGE_H,fill=1,stroke=0)
 for off,col,w in ((8,BORDER_LIGHT,1),(14,BORDER,1.3),(21,BORDER_LIGHT,1),(28,BORDER,1.2)):
  c.setStrokeColor(col);c.setLineWidth(w);c.rect(off,off,PAGE_W-2*off,PAGE_H-2*off,fill=0,stroke=1)
 c.setStrokeColor(BORDER);c.setLineWidth(1)
 step=34
 for x in range(30,int(PAGE_W-30),step):
  c.line(x,28,x+step/2,10);c.line(x+step/2,10,x+step,28);c.line(x,1028,x+step/2,1046);c.line(x+step/2,1046,x+step,1028)
 for y in range(40,int(PAGE_H-40),step):
  c.line(28,y,10,y+step/2);c.line(10,y+step/2,28,y+step);c.line(740,y,758,y+step/2);c.line(758,y+step/2,740,y+step)
 # marca d'água: usa a marca DICOR já existente quando disponível; fallback vetorial.
 wm=Path(__file__).with_name("marca_dagua_dicor.png")
 if wm.exists():
  try:
   c.saveState();c.setFillAlpha(0.12);c.drawImage(str(wm),205,205,width=358,height=520,preserveAspectRatio=True,mask="auto");c.restoreState();
  except Exception:pass
 else:
  c.saveState();c.setStrokeColor(colors.Color(.82,.82,.82,alpha=.28));c.setLineWidth(3)
  c.circle(384,510,175,stroke=1,fill=0);c.roundRect(330,335,108,265,16,stroke=1,fill=0);c.line(384,600,384,655);c.line(384,655,430,685);c.restoreState()
 # Cabeçalho visual do modelo.
 c.setFillColor(BLACK);c.setFont(FONT_BI,30);c.drawCentredString(384,972,"POLÍCIA FEDERAL - DICOR")
 c.setFont(FONT_BI,28);c.drawCentredString(384,933,"DO ESTADO DA CAPITAL")
 c.setFont(FONT_BI,27);c.drawCentredString(384,893,"MORADA DO VALLEY")
 # Brasões estilizados para a identidade quando os PNGs exatos não estiverem disponíveis.
 c.saveState();c.setStrokeColor(GOLD);c.setLineWidth(3);c.setFillColor(colors.HexColor("#D2B54B"))
 p=c.beginPath();p.moveTo(70,990);p.lineTo(112,1018);p.lineTo(154,990);p.lineTo(146,900);p.lineTo(78,900);p.close();c.drawPath(p,stroke=1,fill=1)
 c.setFillColor(BLACK);c.setFont(FONT_BOLD,12);c.drawCentredString(112,970,"POLÍCIA");c.drawCentredString(112,948,"CAPITAL");c.setFont(FONT_BOLD,9);c.drawCentredString(112,926,"PF")
 c.setFillColor(colors.HexColor("#D2B54B"));c.setFillColor(colors.HexColor("#24445A"));
 p=c.beginPath();p.moveTo(614,990);p.lineTo(656,1018);p.lineTo(698,990);p.lineTo(690,900);p.lineTo(622,900);p.close();c.drawPath(p,stroke=1,fill=1)
 c.setFillColor(colors.white);c.setFont(FONT_BOLD,13);c.drawCentredString(656,970,"DICOR");c.setFont(FONT_BOLD,9);c.drawCentredString(656,948,"POLÍCIA FEDERAL");c.restoreState()


def _text(c,text,x,y,max_chars=80,size=11.5,leading=17,font=FONT):
 c.setFont(font,size);c.setFillColor(BLACK)
 for raw in str(text or "").splitlines() or [""]:
  words=raw.split();cur=""
  if not words: c.drawString(x,y,"");y-=leading;continue
  for word in words:
   cand=(cur+" "+word).strip()
   if len(cand)<=max_chars:cur=cand
   else:
    c.drawString(x,y,cur);y-=leading;cur=word
  if cur:c.drawString(x,y,cur);y-=leading
 return y


def _field(c,label,value,y):
 c.setFont(FONT_BOLD,12);c.setFillColor(BLACK);c.drawString(39,y,label);return _text(c,value,55,y-20)


def _download(u,cache):
 cache.mkdir(parents=True,exist_ok=True);p=cache/(hashlib.sha1(u.encode()).hexdigest()+".jpg")
 if p.exists() and p.stat().st_size:return p
 try:
  req=Request(u,headers={"User-Agent":"DICOR-Dossie/302"})
  with urlopen(req,timeout=8) as r:data=r.read(12*1024*1024)
  im=PILImage.open(io.BytesIO(data)).convert("RGB")
  if max(im.size)>1600:
   ratio=1600/max(im.size);im=im.resize((max(1,int(im.width*ratio)),max(1,int(im.height*ratio))))
  im.save(p,"JPEG",quality=88,optimize=True);return p
 except Exception:return None


def _images(records,cache):
 urls=[]
 for r in records:
  for u in r["image_urls"]:
   if u not in urls:urls.append(u)
 out=[]
 with ThreadPoolExecutor(max_workers=6) as pool:
  fs=[pool.submit(_download,u,cache) for u in urls]
  for f in as_completed(fs):
   try:
    p=f.result()
    if p:out.append(p)
   except Exception:pass
 return out


def _grid(c,paths,x,y,w,h,cols):
 if not paths:return
 gap=8;rows=(len(paths)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
 for i,p in enumerate(paths):
  r,col=divmod(i,cols);_draw_image(c,p,(x+col*(cw+gap),y+h-(r+1)*ch-r*gap,cw,ch))


def _draw_image(c,p,box):
 try:
  im=PILImage.open(p);iw,ih=im.size;bx,by,bw,bh=box;s=min(bw/iw,bh/ih);dw,dh=iw*s,ih*s
  c.drawImage(str(p),bx+(bw-dw)/2,by+(bh-dh)/2,width=dw,height=dh,preserveAspectRatio=True,mask="auto");return True
 except Exception:return False


def _record_summary(rs):
 texts=[r["content"] for r in rs if r["content"]]; dates=[_date(r["date"]) for r in rs if r["date"]]
 return ("; ".join(dict.fromkeys(dates)) or "Data não localizada nos registros."," ".join(texts)[:2600] or "Nenhum registro textual identificado.",f"Registros textuais: {len(texts)}.")


def _date(v):
 m=re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})",str(v or ""));return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else (str(v).strip() or "Não informado")


def _page_cover(c,m):
 _bg(c);y=790
 c.setFont(FONT_BOLD,12.8);c.drawString(39,y,f"Nº do Pedido de Pacificação:   {m['pedido']}");y-=32
 c.setFont(FONT,12);c.drawString(39,y,f"Data de Expedição:      {_date(m['data'])}");y-=32
 c.setFont(FONT_BOLD,12.8);c.drawString(39,y,f"Nº do Processo:   {m['processo']}");y-=58
 y=_field(c,"Requerente:",m["requerente"],y)-20;y=_field(c,"Localização:",m["local"],y)-10
 c.setFont(FONT,11.5);c.drawString(39,y,"•");_text(c,f"{m['requerente']}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.",55,y,max_chars=80,size=11.5,leading=17);y-=135
 c.drawString(39,y,"•");_text(c,f"Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{m['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional.",55,y,max_chars=80,size=11.5,leading=17);c.showPage()


def _page_dispositions(c):
 _bg(c);y=_text(c,"DISPOSIÇÕES DO MANDADO",384,830,max_chars=60,size=14,font=FONT_BOLD)-18
 items=["Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.","Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.","Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.","Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.","Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.","O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente."]
 for t in items:
  c.setFont(FONT,11.7);c.drawString(39,y,"•");y=_text(c,t,55,y,max_chars=77,size=11.7,leading=17)-4
 c.showPage()


def _page_planning(c,records):
 _bg(c);y=_text(c,"PLANEJAMENTO OPERACIONAL",384,830,max_chars=60,size=14,font=FONT_BOLD)-18
 y=_text(c,"Para garantir o sucesso da pacificação, a operação contará com:",39,y,max_chars=78,size=12,font=FONT_BOLD)-12
 groups=[("Efetivo envolvido:",( "efetivo","equipe","agente","membro")),("Recursos utilizados:",("recurso","viatura","drone","helicoptero","helicóptero")),("Estratégia de abordagem:",("estrategia","estratégia","abordagem","setor","acesso")),("Medidas serão tomadas pra proteger a população local, incluindo:",("proteção","protecao","morador","médica","medica","oab","direitos humanos"))]
 for label,keys in groups:
  c.setFont(FONT_BOLD,12);c.drawString(39,y,label);y-=19
  vals=[r["content"] for r in records if r["content"] and any(_norm(k) in _norm(r["content"]) for k in keys)]
  if vals:y=_bullets(c,list(dict.fromkeys(vals))[:5],y)
  y-=8
 c.showPage()


def _bullets(c,items,y):
 for t in items:
  c.drawString(39,y,"•");y=_text(c,t,55,y,max_chars=78,size=11.4,leading=17)-4
 return y


def _page_evidence(c,n,records,imgs):
 _bg(c);title=RULES[n][0];y=_text(c,f"{n}. {title}",39,815,max_chars=78,size=12.1,leading=17,font=FONT_BOLD)-8
 data,desc,rel=_record_summary(records);y=_field(c,"Data e Local:",data,y)-3;y=_field(c,"Descrição:",desc,y)-3;y=_field(c,"Relação com o Processo:",rel,y)-3
 _field(c,"Mídia de Apoio:",f"{len(imgs)} mídia(s) incorporada(s)." if imgs else "Nenhuma mídia anexada/localizada.",y)
 if imgs:_grid(c,imgs[:4],39,110,691,360,min(4,len(imgs[:4])))
 c.showPage()


def _page_panel(c,records,imgs):
 _bg(c);y=810;c.setFont(FONT_BOLD,12);c.drawString(39,y,"Mídia de Apoio:");y-=42;c.setFont(FONT_BOLD,12);c.drawString(39,y,"Líder:");y-=23
 leader_lines=[]
 managers=[]
 for r in records:
  for line in r["content"].splitlines():
   m=re.search(r"(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)",line,re.I)
   if m:
    item=f"{m.group(1).strip(' *:-')}    RG: {m.group(2)}"; (leader_lines if 'lider' in _norm(line) else managers).append(item)
 y=_bullets(c,leader_lines[:1] or ["Não identificado"],y)-20;c.setFont(FONT_BOLD,12);c.drawString(39,y,"Gerentes:");y-=23;y=_bullets(c,list(dict.fromkeys(managers))[:14],y);c.showPage()
 _bg(c);c.setFont(FONT,12.5);c.drawString(39,820,"Painel:");
 if imgs:_grid(c,imgs[:1],39,110,691,650,1)
 c.showPage()


def _page_members(c,records,imgs):
 _page_evidence(c,2,records,imgs)
 # Replace the generic image area by a member continuation when there are many photos.
 if len(imgs)>4:
  _bg(c);c.setFont(FONT_BOLD,12);c.drawString(39,820,"Continuação — principais membros");_grid(c,imgs[4:12],39,120,691,640,4);c.showPage()


def _page_motivation(c,records):
 _bg(c);y=_text(c,"MOTIVAÇÃO",384,830,max_chars=60,size=14,font=FONT_BOLD)-18
 vals=[r["content"] for r in records if r["content"] and any(k in _norm(r["content"]) for k in ("art.","tráfico","trafico","quadrilha","ameaça","violencia","violência","prisao","prisão","controle territorial"))]
 _bullets(c,list(dict.fromkeys(vals))[:14],y);c.showPage()


def _page_end(c,m):
 _bg(c);y=_text(c,"PROVAS E DOCUMENTAÇÕES",39,830,max_chars=60,size=14,font=FONT_BOLD)-18
 y=_text(c,"Com base nas provas apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada.",39,y,max_chars=79,size=11.5,leading=17)-35
 c.setFont(FONT_BOLD,11.8);c.drawString(39,y,"DELEGADO RESPONSÁVEL:");y-=24;y=_text(c,m["requerente"],39,y,max_chars=79,size=11.4,leading=17)-30
 c.setFont(FONT_BI,11);c.drawString(39,y,"DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR");y-=70;c.setFont(FONT_BOLD,11.4);c.drawCentredString(215,y,"RESPONSÁVEL PELA CONSOLIDAÇÃO");c.drawCentredString(560,y,"AUTORIDADE DICOR");y-=35;c.setFont(FONT,11);c.drawCentredString(215,y,"____________________________");c.drawCentredString(560,y,"____________________________");c.showPage()


def gerar_pdf_dossie(bot_module:Any,dados:Any,caminho:Any)->str:
 target=Path(caminho);target.parent.mkdir(parents=True,exist_ok=True);cache=target.parent/".dossie_media_v302"
 records=_records(dados); sections={n:[] for n in RULES}
 for r in records: sections[_classify(r) or 12].append(r)
 m=_meta(records,dados); c=canvas.Canvas(str(target),pagesize=(PAGE_W,PAGE_H),pageCompression=1,title=f"Dossiê Operacional — {m['organizacao']}",author="POLÍCIA FEDERAL - DICOR")
 _page_cover(c,m);_page_dispositions(c);_page_planning(c,records)
 _bg(c);y=_text(c,"PROVAS E DOCUMENTAÇÕES",384,830,max_chars=60,size=14,font=FONT_BOLD)-18;_text(c,"As provas e documentações gerais relativas ao processo serão anexadas ao mandado e permanecerão de uso restrito das autoridades competentes. Todas as evidências foram obtidas por meio dos registros da mesa operacional e documentadas para comprovar a necessidade da incursão.",39,y,max_chars=78,size=11.5,leading=17);c.showPage()
 imgs={n:_images(sections[n],cache) for n in sections}
 _page_panel(c,sections[1],imgs[1]);_page_members(c,sections[2],imgs[2])
 for n in (3,4,5,6,7,8,9,10,11): _page_evidence(c,n,sections[n],imgs[n])
 _page_motivation(c,sections[12]);_page_end(c,m);c.save();return str(target)


def gerar_pdf(bot_module:Any,dados:Any,caminho:Any)->str:return gerar_pdf_dossie(bot_module,dados,caminho)

def install(bot_module:Any)->None:print("✅ V302 Dossiê novo carregado — layout fixo PF/DICOR; tarefas, tópicos, mensagens e mídias.",flush=True)

__all__=["gerar_pdf_dossie","gerar_pdf","install"]
