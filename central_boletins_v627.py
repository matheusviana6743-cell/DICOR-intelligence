# -*- coding: utf-8 -*-
"""Central DICOR V627 — Boletins e Perícias.

Mantém a Central V625 como base e altera somente a apresentação dos
módulos Boletins/Perícias. O visual segue o modelo DICOR arquivado:
fundo escuro, moldura/linhas douradas, brasão DICOR e cartões organizados.
"""
from __future__ import annotations

import html
from typing import Any

import central_procurados_v625 as v625

base = v625.base


BO_CSS = r'''
.bo-page{min-height:100vh;background:#05080d;color:#edf2f6;padding-bottom:42px}
.bo-wrap{width:min(1180px,calc(100% - 28px));margin:0 auto;padding-top:24px}
.bo-top{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 0 18px;border-bottom:1px solid #24384b}
.bo-brand{display:flex;align-items:center;gap:13px}.bo-brand img{width:58px;height:58px;object-fit:contain;background:transparent;mix-blend-mode:multiply;filter:drop-shadow(0 8px 16px #0008)}
.bo-brand strong{display:block;font-size:14px;letter-spacing:2px;color:#f0f3f6}.bo-brand span{display:block;margin-top:4px;font-size:9px;letter-spacing:1.7px;color:#c8a04a}
.bo-operator{font-size:9px;color:#74899d}.online-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#39d58a;box-shadow:0 0 10px #39d58a;margin-right:7px}
.bo-hero{margin-top:19px;padding:30px;border:1px solid #34506a;border-radius:18px;background:radial-gradient(circle at 88% 20%,#163b5e 0,#0a1826 30%,#070f18 72%);position:relative;overflow:hidden}
.bo-hero:before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,transparent 0 58%,#c69b3a08 58% 60%,transparent 60%);pointer-events:none}
.bo-eyebrow{font-size:9px;letter-spacing:2.5px;color:#6bb0ee;font-weight:900}.bo-hero h1{margin:9px 0 8px;font-size:36px;letter-spacing:1px}.bo-hero p{margin:0;max-width:740px;color:#8195a9;font-size:11px;line-height:1.7}
.bo-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin-top:14px}.bo-stat{border:1px solid #21384d;border-radius:13px;background:#08111b;padding:16px}.bo-stat small{font-size:8px;letter-spacing:1.4px;color:#688198}.bo-stat b{display:block;font-size:27px;margin-top:7px;color:#dce8f1}.bo-stat.gold b{color:#e3bc5a}.bo-stat.blue b{color:#63adf0}.bo-stat.red b{color:#ff717a}
.bo-panel{margin-top:15px;border:1px solid #29445d;border-radius:17px;background:#070e15;overflow:hidden}.bo-panel-head{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:15px 18px;border-bottom:1px solid #1c3042}.bo-panel-head strong{font-size:11px;letter-spacing:1.6px}.bo-panel-head span{font-size:8px;color:#667e94;letter-spacing:1px}
.bo-list{display:grid;gap:10px;padding:13px}.bo-item{display:grid;grid-template-columns:70px 1fr auto;align-items:center;gap:15px;padding:15px;border:1px solid #1a3146;border-radius:13px;background:linear-gradient(145deg,#0c1722,#071019)}.bo-number{height:46px;width:46px;border-radius:11px;display:grid;place-items:center;background:#102b43;border:1px solid #315b7b;color:#e7be5b;font-size:12px;font-weight:900}.bo-content{min-width:0}.bo-title{font-size:12px;font-weight:900;color:#edf3f7;margin-bottom:5px}.bo-sub{font-size:9px;color:#71869a;line-height:1.65}.bo-sub b{color:#97adc0}.bo-open{padding:10px 13px;border:1px solid #7b5d1f;border-radius:9px;background:linear-gradient(135deg,#e6c261,#9a6d19);color:#090b0e;font-size:8px;font-weight:900;white-space:nowrap}.bo-empty{padding:42px 20px;text-align:center;color:#657b8f;font-size:10px}
.bo-tabs{display:flex;gap:8px;margin-top:15px;flex-wrap:wrap}.bo-tab{padding:10px 15px;border:1px solid #27425a;border-radius:9px;color:#7690a7;font-size:8px;font-weight:900;letter-spacing:1.2px}.bo-tab.active{background:#112c45;border-color:#3b6384;color:#e3bc5a}.bo-back{display:inline-block;margin-top:15px;color:#79a9d6;font-size:9px}
@media(max-width:760px){.bo-wrap{width:min(100% - 18px,1180px);padding-top:10px}.bo-top{align-items:flex-start}.bo-operator{font-size:0}.bo-hero{padding:22px 18px}.bo-hero h1{font-size:28px}.bo-stats{grid-template-columns:1fr}.bo-item{grid-template-columns:52px 1fr}.bo-open{grid-column:2;justify-self:start}.bo-list{padding:9px}.bo-panel-head{align-items:flex-start;flex-direction:column;gap:6px}}
'''


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def num_label(v: Any) -> str:
    s=str(v or "S/N")
    digits=''.join(ch for ch in s if ch.isdigit())
    return digits[-4:].zfill(4) if digits else 'S/N'


