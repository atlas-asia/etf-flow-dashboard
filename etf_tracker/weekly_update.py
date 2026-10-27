# -*- coding: utf-8 -*-
"""每周ETF净流动更新编排：份额 -> 净值NAV -> 重算 -> 输出到public目录。
用法: python weekly_update.py

2026-10-27 加固版：
- 份额环节失败（如上交所整段抓不到）会自动整轮重试，最多 3 轮、间隔 3 分钟；
- 重算后做「分类完整性校验」：任一 Sheet 周度分类数量明显少于分类表，即判定数据不全，
  直接报错退出（工作流红灯），GitHub Pages 继续保留上一次的正确版本，而不是发布一堆 0。
"""
import os, sys, subprocess, shutil, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
PY = sys.executable
PUBLIC = os.path.join(BASE, "public")
SHEETS = ["宽基ETF", "行业ETF", "风格ETF", "港股ETF"]


def run(script):
    print(f"===== {os.path.basename(script)} =====", flush=True)
    subprocess.run([PY, os.path.join(HERE, script)], check=True)


def run_retry(script, attempts=3, wait=180):
    """份额抓取失败多为交易所接口临时不可用，整轮重试（断点续传让重跑很快）。"""
    last = None
    for k in range(attempts):
        try:
            run(script)
            return
        except subprocess.CalledProcessError as e:
            last = e
            print(f"!! {script} 第{k + 1}/{attempts}轮失败: {e}", flush=True)
            if k < attempts - 1:
                print(f"   {wait}秒后重试…", flush=True)
                time.sleep(wait)
    raise last


def _class_file():
    local = r"E:/盈峰资本/FOF研究/宽基跟踪/ETF分类/ETF分类.xlsx"
    return os.environ.get("ETF_CLASS_FILE") or (
        local if os.path.exists(local) else os.path.join(HERE, "ETF分类.xlsx"))


def validate_report(xlsx_path):
    """周度结果必须覆盖分类表里每一类的绝大多数，否则视为数据不全。"""
    cls_file = _class_file()
    wk = pd.read_excel(xlsx_path, sheet_name="周度长表")
    wk = wk.dropna(subset=["净流动(亿元)"])
    bad = []
    for sheet in SHEETS:
        expect = pd.read_excel(cls_file, sheet_name=sheet).dropna(subset=["分类"])["分类"].nunique()
        got = wk[wk["主分类"] == sheet]["分类"].nunique()
        ratio = got / expect if expect else 1
        print(f"  校验 {sheet}: 周度分类 {got}/{expect} = {ratio:.0%}")
        if ratio < 0.8:
            bad.append(f"{sheet} {got}/{expect}")
    if bad:
        raise RuntimeError(
            "周度分类数量异常（低于 80%），判定本周数据不完整，已中止发布以避免页面出现大量 0："
            + "；".join(bad))


def main():
    # NAV 数据源：默认用本机聚源(FinQuery)；CI 设 NAV_SOURCE=eastmoney 改用东方财富(免费无密钥)
    nav_source = os.environ.get("NAV_SOURCE", "gildata").lower()
    # 1. 份额（含断点续传 + 自动重试 + 沪深同步校验）
    run_retry("fetch_shares.py")
    # 2. NAV
    if nav_source == "eastmoney":
        run("fetch_nav_eastmoney.py")
    else:
        run("fetch_nav_gildata.py")
    # 2b. NAV缺口修复（仅聚源模式需要；东财模式跳过）
    if nav_source != "eastmoney":
        try:
            run("fill_nav_month_gaps.py")
        except subprocess.CalledProcessError as e:
            print("NAV缺口修复失败（不影响主流程）:", e, flush=True)
    # 3. 重算 + 生成矩阵版报告（严格按用户公式；拆分仅标记不调整）
    run("recalculate_gildata.py")
    # 3b. 发布前校验：分类完整性
    src_xlsx = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026_矩阵版.xlsx")
    validate_report(src_xlsx)
    # 4. 复制到public
    os.makedirs(PUBLIC, exist_ok=True)
    src_html = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026_矩阵版.html")
    shutil.copy2(src_html, os.path.join(PUBLIC, "index.html"))
    shutil.copy2(src_xlsx, os.path.join(PUBLIC, "ETF净流动数据.xlsx"))
    print("public目录已更新:")
    for f in os.listdir(PUBLIC):
        print(" ", f, os.path.getsize(os.path.join(PUBLIC, f)))


if __name__ == "__main__":
    main()
