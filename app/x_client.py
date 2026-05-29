from __future__ import annotations

import logging
import time
from typing import Any

import requests


LOG = logging.getLogger(__name__)
BASE_URL = "https://api.x.com/2"


class XApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class XClient:
    def __init__(self, bearer_token: str, timeout: int = 20) -> None:
        self.bearer_token = bearer_token
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        last_error = None
        for attempt in range(5):
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code in {429, 500, 502, 503, 504}:
                reset = response.headers.get("x-rate-limit-reset")
                LOG.warning(
                    "X API retryable error status=%s reset=%s attempt=%s body=%s",
                    response.status_code,
                    reset,
                    attempt + 1,
                    response.text[:300],
                )
                if attempt < 4:
                    time.sleep(2 * (attempt + 1))
                    continue
            if response.status_code in {401, 402, 403, 429}:
                raise XApiError(
                    f"X API {response.status_code}: {response.text[:500]}",
                    status_code=response.status_code,
                )
            if response.status_code >= 400:
                last_error = f"X API {response.status_code}: {response.text[:500]}"
                raise XApiError(last_error, status_code=response.status_code)
            return response.json()
        raise XApiError(last_error or "X API request failed")
