import logging
import uuid
from io import BytesIO
import aiohttp
from functools import wraps

from telegram import Update, BotCommand, User
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

import config  # Импортируем конфиг для API ключей и URL
import db      # Импортируем функции для работы с БД
import bot_state # Импортируем глобальное состояние
import keyboards # Импорт клавиатур
from localization import get_text, get_agreement_text # Импорт текстов

logger = logging.getLogger(__name__)

# --- Декоратор для проверки соглашения ---
def require_agreement(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user: # Не должно происходить для обычных команд/сообщений
            return

        user_data = await db.get_or_create_user(user.id, update.effective_chat.id, user.username, user.first_name)

        if not user_data:
            # Ошибка получения данных пользователя
            await update.message.reply_text(get_text("error_getting_user_data", config.DEFAULT_LANGUAGE)) # Отправляем на языке по умолчанию
            return

        if not user_data.get("agreed_to_terms", False):
            # Пользователь не согласился, отправляем сначала выбор языка, потом соглашение
            # Проверяем, есть ли callback_query, чтобы не отправлять снова, если уже идет процесс
            if update.callback_query:
                 # Если это нажатие на кнопку в процессе согласия, даем ему пройти
                 pass
            else:
                await send_agreement_prompt(update, context, user_data)
                return # Останавливаем выполнение оригинальной команды

        # Если согласие есть, добавляем user_data в context для удобства
        context.user_data['db_user'] = user_data
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Вспомогательная функция для отправки запроса на согласие ---
async def send_agreement_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)

    # Шаг 1: Если язык еще не выбран (вдруг такое возможно) - просим выбрать
    # В get_or_create_user мы уже устанавливаем язык по умолчанию, так что этот шаг может быть избыточен,
    # но оставим для надежности или если логика изменится
    if not user_data.get("language"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_text("choose_language", config.DEFAULT_LANGUAGE), # Сначала на языке по умолчанию
            reply_markup=keyboards.get_language_keyboard()
        )
        return

    # Шаг 2: Отправляем текст соглашения и кнопки
    agreement_text = get_agreement_text(user_lang)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{get_text('agreement_prompt', user_lang)}\n\n{agreement_text}",
        reply_markup=keyboards.get_agreement_keyboard(user_lang),
        parse_mode=ParseMode.MARKDOWN # Или HTML, если используете теги
    )

