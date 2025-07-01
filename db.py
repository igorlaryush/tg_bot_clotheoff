import logging
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP, Increment # Добавляем импорты
from typing import Dict, Optional, Any
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


async def get_or_create_user(user_id: int, chat_id: int, username: str = None, first_name: str = None, source: str = None) -> dict | None:
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
            if chat_id and chat_id != current_data.get("chat_id"):
                update_data["chat_id"] = chat_id

            # Ensure essential fields exist if missing from older documents
            if "language" not in current_data:
                update_data["language"] = config.DEFAULT_LANGUAGE
            if "agreed_to_terms" not in current_data:
                update_data["agreed_to_terms"] = False
            if "reply_keyboard_set" not in current_data:
                update_data["reply_keyboard_set"] = False

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
                "reply_keyboard_set": False,        # Persistent keyboard not set yet
                "source": source, # Add source
            }
            await user_doc_ref.set(user_data)
            logger.info("New user %s created in Firestore with source: %s.", user_id, user_data["source"])
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

# === Функции для работы с платежами ===

async def create_payment_order(order_data: Dict[str, Any]) -> bool:
    """Создает заказ на оплату в Firestore."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return False
    
    try:
        order_doc_ref = db.collection("payment_orders").document(order_data["external_id"])
        await order_doc_ref.set(order_data)
        logger.info(f"Payment order created: {order_data['external_id']}")
        return True
    except Exception as e:
        logger.error(f"Failed to create payment order {order_data.get('external_id')}: {e}")
        return False

async def get_payment_order_by_external_id(external_id: str) -> Optional[Dict[str, Any]]:
    """Получает заказ по external_id."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return None
    
    try:
        order_doc_ref = db.collection("payment_orders").document(external_id)
        order_snapshot = await order_doc_ref.get()
        
        if order_snapshot.exists:
            return order_snapshot.to_dict()
        else:
            logger.warning(f"Payment order not found: {external_id}")
            return None
    except Exception as e:
        logger.error(f"Failed to get payment order {external_id}: {e}")
        return None

async def update_payment_order(external_id: str, update_data: Dict[str, Any]) -> bool:
    """Обновляет заказ на оплату."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return False
    
    try:
        order_doc_ref = db.collection("payment_orders").document(external_id)
        await order_doc_ref.update(update_data)
        logger.info(f"Payment order updated: {external_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update payment order {external_id}: {e}")
        return False

async def add_user_photos(user_id: int, photos_count: int) -> bool:
    """Добавляет фото к балансу пользователя."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return False
    
    try:
        user_doc_ref = db.collection("users").document(str(user_id))
        
        # Проверяем, существует ли пользователь
        user_snapshot = await user_doc_ref.get()
        if not user_snapshot.exists:
            logger.error(f"User {user_id} not found when trying to add photos")
            return False
        
        # Добавляем поле photos_balance если его нет, иначе увеличиваем
        current_data = user_snapshot.to_dict()
        current_balance = current_data.get("photos_balance", 0)
        
        await user_doc_ref.update({
            "photos_balance": current_balance + photos_count,
            "last_seen": SERVER_TIMESTAMP
        })
        
        logger.info(f"Added {photos_count} photos to user {user_id}. New balance: {current_balance + photos_count}")
        return True
    except Exception as e:
        logger.error(f"Failed to add photos to user {user_id}: {e}")
        return False

async def deduct_user_photos(user_id: int, photos_count: int = 1) -> bool:
    """Списывает фото с баланса пользователя."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return False
    
    try:
        user_doc_ref = db.collection("users").document(str(user_id))
        
        # Получаем текущий баланс
        user_snapshot = await user_doc_ref.get()
        if not user_snapshot.exists:
            logger.error(f"User {user_id} not found when trying to deduct photos")
            return False
        
        current_data = user_snapshot.to_dict()
        current_balance = current_data.get("photos_balance", 0)
        
        if current_balance < photos_count:
            logger.warning(f"User {user_id} has insufficient balance: {current_balance} < {photos_count}")
            return False
        
        # Списываем фото
        await user_doc_ref.update({
            "photos_balance": current_balance - photos_count,
            "last_seen": SERVER_TIMESTAMP
        })
        
        logger.info(f"Deducted {photos_count} photos from user {user_id}. New balance: {current_balance - photos_count}")
        return True
    except Exception as e:
        logger.error(f"Failed to deduct photos from user {user_id}: {e}")
        return False

async def get_user_photos_balance(user_id: int) -> int:
    """Получает баланс фото пользователя."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return 0
    
    try:
        user_doc_ref = db.collection("users").document(str(user_id))
        user_snapshot = await user_doc_ref.get()
        
        if user_snapshot.exists:
            user_data = user_snapshot.to_dict()
            return user_data.get("photos_balance", 0)
        else:
            logger.warning(f"User {user_id} not found when getting photos balance")
            return 0
    except Exception as e:
        logger.error(f"Failed to get photos balance for user {user_id}: {e}")
        return 0

async def get_user_payment_history(user_id: int, limit: int = 10) -> list:
    """Получает историю платежей пользователя."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return []
    
    try:
        orders_query = (db.collection("payment_orders")
                       .where("user_id", "==", user_id)
                       .order_by("created_at", direction=firestore.Query.DESCENDING)
                       .limit(limit))
        
        orders_snapshot = await orders_query.get()
        orders = []
        
        for doc in orders_snapshot:
            order_data = doc.to_dict()
            orders.append(order_data)
        
        logger.info(f"Retrieved {len(orders)} payment orders for user {user_id}")
        return orders
    except Exception as e:
        logger.error(f"Failed to get payment history for user {user_id}: {e}")
        return []

async def get_all_users() -> list[Dict[str, Any]]:
    """Retrieves all users from Firestore."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return []
    
    users_list = []
    try:
        users_collection = db.collection("users")
        async for doc in users_collection.stream():
            users_list.append(doc.to_dict())
        logger.info(f"Retrieved {len(users_list)} users from Firestore.")
    except Exception as e:
        logger.exception("Error retrieving all users from Firestore: %s", e)
    return users_list

# === Функции для логирования событий пользователя ===

async def log_user_event(user_id: int, event_type: str, event_details: Optional[Dict[str, Any]] = None) -> bool:
    """Logs a user event to Firestore."""
    if not db:
        logger.error("Firestore client is not initialized. Cannot log event.")
        return False

    try:
        event_data = {
            "user_id": user_id,
            "event_type": event_type,
            "timestamp": SERVER_TIMESTAMP,
            "event_details": event_details if event_details else {}
        }
        # Генерируем уникальный ID для события, чтобы избежать перезаписи
        # и иметь возможность ссылаться на конкретное событие.
        # Firestore автоматически генерирует ID, если не указать document(),
        # но мы можем создать его и здесь для большей наглядности или если он нужен заранее.
        # В данном случае, позволим Firestore генерировать ID автоматически.
        event_doc_ref = await db.collection("user_events").add(event_data)
        logger.info(f"Logged event '{event_type}' for user {user_id}. Event ID: {event_doc_ref[1].id}")
        return True
    except Exception as e:
        logger.exception(f"Failed to log event '{event_type}' for user {user_id}: {e}")
        return False
