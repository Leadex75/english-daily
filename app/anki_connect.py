from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_ACTIONS = frozenset({
    "version",
    "requestPermission",
    "modelFieldNames",
    "createModel",
    "addNotes",
})
DEFAULT_ENDPOINT = "http://127.0.0.1:8765"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
MAX_BODY_BYTES = 65536
TIMEOUT_SECONDS = 5


class AnkiConnectError(Exception):
    def __init__(self, message: str, kind: str = "error", status: int = 400):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status


def normalize_endpoint(value: str | None) -> str:
    endpoint = str(value or DEFAULT_ENDPOINT).strip().rstrip("/") or DEFAULT_ENDPOINT
    parsed = urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOOPBACK_HOSTS:
        raise AnkiConnectError("AnkiConnect URL must use http or https on a loopback host", "config")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AnkiConnectError("AnkiConnect URL must not contain credentials, query or fragment", "config")
    port = parsed.port
    if port is not None and not (1 <= port <= 65535):
        raise AnkiConnectError("AnkiConnect URL has an invalid port", "config")
    return endpoint


def validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AnkiConnectError("Request body must be a JSON object", "validation")
    action = str(payload.get("action") or "")
    if action not in ALLOWED_ACTIONS:
        raise AnkiConnectError(f"AnkiConnect action is not allowed: {action or '(empty)'}", "validation", 403)
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise AnkiConnectError("AnkiConnect params must be an object", "validation")
    version = payload.get("version", 6)
    try:
        if int(version) != 6:
            raise AnkiConnectError("AnkiConnect version 6 is required", "validation")
    except (TypeError, ValueError) as exc:
        raise AnkiConnectError("AnkiConnect version must be 6", "validation") from exc
    return {"action": action, "version": 6, "params": params}


def parse_body(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_BODY_BYTES:
        raise AnkiConnectError("Request body is too large", "validation", 413)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AnkiConnectError("Request body must be valid UTF-8 JSON", "validation") from exc
    return validate_payload(payload)


def _host_name(value: str) -> str:
    host = value.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.split(":", 1)[0]


def validate_local_request(headers: dict[str, str], expected_origin: str | None = None) -> None:
    host = str(headers.get("host") or "")
    if _host_name(host) not in LOOPBACK_HOSTS:
        raise AnkiConnectError("AnkiConnect proxy is available only on loopback hosts", "host", 403)
    if not expected_origin:
        return
    expected = expected_origin.rstrip("/")
    for name in ("origin", "referer"):
        value = str(headers.get(name) or "").strip()
        if not value:
            continue
        candidate = value.rsplit("/", 1)[0] if name == "referer" and "/" in value else value
        if candidate.rstrip("/") != expected:
            raise AnkiConnectError(f"Cross-site {name} is not allowed", "origin", 403)


def call_anki_connect(
    payload: dict[str, Any],
    endpoint: str | None = None,
    opener: Any = None,
) -> dict[str, Any]:
    request_payload = validate_payload(payload)
    target = normalize_endpoint(endpoint)
    data = json.dumps(request_payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        target,
        data=data,
        headers={"Content-Type": "text/plain", "Accept": "application/json"},
        method="POST",
    )
    sender = opener or urlopen
    try:
        with sender(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BODY_BYTES + 1)
    except HTTPError as exc:
        raise AnkiConnectError(f"AnkiConnect returned HTTP {exc.code}", "http", 502) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise AnkiConnectError("AnkiConnect is not running or is unreachable", "connection", 502) from exc
    if len(body) > MAX_BODY_BYTES:
        raise AnkiConnectError("AnkiConnect response is too large", "response", 502)
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AnkiConnectError("AnkiConnect returned invalid JSON", "response", 502) from exc
    if not isinstance(result, dict):
        raise AnkiConnectError("AnkiConnect returned an invalid response", "response", 502)
    error = result.get("error")
    if error:
        raise AnkiConnectError(str(error), "anki", 502)
    return {"result": result.get("result")}


def proxy_request(
    payload: dict[str, Any],
    headers: dict[str, str],
    expected_origin: str | None = None,
    endpoint: str | None = None,
    opener: Any = None,
) -> dict[str, Any]:
    validate_local_request(headers, expected_origin)
    return call_anki_connect(payload, endpoint=endpoint, opener=opener)
