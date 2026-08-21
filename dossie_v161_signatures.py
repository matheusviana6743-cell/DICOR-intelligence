# -*- coding: utf-8 -*-
"""V162: assinaturas reais dos dois delegados + duas linhas independentes."""
from pathlib import Path
import re


def install(renderer_module, bot_module=None) -> None:
    """Mantém somente Buiu Gomes e Arthur Fleker, usando as imagens cadastradas no bot."""

    def _registered_images():
        imagens = [None, None]
        if bot_module is None:
            return imagens
        try:
            getter = getattr(bot_module, 'obter_assinaturas_dossie', None)
            if not callable(getter):
                return imagens
            regs = list(getter({}) or [])[:2]
            for idx, reg in enumerate(regs):
                caminho = reg.get('imagem') if isinstance(reg, dict) else None
                cleaner = getattr(bot_module, 'limpar_imagem_assinatura_dossie', None)
                if callable(cleaner):
                    try:
                        caminho = cleaner(caminho) or caminho
                    except Exception:
                        pass
                if caminho and Path(str(caminho)).exists():
                    imagens[idx] = Path(str(caminho))
        except Exception as exc:
            print(f'⚠️ V162: não foi possível carregar assinaturas cadastradas: {type(exc).__name__}', flush=True)
        return imagens

    def _fit_signature_image(path, max_w, max_h):
        if not path:
            return None
        try:
            p = Path(str(path))
            if not p.exists():
                return None
            reader = renderer_module.ImageReader(str(p))
            iw, ih = reader.getSize()
            if not iw or not ih:
                return None
            scale = min(float(max_w) / float(iw), float(max_h) / float(ih))
            return renderer_module.RLImage(
                str(p),
                width=max(1, float(iw) * scale),
                height=max(1, float(ih) * scale),
            )
        except Exception as exc:
            print(f'⚠️ V162: falha ao preparar imagem de assinatura: {type(exc).__name__}', flush=True)
            return None

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

        imagens = _registered_images()

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
            renderer_module.Spacer(1, 24),
        ]

        def _sig_block(nome, cargo, image_path):
            nome_limpo = renderer_module._sanitize_text(nome)
            img = _fit_signature_image(
                image_path,
                6.35 * renderer_module.cm,
                1.45 * renderer_module.cm,
            )
            if img is None:
                assinatura_visual = renderer_module.Paragraph(nome_limpo, styles['sig_name'])
            else:
                assinatura_visual = img

            detalhes = [
                renderer_module.Paragraph(nome_limpo.upper(), styles['sig_caps']),
                renderer_module.Paragraph(cargo, styles['sig_caps']),
                renderer_module.Paragraph('POLÍCIA FEDERAL - DICOR', styles['sig_caps']),
            ]
            bloco = renderer_module.Table(
                [[assinatura_visual], [detalhes]],
                colWidths=[7.35 * renderer_module.cm],
                hAlign='CENTER',
            )
            bloco.setStyle(renderer_module.TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('LINEABOVE', (0, 1), (0, 1), 0.85, renderer_module.HexColor('#444444')),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (0, 0), 0),
                ('BOTTOMPADDING', (0, 0), (0, 0), 4),
                ('TOPPADDING', (0, 1), (0, 1), 8),
                ('BOTTOMPADDING', (0, 1), (0, 1), 2),
            ]))
            return bloco

        esquerdo = _sig_block('Buiu Gomes', 'DELEGADO GERAL', imagens[0])
        direito = _sig_block('Arthur Fleker', 'DELEGADO DICOR', imagens[1])
        delegados = renderer_module.Table(
            [[esquerdo, '', direito]],
            colWidths=[7.35 * renderer_module.cm, 1.20 * renderer_module.cm, 7.35 * renderer_module.cm],
            hAlign='CENTER',
        )
        delegados.setStyle(renderer_module.TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        flow.append(renderer_module.KeepTogether([delegados]))
        return flow

    def _preflight(path):
        p = Path(path)
        if not p.exists() or p.stat().st_size < 6000:
            raise RuntimeError('V162: PDF invalido ou vazio.')
        try:
            import fitz
            doc = fitz.open(str(p))
            text = '\n'.join(page.get_text('text') or '' for page in doc)
            doc.close()
        except Exception:
            return
        if re.search(r'(?i)\bDENARC\b', text):
            raise RuntimeError('V162: termo DENARC ainda apareceu no PDF.')
        if re.search(r'(?i)\bDIC\b', text):
            raise RuntimeError('V162: termo DIC isolado ainda apareceu no PDF.')
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
            raise RuntimeError('V162: preflight ausente: ' + ', '.join(missing))

    renderer_module._signature_page = _signature_page
    renderer_module._preflight = _preflight
    print('✅ V162 assinaturas: imagens cadastradas + duas linhas independentes.', flush=True)
