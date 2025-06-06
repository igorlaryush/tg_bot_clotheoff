import logging
import uuid
from io import BytesIO
import aiohttp
from functools import wraps

from telegram import Update, BotCommand, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

import config  # Импортируем конфиг для API ключей и URL
import db      # Импортируем функции для работы с БД
import bot_state # Импортируем глобальное состояние
import keyboards # Импорт клавиатур
from localization import get_text, get_agreement_text # Импорт текстов
import payments  # Импортируем модуль для работы с платежами

logger = logging.getLogger(__name__)

# --- Декоратор для проверки соглашения ---
def require_agreement(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        user_data = await db.get_or_create_user(user.id, update.effective_chat.id, user.username, user.first_name)

        if not user_data:
            user_tg_lang = user.language_code if user.language_code in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE
            # Send to update.message or update.callback_query.message depending on context
            target_message = update.callback_query.message if update.callback_query else update.message
            await target_message.reply_text(get_text("error_getting_user_data", user_tg_lang))
            return

        if not user_data.get("agreed_to_terms", False):
            # User has not agreed. Prompt for language first, then agreement.
            initial_prompt_lang = user_data.get("language") or (user.language_code if user.language_code in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE)
            
            # Determine where to send the message (reply to command or edit callback message)
            if update.callback_query:
                # If triggered by a callback from a user not yet agreed (e.g. trying to access settings via old button)
                await update.callback_query.message.edit_text(
                    text=get_text("choose_language", initial_prompt_lang),
                    reply_markup=keyboards.get_language_keyboard()
                )
            else:
                # If triggered by a command (e.g. /settings)
                await update.message.reply_text(
                    text=get_text("choose_language", initial_prompt_lang),
                    reply_markup=keyboards.get_language_keyboard()
                )
            context.user_data['initial_lang_selection'] = True # Signal to callback_handler
            return # Stop original command/callback

        # Если согласие есть, добавляем user_data в context для удобства
        context.user_data['db_user'] = user_data
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Вспомогательная функция для отправки запроса на согласие ---
async def send_agreement_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)

    # Шаг 1: Больше не нужен, так как start теперь всегда предлагает выбор языка сначала.
    # if not user_data.get("language"):
    #     await context.bot.send_message(
    #         chat_id=chat_id,
    #         text=get_text("choose_language", config.DEFAULT_LANGUAGE), # Сначала на языке по умолчанию
    #         reply_markup=keyboards.get_language_keyboard()
    #     )
    #     return

    # Шаг 2: Отправляем текст соглашения и кнопки
    logger.info(f"Sending agreement prompt to user {user.id} in lang {user_lang}")
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
        BotCommand("balance", "Check balance and buy photos"),
    ])
    logger.info("Bot commands updated.")

