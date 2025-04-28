import logging
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP, Increment # Добавляем импорты
import config # Импортируем наш конфиг

logger = logging.getLogger(__name__)

# --- Firestore Client ---
db: AsyncClient = None # Используем аннотацию типов

async def init_db():
    """Initializes the Firestore asynchronous client."""
    global db
    if db is None:
        try:
            logger.info(f"Attempting to initialize Firestore async client for project: {config.GCP_PROJECT_ID}, database: {config.FIRESTORE_DB_NAME}")
            # Используем параметры из config.py
            db = firestore.AsyncClient(project=config.GCP_PROJECT_ID, database=config.FIRESTORE_DB_NAME)

            # Проверим соединение (опционально, но полезно) - используем валидное имя
            # Этот документ не обязательно должен существовать, важна сама попытка запроса
            # Используем get() на несуществующем документе для проверки связи и прав
            logger.debug("Performing Firestore connection check...")
            test_doc_ref = db.collection('_internal_ping').document('connection_check')
            await test_doc_ref.get() # This request checks connectivity and basic permissions
            logger.info(f"Firestore connection check successful.")
            logger.info(f"Firestore async client initialized successfully for project: {config.GCP_PROJECT_ID}, database: {config.FIRESTORE_DB_NAME}")

        except Exception as e:
            # Логируем полную ошибку для диагностики
            logger.exception("Failed to initialize Firestore async client!")
            db = None # Убедимся, что db остался None при ошибке
            # Передаем ошибку дальше, чтобы main мог решить, останавливаться ли
            raise e # Re-raise the exception after logging
    return db

# --- Firestore Helper Functions ---

async def get_or_create_user(user_id: int, chat_id: int, username: str = None, first_name: str = None) -> dict | None:
    """Gets or creates a user in Firestore, including language and agreement status."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return None

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        user_snapshot = await user_doc_ref.get()

        if user_snapshot.exists:
            update_data = {"last_seen": SERVER_TIMESTAMP}
            current_data = user_snapshot.to_dict()

            # Update fields only if changed
            if username and username != current_data.get("username"):
                update_data["username"] = username
            if first_name and first_name != current_data.get("first_name"):
                update_data["first_name"] = first_name
            if chat_id != current_data.get("chat_id"):
                update_data["chat_id"] = chat_id

            # Ensure essential fields exist if missing from older documents
            if "language" not in current_data:
                update_data["language"] = config.DEFAULT_LANGUAGE
            if "agreed_to_terms" not in current_data:
                update_data["agreed_to_terms"] = False
            if "processing_options" not in current_data:
                 update_data["processing_options"] = {} # Default empty options

            if len(update_data) > 1: # Update only if more than last_seen changed
                await user_doc_ref.update(update_data)
                logger.debug(f"User {user_id} found and potentially updated.")
            else:
                 # Just update last_seen if nothing else changed
                 await user_doc_ref.update({"last_seen": SERVER_TIMESTAMP})
                 logger.debug(f"User {user_id} found. Updated last_seen.")

            # Return the potentially updated data
            return (await user_doc_ref.get()).to_dict()
        else:
            # Create new user
            user_data = {
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "photos_processed": 0,
                "created_at": SERVER_TIMESTAMP,
                "last_seen": SERVER_TIMESTAMP,
                "language": config.DEFAULT_LANGUAGE, # Set default language
                "agreed_to_terms": False,           # Not agreed yet
                "processing_options": {},           # Default empty options
            }
            await user_doc_ref.set(user_data)
            logger.info(f"New user {user_id} created in Firestore with defaults.")
            return user_data
    except Exception as e:
        logger.exception(f"Error accessing Firestore for user {user_id}: {e}")
        return None

async def update_user_data(user_id: int, update_dict: dict) -> bool:
    """Updates specific fields for a user."""
    if not db:
        logger.error("Firestore client is not initialized for update.")
        return False
    if not update_dict:
        logger.warning("update_user_data called with empty update_dict.")
        return True # Nothing to update

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        # Add last_seen timestamp to every update
        update_dict_with_ts = {**update_dict, "last_seen": SERVER_TIMESTAMP}
        await user_doc_ref.update(update_dict_with_ts)
        logger.info(f"Updated user {user_id} data: {update_dict}")
        return True
    except Exception as e:
        logger.error(f"Failed to update data for user {user_id}: {e}")
        return False

async def increment_user_counter(user_id: int, field: str = "photos_processed", amount: int = 1) -> bool:
    """Atomically increments a counter field for a user."""
    if not db:
        logger.error("Firestore client is not initialized for increment.")
        return False

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        user_snapshot = await user_doc_ref.get()
        if not user_snapshot.exists:
            logger.warning(f"Attempted to increment '{field}' for non-existent user {user_id}. Cannot increment.")
            return False
        await user_doc_ref.update({field: Increment(amount)})
        logger.info(f"Incremented '{field}' for user {user_id} by {amount}.")
        return True
    except Exception as e:
        logger.error(f"Failed to increment '{field}' for user {user_id}: {e}")
        return False
