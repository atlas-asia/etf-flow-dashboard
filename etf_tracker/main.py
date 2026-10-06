# -*- coding: utf-8 -*-
"""
ETF净流动跟踪系统 - 主程序
功能:
1. 获取市场上所有ETF的份额数据(SSE+SZSE)
2. 按分类计算每日净流动(份额变动*净值)
3. 统计月度和最新一周各分类ETF净流动情况
4. 生成HTML仪表盘

运行: python main.py
"""

import sys
import os
import json
import time
import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import classify_etf, ETF_CLASSIFICATION
from data_fetcher import (
    fetch_etf_spot, fetch_sse_etf_shares, fetch_szse_etf_shares,
    fetch_etf_nav_history, get_trading_dates,
    load_cache, save_cache
)
from calculator import (
    calculate_net_flow, aggregate_by_category,
    get_latest_week_summary, get_monthly_summary,
    get_daily_category_summary, get_top_etfs_by_flow
)
from dashboard import generate_dashboard


def main():
    print("=" * 60)
    print("ETF净流动跟踪系统")
    print("=" * 60)

    # 设置日期范围：额外获取2025年末作为2026年首个交易日的前值基数
    today = datetime.date.today()
    reporting_start = datetime.date(2026, 1, 1)
    start_date = datetime.date(2025, 12, 31)

    print(f"取数范围: {start_date} ~ {today}")
    print(f"统计范围: {reporting_start} ~ {today}")
    print()

    # 步骤1: 获取ETF列表
    print("[1/5] 获取ETF列表...")
    spot_df = fetch_etf_spot()
    print(f"  共 {len(spot_df)} 只ETF")
    print()

    # 步骤2: 获取所有ETF份额数据
    print("[2/5] 获取ETF份额数据...")
    trading_dates = get_trading_dates(start_date, today)

    # 获取深交所数据
    print("  获取深交所ETF份额数据...")
    szse_df = fetch_szse_etf_shares(start_date.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
    print(f"    深交所: {len(szse_df)} 条记录")

    # 获取上交所数据(逐日)
    print("  获取上交所ETF份额数据(逐日)...")
    sse_dfs = []
    for d in trading_dates:
        sse_df = fetch_sse_etf_shares(d)
        if not sse_df.empty:
            sse_dfs.append(sse_df)
        time.sleep(0.3)
    sse_df = pd.concat(sse_dfs, ignore_index=True) if sse_dfs else pd.DataFrame()
    print(f"    上交所: {len(sse_df)} 条记录")

    # 合并
    shares_df = pd.concat([sse_df, szse_df], ignore_index=True) if not sse_df.empty else szse_df
    shares_df["基金份额"] = pd.to_numeric(shares_df["基金份额"], errors="coerce")
    shares_df = shares_df.dropna(subset=["基金份额"])
    print(f"  合计: {len(shares_df)} 条记录, {shares_df['基金代码'].nunique()} 只ETF")
    print()

    # 步骤3: 分析份额变动，只获取有变动ETF的净值
    print("[3/5] 分析份额变动并获取净值数据...")
    shares_sorted = shares_df.sort_values(["基金代码", "日期"]).copy()
    shares_sorted["前日份额"] = shares_sorted.groupby("基金代码")["基金份额"].shift(1)
    shares_sorted["份额变动"] = shares_sorted["基金份额"] - shares_sorted["前日份额"]
    shares_sorted.loc[shares_sorted.groupby("基金代码").head(1).index, "份额变动"] = 0

    changed_etfs = shares_sorted[shares_sorted["份额变动"].abs() > 0]["基金代码"].unique()
    print(f"  有份额变动的ETF: {len(changed_etfs)} 只")

    # 获取有变动ETF的净值数据
    etf_names = shares_df.drop_duplicates("基金代码").set_index("基金代码")["基金简称"].to_dict()
    nav_dict = {}
    for i, code in enumerate(changed_etfs):
        nav_df = fetch_etf_nav_history(code)
        if not nav_df.empty:
            nav_dict[code] = nav_df
        if (i + 1) % 200 == 0:
            print(f"    进度: {i+1}/{len(changed_etfs)}")
        time.sleep(0.05)
    print(f"  获取了 {len(nav_dict)} 只ETF的净值数据")
    print()

    # 步骤4: 计算净流动
    print("[4/5] 计算ETF净流动...")
    shares_clean = shares_df[["日期", "基金代码", "基金简称", "基金份额"]].copy()
    flow_df = calculate_net_flow(shares_clean, nav_dict)
    # 2025-12-31仅作为首日基数，不纳入2026年统计
    flow_df = flow_df[flow_df["日期"] >= reporting_start.strftime("%Y-%m-%d")].copy()
    print(f"  2026年以来净流动记录: {len(flow_df)} 条")
    print()

    # 步骤5: 聚合统计
    print("[5/5] 生成统计报表...")
    daily_summary = get_daily_category_summary(flow_df)
    monthly_summary = get_monthly_summary(flow_df)
    weekly_summary = get_latest_week_summary(flow_df)
    top_inflow = get_top_etfs_by_flow(flow_df, top_n=20, ascending=False)
    top_outflow = get_top_etfs_by_flow(flow_df, top_n=20, ascending=True)
    monthly_detail = aggregate_by_category(flow_df, freq="monthly")
    weekly_detail = aggregate_by_category(flow_df, freq="weekly")

    print(f"  日度汇总: {len(daily_summary)} 条")
    print(f"  月度汇总: {len(monthly_summary)} 条")
    print(f"  周度汇总: {len(weekly_summary)} 条")
    print(f"  流入TOP20: {len(top_inflow)} 条")
    print(f"  流出TOP20: {len(top_outflow)} 条")
    print()

    # 生成HTML仪表盘
    print("生成HTML仪表盘...")
    output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(output_dir, "etf_flow_dashboard.html")

    # 准备ETF分类信息
    etf_classified = []
    all_codes = shares_df["基金代码"].unique()
    for code in all_codes:
        name = etf_names.get(code, code)
        main_cat, sub_cat = classify_etf(name)
        etf_classified.append({
            "code": code,
            "name": name,
            "main_category": main_cat,
            "sub_category": sub_cat
        })

    generate_dashboard(
        output_path=output_path,
        flow_df=flow_df,
        daily_summary=daily_summary,
        monthly_summary=monthly_summary,
        weekly_summary=weekly_summary,
        monthly_detail=monthly_detail,
        weekly_detail=weekly_detail,
        top_inflow=top_inflow,
        top_outflow=top_outflow,
        etf_classified=etf_classified,
        start_date=reporting_start.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d")
    )

    print(f"\n仪表盘已生成: {output_path}")
    print(f"共追踪 {len(all_codes)} 只ETF, {len(flow_df)} 条净流动记录")

    # 打印汇总
    if not flow_df.empty:
        total_flow = flow_df["净流动"].sum() / 1e8
        print(f"区间总净流动: {total_flow:+.2f} 亿元")

        print("\n各主分类净流动:")
        by_cat = flow_df.groupby("主分类").agg({
            "净流动": "sum",
            "基金代码": "nunique"
        }).reset_index()
        by_cat["净流动(亿元)"] = by_cat["净流动"] / 1e8
        for _, row in by_cat.iterrows():
            print(f"  {row['主分类']}: {row['净流动(亿元)']:+.2f} 亿元 ({row['基金代码']} 只ETF)")

    print("=" * 60)


if __name__ == "__main__":
    main()
