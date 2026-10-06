# -*- coding: utf-8 -*-
"""每周ETF净流动更新编排：份额 -> 恒生聚源NAV -> 重算 -> 输出到public目录。
用法: python weekly_update.py
"""
import os, sys, subprocess, shutil
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
PY = sys.executable
PUBLIC = os.path.join(BASE, "public")

def run(script):
    print(f"===== {os.path.basename(script)} =====", flush=True)
    subprocess.run([PY, os.path.join(HERE, script)], check=True)

def main():
    # NAV 数据源：默认用本机聚源(FinQuery)；CI 设 NAV_SOURCE=eastmoney 改用东方财富(免费无密钥)
    nav_source = os.environ.get("NAV_SOURCE", "gildata").lower()
    # 1. 份额（含断点续传）
    run("fetch_shares.py")
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
    # 4. 复制到public
    os.makedirs(PUBLIC, exist_ok=True)
    src_html = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026_矩阵版.html")
    src_xlsx = os.path.join(BASE, "ETF净流动_按用户四Sheet分类_2026_矩阵版.xlsx")
    shutil.copy2(src_html, os.path.join(PUBLIC, "index.html"))
    shutil.copy2(src_xlsx, os.path.join(PUBLIC, "ETF净流动数据.xlsx"))
    print("public目录已更新:")
    for f in os.listdir(PUBLIC):
        print(" ", f, os.path.getsize(os.path.join(PUBLIC, f)))

if __name__ == "__main__":
    main()
