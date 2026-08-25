"""DNS-based target resolution for the CHECK24 LLM Proxy."""

import asyncio
import random
import time

import dns.resolver
import httpx


class LLMProxyFailoverTransport(httpx.AsyncHTTPTransport):
    """Resolve proxy targets through DNS TXT and retry another target on failure."""

    def __init__(self, targets_domain: str, ttl_seconds: int = 10):
        super().__init__()
        self._targets_domain = targets_domain
        self._ttl_seconds = ttl_seconds
        self._targets: list[str] = []
        self._cache_expiry = 0.0

    async def _get_targets(self) -> list[str]:
        now = time.monotonic()
        if self._targets and now < self._cache_expiry:
            return list(self._targets)

        try:
            records = await asyncio.to_thread(
                dns.resolver.resolve, self._targets_domain, "TXT"
            )
            self._targets = [b"".join(record.strings).decode() for record in records]
            self._cache_expiry = now + self._ttl_seconds
        except Exception:
            if not self._targets:
                raise
        return list(self._targets)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        targets = await self._get_targets()
        random.shuffle(targets)
        last_error: Exception | None = None

        for target in targets:
            target_url = httpx.URL(target)
            new_url = request.url.copy_with(
                scheme=target_url.scheme,
                host=target_url.host,
                port=target_url.port,
            )
            if target_url.path:
                new_url = new_url.copy_with(
                    path=target_url.path.rstrip("/") + request.url.path
                )

            headers = httpx.Headers(request.headers)
            headers.pop("host", None)
            cloned_request = httpx.Request(
                request.method,
                new_url,
                headers=headers,
                content=request.content,
                extensions=request.extensions,
            )
            try:
                response = await super().handle_async_request(cloned_request)
                if response.status_code >= 500:
                    await response.aclose()
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code}",
                        request=cloned_request,
                        response=response,
                    )
                return response
            except Exception as error:
                last_error = error

        raise httpx.ConnectError(f"All LLM Proxy targets failed: {last_error}")
