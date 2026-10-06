# -*- coding: utf-8 -*-
"""
ETF净流动计算和聚合模块
净流动 = (当日份额 - 前一日份额) * 当日净值
"""

import pandas as pd
import numpy as np
from config import classify_etf


def calculate_net_flow(shares_df, nav_dict):
    """
    计算每只ETF每日的净流动

    参数:
        shares_df: DataFrame[日期, 基金代码, 基金简称, 基金份额]
        nav_dict: dict {基金代码: DataFrame[日期, 单位净值, ...]}

    返回: DataFrame[日期, 基金代码, 基金简称, 主分类, 子分类,
                   当日份额, 前日份额, 份额变动, 当日净值, 净流动(元)]
    """
    print("  计算ETF净流动...")

    # 确保数据类型正确
    shares_df = shares_df.copy()
    shares_df["基金份额"] = pd.to_numeric(shares_df["基金份额"], errors="coerce")
    shares_df["日期"] = shares_df["日期"].astype(str)
    shares_df = shares_df.dropna(subset=["基金份额"])
    shares_df = shares_df.sort_values(["基金代码", "日期"]).reset_index(drop=True)

    # 获取所有ETF代码和名称
    etf_info = shares_df.groupby("基金代码").agg({
        "基金简称": "last"
    }).reset_index()

    # 分类所有ETF
    etf_info["主分类"] = etf_info["基金简称"].apply(lambda x: classify_etf(x)[0])
    etf_info["子分类"] = etf_info["基金简称"].apply(lambda x: classify_etf(x)[1])

    # 构建分类映射
    classify_map = dict(zip(etf_info["基金代码"], zip(etf_info["主分类"], etf_info["子分类"])))
    name_map = dict(zip(etf_info["基金代码"], etf_info["基金简称"]))

    # 按ETF代码分组，计算份额变动
    all_flows = []

    for code, group in shares_df.groupby("基金代码"):
        group = group.sort_values("日期").reset_index(drop=True)
        group["前日份额"] = group["基金份额"].shift(1)
        group["份额变动"] = group["基金份额"] - group["前日份额"]

        # 第一天的份额变动设为0（没有前日数据）
        group.loc[group.index[0], "份额变动"] = 0

        # 获取净值
        main_cat, sub_cat = classify_map.get(code, ("其他ETF", "其他"))
        nav_df = nav_dict.get(code)

        if nav_df is not None and not nav_df.empty:
            # 将净值合并到份额数据上
            nav_df = nav_df.copy()
            nav_df["日期"] = nav_df["日期"].astype(str)
            nav_map = dict(zip(nav_df["日期"], nav_df["单位净值"]))
            group["当日净值"] = group["日期"].map(nav_map)
        else:
            group["当日净值"] = np.nan

        # 如果净值缺失，用最新可用的净值填充
        if group["当日净值"].isna().any():
            valid_navs = group.dropna(subset=["当日净值"])[["日期", "当日净值"]]
            if not valid_navs.empty:
                latest_nav = valid_navs["当日净值"].iloc[-1]
                group["当日净值"] = group["当日净值"].fillna(latest_nav)
            else:
                # 如果完全没有净值数据，用1作为占位
                group["当日净值"] = group["当日净值"].fillna(1.0)

        # 计算净流动 = 份额变动 * 当日净值
        group["净流动"] = group["份额变动"] * group["当日净值"]

        group["主分类"] = main_cat
        group["子分类"] = sub_cat
        group["基金代码"] = code
        group["基金简称"] = name_map.get(code, code)

        all_flows.append(group[["日期", "基金代码", "基金简称", "主分类", "子分类",
                                 "基金份额", "前日份额", "份额变动", "当日净值", "净流动"]].rename(
            columns={"基金份额": "当日份额"}
        ))

    if all_flows:
        result = pd.concat(all_flows, ignore_index=True)
        result = result.sort_values(["日期", "主分类", "子分类"]).reset_index(drop=True)
        print(f"  完成: {len(result)} 条净流动记录")
        return result
    else:
        return pd.DataFrame(columns=["日期", "基金代码", "基金简称", "主分类", "子分类",
                                      "当日份额", "前日份额", "份额变动", "当日净值", "净流动"])


