# -*- coding: utf-8 -*-
"""测试仪表盘生成 - 使用模拟数据"""
import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import classify_etf
from dashboard import generate_dashboard

# 模拟数据
dates = ["2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19"]
categories = ["宽基ETF", "行业ETF", "风格ETF", "港股ETF", "其他ETF"]

# 模拟flow_df
flow_data = []
np.random.seed(42)
etf_samples = [
    ("510050", "50ETF", "宽基ETF", "上证50"),
    ("510300", "300ETF", "宽基ETF", "沪深300"),
    ("512480", "半导体ETF", "行业ETF", "半导体"),
    ("512890", "红利ETF", "风格ETF", "红利"),
    ("513180", "恒生科技ETF", "港股ETF", "科技"),
    ("588000", "科创50ETF", "宽基ETF", "科创板"),
    ("512000", "券商ETF", "行业ETF", "券商"),
    ("510500", "500ETF", "宽基ETF", "中证500"),
    ("515050", "人工智能ETF", "行业ETF", "人工智能"),
    ("512800", "银行ETF", "行业ETF", "银行"),
]

for date in dates:
    for code, name, main_cat, sub_cat in etf_samples:
        shares = np.random.uniform(1e8, 5e9)
        prev_shares = shares - np.random.uniform(-1e8, 1e8)
        nav = np.random.uniform(0.5, 5.0)
        flow = (shares - prev_shares) * nav
        flow_data.append({
            "日期": date,
            "基金代码": code,
            "基金简称": name,
            "主分类": main_cat,
            "子分类": sub_cat,
            "当日份额": shares,
            "前日份额": prev_shares,
            "份额变动": shares - prev_shares,
            "当日净值": nav,
            "净流动": flow
        })

flow_df = pd.DataFrame(flow_data)

# 模拟聚合数据
from calculator import (
    aggregate_by_category, get_latest_week_summary,
    get_monthly_summary, get_daily_category_summary, get_top_etfs_by_flow
)

daily_summary = get_daily_category_summary(flow_df)
monthly_summary = get_monthly_summary(flow_df)
weekly_summary = get_latest_week_summary(flow_df)
monthly_detail = aggregate_by_category(flow_df, freq="monthly")
weekly_detail = aggregate_by_category(flow_df, freq="weekly")
top_inflow = get_top_etfs_by_flow(flow_df, top_n=10, ascending=False)
top_outflow = get_top_etfs_by_flow(flow_df, top_n=10, ascending=True)

etf_classified = [{"code": c, "name": n, "main_category": mc, "sub_category": sc} 
                  for c, n, mc, sc in etf_samples]

output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_dashboard.html")

print("生成测试仪表盘...")
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
    start_date="2026-08-01",
    end_date="2026-08-20"
)
print(f"测试仪表盘已生成: {output_path}")
