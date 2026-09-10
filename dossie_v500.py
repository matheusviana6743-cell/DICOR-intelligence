# -*- coding: utf-8 -*-
"""DICOR V500 — gerador novo de documento de mesa.
Sem Platypus e sem os geradores V3xx/V4xx. Usa somente a arte-base versionada
em dicor_template_v301.b64 e escreve os dados coletados por cima dela.
"""
from __future__ import annotations
import base64, io, json, re, urllib.request
from pathlib import Path
from datetime import datetime
from typing import Any
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

W,H=768,1056
FONT='Courier'; BOLD='Courier-Bold'; BLACK=(.08,.08,.08)
BASE=Path(__file__).parent
TEMPLATE_B64=BASE/'dicor_template_v301.b64'
CACHE=BASE/'data'/'dossie_v500_template.png'

def _norm(v):
    s=str(v or '').casefold().translate(str.maketrans('áàâãéêíóôõúç','aaaaeeiooouc'))
    return ' '.join(re.sub(r'[^0-9a-z]+',' ',s).split())

def _clean(v):
    if v is None:return ''
    if isinstance(v,str):return v.strip()
    if isinstance(v,(int,float,bool)):return str(v)
    try:return json.dumps(v,ensure_ascii=False,default=str)
    except Exception:return str(v)

def _walk(v,path=''):
    if isinstance(v,dict):
        yield path,v
        for k,c in v.items(): yield from _walk(c,f'{path}.{k}' if path else str(k))
    elif isinstance(v,(list,tuple,set)):
        for i,c in enumerate(v): yield from _walk(c,f'{path}[{i}]')
    else: yield path,v

def _pick(d,aliases):
    wanted={_norm(x) for x in aliases}
    for k,v in d.items():
        if _norm(k) in wanted and _clean(v):return _clean(v)
    return ''

def _urls(v):
    out=[]
    for path,obj in _walk(v):
        vals=[]
        if isinstance(obj,str):vals=re.findall(r'https?://[^\s<>\]\)]+',obj)
        elif isinstance(obj,dict):vals=[obj.get(k,'') for k in ('url','proxy_url','attachment_url','image_url','thumbnail_url','media_url','video_url','file_url','path','local_path','filepath')]
        for u in vals:
            if isinstance(u,str) and (u.startswith('http') or u.startswith(('/tmp/','/mnt/','file://'))):
                u=u.rstrip('.,);]')
                if u not in out:out.append(u)
    return out

def _records(data):
    out=[];seen=set()
    for path,obj in _walk(data):
        if not isinstance(obj,dict):continue
        r={'id':_pick(obj,('id','message_id','thread_id','task_id','record_id')),
           'title':_pick(obj,('titulo','título','title','nome','name','assunto','subject')),
           'topic':_pick(obj,('topico','tópico','topic','thread','thread_name','nome_topico','nome_tópico')),
           'task':_pick(obj,('tarefa','task','task_name','nome_tarefa')),
           'source':_pick(obj,('origem','source','canal','channel','channel_name','parent_name')),
           'content':_pick(obj,('conteudo','conteúdo','content','texto','text','mensagem','message','descricao','descrição','description','observacao','observação','valor','value','resultado','result')),
           'author':_pick(obj,('autor','author','autor_nome','author_name','usuario','user','membro')),
           'date':_pick(obj,('data','date','timestamp','created_at','criado_em','created','quando')),
           'raw':obj}
        r['urls']=_urls(obj)
        sig=r['id'] or f'{path}|{r["title"]}|{r["topic"]}|{r["content"][:600]}'
        if sig in seen:continue
        if not any(r[k] for k in ('title','topic','task','source','content','author','date','urls')):continue
        seen.add(sig);out.append(r)
    return out