def aggregate_by_category(flow_df, freq="daily"):
    """
    按分类聚合净流动

    参数:
        flow_df: DataFrame from calculate_net_flow
        freq: "daily", "weekly", "monthly"

    返回: DataFrame[日期/周/月, 主分类, 子分类, 净流动合计, ETF数量]
    """
    if flow_df.empty:
        return pd.DataFrame()

    df = flow_df.copy()
    df["净流动"] = pd.to_numeric(df["净流动"], errors="coerce").fillna(0)

    if freq == "daily":
        df["期间"] = df["日期"]
    elif freq == "weekly":
        df["期间"] = pd.to_datetime(df["日期"]).dt.to_period("W").astype(str)
    elif freq == "monthly":
        df["期间"] = pd.to_datetime(df["日期"]).dt.to_period("M").astype(str)
    else:
        df["期间"] = df["日期"]

    result = df.groupby(["期间", "主分类", "子分类"]).agg({
        "净流动": "sum",
        "基金代码": "nunique"
    }).reset_index()
    result = result.rename(columns={"基金代码": "ETF数量"})

    # 转换净流动为亿元
    result["净流动(亿元)"] = result["净流动"] / 1e8
    result = result.drop(columns=["净流动"])

    return result.sort_values(["期间", "主分类", "子分类"]).reset_index(drop=True)


def get_latest_week_summary(flow_df):
    """
    获取最新一周各分类的净流动汇总
    """
    if flow_df.empty:
        return pd.DataFrame()

    df = flow_df.copy()
    df["净流动"] = pd.to_numeric(df["净流动"], errors="coerce").fillna(0)

    # 获取最新日期
    dates = sorted(df["日期"].unique())
    if len(dates) < 1:
        return pd.DataFrame()

    latest_date = dates[-1]
    latest_dt = pd.to_datetime(latest_date)
    # 往前推7天
    week_start = (latest_dt - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
    week_dates = [d for d in dates if d >= week_start]

    week_df = df[df["日期"].isin(week_dates)]

    result = week_df.groupby(["主分类", "子分类"]).agg({
        "净流动": "sum",
        "基金代码": "nunique"
    }).reset_index()
    result = result.rename(columns={"基金代码": "ETF数量"})
    result["净流动(亿元)"] = result["净流动"] / 1e8
    result = result.drop(columns=["净流动"])
    result["期间"] = f"{week_dates[0]} ~ {latest_date}"
    result = result.sort_values(["主分类", "子分类"]).reset_index(drop=True)

    return result


def get_monthly_summary(flow_df):
    """
    获取每月各分类的净流动汇总
    """
    return aggregate_by_category(flow_df, freq="monthly")


def get_daily_category_summary(flow_df):
    """
    获取每日各主分类的净流动汇总
    """
    if flow_df.empty:
        return pd.DataFrame()

    df = flow_df.copy()
    df["净流动"] = pd.to_numeric(df["净流动"], errors="coerce").fillna(0)

    result = df.groupby(["日期", "主分类"]).agg({
        "净流动": "sum",
        "基金代码": "nunique"
    }).reset_index()
    result = result.rename(columns={"基金代码": "ETF数量"})
    result["净流动(亿元)"] = result["净流动"] / 1e8
    result = result.drop(columns=["净流动"])

    return result.sort_values(["日期", "主分类"]).reset_index(drop=True)


def get_top_etfs_by_flow(flow_df, top_n=20, ascending=False):
    """
    获取净流动最大的ETF
    """
    if flow_df.empty:
        return pd.DataFrame()

    df = flow_df.copy()
    df["净流动"] = pd.to_numeric(df["净流动"], errors="coerce").fillna(0)

    # 按ETF聚合
    result = df.groupby(["基金代码", "基金简称", "主分类", "子分类"]).agg({
        "净流动": "sum"
    }).reset_index()
    result["净流动(亿元)"] = result["净流动"] / 1e8
    result = result.drop(columns=["净流动"])

    if ascending:
        result = result.sort_values("净流动(亿元)").head(top_n)
    else:
        result = result.sort_values("净流动(亿元)", ascending=False).head(top_n)

    return result.reset_index(drop=True)
