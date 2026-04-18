import hashlib
import os
import secrets as _secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
DB_PATH = DATA_DIR / "meta.db"

# 服务配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# 管理密码（通过环境变量或 .env 设置）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# 管理员 Token（不暴露原始密码到 Cookie）
ADMIN_TOKEN = hashlib.sha256(f"admin-token:{ADMIN_PASSWORD}".encode()).hexdigest()

# 上传限制
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "50")) * 1024 * 1024  # 默认50MB

# ZIP 解压大小限制
MAX_EXTRACT_SIZE = int(os.getenv("MAX_EXTRACT_SIZE", "200")) * 1024 * 1024  # 默认200MB


# 持久化 Session 密钥（重启不会失效）
def _get_session_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = DATA_DIR / ".session_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    secret = _secrets.token_hex(32)
    secret_path.write_text(secret, encoding="utf-8")
    return secret


SESSION_SECRET = _get_session_secret()

# 确保目录存在
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
