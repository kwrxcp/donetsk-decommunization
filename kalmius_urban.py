import os
import re
import json
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import time

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "8672495955")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: Змінна BOT_TOKEN не знайдена в середовищі виконання!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

LOCATIONS_FILE = "locations.json"
SUBSCRIBERS_FILE = "subscribers.json"
SETTINGS_FILE = "settings.json"
AGREEMENTS_FILE = "agreements.json"
UPLOADS_DIR = "uploads"

os.makedirs(UPLOADS_DIR, exist_ok=True)

if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"tech_works": False, "silence_works": False, "active_notice": None}, f, ensure_ascii=False)

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"tech_works": False, "silence_works": False, "active_notice": None}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка збереження налаштувань сайту: {e}")

# --- ЗГОДИ КОРИСТУВАЧІВ ---
def load_agreements():
    if not os.path.exists(AGREEMENTS_FILE):
        return []
    try:
        with open(AGREEMENTS_FILE, "r", encoding="utf-8") as f:
            return [int(x) for x in json.load(f)]
    except:
        return []

def save_agreements(data):
    try:
        unique_data = list(set([int(x) for x in data]))
        with open(AGREEMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка збереження згод: {e}")

def has_agreed(user_id: int) -> bool:
    return int(user_id) in load_agreements()

def set_agreed(user_id: int):
    agreements = load_agreements()
    if int(user_id) not in agreements:
        agreements.append(int(user_id))
        save_agreements(agreements)

# --- FSM СТАНЫ ---
class FeedbackState(StatesGroup):
    message = State()

class ArchiveUploadState(StatesGroup):
    waiting_for_file = State()

class AdminReplyState(StatesGroup):
    waiting_for_admin_text = State()

class NoticeCreationState(StatesGroup):
    waiting_for_label = State()
    waiting_for_text = State()

# --- БАЗИ ДАНИХ ---
def load_locations():
    if not os.path.exists(LOCATIONS_FILE):
        return []
    try:
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return [int(x) for x in json.load(f)]
    except Exception:
        return []

def save_subscribers(data):
    try:
        unique_subs = list(set([int(x) for x in data]))
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_subs, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def add_subscriber(user_id: int):
    subs = load_subscribers()
    if user_id not in subs:
        subs.append(user_id)
        save_subscribers(subs)

# --- КЛАВІАТУРИ ---
def get_main_reply_menu(user_id: int):
    keyboard_rows = [
        [KeyboardButton(text="📚 Архів Донецького кряжу")],
        [KeyboardButton(text="🏛 Модуль «КАЛЬМІУС»")],
        [KeyboardButton(text="💬 Зворотний зв'язок та Експедиція")]
    ]
    if str(user_id) == str(ADMIN_ID):
        keyboard_rows.append([KeyboardButton(text="🛠 Адмін-панель")])

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_agreement_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Продовжити (Згоден з умовами)", callback_data="agree_privacy")]
        ]
    )

def get_admin_panel_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛠 Тех. роботи"), KeyboardButton(text="⏳ Хвилина мовчання")],
            [KeyboardButton(text="📢 Оповіщення")],
            [KeyboardButton(text="🔙 Головне меню")]
        ],
        resize_keyboard=True
    )

def get_notices_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Створити"), KeyboardButton(text="📋 Переглянути усі активні")],
            [KeyboardButton(text="🗑 Видалити"), KeyboardButton(text="🔙 Назад в адмін-панель")]
        ],
        resize_keyboard=True
    )

def get_cancel_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
        resize_keyboard=True
    )

def get_feedback_inline_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Надіслати архівні матеріали (Фото/Документи)", callback_data="fb_upload_materials")],
            [InlineKeyboardButton(text="❓ Написати команді (Запитання / Допомога)", callback_data="fb_ask_help")]
        ]
    )

def get_digest_keyboard(user_id: int):
    subs = load_subscribers()
    is_sub = int(user_id) in subs
    btn_text = "🔕 Відписатися від дайджесту" if is_sub else "🔔 Підписатися на оновлення Архіву"
    action = "unsubscribe_digest" if is_sub else "subscribe_digest"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити головний вебпортал архіву", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text=btn_text, callback_data=action)]
        ]
    )

