"""
Graham Research API
===================

Integrated role: live company analysis and thesis tracking only. Responses
from this module are never admissible as historical backtest observations.

Install:
    pip install fastapi uvicorn httpx

Environment variables:
    PUBLIC_BASE_URL=https://your-public-domain.com
    GRAHAM_API_KEY=choose-a-long-random-password
    GRAHAM_REQUIRE_AUTH=1
    SEC_USER_AGENT=YourAppName/1.0 your-email@example.com
    GRAHAM_COMPANY_CACHE_MAX_ENTRIES=128
    GRAHAM_COMPANY_CACHE_TTL_SECONDS=3600
    GRAHAM_SEC_MIN_REQUEST_GAP_SECONDS=0.12
    GRAHAM_DB_PATH=./graham_theses.db

Run from the integrated package:
    graham-live
    # or: uvicorn graham_research.live_app:app --host 127.0.0.1 --port 8000

After deployment, your OpenAPI schema will be:
    https://your-public-domain.com/openapi.json

Analysis parameters:
    history_years=10 retrieves and returns annual periods
    normalization_years=7 selects the EPS normalization window
    detail=false returns compact annual-history provenance
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

LIVE_ANALYSIS_ONLY = True
HISTORICAL_BACKTEST_ELIGIBLE = False

PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "https://replace-with-your-public-domain.com",
).rstrip("/")

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "GrahamResearchApp/1.0 your-email@example.com",
)

EXPECTED_API_KEY = os.getenv("GRAHAM_API_KEY", "")
GRAHAM_REQUIRE_AUTH = os.getenv("GRAHAM_REQUIRE_AUTH", "1")

if GRAHAM_REQUIRE_AUTH != "0" and not EXPECTED_API_KEY:
    raise RuntimeError(
        "Refusing to start an unauthenticated public endpoint. Set "
        "GRAHAM_API_KEY, or use GRAHAM_REQUIRE_AUTH=0 for local testing only."
    )

COMPANY_CACHE_MAX_ENTRIES = int(
    os.getenv("GRAHAM_COMPANY_CACHE_MAX_ENTRIES", "128")
)
COMPANY_CACHE_TTL_SECONDS = float(
    os.getenv("GRAHAM_COMPANY_CACHE_TTL_SECONDS", "3600")
)
SEC_MIN_REQUEST_GAP_SECONDS = float(
    os.getenv("GRAHAM_SEC_MIN_REQUEST_GAP_SECONDS", "0.12")
)
GRAHAM_DB_PATH = os.getenv("GRAHAM_DB_PATH", "./graham_theses.db")

SEC_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}

# Series denominated in a currency. Share counts are excluded because
# `shares` is the correct unit for them, not a foreign currency.
MONETARY_HISTORY_KEYS = frozenset({
    "eps",
    "revenue",
    "net_income",
    "operating_income",
    "operating_cash_flow",
    "capital_expenditures",
})

# XBRL units that are dimensionless or a count. Encountering one of these is
# not a currency mismatch.
NON_CURRENCY_UNITS = frozenset({"shares", "pure", "Rate", "Y", "D"})


def _currency_of(unit: str) -> str:
    """Return the currency portion of a unit such as ``USD/shares``."""
    return unit.split("/", 1)[0]


http_client: httpx.AsyncClient | None = None


def database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(GRAHAM_DB_PATH)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    except Exception:
        connection.close()
        raise
    return connection


def initialize_database() -> None:
    with closing(database_connection()) as connection:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS thesis (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    company_name TEXT,
                    created_at TEXT NOT NULL,
                    is_paper INTEGER NOT NULL,
                    price_at_entry REAL NOT NULL,
                    value_estimate_low REAL NOT NULL,
                    value_estimate_high REAL NOT NULL,
                    method TEXT NOT NULL,
                    thesis_text TEXT NOT NULL,
                    circle_of_competence TEXT NOT NULL,
                    key_assumptions TEXT NOT NULL,
                    falsification TEXT NOT NULL,
                    analysis_snapshot TEXT,
                    snapshot_source TEXT,
                    closed_at TEXT,
                    price_at_exit REAL,
                    exit_reason TEXT,
                    reasoning_was_correct INTEGER
                );

                CREATE TABLE IF NOT EXISTS thesis_review (
                    id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES thesis(id),
                    created_at TEXT NOT NULL,
                    note TEXT NOT NULL,
                    conditions_met TEXT
                );
            """)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global http_client
    await asyncio.to_thread(initialize_database)
    http_client = httpx.AsyncClient(
        headers=SEC_HEADERS,
        timeout=30,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10),
    )
    try:
        yield
    finally:
        await http_client.aclose()
        http_client = None


app = FastAPI(
    title="Graham Research API",
    version="1.0.0",
    description=(
        "Retrieves SEC company facts and performs mechanical "
        "Graham-style calculations. It does not produce buy, sell, "
        "or hold recommendations."
    ),
    servers=[{"url": PUBLIC_BASE_URL}],
    lifespan=lifespan,
)

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------

async def authorize(
    supplied_key: str | None = Security(api_key_header),
) -> None:
    """
    Require an API key unless local testing explicitly disables auth.
    """
    if EXPECTED_API_KEY and (
        not supplied_key
        or not secrets.compare_digest(str(supplied_key), EXPECTED_API_KEY)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )


# ---------------------------------------------------------------------
# SEC data retrieval and caching
# ---------------------------------------------------------------------

ticker_cache: dict[str, dict[str, Any]] = {}
ticker_cache_time = 0.0
ticker_cache_lock = asyncio.Lock()

class BoundedTTLCache:
    def __init__(self, max_entries: int, ttl_seconds: float):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = (
            OrderedDict()
        )

    def get(self, key: str) -> dict[str, Any] | None:
        cached = self._items.get(key)
        if cached is None:
            return None
        if time.time() - cached[0] >= self.ttl_seconds:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return cached[1]

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._items[key] = (time.time(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)


company_cache = BoundedTTLCache(
    COMPANY_CACHE_MAX_ENTRIES,
    COMPANY_CACHE_TTL_SECONDS,
)
company_cache_lock = asyncio.Lock()
sec_request_semaphore = asyncio.Semaphore(5)
sec_pacer_lock = asyncio.Lock()
last_sec_request_time = 0.0


async def get_json(url: str) -> dict[str, Any]:
    global last_sec_request_time
    try:
        if http_client is None:
            raise httpx.RequestError("HTTP client is not running")

        for attempt in range(3):
            async with sec_request_semaphore:
                async with sec_pacer_lock:
                    delay = (
                        last_sec_request_time
                        + SEC_MIN_REQUEST_GAP_SECONDS
                        - time.monotonic()
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    last_sec_request_time = time.monotonic()
                response = await http_client.get(url)

            if response.status_code != 429 or attempt == 2:
                response.raise_for_status()
                return response.json()
            await asyncio.sleep(2 ** attempt)

        raise AssertionError("unreachable")

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"SEC returned HTTP {exc.response.status_code}. "
                "Verify the ticker and SEC User-Agent."
            ),
        ) from exc

    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve or parse SEC data: {exc}",
        ) from exc


async def get_ticker_map() -> dict[str, dict[str, Any]]:
    global ticker_cache
    global ticker_cache_time

    # Refresh once per day.
    if ticker_cache and time.time() - ticker_cache_time < 86_400:
        return ticker_cache

    async with ticker_cache_lock:
        if ticker_cache and time.time() - ticker_cache_time < 86_400:
            return ticker_cache

        raw = await get_json(
            "https://www.sec.gov/files/company_tickers.json"
        )

        ticker_cache = {
            row["ticker"].upper(): {
                "ticker": row["ticker"].upper(),
                "name": row["title"],
                "cik": str(row["cik_str"]).zfill(10),
            }
            for row in raw.values()
        }

        ticker_cache_time = time.time()
        return ticker_cache


async def get_company_facts(cik: str) -> dict[str, Any]:
    # Cache company facts using the configured bounded TTL.
    cached = company_cache.get(cik)
    if cached is not None:
        return cached

    async with company_cache_lock:
        cached = company_cache.get(cik)

        if cached is not None:
            return cached

        facts = await get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        )

        company_cache.set(cik, facts)
        return facts


# ---------------------------------------------------------------------
# SEC fact processing
# ---------------------------------------------------------------------

def filing_url(cik: str, accession_number: str | None) -> str | None:
    if not accession_number:
        return None

    accession_path = accession_number.replace("-", "")

    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{accession_path}/"
        f"{accession_number}-index.html"
    )


