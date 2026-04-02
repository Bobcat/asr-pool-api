from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ASRRequestState = Literal["queued", "running", "completed", "failed", "cancel_requested", "cancelled", "unknown"]
ASRPriority = Literal["interactive", "normal", "background"]
ASRSpeakerMode = Literal["none", "auto", "fixed"]


@dataclass(frozen=True)
class ASRPoolClientConfig:
  base_url: str = "http://127.0.0.1:8090"
  token: str = ""
  http_timeout_s: float = 10.0
  retry_attempts: int = 3
  retry_base_delay_s: float = 0.2
  retry_max_delay_s: float = 2.0
  retry_jitter_s: float = 0.1
  stream_heartbeat_s: float = 10.0

  def normalized(self) -> "ASRPoolClientConfig":
    base = str(self.base_url or "").strip().rstrip("/")
    if not base:
      base = "http://127.0.0.1:8090"
    timeout_s = max(1.0, float(self.http_timeout_s))
    retry_attempts = max(1, int(self.retry_attempts))
    retry_base = max(0.0, float(self.retry_base_delay_s))
    retry_max = max(0.05, float(self.retry_max_delay_s))
    retry_max = max(retry_base, retry_max)
    retry_jitter = max(0.0, float(self.retry_jitter_s))
    heartbeat_s = max(1.0, float(self.stream_heartbeat_s))
    return ASRPoolClientConfig(
      base_url=base,
      token=str(self.token or ""),
      http_timeout_s=timeout_s,
      retry_attempts=retry_attempts,
      retry_base_delay_s=retry_base,
      retry_max_delay_s=retry_max,
      retry_jitter_s=retry_jitter,
      stream_heartbeat_s=heartbeat_s,
    )


@dataclass(frozen=True)
class ASRAudioFile:
  path: Path
  format: str = "wav"
  duration_ms: int | None = None
  sample_rate_hz: int | None = None
  channels: int | None = None


@dataclass(frozen=True)
class ASRRequestRouting:
  fairness_key: str = ""
  slot_affinity: int | None = None


@dataclass(frozen=True)
class ASRRequestOptions:
  language: str | None = None
  initial_prompt: str | None = None
  align_enabled: bool | None = None
  diarize_enabled: bool | None = None
  speaker_mode: ASRSpeakerMode | None = None
  min_speakers: int | None = None
  max_speakers: int | None = None
  beam_size: int | None = None
  chunk_size: int | None = None
  asr_backend: str | None = None


@dataclass(frozen=True)
class ASROutputSelection:
  text: bool = False
  segments: bool = False
  srt: bool = False
  srt_inline: bool = False


@dataclass(frozen=True)
class ASRSubmitRequest:
  request_id: str
  consumer_id: str
  audio: ASRAudioFile
  priority: ASRPriority = "background"
  routing: ASRRequestRouting = field(default_factory=ASRRequestRouting)
  options: ASRRequestOptions = field(default_factory=ASRRequestOptions)
  outputs: ASROutputSelection = field(default_factory=ASROutputSelection)


@dataclass(frozen=True)
class ASRErrorInfo:
  code: str
  message: str
  retryable: bool | None = None
  details: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "code": str(self.code),
      "message": str(self.message),
      "retryable": self.retryable,
      "details": dict(self.details or {}),
    }


@dataclass(frozen=True)
class ASRRequestStatus:
  request_id: str
  consumer_id: str
  state: ASRRequestState
  priority: str = ""
  stage: str | None = None
  queue_position: int | None = None
  fairness_key: str = ""
  slot_affinity_requested: int | None = None
  slot_affinity_effective: int | None = None
  submitted_at_utc: str | None = None
  started_at_utc: str | None = None
  finished_at_utc: str | None = None
  stage_started_at_utc: str | None = None
  timings: dict[str, float] = field(default_factory=dict)
  retryable: bool | None = None
  response: dict[str, Any] | None = None
  error: ASRErrorInfo | None = None

  @property
  def is_terminal(self) -> bool:
    return str(self.state or "").strip().lower() in {"completed", "failed", "cancelled"}

  def to_dict(self) -> dict[str, Any]:
    return {
      "request_id": str(self.request_id),
      "consumer_id": str(self.consumer_id),
      "state": str(self.state),
      "priority": str(self.priority),
      "stage": self.stage,
      "queue_position": self.queue_position,
      "fairness_key": str(self.fairness_key),
      "slot_affinity_requested": self.slot_affinity_requested,
      "slot_affinity_effective": self.slot_affinity_effective,
      "submitted_at_utc": self.submitted_at_utc,
      "started_at_utc": self.started_at_utc,
      "finished_at_utc": self.finished_at_utc,
      "stage_started_at_utc": self.stage_started_at_utc,
      "timings": dict(self.timings or {}),
      "retryable": self.retryable,
      "response": (dict(self.response) if isinstance(self.response, dict) else self.response),
      "error": (self.error.to_dict() if self.error is not None else None),
    }


@dataclass(frozen=True)
class ASRCompletionEvent:
  seq: int
  ts_utc: str
  status: ASRRequestStatus


@dataclass(frozen=True)
class ASRCompletionFeedReset:
  old_feed_id: str
  new_feed_id: str
