# A股沪深主板涨跌停 · 自动更新网页看板

![性质](https://img.shields.io/badge/市场-沪深主板普通A股-4079dc) ![刷新](https://img.shields.io/badge/更新-交易日收盘后-1e9c81)

这是**可部署的网页程序**，不是已经上线的网站。首页 `index.html` 可直接双击打开，首次会展示醒目标注的**虚构演示数据**。需要每天自动看到真实行情，应部署到 GitHub Pages 并启用 GitHub Actions。

## 你得到什么？

- 4张统计卡：收盘涨停 / 收盘跌停 / 首板 / 最高连板
- 连板梯队、N天M板、近期涨跌停数量趋势、行业/题材热度排行
- 涨停、跌停、炸板三张完整股票表（以上游数据池成功返回的范围为准），关键词搜索、题材筛选、连板筛选、历史日期切换、导出 CSV、股票详情页
- **强制筛选**：仅沪深主板普通A股：`600/601/603/605`、`000/001/002/003`；排除 `ST/*ST`、创业板、科创板、北交所、退市整理、新股特殊标识等
- 涨停原因：优先尝试第三方财经来源，始终标记为**市场归因**而非确定因果；查不到就写**待核实**。要得到公司公告核实级别，需另对接公告核验服务
- 失败保护：接口异常/交易日校验失败不会将“0只”当成真实结果覆盖上一次成功的文件；非交易日保留最后交易日。

## 1. 不上线，先在电脑预览

下载并解压后，双击 `index.html` 即可看演示界面（全部是**虚构示例**）。

在 VS Code 终端也可以运行：

```powershell
cd 你的解压目录\a-share-dashboard
python -m http.server 8000
```

浏览器访问 `http://localhost:8000`。这只是**本机地址**，不是随时随地能访问的公网网址。

## 2. 发布到固定网址（GitHub Pages）

1. 登录 GitHub，创建一个公开仓库，例如 `a-share-dashboard`。公开仓库中的行情数据也将是公开的。
2. 把本项目**所有文件、隐藏的 `.github` 文件夹**一并上传到仓库根目录。可在 GitHub 仓库 `Add file → Upload files`，或使用 Git 命令：

   ```powershell
   git init
   git add .
   git commit -m "初始化涨跌停网页看板"
   git branch -M main
   git remote add origin https://github.com/你的用户名/a-share-dashboard.git
   git push -u origin main
   ```

3. 打开仓库 **Settings → Pages → Build and deployment → Source**，选 **GitHub Actions**。
4. 打开 **Actions → 每日收盘数据与看板部署 → Run workflow** 手动执行首次部署。即使行情接口暂不可用，也会先部署网页；在尚无真实快照时网页会醒目标注 **演示数据**，绝不会冒充真实交易数据。建议在交易日16:00后首次执行抓取。首次执行如遇权限问题，再检查 Settings → Actions → General 的工作流权限。
5. 部署成功后，你自己的固定地址通常是：

   `https://你的GitHub用户名.github.io/a-share-dashboard/`

   实际地址以 GitHub Pages 页面提供的 URL 为准。这里的地址**不是已经创建的网站**。

自动更新时间：每周一至周五 **北京时间17:40** 发起 GitHub Actions，平台可能排队延迟；节假日跳过，失败不覆盖旧数据。网页顶部“刷新数据”会重新读取网站已经发布的 JSON；如果后台失败，点刷新也不会凭空生成新行情。

## 3. 数据与可靠性界限

| 字段 | 来源/口径 | 状态 |
|--|--|--|
| 涨停、跌停、炸板池 | AKShare 聚合东方财富相关行情池 | 自动抓取；接口变化/网络限制可能失败 |
| 连板数、N天M板 | 东方财富提供的连板和涨停统计 | 以来源字段为准，不瞎编未给出的结构 |
| 行业 | 东方财富所属行业 | 自动；**细分概念**在补充数据可用时增强 |
| 涨停原因 | 可选 levistock（财联社/开盘红） | 第三方市场归因；不冒充公告事实；可能缺失 |
| 收盘封单最终核验 | 需交易所成交记录或专业数据授权 | **当前未完成逐笔复核** |
| 个股是否可交易 | 代码白名单 + 名称风险提示过滤 | 无法替代当日交易所停牌/风险警示清单，具体状态需复核 |

本程序**没有**专业商业数据订阅；无法保证100%完整、准确或实时；不要据此单独下单。

### 若未来需要更精准的涨停逻辑

可添加“事件/公告数据库”关联、同花顺涨停揭秘、交易所风险证券状态、交易日逐笔封单核验、公司公告证据链接等，仍然只能将关联作为线索而非因果证明。

## 4. 修改自动更新时间

编辑 `.github/workflows/daily.yml`：

```yaml
schedule:
  - cron: '40 17 * * 1-5'
    timezone: 'Asia/Shanghai'
```

日期与最新快照的储存路径分别为 `data/history/YYYY-MM-DD.json` 和 `data/latest.json`。历史最多在首页走势图读取最新14个交易日；只要仓库不删除旧数据，历史快照会永久留存。

## 5. 本地试抓取（可选）

需要 Python **3.11** 或以上（不必影响你原有 Anaconda Python 3.8 项目）：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install levistock   # 可选：补全涨停理由
python scripts/update_data.py
```

注意：**16:00前不更新当日数据**。如果东方财富接口、开盘红、财联社等网站在 GitHub Actions 海外机器上访问失败，更新流程会停止并保留已有快照。可考虑国内服务器、稳定持牌数据接口或授权的付费源。

## 6. 项目结构

```text
index.html                      # 仪表盘，纯HTML/CSS/JS
scripts/update_data.py          # 数据筛选/清洗/保存/来源补充
scripts/test_update_data.py     # 筛选等单元测试
.github/workflows/daily.yml     # 每天自动抓取 + 部署
requirements.txt                # Python依赖
data/history_index.json         # 历史日期索引
data/latest.json                # 成功抓取后生成
data/history/日期.json           # 成功抓取后生成
```

> 这套**网页**和此前 ChatGPT 里每天18:00的**文字复盘定时任务**是两套独立运行的任务，不会自动共享数据。要在网页展示那项文字定时任务的分析结果，还需要把文字报告通过接口写入网页的数据文件。
