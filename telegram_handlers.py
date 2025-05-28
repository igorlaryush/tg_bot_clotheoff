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
        BotCommand("balance", "Check balance and buy photos"),
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

    # Проверяем баланс пользователя
    current_balance = await db.get_user_photos_balance(user_id)
    if current_balance < 1:
        # Недостаточно средств - показываем сообщение и предлагаем купить
        await update.message.reply_text(
            get_text("insufficient_balance", user_lang).format(needed=1, current=current_balance),
            reply_markup=keyboards.get_payment_packages_keyboard(user_lang),
            reply_to_message_id=message_id
        )
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
                    # Возвращаем фото на баланс при ошибке API
                    await db.add_user_photos(user_id, 1)
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
        # Возвращаем фото на баланс при сетевой ошибке
        await db.add_user_photos(user_id, 1)
    except Exception as e:
        logger.exception(f"Unexpected error in handle_photo for user {user_id} (id_gen: {id_gen}): {e}")
        if id_gen and id_gen in bot_state.pending_requests:
            status_message_id = bot_state.pending_requests[id_gen].get("status_message_id")
            if status_message_id:
                 await context.bot.edit_message_text(get_text("unexpected_processing_error", user_lang), chat_id=chat_id, message_id=status_message_id)
            del bot_state.pending_requests[id_gen]
        # Возвращаем фото на баланс при неожиданной ошибке
        await db.add_user_photos(user_id, 1)

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

    # Проверяем, является ли это callback'ом платежей
    payment_callbacks = [
        "show_packages", "show_balance", "show_payment_history", "cancel_payment", "back_to_main"
    ]
    
    if (callback_data in payment_callbacks or 
        callback_data.startswith(("buy_package:", "confirm_purchase:", "payment_history_page:"))):
        
        # Проверяем согласие для платежных операций
        if not user_data.get("agreed_to_terms", False):
            await send_agreement_prompt(update, context, user_data)
            return
            
        handled = await handle_payment_callbacks(update, context, callback_data, user_data, query)
        if handled:
            return

    # Остальная логика обработки callback'ов (существующий код)
    # ... (весь существующий код обработки callback'ов остается без изменений)

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
                    reply_markup=keyboards.get_settings_main_keyboard(user_lang, current_options)
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
        user_data = await db.get_or_create_user(user_id, 0, None, None)  # chat_id будет обновлен из существующих данных
        if not user_data:
            logger.error(f"Cannot notify user {user_id} about payment success - user data not found")
            return

        user_lang = user_data.get("language", config.DEFAULT_LANGUAGE)
        chat_id = user_data.get("chat_id")
        
        if not chat_id:
            logger.error(f"Cannot notify user {user_id} about payment success - chat_id not found")
            return

        text = get_text("payment_success", user_lang).format(
            package_name=package_name,
            photos=photos_added,
            new_balance=new_balance
        )

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
