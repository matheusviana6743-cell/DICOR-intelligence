from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


VISUAL_INDEX_VERSION = 1
VISUAL_ALGORITHM_VERSION = "dicor-local-v1"
VISUAL_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VISUAL_IMAGE_MIME_PREFIX = "image/"
VISUAL_DEFAULT_FULL_THRESHOLD = 58.0
VISUAL_DEFAULT_CLOTHING_THRESHOLD = 60.0


class VisualSearchError(RuntimeError):
    """Erro controlado da busca visual local."""


@dataclass(frozen=True)
class VisualImageRecord:
    image_id: str
    rg: str
    nome: str
    individuo_id: int
    registro_id: int
    path: str
    url: str = ""
    source: str = ""
    mime_type: str = ""
    description: str = ""

    @classmethod
    def from_mapping(cls, raw: Dict[str, Any]) -> "VisualImageRecord":
        image_id = str(raw.get("image_id") or "").strip()
        path = str(raw.get("path") or raw.get("caminho") or "").strip()
        rg = str(raw.get("rg") or "").strip()
        individuo_id = int(raw.get("individuo_id") or raw.get("registro_id") or 0)
        registro_id = int(raw.get("registro_id") or individuo_id or 0)
        if not image_id:
            digest = hashlib.sha1(f"{registro_id}:{path}".encode("utf-8", "ignore")).hexdigest()[:16]
            image_id = f"imagem:{digest}"
        return cls(
            image_id=image_id,
            rg=rg,
            nome=str(raw.get("nome") or raw.get("name") or "Ficha sem nome").strip()[:160],
            individuo_id=individuo_id,
            registro_id=registro_id,
            path=path,
            url=str(raw.get("url") or raw.get("url_original") or "").strip(),
            source=str(raw.get("source") or raw.get("origem") or "").strip()[:80],
            mime_type=str(raw.get("mime_type") or raw.get("mime") or "").strip()[:120],
            description=str(raw.get("description") or raw.get("descricao") or "").strip()[:500],
        )


def can_rebuild_visual_index(*, is_inspector_plus: bool, is_admin: bool = False) -> bool:
    return bool(is_inspector_plus or is_admin)


def is_supported_visual_file(path_or_name: Any, mime_type: str = "") -> bool:
    mime = str(mime_type or "").lower().strip()
    if mime.startswith(VISUAL_IMAGE_MIME_PREFIX):
        return True
    suffix = Path(str(path_or_name or "")).suffix.lower()
    return suffix in VISUAL_IMAGE_EXTENSIONS


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    vetor = np.asarray(vector, dtype=np.float32).reshape(-1)
    norma = float(np.linalg.norm(vetor))
    if norma <= 1e-12:
        return np.zeros_like(vetor, dtype=np.float32)
    return (vetor / norma).astype(np.float32)


def _rgb_histogram(arr: np.ndarray, bins: int = 8) -> np.ndarray:
    partes: List[np.ndarray] = []
    for canal in range(3):
        hist, _ = np.histogram(arr[:, :, canal], bins=bins, range=(0, 255))
        partes.append(hist.astype(np.float32))
    vetor = np.concatenate(partes)
    soma = float(vetor.sum())
    if soma:
        vetor = vetor / soma
    return vetor.astype(np.float32)


def _grid_means(arr: np.ndarray, rows: int = 4, cols: int = 4) -> np.ndarray:
    h, w = arr.shape[:2]
    partes: List[np.ndarray] = []
    for r in range(rows):
        y0 = int(round(h * r / rows))
        y1 = int(round(h * (r + 1) / rows))
        for c in range(cols):
            x0 = int(round(w * c / cols))
            x1 = int(round(w * (c + 1) / cols))
            bloco = arr[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1), :]
            partes.append((bloco.mean(axis=(0, 1)) / 255.0).astype(np.float32))
    return np.concatenate(partes).astype(np.float32)


