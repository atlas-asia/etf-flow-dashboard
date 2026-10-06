# -*- coding: utf-8 -*-
"""获取2025-12-31至最新交易日的沪深ETF原始份额，保存到cache/shares_all.pkl"""
import os, sys, time, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import fetch_sse_etf_shares, fetch_szse_etf_shares, get_trading_dates, CACHE_DIR

HERE = os.path.dirname(os.path.abspath(__file__))
_LOCAL_CLASS = r"E:/盈峰资本/FOF研究/宽基跟踪/ETF分类/ETF分类.xlsx"
# 本地优先用 E 盘源文件；CI/无 E 盘时回退到随仓库内置的四 Sheet 分类表
CLASS_FILE = os.environ.get("ETF_CLASS_FILE") or (
    _LOCAL_CLASS if os.path.exists(_LOCAL_CLASS) else os.path.join(HERE, "ETF分类.xlsx")
)

maps = []
for sheet in ["宽基ETF", "行业ETF", "风格ETF", "港股ETF"]:
    df = pd.read_excel(CLASS_FILE, sheet_name=sheet).dropna(subset=["分类", "代码"]).copy()
    df["基金代码"] = df["代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    df = df.dropna(subset=["基金代码"])
    df["基金代码"] = df["基金代码"].astype(str).str.zfill(6)
    maps.append(df[["基金代码"]])
codes = set(pd.concat(maps, ignore_index=True)["基金代码"].unique())
print(f"分类ETF总数: {len(codes)}")

start_date = dt.date(2025, 12, 31)
end_date = dt.date.today()
trading_dates = get_trading_dates(start_date, end_date)
print(f"交易日数: {len(trading_dates)}, {trading_dates[0]} ~ {trading_dates[-1]}")

# 深交所（按月）
print("获取深交所份额...")
sz = fetch_szse_etf_shares("20251231", end_date.strftime("%Y%m%d"))
print(f"  深交所: {len(sz)}行")

# 上交所（逐日，可断点续传）
sse_cache = os.path.join(CACHE_DIR, "sse_parts.pkl")
if os.path.exists(sse_cache):
    sse_parts = pd.read_pickle(sse_cache)
else:
    sse_parts = []
done_dates = set(p["日期"].unique() for p in []) # placeholder
done = set()
for p in sse_parts:
    done |= set(p["日期"].unique().tolist()) if hasattr(p["日期"], "unique") else set()
print(f"已完成SSE日期: {len(done)}")

for i, d in enumerate(trading_dates, 1):
    if d in done:
        continue
    part = fetch_sse_etf_shares(d)
    if not part.empty:
        sse_parts.append(part)
    if i % 30 == 0:
        pd.to_pickle(sse_parts, sse_cache)
        print(f"  SSE {i}/{len(trading_dates)}")
    time.sleep(0.15)
pd.to_pickle(sse_parts, sse_cache)

sse = pd.concat(sse_parts, ignore_index=True) if sse_parts else pd.DataFrame()
print(f"  上交所: {len(sse)}行")

shares = pd.concat([sse, sz], ignore_index=True)
shares["基金代码"] = shares["基金代码"].astype(str).str.zfill(6)
shares = shares[shares["基金代码"].isin(codes)].copy()
shares["日期"] = shares["日期"].astype(str)
shares["基金份额"] = pd.to_numeric(shares["基金份额"], errors="coerce")
shares = shares.dropna(subset=["基金份额"]).drop_duplicates(["日期", "基金代码"], keep="last")
shares = shares.sort_values(["基金代码", "日期"])
pd.to_pickle(shares, os.path.join(CACHE_DIR, "shares_all.pkl"))
print(f"合计: {len(shares)}行, 覆盖{shares['基金代码'].nunique()}只, 截至{shares['日期'].max()}")
