import os
import logging

logger = logging.getLogger(__name__)

# --- Загрузка текстов соглашений ---
AGREEMENTS = {}
SUPPORTED_LANGUAGES = ['en', 'ru'] # Добавьте другие языки сюда

def load_agreement_text(lang_code):
    try:
        filename = f"user_agreement_{lang_code}.txt"
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logger.warning(f"Agreement file not found: {filename}")
            return f"User agreement text for '{lang_code}' is missing."
    except Exception as e:
        logger.error(f"Failed to load agreement text for {lang_code}: {e}")
        return f"Error loading user agreement for '{lang_code}'."

for lang in SUPPORTED_LANGUAGES:
    AGREEMENTS[lang] = load_agreement_text(lang)

# --- Текстовые строки ---
# Ключ -> {язык: текст}
TEXTS = {
    # --- Общее ---
    "error_occurred": {
        "en": "An error occurred. Please try again later.",
        "ru": "Произошла ошибка. Пожалуйста, попробуйте позже.",
    },
    "processing_photo": {
        "en": "⏳ Processing your photo...",
        "ru": "⏳ Обрабатываю ваше фото...",
    },
    "photo_sent_for_processing": {
        "en": "Photo sent for processing. Waiting for result...",
        "ru": "Фото отправлено на обработку. Ожидаю результат...",
    },
    "api_error": {
        "en": "❌ API Error: {status}. Could not send photo for processing. Details: {details}",
        "ru": "❌ Ошибка API: {status}. Не удалось отправить фото на обработку. Детали: {details}",
    },
    "network_error": {
        "en": "❌ Network error connecting to processing service.",
        "ru": "❌ Сетевая ошибка при подключении к сервису обработки.",
    },
    "unexpected_processing_error": {
        "en": "❌ An unexpected error occurred while processing your request.",
        "ru": "❌ Произошла непредвиденная ошибка при обработке вашего запроса.",
    },
     "result_caption": {
        "en": "✅ Processed image (ID: {id_gen}).\nProcessing time: {time}s",
        "ru": "✅ Обработанное изображение (ID: {id_gen}).\nВремя обработки: {time}с",
    },
     "result_caption_no_time": {
        "en": "✅ Processed image (ID: {id_gen}).",
        "ru": "✅ Обработанное изображение (ID: {id_gen}).",
    },
    "processing_failed": {
        "en": "❌ Processing failed for image (ID: {id_gen}).\nReason: {reason}",
        "ru": "❌ Ошибка обработки изображения (ID: {id_gen}).\nПричина: {reason}",
    },
    "failed_to_send_result": {
        "en": "Failed to deliver processing result for ID: {id_gen}. Error: {error}",
        "ru": "Не удалось доставить результат обработки для ID: {id_gen}. Ошибка: {error}",
    },
    "error_getting_user_data": {
        "en": "Sorry, there was a problem accessing your user data. Please try again later.",
        "ru": "Извините, произошла проблема с доступом к вашим данным. Пожалуйста, попробуйте позже.",
    },
    "photo_download_error":{
        "en": "Could not download the photo.",
        "ru": "Не удалось загрузить фото.",
    },

    # --- Соглашение и язык ---
    "choose_language": {
        "en": "Please choose your language:",
        "ru": "Пожалуйста, выберите ваш язык:",
    },
    "agreement_prompt": {
        "en": "Please review and accept the User Agreement to continue:",
        "ru": "Пожалуйста, ознакомьтесь и примите Пользовательское Соглашение для продолжения:",
    },
    "accept_button": {
        "en": "✅ Accept",
        "ru": "✅ Принять",
    },
    "decline_button": {
        "en": "❌ Decline",
        "ru": "❌ Отклонить",
    },
    "agreement_accepted": {
        "en": "Thank you! You can now use the bot. Send /help for instructions or /settings to configure options.",
        "ru": "Спасибо! Теперь вы можете использовать бота. Отправьте /help для инструкций или /settings для настройки опций.",
    },
    "agreement_declined": {
        "en": "You have declined the User Agreement. You need to accept it to use this bot. Send /start again if you change your mind.",
        "ru": "Вы отклонили Пользовательское Соглашение. Вам необходимо принять его, чтобы использовать бота. Отправьте /start снова, если передумаете.",
    },
    "must_accept_agreement": {
        "en": "You must accept the User Agreement first. Please check the message above or send /start.",
        "ru": "Сначала вы должны принять Пользовательское Соглашение. Пожалуйста, проверьте сообщение выше или отправьте /start.",
    },
     "language_set": {
        "en": "Language set to English.",
        "ru": "Язык установлен на Русский.",
    },

    # --- Старт и Помощь ---
    "start_message": {
        "en": """
Welcome, {user_name}!

Your balance: 
💎 {balance} coins

1 coin = 1 generation.
To top up your balance, press the 'Buy coins' button.

❗️ We respect our users' privacy, so photos and request history are not stored anywhere.
        """,
        "ru": """
Привет, {user_name}!

Ваш баланс:
💎 {balance} монет.

1 монета = 1 генерация.
Для того, чтобы пополнить баланс, нажми кнопку 'Купить монеты'.

❗️ Мы уважаем конфиденциальность наших пользователей, поэтому фотографии и история запросов нигде не хранятся.
        """
    },
    "upload_photo_button": {
        "en": "📷 Upload Photo",
        "ru": "📷 Загрузить фото"
    },
    "buy_coins_button": {
        "en": "💎 Buy coins",
        "ru": "💎 Купить монеты"
    },
    "my_channel_button": {
        "en": "My Channel",
        "ru": "Наш канал"
    },
    "menu_button": {
        "en": "Start",
        "ru": "Меню"
    },
    "menu_activated": {
        "en": "You can now use the 'Menu' button below to return here at any time.",
        "ru": "Теперь вы можете использовать кнопку 'Меню' для возврата сюда в любое время."
    },
    "upload_photo_prompt": {
        "en": """
🤓 You can upload a photo, here are a few simple rules:

➖ There should be only one person in the photo;
➖ The person should be in the center;
➖ Better lighting and quality = better result;
➖ Make sure clothes do not hide the body;

🔒 We respect our users' privacy, so photos are not stored anywhere.

📎 Now send your photo.
        """,
        "ru": """
🤓 Можете загрузить фотографию, вот несколько простых правил:

➖ На фото должен быть только один человек;
➖ Человек должен быть в центре;
➖ Лучшее освещение и качество = лучший результат;
➖ Убедитесь, что одежда не скрывает тело;

🔒 Мы уважаем конфиденциальность наших пользователей, поэтому не храним фотографии и историю запросов.

📎 Теперь отправьте ваше фото.
        """
    },
    "help_message": {
        "en": "Send me a photo with a person in it. I process it based on your settings.\n"
              "You will receive the result back here once it's ready.\n\n"
              "**Important:**\n"
              "- Ensure the image clearly shows one person.\n"
              "- Processing can take some time.\n"
              "- Use responsibly.",
        "ru": "Отправьте мне фото с человеком. Я обработаю его согласно вашим настройкам.\n"
              "Вы получите результат здесь, когда он будет готов.\n\n"
              "**Важно:**\n"
              "- Убедитесь, что на изображении четко виден один человек.\n"
              "- Обработка может занять некоторое время.\n"
              "- Используйте ответственно.",
    },

    # --- Настройки ---
    "settings_title": {
        "en": "⚙️ Settings",
        "ru": "⚙️ Настройки",
    },
    "settings_choose_option": {
        "en": "Select an option to configure:",
        "ru": "Выберите опцию для настройки:",
    },
    "settings_current_options": {
        "en": "Current Processing Options:",
        "ru": "Текущие опции обработки:",
    },
    "option_language": {
        "en": "🌐 Language",
        "ru": "🌐 Язык",
    },
    "option_postprocessing": {
        "en": "✨ Post-processing",
        "ru": "✨ Постобработка",
    },
    "option_age": {
        "en": "🎂 Age",
        "ru": "🎂 Возраст",
    },
    "option_breast_size": {
        "en": "🍒 Breast Size",
        "ru": "🍒 Размер груди",
    },
    "option_body_type": {
        "en": "🤸 Body Type",
        "ru": "🤸 Тип тела",
    },
    "option_butt_size": {
        "en": "🍑 Butt Size",
        "ru": "🍑 Размер ягодиц",
    },
     "option_pose": {
        "en": "🧘 Sex positions",
        "ru": "🧘 Секс позы",
    },
    "option_cloth": {
        "en": "👗 Costume",
        "ru": "👗 Костюм",
    },
    "option_not_set": {
        "en": "Not set",
        "ru": "Не задано",
    },
    "choose_value_for": {
        "en": "Choose a value for {option_name}:",
        "ru": "Выберите значение для {option_name}:",
    },
    "setting_updated": {
        "en": "{option_name} updated to: {value}",
        "ru": "{option_name} обновлено на: {value}",
    },
    "setting_reset": {
        "en": "{option_name} reset.",
        "ru": "{option_name} сброшено.",
    },
    "back_button": {
        "en": "« Back",
        "ru": "« Назад",
    },
    "reset_button": {
        "en": "Reset to default",
        "ru": "Сбросить",
    },
     "value_not_set": {
        "en": "Default",
        "ru": "По умолч.",
     },

    # --- Платежи и баланс ---
    "balance_title": {
        "en": "💰 Your Balance",
        "ru": "💰 Ваш баланс",
    },
    "current_balance": {
        "en": "Current balance: {balance} edits",
        "ru": "Текущий баланс: {balance} обработок",
    },
    "insufficient_balance": {
        "en": "❌ Insufficient balance! You need {needed} edits, but you have only {current}.\n\nPlease purchase more edits to continue.",
        "ru": "❌ Недостаточно средств! Вам нужно {needed} обработок, а у вас только {current}.\n\nПожалуйста, купите больше обработок для продолжения.",
    },
    "buy_photos": {
        "en": "\uD83D\uDCB3 Buy edits",
        "ru": "\uD83D\uDCB3 Купить обработки",
    },
    "payment_history": {
        "en": "📋 Payment History",
        "ru": "📋 История платежей",
    },
    "choose_package": {
        "en": "Choose a package to purchase:",
        "ru": "Выберите пакет для покупки:",
    },
    "package_details": {
        "en": "📦 **{name}**\n\n{description}\n\n💎 Edits: {photos}\n💰 Price: {price} ₽\n\nConfirm your purchase?",
        "ru": "📦 **{name}**\n\n{description}\n\n💎 Обработок: {photos}\n💰 Цена: {price} ₽\n\nПодтвердить покупку?",
    },
    "confirm_purchase": {
        "en": "✅ Confirm Purchase",
        "ru": "✅ Подтвердить покупку",
    },
    "back_to_packages": {
        "en": "⬅️ Back to Packages",
        "ru": "⬅️ Назад к пакетам",
    },
    "cancel_button": {
        "en": "❌ Cancel",
        "ru": "❌ Отмена",
    },
    "creating_payment": {
        "en": "⏳ Creating payment link...",
        "ru": "⏳ Создаю ссылку для оплаты...",
    },
    "payment_link_created": {
        "en": "💳 **Payment Link Created**\n\nPackage: {package_name}\nAmount: {amount} ₽\n\nClick the button below to proceed with payment:",
        "ru": "💳 **Ссылка для оплаты создана**\n\nПакет: {package_name}\nСумма: {amount} ₽\n\nНажмите кнопку ниже для оплаты:",
    },
    "pay_now": {
        "en": "💳 Pay Now",
        "ru": "💳 Оплатить сейчас",
    },
    "payment_error": {
        "en": "❌ Error creating payment. Please try again later.",
        "ru": "❌ Ошибка создания платежа. Попробуйте позже.",
    },
    "payment_success": {
        "en": "✅ **Payment Successful!**\n\nYou have purchased: {package_name}\nEdits added: {photos}\nNew balance: {new_balance} edits\n\nThank you for your purchase!",
        "ru": "✅ **Платеж успешен!**\n\nВы купили: {package_name}\nДобавлено обработок: {photos}\nНовый баланс: {new_balance} обработок\n\nСпасибо за покупку!",
    },
    "payment_failed": {
        "en": "❌ Payment failed. Please try again or contact support.",
        "ru": "❌ Платеж не прошел. Попробуйте снова или обратитесь в поддержку.",
    },
    "payment_cancelled": {
        "en": "❌ Payment was cancelled.",
        "ru": "❌ Платеж был отменен.",
    },
    "no_payment_history": {
        "en": "📋 No payment history found.",
        "ru": "📋 История платежей пуста.",
    },
    "payment_history_item": {
        "en": "📦 {package_name}\n💰 {amount} ₽ • {status}\n📅 {date}",
        "ru": "📦 {package_name}\n💰 {amount} ₽ • {status}\n📅 {date}",
    },
    "payment_status_pending": {
        "en": "⏳ Pending",
        "ru": "⏳ Ожидание",
    },
    "payment_status_success": {
        "en": "✅ Paid",
        "ru": "✅ Оплачено",
    },
    "payment_status_failed": {
        "en": "❌ Failed",
        "ru": "❌ Ошибка",
    },
    "payment_status_cancelled": {
        "en": "❌ Cancelled",
        "ru": "❌ Отменено",
    },
    "back_to_main": {
        "en": "🏠 Main Menu",
        "ru": "🏠 Главное меню",
    },
    "show_balance": {
        "en": "💰 Balance",
        "ru": "💰 Баланс",
    },
    "scheduled_notification_promo": {
        "en": "Want something more? The time has come 🥵\n\nCreate neurophotos with her face ACCORDING TO YOUR REQUEST, any desire of your imagination will be brought to life in just a few seconds\n\n1. Describe what should be in the photo using /settings.\n2. Send a high-quality photo of a person.\n3. Enjoy the results!",
        "ru": "Хочешь чего-то большего ? Время пришло 🥵\n\nСоздавай нейрофото с её лицом по СВОЕМУ ЗАПРОСУ, любое желания твоей фантазии будет воплощено в жизнь всего за не сколько секунд\n\n1. Опиши что должно быть на фото /settings. \n2. Отправь фото человека, в хорошем качестве.\n3. Наслаждайся результатами!",
    },
    "settings_intro": {
        "en": "⚙️ *Settings*\\n\\nHere you can change the bot's language.",
        "ru": "⚙️ *Настройки*\\n\\nЗдесь вы можете изменить язык бота."
    },
    "configure_photo_settings_title": {
        "en": """
❓ What would you like to do?

1️⃣ Costume - See the girl in a sexy costume😏 

2️⃣ Undress - Undressing with the ability to change body parameters

3️⃣ Sex-pose - See the girl in a porn scene

Press the button and enjoy 👇
        """,
        "ru": """
❓ Что бы ты хотел сделать?

1️⃣ Костюм - Посмотри на девушку в сексуальном костюме😏 

2️⃣ Раздевание - Раздевание с возможностью изменения параметров тела

3️⃣ Секс-поза - Посмотри на девушку в  порно сцене

Нажмите кнопку и наслаждайтесь 👇
        """
    },
    "process_button": {
        "en": "✅ Process Photo",
        "ru": "✅ Обработать фото"
    },
    "photo_processing_cancelled": {
        "en": "Photo processing cancelled.",
        "ru": "Обработка фото отменена."
    },
    "preview_payment_required": {
        "en": "🔒 Almost ready! Pay to get the unblurred version.",
        "ru": "🔒 Почти готово! Оплатите, чтобы получить фото без размытия."
    },
    "option_value_display": {
        "en": "{option_name}: *{value}*",
        "ru": "{option_name}: *{value}*"
    },
    "option_value_not_set": {
        "en": "{option_name}: Not set",
        "ru": "{option_name}: Не задано"
    },
    "select_option_title": {
        "en": "Select a value for *{option_name}*:",
        "ru": "Выберите значение для *{option_name}*:"
    },
    "settings_appearance_intro": {
        "en": "🎨 *Appearance Settings*\n\nChoose how you want the generated person to look.",
        "ru": "🎨 *Настройки внешности*\n\nВыберите, как будет выглядеть сгенерированный человек."
    },
    "settings_saved": {
        "en": "✅ Settings saved!",
        "ru": "✅ Настройки сохранены!"
    },
    "select_language": {
        "en": "Please select your language:",
        "ru": "Пожалуйста, выберите ваш язык:"
    },
    "select_postprocessing": {
        "en": "Select a post-processing filter:",
        "ru": "Выберите фильтр постобработки:"
    },
    "select_age": {
        "en": "Select the desired age:",
        "ru": "Выберите желаемый возраст:"
    },
    "select_breast_size": {
        "en": "Select the desired breast size:",
        "ru": "Выберите желаемый размер груди:"
    },
    "select_body_type": {
        "en": "Select the desired body type:",
        "ru": "Выберите желаемый тип телосложения:"
    },
    "select_butt_size": {
        "en": "Select the desired butt size:",
        "ru": "Выберите желаемый размер ягодиц:"
    },
    "option_appearance": {
        "en": "👙 Undress",
        "ru": "👙 Раздеть"
    },
    "pay_with_streampay": {
        "en": "Pay by card",
        "ru": "Оплата картой"
    },
    "pay_with_tgstars": {
        "en": "Pay with Telegram Stars",
        "ru": "Оплатить через Stars"
    },
}

