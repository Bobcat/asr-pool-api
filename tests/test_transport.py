from __future__ import annotations

import threading
import unittest
from urllib import parse as urlparse
from unittest import mock

from asr_pool_api import _transport
from asr_pool_api.models import ASRPoolClientConfig


class _FakeSSEStream:
  def __init__(self, lines: list[str]) -> None:
    self.status = 200
    self._lines = [line.encode("utf-8") for line in lines]

  def readline(self) -> bytes:
    if self._lines:
      return self._lines.pop(0)
    return b""

  def __enter__(self) -> "_FakeSSEStream":
    return self

  def __exit__(self, exc_type, exc, tb) -> bool:
    return False


class TransportTests(unittest.TestCase):
  def test_iter_completion_events_reconnects_from_last_seen_seq(self) -> None:
    stop_event = threading.Event()
    urls: list[str] = []
    responses = [
      _FakeSSEStream([
        "event: completion\n",
        'data: {"seq":11,"ts_utc":"2026-04-05T08:00:00Z","request_id":"req-11","consumer_id":"consumer-a","state":"completed"}\n',
        "\n",
      ]),
      _FakeSSEStream([]),
    ]

    def _fake_urlopen(req, timeout):
      del timeout
      urls.append(str(req.full_url))
      if len(urls) == 2:
        stop_event.set()
      return responses[len(urls) - 1]

    cfg = ASRPoolClientConfig(
      base_url="http://pool.test",
      retry_base_delay_s=0.0,
      retry_max_delay_s=0.0,
      retry_jitter_s=0.0,
      stream_heartbeat_s=1.0,
    )
    with mock.patch("asr_pool_api._transport.urlrequest.urlopen", side_effect=_fake_urlopen):
      rows = list(_transport.iter_completion_events(
        config=cfg,
        consumer_id="consumer-a",
        since_seq=10,
        stop_event=stop_event,
      ))

    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0][0], "completion")
    self.assertEqual(rows[0][1]["seq"], 11)
    self.assertEqual(len(urls), 2)
    second_query = urlparse.parse_qs(urlparse.urlparse(urls[1]).query)
    self.assertEqual(second_query.get("since_seq"), ["11"])


if __name__ == "__main__":
  unittest.main()
