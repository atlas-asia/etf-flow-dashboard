# -*- coding: utf-8 -*-
"""CI 用：通过东方财富 lsjz 接口批量获取 ETF 历史单位净值（免费、无密钥）。
- 只取份额有变动的 ETF（与 fetch_nav_gildata.py 口径一致）
- 增量保存到 cache/nav_gildata.csv，并生成 cache/nav_all.pkl
- 输出格式与 fetch_nav_gildata.py 完全一致，recalculate_gildata.py 无需改动
用法: python fetch_nav_eastmoney.py  (建议设置 NAV_SOURCE=eastmoney 走本脚本)
"""
import os, sys, time
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR, fetch_etf_nav_history


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
        try:
            df = fetch_etf_nav_history(code, page_size=1000)
            if not df.empty:
                df = df[["日期", "单位净值"]].copy()
                df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
                df = df.dropna(subset=["单位净值"])
                df["基金代码"] = code
                df = df[["基金代码", "日期", "单位净值"]]
                nav_df = pd.concat([nav_df, df], ignore_index=True)
                ok += 1
        except Exception as e:
            print(f"  {code} 获取失败: {e}", flush=True)
        if i % 50 == 0:
            nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
            print(f"  [{i}/{total}] 已处理, 累计{len(nav_df)}行", flush=True)
        time.sleep(0.3)

    nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
    nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
    nav_df = nav_df[(nav_df["日期"] >= "2026-01-01") & (nav_df["日期"] <= end_date)]
    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)
    print(f"NAV合计: {len(nav_df)}行, 覆盖{nav_df['基金代码'].nunique()}只, "
          f"日期{nav_df['日期'].min()}~{nav_df['日期'].max()}", flush=True)


if __name__ == "__main__":
    main()
