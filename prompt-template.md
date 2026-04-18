# 内网轻量工具 — 快速开发提示词模板

> 从 html-preview-server 项目提炼，适用于：内网文件管理、简易审批流、内部文档站、数据看板等单服务工具。
> 核心理念：**零构建、单模板、SQLite、Docker 一键部署**。

---

## 使用方式

把下面 `[替换区]` 的内容换成你的实际需求，粘贴给 Claude Code 即可。

---

## 提示词模板

```
帮我创建一个内网轻量 Web 工具，项目名：[项目名称]。

## 功能需求

[描述你要做什么，例如：]
- 用户可以 [核心动作]
- 数据按用户隔离，每个用户只能看到自己的数据
- 管理员（通过密码登录）可以查看和管理所有用户的数据
- [其他功能...]

## 技术栈（固定）

- Python 3.11 + FastAPI + uvicorn
- 数据库：aiosqlite（SQLite 异步），数据文件放在 data/meta.db
- 模板：Jinja2，HTML/CSS/JS 全部内联在一个模板文件中，不使用前端构建工具
- 文件存储：data/ 目录下按业务需要建子目录
- 部署：Docker + docker-compose，挂载 data/ 卷持久化

## 文件结构

```
[项目名]/
├── config.py          # 配置：从 .env 和环境变量读取，定义路径常量
├── database.py        # 数据库层：建表、迁移、CRUD 函数（纯 aiosqlite）
├── main.py            # 路由和业务逻辑：FastAPI app、页面路由、API 路由
├── templates/
│   └── index.html     # 单页面应用：Jinja2 模板，含内联 CSS + JS
├── data/              # 运行时数据（gitignore）
├── .env               # 环境变量（gitignore）
├── .gitignore
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 代码规范

### config.py
- 用 `python-dotenv` 加载 `.env`
- 所有配置从环境变量读取，提供合理默认值
- 用 `pathlib.Path` 定义路径，启动时自动 `mkdir(parents=True, exist_ok=True)`
- 配置项：HOST、PORT、ADMIN_PASSWORD、MAX_UPLOAD_SIZE 等

### database.py
- 用 `CREATE TABLE IF NOT EXISTS` 建表
- 用 `ALTER TABLE ... ADD COLUMN` 做增量迁移（try/except 忽略已存在列）
- 所有函数是 `async def`，用 `async with aiosqlite.connect(DB_PATH) as db`
- 返回类型：单条用 `dict | None`，列表用 `list[dict]`
- `db.row_factory = aiosqlite.Row`，结果用 `dict(row)` 转换
- update 函数用白名单过滤允许更新的字段，空字符串表示清除字段

### main.py
- 用 `@asynccontextmanager` 的 `lifespan` 做启动初始化（init_db）
- 工具函数放最上面，按路由分组用注释分隔：`# ── 认证 API ──`
- 认证体系：
  - `get_identity(request)` 返回 `(username, is_admin)` 元组
  - 普通用户：输入用户名即可进入，存 Cookie（支持中文需要 `urllib.parse.quote/unquote`）
  - 管理员：密码登录，Cookie 存 auth_token
  - 所有管理接口先检查身份，管理员看全部/普通用户只看自己的
  - 管理接口做权限检查：`if not admin and project.owner != username: raise 403`
- ID 生成：用 `secrets.choice` 从 a-z0-9 生成 6 位随机串
- 错误处理：用 `HTTPException`，返回中文 detail
- 预览/公开访问的路由不做登录校验（如 /p/{id}）
- 启动入口：`uvicorn.run("main:app", host=HOST, port=PORT)`

### templates/index.html
- 单文件包含全部 HTML + CSS + JS，不拆分
- Jinja2 控制页面状态（显示登录页/主界面/密码页）
- CSS：
  - 用 CSS 变量定义颜色体系（--bg, --card, --ink, --muted, --line, --primary, --danger, --success）
  - 不使用任何 CSS 框架，纯手写
  - 响应式：`@media (max-width: 640px)` 调整布局
  - 通用组件样式：.btn, .btn-primary, .btn-danger, .modal, .toast
