# -*- coding: utf-8 -*-
"""Ajuste V161: somente as assinaturas oficiais dos dois delegados."""
from pathlib import Path
import re


def install(renderer_module) -> None:
    """Mantém apenas Buiu Gomes e Arthur Fleker na página de assinaturas."""

    def _signature_page(meta, styles):
        pedido = renderer_module._sanitize_text(
            meta.get('pedido_numero') or meta.get('numero') or 'Não informado'
        )
        local = renderer_module._sanitize_text(
            meta.get('pedido_local') or meta.get('comunidade') or 'área indicada no procedimento'
        )
        try:
            from zoneinfo import ZoneInfo
            hoje = renderer_module.datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y')
        except Exception:
            hoje = renderer_module.datetime.now().strftime('%d/%m/%Y')

        flow = [renderer_module.Paragraph('PROVAS E DOCUMENTAÇÕES', styles['section'])]
        flow += [renderer_module._bullet(
            f'Com base nas provas apresentadas e nas informações consolidadas no processo, solicita-se a manutenção do Pedido de Pacificação {pedido} e a adoção das medidas necessárias à segurança operacional na área indicada como “{local}”.',
            styles,
        )]
        flow += [
            renderer_module.Spacer(1, 8),
            renderer_module.Paragraph('<b>RESPONSÁVEIS PELO PROCEDIMENTO</b>', styles['tiny']),
            renderer_module.Spacer(1, 3),
            renderer_module.Paragraph('Buiu Gomes - Delegado Geral', styles['tiny']),
            renderer_module.Paragraph('Arthur Fleker - Delegado DICOR', styles['tiny']),
            renderer_module.Paragraph(f'Capital Morada do Valley - {hoje}', styles['tiny']),
            renderer_module.Spacer(1, 36),
        ]

        def _sig_block(nome, cargo):
            nome_limpo = renderer_module._sanitize_text(nome)
            return [
                renderer_module.Paragraph(nome_limpo, styles['sig_name']),
                renderer_module.Spacer(1, 4),
                renderer_module.Paragraph(nome_limpo.upper(), styles['sig_caps']),
                renderer_module.Paragraph(cargo, styles['sig_caps']),
                renderer_module.Paragraph('POLÍCIA FEDERAL - DICOR', styles['sig_caps']),
            ]

        delegados = renderer_module.Table(
            [[
                _sig_block('Buiu Gomes', 'DELEGADO GERAL'),
                _sig_block('Arthur Fleker', 'DELEGADO DICOR'),
            ]],
            colWidths=[8.05 * renderer_module.cm, 8.05 * renderer_module.cm],
            hAlign='CENTER',
        )
        delegados.setStyle(renderer_module.TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LINEABOVE', (0, 0), (0, 0), 0.85, renderer_module.HexColor('#444444')),
            ('LINEABOVE', (1, 0), (1, 0), 0.85, renderer_module.HexColor('#444444')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        flow.append(renderer_module.KeepTogether([delegados]))
        return flow

    def _preflight(path):
        p = Path(path)
        if not p.exists() or p.stat().st_size < 6000:
            raise RuntimeError('V161: PDF invalido ou vazio.')
        try:
            import fitz
            doc = fitz.open(str(p))
            text = '\n'.join(page.get_text('text') or '' for page in doc)
            doc.close()
        except Exception:
            return
        if re.search(r'(?i)\bDENARC\b', text):
            raise RuntimeError('V161: termo DENARC ainda apareceu no PDF.')
        if re.search(r'(?i)\bDIC\b', text):
            raise RuntimeError('V161: termo DIC isolado ainda apareceu no PDF.')
        required = (
            'POLÍCIA FEDERAL - DICOR',
            'Buiu Gomes',
            'Arthur Fleker',
            'DELEGADO GERAL',
            'DELEGADO DICOR',
            'INGREDIENTES',
            'PRODUTO FINAL',
        )
        missing = [item for item in required if item not in text]
        if missing:
            raise RuntimeError('V161: preflight ausente: ' + ', '.join(missing))

    renderer_module._signature_page = _signature_page
    renderer_module._preflight = _preflight
    print('✅ V161 assinaturas: somente Buiu Gomes e Arthur Fleker.', flush=True)
