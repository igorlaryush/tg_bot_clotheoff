# bot.py
import os
import logging
import asyncio
import uuid
from io import BytesIO
import secrets
import json

import aiohttp
from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import uvicorn

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Application,
)
from telegram.constants import ParseMode

# --- Firestore Integration ---
from google.cloud import firestore # <--- Добавили импорт Firestore
# Используем асинхронный клиент Firestore
db = None # <--- Глобальная переменная для клиента Firestore

# --- Configuration ---
load_dotenv(override=True)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLOTHOFF_API_KEY = os.getenv("CLOTHOFF_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", '5000'))
WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", secrets.token_urlsafe(32))
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID") # <--- Загружаем ID проекта

CLOTHOFF_API_URL = "https://public-api.clothoff.net/undress"

# --- Validate Configuration ---
# Добавляем проверку GCP_PROJECT_ID
if not all([TELEGRAM_BOT_TOKEN, CLOTHOFF_API_KEY, NGROK_URL, GCP_PROJECT_ID]):
    raise ValueError("Missing required environment variables (TELEGRAM_BOT_TOKEN, CLOTHOFF_API_KEY, NGROK_URL, GCP_PROJECT_ID)")

# --- Firestore Initialization ---
try:
    # Инициализируем АСИНХРОННЫЙ клиент Firestore
    # Он автоматически подхватит учетные данные (Application Default Credentials)
    # и будет использовать проект из переменной GCP_PROJECT_ID
    db = firestore.AsyncClient(project=GCP_PROJECT_ID, database="undress-tg-bot-dev")
    logging.info(f"Firestore client initialized for project: {GCP_PROJECT_ID}")
except Exception as e:
    logging.exception("Failed to initialize Firestore client!")
    # Вы можете решить, прерывать ли запуск, если БД недоступна
    # raise e # Раскомментируйте, чтобы остановить запуск при ошибке инициализации БД

CLOTHOFF_RECEIVER_URL = f"{NGROK_URL.rstrip('/')}/webhook"
TELEGRAM_RECEIVER_URL = f"{NGROK_URL.rstrip('/')}/{WEBHOOK_SECRET_PATH}"

# Configure logging (без изменений)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logging.getLogger("uvicorn").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Variables ---
ptb_application: Application = None
results_queue = asyncio.Queue()
# Меняем структуру: храним user_id вместе с chat_id
# Ключ: id_gen, Значение: {"chat_id": ..., "user_id": ...}
pending_requests = {}

# --- Flask App Setup (без изменений) ---
flask_app = Flask(__name__)
flask_app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- Firestore Helper Functions ---

async def get_or_create_user(user_id: int, chat_id: int, username: str = None, first_name: str = None) -> dict:
    """Получает или создает пользователя в Firestore."""
    if not db:
        logger.error("Firestore client is not initialized.")
        return None # Или выбросить исключение

    user_doc_ref = db.collection("users").document(str(user_id)) # ID документа = user_id как строка
    try:
        user_snapshot = await user_doc_ref.get()

        if user_snapshot.exists:
            # Пользователь найден, обновим last_seen и, возможно, имя/username
            update_data = {"last_seen": firestore.SERVER_TIMESTAMP}
            if username: update_data["username"] = username
            if first_name: update_data["first_name"] = first_name
            await user_doc_ref.update(update_data)
            logger.debug(f"User {user_id} found and updated.")
            return user_snapshot.to_dict() # Возвращаем данные как были до обновления
        else:
            # Пользователь не найден, создаем новую запись
            user_data = {
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "photos_processed": 0, # Счетчик обработанных фото
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_seen": firestore.SERVER_TIMESTAMP,
                # Добавьте другие поля по необходимости (язык, статус подписки и т.д.)
            }
            await user_doc_ref.set(user_data)
            logger.info(f"New user {user_id} created in Firestore.")
            return user_data
    except Exception as e:
        logger.exception(f"Error accessing Firestore for user {user_id}: {e}")
        return None # Возвращаем None при ошибке доступа к БД

