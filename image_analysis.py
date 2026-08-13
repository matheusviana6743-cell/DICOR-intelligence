from __future__ import annotations

import hashlib
import io
import logging
import math
import os
import re
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError


LOGGER = logging.getLogger("dicor.image_analysis")

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
SUPPORTED_IMAGE_MIME_PREFIX = "image/"
OCR_MAX_PIXELS = max(1_000_000, int(os.getenv("DICOR_OCR_MAX_PIXELS", "9000000")))
OCR_VARIANT_LIMIT = max(1, min(8, int(os.getenv("DICOR_OCR_VARIANT_LIMIT", "6"))))

_ENGINE_LOCK = threading.Lock()
_ENGINE: Any = None
_ENGINE_STATUS: Optional["OcrHealth"] = None


class OcrEngineUnavailable(RuntimeError):
    """Falha técnica do backend OCR, distinta de imagem ruim."""


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    fmt: str
    mode: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float = 0.0
    box: Tuple[Tuple[float, float], ...] = field(default_factory=tuple)
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    cx: float = 0.0
    cy: float = 0.0
    height: float = 1.0


@dataclass(frozen=True)
class OcrResult:
    lines: Tuple[OcrLine, ...]
    text: str
    image_info: ImageInfo
    preprocessing: str
    elapsed_ms: int
    engine: str
    backend: str
    chars: int


@dataclass(frozen=True)
class OcrHealth:
    ready: bool
    engine: str
    backend: str
    onnx_available: bool
    error: str = ""
    versions: Dict[str, str] = field(default_factory=dict)
    chars: int = 0
    records: int = 0
    elapsed_ms: int = 0


@dataclass(frozen=True)
class PanelRecord:
    cargo: str = ""
    nome: str = ""
    passaporte: str = ""
    source: str = ""
    score: float = 0.0

    def as_dict(self) -> Dict[str, str]:
        return {
            "cargo": self.cargo,
            "nome": self.nome,
            "passaporte": self.passaporte,
            "rg": self.passaporte,
        }


@dataclass(frozen=True)
class DatabaseRecord:
    rg: str = ""
    nome: str = ""
    cargo: str = ""
    telefone: str = ""
    status: str = "ignored"
    reason: str = ""
    source: str = ""

    def as_member_dict(self) -> Dict[str, str]:
        return {
            "rg": self.rg,
            "nome": self.nome,
            "cargo": self.cargo or "MEMBRO",
            "telefone": self.telefone,
        }


@dataclass(frozen=True)
class StructuredAnalysis:
    ocr: OcrResult
    records: Tuple[Dict[str, str], ...]
    doubtful: Tuple[Dict[str, str], ...]
    ignored: Tuple[str, ...]
    log: Dict[str, Any]


def _compact_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _module_version(name: str) -> str:
    try:
        module = __import__(name)
        return str(getattr(module, "__version__", "") or "unknown")
    except Exception as exc:
        return f"unavailable ({_compact_error(exc)})"


def _load_engine() -> Any:
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            return _ENGINE
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:
            raise OcrEngineUnavailable(
                "OCR_ENGINE_UNAVAILABLE: rapidocr_onnxruntime não está instalado ou não pôde ser importado. "
                f"{_compact_error(exc)}"
            ) from exc
        try:
            _ENGINE = RapidOCR()
        except Exception as exc:
            raise OcrEngineUnavailable(
                "OCR_ENGINE_UNAVAILABLE: rapidocr_onnxruntime falhou ao inicializar. "
                f"{_compact_error(exc)}"
            ) from exc
        return _ENGINE