# /start - Не требует декоратора, т.к. сам инициирует процесс согласия
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # --- Извлечение параметра start ---
    source_param = None
    if context.args:
        source_param = context.args[0]
        logger.info(f"Received /start from user_id: {user.id} in chat_id: {chat_id} with source_param: {source_param}")
    else:
        logger.info(f"Received /start from user_id: {user.id} in chat_id: {chat_id} (no source_param)")
    
    user_source = source_param if source_param else "organic"
    # --- Конец извлечения параметра start ---

    user_data = await db.get_or_create_user(
        user_id=user.id,
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name,
        source=user_source # <--- Передаем источник
    )

    if not user_data:
        user_tg_lang = user.language_code if user.language_code in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE
        await update.message.reply_text(get_text("error_getting_user_data", user_tg_lang))
        return

    if not user_data.get("agreed_to_terms", False):
        # User has not agreed. Prompt for language first.
        # The text "choose_language" should be available in default languages.
        # We use a neutral or default language for this very first prompt.
        initial_prompt_lang = config.DEFAULT_LANGUAGE 
        # Or, try user's Telegram client language if available for the prompt itself
        if user.language_code in config.SUPPORTED_LANGUAGES:
            initial_prompt_lang = user.language_code

        await context.bot.send_message(
            chat_id=chat_id,
            text=get_text("choose_language", initial_prompt_lang), # Prompt in a neutral/default lang
            reply_markup=keyboards.get_language_keyboard() # Buttons "English", "Русский"
        )
        # Set a flag that we are in the initial language selection phase
        context.user_data['initial_lang_selection'] = True
    else:
        # User has agreed. Send welcome message in their stored language.
        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        welcome_message_text = get_text("start_message", user_lang).format(user_name=user.first_name)
        try:
            with open('images/welcome.png', 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=welcome_message_text,
                    parse_mode=ParseMode.MARKDOWN
                )
        except FileNotFoundError:
            import os
            current_dir = os.getcwd()
            logger.info(f"Current working directory: {current_dir}")
            
            # List all files in current directory
            files = os.listdir(current_dir)
            logger.info(f"Files in current directory: {files}")
            
            # Check if images directory exists and list its contents
            images_dir = os.path.join(current_dir, 'images')
            if os.path.exists(images_dir):
                image_files = os.listdir(images_dir)
                logger.info(f"Files in images directory: {image_files}")
            else:
                logger.error("Images directory not found")
            logger.error("welcome.png not found. Sending only text message for /start.")
            await update.message.reply_text(welcome_message_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error sending welcome photo for /start: {e}")
            await update.message.reply_text(welcome_message_text, parse_mode=ParseMode.MARKDOWN)

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

    # Проверяем баланс пользователя
    current_balance = await db.get_user_photos_balance(user_id)
    if current_balance < 1:
        # Недостаточно средств - показываем сообщение и предлагаем купить
        await update.message.reply_text(
            get_text("insufficient_balance", user_lang).format(needed=1, current=current_balance),
            reply_markup=keyboards.get_payment_packages_keyboard(user_lang),
            reply_to_message_id=message_id
        )
        # Логируем попытку генерации при недостаточном балансе
        await db.log_user_event(user_id, "generation_attempt_insufficient_balance", {"current_balance": current_balance})
        return

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

        # Списываем фото с баланса перед отправкой на обработку
        deduct_success = await db.deduct_user_photos(user_id, 1)
        if not deduct_success:
            logger.error(f"Failed to deduct photo from user {user_id} balance")
            await update.message.reply_text(get_text("error_occurred", user_lang), reply_to_message_id=message_id)
            return

        id_gen = str(uuid.uuid4())
        bot_state.pending_requests[id_gen] = {"chat_id": chat_id, "user_id": user_id, "message_id": message_id, "lang": user_lang} # Сохраняем язык
        logger.info(f"Generated id_gen: {id_gen} for user {user_id}. Pending requests: {len(bot_state.pending_requests)}")

        # Логируем событие начала генерации
        await db.log_user_event(user_id, "generation_requested", {"id_gen": id_gen})

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
                logger.debug(f"API Raw Response ({response.status}) for id_gen {id_gen}: {response_text[:500]}") # Log first 500 chars

                if response.status == 200:
                    logger.info(f"API call successful for id_gen {id_gen}. Waiting for webhook.")
                    # Статус не меняем, пользователь ждет результат. pending_requests очистится в queue_processor
                else: # API ответило с ошибкой
                    logger.error(f"API error for id_gen {id_gen}: Status {response.status}, Response: {response_text[:200]}")
                    await db.add_user_photos(user_id, 1) # Возвращаем фото
                    if id_gen in bot_state.pending_requests: del bot_state.pending_requests[id_gen]
                    
                    error_details = response_text[:100] 
                    # status_message должно быть определено здесь, т.к. API вызов был сделан
                    await context.bot.edit_message_text(
                        get_text("api_error", user_lang).format(status=response.status, details=error_details),
                        chat_id=chat_id,
                        message_id=status_message.message_id
                    )
                    return # Завершаем обработку здесь, т.к. ошибка API обработана

    except aiohttp.ClientError as e: # Сетевая ошибка (таймаут, недоступность сервера и т.д.)
        logger.error(f"API request ClientError for user {user_id}, id_gen {id_gen if id_gen else 'N/A'}: {e}")
        # Фото было списано до этого блока try-except (если id_gen существует)
        if id_gen: # Если id_gen был сгенерирован, значит фото списано
            await db.add_user_photos(user_id, 1) 
            status_message_id_to_edit = None
            if id_gen in bot_state.pending_requests:
                status_message_id_to_edit = bot_state.pending_requests[id_gen].get("status_message_id")
                del bot_state.pending_requests[id_gen]
            
            if status_message_id_to_edit:
                await context.bot.edit_message_text(
                    get_text("network_error", user_lang), 
                    chat_id=chat_id, 
                    message_id=status_message_id_to_edit
                )
            else: # Сообщение "в обработке" не было отправлено или не найдено, но ошибка произошла
                await update.message.reply_text(get_text("network_error", user_lang), reply_to_message_id=message_id)
        else: # Ошибка произошла до генерации id_gen и списания фото (маловероятно здесь, но для полноты)
            await update.message.reply_text(get_text("network_error", user_lang), reply_to_message_id=message_id)
        return

    except Exception as e: # Любая другая непредвиденная ошибка
        logger.exception(f"Unexpected error in photo handling for user {user_id}, id_gen {id_gen if id_gen else 'N/A'}: {e}")
        if id_gen: # Если id_gen был сгенерирован, значит фото списано
            await db.add_user_photos(user_id, 1)
            status_message_id_to_edit = None
            if id_gen in bot_state.pending_requests:
                status_message_id_to_edit = bot_state.pending_requests[id_gen].get("status_message_id")
                del bot_state.pending_requests[id_gen]

            if status_message_id_to_edit:
                await context.bot.edit_message_text(
                    get_text("unexpected_processing_error", user_lang), 
                    chat_id=chat_id, 
                    message_id=status_message_id_to_edit
                )
            else: # Сообщение "в обработке" не было отправлено или не найдено
                 await update.message.reply_text(get_text("unexpected_processing_error", user_lang), reply_to_message_id=message_id)
        else: # Ошибка до id_gen
            await update.message.reply_text(get_text("unexpected_processing_error", user_lang), reply_to_message_id=message_id)
        return

# --- Настройки ---
@require_agreement
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data['db_user']
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    current_options = user_data.get("processing_options", {})
    # chat_id = update.effective_chat.id # No longer needed directly here as we use update.message.reply_text

    text = f"{get_text('settings_title', user_lang)}\n\n"
    text += get_text("settings_choose_option", user_lang)

    # try:
    #     with open('images/settings.png', 'rb') as photo:
    #         await context.bot.send_photo(
    #             chat_id=chat_id,
    #             photo=photo,
    #             caption=text,
    #             reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
    #         )
    # except FileNotFoundError:
    #     logger.error("settings.png not found. Sending only text message for /settings.")
    #     await update.message.reply_text(
    #         text=text,
    #         reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
    #     )
    # except Exception as e:
    #     logger.error(f"Error sending settings photo for /settings: {e}")
    #     await update.message.reply_text(
    #         text=text,
    #         reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
    #     )
    
    await update.message.reply_text(
        text=text,
        reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
    )

# --- Обработчик Callback Query (нажатия кнопок) ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat_id = update.effective_chat.id
    callback_data = query.data

    logger.debug(f"Callback query received from user {user.id} in chat {chat_id}: {callback_data}")

    user_data = await db.get_or_create_user(user.id, chat_id, user.username, user.first_name)
    if not user_data:
        user_tg_lang = user.language_code if user.language_code in config.SUPPORTED_LANGUAGES else config.DEFAULT_LANGUAGE
        await query.edit_message_text(get_text("error_getting_user_data", user_tg_lang))
        return

    current_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    initial_selection_phase = context.user_data.pop('initial_lang_selection', False) # Check and clear flag

    # --- Language Selection (set_lang:en, set_lang:ru) ---
    if callback_data.startswith("set_lang:"):
        chosen_lang = callback_data.split(":")[1]
        
        # Update language in DB and local user_data
        if chosen_lang != user_data.get("language"):
            success = await db.update_user_data(user.id, {"language": chosen_lang})
            if success:
                user_data["language"] = chosen_lang
                current_lang = chosen_lang # Update for current context
                await query.edit_message_text(get_text("language_set", chosen_lang))
            else:
                await query.edit_message_text(get_text("error_occurred", current_lang))
                # Re-set flag if DB update failed during initial phase to allow retry
                if initial_selection_phase:
                     context.user_data['initial_lang_selection'] = True
                return
        else:
            # Language already set to this, just edit message to confirm and remove old keyboard
            await query.edit_message_text(get_text("language_set", chosen_lang))

        if initial_selection_phase:
            # Coming from /start, now show agreement in chosen language
            await send_agreement_prompt(update, context, user_data)
        else:
            # Language changed from settings. The settings menu should be refreshed by user action (e.g. "Back" button)
            # or specific logic in settings flow if message needs to be auto-updated.
            # For now, just confirming the language set is sufficient here.
            # The 'show_settings_option:language' will display choices, and its 'Back' button handles return.
            pass
        return

    # --- Agreement Handling (accept_terms:true, decline_terms:true) ---
    elif callback_data.startswith("accept_terms:"): # Handles "accept_terms:true"
        # Language should have been set by the 'set_lang:' callback if it was initial_selection_phase
        # or already be in user_data if user is revisiting.
        lang_to_save = user_data.get("language", config.DEFAULT_LANGUAGE) # Ensure we have a lang to save

        success = await db.update_user_data(user.id, {"agreed_to_terms": True, "language": lang_to_save})
        if success:
            user_data["agreed_to_terms"] = True # Update local copy
            await query.edit_message_text(get_text("agreement_accepted", lang_to_save))
            
            welcome_message_text = get_text("start_message", lang_to_save).format(user_name=user.first_name)
            try:
                with open('images/welcome.png', 'rb') as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=welcome_message_text, parse_mode=ParseMode.MARKDOWN)
            except FileNotFoundError:
                logger.error("welcome.png not found. Sending text message after agreement.")
                await context.bot.send_message(chat_id=chat_id, text=welcome_message_text, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Error sending welcome photo after agreement: {e}")
                await context.bot.send_message(chat_id=chat_id, text=welcome_message_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text(get_text("error_occurred", lang_to_save))
        return

    elif callback_data.startswith("decline_terms:"): # Handles "decline_terms:true"
        lang_to_save = user_data.get("language", config.DEFAULT_LANGUAGE)
        # User declined. We don't necessarily need to change their chosen language.
        await db.update_user_data(user.id, {"agreed_to_terms": False}) # Explicitly set to false
        await query.edit_message_text(get_text("agreement_declined", lang_to_save))
        return

    # --- All subsequent callbacks require agreement ---
    if not user_data.get("agreed_to_terms", False):
        # If user tries to interact with other buttons without agreeing
        await query.message.reply_text(get_text("must_accept_agreement", current_lang))
        # Optionally, redirect to start or resend language/agreement prompt
        # For now, just a message. The decorator on commands handles command access.
        return

    # --- Agreement is True, proceed with other callbacks ---
    context.user_data['db_user'] = user_data # For require_agreement decorator and other handlers
    current_options = user_data.get("processing_options", {})

    # --- Payment Callbacks Handling (Example, ensure your function exists and is called correctly) ---
    payment_callbacks_prefixes = ("buy_package:", "confirm_purchase:", "payment_history_page:")
    payment_callbacks_exact = ["show_packages", "show_balance", "show_payment_history", "cancel_payment", "back_to_main"]
    if callback_data.startswith(payment_callbacks_prefixes) or callback_data in payment_callbacks_exact:
        if hasattr(payments, 'handle_payment_callbacks'): # Assuming you might move this
             await payments.handle_payment_callbacks(update, context, callback_data, user_data, query)
        else: # Fallback to local one if not moved
             await handle_payment_callbacks(update, context, callback_data, user_data, query)
        return


    # --- Settings Callbacks Handling (Linter errors addressed here) ---
    if callback_data == "back_to_settings:main" or callback_data == "settings_main": # Added settings_main for direct entry if used
        await query.edit_message_text(
            text=get_text("settings_choose_option", current_lang),
            reply_markup=keyboards.get_settings_main_keyboard(current_lang, current_options)
        )
    elif callback_data.startswith("show_settings_option:"):
        option_key = callback_data.split(":")[1]
        option_name_display = get_text(f"option_{option_key}", current_lang)
        
        value_for_keyboard = current_options.get(option_key, "")
        if option_key == 'language':
             value_for_keyboard = current_lang # For language, current_value is the current language

        await query.edit_message_text(
            text=get_text("choose_value_for", current_lang).format(option_name=option_name_display),
            reply_markup=keyboards.get_option_value_keyboard(option_key, current_lang, value_for_keyboard) # Corrected function name
        )
    
    elif callback_data.startswith("set_setting:"): # For general settings, not language
        parts = callback_data.split(":", 2)
        option_key = parts[1]
        new_value_str = parts[2]

        current_options[option_key] = new_value_str
        
        success = await db.update_user_data(user.id, {"processing_options": current_options})
        if success:
            user_data["processing_options"] = current_options # Update local
            confirm_text = get_text("setting_updated", current_lang).format(
                option_name=get_text(f"option_{option_key}", current_lang), 
                value=new_value_str if new_value_str else get_text("value_not_set", current_lang)
            )
            # Refresh main settings view
            await query.edit_message_text(
                text=f"{confirm_text}\n\n{get_text('settings_choose_option', current_lang)}",
                reply_markup=keyboards.get_settings_main_keyboard(current_lang, current_options)
            )
        else:
            await query.edit_message_text(get_text("error_occurred", current_lang))
    
    # Removed "reset_all_settings" as it was causing linter errors with get_settings_main_keyboard
    # and its direct implementation needs review based on how PROCESSING_OPTIONS defaults are handled.
    # A "reset to default" for each option is present in get_option_value_keyboard (empty value).
    # If a global reset is needed, it should pass current_options={} to get_settings_main_keyboard.
    # For example, a new callback "reset_all_processing_options" could do:
    # current_options = {}
    # await db.update_user_data(user.id, {"processing_options": current_options})
    # await query.edit_message_text(text=..., reply_markup=keyboards.get_settings_main_keyboard(current_lang, current_options))

    else:
        logger.warning(f"Unhandled agreed callback_data: {callback_data} from user {user.id}")

# === Команды и обработчики для платежей ===

@require_agreement
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает баланс пользователя и опции покупки."""
    user_data = context.user_data['db_user']
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    user_id = user_data['user_id']
    chat_id = update.effective_chat.id

    # Получаем текущий баланс
    current_balance = await db.get_user_photos_balance(user_id)
    
    text = f"{get_text('balance_title', user_lang)}\n\n"
    text += get_text('current_balance', user_lang).format(balance=current_balance)

    try:
        with open('images/balance.png', 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                reply_markup=keyboards.get_balance_keyboard(user_lang)
            )
    except FileNotFoundError:
        logger.error("balance.png not found. Sending only text message for /balance.")
        await update.message.reply_text(
            text=text,
            reply_markup=keyboards.get_balance_keyboard(user_lang)
        )
    except Exception as e:
        logger.error(f"Error sending balance photo for /balance: {e}")
        await update.message.reply_text(
            text=text,
            reply_markup=keyboards.get_balance_keyboard(user_lang)
        )

async def handle_payment_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str, user_data: dict, query):
    """Обрабатывает callback'и связанные с платежами."""
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    user_id = user_data['user_id']
    chat_id = query.message.chat_id

    # Показать пакеты для покупки
    if callback_data == "show_packages":
        text = get_text("choose_package", user_lang)
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=keyboards.get_payment_packages_keyboard(user_lang)
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e): raise e

    # Выбор конкретного пакета
    elif callback_data.startswith("buy_package:"):
        package_id = callback_data.split(":")[1]
        package_info = payments.get_package_info(package_id, user_lang)
        
        if package_info:
            # Логируем событие инициации платежа
            await db.log_user_event(user_id, "payment_initiated", {
                "package_id": package_id,
                "package_name": package_info.get('name'),
                "package_price": package_info.get('price'),
                "package_photos": package_info.get('photos')
            })

            text = get_text("package_details", user_lang).format(
                name=package_info['name'],
                description=package_info['description'],
                photos=package_info['photos'],
                price=package_info['price']
            )
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=keyboards.get_payment_confirmation_keyboard(package_id, user_lang),
                    parse_mode=ParseMode.MARKDOWN
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e): raise e
        else:
            await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))

    # Подтверждение покупки
    elif callback_data.startswith("confirm_purchase:"):
        package_id = callback_data.split(":")[1]
        package_info = payments.get_package_info(package_id, user_lang)
        
        if not package_info:
            await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))
            return

        # Показываем сообщение о создании платежа
        await query.edit_message_text(text=get_text("creating_payment", user_lang))
        
        # Создаем заказ на оплату
        order_data = await payments.create_payment_order(user_id, package_id)
        
        if order_data:
            # Успешно создали заказ - показываем ссылку на оплату
            text = get_text("payment_link_created", user_lang).format(
                package_name=package_info['name'],
                amount=package_info['price']
            )
            
            keyboard = [[InlineKeyboardButton(
                get_text("pay_now", user_lang),
                url=order_data['pay_url']
            )]]
            
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Ошибка создания заказа
            await query.edit_message_text(text=get_text("payment_error", user_lang))

    # Показать баланс
    elif callback_data == "show_balance":
        current_balance = await db.get_user_photos_balance(user_id)
        text = f"{get_text('balance_title', user_lang)}\n\n"
        text += get_text('current_balance', user_lang).format(balance=current_balance)
        
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=keyboards.get_balance_keyboard(user_lang)
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e): raise e

    # Показать историю платежей
    elif callback_data == "show_payment_history" or callback_data.startswith("payment_history_page:"):
        page = 0
        if callback_data.startswith("payment_history_page:"):
            page = int(callback_data.split(":")[1])
        
        orders = await db.get_user_payment_history(user_id, limit=5)
        
        if not orders:
            text = get_text("no_payment_history", user_lang)
        else:
            text = f"{get_text('payment_history', user_lang)}\n\n"
            
            for order in orders:
                package_info = payments.get_package_info(order['package_id'], user_lang)
                package_name = package_info['name'] if package_info else order['package_id']
                
                # Форматируем статус
                status_key = f"payment_status_{order['status']}"
                status_text = get_text(status_key, user_lang)
                
                # Форматируем дату
                created_at = order.get('created_at')
                date_str = created_at.strftime('%d.%m.%Y') if created_at else "N/A"
                
                text += get_text("payment_history_item", user_lang).format(
                    package_name=package_name,
                    amount=order['amount'],
                    status=status_text,
                    date=date_str
                ) + "\n\n"
        
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=keyboards.get_payment_history_keyboard(user_lang, page)
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e): raise e

    # Отмена платежа
    elif callback_data == "cancel_payment":
        await query.edit_message_text(text=get_text("payment_cancelled", user_lang))

    # Возврат в главное меню
    elif callback_data == "back_to_main":
        await query.delete_message()

    return True  # Указываем, что callback был обработан

