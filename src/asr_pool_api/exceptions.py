from __future__ import annotations

from typing import Any


class ASRPoolError(RuntimeError):
  def __init__(
    self,
    *,
    code: str,
    message: str,
    retryable: bool | None = None,
    details: dict[str, Any] | None = None,
  ) -> None:
    self.code = str(code or "ASR_POOL_ERROR")
    self.message = str(message or self.code)
    self.retryable = retryable
    self.details = dict(details or {})
    super().__init__(f"{self.code}: {self.message}")


class ASRPoolInputError(ASRPoolError):
  pass


class ASRPoolTransportError(ASRPoolError):
  pass


class ASRPoolArtifactError(ASRPoolError):
  pass


class ASRPoolRequestRejected(ASRPoolError):
  def __init__(
    self,
    *,
    code: str,
    message: str,
    retryable: bool | None = None,
    details: dict[str, Any] | None = None,
    request_status: Any = None,
  ) -> None:
    self.request_status = request_status
    super().__init__(code=code, message=message, retryable=retryable, details=details)
