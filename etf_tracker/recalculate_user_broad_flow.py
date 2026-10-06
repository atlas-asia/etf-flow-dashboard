# -*- coding: utf-8 -*-
"""按用户ETF分类.xlsx中的宽基分类重算2026年月度与最新一周净流动。"""
import os
import sys
import time
import datetime as dt
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import fetch_sse_etf_shares, fetch_szse_etf_shares, fetch_etf_price_sina, get_trading_dates

CLASS_FILE = r"E:/盈峰资本/FOF研究/宽基跟踪/ETF分类/ETF分类.xlsx"
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_XLSX = os.path.join(OUT_DIR, "宽基ETF净流动_按用户分类_2026.xlsx")
OUT_HTML = os.path.join(OUT_DIR, "宽基ETF净流动_按用户分类_2026.html")
CATEGORIES = ["上证50", "沪深300", "中证A500", "科创板", "中证1000", "中证2000"]

classification = pd.read_excel(CLASS_FILE, sheet_name="宽基ETF")
classification = classification.dropna(subset=["分类", "代码"]).copy()
classification = classification[classification["分类"].isin(CATEGORIES)].copy()
classification["基金代码"] = classification["代码"].astype(str).str.extract(r"(\d{6})", expand=False).astype(str).str.zfill(6)
classification = classification.dropna(subset=["基金代码"]).drop_duplicates("基金代码")
code_to_cat = classification.set_index("基金代码")["分类"].to_dict()
code_to_name = classification.set_index("基金代码")["名称"].to_dict()
codes = sorted(code_to_cat)

start_date = dt.date(2025, 12, 31)
today = dt.date.today()
trading_dates = get_trading_dates(start_date, today)

