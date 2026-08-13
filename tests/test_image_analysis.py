import io

from PIL import Image

import image_analysis as ia


def test_ocr_health_ready_with_real_backend():
    status = ia.health_check()
    assert status.ready, status.error
    assert status.engine == "rapidocr_onnxruntime"
    assert status.backend == "onnxruntime-cpu"
    assert status.records >= 1


def test_panel_pipeline_reads_cargo_nome_passaporte():
    result = ia.analyze_panel_image(
        ia.create_synthetic_panel_image(),
        filename="painel.png",
        content_type="image/png",
    )
    assert result.records
    first = result.records[0]
    assert first["cargo"] == "GERENTE"
    assert first["nome"] == "TESTE SILVA"
    assert first["passaporte"] == "12345"
    transcription = ia.build_panel_transcription(result.records)
    assert "PAINEL TRANSCRITO" in transcription
    assert "Passaporte: 12345" in transcription


def test_database_pipeline_preserves_rows_and_columns():
    result = ia.analyze_database_image(
        ia.create_synthetic_database_image(),
        filename="banco.png",
        content_type="image/png",
    )
    assert list(result.records) == [
        {"rg": "12345", "nome": "TESTE SILVA", "cargo": "GERENTE", "telefone": "555-0100"},
        {"rg": "54321", "nome": "TESTE SOUZA", "cargo": "MEMBRO", "telefone": "555-0200"},
    ]
    assert result.doubtful == ()


def test_panel_parser_handles_two_visual_columns_without_mixing():
    lines = [
        ia.OcrLine(text="Cargo: GERENTE", x1=20, x2=180, cx=100, y1=20, y2=40, cy=30, height=20),
        ia.OcrLine(text="Nome: JULIANA SALVATORI", x1=20, x2=260, cx=140, y1=50, y2=70, cy=60, height=20),
        ia.OcrLine(text="Passaporte: 40335", x1=20, x2=220, cx=120, y1=80, y2=100, cy=90, height=20),
        ia.OcrLine(text="Cargo: GERENTE", x1=430, x2=590, cx=510, y1=20, y2=40, cy=30, height=20),
        ia.OcrLine(text="Nome: ROGER MAX", x1=430, x2=650, cx=540, y1=50, y2=70, cy=60, height=20),
        ia.OcrLine(text="Passaporte: 20725", x1=430, x2=630, cx=530, y1=80, y2=100, cy=90, height=20),
    ]
    records, ignored = ia.parse_panel_people(lines, image_width=800)
    assert ignored == []
    assert [record.as_dict() for record in records] == [
        {"cargo": "GERENTE", "nome": "JULIANA SALVATORI", "passaporte": "40335", "rg": "40335"},
        {"cargo": "GERENTE", "nome": "ROGER MAX", "passaporte": "20725", "rg": "20725"},
    ]


def test_database_parser_separates_doubtful_from_ignored():
    text = """
    RG | NOME | CARGO | TELEFONE
    12345 | TESTE SILVA | GERENTE | 555-0100
    SEM RG | LINHA SOLTA
    """
    valid, doubtful, ignored = ia.parse_database_table(text)
    assert [record.as_member_dict() for record in valid] == [
        {"rg": "12345", "nome": "TESTE SILVA", "cargo": "GERENTE", "telefone": "555-0100"}
    ]
    assert isinstance(doubtful, list)
    assert isinstance(ignored, list)


def test_invalid_image_bytes_fail_before_ocr():
    try:
        ia.analyze_panel_image(b"not an image", filename="x.png", content_type="image/png")
    except ValueError as exc:
        assert "imagem" in str(exc).lower() or "bytes" in str(exc).lower()
    else:
        raise AssertionError("invalid bytes should not be accepted")


def test_webp_normalization_supported_when_pillow_supports_webp():
    img = Image.new("RGB", (320, 120), (255, 255, 255))
    output = io.BytesIO()
    img.save(output, "WEBP")
    normalized, info = ia.load_image_bytes(output.getvalue(), filename="teste.webp", content_type="image/webp")
    try:
        assert normalized.mode == "RGB"
        assert info.fmt == "WEBP"
    finally:
        normalized.close()