async def increment_user_counter(user_id: int, field: str = "photos_processed", amount: int = 1) -> bool:
    """Атомарно увеличивает счетчик для пользователя."""
    if not db:
        logger.error("Firestore client is not initialized for increment.")
        return False

    user_doc_ref = db.collection("users").document(str(user_id))
    try:
        await user_doc_ref.update({field: firestore.Increment(amount)})
        logger.info(f"Incremented '{field}' for user {user_id} by {amount}.")
        return True
    except Exception as e:
        # Может произойти, если документа пользователя еще нет (маловероятно, если get_or_create_user вызывается первым)
        logger.error(f"Failed to increment '{field}' for user {user_id}: {e}")
        return False

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Received /start from user_id: {user.id}, username: {user.username}")
    # --- Firestore Integration ---
    user_data = await get_or_create_user(
        user_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name
    )
    if user_data:
        logger.info(f"User {user.id} data retrieved/created.")
    else:
        logger.warning(f"Could not get/create user data for {user.id}")
    # --- End Firestore Integration ---

    await context.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
    ])
    await update.message.reply_text(
        f"Hello {user.first_name}! Send me a photo containing a person, and I'll try to process it using Clothoff.io."
        "\n\n⚠️ **Disclaimer:** Use this bot responsibly and ethically."
        "\n\nThis bot uses the Clothoff API and is for demonstration purposes.",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Можно тоже добавить get_or_create_user для обновления last_seen
    user = update.effective_user
    await get_or_create_user(user.id, update.effective_chat.id, user.username, user.first_name)
    # ---
    await update.message.reply_text(
        "Send me a photo with a person in it. I will send it to the Clothoff API for processing.\n"
        "You will receive the result back here once it's ready.\n\n"
        "**Important:**\n"
        "- Ensure the image clearly shows one person.\n"
        "- Processing can take some time.\n"
        "- Results depend on the Clothoff API's capabilities.\n"
        "- Use responsibly.",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    user_id = user.id

    logger.info(f"Received photo from user_id: {user_id} in chat_id: {chat_id}")

    # --- Firestore: Получить/создать пользователя перед обработкой ---
    user_data = await get_or_create_user(user_id, chat_id, user.username, user.first_name)
    if not user_data:
        await update.message.reply_text("Sorry, there was a problem accessing user data. Please try again later.", reply_to_message_id=message_id)
        return
    # --- Опционально: Проверка лимитов или статуса пользователя ---
    # Например: if user_data.get('photos_processed', 0) >= MAX_PHOTOS_PER_DAY:
    #             await update.message.reply_text("You've reached your daily limit.")
    #             return
    # ---

    try:
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        photo_bytes_io = BytesIO()
        await photo_file.download_to_memory(photo_bytes_io)
        photo_bytes_io.seek(0)
        photo_bytes = photo_bytes_io.read()

        if not photo_bytes:
             await update.message.reply_text("Could not download the photo.", reply_to_message_id=message_id)
             return

        id_gen = str(uuid.uuid4())
        # --- Сохраняем и user_id, и chat_id ---
        pending_requests[id_gen] = {"chat_id": chat_id, "user_id": user_id}
        logger.info(f"Generated id_gen: {id_gen} for user {user_id}")

        data = aiohttp.FormData()
        data.add_field('image', photo_bytes, filename='photo.jpg', content_type='image/jpeg')
        data.add_field('id_gen', id_gen)
        data.add_field('webhook', CLOTHOFF_RECEIVER_URL)

        headers = {'x-api-key': CLOTHOFF_API_KEY, 'accept': 'application/json'}

        await update.message.reply_text("Processing your photo...", reply_to_message_id=message_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(CLOTHOFF_API_URL, data=data, headers=headers) as response:
                response_text = await response.text()
                logger.debug(f"Clothoff API Raw Response ({response.status}) for id_gen {id_gen}: {response_text}")

                if response.status == 200:
                    logger.info(f"Clothoff API call successful for id_gen {id_gen}. Waiting for webhook.")
                else:
                    logger.error(f"Clothoff API error for id_gen {id_gen}: Status {response.status}, Response: {response_text}")
                    if id_gen in pending_requests: del pending_requests[id_gen]
                    await update.message.reply_text(f"API Error: {response.status} - {response_text}", reply_to_message_id=message_id)

    except aiohttp.ClientError as e:
        logger.error(f"Network error calling Clothoff API for user {user_id} (id_gen: {id_gen if 'id_gen' in locals() else 'N/A'}): {e}")
        if 'id_gen' in locals() and id_gen in pending_requests: del pending_requests[id_gen]
        await update.message.reply_text("Connection error to processing service.", reply_to_message_id=message_id)
    except Exception as e:
        logger.exception(f"Unexpected error in handle_photo for user {user_id} (id_gen: {id_gen if 'id_gen' in locals() else 'N/A'}): {e}")
        if 'id_gen' in locals() and id_gen in pending_requests: del pending_requests[id_gen]
        await update.message.reply_text("An unexpected error occurred.", reply_to_message_id=message_id)

# --- Обработчик результатов из очереди Clothoff ---
async def process_results_queue(app: Application):
    logger.info("Result processing task started.")
    while True:
        try:
            result = await results_queue.get()
            id_gen = result.get("id_gen")
            logger.info(f"Dequeued result: {id_gen}, status: {result.get('status')}")

            if not id_gen:
                logger.warning("Received result from queue with missing id_gen.")
                results_queue.task_done()
                continue

            # --- Извлекаем user_id и chat_id ---
            request_info = pending_requests.pop(id_gen, None)
            if request_info is None:
                logger.warning(f"Received result for unknown or timed-out id_gen: {id_gen}")
                results_queue.task_done()
                continue

            chat_id = request_info.get("chat_id")
            user_id = request_info.get("user_id") # Получаем user_id

            if not chat_id or not user_id:
                 logger.error(f"Missing chat_id or user_id in pending_requests for id_gen: {id_gen}")
                 results_queue.task_done()
                 continue
            # ---

            status = result.get("status")
            image_data = result.get("image_data")
            error_message = result.get("error_message")

            try:
                if status == '200' and image_data:
                    logger.info(f"Sending processed image for id_gen {id_gen} to chat_id {chat_id} (user: {user_id})")
                    await app.bot.send_photo(
                        chat_id=chat_id,
                        photo=bytes(image_data),
                        caption=f"Processed image (ID: {id_gen})."
                    )
                    # --- Firestore: Увеличиваем счетчик после успешной отправки ---
                    await increment_user_counter(user_id, "photos_processed")
                    # ---
                else:
                    error_msg = error_message or f"Processing failed (status {status})."
                    logger.warning(f"Processing failed for id_gen {id_gen} (user {user_id}, chat {chat_id}): {error_msg}")
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"Processing failed for image (ID: {id_gen}). Reason: {error_msg}"
                    )
            except Exception as send_err:
                 logger.error(f"Failed to send result for id_gen {id_gen} to chat_id {chat_id} (user: {user_id}): {send_err}")
                 # Попытка уведомить об ошибке отправки
                 try:
                      await app.bot.send_message(chat_id=chat_id, text=f"Failed to send result for ID: {id_gen}.")
                 except Exception:
                      logger.error(f"Also failed to send error notification to chat_id {chat_id}")

            results_queue.task_done()

        except asyncio.CancelledError:
            logger.info("Result processing task cancelled.")
            break
        except Exception as e:
            logger.exception(f"Error in results processing loop: {e}")
            # Добавляем небольшую задержку перед повторной попыткой в случае общей ошибки цикла
            await asyncio.sleep(5)


# --- Flask Routes (telegram_webhook_handler, clothoff_webhook_handler) ---
# --- Без изменений, они не взаимодействуют напрямую с Firestore ---

@flask_app.route(f"/{WEBHOOK_SECRET_PATH}", methods=['POST'])
async def telegram_webhook_handler():
    if ptb_application is None:
        logger.error("PTB Application not initialized yet.")
        return jsonify({"error": "Bot not ready"}), 503 # Service Unavailable
    try:
        update_data = request.get_json()
        if not update_data:
            logger.warning("Received empty payload from Telegram.")
            return jsonify({"error": "Bad Request: Empty payload"}), 400
        logger.debug(f"Telegram webhook received: {json.dumps(update_data, indent=2)}")
        update = Update.de_json(update_data, ptb_application.bot)
        await ptb_application.process_update(update)
        return jsonify({"ok": True}), 200
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from Telegram webhook.")
        return jsonify({"error": "Bad Request: Invalid JSON"}), 400
    except Exception as e:
        logger.exception(f"Error processing Telegram update: {e}")
        return jsonify({"ok": "Error processing update, logged."}), 200

@flask_app.route('/webhook', methods=['POST'])
def clothoff_webhook_handler():
    if results_queue is None:
        logger.error("Results queue is None in clothoff_webhook_handler!")
        return jsonify({"error": "Internal server error: Queue not ready"}), 500

    content_type = request.content_type or ''
    if request.method != 'POST':
        return jsonify({"error": "Method Not Allowed"}), 405
    if 'multipart/form-data' not in content_type:
        logger.warning("Clothoff: Received non-multipart request: %s", content_type)
        return jsonify({"error": "Bad Request: Expected multipart/form-data"}), 400

    try:
        status = request.form.get('status')
        id_gen = request.form.get('id_gen')
        time_gen = request.form.get('time_gen')
        res_image_file = request.files.get('res_image')
        img_message = request.form.get('img_message')
        logger.info(f"Clothoff Webhook received for id_gen: {id_gen}, status: {status}")

        if not id_gen:
             raise ValueError("Missing 'id_gen' in Clothoff webhook data")

        result_data = { "id_gen": id_gen, "status": status, "image_data": None, "error_message": None, "time_gen": time_gen }

        if status == '200' and res_image_file:
            if not res_image_file.filename: raise ValueError("'res_image' received but has no filename")
            image_bytes = res_image_file.read()
            result_data["image_data"] = image_bytes
            logger.info(f"Clothoff: Received image for id_gen: {id_gen}, size: {len(image_bytes)} bytes")
        elif status != '200':
            result_data["error_message"] = img_message or "Unknown error from Clothoff"
            logger.warning(f"Clothoff: Error status for id_gen {id_gen}: {status} - {result_data['error_message']}")
        else:
             raise ValueError("Clothoff: Status 200 but 'res_image' file is missing")

        try:
            results_queue.put_nowait(result_data)
            logger.debug(f"Clothoff: Successfully put result for {id_gen} onto the queue.")
        except asyncio.QueueFull:
            logger.error(f"Result queue is full! Dropping Clothoff result for id_gen: {id_gen}")
            return jsonify({"error": "Internal server error: Processing queue full"}), 503
        except Exception as q_err:
            logger.error(f"Error putting Clothoff result onto queue for id_gen {id_gen}: {q_err}")
            return jsonify({"error": "Internal server error: Failed to queue result"}), 500

        return jsonify({"message": "Clothoff webhook received successfully"}), 200
    except ValueError as ve:
        logger.error(f"Invalid Clothoff webhook data: {ve}")
        return jsonify({"error": f"Bad Request: {ve}"}), 400
    except Exception as e:
        logger.exception(f"Unexpected error processing Clothoff webhook: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

async def main():
    global ptb_application
    global db # Убедимся, что используем глобальный клиент

    # Проверка инициализации Firestore (если она не удалась ранее)
    if not db:
        logger.error("Firestore client failed to initialize. Bot cannot start correctly with DB features.")
        # Решите, нужно ли останавливать бота, если БД недоступна
        # return # Раскомментируйте для остановки

    logger.info("Initializing PTB Application...")
    ptb_application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    ptb_application.add_handler(CommandHandler("start", start))
    ptb_application.add_handler(CommandHandler("help", help_command))
    ptb_application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    await ptb_application.initialize()

    logger.info(f"Setting Telegram webhook to: {TELEGRAM_RECEIVER_URL}")
    try:
        await ptb_application.bot.set_webhook(
            url=TELEGRAM_RECEIVER_URL,
            allowed_updates=Update.ALL_TYPES,
            secret_token=WEBHOOK_SECRET_PATH
        )
        logger.info("Telegram webhook set successfully.")
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return

    results_task = asyncio.create_task(process_results_queue(ptb_application))
    logger.info("Clothoff result processing task scheduled.")

    await ptb_application.start()
    logger.info("PTB Application background tasks started.")

    asgi_flask_app = WsgiToAsgi(flask_app)

    config = uvicorn.Config(
        app=asgi_flask_app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    logger.info(f"Starting Uvicorn server on port {WEBHOOK_PORT}...")
    logger.info(f"Telegram should send updates to: {TELEGRAM_RECEIVER_URL}")
    logger.info(f"Clothoff API should send results to: {CLOTHOFF_RECEIVER_URL}")
    logger.info(f"Using GCP Project ID for Firestore: {GCP_PROJECT_ID}") # Логируем используемый проект

    try:
        await server.serve()
    finally:
        logger.info("Shutting down...")
        await ptb_application.stop()
        await ptb_application.shutdown()
        results_task.cancel()
        try:
            await results_task
        except asyncio.CancelledError:
            logger.info("Result processing task cancelled successfully.")
        # Закрытие клиента Firestore обычно не требуется явно для AsyncClient,
        # но если бы вы использовали синхронный или имели другие ресурсы,
        # здесь было бы место для их освобождения.
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
