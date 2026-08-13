from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from botocore.exceptions import ClientError, EndpointConnectionError

import b2_storage as b2


class Clock:
    def __init__(self) -> None:
        self.value = 1_700_000_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += float(seconds)


class FakeS3Client:
    def __init__(self, *, health_error: BaseException | None = None, upload_error: BaseException | None = None) -> None:
        self.health_error = health_error
        self.upload_error = upload_error
        self.head_bucket_calls = 0
        self.upload_calls: List[Dict[str, Any]] = []
        self.put_calls: List[Dict[str, Any]] = []

    def head_bucket(self, Bucket: str) -> Dict[str, Any]:
        self.head_bucket_calls += 1
        if self.health_error is not None:
            raise self.health_error
        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "Bucket": Bucket}

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs: Dict[str, Any] | None = None) -> None:
        if self.upload_error is not None:
            raise self.upload_error
        self.upload_calls.append({"Filename": Filename, "Bucket": Bucket, "Key": Key, "ExtraArgs": ExtraArgs or {}})

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str, Metadata: Dict[str, str] | None = None) -> Dict[str, Any]:
        if self.upload_error is not None:
            raise self.upload_error
        self.put_calls.append({"Bucket": Bucket, "Key": Key, "Body": Body, "ContentType": ContentType, "Metadata": Metadata or {}})
        return {"ETag": '"ok"'}


def client_error(code: str, message: str = "simulated") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "PutObject")


def manager(tmp_path: Path, client: FakeS3Client, logs: List[str], clock: Clock | None = None) -> b2.B2StorageManager:
    return b2.B2StorageManager(
        config=b2.B2Config(
            enabled=True,
            endpoint_url="https://s3.us-east-005.backblazeb2.com",
            region_name="us-east-005",
            access_key_id="configured-access-key",
            secret_access_key="configured-secret",
            bucket_name="existing-bucket",
            prefix="dicor/database",
        ),
        client_factory=lambda: client,
        state_path=tmp_path / "b2_state.json",
        logger=logs.append,
        retry_seconds=300,
        log_interval_seconds=300,
        now=clock or Clock(),
    )


def test_health_ready_bucket_valid(tmp_path: Path) -> None:
    logs: List[str] = []
    client = FakeS3Client()
    mgr = manager(tmp_path, client, logs)

    health = mgr.health_check(force=True)

    assert health.ready
    assert health.status == b2.READY
    assert client.head_bucket_calls == 1
    assert any("READY" in line for line in logs)


def test_nosuchbucket_marks_unavailable_without_crash_or_local_delete(tmp_path: Path) -> None:
    logs: List[str] = []
    clock = Clock()
    local = tmp_path / "catalogo_uploads" / "foto.jpg"
    local.parent.mkdir()
    local.write_bytes(b"image")
    client = FakeS3Client(health_error=client_error("NoSuchBucket", "The specified bucket does not exist"))
    mgr = manager(tmp_path, client, logs, clock)

    health = mgr.health_check(force=True)
    result = mgr.upload_file(local, "files/catalogo_uploads/foto.jpg")

    assert health.unavailable
    assert health.reason == b2.NO_SUCH_BUCKET
    assert result.pending
    assert local.exists()
    assert client.upload_calls == []
    assert len([line for line in logs if "UNAVAILABLE" in line]) == 1


def test_access_denied_is_not_reported_as_missing_bucket(tmp_path: Path) -> None:
    logs: List[str] = []
    client = FakeS3Client(health_error=client_error("AccessDenied", "denied"))
    mgr = manager(tmp_path, client, logs)

    health = mgr.health_check(force=True)

    assert health.unavailable
    assert health.reason == b2.ACCESS_DENIED
    assert health.reason != b2.NO_SUCH_BUCKET
    assert any("AccessDenied" in line for line in logs)