# --- ПЕРЕВІРКА ДОСТУПУ (БЛОКУВАННЯ ДО ЗГОДИ) ---
async def check_agreement(message: Message) -> bool:
    user_id = message.from_user.id
    if not has_agreed(user_id):
        privacy_text = (
            "🔒 **ПОЛІТИКА КОНФІДЕНЦІЙНОСТІ ТА ЗГОДА НА ОБРОБКУ ПЕРСОНАЛЬНИХ ДАНИХ**\n\n"
            "Відповідно до Закону України «Про захист персональних даних» № 2297-VI та Закону України «Про електронну комерцію» № 675-VIII, підтвердженням вашої згоди на обробку персональних даних є запуск бота або продовження користування ним.\n\n"
            "**1. Склад персональних даних**\n"
            "Бот здійснює збір та обробку лише мінімально необхідного обсягу даних, а саме:\n"
            "• Ім’я та Прізвище (вказуються у вашому обліковому записі Telegram);\n"
            "• Ідентифікатор користувача (Telegram ID) та юзернейм (`@username`).\n\n"
            "**2. Мета та підстави обробки даних**\n"
            "• **Мета:** Забезпечення коректного функціонування архіву, ідентифікація користувача в системі, збереження налаштувань та надання персоналізованого доступу до матеріалів.\n"
            "• **Підстава:** Ваша добровільна згода, виражена шляхом вчинення конклюдентних дій (запуск бота або надсилання будь-яких команд).\n\n"
            "**3. Передача та зберігання даних**\n"
            "• Персональні дані використовуються виключно для внутрішньої роботи сервісу.\n"
            "• Дані не передаються, не продаються та не розкриваються третім особам, окрім випадків, безпосередньо передбачених чинним законодавством України.\n\n"
            "👉 *Натискаючи кнопку «Продовжити» нижче (або надсилаючи команду /agree), ви підтверджуєте, що ознайомлені з цими умовами та даєте повну й беззастережну згоду на обробку вказаних персональних даних.*"
        )
        await message.answer(privacy_text, reply_markup=get_agreement_keyboard(), parse_mode="Markdown")
        return False
    return True

# --- НАВІГАЦІЯ ТА СТАРТ ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if not await check_agreement(message):
        return

    add_subscriber(user_id)
    await show_main_welcome(message)

