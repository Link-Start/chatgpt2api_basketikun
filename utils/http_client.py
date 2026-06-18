from __future__ import annotations

import os
from typing import Any

from curl_cffi import requests as curl_requests


DEFAULT_BACKEND = "curl_cffi"
DEFAULT_TIMEOUT = 30.0

FINGERPRINT_HEADERS: dict[str, dict[str, str]] = {
    "chrome": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "sec-ch-ua": '"Chromium";v="145", "Google Chrome";v="145", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    "edge": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "sec-ch-ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
}


class HttpResponse:
    def __init__(self, raw: Any):
        self.raw = raw

    @property
    def is_success(self) -> bool:
        return 200 <= int(getattr(self.raw, "status_code", 0) or 0) < 400

    @property
    def status(self) -> int:
        return int(getattr(self.raw, "status_code", 0) or 0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)


class HttpClient:
    def __init__(
        self,
        *,
        proxy: str = "",
        verify: bool = True,
        fingerprint: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        follow_redirects: bool = True,
        backend: str = "",
        http2: bool = True,
    ) -> None:
        self.backend = _normalize_backend(backend)
        self.fingerprint = str(fingerprint or "").strip()
        self.follow_redirects = follow_redirects
        self.timeout = float(timeout or DEFAULT_TIMEOUT)
        self.proxy = str(proxy or "").strip()
        self.verify = verify
        if self.backend == "httpx":
            self.client = self._build_httpx_client(headers or {}, http2)
        else:
            self.client = self._build_curl_client(headers or {})
        self.headers = self.client.headers
        self.cookies = self.client.cookies

    def request(
        self,
        method: str,
        url: str,
        *,
        follow_redirects: bool | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        follow = self.follow_redirects if follow_redirects is None else follow_redirects
        if self.backend == "httpx":
            raw = self.client.request(
                method,
                url,
                follow_redirects=follow,
                timeout=float(timeout or self.timeout),
                **kwargs,
            )
        else:
            raw = self.client.request(
                method,
                url,
                allow_redirects=follow,
                timeout=float(timeout or self.timeout),
                **kwargs,
            )
        return HttpResponse(raw)

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self.client.close()

    def _build_curl_client(self, headers: dict[str, str]):
        kwargs: dict[str, Any] = {"verify": self.verify}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        if self.fingerprint:
            kwargs["impersonate"] = self.fingerprint
        session = curl_requests.Session(**kwargs)
        session.headers.update(browser_headers(self.fingerprint))
        session.headers.update(headers)
        return session

    def _build_httpx_client(self, headers: dict[str, str], http2: bool):
        import httpx

        merged_headers = browser_headers(self.fingerprint)
        merged_headers.update(headers)
        try:
            return httpx.Client(
                headers=merged_headers,
                verify=self.verify,
                proxy=self.proxy or None,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                http2=http2,
                trust_env=False,
            )
        except ImportError:
            return httpx.Client(
                headers=merged_headers,
                verify=self.verify,
                proxy=self.proxy or None,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                http2=False,
                trust_env=False,
            )


def request(method: str, url: str, **kwargs: Any) -> HttpResponse:
    client = HttpClient(
        proxy=str(kwargs.pop("proxy", "") or ""),
        verify=bool(kwargs.pop("verify", True)),
        fingerprint=str(kwargs.pop("fingerprint", "") or ""),
        headers=kwargs.pop("base_headers", None),
        timeout=float(kwargs.pop("client_timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT),
        follow_redirects=bool(kwargs.pop("follow_redirects", True)),
        backend=str(kwargs.pop("backend", "") or ""),
    )
    try:
        return client.request(method, url, **kwargs)
    finally:
        client.close()


def get(url: str, **kwargs: Any) -> HttpResponse:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> HttpResponse:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs: Any) -> HttpResponse:
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs: Any) -> HttpResponse:
    return request("DELETE", url, **kwargs)


def browser_headers(fingerprint: str = "") -> dict[str, str]:
    value = str(fingerprint or "").strip().lower()
    if value.startswith("edge"):
        return dict(FINGERPRINT_HEADERS["edge"])
    if value.startswith("chrome"):
        return dict(FINGERPRINT_HEADERS["chrome"])
    return {}


def _normalize_backend(value: str = "") -> str:
    backend = str(value or os.getenv("CHATGPT2API_HTTP_BACKEND") or DEFAULT_BACKEND).strip().lower()
    return "httpx" if backend == "httpx" else "curl_cffi"
