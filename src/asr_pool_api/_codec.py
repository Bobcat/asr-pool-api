from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
  ASRAudioFile,
  ASRCompletionEvent,
  ASRCompletionFeedReset,
  ASRErrorInfo,
  ASROutputSelection,
  ASRRequestOptions,
  ASRRequestStatus,
  ASRSubmitRequest,
)

_SCHEMA_VERSION = "asr_v2"


def _clean_text(value: Any) -> str:
  return str(value or "").strip()


def _clean_int(value: Any) -> int | None:
  if value is None:
    return None
  try:
    return int(value)
  except Exception:
    return None


def _clean_float(value: Any) -> float | None:
  if value is None:
    return None
  try:
    return float(value)
  except Exception:
    return None


def _clean_timings(payload: Any) -> dict[str, float]:
  out: dict[str, float] = {}
  for raw_key, raw_value in dict(payload or {}).items():
    key = _clean_text(raw_key)
    if not key:
      continue
    sec = _clean_float(raw_value)
    if sec is None:
      continue
    out[key] = max(0.0, float(sec))
  return out


def build_submit_request_payload(request: ASRSubmitRequest) -> tuple[dict[str, Any], Path]:
  request_id = _clean_text(request.request_id)
  if not request_id:
    raise ValueError("request_id is required")
  consumer_id = _clean_text(request.consumer_id)
  if not consumer_id:
    raise ValueError("consumer_id is required")
  audio_path = Path(request.audio.path).expanduser().resolve()
  if not audio_path.exists() or not audio_path.is_file():
    raise FileNotFoundError(f"ASR input file not found: {audio_path}")

  audio_format = _clean_text(request.audio.format).lower()
  if not audio_format:
    audio_format = str(audio_path.suffix or "").lstrip(".").lower() or "bin"

  payload: dict[str, Any] = {
    "schema_version": _SCHEMA_VERSION,
    "request_id": request_id,
    "consumer_id": consumer_id,
    "priority": _clean_text(request.priority) or "normal",
    "audio": {
      "local_path": str(audio_path),
      "format": audio_format,
    },
    "outputs": {
      "text": bool(request.outputs.text),
      "segments": bool(request.outputs.segments),
      "srt": bool(request.outputs.srt),
      "srt_inline": bool(request.outputs.srt_inline),
    },
  }

  if request.audio.duration_ms is not None:
    payload["audio"]["duration_ms"] = int(max(1, int(request.audio.duration_ms)))
  if request.audio.sample_rate_hz is not None:
    payload["audio"]["sample_rate_hz"] = int(max(1, int(request.audio.sample_rate_hz)))
  if request.audio.channels is not None:
    payload["audio"]["channels"] = int(max(1, int(request.audio.channels)))

  routing: dict[str, Any] = {}
  fairness_key = _clean_text(request.routing.fairness_key)
  if fairness_key:
    routing["fairness_key"] = fairness_key
  if routing:
    payload["routing"] = routing

  options: dict[str, Any] = {}
  if request.options.language is not None:
    lang = _clean_text(request.options.language)
    if lang:
      options["language"] = lang
  if request.options.initial_prompt is not None:
    prompt = str(request.options.initial_prompt).strip()
    if prompt:
      options["initial_prompt"] = prompt
  if request.options.align_enabled is not None:
    options["align_enabled"] = bool(request.options.align_enabled)
  if request.options.diarize_enabled is not None:
    options["diarize_enabled"] = bool(request.options.diarize_enabled)
  if request.options.speaker_mode is not None:
    speaker_mode = _clean_text(request.options.speaker_mode).lower()
    if speaker_mode:
      options["speaker_mode"] = speaker_mode
  if request.options.min_speakers is not None:
    options["min_speakers"] = int(max(1, int(request.options.min_speakers)))
  if request.options.max_speakers is not None:
    options["max_speakers"] = int(max(1, int(request.options.max_speakers)))
  if request.options.beam_size is not None:
    options["beam_size"] = int(max(1, int(request.options.beam_size)))
  if request.options.chunk_size is not None:
    options["chunk_size"] = int(max(1, int(request.options.chunk_size)))
  if request.options.asr_backend is not None:
    asr_backend = _clean_text(request.options.asr_backend).lower()
    if asr_backend:
      options["asr_backend"] = asr_backend
  if options:
    payload["options"] = options

  return payload, audio_path


def error_info_from_payload(
  payload: dict[str, Any],
  *,
  default_code: str,
  default_message: str,
  default_retryable: bool | None = None,
  extra_details: dict[str, Any] | None = None,
) -> ASRErrorInfo:
  body = dict(payload or {})
  details = dict(body.get("details") or {})
  if extra_details:
    details.update(dict(extra_details))
  return ASRErrorInfo(
    code=_clean_text(body.get("code")) or str(default_code),
    message=_clean_text(body.get("message")) or str(default_message),
    retryable=(body.get("retryable") if body.get("retryable") is not None else default_retryable),
    details=details,
  )


def request_status_from_payload(
  payload: dict[str, Any],
  *,
  fallback_request_id: str = "",
  fallback_consumer_id: str = "",
) -> ASRRequestStatus:
  body = dict(payload or {})
  err_obj = body.get("error")
  error = None
  if isinstance(err_obj, dict) and err_obj:
    error = error_info_from_payload(
      err_obj,
      default_code="ASR_REMOTE_ERROR",
      default_message="ASR request error",
    )
  return ASRRequestStatus(
    request_id=_clean_text(body.get("request_id")) or str(fallback_request_id),
    consumer_id=_clean_text(body.get("consumer_id")) or str(fallback_consumer_id),
    state=_clean_text(body.get("state")).lower() or "unknown",
    priority=_clean_text(body.get("priority")),
    stage=(_clean_text(body.get("stage")) or None),
    queue_position=_clean_int(body.get("queue_position")),
    fairness_key=_clean_text(body.get("fairness_key")),
    submitted_at_utc=(_clean_text(body.get("submitted_at_utc")) or None),
    started_at_utc=(_clean_text(body.get("started_at_utc")) or None),
    finished_at_utc=(_clean_text(body.get("finished_at_utc")) or None),
    stage_started_at_utc=(_clean_text(body.get("stage_started_at_utc")) or None),
    timings=_clean_timings(body.get("timings")),
    retryable=body.get("retryable"),
    response=(dict(body.get("response") or {}) if isinstance(body.get("response"), dict) else None),
    error=error,
  )


def completion_event_from_payload(payload: dict[str, Any]) -> ASRCompletionEvent:
  body = dict(payload or {})
  return ASRCompletionEvent(
    seq=max(0, int(body.get("seq") or 0)),
    ts_utc=_clean_text(body.get("ts_utc")),
    status=request_status_from_payload(body),
  )


def feed_reset_from_payload(payload: dict[str, Any]) -> ASRCompletionFeedReset:
  body = dict(payload or {})
  return ASRCompletionFeedReset(
    old_feed_id=_clean_text(body.get("old_feed_id")),
    new_feed_id=_clean_text(body.get("new_feed_id")),
  )
