import hashlib
import io
import re
import shutil
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import qrcode
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware

import database
from config import ADMIN_PASSWORD, PORT, HOST, MAX_UPLOAD_SIZE, PROJECTS_DIR, SESSION_SECRET
from config import ADMIN_TOKEN, MAX_EXTRACT_SIZE, WPSJS_DIR

# WPSJS 静态目录挂载
app.mount("/wpsjs", StaticFiles(directory=WPSJS_DIR, html=True), name="wpsjs")

templates_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
IGNORED_ZIP_NAMES = {"__MACOSX", ".DS_Store", "Thumbs.db"}

PW_MAX_LEN = 128

# ── 认证限速 ────────────────────────────────────────────
_auth_failures: dict[str, list[float]] = {}
AUTH_RATE_LIMIT = 10       # 最大失败次数
AUTH_RATE_WINDOW = 300     # 5 分钟窗口


def _get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_auth_rate_limit(ip: str):
    now = time.time()
    attempts = _auth_failures.get(ip, [])
    recent = [t for t in attempts if now - t < AUTH_RATE_WINDOW]
    _auth_failures[ip] = recent
    if len(recent) >= AUTH_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")


def _record_auth_failure(ip: str):
    _auth_failures.setdefault(ip, []).append(time.time())


def _clear_auth_failures(ip: str):
    _auth_failures.pop(ip, None)


@asynccontextmanager
async def lifespan(app):
    await database.init_db()
    yield

app = FastAPI(title="HTML Preview Server", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# ── 工具函数 ──────────────────────────────────────────────

def generate_id(length: int = 6) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(chars) for _ in range(length))


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return dk.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    computed, _ = _hash_password(password, salt)
    return secrets.compare_digest(computed, stored_hash)


def _hash_project_pw(password: str) -> str:
    return hashlib.sha256(f"project-pw:{password}".encode()).hexdigest()


def get_username(request: Request) -> str | None:
    """从 Session 获取当前用户名"""
    return request.session.get("user")


def is_admin(request: Request) -> bool:
    """判断是否管理员"""
    return request.cookies.get("auth_token") == ADMIN_TOKEN


def get_identity(request: Request) -> tuple[str | None, bool]:
    """返回 (username, is_admin)"""
    admin = is_admin(request)
    user = get_username(request)
    return user, admin


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def validate_project_id(project_id: str) -> str:
    project_id = project_id.strip().lower()
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="链接 ID 需为 3-64 位小写字母、数字或中划线")
    return project_id


async def generate_unique_id(length: int = 6) -> str:
    for _ in range(20):
        project_id = generate_id(length)
        if not await database.get_project(project_id) and not project_dir(project_id).exists():
            return project_id
    raise HTTPException(status_code=500, detail="生成项目 ID 失败，请重试")


def is_ignored_zip_member(name: str) -> bool:
    parts = [p for p in Path(name).parts if p not in ("", ".")]
    return not parts or any(part.startswith(".") or part in IGNORED_ZIP_NAMES for part in parts)


def safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> list[str]:
    dest_resolved = dest.resolve()
    extracted: list[str] = []
    total_size = 0

    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if is_ignored_zip_member(name):
            continue

        target = dest / name
        try:
            target.resolve().relative_to(dest_resolved)
        except ValueError:
            raise HTTPException(status_code=400, detail="ZIP 中包含不安全路径")

        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        total_size += info.file_size
        if total_size > MAX_EXTRACT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"ZIP 解压后超过大小限制 ({MAX_EXTRACT_SIZE // 1024 // 1024}MB)"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        extracted.append(name)

    if not extracted:
        raise HTTPException(status_code=400, detail="ZIP 文件为空")
    return extracted


def flatten_single_root_dir(pdir: Path):
    items = [p for p in pdir.iterdir() if p.name not in IGNORED_ZIP_NAMES and not p.name.startswith(".")]
    if len(items) != 1 or not items[0].is_dir():
        return

    inner_dir = items[0]
    for item in inner_dir.iterdir():
        shutil.move(str(item), str(pdir / item.name))
    inner_dir.rmdir()


