"""Source-derived parcel search protocol. No delivery-change endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any, Iterable
from uuid import uuid4

import httpx

API_BASE = "https://member.kms.kuronekoyamato.co.jp/api/"
SEARCH_PATH = "receive_parcel/v1/getParcelInfo"
SEARCH_PAGE = "https://member.kms.kuronekoyamato.co.jp/parcel/search"


class YamatoError(Exception):
    """A failure with machine-readable details, including the server response."""

    def __init__(self, kind: str, message: str, **details: Any):
        super().__init__(message)
        self.details = {"kind": kind, "message": message, **details}


def normalize_tracking_number(number: str) -> str:
    """Accept ASCII digits with optional conventional grouping hyphens."""
    if not isinstance(number, str) or not re.fullmatch(r"(?:[0-9]{11,12}|[0-9]{4}-[0-9]{4}-[0-9]{3,4})", number):
        raise YamatoError("validation", "Tracking numbers must contain 11 or 12 ASCII digits, optionally grouped with hyphens.")
    normalized = number.replace("-", "")
    if int(normalized[:-1]) % 7 != int(normalized[-1]):
        raise YamatoError("validation", "Tracking number check digit does not match the Yamato modulo-7 rule.")
    return normalized


class YamatoClient:
    """One cookie-preserving HTTP session; requests are never retried."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = 20.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise YamatoError("validation", "Timeout must be a positive finite number.")
        self.timeout = timeout
        self.device_id = str(uuid4())
        self._owns_client = client is None
        self.client = client if client is not None else httpx.Client(follow_redirects=False)

    def __enter__(self) -> YamatoClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def track(self, numbers: Iterable[str]) -> dict[str, Any]:
        normalized = [normalize_tracking_number(number) for number in numbers]
        if not normalized:
            raise YamatoError("validation", "Supply at least one tracking number. Use probe for an empty-list request.")
        if len(normalized) > 100:
            raise YamatoError("validation", "Search accepts at most 100 tracking numbers.")
        return self._search(normalized)

    def probe(self) -> dict[str, Any]:
        """Submit an empty shipment list only. Acceptance does not prove tracking works."""
        return self._search([])

    def detail(self, number: str) -> dict[str, Any]:
        return self._request(
            "receive_parcel/v1/getParcelDetailInfo",
            {"nmtJho": {"okjNo": normalize_tracking_number(number), "uktHasKbn": "01"}},
            "NRCWBRP0610",
        )

    def slots(self, number: str) -> dict[str, Any]:
        body = self.detail(number)
        result = body.get("result")
        if not isinstance(result, dict):
            raise YamatoError("protocol", "Expected detail result to be an object.", response=body)
        eligibility = result.get("henKahHntKkaJho") or {}
        eligibility_flag = eligibility.get("jtkNaiUktHenKahFlg") if isinstance(eligibility, dict) else None
        return {
            "nmtJho": result.get("nmtJho"),
            "eligible_for_date_change": eligibility_flag == "1",
            "henKahHntKkaJho": result.get("henKahHntKkaJho"),
            "date_change_eligibility": eligibility_flag,
            "scnHttKboDayJhoLst": result.get("scnHttKboDayJhoLst") or [],
            "scnHttKboBsyJhoLst": result.get("scnHttKboBsyJhoLst") or [],
            "note": "Raw server options only. Date changes require eligible_for_date_change=true and date/time availability flags equal to 1.",
        }

    def _search(self, numbers: list[str]) -> dict[str, Any]:
        payload = {
            "myNmtJho": {"nmtJhoLst": [
                {"okjNo": number, "uktHasKbn": "01", "kroMchFlg": "0"}
                for number in numbers
            ]},
        }
        return self._request(SEARCH_PATH, payload, "NRCWBRP0200")

    def _request(self, path: str, payload: dict[str, Any], page_id: str) -> dict[str, Any]:
        payload["ktuJho"] = {
            "iriTs": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "tnmSbtCd": "1",
        }
        headers = {
            "X-SYSTEM-ID": "NRC", "X-PG_ID": page_id, "X-PG-ID": page_id,
            "Accept": "application/json", "Origin": "https://member.kms.kuronekoyamato.co.jp",
            "Referer": SEARCH_PAGE,
        }
        token = self.client.cookies.get("token")
        if token:
            headers["Authorization"] = "Bearer " + token
            account_id = self.client.cookies.get("web_service_id")
            if account_id:
                payload["ktuJho"]["kroId"] = account_id
        xsrf_token = self.client.cookies.get("XSRF-TOKEN")
        if xsrf_token:
            headers["X-XSRF-TOKEN"] = xsrf_token
        try:
            response = self.client.post(
                API_BASE + path, json=payload, headers=headers,
                params={"X-NEKO-TRACE": str(uuid4()), "X-NEKO-DEVICE": self.device_id},
                timeout=self.timeout, follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise YamatoError("transport", str(exc), exception=type(exc).__name__) from exc
        try:
            body = response.json()
        except ValueError:
            body = response.text
        context = {"http_status": response.status_code, "response": body}
        if not 200 <= response.status_code < 300:
            raise YamatoError("http", "Yamato returned an unsuccessful HTTP status.", **context)
        if not isinstance(body, dict):
            raise YamatoError("protocol", "Expected a JSON object from Yamato.", **context)
        if body.get("errors"):
            raise YamatoError("application", "Yamato returned application errors.", **context)
        if "result" not in body:
            raise YamatoError("protocol", "Yamato response did not contain result.", **context)
        return body
