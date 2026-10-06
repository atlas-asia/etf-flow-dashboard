# ETF 净流动周更看板（自动更新版）

每周六北京时间 09:00，由 GitHub Actions 自动跑一遍「抓取份额 + 抓取净值 + 重算」，
并把最新看板发布到 GitHub Pages，**完全免费、不依赖你本机电脑开机**。

## 它做了什么
1. 抓取沪深交易所 ETF 原始份额（上交所 + 深交所，断点续传）
2. 抓取每只 ETF 的每日单位净值（**东方财富** lsjz 接口，免费、无需任何账号/密钥）
3. 按你的四 Sheet 分类（宽基 / 行业 / 风格 / 港股 ETF）重算
   - 月度净流动矩阵
   - 最新一个完整交易周（周一至周五）净流动
4. 生成 `public/index.html` + `public/ETF净流动数据.xlsx` 并发布到 GitHub Pages

> 净流动口径（与你确认一致）：`净流动(元)＝(当日份额 − 前一交易日份额) × 当日单位净值`

---

## 首次发布步骤（纯网页操作，不用装任何软件、不用敲命令）

### 第 1 步：在 GitHub 上新建一个空仓库
1. 浏览器打开 https://github.com ，登录你的账号
2. 点右上角 **「+」→ 「New repository」**（新建仓库）
3. 填仓库名：例如 `etf-flow-dashboard`（只能英文/数字/减号）
4. **可见性选「Public」**（最省事，Pages 一定免费可用；若想保密选 Private 也行，免费版同样支持 Pages）
5. 下方三个勾选项 **全部不要勾**（不要勾 Add a README / .gitignore / License），让仓库是空的
6. 点 **「Create repository」**

### 第 2 步：把本文件夹的内容上传进去（关键！）
> 你刚注册的 GitHub 账号已经能用了，这一步只用到浏览器拖拽。

1. 打开你电脑上的**文件资源管理器**，进入本文件夹 `etf-dashboard`
2. 在文件夹空白处上方点 **「查看」→ 勾选「隐藏的项目」**（很重要！这样你才看得到 `.github` 这个隐藏文件夹，否则定时任务不会生效）
3. 按 `Ctrl + A` 全选 `etf-dashboard` 里面的**所有内容**（应包含：`etf_tracker` 文件夹、`.github` 文件夹、`public` 文件夹、`cache` 文件夹、`requirements.txt`、`.gitignore`、`README.md`）
4. 回到 GitHub 那个空仓库页面，把这一大堆文件**直接拖进浏览器**的虚线框里（写着 "drag and drop" 的区域）
5. 等进度条走完，在最下方 **Commit changes** 的框里随便写个说明（如 `init`），点 **「Commit changes」**

> 如果上传后你在仓库里**没看到 `.github` 文件夹**：说明隐藏项没选上。请补做下面这一步——
> 在仓库页面点 **「Add file」→「Create new file」**，文件名填 `.github/workflows/weekly.yml`，
> 把本 README 最下方「附录：weekly.yml 完整内容」整段复制粘贴进去，再点 **Commit changes**。
> （能看到 `.github` 就**跳过**这步，不要重复建。）

### 第 3 步：手动触发第一次运行（让系统把数据跑出来）
1. 进入仓库 → 顶部 **「Actions」** 标签页
2. 左侧应看到工作流 **「ETF 周更自动更新」**，点进去
3. 点右侧 **「Run workflow」→ 再点绿色「Run workflow」**
4. 等几分钟（首次要抓全量数据，可能 10~30 分钟），状态变绿 ✅ 即成功

### 第 4 步：开启 GitHub Pages（拿到公网链接）
1. 仓库 → **「Settings」→ 左侧「Pages」**
2. **Build and deployment → Source** 选 **「Deploy from a branch」**
3. **Branch** 选 **`gh-pages`**，文件夹选 **`/ (root)`**，点 **Save**
4. 约 1~2 分钟后，页面会显示你的站点地址，形如：
   `https://<你的用户名>.github.io/etf-flow-dashboard/`

以后这个链接就是你的看板，每周六自动刷新。

---

## 以后全自动了
- **每周六 09:00（北京时间）** GitHub 自动更新；你电脑关着、没开机都无所谓。
- 想立刻看更新：进仓库 **Actions** 点 **Run workflow**。
- 改了分类表（`etf_tracker/ETF分类.xlsx`）后，把它重新放进 `etf_tracker/` 再上传一次即可
  （在仓库里进入 `etf_tracker` 文件夹 → Add file → Upload files 覆盖同名文件）。

---

## 本地手动跑（可选，用于自己验证）
```bash
pip install -r requirements.txt
# 本地默认走聚源(FinQuery)；CI 才走东方财富
python etf_tracker/weekly_update.py
```

---

## 附录：weekly.yml 完整内容（仅在第 2 步补建工作流时需要）
```yaml
name: ETF 周更自动更新

on:
  schedule:
    # 北京时间 每周六 09:00 = UTC 每周六 01:00
    - cron: '0 1 * * 6'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 300
    steps:
      - name: 签出代码
        uses: actions/checkout@v4

      - name: 配置 Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 恢复增量缓存（断点续传用，跨次累积）
        uses: actions/cache@v4
        with:
          path: cache
          key: etf-cache-${{ github.run_number }}
          restore-keys: |
            etf-cache-

      - name: 安装依赖
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: 运行周更（净值走东方财富，免费无密钥）
        env:
          NAV_SOURCE: eastmoney
        run: python etf_tracker/weekly_update.py

      - name: 部署到 GitHub Pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./public
          publish_branch: gh-pages
```
