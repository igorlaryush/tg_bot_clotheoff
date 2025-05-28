from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from localization import get_text, SUPPORTED_LANGUAGES # Импортируем строки и список языков
import payments # Импортируем модуль платежей

# --- Опции для настроек (как в config.py или здесь) ---
PROCESSING_OPTIONS = {
    "postprocessing": ["", "anime", "upscale"], # "" - не выбрано
    "age": ["", "18", "20", "30", "40", "50"],
    "breast_size": ["", "small", "normal", "big"],
    "body_type": ["", "skinny", "normal", "curvy", "muscular"],
    "butt_size": ["", "small", "normal", "big"],
    "pose": [ # Из картинки пользователя
        "", "Blowjob", "Doggy Style", "Cumshot", "Cumshot POV", "Shower Room",
        "Shibari", "Ahegao", "Ahegao cum", "Holding tits", "Missionary POV",
        "Cowgirl POV", "Anal Fuck", "Legs up presenting", "Spreading legs",
        "Tit Fuck", "TGirl", "Tits On Glass", "Christmas", "Winter 1"
    ],
    "cloth": [ # Из картинки пользователя
        "", "naked", "bikini", "lingerie", "sport wear", "bdsm", "latex",
        "teacher", "schoolgirl", "bikini leopard", "naked cum", "naked tatoo",
        "witch", "sexy witch", "sexy maid", "Christmas underwear", "pregnant",
        "cheerleader", "police", "secretary"
    ]
}

# --- Клавиатура выбора языка ---
def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        # Можно добавить флаги или полные названия языков
        [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang:en")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang:ru")],
        # Добавьте кнопки для других языков из SUPPORTED_LANGUAGES
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатура соглашения ---
def get_agreement_keyboard(lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(get_text("accept_button", lang), callback_data="accept_terms:true"),
            InlineKeyboardButton(get_text("decline_button", lang), callback_data="decline_terms:true"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Главное меню настроек ---
def get_settings_main_keyboard(lang: str, current_options: dict) -> InlineKeyboardMarkup:
    keyboard = []

    # Кнопка смены языка
    keyboard.append([InlineKeyboardButton(get_text("option_language", lang), callback_data="show_settings_option:language")])

    # Кнопки для опций обработки
    for option_key in PROCESSING_OPTIONS.keys():
        option_name = get_text(f"option_{option_key}", lang) # Получаем локализованное имя опции
        current_value = current_options.get(option_key, "")
        display_value = current_value if current_value else get_text("option_not_set", lang)
        button_text = f"{option_name}: {display_value}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"show_settings_option:{option_key}")])

    return InlineKeyboardMarkup(keyboard)


# --- Клавиатура выбора значения для опции ---
def get_option_value_keyboard(option_key: str, lang: str, current_value: str) -> InlineKeyboardMarkup:
    keyboard = []
    available_values = []

    if option_key == 'language':
        available_values = SUPPORTED_LANGUAGES
        # Создаем кнопки для каждого языка
        for lang_code in available_values:
            # Просто отображаем код языка или можно добавить флаги/полные названия
            lang_name = lang_code.upper()
            # Отмечаем текущий язык
            prefix = "✅ " if lang_code == current_value else ""
            keyboard.append([InlineKeyboardButton(f"{prefix}{lang_name}", callback_data=f"set_lang:{lang_code}")]) # Используем тот же callback что и при первом выборе
    else:
        available_values = PROCESSING_OPTIONS.get(option_key, [])
        # Группируем кнопки по 2-3 в ряд для длинных списков
        row = []
        max_cols = 2 # Например, по 2 кнопки в ряд
        for value in available_values:
            display_text = value if value else get_text("value_not_set", lang) # Отображаем "Default" для пустого значения
            prefix = "✅ " if value == current_value else ""
            row.append(InlineKeyboardButton(f"{prefix}{display_text}", callback_data=f"set_setting:{option_key}:{value}"))
            if len(row) == max_cols:
                keyboard.append(row)
                row = []
        if row: # Добавляем оставшиеся кнопки, если их меньше max_cols
            keyboard.append(row)

        # Добавляем кнопку сброса, если есть текущее значение (не пустое)
        if current_value:
             keyboard.append([InlineKeyboardButton(get_text("reset_button", lang), callback_data=f"set_setting:{option_key}:")]) # Пустое значение для сброса

    # Кнопка "Назад" в главное меню настроек
    keyboard.append([InlineKeyboardButton(get_text("back_button", lang), callback_data="back_to_settings:main")])

    return InlineKeyboardMarkup(keyboard)

# === Клавиатуры для платежей ===

def get_payment_packages_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с доступными пакетами для покупки."""
    keyboard = []
    packages = payments.get_all_packages(lang)
    
    for package_id, package_info in packages.items():
        if package_info:
            # Формируем текст кнопки
            popular_mark = "🔥 " if package_info.get('popular') else ""
            button_text = f"{popular_mark}{package_info['name']}"
            button_text += f"\n{package_info['photos']} фото - ${package_info['price']}"
            
            keyboard.append([InlineKeyboardButton(
                button_text, 
                callback_data=f"buy_package:{package_id}"
            )])
    
    # Кнопка "Назад" или "Отмена"
    keyboard.append([InlineKeyboardButton(
        get_text("back_button", lang), 
        callback_data="cancel_payment"
    )])
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_confirmation_keyboard(package_id: str, lang: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру подтверждения покупки пакета."""
    keyboard = [
        [InlineKeyboardButton(
            get_text("confirm_purchase", lang), 
            callback_data=f"confirm_purchase:{package_id}"
        )],
        [InlineKeyboardButton(
            get_text("back_to_packages", lang), 
            callback_data="show_packages"
        )],
        [InlineKeyboardButton(
            get_text("cancel_button", lang), 
            callback_data="cancel_payment"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_balance_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления балансом."""
    keyboard = [
        [InlineKeyboardButton(
            get_text("buy_photos", lang), 
            callback_data="show_packages"
        )],
        [InlineKeyboardButton(
            get_text("payment_history", lang), 
            callback_data="show_payment_history"
        )],
        [InlineKeyboardButton(
            get_text("back_button", lang), 
            callback_data="back_to_main"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_history_keyboard(lang: str, page: int = 0) -> InlineKeyboardMarkup:
    """Создает клавиатуру для истории платежей."""
    keyboard = []
    
    # Кнопки навигации по страницам (если нужно)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            "⬅️ Назад", 
            callback_data=f"payment_history_page:{page-1}"
        ))
    
    nav_row.append(InlineKeyboardButton(
        "Вперед ➡️", 
        callback_data=f"payment_history_page:{page+1}"
    ))
    
    if nav_row:
        keyboard.append(nav_row)
    
    # Кнопка "Назад к балансу"
    keyboard.append([InlineKeyboardButton(
        get_text("back_button", lang), 
        callback_data="show_balance"
    )])
    
    return InlineKeyboardMarkup(keyboard)
