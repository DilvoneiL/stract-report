from flask import Flask, Response
import requests
import csv
import io
from typing import Dict, List, Any, Tuple
import os
import time

API_BASE = os.getenv("API_BASE", "https://sidebar.stract.to/api")
AUTH_TOKEN = os.getenv("AUTH_TOKEN") 

if not AUTH_TOKEN:
    raise RuntimeError(
        "AUTH_TOKEN não definido. Exporte no terminal:\n"
        '  export AUTH_TOKEN="..."\n'
    ) 
HTTP_TIMEOUT = 12
RETRY_ATTEMPTS = 2


app = Flask(__name__)
print("URL MAP:", app.url_map)

def api_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    """GET na API com Authorization Bearer + retry leve."""
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last_exc = exc
          
            time.sleep(0.4 * (attempt + 1))
    
    raise last_exc

def ensure_cpc(row: Dict[str, Any]) -> None:

    keys_lower = {k.lower(): k for k in row.keys()}
    has_cpc = any(k.lower() == "cost per click" for k in row.keys())
    spend_k = keys_lower.get("spend")
    clicks_k = keys_lower.get("clicks")

    if not has_cpc and spend_k and clicks_k:
        clicks = to_float(row.get(clicks_k))
        spend = to_float(row.get(spend_k))
        row["Cost per Click"] = (spend / clicks) if clicks else ""


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
                headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
                r = requests.get(next_url, headers=headers, timeout=HTTP_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            next_url = None
        else:
            p = dict(params)
            p["page"] = page
            data = api_get(path, p)

        #lista simples
        if isinstance(data, list):
            out.extend(data)
            break

        #dict
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

            #link next
            if isinstance(data.get("next"), str) and data["next"]:
                next_url = data["next"]
                continue

            #fallbacks
            if data.get("has_next") is True or data.get("next_page"):
                page += 1
                continue

           
            break

        
        break

    return out



#Domain helpers

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
            return [{"name": d.get("value") or d.get("name") or d.get("platform"),
                     "label": d.get("text") or d.get("label") or d.get("name")}
                    for d in data
                    if (d.get("value") or d.get("name") or d.get("platform"))]
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
                    out.append({
                        "id": value,
                        "name": text,
                        "token": token  
                    })
        return out

    # fallback
    if isinstance(data, list):
        out = []
        for a in data:
            if isinstance(a, dict):
                out.append({
                    "id": a.get("value") or a.get("id"),
                    "name": a.get("text") or a.get("name") or a.get("value") or "",
                    "token": a.get("token") or a.get("access_token")
                })
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

    # dedupe mantendo ordem
    seen = set()
    uniq = []
    for x in fields:
        if x and x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq

def parse_account_id(account: Dict[str, Any]) -> Any:
    return (
        account.get("value") or   
        account.get("id") or
        account.get("account") or
        account.get("account_id") or
        account.get("uuid")
    )

def parse_account_name(account: Dict[str, Any]) -> str:
    return account.get("name") or str(account.get("id") or "")


def get_insights(platform: str, account: Dict[str, Any], fields: List[str]) -> List[Dict[str, Any]]:
    account_id = account.get("id")
    # PRIORIDADE: token da conta; FALLBACK: AUTH_TOKEN
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
        except:
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
        except:
            return 0.0
    return 0.0

def normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in row.items():
        if not isinstance(k, str):
            continue
        lk = k.lower().strip()
        # remove apenas ids claros
        if lk == "id" or lk.endswith("_id") or lk.endswith(" id"):
            continue
        out[k] = v
    return out


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

#Report builders

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
            else:
               
                pass

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

    # prioriza colunas 
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
            else:
               
                pass

    out = list(agg.values())
    return out, headers

#Flask routes



@app.get("/")
def root():

    name = "dilvonei"
    email = "dilvoneialveslacerdajunior@gmail.com"
    linkedin = "https://www.linkedin.com/in/dilvonei-alves-lacerda-05328a228/"
    return f"{name}\n{email}\n{linkedin}\n"

@app.get("/geral")
def geral():
    rows, headers = general_ads_table()
    return build_csv_response(rows, headers, "geral.csv")

@app.get("/geral/resumo")
def geral_resumo():
    rows, headers = general_summary_table()
    return build_csv_response(rows, headers, "geral_resumo.csv")

@app.get("/<platform>")
def plataforma(platform: str):
    rows, headers = platform_ads_table(platform)
    return build_csv_response(rows, headers, f"{platform}.csv")

@app.get("/<platform>/resumo")
def plataforma_resumo(platform: str):
    rows, headers = platform_summary_table(platform)
    return build_csv_response(rows, headers, f"{platform}_resumo.csv")

if __name__ == "__main__":
    print("URL MAP:", app.url_map)
    app.run(host="0.0.0.0", port=5000, debug=False)