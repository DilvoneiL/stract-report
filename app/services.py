from __future__ import annotations

from flask import Response, current_app
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import csv
import io
from typing import Dict, List, Any, Tuple
import os
import time

# ----------------- Config (via terminal) -----------------
API_BASE = os.getenv("API_BASE", "https://sidebar.stract.to/api").rstrip("/")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "12"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "2"))

if not AUTH_TOKEN:
    raise RuntimeError(
        "AUTH_TOKEN não definido. Exporte no terminal:\n"
        '  export AUTH_TOKEN="..."\n'
    )

#HTTP Session com Retry/Timeout
def _build_session(timeout: int, retries: int) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)

    orig = s.request
    def _with_timeout(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return orig(method, url, **kwargs)
    s.request = _with_timeout 
    return s

_SESSION = _build_session(HTTP_TIMEOUT, RETRY_ATTEMPTS)

def _auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {}

#HTTP helpers
def api_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    """GET na API com Authorization Bearer (logs sem vazar token)."""
    url = f"{API_BASE}{path}"
    safe_params = dict(params or {})
    safe_params.pop("token", None)
    current_app.logger.info("GET %s params=%s", url, safe_params)

    r = _SESSION.get(url, headers=_auth_headers(), params=params or {})
    current_app.logger.info("-> %s %s", r.status_code, r.reason)
    r.raise_for_status()
    return r.json()

#Paginação
def fetch_all_pages(path: str, params: Dict[str, Any]) -> List[Any]:
    out: List[Any] = []
    page = 1
    next_url = None
    max_pages = 50

    while True:
        if page > max_pages:
            break

        if next_url:
            if next_url.startswith(API_BASE):
                rel = next_url.replace(API_BASE, "")
                data = api_get(rel, {})
            else:
                r = _SESSION.get(next_url, headers=_auth_headers(), timeout=HTTP_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            next_url = None
        else:
            p = dict(params)
            p["page"] = page
            data = api_get(path, p)

        if isinstance(data, list):
            out.extend(data)
            break

        # dict
        if isinstance(data, dict):
            items = None
            for k in ("insights", "accounts", "fields", "platforms", "results", "data", "items"):
                if k in data and isinstance(data[k], list):
                    items = data[k]
                    break

            if items is None:
                if data:
                    out.append(data)
                break

            out.extend(items)

            pagination = data.get("pagination")
            if isinstance(pagination, dict):
                current = pagination.get("current")
                total = pagination.get("total")
                if isinstance(current, int) and isinstance(total, int) and current < total:
                    page += 1
                    continue
                break

            if isinstance(data.get("next"), str) and data["next"]:
                next_url = data["next"]
                continue

            if data.get("has_next") is True or data.get("next_page"):
                page += 1
                continue

            break

        break

    return out

#helpers
def get_platforms() -> List[Dict[str, Any]]:
    data = api_get("/platforms")

    if isinstance(data, dict) and isinstance(data.get("platforms"), list):
        out = []
        for p in data["platforms"]:
            if isinstance(p, dict):
                value = p.get("value")
                text = p.get("text")
                if value:
                    out.append({"name": value, "label": text or value})
        return out

    if isinstance(data, list):
        if data and isinstance(data[0], str):
            return [{"name": x, "label": x} for x in data]
        if data and isinstance(data[0], dict):
            return [
                {
                    "name": d.get("value") or d.get("name") or d.get("platform"),
                    "label": d.get("text") or d.get("label") or d.get("name"),
                }
                for d in data
                if (d.get("value") or d.get("name") or d.get("platform"))
            ]
    return []

def get_accounts(platform: str) -> List[Dict[str, Any]]:
    data = api_get("/accounts", {"platform": platform})

    if isinstance(data, dict) and isinstance(data.get("accounts"), list):
        out = []
        for a in data["accounts"]:
            if isinstance(a, dict):
                value = a.get("value") or a.get("id")
                text = a.get("text") or a.get("name") or value
                token = a.get("token") or a.get("access_token")
                if value:
                    out.append({"id": value, "name": text, "token": token})
        return out

    if isinstance(data, list):
        out = []
        for a in data:
            if isinstance(a, dict):
                out.append(
                    {
                        "id": a.get("value") or a.get("id"),
                        "name": a.get("text") or a.get("name") or a.get("value") or "",
                        "token": a.get("token") or a.get("access_token"),
                    }
                )
        return out

    return []

def get_fields(platform: str) -> List[str]:
    data = fetch_all_pages("/fields", {"platform": platform})
    fields = []
    for f in data:
        if isinstance(f, dict):
            v = f.get("value")
            if v:
                fields.append(v)
        elif isinstance(f, str):
            fields.append(f)

    seen = set()
    uniq = []
    for x in fields:
        if x and x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq

def parse_account_name(account: Dict[str, Any]) -> str:
    return account.get("name") or str(account.get("id") or "")

def is_number(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return False
        try:
            float(s)
            return True
        except Exception:
            return False
    return False

def to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return 0.0
        try:
            return float(s)
        except Exception:
            return 0.0
    return 0.0

def normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in row.items():
        if not isinstance(k, str):
            continue
        lk = k.lower().strip()
        if lk == "id" or lk.endswith("_id") or lk.endswith(" id"):
            continue
        out[k] = v
    return out

def ensure_cpc(row: Dict[str, Any]) -> None:
    keys_lower = {k.lower(): k for k in row.keys()}
    has_cpc = any(k.lower() == "cost per click" for k in row.keys())
    spend_k = keys_lower.get("spend")
    clicks_k = keys_lower.get("clicks")

    if not has_cpc and spend_k and clicks_k:
        clicks = to_float(row.get(clicks_k))
        spend = to_float(row.get(spend_k))
        row["Cost per Click"] = (spend / clicks) if clicks else ""

#Report builders
def get_insights(platform: str, account: Dict[str, Any], fields: List[str]) -> List[Dict[str, Any]]:
    account_id = account.get("id")
    account_token = account.get("token") or AUTH_TOKEN
    if not account_id:
        return []

    params = {
        "platform": platform,
        "account": account_id,
        "token": account_token,
        "fields": ",".join(fields),
    }

    data = fetch_all_pages("/insights", params)
    return [row for row in data if isinstance(row, dict)]

def platform_ads_table(platform: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    accounts = get_accounts(platform)
    fields = get_fields(platform)

    rows: List[Dict[str, Any]] = []
    all_cols: List[str] = []

    for acc in accounts:
        acc_name = parse_account_name(acc)
        insights = get_insights(platform, acc, fields)

        for item in insights:
            item = normalize_row_keys(item)
            item["Account Name"] = acc_name
            item["Platform"] = platform
            ensure_cpc(item)
            rows.append(item)
            for k in item.keys():
                if k not in all_cols:
                    all_cols.append(k)

    preferred = ["Platform", "Account Name"]
    headers = preferred + [c for c in all_cols if c not in preferred]
    return rows, headers

def platform_summary_table(platform: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows, headers = platform_ads_table(platform)

    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        acc = r.get("Account Name", "")
        if acc not in agg:
            agg[acc] = {h: "" for h in headers}
            agg[acc]["Platform"] = platform
            agg[acc]["Account Name"] = acc

        for h in headers:
            if h in ("Platform", "Account Name"):
                continue
            v = r.get(h)
            if is_number(v):
                agg[acc][h] = to_float(agg[acc].get(h)) + to_float(v)

    out = list(agg.values())
    return out, headers

def general_ads_table() -> Tuple[List[Dict[str, Any]], List[str]]:
    platforms = [p["name"] for p in get_platforms() if p.get("name")]
    all_rows: List[Dict[str, Any]] = []
    all_cols: List[str] = []

    for platform in platforms:
        rows, _headers = platform_ads_table(platform)
        for r in rows:
            ensure_cpc(r)
            all_rows.append(r)
            for k in r.keys():
                if k not in all_cols:
                    all_cols.append(k)

    preferred = ["Platform", "Account Name"]
    headers = preferred + [c for c in all_cols if c not in preferred]
    return all_rows, headers

def general_summary_table() -> Tuple[List[Dict[str, Any]], List[str]]:
    rows, headers = general_ads_table()

    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        plat = r.get("Platform", "")
        if plat not in agg:
            agg[plat] = {h: "" for h in headers}
            agg[plat]["Platform"] = plat

        for h in headers:
            if h == "Platform":
                continue
            v = r.get(h)
            if is_number(v):
                agg[plat][h] = to_float(agg[plat].get(h)) + to_float(v)

    out = list(agg.values())
    return out, headers

#CSV 
def build_csv_response(rows: List[Dict[str, Any]], headers: List[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({h: r.get(h, "") for h in headers})
    csv_text = buf.getvalue()
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
