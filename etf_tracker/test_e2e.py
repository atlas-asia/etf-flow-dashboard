# -*- coding: utf-8 -*-
"""端到端测试脚本 - 用少量ETF验证完整流程"""

import sys
import os
import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import classify_etf
from data_fetcher import (
    fetch_etf_spot, fetch_all_etf_shares, fetch_all_etf_prices,
    fetch_sse_etf_shares, fetch_szse_etf_shares,
    fetch_etf_nav_history, get_trading_dates
)
from calculator import (
    calculate_net_flow, aggregate_by_category,
    get_latest_week_summary, get_monthly_summary,
    get_daily_category_summary, get_top_etfs_by_flow
)

def main():
    print("=" * 60)
    print("ETF净流动跟踪系统 - 端到端测试")
    print("=" * 60)

    # 日期范围: 本月
    today = datetime.date.today()
    month_start = today.replace(day=1)
    print(f"数据范围: {month_start} ~ {today}")

    # 步骤1: 获取ETF列表
    print("\n[1] 获取ETF列表...")
    spot_df = fetch_etf_spot()
    print(f"  共 {len(spot_df)} 只ETF")

    # 步骤2: 获取份额数据
    print("\n[2] 获取ETF份额数据...")
    trading_dates = get_trading_dates(month_start, today)
    print(f"  交易日: {trading_dates}")

    # 获取SZSE数据
    print("  获取深交所数据...")
    szse_df = fetch_szse_etf_shares(month_start.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
    print(f"  SZSE: {len(szse_df)} 条")

    # 获取SSE数据(逐日)
    print("  获取上交所数据...")
    sse_dfs = []
    for d in trading_dates:
        df = fetch_sse_etf_shares(d)
        if not df.empty:
            sse_dfs.append(df)
            print(f"    {d}: {len(df)} 只")
    sse_df = pd.concat(sse_dfs, ignore_index=True) if sse_dfs else pd.DataFrame()
    print(f"  SSE: {len(sse_df)} 条")

    # 合并
    shares_df = pd.concat([sse_df, szse_df], ignore_index=True)
    shares_df["基金份额"] = pd.to_numeric(shares_df["基金份额"], errors="coerce")
    shares_df = shares_df.dropna(subset=["基金份额"])
    print(f"  合计: {len(shares_df)} 条, {shares_df['基金代码'].nunique()} 只ETF")

    # 步骤3: 计算哪些ETF有份额变动
    print("\n[3] 分析份额变动...")
    shares_df = shares_df.sort_values(["基金代码", "日期"])
    shares_df["前日份额"] = shares_df.groupby("基金代码")["基金份额"].shift(1)
    shares_df["份额变动"] = shares_df["基金份额"] - shares_df["前日份额"]
    shares_df.loc[shares_df.groupby("基金代码").head(1).index, "份额变动"] = 0

    changed_etfs = shares_df[shares_df["份额变动"].abs() > 0]["基金代码"].unique()
    print(f"  有份额变动的ETF: {len(changed_etfs)} 只")

    # 步骤4: 获取有变动的ETF净值数据
    print("\n[4] 获取ETF净值数据(仅有变动的ETF)...")
    nav_dict = {}
    for i, code in enumerate(changed_etfs):
        nav_df = fetch_etf_nav_history(code)
        if not nav_df.empty:
            nav_dict[code] = nav_df
        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{len(changed_etfs)}")
    print(f"  获取了 {len(nav_dict)} 只ETF的净值数据")

    # 步骤5: 计算净流动
    print("\n[5] 计算净流动...")
    # 重置shares_df用于计算
    shares_clean = shares_df[["日期", "基金代码", "基金简称", "基金份额"]].copy()

    flow_df = calculate_net_flow(shares_clean, nav_dict)
    if not flow_df.empty:
        print(f"  净流动记录: {len(flow_df)} 条")
        print(f"  日期范围: {flow_df['日期'].min()} ~ {flow_df['日期'].max()}")
        print(f"  总净流动: {flow_df['净流动'].sum() / 1e8:.2f} 亿元")

        # 按主分类汇总
        print("\n  各主分类净流动:")
        by_cat = flow_df.groupby("主分类").agg({
            "净流动": "sum",
            "基金代码": "nunique"
        }).reset_index()
        by_cat["净流动(亿元)"] = by_cat["净流动"] / 1e8
        for _, row in by_cat.iterrows():
            print(f"    {row['主分类']}: {row['净流动(亿元)']:+.2f} 亿元 ({row['基金代码']} 只ETF)")

        # 月度汇总
        print("\n  月度汇总:")
        monthly = get_monthly_summary(flow_df)
        print(monthly.to_string())

        # 周度汇总
        print("\n  最新一周汇总:")
        weekly = get_latest_week_summary(flow_df)
        print(weekly.to_string())

        # Top流入流出
        print("\n  净流入TOP10:")
        top_in = get_top_etfs_by_flow(flow_df, top_n=10, ascending=False)
        for _, row in top_in.iterrows():
            print(f"    {row['基金代码']} {row['基金简称']}: {row['净流动(亿元)']:+.2f} 亿元")
    else:
        print("  无净流动数据!")

    print("\n" + "=" * 60)
    print("测试完成!")


if __name__ == "__main__":
    main()
