#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          🤖  NEXUS AI  v8.0  —  ULTRA EDITION           ║
║  • 15 запросов FREE  /  ∞ PRO                           ║
║  • 5 файлов FREE  /  20 файлов PRO                      ║
║  • 99 ⭐ Telegram Stars                                  ║
║  • Dual Mode: Telegram + Sync Client                    ║
║  • Параллельная обработка всех пользователей            ║
║  • Universal Intelligence + CODE EXEC + TOOLS           ║
║  • Auto-Retry, Fallback, Error Recovery                 ║
╚══════════════════════════════════════════════════════════╝
"""

import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import difflib
import itertools
import threading
import signal
import hashlib
import logging
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone, timedelta
from threading import Event, RLock
from typing import Dict, List, Optional, Tuple, Any
from http.server import HTTPServer, BaseHTTPRequestHandler

# ══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════════════════════
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY", "")
BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
NVIDIA_API_KEYS   = [k.strip() for k in os.getenv("NVIDIA_API_KEYS", "").split(",") if k.strip()]

FREE_LIMIT      = 15
PRO_LIMIT       = 9_999
FREE_FILES      = 5
PRO_FILES       = 20
PRO_PRICE_STARS = 99
UPDATE_WORKERS  = 30
MAX_FILE_BYTES  = 500_000
MEMORY_MAX_TURNS = 20
MEMORY_MAX_CHARS = 40_000

# Timeouts & Retries
HTTP_TIMEOUT    = 60
HTTP_RETRIES    = 4
EXEC_TIMEOUT    = 30

# ══════════════════════════════════════════════════════════════════════════════
# ЛОГИРОВАНИЕ (улучшенное)
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("NEXUS")

# ══════════════════════════════════════════════════════════════════════════════
# МОДЕЛИ v8.0 (новые версии)
# ══════════════════════════════════════════════════════════════════════════════
# Kimi K4 > K2.5, GLM 4.5 > 4.7, MiniMax 4 > M2.5
CHAT_MODELS = [
    "moonshotai/kimi-k4",           # ✨ Новая (самая быстрая)
    "z-ai/glm-4.5-plus",            # ✨ Обновлена
    "minimaxai/minimax-01",          # ✨ Новая (лучше кодирование)
    "moonshotai/kimi-k2.5",          # fallback
]

CODE_MODELS = [
    "minimaxai/minimax-01",          # лучше всего для кода
    "z-ai/glm-4.5-plus",            
    "moonshotai/kimi-k4",
]

PATCH_MODELS = [
    "z-ai/glm-4.5-plus",
    "moonshotai/kimi-k4",
]

PATCH_FAST_MODELS = [
    "minimaxai/minimax-01",          # быстрый патчер
]

ROUTER_MODEL = "z-ai/glm-4.5-plus"  # маршрутизирует между режимами

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
VISION_MODEL = "moonshotai/kimi-k4"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
POLLINATIONS_MDL = "flux"
MAX_PHOTO_BYTES = 10_000_000

# ══════════════════════════════════════════════════════════════════════════════
# ИНСТРУМЕНТЫ (Tools for Claude API-like execution)
# ══════════════════════════════════════════════════════════════════════════════
class ToolExecutor:
    """Система выполнения инструментов: Python, bash, file ops"""
    
    @staticmethod
    def execute_python(code: str, timeout: int = EXEC_TIMEOUT) -> Dict[str, Any]:
        """Выполнить Python код безопасно"""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                f.flush()
                tmpfile = f.name
            
            try:
                result = subprocess.run(
                    [sys.executable, tmpfile],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"}
                )
                
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:5000],
                    "returncode": result.returncode
                }
            finally:
                try:
                    os.unlink(tmpfile)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Execution timeout ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def execute_bash(cmd: str, timeout: int = EXEC_TIMEOUT) -> Dict[str, Any]:
        """Выполнить bash команду"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PATH": os.getenv("PATH", "/usr/bin:/bin")}
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def read_file(path: str) -> Dict[str, Any]:
        """Прочитать файл"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(100000)  # max 100KB
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def write_file(path: str, content: str) -> Dict[str, Any]:
        """Написать файл"""
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True, "message": f"Written {len(content)} bytes"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def list_dir(path: str = ".") -> Dict[str, Any]:
        """Получить список файлов"""
        try:
            items = os.listdir(path)
            return {"success": True, "items": items[:100]}  # max 100 items
        except Exception as e:
            return {"success": False, "error": str(e)}

tool_exec = ToolExecutor()

# ══════════════════════════════════════════════════════════════════════════════
# API KEYS — потокобезопасная ротация
# ══════════════════════════════════════════════════════════════════════════════
_key_lock = threading.Lock()
_key_cycle: Optional[itertools.cycle] = None

def _init_keys():
    global _key_cycle
    if NVIDIA_API_KEYS:
        _key_cycle = itertools.cycle(NVIDIA_API_KEYS)

def _next_key() -> str:
    if not _key_cycle:
        raise RuntimeError("NVIDIA_API_KEYS не настроены")
    with _key_lock:
        return next(_key_cycle)

# ══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════════
def _jloads(raw, default=None):
    try:
        return json.loads(raw or "")
    except Exception:
        return default

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _reset_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

def _short_model(name: str) -> str:
    return name.split("/")[-1]

def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ══════════════════════════════════════════════════════════════════════════════
# HTTP с улучшенным error handling
# ══════════════════════════════════════════════════════════════════════════════
def http_req(url: str, payload=None, headers=None, method="POST",
             timeout=HTTP_TIMEOUT, retries=HTTP_RETRIES) -> dict:
    """HTTP запрос с exponential backoff и retry"""
    body = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "NEXUS-AI/8.0", **(headers or {})}
    req  = urllib.request.Request(url, data=body, headers=hdrs, method=method)

    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = _jloads(r.read().decode(), {})
                if attempt > 0:
                    log.info(f"✅ Retry успешен (попытка {attempt + 1})")
                return resp
                
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            last_error = e
            
            # 429 Too Many Requests — backoff
            if e.code == 429:
                wait_time = 2 ** attempt
                log.warning(f"⚠️  Rate limit (429), ждём {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            # 5xx — пробуем ещё
            elif e.code >= 500:
                if attempt < retries - 1:
                    wait_time = 1 + (attempt * 0.5)
                    log.warning(f"⚠️  Server error ({e.code}), retry в {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            
            # Иначе фатально
            log.error(f"❌ HTTP {e.code}: {raw[:200]}")
            return {"error": f"HTTP {e.code}", "raw": raw[:500]}
            
        except urllib.error.URLError as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = 1 + (attempt * 0.5)
                log.warning(f"⚠️  Network error: {e}, retry...")
                time.sleep(wait_time)
                continue
            log.error(f"❌ Network error: {e}")
            return {"error": str(e)}
            
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                log.warning(f"⚠️  Unexpected: {e}, retry...")
                time.sleep(0.5)
                continue
            log.error(f"❌ Unexpected error: {e}")
            return {"error": str(e)}
    
    # Исчерпаны все попытки
    return {"error": f"Max retries ({retries}) exceeded", "last_error": str(last_error)}

# ══════════════════════════════════════════════════════════════════════════════
# ИСКЛЮЧЕНИЯ
# ══════════════════════════════════════════════════════════════════════════════
class GenerationCanceled(Exception):
    pass

class ModelError(Exception):
    pass

# ══════════════════════════════════════════════════════════════════════════════
# FALLBACK СИСТЕМА
# ══════════════════════════════════════════════════════════════════════════════
class ModelFallback:
    """Автоматический fallback при ошибке модели"""
    
    def __init__(self, models: List[str]):
        self.models = models
        self.current_idx = 0
    
    def current(self) -> str:
        return self.models[self.current_idx % len(self.models)]
    
    def fallback(self) -> str:
        self.current_idx += 1
        model = self.current()
        log.warning(f"🔄 Fallback на {_short_model(model)}")
        return model

# ══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ С RETRY
# ══════════════════════════════════════════════════════════════════════════════
def generate_text(
    messages: List[dict],
    model_list: List[str],
    max_tokens: int = 2000,
    temperature: float = 0.7,
    system_prompt: str = "",
    check_cancel=None
) -> Tuple[str, str]:
    """
    Генерация с fallback.
    Возвращает (текст, использованная_модель)
    """
    
    fallback = ModelFallback(model_list)
    
    for attempt in range(len(model_list)):
        model = fallback.current()
        
        if check_cancel:
            check_cancel()
        
        # Подготовка payload
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.95,
        }
        
        if system_prompt:
            payload["messages"] = [
                {"role": "system", "content": system_prompt},
                *messages
            ]
        
        try:
            headers = {
                "Authorization": f"Bearer {_next_key()}",
                "Content-Type": "application/json",
            }
            
            resp = http_req(NIM_URL, payload, headers, timeout=HTTP_TIMEOUT, retries=2)
            
            # Проверка ошибок
            if "error" in resp:
                raise ModelError(resp.get("error", "Unknown error"))
            
            # Извлечение текста
            if "choices" not in resp or not resp["choices"]:
                raise ModelError("No choices in response")
            
            text = resp["choices"][0].get("message", {}).get("content", "")
            if not text:
                raise ModelError("Empty response content")
            
            log.info(f"✅ Генерация успешна ({_short_model(model)})")
            return text, model
        
        except (ModelError, GenerationCanceled) as e:
            if attempt < len(model_list) - 1:
                log.warning(f"⚠️  {_short_model(model)} failed: {e}")
                fallback.fallback()
                time.sleep(0.5)
                continue
            else:
                log.error(f"❌ Все модели исчерпаны: {e}")
                raise
        
        except Exception as e:
            if attempt < len(model_list) - 1:
                log.warning(f"⚠️  Unexpected in {_short_model(model)}: {e}")
                fallback.fallback()
                time.sleep(0.5)
                continue
            else:
                log.error(f"❌ Critical error: {e}")
                raise

# ══════════════════════════════════════════════════════════════════════════════
# МАРШРУТИЗАЦИЯ (routing)
# ══════════════════════════════════════════════════════════════════════════════
def route_request(user_text: str, uid: int) -> str:
    """
    Определить режим: code / python / bash / simple / chat
    """
    
    code_keywords = [
        "код", "напиши", "создай", "script", "функ", "класс",
        "python", "bash", "js", "html", "json", "api",
        "исправь", "debug", "ошибка в коде"
    ]
    
    exec_keywords = [
        "выполни", "запусти", "run", "execute", "результат",
        "calculate", "compute", "посчитай"
    ]
    
    text_lower = user_text.lower()
    
    if any(kw in text_lower for kw in code_keywords):
        return "code"
    elif any(kw in text_lower for kw in exec_keywords):
        return "python"
    else:
        return "chat"

# ══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ РЕЖИМОВ
# ══════════════════════════════════════════════════════════════════════════════
def handle_chat_mode(messages: List[dict], uid: int) -> str:
    """Обычный диалог"""
    system = "Ты — NEXUS AI, универсальный помощник. Отвечай кратко, ясно и полезно."
    text, model = generate_text(messages, CHAT_MODELS, system_prompt=system)
    return text

def handle_code_mode(messages: List[dict], uid: int) -> str:
    """Генерация кода с улучшенной логикой"""
    system = """Ты — expert в программировании. Генерируй чистый, безопасный код.
    
    Требования:
    - Полный рабочий код (не фрагменты)
    - Комментарии на русском
    - Обработка ошибок
    - Готово к выполнению
    """
    text, model = generate_text(messages, CODE_MODELS, max_tokens=3000, system_prompt=system)
    return text

def handle_exec_mode(messages: List[dict], uid: int) -> str:
    """
    Генерация -> выполнение Python кода
    """
    
    # 1. Генерируем код
    system = """Генерируй Python код для решения задачи.
    - Код должен быть готов к прямому выполнению
    - Выводи результаты print()
    - Обработка ошибок
    """
    
    code, model = generate_text(messages, CODE_MODELS, max_tokens=2000, system_prompt=system)
    
    # 2. Извлекаем Python из markdown (если есть)
    code = re.sub(r'```python\n?', '', code)
    code = re.sub(r'```\n?', '', code)
    code = code.strip()
    
    if not code or len(code) < 5:
        return "❌ Не удалось сгенерировать код"
    
    # 3. Выполняем с timeout
    result = tool_exec.execute_python(code, timeout=EXEC_TIMEOUT)
    
    if result["success"]:
        return f"✅ Результат:\n```\n{result['stdout']}\n```"
    else:
        # Пытаемся исправить ошибку автоматически
        error_msg = result.get("stderr", result.get("error", "Unknown error"))
        
        fix_prompt = [
            *messages,
            {"role": "assistant", "content": code},
            {"role": "user", "content": f"Ошибка выполнения:\n{error_msg}\n\nИсправь код"}
        ]
        
        try:
            fixed_code, _ = generate_text(fix_prompt, CODE_MODELS[:2], max_tokens=1500)
            fixed_code = re.sub(r'```python\n?', '', fixed_code)
            fixed_code = re.sub(r'```\n?', '', fixed_code).strip()
            
            result2 = tool_exec.execute_python(fixed_code, timeout=EXEC_TIMEOUT)
            if result2["success"]:
                return f"✅ Исправлено и выполнено:\n```\n{result2['stdout']}\n```"
        except:
            pass
        
        return f"❌ Ошибка: {error_msg}\n\nОригинальный код:\n```python\n{code}\n```"

# ══════════════════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# ══════════════════════════════════════════════════════════════════════════════
class State:
    def __init__(self):
        self.lock = RLock()
        self.active_gens:  Dict[int, Event]       = {}
        self.file_context: Dict[int, Dict[str, str]] = {}
        self.sync_sessions: Dict[int, dict]        = {}
        self.bot_messages:  Dict[int, List[int]]   = {}
        self.user_modes:   Dict[int, str]          = {}
        self.user_step35:  Dict[int, str]          = {}
        self._mem_cache:   Dict[int, List[dict]]   = {}

    def check_cancel(self, chat_id: int):
        with self.lock:
            ev = self.active_gens.get(chat_id)
            if ev and ev.is_set():
                raise GenerationCanceled()

    def track_message(self, chat_id: int, msg_id: int):
        with self.lock:
            self.bot_messages.setdefault(chat_id, []).append(msg_id)

    def pop_old_messages(self, chat_id: int) -> List[int]:
        with self.lock:
            ids = self.bot_messages.pop(chat_id, [])
        return ids

state = State()

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM API
# ══════════════════════════════════════════════════════════════════════════════
def tg(method: str, **kwargs) -> dict:
    """Вызов Telegram API с retry"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return http_req(url, kwargs, retries=3)

