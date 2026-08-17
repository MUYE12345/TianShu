# 天枢 Tianshu

> **智能体中枢平台** —— AI 问答 / 多智能体编排 / 知识库 RAG / 论文解析 / Wiki 知识管理 / 新闻聚合 / 桌面划屏翻译与陪伴桌宠  
> **版本**: v1.0.0

---

## 📋 目录

- [项目简介](#项目简介)
- [功能总览](#功能总览)
- [快速开始](#快速开始)
- [模型配置](#模型配置)
- [使用指南](#使用指南)
- [核心特性](#核心特性)
- [项目架构](#项目架构)
- [技术栈](#技术栈)

---

## 项目简介

**天枢**（Tianshu，北斗第一星，寓意"中枢"）是一个面向个人日常场景的 **AI 智能体中枢平台**，把多智能体协作、知识库检索增强（RAG）、论文智能解析、Wiki 知识沉淀、新闻聚合与桌面辅助工具统一到一个平台。

- **智能问答**：单智能体（规划/工具调用/反思）+ 专家模式（多智能体自动分工）
- **智能体编排**：拖拽搭建团队图，主控 → 子智能体并行执行 → 汇总，真实调用大模型
- **知识沉淀**：知识库 RAG（Milvus 向量检索 + 混合检索），一键生成网页 / 思维导图 / PPT / 简报 / 时间轴产物
- **论文解析**：魔搭式双栏阅读（真实 PDF 原图 + 段落框 + 点击联动翻译），动态逐页翻译 + AI 章节解读
- **Wiki 笔记**：上传文章自动解析成结构化 wiki，知识图谱 + 思维导图可视化
- **多终端**：Web 界面 + tkinter 桌面悬浮窗（划屏翻译 / Q 版桌宠）+ 飞书 / QQ 邮箱推送

---

## 功能总览

| 模块 | 功能 |
|------|------|
| 🤖 **AI 问答** | 单智能体（规划 → 工具调用 → 反思）、专家模式多智能体协作、SSE 流式输出、会话历史 |
| 🧩 **智能体编排** | 拖拽搭建团队（主从协作 / 平等协作）、主控规划 → 子智能体并行 → 汇总、实时执行日志 |
| 📚 **知识库** | 主题知识库 + 全部知识、文档上传解析、RAG 问答带引用、Milvus 向量检索 + 混合检索 |
| 🎨 **知识产物** | 网页 HTML / 思维导图 / PPT（可下载 .pptx）/ 简报 / 时间轴，基于大模型自动生成 |
| 📄 **论文解析** | 上传 PDF → 魔搭式双栏（真实 PDF 原图 + 段落框 + 点击同步翻译）、动态逐页翻译、AI 章节解读、缩放 |
| 📝 **Wiki 笔记** | 上传文章解析为 wiki、Markdown 编辑、`[[双向链接]]`、知识图谱、思维导图 |
| 📰 **每日新闻** | 深科技 / 机器之心 / 量子位 / 新智元，自动爬虫 + AI 摘要 |
| 📡 **时事新闻** | 新京报（第一看点 / 国际 / 科技 / 政事） |
| 🛠 **工具 / MCP / 技能市场** | 安装 / 卸载 / 修改 / 删除，三方能力即装即用 |
| ⏰ **定时任务** | Cron 可视化配置，数据库持久化 |
| 🐱 **Q 版桌宠** | tkinter 悬浮窗 + 智能提醒（天气 / 休息 / 知识 / 任务） |
| 🔤 **划屏翻译** | tkinter 悬浮窗划选截图，视觉大模型识别 + 逐行翻译 |
| ⚙️ **设置** | 模型管理（11 个模型）、推送、桌宠、MCP、SKILL、日志 |

---

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 20+

### 1. 配置环境变量

```bash
cd Intelligen_housekeeper
# 编辑 .env，至少配置大模型 API Key
```

### 2. 启动后端

```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 3. 启动前端（另一个终端）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。首次使用先在登录页注册账号。

### 4. 启动桌面应用（可选，需本机桌面环境）

```bash
python run_desktop.py           # 划屏翻译 + 桌宠
python run_desktop.py translate # 仅划屏翻译
python run_desktop.py pet       # 仅桌宠
```

---

## 模型配置

天枢支持 **OpenAI 兼容接口**的多模型管理，模型**完全由你在「设置 → 模型配置」页面自行配置**（数据库持久化），支持：

- **添加任意模型**：填写 API 地址（如 DashScope / DeepSeek / 自建网关）、API Key、模型名，可选「思考模式」「视觉支持」
- **动态切换默认模型**：所有 AI 功能（问答 / 编排 / 知识库 / 论文翻译）默认使用你设置的默认模型
- **启用 / 停用 / 测试**：随时测试某模型能否连通，停用后不再使用

### 环境变量（.env）

启动时的兜底配置（首次运行时如数据库无模型会自动导入）：

```ini
# 主模型
MAIN_MODEL_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
MAIN_MODEL_API_KEY=sk-your-api-key
MAIN_MODEL_NAME=your-model-name
MAIN_MODEL_THINKING_MODE=false

# 其它
DASHSCOPE_API_KEY=sk-your-api-key   # 与 DashScope 类端点相关
REVIEW_MODEL_NAME=your-review-model # 审查模型
```

### 视觉模型

截图翻译、论文扫描页图片识别等**图片类功能**需要**支持视觉的模型**（如通义千问 VL 系列）。在「设置 → 模型配置」里把视觉模型勾选「👁 视觉支持」，系统会自动优先用它处理图片；若未配置，会回退到 `qwen3.6-flash`。

> 注意：默认文本模型（如 DeepSeek）一般不支持看图，图片功能请确保已配置一个带视觉支持的模型。

---

## 使用指南

### Web 界面路由

| 页面 | 路由 |
|------|------|
| AI 问答 | `/chat` |
| 每日新闻 | `/daily-news` |
| 时事新闻 | `/current-news` |
| 论文解析 | `/paper`、`/paper/:id` |
| 知识库 | `/wiki`、`/wiki/:id` |
| Wiki 笔记 | `/notes` |
| 定时任务 | `/plan` |
| 智能体管理 | `/agent` |
| 智能体编排 | `/agent-orchestration` |
| 工具市场 | `/tools` |
| MCP 市场 | `/mcp-market` |
| 技能市场 | `/skills-market` |
| 设置 | `/settings/model`（及 push / avatar / mcp / skills / profile / logs） |

### AI 问答

- 默认单智能体：任务规划 → 按需调用工具（文件 / shell / 搜索等）→ 自我反思改进，SSE 流式输出
- 打开「🧠 专家」开关：触发**多智能体编排**（Master 分解任务 → 动态 Worker 并行执行 → 汇总）
- 左侧会话栏：历史会话管理，切换模块后状态保留（KeepAlive）

### 智能体编排

- 从左侧拖拽（或点击）智能体搭建团队：第一个为主控，其余为子智能体
- 选择「主从协作」或「平等协作」模式，输入全局指令，点执行
- 真实调用大模型：主控规划分工 → 子智能体并行执行 → 主控汇总，全程流式展示日志与最终结果

### 知识库

- 创建主题知识库 → 上传 PDF / Word / Excel / PPT / md / txt 等 → 自动解析
- RAG 问答带**引用溯源**，支持选中部分文档聚焦提问
- 一键生成网页、思维导图、PPT（可下载 .pptx）、简报、时间轴
- 向量检索基于 **Milvus**（语义 + 关键词混合检索 + 重排）

### 论文解析

- 上传 PDF → OCR 提取文本 → 渲染为真实 PDF 页面图（魔搭式）
- 左栏真实 PDF 原图 + 段落框，点击段落框右侧翻译**自动定位高亮**，支持缩放
- **动态翻译**：滚动到未翻译页自动触发，显示"正在翻译"状态，翻完即显示
- AI 章节解读：摘要 / 引言 / 方法等逐段中文解读

### Wiki 笔记

- 「上传文章解析」：把文章自动拆成根来源页 + 各章节子页（`[[链接]]` 关联）
- 知识图谱：`[[双向链接]]` 形成的关联图
- 思维导图：文章 → 章节的树形可视化，点节点直达页面

---

## 核心特性

### 🛡️ 安全围栏（Tool Harness）

所有 Agent 工具调用（`SimpleTool.invoke` 统一入口）默认经过五层防护，防止危险操作：

| 防护层 | 说明 | 默认 |
|--------|------|------|
| **紧急熔断** | 一键暂停全部工具执行（事故时先按这个） | 关 |
| **风险分级** | 危险工具（shell/cli/git/沙箱代码执行/用户上传工具）安全模式下**默认禁止** | 安全模式开 |
| **命令白名单** | 即使关闭安全模式，`rm -rf` / `format` / `shutdown` 等破坏性命令仍被拦截 | 常开 |
| **路径围栏** | 写文件/工作目录必须落在项目根内，防止越界写入 | 开 |
| **内容级限制** | 敏感文件（`.env`/数据库/私钥/`.git` 凭据）禁止读写；写工具只能写对应扩展名（防篡改代码/配置） | 常开 |
| **Docker-only 执行** | 沙箱代码执行必须在 Docker 容器内（`--network=none --cap-drop=ALL`），无本地直跑回退 | 强制 |
| **爬虫 SSRF 防护** | 任意 URL 抓取仅允许 http/https，拒绝内网/回环/链路本地/云元数据地址，防攻击其他平台 | 常开 |
| **限流 + 审计** | 每分钟调用上限；全量调用记录（内存 + `data/harness/audit.jsonl`） | 开 |

管理界面：侧栏「系统 → 安全围栏」（`/settings/harness`），可开关各项策略、查看风险分级与审计。
管理 API（需登录）：`GET /api/harness/status`、`GET /api/harness/audit`、
`POST /api/harness/safe-mode`、`POST /api/harness/emergency-stop`、
`POST /api/harness/path-fence`、`POST /api/harness/block-tool`。

> 关闭安全模式可让 Agent 执行 shell/git 等操作（仍受命令白名单与审计约束）；想完全放开或收紧，用上面的 API 调整。

### 真实的多智能体编排（参考 tianzhi2 / LangGraph）

- 单智能体走 LangGraph（Plan → Execute → Reflect），工具循环有预算上限，回答干净
- 编排页可拖拽搭建用户自定义团队，主控 → 子智能体并行 → 汇总，非模拟
- 运行中切换模块不中断（KeepAlive + 后端任务完成）

### 动态翻译

- 论文翻译按需触发（滚动到哪页翻哪页），队列 + 失败跳过，避免无限重试
- 单页翻译接口 `POST /api/paper/{id}/pages/{n}/translate`，后台完成后前端自动刷新

### 稳定性

- Windows 下所有文件读写显式 UTF-8（修复 GBK 编码崩溃）
- Selenium 爬虫显式本地 chromedriver + 超时回退（避免国内被墙的联网下载挂起）
- 会话 / 编排页 KeepAlive 状态保留

---

## 项目架构

```
Intelligen_housekeeper/
│
├── agent/                            # Agent 引擎
│   ├── langgraph_agent.py            # LangGraph 单智能体 + 专家模式多智能体
│   ├── multi_agent_service.py        # Master/Worker 多智能体调度器
│   ├── orchestration_service.py      # 用户自定义团队编排
│   ├── rag_engine.py                 # RAG 检索（Milvus 向量 + 关键词混合）
│   ├── multi_agent_memory.py         # 三层记忆管理器
│   ├── tool_service.py               # 工具管理
│   ├── knowledge_engine.py           # 统一知识引擎
│   ├── crawlers/                     # 新闻爬虫 + 浏览器爬虫
│   ├── notification/                 # 飞书 / QQ 邮箱推送
│   └── memory/                       # 记忆系统
│
├── backend/                          # FastAPI 后端
│   ├── main.py                       # 应用入口
│   ├── config.py                     # Pydantic 配置（.env）
│   ├── database.py                   # SQLAlchemy + SQLite
│   │
│   ├── routers/                      # API 路由
│   │   ├── chat.py                   #   问答（SSE 流式 + 会话）
│   │   ├── knowledge.py              #   知识库（上传/解析/问答/产物/pptx）
│   │   ├── wiki.py                   #   Wiki 页面 + 文章解析 + 图谱
│   │   ├── paper.py                  #   论文（OCR/可视化/翻译/章节解读）
│   │   ├── agent.py                  #   智能体 CRUD + 编排
│   │   ├── memory.py                 #   记忆 / Milvus
│   │   ├── companion.py              #   陪伴助手提醒
│   │   └── ... （共 20 个路由器）
│   │
│   ├── core/                         # 核心架构
│   │   ├── model_config.py           #   多模型管理 + 视觉模型
│   │   └── adapters/                 #   LLM 适配器（OpenAI/Anthropic）
│   │
│   ├── models/                       # SQLAlchemy 模型
│   ├── services/                     # 业务服务
│   ├── companion/                    # 桌宠 + 提醒
│   └── screen_translate/             # 划屏翻译（悬浮窗 + 视觉模型翻译）
│
├── frontend/                         # Vue 3 前端
│   ├── src/
│   │   ├── views/                    #   chat/news/paper/wiki/agent/settings 等
│   │   ├── components/               #   wiki（KbCover/KnowledgeGraph/WikiMindMap）等
│   │   ├── layouts/                  #   MainLayout（Kitro 风格 + KeepAlive）
│   │   ├── router/                   #   路由
│   │   └── styles/                   #   Kitro 设计令牌
│   └── vite.config.js                #   /api + /static 代理
│
├── data/                             # 运行时数据（SQLite / 知识库 / wiki / 论文图）
├── docs/                             # 设计文档
├── .env                              # 环境变量
├── requirements.txt
└── run_desktop.py                    # 桌面应用启动器（tkinter）
```

---

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| 框架 | FastAPI + Uvicorn + SQLAlchemy |
| 数据库 | SQLite |
| 向量库 | Milvus（RAG 向量检索）+ ChromaDB |
| Agent | LangGraph + 自研多智能体调度器 |
| 检索 | RAG 混合检索（向量 + BM25 + 重排） |
| LLM | OpenAI 兼容多模型适配（DashScope 等） |
| 桌面 | tkinter（标准库） |

### 前端

| 类别 | 技术 |
|------|------|
| 框架 | Vue 3 (Composition API) |
| UI | Element Plus + ECharts（图谱/思维导图） |
| 构建 | Vite |
| 风格 | Kitro 设计令牌（CSS 变量 + 主题） |

---

> 项目状态: v1.0.0 · 持续开发中
