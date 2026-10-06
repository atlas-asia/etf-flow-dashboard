# -*- coding: utf-8 -*-
"""通过恒生聚源FinQuery批量获取2026年NAV数据（只取份额有变动的ETF）。
- 40只×2个月为一批次
- 增量保存cache/nav_gildata.csv，可断点续传
- 缺失代码尝试东财接口兜底
"""
import os, sys, glob, json, re, time, urllib.request
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR, fetch_etf_nav_history

# ---------- 恒生聚源直连 ----------
def get_url():
    cands = []
    for f in glob.glob(r"C:/Users/Asia/.workbuddy/logs/*/workbuddyMainThread__*.log"):
        txt = open(f, encoding="utf-8", errors="ignore").read()
        cands += re.findall(r"https://api\.gildata\.com/mcp-servers/aidata-assistant-srv-tool\?token=[A-Za-z0-9._\-]+", txt)
    if not cands:
        raise RuntimeError("gildata URL not found in logs")
    return sorted(set(cands))[-1]

URL = get_url()
INIT = {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "etf-tracker", "version": "1.0"}}

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    req = urllib.request.Request(URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    result = None
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                result = json.loads(line[5:].strip())
            except Exception:
                pass
    return result

def finquery(query, retries=2):
    for attempt in range(retries + 1):
        try:
            try:
                rpc("initialize", INIT)
            except Exception:
                pass
            return rpc("tools/call", {"name": "FinQuery", "arguments": {"query": query}})
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(3 * (attempt + 1))

def parse_nav(res):
    """解析FinQuery结果 -> DataFrame[基金代码, 日期, 单位净值]"""
    if not res or "result" not in res:
        return pd.DataFrame(columns=["基金代码", "日期", "单位净值"])
    text = "".join(item.get("text", "") for item in res["result"].get("content", []))
    md = ""
    try:
        inner = json.loads(text)
        for r in inner.get("results", []):
            md += r.get("table_markdown", "")
    except Exception:
        md = text
    rows = []
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # ['', code, name, date, nav, ...]
        if len(parts) >= 5 and re.fullmatch(r"\d{6}", parts[1] or "") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[3] or ""):
            try:
                nav = float(parts[4])
            except ValueError:
                continue
            rows.append((parts[1], parts[3], nav))
    return pd.DataFrame(rows, columns=["基金代码", "日期", "单位净值"])

# ---------- 主流程 ----------
def main():
    shares = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    shares = shares.sort_values(["基金代码", "日期"])
    shares["前日份额"] = shares.groupby("基金代码")["基金份额"].shift(1)
    shares["份额变动"] = shares["基金份额"] - shares["前日份额"]
    s2026 = shares[shares["日期"] >= "2026-01-01"]
    changed = sorted(s2026.loc[s2026["份额变动"].fillna(0).ne(0), "基金代码"].unique())
    print(f"份额有变动的ETF: {len(changed)}只")

    # NAV覆盖的月份区间（2个月一批）
    end_date = s2026["日期"].max()
    periods = []
    for (y, m) in [(2026, 1), (2026, 3), (2026, 5), (2026, 7)]:
        start = f"{y}-{m:02d}-01"
        if m == 7:
            e = end_date
        else:
            nm = m + 2
            e = (pd.Timestamp(y, nm, 1) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if start > end_date:
            continue
        periods.append((start, e))
    print("区间:", periods)

    csv_path = os.path.join(CACHE_DIR, "nav_gildata.csv")
    state_path = os.path.join(CACHE_DIR, "nav_state.json")
    if os.path.exists(csv_path):
        nav_df = pd.read_csv(csv_path, dtype={"基金代码": str})
        nav_df["基金代码"] = nav_df["基金代码"].str.zfill(6)
    else:
        nav_df = pd.DataFrame(columns=["基金代码", "日期", "单位净值"])
    done = set()
    if os.path.exists(state_path):
        done = set(json.load(open(state_path, encoding="utf-8")))

    CHUNK = 40
    chunks = [changed[i:i+CHUNK] for i in range(0, len(changed), CHUNK)]
    tasks = [(ci, pi) for ci in range(len(chunks)) for pi in range(len(periods))]
    total = len(tasks)
    print(f"总批次: {total} (chunks={len(chunks)}, periods={len(periods)})")

    t0 = time.time()
    for n, (ci, pi) in enumerate(tasks, 1):
        key = f"{ci}_{pi}"
        if key in done:
            continue
        codes = chunks[ci]
        s, e = periods[pi]
        code_str = "、".join(codes)
        q = f"查询基金{code_str}共{len(codes)}只ETF在{s}至{e}每个交易日的单位净值"
        try:
            res = finquery(q)
            df = parse_nav(res)
        except Exception as ex:
            print(f"  [{n}/{total}] 批次{key} 失败: {ex}")
            time.sleep(5)
            continue
        if not df.empty:
            nav_df = pd.concat([nav_df, df], ignore_index=True)
            nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
            nav_df.to_csv(csv_path, index=False)
        done.add(key)
        json.dump(sorted(done), open(state_path, "w", encoding="utf-8"))
        el = time.time() - t0
        print(f"  [{n}/{total}] 批次{key}: +{len(df)}行 (累计{len(nav_df)}行, 已用{el/60:.1f}分钟)")

    # 校验缺失代码
    got_codes = set(nav_df["基金代码"].unique())
    missing = [c for c in changed if c not in got_codes]
    print(f"聚源覆盖: {len(got_codes)}, 缺失: {len(missing)}")

    # 缺失代码逐个查询
    for c in missing:
        try:
            res = finquery(f"查询基金{c}在2026年1月1日至{end_date}每个交易日的单位净值")
            df = parse_nav(res)
            if not df.empty:
                nav_df = pd.concat([nav_df, df], ignore_index=True)
                nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
                print(f"  补查{c}: +{len(df)}行")
                continue
        except Exception:
            pass
        # 东财兜底
        try:
            ed = fetch_etf_nav_history(c, page_size=300)
            if not ed.empty:
                ed = ed.rename(columns={})[["日期", "单位净值"]].copy()
                ed["基金代码"] = c
                ed = ed[["基金代码", "日期", "单位净值"]]
                nav_df = pd.concat([nav_df, ed], ignore_index=True)
                print(f"  东财兜底{c}: +{len(ed)}行")
                time.sleep(1.5)
                continue
        except Exception:
            pass
        print(f"  仍缺失: {c}")

    nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
    nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
    nav_df = nav_df[(nav_df["日期"] >= "2026-01-01") & (nav_df["日期"] <= end_date)]
    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)
    print(f"NAV合计: {len(nav_df)}行, 覆盖{nav_df['基金代码'].nunique()}只, 日期{nav_df['日期'].min()}~{nav_df['日期'].max()}")

if __name__ == "__main__":
    main()
