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
        "en": "Hello {user_name}! Send me a photo containing a person, and I'll try to process it using Clothoff.io.\n\nUse /settings to change language or processing options.\n\n⚠️ **Disclaimer:** Use this bot responsibly and ethically.",
        "ru": "Привет, {user_name}! Отправь мне фото с человеком, и я попробую обработать его с помощью Clothoff.io.\n\nИспользуйте /settings для смены языка или опций обработки.\n\n⚠️ **Отказ от ответственности:** Используйте этого бота ответственно и этично.",
    },
    "help_message": {
        "en": "Send me a photo with a person in it. I will send it to the Clothoff API for processing based on your /settings.\n"
              "You will receive the result back here once it's ready.\n\n"
              "**Important:**\n"
              "- Ensure the image clearly shows one person.\n"
              "- Processing can take some time.\n"
              "- Results depend on the Clothoff API's capabilities.\n"
              "- Use responsibly.",
        "ru": "Отправьте мне фото с человеком. Я отправлю его в Clothoff API для обработки согласно вашим /settings.\n"
              "Вы получите результат здесь, когда он будет готов.\n\n"
              "**Важно:**\n"
              "- Убедитесь, что на изображении четко виден один человек.\n"
              "- Обработка может занять некоторое время.\n"
              "- Результаты зависят от возможностей Clothoff API.\n"
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
        "en": "🧘 Pose",
        "ru": "🧘 Поза",
    },
    "option_cloth": {
        "en": "👙 Cloth",
        "ru": "👙 Одежда",
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
        "en": "Current balance: {balance} photos",
        "ru": "Текущий баланс: {balance} фото",
    },
    "insufficient_balance": {
        "en": "❌ Insufficient balance! You need {needed} photos, but you have only {current}.\n\nPlease purchase more photos to continue.",
        "ru": "❌ Недостаточно средств! Вам нужно {needed} фото, а у вас только {current}.\n\nПожалуйста, купите больше фото для продолжения.",
    },
    "buy_photos": {
        "en": "💳 Buy Photos",
        "ru": "💳 Купить фото",
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
        "en": "📦 **{name}**\n\n{description}\n\n💎 Photos: {photos}\n💰 Price: ${price}\n\nConfirm your purchase?",
        "ru": "📦 **{name}**\n\n{description}\n\n💎 Фото: {photos}\n💰 Цена: ${price}\n\nПодтвердить покупку?",
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
        "en": "💳 **Payment Link Created**\n\nPackage: {package_name}\nAmount: ${amount}\n\nClick the button below to proceed with payment:",
        "ru": "💳 **Ссылка для оплаты создана**\n\nПакет: {package_name}\nСумма: ${amount}\n\nНажмите кнопку ниже для оплаты:",
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
        "en": "✅ **Payment Successful!**\n\nYou have purchased: {package_name}\nPhotos added: {photos}\nNew balance: {new_balance} photos\n\nThank you for your purchase!",
        "ru": "✅ **Платеж успешен!**\n\nВы купили: {package_name}\nДобавлено фото: {photos}\nНовый баланс: {new_balance} фото\n\nСпасибо за покупку!",
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
        "en": "📦 {package_name}\n💰 ${amount} • {status}\n📅 {date}",
        "ru": "📦 {package_name}\n💰 ${amount} • {status}\n📅 {date}",
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
    }
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