def get_project_stats(pdir: Path) -> tuple[int, int]:
    files = [p for p in pdir.rglob("*") if p.is_file()]
    total_size = sum(p.stat().st_size for p in files)
    return len(files), total_size


def find_entry_file(pdir: Path, require_index: bool = False) -> str | None:
    candidates = [p for p in pdir.rglob("*") if p.is_file() and p.suffix.lower() in {".html", ".htm"}]
    if not candidates:
        return None

    root_index = pdir / "index.html"
    if root_index.exists():
        return "index.html"

    root_index_htm = pdir / "index.htm"
    if root_index_htm.exists():
        return "index.htm"

    index_files = [p for p in candidates if p.name.lower() in {"index.html", "index.htm"}]
    if require_index and not index_files:
        return None

    entry = sorted(index_files or candidates, key=lambda p: (len(p.parts), str(p).lower()))[0]
    return entry.relative_to(pdir).as_posix()


# ── 页面路由 ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    username, admin = get_identity(request)
    tmpl = templates_env.get_template("index.html")
    return tmpl.render(
        authenticated=bool(username or admin),
        username=username,
        is_admin=admin,
    )


# ── 健康检查 ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── 认证 API ──────────────────────────────────────────────

@app.get("/api/check-user")
async def check_user(username: str):
    """检查用户名是否已注册"""
    name = username.strip()
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    exists = await database.user_exists(name)
    return {"exists": exists}


@app.post("/api/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...)):
    """新用户注册：设置用户名和密码"""
    ip = _get_client_ip(request)
    _check_auth_rate_limit(ip)

    name = username.strip()
    pw = password
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(name) > 20:
        raise HTTPException(status_code=400, detail="用户名最多20个字符")
    if not pw or len(pw) < 4:
        raise HTTPException(status_code=400, detail="密码至少4个字符")
    if len(pw) > PW_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"密码最多{PW_MAX_LEN}个字符")

    if await database.user_exists(name):
        _record_auth_failure(ip)
        raise HTTPException(status_code=400, detail="用户名已被注册")

    pw_hash, salt = _hash_password(pw)
    await database.create_user(name, pw_hash, salt)
    _clear_auth_failures(ip)
    request.session["user"] = name
    return {"ok": True, "username": name}


