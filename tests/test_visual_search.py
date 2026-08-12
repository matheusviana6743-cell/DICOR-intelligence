from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from visual_search import (
    VisualSearchError,
    VisualSearchIndex,
    can_rebuild_visual_index,
    extract_visual_features_from_bytes,
    is_supported_visual_file,
)


def _character_image(
    *,
    shirt: tuple[int, int, int],
    pants: tuple[int, int, int] = (35, 35, 35),
    skin: tuple[int, int, int] = (205, 160, 120),
    hat: tuple[int, int, int] | None = None,
    backpack: tuple[int, int, int] | None = None,
    face_hidden: bool = False,
    offset: int = 0,
) -> bytes:
    image = Image.new("RGB", (180, 240), (228, 232, 238))
    draw = ImageDraw.Draw(image)
    x = 90 + offset
    if backpack:
        draw.rounded_rectangle((x - 58, 88, x - 30, 172), radius=7, fill=backpack)
        draw.rounded_rectangle((x + 30, 88, x + 58, 172), radius=7, fill=backpack)
    if hat:
        draw.rectangle((x - 28, 34, x + 28, 46), fill=hat)
        draw.rounded_rectangle((x - 21, 18, x + 21, 40), radius=8, fill=hat)
    draw.ellipse((x - 28, 42, x + 28, 98), fill=skin)
    if face_hidden:
        draw.rectangle((x - 24, 60, x + 24, 82), fill=(30, 30, 30))
    else:
        draw.ellipse((x - 11, 64, x - 6, 69), fill=(20, 20, 20))
        draw.ellipse((x + 6, 64, x + 11, 69), fill=(20, 20, 20))
        draw.arc((x - 12, 72, x + 12, 90), 0, 180, fill=(120, 40, 40), width=2)
    draw.rounded_rectangle((x - 38, 96, x + 38, 170), radius=16, fill=shirt)
    draw.rectangle((x - 54, 108, x - 34, 164), fill=shirt)
    draw.rectangle((x + 34, 108, x + 54, 164), fill=shirt)
    draw.rectangle((x - 32, 170, x - 4, 228), fill=pants)
    draw.rectangle((x + 4, 170, x + 32, 228), fill=pants)
    draw.line((x - 38, 116, x + 38, 160), fill=tuple(max(0, c - 45) for c in shirt), width=3)
    draw.line((x + 38, 116, x - 38, 160), fill=tuple(min(255, c + 40) for c in shirt), width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _save(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _record(path: Path, rg: str, nome: str, image_id: str) -> dict:
    return {
        "image_id": image_id,
        "rg": rg,
        "nome": nome,
        "individuo_id": int("".join(ch for ch in rg if ch.isdigit()) or "1"),
        "registro_id": int("".join(ch for ch in rg if ch.isdigit()) or "1"),
        "path": str(path),
        "mime_type": "image/png",
        "source": "teste_sintetico",
    }


def test_supported_image_detection() -> None:
    assert is_supported_visual_file("foto.png")
    assert is_supported_visual_file("sem_extensao", "image/jpeg")
    assert not is_supported_visual_file("documento.pdf", "application/pdf")


def test_bad_image_is_rejected() -> None:
    try:
        extract_visual_features_from_bytes(b"nao e imagem")
    except VisualSearchError:
        return
    raise AssertionError("imagem inválida deveria ser recusada")


def test_tiny_image_is_rejected() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), (100, 100, 100)).save(buffer, format="PNG")
    try:
        extract_visual_features_from_bytes(buffer.getvalue())
    except VisualSearchError as erro:
        assert "pequena" in str(erro)
        return
    raise AssertionError("imagem pequena deveria ser recusada")


