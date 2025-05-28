import logging
from dotenv import dotenv_values

logger = logging.getLogger(__name__)


config = dotenv_values(".env")

TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
CLOTHOFF_API_KEY = config.get("CLOTHOFF_API_KEY")
PORT = int(config.get("PORT", '8080'))
print(PORT)

WEBHOOK_SECRET_PATH = config.get("WEBHOOK_SECRET_PATH")
logger.info("CONFIG.PY: Read from env: RAW WEBHOOK_SECRET_PATH_FROM_ENV = '%s'", WEBHOOK_SECRET_PATH)

if not WEBHOOK_SECRET_PATH:
    raise ValueError("WEBHOOK_SECRET_PATH is not set in environment variables.")

GCP_PROJECT_ID = config.get("GCP_PROJECT_ID")
FIRESTORE_DB_NAME = config.get("FIRESTORE_DB_NAME", "undress-tg-bot-prod")

DEFAULT_LANGUAGE = config.get("DEFAULT_LANGUAGE", "ru")
SUPPORTED_LANGUAGES = ['en', 'ru']

CLOTHOFF_API_URL = "https://public-api.clothoff.net/undress"

# StreamPay Configuration
STREAMPAY_API_URL = config.get("STREAMPAY_API_URL", "https://api.streampay.org")
STREAMPAY_STORE_ID = int(config.get("STREAMPAY_STORE_ID", "0"))
STREAMPAY_PRIVATE_KEY = config.get("STREAMPAY_PRIVATE_KEY")
STREAMPAY_PUBLIC_KEY = config.get("STREAMPAY_PUBLIC_KEY")
STREAMPAY_ENABLED = bool(STREAMPAY_STORE_ID and STREAMPAY_PRIVATE_KEY and STREAMPAY_PUBLIC_KEY)

if STREAMPAY_ENABLED:
    logger.info("StreamPay payment system enabled")
else:
    logger.warning("StreamPay payment system disabled - missing configuration")

BASE_URL = config.get("BASE_URL")
logger.info(f"CONFIG.PY: Read from env: RAW BASE_URL = '{BASE_URL}'")

if BASE_URL:
    base_url = BASE_URL.rstrip('/')
    CLOTHOFF_RECEIVER_URL = f"{base_url}/webhook"
    TELEGRAM_RECEIVER_URL = f"{base_url}/{WEBHOOK_SECRET_PATH}"
    STREAMPAY_CALLBACK_URL = f"{base_url}/payment/callback"
    logger.info(f"CONFIG.PY: Final TELEGRAM_RECEIVER_URL = '{TELEGRAM_RECEIVER_URL}'")
    logger.info(f"CONFIG.PY: Final STREAMPAY_CALLBACK_URL = '{STREAMPAY_CALLBACK_URL}'")
else:
    CLOTHOFF_RECEIVER_URL = None
    TELEGRAM_RECEIVER_URL = None
    STREAMPAY_CALLBACK_URL = None
    logger.warning("BASE_URL is not set in environment variables. Derived URLs (Telegram/Clothoff/StreamPay receiver) are None.")


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