def load_image_bytes(data: bytes, *, filename: str = "", content_type: str = "") -> Tuple[Image.Image, ImageInfo]:
    if not isinstance(data, (bytes, bytearray)) or len(data) < 16:
        raise ValueError("Imagem vazia ou bytes insuficientes.")
    ext = Path(str(filename or "")).suffix.lower()
    mime = str(content_type or "").lower()
    if ext and ext not in SUPPORTED_IMAGE_EXTENSIONS and not mime.startswith(SUPPORTED_IMAGE_MIME_PREFIX):
        raise ValueError(f"Extensão de imagem não suportada: {ext}")
    if mime and not mime.startswith(SUPPORTED_IMAGE_MIME_PREFIX) and ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Content-Type não suportado para imagem: {mime}")
    sha = hashlib.sha256(bytes(data)).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as opened:
            fmt = str(opened.format or ext.lstrip(".") or "unknown").upper()
            normalized = ImageOps.exif_transpose(opened)
            if normalized.mode not in {"RGB", "RGBA", "L"}:
                normalized = normalized.convert("RGB")
            elif normalized.mode == "RGBA":
                background = Image.new("RGB", normalized.size, (255, 255, 255))
                background.paste(normalized, mask=normalized.getchannel("A"))
                normalized = background
            else:
                normalized = normalized.convert("RGB")
            width, height = normalized.size
            if width <= 0 or height <= 0:
                raise ValueError("Imagem sem dimensões válidas.")
            if width * height > OCR_MAX_PIXELS:
                scale = math.sqrt(OCR_MAX_PIXELS / float(width * height))
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                normalized = normalized.resize(new_size, Image.Resampling.LANCZOS)
                width, height = normalized.size
            return normalized.copy(), ImageInfo(width, height, fmt, "RGB", len(data), sha)
    except UnidentifiedImageError as exc:
        raise ValueError("Arquivo não é uma imagem reconhecível.") from exc


def _image_brightness(img: Image.Image) -> float:
    gray = ImageOps.grayscale(img)
    return float(ImageStat.Stat(gray).mean[0])


def _upscale_size(width: int, height: int, target_long: int = 2100) -> Tuple[int, int]:
    longest = max(1, max(width, height))
    scale = min(3.0, max(1.0, target_long / float(longest)))
    return max(1, int(width * scale)), max(1, int(height * scale))


def generate_preprocess_variants(img: Image.Image) -> List[Tuple[str, Image.Image]]:
    base = img.convert("RGB")
    width, height = base.size
    up_size = _upscale_size(width, height)
    upscaled = base.resize(up_size, Image.Resampling.LANCZOS) if up_size != base.size else base.copy()
    variants: List[Tuple[str, Image.Image]] = [("original-rgb", base.copy()), ("upscale-rgb", upscaled.copy())]

    gray = ImageOps.grayscale(upscaled)
    gray = ImageOps.autocontrast(gray)
    variants.append(("gray-autocontrast", gray.convert("RGB")))

    contrast = ImageEnhance.Contrast(gray).enhance(1.75)
    sharp = ImageEnhance.Sharpness(contrast).enhance(1.45).filter(ImageFilter.SHARPEN)
    variants.append(("gray-contrast-sharp", sharp.convert("RGB")))

    brightness = _image_brightness(base)
    if brightness < 120:
        inverted = ImageOps.invert(gray)
        inverted = ImageEnhance.Contrast(inverted).enhance(1.6).filter(ImageFilter.SHARPEN)
        variants.append(("dark-inverted-contrast", inverted.convert("RGB")))

    threshold_source = sharp
    mean = int(max(60, min(205, ImageStat.Stat(threshold_source).mean[0])))
    threshold = threshold_source.point(lambda p: 255 if p > mean - 8 else 0)
    variants.append(("adaptive-threshold", threshold.convert("RGB")))

    unique: List[Tuple[str, Image.Image]] = []
    seen: set[str] = set()
    for name, variant in variants:
        thumb = variant.copy()
        thumb.thumbnail((96, 96))
        digest = hashlib.sha1(thumb.tobytes()).hexdigest()
        if digest in seen:
            variant.close()
            continue
        seen.add(digest)
        unique.append((name, variant))
        if len(unique) >= OCR_VARIANT_LIMIT:
            break
    return unique


def _box_limits(box: Any) -> Tuple[Tuple[Tuple[float, float], ...], float, float, float, float]:
    points: List[Tuple[float, float]] = []
    try:
        for point in box or []:
            if hasattr(point, "tolist"):
                point = point.tolist()
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
    except Exception:
        points = []
    if not points:
        return tuple(), 0.0, 0.0, 0.0, 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return tuple(points), min(xs), min(ys), max(xs), max(ys)