@router.message(Command("agree"))
async def cmd_agree(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    set_agreed(user_id)
    add_subscriber(user_id)
    await show_main_welcome(message)

@router.callback_query(F.data == "agree_privacy")
async def cb_agree_privacy(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    set_agreed(user_id)
    add_subscriber(user_id)
    
    await callback.message.delete()
    await show_main_welcome(callback.message)
    await callback.answer("Згоду прийнято!")

async def show_main_welcome(message: Message):
    welcome_text = (
        "📚 **АРХІВ ДОНЕЦЬКОГО КРЯЖУ**\n"
        "_Цифровий простір пам’яті про Донеччину._\n\n"
        "Історія краю складається з тисяч історій, місць, архітектурних пам’яток, імен і свідчень. Наше завдання — збирати, досліджувати та зберігати їх, роблячи спадщину Донеччини доступною кожному.\n\n"
        "🧭 **Що ви шукаєте?**\n"
        "Через цей бот ви можете перейти до тематичних розділів платформи, досліджувати минуле населених пунктів і знайомитися з проєктами архіву.\n\n"
        "Один із них — **«КАЛЬМІУС»**: дослідження топоніміки Донеччини, перейменувань і деколонізації публічного простору.\n\n"
        "_Пам’ять потребує простору, а спадщина — збереження._\n\n"
        "👇 **Оберіть розділ у меню, щоб продовжити.**"
    )
    chat_id = message.chat.id
    await message.answer(welcome_text, reply_markup=get_main_reply_menu(chat_id), parse_mode="Markdown")

@router.message(F.text == "🔙 Головне меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    if not await check_agreement(message):
        return
    await show_main_welcome(message)

@router.message(F.text == "❌ Скасувати")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    if not await check_agreement(message):
        return
    user_id = message.from_user.id
    menu = get_admin_panel_menu() if str(user_id) == str(ADMIN_ID) else get_main_reply_menu(user_id)
    await message.answer("Дію скасовано.", reply_markup=menu)

@router.message(F.text == "📚 Архів Донецького кряжу")
async def text_archive(message: Message, state: FSMContext):
    await state.clear()
    if not await check_agreement(message):
        return
    text = (
        "📚 **Архів Донецького кряжу — Головна платформа**\n\n"
        "Це незалежний цифровий простір збереження урбаністичної, історичної та культурної спадщини "
        "східного регіону України. Тут зібрані унікальні матеріали, дослідження та карти.\n\n"
        "Ви можете підписатися на сповіщення про нові архівні публікації прямо у цьому боті:"
    )
    await message.answer(text, reply_markup=get_digest_keyboard(message.from_user.id), parse_mode="Markdown")

@router.message(F.text == "🏛 Модуль «КАЛЬМІУС»")
async def text_kalmius(message: Message, state: FSMContext):
    await state.clear()
    if not await check_agreement(message):
        return
    text = (
        "🏛 **Модуль «КАЛЬМІУС» (Ініціатива в межах Архіву)**\n\n"
        "Цей спеціальний напрям присвячений процесам деколонізації, дерадянізації та відновлення історичної топонімики "
        "на Донеччині (зокрема у Донецьку та Маріуполі).\n\n"
        "Ви можете переглянути повну базу об'єктів та подати пропозиції на нашому вебпорталі:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити базу Кальміус на сайті", url="https://highlandsarchive.donetsk.ua")]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.in_({"subscribe_digest", "unsubscribe_digest"}))
async def toggle_digest_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    subs = load_subscribers()
    
    if callback.data == "subscribe_digest":
        if user_id not in subs:
            subs.append(user_id)
            save_subscribers(subs)
        await callback.answer("Ви успішно підписалися на дайджест оновлень Архіву!", show_alert=True)
    else:
        if user_id in subs:
            subs.remove(user_id)
            save_subscribers(subs)
        await callback.answer("Ви відписалися від оновлень.", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=get_digest_keyboard(user_id))

# --- ЗВОРОТНИЙ ЗВ'ЯЗОК ТА ЕКСПЕДИЦІЯ (БЕСКОНЕЧНЫЙ ДИАЛОГ) ---
@router.message(F.text == "💬 Зворотний зв'язок та Експедиція")
async def text_feedback_menu(message: Message, state: FSMContext):
    await state.clear()
    if not await check_agreement(message):
        return
    text = "💬 **Зворотний зв'язок та Архівна Експедиція**\n\nОберіть категорію звернення:"
    await message.answer(text, reply_markup=get_feedback_inline_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "fb_ask_help")
async def cb_feedback_help(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = "❓ **Запитання чи звернення до команди Архіву**\n\nНапишіть ваше повідомлення нижче:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Очікуємо на ваше повідомлення...", reply_markup=get_cancel_reply_keyboard())
    await callback.answer()

@router.callback_query(F.data == "fb_upload_materials")
async def cb_feedback_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveUploadState.waiting_for_file)
    text = "📁 **Архівна Експедиція (Фотофіксація)**\n\nНадішліть фотографії або матеріали одним повідомленням:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Прикріпіть файли або медіа:", reply_markup=get_cancel_reply_keyboard())
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    user_id = message.from_user.id
    await state.clear()
    await message.answer("✅ **Дякуємо!** Ваше повідомлення надіслано команді Архіву. Ви можете продовжувати писати у цей чат у разі потреби.", reply_markup=get_main_reply_menu(user_id), parse_mode="Markdown")

    admin_msg = (
        f"💬 **Нове повідомлення від користувача!**\n\n"
        f"👤 **Від:** @{message.from_user.username or 'немає'} (ID: `{user_id}`)\n"
        f"📝 **Текст:**\n{feedback_text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Відповісти користувачу", callback_data=f"admin_reply_{user_id}")]
    ])
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass

@router.message(ArchiveUploadState.waiting_for_file)
async def process_archive_upload(message: Message, state: FSMContext):
    await state.clear()
    caption = message.caption or "Без опису"
    user_id = message.from_user.id

    await message.answer("📸 **Архівні матеріали успішно прийнято!**", reply_markup=get_main_reply_menu(user_id), parse_mode="Markdown")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Відповісти на матеріали", callback_data=f"admin_reply_{user_id}")]
    ])

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID), 
            text=f"📁 **Нові матеріали Експедиції!**\n👤 **Від:** @{message.from_user.username or 'немає'} (ID: `{user_id}`)\n📝 **Опис:** {caption}",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await message.forward(chat_id=int(ADMIN_ID))
    except Exception:
        pass