def unit_items(
    company_facts: dict[str, Any],
    taxonomy: str,
    tag: str,
    preferred_units: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    fact = (
        company_facts
        .get("facts", {})
        .get(taxonomy, {})
        .get(tag, {})
    )

    units = fact.get("units", {})

    for unit in preferred_units:
        if unit in units:
            return units[unit], unit, False

    # Use the first available unit only when preferred units are absent.
    for unit, values in units.items():
        return values, unit, True

    return [], None, False


class AnnualSeries(list[dict[str, Any]]):
    """Annual fact rows with continuity metadata used by the API serializer."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> None:
        super().__init__(rows)
        self.metadata = metadata


def annual_series(
    company_facts: dict[str, Any],
    cik: str,
    taxonomy: str,
    tags: tuple[str, ...],
    units: tuple[str, ...],
    maximum_years: int = 10,
) -> AnnualSeries:
    """
    Collect annual-duration facts from 10-K filings.

    Facts are grouped by period end date rather than SEC fiscal-year
    metadata because comparative years may appear in the same filing.
    """
    selected: dict[str, dict[str, Any]] = {}

    for priority, tag in enumerate(tags):
        items, unit_used, used_fallback = unit_items(
            company_facts,
            taxonomy,
            tag,
            units,
        )
        for item in items:
            if item.get("form") not in {"10-K", "10-K/A"}:
                continue

            value = item.get("val")
            start = item.get("start")
            end = item.get("end")

            if not isinstance(value, (int, float)) or not start or not end:
                continue

            try:
                duration = (
                    date.fromisoformat(end) -
                    date.fromisoformat(start)
                ).days
            except ValueError:
                continue

            # Accommodate 52-week, 53-week, and unusual fiscal years.
            if duration < 300 or duration > 430:
                continue

            candidate = {
                "year": int(end[:4]),
                "start": start,
                "end": end,
                "value": float(value),
                "tag": tag,
                "form": item.get("form"),
                "filed": item.get("filed"),
                "accession_number": item.get("accn"),
                "source_url": filing_url(cik, item.get("accn")),
                "unit": unit_used,
                "unit_fallback": used_fallback,
                "_priority": priority,
            }

            existing = selected.get(end)

            if existing is None:
                selected[end] = candidate
                continue

            better_tag = priority < existing["_priority"]
            same_tag_newer_filing = (
                priority == existing["_priority"]
                and str(candidate.get("filed", "")) >
                str(existing.get("filed", ""))
            )

            if better_tag or same_tag_newer_filing:
                selected[end] = candidate

    result = sorted(
        selected.values(),
        key=lambda row: row["end"],
    )[-maximum_years:]

    original_years = [row["year"] for row in result]
    dropped_years: list[int] = []

    # A distant old comparative run can be pulled into an otherwise recent
    # run by the observation-count slice. Walk backward from the latest fact
    # and drop everything before the first multi-year hole. A one-year
    # internal gap is retained and explicitly disclosed below.
    for index in range(len(result) - 1, 0, -1):
        if result[index]["year"] - result[index - 1]["year"] > 2:
            dropped_years = [row["year"] for row in result[:index]]
            result = result[index:]
            break

    for row in result:
        row.pop("_priority", None)

    years = [row["year"] for row in result]
    if years:
        present_years = set(years)
        missing_years = [
            year
            for year in range(min(years), max(years) + 1)
            if year not in present_years
        ]
        years_covered: list[int] = [min(years), max(years)]
    else:
        missing_years = []
        years_covered = []

    return AnnualSeries(
        result,
        {
            "years_covered": years_covered,
            "missing_years": missing_years,
            "is_contiguous": not missing_years,
            "dropped_years": dropped_years,
            "truncated_before_year": (
                min(years) if dropped_years and years else None
            ),
            "original_years": original_years,
        },
    )


def latest_instant(
    company_facts: dict[str, Any],
    cik: str,
    taxonomy: str,
    tags: tuple[str, ...],
    units: tuple[str, ...],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []

    for priority, tag in enumerate(tags):
        items, unit_used, used_fallback = unit_items(
            company_facts,
            taxonomy,
            tag,
            units,
        )
        for item in items:
            if item.get("form") not in {"10-K", "10-K/A"}:
                continue

            value = item.get("val")
            end = item.get("end")

            if not isinstance(value, (int, float)) or not end:
                continue

            candidates.append({
                "end": end,
                "value": float(value),
                "tag": tag,
                "form": item.get("form"),
                "filed": item.get("filed"),
                "accession_number": item.get("accn"),
                "source_url": filing_url(cik, item.get("accn")),
                "unit": unit_used,
                "unit_fallback": used_fallback,
                "_priority": priority,
            })

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            row["end"],
            str(row.get("filed", "")),
            -row["_priority"],
        )
    )

    result = candidates[-1]
    result.pop("_priority", None)
    return result


def sum_instants(
    company_facts: dict[str, Any],
    cik: str,
    taxonomy: str,
    tags: tuple[str, ...],
    units: tuple[str, ...],
    filing_url_fn: Any = None,
) -> dict[str, Any] | None:
    """Sum distinct same-period instant facts, such as share classes."""
    candidates: list[dict[str, Any]] = []
    url_builder = filing_url_fn or filing_url

    for priority, tag in enumerate(tags):
        items, unit_used, used_fallback = unit_items(
            company_facts, taxonomy, tag, units
        )
        for item in items:
            if item.get("form") not in {"10-K", "10-K/A"}:
                continue

            value = item.get("val")
            end = item.get("end")
            if not isinstance(value, (int, float)) or not end:
                continue

            candidates.append({
                "end": end,
                "value": float(value),
                "tag": tag,
                "form": item.get("form"),
                "filed": item.get("filed"),
                "accession_number": item.get("accn"),
                "source_url": url_builder(cik, item.get("accn")),
                "unit": unit_used,
                "unit_fallback": used_fallback,
                "_priority": priority,
            })

    if not candidates:
        return None

    latest_end = max(row["end"] for row in candidates)
    candidates = [row for row in candidates if row["end"] == latest_end]
    best_priority = min(row["_priority"] for row in candidates)
    candidates = [
        row for row in candidates if row["_priority"] == best_priority
    ]
    latest_filed = max(str(row.get("filed", "")) for row in candidates)
    candidates = [
        row
        for row in candidates
        if str(row.get("filed", "")) == latest_filed
    ]

    distinct: dict[float, dict[str, Any]] = {}
    for row in candidates:
        distinct.setdefault(row["value"], row)

    class_values = list(distinct)
    result = next(iter(distinct.values())).copy()
    result["value"] = float(sum(class_values))
    result["share_classes_summed"] = len(class_values)
    result["class_values"] = class_values
    result.pop("_priority", None)
    return result


def record_value(record: dict[str, Any] | None) -> float | None:
    if not record:
        return None
    return record.get("value")


def last_record(
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return records[-1] if records else None


def safe_divide(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None

    return numerator / denominator


def rounded(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None

    return round(value, digits)


def make_check(
    name: str,
    value: float | int | None,
    passes: bool | None,
    rule: str,
) -> dict[str, Any]:
    if passes is None:
        status = "not_available"
    else:
        status = "pass" if passes else "fail"

    return {
        "name": name,
        "status": status,
        "value": value,
        "rule": rule,
    }


# Severity contract:
#   high   — a returned figure is likely materially wrong. The caller is
#            instructed to DISCARD the outputs named in `affects`. A false
#            positive here destroys an analysis silently. Any warning that
#            can fire on an ordinary company does not belong at this level.
#   medium — a figure is unavailable, or a caveat changes interpretation.
#   low    — a standing model-scope caveat present on every response.
def make_warning(
    code: str,
    severity: str,
    message: str,
    affects: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "affects": affects or [],
    }


def tag_appears_anywhere(
    company_facts: dict[str, Any],
    taxonomy: str,
    tags: tuple[str, ...],
    record: dict[str, Any] | None = None,
) -> str:
    if record is not None:
        return "reported"

    taxonomy_facts = company_facts.get("facts", {}).get(taxonomy, {})
    tag_present = any(
        bool(taxonomy_facts.get(tag, {}).get("units", {}))
        for tag in tags
    )
    return "tag_present_no_annual_value" if tag_present else "tag_absent"


def with_basis(
    record: dict[str, Any] | None,
    basis: str,
) -> dict[str, Any]:
    result = dict(record) if record else {"value": None}
    result["basis"] = "reported" if record is not None else basis
    return result


# ---------------------------------------------------------------------
# Analysis endpoint
# ---------------------------------------------------------------------

@app.get(
    "/analyze/{ticker}",
    operation_id="analyzeCompany",
    summary="Run a mechanical Graham-style analysis",
    description=(
        "Retrieves SEC financial facts and calculates historical "
        "profitability, liquidity, valuation, Graham Number, free cash "
        "flow, leverage, and a margin-of-safety price. The caller must "
        "provide the current market price. mechanical_result is an object "
        "whose verdict distinguishes failed checks from incomplete data "
        "and lists failed and unavailable required checks."
    ),
)
async def analyze_company(
    ticker: str,
    price: float = Query(
        ...,
        gt=0,
        description="Current share price supplied by the user.",
    ),
    margin_of_safety: float = Query(
        0.30,
        ge=0,
        le=0.80,
        description="Required discount from mechanical value.",
    ),
    earnings_multiple: float = Query(
        10.0,
        ge=4,
        le=25,
        description="Multiple applied to normalized EPS.",
    ),
    history_years: int = Query(
        10,
        ge=5,
        le=15,
        description="Maximum number of annual periods to retrieve and return.",
    ),
    normalization_years: int = Query(
        7,
        ge=5,
        le=15,
        description=(
            "Most recent annual EPS periods used for normalization and "
            "profitability history."
        ),
    ),
    detail: bool = Query(
        False,
        description=(
            "Return full per-row annual provenance instead of compact, "
            "series-level provenance."
        ),
    ),
    _: None = Depends(authorize),
) -> dict[str, Any]:
    normalized_ticker = ticker.strip().upper()
    requested_normalization_years = normalization_years
    normalization_years = min(normalization_years, history_years)

    ticker_map = await get_ticker_map()
    company = ticker_map.get(normalized_ticker)

    if not company:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker {normalized_ticker} was not found.",
        )

    cik = company["cik"]
    facts = await get_company_facts(cik)

    # Income and cash-flow history.
    eps_history = annual_series(
        facts,
        cik,
        "us-gaap",
        (
            "EarningsPerShareDiluted",
            "EarningsPerShareBasicAndDiluted",
            "EarningsPerShareBasic",
        ),
        ("USD/shares", "USD-per-shares"),
        history_years,
    )

    revenue_history = annual_series(
        facts,
        cik,
        "us-gaap",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
        ("USD",),
        history_years,
    )

    net_income_history = annual_series(
        facts,
        cik,
        "us-gaap",
        ("NetIncomeLoss", "ProfitLoss"),
        ("USD",),
        history_years,
    )

    operating_income_history = annual_series(
        facts,
        cik,
        "us-gaap",
        ("OperatingIncomeLoss",),
        ("USD",),
        history_years,
    )

    operating_cash_flow_history = annual_series(
        facts,
        cik,
        "us-gaap",
        ("NetCashProvidedByUsedInOperatingActivities",),
        ("USD",),
        history_years,
    )

    capex_history = annual_series(
        facts,
        cik,
        "us-gaap",
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
        ("USD",),
        history_years,
    )

    diluted_shares_history = annual_series(
        facts,
        cik,
        "us-gaap",
        ("WeightedAverageNumberOfDilutedSharesOutstanding",),
        ("shares",),
        history_years,
    )

    interest_expense_history = annual_series(
        facts,
        cik,
        "us-gaap",
        (
            "InterestExpenseNonOperating",
            "InterestAndDebtExpense",
            "InterestExpense",
        ),
        ("USD",),
        history_years,
    )

    # Latest balance-sheet values.
    current_assets_tags = ("AssetsCurrent",)
    current_assets_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        current_assets_tags,
        ("USD",),
    )

    current_liabilities_tags = ("LiabilitiesCurrent",)
    current_liabilities_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        current_liabilities_tags,
        ("USD",),
    )

    cash_tags = (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    )
    cash_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        cash_tags,
        ("USD",),
    )

    equity_tags = (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    )
    equity_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        equity_tags,
        ("USD",),
    )

    common_shares_tags = ("EntityCommonStockSharesOutstanding",)
    common_shares_raw = sum_instants(
        facts,
        cik,
        "dei",
        common_shares_tags,
        ("shares",),
        filing_url,
    )

    current_debt_tags = (
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "DebtCurrent",
    )
    current_debt_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        current_debt_tags,
        ("USD",),
    )

    noncurrent_debt_tags = (
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "LongTermDebt",
    )
    noncurrent_debt_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        noncurrent_debt_tags,
        ("USD",),
    )

    short_term_borrowings_tags = (
        "ShortTermBorrowings",
        "OtherShortTermBorrowings",
        "CommercialPaper",
    )
    short_term_borrowings_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        short_term_borrowings_tags,
        ("USD",),
    )

    total_liabilities_tags = ("Liabilities",)
    total_liabilities_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        total_liabilities_tags,
        ("USD",),
    )
    goodwill_tags = ("Goodwill",)
    goodwill_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        goodwill_tags,
        ("USD",),
    )
    intangible_assets_tags = (
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    )
    intangible_assets_raw = latest_instant(
        facts,
        cik,
        "us-gaap",
        intangible_assets_tags,
        ("USD",),
    )

    def balance_sheet_record(
        raw: dict[str, Any] | None,
        taxonomy: str,
        tags: tuple[str, ...],
    ) -> dict[str, Any]:
        return with_basis(
            raw,
            tag_appears_anywhere(facts, taxonomy, tags, raw),
        )

    current_assets_record = balance_sheet_record(
        current_assets_raw, "us-gaap", current_assets_tags
    )
    current_liabilities_record = balance_sheet_record(
        current_liabilities_raw, "us-gaap", current_liabilities_tags
    )
    cash_record = balance_sheet_record(cash_raw, "us-gaap", cash_tags)
    equity_record = balance_sheet_record(equity_raw, "us-gaap", equity_tags)
    common_shares_record = balance_sheet_record(
        common_shares_raw, "dei", common_shares_tags
    )
    current_debt_record = balance_sheet_record(
        current_debt_raw, "us-gaap", current_debt_tags
    )
    noncurrent_debt_record = balance_sheet_record(
        noncurrent_debt_raw, "us-gaap", noncurrent_debt_tags
    )
    short_term_borrowings_record = balance_sheet_record(
        short_term_borrowings_raw, "us-gaap", short_term_borrowings_tags
    )
    total_liabilities_record = with_basis(
        total_liabilities_raw,
        tag_appears_anywhere(
            facts,
            "us-gaap",
            total_liabilities_tags,
            total_liabilities_raw,
        ),
    )
    goodwill_record = with_basis(
        goodwill_raw,
        tag_appears_anywhere(
            facts, "us-gaap", goodwill_tags, goodwill_raw
        ),
    )
    intangible_assets_record = with_basis(
        intangible_assets_raw,
        tag_appears_anywhere(
            facts,
            "us-gaap",
            intangible_assets_tags,
            intangible_assets_raw,
        ),
    )

    # Values used in calculations.
    recent_eps_rows = eps_history[-normalization_years:]
    recent_eps = [row["value"] for row in recent_eps_rows]

    normalized_eps = median(recent_eps) if recent_eps else None
    profitable_years = sum(value > 0 for value in recent_eps)
    latest_year_eps = recent_eps[-1] if recent_eps else None
    ratio_to_latest = (
        normalized_eps / latest_year_eps
        if normalized_eps is not None
        and latest_year_eps is not None
        and latest_year_eps > 0
        else None
    )
    normalization = {
        "method": "median",
        "description": (
            f"Median of {len(recent_eps)} annual diluted EPS observations "
            f"from fiscal years {recent_eps_rows[0]['year']}-"
            f"{recent_eps_rows[-1]['year']}."
            if recent_eps_rows
            else "Median could not be calculated because no usable annual "
            "diluted EPS observations were found."
        ),
        "window_years": len(recent_eps),
        "fiscal_years": [row["year"] for row in recent_eps_rows],
        "values_used": recent_eps,
        "latest_year_eps": latest_year_eps,
        "ratio_to_latest": ratio_to_latest,
    }

    latest_diluted_shares = record_value(
        last_record(diluted_shares_history)
    )
    reported_common_shares = record_value(common_shares_record)

    shares_for_book_value = (
        reported_common_shares
        if reported_common_shares and reported_common_shares > 0
        else latest_diluted_shares
    )
    shares_record_for_book = (
        common_shares_record
        if reported_common_shares and reported_common_shares > 0
        else last_record(diluted_shares_history)
    )

    equity = record_value(equity_record)
    book_value_per_share = safe_divide(
        equity,
        shares_for_book_value,
    )

    current_assets = record_value(current_assets_record)
    current_liabilities = record_value(current_liabilities_record)

    current_ratio = safe_divide(
        current_assets,
        current_liabilities,
    )

    cash = record_value(cash_record)

    debt_components = [
        record_value(current_debt_record),
        record_value(noncurrent_debt_record),
        record_value(short_term_borrowings_record),
    ]

    available_debt_components = [
        value for value in debt_components if value is not None
    ]

    total_debt = (
        sum(available_debt_components)
        if available_debt_components
        else None
    )

    net_debt = (
        total_debt - cash
        if total_debt is not None and cash is not None
        else None
    )

    debt_to_equity = safe_divide(total_debt, equity)

    goodwill = record_value(goodwill_record)
    intangible_assets = record_value(intangible_assets_record)
    both_intangible_tags_absent = (
        goodwill_record["basis"] == "tag_absent"
        and intangible_assets_record["basis"] == "tag_absent"
    )
    both_intangible_values_reported = (
        goodwill_record["basis"] == "reported"
        and intangible_assets_record["basis"] == "reported"
        and goodwill is not None
        and intangible_assets is not None
    )
    if equity is not None and both_intangible_values_reported:
        tangible_book_value = equity - goodwill - intangible_assets
    elif equity is not None and both_intangible_tags_absent:
        tangible_book_value = equity
    else:
        tangible_book_value = None

    tangible_book_value_per_share = safe_divide(
        tangible_book_value,
        shares_for_book_value,
    )
    price_to_tangible_book = (
        safe_divide(price, tangible_book_value_per_share)
        if tangible_book_value_per_share is not None
        and tangible_book_value_per_share > 0
        else None
    )
    intangibles_share_of_equity = (
        safe_divide(goodwill + intangible_assets, equity)
        if both_intangible_values_reported
        and equity is not None
        and equity > 0
        else None
    )

    total_liabilities = record_value(total_liabilities_record)
    net_current_asset_value = (
        current_assets - total_liabilities
        if current_assets is not None and total_liabilities is not None
        else None
    )
    ncav_per_share = safe_divide(
        net_current_asset_value,
        shares_for_book_value,
    )

    latest_operating_income = record_value(
        last_record(operating_income_history)
    )

    latest_interest_expense = record_value(
        last_record(interest_expense_history)
    )

    interest_coverage = (
        safe_divide(latest_operating_income, abs(latest_interest_expense))
        if latest_interest_expense is not None
        and latest_interest_expense != 0
        else None
    )
    no_interest_and_no_debt = (
        latest_interest_expense == 0
        and total_debt is not None
        and total_debt == 0
    )

    latest_operating_cash_flow = record_value(
        last_record(operating_cash_flow_history)
    )

    latest_capex = record_value(last_record(capex_history))

    free_cash_flow = (
        latest_operating_cash_flow - abs(latest_capex)
        if (
            latest_operating_cash_flow is not None
            and latest_capex is not None
        )
        else None
    )

    normalized_pe = (
        safe_divide(price, normalized_eps)
        if normalized_eps and normalized_eps > 0
        else None
    )

    price_to_book = (
        safe_divide(price, book_value_per_share)
        if book_value_per_share and book_value_per_share > 0
        else None
    )

    pe_times_pb = (
        normalized_pe * price_to_book
        if normalized_pe is not None and price_to_book is not None
        else None
    )

    earnings_value = (
        normalized_eps * earnings_multiple
        if normalized_eps and normalized_eps > 0
        else None
    )

    graham_number = (
        math.sqrt(
            22.5 *
            normalized_eps *
            book_value_per_share
        )
        if (
            normalized_eps
            and normalized_eps > 0
            and book_value_per_share
            and book_value_per_share > 0
        )
        else None
    )

    value_candidates = [
        value
        for value in (earnings_value, graham_number)
        if value is not None and value > 0
    ]

    conservative_mechanical_value = (
        min(value_candidates)
        if value_candidates
        else None
    )

    maximum_price = (
        conservative_mechanical_value * (1 - margin_of_safety)
        if conservative_mechanical_value is not None
        else None
    )

    def metric_period(
        records: list[dict[str, Any] | None],
        basis: str,
    ) -> dict[str, Any]:
        dated = [
            record
            for record in records
            if record is not None and record.get("end")
        ]
        if not dated:
            return {"end": None, "period_end": None, "basis": basis}

        oldest = min(dated, key=lambda record: record["end"])
        result: dict[str, Any] = {
            "end": oldest["end"],
            "period_end": oldest["end"],
            "basis": basis,
        }
        year = oldest.get("year")
        if year is not None:
            result["fiscal_year"] = year
        return result

    eps_period = metric_period(
        list(recent_eps_rows),
        "median of annual diluted EPS",
    )
    eps_period["fiscal_years"] = [
        row["year"] for row in recent_eps_rows
    ]
    eps_period["latest_end"] = (
        recent_eps_rows[-1]["end"] if recent_eps_rows else None
    )
    book_period = metric_period(
        [equity_record, shares_record_for_book],
        "latest balance sheet and share count",
    )
    current_ratio_period = metric_period(
        [current_assets_record, current_liabilities_record],
        "latest balance sheet",
    )
    debt_period = metric_period(
        [
            current_debt_record,
            noncurrent_debt_record,
            short_term_borrowings_record,
        ],
        "latest balance sheet",
    )
    net_debt_period = metric_period(
        [
            current_debt_record,
            noncurrent_debt_record,
            short_term_borrowings_record,
            cash_record,
        ],
        "latest balance sheet",
    )
    debt_to_equity_period = metric_period(
        [
            current_debt_record,
            noncurrent_debt_record,
            short_term_borrowings_record,
            equity_record,
        ],
        "latest balance sheet",
    )
    interest_period = metric_period(
        [
            last_record(operating_income_history),
            last_record(interest_expense_history),
        ],
        "latest annual",
    )
    fcf_period = metric_period(
        [
            last_record(operating_cash_flow_history),
            last_record(capex_history),
        ],
        "latest annual",
    )
    intangibles_period = metric_period(
        [goodwill_record, intangible_assets_record, equity_record],
        "latest balance sheet",
    )
    metric_periods = {
        "normalized_eps": eps_period,
        "normalization": eps_period,
        "profitable_years_in_period": eps_period,
        "years_examined": eps_period,
        "book_value_per_share_approximation": book_period,
        "current_ratio": current_ratio_period,
        "total_debt": debt_period,
        "cash": metric_period([cash_record], "latest balance sheet"),
        "net_debt": net_debt_period,
        "debt_to_equity": debt_to_equity_period,
        "interest_coverage": interest_period,
        "latest_free_cash_flow": fcf_period,
        "normalized_pe": metric_period(
            list(recent_eps_rows),
            "median annual EPS and caller-supplied price",
        ),
        "price_to_book": metric_period(
            [equity_record, shares_record_for_book],
            "latest balance sheet, share count, and caller-supplied price",
        ),
        "pe_times_pb": metric_period(
            list(recent_eps_rows) + [equity_record, shares_record_for_book],
            "annual EPS, latest balance sheet, and caller-supplied price",
        ),
        "intangibles_share_of_equity": intangibles_period,
        "tangible_book_value": intangibles_period,
        "tangible_book_value_per_share": metric_period(
            [goodwill_record, intangible_assets_record, equity_record,
             shares_record_for_book],
            "latest balance sheet and share count",
        ),
        "net_current_asset_value": metric_period(
            [current_assets_record, total_liabilities_record],
            "latest balance sheet",
        ),
        "ncav_per_share": metric_period(
            [current_assets_record, total_liabilities_record,
             shares_record_for_book],
            "latest balance sheet and share count",
        ),
        "price_to_tangible_book": metric_period(
            [goodwill_record, intangible_assets_record, equity_record,
             shares_record_for_book],
            "latest balance sheet, share count, and caller-supplied price",
        ),
        "earnings_based_value": eps_period,
        "graham_number": metric_period(
            list(recent_eps_rows) + [equity_record, shares_record_for_book],
            "annual EPS, latest balance sheet, and share count",
        ),
        "conservative_mechanical_value": metric_period(
            list(recent_eps_rows) + [equity_record, shares_record_for_book],
            "annual EPS, latest balance sheet, and share count",
        ),
        "maximum_price_after_margin_of_safety": metric_period(
            list(recent_eps_rows) + [equity_record, shares_record_for_book],
            "annual EPS, latest balance sheet, share count, and caller inputs",
        ),
    }

    balance_sheet_inputs = [
        (name, record)
        for name, record in (
            ("current_assets", current_assets_record),
            ("current_liabilities", current_liabilities_record),
            ("cash", cash_record),
            ("shareholders_equity", equity_record),
            ("common_shares", common_shares_record),
            ("current_debt", current_debt_record),
            ("noncurrent_debt", noncurrent_debt_record),
            ("short_term_borrowings", short_term_borrowings_record),
            ("total_liabilities", total_liabilities_record),
            ("goodwill", goodwill_record),
            ("intangible_assets", intangible_assets_record),
        )
        if record.get("value") is not None and record.get("end")
    ]
    mixed_period_details: tuple[str, str, str, str, int] | None = None
    if balance_sheet_inputs:
        earliest_name, earliest_record = min(
            balance_sheet_inputs, key=lambda item: item[1]["end"]
        )
        latest_name, latest_record = max(
            balance_sheet_inputs, key=lambda item: item[1]["end"]
        )
        try:
            period_spread = (
                date.fromisoformat(latest_record["end"])
                - date.fromisoformat(earliest_record["end"])
            ).days
        except ValueError:
            period_spread = 0
        if period_spread > 100:
            mixed_period_details = (
                earliest_name,
                earliest_record["end"],
                latest_name,
                latest_record["end"],
                period_spread,
            )

    checks = [
        make_check(
            f"{normalization_years}-year earnings history",
            len(recent_eps),
            len(recent_eps) >= normalization_years,
            f"At least {normalization_years} annual EPS observations",
        ),
        make_check(
            "Positive earnings history",
            profitable_years,
            (
                profitable_years == len(recent_eps)
                if len(recent_eps) >= normalization_years
                else None
            ),
            (
                f"Positive EPS in each of the {normalization_years} "
                "most recent years"
            ),
        ),
        make_check(
            "Current ratio",
            rounded(current_ratio),
            current_ratio >= 1.5 if current_ratio is not None else None,
            "Current ratio of at least 1.5",
        ),
        make_check(
            "Normalized P/E",
            rounded(normalized_pe),
            normalized_pe <= 15 if normalized_pe is not None else None,
            "Normalized P/E no greater than 15",
        ),
        make_check(
            "Price to book",
            rounded(price_to_book),
            price_to_book <= 1.5 if price_to_book is not None else None,
            "Price-to-book no greater than 1.5",
        ),
        make_check(
            "P/E multiplied by P/B",
            rounded(pe_times_pb),
            pe_times_pb <= 22.5 if pe_times_pb is not None else None,
            "P/E × P/B no greater than 22.5",
        ),
        make_check(
            "Free cash flow",
            rounded(free_cash_flow, 2),
            free_cash_flow > 0 if free_cash_flow is not None else None,
            "Latest calculated free cash flow is positive",
        ),
        make_check(
            "Interest coverage",
            rounded(interest_coverage),
            (
                True
                if no_interest_and_no_debt
                else (
                    interest_coverage >= 3
                    if interest_coverage is not None
                    else None
                )
            ),
            (
                "No interest expense and no reported debt — coverage not applicable"
                if no_interest_and_no_debt
                else "Operating income covers interest at least three times"
            ),
        ),
        make_check(
            "Margin-of-safety price",
            rounded(maximum_price),
            (
                price <= maximum_price
                if maximum_price is not None
                else None
            ),
            "Current price is at or below the calculated maximum price",
        ),
    ]

    required_check_names = {
        f"{normalization_years}-year earnings history",
        "Positive earnings history",
        "Current ratio",
        "Normalized P/E",
        "Price to book",
        "P/E multiplied by P/B",
        "Margin-of-safety price",
    }

    required_checks = [
        check
        for check in checks
        if check["name"] in required_check_names
    ]

    failed_checks = [
        check["name"] for check in required_checks
        if check["status"] == "fail"
    ]
    unavailable_checks = [
        check["name"] for check in required_checks
        if check["status"] == "not_available"
    ]
    if unavailable_checks:
        mechanical_verdict = "incomplete_data"
    elif failed_checks:
        mechanical_verdict = "does_not_pass_configured_screen"
    else:
        mechanical_verdict = "passes_configured_screen"

    warnings: list[dict[str, Any]] = [
        make_warning(
            "MODEL_SCOPE",
            "low",
            "This general model is not designed for banks, insurers, "
            "REITs, utilities, pre-profit companies, or businesses whose "
            "book value is not economically meaningful.",
        ),
        make_warning(
            "BOOK_VALUE_SHARE_APPROXIMATION",
            "low",
            "Book value per share may use the latest reported common "
            "shares or diluted weighted-average shares as an approximation.",
            ["book_value_per_share_approximation", "price_to_book"],
        ),
        make_warning(
            "XBRL_TAG_VARIATION",
            "low",
            "SEC XBRL tags can differ among companies. Important values "
            "must be checked against the original 10-K and footnotes.",
        ),
        make_warning(
            "VALUE_TRAP_LIMITATION",
            "low",
            "A mechanical screen cannot determine whether weak results "
            "are temporary or whether the company is a value trap.",
        ),
    ]

    if requested_normalization_years > history_years:
        warnings.append(make_warning(
            "NORMALIZATION_WINDOW_CLAMPED",
            "medium",
            (
                f"The requested {requested_normalization_years}-year "
                f"normalization window was reduced to {history_years} years "
                "because it exceeded the history retrieval window."
            ),
            ["normalized_eps", "profitable_years_in_period"],
        ))

    if (
        common_shares_record
        and common_shares_record.get("share_classes_summed", 1) > 1
    ):
        warnings.append(make_warning(
            "MULTI_CLASS_SHARES",
            "high",
            f"{common_shares_record['share_classes_summed']} share classes were "
            "summed for book value per share. Confirm against the 10-K cover page; "
            "class structures vary and some classes are not economically equivalent.",
            ["price_to_book", "graham_number"],
        ))

    if len(recent_eps) < normalization_years:
        warnings.append(make_warning(
            "INSUFFICIENT_EPS_HISTORY",
            "medium",
            (
                f"Fewer than {normalization_years} usable annual EPS "
                "observations were found."
            ),
            ["normalized_eps", "profitable_years_in_period"],
        ))

    if (
        ratio_to_latest is not None
        and (ratio_to_latest < 0.70 or ratio_to_latest > 1.40)
    ):
        warnings.append(make_warning(
            "NORMALIZATION_FAR_FROM_LATEST",
            "medium",
            f"Normalized EPS of {normalized_eps:.2f} is "
            f"{abs(ratio_to_latest - 1):.0%} "
            f"{'above' if ratio_to_latest > 1 else 'below'} the most recent "
            f"year's {latest_year_eps:.2f}. Median normalization across a "
            "sustained trend reports a level the business may no longer "
            "reach. Confirm the earnings basis before relying on any "
            "valuation derived from it.",
            [
                "normalized_eps",
                "normalized_pe",
                "pe_times_pb",
                "graham_number",
                "earnings_based_value",
                "conservative_mechanical_value",
                "maximum_price_after_margin_of_safety",
            ],
        ))

    annual_history = {
        "eps": eps_history,
        "revenue": revenue_history,
        "net_income": net_income_history,
        "operating_income": operating_income_history,
        "operating_cash_flow": operating_cash_flow_history,
        "capital_expenditures": capex_history,
        "diluted_shares": diluted_shares_history,
        "interest_expense": interest_expense_history,
    }
    latest_period_ends = {
        series_name: rows[-1]["end"]
        for series_name, rows in annual_history.items()
        if rows
    }
    if latest_period_ends:
        newest = max(latest_period_ends.values())
        newest_series = sorted(
            series_name
            for series_name, end in latest_period_ends.items()
            if end == newest
        )[0]
        lagging_descriptions: list[str] = []
        for series_name, end in sorted(latest_period_ends.items()):
            try:
                days_behind = (
                    date.fromisoformat(newest) - date.fromisoformat(end)
                ).days
            except ValueError:
                continue
            if days_behind > 400:
                lagging_descriptions.append(
                    f"{series_name} ({end}, {days_behind} days behind)"
                )
        if lagging_descriptions:
            warnings.append(make_warning(
                "STALE_SERIES",
                "high",
                f"Series resolve to different filing periods. Most recent: "
                f"{newest} ({newest_series}). Lagging: "
                f"{', '.join(lagging_descriptions)}. Metrics combining "
                "series from different periods — interest coverage, margins, "
                "free cash flow — may be built from mismatched years.",
                [
                    "interest_coverage",
                    "latest_free_cash_flow",
                    "normalized_pe",
                ],
            ))

    for series_name, rows in annual_history.items():
        metadata = rows.metadata
        continuity_issues = (
            metadata["dropped_years"] + metadata["missing_years"]
        )
        if continuity_issues:
            warnings.append(make_warning(
                "SERIES_NOT_CONTIGUOUS",
                "medium",
                f"{series_name} has gaps at {continuity_issues}. Observations "
                "before the gap were dropped, so this series covers fewer "
                "years than requested. Multi-year averages and growth "
                "figures use only the contiguous run.",
                [series_name],
            ))

    unit_fallback_fields = {
        series_name
        for series_name, rows in annual_history.items()
        if any(row.get("unit_fallback") for row in rows)
    }
    unit_fallback_fields.update(
        field_name
        for field_name, record in (
            ("current_assets", current_assets_record),
            ("current_liabilities", current_liabilities_record),
            ("cash", cash_record),
            ("shareholders_equity", equity_record),
            ("common_shares", common_shares_record),
            ("current_debt", current_debt_record),
            ("noncurrent_debt", noncurrent_debt_record),
            ("short_term_borrowings", short_term_borrowings_record),
            ("total_liabilities", total_liabilities_record),
            ("goodwill", goodwill_record),
            ("intangible_assets", intangible_assets_record),
        )
        if record.get("unit_fallback")
    )
    if unit_fallback_fields:
        sorted_fallback_fields = sorted(unit_fallback_fields)
        warnings.append(make_warning(
            "UNIT_FALLBACK",
            "medium",
            f"For {', '.join(sorted_fallback_fields)}, none of the preferred "
            "units were present in the filing and an alternative unit was "
            "used. Confirm the figure means what it appears to mean.",
            sorted_fallback_fields,
        ))

    non_usd = sorted({
        _currency_of(row["unit"])
        for key, rows in annual_history.items()
        if key in MONETARY_HISTORY_KEYS
        for row in rows
        if row.get("unit")
        and row["unit"] not in NON_CURRENCY_UNITS
        and _currency_of(row["unit"]) != "USD"
    })
    balance_sheet_units = {
        record["unit"]
        for record in (
            current_assets_record,
            current_liabilities_record,
            cash_record,
            equity_record,
            current_debt_record,
            noncurrent_debt_record,
            short_term_borrowings_record,
            total_liabilities_record,
            goodwill_record,
            intangible_assets_record,
        )
        if record and record.get("unit")
    }
    non_usd = sorted(set(non_usd) | {
        _currency_of(unit)
        for unit in balance_sheet_units
        if unit not in NON_CURRENCY_UNITS
        and _currency_of(unit) != "USD"
    })
    if non_usd:
        warnings.append(make_warning(
            "NON_USD_UNITS",
            "high",
            f"Some facts are reported in {', '.join(non_usd)}, not USD. Ratios "
            "combining them with a USD share price are not meaningful.",
            ["normalized_pe", "price_to_book", "graham_number"],
        ))

    if mixed_period_details is not None:
        (
            earliest_name,
            earliest_end,
            latest_name,
            latest_end,
            period_spread,
        ) = mixed_period_details
        warnings.append(make_warning(
            "MIXED_PERIOD_BALANCE_SHEET",
            "medium",
            f"Balance-sheet figures span {period_spread} days "
            f"({earliest_end} to {latest_end}). {earliest_name} is dated "
            f"{earliest_end} and {latest_name} is dated {latest_end}; metrics "
            "combining them mix periods. Share counts are cover-page figures "
            "as of the filing date and routinely post-date the balance sheet.",
            [
                "book_value_per_share_approximation",
                "price_to_book",
                "graham_number",
                "tangible_book_value_per_share",
                "ncav_per_share",
            ],
        ))

    if (
        intangibles_share_of_equity is not None
        and intangibles_share_of_equity > 0.40
    ):
        tangible_ratio_text = (
            f"{price_to_tangible_book:.2f}"
            if price_to_tangible_book is not None
            else "not available"
        )
        reported_ratio_text = (
            f"{price_to_book:.2f}"
            if price_to_book is not None
            else "not available"
        )
        warnings.append(make_warning(
            "BOOK_VALUE_INTANGIBLE_HEAVY",
            "medium",
            f"Goodwill and intangible assets are "
            f"{intangibles_share_of_equity:.0%} of shareholders' equity. "
            "Price-to-book and the Graham Number compare price against a "
            "book value that is largely not realizable assets. Price to "
            f"tangible book is {tangible_ratio_text}x against "
            f"{reported_ratio_text}x on reported book.",
            ["price_to_book", "graham_number", "pe_times_pb"],
        ))

    if both_intangible_tags_absent and equity is not None:
        warnings.append(make_warning(
            "INTANGIBLE_TAGS_ABSENT_ZERO_TREATMENT",
            "medium",
            (
                "Goodwill and intangible-asset tags do not appear in this "
                "company's SEC filings. Tangible book value was computed "
                "treating both as zero. This is usually correct for companies "
                "that hold neither, but absence of a tag is not a positive "
                "statement of zero. Confirm against the balance sheet."
            ),
            ["tangible_book_value", "tangible_book_value_per_share", "price_to_tangible_book"],
        ))
    elif tangible_book_value is None:
        warnings.append(make_warning(
            "TANGIBLE_BOOK_UNAVAILABLE",
            "medium",
            (
                "Tangible book value was unavailable because shareholders' "
                "equity, goodwill, or intangible assets could not be established "
                "without silently substituting zero."
            ),
            ["tangible_book_value", "tangible_book_value_per_share", "price_to_tangible_book"],
        ))

    if current_ratio is None:
        warnings.append(make_warning(
            "CURRENT_RATIO_UNAVAILABLE",
            "medium",
            "Current assets or current liabilities were unavailable.",
            ["current_ratio"],
        ))

    if total_liabilities is None:
        warnings.append(make_warning(
            "TOTAL_LIABILITIES_UNAVAILABLE",
            "medium",
            "Total liabilities were unavailable; net current asset value could not be calculated.",
            ["net_current_asset_value", "ncav_per_share"],
        ))
    elif ncav_per_share is not None:
        warnings.append(make_warning(
            "NCAV_REALIZABILITY",
            "medium",
            (
                "Net current asset value assumes current assets could be realized "
                "at carrying value and that all liabilities are stated. Neither "
                "holds in a distressed liquidation. Genuine net-net situations "
                "are rare and usually involve companies in serious operating difficulty."
            ),
            ["net_current_asset_value", "ncav_per_share"],
        ))

    if total_debt is None:
        warnings.append(make_warning(
            "TOTAL_DEBT_UNAVAILABLE",
            "medium",
            "A reliable total-debt figure could not be assembled.",
            ["total_debt", "net_debt", "debt_to_equity"],
        ))
    else:
        long_term_debt_tag_note = (
            f" The noncurrent figure matched tag "
            f"{noncurrent_debt_record['tag']}."
            if noncurrent_debt_record.get("tag") == "LongTermDebt"
            else ""
        )
        warnings.append(make_warning(
            "DEBT_COMPOSITION_CAVEAT",
            "medium",
            "Total debt is assembled from current and noncurrent long-term debt "
            "plus short-term borrowings. Some filers tag short-term borrowings "
            "and current long-term debt in overlapping ways, so this figure may "
            "double-count. Operating lease liabilities are excluded, which "
            "understates leverage for lease-heavy businesses such as retail, "
            "restaurants and airlines. Verify against the debt footnote."
            f"{long_term_debt_tag_note}",
            ["total_debt", "net_debt", "debt_to_equity"],
        ))

    if free_cash_flow is None:
        warnings.append(make_warning(
            "FREE_CASH_FLOW_UNAVAILABLE",
            "medium",
            "Operating cash flow or capital expenditures were unavailable.",
            ["latest_free_cash_flow"],
        ))

    if interest_coverage is None:
        warnings.append(make_warning(
            "INTEREST_COVERAGE_UNAVAILABLE",
            "medium",
            "Interest coverage could not be calculated.",
            ["interest_coverage"],
        ))

    balance_sheet_sources = {
        "current_assets": current_assets_record,
        "current_liabilities": current_liabilities_record,
        "cash": cash_record,
        "shareholders_equity": equity_record,
        "common_shares": common_shares_record,
        "current_debt": current_debt_record,
        "noncurrent_debt": noncurrent_debt_record,
        "short_term_borrowings": short_term_borrowings_record,
        "total_liabilities": total_liabilities_record,
        "goodwill": goodwill_record,
        "intangible_assets": intangible_assets_record,
    }
    data_gaps = {
        basis: [
            name
            for name, record in balance_sheet_sources.items()
            if record["basis"] == basis
        ]
        for basis in ("tag_absent", "tag_present_no_annual_value")
    }

    return {
        "company": {
            "ticker": normalized_ticker,
            "name": company["name"],
            "cik": cik,
        },
        "user_inputs": {
            "current_price": price,
            "margin_of_safety": margin_of_safety,
            "earnings_multiple": earnings_multiple,
            "history_years": history_years,
            "normalization_years": normalization_years,
        },
        "mechanical_result": {
            "verdict": mechanical_verdict,
            "failed_checks": failed_checks,
            "unavailable_checks": unavailable_checks,
            "note": (
                "'incomplete_data' means the screen could not be completed, which "
                "is different from the company failing it."
            ),
        },
        "metrics": {
            "normalized_eps": rounded(normalized_eps),
            "normalization": normalization,
            "profitable_years_in_period": profitable_years,
            "years_examined": len(recent_eps),
            "book_value_per_share_approximation": rounded(
                book_value_per_share
            ),
            "current_ratio": rounded(current_ratio),
            "total_debt": rounded(total_debt, 2),
            "cash": rounded(cash, 2),
            "net_debt": rounded(net_debt, 2),
            "debt_to_equity": rounded(debt_to_equity),
            "interest_coverage": rounded(interest_coverage),
            "latest_free_cash_flow": rounded(free_cash_flow, 2),
            "normalized_pe": rounded(normalized_pe),
            "price_to_book": rounded(price_to_book),
            "pe_times_pb": rounded(pe_times_pb),
            "intangibles_share_of_equity": rounded(
                intangibles_share_of_equity
            ),
        },
        "metric_periods": metric_periods,
        "valuation": {
            "tangible_book_value": rounded(tangible_book_value, 2),
            "tangible_book_value_per_share": rounded(
                tangible_book_value_per_share
            ),
            "net_current_asset_value": rounded(net_current_asset_value, 2),
            "ncav_per_share": rounded(ncav_per_share),
            "price_to_tangible_book": rounded(price_to_tangible_book),
            "earnings_based_value": rounded(earnings_value),
            "graham_number": rounded(graham_number),
            "conservative_mechanical_value": rounded(
                conservative_mechanical_value
            ),
            "maximum_price_after_margin_of_safety": rounded(
                maximum_price
            ),
        },
        "screen_checks": checks,
        "annual_history": (
            {
                name: {
                    "values": list(rows),
                    "latest_period_end": latest_period_ends.get(name),
                    **{
                        key: value
                        for key, value in rows.metadata.items()
                        if key != "original_years"
                    },
                }
                for name, rows in annual_history.items()
            }
            if detail
            else {
                name: {
                    "values": [
                        {
                            "year": row["year"],
                            "end": row["end"],
                            "value": row["value"],
                        }
                        for row in rows
                    ],
                    "latest_period_end": latest_period_ends.get(name),
                    "tags": sorted({row["tag"] for row in rows}),
                    "source_urls": sorted({
                        row["source_url"]
                        for row in rows
                        if row.get("source_url")
                    }),
                    **{
                        key: value
                        for key, value in rows.metadata.items()
                        if key != "original_years"
                    },
                }
                for name, rows in annual_history.items()
            }
        ),
        "balance_sheet_sources": balance_sheet_sources,
        "data_gaps": data_gaps,
        "warnings": warnings,
        "warning_messages": [warning["message"] for warning in warnings],
        "research_eligibility": {
            "scope": "live_analysis_only",
            "historical_backtest_eligible": False,
            "reason": (
                "Current SEC Company Facts can contain later amendments and "
                "comparative disclosures and is not a vendor-vintage panel."
            ),
        },
        "status": "Manual filing and qualitative review required.",
        "disclaimer": (
            "Educational mechanical analysis only. Passing the screen "
            "is not a recommendation to buy, sell, or hold the security."
        ),
    }


# ---------------------------------------------------------------------
# Immutable thesis records
# ---------------------------------------------------------------------

class ThesisCreate(BaseModel):
    ticker: str
    company_name: str | None = None
    is_paper: bool
    price_at_entry: float = Field(gt=0)
    value_estimate_low: float = Field(gt=0)
    value_estimate_high: float = Field(gt=0)
    method: str
    thesis_text: str
    circle_of_competence: str
    key_assumptions: list[str]
    falsification: list[str]
    analysis_snapshot: dict[str, Any] | None = None


class ThesisReviewCreate(BaseModel):
    note: str
    conditions_met: list[str] | None = None


class ThesisCloseCreate(BaseModel):
    price_at_exit: float = Field(gt=0)
    exit_reason: str
    reasoning_was_correct: bool


PRICE_WORDS = re.compile(
    r"\b(price|prices|stock|stocks|share|shares|market cap|valuation)\b",
    re.I,
)
MOVEMENT_WORDS = re.compile(
    r"\b(drop|drops|fall|falls|decline|declines|down|below|crash|crashes|"
    r"tank|tanks|lose|loses|loss|red)\b",
    re.I,
)


def validate_thesis(payload: ThesisCreate) -> list[str]:
    problems: list[str] = []
    if len(payload.thesis_text.strip()) < 200:
        problems.append(
            "Thesis too short. State in your own words what the business does, "
            "why you believe it is mispriced, and why the problem is temporary."
        )
    if not payload.falsification:
        problems.append(
            "No falsification condition. Name what would prove you wrong, or do "
            "not record this."
        )
    for entry in payload.falsification:
        if len(entry.strip()) < 15:
            problems.append(
                f'"{entry}" is too vague to resolve. Name an observable business fact.'
            )
        elif PRICE_WORDS.search(entry) and MOVEMENT_WORDS.search(entry):
            problems.append(
                f'"{entry}" describes price movement, not a business fact. A '
                "falling price is often a reason to buy more, not evidence the "
                "thesis was wrong. Name something observable in the filings."
            )
    if not payload.key_assumptions:
        problems.append(
            "No assumptions listed. You made some; write them down."
        )
    if payload.value_estimate_low == payload.value_estimate_high:
        problems.append(
            "Point estimate rather than a range. Two analysts reading the same "
            "filings get different numbers; say so."
        )
    elif payload.value_estimate_low > payload.value_estimate_high:
        problems.append("Low estimate exceeds high estimate.")
    if len(payload.circle_of_competence.strip()) < 50:
        problems.append(
            "Explain how this business makes money and what could break it. If "
            "you cannot, you cannot forecast its cash flows."
        )
    return problems


def decode_json(value: str | None) -> Any:
    return json.loads(value) if value is not None else None


def thesis_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["is_paper"] = bool(result["is_paper"])
    result["key_assumptions"] = decode_json(result["key_assumptions"])
    result["falsification"] = decode_json(result["falsification"])
    result["analysis_snapshot"] = decode_json(result["analysis_snapshot"])
    if result["reasoning_was_correct"] is not None:
        result["reasoning_was_correct"] = bool(result["reasoning_was_correct"])
    result["margin_of_safety_at_entry"] = (
        result["value_estimate_low"] - result["price_at_entry"]
    ) / result["value_estimate_low"]
    return result


def review_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["conditions_met"] = decode_json(result["conditions_met"])
    return result


def _fetch_thesis_from_connection(
    connection: sqlite3.Connection,
    thesis_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM thesis WHERE id = ?", (thesis_id,)
    ).fetchone()
    if row is None:
        return None
    reviews = connection.execute(
        "SELECT * FROM thesis_review WHERE thesis_id = ? ORDER BY created_at, id",
        (thesis_id,),
    ).fetchall()
    result = thesis_row_to_dict(row)
    result["reviews"] = [review_row_to_dict(review) for review in reviews]
    return result


def _fetch_thesis_sync(thesis_id: str) -> dict[str, Any] | None:
    with closing(database_connection()) as connection:
        return _fetch_thesis_from_connection(connection, thesis_id)


async def fetch_thesis(thesis_id: str) -> dict[str, Any]:
    result = await asyncio.to_thread(_fetch_thesis_sync, thesis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Thesis was not found.")
    return result


async def create_analysis_snapshot(
    ticker: str,
    price: float,
) -> dict[str, Any]:
    return await analyze_company(
        ticker=ticker,
        price=price,
        margin_of_safety=0.30,
        earnings_multiple=10.0,
        history_years=10,
        normalization_years=7,
        detail=True,
        _=None,
    )


def _fetch_scorecard_rows_sync(
    is_paper: bool | None,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    where = ""
    parameters: list[Any] = []
    if is_paper is not None:
        where = " WHERE is_paper = ?"
        parameters.append(int(is_paper))

    with closing(database_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM thesis" + where,
            parameters,
        ).fetchall()
        review_rows = connection.execute(
            "SELECT thesis_id, MAX(created_at) AS last_review "
            "FROM thesis_review GROUP BY thesis_id"
        ).fetchall()
    return rows, review_rows


@app.get("/thesis/scorecard", dependencies=[Depends(authorize)])
async def thesis_scorecard(
    is_paper: bool | None = Query(None),
) -> dict[str, Any]:
    rows, review_rows = await asyncio.to_thread(
        _fetch_scorecard_rows_sync,
        is_paper,
    )

    reviews_by_thesis = {
        row["thesis_id"]: row["last_review"] for row in review_rows
    }
    closed = [row for row in rows if row["closed_at"] is not None]
    opened = [row for row in rows if row["closed_at"] is None]
    returns = [
        (row["price_at_exit"] - row["price_at_entry"]) / row["price_at_entry"]
        for row in closed
        if row["price_at_exit"] is not None
    ]
    reasoning_rows = [
        row for row in closed if row["reasoning_was_correct"] is not None
    ]
    reasoning_correct = sum(
        row["reasoning_was_correct"] == 1 for row in reasoning_rows
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    open_past_review = 0
    for row in opened:
        last_activity = reviews_by_thesis.get(row["id"]) or row["created_at"]
        try:
            activity_time = datetime.fromisoformat(last_activity)
        except ValueError:
            continue
        if activity_time <= cutoff:
            open_past_review += 1

    enough_returns = len(closed) >= 10
    return {
        "total_closed": len(closed),
        "paper_count": sum(row["is_paper"] == 1 for row in closed),
        "real_count": sum(row["is_paper"] == 0 for row in closed),
        "reasoning_correct": reasoning_correct,
        "reasoning_correct_rate": (
            reasoning_correct / len(reasoning_rows) if reasoning_rows else None
        ),
        "right_reasoning_lost_money": sum(
            row["reasoning_was_correct"] == 1
            and row["price_at_exit"] is not None
            and row["price_at_exit"] < row["price_at_entry"]
            for row in closed
        ),
        "wrong_reasoning_made_money": sum(
            row["reasoning_was_correct"] == 0
            and row["price_at_exit"] is not None
            and row["price_at_exit"] > row["price_at_entry"]
            for row in closed
        ),
        "mean_return": mean(returns) if enough_returns and returns else None,
        "median_return": median(returns) if enough_returns and returns else None,
        "return_statistics_note": (
            None
            if enough_returns
            else "Too few closed positions for return statistics to carry meaning."
        ),
        "open_count": len(opened),
        "open_past_review": open_past_review,
        "interpretation": (
            "Reasoning accuracy is the signal; returns at this sample size are "
            "mostly noise. Positions where correct reasoning lost money and "
            "incorrect reasoning made money are the two categories most likely "
            "to teach the wrong lesson. Paper theses count toward reasoning "
            "accuracy at no cost and are the fastest way to accumulate evidence "
            "about your own judgment."
        ),
    }


def _list_theses_sync(
    ticker: str | None,
    is_paper: bool | None,
    open_only: bool,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    parameters: list[Any] = []
    if ticker:
        clauses.append("ticker = ?")
        parameters.append(ticker.strip().upper())
    if is_paper is not None:
        clauses.append("is_paper = ?")
        parameters.append(int(is_paper))
    if open_only:
        clauses.append("closed_at IS NULL")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(database_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM thesis" + where + " ORDER BY created_at DESC, id",
            parameters,
        ).fetchall()
    return [thesis_row_to_dict(row) for row in rows]


@app.get("/thesis", dependencies=[Depends(authorize)])
async def list_theses(
    ticker: str | None = Query(None),
    is_paper: bool | None = Query(None),
    open_only: bool = Query(False),
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        _list_theses_sync,
        ticker,
        is_paper,
        open_only,
    )


def _create_thesis_sync(
    thesis_id: str,
    created_at: str,
    payload: ThesisCreate,
    snapshot: dict[str, Any] | None,
    snapshot_source: str,
) -> dict[str, Any]:
    with closing(database_connection()) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO thesis (
                    id, ticker, company_name, created_at, is_paper,
                    price_at_entry, value_estimate_low, value_estimate_high,
                    method, thesis_text, circle_of_competence,
                    key_assumptions, falsification, analysis_snapshot,
                    snapshot_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thesis_id,
                    payload.ticker.strip().upper(),
                    payload.company_name,
                    created_at,
                    int(payload.is_paper),
                    payload.price_at_entry,
                    payload.value_estimate_low,
                    payload.value_estimate_high,
                    payload.method,
                    payload.thesis_text,
                    payload.circle_of_competence,
                    json.dumps(payload.key_assumptions),
                    json.dumps(payload.falsification),
                    json.dumps(snapshot) if snapshot is not None else None,
                    snapshot_source,
                ),
            )
        result = _fetch_thesis_from_connection(connection, thesis_id)
    if result is None:
        raise RuntimeError("Created thesis could not be read back.")
    return result


@app.post("/thesis", status_code=201, dependencies=[Depends(authorize)])
async def create_thesis(payload: ThesisCreate) -> dict[str, Any]:
    problems = validate_thesis(payload)
    if problems:
        raise HTTPException(status_code=422, detail=problems)

    snapshot_warning: str | None = None
    if payload.analysis_snapshot is not None:
        snapshot = payload.analysis_snapshot
        snapshot_source = "caller_supplied"
    else:
        snapshot_source = "server_generated"
        try:
            snapshot = await create_analysis_snapshot(
                payload.ticker.strip().upper(), payload.price_at_entry
            )
        except Exception:
            snapshot = None
            snapshot_warning = (
                "The analysis snapshot could not be generated; the thesis was "
                "stored without one."
            )

    thesis_id = str(uuid.uuid4())
    created_at = utc_now()
    result = await asyncio.to_thread(
        _create_thesis_sync,
        thesis_id,
        created_at,
        payload,
        snapshot,
        snapshot_source,
    )
    warnings: list[str] = []
    if payload.price_at_entry > payload.value_estimate_low:
        warnings.append(
            "Entry price is above your own low estimate. There is no margin of "
            "safety here."
        )
    if snapshot_warning:
        warnings.append(snapshot_warning)
    result["warnings"] = warnings
    return result


@app.get("/thesis/{thesis_id}", dependencies=[Depends(authorize)])
async def get_thesis(thesis_id: str) -> dict[str, Any]:
    return await fetch_thesis(thesis_id)


def _append_thesis_review_sync(
    thesis_id: str,
    review_id: str,
    created_at: str,
    payload: ThesisReviewCreate,
) -> dict[str, Any] | None:
    with closing(database_connection()) as connection:
        with connection:
            exists = connection.execute(
                "SELECT 1 FROM thesis WHERE id = ?",
                (thesis_id,),
            ).fetchone()
            if exists is None:
                return None
            connection.execute(
                """
                INSERT INTO thesis_review (
                    id, thesis_id, created_at, note, conditions_met
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    thesis_id,
                    created_at,
                    payload.note,
                    json.dumps(payload.conditions_met)
                    if payload.conditions_met is not None
                    else None,
                ),
            )
            row = connection.execute(
                "SELECT * FROM thesis_review WHERE id = ?",
                (review_id,),
            ).fetchone()
    return review_row_to_dict(row)


