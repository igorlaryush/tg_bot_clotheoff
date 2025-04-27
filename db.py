import logging
from google.cloud import firestore
from google.cloud.firestore import AsyncClient # Явно импортируем AsyncClient
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
    """Gets or creates a user in Firestore."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return None

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        user_snapshot = await user_doc_ref.get()

        if user_snapshot.exists:
            update_data = {"last_seen": firestore.SERVER_TIMESTAMP}
            # Обновляем только если переданы новые значения
            current_data = user_snapshot.to_dict()
            if username and username != current_data.get("username"):
                update_data["username"] = username
            if first_name and first_name != current_data.get("first_name"):
                 update_data["first_name"] = first_name
            # Обновляем chat_id, если он изменился (маловероятно для ЛС, но возможно в группах)
            if chat_id != current_data.get("chat_id"):
                update_data["chat_id"] = chat_id

            if len(update_data) > 1: # Обновляем только если есть что обновить кроме last_seen
                await user_doc_ref.update(update_data)
                logger.debug(f"User {user_id} found and updated.")
            else:
                 await user_doc_ref.update({"last_seen": firestore.SERVER_TIMESTAMP}) # Обновляем только last_seen
                 logger.debug(f"User {user_id} found. Updated last_seen.")
            # Возвращаем данные *после* потенциального обновления
            return (await user_doc_ref.get()).to_dict()
        else:
            user_data = {
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "photos_processed": 0,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_seen": firestore.SERVER_TIMESTAMP,
            }
            await user_doc_ref.set(user_data)
            logger.info(f"New user {user_id} created in Firestore.")
            return user_data
    except Exception as e:
        logger.exception(f"Error accessing Firestore for user {user_id}: {e}")
        return None

async def increment_user_counter(user_id: int, field: str = "photos_processed", amount: int = 1) -> bool:
    """Atomically increments a counter field for a user."""
    if not db:
        logger.error("Firestore client is not initialized for increment.")
        return False

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        # Проверим, существует ли документ перед инкрементом, чтобы избежать ошибок
        user_snapshot = await user_doc_ref.get()
        if not user_snapshot.exists:
            logger.warning(f"Attempted to increment '{field}' for non-existent user {user_id}. Maybe create user first?")
            # Или можно создать пользователя здесь с нулевым счетчиком, а потом инкрементировать
            # await get_or_create_user(user_id, 0) # Понадобится chat_id! Лучше убедиться, что пользователь создан ранее.
            return False

        await user_doc_ref.update({field: firestore.Increment(amount)})
        logger.info(f"Incremented '{field}' for user {user_id} by {amount}.")
        return True
    except Exception as e:
        logger.error(f"Failed to increment '{field}' for user {user_id}: {e}")
        return False