print(f"用户宽基标的: {len(codes)}只")
print("获取深交所份额...")
sz = fetch_szse_etf_shares(start_date.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
print("获取上交所份额...")
sse_parts = []
for i, d in enumerate(trading_dates, 1):
    part = fetch_sse_etf_shares(d)
    if not part.empty:
        sse_parts.append(part)
    if i % 30 == 0:
        print(f"  SSE {i}/{len(trading_dates)}")
    time.sleep(0.15)
sse = pd.concat(sse_parts, ignore_index=True) if sse_parts else pd.DataFrame()
shares = pd.concat([sse, sz], ignore_index=True)
shares["基金代码"] = shares["基金代码"].astype(str).str.zfill(6)
shares = shares[shares["基金代码"].isin(codes)].copy()
shares["日期"] = shares["日期"].astype(str)
shares["基金份额"] = pd.to_numeric(shares["基金份额"], errors="coerce")
shares = shares.dropna(subset=["基金份额"]).sort_values(["基金代码", "日期"])
shares["前日份额"] = shares.groupby("基金代码")["基金份额"].shift(1)
shares["份额变动"] = shares["基金份额"] - shares["前日份额"]

changed_codes = shares.loc[shares["份额变动"].fillna(0).ne(0), "基金代码"].unique().tolist()
print(f"获取净值: {len(changed_codes)}只")
price_rows = []
for i, code in enumerate(changed_codes, 1):
    market = "sh" if code.startswith(("5", "6")) else "sz"
    price = fetch_etf_price_sina(f"{market}{code}")
    if not price.empty:
        price = price[["date", "close"]].rename(columns={"date": "日期", "close": "计算价格"})
        price["日期"] = price["日期"].astype(str)
        price["基金代码"] = str(code).zfill(6)
        price_rows.append(price)
    if i % 50 == 0:
        print(f"  PRICE {i}/{len(changed_codes)}")
    time.sleep(0.04)
price_df = pd.concat(price_rows, ignore_index=True) if price_rows else pd.DataFrame(columns=["日期", "计算价格", "基金代码"])
price_df["日期"] = price_df["日期"].astype(str)
price_df["基金代码"] = price_df["基金代码"].astype(str).str.zfill(6)
price_df["计算价格"] = pd.to_numeric(price_df["计算价格"], errors="coerce")
print(f"价格记录: {len(price_df)}, 份额记录: {len(shares)}")

flow = shares.merge(price_df, on=["基金代码", "日期"], how="left")
print(f"价格匹配记录: {flow['计算价格'].notna().sum()}")
flow["计算价格"] = flow.groupby("基金代码")["计算价格"].transform(lambda s: s.ffill().bfill())
flow["净流动(元)"] = flow["份额变动"] * flow["计算价格"]
flow["分类"] = flow["基金代码"].map(code_to_cat)
flow["名称"] = flow["基金代码"].map(code_to_name)
flow = flow[flow["日期"] >= "2026-01-01"].copy()
flow["月份"] = flow["日期"].str[:7]

monthly = flow.groupby(["月份", "分类"], observed=True).agg(
    净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
).reset_index()
monthly["净流动(亿元)"] = monthly["净流动_元"] / 1e8
monthly["分类"] = pd.Categorical(monthly["分类"], CATEGORIES, ordered=True)
monthly = monthly.sort_values(["月份", "分类"])

valid_dates = sorted(flow.loc[flow["净流动(元)"].notna(), "日期"].unique())
latest_date = valid_dates[-1]
latest_dt = pd.to_datetime(latest_date)
week_start = (latest_dt - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
week = flow[(flow["日期"] >= week_start) & (flow["日期"] <= latest_date)].copy()
weekly = week.groupby("分类", observed=True).agg(
    净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
).reset_index()
weekly["净流动(亿元)"] = weekly["净流动_元"] / 1e8
weekly["统计区间"] = f"{week['日期'].min()} ~ {latest_date}"
weekly["分类"] = pd.Categorical(weekly["分类"], CATEGORIES, ordered=True)
weekly = weekly.sort_values("分类")

etf_detail = flow.groupby(["分类", "基金代码", "名称"], observed=True).agg(**{
    "2026年以来净流动_元": ("净流动(元)", "sum"),
    "数据起始日": ("日期", "min"),
    "数据截止日": ("日期", "max")
}).reset_index()
etf_detail["2026年以来净流动(亿元)"] = etf_detail["2026年以来净流动_元"] / 1e8
etf_detail["分类"] = pd.Categorical(etf_detail["分类"], CATEGORIES, ordered=True)
etf_detail = etf_detail.sort_values(["分类", "基金代码"])

with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
    monthly[["月份", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name="月度净流动")
    weekly[["统计区间", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer, index=False, sheet_name="最新一周")
    classification[["分类", "代码", "名称", "基金代码"]].to_excel(writer, index=False, sheet_name="宽基分类映射")
    etf_detail[["分类", "基金代码", "名称", "2026年以来净流动(亿元)", "数据起始日", "数据截止日"]].to_excel(writer, index=False, sheet_name="ETF明细")

months = sorted(monthly["月份"].unique())
chart_data = {cat: [round(float(monthly.loc[(monthly["月份"] == m) & (monthly["分类"] == cat), "净流动(亿元)"].sum()), 2) for m in months] for cat in CATEGORIES}
weekly_data = {str(r["分类"]): round(float(r["净流动(亿元)"]), 2) for _, r in weekly.iterrows()}
rows = "".join(f"<tr><td>{r['月份']}</td><td>{r['分类']}</td><td class={'pos' if r['净流动(亿元)'] >= 0 else 'neg'}>{r['净流动(亿元)']:+.2f}</td><td>{int(r['ETF数量'])}</td></tr>" for _, r in monthly.iterrows())
week_rows = "".join(f"<tr><td>{r['统计区间']}</td><td>{r['分类']}</td><td class={'pos' if r['净流动(亿元)'] >= 0 else 'neg'}>{r['净流动(亿元)']:+.2f}</td><td>{int(r['ETF数量'])}</td></tr>" for _, r in weekly.iterrows())
html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>宽基ETF净流动</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script><style>body{{font-family:Arial,"Microsoft YaHei";background:#f5f7fb;color:#222;margin:0}}.wrap{{max-width:1200px;margin:auto;padding:24px}}.hero,.panel{{background:#fff;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 2px 10px #dfe5ef}}h1{{margin:0 0 8px}}.note{{color:#65748b;font-size:13px}}.chart{{height:390px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #e8edf4;text-align:left}}th{{background:#eef3fa}}.pos{{color:#d32f2f;font-weight:700}}.neg{{color:#238636;font-weight:700}}.source{{font-size:12px;color:#718096;margin-top:10px}}</style></head><body><div class="wrap"><div class="hero"><h1>宽基ETF净流动跟踪</h1><div class="note">完全采用用户文件《ETF分类.xlsx》中的宽基分类；统计截至 {latest_date}</div></div><div class="panel"><h2>2026年以来月度净流动（亿元）</h2><div class="chart"><canvas id="monthly"></canvas></div></div><div class="panel"><h2>最新一周净流动（亿元）</h2><div class="chart"><canvas id="weekly"></canvas></div></div><div class="panel"><h2>月度明细</h2><table><thead><tr><th>月份</th><th>分类</th><th>净流动(亿元)</th><th>ETF数量</th></tr></thead><tbody>{rows}</tbody></table></div><div class="panel"><h2>最新一周明细</h2><table><thead><tr><th>区间</th><th>分类</th><th>净流动(亿元)</th><th>ETF数量</th></tr></thead><tbody>{week_rows}</tbody><tfoot></tfoot></table><div class="source">数据源：上交所/深交所ETF每日份额、新浪ETF历史收盘价；净流动=(当日份额-前一交易日份额)×当日收盘价。分类源：用户提供的ETF分类.xlsx。因东方财富NAV接口批量限流，本版采用收盘价替代NAV，金额与严格净值口径可能存在小幅差异。</div></div></div><script>const months={json.dumps(months,ensure_ascii=False)};const cats={json.dumps(CATEGORIES,ensure_ascii=False)};const mdata={json.dumps(chart_data,ensure_ascii=False)};const wdata={json.dumps(weekly_data,ensure_ascii=False)};const colors=['#1f77b4','#ff7f0e','#d62728','#9467bd','#2ca02c','#17becf'];new Chart(document.getElementById('monthly'),{{type:'bar',data:{{labels:months,datasets:cats.map((c,i)=>({{label:c,data:mdata[c],backgroundColor:colors[i]}}))}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{tooltip:{{mode:'index',intersect:false}}}},scales:{{y:{{title:{{display:true,text:'亿元'}}}}}}}}}});new Chart(document.getElementById('weekly'),{{type:'bar',data:{{labels:cats,datasets:[{{data:cats.map(c=>wdata[c]||0),backgroundColor:cats.map((c,i)=>colors[i])}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{title:{{display:true,text:'亿元'}}}}}}}}}});</script></body></html>'''
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(monthly[["月份", "分类", "净流动(亿元)", "ETF数量"]].to_string(index=False))
print("\n最新一周")
print(weekly[["统计区间", "分类", "净流动(亿元)", "ETF数量"]].to_string(index=False))
print(OUT_XLSX)
print(OUT_HTML)
