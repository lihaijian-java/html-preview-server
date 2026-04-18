# HTML Preview Server

内网 HTML 演示文稿分享平台。上传单文件 HTML 或多页项目（ZIP），自动生成预览链接，直接发给同事即可访问。

## 功能特性

- **用户注册登录** - 首次使用设置密码，后续密码验证，防止冒充
- **拖拽上传** - 支持 `.html` 单文件或 `.zip` 压缩包
- **自动生成链接** - 上传即得 `http://IP:PORT/p/xxxxx` 短链接
- **多页项目支持** - ZIP 自动解压，页面间相对路径跳转自然可用
- **密码保护** - 用户登录密码 + 单项目可选访问密码
- **二维码生成** - 手机扫码直接预览
- **访问统计** - 记录每个项目的访问次数
- **过期时间** - 可为项目设置自动过期
- **自定义链接** - 可修改项目链接 ID，如 `/p/my-demo`
- **Docker 部署** - 一行命令启动，数据持久化

## 快速开始

### Docker 部署（推荐）

**方式一：docker run**

```bash
# 构建镜像
docker build -t html-preview-server .

# 启动（挂载 data 目录到宿主机，数据持久化）
docker run -d \
  --name html-preview \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /your/host/path/data:/app/data \
  -e ADMIN_PASSWORD=your_secure_password \
  html-preview-server
```

> `-v` 将容器内的数据目录挂载到宿主机，数据库、项目文件、Session 密钥全部持久化，容器删除重建数据不丢失。将 `/your/host/path/data` 替换为实际的宿主机路径。

需要自定义更多参数时：

```bash
docker run -d \
  --name html-preview \
  --restart unless-stopped \
  -p 9090:8080 \
  -v /your/host/path/data:/app/data \
  -e ADMIN_PASSWORD=your_secure_password \
  -e MAX_UPLOAD_SIZE=50 \
  -e MAX_EXTRACT_SIZE=200 \
  html-preview-server
```

**方式二：docker-compose**

```bash
# 修改管理密码
# 编辑 .env 文件中的 ADMIN_PASSWORD

# 启动
docker-compose up -d --build
```

> docker-compose 已配置 `./data:/app/data` 挂载，数据自动持久化到项目目录下的 `data/` 文件夹。

### Windows 本地运行

双击 `startup.bat`，首次运行会自动创建虚拟环境并安装依赖。

### 手动运行

```bash
# 安装依赖
pip install -r requirements.txt

# 修改密码（可选）
# 编辑 .env 文件中的 ADMIN_PASSWORD

# 启动
python main.py
```

## 配置项

通过 `.env` 文件或环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | `admin123` | 管理员登录密码（生产环境务必修改） |
| `PORT` | `8080` | 服务端口 |
| `MAX_UPLOAD_SIZE` | `50` | 上传大小限制（MB） |
| `MAX_EXTRACT_SIZE` | `200` | ZIP 解压大小限制（MB） |

## 使用说明

### 用户登录

1. 打开页面，输入用户名
2. 首次使用：设置密码并确认，进入工作区
3. 再次使用：输入密码登录
4. 顶栏可修改密码、切换用户、退出

管理员通过「管理员登录」按钮使用管理密码登录，可查看和管理所有用户的项目。

### 上传项目

1. 登录工作区
2. 拖拽或点击上传区域选择文件
   - 单页演示：直接上传 `.html` 文件
   - 多页项目：将所有文件打包为 `.zip` 上传（确保根目录或一级子目录下有 `index.html`）

### 管理项目

每个项目支持以下操作：

- **复制链接** - 一键复制预览链接
- **二维码** - 生成预览链接二维码
- **下载项目** - 将项目打包为 ZIP 下载
- **编辑** - 修改名称、自定义链接 ID、设置/移除访问密码、设置过期时间
- **删除** - 彻底删除项目和文件

### 带密码的项目

为项目设置密码后，访问者打开链接会看到密码输入页，输入正确密码后才能查看。

## 项目结构

```
html-preview-server/
├── main.py                # FastAPI 入口与路由
├── database.py            # SQLite 数据库操作
├── config.py              # 配置管理
├── templates/
│   └── index.html         # 前端页面
├── static/                # 静态资源（Bootstrap）
├── Dockerfile
├── docker-compose.yml
├── startup.bat            # Windows 一键启动
├── requirements.txt
├── .env                   # 环境变量配置
└── data/                  # 数据目录（自动创建，需挂载持久化）
    ├── meta.db            # SQLite 数据库
    ├── .session_secret    # Session 密钥
    └── projects/          # 上传文件存储
```

## 技术栈

- **后端**: Python + FastAPI
- **数据库**: SQLite（零配置）
- **前端**: Bootstrap 5 + 原生 JS
- **部署**: Docker / docker-compose

## License

MIT