def nice_date(v: Any) -> str:
    try:
        return v.astimezone().strftime('%d/%m/%Y • %H:%M')
    except Exception:
        return '--'


def module_page(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    is_pericia=kind == 'pe'
    icon='🔬' if is_pericia else '📋'
    label='PERÍCIAS EXTERNAS' if is_pericia else 'BOLETINS DE OCORRÊNCIA'
    accent='PERÍCIAS • ATENDIMENTOS' if is_pericia else 'BO • ATENDIMENTOS'
    items=[]
    for r in rows:
        number=esc(num_label(r.get('number')))
        title_row=esc(r.get('name') or ('Atendimento de perícia' if is_pericia else 'Boletim de ocorrência'))
        date=esc(nice_date(r.get('created')))
        item_id=esc(r.get('url') or '#')
        status='EM ANDAMENTO'
        items.append(f'''<article class="bo-item"><div class="bo-number">{number}</div><div class="bo-content"><div class="bo-title">{title_row}</div><div class="bo-sub"><b>{label}</b><br>Recebido em {date}<br>Status: <b>{status}</b></div></div><a class="bo-open" href="{item_id}" target="_blank" rel="noopener">ABRIR ATENDIMENTO →</a></article>''')
    content=''.join(items) or '<div class="bo-empty">Nenhum atendimento ativo encontrado no Discord.</div>'
    body=f'''<div class="bo-page"><div class="bo-wrap"><header class="bo-top"><div class="bo-brand">{base.img(base.DICOR_LOGO,"","DICOR")}<div><strong>POLÍCIA FEDERAL • DICOR</strong><span>PCPT • POLÍCIA CAPITAL / POLÍCIA FEDERAL</span></div></div><div class="bo-operator"><span class="online-dot"></span>{esc(qra)}</div></header><section class="bo-hero"><div class="bo-eyebrow">{esc(accent)} • CENTRAL OPERACIONAL</div><h1>{icon} {esc(title)}</h1><p>{esc(subtitle)}</p></section><section class="bo-stats"><div class="bo-stat blue"><small>ATENDIMENTOS ATIVOS</small><b>{len(rows)}</b></div><div class="bo-stat gold"><small>FONTE</small><b>DISCORD</b></div><div class="bo-stat red"><small>STATUS</small><b>ATIVO</b></div></section><nav class="bo-tabs"><a class="bo-tab {'active' if not is_pericia else ''}" href="/boletins">BOLETINS</a><a class="bo-tab {'active' if is_pericia else ''}" href="/pericias">PERÍCIAS</a><a class="bo-tab" href="/procurados">PROCURADOS</a><a class="bo-tab" href="/funcionalidades">FUNCIONALIDADES</a></nav><section class="bo-panel"><div class="bo-panel-head"><strong>{esc(label)}</strong><span>{len(rows)} REGISTRO(S) • SINCRONIZAÇÃO COM DISCORD</span></div><div class="bo-list">{content}</div></section><a class="bo-back" href="/funcionalidades">← Voltar para todas as funcionalidades</a></div></div>'''
    return base.page(f'DICOR • {title}',body,base.APP_CSS+BO_CSS)


def listing(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    return module_page(title, subtitle, rows, qra, kind)


# O servidor V625 continua responsável pela integração/rotas. As rotas
# /boletins e /pericias chamam a função global `listing`, portanto basta
# substituir essa função antes do start do servidor.
v625.base.listing = listing
base.listing = listing
base.start_server = v625.start_server_v625


def install(bot_module: Any):
    return base.install(bot_module)
