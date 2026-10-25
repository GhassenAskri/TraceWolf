"""Send one genuine SDK-instrumented OpenAI call (mocked HTTP) for a NEW volume to the real ingest endpoint."""
import httpx2

from tests import spans as s

body = s.to_protobuf(s.capture(s.chat(volume="bob-chat-7")))
r = httpx2.post("http://127.0.0.1:8011/v1/traces", content=body, headers={"content-type": "application/x-protobuf"}, timeout=20)
print("POST /v1/traces ->", r.status_code)
