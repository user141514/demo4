"""
配置管理 — 优先级：mykey.py > .env > 环境变量 > 默认值
借鉴 demo2 llm_config.py 设计，兼容旧代码模块级常量访问
"""
import importlib.util
import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY_FILE = Path(os.getenv("LM_KEY_FILE", str(PROJECT_ROOT / "mykey.py")))

# ── 默认值 ─────────────────────────────────────────────────

DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"
LLM_TIMEOUT = 120

# Upload limits
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "doc", "md"}

# ── 加载逻辑 ─────────────────────────────────────────────


def _load_mykey(path):
    """从 mykey.py 动态加载配置"""
    if not path.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("mykey_config", str(path))
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # demo2 风格：llm_config dict
        if hasattr(module, "llm_config") and isinstance(module.llm_config, dict):
            return module.llm_config
        # demo4 当前风格：DEEPSEEK_API_KEY 字符串
        if hasattr(module, "DEEPSEEK_API_KEY"):
            return {"openai_api_key": getattr(module, "DEEPSEEK_API_KEY")}
    except Exception:
        pass
    return {}


def _load_dotenv(path):
    """从 .env 文件加载配置"""
    if not path.exists():
        return {}
    mapping = {
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_BASE_URL": "openai_base_url",
        "LM_LLM_TIMEOUT": "llm_timeout_seconds",
    }
    config = {}
    try:
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            setting_key = mapping.get(key)
            if not setting_key:
                continue
            value = value.strip().strip('"').strip("'")
            if value:
                config[setting_key] = value
    except Exception:
        pass
    return config


@lru_cache(maxsize=1)
def load_settings():
    """加载所有配置（缓存结果）"""
    settings = {
        "openai_api_key": "",
        "openai_base_url": "https://api.deepseek.com",
        "openai_chat_model": "deepseek-chat",
        "openai_reasoner_model": "deepseek-reasoner",
        "llm_timeout_seconds": 120,
        "llm_mode": "live",
    }
    settings.update(_load_mykey(DEFAULT_KEY_FILE))
    settings.update(_load_dotenv(PROJECT_ROOT / ".env"))

    # 环境变量覆盖
    for env_key, setting_key in [
        ("OPENAI_API_KEY", "openai_api_key"),
        ("OPENAI_BASE_URL", "openai_base_url"),
    ]:
        val = os.getenv(env_key, "").strip()
        if val:
            settings[setting_key] = val

    settings["openai_base_url"] = settings["openai_base_url"].rstrip("/")
    return settings


def _refresh_module_globals():
    """将加载的配置同步到模块级常量"""
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL, DEEPSEEK_REASONER_MODEL, LLM_TIMEOUT
    s = load_settings()
    DEEPSEEK_API_KEY = s.get("openai_api_key", "")
    DEEPSEEK_BASE_URL = s.get("openai_base_url", "https://api.deepseek.com")
    DEEPSEEK_CHAT_MODEL = s.get("openai_chat_model", "deepseek-chat")
    DEEPSEEK_REASONER_MODEL = s.get("openai_reasoner_model", "deepseek-reasoner")
    LLM_TIMEOUT = int(s.get("llm_timeout_seconds", 120))


# 启动时自动加载
_refresh_module_globals()