# --- Команды ---
async def setup_bot_commands(context: ContextTypes.DEFAULT_TYPE):
    """Sets the bot commands."""
    await context.bot.set_my_commands([
        BotCommand("start", "Start/Restart the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("settings", "Change language & processing options"),
    ])
    logger.info("Bot commands updated.")

# /start - Не требует декоратора, т.к. сам инициирует процесс согласия
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

    if not user_data:
        await update.message.reply_text(get_text("error_getting_user_data", config.DEFAULT_LANGUAGE))
        return

    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)

    if not user_data.get("agreed_to_terms", False):
        await send_agreement_prompt(update, context, user_data)
    else:
        # Если уже согласился, просто приветствуем
        # Отправляем приветственное изображение
        try:
            with open('images/welcome.png', 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=get_text("start_message", user_lang).format(user_name=user.first_name),
                    parse_mode=ParseMode.MARKDOWN
                )
        except FileNotFoundError:
            logger.error("welcome.png not found. Sending only text message for /start.")
            await update.message.reply_text(
                get_text("start_message", user_lang).format(user_name=user.first_name),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending welcome photo for /start: {e}")
            await update.message.reply_text(
                get_text("start_message", user_lang).format(user_name=user.first_name),
                parse_mode=ParseMode.MARKDOWN
            )

@require_agreement # Теперь /help требует согласия
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lang = context.user_data['db_user'].get("language", config.DEFAULT_LANGUAGE)
    chat_id = update.effective_chat.id # Получаем chat_id
    try:
        with open('images/help.png', 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=get_text("help_message", user_lang),
                parse_mode=ParseMode.MARKDOWN
            )
    except FileNotFoundError:
        logger.error("help.png not found. Sending only text message for /help.")
        await update.message.reply_text(
            get_text("help_message", user_lang),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error sending help photo for /help: {e}")
        await update.message.reply_text(
            get_text("help_message", user_lang),
            parse_mode=ParseMode.MARKDOWN
        )

@require_agreement # Обработка фото требует согласия
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    user_data = context.user_data['db_user'] # Получаем user_data из декоратора
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    user_id = user_data['user_id']
    chat_id = user_data['chat_id']
    message_id = update.message.message_id

    logger.info(f"Processing photo from user_id: {user_id} with lang: {user_lang}")

    photo_file = None
    id_gen = None
    try:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)

        photo_bytes_io = BytesIO()
        await photo_file.download_to_memory(photo_bytes_io)
        photo_bytes_io.seek(0)
        photo_bytes = photo_bytes_io.read()

        if not photo_bytes:
            logger.warning(f"Could not download photo bytes for file_id: {photo.file_id}")
            await update.message.reply_text(get_text("photo_download_error", user_lang), reply_to_message_id=message_id)
            return

        id_gen = str(uuid.uuid4())
        bot_state.pending_requests[id_gen] = {"chat_id": chat_id, "user_id": user_id, "message_id": message_id, "lang": user_lang} # Сохраняем язык
        logger.info(f"Generated id_gen: {id_gen} for user {user_id}. Pending requests: {len(bot_state.pending_requests)}")

        # --- Подготовка данных для API, включая опции ---
        data = aiohttp.FormData()
        data.add_field('image', photo_bytes, filename=f'{id_gen}.jpg', content_type='image/jpeg')
        data.add_field('id_gen', id_gen)
        data.add_field('webhook', config.CLOTHOFF_RECEIVER_URL)

        # Добавляем опции обработки из user_data
        processing_options = user_data.get('processing_options', {})
        api_options_sent = {}
        for key, value in processing_options.items():
            if value: # Добавляем только если значение не пустое/не дефолтное
                data.add_field(key, str(value)) # Убедимся что значение строковое
                api_options_sent[key] = value

        if api_options_sent:
             logger.info(f"Sending processing options for id_gen {id_gen}: {api_options_sent}")

        headers = {'x-api-key': config.CLOTHOFF_API_KEY, 'accept': 'application/json'}

        status_message = await update.message.reply_text(get_text("processing_photo", user_lang), reply_to_message_id=message_id)
        bot_state.pending_requests[id_gen]["status_message_id"] = status_message.message_id

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(config.CLOTHOFF_API_URL, data=data, headers=headers) as response:
                response_text = await response.text()
                logger.debug(f"Clothoff API Raw Response ({response.status}) for id_gen {id_gen}: {response_text}")

                if response.status == 200:
                    logger.info(f"Clothoff API call successful for id_gen {id_gen}. Waiting for webhook.")
                    # Можно обновить статус
                    # await context.bot.edit_message_text(get_text("photo_sent_for_processing", user_lang), chat_id=chat_id, message_id=status_message.message_id)
                else:
                    logger.error(f"Clothoff API error for id_gen {id_gen}: Status {response.status}, Response: {response_text}")
                    if id_gen in bot_state.pending_requests: del bot_state.pending_requests[id_gen]
                    error_details = response_text[:100] # Обрезаем длинный ответ
                    await context.bot.edit_message_text(
                        get_text("api_error", user_lang).format(status=response.status, details=error_details),
                        chat_id=chat_id,
                        message_id=status_message.message_id
                    )

    except aiohttp.ClientError as e:
        logger.error(f"Network error calling Clothoff API for user {user_id} (id_gen: {id_gen}): {e}")
        if id_gen and id_gen in bot_state.pending_requests:
             status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
             if status_message_id:
                  await context.bot.edit_message_text(get_text("network_error", user_lang), chat_id=chat_id, message_id=status_message_id)
             del bot_state.pending_requests[id_gen]
    except Exception as e:
        logger.exception(f"Unexpected error in handle_photo for user {user_id} (id_gen: {id_gen}): {e}")
        if id_gen and id_gen in bot_state.pending_requests:
            status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
            if status_message_id:
                 await context.bot.edit_message_text(get_text("unexpected_processing_error", user_lang), chat_id=chat_id, message_id=status_message_id)
            del bot_state.pending_requests[id_gen]

# --- Настройки ---
@require_agreement
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data['db_user']
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    current_options = user_data.get("processing_options", {})
    chat_id = update.effective_chat.id # Получаем chat_id

    text = f"{get_text('settings_title', user_lang)}\n\n"
    # Можно добавить отображение текущих настроек текстом, но клавиатура уже показывает их
    # text += f"{get_text('settings_current_options', user_lang)}\n"
    # for key, value in current_options.items():
    #      if value:
    #          text += f"- {get_text(f'option_{key}', user_lang)}: {value}\n"

    text += get_text("settings_choose_option", user_lang)

    try:
        with open('images/settings.png', 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
            )
    except FileNotFoundError:
        logger.error("settings.png not found. Sending only text message for /settings.")
        await update.message.reply_text(
            text=text,
            reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
        )
    except Exception as e:
        logger.error(f"Error sending settings photo for /settings: {e}")
        await update.message.reply_text(
            text=text,
            reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
        )

# --- Обработчик Callback Query (нажатия кнопок) ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Обязательно отвечаем на callback

    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    callback_data = query.data

    logger.info(f"Callback query received from user {user.id}: {callback_data}")

    # Получаем данные пользователя (не используем декоратор тут, т.к. часть кнопок - до соглашения)
    user_data = await db.get_or_create_user(user.id, chat_id, user.username, user.first_name)
    if not user_data:
        await context.bot.send_message(chat_id, get_text("error_getting_user_data", config.DEFAULT_LANGUAGE))
        return

    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    current_options = user_data.get("processing_options", {})

    # --- Логика обработки разных callback_data ---

    # 1. Выбор языка
    if callback_data.startswith("set_lang:"):
        new_lang = callback_data.split(":")[1]
        if new_lang in config.SUPPORTED_LANGUAGES:
            updated = await db.update_user_data(user.id, {"language": new_lang})
            if updated:
                user_lang = new_lang # Обновляем язык для дальнейших сообщений
                # Если пользователь еще не согласился, показываем соглашение на новом языке
                if not user_data.get("agreed_to_terms"):
                    agreement_text = get_agreement_text(user_lang)
                    try:
                        await query.edit_message_text(
                            text=f"{get_text('agreement_prompt', user_lang)}\n\n{agreement_text}",
                            reply_markup=keyboards.get_agreement_keyboard(user_lang),
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except BadRequest as e:
                        if "Message is not modified" not in str(e): raise e
                        logger.debug("Agreement message not modified.")
                else:
                    # Если уже согласился, просто уведомляем о смене языка и возвращаемся в настройки
                    await context.bot.send_message(chat_id, get_text("language_set", user_lang))
                    # Обновляем меню настроек
                    await query.edit_message_text(
                        text=get_text("settings_choose_option", user_lang),
                        reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
                     )

            else:
                 await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))
        else:
            logger.warning(f"Unsupported language code received: {new_lang}")

    # 2. Соглашение
    elif callback_data.startswith("accept_terms:"):
        updated = await db.update_user_data(user.id, {"agreed_to_terms": True})
        if updated:
            await query.edit_message_text(text=get_text("agreement_accepted", user_lang))
        else:
            await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))

    elif callback_data.startswith("decline_terms:"):
        await query.edit_message_text(text=get_text("agreement_declined", user_lang))

    # --- Обработка настроек (требует согласия, но проверка уже в /settings) ---
    elif callback_data.startswith("show_settings_option:"):
        option_key = callback_data.split(":")[1]
        option_name = get_text(f"option_{option_key}", user_lang)
        current_value = user_data.get("language") if option_key == 'language' else current_options.get(option_key, "")

        try:
            await query.edit_message_text(
                text=get_text("choose_value_for", user_lang).format(option_name=option_name),
                reply_markup=keyboards.get_option_value_keyboard(option_key, user_lang, current_value)
            )
        except BadRequest as e:
             if "Message is not modified" not in str(e): raise e
             logger.debug(f"Settings option '{option_key}' view not modified.")


    elif callback_data.startswith("set_setting:"):
        parts = callback_data.split(":", 2)
        option_key = parts[1]
        new_value = parts[2] # Может быть пустой строкой для сброса

        # Обновляем вложенный map processing_options
        current_options[option_key] = new_value
        updated = await db.update_user_data(user.id, {"processing_options": current_options})

        if updated:
            option_name = get_text(f"option_{option_key}", user_lang)
            display_value = new_value if new_value else get_text("value_not_set", user_lang)
            # Уведомляем об обновлении
            await context.bot.send_message(chat_id, get_text("setting_updated", user_lang).format(option_name=option_name, value=display_value))
            # Возвращаемся в главное меню настроек
            try:
                await query.edit_message_text(
                    text=get_text("settings_choose_option", user_lang),
                    reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options) # Передаем обновленные опции
                )
            except BadRequest as e:
                 if "Message is not modified" not in str(e): raise e
                 logger.debug("Settings main menu not modified after update.")
        else:
             await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))


    elif callback_data == "back_to_settings:main":
         try:
            await query.edit_message_text(
                text=get_text("settings_choose_option", user_lang),
                reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
            )
         except BadRequest as e:
             if "Message is not modified" not in str(e): raise e
             logger.debug("Back to settings main menu - message not modified.")

    else:
        logger.warning(f"Unhandled callback_data: {callback_data}")
