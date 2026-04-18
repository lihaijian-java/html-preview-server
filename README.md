# HTML Preview Server

> 受 [Pagey.site](https://pagey.site/) 启发，打造的**可私有部署**的 HTML 站点托管服务。
> 上传 HTML 或 ZIP，秒级生成预览链接——无需公网，内网即用。

## ✨ 与 Pagey.site 的对比

本项目参考了 Pagey.site 的核心理念——"拖拽上传，即刻上线"，并针对**内网 / 私有部署**场景做了适配：

| 能力 | Pagey.site | 本项目 |
|------|-----------|--------|
| HTML / ZIP 上传部署 | ✅ | ✅ |
| 即时生成预览链接 | ✅ | ✅ |
| 密码保护 | ✅ | ✅ |
| 过期时间 | ✅ | ✅ |
| 自定义链接 | ✅（自定义子域名） | ✅（自定义路径 ID） |
| 多用户管理 | ✅（SaaS 账号体系） | ✅（自建用户 + 管理员） |
| 访问统计 | ✅（付费版详细分析） | ✅（访问次数统计） |
| 二维码分享 | ❌ | ✅ |
| 项目下载 | ✅ | ✅ |
| 私有部署 | ❌（SaaS 服务） | ✅（Docker 一键部署） |
| 版本历史 | ✅ | ❌ |
| AI 建站 | ✅ | ❌ |
| 数据分析面板 | ✅ | ❌ |

**简单来说：** 如果你需要一个在公司内网或个人服务器上运行的轻量 HTML 托管工具，不想把文件传到第三方平台，这个项目就是为你准备的。

## 🚀 功能特性

- **拖拽上传** — 支持 `.html` 单文件或 `.zip` 压缩包，拖进去就完事
- **即时预览链接** — 上传即得 `http://IP:PORT/p/xxxxx` 短链接，直接发给同事
- **多页项目** — ZIP 自动解压，页面间相对路径跳转正常可用
- **密码保护** — 可为项目单独设置访问密码，分享时更安全
- **过期时间** — 到期自动失效，适合临时演示场景
- **自定义链接** — 修改项目 ID 为有意义的路径，如 `/p/my-demo`
- **二维码生成** — 手机扫码直接预览，展示场景超方便
- **访问统计** — 记录每个项目的访问次数
- **用户体系** — 用户注册登录 + 管理员全局管理
- **认证限速** — 防暴力破解，5 分钟内最多 10 次失败尝试
- **Docker 部署** — 一行命令启动，数据持久化

## 📦 快速开始

### Docker 部署（推荐）

**方式一：docker run**

```bash
# 构建镜像
docker build -t html-preview-server .

# 启动
docker run -d \
  --name html-preview \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /your/host/path/data:/app/data \
  -e ADMIN_PASSWORD=your_secure_password \
  html-preview-server
```

> 💡 `-v` 挂载数据目录，数据库、项目文件、Session 密钥全部持久化，容器重建数据不丢。

**方式二：docker-compose**

```bash
# 编辑 .env 中的 ADMIN_PASSWORD
docker-compose up -d --build
```

### Windows 本地运行

双击 `startup.bat`，首次运行自动创建虚拟环境并安装依赖。

### 手动运行

```bash
pip install -r requirements.txt
python main.py
```

## ⚙️ 配置项

通过 `.env` 文件或环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | `admin123` | 管理员密码（**生产环境务必修改**） |
| `PORT` | `8080` | 服务端口 |
| `MAX_UPLOAD_SIZE` | `50` | 上传大小限制（MB） |
| `MAX_EXTRACT_SIZE` | `200` | ZIP 解压大小限制（MB） |

## 📖 使用说明

### 用户登录

1. 打开页面，输入用户名
2. 首次使用设置密码，再次使用密码登录
3. 管理员通过「管理员登录」使用管理密码，可查看和管理所有用户项目

### 上传项目

- **单页演示** — 直接上传 `.html` 文件
- **多页项目** — 打包为 `.zip` 上传（根目录或一级子目录下需有 `index.html`）

### 管理项目

| 操作 | 说明 |
|------|------|
| 复制链接 | 一键复制预览链接 |
| 二维码 | 生成预览链接二维码 |
| 下载项目 | 打包为 ZIP 下载 |
| 编辑 | 修改名称、自定义链接、设置密码、设置过期时间 |
| 删除 | 彻底删除项目和文件 |

## 🏗️ 项目结构

```
html-preview-server/
├── main.py              # FastAPI 入口与路由
├── database.py          # SQLite 数据库操作
├── config.py            # 配置管理
├── templates/
│   └── index.html       # 前端页面（Bootstrap 5）
├── static/              # 静态资源
├── Dockerfile
├── docker-compose.yml
├── startup.bat          # Windows 一键启动
├── requirements.txt
└── data/                # 数据目录（自动创建）
    ├── meta.db          # SQLite 数据库
    ├── .session_secret  # Session 密钥
    └── projects/        # 上传文件存储
```

## 🛠️ 技术栈

- **后端：** Python + FastAPI + aiosqlite
- **数据库：** SQLite（零配置，单文件）
- **前端：** Bootstrap 5 + 原生 JavaScript
- **部署：** Docker / docker-compose

## 📄 License

MIT
