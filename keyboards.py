from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from localization import get_text, SUPPORTED_LANGUAGES # Импортируем строки и список языков
import payments # Импортируем модуль платежей
import config # Импортируем конфигурационный файл
import discounts  # new module for personal discounts

# helper to add strike-through to a string (using unicode combining char U+0336)
def _strike(text: str) -> str:
    return ''.join(ch + '\u0336' for ch in text)

LANG_NAMES = {
    "en": "English",
    "ru": "Русский"
}
LANG_FLAGS = {
    "en": "🇬🇧",
    "ru": "🇷🇺"
}

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
        [InlineKeyboardButton(f"{LANG_FLAGS['en']} {LANG_NAMES['en']}", callback_data="set_lang:en")],
        [InlineKeyboardButton(f"{LANG_FLAGS['ru']} {LANG_NAMES['ru']}", callback_data="set_lang:ru")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатура для постоянного меню ---
def get_main_reply_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Создает постоянную клавиатуру с кнопкой 'Меню'."""
    keyboard = [
        [KeyboardButton(get_text("menu_button", lang))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
    keyboard.append([
        InlineKeyboardButton(get_text("back_button", lang), callback_data=back_callback),
        InlineKeyboardButton(get_text("process_button", lang), callback_data="photo_action:process")
    ])

    return InlineKeyboardMarkup(keyboard)

# --- Клавиатура выбора значения для опции (теперь только для языка) ---
def get_option_value_keyboard(option_key: str, lang: str, current_lang: str) -> InlineKeyboardMarkup:
    keyboard = []
    
    if option_key == 'language':
        available_values = SUPPORTED_LANGUAGES
        # Создаем кнопки для каждого языка
        for lang_code in available_values:
            flag = LANG_FLAGS.get(lang_code, "")
            name = LANG_NAMES.get(lang_code, lang_code.upper())
            button_text = f"{flag} {name}".strip()

            if lang_code == current_lang:
                button_text = f"✅ {button_text}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"set_lang:{lang_code}")])

    # Кнопка "Назад"
    keyboard.append([
        InlineKeyboardButton(get_text("back_button", lang), callback_data="back_to_start")
    ])

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
        button_text = f"{option_name}" # Теперь просто название опции
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"photo_option:{option_key}")])

    return InlineKeyboardMarkup(keyboard)

def get_photo_appearance_settings_keyboard(lang: str, current_settings: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для подменю 'Внешность' в потоке настройки фото."""
    keyboard = []

    # Кнопки для опций внешности
    for option_key in APPEARANCE_OPTIONS.keys():
        option_name = get_text(f"option_{option_key}", lang)
        value = current_settings.get(option_key)
        
        if value:
            button_text = f"{option_name}: {value}"
        else:
            button_text = f"{option_name}"
            
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"photo_option:{option_key}")])
    
    # Кнопка "Назад" в главное меню настроек фото
    keyboard.append([
        InlineKeyboardButton(get_text("back_button", lang), callback_data="photo_back:main"),
        InlineKeyboardButton(get_text("process_button", lang), callback_data="photo_action:process")
    ])

    return InlineKeyboardMarkup(keyboard)

def get_photo_option_value_keyboard(option_key: str, lang: str, current_settings: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора значения опции в потоке настройки фото."""
    keyboard = []
    available_values = PROCESSING_OPTIONS.get(option_key, [])
    
    # Группируем кнопки
    row = []
    max_cols = 2
    for value in available_values:
        # Для пустого значения ("") показываем локализованный текст
        display_text = value if value else get_text("value_not_set", lang)
        
        if current_settings.get(option_key) == value:
            display_text = f"✅ {display_text}"

        row.append(InlineKeyboardButton(display_text, callback_data=f"photo_set:{option_key}:{value}"))
        if len(row) == max_cols:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Кнопка "Назад" и "Обработать"
    back_target = "appearance" if option_key in APPEARANCE_OPTIONS else "main"
    
    if option_key in APPEARANCE_OPTIONS.keys():
        keyboard.append([
            InlineKeyboardButton(get_text("back_button", lang), callback_data=f"photo_back:{back_target}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(get_text("back_button", lang), callback_data=f"photo_back:{back_target}"),
            InlineKeyboardButton(get_text("process_button", lang), callback_data="photo_action:process")
        ])

    return InlineKeyboardMarkup(keyboard)

# === Клавиатуры для платежей ===

# async version supporting personal discounts
async def get_payment_packages_keyboard(lang: str, user_id: int | None = None) -> InlineKeyboardMarkup:
    """Creates a keyboard with available packages, adjusting price by user-specific discounts."""
    keyboard: list[list[InlineKeyboardButton]] = []

    packages = payments.get_all_packages(lang)

    for package_id, package_info in packages.items():
        if not package_info:
            continue

        orig_price = package_info["price"]
        price = orig_price
        if user_id is not None:
            disc = await discounts.get_active_discount(user_id, package_id)
            price = await discounts.price_with_discount(price, disc)

        popular_mark = "🔥 " if package_info.get("popular") else ""
        unit_word = "обработок" if lang == "ru" else "edits"
        button_text = f"{popular_mark}{package_info['name']}"
        if price < orig_price:
            old = _strike(f"{orig_price} ₽")
            button_text += f"\n{package_info['photos']} {unit_word} - {old} → {price} ₽"
        else:
            button_text += f"\n{package_info['photos']} {unit_word} - {price} ₽"
        button_text += f"\n{package_info['popular_postfix']}"

        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"buy_package:{package_id}"
            )
        ])

    # Back / cancel button
    keyboard.append([
        InlineKeyboardButton(
            get_text("back_button", lang),
            callback_data="cancel_payment"
        )
    ])

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

# --- Клавиатура для команды /start ---
def get_start_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для приветственного сообщения."""
    keyboard = [
        [InlineKeyboardButton(get_text("upload_photo_button", lang), callback_data="show_upload_prompt")],
        [InlineKeyboardButton(get_text("buy_coins_button", lang), callback_data="show_packages")],
        [
            InlineKeyboardButton(get_text("option_language", lang), callback_data="show_settings_option:language"),
            InlineKeyboardButton(get_text("my_channel_button", lang), url=config.TELEGRAM_CHANNEL_URL)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# === New: keyboard offering choice of payment provider ===

def get_payment_methods_keyboard(package_id: str, lang: str) -> InlineKeyboardMarkup:
    """Creates a keyboard that lets the user choose how to pay for a package."""
    keyboard = [
        # Existing provider – StreamPay
        [InlineKeyboardButton(
            f"💳 {get_text('pay_with_streampay', lang)}",  # e.g. "Pay by card"
            callback_data=f"pay_method:streampay:{package_id}"
        )],
        # New provider – Telegram Stars
        [InlineKeyboardButton(
            f"⭐️ {get_text('pay_with_tgstars', lang)}",  # e.g. "Pay with Telegram Stars"
            callback_data=f"pay_method:tgstars:{package_id}"
        )],
        # Back button
        [InlineKeyboardButton(
            get_text("back_to_packages", lang),
            callback_data="show_packages"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)
