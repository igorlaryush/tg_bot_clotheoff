import os
import logging
import secrets
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLOTHOFF_API_KEY = os.getenv("CLOTHOFF_API_KEY")
PORT = int(os.getenv("PORT", '8080'))
print(PORT)

WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH")
logger.info("CONFIG.PY: Read from env: RAW WEBHOOK_SECRET_PATH_FROM_ENV = '%s'", WEBHOOK_SECRET_PATH)

if not WEBHOOK_SECRET_PATH:
    raise ValueError("WEBHOOK_SECRET_PATH is not set in environment variables.")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
FIRESTORE_DB_NAME = os.getenv("FIRESTORE_DB_NAME", "undress-tg-bot-prod")

DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ru")
SUPPORTED_LANGUAGES = ['en', 'ru']

CLOTHOFF_API_URL = "https://public-api.clothoff.net/undress"


BASE_URL = os.getenv("BASE_URL")
logger.info(f"CONFIG.PY: Read from env: RAW BASE_URL = '{BASE_URL}'")

if BASE_URL:
    base_url = BASE_URL.rstrip('/')
    CLOTHOFF_RECEIVER_URL = f"{base_url}/webhook"
    TELEGRAM_RECEIVER_URL = f"{base_url}/{WEBHOOK_SECRET_PATH}"
    logger.info(f"CONFIG.PY: Final TELEGRAM_RECEIVER_URL = '{TELEGRAM_RECEIVER_URL}'")
else:
    CLOTHOFF_RECEIVER_URL = None
    TELEGRAM_RECEIVER_URL = None
    logger.warning("BASE_URL is not set in environment variables. Derived URLs (Telegram/Clothoff receiver) are None.")


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.DEBUG) # DEBUG для PTB
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("google.cloud.firestore").setLevel(logging.WARNING)
    logging.getLogger("google.api_core.bidi").setLevel(logging.WARNING)
    logging.getLogger('google.auth.compute_engine._metadata').setLevel(logging.WARNING)
    logging.getLogger(__name__).setLevel(logging.DEBUG)


setup_logging()
logger.info("Configuration loading module executed.")

logger.info("config.py loaded.")