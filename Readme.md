# 📈 Limit-Up Sniper (涨停狙击手)

**Limit-Up Sniper** 是一个基于 AI 的 A 股短线辅助决策系统。它结合了 **Deepseek 大模型** 的语义分析能力和 **新浪财经** 的实时行情数据，旨在帮助用户快速捕捉市场热点，识别竞价抢筹（Aggressive）和盘中打板（LimitUp）的机会。

![Status](https://img.shields.io/badge/Status-Active-green) ![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Vue.js](https://img.shields.io/badge/Frontend-Vue.js%203-42b883)

## ✨ 核心功能

1.  **🤖 AI 舆情分析 (Deepseek Powered)**
    *   自动抓取财联社电报新闻。
    *   使用 Deepseek V3 模型深度理解新闻内容，挖掘潜在受益股。
    *   **智能分类**：
        *   **🎯 Aggressive (竞价抢筹)**：针对重磅利好或核心龙头，适合开盘竞价关注。
        *   **🚀 LimitUp (盘中打板)**：针对中等利好或换手板预期，适合盘中确认后介入。

2.  **📊 实时行情监控**
    *   毫秒级对接新浪财经 Level-1 行情。
    *   实时计算涨幅、涨速，动态刷新。
    *   **视觉增强**：涨停板高亮、呼吸灯特效、红绿盘色阶显示。

3.  **📱 全平台响应式 UI**
    *   **桌面端**：左右分屏设计，左侧展示竞价标的，右侧展示盘中异动。
    *   **移动端**：底部 Tab 切换，完美适配手机屏幕，随时随地复盘。

4.  **⚡ 实时交互体验**
    *   **WebSocket 日志终端**：前端实时显示后台 AI 分析进度和系统日志，拒绝黑盒等待。
    *   **智能显隐**：根据当前交易时间（09:30, 15:00）自动切换“竞价”与“盘中”列表的显示状态。

## 🛠️ 技术栈

*   **后端**: Python 3.12, FastAPI, Uvicorn
*   **前端**: HTML5, Vue.js 3 (CDN), TailwindCSS (CDN)
*   **数据源**: 财联社 (新闻), 新浪财经 (行情)
*   **AI 模型**: Deepseek Chat API

## 🚀 快速开始

### 1. 环境准备

确保已安装 Python 3.8 或更高版本。

```bash
# 克隆或下载本项目到本地
git clone <repository-url>
cd Limit-Up-Sniper
```

### 2. Windows 快速启动 (推荐)

我们提供了 Windows 批处理脚本，方便一键安装和运行。

1.  **安装**: 双击运行 `install.bat`。
    *   自动创建虚拟环境并安装依赖。
    *   提示输入 Deepseek API Key。
2.  **运行**: 双击运行 `run.bat`。
    *   自动启动服务并打开浏览器。
3.  **更新**: 双击运行 `update.bat`。

### 3. Linux / Mac 手动启动

#### 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 配置 API Key

```bash
export DEEPSEEK_API_KEY="sk-你的Deepseek密钥"
```

#### 启动服务

```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 4. 访问系统

打开浏览器访问：[http://127.0.0.1:8000](http://127.0.0.1:8000)

## 📖 使用指南

1.  **每日复盘 (盘前/盘后)**
    *   点击右上角的 **"开始复盘"** 按钮。
    *   系统将自动抓取过去几小时的新闻，调用 AI 进行分析。
    *   分析完成后，页面会自动刷新，展示挖掘到的潜力股。

2.  **盘中监控 (09:30 - 15:00)**
    *   保持页面开启，系统每 3 秒自动刷新一次行情价格。
    *   **竞价栏 (左)**：关注开盘前的集合竞价表现。
    *   **打板栏 (右)**：关注盘中涨速过快或即将封板的股票。

3.  **手动加自选**
    *   在右上角输入框输入代码（如 `sh600519`），回车即可加入监控列表。

## 📂 项目结构

```
Limit-Up-Sniper/
├── app/
│   ├── main.py              # FastAPI 后端主程序 (WebSocket, API)
│   ├── core/                # 核心逻辑模块
│   │   ├── news_analyzer.py # 新闻抓取与 AI 分析
│   │   ├── market_scanner.py# 市场扫描与行情获取
│   │   └── stock_utils.py   # 工具函数
│   └── templates/           # 前端页面
├── data/                    # 数据存储 (JSON)
├── run.py                   # 启动脚本
├── install.sh               # 一键部署脚本
└── requirements.txt         # 依赖列表
```

## ⚠️ 免责声明

本项目仅供编程学习与技术交流使用。
*   **数据来源**：本项目使用公开网络数据，不保证数据的准确性与及时性。
*   **投资风险**：系统生成的分析结果仅代表 AI 对新闻的语义理解，**不构成任何投资建议**。股市有风险，入市需谨慎。开发者不对因使用本软件产生的任何亏损负责。

---
*Built with ❤️ by Limit-Up Sniper Team*
