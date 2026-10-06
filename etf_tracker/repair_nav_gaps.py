# -*- coding: utf-8 -*-
"""修复NAV缺口：按(代码×月份)缺口重新查询恒生聚源，失败批次减半重试，最后东财兜底。"""
import os, sys, glob, json, re, time, urllib.request
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR, fetch_etf_nav_history

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

def finquery(query):
    try:
        rpc("initialize", INIT)
    except Exception:
        pass
    return rpc("tools/call", {"name": "FinQuery", "arguments": {"query": query}})

def parse_nav(res):
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
        if len(parts) >= 5 and re.fullmatch(r"\d{6}", parts[1] or "") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[3] or ""):
            try:
                nav = float(parts[4])
            except ValueError:
                continue
            rows.append((parts[1], parts[3], nav))
    return pd.DataFrame(rows, columns=["基金代码", "日期", "单位净值"])

def query_month(codes, ym):
    y, m = int(ym[:4]), int(ym[5:7])
    start = f"{y}-{m:02d}-01"
    end = (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    code_str = "、".join(codes)
    q = f"查询基金{code_str}共{len(codes)}只ETF在{start}至{end}每个交易日的单位净值"
    try:
        return parse_nav(finquery(q))
    except Exception:
        return pd.DataFrame(columns=["基金代码", "日期", "单位净值"])

def main():
    csv_path = os.path.join(CACHE_DIR, "nav_gildata.csv")
    nav_df = pd.read_csv(csv_path, dtype={"基金代码": str})
    nav_df["基金代码"] = nav_df["基金代码"].str.zfill(6)
    gaps_path = os.path.join(CACHE_DIR, "nav_gaps.csv")
    shares_all = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    s26_all = shares_all[shares_all["日期"] >= "2026-01-01"][["基金代码", "日期"]].drop_duplicates()
    if os.path.exists(gaps_path):
        gaps = pd.read_csv(gaps_path, dtype={"基金代码": str})
    else:
        m = s26_all.merge(nav_df[["基金代码", "日期"]], on=["基金代码", "日期"], how="left", indicator=True)
        miss = m[m["_merge"] == "left_only"].copy()
        miss["月份"] = miss["日期"].str[:7]
        gaps = miss.groupby(["基金代码", "月份"]).size().reset_index(name="缺日数")
        gaps.to_csv(gaps_path, index=False)
    gaps["基金代码"] = gaps["基金代码"].str.zfill(6)
    print(f"缺口: {len(gaps)}个(代码×月份)")

    new_rows = []
    # 按月分组，每月内按40只分块查询
    for ym, grp in gaps.groupby("月份"):
        codes = sorted(grp["基金代码"].unique())
        print(f"{ym}: {len(codes)}只")
        def work(cs):
            df = query_month(cs, ym)
            if df.empty and len(cs) > 10:
                time.sleep(2)
                # 减半重试
                mid = len(cs) // 2
                df = pd.concat([work(cs[:mid]), work(cs[mid:])], ignore_index=True)
            return df
        t0 = time.time()
        for i in range(0, len(codes), 40):
            chunk = codes[i:i+40]
            df = work(chunk)
            if not df.empty:
                new_rows.append(df)
                print(f"  +{len(df)}行 ({chunk[0]}..{chunk[-1]}) [{time.time()-t0:.0f}s]")
            else:
                print(f"  仍为0行: {chunk}")
            time.sleep(0.5)

    if new_rows:
        add = pd.concat(new_rows, ignore_index=True)
        add["基金代码"] = add["基金代码"].astype(str).str.zfill(6)
        nav_df = pd.concat([nav_df, add], ignore_index=True)
        nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
        nav_df.to_csv(csv_path, index=False)
        print(f"本轮新增: {len(add)}行")

    # 重新评估缺口
    shares = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    s26 = shares[shares["日期"] >= "2026-01-01"][["基金代码", "日期"]].drop_duplicates()
    m = s26.merge(nav_df[["基金代码", "日期"]], on=["基金代码", "日期"], how="left", indicator=True)
    miss = m[m["_merge"] == "left_only"]
    print(f"剩余缺口: {len(miss)}条")
    miss_codes = sorted(miss["基金代码"].unique())
    print(f"涉及{len(miss_codes)}只:", miss_codes[:50])

    # 东财兜底
    fixed = 0
    for c in miss_codes:
        ed = fetch_etf_nav_history(c, page_size=300)
        if ed.empty:
            time.sleep(1.2)
            continue
        ed = ed[["日期", "单位净值"]].copy()
        ed["基金代码"] = c
        ed["日期"] = ed["日期"].astype(str)
        need = set(miss[miss["基金代码"] == c]["日期"])
        ed = ed[ed["日期"].isin(need)]
        if not ed.empty:
            nav_df = pd.concat([nav_df, ed[["基金代码", "日期", "单位净值"]]], ignore_index=True)
            fixed += len(ed)
            print(f"  东财{c}: +{len(ed)}行")
        time.sleep(1.2)
    nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
    nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)

    # 最终缺口
    m2 = s26.merge(nav_df[["基金代码", "日期"]], on=["基金代码", "日期"], how="left", indicator=True)
    final_miss = m2[m2["_merge"] == "left_only"]
    print(f"最终缺口: {len(final_miss)}条 (东财修复{fixed}行)")
    if len(final_miss):
        final_miss.to_csv(os.path.join(CACHE_DIR, "nav_gaps.csv"), index=False)
    print(f"NAV合计: {len(nav_df)}行")

if __name__ == "__main__":
    main()
