# -*- coding: utf-8 -*-
"""
ETF数据获取模块
数据源:
1. 上交所(SSE) ETF份额: SSE API via curl_cffi
2. 深交所(SZSE) ETF份额: akshare fund_scale_daily_szse
3. ETF实时行情(价格/份额): akshare fund_etf_spot_em
4. ETF历史净值: 东方财富 lsjz API via curl_cffi
5. ETF历史价格: 新浪API via akshare fund_etf_hist_sina
"""

import os
import json
import time
import datetime
import pandas as pd
from curl_cffi import requests as cffi_requests

import akshare as ak

# 数据缓存目录
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# SSE API配置
SSE_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36",
}

# 东方财富净值API
NAV_API_URL = "https://api.fund.eastmoney.com/f10/lsjz"
NAV_HEADERS = {
    "Referer": "http://fundf10.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_cache_path(filename):
    """获取缓存文件路径"""
    return os.path.join(CACHE_DIR, filename)


def save_cache(filename, data):
    """保存数据到缓存"""
    path = get_cache_path(filename)
    if isinstance(data, pd.DataFrame):
        data.to_pickle(path)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)


def load_cache(filename):
    """从缓存加载数据"""
    path = get_cache_path(filename)
    if not os.path.exists(path):
        return None
    if filename.endswith(".pkl"):
        return pd.read_pickle(path)
    elif filename.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def fetch_sse_etf_shares(date_str):
    """
    获取上交所ETF份额数据
    date_str: 日期字符串，格式 '2026-08-19'
    返回: DataFrame[基金代码, 基金简称, 基金份额]
    """
    data_str = date_str  # SSE API接受的日期格式
    params = {
        "isPagination": "true",
        "pageHelp.pageSize": "10000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "1",
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": data_str,
    }
    try:
        resp = cffi_requests.get(SSE_URL, params=params, headers=SSE_HEADERS, impersonate="chrome", timeout=20)
        data = resp.json()
        result = data.get("result", [])
        if not result:
            return pd.DataFrame(columns=["基金代码", "基金简称", "基金份额", "日期"])

        df = pd.DataFrame(result)
        df = df.rename(columns={
            "SEC_CODE": "基金代码",
            "SEC_NAME": "基金简称",
            "TOT_VOL": "基金份额",
        })
        df["基金份额"] = pd.to_numeric(df["基金份额"], errors="coerce") * 10000  # 万份转为份
        df["日期"] = date_str
        return df[["基金代码", "基金简称", "基金份额", "日期"]]
    except Exception as e:
        print(f"  SSE API error for {date_str}: {e}")
        return pd.DataFrame(columns=["基金代码", "基金简称", "基金份额", "日期"])


def fetch_szse_etf_shares(start_date, end_date):
    """
    获取深交所ETF份额数据。接口不支持过长区间，因此按自然月分批请求。
    start_date, end_date: 日期字符串，格式 '20260801'
    返回: DataFrame[日期, 基金代码, 基金简称, 基金份额]
    """
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    chunks = []
    cursor = start

    while cursor <= end:
        month_end = min(cursor + pd.offsets.MonthEnd(0), end)
        try:
            df = ak.fund_scale_daily_szse(
                start_date=cursor.strftime("%Y%m%d"),
                end_date=month_end.strftime("%Y%m%d")
            )
            if not df.empty:
                df["日期"] = df["日期"].astype(str)
                chunks.append(df)
        except Exception as e:
            print(f"  SZSE API error {cursor:%Y-%m-%d}~{month_end:%Y-%m-%d}: {e}")
        cursor = month_end + pd.Timedelta(days=1)
        time.sleep(0.2)

    if not chunks:
        return pd.DataFrame(columns=["日期", "基金代码", "基金简称", "基金份额"])

    result = pd.concat(chunks, ignore_index=True)
    return result.drop_duplicates(subset=["日期", "基金代码"], keep="last")


def fetch_etf_spot():
    """
    获取ETF实时行情(包含最新份额和价格)
    返回: DataFrame
    """
    df = ak.fund_etf_spot_em()
    # 重命名关键列
    df = df.rename(columns={
        "代码": "基金代码",
        "名称": "基金简称",
        "最新价": "最新价",
        "最新份额": "最新份额",
        "数据日期": "数据日期",
    })
    return df


