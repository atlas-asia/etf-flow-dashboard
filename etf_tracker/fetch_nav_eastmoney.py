# -*- coding: utf-8 -*-
"""CI 用：通过东方财富 lsjz 接口批量获取 ETF 历史单位净值（免费、无密钥、纯 requests）。
- 只取份额有变动的 ETF
- 增量保存到 cache/nav_gildata.csv，并生成 cache/nav_all.pkl
- 输出格式（基金代码,日期,单位净值）与 fetch_nav_gildata.py 完全一致，recalculate_gildata.py 无需改动

注意：
- 不依赖 akshare（其接口随版本变动易崩），直接用 requests 调东财公开接口。
- 东财 lsjz 接口有效每页固定 20 条，pageSize 填过大反而返回空，故用 pageSize=20 翻页。
- 带 startDate=2026-01-01 只取 2026 年数据，减少请求量。
"""
import os, sys, time
import requests
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR

EM_URL = "https://api.fund.eastmoney.com/f10/lsjz"
EM_HEADERS = {
    "Referer": "https://fundf10.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def fetch_nav_one(code, max_pages=60):
    """返回 DataFrame[基金代码, 日期, 单位净值]，取不到返回空表。"""
    rows = []
    try:
        for page in range(1, max_pages + 1):
            params = {
                "fundCode": code,
                "pageIndex": page,
                "pageSize": 20,
                "startDate": "2026-01-01",
                "endDate": "",
            }
            resp = requests.get(EM_URL, params=params, headers=EM_HEADERS, timeout=20)
            j = resp.json()
            lst = (j.get("Data") or {}).get("LSJZList") or []
            if not lst:
                break
            rows.extend(lst)
            if len(lst) < 20:
                break
            time.sleep(0.1)
        if not rows:
            return pd.DataFrame(columns=["基金代码", "日期", "单位净值"])
        df = pd.DataFrame(rows)
        df = df.rename(columns={"FSRQ": "日期", "DWJZ": "单位净值"})
        df["日期"] = df["日期"].astype(str)
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        df = df.dropna(subset=["单位净值"])
        # 兜底：仅保留 2026 年及以后
        df = df[df["日期"] >= "2026-01-01"]
        df["基金代码"] = code
        return df[["基金代码", "日期", "单位净值"]]
    except Exception as e:
        print(f"  {code} NAV获取失败: {e}", flush=True)
        return pd.DataFrame(columns=["基金代码", "日期", "单位净值"])


def main():
    shares = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    shares = shares.sort_values(["基金代码", "日期"])
    shares["前日份额"] = shares.groupby("基金代码")["基金份额"].shift(1)
    shares["份额变动"] = shares["基金份额"] - shares["前日份额"]
    s2026 = shares[shares["日期"] >= "2026-01-01"]
    changed = sorted(s2026.loc[s2026["份额变动"].fillna(0).ne(0), "基金代码"].unique())
    print(f"份额有变动的ETF: {len(changed)}只", flush=True)

    csv_path = os.path.join(CACHE_DIR, "nav_gildata.csv")
    if os.path.exists(csv_path):
        nav_df = pd.read_csv(csv_path, dtype={"基金代码": str})
        nav_df["基金代码"] = nav_df["基金代码"].str.zfill(6)
    else:
        nav_df = pd.DataFrame(columns=["基金代码", "日期", "单位净值"])

    end_date = s2026["日期"].max()
    total = len(changed)
    ok = 0
    for i, code in enumerate(changed, 1):
        df = fetch_nav_one(code)
        if not df.empty:
            nav_df = pd.concat([nav_df, df], ignore_index=True)
            ok += 1
        if i % 10 == 0:
            nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
            print(f"  [{i}/{total}] 已处理, 成功{ok}只, 累计{len(nav_df)}行", flush=True)
        time.sleep(0.2)

    nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
    nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
    if len(nav_df):
        nav_df = nav_df[(nav_df["日期"] >= "2026-01-01") & (nav_df["日期"] <= end_date)]
    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)
    print(f"NAV合计: {len(nav_df)}行, 覆盖{nav_df['基金代码'].nunique()}只, "
          f"日期{nav_df['日期'].min() if len(nav_df) else 'NA'}~{nav_df['日期'].max() if len(nav_df) else 'NA'}", flush=True)


if __name__ == "__main__":
    main()
