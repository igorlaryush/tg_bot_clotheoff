import logging
import os # Added for os.getenv()
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Load .env file if it exists. Returns an empty dict if not found.
dotenv_config = dotenv_values(".env")

def get_config_value(key: str, default: str = None) -> str | None:
    """Gets a config value from .env, then os.environ, then default."""
    value = dotenv_config.get(key)
    if value is None:
        value = os.getenv(key)
    if value is None:
        value = default
    return value

# --- Core Bot Configuration ---
TELEGRAM_BOT_TOKEN = get_config_value("TELEGRAM_BOT_TOKEN")
CLOTHOFF_API_KEY = get_config_value("CLOTHOFF_API_KEY")
SCHEDULER_SECRET_TOKEN = get_config_value("SCHEDULER_SECRET_TOKEN")

PORT_STR = get_config_value("PORT", "8080")
PORT = int(PORT_STR) if PORT_STR else 8080

WEBHOOK_SECRET_PATH = get_config_value("WEBHOOK_SECRET_PATH")
logger.info("CONFIG.PY: Read WEBHOOK_SECRET_PATH = '%s'", WEBHOOK_SECRET_PATH)
if not WEBHOOK_SECRET_PATH:
    # This one is critical, so we might still want to raise an error if not set by any means.
    # For now, following the pattern. If it must be present, an explicit check after get_config_value is needed.
    logger.warning("WEBHOOK_SECRET_PATH is not set. This might cause issues.")
    # raise ValueError("WEBHOOK_SECRET_PATH is not set in environment variables or .env")

# --- GCP & Firestore ---
GCP_PROJECT_ID = get_config_value("GCP_PROJECT_ID")
FIRESTORE_DB_NAME = get_config_value("FIRESTORE_DB_NAME", "undress-tg-bot-prod")

# --- Localization ---
DEFAULT_LANGUAGE = get_config_value("DEFAULT_LANGUAGE", "ru")
SUPPORTED_LANGUAGES = ['en', 'ru'] # This might remain hardcoded or be from config if needed

# --- External APIs ---
CLOTHOFF_API_URL = get_config_value("CLOTHOFF_API_URL", "https://public-api.clothoff.net/undress")

# --- StreamPay Configuration ---
STREAMPAY_API_URL = get_config_value("STREAMPAY_API_URL", "https://api.streampay.org")
STREAMPAY_STORE_ID_STR = get_config_value("STREAMPAY_STORE_ID", "0")
STREAMPAY_STORE_ID = int(STREAMPAY_STORE_ID_STR) if STREAMPAY_STORE_ID_STR else 0
STREAMPAY_PRIVATE_KEY = get_config_value("STREAMPAY_PRIVATE_KEY")
STREAMPAY_PUBLIC_KEY = get_config_value("STREAMPAY_PUBLIC_KEY")
STREAMPAY_ENABLED = bool(STREAMPAY_STORE_ID and STREAMPAY_PRIVATE_KEY and STREAMPAY_PUBLIC_KEY)

if STREAMPAY_ENABLED:
    logger.info("StreamPay payment system enabled")
else:
    logger.warning("StreamPay payment system disabled - missing configuration")

# --- URL Configuration (derived from BASE_URL) ---
BASE_URL = get_config_value("BASE_URL")
logger.info(f"CONFIG.PY: Read BASE_URL = '{BASE_URL}'")

CLOTHOFF_RECEIVER_URL = None
TELEGRAM_RECEIVER_URL = None
STREAMPAY_CALLBACK_URL = None

if BASE_URL and WEBHOOK_SECRET_PATH: # Ensure both are present for TELEGRAM_RECEIVER_URL
    base_url_stripped = BASE_URL.rstrip('/')
    CLOTHOFF_RECEIVER_URL = f"{base_url_stripped}/webhook"
    TELEGRAM_RECEIVER_URL = f"{base_url_stripped}/{WEBHOOK_SECRET_PATH}"
    STREAMPAY_CALLBACK_URL = f"{base_url_stripped}/payment/callback"
    logger.info(f"CONFIG.PY: Final TELEGRAM_RECEIVER_URL = '{TELEGRAM_RECEIVER_URL}'")
    logger.info(f"CONFIG.PY: Final STREAMPAY_CALLBACK_URL = '{STREAMPAY_CALLBACK_URL}'")
    logger.info(f"CONFIG.PY: Final CLOTHOFF_RECEIVER_URL = '{CLOTHOFF_RECEIVER_URL}'")
elif not BASE_URL:
    logger.warning("BASE_URL is not set. Derived URLs (Telegram/Clothoff/StreamPay receiver) will be None.")
elif not WEBHOOK_SECRET_PATH:
    logger.warning("WEBHOOK_SECRET_PATH is not set. TELEGRAM_RECEIVER_URL cannot be fully constructed.")


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