def _extract_ocr_lines(raw_result: Any) -> List[OcrLine]:
    raw_items: Any = raw_result
    if hasattr(raw_result, "txts"):
        texts = list(getattr(raw_result, "txts") or [])
        scores = list(getattr(raw_result, "scores") or [])
        boxes = list(getattr(raw_result, "boxes") or [])
        items: List[Tuple[Any, str, Any]] = []
        for idx, text in enumerate(texts):
            items.append((boxes[idx] if idx < len(boxes) else [], str(text or ""), scores[idx] if idx < len(scores) else 0.5))
    else:
        if isinstance(raw_result, tuple) and raw_result:
            raw_items = raw_result[0]
        items = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                box = item[0]
                text = ""
                score: Any = 0.5
                if len(item) >= 3 and isinstance(item[1], str):
                    text = item[1]
                    score = item[2]
                elif isinstance(item[1], (list, tuple)) and item[1]:
                    text = str(item[1][0] or "")
                    score = item[1][1] if len(item[1]) > 1 else 0.5
                items.append((box, text, score))

    lines: List[OcrLine] = []
    for box, text, score in items:
        clean = re.sub(r"\s+", " ", str(text or "")).strip()
        if not clean:
            continue
        try:
            numeric_score = float(score)
        except Exception:
            numeric_score = 0.5
        points, x1, y1, x2, y2 = _box_limits(box)
        lines.append(
            OcrLine(
                text=clean,
                score=max(0.0, min(1.0, numeric_score)),
                box=points,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                cx=(x1 + x2) / 2.0,
                cy=(y1 + y2) / 2.0,
                height=max(1.0, y2 - y1),
            )
        )
    lines.sort(key=lambda line: (line.cy, line.x1, line.text))
    return lines


def _variant_score(lines: Sequence[OcrLine], context: str) -> float:
    text = "\n".join(line.text for line in lines)
    norm = normalize_text(text)
    label_hits = 0
    if context == "panel":
        for key in ("cargo", "nome", "passaporte"):
            if key in norm:
                label_hits += 5
        label_hits += len(re.findall(r"\b\d{3,8}\b", text))
    elif context == "database":
        for key in ("rg", "nome", "cargo", "telefone"):
            if re.search(rf"\b{key}\b", norm):
                label_hits += 5
        label_hits += len(re.findall(r"\b\d{3,8}\b", text))
    avg_score = sum(line.score for line in lines) / max(1, len(lines))
    return len(text) * 0.4 + label_hits * 12 + avg_score * 25 + len(lines)


