from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class HTTPError(RuntimeError):
    pass


@dataclass(slots=True)
class JsonHttpClient:
    timeout: int = 30
    user_agent: str = "LeadFlow-Agent/0.1 (+https://github.com/)"

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            query = urllib.parse.urlencode(clean)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        req_headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, headers=req_headers, method="GET")
        return self._open_json(request)

    def post_json(self, url: str, *, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        return self._open_json(request)

    def _open_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = raw[:1000]
            raise HTTPError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise HTTPError(f"Network error: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPError(f"Provider returned invalid JSON: {raw[:500]}") from exc
        if not isinstance(data, dict):
            raise HTTPError("Provider returned an unexpected JSON shape.")
        return data
