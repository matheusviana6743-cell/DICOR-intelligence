from __future__ import annotations

import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    from botocore.exceptions import (
        ClientError,
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )
except Exception:  # pragma: no cover - botocore is optional at import time
    ClientError = None  # type: ignore[assignment]
    EndpointConnectionError = Exception  # type: ignore[assignment]
    ConnectTimeoutError = Exception  # type: ignore[assignment]
    ReadTimeoutError = Exception  # type: ignore[assignment]
    ConnectionClosedError = Exception  # type: ignore[assignment]


READY = "READY"
UNAVAILABLE = "UNAVAILABLE"
UNCONFIGURED = "UNCONFIGURED"

NO_SUCH_BUCKET = "NoSuchBucket"
ACCESS_DENIED = "AccessDenied"
INVALID_ACCESS_KEY = "InvalidAccessKeyId"
SIGNATURE_MISMATCH = "SignatureDoesNotMatch"
NETWORK = "NetworkUnavailable"
TIMEOUT = "Timeout"
NOT_FOUND = "NotFound"
UNKNOWN = "UnknownError"


@dataclass(frozen=True)
class B2Config:
    enabled: bool
    endpoint_url: str
    region_name: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    prefix: str = ""

    @property
    def has_endpoint(self) -> bool:
        return bool(self.endpoint_url.strip())

    @property
    def has_region(self) -> bool:
        return bool(self.region_name.strip())

    @property
    def has_access_key(self) -> bool:
        return bool(self.access_key_id.strip())

    @property
    def has_secret_key(self) -> bool:
        return bool(self.secret_access_key.strip())

    @property
    def has_bucket(self) -> bool:
        return bool(self.bucket_name.strip())

    def missing_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.enabled:
            missing.append("B2_ENABLED")
        if not self.has_endpoint:
            missing.append("B2_ENDPOINT_URL")
        if not self.has_region:
            missing.append("B2_REGION")
        if not self.has_access_key:
            missing.append("B2_ACCESS_KEY_ID")
        if not self.has_secret_key:
            missing.append("B2_SECRET_ACCESS_KEY")
        if not self.has_bucket:
            missing.append("B2_BUCKET")
        return missing

    def configured(self) -> bool:
        return not self.missing_fields()

    def safe_summary(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "endpoint_configured": self.has_endpoint,
            "region_configured": self.has_region,
            "access_key_configured": self.has_access_key,
            "secret_configured": self.has_secret_key,
            "bucket": self.bucket_name.strip(),
            "prefix": self.prefix.strip("/"),
        }


@dataclass(frozen=True)
class B2Health:
    status: str
    reason: str = ""
    detail: str = ""
    retry_after_seconds: int = 0
    bucket: str = ""
    pending_count: int = 0

    @property
    def ready(self) -> bool:
        return self.status == READY

    @property
    def unavailable(self) -> bool:
        return self.status == UNAVAILABLE


@dataclass(frozen=True)
class B2UploadResult:
    uploaded: bool
    pending: bool
    key: str
    reason: str = ""
    detail: str = ""
    size: int = 0
    content_type: str = "application/octet-stream"


def _client_error_code(error: BaseException) -> str:
    if ClientError is not None and isinstance(error, ClientError):
        try:
            code = str(error.response.get("Error", {}).get("Code", "") or "").strip()
            if code:
                return code
        except Exception:
            return ""
    return ""


def classify_b2_error(error: BaseException) -> Tuple[str, bool]:
    code = _client_error_code(error)
    text = f"{type(error).__name__}: {error}".lower()
    compact = code.lower() or text
    if "nosuchbucket" in compact or "specified bucket does not exist" in compact:
        return NO_SUCH_BUCKET, False
    if "accessdenied" in compact or "access denied" in compact or "forbidden" in compact:
        return ACCESS_DENIED, False
    if "invalidaccesskeyid" in compact:
        return INVALID_ACCESS_KEY, True
    if "signaturedoesnotmatch" in compact or "signature mismatch" in compact:
        return SIGNATURE_MISMATCH, True
    if ClientError is not None and isinstance(error, ClientError):
        if code in {"404", "NoSuchKey", "NotFound"}:
            return NOT_FOUND, False
    network_classes = (EndpointConnectionError, ConnectionClosedError)
    timeout_classes = (ConnectTimeoutError, ReadTimeoutError, TimeoutError)
    if isinstance(error, timeout_classes):
        return TIMEOUT, False
    if isinstance(error, network_classes):
        return NETWORK, False
    if "endpointconnectionerror" in text or "could not connect" in text or "connection" in text:
        return NETWORK, False
    if "timeout" in text or "timed out" in text:
        return TIMEOUT, False
    return UNKNOWN, False


