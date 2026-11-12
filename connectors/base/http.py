"""HTTP access to public institutional sources: host allow-list, rate limit, bounded retries."""

import hashlib
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit

import httpx

log = logging.getLogger("politeia.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
KEPT_HEADERS = ("content-type", "last-modified", "etag", "deprecation", "sunset", "link")


class SourceAccessError(RuntimeError):
    def __init__(self, message: str, url: str, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


@dataclass(frozen=True)
class FetchedResponse:
    url: str
    status: int
    content: bytes
    headers: dict[str, str]
    retrieved_at: datetime
    response_format: str
    sha256: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")


def _format_of(content_type: str) -> str:
    ct = content_type.lower()
    for fmt in ("json", "xml", "csv", "html"):
        if fmt in ct:
            return fmt
    return "binary"


class SourceHttpClient:
    def __init__(
        self,
        allowed_hosts: list[str],
        *,
        max_requests_per_second: float = 5.0,
        max_attempts: int = 4,
        base_backoff_s: float = 1.0,
        timeout_s: float = 30.0,
        user_agent: str = "Politeia/0.1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.allowed_hosts = set(allowed_hosts)
        self.min_interval = 1.0 / max_requests_per_second
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.sleep = sleep
        self._last_request = 0.0
        self.request_count = 0
        self.deprecations: dict[str, str] = {}
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_s),
            headers={"User-Agent": user_agent},
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _check_host(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self.allowed_hosts:
            raise SourceAccessError(f"host not allowed for this source: {parts.hostname}", url)

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            self.sleep(wait)
        self._last_request = time.monotonic()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                try:
                    delta = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                    return min(max(delta, 0.0), 60.0)
                except (TypeError, ValueError):
                    pass
        return self.base_backoff_s * 2 ** (attempt - 1) + random.uniform(0, self.base_backoff_s)

    def get(self, url: str, params: dict | None = None, accept: str = "application/json") -> FetchedResponse:
        full_url = f"{url}?{urlencode(params, doseq=True)}" if params else url
        redirects = 0
        attempt = 0
        while True:
            self._check_host(full_url)
            attempt += 1
            self._throttle()
            self.request_count += 1
            try:
                resp = self._client.get(full_url, headers={"Accept": accept})
            except httpx.TransportError as exc:
                if attempt >= self.max_attempts:
                    raise SourceAccessError(f"network error after {attempt} attempts: {exc}", full_url) from exc
                log.warning("network error, retrying", extra={"url": full_url, "attempt": attempt})
                self.sleep(self._backoff(attempt, None))
                continue

            if resp.is_redirect and redirects < 3:
                redirects += 1
                full_url = str(resp.next_request.url) if resp.next_request else full_url
                attempt -= 1
                continue
            if resp.status_code in RETRYABLE_STATUS:
                if attempt >= self.max_attempts:
                    raise SourceAccessError(
                        f"HTTP {resp.status_code} after {attempt} attempts", full_url, resp.status_code
                    )
                delay = self._backoff(attempt, resp.headers.get("retry-after"))
                log.warning("retryable status", extra={"url": full_url, "status": resp.status_code, "delay": delay})
                self.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise SourceAccessError(f"HTTP {resp.status_code}", full_url, resp.status_code)

            headers = {k: v for k, v in resp.headers.items() if k.lower() in KEPT_HEADERS}
            if "deprecation" in headers:
                self.deprecations[url] = headers.get("sunset", "")
            return FetchedResponse(
                url=full_url,
                status=resp.status_code,
                content=resp.content,
                headers=headers,
                retrieved_at=datetime.now(UTC),
                response_format=_format_of(resp.headers.get("content-type", "")),
            )