def _section(r):
    h=_norm(' '.join((r['task'],r['topic'],r['title'],r['source'],r['content'])))
    rules={1:('painel','fotos lideres','lideranca'),2:('fotos dos membros','membros','integrantes','gerentes'),3:('localizacao','coordenadas','endereco'),4:('foto de cima','visao aerea','vista aerea'),5:('material que vendem','materiais','ingredientes','produtos'),6:('registrar compra','compra','negociacao'),7:('informante','foto do informante','informacoes do informante'),8:('bau de membros','baú de membros'),9:('bau de lider','bau de lider','baú de líder'),10:('local de fabricacao','fabricacao','rota de farm'),11:('local de producao','producao','rota de producao'),12:('informacoes gerais','informacao geral','radio','crimes da comunidade')}
    best,score=12,0
    for n,als in rules.items():
        s=sum(8 if _norm(a) in _norm(' '.join((r['task'],r['topic'],r['title'],r['source']))) else 1 if _norm(a) in h else 0 for a in als)
        if s>score:best,score=n,s
    return best

def _template():
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    if CACHE.exists() and CACHE.stat().st_size>10000:return CACHE
    raw=''.join(TEMPLATE_B64.read_text(encoding='utf-8').split())
    try:data=base64.b64decode(raw,validate=True)
    except Exception as e:raise RuntimeError(f'template visual inválido: {e}')
    if len(data)<10000:raise RuntimeError('template visual incompleto')
    img=Image.open(io.BytesIO(data)).convert('RGB').resize((W,H));img.save(CACHE,'PNG');return CACHE

def _wrap(text,size,width):
    text=re.sub(r'(?:/tmp|/mnt)/[^\s]+','',str(text or ''))
    out=[]
    for para in text.splitlines() or ['']:
        cur=''
        for word in para.split():
            cand=word if not cur else cur+' '+word
            if stringWidth(cand,FONT,size)<=width:cur=cand
            else:
                if cur:out.append(cur)
                cur=word
        if cur:out.append(cur)
    return out

def _text(c,text,x,y,size=11,bold=False,width=650,leading=16,max_lines=30):
    c.setFillColorRGB(*BLACK);c.setFont(BOLD if bold else FONT,size)
    for line in _wrap(text,size,width)[:max_lines]:c.drawString(x,y,line);y-=leading
    return y

def _label(c,text,x,y,size=12):c.setFillColorRGB(*BLACK);c.setFont(BOLD,size);c.drawString(x,y,text)

def _bg(c):c.drawImage(ImageReader(str(_template())),0,0,width=W,height=H,mask='auto')

def _img_download(u,cache):
    cache.mkdir(parents=True,exist_ok=True);p=cache/(str(abs(hash(u)))+'.jpg')
    if p.exists() and p.stat().st_size:return p
    try:
        if u.startswith('/tmp/') or u.startswith('/mnt/'):
            pth=Path(u)
            if not pth.exists():return None
            im=Image.open(pth).convert('RGB')
        else:
            req=urllib.request.Request(u,headers={'User-Agent':'DICOR-V500'})
            with urllib.request.urlopen(req,timeout=8) as r:data=r.read(12*1024*1024)
            im=Image.open(io.BytesIO(data)).convert('RGB')
        im.thumbnail((1800,1800));im.save(p,'JPEG',quality=88);return p
    except Exception:return None

def _images(rows,bot):
    cache=Path(getattr(bot,'DATA_DIR',BASE/'data'))/'dossie_v500_media';urls=[]
    for r in rows:
        for u in r.get('urls',[]):
            if u not in urls:urls.append(u)
    out=[]
    for u in urls:
        p=_img_download(u,cache)
        if p:out.append(p)
    return out