def test_full_visual_search_finds_same_character_style() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        alvo = root / "alvo.png"
        outro = root / "outro.png"
        _save(alvo, _character_image(shirt=(190, 25, 25), pants=(20, 20, 80), hat=(10, 10, 10), backpack=(70, 40, 20)))
        _save(outro, _character_image(shirt=(20, 160, 90), pants=(130, 130, 20), skin=(150, 105, 80)))
        index = VisualSearchIndex(root / "visual")
        stats = index.build_or_update([
            _record(alvo, "101", "Alvo Vermelho", "individuo:101:foto1"),
            _record(outro, "202", "Outro Verde", "individuo:202:foto1"),
        ], prune=True)
        assert stats["indexed_images"] == 2
        result = index.search_bytes(_character_image(shirt=(185, 30, 30), pants=(25, 25, 85), hat=(10, 10, 10), backpack=(74, 45, 24)), mode="full")
        assert result["results"]
        assert result["results"][0]["rg"] == "101"
        assert result["results"][0]["score"] >= 70


def test_clothing_mode_works_when_face_is_hidden() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        azul = root / "azul.png"
        amarelo = root / "amarelo.png"
        _save(azul, _character_image(shirt=(20, 60, 210), pants=(18, 18, 70), skin=(225, 175, 135)))
        _save(amarelo, _character_image(shirt=(220, 190, 30), pants=(80, 60, 20), skin=(120, 80, 60)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([
            _record(azul, "303", "Roupa Azul", "individuo:303:foto1"),
            _record(amarelo, "404", "Roupa Amarela", "individuo:404:foto1"),
        ], prune=True)
        result = index.search_bytes(_character_image(shirt=(25, 65, 205), pants=(20, 20, 70), skin=(70, 70, 70), face_hidden=True), mode="roupa")
        assert result["mode"] == "clothing"
        assert result["results"][0]["rg"] == "303"
        assert result["results"][0]["clothing_score"] >= result["results"][0]["appearance_score"]


def test_accessories_contribute_without_claiming_identity() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        mochila = root / "mochila.png"
        sem_mochila = root / "sem_mochila.png"
        _save(mochila, _character_image(shirt=(80, 80, 80), backpack=(10, 90, 160), hat=(15, 15, 15)))
        _save(sem_mochila, _character_image(shirt=(80, 80, 80), backpack=None, hat=None))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([
            _record(mochila, "505", "Com Mochila", "individuo:505:foto1"),
            _record(sem_mochila, "606", "Sem Mochila", "individuo:606:foto1"),
        ], prune=True)
        result = index.search_bytes(_character_image(shirt=(82, 82, 82), backpack=(10, 90, 160), hat=(15, 15, 15)), mode="full")
        assert result["results"][0]["rg"] == "505"
        assert all("mesma pessoa" not in " ".join(r["explanations"]).lower() for r in result["results"])


def test_grouping_by_rg_avoids_duplicate_results() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        p1 = root / "p1.png"
        p2 = root / "p2.png"
        p3 = root / "p3.png"
        _save(p1, _character_image(shirt=(160, 30, 160), offset=-4))
        _save(p2, _character_image(shirt=(162, 28, 158), offset=3))
        _save(p3, _character_image(shirt=(10, 180, 180)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([
            _record(p1, "707", "Duas Fotos", "arquivo:1"),
            _record(p2, "707", "Duas Fotos", "arquivo:2"),
            _record(p3, "808", "Outra Ficha", "arquivo:3"),
        ], prune=True)
        result = index.search_bytes(_character_image(shirt=(161, 29, 161)), mode="full")
        rgs = [item["rg"] for item in result["results"]]
        assert rgs.count("707") == 1
        assert result["results"][0]["matches_count"] == 2


def test_empty_index_returns_controlled_message() -> None:
    with tempfile.TemporaryDirectory() as temp:
        result = VisualSearchIndex(Path(temp) / "visual").search_bytes(_character_image(shirt=(10, 20, 30)), mode="full")
        assert result["results"] == []
        assert "vazio" in result["reason"]


def test_index_persists_after_reload() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        foto = root / "persist.png"
        _save(foto, _character_image(shirt=(30, 120, 220)))
        first = VisualSearchIndex(root / "visual")
        first.build_or_update([_record(foto, "909", "Persistente", "individuo:909:foto1")], prune=True)
        second = VisualSearchIndex(root / "visual")
        result = second.search_bytes(_character_image(shirt=(31, 119, 218)), mode="full")
        assert result["results"][0]["rg"] == "909"


def test_incremental_add_update_and_prune() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        a = root / "a.png"
        b = root / "b.png"
        _save(a, _character_image(shirt=(200, 20, 20)))
        _save(b, _character_image(shirt=(20, 200, 20)))
        index = VisualSearchIndex(root / "visual")
        first = index.build_or_update([_record(a, "111", "A", "a")], prune=True)
        assert first["added"] == 1
        second = index.build_or_update([_record(a, "111", "A", "a"), _record(b, "222", "B", "b")], prune=False)
        assert second["added"] == 1
        _save(a, _character_image(shirt=(25, 25, 220)))
        third = index.build_or_update([_record(a, "111", "A", "a"), _record(b, "222", "B", "b")], prune=False)
        assert third["updated"] == 1
        fourth = index.build_or_update([_record(a, "111", "A", "a")], prune=True)
        assert fourth["indexed_images"] == 1


def test_top_results_are_limited_to_five() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        records = []
        for idx in range(8):
            path = root / f"{idx}.png"
            _save(path, _character_image(shirt=(120 + idx, 40, 40)))
            records.append(_record(path, str(1000 + idx), f"Pessoa {idx}", f"img:{idx}"))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update(records, prune=True)
        result = index.search_bytes(_character_image(shirt=(123, 40, 40)), mode="full", threshold=0)
        assert len(result["results"]) == 5


def test_no_match_below_threshold() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "escuro.png"
        _save(path, _character_image(shirt=(5, 5, 5), pants=(5, 5, 5), skin=(15, 15, 15)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([_record(path, "333", "Escuro", "escuro")], prune=True)
        result = index.search_bytes(_character_image(shirt=(240, 240, 240), pants=(220, 220, 220), skin=(225, 225, 225)), mode="full", threshold=95)
        assert result["results"] == []


def test_rebuild_permission_helper() -> None:
    assert can_rebuild_visual_index(is_inspector_plus=True, is_admin=False)
    assert can_rebuild_visual_index(is_inspector_plus=False, is_admin=True)
    assert not can_rebuild_visual_index(is_inspector_plus=False, is_admin=False)


def test_removed_image_id_does_not_remain_searchable() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "remove.png"
        _save(path, _character_image(shirt=(200, 100, 20)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([_record(path, "444", "Remover", "remover")], prune=True)
        removed = index.remove_image_ids(["remover"])
        assert removed["removed"] == 1
        result = index.search_bytes(_character_image(shirt=(200, 100, 20)), mode="full")
        assert result["results"] == []


def test_two_similar_records_are_ranked_safely() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        p1 = root / "p1.png"
        p2 = root / "p2.png"
        _save(p1, _character_image(shirt=(90, 90, 210), pants=(30, 30, 80)))
        _save(p2, _character_image(shirt=(95, 95, 205), pants=(40, 40, 75), hat=(120, 120, 120)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([
            _record(p1, "555", "Similar 1", "s1"),
            _record(p2, "556", "Similar 2", "s2"),
        ], prune=True)
        result = index.search_bytes(_character_image(shirt=(92, 92, 208), pants=(32, 32, 82)), mode="full", threshold=50)
        assert 1 <= len(result["results"]) <= 2
        assert all("definitiv" not in " ".join(r["explanations"]).lower() for r in result["results"])


def test_query_with_clothes_only_prefers_clothing_match() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        roupa = root / "roupa.png"
        face = root / "face.png"
        _save(roupa, _character_image(shirt=(10, 120, 200), skin=(220, 180, 140)))
        _save(face, _character_image(shirt=(200, 20, 20), skin=(220, 180, 140)))
        index = VisualSearchIndex(root / "visual")
        index.build_or_update([
            _record(roupa, "777", "Roupa", "roupa"),
            _record(face, "778", "Face", "face"),
        ], prune=True)
        result = index.search_bytes(_character_image(shirt=(12, 118, 198), skin=(80, 80, 80), face_hidden=True), mode="roupa")
        assert result["results"][0]["rg"] == "777"


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
    print("visual_search synthetic tests passed")