@router.callback_query(F.data.startswith("admin_reply_"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext):
    target_user_id = callback.data.split("_")[2]
    await state.set_state(AdminReplyState.waiting_for_admin_text)
    await state.update_data(target_user_id=target_user_id)
    
    await callback.message.answer(f"✍️ **Введіть текст відповіді для користувача (ID: `{target_user_id}`):**")
    await callback.answer()

@router.message(AdminReplyState.waiting_for_admin_text, F.from_user.id == int(ADMIN_ID))
async def send_admin_reply_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    if not target_user_id:
        return

    try:
        # Отправляем ответ пользователю с кнопкой ответить обратно админу (или возможностью писать дальше)
        await bot.send_message(
            chat_id=int(target_user_id),
            text=f"💬 **Відповідь від команди Архіву:**\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.answer("✅ **Відповідь успішно доставлена!**", reply_markup=get_admin_panel_menu())
    except Exception as e:
        await message.answer(f"⚠️ Помилка: {e}", reply_markup=get_admin_panel_menu())

# --- АДМІН-ПАНЕЛЬ ---
@router.message(F.text == "🛠 Адмін-панель", F.from_user.id == int(ADMIN_ID))
async def admin_panel_home(message: Message, state: FSMContext):
    await state.clear()
    settings = load_settings()
    
    tech_status = "🟢 Вимкнені" if not settings.get("tech_works") else "🔴 УВІМКНЕНІ"
    silence_status = "🟢 Вимкнена" if not settings.get("silence_works") else "🔴 УВІМКНЕНА"
    
    text = (
        f"🛠 **Адмін-панель управління сайтом:**\n\n"
        f"• Технічні роботи: {tech_status}\n"
        f"• Хвилина мовчання: {silence_status}\n\n"
        f"Оберіть потрібну дію на клавіатурі нижче:"
    )
    await message.answer(text, reply_markup=get_admin_panel_menu(), parse_mode="Markdown")

@router.message(F.text == "🛠 Тех. роботи", F.from_user.id == int(ADMIN_ID))
async def admin_toggle_tech(message: Message):
    settings = load_settings()
    settings["tech_works"] = not settings.get("tech_works", False)
    save_settings(settings)
    
    status = "🔴 УВІМКНЕНО" if settings["tech_works"] else "🟢 ВИМКНЕНО"
    await message.answer(f"Технічні роботи на сайті: **{status}**", reply_markup=get_admin_panel_menu(), parse_mode="Markdown")

@router.message(F.text == "⏳ Хвилина мовчання", F.from_user.id == int(ADMIN_ID))
async def admin_toggle_silence(message: Message):
    settings = load_settings()
    settings["silence_works"] = not settings.get("silence_works", False)
    save_settings(settings)
    
    status = "🔴 УВІМКНЕНО" if settings["silence_works"] else "🟢 ВИМКНЕНО"
    await message.answer(f"Хвилина мовчання на сайті: **{status}**", reply_markup=get_admin_panel_menu(), parse_mode="Markdown")

@router.message(F.text == "📢 Оповіщення", F.from_user.id == int(ADMIN_ID))
async def admin_notices_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📢 **Керування сповіщеннями на сайті:**", reply_markup=get_notices_menu(), parse_mode="Markdown")

@router.message(F.text == "🔙 Назад в адмін-панель", F.from_user.id == int(ADMIN_ID))
async def back_to_admin_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Адмін-панель:", reply_markup=get_admin_panel_menu())

# --- УПРАВЛІННЯ ОПОВІЩЕННЯМИ ---
@router.message(F.text == "➕ Створити", F.from_user.id == int(ADMIN_ID))
async def notice_create_start(message: Message, state: FSMContext):
    await state.set_state(NoticeCreationState.waiting_for_label)
    await message.answer(
        "📢 **Крок 1 із 3: Заголовок сповіщення**\n\nВведіть мітку (наприклад: `Донеччина / новини`):",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="Markdown"
    )

@router.message(NoticeCreationState.waiting_for_label, F.from_user.id == int(ADMIN_ID))
async def notice_get_label(message: Message, state: FSMContext):
    await state.update_data(notice_label=message.text)
    await state.set_state(NoticeCreationState.waiting_for_text)
    await message.answer("📝 **Крок 2 із 3: Текст сповіщення**\n\nВведіть текст повідомлення:", reply_markup=get_cancel_reply_keyboard(), parse_mode="Markdown")

@router.message(NoticeCreationState.waiting_for_text, F.from_user.id == int(ADMIN_ID))
async def notice_get_text(message: Message, state: FSMContext):
    await state.update_data(notice_text=message.text)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 година", callback_data="dur_3600"), InlineKeyboardButton(text="12 годин", callback_data="dur_43200")],
            [InlineKeyboardButton(text="Доба", callback_data="dur_86400"), InlineKeyboardButton(text="2 доби", callback_data="dur_172800")],
            [InlineKeyboardButton(text="Тиждень", callback_data="dur_604800"), InlineKeyboardButton(text="Завжди", callback_data="dur_0")]
        ]
    )
    await message.answer("⏱ **Крок 3 із 3: Оберіть тривалість відображення:**", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("dur_"), F.from_user.id == int(ADMIN_ID))
