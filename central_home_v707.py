# -*- coding: utf-8 -*-
"""DICOR Central V707.
Adds a polished access screen and broader Discord synchronization while
keeping V706 presentation and the V700 authentication/persistence core.
"""
from __future__ import annotations

import html
import json
from urllib.parse import quote

from aiohttp import web

import central_home_v706 as v706
import central_home_v700 as v700

CSS_LOGIN = r"""
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#f4f7f9}body{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0,#153c58 0,transparent 32%),radial-gradient(circle at 15% 15%,#0e2738 0,transparent 30%),#02070c}a{text-decoration:none;color:inherit}.login{width:min(560px,calc(100% - 30px));padding:34px;border:1px solid #29485b;border-radius:22px;background:linear-gradient(155deg,#0a1b28f8,#050e15f8);box-shadow:0 30px 90px #000b;text-align:center}.login img{width:125px;height:125px;object-fit:contain;filter:drop-shadow(0 14px 24px #000b)}.login .brandline{margin-top:10px;color:#f1d477;font-weight:900;font-size:10px;letter-spacing:2px}.login h1{font-size:30px;margin:8px 0}.login p{color:#92a5b1;font-size:12px;margin:0 0 24px}.form{text-align:left}.form label{display:block;color:#6d8595;font-size:9px;font-weight:900;letter-spacing:1.4px;margin:14px 0 6px}.form input{width:100%;height:51px;border:1px solid #2a475a;background:#06121b;color:#f3f6f8;border-radius:10px;padding:0 14px;font-size:14px;outline:none}.form input:focus{border-color:#e0c15d;box-shadow:0 0 0 3px #e0c15d1d}.submit{width:100%;height:51px;border:0;border-radius:10px;margin-top:18px;background:linear-gradient(135deg,#f1d274,#a87414);color:#090b0c;font-size:11px;font-weight:950;letter-spacing:.8px}.login .foot{margin-top:16px;color:#566f7f;font-size:9px}
"""


def login(err=""):
    error = f'<div style="margin:12px 0;padding:10px;border:1px solid #65353c;border-radius:9px;color:#e5aeb3;background:#211014;font-size:11px">{html.escape(str(err))}</div>' if err else ""
    body=f'''<main class="login"><img src="{v706.e(v706.LOGO)}" alt="Brasão DICOR"><div class="brandline">{v706.e(v706.BRAND)}</div><h1>ACESSO À CENTRAL</h1><p>Informe seu QRA e passaporte para acessar o ambiente DICOR.</p>{error}<form class="form" method="post" action="/cadastro-operador"><label>QRA</label><input name="qra" maxlength="45" autocomplete="username" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="20" placeholder="Digite seu passaporte" required><button class="submit">ENTRAR NA CENTRAL →</button></form><div class="foot">PCPT • POLICIA MORADA - POLICIA FEDERAL • DICOR</div></main>'''
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • Acesso</title><style>{CSS_LOGIN}</style></head><body>{body}</body></html>'


def _msg_text(m):
    parts=[getattr(m,"content","") or ""]
    for emb in getattr(m,"embeds",[]) or []:
        parts.extend([getattr(emb,"title","") or "",getattr(emb,"description","") or ""])
        for f in getattr(emb,"fields",[]) or []:
            parts.append(f"{getattr(f,'name','')}: {getattr(f,'value','')}")
    return v706.clean_text(" ".join(x for x in parts if x))


async def _scan_named_channels(client, keywords, kind):
    if not client or not getattr(client,"is_ready",lambda:False)(): return []
    out=[]; seen=set()
    for guild in getattr(client,"guilds",[]) or []:
        for ch in getattr(guild,"text_channels",[]) or []:
            nm=v706.clean_text(getattr(ch,"name","")).casefold()
            if not any(k in nm for k in keywords): continue
            cid=getattr(ch,"id",0)
            if cid in seen: continue
            seen.add(cid)
            try: msgs=[m async for m in ch.history(limit=200,oldest_first=False)]
            except Exception: continue
            for m in msgs:
                text=_msg_text(m)
                if not text: continue
                if kind=="boletins" and not any(x in text.casefold() for x in ("boletim","b.o.","ocorrência","ocorrencia")): continue
                if kind=="pericias" and not any(x in text.casefold() for x in ("perícia","pericia","laudo")): continue
                mid=str(getattr(m,"id","") or "")
                row={"id":mid or v706.hashlib.sha256((nm+text).encode()).hexdigest()[:20],"number":"S/N","name":v706.clean_text(text.split("\n",1)[0])[:100] or kind.title(),"kind":kind,"source":"DISCORD","subject":"","date":str(getattr(m,"created_at","")),"image":"","url":str(getattr(m,"jump_url","")),"fields":{"Canal":getattr(ch,"name","") or "","Número do registro":"S/N"},"full_text":text}
                out.append(row)
    uniq={r["id"]:r for r in out}
    return list(uniq.values())[:500]


_ORIG_V706_REFRESH=v700.refresh_data
async def refresh_data_v707():
    await _ORIG_V706_REFRESH()
    try:
        bo=await _scan_named_channels(v700.CLIENT,("boletim","boletins","b-o"),"boletins")
        pe=await _scan_named_channels(v700.CLIENT,("pericia","perícia","pericial"),"pericias")
        if bo: v700.C["boletins"] = list({str(r.get("id")):r for r in list(v700.C.get("boletins",[]) or [])+bo}.values())[:500]
        if pe: v700.C["pericias"] = list({str(r.get("id")):r for r in list(v700.C.get("pericias",[]) or [])+pe}.values())[:500]
    except Exception:
        pass


def install(bot_module):
    v700.login=login
    v700.refresh_data=refresh_data_v707
    return v706.install(bot_module)
