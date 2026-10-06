# -*- coding: utf-8 -*-
"""
ETF净流动仪表盘HTML生成模块
使用Chart.js绘制图表
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime


def df_to_records(df):
    """将DataFrame转为records(list of dict)，处理特殊类型"""
    if df is None or df.empty:
        return []
    records = df.to_dict("records")
    # 处理NaN和numpy类型
    for record in records:
        for key, val in record.items():
            if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                record[key] = 0
            elif isinstance(val, (np.floating, np.integer)):
                record[key] = float(val)
            elif hasattr(val, "isoformat"):
                record[key] = val.isoformat()
    return records


CATEGORY_ORDER = ["宽基ETF", "行业ETF", "风格ETF", "港股ETF", "其他ETF"]
TOTAL_CATEGORIES = {"宽基ETF", "行业ETF", "港股ETF"}


def build_grouped_rows(df, include_period):
    """按固定主分类顺序组织明细，并为指定分类追加合计行。"""
    if df is None or df.empty:
        return []

    periods = sorted(df["期间"].unique(), reverse=True) if include_period else [None]
    rows = []
    for period in periods:
        period_df = df[df["期间"] == period] if include_period else df
        for main_cat in CATEGORY_ORDER:
            cat_df = period_df[period_df["主分类"] == main_cat].copy()
            if cat_df.empty:
                continue
            cat_df = cat_df.sort_values("子分类")
            first = True
            for _, row in cat_df.iterrows():
                item = row.to_dict()
                item["分组开始"] = first
                item["行类型"] = "明细"
                rows.append(item)
                first = False
            if main_cat in TOTAL_CATEGORIES:
                rows.append({
                    "期间": period if include_period else cat_df["期间"].iloc[0] if "期间" in cat_df else "",
                    "主分类": main_cat,
                    "子分类": "合计",
                    "ETF数量": int(cat_df["ETF数量"].sum()),
                    "净流动(亿元)": float(cat_df["净流动(亿元)"].sum()),
                    "分组开始": False,
                    "行类型": "合计"
                })
    return rows


def generate_dashboard(output_path, flow_df, daily_summary, monthly_summary,
                       weekly_summary, monthly_detail, weekly_detail,
                       top_inflow, top_outflow, etf_classified,
                       start_date, end_date):
    """生成HTML仪表盘"""

    # 准备数据
    daily_data = df_to_records(daily_summary)
    monthly_data = df_to_records(monthly_summary)
    weekly_data = df_to_records(weekly_summary)
    monthly_grouped_data = df_to_records(pd.DataFrame(build_grouped_rows(monthly_detail, include_period=True)))
    weekly_grouped_data = df_to_records(pd.DataFrame(build_grouped_rows(weekly_summary, include_period=False)))
    top_inflow_data = df_to_records(top_inflow)
    top_outflow_data = df_to_records(top_outflow)
    etf_list = etf_classified

    # 计算总净流动
    if not flow_df.empty:
        total_flow = float(flow_df["净流动"].sum()) / 1e8  # 亿元
        total_etfs = flow_df["基金代码"].nunique()
        dates = sorted(flow_df["日期"].unique())
        latest_date = dates[-1] if dates else ""
        earliest_date = dates[0] if dates else ""
    else:
        total_flow = 0
        total_etfs = 0
        latest_date = ""
        earliest_date = ""

    # 各主分类净流动(最新一周)
    weekly_by_main = {}
    if not weekly_summary.empty:
        for _, row in weekly_summary.iterrows():
            cat = row["主分类"]
            flow = row["净流动(亿元)"]
            if cat not in weekly_by_main:
                weekly_by_main[cat] = 0
            weekly_by_main[cat] += flow

    # 各主分类净流动(月度)
    monthly_by_main = {}
    if not monthly_summary.empty:
        for _, row in monthly_summary.iterrows():
            period = row["期间"]
            cat = row["主分类"]
            flow = row["净流动(亿元)"]
            key = f"{period}|{cat}"
            if key not in monthly_by_main:
                monthly_by_main[key] = 0
            monthly_by_main[key] += flow

    # 分类体系结构
    category_tree = {}
    for etf in etf_list:
        main_cat = etf["main_category"]
        sub_cat = etf["sub_category"]
        if main_cat not in category_tree:
            category_tree[main_cat] = {}
        if sub_cat not in category_tree[main_cat]:
            category_tree[main_cat][sub_cat] = 0
        category_tree[main_cat][sub_cat] += 1

    # 统计ETF总数
    total_etf_count = len(etf_list)

    # 准备日度数据(按主分类)
    daily_main_cats = sorted(set(d["主分类"] for d in daily_data)) if daily_data else []
    daily_dates = sorted(set(d["日期"] for d in daily_data)) if daily_data else []

    # 准备日度堆叠图数据
    daily_stacked_data = {}
    for cat in daily_main_cats:
        daily_stacked_data[cat] = []
        for d in daily_dates:
            val = 0
            for record in daily_data:
                if record["日期"] == d and record["主分类"] == cat:
                    val = record["净流动(亿元)"]
                    break
            daily_stacked_data[cat].append(round(val, 2))

    # 准备月度数据(按子分类)
    monthly_periods = sorted(set(d["期间"] for d in monthly_data)) if monthly_data else []
    monthly_cats = sorted(set((d["主分类"], d["子分类"]) for d in monthly_data)) if monthly_data else []

    monthly_stacked_data = {}
    for main_cat, sub_cat in monthly_cats:
        key = f"{main_cat} - {sub_cat}"
        monthly_stacked_data[key] = []
        for period in monthly_periods:
            val = 0
            for record in monthly_data:
                if record["期间"] == period and record["主分类"] == main_cat and record["子分类"] == sub_cat:
                    val = record["净流动(亿元)"]
                    break
            monthly_stacked_data[key].append(round(val, 2))

    # 生成HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETF净流动跟踪仪表盘</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f0f2f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white; padding: 30px; border-radius: 12px;
            margin-bottom: 20px; text-align: center;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .subtitle {{ font-size: 14px; color: #aaa; }}
        .header .date-range {{ font-size: 13px; color: #8ecae6; margin-top: 8px; }}
        .summary-cards {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }}
        .card {{
            background: white; border-radius: 12px; padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            text-align: center;
        }}
        .card .label {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
        .card .value {{ font-size: 24px; font-weight: 700; }}
        .card .value.red {{ color: #e53935; }}
        .card .value.green {{ color: #43a047; }}
        .card .value.blue {{ color: #1e88e5; }}
        .card .sub {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .section {{
            background: white; border-radius: 12px; padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px;
        }}
        .section-title {{
            font-size: 18px; font-weight: 700; margin-bottom: 16px;
            padding-bottom: 10px; border-bottom: 2px solid #f0f0f0;
            display: flex; align-items: center; gap: 8px;
        }}
        .section-title .icon {{ font-size: 22px; }}
        .chart-container {{ position: relative; height: 400px; }}
        .chart-container.small {{ height: 320px; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
        table {{
            width: 100%; border-collapse: collapse; font-size: 13px;
        }}
        table th {{
            background: #f5f7fa; padding: 10px 12px; text-align: left;
            font-weight: 600; border-bottom: 2px solid #e0e0e0;
            white-space: nowrap;
        }}
        table td {{
            padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
        }}
        table tr:hover {{ background: #f9f9f9; }}
        tr.group-start td {{ border-top: 3px solid #d8e1ee; }}
        tr.total-row td {{ background: #eef4fb; font-weight: 700; border-bottom: 2px solid #c6d5e8; }}
        tr.total-row td:first-child {{ color: #174a7e; }}
        .group-label {{ font-weight: 700; color: #23395d; }}
        .flow-positive {{ color: #e53935; font-weight: 600; }}
        .flow-negative {{ color: #43a047; font-weight: 600; }}
        .tag {{
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 11px; font-weight: 500; margin: 1px;
        }}
        .tag-broad {{ background: #e3f2fd; color: #1565c0; }}
        .tag-industry {{ background: #fce4ec; color: #c62828; }}
        .tag-style {{ background: #f3e5f5; color: #7b1fa2; }}
        .tag-hk {{ background: #e8f5e9; color: #2e7d32; }}
        .tag-other {{ background: #f5f5f5; color: #616161; }}
        .tabs {{
            display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap;
        }}
        .tab {{
            padding: 6px 16px; border-radius: 6px; cursor: pointer;
            font-size: 13px; font-weight: 500; background: #f0f0f0;
            color: #666; transition: all 0.2s;
        }}
        .tab.active {{ background: #1a73e8; color: white; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .category-breakdown {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
        }}
        .cat-block {{
            background: #f9fafc; border-radius: 8px; padding: 16px;
            border-left: 3px solid #1a73e8;
        }}
        .cat-block h4 {{ font-size: 14px; margin-bottom: 10px; color: #1a73e8; }}
        .cat-block .sub-cat-list {{ font-size: 12px; }}
        .cat-block .sub-cat-item {{
            display: flex; justify-content: space-between;
            padding: 4px 0; border-bottom: 1px dotted #e0e0e0;
        }}
        .cat-block .sub-cat-item:last-child {{ border-bottom: none; }}
        .footer {{
            text-align: center; padding: 20px; color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>ETF净流动跟踪仪表盘</h1>
        <div class="subtitle">按分类统计ETF份额变动带来的资金净流动</div>
        <div class="date-range">数据期间: {earliest_date} ~ {latest_date} | 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-cards">
        <div class="card">
            <div class="label">追踪ETF总数</div>
            <div class="value blue">{total_etfs}</div>
            <div class="sub">覆盖{len(daily_dates)}个交易日</div>
        </div>
        <div class="card">
            <div class="label">区间总净流动</div>
            <div class="value {'red' if total_flow >= 0 else 'green'}">{total_flow:+.2f} 亿</div>
            <div class="sub">份额变动 * 净值</div>
        </div>
        <div class="card">
            <div class="label">最新交易日</div>
            <div class="value blue">{latest_date}</div>
            <div class="sub">{daily_dates[-1] if daily_dates else '-'}</div>
        </div>
        <div class="card">
            <div class="label">分类数量</div>
            <div class="value blue">{len(category_tree)}</div>
            <div class="sub">宽基/行业/风格/港股/其他</div>
        </div>
    </div>

    <!-- 日度净流动图 -->
    <div class="section">
        <div class="section-title">
            <span class="icon">📊</span>
            每日各分类ETF净流动 (亿元)
        </div>
        <div class="chart-container">
            <canvas id="dailyChart"></canvas>
        </div>
    </div>

    <!-- 周度和月度 -->
    <div class="two-col">
        <div class="section">
            <div class="section-title">
                <span class="icon">📅</span>
                最新一周各分类净流动
            </div>
            <div class="chart-container small">
                <canvas id="weeklyChart"></canvas>
            </div>
        </div>
        <div class="section">
            <div class="section-title">
                <span class="icon">📆</span>
                月度各分类净流动
            </div>
            <div class="chart-container small">
                <canvas id="monthlyChart"></canvas>
            </div>
        </div>
    </div>

    <!-- 月度详细 -->
    <div class="section">
        <div class="section-title">
            <span class="icon">📋</span>
            2026年以来各月份ETF净流动（分类分组）
        </div>
        <div id="monthlyTableContainer">
            <table id="monthlyTable">
                <thead>
                    <tr>
                        <th>月份</th>
                        <th>主分类</th>
                        <th>子分类</th>
                        <th>净流动(亿元)</th>
                        <th>ETF数量</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <!-- 周度详细 -->
    <div class="section">
        <div class="section-title">
            <span class="icon">📋</span>
            最新一周各子分类净流动明细
        </div>
        <div id="weeklyTableContainer">
            <table id="weeklyTable">
                <thead>
                    <tr>
                        <th>主分类</th>
                        <th>子分类</th>
                        <th>净流动(亿元)</th>
                        <th>ETF数量</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <!-- Top ETF -->
    <div class="two-col">
        <div class="section">
            <div class="section-title">
                <span class="icon">🔥</span>
                净流入TOP20 ETF
            </div>
            <table>
                <thead>
                    <tr><th>排名</th><th>代码</th><th>名称</th><th>分类</th><th>净流动(亿)</th></tr>
                </thead>
                <tbody id="topInflowBody"></tbody>
            </table>
        </div>
        <div class="section">
            <div class="section-title">
                <span class="icon">💧</span>
                净流出TOP20 ETF
            </div>
            <table>
                <thead>
                    <tr><th>排名</th><th>代码</th><th>名称</th><th>分类</th><th>净流动(亿)</th></tr>
                </thead>
                <tbody id="topOutflowBody"></tbody>
            </table>
        </div>
    </div>

    <!-- 分类体系 -->
    <div class="section">
        <div class="section-title">
            <span class="icon">🗂️</span>
            ETF分类体系 ({total_etf_count}只ETF)
        </div>
        <div class="category-breakdown" id="categoryBreakdown"></div>
    </div>

    <div class="footer">
        ETF净流动跟踪系统 | 数据来源: 上交所/深交所/东方财富 | 净流动 = 份额变动 × 当日净值
        <br>注: 红色表示净流入(申购), 绿色表示净流出(赎回)
    </div>
</div>

<script>
// 数据
const dailyData = {json.dumps(daily_data, ensure_ascii=False)};
const monthlyData = {json.dumps(monthly_data, ensure_ascii=False)};
const weeklyData = {json.dumps(weekly_data, ensure_ascii=False)};
const monthlyGroupedData = {json.dumps(monthly_grouped_data, ensure_ascii=False)};
const weeklyGroupedData = {json.dumps(weekly_grouped_data, ensure_ascii=False)};
const topInflow = {json.dumps(top_inflow_data, ensure_ascii=False)};
const topOutflow = {json.dumps(top_outflow_data, ensure_ascii=False)};
const categoryTree = {json.dumps(category_tree, ensure_ascii=False)};
const dailyMainCats = {json.dumps(daily_main_cats, ensure_ascii=False)};
const dailyDates = {json.dumps(daily_dates, ensure_ascii=False)};
const dailyStackedData = {json.dumps(daily_stacked_data, ensure_ascii=False)};
const monthlyPeriods = {json.dumps(monthly_periods, ensure_ascii=False)};
const monthlyStackedData = {json.dumps(monthly_stacked_data, ensure_ascii=False)};
const weeklyByMain = {json.dumps(weekly_by_main, ensure_ascii=False)};
const monthlyByMain = {json.dumps(monthly_by_main, ensure_ascii=False)};

// 颜色方案
const COLORS = {{
    '宽基ETF': '#1565c0',
    '行业ETF': '#c62828',
    '风格ETF': '#7b1fa2',
    '港股ETF': '#2e7d32',
    '其他ETF': '#616161'
}};

const BG_COLORS = {{
    '宽基ETF': 'rgba(21, 101, 192, 0.7)',
    '行业ETF': 'rgba(198, 40, 40, 0.7)',
    '风格ETF': 'rgba(123, 31, 162, 0.7)',
    '港股ETF': 'rgba(46, 125, 50, 0.7)',
    '其他ETF': 'rgba(97, 97, 97, 0.7)'
}};

// 日度堆叠柱状图
new Chart(document.getElementById('dailyChart'), {{
    type: 'bar',
    data: {{
        labels: dailyDates,
        datasets: dailyMainCats.map(cat => ({{
            label: cat,
            data: dailyStackedData[cat] || [],
            backgroundColor: BG_COLORS[cat] || 'rgba(100,100,100,0.7)',
            borderColor: COLORS[cat] || '#666',
            borderWidth: 1
        }}))
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            tooltip: {{ mode: 'index', intersect: false }},
            legend: {{ position: 'top' }}
        }},
        scales: {{
            x: {{ stacked: true, grid: {{ display: false }} }},
            y: {{
                stacked: true,
                title: {{ display: true, text: '净流动(亿元)' }},
                grid: {{ color: 'rgba(0,0,0,0.05)' }}
            }}
        }}
    }}
}});

// 周度柱状图(按主分类)
const weeklyCats = Object.keys(weeklyByMain);
const weeklyVals = weeklyCats.map(c => Math.round(weeklyByMain[c] * 100) / 100);
new Chart(document.getElementById('weeklyChart'), {{
    type: 'bar',
    data: {{
        labels: weeklyCats,
        datasets: [{{
            label: '净流动(亿元)',
            data: weeklyVals,
            backgroundColor: weeklyCats.map(c => BG_COLORS[c] || 'rgba(100,100,100,0.7)'),
            borderColor: weeklyCats.map(c => COLORS[c] || '#666'),
            borderWidth: 1
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{
                callbacks: {{
                    label: function(ctx) {{
                        const val = ctx.parsed.y;
                        return (val >= 0 ? '净流入: ' : '净流出: ') + Math.abs(val).toFixed(2) + ' 亿元';
                    }}
                }}
            }}
        }},
        scales: {{
            y: {{
                title: {{ display: true, text: '亿元' }},
                grid: {{ color: 'rgba(0,0,0,0.05)' }}
            }}
        }}
    }}
}});

// 月度柱状图(按主分类)
const monthlyDataByCat = {{}};
monthlyData.forEach(d => {{
    const key = d['期间'] + '|' + d['主分类'];
    monthlyDataByCat[key] = d['净流动(亿元)'];
}});

const monthlyCats = [...new Set(monthlyData.map(d => d['主分类']))];
const monthlyDatasets = monthlyCats.map(cat => ({{
    label: cat,
    data: monthlyPeriods.map(p => {{
        const key = p + '|' + cat;
        return monthlyDataByCat[key] || 0;
    }}),
    backgroundColor: BG_COLORS[cat] || 'rgba(100,100,100,0.7)',
    borderColor: COLORS[cat] || '#666',
    borderWidth: 1
}}));

new Chart(document.getElementById('monthlyChart'), {{
    type: 'bar',
    data: {{
        labels: monthlyPeriods,
        datasets: monthlyDatasets
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            tooltip: {{ mode: 'index', intersect: false }},
            legend: {{ display: false }}
        }},
        scales: {{
            x: {{ grid: {{ display: false }} }},
            y: {{
                title: {{ display: true, text: '亿元' }},
                grid: {{ color: 'rgba(0,0,0,0.05)' }}
            }}
        }}
    }}
}});

function tagClass(mainCat) {{
    return mainCat === '宽基ETF' ? 'tag-broad' :
           mainCat === '行业ETF' ? 'tag-industry' :
           mainCat === '风格ETF' ? 'tag-style' :
           mainCat === '港股ETF' ? 'tag-hk' : 'tag-other';
}}

// 月度表格：月份倒序，月份内按宽基/行业/风格/港股/其他固定分组
const monthlyTableBody = document.querySelector('#monthlyTable tbody');
monthlyGroupedData.forEach(row => {{
    const flow = row['净流动(亿元)'];
    const tr = document.createElement('tr');
    if (row['分组开始']) tr.classList.add('group-start');
    if (row['行类型'] === '合计') tr.classList.add('total-row');
    tr.innerHTML = `
        <td>${{row['期间']}}</td>
        <td><span class="tag ${{tagClass(row['主分类'])}}">${{row['主分类']}}</span></td>
        <td class="${{row['行类型'] === '合计' ? 'group-label' : ''}}">${{row['子分类']}}</td>
        <td class="${{flow >= 0 ? 'flow-positive' : 'flow-negative'}}">${{flow >= 0 ? '+' : ''}}${{flow.toFixed(2)}}</td>
        <td>${{row['ETF数量']}}</td>
    `;
    monthlyTableBody.appendChild(tr);
}});

// 周度表格：按宽基/行业/风格/港股/其他固定分组
const weeklyTableBody = document.querySelector('#weeklyTable tbody');
weeklyGroupedData.forEach(row => {{
    const flow = row['净流动(亿元)'];
    const tr = document.createElement('tr');
    if (row['分组开始']) tr.classList.add('group-start');
    if (row['行类型'] === '合计') tr.classList.add('total-row');
    tr.innerHTML = `
        <td><span class="tag ${{tagClass(row['主分类'])}}">${{row['主分类']}}</span></td>
        <td class="${{row['行类型'] === '合计' ? 'group-label' : ''}}">${{row['子分类']}}</td>
        <td class="${{flow >= 0 ? 'flow-positive' : 'flow-negative'}}">${{flow >= 0 ? '+' : ''}}${{flow.toFixed(2)}}</td>
        <td>${{row['ETF数量']}}</td>
    `;
    weeklyTableBody.appendChild(tr);
}});

// Top流入
const topInflowBody = document.getElementById('topInflowBody');
topInflow.forEach((row, i) => {{
    const flow = row['净流动(亿元)'];
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${{i + 1}}</td>
        <td>${{row['基金代码']}}</td>
        <td>${{row['基金简称']}}</td>
        <td><span class="tag ${{row['主分类'] === '宽基ETF' ? 'tag-broad' : row['主分类'] === '行业ETF' ? 'tag-industry' : row['主分类'] === '风格ETF' ? 'tag-style' : row['主分类'] === '港股ETF' ? 'tag-hk' : 'tag-other'}}">${{row['子分类']}}</span></td>
        <td class="flow-positive">+${{flow.toFixed(2)}}</td>
    `;
    topInflowBody.appendChild(tr);
}});

// Top流出
const topOutflowBody = document.getElementById('topOutflowBody');
topOutflow.forEach((row, i) => {{
    const flow = row['净流动(亿元)'];
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${{i + 1}}</td>
        <td>${{row['基金代码']}}</td>
        <td>${{row['基金简称']}}</td>
        <td><span class="tag ${{row['主分类'] === '宽基ETF' ? 'tag-broad' : row['主分类'] === '行业ETF' ? 'tag-industry' : row['主分类'] === '风格ETF' ? 'tag-style' : row['主分类'] === '港股ETF' ? 'tag-hk' : 'tag-other'}}">${{row['子分类']}}</span></td>
        <td class="flow-negative">${{flow.toFixed(2)}}</td>
    `;
    topOutflowBody.appendChild(tr);
}});

// 分类体系
const catBreakdown = document.getElementById('categoryBreakdown');
Object.keys(categoryTree).sort().forEach(mainCat => {{
    const block = document.createElement('div');
    block.className = 'cat-block';
    const subs = categoryTree[mainCat];
    let subItems = '';
    Object.keys(subs).sort((a, b) => subs[b] - subs[a]).forEach(subCat => {{
        subItems += `<div class="sub-cat-item"><span>${{subCat}}</span><span>${{subs[subCat]}}只</span></div>`;
    }});
    const total = Object.values(subs).reduce((a, b) => a + b, 0);
    block.innerHTML = `
        <h4>${{mainCat}} (${{total}}只)</h4>
        <div class="sub-cat-list">${{subItems}}</div>
    `;
    catBreakdown.appendChild(block);
}});

</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  HTML文件大小: {len(html) / 1024:.1f} KB")
