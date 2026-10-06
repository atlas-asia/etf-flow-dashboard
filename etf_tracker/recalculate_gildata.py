# -*- coding: utf-8 -*-
"""使用cache中的份额(shares_all.pkl)与恒生聚源NAV(nav_all.pkl)重算ETF净流动，
输出与reshape_flow_report.py兼容的Excel结构，并同步生成矩阵版报告。"""
import os, sys, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import CACHE_DIR

HERE = os.path.dirname(os.path.abspath(__file__))
_LOCAL_CLASS = r"E:/盈峰资本/FOF研究/宽基跟踪/ETF分类/ETF分类.xlsx"
CLASS_FILE = os.environ.get("ETF_CLASS_FILE") or (
    _LOCAL_CLASS if os.path.exists(_LOCAL_CLASS) else os.path.join(HERE, "ETF分类.xlsx")
)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_XLSX = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026.xlsx")
OUT_HTML = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026.html")
SHEETS = ["宽基ETF", "行业ETF", "风格ETF", "港股ETF"]

def main():
    # 分类映射
    maps = []
    for sheet in SHEETS:
        df = pd.read_excel(CLASS_FILE, sheet_name=sheet).dropna(subset=["分类", "代码"]).copy()
        df["基金代码"] = df["代码"].astype(str).str.extract(r"(\d{6})", expand=False)
        df = df.dropna(subset=["基金代码"])
        df["基金代码"] = df["基金代码"].astype(str).str.zfill(6)
        df["主分类"] = sheet
        maps.append(df[["主分类", "分类", "代码", "基金代码", "名称"]])
    classification = pd.concat(maps, ignore_index=True)
    classification = classification.drop_duplicates(["主分类", "基金代码"], keep="first")
    all_codes = sorted(classification["基金代码"].unique())

    # 份额
    shares = pd.read_pickle(os.path.join(CACHE_DIR, "shares_all.pkl"))
    shares = shares[shares["基金代码"].isin(all_codes)].copy()
    shares = shares.sort_values(["基金代码", "日期"])
    shares["前日份额"] = shares.groupby("基金代码")["基金份额"].shift(1)
    shares["份额变动"] = shares["基金份额"] - shares["前日份额"]

    # NAV
    nav_df = pd.read_pickle(os.path.join(CACHE_DIR, "nav_all.pkl"))
    nav_df = nav_df[nav_df["基金代码"].isin(all_codes)].copy()

    # 净流动：严格按用户确认口径
    # （当日交易所原始份额 - 前一交易日交易所原始份额）× 当日单位净值NAV
    flow_base = shares.merge(nav_df[["基金代码", "日期", "单位净值"]], on=["基金代码", "日期"], how="left")
    flow_base["单位净值"] = flow_base.groupby("基金代码")["单位净值"].transform(lambda s: s.ffill().bfill())
    flow_base["净流动(元)"] = flow_base["份额变动"] * flow_base["单位净值"]
    flow_base["调整后份额变动"] = flow_base["份额变动"]
    flow_base["拆分修正"] = False
    # 仅标记可能的拆分/折算，不改变用户公式计算结果
    flow_base["前日净值"] = flow_base.groupby("基金代码")["单位净值"].shift(1)
    份额比 = flow_base["基金份额"] / flow_base["前日份额"]
    净值比 = flow_base["单位净值"] / flow_base["前日净值"]
    flow_base["拆分修正"] = (((份额比 > 1.30) & (净值比 < 0.85)) | ((份额比 < 0.77) & (净值比 > 1.18))).fillna(False)
    n_split = int(flow_base["拆分修正"].sum())
    if n_split:
        print(f"标记可能拆分/折算: {n_split}条（按用户公式未调整）")
    flow_base = flow_base[flow_base["日期"] >= "2026-01-01"].copy()
    flow_base["月份"] = flow_base["日期"].str[:7]

    flow = flow_base.merge(classification[["主分类", "分类", "基金代码", "名称"]], on="基金代码", how="inner")

    monthly = flow.groupby(["主分类", "月份", "分类"], observed=True).agg(
        净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
    ).reset_index()
    monthly["净流动(亿元)"] = monthly["净流动_元"] / 1e8

    # 最新完整交易周（周一至周五）
    valid_dates = sorted(flow.loc[flow["净流动(元)"].notna(), "日期"].unique())
    latest_date = valid_dates[-1]
    latest_dt = pd.to_datetime(latest_date)
    # 找到latest_date所在日历周（ISO周）
    week_dates = sorted([d for d in valid_dates
                         if pd.to_datetime(d).isocalendar()[:2] == latest_dt.isocalendar()[:2]])
    week = flow[flow["日期"].isin(week_dates)].copy()
    week_start = week_dates[0]
    weekly = week.groupby(["主分类", "分类"], observed=True).agg(
        净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
    ).reset_index()
    weekly["净流动(亿元)"] = weekly["净流动_元"] / 1e8
    weekly["统计区间"] = f"{week_start} ~ {latest_date}"

    etf_detail = flow.groupby(["主分类", "分类", "基金代码", "名称"], observed=True).agg(**{
        "2026年以来净流动_元": ("净流动(元)", "sum"), "数据起始日": ("日期", "min"), "数据截止日": ("日期", "max")
    }).reset_index()
    etf_detail["2026年以来净流动(亿元)"] = etf_detail["2026年以来净流动_元"] / 1e8

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        monthly[["主分类", "月份", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name="全部月度净流动")
        daily_week = flow[flow["日期"].isin(week_dates)].groupby(["主分类", "日期", "分类"], observed=True).agg(净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")).reset_index()
        daily_week["净流动(亿元)"] = daily_week["净流动_元"] / 1e8
        daily_week.to_excel(writer, index=False, sheet_name="最新一周逐日净流动")
        weekly[["统计区间", "主分类", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name="全部最新一周")
        classification.to_excel(writer, index=False, sheet_name="全部分类映射")
        etf_detail[["主分类", "分类", "基金代码", "名称", "2026年以来净流动(亿元)", "数据起始日", "数据截止日"]].to_excel(writer, index=False, sheet_name="全部ETF明细")
        for sheet in SHEETS:
            monthly[monthly["主分类"] == sheet][["月份", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name=f"{sheet[:2]}月度")
            weekly[weekly["主分类"] == sheet][["统计区间", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name=f"{sheet[:2]}周度")

    print("最新周:", week_start, "~", latest_date)
    print("月度行:", len(monthly), "周度行:", len(weekly), "ETF明细:", len(etf_detail))
    print(OUT_XLSX)
    # 同步生成矩阵版
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reshape_flow_report.py")], check=True)

if __name__ == "__main__":
    main()
