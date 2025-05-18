import os
import logging
import secrets
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# --- Configuration Loading ---
load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLOTHOFF_API_KEY = os.getenv("CLOTHOFF_API_KEY")
BASE_URL = os.getenv("BASE_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", '8080'))
# Генерируем секретный путь один раз при загрузке, если он не задан
WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH")
if not WEBHOOK_SECRET_PATH:
    WEBHOOK_SECRET_PATH = secrets.token_urlsafe(32)
    logger.warning(f"WEBHOOK_SECRET_PATH not set, generated: {WEBHOOK_SECRET_PATH}. "
                   f"Set this in your .env file for persistence across restarts.")
    # Опционально: можно записать сгенерированный путь обратно в .env,
    # но это требует дополнительных библиотек и усложняет логику.
    # Проще попросить пользователя добавить его вручную.

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
FIRESTORE_DB_NAME = os.getenv("FIRESTORE_DB_NAME", "undress-tg-bot-dev") # Имя БД тоже в конфиг

DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ru") # Язык по умолчанию для новых пользователей
SUPPORTED_LANGUAGES = ['en', 'ru']

CLOTHOFF_API_URL = "https://public-api.clothoff.net/undress"

# --- Calculate derived URLs ---
if BASE_URL:
    # Убираем / в конце, если он есть, перед добавлением путей
    base_ngrok_url = BASE_URL.rstrip('/')
    CLOTHOFF_RECEIVER_URL = f"{base_ngrok_url}/webhook"
    TELEGRAM_RECEIVER_URL = f"{base_ngrok_url}/{WEBHOOK_SECRET_PATH}"
else:
    CLOTHOFF_RECEIVER_URL = None
    TELEGRAM_RECEIVER_URL = None
    logger.error("NGROK_URL is not set in environment variables!")

# --- Validate Configuration ---
# Добавляем проверку GCP_PROJECT_ID и NGROK_URL
REQUIRED_VARS = {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "CLOTHOFF_API_KEY": CLOTHOFF_API_KEY,
    "NGROK_URL": BASE_URL,
    "GCP_PROJECT_ID": GCP_PROJECT_ID
}

missing_vars = [k for k, v in REQUIRED_VARS.items() if not v]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# --- Logging Configuration ---
# Вынесем настройку логгера сюда, чтобы она применялась раньше
def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    # Уменьшаем шум от библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("google.cloud.firestore").setLevel(logging.WARNING) # Уменьшаем логи Firestore
    logging.getLogger("google.api_core.bidi").setLevel(logging.WARNING) # И от его зависимостей
    logging.getLogger('google.auth.compute_engine._metadata').setLevel(logging.WARNING)

setup_logging() # Вызываем настройку при импорте модуля
logger.info("Configuration loaded.")
