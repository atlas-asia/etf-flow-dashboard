# -*- coding: utf-8 -*-
"""获取2025-12-31至最新交易日的沪深ETF原始份额，保存到cache/shares_all.pkl

2026-10-27 加固版：
- 上交所(SSE) 接口偶发整段返回空（cookie 失效/海外机房被限流），此前会静默跳过，
  导致报告只用深交所数据算出「一堆 0」。现在：
  1) 最近 10 个交易日的 SSE 数据失败会自动重试（刷新 cookie + 退避）；
  2) 抓完后强制校验「沪深两个交易所的最新日期差 ≤ 1 个交易日」，否则直接抛错，
     让工作流红灯、GitHub Pages 保留上一次正确版本，不再发布半截数据。
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import fetch_szse_etf_shares, get_trading_dates, CACHE_DIR

# 上交所份额：用 requests 直连（带 session cookie + _时间戳参数，GitHub 海外服务器可访问）
SSE_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/disclosure/fund/etf/list/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
_EMPTY_SSE = ["基金代码", "基金简称", "基金份额", "日期"]
_sse_session = requests.Session()
_sse_ready = False


def _warm_session(force=False):
    """访问上交所首页拿必要 cookie；否则 commonQuery 会静默返回空。"""
    global _sse_ready
    if _sse_ready and not force:
        return
    if force:
        try:
            _sse_session.cookies.clear()
        except Exception:
            pass
    for attempt in range(3):
        try:
            _sse_session.get("https://www.sse.com.cn/",
                             headers={"User-Agent": SSE_HEADERS["User-Agent"]}, timeout=15)
            _sse_ready = True
            return
        except Exception as e:
            print(f"  SSE 预热失败(第{attempt + 1}次): {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    _sse_ready = False


_warm_session()


def fetch_sse_etf_shares(date_str):
    _warm_session()
    params = {
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": date_str,
        "isPagination": "true", "pageHelp.pageSize": "10000", "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1", "pageHelp.cacheSize": "1", "pageHelp.endPage": "1",
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = _sse_session.get(SSE_URL, params=params, headers=SSE_HEADERS, timeout=25)
        resp.encoding = "utf-8"
        data = resp.json()
        result = data.get("result") or []
        if not result:
            return pd.DataFrame(columns=_EMPTY_SSE)
        df = pd.DataFrame(result).rename(columns={
            "SEC_CODE": "基金代码", "SEC_NAME": "基金简称", "TOT_VOL": "基金份额"})
        df["基金份额"] = pd.to_numeric(df["基金份额"], errors="coerce") * 10000
        df["日期"] = date_str
        return df[["基金代码", "基金简称", "基金份额", "日期"]]
    except Exception as e:
        print(f"  SSE API error for {date_str}: {e}", flush=True)
        return pd.DataFrame(columns=_EMPTY_SSE)


def fetch_sse_etf_shares_retry(date_str, attempts=4):
    """带重试的 SSE 抓取：失败时刷新 cookie（cookie 失效是整段返回空的常见原因）。"""
    for k in range(attempts):
        df = fetch_sse_etf_shares(date_str)
        if not df.empty:
            return df
        _warm_session(force=True)
        time.sleep(2 * (k + 1))
    print(f"  SSE {date_str} 重试{attempts}次仍为空", flush=True)
    return pd.DataFrame(columns=_EMPTY_SSE)


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
done = set()
for p in sse_parts:
    done |= set(p["日期"].unique().tolist()) if hasattr(p["日期"], "unique") else set()
print(f"已完成SSE日期: {len(done)}")

# 只对最近 10 个交易日做重试，历史日期应当已经稳定，避免每次跑几百次无效重试
recent = set(trading_dates[-10:])

for i, d in enumerate(trading_dates, 1):
    if d in done:
        continue
    part = fetch_sse_etf_shares_retry(d) if d in recent else fetch_sse_etf_shares(d)
    if not part.empty:
        sse_parts.append(part)
    if i % 30 == 0:
        pd.to_pickle(sse_parts, sse_cache)
        print(f"  SSE {i}/{len(trading_dates)}")
    time.sleep(0.15)
pd.to_pickle(sse_parts, sse_cache)

sse = pd.concat(sse_parts, ignore_index=True) if sse_parts else pd.DataFrame()
print(f"  上交所: {len(sse)}行")

if sse.empty:
    raise RuntimeError("上交所份额为空：SSE 接口本次全部失败，拒绝生成半截报告")

# ---- 关键校验：沪深数据必须同步，否则说明某一交易所整段抓取失败 ----
_idx = {d: i for i, d in enumerate(trading_dates)}
sse_max = sse["日期"].astype(str).max()
sz_max = sz["日期"].astype(str).max() if not sz.empty else None
if sz_max:
    gap = _idx.get(sz_max, len(trading_dates) - 1) - _idx.get(sse_max, 0)
    print(f"  数据最新日: SSE {sse_max} / SZSE {sz_max} (相差{gap}个交易日)")
    if gap > 1:
        raise RuntimeError(
            f"上交所数据落后深交所 {gap} 个交易日（SSE {sse_max} vs SZSE {sz_max}），"
            f"疑似 SSE 抓取整段失败，已中止以免发布含大量 0 的报告。请重跑工作流。")

# 每日 SSE 只数异常（明显少于近期中位数）也要拦下
_cnt = sse[sse["基金代码"].isin(codes)].groupby("日期")["基金代码"].nunique()
if len(_cnt) >= 6:
    med = float(_cnt.tail(20).median())
    bad = _cnt.tail(5)[_cnt.tail(5) < 0.8 * med]
    if len(bad):
        raise RuntimeError(f"上交所最近交易日只数异常（近期中位数{med:.0f}只）：{bad.to_dict()}，疑似抓取不完整")

shares = pd.concat([sse, sz], ignore_index=True)
shares["基金代码"] = shares["基金代码"].astype(str).str.zfill(6)
shares = shares[shares["基金代码"].isin(codes)].copy()
shares["日期"] = shares["日期"].astype(str)
shares["基金份额"] = pd.to_numeric(shares["基金份额"], errors="coerce")
shares = shares.dropna(subset=["基金份额"]).drop_duplicates(["日期", "基金代码"], keep="last")
shares = shares.sort_values(["基金代码", "日期"])
print(f"合计(截断前): {len(shares)}行, 覆盖{shares['基金代码'].nunique()}只, 截至{shares['日期'].max()}")

# ---- 尾部完整性：只用「覆盖充分」的交易日，绝不让半截数据的日期进入报告 ----
_total = len(codes)
_dates = sorted(shares["日期"].unique())
_cov = shares.groupby("日期")["基金代码"].nunique()
_ok_dates = [d for d in _dates if _cov.get(d, 0) >= 0.85 * _total]
if not _ok_dates:
    raise RuntimeError(f"没有任何交易日覆盖达到 85%，数据不可用（共{_total}只ETF）")
_good_last = _ok_dates[-1]
_raw_last = _dates[-1]
_gap = _idx.get(_raw_last, 0) - _idx.get(_good_last, 0)
print(f"  最后一个完整交易日: {_good_last}（覆盖{_cov[_good_last]}/{_total}）")
if _gap > 2:
    raise RuntimeError(
        f"最新交易日 {_raw_last} 起连续 {_gap} 个交易日数据不完整"
        f"（{_raw_last} 仅覆盖 {_cov[_raw_last]}/{_total}），疑似交易所接口整段失败，已中止发布")
if _gap > 0:
    print(f"  提示: 丢弃尾部 {_gap} 个不完整交易日（{_good_last} 之后），本周统计截止到 {_good_last}")
    shares = shares[shares["日期"] <= _good_last].copy()

pd.to_pickle(shares, os.path.join(CACHE_DIR, "shares_all.pkl"))
print(f"合计: {len(shares)}行, 覆盖{shares['基金代码'].nunique()}只, 截至{shares['日期'].max()}")