async def notice_finish_creation(callback: CallbackQuery, state: FSMContext):
    duration_sec = int(callback.data.split("_")[1])
    data = await state.get_data()
    await state.clear()

    label = data.get("notice_label")
    text = data.get("notice_text")
    
    notice_id = "notice_" + str(int(time.time()))
    expires_at = (int(time.time() * 1000) + duration_sec * 1000) if duration_sec > 0 else 0

    settings = load_settings()
    settings["active_notice"] = {
        "id": notice_id,
        "label": label,
        "text": text,
        "expires_at": expires_at
    }
    save_settings(settings)

    await callback.message.edit_text(f"✅ **Сповіщення успішно опубліковано на сайті!**\n\n📌 **{label}**\n{text}", parse_mode="Markdown")
    await callback.message.answer("Оберіть дію:", reply_markup=get_notices_menu())
    await callback.answer("Опубліковано!")

@router.message(F.text == "📋 Переглянути усі активні", F.from_user.id == int(ADMIN_ID))
async def notice_list_active(message: Message):
    settings = load_settings()
    notice = settings.get("active_notice")
    
    if not notice:
        await message.answer("📭 Наразі немає активних сповіщень на сайті.", reply_markup=get_notices_menu())
        return
        
    text = (
        f"📢 **Активне сповіщення на сайті:**\n\n"
        f"📌 **Заголовок:** {notice.get('label')}\n"
        f"📝 **Текст:** {notice.get('text')}"
    )
    await message.answer(text, reply_markup=get_notices_menu(), parse_mode="Markdown")

@router.message(F.text == "🗑 Видалити", F.from_user.id == int(ADMIN_ID))
async def notice_delete(message: Message):
    settings = load_settings()
    settings["active_notice"] = None
    save_settings(settings)
    await message.answer("🗑 **Активне сповіщення успішно видалено з сайту.**", reply_markup=get_notices_menu(), parse_mode="Markdown")

@router.message(Command("broadcast"), F.from_user.id == int(ADMIN_ID))
async def cmd_broadcast(message: Message):
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Вкажіть текст розсилки.")
        return

    subs = load_subscribers()
    if not subs:
        await message.answer("⚠️ Немає підписників.")
        return

    success = 0
    for uid in subs:
        try:
            await bot.send_message(chat_id=int(uid), text=f"📢 **Дайджест оновлень:**\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Розсилку завершено! Доставлено: `{success}`", parse_mode="Markdown")

# --- ВЕБСЕРВЕР ---
async def handle_root(request):
    return web.Response(text="Archival Multibot Service is running!")

async def handle_get_locations(request):
    if os.path.exists(LOCATIONS_FILE):
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        return web.Response(text=data, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})
    return web.Response(text="[]", content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

async def handle_get_settings(request):
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        return web.Response(text=data, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})
    return web.Response(text='{"tech_works": false, "silence_works": false, "active_notice": null}', content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/locations.json", handle_get_locations)
    app.router.add_get("/settings.json", handle_get_settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await web_server()
    print("Мультибот запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())