@app.post("/api/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """已注册用户登录"""
    ip = _get_client_ip(request)
    _check_auth_rate_limit(ip)

    name = username.strip()
    pw = password
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not pw:
        raise HTTPException(status_code=400, detail="请输入密码")
    if len(pw) > PW_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"密码最多{PW_MAX_LEN}个字符")

    user = await database.get_user(name)
    if not user or not _verify_password(pw, user["password_hash"], user["salt"]):
        _record_auth_failure(ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    _clear_auth_failures(ip)
    request.session["user"] = name
    return {"ok": True, "username": name}


@app.post("/api/change-password")
async def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...)):
    """修改密码"""
    username = get_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")

    user = await database.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not _verify_password(old_password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="原密码错误")

    if not new_password or len(new_password) < 4:
        raise HTTPException(status_code=400, detail="新密码至少4个字符")
    if len(new_password) > PW_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"新密码最多{PW_MAX_LEN}个字符")

    pw_hash, salt = _hash_password(new_password)
    await database.update_user_password(username, pw_hash, salt)
    return {"ok": True}


@app.post("/api/auth")
async def auth(request: Request, password: str = Form(...)):
    """管理员登录"""
    ip = _get_client_ip(request)
    _check_auth_rate_limit(ip)

    if password != ADMIN_PASSWORD:
        _record_auth_failure(ip)
        raise HTTPException(status_code=401, detail="密码错误")
    _clear_auth_failures(ip)
    response = JSONResponse({"ok": True, "is_admin": True})
    response.set_cookie("auth_token", ADMIN_TOKEN, httponly=True, max_age=86400 * 30)
    return response


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    response = JSONResponse({"ok": True})
    response.delete_cookie("auth_token")
    return response


@app.get("/api/check-auth")
async def check_auth_api(request: Request):
    username, admin = get_identity(request)
    return {
        "authenticated": bool(username or admin),
        "username": username,
        "is_admin": admin,
    }


# ── 上传 API ──────────────────────────────────────────────

@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), name: str = Form(None)):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    # 检查文件大小
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"文件超过限制 ({MAX_UPLOAD_SIZE // 1024 // 1024}MB)")

    filename = Path(file.filename or "untitled.html").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".html", ".htm", ".zip"}:
        raise HTTPException(status_code=400, detail="仅支持 .html、.htm 或 .zip 文件")

    project_id = await generate_unique_id()
    pdir = project_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)

    display_name = (name or Path(filename).stem).strip()[:80] or "未命名项目"

    if suffix == ".zip":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            safe_extract_zip(zf, pdir)
            zf.close()
            flatten_single_root_dir(pdir)
        except zipfile.BadZipFile:
            shutil.rmtree(pdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="无效的 ZIP 文件")
        except HTTPException:
            shutil.rmtree(pdir, ignore_errors=True)
            raise
    else:
        dest = pdir / "index.html"
        with open(dest, "wb") as f:
            f.write(content)

    entry_file = find_entry_file(pdir, require_index=(suffix == ".zip"))
    if not entry_file:
        shutil.rmtree(pdir, ignore_errors=True)
        if suffix == ".zip":
            raise HTTPException(status_code=400, detail="ZIP 中必须包含 index.html 或 index.htm 作为入口文件")
        raise HTTPException(status_code=400, detail="未找到可预览的 HTML 文件")

    file_count, total_size = get_project_stats(pdir)

    owner = username if username else "管理员"  # 管理员无 username，设"管理员"
    project = await database.create_project(
        project_id,
        display_name,
        owner=owner,
        entry_file=entry_file,
        original_filename=filename,
        file_count=file_count,
        total_size=total_size,
    )
    return {"ok": True, "project": project}


# ── 项目管理 API ──────────────────────────────────────────

@app.get("/api/projects")
async def list_projects(request: Request):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    # 管理员看全部，普通用户只看自己的
    projects = await database.list_projects(owner=None if admin else username)

    now = datetime.now()
    for p in projects:
        if p["expires_at"]:
            try:
                exp = datetime.fromisoformat(p["expires_at"])
                p["expired"] = now > exp
            except ValueError:
                p["expired"] = False
        else:
            p["expired"] = False
    return projects


@app.put("/api/projects/{project_id}")
async def update_project(project_id: str, request: Request):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    # 权限检查：管理员可改任何项目，普通用户只能改自己的
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not admin and project.get("owner") != username:
        raise HTTPException(status_code=403, detail="无权操作")

    data = await request.json()

    # 处理项目密码：非空则哈希，空则不修改，clear_password 则清除
    raw_pw = data.pop("password", None)
    if raw_pw:
        data["password"] = _hash_project_pw(raw_pw)
    if data.pop("clear_password", False):
        data["password"] = ""

    new_id = data.get("id")
    if new_id:
        new_id = validate_project_id(new_id)
    if new_id and new_id != project_id:
        data["id"] = new_id
        old_dir = project_dir(project_id)
        new_dir_path = project_dir(new_id)
        if await database.get_project(new_id) or new_dir_path.exists():
            raise HTTPException(status_code=400, detail="链接ID已存在")
        if old_dir.exists():
            old_dir.rename(new_dir_path)

    result = await database.update_project(project_id, **data)
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"ok": True, "project": result}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not admin and project.get("owner") != username:
        raise HTTPException(status_code=403, detail="无权操作")

    success = await database.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="项目不存在")

    pdir = project_dir(project_id)
    if pdir.exists():
        shutil.rmtree(pdir)

    return {"ok": True}


# ── 二维码 API ────────────────────────────────────────────

@app.get("/api/qrcode/{project_id}")
async def qrcode_api(project_id: str, request: Request):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    host = request.headers.get("host", f"localhost:{PORT}")
    scheme = request.url.scheme
    preview_url = f"{scheme}://{host}/p/{project_id}"

    img = qrcode.make(preview_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


@app.get("/api/projects/{project_id}/download")
async def download_project(project_id: str, request: Request):
    username, admin = get_identity(request)
    if not username and not admin:
        raise HTTPException(status_code=401, detail="未授权")

    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not admin and project.get("owner") != username:
        raise HTTPException(status_code=403, detail="无权操作")

    pdir = project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="项目文件不存在")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in pdir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(pdir).as_posix())
    buf.seek(0)

    filename = re.sub(r"[^a-zA-Z0-9._-]+", "-", project["name"]).strip("-") or project_id
    headers = {"Content-Disposition": f'attachment; filename="{filename}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


# ── 预览路由 ──────────────────────────────────────────────

@app.get("/p/{project_id}", response_class=HTMLResponse)
async def preview(project_id: str, request: Request):
    project = await database.get_project(project_id)

    if not project:
        return HTMLResponse("<h1>404 - 项目不存在</h1>", status_code=404)

    if project["expires_at"]:
        try:
            exp = datetime.fromisoformat(project["expires_at"])
            if datetime.now() > exp:
                return HTMLResponse("<h1>此链接已过期</h1>", status_code=410)
        except ValueError:
            pass

    if project["password"]:
        proj_cookie = request.cookies.get(f"proj_{project_id}")
        if proj_cookie != project["password"]:
            tmpl = templates_env.get_template("index.html")
            return tmpl.render(
                need_project_password=True,
                project_id=project_id,
                project_name=project["name"]
            )

    await database.increment_visit(project_id)

    pdir = project_dir(project_id)
    entry_file = project.get("entry_file") or "index.html"
    entry_path = pdir / entry_file
    try:
        entry_path.resolve().relative_to(pdir.resolve())
    except ValueError:
        return HTMLResponse("<h1>项目入口文件无效</h1>", status_code=500)

    if entry_file != "index.html" and entry_path.exists():
        return RedirectResponse(url=f"/p/{project_id}/{entry_file}", status_code=302)

    if entry_path.exists():
        return FileResponse(entry_path, media_type="text/html")
    return HTMLResponse("<h1>404 - 入口 HTML 不存在</h1>", status_code=404)


@app.post("/p/{project_id}/auth")
async def project_auth(project_id: str, password: str = Form(...)):
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project["password"] or _hash_project_pw(password) != project["password"]:
        raise HTTPException(status_code=401, detail="密码错误")

    response = JSONResponse({"ok": True})
    response.set_cookie(f"proj_{project_id}", project["password"],
                        httponly=True, max_age=86400 * 30)
    return response


@app.get("/p/{project_id}/{file_path:path}")
async def serve_project_file(project_id: str, file_path: str, request: Request):
    """提供项目内的任意文件，使相对路径跳转自然可用"""
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404)

    if project["expires_at"]:
        try:
            if datetime.now() > datetime.fromisoformat(project["expires_at"]):
                raise HTTPException(status_code=410, detail="链接已过期")
        except ValueError:
            pass

    if project["password"]:
        proj_cookie = request.cookies.get(f"proj_{project_id}")
        if proj_cookie != project["password"]:
            raise HTTPException(status_code=401)

    pdir = project_dir(project_id)
    full_path = pdir / file_path
    try:
        full_path.resolve().relative_to(pdir.resolve())
    except ValueError:
        raise HTTPException(status_code=403)

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404)

    suffix = full_path.suffix.lower()
    mime_map = {
        ".html": "text/html", ".htm": "text/html",
        ".css": "text/css", ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".woff": "font/woff", ".woff2": "font/woff2",
        ".ttf": "font/ttf", ".eot": "application/vnd.ms-fontobject",
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".pdf": "application/pdf",
    }
    media_type = mime_map.get(suffix, "application/octet-stream")
    return FileResponse(full_path, media_type=media_type)


# ── 启动入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