@app.post(
    "/thesis/{thesis_id}/review",
    status_code=201,
    dependencies=[Depends(authorize)],
)
async def append_thesis_review(
    thesis_id: str,
    payload: ThesisReviewCreate,
) -> dict[str, Any]:
    review_id = str(uuid.uuid4())
    created_at = utc_now()
    result = await asyncio.to_thread(
        _append_thesis_review_sync,
        thesis_id,
        review_id,
        created_at,
        payload,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Thesis was not found.")
    return result


def _close_thesis_sync(
    thesis_id: str,
    closed_at: str,
    payload: ThesisCloseCreate,
) -> tuple[str, dict[str, Any] | None]:
    with closing(database_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """
                UPDATE thesis
                SET closed_at = ?, price_at_exit = ?, exit_reason = ?,
                    reasoning_was_correct = ?
                WHERE id = ? AND closed_at IS NULL AND price_at_exit IS NULL
                    AND exit_reason IS NULL AND reasoning_was_correct IS NULL
                """,
                (
                    closed_at,
                    payload.price_at_exit,
                    payload.exit_reason,
                    int(payload.reasoning_was_correct),
                    thesis_id,
                ),
            )
            if cursor.rowcount == 0:
                exists = connection.execute(
                    "SELECT 1 FROM thesis WHERE id = ?",
                    (thesis_id,),
                ).fetchone()
                return (
                    ("missing", None)
                    if exists is None
                    else ("already_closed", None)
                )
        return (
            "closed",
            _fetch_thesis_from_connection(connection, thesis_id),
        )


@app.post(
    "/thesis/{thesis_id}/close",
    dependencies=[Depends(authorize)],
)
async def close_thesis(
    thesis_id: str,
    payload: ThesisCloseCreate,
) -> dict[str, Any]:
    status, result = await asyncio.to_thread(
        _close_thesis_sync,
        thesis_id,
        utc_now(),
        payload,
    )
    if status == "missing":
        raise HTTPException(status_code=404, detail="Thesis was not found.")
    if status == "already_closed":
        raise HTTPException(status_code=409, detail="Thesis is already closed.")
    if result is None:
        raise RuntimeError("Closed thesis could not be read back.")
    return result


def latest_history_value(snapshot: dict[str, Any], name: str) -> float | None:
    history = snapshot.get("annual_history", {}).get(name)
    if isinstance(history, list):
        rows = history
    elif isinstance(history, dict):
        rows = history.get("values", [])
    else:
        rows = []
    value = rows[-1].get("value") if rows else None
    return float(value) if isinstance(value, (int, float)) else None


def snapshot_metric(snapshot: dict[str, Any], name: str) -> float | None:
    metrics = snapshot.get("metrics", {})
    if name == "revenue":
        return latest_history_value(snapshot, "revenue")
    if name == "margins":
        revenue = latest_history_value(snapshot, "revenue")
        operating_income = latest_history_value(snapshot, "operating_income")
        return safe_divide(operating_income, revenue)
    if name == "eps":
        value = metrics.get("normalized_eps")
    elif name == "free_cash_flow":
        value = metrics.get("latest_free_cash_flow")
    elif name == "share_count":
        value = (
            snapshot.get("balance_sheet_sources", {})
            .get("common_shares", {}) or {}
        ).get("value")
    else:
        value = metrics.get(name)
    return float(value) if isinstance(value, (int, float)) else None


def compare_values(then: float | None, now: float | None) -> dict[str, Any]:
    result: dict[str, Any] = {"then": then, "now": now}
    if then is None:
        result.update(change="unavailable_then", pct_change="unavailable_then")
    elif now is None:
        result.update(change="unavailable_now", pct_change="unavailable_now")
    else:
        change = now - then
        result["change"] = rounded(change, 4)
        result["pct_change"] = rounded(change / then, 4) if then != 0 else None
    return result


@app.get(
    "/thesis/{thesis_id}/diff",
    dependencies=[Depends(authorize)],
)
async def diff_thesis(
    thesis_id: str,
    price: float = Query(..., gt=0),
) -> dict[str, Any]:
    thesis = await fetch_thesis(thesis_id)
    current = await create_analysis_snapshot(thesis["ticker"], price)
    snapshot = thesis["analysis_snapshot"] or {}
    metric_names = (
        "revenue",
        "margins",
        "eps",
        "free_cash_flow",
        "total_debt",
        "interest_coverage",
        "share_count",
        "current_ratio",
    )
    business_changes = {
        name: compare_values(
            snapshot_metric(snapshot, name),
            snapshot_metric(current, name),
        )
        for name in metric_names
    }
    prior_checks = {
        check["name"]: check["status"]
        for check in snapshot.get("screen_checks", [])
    }
    current_checks = {
        check["name"]: check["status"]
        for check in current.get("screen_checks", [])
    }
    screen_changes = [
        {"name": name, "then": prior_checks.get(name), "now": current_checks.get(name)}
        for name in sorted(set(prior_checks) | set(current_checks))
        if prior_checks.get(name) != current_checks.get(name)
    ]
    assumption_fields = (
        "normalization_years",
        "earnings_multiple",
        "margin_of_safety",
    )
    old_inputs = snapshot.get("user_inputs", {})
    new_inputs = current.get("user_inputs", {})
    assumption_changes = {
        name: {"then": old_inputs.get(name), "now": new_inputs.get(name)}
        for name in assumption_fields
        if old_inputs.get(name) != new_inputs.get(name)
    }
    return {
        "falsification_conditions": thesis["falsification"],
        "business_changes": business_changes,
        "screen_changes": screen_changes,
        "assumption_changes": assumption_changes,
        "price_change": compare_values(
            old_inputs.get("current_price"),
            price,
        ),
    }