class B2StorageManager:
    def __init__(
        self,
        *,
        config: B2Config,
        client_factory: Callable[[], Any],
        state_path: Optional[Path] = None,
        logger: Optional[Callable[[str], None]] = None,
        retry_seconds: int = 1800,
        log_interval_seconds: int = 1800,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self.config = config
        self.client_factory = client_factory
        self.state_path = Path(state_path) if state_path is not None else None
        self.logger = logger or (lambda message: None)
        self.retry_seconds = max(60, int(retry_seconds or 1800))
        self.log_interval_seconds = max(60, int(log_interval_seconds or 1800))
        self.now = now or time.time
        self._lock = RLock()
        self._state = self._load_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "status": UNCONFIGURED,
            "reason": "",
            "detail": "",
            "blocked_until": 0,
            "permanent": False,
            "last_log_key": "",
            "last_log_at": 0,
            "pending": {},
            "updated_at": 0,
        }

    def _load_state(self) -> Dict[str, Any]:
        state = self._default_state()
        if self.state_path is None or not self.state_path.exists():
            return state
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state.update(raw)
            if not isinstance(state.get("pending"), dict):
                state["pending"] = {}
            return state
        except Exception:
            return state

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(self._state)
            payload["updated_at"] = int(self.now())
            tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
        except Exception:
            return

    def _log_once(self, key: str, message: str, *, interval: Optional[int] = None) -> None:
        interval_s = int(interval or self.log_interval_seconds)
        now = float(self.now())
        with self._lock:
            last_key = str(self._state.get("last_log_key") or "")
            last_at = float(self._state.get("last_log_at") or 0)
            if key == last_key and now - last_at < interval_s:
                return
            self._state["last_log_key"] = key
            self._state["last_log_at"] = now
            self._save_state()
        self.logger(message)

    def _pending(self) -> Dict[str, Dict[str, Any]]:
        pending = self._state.setdefault("pending", {})
        if not isinstance(pending, dict):
            pending = {}
            self._state["pending"] = pending
        return pending

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending())

    def is_configured(self) -> bool:
        return self.config.configured()

    def status(self) -> B2Health:
        with self._lock:
            blocked_until = int(self._state.get("blocked_until") or 0)
            retry_after = max(0, blocked_until - int(self.now()))
            return B2Health(
                status=str(self._state.get("status") or UNCONFIGURED),
                reason=str(self._state.get("reason") or ""),
                detail=str(self._state.get("detail") or ""),
                retry_after_seconds=retry_after,
                bucket=self.config.bucket_name,
                pending_count=len(self._pending()),
            )

    def _set_ready(self) -> B2Health:
        with self._lock:
            self._state["status"] = READY
            self._state["reason"] = ""
            self._state["detail"] = ""
            self._state["blocked_until"] = 0
            self._state["permanent"] = False
            self._save_state()
            health = self.status()
        self._log_once("ready", f"[B2] Backend READY. Bucket acessível: {self.config.bucket_name}", interval=300)
        return health

    def _set_unconfigured(self) -> B2Health:
        missing = ", ".join(self.config.missing_fields())
        with self._lock:
            self._state["status"] = UNCONFIGURED
            self._state["reason"] = "CONFIG_MISSING"
            self._state["detail"] = f"Campos ausentes: {missing}"
            self._state["blocked_until"] = 0
            self._state["permanent"] = True
            self._save_state()
            health = self.status()
        self._log_once(
            "unconfigured",
            f"[B2] Backend UNCONFIGURED. Configure {missing}. Arquivos locais permanecem preservados em /data.",
            interval=self.log_interval_seconds,
        )
        return health

    def mark_unavailable(self, error: BaseException | str, *, reason: Optional[str] = None) -> B2Health:
        if isinstance(error, BaseException):
            classified, permanent = classify_b2_error(error)
            detail = f"{type(error).__name__}: {error}"
        else:
            classified, permanent = (reason or UNKNOWN), False
            detail = str(error)
        reason_final = str(reason or classified)
        blocked_until = 0 if permanent else int(self.now()) + self.retry_seconds
        with self._lock:
            self._state["status"] = UNAVAILABLE
            self._state["reason"] = reason_final
            self._state["detail"] = detail[:1000]
            self._state["blocked_until"] = blocked_until
            self._state["permanent"] = bool(permanent)
            self._save_state()
            health = self.status()
        extra = ""
        if reason_final == NO_SUCH_BUCKET:
            extra = f" Bucket configurado não existe: {self.config.bucket_name}."
        elif reason_final == ACCESS_DENIED:
            extra = " Credenciais sem permissão para consultar/enviar ao bucket."
        elif reason_final in {INVALID_ACCESS_KEY, SIGNATURE_MISMATCH}:
            extra = " Credenciais ou assinatura inválidas."
        elif reason_final in {NETWORK, TIMEOUT}:
            extra = " Falha temporária de rede/timeout."
        self._log_once(
            f"unavailable:{reason_final}",
            f"[B2] Backend UNAVAILABLE: {reason_final}.{extra} Uploads remotos temporariamente desativados; arquivos locais permanecem preservados em /data. Pendentes: {health.pending_count}.",
            interval=self.log_interval_seconds,
        )
        return health

    def due_for_retry(self) -> bool:
        with self._lock:
            if self._state.get("permanent"):
                return False
            blocked_until = int(self._state.get("blocked_until") or 0)
            return blocked_until <= int(self.now())

    def health_check(self, *, force: bool = False) -> B2Health:
        if not self.config.configured():
            return self._set_unconfigured()
        current = self.status()
        if current.ready and not force:
            return current
        if current.unavailable and not force and not self.due_for_retry():
            return current
        self._log_once("health-start", "[B2] Health check iniciado.", interval=300)
        try:
            client = self.client_factory()
            if client is None:
                raise RuntimeError("cliente boto3 indisponível")
            client.head_bucket(Bucket=self.config.bucket_name)
            return self._set_ready()
        except Exception as error:
            return self.mark_unavailable(error)

    def can_use_remote(self, *, force_health: bool = False) -> bool:
        health = self.health_check(force=force_health)
        return health.ready

    def queue_pending_file(self, path: Path, key: str, *, category: str = "", content_type: str = "") -> None:
        path = Path(path)
        with self._lock:
            self._pending()[str(key)] = {
                "kind": "file",
                "path": str(path),
                "key": str(key),
                "category": str(category or ""),
                "content_type": str(content_type or ""),
                "queued_at": int(self.now()),
            }
            self._save_state()

    def clear_pending(self, key: str) -> None:
        with self._lock:
            self._pending().pop(str(key), None)
            self._save_state()

    def remote_key(self, key: str) -> str:
        key = str(key or "").strip().lstrip("/")
        prefix = self.config.prefix.strip("/")
        if prefix and not key.startswith(prefix + "/"):
            return f"{prefix}/{key}"
        return key

    def upload_file(self, path: Path, key: str, *, category: str = "", content_type: str = "") -> B2UploadResult:
        path = Path(path)
        key = self.remote_key(key)
        if not path.exists() or not path.is_file():
            return B2UploadResult(False, False, key, reason="LOCAL_FILE_MISSING", detail=str(path), size=0)
        size = int(path.stat().st_size)
        guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not self.can_use_remote():
            self.queue_pending_file(path, key, category=category, content_type=guessed)
            return B2UploadResult(False, True, key, reason=self.status().reason, detail="backend indisponível", size=size, content_type=guessed)
        try:
            client = self.client_factory()
            if client is None:
                raise RuntimeError("cliente boto3 indisponível")
            client.upload_file(
                str(path),
                self.config.bucket_name,
                key,
                ExtraArgs={"ContentType": guessed, "Metadata": {"origem": "dicor-intelligence"}},
            )
            self.clear_pending(key)
            return B2UploadResult(True, False, key, size=size, content_type=guessed)
        except Exception as error:
            reason, _permanent = classify_b2_error(error)
            self.queue_pending_file(path, key, category=category, content_type=guessed)
            self.mark_unavailable(error, reason=reason)
            return B2UploadResult(False, True, key, reason=reason, detail=f"{type(error).__name__}: {error}"[:1000], size=size, content_type=guessed)

    def upload_bytes(self, data: bytes, key: str, *, content_type: str = "application/octet-stream") -> B2UploadResult:
        payload = bytes(data or b"")
        key = self.remote_key(key)
        if not payload:
            return B2UploadResult(False, False, key, reason="EMPTY_PAYLOAD", detail="", size=0, content_type=content_type)
        if not self.can_use_remote():
            return B2UploadResult(False, True, key, reason=self.status().reason, detail="backend indisponível", size=len(payload), content_type=content_type)
        try:
            client = self.client_factory()
            if client is None:
                raise RuntimeError("cliente boto3 indisponível")
            client.put_object(Bucket=self.config.bucket_name, Key=key, Body=payload, ContentType=content_type, Metadata={"origem": "dicor-intelligence"})
            self.clear_pending(key)
            return B2UploadResult(True, False, key, size=len(payload), content_type=content_type)
        except Exception as error:
            reason, _permanent = classify_b2_error(error)
            self.mark_unavailable(error, reason=reason)
            return B2UploadResult(False, True, key, reason=reason, detail=f"{type(error).__name__}: {error}"[:1000], size=len(payload), content_type=content_type)

    def sync_pending(self, *, limit: int = 50) -> Dict[str, int]:
        if not self.can_use_remote():
            return {"attempted": 0, "uploaded": 0, "failed": 0, "remaining": self.pending_count()}
        attempted = uploaded = failed = 0
        keys: Iterable[str]
        with self._lock:
            keys = list(self._pending().keys())[: max(0, int(limit))]
        for key in keys:
            with self._lock:
                item = dict(self._pending().get(key) or {})
            if item.get("kind") != "file":
                continue
            attempted += 1
            result = self.upload_file(
                Path(str(item.get("path") or "")),
                str(item.get("key") or key),
                category=str(item.get("category") or ""),
                content_type=str(item.get("content_type") or ""),
            )
            if result.uploaded:
                uploaded += 1
            else:
                failed += 1
                if self.status().unavailable:
                    break
        return {"attempted": attempted, "uploaded": uploaded, "failed": failed, "remaining": self.pending_count()}
