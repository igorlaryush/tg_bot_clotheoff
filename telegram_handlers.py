import logging
import uuid
from io import BytesIO
import aiohttp
from functools import wraps
from datetime import datetime

from telegram import Update, BotCommand, User, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
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

        # Send the persistent reply keyboard ONCE.
        if not user_data.get("reply_keyboard_set"):
            await context.bot.send_message(
                chat_id=chat_id,
                text=get_text("menu_activated", user_lang),
                reply_markup=keyboards.get_main_reply_keyboard(user_lang)
            )
            await db.update_user_data(user.id, {"reply_keyboard_set": True})

        current_balance = await db.get_user_photos_balance(user.id)
        
        welcome_message_text = get_text("start_message", user_lang).format(
            user_name=user.first_name,
            balance=current_balance
        )
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_message_text,
            reply_markup=keyboards.get_start_keyboard(user_lang),
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

@require_agreement
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles an incoming photo by starting a configuration session.
    The actual processing is triggered by a callback button.
    """
    if not update.message.photo:
        return

    # If there's already a photo session, cancel it before starting a new one.
    if 'pending_photo_session' in context.user_data:
        try:
            config_message_id = context.user_data['pending_photo_session'].get('config_message_id')
            if config_message_id:
                user_lang_old = context.user_data['db_user'].get("language", config.DEFAULT_LANGUAGE)
                await context.bot.edit_message_text(
                    text=get_text("photo_processing_cancelled", user_lang_old),
                    chat_id=update.effective_chat.id,
                    message_id=config_message_id,
                    reply_markup=None
                )
        except Exception as e:
            logger.warning(f"Could not edit old config message on new photo upload: {e}")
        finally:
            del context.user_data['pending_photo_session']

    user_data = context.user_data['db_user']
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    user_id = user_data['user_id']
    message_id = update.message.message_id

    # Check balance before even starting configuration
    current_balance = await db.get_user_photos_balance(user_id)
    if current_balance < 1:
        await update.message.reply_text(
            get_text("insufficient_balance", user_lang).format(needed=1, current=current_balance),
            reply_markup=keyboards.get_payment_packages_keyboard(user_lang),
            reply_to_message_id=message_id
        )
        await db.log_user_event(user_id, "generation_attempt_insufficient_balance", {"current_balance": current_balance})
        return

    # Store photo info and initialize empty settings for this session
    photo = update.message.photo[-1]
    context.user_data['pending_photo_session'] = {
        'file_id': photo.file_id,
        'message_id': message_id,
        'settings': {},
        'config_message_id': None, # To be stored after sending the keyboard
        'is_photo_message': True   # Flag to indicate the config message has a photo
    }

    logger.info(f"Starting photo configuration session for user {user_id}")

    # Send the configuration keyboard
    try:
        with open('images/configure_photo.jpg', 'rb') as photo_to_send:
            config_message = await update.message.reply_photo(
                photo=photo_to_send,
                caption=get_text("configure_photo_settings_title", user_lang),
                reply_markup=keyboards.get_photo_settings_keyboard(user_lang, {}),
                parse_mode=ParseMode.MARKDOWN
            )
    except FileNotFoundError:
        logger.warning("configure_photo.jpg not found. Sending text-only config message.")
        config_message = await update.message.reply_text(
            text=get_text("configure_photo_settings_title", user_lang),
            reply_markup=keyboards.get_photo_settings_keyboard(user_lang, {}),
            parse_mode=ParseMode.MARKDOWN
        )
    # Save the message ID of the configuration menu so we can edit it
    context.user_data['pending_photo_session']['config_message_id'] = config_message.message_id

# --- Обработчик всех inline-кнопок ---
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

    # --- Photo Configuration Flow ---
    if callback_data.startswith("photo_"):
        if 'pending_photo_session' not in context.user_data:
            await query.edit_message_text(get_text("error_occurred", current_lang))
            logger.warning(f"User {user.id} interacted with a photo callback, but no session was found.")
            return
        
        session = context.user_data['pending_photo_session']
        current_settings = session.get('settings', {})
        action, *params = callback_data.split(':')

        async def edit_or_replace(text, reply_markup, parse_mode=None):
            """Deletes the photo message and sends a new text one on first interaction."""
            if session.get('is_photo_message'):
                await query.delete_message()
                new_message = await context.bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode
                )
                session['config_message_id'] = new_message.message_id
                session['is_photo_message'] = False
            else:
                try:
                    await query.edit_message_text(
                        text=text, reply_markup=reply_markup, parse_mode=parse_mode
                    )
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass # Ignore if the message content is the same
                    else:
                        logger.error(f"Failed to edit photo config message: {e}")
                        raise e

        if action == "photo_submenu":
            submenu_key = params[0]
            if submenu_key == "appearance":
                await edit_or_replace(
                    text=get_text("settings_appearance_intro", current_lang),
                    reply_markup=keyboards.get_photo_appearance_settings_keyboard(current_lang, current_settings)
                )

        elif action == "photo_option":
            option_key = params[0]
            await edit_or_replace(
                text=get_text("select_option_title", current_lang).format(option_name=get_text(f"option_{option_key}", current_lang)),
                reply_markup=keyboards.get_photo_option_value_keyboard(option_key, current_lang, current_settings),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "photo_set":
            option_key, value = params
            
            # If the user clicks the same option, un-set it. Otherwise, set it.
            if current_settings.get(option_key) == value:
                current_settings.pop(option_key, None)
            else:
                current_settings[option_key] = value

            if option_key in keyboards.APPEARANCE_OPTIONS:
                # Return to the appearance submenu
                await edit_or_replace(
                    text=get_text("settings_appearance_intro", current_lang),
                    reply_markup=keyboards.get_photo_appearance_settings_keyboard(current_lang, current_settings)
                )
            else:
                # Re-render the same value selection screen to show the updated checkmark
                await edit_or_replace(
                    text=get_text("select_option_title", current_lang).format(option_name=get_text(f"option_{option_key}", current_lang)),
                    reply_markup=keyboards.get_photo_option_value_keyboard(option_key, current_lang, current_settings),
                    parse_mode=ParseMode.MARKDOWN,
                )

        elif action == "photo_back":
            target_menu = params[0]
            if target_menu == "main":
                await edit_or_replace(
                    text=get_text("configure_photo_settings_title", current_lang),
                    reply_markup=keyboards.get_photo_settings_keyboard(current_lang, current_settings),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif target_menu == "appearance":
                 await edit_or_replace(
                    text=get_text("settings_appearance_intro", current_lang),
                    reply_markup=keyboards.get_photo_appearance_settings_keyboard(current_lang, current_settings)
                )
        
        elif action == "photo_action":
            sub_action = params[0]
            if sub_action == "process":
                # Delete the configuration message
                await query.delete_message()
                # Run the processing logic
                await _execute_photo_processing(update, context, current_settings)
        return

    # --- Upload Photo Prompt ---
    if callback_data == "show_upload_prompt":
        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        
        try:
            with open('images/upload_guide.mp4', 'rb') as video:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video,
                    caption=get_text("upload_photo_prompt", user_lang)
                )
        except FileNotFoundError:
             logger.warning("Video file 'upload_guide.mp4' not found. Sending text prompt only.")
             await query.message.reply_text(get_text("upload_photo_prompt", user_lang))
        except Exception as e:
             logger.error(f"Failed to send video prompt: {e}")
             await query.message.reply_text(get_text("upload_photo_prompt", user_lang)) # Fallback on other errors
        
        return

    # --- Language Selection (set_lang:en, set_lang:ru) ---
    if callback_data.startswith("set_lang:"):
        chosen_lang = callback_data.split(":")[1]

        db_update_needed = chosen_lang != user_data.get("language")
        success = True # Assume success if no DB update is needed

        if db_update_needed:
            success = await db.update_user_data(user.id, {"language": chosen_lang})

        if success:
            user_data["language"] = chosen_lang # Update local state

            if initial_selection_phase:
                # New user flow: show agreement next
                await send_agreement_prompt(update, context, user_data)
            else:
                # Existing user flow: show updated start menu directly
                current_balance = await db.get_user_photos_balance(user.id)
                welcome_message_text = get_text("start_message", chosen_lang).format(
                    user_name=user.first_name,
                    balance=current_balance
                )
                await query.edit_message_text(
                    text=welcome_message_text,
                    reply_markup=keyboards.get_start_keyboard(chosen_lang),
                    parse_mode=ParseMode.MARKDOWN
                )
        else: # DB update failed
            await query.edit_message_text(get_text("error_occurred", current_lang))
            if initial_selection_phase:
                context.user_data['initial_lang_selection'] = True # Allow retry
        
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

    # --- Payment Callbacks Handling (Example, ensure your function exists and is called correctly) ---
    payment_callbacks_prefixes = ("buy_package:", "confirm_purchase:", "payment_history_page:")
    payment_callbacks_exact = ["show_packages", "show_balance", "show_payment_history", "cancel_payment", "back_to_main"]
    if callback_data.startswith(payment_callbacks_prefixes) or callback_data in payment_callbacks_exact:
        if hasattr(payments, 'handle_payment_callbacks'): # Assuming you might move this
             await payments.handle_payment_callbacks(update, context, callback_data, user_data, query)
        else: # Fallback to local one if not moved
             await handle_payment_callbacks(update, context, callback_data, user_data, query)
        return

    # --- Language selection (from /start) ---
    elif callback_data.startswith("show_settings_option:"):
        option_key = callback_data.split(":")[1]
        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        
        if option_key == 'language':
            # This now opens the language selection keyboard
             await query.edit_message_text(
                text=get_text("select_language", user_lang),
                reply_markup=keyboards.get_option_value_keyboard(
                    option_key=option_key,
                    lang=user_lang,
                    current_lang=user_lang
                )
            )

    # --- Back to Start Menu (from language selection) ---
    elif callback_data == "back_to_start":
        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        current_balance = await db.get_user_photos_balance(user.id)
        welcome_message_text = get_text("start_message", user_lang).format(
            user_name=user.first_name,
            balance=current_balance
        )
        await query.edit_message_text(
            text=welcome_message_text,
            reply_markup=keyboards.get_start_keyboard(user_lang),
            parse_mode=ParseMode.MARKDOWN
        )

    # --- Обработка кнопок ПЛАТЕЖЕЙ ---
    # (Перенесено в отдельную функцию для чистоты)
    elif "buy_package" in callback_data or \
         "confirm_purchase" in callback_data or \
         "payment_history_page" in callback_data or \
         callback_data in ["show_packages", "show_balance", "show_payment_history", "cancel_payment", "back_to_main"]:
        if hasattr(payments, 'handle_payment_callbacks'): # Assuming you might move this
             await payments.handle_payment_callbacks(update, context, callback_data, user_data, query)
        else: # Fallback to local one if not moved
             await handle_payment_callbacks(update, context, callback_data, user_data, query)
        return

    # --- Payment method selection ---
    elif callback_data.startswith("pay_method:"):
        # Format: pay_method:<method>:<package_id>
        _, method, package_id = callback_data.split(":", 2)
        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)

        package_info = payments.get_package_info(package_id, user_lang)
        if not package_info:
            await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))
            return

        if method == "streampay":
            # Reuse existing flow to create StreamPay invoice (previously in confirm_purchase)
            await query.edit_message_text(text=get_text("creating_payment", user_lang))
            order_data = await payments.create_payment_order(user_data['user_id'], package_id)
            if order_data:
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
                await query.edit_message_text(text=get_text("payment_error", user_lang))
            return

        elif method == "tgstars":
            # Attempt to create Telegram Stars invoice directly via send_invoice
            
            star_amount = int(package_info.get('stars_price') or package_info['price'])
            if star_amount <= 0:
                logger.error(f"Invalid star amount for package {package_id}: {star_amount}")
                await query.edit_message_text(text=get_text("payment_error", user_lang))
                return

            payload = f"tgstars_{user.id}_{package_id}_{uuid.uuid4().hex[:8]}"

            # Save pending order in DB (status pending) BEFORE sending invoice to link later update
            order_data = {
                "external_id": payload,
                "user_id": user.id,
                "package_id": package_id,
                "invoice_id": None,
                "amount": star_amount,
                "currency": "XTR",
                "photos_count": package_info['photos'],
                "status": "pending",
                "created_at": datetime.utcnow(),
                "pay_url": None,
                "method": "tgstars"
            }
            await db.create_payment_order(order_data)

            # Replace message with invoice (Telegram will create a new message automatically)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
            except Exception:
                pass  # Ignore if can't delete

            try:
                await context.bot.send_invoice(
                    chat_id=chat_id,
                    title=package_info['name'],
                    description=package_info['description'],
                    payload=payload,
                    provider_token='',  # Empty for Stars
                    currency='XTR',
                    prices=[LabeledPrice(package_info['name'], star_amount)],
                    start_parameter="tgstars_payment"
                )
            except Exception as e:
                logger.error(f"Failed to send TG Stars invoice: {e}")
                await context.bot.send_message(chat_id, get_text("payment_error", user_lang))
            return

        else:
            logger.warning(f"Unknown payment method selected: {method}")
            await context.bot.send_message(chat_id, get_text("error_occurred", user_lang))
            return

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
            # Логируем событие выбора пакета (еще без выбора метода оплаты)
            await db.log_user_event(user_id, "payment_package_selected", {
                "package_id": package_id,
                "package_name": package_info.get('name'),
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
                    reply_markup=keyboards.get_payment_methods_keyboard(package_id, user_lang),
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
        order_data = await payments.create_payment_order(user_data['user_id'], package_id)
        
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

async def _execute_photo_processing(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    processing_options: dict
):
    """
    Handles the actual API call for photo processing.
    Assumes balance has been checked and deducted.
    """
    if 'pending_photo_session' not in context.user_data:
        logger.error("execute_photo_processing called without a pending photo session.")
        return

    session_data = context.user_data.get('pending_photo_session', {})
    photo_file_id = session_data.get('file_id')
    original_message_id = session_data.get('message_id')

    if not photo_file_id or not original_message_id:
        logger.error(f"Missing photo_file_id or original_message_id in session for user {update.effective_user.id}")
        return

    user_data = context.user_data.get('db_user', {})
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
    user_id = user_data.get('user_id')
    chat_id = user_data.get('chat_id')

    if not all([user_data, user_lang, user_id, chat_id]):
        logger.error(f"Missing user data in context for photo processing for user {update.effective_user.id}")
        return
        
    id_gen = None
    try:
        # First, deduct the photo from balance.
        deduct_success = await db.deduct_user_photos(user_id, 1)
        if not deduct_success:
            logger.error(f"Failed to deduct photo from user {user_id} balance before processing.")
            # Notify user that deduction failed
            await context.bot.send_message(
                chat_id=chat_id, 
                text=get_text("error_occurred", user_lang),
                reply_to_message_id=original_message_id
            )
            return

        # Let the user know we are starting
        status_message = await context.bot.send_message(
            chat_id,
            text=get_text("processing_photo", user_lang),
            reply_to_message_id=original_message_id
        )

        photo_file = await context.bot.get_file(photo_file_id)
        photo_bytes_io = BytesIO()
        await photo_file.download_to_memory(photo_bytes_io)
        photo_bytes_io.seek(0)
        photo_bytes = photo_bytes_io.read()

        if not photo_bytes:
            logger.warning(f"Could not download photo bytes for file_id: {photo_file_id}")
            await status_message.edit_text(get_text("photo_download_error", user_lang))
            await db.add_user_photos(user_id, 1) # Refund
            return

        id_gen = str(uuid.uuid4())
        bot_state.pending_requests[id_gen] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": original_message_id, # So webhook can reply to original photo
            "status_message_id": status_message.message_id,
            "lang": user_lang
        }
        logger.info(f"Generated id_gen: {id_gen} for user {user_id}. Pending requests: {len(bot_state.pending_requests)}")

        await db.log_user_event(user_id, "generation_requested", {"id_gen": id_gen, "options": processing_options})

        data = aiohttp.FormData()
        data.add_field('image', photo_bytes, filename=f'{id_gen}.jpg', content_type='image/jpeg')
        data.add_field('id_gen', id_gen)
        data.add_field('webhook', config.CLOTHOFF_RECEIVER_URL)
        
        # Add processing options to the request
        for key, value in processing_options.items():
            if value: # Only send non-empty values
                data.add_field(key, str(value))

        # Log the request details before sending
        log_payload = {
            "id_gen": id_gen,
            "webhook": config.CLOTHOFF_RECEIVER_URL,
            "image_size": len(photo_bytes),
            **processing_options
        }
        logger.info(f"Sending request to Clothoff API for id_gen {id_gen}. Payload: {log_payload}")

        headers = {'x-api-key': config.CLOTHOFF_API_KEY, 'accept': 'application/json'}

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(config.CLOTHOFF_API_URL, data=data, headers=headers) as response:
                response_text = await response.text()
                logger.debug(f"API Raw Response ({response.status}) for id_gen {id_gen}: {response_text[:500]}")

                if response.status == 200:
                    logger.info(f"API call successful for id_gen {id_gen}. Waiting for webhook.")
                    await status_message.edit_text(get_text("photo_sent_for_processing", user_lang))
                else:
                    logger.error(f"API error for id_gen {id_gen}: Status {response.status}, Response: {response_text[:200]}")
                    await db.add_user_photos(user_id, 1) # Refund
                    if id_gen in bot_state.pending_requests: del bot_state.pending_requests[id_gen]
                    
                    error_details = response_text[:100]
                    await status_message.edit_text(
                        get_text("api_error", user_lang).format(status=response.status, details=error_details)
                    )

    except aiohttp.ClientError as e:
        logger.error(f"API request ClientError for user {user_id}, id_gen {id_gen if id_gen else 'N/A'}: {e}")
        if id_gen: await db.add_user_photos(user_id, 1) # Refund
        if id_gen and id_gen in bot_state.pending_requests:
            status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
            del bot_state.pending_requests[id_gen]
            if status_message_id:
                await context.bot.edit_message_text(
                    get_text("network_error", user_lang), chat_id=chat_id, message_id=status_message_id
                )
    except Exception as e:
        logger.exception(f"Unexpected error in photo processing for user {user_id}, id_gen {id_gen if id_gen else 'N/A'}: {e}")
        if id_gen: await db.add_user_photos(user_id, 1) # Refund
        if id_gen and id_gen in bot_state.pending_requests:
            status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
            del bot_state.pending_requests[id_gen]
            if status_message_id:
                await context.bot.edit_message_text(
                    get_text("unexpected_processing_error", user_lang), chat_id=chat_id, message_id=status_message_id
                )
    finally:
        if 'pending_photo_session' in context.user_data:
            del context.user_data['pending_photo_session']

@require_agreement
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles successful payments coming from Telegram Stars provider."""
    payment = update.message.successful_payment
    if not payment:
        return

    user = update.effective_user
    chat_id = update.effective_chat.id

    # Parse payload, expected: tgstars_<user_id>_<package_id>_<random>
    payload_parts = payment.invoice_payload.split("_")
    if len(payload_parts) < 3:
        logger.error(f"Unexpected invoice payload format: {payment.invoice_payload}")
        return

    _prefix, payload_user_id, package_id, *_ = payload_parts
    if str(user.id) != payload_user_id:
        logger.warning(f"Payload user ID {payload_user_id} does not match sender {user.id}")

    user_data = await db.get_or_create_user(user.id, chat_id, user.username, user.first_name)
    user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)

    # Update order in DB
    external_id = payment.invoice_payload
    order = await db.get_payment_order_by_external_id(external_id)
    if order and order.get("status") != "success":
        update_data = {
            "status": "success",
            "updated_at": datetime.utcnow(),
            "telegram_payment_charge_id": payment.telegram_payment_charge_id,
            "provider_payment_charge_id": payment.provider_payment_charge_id,
        }
        await db.update_payment_order(external_id, update_data)
        # Credit photos
        photos_to_add = order["photos_count"] if order else 0
        if photos_to_add:
            await db.add_user_photos(user.id, photos_to_add)
        new_balance = await db.get_user_photos_balance(user.id)
        await notify_payment_success(user.id, order["package_id"], photos_to_add, new_balance)
    else:
        logger.info(f"Payment order already processed or not found for payload {external_id}")

# === Telegram Stars pre-checkout ===
async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approves every pre_checkout_query (required for Stars)."""
    query = update.pre_checkout_query
    try:
        await query.answer(ok=True)
    except Exception as e:
        logger.error(f"Failed to answer pre_checkout_query: {e}")