async def notify_payment_success(user_id: int, package_name: str, photos_added: int, new_balance: int):
    """Уведомляет пользователя об успешном платеже."""
    try:
        # Получаем данные пользователя для языка и chat_id
        user_data = await db.get_or_create_user(user_id, None, None, None)  # chat_id будет обновлен из существующих данных
        if not user_data:
            logger.error(f"Cannot notify user {user_id} about payment success - user data not found")
            return

        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        chat_id = user_data.get("chat_id")
        
        if chat_id is None:
            logger.error(f"Cannot notify user {user_id} about payment success - chat_id not found")
            return

        text = get_text("payment_success", user_lang).format(
            package_name=package_name,
            photos=photos_added,
            new_balance=new_balance
        )

        # Логируем успешный платеж перед отправкой уведомления
        await db.log_user_event(user_id, "payment_successful", {
            "package_name": package_name,
            "photos_added": photos_added,
            "new_balance_after_payment": new_balance
        })

        # Сохраняем уведомление в bot_state для отправки через основной цикл
        notification_data = {
            "type": "payment_success",
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text
        }
        
        # Добавляем в очередь уведомлений (нужно будет создать эту очередь в bot_state)
        if hasattr(bot_state, 'notifications_queue'):
            try:
                bot_state.notifications_queue.put_nowait(notification_data)
                logger.info(f"Payment success notification queued for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to queue payment notification for user {user_id}: {e}")
        else:
            logger.warning("Notifications queue not available - payment notification not sent")
        
    except Exception as e:
        logger.error(f"Failed to prepare payment notification for user {user_id}: {e}")