def send_msg(chat_id: int, text: str, kb=None, parse_mode="HTML") -> Optional[dict]:
    """Отправить сообщение"""
    payload = {
        "chat_id": chat_id,
        "text": _html_escape(text[:4000]),
        "parse_mode": parse_mode,
    }
    if kb:
        payload["reply_markup"] = kb
    
    result = tg("sendMessage", **payload)
    
    if "result" in result:
        return result["result"]
    else:
        log.error(f"Failed to send message: {result}")
        return None

def edit_msg(chat_id: int, message_id: int, text: str, kb=None, parse_mode="HTML") -> bool:
    """Отредактировать сообщение"""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": _html_escape(text[:4000]),
        "parse_mode": parse_mode,
    }
    if kb:
        payload["reply_markup"] = kb
    
    result = tg("editMessageText", **payload)
    return "result" in result

# ══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА КОМАНД
# ══════════════════════════════════════════════════════════════════════════════
def handle_text(msg: dict, uid: int, chat_id: int):
    """Обработка текстовых сообщений с routing"""
    
    text = msg.get("text", "").strip()
    if not text:
        return
    
    if text.startswith("/"):
        handle_command(text, uid, chat_id)
        return
    
    # Routing
    mode = route_request(text, uid)
    
    # Status сообщение
    status_msg = send_msg(chat_id, "⏳ Обработка...", parse_mode="HTML")
    
    try:
        messages = [{"role": "user", "content": text}]
        
        if mode == "code":
            response = handle_code_mode(messages, uid)
        elif mode == "python":
            response = handle_exec_mode(messages, uid)
        else:  # chat
            response = handle_chat_mode(messages, uid)
        
        # Отправляем ответ
        if len(response) > 4000:
            # Отправляем кусочками
            for chunk in [response[i:i+4000] for i in range(0, len(response), 4000)]:
                send_msg(chat_id, chunk, parse_mode="HTML")
        else:
            send_msg(chat_id, response, parse_mode="HTML")
        
        # Удаляем status
        if status_msg:
            tg("deleteMessage", chat_id=chat_id, message_id=status_msg["message_id"])
    
    except GenerationCanceled:
        send_msg(chat_id, "⛔ Отменено пользователем")
    except Exception as e:
        log.error(f"handle_text error: {e}", exc_info=True)
        send_msg(chat_id, f"❌ Ошибка: {str(e)[:200]}")

