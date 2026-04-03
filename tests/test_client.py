from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from asr_pool_api import (
  ASRAudioFile,
  ASROutputSelection,
  ASRPoolClient,
  ASRPoolClientConfig,
  ASRPoolRequestRejected,
  ASRSubmitRequest,
)


class ClientTests(unittest.TestCase):
  def test_submit_audio_returns_status_object(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      audio_path = Path(tmp) / "audio.wav"
      audio_path.write_bytes(b"RIFF")
      client = ASRPoolClient(ASRPoolClientConfig(base_url="http://pool.test"))
      request = ASRSubmitRequest(
        request_id="req-1",
        consumer_id="consumer-a",
        audio=ASRAudioFile(path=audio_path, format="wav"),
        outputs=ASROutputSelection(srt=True),
      )
      with mock.patch(
        "asr_pool_api._transport.submit_multipart_request",
        return_value=(202, {"request_id": "req-1", "consumer_id": "consumer-a", "state": "queued"}, 1),
      ):
        status = client.submit_audio(request)
      self.assertEqual(status.request_id, "req-1")
      self.assertEqual(status.state, "queued")

  def test_submit_audio_raises_rejected_error_on_non_2xx(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      audio_path = Path(tmp) / "audio.wav"
      audio_path.write_bytes(b"RIFF")
      client = ASRPoolClient(ASRPoolClientConfig(base_url="http://pool.test"))
      request = ASRSubmitRequest(
        request_id="req-2",
        consumer_id="consumer-a",
        audio=ASRAudioFile(path=audio_path, format="wav"),
      )
      with mock.patch(
        "asr_pool_api._transport.submit_multipart_request",
        return_value=(409, {"code": "ASR_DUP", "message": "duplicate", "request_id": "req-2"}, 1),
      ):
        with self.assertRaises(ASRPoolRequestRejected):
          client.submit_audio(request)

  def test_iter_completions_maps_feed_reset(self) -> None:
    client = ASRPoolClient(ASRPoolClientConfig(base_url="http://pool.test"))

    def _iter_completion_events(**_kwargs):
      yield "feed_reset", {"old_feed_id": "old", "new_feed_id": "new"}
      return

    with mock.patch("asr_pool_api._transport.iter_completion_events", _iter_completion_events):
      rows = list(client.iter_completions(consumer_id="consumer-a", stop_event=threading.Event()))
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0].old_feed_id, "old")
    self.assertEqual(rows[0].new_feed_id, "new")

  def test_iter_completions_skips_malformed_completion_and_continues(self) -> None:
    client = ASRPoolClient(ASRPoolClientConfig(base_url="http://pool.test"))

    def _iter_completion_events(**_kwargs):
      yield "completion", {"seq": {}}
      yield "completion", {
        "seq": 12,
        "ts_utc": "2026-04-03T08:00:00Z",
        "request_id": "req-12",
        "consumer_id": "consumer-a",
        "state": "completed",
      }

    with mock.patch("asr_pool_api._transport.iter_completion_events", _iter_completion_events):
      rows = list(client.iter_completions(consumer_id="consumer-a", stop_event=threading.Event()))
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0].seq, 12)
    self.assertEqual(rows[0].status.request_id, "req-12")


if __name__ == "__main__":
  unittest.main()