def test_network_error_uses_backoff_and_skips_repeated_uploads(tmp_path: Path) -> None:
    logs: List[str] = []
    clock = Clock()
    local = tmp_path / "a.txt"
    local.write_text("ok", encoding="utf-8")
    client = FakeS3Client(health_error=EndpointConnectionError(endpoint_url="https://b2.example"))
    mgr = manager(tmp_path, client, logs, clock)

    assert mgr.health_check(force=True).reason == b2.NETWORK
    result_1 = mgr.upload_file(local, "files/a.txt")
    result_2 = mgr.upload_file(local, "files/a.txt")

    assert result_1.pending and result_2.pending
    assert client.upload_calls == []
    assert client.head_bucket_calls == 1
    assert mgr.pending_count() == 1


def test_successful_file_and_bytes_upload(tmp_path: Path) -> None:
    logs: List[str] = []
    client = FakeS3Client()
    local = tmp_path / "foto.jpg"
    local.write_bytes(b"jpeg")
    mgr = manager(tmp_path, client, logs)

    file_result = mgr.upload_file(local, "files/catalogo_uploads/foto.jpg", category="catalogo")
    bytes_result = mgr.upload_bytes(b"{}", "current/master_records.json", content_type="application/json")

    assert file_result.uploaded
    assert bytes_result.uploaded
    assert client.upload_calls[0]["Bucket"] == "existing-bucket"
    assert client.upload_calls[0]["Key"] == "dicor/database/files/catalogo_uploads/foto.jpg"
    assert client.put_calls[0]["Key"] == "dicor/database/current/master_records.json"


def test_missing_local_file_is_controlled_failure(tmp_path: Path) -> None:
    logs: List[str] = []
    client = FakeS3Client()
    mgr = manager(tmp_path, client, logs)

    result = mgr.upload_file(tmp_path / "missing.jpg", "files/missing.jpg")

    assert not result.uploaded
    assert not result.pending
    assert result.reason == "LOCAL_FILE_MISSING"
    assert client.upload_calls == []


def test_100_files_do_not_generate_100_logs_or_100_upload_attempts_when_bucket_missing(tmp_path: Path) -> None:
    logs: List[str] = []
    clock = Clock()
    client = FakeS3Client(health_error=client_error("NoSuchBucket", "missing bucket"))
    mgr = manager(tmp_path, client, logs, clock)

    assert mgr.health_check(force=True).reason == b2.NO_SUCH_BUCKET
    for index in range(100):
        local = tmp_path / "catalogo_uploads" / f"foto-{index}.jpg"
        local.parent.mkdir(exist_ok=True)
        local.write_bytes(f"image-{index}".encode("ascii"))
        result = mgr.upload_file(local, f"files/catalogo_uploads/foto-{index}.jpg")
        assert result.pending
        assert local.exists()

    assert mgr.pending_count() == 100
    assert client.upload_calls == []
    assert client.head_bucket_calls == 1
    assert len([line for line in logs if "UNAVAILABLE" in line]) == 1


def test_backend_recovers_and_syncs_pending_files(tmp_path: Path) -> None:
    logs: List[str] = []
    clock = Clock()
    client = FakeS3Client(health_error=client_error("NoSuchBucket", "missing bucket"))
    mgr = manager(tmp_path, client, logs, clock)
    local = tmp_path / "catalogo_uploads" / "foto.jpg"
    local.parent.mkdir()
    local.write_bytes(b"image")

    assert mgr.health_check(force=True).reason == b2.NO_SUCH_BUCKET
    assert mgr.upload_file(local, "files/catalogo_uploads/foto.jpg").pending
    clock.advance(301)
    client.health_error = None
    summary = mgr.sync_pending(limit=10)

    assert summary["uploaded"] == 1
    assert summary["remaining"] == 0
    assert client.upload_calls
    assert mgr.status().ready


def test_upload_error_marks_pending_and_preserves_local_file(tmp_path: Path) -> None:
    logs: List[str] = []
    local = tmp_path / "foto.jpg"
    local.write_bytes(b"image")
    client = FakeS3Client(upload_error=client_error("NoSuchBucket", "missing bucket"))
    mgr = manager(tmp_path, client, logs)

    result = mgr.upload_file(local, "files/foto.jpg")

    assert result.pending
    assert result.reason == b2.NO_SUCH_BUCKET
    assert local.exists()
    assert mgr.status().unavailable