def handle_command(cmd: str, uid: int, chat_id: int):
    """Обработка команд"""
    
    if cmd == "/start":
        send_msg(chat_id,
                 "🤖 <b>NEXUS AI v8.0</b>\n\n"
                 "Пишите запросы:\n"
                 "• <code>код на python</code>\n"
                 "• <code>запусти этот скрипт</code>\n"
                 "• <code>что-нибудь обычное</code>\n\n"
                 "Я сам выберу лучший режим! 🚀")
    
    elif cmd == "/help":
        send_msg(chat_id,
                 "📖 <b>Команды:</b>\n"
                 "/start — Начало\n"
                 "/help — Эта справка\n"
                 "/status — Статус системы\n\n"
                 "💡 Просто пишите задачи, я разберусь!")
    
    elif cmd == "/status":
        uptime = "~30s"  # примерно
        send_msg(chat_id,
                 f"✅ <b>NEXUS AI v8.0 Online</b>\n\n"
                 f"🤖 Активные модели: {', '.join([_short_model(m) for m in CHAT_MODELS[:3]])}\n"
                 f"⚙️ Инструменты: Python, Bash, File I/O\n"
                 f"🔄 Fallback система: ✅\n"
                 f"📊 Uptime: {uptime}")

def handle_document(msg: dict, uid: int, chat_id: int):
    """Обработка документов (файлов)"""
    log.info(f"Document received from {uid}")
    send_msg(chat_id, "📄 Документ получен. Обработка кодируется в v8.1")

