# -*- coding: utf-8 -*-
"""导出当前场内ETF代码、名称及分类清单。"""
import os
import sys
from datetime import datetime
import pandas as pd
import akshare as ak

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import classify_etf

OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_ORDER = {"宽基ETF": 1, "行业ETF": 2, "风格ETF": 3, "港股ETF": 4, "其他ETF": 5}

spot = ak.fund_etf_spot_em()
spot = spot.rename(columns={"代码": "基金代码", "名称": "基金简称"})
spot["基金代码"] = spot["基金代码"].astype(str).str.zfill(6)
spot[["主分类", "子分类"]] = spot["基金简称"].apply(lambda x: pd.Series(classify_etf(x)))
spot["主分类排序"] = spot["主分类"].map(MAIN_ORDER).fillna(99)
spot = spot.sort_values(["主分类排序", "子分类", "基金代码"]).drop(columns=["主分类排序"])

keep = ["基金代码", "基金简称", "主分类", "子分类", "最新价", "最新份额", "流通市值", "总市值", "数据日期", "更新时间"]
for col in keep:
    if col not in spot.columns:
        spot[col] = None
catalog = spot[keep].copy()
for col in ["数据日期", "更新时间"]:
    catalog[col] = catalog[col].astype(str)
catalog["数据来源"] = "东方财富 fund_etf_spot_em；分类为项目关键词规则"
catalog["导出时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

csv_path = os.path.join(OUT_DIR, "etf_catalog_classified.csv")
xlsx_path = os.path.join(OUT_DIR, "etf_catalog_classified.xlsx")
catalog.to_csv(csv_path, index=False, encoding="utf-8-sig")
with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    catalog.to_excel(writer, index=False, sheet_name="ETF分类清单")
    summary = catalog.groupby(["主分类", "子分类"], sort=False).agg(ETF数量=("基金代码", "nunique")).reset_index()
    summary.to_excel(writer, index=False, sheet_name="分类汇总")

print(f"records={len(catalog)}")
print(f"unique_codes={catalog['基金代码'].nunique()}")
print(f"duplicate_codes={catalog['基金代码'].duplicated().sum()}")
print(catalog.groupby("主分类", sort=False)["基金代码"].nunique().to_string())
print(csv_path)
print(xlsx_path)
