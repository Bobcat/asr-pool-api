from __future__ import annotations

import logging
from pathlib import Path
import threading
from typing import Iterator

from . import _codec, _transport
from .exceptions import (
  ASRPoolArtifactError,
  ASRPoolInputError,
  ASRPoolRequestRejected,
  ASRPoolTransportError,
)
from .models import (
  ASRCompletionEvent,
  ASRCompletionFeedReset,
  ASRPoolClientConfig,
  ASRRequestStatus,
  ASRSubmitRequest,
)

_LOGGER = logging.getLogger(__name__)


class ASRPoolClient:
  def __init__(self, config: ASRPoolClientConfig) -> None:
    self._config = config.normalized()

  @property
  def config(self) -> ASRPoolClientConfig:
    return self._config

  def submit_audio(self, request: ASRSubmitRequest) -> ASRRequestStatus:
    try:
      payload, audio_path = _codec.build_submit_request_payload(request)
    except FileNotFoundError as e:
      raise ASRPoolInputError(
        code="ASR_REMOTE_INPUT_PATH_MISSING",
        message=str(e),
        retryable=False,
        details={},
      ) from e
    except ValueError as e:
      raise ASRPoolInputError(
        code="ASR_REMOTE_INPUT_INVALID",
        message=str(e),
        retryable=False,
        details={},
      ) from e

    try:
      status_code, body, attempts_used = _transport.submit_multipart_request(
        config=self._config,
        request_payload=payload,
        audio_path=audio_path,
      )
    except _transport.MultipartBuildError as e:
      cause = e.__cause__
      exc_type = type(cause).__name__ if cause is not None else type(e).__name__
      raise ASRPoolInputError(
        code="ASR_REMOTE_MULTIPART_BUILD_FAILED",
        message=f"Failed to build multipart ASR submit payload: {e}",
        retryable=False,
        details={"exc_type": exc_type},
      ) from e
    except Exception as e:
      raise ASRPoolTransportError(
        code="ASR_REMOTE_SUBMIT_IO_FAILURE",
        message=f"ASR pool submit I/O failed: {type(e).__name__}: {e}",
        retryable=True,
        details={
          "pool_base_url": self._config.base_url,
          "request_id": str(request.request_id),
          "attempts": int(self._config.retry_attempts),
          "http_timeout_s": float(self._config.http_timeout_s),
          "exc_type": type(e).__name__,
        },
      ) from e

    status = _codec.request_status_from_payload(
      body,
      fallback_request_id=str(request.request_id),
      fallback_consumer_id=str(request.consumer_id),
    )
    if status_code not in {200, 202}:
      details = {
        "http_status": int(status_code),
        "pool_base_url": self._config.base_url,
        "request_id": str(request.request_id),
        "submit_attempts": int(attempts_used),
      }
      details.update(dict(body.get("details") or {}))
      raise ASRPoolRequestRejected(
        code=str(body.get("code") or "ASR_REMOTE_SUBMIT_FAILED"),
        message=str(body.get("message") or f"ASR pool submit failed with HTTP {status_code}"),
        retryable=body.get("retryable", True),
        details=details,
        request_status=status,
      )
    return status

  def get_request_statuses(
    self,
    *,
    consumer_id: str,
    request_ids: list[str],
    limit: int = 200,
  ) -> list[ASRRequestStatus]:
    cid = str(consumer_id or "").strip()
    if not cid:
      raise ASRPoolInputError(
        code="ASR_COMPLETIONS_STREAM_CONSUMER_REQUIRED",
        message="consumer_id is required",
        retryable=False,
        details={},
      )
    if not list(request_ids or []):
      return []
    try:
      rows = _transport.fetch_pending_status(
        config=self._config,
        consumer_id=cid,
        request_ids=list(request_ids or []),
        limit=limit,
      )
    except _transport.RemoteRequestError as e:
      details = dict(e.details or {})
      if e.status_code is not None:
        details.setdefault("http_status", int(e.status_code))
      raise ASRPoolRequestRejected(
        code=e.code,
        message=e.message,
        retryable=e.retryable,
        details=details,
      ) from e
    except Exception as e:
      raise ASRPoolTransportError(
        code="ASR_PENDING_STATUS_IO_FAILURE",
        message=f"ASR pool pending-status I/O failed: {type(e).__name__}: {e}",
        retryable=True,
        details={"pool_base_url": self._config.base_url, "exc_type": type(e).__name__},
      ) from e
    return [
      _codec.request_status_from_payload(row, fallback_consumer_id=cid)
      for row in rows
    ]

  def iter_completions(
    self,
    *,
    consumer_id: str,
    since_seq: int = 0,
    stop_event: threading.Event | None = None,
  ) -> Iterator[ASRCompletionEvent | ASRCompletionFeedReset]:
    cid = str(consumer_id or "").strip()
    if not cid:
      raise ASRPoolInputError(
        code="ASR_COMPLETIONS_STREAM_CONSUMER_REQUIRED",
        message="consumer_id is required",
        retryable=False,
        details={},
      )
    active_stop = stop_event if stop_event is not None else threading.Event()
    last_since_seq = max(0, int(since_seq))
    try:
      for kind, payload in _transport.iter_completion_events(
        config=self._config,
        consumer_id=cid,
        since_seq=last_since_seq,
        stop_event=active_stop,
      ):
        if kind == "completion":
          try:
            event = _codec.completion_event_from_payload(payload)
          except Exception as e:
            seq = None
            try:
              seq = int(dict(payload or {}).get("seq") or 0)
            except Exception:
              seq = None
            _LOGGER.warning(
              "asr_pool_api skipped malformed completion payload consumer_id=%s seq=%s exc=%s: %s",
              cid,
              seq,
              type(e).__name__,
              e,
            )
            if seq is not None and seq > 0:
              last_since_seq = max(last_since_seq, int(seq) + 1)
            continue
          last_since_seq = max(last_since_seq, int(event.seq) + 1)
          yield event
        elif kind == "feed_reset":
          try:
            event = _codec.feed_reset_from_payload(payload)
          except Exception as e:
            _LOGGER.warning(
              "asr_pool_api skipped malformed feed_reset payload consumer_id=%s exc=%s: %s",
              cid,
              type(e).__name__,
              e,
            )
            continue
          last_since_seq = 0
          yield event
    except Exception as e:
      raise ASRPoolTransportError(
        code="ASR_COMPLETIONS_STREAM_IO_FAILURE",
        message=f"{type(e).__name__}: {e}",
        retryable=True,
        details={
          "pool_base_url": self._config.base_url,
          "exc_type": type(e).__name__,
          "since_seq": int(last_since_seq),
        },
      ) from e

  def download_srt(
    self,
    *,
    request_id: str,
    dst_path: Path,
    allow_empty: bool = False,
  ) -> Path:
    rid = str(request_id or "").strip()
    if not rid:
      raise ASRPoolInputError(
        code="ASR_REMOTE_REQUEST_ID_REQUIRED",
        message="request_id is required",
        retryable=False,
        details={},
      )
    try:
      return _transport.download_request_srt_to_path(
        config=self._config,
        request_id=rid,
        dst_path=Path(dst_path),
        allow_empty=allow_empty,
      )
    except _transport.RemoteRequestError as e:
      details = dict(e.details or {})
      if e.status_code is not None:
        details.setdefault("http_status", int(e.status_code))
      raise ASRPoolArtifactError(
        code=e.code,
        message=e.message,
        retryable=e.retryable,
        details=details,
      ) from e
    except Exception as e:
      raise ASRPoolArtifactError(
        code="ASR_REMOTE_ARTIFACT_FETCH_IO_FAILURE",
        message=f"{type(e).__name__}: {e}",
        retryable=True,
        details={"pool_base_url": self._config.base_url, "exc_type": type(e).__name__},
      ) from e
