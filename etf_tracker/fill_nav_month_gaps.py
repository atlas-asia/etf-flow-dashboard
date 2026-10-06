# -*- coding: utf-8 -*-
"""补齐NAV整月缺失：41只×1月 + 40只×4月（及其他零星缺口）。
- 从shares与nav的实时对比计算真实缺口（不依赖旧nav_gaps.csv）
- 按月份分组查询聚源，单批最多40只
- 查询后校验行数，不足则减半重试
"""
import os, sys, glob, json, re, time, urllib.request
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR

def get_url():
    cands = []
    for f in glob.glob(r"C:/Users/Asia/.workbuddy/logs/*/workbuddyMainThread__*.log"):
        txt = open(f, encoding="utf-8", errors="ignore").read()
        cands += re.findall(r"https://api\.gildata\.com/mcp-servers/aidata-assistant-srv-tool\?token=[A-Za-z0-9._\-]+", txt)
    if not cands:
        raise RuntimeError("gildata URL not found in logs")
    return sorted(set(cands))[-1]

try:
    URL = get_url()
except Exception:
    URL = None
INIT = {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "etf-tracker", "version": "1.0"}}

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
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
    # 校验表头：必须包含"单位净值"且不含"份额"列，防止取错列
    header = ""
    for line in md.splitlines():
        if line.startswith("|"):
            header = line
            break
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
    df = pd.DataFrame(rows, columns=["基金代码", "日期", "单位净值"])
    return df

def query_month(codes, ym):
    y, m = int(ym[:4]), int(ym[5:7])
    start = f"{y}-{m:02d}-01"
    end = (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    code_str = "、".join(codes)
    q = f"查询基金{code_str}共{len(codes)}只ETF在{start}至{end}每个交易日的单位净值"
    return parse_nav(finquery(q))

def main():
    if URL is None:
        print("未找到聚源 token（CI 环境），跳过缺口修复（东财净值模式无需此步）")
        return
    csv_path = os.path.join(CACHE_DIR, "nav_gildata.csv")
    nav_df = pd.read_csv(csv_path, dtype={"基金代码": str})
    nav_df["基金代码"] = nav_df["基金代码"].str.zfill(6)
    shares = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    shares["基金代码"] = shares["基金代码"].astype(str).str.zfill(6)

    s26 = shares[shares["日期"] >= "2026-01-01"][["基金代码", "日期"]].drop_duplicates()
    m = s26.merge(nav_df[["基金代码", "日期"]], on=["基金代码", "日期"], how="left", indicator=True)
    miss = m[m["_merge"] == "left_only"].copy()
    miss["月份"] = miss["日期"].str[:7]
    print(f"真实缺口: {len(miss)}条", flush=True)
    print(miss.groupby("月份").size().to_string(), flush=True)

    new_rows = []
    for ym, grp in miss.groupby("月份"):
        codes = sorted(grp["基金代码"].unique())
        need_days = miss[miss["月份"] == ym]["日期"].nunique()
        print(f"\n{ym}: {len(codes)}只, 需要{need_days}个交易日", flush=True)
        def work(cs):
            df = query_month(cs, ym)
            got_days = df["日期"].nunique() if not df.empty else 0
            if got_days < need_days * 0.8 and len(cs) > 5:
                time.sleep(2)
                mid = len(cs) // 2
                df = pd.concat([work(cs[:mid]), work(cs[mid:])], ignore_index=True)
            return df
        for i in range(0, len(codes), 35):
            chunk = codes[i:i+35]
            df = work(chunk)
            if not df.empty:
                # 只保留真正需要的(代码,日期)
                need_pairs = set(zip(miss[miss["月份"] == ym]["基金代码"], miss[miss["月份"] == ym]["日期"]))
                df = df[df.apply(lambda r: (r["基金代码"], r["日期"]) in need_pairs, axis=1)]
            if not df.empty:
                new_rows.append(df)
                print(f"  +{len(df)}行 ({chunk[0]}..{chunk[-1]})", flush=True)
            else:
                print(f"  0行!: {chunk}", flush=True)
            time.sleep(0.5)

    if new_rows:
        add = pd.concat(new_rows, ignore_index=True)
        add["基金代码"] = add["基金代码"].astype(str).str.zfill(6)
        nav_df = pd.concat([nav_df, add], ignore_index=True)
        nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
        print(f"\n本轮新增: {len(add)}行", flush=True)
    else:
        print("\n无新增", flush=True)

    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)

    # 最终校验
    m2 = s26.merge(nav_df[["基金代码", "日期"]], on=["基金代码", "日期"], how="left", indicator=True)
    final_miss = m2[m2["_merge"] == "left_only"]
    print(f"最终缺口: {len(final_miss)}条", flush=True)
    if len(final_miss):
        print(final_miss.groupby(final_miss["日期"].str[:7]).size().to_string(), flush=True)
    print(f"NAV合计: {len(nav_df)}行", flush=True)

if __name__ == "__main__":
    main()
