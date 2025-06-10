from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from localization import get_text, SUPPORTED_LANGUAGES # Импортируем строки и список языков
import payments # Импортируем модуль платежей

# --- Опции для настроек (как в config.py или здесь) ---
APPEARANCE_OPTIONS = {
    "postprocessing": ["", "anime", "upscale"], # "" - не выбрано
    "age": ["", "18", "20", "30", "40", "50"],
    "breast_size": ["", "small", "normal", "big"],
    "body_type": ["", "skinny", "normal", "curvy", "muscular"],
    "butt_size": ["", "small", "normal", "big"],
}

SCENE_OPTIONS = {
    "pose": [ # Из картинки пользователя
        "Blowjob", "Doggy Style", "Cumshot", "Cumshot POV", "Shower Room",
        "Shibari", "Ahegao", "Ahegao cum", "Holding tits", "Missionary POV",
        "Cowgirl POV", "Anal Fuck", "Legs up presenting", "Spreading legs",
        "Tit Fuck", "TGirl", "Tits On Glass", "Christmas", "Winter 1", "naked cum", 
        "pregnant"
    ],
    "cloth": [ # Из картинки пользователя
        "bikini", "lingerie", "sport wear", "bdsm", "latex",
        "teacher", "schoolgirl", "bikini leopard",  "naked tatoo",
        "witch", "sexy witch", "sexy maid", "Christmas underwear", 
        "cheerleader", "police", "secretary"
    ]
}

PROCESSING_OPTIONS = {**APPEARANCE_OPTIONS, **SCENE_OPTIONS}

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
def get_settings_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        # Кнопка смены языка
        [InlineKeyboardButton(get_text("option_language", lang), callback_data="show_settings_option:language")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатура подменю настроек внешности (может быть использована и новым потоком) ---
def get_appearance_settings_keyboard(lang: str, is_photo_flow: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    
    base_callback = "photo_option" if is_photo_flow else "show_settings_option"
    back_callback = "photo_back:main" if is_photo_flow else "back_to_settings:main"

    # Кнопки для опций обработки
    for option_key in APPEARANCE_OPTIONS.keys():
        option_name = get_text(f"option_{option_key}", lang) # Получаем локализованное имя опции
        display_value = get_text("option_not_set", lang)
        button_text = f"{option_name}: {display_value}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"{base_callback}:{option_key}")])
    
    # Кнопка "Назад"
    keyboard.append([InlineKeyboardButton(get_text("back_button", lang), callback_data=back_callback)])

    return InlineKeyboardMarkup(keyboard)

# --- Клавиатура выбора значения для опции (может быть использована и новым потоком) ---
def get_option_value_keyboard(option_key: str, lang: str, is_photo_flow: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    available_values = []

    set_callback_base = "photo_set" if is_photo_flow else "set_setting"
    back_target_base = "photo_back" if is_photo_flow else "back_to_settings"

    if option_key == 'language':
        available_values = SUPPORTED_LANGUAGES
        # Создаем кнопки для каждого языка
        for lang_code in available_values:
            # Просто отображаем код языка или можно добавить флаги/полные названия
            lang_name = lang_code.upper()
            # Отмечаем текущий язык
            keyboard.append([InlineKeyboardButton(f"{lang_name}", callback_data=f"set_lang:{lang_code}")]) # Используем тот же callback что и при первом выборе
    else:
        available_values = PROCESSING_OPTIONS.get(option_key, [])
        # Группируем кнопки по 2-3 в ряд для длинных списков
        row = []
        max_cols = 2 # Например, по 2 кнопки в ряд
        for value in available_values:
            display_text = value if value else get_text("value_not_set", lang) # Отображаем "Default" для пустого значения
            row.append(InlineKeyboardButton(f"{display_text}", callback_data=f"{set_callback_base}:{option_key}:{value}"))
            if len(row) == max_cols:
                keyboard.append(row)
                row = []
        if row: # Добавляем оставшиеся кнопки, если их меньше max_cols
            keyboard.append(row)

    # Кнопка "Назад" в главное меню настроек или в подменю
    back_target = "appearance" if option_key in APPEARANCE_OPTIONS else "main"
    keyboard.append([InlineKeyboardButton(get_text("back_button", lang), callback_data=f"{back_target_base}:{back_target}")])

    return InlineKeyboardMarkup(keyboard)

# === Клавиатуры для нового потока настройки фото ===

def get_photo_settings_keyboard(lang: str, current_settings: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для настройки параметров конкретного фото."""
    keyboard = []
    
    # Кнопка для подменю внешности
    keyboard.append([InlineKeyboardButton(
        get_text("option_appearance", lang), 
        callback_data="photo_submenu:appearance"
    )])

    # Кнопки для опций сцены (поза и одежда)
    for option_key in SCENE_OPTIONS.keys():
        option_name = get_text(f"option_{option_key}", lang)
        value = current_settings.get(option_key)
        display_value = value if value else get_text("value_not_set", lang)
        button_text = f"{option_name}: {display_value}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"photo_option:{option_key}")])

    # Кнопка "Обработать" и "Отмена"
    keyboard.append([
        InlineKeyboardButton(get_text("process_button", lang), callback_data="photo_action:process"),
        InlineKeyboardButton(get_text("cancel_button", lang), callback_data="photo_action:cancel")
    ])

    return InlineKeyboardMarkup(keyboard)

def get_photo_appearance_settings_keyboard(lang: str, current_settings: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для подменю 'Внешность' в потоке настройки фото."""
    keyboard = []

    # Кнопки для опций внешности
    for option_key in APPEARANCE_OPTIONS.keys():
        option_name = get_text(f"option_{option_key}", lang)
        value = current_settings.get(option_key)
        display_value = value if value else get_text("value_not_set", lang)
        button_text = f"{option_name}: {display_value}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"photo_option:{option_key}")])
    
    # Кнопка "Назад" в главное меню настроек фото
    keyboard.append([InlineKeyboardButton(get_text("back_button", lang), callback_data="photo_back:main")])

    return InlineKeyboardMarkup(keyboard)

def get_photo_option_value_keyboard(option_key: str, lang: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора значения опции в потоке настройки фото."""
    keyboard = []
    available_values = PROCESSING_OPTIONS.get(option_key, [])
    
    # Группируем кнопки
    row = []
    max_cols = 2
    for value in available_values:
        # Для пустого значения ("") показываем локализованный текст
        display_text = value if value else get_text("value_not_set", lang)
        row.append(InlineKeyboardButton(display_text, callback_data=f"photo_set:{option_key}:{value}"))
        if len(row) == max_cols:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Кнопка "Назад"
    back_target = "appearance" if option_key in APPEARANCE_OPTIONS else "main"
    keyboard.append([InlineKeyboardButton(get_text("back_button", lang), callback_data=f"photo_back:{back_target}")])

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
            button_text += f"\n{package_info['photos']} фото - {package_info['price']} ₽"
            
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
