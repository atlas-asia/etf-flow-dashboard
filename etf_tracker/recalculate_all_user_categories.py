# -*- coding: utf-8 -*-
"""按用户ETF分类.xlsx四个Sheet，统计2026年月度及最新一周净流动。"""
import os, sys, time, json, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetcher import fetch_sse_etf_shares, fetch_szse_etf_shares, fetch_etf_nav_history, get_trading_dates

CLASS_FILE = r"E:/盈峰资本/FOF研究/宽基跟踪/ETF分类/ETF分类.xlsx"
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_XLSX = os.path.join(OUT_DIR, "ETF净流动_按用户四Sheet分类_2026.xlsx")
OUT_HTML = os.path.join(OUT_DIR, "ETF净流动_按用户四Sheet分类_2026.html")
SHEETS = ["宽基ETF", "行业ETF", "风格ETF", "港股ETF"]

maps = []
for sheet in SHEETS:
    df = pd.read_excel(CLASS_FILE, sheet_name=sheet).dropna(subset=["分类", "代码"]).copy()
    df["基金代码"] = df["代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    df = df.dropna(subset=["基金代码"])
    df["基金代码"] = df["基金代码"].astype(str).str.zfill(6)
    df["主分类"] = sheet
    maps.append(df[["主分类", "分类", "代码", "基金代码", "名称"]])
classification = pd.concat(maps, ignore_index=True)
# 同一Sheet内同一代码重复时保留首次；不同Sheet重复则分别计入用户指定分类
classification = classification.drop_duplicates(["主分类", "基金代码"], keep="first")
all_codes = sorted(classification["基金代码"].unique())
print(f"分类映射: {len(classification)}条，唯一ETF: {len(all_codes)}只")
print(classification.groupby("主分类")["基金代码"].nunique().to_string())

start_date = dt.date(2025, 12, 31)
today = dt.date.today()
trading_dates = get_trading_dates(start_date, today)
print("获取深交所份额...")
sz = fetch_szse_etf_shares(start_date.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
print("获取上交所份额...")
sse_parts = []
for i, d in enumerate(trading_dates, 1):
    part = fetch_sse_etf_shares(d)
    if not part.empty: sse_parts.append(part)
    if i % 30 == 0: print(f"  SSE {i}/{len(trading_dates)}")
    time.sleep(0.12)
sse = pd.concat(sse_parts, ignore_index=True) if sse_parts else pd.DataFrame()
shares = pd.concat([sse, sz], ignore_index=True)
shares["基金代码"] = shares["基金代码"].astype(str).str.zfill(6)
shares = shares[shares["基金代码"].isin(all_codes)].copy()
shares["日期"] = shares["日期"].astype(str)
shares["基金份额"] = pd.to_numeric(shares["基金份额"], errors="coerce")
shares = shares.dropna(subset=["基金份额"]).drop_duplicates(["日期", "基金代码"], keep="last")
shares = shares.sort_values(["基金代码", "日期"])
shares["前日份额"] = shares.groupby("基金代码")["基金份额"].shift(1)
shares["份额变动"] = shares["基金份额"] - shares["前日份额"]
changed_codes = shares.loc[shares["份额变动"].fillna(0).ne(0), "基金代码"].unique().tolist()
print(f"获取NAV: {len(changed_codes)}只（并发请求）")

def get_nav(code):
    try:
        nav = fetch_etf_nav_history(code, page_size=300)
        if nav.empty:
            return pd.DataFrame(columns=["日期", "单位净值", "基金代码"])
        nav = nav[["日期", "单位净值"]].copy()
        nav["日期"] = nav["日期"].astype(str)
        nav["基金代码"] = code
        return nav
    except Exception:
        return pd.DataFrame(columns=["日期", "单位净值", "基金代码"])

nav_rows = []
with ThreadPoolExecutor(max_workers=12) as executor:
    futures = [executor.submit(get_nav, code) for code in changed_codes]
    for i, future in enumerate(as_completed(futures), 1):
        nav = future.result()
        if not nav.empty: nav_rows.append(nav)
        if i % 100 == 0: print(f"  NAV {i}/{len(changed_codes)}")
nav_df = pd.concat(nav_rows, ignore_index=True) if nav_rows else pd.DataFrame(columns=["日期", "单位净值", "基金代码"])
nav_df["基金代码"] = nav_df["基金代码"].astype(str).str.zfill(6)
nav_df["日期"] = nav_df["日期"].astype(str)
nav_df["单位净值"] = pd.to_numeric(nav_df["单位净值"], errors="coerce")
flow_base = shares.merge(nav_df, on=["基金代码", "日期"], how="left")
flow_base["单位净值"] = flow_base.groupby("基金代码")["单位净值"].transform(lambda s: s.ffill().bfill())
flow_base["净流动(元)"] = flow_base["份额变动"] * flow_base["单位净值"]
flow_base = flow_base[flow_base["日期"] >= "2026-01-01"].copy()
flow_base["月份"] = flow_base["日期"].str[:7]

flow = flow_base.merge(classification[["主分类", "分类", "基金代码", "名称"]], on="基金代码", how="inner")
monthly = flow.groupby(["主分类", "月份", "分类"], observed=True).agg(
    净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
).reset_index()
monthly["净流动(亿元)"] = monthly["净流动_元"] / 1e8
valid_dates = sorted(flow.loc[flow["净流动(元)"].notna(), "日期"].unique())
latest_date = valid_dates[-1]
latest_dt = pd.to_datetime(latest_date)
week_dates = sorted([d for d in valid_dates if pd.to_datetime(d).isocalendar().week == latest_dt.isocalendar().week and pd.to_datetime(d).year == latest_dt.year])
week = flow[flow["日期"].isin(week_dates)].copy()
week_start = week_dates[0]
weekly = week.groupby(["主分类", "分类"], observed=True).agg(
    净流动_元=("净流动(元)", "sum"), ETF数量=("基金代码", "nunique")
).reset_index()
weekly["净流动(亿元)"] = weekly["净流动_元"] / 1e8
weekly["统计区间"] = f"{week['日期'].min()} ~ {latest_date}"
etf_detail = flow.groupby(["主分类", "分类", "基金代码", "名称"], observed=True).agg(**{
    "2026年以来净流动_元": ("净流动(元)", "sum"), "数据起始日": ("日期", "min"), "数据截止日": ("日期", "max")
}).reset_index()
etf_detail["2026年以来净流动(亿元)"] = etf_detail["2026年以来净流动_元"] / 1e8

with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
    monthly[["主分类", "月份", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer,index=False,sheet_name="全部月度净流动")
    weekly[["统计区间", "主分类", "分类", "净流动(亿元)", "ETF数量"]].to_excel(writer,index=False,sheet_name="全部最新一周")
    classification.to_excel(writer,index=False,sheet_name="全部分类映射")
    etf_detail[["主分类", "分类", "基金代码", "名称", "2026年以来净流动(亿元)", "数据起始日", "数据截止日"]].to_excel(writer,index=False,sheet_name="全部ETF明细")
    for sheet in SHEETS:
        monthly[monthly["主分类"]==sheet][["月份","分类","净流动(亿元)","ETF数量"]].to_excel(writer,index=False,sheet_name=f"{sheet[:2]}月度")
        weekly[weekly["主分类"]==sheet][["统计区间","分类","净流动(亿元)","ETF数量"]].to_excel(writer,index=False,sheet_name=f"{sheet[:2]}周度")

monthly_records = monthly[["主分类","月份","分类","净流动(亿元)","ETF数量"]].to_dict("records")
weekly_records = weekly[["统计区间","主分类","分类","净流动(亿元)","ETF数量"]].to_dict("records")
for rec in monthly_records+weekly_records:
    rec["净流动(亿元)"] = round(float(rec["净流动(亿元)"]),2); rec["ETF数量"] = int(rec["ETF数量"])
nav = "".join(f'<button onclick="showTab(\'{s}\')">{s}</button>' for s in SHEETS)
sections=[]
for sheet in SHEETS:
    cats=classification[classification["主分类"]==sheet]["分类"].drop_duplicates().tolist()
    months=sorted(monthly[monthly["主分类"]==sheet]["月份"].unique())
    md={c:[round(float(monthly.loc[(monthly["主分类"]==sheet)&(monthly["月份"]==m)&(monthly["分类"]==c),"净流动(亿元)"].sum()),2) for m in months] for c in cats}
    wd={r["分类"]:round(float(r["净流动(亿元)"]),2) for _,r in weekly[weekly["主分类"]==sheet].iterrows()}
    mrows="".join(f"<tr><td>{r['月份']}</td><td>{r['分类']}</td><td class={'pos' if r['净流动(亿元)']>=0 else 'neg'}>{r['净流动(亿元)']:+.2f}</td><td>{int(r['ETF数量'])}</td></tr>" for _,r in monthly[monthly["主分类"]==sheet].iterrows())
    wrows="".join(f"<tr><td>{r['统计区间']}</td><td>{r['分类']}</td><td class={'pos' if r['净流动(亿元)']>=0 else 'neg'}>{r['净流动(亿元)']:+.2f}</td><td>{int(r['ETF数量'])}</td></tr>" for _,r in weekly[weekly["主分类"]==sheet].iterrows())
    sections.append(f'''<section id="{sheet}" class="tab"><div class="panel"><h2>{sheet}：2026年月度净流动</h2><div class="chart"><canvas id="m{SHEETS.index(sheet)}"></canvas></div></div><div class="panel"><h2>{sheet}：最新一周净流动</h2><div class="chart"><canvas id="w{SHEETS.index(sheet)}"></canvas></div></div><div class="panel"><h2>月度明细</h2><table><thead><tr><th>月份</th><th>分类</th><th>净流动(亿元)</th><th>ETF数量</th></tr></thead><tbody>{mrows}</tbody></table></div><div class="panel"><h2>最新一周明细</h2><table><thead><tr><th>区间</th><th>分类</th><th>净流动(亿元)</th><th>ETF数量</th></tr></thead><tbody>{wrows}</tbody></table></div><script type="application/json" id="d{SHEETS.index(sheet)}">{json.dumps({'months':months,'cats':cats,'monthly':md,'weekly':wd},ensure_ascii=False)}</script></section>''')
html=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>ETF净流动全分类</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script><style>body{{font-family:Arial,"Microsoft YaHei";background:#f5f7fb;color:#222;margin:0}}.wrap{{max-width:1380px;margin:auto;padding:24px}}.hero,.panel{{background:white;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 2px 10px #dfe5ef}}button{{padding:9px 18px;margin:4px;border:0;border-radius:7px;background:#e7eef8;cursor:pointer}}button.active{{background:#2166ac;color:white}}.tab{{display:none}}.tab.active{{display:block}}.chart{{height:390px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px;border-bottom:1px solid #e8edf4;text-align:left}}th{{background:#eef3fa}}.pos{{color:#d32f2f;font-weight:bold}}.neg{{color:#238636;font-weight:bold}}.note{{font-size:13px;color:#65748b}}</style></head><body><div class="wrap"><div class="hero"><h1>ETF净流动全分类跟踪</h1><p class="note">分类完全采用用户ETF分类.xlsx四个Sheet；宽基已包含中证500。统计截至{latest_date}，最新完整交易周：{week_start} ~ {latest_date}。净流动=原始份额变化×当日单位净值NAV。</p><div>{nav}</div></div>{''.join(sections)}<div class="panel note">数据源：上交所/深交所ETF每日原始份额、东方财富单位净值NAV；净流动=(当日原始份额-上一交易日原始份额)×当日单位净值NAV。周度严格按周一至周五实际交易日。港股Sheet中原文件存在重复代码，已在Sheet内按代码去重。</div></div><script>const charts=[];function showTab(id){{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active');document.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x.textContent===id));}}document.querySelectorAll('.tab').forEach((sec,i)=>{{const d=JSON.parse(document.getElementById('d'+i).textContent);charts.push(new Chart(document.getElementById('m'+i),{{type:'line',data:{{labels:d.months,datasets:d.cats.map((c,j)=>({{label:c,data:d.monthly[c],borderColor:`hsl(${{j*360/d.cats.length}},65%,45%)`,tension:.2}}))}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom'}}}}}}}}));charts.push(new Chart(document.getElementById('w'+i),{{type:'bar',data:{{labels:d.cats,datasets:[{{data:d.cats.map(c=>d.weekly[c]||0),backgroundColor:d.cats.map((c,j)=>`hsl(${{j*360/d.cats.length}},65%,55%)`)}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}}));}});showTab('宽基ETF');</script></body></html>'''
with open(OUT_HTML,"w",encoding="utf-8") as f:f.write(html)
print("最新周",week["日期"].min(),latest_date)
print("月度行",len(monthly),"周度行",len(weekly),"ETF明细",len(etf_detail))
print(OUT_XLSX);print(OUT_HTML)
# 同步生成固定入口的矩阵版网页与Excel
import subprocess
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "reshape_flow_report.py")], check=True)
