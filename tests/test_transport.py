from __future__ import annotations

import threading
import tempfile
import unittest
from urllib import parse as urlparse
from unittest import mock
from pathlib import Path

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


class _FakeHTTPResponse:
  status = 202
  will_close = False

  def read(self) -> bytes:
    return b'{"request_id":"req-1","consumer_id":"consumer-a","state":"queued"}'

  def getheader(self, name: str, default: str = "") -> str:
    del name
    return default


class _FakeHTTPConnection:
  instances: list["_FakeHTTPConnection"] = []

  def __init__(self, host: str, port: int | None = None, timeout: float | None = None) -> None:
    self.host = host
    self.port = port
    self.timeout = timeout
    self.requests: list[dict[str, object]] = []
    self.closed = False
    self.instances.append(self)

  def request(
    self,
    method: str,
    url: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
  ) -> None:
    self.requests.append(
      {
        "method": method,
        "url": url,
        "body": bytes(body or b""),
        "headers": dict(headers or {}),
      }
    )

  def getresponse(self) -> _FakeHTTPResponse:
    return _FakeHTTPResponse()

  def close(self) -> None:
    self.closed = True


class TransportTests(unittest.TestCase):
  def test_submit_multipart_request_reuses_persistent_http_connection(self) -> None:
    _FakeHTTPConnection.instances.clear()
    cfg = ASRPoolClientConfig(base_url="http://pool.test:18090/base", token="secret")
    transport = _transport.PersistentHTTPTransport()
    with tempfile.TemporaryDirectory() as tmp:
      audio_path = Path(tmp) / "audio.wav"
      audio_path.write_bytes(b"RIFF")
      with mock.patch("asr_pool_api._transport.http.client.HTTPConnection", _FakeHTTPConnection):
        for _idx in range(2):
          status_code, body, attempts = _transport.submit_multipart_request(
            config=cfg,
            request_payload={
              "request_id": "req-1",
              "consumer_id": "consumer-a",
              "audio": {"format": "wav"},
            },
            audio_path=audio_path,
            transport=transport,
          )
          self.assertEqual(status_code, 202)
          self.assertEqual(body["state"], "queued")
          self.assertEqual(attempts, 1)

    self.assertEqual(len(_FakeHTTPConnection.instances), 1)
    conn = _FakeHTTPConnection.instances[0]
    self.assertEqual(conn.host, "pool.test")
    self.assertEqual(conn.port, 18090)
    self.assertEqual(len(conn.requests), 2)
    self.assertEqual(conn.requests[0]["method"], "POST")
    self.assertEqual(conn.requests[0]["url"], "/base/asr/v1/requests")
    self.assertEqual(conn.requests[0]["headers"]["X-ASR-Token"], "secret")
    self.assertTrue(str(conn.requests[0]["headers"]["Content-Type"]).startswith("multipart/form-data; boundary="))

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
