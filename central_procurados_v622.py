# -*- coding: utf-8 -*-
"""Central DICOR V622 - correção final de Procurados + Banco de Fotos."""
from __future__ import annotations

import html
import io
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Any

import central_procurados_v621 as v621
import central_discord_v613 as base

base.quote = quote
_CLIENT: Any = None
PHOTO_CHANNEL_ID = int(os.getenv("CENTRAL_FOTOS_CHANNEL_ID", "0") or 0)
PHOTO_NAMES = {"central-fotos", "fotos-central", "fotos", "arquivo-fotos"}


def clean(v: Any) -> str:
    s = str(v or "")
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_~`]+", "", s)
    s = s.replace("\\n", " ")
    return re.sub(r"\s+", " ", s).strip(" |•-—:;\t\r\n")


def norm(v: Any) -> str:
    s = clean(v).casefold()
    s = re.sub(r"[^a-zà-ÿ0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fields(m: Any) -> list[tuple[str,str]]:
    out=[]
    for e in getattr(m,"embeds",[]) or []:
        for f in getattr(e,"fields",[]) or []:
            n,v=clean(getattr(f,"name","")),clean(getattr(f,"value",""))
            if n or v: out.append((n,v))
    return out


def field_value(fs: list[tuple[str,str]], labels: tuple[str,...]) -> str:
    wanted=[norm(x) for x in labels]
    for n,v in fs:
        nn=norm(n)
        if any(nn==w or w in nn for w in wanted): return clean(v)
    return ""


def all_text(m: Any, fs: list[tuple[str,str]]) -> str:
    p=[clean(getattr(m,"content","") or "")]
    for e in getattr(m,"embeds",[]) or []:
        p += [clean(getattr(e,"title","") or ""), clean(getattr(e,"description","") or "")]
    p += [f"{n}: {v}" for n,v in fs]
    return clean(" | ".join(x for x in p if x))


def text_value(text: str, labels: tuple[str,...]) -> str:
    for label in labels:
        m=re.search(rf"(?:{re.escape(label)})\s*[:=-]\s*([^|\n]+)",text,re.I)
        if m: return clean(m.group(1))[:500]
    return ""


def name_value(m: Any, fs: list[tuple[str,str]], text: str) -> str:
    value=field_value(fs,("nome completo","nome do procurado","nome do indivíduo","nome","indivíduo","individuo"))
    if value: return value
    value=text_value(text,("nome completo","nome do procurado","nome do indivíduo","nome"))
    if value: return value
    # Alguns registros usam o nome no autor/título do embed.
    for e in getattr(m,"embeds",[]) or []:
        author=getattr(e,"author",None)
        av=clean(getattr(author,"name","") if author else "")
        if av and norm(av) not in {"procurado","procurados","registro","dicor","central dicor"}: return av
        title=clean(getattr(e,"title","") or "")
        title=re.sub(r"^(?:procurado|registro|mandado)\s*(?:n[ºo°#:-]?\s*\d+)?\s*[-:|•]?\s*","",title,flags=re.I)
        if title and norm(title) not in {"procurados","registro de procurado"}: return title
    # Conteúdo em formato "NOME | RG | ...".
    first=re.split(r"\s*[|•\n]\s*",text,maxsplit=1)[0]
    return first


def normalize_name(v: Any) -> str:
    s=clean(v)
    s=re.sub(r"^(?:nome(?:\s+completo)?|nome\s+do\s+(?:procurado|indiv[ií]duo)|indiv[ií]duo|procurado)\s*[:#=-]?\s*","",s,flags=re.I)
    s=re.sub(r"^(?:n[ºo°]|registro)\s*[:#=-]?\s*\d+\s*[-|•:]\s*","",s,flags=re.I)
    s=re.split(r"\s*[|•]\s*",s,maxsplit=1)[0]
    s=re.sub(r"\s+"," ",s).strip(" -:;")
    if not s or re.match(r"^(?:rg|passaporte|crime|crimes|status|situa[cç][aã]o|pena|senten[cç]a)\b",s,re.I): return "Indivíduo não identificado"
    return s[:90]


def crime_value(fs: list[tuple[str,str]], text: str) -> str:
    v=field_value(fs,("crimes cometidos","crimes","crime","acusações","acusação","acusacao","infrações","infracoes","artigos","envolvimento"))
    if not v: v=text_value(text,("crimes cometidos","crimes","crime","acusações","acusação","acusacao","infrações","infracoes","artigos"))
    return v[:600] if v else "Não informado"


def image_source(m: Any) -> str:
    for e in getattr(m,"embeds",[]) or []:
        for attr in ("image","thumbnail"):
            obj=getattr(e,attr,None); url=clean(getattr(obj,"url","") if obj else "")
            if url: return url
    for a in getattr(m,"attachments",[]) or []:
        url=clean(getattr(a,"url",""))
        if url: return url
    return ""


def penalty(text: str) -> int:
    t=clean(text).casefold()
    m=re.search(r"(?:pena|senten[cç]a).{0,60}?(\d+)\s*anos?(?:\s*e\s*(\d+)\s*mes(?:es)?)?",t)
    if m: return int(m.group(1))*12+int(m.group(2) or 0)
    m=re.search(r"(?:pena|senten[cç]a).{0,60}?(\d+)\s*mes(?:es)?",t)
    return int(m.group(1)) if m else 0


def closed(text: str) -> bool:
    return bool(re.search(r"\b(capturad[oa]s?|pres[oa]s?|encerrad[oa]s?|cancelad[oa]s?|finalizad[oa]s?)\b",clean(text).casefold()))


async def collect_procurados(client: Any) -> list[dict[str,Any]]:
    channel=await base.get_channel(client,base.PROCURADOS_ID)
    if channel is None: return []
    rows=[]
    try:
        async for m in channel.history(limit=1000,oldest_first=False):
            fs=fields(m); text=all_text(m,fs)
            if not text or closed(text): continue
            mid=getattr(m,"id",0); src=image_source(m)
            rows.append({
                "number":base.number_from(text),
                "name":normalize_name(name_value(m,fs,text)),
                "rg":(field_value(fs,("rg","registro geral","passaporte","identidade","id")) or text_value(text,("rg","registro geral","passaporte","identidade")) or "Não informado")[:80],
                "crime":crime_value(fs,text),
                "last_seen":(field_value(fs,("último avistamento","ultimo avistamento","última localização","ultima localização","localização","localizacao","avistamento","última vez visto")) or text_value(text,("último avistamento","ultimo avistamento","última localização","ultima localização","localização","localizacao","avistamento","última vez visto")) or "Não informado")[:250],
                "status":field_value(fs,("status","situação","situacao")) or "ATIVO",
                "created":getattr(m,"created_at",None) or datetime.now(timezone.utc),
                "url":getattr(m,"jump_url","#"),
                "image":f"/imagem-procurado/{mid}" if src and mid else "",
                "image_source":src,
                "preview":text[:2500],
                "source_id":mid,
                "penalty_months":penalty(text),
            })
    except Exception as exc:
        print(f"⚠️ V622 Procurados: {type(exc).__name__}: {exc}",flush=True); return []
    return sorted({r.get("source_id") or r.get("url") or id(r):r for r in rows}.values(),key=lambda r:r.get("created") or datetime.min.replace(tzinfo=timezone.utc),reverse=True)


base.collect_procurados=collect_procurados
v621.collect_procurados=collect_procurados
v621.v620.collect_procurados=collect_procurados
v621.v620.v616.collect_procurados=collect_procurados

# Usa o card/registro da V621, mas garante que o destino individual é sempre interno.
v621.base.dashboard=v621.dashboard

async def find_photo_channel(client: Any):
    if PHOTO_CHANNEL_ID:
        c=await base.get_channel(client,PHOTO_CHANNEL_ID)
        if c: return c
    for g in getattr(client,"guilds",[]) or []:
        for c in getattr(g,"text_channels",[]) or []:
            if clean(getattr(c,"name","")).casefold() in PHOTO_NAMES: return c
    # Primeira utilização: cria o canal de arquivo automaticamente.
    for g in getattr(client,"guilds",[]) or []:
        try:
            return await g.create_text_channel("central-fotos",reason="DICOR Central - armazenamento visual")
        except Exception:
            continue
    return None


def photo_card(link:str,name:str,dt:Any)->str:
    return f'''<article class="photo-item"><img src="{html.escape(link,quote=True)}" alt="{html.escape(name,quote=True)}" loading="lazy"><div class="pi"><small>{html.escape(name)} • {dt.astimezone().strftime("%d/%m/%Y %H:%M")}</small><div class="stable-link">{html.escape(link,quote=True)}</div><button class="copy-link" onclick="navigator.clipboard.writeText(location.origin+\'{html.escape(link,quote=True)}')">COPIAR LINK ESTÁVEL</button></div></article>'''


async def photos_page(req: Any):
    session=base.read_session(req)
    if not session: raise base.web.HTTPFound("/cadastro-operador?next=/fotos")
    channel=await find_photo_channel(_CLIENT); items=[]
    if channel:
        try:
            async for m in channel.history(limit=80,oldest_first=False):
                for a in getattr(m,"attachments",[]) or []:
                    if getattr(a,"content_type","") and not str(a.content_type).startswith("image/"): continue
                    items.append((f"/foto/{m.id}",clean(getattr(a,"filename","Foto")),getattr(m,"created_at",datetime.now(timezone.utc))))
        except Exception as exc: print(f"⚠️ V622 fotos: {type(exc).__name__}: {exc}",flush=True)
    qra,passport=session
    cards="".join(photo_card(*x) for x in items) or '<div class="empty">Nenhuma foto armazenada ainda.</div>'
    body=f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {html.escape(qra)} • {html.escape(passport)}</div></header><div class="central-tabs"><a class="tab" href="/procurados">PROCURADOS</a><a class="tab active" href="/fotos">FOTOS</a></div><div class="photo-manager"><div class="photo-hero"><div class="eyebrow">CENTRAL DICOR • ARQUIVO VISUAL</div><h1>BANCO DE FOTOS</h1><p>Envie uma imagem, armazene no arquivo da Central e receba um link próprio que não depende do link direto da mensagem.</p><form class="upload-zone" method="post" action="/fotos/upload" enctype="multipart/form-data"><b>ADICIONAR NOVA FOTO</b><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required><button class="upload-btn" type="submit">ENVIAR E GERAR LINK</button></form></div><section class="wanted"><div class="wanted-head"><b>ARQUIVO VISUAL</b><span>{len(items)} FOTO(S)</span></div><div class="photo-list">{cards}</div></section></div></main></div><script></script>'''
    return base.web.Response(text=base.page("DICOR • Fotos",body,base.APP_CSS+v621.PHOTO_CSS),content_type="text/html")


async def upload_photo(req: Any):
    session=base.read_session(req)
    if not session: raise base.web.HTTPFound("/cadastro-operador?next=/fotos")
    reader=await req.multipart(); part=await reader.next()
    if part is None or part.name!="foto": raise base.web.HTTPBadRequest(text="Imagem não enviada.")
    filename=os.path.basename(part.filename or "foto.png")
    if not re.search(r"\.(?:png|jpe?g|webp|gif)$",filename,re.I): raise base.web.HTTPBadRequest(text="Use PNG, JPG, WEBP ou GIF.")
    data=await part.read(decode=False)
    if not data or len(data)>10*1024*1024: raise base.web.HTTPBadRequest(text="A imagem deve ter até 10 MB.")
    channel=await find_photo_channel(_CLIENT)
    if channel is None: raise base.web.HTTPServiceUnavailable(text="Não foi possível criar o arquivo de fotos.")
    try:
        import discord
        msg=await channel.send(content=f"CENTRAL DICOR • ARQUIVO VISUAL • {filename}",file=discord.File(io.BytesIO(data),filename=filename))
        link=f"/foto/{msg.id}"
        body=f'''<main class="auth"><div class="eyebrow">CENTRAL DICOR • ARQUIVO VISUAL</div><h1>FOTO ARMAZENADA</h1><p class="sub">A imagem foi guardada no arquivo e recebeu um link próprio da Central.</p><div class="photo-msg"><b>LINK ESTÁVEL</b><div class="stable-link">{html.escape(link)}</div><button class="upload-btn" onclick="navigator.clipboard.writeText(location.origin+'{html.escape(link)}');return false;">COPIAR LINK</button></div><a class="primary gold" style="display:block;text-decoration:none;padding-top:16px" href="/fotos">VOLTAR AO BANCO DE FOTOS</a></main>'''
        return base.web.Response(text=base.page("DICOR • Foto",body,base.AUTH_CSS+v621.PHOTO_CSS),content_type="text/html")
    except Exception as exc:
        print(f"⚠️ V622 upload: {type(exc).__name__}: {exc}",flush=True); raise base.web.HTTPInternalServerError(text="Não foi possível armazenar a foto.")


async def stable_photo(req: Any):
    if not base.read_session(req): raise base.web.HTTPFound("/cadastro-operador?next="+quote(req.path))
    mid=int(req.match_info.get("message_id","0")); channel=await find_photo_channel(_CLIENT)
    if not channel: raise base.web.HTTPNotFound()
    try:
        msg=await channel.fetch_message(mid); a=next(iter(getattr(msg,"attachments",[]) or []),None)
        if a is None: raise base.web.HTTPNotFound()
        return base.web.Response(body=await a.read(),content_type=getattr(a,"content_type",None) or "application/octet-stream",headers={"Cache-Control":"public,max-age=31536000,immutable"})
    except base.web.HTTPException: raise
    except Exception: raise base.web.HTTPNotFound()


async def procurado_photo(req: Any):
    if not base.read_session(req): raise base.web.HTTPFound("/cadastro-operador?next="+quote(req.path))
    mid=int(req.match_info.get("message_id","0")); channel=await base.get_channel(_CLIENT,base.PROCURADOS_ID)
    if not channel: raise base.web.HTTPNotFound()
    try:
        msg=await channel.fetch_message(mid)
        a=next(iter(getattr(msg,"attachments",[]) or []),None)
        if a is not None: return base.web.Response(body=await a.read(),content_type=getattr(a,"content_type",None) or "image/jpeg",headers={"Cache-Control":"public,max-age=3600"})
        src=image_source(msg)
        if not src: raise base.web.HTTPNotFound()
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(src,timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status!=200: raise base.web.HTTPNotFound()
                return base.web.Response(body=await r.read(),content_type=r.headers.get("Content-Type","image/jpeg"),headers={"Cache-Control":"public,max-age=3600"})
    except base.web.HTTPException: raise
    except Exception: raise base.web.HTTPNotFound()


async def detail_route(req: Any):
    session=base.read_session(req)
    if not session: raise base.web.HTTPFound("/cadastro-operador?next="+quote(req.path))
    rid=str(req.match_info.get("source_id","")); rows=base.CACHE.get("procurados",[])
    row=next((r for r in rows if str(r.get("source_id"))==rid),None)
    if row is None:
        fresh=await collect_procurados(_CLIENT); row=next((r for r in fresh if str(r.get("source_id"))==rid),None)
    if row is None: raise base.web.HTTPNotFound(text="Registro não encontrado.")
    qra,passport=session
    return base.web.Response(text=v621.wanted_detail(row,qra,passport),content_type="text/html")


class ApplicationPatch(base.web.Application):
    def __init__(self,*args:Any,**kwargs:Any):
        super().__init__(*args,**kwargs)
        self.router.add_get("/procurado/{source_id}",detail_route,name="v622_detail")
        self.router.add_get("/imagem-procurado/{message_id}",procurado_photo,name="v622_wanted_photo")
        self.router.add_get("/fotos",photos_page,name="v622_photos")
        self.router.add_get("/foto/{message_id}",stable_photo,name="v622_stable_photo")
        self.router.add_post("/fotos/upload",upload_photo,name="v622_upload")


async def start_server_v622(client: Any):
    global _CLIENT
    _CLIENT=client
    original=base.web.Application
    base.web.Application=ApplicationPatch
    try:
        return await v621.v620.v616.start_server_v616(client)
    finally:
        base.web.Application=original


base.start_server=start_server_v622
v621.v620.base.start_server=start_server_v622


def install(bot_module: Any):
    return base.install(bot_module)
