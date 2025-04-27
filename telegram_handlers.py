import logging
import uuid
from io import BytesIO
import aiohttp

from telegram import Update, BotCommand
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config  # Импортируем конфиг для API ключей и URL
import db      # Импортируем функции для работы с БД
import bot_state # Импортируем глобальное состояние

logger = logging.getLogger(__name__)

async def setup_bot_commands(context: ContextTypes.DEFAULT_TYPE):
    """Sets the bot commands."""
    await context.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        # Добавьте другие команды сюда
    ])
    logger.info("Bot commands updated.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Received /start from user_id: {user.id} in chat_id: {chat_id}")

    user_data = await db.get_or_create_user(
        user_id=user.id,
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name
    )
    if user_data:
        logger.info(f"User {user.id} data retrieved/created.")
    else:
        logger.warning(f"Could not get/create user data for {user.id}")
        # Возможно, стоит уведомить пользователя об ошибке
        await update.message.reply_text("Sorry, there was a problem initializing your user profile. Please try again later.")
        return

    # Устанавливаем команды при первом /start
    # await setup_bot_commands(context) # Или вызывать это один раз при запуске бота в main.py

    await update.message.reply_text(
        f"Hello {user.first_name}! Send me a photo containing a person, and I'll try to process it using Clothoff.io."
        "\n\n⚠️ **Disclaimer:** Use this bot responsibly and ethically."
        "\n\nThis bot uses the Clothoff API and is for demonstration purposes.",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Received /help from user_id: {user.id} in chat_id: {chat_id}")
    # Обновляем last_seen пользователя
    await db.get_or_create_user(user.id, chat_id, user.username, user.first_name)

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
        logger.debug("Update does not contain photo.")
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    user_id = user.id

    logger.info(f"Received photo from user_id: {user_id} in chat_id: {chat_id}")

    # Получаем/создаем пользователя и проверяем результат
    user_data = await db.get_or_create_user(user_id, chat_id, user.username, user.first_name)
    if not user_data:
        await update.message.reply_text("Sorry, there was a problem accessing your user data. Please try again later.", reply_to_message_id=message_id)
        return

    # --- Опционально: Проверка лимитов ---
    # photos_today = user_data.get('photos_processed_today', 0) # Пример, если есть дневной счетчик
    # if photos_today >= DAILY_LIMIT:
    #     await update.message.reply_text("You've reached your daily processing limit.", reply_to_message_id=message_id)
    #     return

    photo_file = None
    id_gen = None # Инициализируем для блока finally/except
    try:
        # Выбираем фото наибольшего разрешения
        photo = update.message.photo[-1]
        logger.debug(f"Selected photo file_id: {photo.file_id} size: {photo.width}x{photo.height}")
        photo_file = await context.bot.get_file(photo.file_id)

        photo_bytes_io = BytesIO()
        await photo_file.download_to_memory(photo_bytes_io)
        photo_bytes_io.seek(0)
        photo_bytes = photo_bytes_io.read()

        if not photo_bytes:
            logger.warning(f"Could not download photo bytes for file_id: {photo.file_id}")
            await update.message.reply_text("Could not download the photo.", reply_to_message_id=message_id)
            return

        # Генерируем ID и сохраняем запрос в bot_state
        id_gen = str(uuid.uuid4())
        bot_state.pending_requests[id_gen] = {"chat_id": chat_id, "user_id": user_id, "message_id": message_id}
        logger.info(f"Generated id_gen: {id_gen} for user {user_id}. Pending requests: {len(bot_state.pending_requests)}")

        # --- Отправка в Clothoff API ---
        data = aiohttp.FormData()
        data.add_field('image', photo_bytes, filename=f'{id_gen}.jpg', content_type='image/jpeg') # Даем уникальное имя
        data.add_field('id_gen', id_gen)
        data.add_field('webhook', config.CLOTHOFF_RECEIVER_URL)

        headers = {
            'x-api-key': config.CLOTHOFF_API_KEY,
            'accept': 'application/json'
        }

        # Уведомляем пользователя о начале обработки
        status_message = await update.message.reply_text("⏳ Processing your photo...", reply_to_message_id=message_id)
        # Сохраняем ID статус-сообщения для возможного обновления
        bot_state.pending_requests[id_gen]["status_message_id"] = status_message.message_id


        timeout = aiohttp.ClientTimeout(total=60) # Ставим таймаут на запрос к API
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(config.CLOTHOFF_API_URL, data=data, headers=headers) as response:
                response_text = await response.text()
                logger.debug(f"Clothoff API Raw Response ({response.status}) for id_gen {id_gen}: {response_text}")

                if response.status == 200:
                    logger.info(f"Clothoff API call successful for id_gen {id_gen}. Waiting for webhook.")
                    # Можно обновить статусное сообщение
                    # await context.bot.edit_message_text("Photo sent for processing. Waiting for result...", chat_id=chat_id, message_id=status_message.message_id)
                else:
                    logger.error(f"Clothoff API error for id_gen {id_gen}: Status {response.status}, Response: {response_text}")
                    if id_gen in bot_state.pending_requests: del bot_state.pending_requests[id_gen]
                    await context.bot.edit_message_text(
                        f"❌ API Error: {response.status}. Could not send photo for processing. Details: {response_text[:100]}", # Обрезаем длинные ответы
                        chat_id=chat_id,
                        message_id=status_message.message_id
                    )
                    # await update.message.reply_text(f"API Error: {response.status} - {response_text}", reply_to_message_id=message_id) # Старый вариант

    except aiohttp.ClientError as e:
        logger.error(f"Network error calling Clothoff API for user {user_id} (id_gen: {id_gen}): {e}")
        if id_gen and id_gen in bot_state.pending_requests:
             status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
             if status_message_id:
                  await context.bot.edit_message_text("❌ Network error connecting to processing service.", chat_id=chat_id, message_id=status_message_id)
             del bot_state.pending_requests[id_gen]
        # await update.message.reply_text("Connection error to processing service.", reply_to_message_id=message_id)
    except Exception as e:
        logger.exception(f"Unexpected error in handle_photo for user {user_id} (id_gen: {id_gen}): {e}")
        if id_gen and id_gen in bot_state.pending_requests:
            status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
            if status_message_id:
                 await context.bot.edit_message_text("❌ An unexpected error occurred while processing your request.", chat_id=chat_id, message_id=status_message_id)
            del bot_state.pending_requests[id_gen]
        # await update.message.reply_text("An unexpected error occurred.", reply_to_message_id=message_id)