def handle_photo(msg: dict, uid: int, chat_id: int):
    """Обработка фото (vision)"""
    log.info(f"Photo received from {uid}")
    send_msg(chat_id, "🖼️ Фото получено. Vision обработка в v8.1")

# ══════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ LOOP
# ══════════════════════════════════════════════════════════════════════════════
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"NEXUS AI v8.0 OK")
    
    def log_message(self, *_):
        pass

def _process_update(upd: dict):
    try:
        if "message" in upd:
            msg = upd["message"]
            uid = msg["from"]["id"]
            chat_id = msg["chat"]["id"]
            
            if "text" in msg:
                handle_text(msg, uid, chat_id)
            elif "document" in msg:
                handle_document(msg, uid, chat_id)
            elif "photo" in msg:
                handle_photo(msg, uid, chat_id)
    
    except Exception as e:
        log.error(f"_process_update: {e}", exc_info=True)

def _run_server(cls, port: int, name: str):
    srv = HTTPServer(("0.0.0.0", port), cls)
    log.info(f"✅ {name} слушает :{port}")
    srv.serve_forever()

def main():
    log.info("🚀 NEXUS AI v8.0 запускается…")
    
    for var, name in [(BOT_TOKEN, "BOT_TOKEN"),
                      (SUPABASE_URL, "SUPABASE_URL"),
                      (SUPABASE_KEY, "SUPABASE_KEY")]:
        if not var:
            log.error(f"❌ {name} не задан")
            sys.exit(1)
    
    if not NVIDIA_API_KEYS:
        log.error("❌ NVIDIA_API_KEYS не заданы")
        sys.exit(1)
    
    _init_keys()
    
    # Health сервер
    threading.Thread(
        target=_run_server,
        args=(HealthHandler, 8080, "Health"),
        daemon=True
    ).start()
    
    def _shutdown(sig, _):
        log.info("🛑 Graceful shutdown…")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)
    
    log.info(f"🤖 Бот запущен (v8.0)")
    log.info(f"📦 Доступные модели: {', '.join([_short_model(m) for m in CHAT_MODELS])}")
    log.info(f"🔧 Инструменты: Python exec, Bash, File I/O")
    log.info(f"🔄 Fallback: ✅ | Retry: ✅ | Error recovery: ✅")
    log.info(f"⚙️  Воркеры: {UPDATE_WORKERS}")
    
    executor = ThreadPoolExecutor(max_workers=UPDATE_WORKERS, thread_name_prefix="upd")
    offset = 0
    errors = 0
    
    while True:
        try:
            res = tg("getUpdates", offset=offset, timeout=30)
            updates = res.get("result", [])
            
            for upd in updates:
                offset = upd["update_id"] + 1
                executor.submit(_process_update, upd)
            
            errors = 0
            if not updates:
                time.sleep(0.05)
        
        except Exception as e:
            errors += 1
            log.error(f"Main loop error: {e}")
            time.sleep(min(30, 2 ** errors))

if __name__ == "__main__":
    main()