# --- Получение текста ---
DEFAULT_LANG = 'en' # Язык по умолчанию, если у пользователя не установлен или ключ не найден

def get_text(key: str, lang_code: str = DEFAULT_LANG) -> str:
    """Возвращает локализованный текст для ключа."""
    if not lang_code:
        lang_code = DEFAULT_LANG
    # Сначала ищем текст для запрошенного языка
    lang_dict = TEXTS.get(key)
    if lang_dict:
        text = lang_dict.get(lang_code)
        if text:
            return text
        # Если нет на нужном языке, пробуем на языке по умолчанию
        text_default = lang_dict.get(DEFAULT_LANG)
        if text_default:
             logger.debug(f"Text key '{key}' not found for lang '{lang_code}', using default '{DEFAULT_LANG}'.")
             return text_default
    # Если ключ вообще не найден
    logger.warning(f"Text key '{key}' not found in TEXTS.")
    return f"_{key}_" # Возвращаем ключ как индикатор отсутствия перевода

def get_agreement_text(lang_code: str) -> str:
    """Возвращает текст соглашения для указанного языка."""
    if not lang_code:
        lang_code = DEFAULT_LANG
    return AGREEMENTS.get(lang_code, AGREEMENTS.get(DEFAULT_LANG, "Missing agreement text."))

# --- Опции для настроек (как в config.py или здесь) ---
APPEARANCE_OPTIONS = {
    "settings_choose_option": "Please choose an option to configure:",
    "settings_saved": "✅ Settings saved!",
    "settings_appearance_intro": "🎨 *Appearance Settings*\n\nChoose how you want the generated person to look.",
    "select_language": "Please select your language:",
    "select_postprocessing": "Select a post-processing filter:",
    "select_age": "Select the desired age:",
    "option_pose": "Pose",
    "option_cloth": "Cloth",
    "option_appearance": "🎨 Appearance",
    "value_not_set": "Not set",
}
