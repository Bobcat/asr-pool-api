from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asr_pool_api import (
  ASRAudioFile,
  ASROutputSelection,
  ASRRequestOptions,
  ASRRequestRouting,
  ASRSubmitRequest,
)
from asr_pool_api import _codec


class CodecTests(unittest.TestCase):
  def test_build_submit_request_payload_sets_schema_and_fields(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      audio_path = Path(tmp) / "sample.wav"
      audio_path.write_bytes(b"RIFF")
      request = ASRSubmitRequest(
        request_id="req-1",
        consumer_id="consumer-a",
        audio=ASRAudioFile(
          path=audio_path,
          format="wav",
          duration_ms=1234,
          sample_rate_hz=16000,
          channels=1,
        ),
        routing=ASRRequestRouting(fairness_key="sess-1"),
        options=ASRRequestOptions(language="nl", align_enabled=True, diarize_enabled=False),
        outputs=ASROutputSelection(srt=True),
      )

      payload, resolved_audio = _codec.build_submit_request_payload(request)

      self.assertEqual(resolved_audio, audio_path.resolve())
      self.assertEqual(payload["schema_version"], "asr_v2")
      self.assertEqual(payload["request_id"], "req-1")
      self.assertEqual(payload["consumer_id"], "consumer-a")
      self.assertEqual(payload["priority"], "normal")
      self.assertEqual(payload["routing"]["fairness_key"], "sess-1")
      self.assertEqual(payload["audio"]["duration_ms"], 1234)
      self.assertEqual(payload["outputs"]["srt"], True)
      self.assertEqual(payload["options"]["language"], "nl")

  def test_request_status_from_payload_builds_error_info(self) -> None:
    status = _codec.request_status_from_payload(
      {
        "request_id": "req-2",
        "consumer_id": "consumer-b",
        "state": "failed",
        "error": {
          "code": "ASR_FAIL",
          "message": "boom",
          "retryable": False,
          "details": {"slot": 1},
        },
      }
    )

    self.assertEqual(status.request_id, "req-2")
    self.assertEqual(status.state, "failed")
    self.assertIsNotNone(status.error)
    assert status.error is not None
    self.assertEqual(status.error.code, "ASR_FAIL")
    self.assertEqual(status.error.details["slot"], 1)


if __name__ == "__main__":
  unittest.main()
