import logging
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP, Increment # Добавляем импорты
import config # Импортируем наш конфиг

logger = logging.getLogger(__name__)

db: AsyncClient = None

async def init_db():
    """Initializes the Firestore asynchronous client."""
    global db
    if db is None:
        try:
            logger.info(
                "Attempting to initialize Firestore async client for project: %s, database: %s",
                config.GCP_PROJECT_ID,
                config.FIRESTORE_DB_NAME
            )

            db = firestore.AsyncClient(
                project=config.GCP_PROJECT_ID, # 'tg-bot-clotheoff-prod', 
                database=config.FIRESTORE_DB_NAME, # 'undress-tg-bot-prod', 
            )

            logger.info("Performing Firestore connection check...")
            test_query = db.collection('users').limit(1)
            print(await test_query.get())
            logger.info("Firestore connection check successful.")

        except Exception as e:
            # Логируем полную ошибку для диагностики
            logger.exception("Failed to initialize Firestore async client!")
            db = None # Убедимся, что db остался None при ошибке
            # Передаем ошибку дальше, чтобы main мог решить, останавливаться ли
            raise e # Re-raise the exception after logging
    return db


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
                logger.debug("User %s found and potentially updated.", user_id)
            else:
                 # Just update last_seen if nothing else changed
                 await user_doc_ref.update({"last_seen": SERVER_TIMESTAMP})
                 logger.debug("User %s found. Updated last_seen.", user_id)

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
            logger.info("New user %s created in Firestore with defaults.", user_id)
            return user_data
    except Exception as e:
        logger.exception("Error accessing Firestore for user %s: %s", user_id, e)
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
        logger.info("Updated user %s data: %s", user_id, update_dict)
        return True
    except Exception as e:
        logger.error("Failed to update data for user %s: %s", user_id, e)
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
            logger.warning(
                "Attempted to increment '%s' for non-existent user %s. Cannot increment.",
                field,
                user_id
            )
            return False
        await user_doc_ref.update({field: Increment(amount)})
        logger.info("Incremented '%s' for user %s by %s.", field, user_id, amount)
        return True
    except Exception as e:
        logger.error("Failed to increment '%s' for user %s: %s", field, user_id, e)
        return False