def fetch_etf_nav_history(fund_code, page_size=200):
    """
    获取ETF历史净值数据(东方财富API)
    返回: DataFrame[日期, 单位净值, 累计净值, 日增长率]
    """
    params = {
        "fundCode": fund_code,
        "pageIndex": 1,
        "pageSize": page_size,
    }
    try:
        resp = cffi_requests.get(NAV_API_URL, params=params, headers=NAV_HEADERS, impersonate="chrome", timeout=15)
        data = resp.json()
        lsjz_list = data.get("Data", {}).get("LSJZList", [])
        if not lsjz_list:
            return pd.DataFrame(columns=["日期", "单位净值", "累计净值", "日增长率"])

        df = pd.DataFrame(lsjz_list)
        df = df.rename(columns={
            "FSRQ": "日期",
            "DWJZ": "单位净值",
            "LJJZ": "累计净值",
            "JZZZL": "日增长率",
        })
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        df["累计净值"] = pd.to_numeric(df["累计净值"], errors="coerce")
        return df[["日期", "单位净值", "累计净值", "日增长率"]]
    except Exception as e:
        return pd.DataFrame(columns=["日期", "单位净值", "累计净值", "日增长率"])


def fetch_etf_price_sina(symbol):
    """
    获取ETF历史价格数据(新浪API)
    symbol: 格式 'sh510050' 或 'sz159919'
    返回: DataFrame[date, close, ...]
    """
    try:
        df = ak.fund_etf_hist_sina(symbol=symbol)
        return df
    except Exception:
        return pd.DataFrame()


def get_trading_dates(start_date, end_date):
    """
    获取交易日列表(排除周末)
    注意: 不包含节假日处理，需要后续过滤
    """
    dates = pd.bdate_range(start=start_date, end=end_date)
    return [d.strftime("%Y-%m-%d") for d in dates]


def fetch_all_etf_shares(trading_dates):
    """
    获取所有ETF份额数据(SSE + SZSE)
    trading_dates: 交易日列表 ['2026-08-01', ...]
    返回: DataFrame[日期, 基金代码, 基金简称, 基金份额]
    """
    all_data = []

    # 1. 获取深交所数据(一次API调用)
    print("  获取深交所ETF份额数据...")
    szse_start = trading_dates[0].replace("-", "")
    szse_end = trading_dates[-1].replace("-", "")
    szse_df = fetch_szse_etf_shares(szse_start, szse_end)
    if not szse_df.empty:
        szse_df["日期"] = szse_df["日期"].astype(str)
        # 确保份额是数值
        szse_df["基金份额"] = pd.to_numeric(szse_df["基金份额"], errors="coerce")
        all_data.append(szse_df)
        print(f"    深交所: {len(szse_df)} 条记录")

    # 2. 获取上交所数据(逐日获取)
    print("  获取上交所ETF份额数据...")
    sse_data = []
    for date in trading_dates:
        sse_df = fetch_sse_etf_shares(date)
        if not sse_df.empty:
            sse_data.append(sse_df)
            print(f"    {date}: {len(sse_df)} 只ETF")
        time.sleep(0.3)  # 避免请求过快

    if sse_data:
        sse_combined = pd.concat(sse_data, ignore_index=True)
        all_data.append(sse_combined)
        print(f"    上交所合计: {len(sse_combined)} 条记录")

    if all_data:
        result = pd.concat(all_data, ignore_index=True)
        result["基金份额"] = pd.to_numeric(result["基金份额"], errors="coerce")
        result["日期"] = result["日期"].astype(str)
        return result
    else:
        return pd.DataFrame(columns=["日期", "基金代码", "基金简称", "基金份额"])


def fetch_all_etf_prices(etf_codes, etf_names):
    """
    批量获取ETF净值数据
    etf_codes: ETF代码列表
    etf_names: 对应的ETF名称列表
    返回: dict {代码: DataFrame[日期, 单位净值]}
    """
    result = {}
    total = len(etf_codes)
    print(f"  开始获取 {total} 只ETF的净值数据...")

    for i, (code, name) in enumerate(zip(etf_codes, etf_names)):
        nav_df = fetch_etf_nav_history(code)
        if not nav_df.empty:
            result[code] = nav_df

        if (i + 1) % 50 == 0:
            print(f"    进度: {i+1}/{total} ({(i+1)/total*100:.0f}%)")
        time.sleep(0.05)  # 避免请求过快

    print(f"  完成: 获取了 {len(result)} 只ETF的净值数据")
    return result
