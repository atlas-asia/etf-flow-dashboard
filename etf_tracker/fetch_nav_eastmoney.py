# -*- coding: utf-8 -*-
"""CI 用：通过东方财富 lsjz 接口批量获取 ETF 历史单位净值（免费、无密钥）。
- 只取份额有变动的 ETF
- 增量保存到 cache/nav_gildata.csv，并生成 cache/nav_all.pkl
- 输出格式与 fetch_nav_gildata.py 完全一致，recalculate_gildata.py 无需改动
实现：使用 akshare 的 fund_etf_fund_info_em（东方财富通道，GitHub 海外服务器可访问），
      不再依赖 curl_cffi（其在 GitHub runner 上 impersonate 会抛异常导致取数为 0）。
"""
import os, sys, time
import pandas as pd
import akshare as ak
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR


def fetch_nav_one(code):
    """返回 DataFrame[基金代码, 日期, 单位净值]，取不到返回空表。"""
    try:
        df = ak.fund_etf_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            return pd.DataFrame(columns=["基金代码", "日期", "单位净值"])
        # 兼容不同 akshare 版本的列名
        df = df.rename(columns={"净值日期": "日期", "单位净值": "单位净值"})
        if "日期" not in df.columns and len(df.columns) >= 1:
            df = df.rename(columns={df.columns[0]: "日期"})
        if "单位净值" not in df.columns and len(df.columns) >= 2:
            df = df.rename(columns={df.columns[1]: "单位净值"})
        df = df[["日期", "单位净值"]].copy()
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        df = df.dropna(subset=["单位净值"])
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
    for i, code in enumerate(changed, 1):
        df = fetch_nav_one(code)
        if not df.empty:
            nav_df = pd.concat([nav_df, df], ignore_index=True)
        if i % 50 == 0:
            nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
            print(f"  [{i}/{total}] 已处理, 累计{len(nav_df)}行", flush=True)
        time.sleep(0.3)

    nav_df = nav_df.drop_duplicates(["基金代码", "日期"], keep="last")
    nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
    if len(nav_df):
        nav_df = nav_df[(nav_df["日期"] >= "2026-01-01") & (nav_df["日期"] <= end_date)]
    nav_df = nav_df.sort_values(["基金代码", "日期"])
    pd.to_pickle(nav_df, os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df.to_csv(csv_path, index=False)
    print(f"NAV合计: {len(nav_df)}行, 覆盖{nav_df['基金代码'].nunique()}只, "
          f"日期{nav_df['日期'].min() if len(nav_df) else 'NA'}~{nav_df['日期'].max() if len(nav_df) else 'NA'}", flush=True)


if __name__ == "__&#8203;main__":
    main()
