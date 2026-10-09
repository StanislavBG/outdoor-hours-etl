"""Shared Open-Meteo HTTP/framing/IO helpers used by the weather and AQ sources."""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from etl.points import Point

MAX_ATTEMPTS = 8
DEFAULT_RETRY_AFTER_S = 60
REQUEST_TIMEOUT_S = 180


class FetchBodyError(Exception):
    """A 2xx response whose body is empty, not JSON, or an Open-Meteo error payload. Retried."""


class RateLimitExhausted(Exception):
    """Open-Meteo reported its request quota as exhausted. Never retried: it will not clear in backoff."""


def _parse_body(r: httpx.Response) -> dict:
    ctype = r.headers.get("Content-Type", "")
    try:
        payload = r.json()
    except ValueError:
        raise FetchBodyError(
            f"unparseable body: status={r.status_code} content-type={ctype!r} body={r.text[:200]!r}"
        ) from None
    if isinstance(payload, dict) and payload.get("error"):
        reason = str(payload.get("reason", ""))
        if "limit" in reason.lower():
            raise RateLimitExhausted(reason)
        raise FetchBodyError(
            f"error body: status={r.status_code} content-type={ctype!r} reason={reason or r.text[:200]!r}"
        )
    return payload


def _backoff(attempt: int) -> float:
    return min(300, 8 * 2**attempt)


def fetch_json(
    client: httpx.Client,
    endpoint: str,
    params: dict,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """GET endpoint and return JSON. Retries 429, 5xx, transport errors and bad 2xx bodies.

    A 2xx body that is empty, non-JSON or `{"error": true}` raises FetchBodyError and is
    retried; a quota "limit" reason raises RateLimitExhausted immediately.

    On 429 the wait is Retry-After when present, else exponential backoff (never both).
    Other 4xx raise immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        wait = _backoff(attempt)
        try:
            r = client.get(endpoint, params=params, timeout=REQUEST_TIMEOUT_S)
        except httpx.TransportError as exc:
            last_exc = exc
        else:
            if r.status_code == 429:
                last_exc = httpx.HTTPStatusError("429 rate-limited", request=r.request, response=r)
                retry_after = r.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = DEFAULT_RETRY_AFTER_S
                    print(f"    429 rate-limited; sleeping {wait:g}s then retrying", flush=True)
            elif r.status_code >= 500:
                last_exc = httpx.HTTPStatusError(f"{r.status_code} server error", request=r.request, response=r)
            else:
                r.raise_for_status()
                try:
                    return _parse_body(r)
                except FetchBodyError as exc:
                    last_exc = exc
        if attempt < MAX_ATTEMPTS - 1:
            sleep(int(wait) if float(wait).is_integer() else wait)
    assert last_exc is not None
    raise last_exc


def to_dataframe(payload: dict, point: Point, extra: dict | None = None) -> pd.DataFrame:
    df = pd.DataFrame(payload["hourly"])
    df["ts_utc"] = pd.to_datetime(df.pop("time"), unit="s", utc=True)
    df["point"] = point.id
    df["region"] = point.region
    for key, value in (extra or {}).items():
        df[key] = value
    cols = ["region", "point", "ts_utc"] + [c for c in df.columns if c not in {"region", "point", "ts_utc"}]
    return df[cols]


def day_chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write via a sibling temp file then os.replace, so a crash never leaves a partial target."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def download_chunks(
    client: httpx.Client,
    point: Point,
    start: date,
    end: date,
    out_dir: Path,
    *,
    max_days: int,
    overwrite: bool,
    delay_s: float,
    fetch: Callable[[date, date], pd.DataFrame],
) -> list[Path]:
    """Shared chunk loop: skip existing files, fetch missing chunks, write atomically."""
    written: list[Path] = []
    for cstart, cend in day_chunks(start, end, max_days):
        fname = f"{cstart.isoformat()}_{cend.isoformat()}.parquet"
        fpath = out_dir / fname
        if fpath.exists() and not overwrite:
            print(f"  skip {point.id} {fname} (exists)", flush=True)
            written.append(fpath)
            continue
        print(f"  fetch {point.id} {cstart}..{cend}", flush=True)
        write_parquet_atomic(fetch(cstart, cend), fpath)
        written.append(fpath)
        time.sleep(delay_s)
    return written
