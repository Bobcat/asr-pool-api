# asr-pool-api

`asr-pool-api` is a Python client library for `asr-pool`.
It provides a typed interface for submitting audio, reading request status,
consuming streaming completion events, and downloading SRT artifacts.
The library abstracts the pool's current web transport, including its
streaming completion feed.

## What It Does

- submits audio requests to `asr-pool`
- fetches point-in-time request status snapshots for known request ids
- consumes completion events from the pool completion feed
- downloads generated SRT artifacts to a local path
- maps remote failures and I/O failures to typed Python exceptions

## Public API

Main entry points:

- `ASRPoolClient`
- `ASRPoolClientConfig`
- `ASRSubmitRequest`
- `ASRAudioFile`
- `ASRRequestOptions`
- `ASRRequestRouting`
- `ASROutputSelection`
- `ASRRequestStatus`
- `ASRCompletionEvent`
- `ASRCompletionFeedReset`

Core client methods:

- `ASRPoolClient.submit_audio(...)`
- `ASRPoolClient.get_request_statuses(...)`
- `ASRPoolClient.iter_completions(...)`
- `ASRPoolClient.download_srt(...)`

## Usage Overview

Create a client with a pool base URL, then build typed request objects instead
of assembling raw multipart payloads or parsing SSE frames yourself.

```python
from pathlib import Path

from asr_pool_api import (
  ASRAudioFile,
  ASROutputSelection,
  ASRPoolClient,
  ASRPoolClientConfig,
  ASRRequestOptions,
  ASRSubmitRequest,
)

client = ASRPoolClient(
  ASRPoolClientConfig(base_url="http://127.0.0.1:8090")
)

status = client.submit_audio(
  ASRSubmitRequest(
    request_id="job_123",
    consumer_id="client-1",
    audio=ASRAudioFile(path=Path("/path/to/audio.wav"), format="wav"),
    options=ASRRequestOptions(language="nl", speaker_mode="auto"),
    outputs=ASROutputSelection(srt=True),
  )
)
```

Poll request status snapshots for progress-oriented UX:

```python
rows = client.get_request_statuses(
  consumer_id="client-1",
  request_ids=["job_123"],
)
```

Consume terminal completion events from the pool feed:

```python
for event in client.iter_completions(consumer_id="client-1", since_seq=0):
  print(type(event).__name__)
```

Download the final SRT artifact after completion:

```python
client.download_srt(
  request_id="job_123",
  dst_path=Path("/path/to/output.srt"),
)
```

## Configuration

`ASRPoolClientConfig` controls the transport behavior:

- `base_url`
- `token`
- `http_timeout_s`
- `retry_attempts`
- `retry_base_delay_s`
- `retry_max_delay_s`
- `retry_jitter_s`
- `stream_heartbeat_s`

Defaults are suitable for a local pool at `http://127.0.0.1:8090`, but callers
can override timeout, retry, auth token, and stream heartbeat settings as
needed.

## Request Model Overview

`ASRSubmitRequest` is the main input model.
It combines:

- request identity: `request_id`, `consumer_id`
- audio input: `ASRAudioFile`
- scheduling: `priority`, `ASRRequestRouting`
- ASR options: `ASRRequestOptions`
- desired outputs: `ASROutputSelection`

`priority` defaults to `normal`; set it to `interactive` for latency-sensitive
work. `ASRRequestRouting` carries `fairness_key` for interactive fairness.
Clients do not choose pool runner slots.

This keeps consumer code at the domain level instead of manipulating the pool's
wire format directly.

## Status And Completion Model

`ASRRequestStatus` exposes the fields most clients need for progress and final
state handling, including:

- `state`
- `stage`
- `queue_position`
- `submitted_at_utc`
- `started_at_utc`
- `finished_at_utc`
- `stage_started_at_utc`
- `response`
- `error`

Completion streaming yields two event types:

- `ASRCompletionEvent`
- `ASRCompletionFeedReset`

`ASRCompletionFeedReset` is intentionally public because it is meaningful at the
client level: it tells the consumer that the completion feed identity changed
and events may have been missed across the reset boundary.

## Error Model

The client raises typed exceptions instead of exposing raw transport details:

- `ASRPoolInputError`
- `ASRPoolTransportError`
- `ASRPoolRequestRejected`
- `ASRPoolArtifactError`

All inherit from `ASRPoolError` and expose:

- `code`
- `message`
- `retryable`
- `details`

This lets callers make clear distinctions between local validation failures,
remote request rejection, transport failures, and artifact download failures.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
