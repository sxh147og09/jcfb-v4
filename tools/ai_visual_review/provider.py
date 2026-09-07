"""Provider-neutral, fail-closed batch vision adapter.

The adapter is deliberately separate from the review protocol.  It prepares
the two governed inputs (deterministic crop and original image), calls an
external provider supplied by the caller, and converts only structured,
evidence-bearing responses into :class:`VisualPassObservation` objects.

No provider is called at import time.  The optional OpenAI-compatible client
uses only an environment credential and never includes that credential in a
request/config/response hash or in a returned record.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol

from .protocol import HASH_RE, VisualPassObservation, build_review_record as build_protocol_review_record, canonical_hash


class VisionAdapterError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class VisionPassRequest:
    pass_id: str
    review_method: str
    queue_item_id: str
    market: str
    cell_label: str
    raw_image_sha256: str
    image_reference: str
    crop_reference: Optional[str]
    crop_hash: str
    locator_identity: str
    locator_version: str
    locator_hash: str
    image_bytes: Optional[bytes] = None

    def hash_payload(self) -> dict[str, Any]:
        return {
            "pass_id": self.pass_id,
            "review_method": self.review_method,
            "queue_item_id": self.queue_item_id,
            "market": self.market,
            "cell_label": self.cell_label,
            "raw_image_sha256": self.raw_image_sha256,
            "image_reference": self.image_reference,
            "crop_reference": self.crop_reference,
            "crop_hash": self.crop_hash,
            "locator_identity": self.locator_identity,
            "locator_version": self.locator_version,
            "locator_hash": self.locator_hash,
        }

    @property
    def request_hash(self) -> str:
        return _hash(self.hash_payload())


class VisionProvider(Protocol):
    provider_identity: str
    provider_version: str
    provider_config_hash: str

    def review(self, request: VisionPassRequest) -> Mapping[str, Any]: ...


def _required_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise VisionAdapterError("PROVIDER_HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return value


@dataclass(frozen=True)
class AdapterObservation:
    """Protocol observation plus adapter-only provider lineage metadata."""

    observation: VisualPassObservation
    provider_config_hash: str
    request_hash: str
    response_hash: Optional[str]
    evidence_uri: Optional[str] = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.observation, name)

    def validate(self, *, expected_method: str, expected_label: str) -> None:
        self.observation.validate(expected_method=expected_method, expected_label=expected_label)

    def as_dict(self) -> dict[str, Any]:
        value = self.observation.as_dict()
        value.update({"provider_config_hash": self.provider_config_hash, "request_hash": self.request_hash, "response_hash": self.response_hash, "evidence_uri": self.evidence_uri})
        return value


class ProviderNeutralBatchVisionAdapter:
    """Create Pass A/Pass B observations for a queue item.

    ``provider`` is injected, which permits an OpenAI-compatible provider,
    another vendor, or a deterministic test double without changing the
    governed protocol.  ``image_resolver`` is also injected so this layer
    never guesses where Library bytes live.
    """

    def __init__(
        self,
        provider: VisionProvider,
        *,
        image_resolver: Optional[Callable[[Mapping[str, Any], str], Optional[bytes]]] = None,
    ) -> None:
        self.provider = provider
        self.image_resolver = image_resolver
        for field in ("provider_identity", "provider_version", "provider_config_hash"):
            if not isinstance(getattr(provider, field, None), str) or not getattr(provider, field).strip():
                raise VisionAdapterError("PROVIDER_IDENTITY_INCOMPLETE", field)
        _required_hash(provider.provider_config_hash, "provider_config_hash")

    def build_request(self, item: Mapping[str, Any], pass_id: str) -> VisionPassRequest:
        if pass_id == "PASS_A":
            method = "AI_VISUAL_FROM_DETERMINISTIC_CROP"
            crop_reference = item.get("crop_evidence", {}).get("evidence_region_path")
        elif pass_id == "PASS_B":
            method = "AI_VISUAL_FROM_ORIGINAL_IMAGE"
            crop_reference = None
        else:
            raise VisionAdapterError("PASS_ID_INVALID", pass_id)
        crop_hash = item.get("crop_evidence", {}).get("crop_hash")
        for field, value in (("raw_image_sha256", item.get("raw_image_sha256")), ("crop_hash", crop_hash), ("locator_hash", item.get("locator_hash"))):
            _required_hash(value, field)
        resolver_bytes = self.image_resolver(item, pass_id) if self.image_resolver else None
        if resolver_bytes is not None and not isinstance(resolver_bytes, bytes):
            raise VisionAdapterError("IMAGE_BYTES_INVALID", "image_resolver must return bytes or None")
        return VisionPassRequest(
            pass_id=pass_id,
            review_method=method,
            queue_item_id=str(item.get("queue_item_id", "")),
            market=str(item.get("market", "")),
            cell_label=str(item.get("cell_label", "")),
            raw_image_sha256=str(item["raw_image_sha256"]),
            image_reference=str(item.get("raw_zip_member", item.get("raw_image_reference", "UNKNOWN"))),
            crop_reference=str(crop_reference) if crop_reference else None,
            crop_hash=str(crop_hash),
            locator_identity=str(item.get("locator_identity", "")),
            locator_version=str(item.get("locator_version", "")),
            locator_hash=str(item["locator_hash"]),
            image_bytes=resolver_bytes,
        )

    def _observation(self, request: VisionPassRequest) -> AdapterObservation:
        try:
            response = self.provider.review(request)
        except VisionAdapterError as exc:
            observation = VisualPassObservation(
                request.pass_id, request.review_method, "NOT_EXECUTED", None, None, None,
                self.provider.provider_identity, self.provider.provider_version,
                self.provider.provider_config_hash, f"{exc.code}:{exc.message}",
            )
            return AdapterObservation(observation, self.provider.provider_config_hash, request.request_hash, None)
        except Exception as exc:  # provider failure becomes an explicit pass failure
            observation = VisualPassObservation(
                request.pass_id, request.review_method, "NOT_EXECUTED", None, None, None,
                self.provider.provider_identity, self.provider.provider_version,
                self.provider.provider_config_hash, f"PROVIDER_CALL_FAILED:{type(exc).__name__}",
            )
            return AdapterObservation(observation, self.provider.provider_config_hash, request.request_hash, None)
        if not isinstance(response, Mapping):
            raise VisionAdapterError("PROVIDER_RESPONSE_INVALID", "response must be an object")
        response_hash = _hash(response)
        status = response.get("status")
        if status not in {"READABLE", "UNREADABLE", "AMBIGUOUS", "CONFLICT", "NOT_EXECUTED"}:
            raise VisionAdapterError("PROVIDER_STATUS_INVALID", str(status))
        evidence = response.get("evidence")
        if not isinstance(evidence, Mapping) or not evidence:
            raise VisionAdapterError("PROVIDER_EVIDENCE_REQUIRED", "structured evidence is required")
        evidence_hash = _hash({"request_hash": request.request_hash, "response_hash": response_hash, "evidence": evidence})
        value = response.get("value_text")
        label = response.get("label_text")
        if status == "READABLE" and (not isinstance(value, str) or not isinstance(label, str)):
            raise VisionAdapterError("PROVIDER_READABLE_BINDING_INCOMPLETE", "readable response requires value_text and label_text")
        if status != "READABLE" and value is not None:
            raise VisionAdapterError("PROVIDER_NONREADABLE_VALUE_FORBIDDEN", "non-readable response cannot carry value_text")
        observation = VisualPassObservation(
            request.pass_id, request.review_method, status, value, label, evidence_hash,
            self.provider.provider_identity, self.provider.provider_version,
            self.provider.provider_config_hash, response.get("reason"),
        )
        return AdapterObservation(observation, self.provider.provider_config_hash, request.request_hash, response_hash, str(response.get("evidence_uri")) if response.get("evidence_uri") else None)

    def review_item(self, item: Mapping[str, Any]) -> tuple[AdapterObservation, AdapterObservation]:
        # Both passes are attempted independently.  Missing bytes are a
        # provider/input blocker, never a reason to copy OCR into a result.
        return self._observation(self.build_request(item, "PASS_A")), self._observation(self.build_request(item, "PASS_B"))

    def build_review_record(self, item: Mapping[str, Any], *, reviewer_run_id: str = "AI-VISUAL-ADAPTER") -> dict[str, Any]:
        pass_a, pass_b = self.review_item(item)
        record = build_protocol_review_record(item, pass_a=pass_a, pass_b=pass_b, reviewer_run_id=reviewer_run_id)
        record["provider_metadata"] = {
            "provider_identity": self.provider.provider_identity,
            "provider_version": self.provider.provider_version,
            "provider_config_hash": self.provider.provider_config_hash,
            "request_hashes": {"PASS_A": pass_a.request_hash, "PASS_B": pass_b.request_hash},
            "response_hashes": {"PASS_A": pass_a.response_hash, "PASS_B": pass_b.response_hash},
        }
        record["canonical_review_record_hash"] = canonical_hash(record)
        return record


class StagingImageResolver:
    """Resolve only the queue's explicit crop path and raw ZIP member.

    The resolver verifies the declared crop/raw hashes.  It never searches an
    external Library or chooses a visually similar file.
    """

    def __init__(self, staging_root: str | Path, raw_zip_path: str | Path) -> None:
        self.staging_root = Path(staging_root).resolve()
        self.raw_zip_path = Path(raw_zip_path).resolve()

    def _crop_bytes(self, item: Mapping[str, Any]) -> bytes:
        relative = item.get("crop_evidence", {}).get("evidence_region_path")
        if not isinstance(relative, str) or not relative:
            raise VisionAdapterError("CROP_REFERENCE_MISSING", "queue item has no deterministic crop reference")
        candidates = [path for path in self.staging_root.rglob(Path(relative).name) if str(path).replace("\\", "/").endswith(relative.replace("\\", "/"))]
        if not candidates:
            raise VisionAdapterError("CROP_REFERENCE_AMBIGUOUS", relative)
        expected = item.get("crop_evidence", {}).get("crop_hash")
        matching = [path.read_bytes() for path in candidates if _hash_bytes(path.read_bytes()) == expected]
        if not matching or len({_hash_bytes(content) for content in matching}) != 1:
            raise VisionAdapterError("CROP_HASH_MISMATCH", relative)
        return matching[0]

    def _raw_bytes(self, item: Mapping[str, Any]) -> bytes:
        member = item.get("raw_zip_member")
        if not isinstance(member, str) or not member or ".." in Path(member).parts or member.startswith(("/", "\\")):
            raise VisionAdapterError("RAW_MEMBER_REFERENCE_INVALID", str(member))
        try:
            with zipfile.ZipFile(self.raw_zip_path, "r") as archive:
                content = archive.read(member)
        except (FileNotFoundError, KeyError, zipfile.BadZipFile) as exc:
            raise VisionAdapterError("RAW_MEMBER_NOT_RESOLVED", member) from exc
        expected = item.get("raw_image_sha256")
        if _hash_bytes(content) != expected:
            raise VisionAdapterError("RAW_IMAGE_HASH_MISMATCH", member)
        return content

    def __call__(self, item: Mapping[str, Any], pass_id: str) -> Optional[bytes]:
        return self._crop_bytes(item) if pass_id == "PASS_A" else self._raw_bytes(item)


def run_adapter_batch(queue_path: str | Path, output: str | Path, adapter: ProviderNeutralBatchVisionAdapter, *, reviewer_run_id: str) -> dict[str, Any]:
    """Run adapter evidence generation; never writes accepted/archive/training data."""
    queue_file = Path(queue_path)
    items = [json.loads(line) for line in queue_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [adapter.build_review_record(item, reviewer_run_id=reviewer_run_id) for item in items]
    counts = Counter(record["review_status"] for record in records)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    manifest = {
        "manifest_identity": "official-odds-ai-visual-review-provider-manifest@1.0.0",
        "contract_identity": "official-odds-ai-visual-review@1.0.0",
        "review_run_id": reviewer_run_id,
        "candidate_count": len(items),
        "record_count": len(records),
        "status_counts": dict(sorted(counts.items())),
        "provider_identity": adapter.provider.provider_identity,
        "provider_version": adapter.provider.provider_version,
        "provider_config_hash": adapter.provider.provider_config_hash,
        "source_queue_path": str(queue_file),
        "source_queue_hash": _hash_bytes(queue_file.read_bytes()),
        "accepted_payload_written": False,
        "archive_written": False,
        "training_written": False,
    }
    manifest["manifest_hash"] = _hash(manifest)
    write_jsonl(output_dir / "ai_visual_review_records.jsonl", records)
    write_jsonl(output_dir / "human_escalation_queue.jsonl", [record for record in records if record["review_status"] not in {"AI_CONFIRMED", "AI_CORRECTED"}])
    write_json(output_dir / "ai_visual_review_manifest.json", manifest)
    return manifest


class OpenAICompatibleVisionProvider:
    """Lazy OpenAI-compatible vision client; no credential means unavailable."""

    def __init__(self, *, endpoint: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None, timeout_seconds: float = 60.0) -> None:
        self.endpoint = endpoint or os.environ.get("JCFB_VISION_API_URL", "https://api.openai.com/v1/chat/completions")
        self.model = model or os.environ.get("JCFB_VISION_MODEL", "gpt-4.1-mini")
        self._api_key = api_key or os.environ.get("JCFB_VISION_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.timeout_seconds = timeout_seconds
        self.provider_identity = "openai-compatible-vision"
        self.provider_version = "chat-completions-compatible@1.0"
        self.provider_config_hash = _hash({"endpoint": self.endpoint, "model": self.model, "timeout_seconds": self.timeout_seconds})

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.model and self._api_key)

    def review(self, request: VisionPassRequest) -> Mapping[str, Any]:
        if not self.available:
            raise VisionAdapterError("VISION_PROVIDER_CONNECTION_REQUIRED", "endpoint, model, and API credential are required")
        if request.image_bytes is None:
            raise VisionAdapterError("IMAGE_BYTES_REQUIRED", "a resolver must provide source bytes before provider call")
        image_uri = "data:image/png;base64," + base64.b64encode(request.image_bytes).decode("ascii")
        prompt = (
            "Read exactly the governed odds cell. Return JSON only with keys: "
            "status (READABLE/UNREADABLE/AMBIGUOUS/CONFLICT), value_text, label_text, "
            "evidence (object), reason. Do not infer from adjacent cells or OCR. "
            f"The exact cell label is {request.cell_label!r}; bind the value to that label."
        )
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_uri}}]}],
        }
        req = urllib.request.Request(self.endpoint, data=_canonical_bytes(body), headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VisionAdapterError("VISION_PROVIDER_CALL_FAILED", type(exc).__name__) from exc
        try:
            text = payload["choices"][0]["message"]["content"]
            result = json.loads(text) if isinstance(text, str) else text
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise VisionAdapterError("VISION_PROVIDER_RESPONSE_UNPARSEABLE", "provider did not return structured JSON") from exc
        if not isinstance(result, Mapping):
            raise VisionAdapterError("VISION_PROVIDER_RESPONSE_INVALID", "provider JSON must be an object")
        return result


__all__ = ["AdapterObservation", "OpenAICompatibleVisionProvider", "ProviderNeutralBatchVisionAdapter", "StagingImageResolver", "VisionAdapterError", "VisionPassRequest", "VisionProvider", "run_adapter_batch"]
