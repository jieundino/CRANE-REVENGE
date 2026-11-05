"""CRANE REVENGE 테스트 패키지 및 인메모리 ASGI 테스트 클라이언트."""

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urlsplit


@dataclass
class ASGIResponse:
    """ASGI 호출 결과를 담는 응답 객체."""

    status_code: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class ASGIClient:
    """소켓/스레드 생성 없이 FastAPI ASGI 앱을 직접 호출하는 테스트 클라이언트."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
    ) -> ASGIResponse:
        parsed = urlsplit(path)
        clean_path = parsed.path or "/"
        query_bytes = parsed.query.encode("utf-8")

        headers: list[tuple[bytes, bytes]] = [
            (b"host", b"testserver"),
            (b"user-agent", b"crane-revenge-testclient"),
        ]
        if json_body is not None:
            raw_body = json.dumps(json_body).encode("utf-8")
            headers.append((b"content-type", b"application/json"))
            headers.append((b"content-length", str(len(raw_body)).encode("ascii")))
        else:
            raw_body = b""

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": clean_path,
            "raw_path": clean_path.encode("utf-8"),
            "query_string": query_bytes,
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "state": {},
        }

        request_sent = False
        sent_messages: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {
                    "type": "http.request",
                    "body": raw_body,
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent_messages.append(message)

        coro = self.app(scope, receive, send)
        try:
            while True:
                coro.send(None)
        except StopIteration:
            pass

        status_code = 500
        resp_headers: dict[str, str] = {}
        body_chunks: list[bytes] = []

        for msg in sent_messages:
            if msg.get("type") == "http.response.start":
                status_code = int(msg.get("status", 500))
                for k, v in msg.get("headers", []):
                    resp_headers[k.decode("latin1").lower()] = v.decode("latin1")
            elif msg.get("type") == "http.response.body":
                body_chunks.append(msg.get("body", b""))

        return ASGIResponse(
            status_code=status_code,
            headers=resp_headers,
            body=b"".join(body_chunks),
        )

    def get(self, path: str) -> ASGIResponse:
        return self.request("GET", path)

    def post(self, path: str, *, json: Any | None = None) -> ASGIResponse:
        return self.request("POST", path, json_body=json)