def _run_engine_on_image(engine: Any, img: Image.Image) -> List[OcrLine]:
    with tempfile.NamedTemporaryFile(prefix="dicor-ocr-", suffix=".png", delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        img.save(temp_path, "PNG", optimize=True)
        try:
            result = engine(str(temp_path), use_det=True, use_cls=True, use_rec=True)
        except TypeError:
            result = engine(str(temp_path))
        return _extract_ocr_lines(result)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def run_ocr(data: bytes, *, filename: str = "", content_type: str = "", context: str = "generic") -> OcrResult:
    started = time.perf_counter()
    engine = _load_engine()
    img, info = load_image_bytes(data, filename=filename, content_type=content_type)
    best_name = ""
    best_lines: List[OcrLine] = []
    best_score = -1.0
    variants = generate_preprocess_variants(img)
    try:
        for name, variant in variants:
            try:
                lines = _run_engine_on_image(engine, variant)
                score = _variant_score(lines, context)
                if score > best_score:
                    best_score = score
                    best_name = name
                    best_lines = lines
            except Exception as exc:
                LOGGER.warning("OCR variant failed: %s sha=%s variant=%s", _compact_error(exc), info.sha256[:12], name)
    finally:
        for _, variant in variants:
            try:
                variant.close()
            except Exception:
                pass
        try:
            img.close()
        except Exception:
            pass

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    text = "\n".join(line.text for line in best_lines)
    LOGGER.info(
        "OCR analysis module=%s bytes=%s sha=%s format=%s resolution=%sx%s preprocessing=%s chars=%s lines=%s elapsed_ms=%s",
        context,
        info.byte_count,
        info.sha256[:12],
        info.fmt,
        info.width,
        info.height,
        best_name,
        len(text),
        len(best_lines),
        elapsed_ms,
    )
    return OcrResult(
        lines=tuple(best_lines),
        text=text,
        image_info=info,
        preprocessing=best_name,
        elapsed_ms=elapsed_ms,
        engine="rapidocr_onnxruntime",
        backend="onnxruntime-cpu",
        chars=len(text),
    )


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("0", "o").replace("6", "g")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _clean_value(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n:-|;,.")
    return text[:limit].strip()


def normalize_rg(value: Any) -> str:
    raw = str(value or "").upper()
    raw = raw.replace("O", "0").replace("I", "1").replace("L", "1").replace("S", "5")
    digits = re.sub(r"\D", "", raw)
    if 2 <= len(digits) <= 10:
        return digits
    return ""


def normalize_phone(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(?<!\d)(?:\(?\s*0?\d{2,3}\s*\)?\s*)?\d{3,5}\s*[-–— ]\s*\d{3,5}(?!\d)", text)
    if not match:
        return ""
    raw = match.group(0).strip()
    raw = re.sub(r"\s+", " ", raw)
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 6 or len(digits) > 12:
        return ""
    if "-" not in raw and len(digits) >= 7:
        return f"{digits[:-4]}-{digits[-4:]}"
    return raw


def _label_kind(text: str) -> str:
    norm = normalize_text(text)
    if re.search(r"\b(car(?:g|go|6o)|carg0|funcao|hierarquia)\b", norm):
        return "cargo"
    if re.search(r"\b(nom(?:e|c)|n0me|norne|pessoa|membro)\b", norm):
        return "nome"
    if re.search(r"\b(passaporte|passap(?:o|0)rte|rg|registro|documento|identidade)\b", norm):
        return "passaporte"
    return ""


def _strip_label(text: str, kind: str) -> str:
    if not kind:
        return _clean_value(text)
    patterns = {
        "cargo": r"(?i)\b(?:cargo|car60|carg0|funcao|função|hierarquia)\b\s*[:#=\-–—]?\s*",
        "nome": r"(?i)\b(?:nome|n0me|norne|pessoa|membro)\b\s*[:#=\-–—]?\s*",
        "passaporte": r"(?i)\b(?:passaporte|passap0rte|rg|registro|documento|identidade)\b\s*[:#=\-–—]?\s*",
    }
    return _clean_value(re.sub(patterns[kind], "", text, count=1))


def _line_columns(lines: Sequence[OcrLine], width: float) -> List[List[OcrLine]]:
    valid = [line for line in lines if line.text.strip()]
    if not valid:
        return []
    if width <= 0:
        width = max((line.x2 for line in valid), default=1.0)
    centers = sorted(line.cx for line in valid if line.cx > 0)
    if len(centers) < 6:
        return [sorted(valid, key=lambda line: (line.cy, line.x1))]
    gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
    gap, idx = max(gaps, default=(0.0, 0))
    if gap < max(120.0, width * 0.18):
        return [sorted(valid, key=lambda line: (line.cy, line.x1))]
    split = (centers[idx] + centers[idx + 1]) / 2.0
    left = [line for line in valid if line.cx <= split]
    right = [line for line in valid if line.cx > split]
    if len(left) < 3 or len(right) < 3:
        return [sorted(valid, key=lambda line: (line.cy, line.x1))]
    return [sorted(left, key=lambda line: (line.cy, line.x1)), sorted(right, key=lambda line: (line.cy, line.x1))]


def parse_panel_people(lines_or_text: Sequence[OcrLine] | str, *, image_width: float = 0.0) -> Tuple[List[PanelRecord], List[str]]:
    if isinstance(lines_or_text, str):
        raw_lines = [
            OcrLine(text=line.strip(), y1=float(idx * 20), y2=float(idx * 20 + 12), cy=float(idx * 20 + 6), height=12.0)
            for idx, line in enumerate(lines_or_text.splitlines())
            if line.strip()
        ]
    else:
        raw_lines = list(lines_or_text)
    columns = _line_columns(raw_lines, image_width)
    records: List[PanelRecord] = []
    ignored: List[str] = []

    def flush(current: Dict[str, str], source_parts: List[str]) -> None:
        cargo = _clean_value(current.get("cargo"), 80)
        nome = _clean_value(current.get("nome"), 120)
        passaporte = normalize_rg(current.get("passaporte"))
        source = " | ".join(source_parts)
        if nome and passaporte:
            records.append(PanelRecord(cargo=cargo or "MEMBRO", nome=nome, passaporte=passaporte, source=source, score=0.85))
        elif source.strip():
            ignored.append(source)

    for column in columns:
        current: Dict[str, str] = {}
        source_parts: List[str] = []
        for line in column:
            text = _clean_value(line.text, 240)
            if not text:
                continue
            kind = _label_kind(text)
            inline_labels = re.findall(r"(?i)(cargo|car60|carg0|nome|n0me|norne|passaporte|passap0rte|rg|registro)\s*[:#=\-–—]?\s*([^:|]+?)(?=(?:\s+(?:cargo|car60|carg0|nome|n0me|norne|passaporte|passap0rte|rg|registro)\s*[:#=\-–—])|$)", text)
            if inline_labels and len(inline_labels) >= 2:
                if current and current.get("nome") and current.get("passaporte"):
                    flush(current, source_parts)
                    current, source_parts = {}, []
                for label, value in inline_labels:
                    k = _label_kind(label)
                    if k:
                        current[k] = _strip_label(f"{label}: {value}", k)
                source_parts.append(text)
                continue
            if kind:
                if kind == "cargo" and current and current.get("nome") and current.get("passaporte"):
                    flush(current, source_parts)
                    current, source_parts = {}, []
                current[kind] = _strip_label(text, kind)
                source_parts.append(text)
                continue
            if current:
                missing = next((key for key in ("cargo", "nome", "passaporte") if not current.get(key)), "")
                if missing:
                    current[missing] = text
                    source_parts.append(text)
                else:
                    flush(current, source_parts)
                    current, source_parts = {}, []
        if current or source_parts:
            flush(current, source_parts)

    deduped: List[PanelRecord] = []
    seen: set[str] = set()
    for record in records:
        key = record.passaporte or normalize_text(record.nome)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped, ignored


def _row_groups(lines: Sequence[OcrLine]) -> List[List[OcrLine]]:
    valid = [line for line in lines if line.text.strip()]
    if not valid:
        return []
    heights = sorted(max(1.0, line.height) for line in valid)
    median_h = heights[len(heights) // 2]
    tolerance = max(10.0, median_h * 0.8)
    rows: List[List[OcrLine]] = []
    for line in sorted(valid, key=lambda item: (item.cy, item.x1)):
        target: Optional[List[OcrLine]] = None
        best_distance = 1_000_000.0
        for row in rows[-5:]:
            cy = sum(item.cy for item in row) / max(1, len(row))
            distance = abs(line.cy - cy)
            if distance <= tolerance and distance < best_distance:
                target = row
                best_distance = distance
        if target is None:
            rows.append([line])
        else:
            target.append(line)
    for row in rows:
        row.sort(key=lambda item: item.x1)
    return rows


def _header_positions(rows: Sequence[Sequence[OcrLine]], width: float) -> Dict[str, float]:
    headers: Dict[str, float] = {}
    for row in rows[:8]:
        for line in row:
            norm = normalize_text(line.text)
            if re.fullmatch(r"rg|id|registro", norm):
                headers["rg"] = line.cx
            elif "nome" == norm or norm.startswith("nome "):
                headers["nome"] = line.cx
            elif "cargo" in norm or "funcao" in norm:
                headers["cargo"] = line.cx
            elif "telefone" in norm or "fone" in norm or "tel" == norm:
                headers["telefone"] = line.cx
        if len(headers) >= 3:
            break
    if len(headers) >= 3:
        return headers
    width = width or max((line.x2 for row in rows for line in row), default=1000.0)
    return {
        "rg": width * 0.08,
        "nome": width * 0.34,
        "cargo": width * 0.62,
        "telefone": width * 0.84,
    }


def _parse_table_text_line(text: str) -> Optional[DatabaseRecord]:
    raw = _clean_value(text, 260)
    if not raw:
        return None
    if normalize_text(raw) in {"rg nome cargo telefone", "rg nome cargo telefone celular"}:
        return None
    parts = [part.strip() for part in re.split(r"\s*\|\s*|\t+| {2,}", raw) if part.strip()]
    if len(parts) >= 4:
        rg, nome, cargo, telefone = parts[0], parts[1], parts[2], " ".join(parts[3:])
        rg_norm = normalize_rg(rg)
        phone_norm = normalize_phone(telefone)
        if rg_norm and nome:
            status = "valid" if phone_norm or telefone else "doubtful"
            return DatabaseRecord(rg=rg_norm, nome=_clean_value(nome, 120), cargo=_clean_value(cargo, 80) or "MEMBRO", telefone=phone_norm, status=status, source=raw)
    match = re.match(r"^\s*#?\s*([A-Za-z0-9.-]{2,12})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' .-]{2,90}?)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' .-]{2,50}?)(?:\s+((?:\(?\d{2,3}\)?\s*)?\d{3,5}[-–— ]\d{3,5}))?\s*$", raw)
    if match:
        rg_norm = normalize_rg(match.group(1))
        if rg_norm:
            phone_norm = normalize_phone(match.group(4) or "")
            return DatabaseRecord(
                rg=rg_norm,
                nome=_clean_value(match.group(2), 120),
                cargo=_clean_value(match.group(3), 80) or "MEMBRO",
                telefone=phone_norm,
                status="valid" if phone_norm or not match.group(4) else "doubtful",
                source=raw,
            )
    return None


def parse_database_table(lines_or_text: Sequence[OcrLine] | str, *, image_width: float = 0.0) -> Tuple[List[DatabaseRecord], List[DatabaseRecord], List[str]]:
    if isinstance(lines_or_text, str):
        lines = [
            OcrLine(text=line.strip(), x1=0.0, x2=float(len(line) * 8), cx=float(len(line) * 4), y1=float(idx * 20), y2=float(idx * 20 + 12), cy=float(idx * 20 + 6), height=12.0)
            for idx, line in enumerate(lines_or_text.splitlines())
            if line.strip()
        ]
    else:
        lines = list(lines_or_text)

    rows = _row_groups(lines)
    headers = _header_positions(rows, image_width)
    header_y = 0.0
    for row in rows[:8]:
        joined = normalize_text(" ".join(line.text for line in row))
        if "rg" in joined and "nome" in joined:
            header_y = max((line.cy for line in row), default=0.0)
            break

    valid: List[DatabaseRecord] = []
    doubtful: List[DatabaseRecord] = []
    ignored: List[str] = []
    header_order = sorted(headers.items(), key=lambda item: item[1])

    for row in rows:
        row_text = " | ".join(line.text for line in row)
        row_norm = normalize_text(row_text)
        if not row_text.strip() or ("rg" in row_norm and "nome" in row_norm and "cargo" in row_norm):
            continue
        if header_y and max((line.cy for line in row), default=0.0) <= header_y + 4:
            continue

        fallback = _parse_table_text_line(row_text)
        if fallback and fallback.status == "valid":
            valid.append(fallback)
            continue

        cells: Dict[str, List[str]] = {"rg": [], "nome": [], "cargo": [], "telefone": []}
        for line in row:
            if not header_order:
                continue
            nearest = min(header_order, key=lambda item: abs(line.cx - item[1]))[0]
            cells.setdefault(nearest, []).append(line.text)
        rg = normalize_rg(" ".join(cells.get("rg") or []))
        nome = _clean_value(" ".join(cells.get("nome") or []), 120)
        cargo = _clean_value(" ".join(cells.get("cargo") or []), 80) or "MEMBRO"
        telefone = normalize_phone(" ".join(cells.get("telefone") or []))
        if not rg and fallback:
            rg, nome, cargo, telefone = fallback.rg, fallback.nome, fallback.cargo, fallback.telefone
        if rg and nome and sum(ch.isalpha() for ch in nome) >= 3:
            record = DatabaseRecord(rg=rg, nome=nome, cargo=cargo, telefone=telefone, status="valid" if telefone or len(row) >= 3 else "doubtful", source=row_text)
            if record.status == "valid":
                valid.append(record)
            else:
                doubtful.append(record)
        elif nome or rg:
            doubtful.append(DatabaseRecord(rg=rg, nome=nome, cargo=cargo, telefone=telefone, status="doubtful", reason="linha incompleta", source=row_text))
        else:
            ignored.append(row_text)

    deduped_valid: List[DatabaseRecord] = []
    deduped_doubtful: List[DatabaseRecord] = []
    seen: set[str] = set()
    for record in valid:
        key = record.rg or normalize_text(record.nome)
        if key and key not in seen:
            seen.add(key)
            deduped_valid.append(record)
    for record in doubtful:
        key = record.rg or normalize_text(record.nome + record.telefone)
        if key and key not in seen:
            seen.add(key)
            deduped_doubtful.append(record)
    return deduped_valid, deduped_doubtful, ignored


def analyze_panel_image(data: bytes, *, filename: str = "", content_type: str = "") -> StructuredAnalysis:
    ocr = run_ocr(data, filename=filename, content_type=content_type, context="panel")
    records, ignored = parse_panel_people(ocr.lines, image_width=ocr.image_info.width)
    log = {
        "module": "panel",
        "resolution": f"{ocr.image_info.width}x{ocr.image_info.height}",
        "format": ocr.image_info.fmt,
        "bytes": ocr.image_info.byte_count,
        "preprocessing": ocr.preprocessing,
        "chars": ocr.chars,
        "records": len(records),
        "ignored": len(ignored),
        "elapsed_ms": ocr.elapsed_ms,
    }
    LOGGER.info("Panel OCR records=%s ignored=%s sha=%s", len(records), len(ignored), ocr.image_info.sha256[:12])
    return StructuredAnalysis(ocr=ocr, records=tuple(record.as_dict() for record in records), doubtful=tuple(), ignored=tuple(ignored), log=log)


def analyze_database_image(data: bytes, *, filename: str = "", content_type: str = "") -> StructuredAnalysis:
    ocr = run_ocr(data, filename=filename, content_type=content_type, context="database")
    valid, doubtful, ignored = parse_database_table(ocr.lines, image_width=ocr.image_info.width)
    log = {
        "module": "database",
        "resolution": f"{ocr.image_info.width}x{ocr.image_info.height}",
        "format": ocr.image_info.fmt,
        "bytes": ocr.image_info.byte_count,
        "preprocessing": ocr.preprocessing,
        "chars": ocr.chars,
        "valid": len(valid),
        "doubtful": len(doubtful),
        "ignored": len(ignored),
        "elapsed_ms": ocr.elapsed_ms,
    }
    LOGGER.info("Database OCR valid=%s doubtful=%s ignored=%s sha=%s", len(valid), len(doubtful), len(ignored), ocr.image_info.sha256[:12])
    return StructuredAnalysis(
        ocr=ocr,
        records=tuple(record.as_member_dict() for record in valid),
        doubtful=tuple(record.as_member_dict() for record in doubtful),
        ignored=tuple(ignored),
        log=log,
    )


def dedupe_records(records: Iterable[Dict[str, str]], key_fields: Sequence[str]) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        key = ""
        for field_name in key_fields:
            value = str(record.get(field_name) or "").strip()
            if value:
                key = f"{field_name}:{normalize_rg(value) if field_name in {'rg', 'passaporte'} else normalize_text(value)}"
                break
        if not key:
            key = "record:" + normalize_text("|".join(str(record.get(k) or "") for k in sorted(record)))
        if key in seen:
            continue
        seen.add(key)
        output.append(dict(record))
    return output


def build_panel_transcription(records: Sequence[Dict[str, str]]) -> str:
    lines = ["PAINEL TRANSCRITO"]
    for idx, record in enumerate(records, 1):
        cargo = _clean_value(record.get("cargo"), 80) or "MEMBRO"
        nome = _clean_value(record.get("nome"), 120)
        passaporte = normalize_rg(record.get("passaporte") or record.get("rg"))
        lines.extend(["", f"{idx}.", f"Cargo: {cargo}", f"Nome: {nome}", f"Passaporte: {passaporte}"])
    return "\n".join(lines).strip()


def create_synthetic_panel_image() -> bytes:
    img = Image.new("RGB", (980, 310), (12, 14, 16))
    draw = ImageDrawShim(img)
    draw.text((40, 34), "Cargo: GERENTE", fill=(245, 245, 245), size=38)
    draw.text((40, 102), "Nome: TESTE SILVA", fill=(245, 245, 245), size=38)
    draw.text((40, 170), "Passaporte: 12345", fill=(245, 245, 245), size=38)
    output = io.BytesIO()
    img.save(output, "PNG")
    return output.getvalue()


def create_synthetic_database_image() -> bytes:
    img = Image.new("RGB", (1220, 320), (245, 245, 242))
    draw = ImageDrawShim(img)
    xs = [45, 265, 665, 920]
    headers = ["RG", "NOME", "CARGO", "TELEFONE"]
    for x, header in zip(xs, headers):
        draw.text((x, 35), header, fill=(18, 18, 18), size=34)
    rows = [
        ("12345", "TESTE SILVA", "GERENTE", "555-0100"),
        ("54321", "TESTE SOUZA", "MEMBRO", "555-0200"),
    ]
    y = 105
    for row in rows:
        for x, value in zip(xs, row):
            draw.text((x, y), value, fill=(20, 20, 20), size=32)
        y += 78
    output = io.BytesIO()
    img.save(output, "PNG")
    return output.getvalue()


class ImageDrawShim:
    def __init__(self, image: Image.Image):
        from PIL import ImageDraw, ImageFont

        self.draw = ImageDraw.Draw(image)
        self.ImageFont = ImageFont

    def _font(self, size: int):
        candidates = [
            "arial.ttf",
            "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for candidate in candidates:
            try:
                return self.ImageFont.truetype(candidate, size)
            except Exception:
                continue
        return self.ImageFont.load_default()

    def text(self, xy: Tuple[int, int], value: str, *, fill: Tuple[int, int, int], size: int) -> None:
        self.draw.text(xy, value, fill=fill, font=self._font(size))


def health_check() -> OcrHealth:
    global _ENGINE_STATUS
    started = time.perf_counter()
    versions = {
        "rapidocr_onnxruntime": _module_version("rapidocr_onnxruntime"),
        "onnxruntime": _module_version("onnxruntime"),
        "opencv": _module_version("cv2"),
        "pillow": _module_version("PIL"),
        "numpy": _module_version("numpy"),
    }
    try:
        result = analyze_panel_image(create_synthetic_panel_image(), filename="health-panel.png", content_type="image/png")
        records = list(result.records)
        ready = bool(records and records[0].get("nome") == "TESTE SILVA" and records[0].get("passaporte") == "12345")
        if not ready:
            raise OcrEngineUnavailable("OCR health smoke não retornou Cargo/Nome/Passaporte esperados.")
        _ENGINE_STATUS = OcrHealth(
            ready=True,
            engine="rapidocr_onnxruntime",
            backend="onnxruntime-cpu",
            onnx_available=True,
            versions=versions,
            chars=result.ocr.chars,
            records=len(records),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        _ENGINE_STATUS = OcrHealth(
            ready=False,
            engine="rapidocr_onnxruntime",
            backend="onnxruntime-cpu",
            onnx_available="unavailable" not in versions.get("onnxruntime", ""),
            error=_compact_error(exc),
            versions=versions,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    return _ENGINE_STATUS


def get_cached_health() -> Optional[OcrHealth]:
    return _ENGINE_STATUS