def _grid(c,imgs,x,y,w,h,cols=4,max_items=8):
    imgs=imgs[:max_items]
    if not imgs:return
    gap=8;rows=(len(imgs)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
    for i,p in enumerate(imgs):
        rr,cc=divmod(i,cols);bx=x+cc*(cw+gap);by=y+h-(rr+1)*ch-rr*gap
        try:
            im=Image.open(p);iw,ih=im.size;s=min(cw/iw,ch/ih);dw,dh=iw*s,ih*s;c.drawImage(str(p),bx+(cw-dw)/2,by+(ch-dh)/2,dw,dh,mask='auto')
        except Exception:pass

def generate(bot_module,data,output):
    rows=_records(data);groups={n:[] for n in range(1,13)}
    for r in rows:groups[_section(r)].append(r)
    def first(keys,default):
        for r in rows:
            v=_pick(r['raw'],keys)
            if v:return v
        return default
    ident=next((str(r['id']) for r in rows if str(r['id']).isdigit()),'MESA')
    meta={'pedido':first(('nº do pedido de pacificação','numero do pedido','numero_pedido','pedido'),f'INV-{ident[-6:]}'),
          'data':first(('data de expedição','data de expedicao','data_expedicao','data'),datetime.now().strftime('%d/%m/%Y')),
          'processo':first(('nº do processo','numero processo','numero_processo','processo'),f'PF-DICOR-{ident}'),
          'requerente':first(('requerente','solicitante','responsavel','responsável','autoridade'),'Polícia Federal - DICOR'),
          'org':first(('organização','organizacao','comunidade','grupo','alvo','investigado'),'Não identificado')}
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);c=canvas.Canvas(str(out),pagesize=(W,H))
    # 1 capa
    _bg(c);y=800; y=_text(c,f'N° do Pedido de Pacificação:   {meta["pedido"]}',40,y,12.2,True,690,18,1)-33; y=_text(c,f'Data de Expedição:      {meta["data"]}',40,y,12,False,690,18,1)-33; y=_text(c,f'N° do Processo:   {meta["processo"]}',40,y,12.2,True,690,18,1)-58;_label(c,'Requerente:',40,y);y-=28;y=_text(c,'• '+meta['requerente'],58,y,11.3,False,650,17,2)-26;_label(c,'Localização:',40,y);y-=28;y=_text(c,'• '+meta['requerente']+' — DICOR, conforme registros da mesa operacional.',58,y,11.2,False,650,17,4)-8;_text(c,'• Local/organização: '+meta['org'],58,y,11.2,False,650,17,3);c.showPage()
    # 2-3 fixas
    _bg(c);_text(c,'DISPOSIÇÕES DO MANDADO',205,830,14,True,360,18,1);y=775
    for t in ['O documento consolida exclusivamente informações encontradas nos registros da mesa.','Os dados permanecem vinculados às suas fontes originais.','Informações ausentes não são inventadas pelo gerador.','Anexos e imagens são preservados sempre que disponíveis.']:
        y=_text(c,'• '+t,56,y,11.4,False,650,17,3)-8
    c.showPage()
    _bg(c);_text(c,'PLANEJAMENTO OPERACIONAL',185,830,14,True,400,18,1);y=780
    for title,keys in [('Efetivo envolvido:',('efetivo','equipe','agente','membro')),('Recursos utilizados:',('recurso','viatura','equipamento')),('Estratégia de abordagem:',('estrategia','abordagem','setor','acesso')),('Medidas de proteção:',('proteção','protecao','morador'))]:
        _label(c,title,40,y);y-=24;vals=[r['content'] for r in rows if r['content'] and any(_norm(k) in _norm(r['content']) for k in keys)];y=_text(c,'• '+('; '.join(dict.fromkeys(vals)) if vals else 'Conforme registros da mesa.'),58,y,10.8,False,640,16,4)-15
    c.showPage()
    _bg(c);_text(c,'PROVAS E DOCUMENTAÇÕES',40,830,14,True,680,18,1);_text(c,'• Consolidação das evidências registradas nas tarefas, tópicos, mensagens e anexos da mesa operacional.',40,780,11.2,False,680,16.5,5);c.showPage()
    people=[]
    for r in groups[1]+groups[2]:
        for line in str(r['content']).splitlines():
            m=re.search(r'(.+?)\s*(?:RG\s*[:=-]\s*)(\d+)',line,re.I)
            if m:people.append((m.group(1).strip(' *:-'),m.group(2)))
    _bg(c);_label(c,'Mídia de Apoio:',40,830);_label(c,'Líder:',40,780);y=_text(c,(('• '+people[0][0]+'        RG: '+people[0][1]) if people else '• Não identificado'),58,742,11.1,False,640,16.5,2)-30;_label(c,'Gerentes:',40,y);y-=30
    for n,rg in people[1:10]:y=_text(c,f'• {n}        RG: {rg}',58,y,10.9,False,640,16.5,2)-3
    c.showPage()
    # páginas de evidência, uma por etapa
    for n in range(1,13):
        _bg(c);y=830;y=_text(c,f'{n}. {(["Foto do painel da organização.","Foto dos principais membros da organização.","Localização da organização.","Foto de cima da organização para realizar estratégia de pacificação:","Material que vendem.","Registrar compra do ilícito em frente ou dentro da comunidade/organização.","Foto do informante da organização.","Foto do baú de membros.","Foto do baú de líder.","Foto e localização do local de fabricação.","Foto e localização do local de produção.","Informações gerais."][n-1])}',40,y,11.4,True,680,17,3)-10
        rowsn=groups[n];_label(c,'Data e Local:',40,y);y=_text(c,'• '+('; '.join(dict.fromkeys(r['date'] for r in rowsn if r['date'])) or 'Conforme registros da mesa.'),58,y-24,10.6,False,640,15.5,4)-8;_label(c,'Descrição:',40,y);y=_text(c,'• '+(' '.join(r['content'] for r in rowsn if r['content']) or 'Nenhuma informação textual localizada.'),58,y-24,10.2,False,640,14.5,7)-8;_label(c,'Relação com o Processo:',40,y);y=_text(c,'• Informação consolidada a partir das tarefas, tópicos, mensagens e anexos vinculados a esta etapa.',58,y-24,10.2,False,640,14.5,4)-8;_label(c,'Mídia de Apoio:',40,y);imgs=_images(rowsn,bot_module);_text(c,f'• {len(imgs)} mídia(s) carregada(s).',58,y-24,10.2,False,640,15,2);_grid(c,imgs,75,70,620,300,4,8);c.showPage()
    _bg(c);_text(c,'MOTIVAÇÃO',270,830,14,True,260,18,1);txt='\n'.join('• '+r['content'] for r in rows if r['content'] and any(k in _norm(r['content']) for k in ('art.','historico','histórico','ameaça','violencia','violência','prisao','prisão','controle territorial'))) or '• Fundamentação conforme os registros da mesa operacional.';_text(c,txt,40,780,10.7,False,680,15.5,32);c.showPage()
    _bg(c);_text(c,'PROVAS E DOCUMENTAÇÕES',40,830,14,True,680,18,1);_text(c,f'Consolidação final da mesa referente à organização {meta["org"]}. O documento foi montado a partir dos registros disponíveis e mantém as evidências vinculadas às respectivas fontes.',40,780,11.0,False,680,16.5,8);_label(c,'DELEGADO RESPONSÁVEL:',40,650);_text(c,meta['requerente'],58,622,11.2,False,640,17,2);_label(c,'DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR',40,545,10.2);_text(c,'______________________________',95,390,11,False,270,17,1);_text(c,'______________________________',440,390,11,False,270,17,1);_text(c,'Responsável pela consolidação',92,365,9.4,False,280,14,1);_text(c,'Autoridade DICOR',455,365,9.4,False,220,14,1);c.showPage();c.save();return str(out)

gerar_pdf_dossie=generate
gerar_pdf=generate

def install(bot_module): print('✅ V500 Dossiê instalado: gerador novo e independente.',flush=True)