- JS：
  - 原生 JS，不使用任何框架
  - 用 `fetch` 调 API，`FormData` 提交表单
  - 文件上传用 `XMLHttpRequest`（支持进度条）
  - 搜索/筛选在前端做（缓存数据，JS 过滤），不走后端接口
  - 用 `{% if authenticated %}` Jinja2 变量控制 JS 常量（如 IS_ADMIN）
  - Toast 通知：创建 DOM 元素，3秒后自动移除
  - 模态框：通过 `classList.add/remove('active')` 控制显示
  - XSS 防护：用 `esc()` 函数（textContent 转义）渲染用户输入
- 页面结构：
  1. Toast 容器（固定定位右上角）
  2. 登录页（条件渲染）
  3. 主界面（条件渲染）
     - 顶栏：标题 + 用户名徽章 + 操作按钮
     - 上传/操作区
     - 筛选栏（管理员可见）
     - 统计卡片
     - 项目列表 + 搜索框
  4. 模态框们（编辑、删除确认、二维码等）

### Docker 部署
- Dockerfile：python:3.11-slim，COPY 代码，暴露端口，CMD 运行
- docker-compose：build 本地镜像，挂载 `./data:/app/data`，env_file 引用 .env

## 环境变量

```
ADMIN_PASSWORD=[管理密码]
PORT=8080
HOST=0.0.0.0
```

## 开发步骤

1. 先写 config.py（配置和路径）
2. 再写 database.py（建表 + CRUD）
3. 然后 main.py（路由和业务逻辑）
4. 最后 templates/index.html（前端页面）
5. 补齐 .env、.gitignore、requirements.txt、Dockerfile、docker-compose.yml
6. 测试：python main.py 启动，浏览器验证功能

## 注意事项

- Cookie 中的用户名等非 ASCII 值必须用 `urllib.parse.quote()` 编码后写入，读取时用 `unquote()` 解码
- 所有用户可输入的字符串在渲染到 HTML 时必须经过 esc() 转义防 XSS
- 文件操作要防止路径逃逸（resolve 后 relative_to 检查）
- ZIP 解压要过滤 __MACOSX、.DS_Store 等系统文件，检测并处理单层根目录
- 数据库迁移用 try/except 包裹 ALTER TABLE，不破坏已有数据
- 前端搜索在前端做：缓存全量数据，JS 过滤，减少后端接口
```

---

## 填写示例

下面是一个填写好的示例，展示如何用这个模板创建一个"内网简易投票工具"：

```
帮我创建一个内网轻量 Web 工具，项目名：vote-server。

## 功能需求

- 用户输入名字进入，可以创建投票（标题 + 选项列表）
- 可以分享投票链接给其他人投票（匿名投票，每个浏览器限投一次）
- 投票创建者可以查看实时统计（票数、占比）
- 管理员可以查看所有投票、关闭投票、删除投票
- 支持搜索投票（按标题）
- 投票可设置截止时间

[技术栈、文件结构、代码规范部分...直接复用模板原文...]
```

---

## 模板设计思路

| 设计决策 | 原因 |
|---------|------|
| 单 HTML 模板 + 内联 CSS/JS | 内网工具不需要构建链，复制即用 |
| aiosqlite | 零运维数据库，data/ 目录挂载即备份 |
| 用户名 Cookie 而非注册 | 内网场景最低摩擦 |
| 管理员密码全局 | 一个密码管全局，内网够用 |
| 前端搜索而非后端 | 数据量小，减少 API 设计 |
| Docker 部署 | 内网服务器 docker-compose up 即跑 |
| 增量 ALTER TABLE 迁移 | 不破坏已有数据，不依赖迁移框架 |