def _edge_orientation_histogram(arr: np.ndarray, rows: int = 4, cols: int = 4, bins: int = 8) -> np.ndarray:
    cinza = (
        arr[:, :, 0].astype(np.float32) * 0.299
        + arr[:, :, 1].astype(np.float32) * 0.587
        + arr[:, :, 2].astype(np.float32) * 0.114
    )
    gy, gx = np.gradient(cinza)
    magnitude = np.sqrt(gx * gx + gy * gy)
    angulo = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)
    h, w = cinza.shape
    partes: List[np.ndarray] = []
    for r in range(rows):
        y0 = int(round(h * r / rows))
        y1 = int(round(h * (r + 1) / rows))
        for c in range(cols):
            x0 = int(round(w * c / cols))
            x1 = int(round(w * (c + 1) / cols))
            mag = magnitude[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
            ang = angulo[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
            hist, _ = np.histogram(ang, bins=bins, range=(0.0, 1.0), weights=mag)
            hist = hist.astype(np.float32)
            soma = float(hist.sum())
            if soma:
                hist = hist / soma
            partes.append(hist)
    return np.concatenate(partes).astype(np.float32)


def _texture_stats(arr: np.ndarray) -> np.ndarray:
    cinza = (
        arr[:, :, 0].astype(np.float32) * 0.299
        + arr[:, :, 1].astype(np.float32) * 0.587
        + arr[:, :, 2].astype(np.float32) * 0.114
    ) / 255.0
    gy, gx = np.gradient(cinza)
    magnitude = np.sqrt(gx * gx + gy * gy)
    canais = arr.astype(np.float32) / 255.0
    stats = [
        float(cinza.mean()),
        float(cinza.std()),
        float(magnitude.mean()),
        float(magnitude.std()),
        float(canais[:, :, 0].mean()),
        float(canais[:, :, 1].mean()),
        float(canais[:, :, 2].mean()),
        float(canais[:, :, 0].std()),
        float(canais[:, :, 1].std()),
        float(canais[:, :, 2].std()),
    ]
    return np.asarray(stats, dtype=np.float32)


def _resize_rgb(image: Image.Image, size: int = 128) -> np.ndarray:
    corrigida = ImageOps.exif_transpose(image).convert("RGB")
    corrigida.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    x = (size - corrigida.width) // 2
    y = (size - corrigida.height) // 2
    canvas.paste(corrigida, (x, y))
    return np.asarray(canvas, dtype=np.uint8)


def validate_image(image: Image.Image) -> Tuple[bool, str, Dict[str, float]]:
    largura, altura = image.size
    if largura < 40 or altura < 40:
        return False, "imagem muito pequena para comparação confiável", {"width": float(largura), "height": float(altura)}
    arr = _resize_rgb(image, 96)
    media = float(arr.mean())
    desvio = float(arr.std())
    if media < 7.0:
        return False, "imagem escura demais para comparação confiável", {"brightness": media, "contrast": desvio}
    if media > 248.0 and desvio < 3.0:
        return False, "imagem clara demais e sem detalhes úteis", {"brightness": media, "contrast": desvio}
    if desvio < 2.5:
        return False, "imagem sem contraste suficiente para comparação visual", {"brightness": media, "contrast": desvio}
    return True, "ok", {"brightness": media, "contrast": desvio, "width": float(largura), "height": float(altura)}


def _extract_from_array(arr: np.ndarray) -> Dict[str, np.ndarray]:
    h = arr.shape[0]
    full = np.concatenate([
        _rgb_histogram(arr, 8),
        _grid_means(arr, 4, 4),
        _edge_orientation_histogram(arr, 4, 4, 8),
        _texture_stats(arr),
    ])
    roupa_crop = arr[int(h * 0.25):, :, :]
    if roupa_crop.size == 0:
        roupa_crop = arr
    roupa = np.concatenate([
        _rgb_histogram(roupa_crop, 10),
        _grid_means(roupa_crop, 4, 3),
        _edge_orientation_histogram(roupa_crop, 4, 3, 8),
        _texture_stats(roupa_crop),
    ])
    aparencia_crop = arr[:max(8, int(h * 0.55)), :, :]
    aparencia = np.concatenate([
        _rgb_histogram(aparencia_crop, 8),
        _grid_means(aparencia_crop, 3, 4),
        _edge_orientation_histogram(aparencia_crop, 3, 4, 8),
        _texture_stats(aparencia_crop),
    ])
    acessorio_crop = arr[:max(8, int(h * 0.78)), :, :]
    acessorio = np.concatenate([
        _rgb_histogram(acessorio_crop, 6),
        _edge_orientation_histogram(acessorio_crop, 4, 4, 8),
        _texture_stats(acessorio_crop),
    ])
    return {
        "full": _normalize_vector(full),
        "clothing": _normalize_vector(roupa),
        "appearance": _normalize_vector(aparencia),
        "accessory": _normalize_vector(acessorio),
    }


def extract_visual_features_from_image(image: Image.Image) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    ok, reason, quality = validate_image(image)
    if not ok:
        raise VisualSearchError(reason)
    arr = _resize_rgb(image, 128)
    return _extract_from_array(arr), quality


def extract_visual_features_from_bytes(data: bytes) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    if not data or len(data) < 32:
        raise VisualSearchError("arquivo de imagem vazio ou inválido")
    try:
        import io

        with Image.open(io.BytesIO(data)) as img:
            return extract_visual_features_from_image(img)
    except VisualSearchError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as erro:
        raise VisualSearchError(f"não foi possível abrir a imagem: {type(erro).__name__}") from erro


def extract_visual_features_from_path(path: Path) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    try:
        with Image.open(path) as img:
            return extract_visual_features_from_image(img)
    except VisualSearchError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as erro:
        raise VisualSearchError(f"não foi possível abrir a imagem `{path.name}`: {type(erro).__name__}") from erro


def _fingerprint(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    sha1 = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha1.update(chunk)
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha1": sha1.hexdigest(),
    }


def _empty_matrix(rows: int, cols: int) -> np.ndarray:
    return np.zeros((rows, cols), dtype=np.float32)


def _stack_vectors(entries: List[Dict[str, Any]], key: str) -> np.ndarray:
    if not entries:
        return _empty_matrix(0, 0)
    vetores = [np.asarray(e[key], dtype=np.float32).reshape(-1) for e in entries]
    return np.vstack(vetores).astype(np.float32)


class VisualSearchIndex:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.index_dir = self.root / "index"
        self.metadata_dir = self.root / "metadata"
        self.cache_dir = self.root / "cache"
        self.index_path = self.index_dir / "visual_index_v1.npz"
        self.metadata_path = self.metadata_dir / "metadata_v1.json"
        self.entries: List[Dict[str, Any]] = []
        self.vectors: Dict[str, np.ndarray] = {
            "full": _empty_matrix(0, 0),
            "clothing": _empty_matrix(0, 0),
            "appearance": _empty_matrix(0, 0),
            "accessory": _empty_matrix(0, 0),
        }
        self.last_warning = ""

    def ensure_dirs(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        self.entries = []
        self.vectors = {
            "full": _empty_matrix(0, 0),
            "clothing": _empty_matrix(0, 0),
            "appearance": _empty_matrix(0, 0),
            "accessory": _empty_matrix(0, 0),
        }
        self.last_warning = ""
        if not self.index_path.exists() or not self.metadata_path.exists():
            return
        try:
            metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if int(metadata.get("index_version") or 0) != VISUAL_INDEX_VERSION:
                self.last_warning = "versão do índice visual incompatível; reconstrua o índice"
                return
            if str(metadata.get("algorithm_version") or "") != VISUAL_ALGORITHM_VERSION:
                self.last_warning = "algoritmo do índice visual mudou; reconstrua o índice"
                return
            entries = list(metadata.get("entries") or [])
            with np.load(self.index_path, allow_pickle=False) as data:
                vectors = {
                    "full": np.asarray(data["full"], dtype=np.float32),
                    "clothing": np.asarray(data["clothing"], dtype=np.float32),
                    "appearance": np.asarray(data["appearance"], dtype=np.float32),
                    "accessory": np.asarray(data["accessory"], dtype=np.float32),
                }
            total = len(entries)
            if any(v.shape[0] != total for v in vectors.values()):
                self.last_warning = "metadados e vetores do índice visual estão inconsistentes; reconstrua o índice"
                return
            self.entries = entries
            self.vectors = vectors
        except Exception as erro:
            self.entries = []
            self.vectors = {
                "full": _empty_matrix(0, 0),
                "clothing": _empty_matrix(0, 0),
                "appearance": _empty_matrix(0, 0),
                "accessory": _empty_matrix(0, 0),
            }
            self.last_warning = f"índice visual não pôde ser carregado: {type(erro).__name__}"

    def save(self) -> None:
        self.ensure_dirs()
        metadata = {
            "index_version": VISUAL_INDEX_VERSION,
            "algorithm_version": VISUAL_ALGORITHM_VERSION,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_entries": len(self.entries),
            "entries": self.entries,
        }
        tmp_meta = self.metadata_path.with_suffix(".json.tmp")
        tmp_index = self.index_path.with_suffix(".npz.tmp")
        tmp_meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        with tmp_index.open("wb") as fh:
            np.savez_compressed(
                fh,
                full=self.vectors["full"],
                clothing=self.vectors["clothing"],
                appearance=self.vectors["appearance"],
                accessory=self.vectors["accessory"],
            )
        os.replace(tmp_meta, self.metadata_path)
        os.replace(tmp_index, self.index_path)

    def summary(self) -> Dict[str, Any]:
        registros = {str(e.get("rg") or "") for e in self.entries if str(e.get("rg") or "").strip()}
        tamanho = 0
        for caminho in (self.index_path, self.metadata_path):
            try:
                tamanho += caminho.stat().st_size
            except OSError:
                pass
        return {
            "entries": len(self.entries),
            "records": len(registros),
            "index_bytes": tamanho,
            "warning": self.last_warning,
            "root": str(self.root),
        }

    def build_or_update(
        self,
        raw_records: Iterable[Dict[str, Any] | VisualImageRecord],
        *,
        prune: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        self.load()
        self.ensure_dirs()
        records: List[VisualImageRecord] = []
        for raw in raw_records:
            record = raw if isinstance(raw, VisualImageRecord) else VisualImageRecord.from_mapping(dict(raw or {}))
            if record.path and is_supported_visual_file(record.path, record.mime_type) and record.registro_id:
                records.append(record)
        existing_by_id = {str(e.get("image_id") or ""): e for e in self.entries}
        kept_entries: List[Dict[str, Any]] = []
        valid_ids = {r.image_id for r in records}
        if not prune:
            kept_entries = list(self.entries)
        else:
            kept_entries = [e for e in self.entries if str(e.get("image_id") or "") in valid_ids]

        kept_by_id = {str(e.get("image_id") or ""): e for e in kept_entries}
        new_entries: List[Dict[str, Any]] = []
        added = 0
        updated = 0
        skipped = 0
        invalid = 0
        errors: List[str] = []
        total = len(records)
        for index, record in enumerate(records, start=1):
            if progress_callback:
                progress_callback({"phase": "indexing", "current": index, "total": total, "added": added, "updated": updated, "skipped": skipped, "invalid": invalid})
            path = Path(record.path)
            if not path.exists() or not path.is_file():
                invalid += 1
                errors.append(f"{record.image_id}: arquivo indisponível")
                continue
            try:
                fp = _fingerprint(path)
                antigo = existing_by_id.get(record.image_id)
                if antigo and str(antigo.get("sha1") or "") == fp["sha1"] and str(antigo.get("algorithm_version") or "") == VISUAL_ALGORITHM_VERSION:
                    if record.image_id not in kept_by_id:
                        kept_entries.append(antigo)
                        kept_by_id[record.image_id] = antigo
                    skipped += 1
                    continue
                features, quality = extract_visual_features_from_path(path)
                entry = {
                    "image_id": record.image_id,
                    "rg": record.rg,
                    "nome": record.nome,
                    "individuo_id": int(record.individuo_id),
                    "registro_id": int(record.registro_id),
                    "path": str(path),
                    "url": record.url,
                    "source": record.source,
                    "mime_type": record.mime_type,
                    "description": record.description,
                    "algorithm_version": VISUAL_ALGORITHM_VERSION,
                    "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "size": fp["size"],
                    "mtime_ns": fp["mtime_ns"],
                    "sha1": fp["sha1"],
                    "quality": quality,
                    "_features": features,
                }
                if record.image_id in kept_by_id:
                    pos = next(i for i, e in enumerate(kept_entries) if str(e.get("image_id") or "") == record.image_id)
                    kept_entries[pos] = entry
                    kept_by_id[record.image_id] = entry
                    updated += 1
                else:
                    kept_entries.append(entry)
                    kept_by_id[record.image_id] = entry
                    added += 1
                new_entries.append(entry)
            except Exception as erro:
                invalid += 1
                errors.append(f"{record.image_id}: {type(erro).__name__}: {erro}")

        def vector_for(entry: Dict[str, Any], key: str) -> np.ndarray:
            if "_features" in entry:
                return np.asarray(entry["_features"][key], dtype=np.float32)
            antigo = existing_by_id.get(str(entry.get("image_id") or ""))
            if antigo:
                try:
                    idx = self.entries.index(antigo)
                    return np.asarray(self.vectors[key][idx], dtype=np.float32)
                except Exception:
                    pass
            return np.zeros((0,), dtype=np.float32)

        prepared: List[Dict[str, Any]] = []
        matrices: Dict[str, List[np.ndarray]] = {"full": [], "clothing": [], "appearance": [], "accessory": []}
        for entry in kept_entries:
            row = {k: v for k, v in entry.items() if k != "_features"}
            vetores = {key: vector_for(entry, key) for key in matrices}
            if any(v.size == 0 for v in vetores.values()):
                invalid += 1
                continue
            prepared.append(row)
            for key, vetor in vetores.items():
                matrices[key].append(vetor)
        self.entries = prepared
        self.vectors = {key: np.vstack(value).astype(np.float32) if value else _empty_matrix(0, 0) for key, value in matrices.items()}
        self.save()
        return {
            "records_received": total,
            "indexed_images": len(self.entries),
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "invalid": invalid,
            "errors": errors[:20],
            "pruned": max(0, len(existing_by_id) - len([e for e in kept_entries if str(e.get("image_id") or "") in existing_by_id])),
            "summary": self.summary(),
        }

    def remove_image_ids(self, image_ids: Sequence[str]) -> Dict[str, int]:
        self.load()
        alvo = {str(x) for x in image_ids}
        if not alvo:
            return {"removed": 0, "remaining": len(self.entries)}
        keep_indices = [i for i, e in enumerate(self.entries) if str(e.get("image_id") or "") not in alvo]
        removed = len(self.entries) - len(keep_indices)
        self.entries = [self.entries[i] for i in keep_indices]
        self.vectors = {key: matrix[keep_indices] if len(keep_indices) else _empty_matrix(0, matrix.shape[1] if matrix.ndim == 2 else 0) for key, matrix in self.vectors.items()}
        self.save()
        return {"removed": removed, "remaining": len(self.entries)}

    def search_bytes(
        self,
        image_bytes: bytes,
        *,
        mode: str = "full",
        top_k: int = 5,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        self.load()
        mode_norm = "clothing" if str(mode or "").lower() in {"roupa", "clothing", "vestimenta"} else "full"
        if not self.entries:
            return {"results": [], "mode": mode_norm, "reason": "índice visual vazio", "warning": self.last_warning, "summary": self.summary()}
        query, quality = extract_visual_features_from_bytes(image_bytes)
        top_k = max(1, min(5, int(top_k or 5)))
        threshold_value = float(threshold if threshold is not None else (VISUAL_DEFAULT_CLOTHING_THRESHOLD if mode_norm == "clothing" else VISUAL_DEFAULT_FULL_THRESHOLD))
        full_sim = self._similarity("full", query["full"])
        clothing_sim = self._similarity("clothing", query["clothing"])
        appearance_sim = self._similarity("appearance", query["appearance"])
        accessory_sim = self._similarity("accessory", query["accessory"])
        if mode_norm == "clothing":
            general = full_sim * 0.18 + clothing_sim * 0.68 + appearance_sim * 0.04 + accessory_sim * 0.10
        else:
            general = full_sim * 0.48 + clothing_sim * 0.24 + appearance_sim * 0.20 + accessory_sim * 0.08

        grouped: Dict[str, Dict[str, Any]] = {}
        for idx, entry in enumerate(self.entries):
            rg_key = str(entry.get("rg") or f"id:{entry.get('registro_id') or idx}").strip()
            score = float(general[idx] * 100.0)
            if score < threshold_value:
                continue
            item = grouped.setdefault(
                rg_key,
                {
                    "rg": str(entry.get("rg") or ""),
                    "nome": str(entry.get("nome") or "Ficha sem nome"),
                    "registro_id": int(entry.get("registro_id") or entry.get("individuo_id") or 0),
                    "individuo_id": int(entry.get("individuo_id") or entry.get("registro_id") or 0),
                    "score": 0.0,
                    "full_score": 0.0,
                    "clothing_score": 0.0,
                    "appearance_score": 0.0,
                    "accessory_score": 0.0,
                    "matches_count": 0,
                    "best_image": {},
                    "all_scores": [],
                },
            )
            item["matches_count"] += 1
            item["all_scores"].append(score)
            item["full_score"] = max(float(item["full_score"]), float(full_sim[idx] * 100.0))
            item["clothing_score"] = max(float(item["clothing_score"]), float(clothing_sim[idx] * 100.0))
            item["appearance_score"] = max(float(item["appearance_score"]), float(appearance_sim[idx] * 100.0))
            item["accessory_score"] = max(float(item["accessory_score"]), float(accessory_sim[idx] * 100.0))
            if score > float(item["score"]):
                item["score"] = score
                item["nome"] = str(entry.get("nome") or item["nome"])
                item["registro_id"] = int(entry.get("registro_id") or item["registro_id"] or 0)
                item["individuo_id"] = int(entry.get("individuo_id") or item["individuo_id"] or 0)
                item["best_image"] = {
                    "image_id": str(entry.get("image_id") or ""),
                    "path": str(entry.get("path") or ""),
                    "url": str(entry.get("url") or ""),
                    "source": str(entry.get("source") or ""),
                    "description": str(entry.get("description") or ""),
                }
        results = list(grouped.values())
        for item in results:
            scores = sorted((_safe_float(x) for x in item.get("all_scores") or []), reverse=True)
            if len(scores) >= 2:
                item["score"] = min(100.0, scores[0] * 0.92 + scores[1] * 0.08)
            item["score"] = round(float(item["score"]), 1)
            item["full_score"] = round(float(item["full_score"]), 1)
            item["clothing_score"] = round(float(item["clothing_score"]), 1)
            item["appearance_score"] = round(float(item["appearance_score"]), 1)
            item["accessory_score"] = round(float(item["accessory_score"]), 1)
            item["explanations"] = explain_similarity(item, mode_norm)
            item.pop("all_scores", None)
        results.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        return {
            "results": results[:top_k],
            "mode": mode_norm,
            "threshold": threshold_value,
            "query_quality": quality,
            "warning": self.last_warning,
            "summary": self.summary(),
        }

    def _similarity(self, key: str, query_vector: np.ndarray) -> np.ndarray:
        matrix = self.vectors.get(key)
        if matrix is None or matrix.size == 0:
            return np.zeros((len(self.entries),), dtype=np.float32)
        query_vector = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if matrix.shape[1] != query_vector.shape[0]:
            return np.zeros((len(self.entries),), dtype=np.float32)
        similarity = matrix @ query_vector
        return np.clip(similarity, 0.0, 1.0).astype(np.float32)


def explain_similarity(result: Dict[str, Any], mode: str = "full") -> List[str]:
    clothing = _safe_float(result.get("clothing_score"))
    appearance = _safe_float(result.get("appearance_score"))
    accessory = _safe_float(result.get("accessory_score"))
    full = _safe_float(result.get("full_score"))
    explanations: List[str] = []
    if clothing >= 76:
        explanations.append("cores e distribuição da roupa muito próximas")
    elif clothing >= 66:
        explanations.append("padrão geral de vestimenta parecido")
    if str(mode) != "clothing":
        if appearance >= 76:
            explanations.append("aparência visual geral próxima")
        elif appearance >= 66:
            explanations.append("proporções e contraste da região superior compatíveis")
    if accessory >= 74:
        explanations.append("silhueta e detalhes periféricos semelhantes")
    if full >= 78 and not explanations:
        explanations.append("composição visual geral próxima")
    if not explanations:
        explanations.append("semelhança estatística moderada; exige conferência humana")
    return explanations[:3]


def format_index_size(num_bytes: int) -> str:
    valor = float(num_bytes)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024.0 or unidade == "GB":
            return f"{valor:.1f} {unidade}"
        valor /= 1024.0
    return f"{valor:.1f} GB"

