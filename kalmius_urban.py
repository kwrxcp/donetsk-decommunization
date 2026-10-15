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

# Налаштування логування
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
UPLOADS_DIR = "uploads"

os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- FSM СТАНЫ ---

class SiteProposalState(StatesGroup):
    waiting_for_proposed_name = State()
    waiting_for_reason = State()
    waiting_for_author = State()

class FeedbackState(StatesGroup):
    message = State()

class ArchiveUploadState(StatesGroup):
    waiting_for_file = State()

class AdminRejectState(StatesGroup):
    waiting_for_reason = State()

# --- БАЗИ ДАНИХ ---

def load_locations():
    if not os.path.exists(LOCATIONS_FILE):
        return []
    try:
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Помилка читання {LOCATIONS_FILE}: {e}")
        return []

def save_locations(data):
    try:
        with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка запису в {LOCATIONS_FILE}: {e}")

def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return []

def save_subscribers(data):
    try:
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка запису підписників: {e}")

# --- КЛАВІАТУРИ (З АДМІНСЬКОЮ КНОПКОЮ ВНИЗУ) ---

def get_main_reply_menu(user_id: int):
    keyboard_rows = [
        [KeyboardButton(text="📚 Архів Донецького кряжу")],
        [KeyboardButton(text="🏛 Модуль «КАЛЬМІУС»")],
        [KeyboardButton(text="💬 Зворотний зв'язок та Експедиція")]
    ]
    # Якщо користувач — адміністратор, додаємо кнопку керування прямо на клавіатуру внизу
    if str(user_id) == str(ADMIN_ID):
        keyboard_rows.append([KeyboardButton(text="🛠 Адмін-панель (Статистика)")])

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_cancel_reply_keyboard(user_id: int):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Скасувати")]
        ],
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
    is_sub = user_id in subs
    btn_text = "🔕 Відписатися від дайджесту" if is_sub else "🔔 Підписатися на оновлення Архіву"
    action = "unsubscribe_digest" if is_sub else "subscribe_digest"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити головний вебпортал архіву", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text=btn_text, callback_data=action)]
        ]
    )

# --- ГОЛОВНЕ МЕНЮ ТА НАВІГАЦІЯ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    text = (
        "Вітаємо у офіційному мультиботі платформи **«Архів Донецького кряжу»**!\n\n"
        "Наш головний фокус — збереження історичної, культурної та архітектурної спадщини Донеччини, "
        "документування пам'яті та дослідження регіону.\n\n"
        "Як частина проєкту, модуль **«КАЛЬМІУС»** охоплює питання топоніміки та деколонізації.\n\n"
        "👇 *Оберіть потрібний розділ за допомогою клавіатури нижче:*"
    )
    await message.answer(text, reply_markup=get_main_reply_menu(user_id), parse_mode="Markdown")

@router.message(F.text == "❌ Скасувати")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Дію скасовано. Повертаємось до головного меню:", reply_markup=get_main_reply_menu(message.from_user.id))

@router.message(F.text == "📚 Архів Донецького кряжу")
async def text_archive(message: Message, state: FSMContext):
    await state.clear()
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

@router.message(F.text == "🛠 Адмін-панель (Статистика)")
async def admin_keyboard_stats(message: Message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    
    locations = load_locations()
    subs = load_subscribers()

    total_objects = len(locations)
    total_proposals = sum(len(item.get("proposals", [])) for item in locations)
    total_votes = sum(
        sum(prop.get("votes", 0) for prop in item.get("proposals", []))
        for item in locations
    )

    text = (
        f"📊 **Адмін-панель платформи «Архів Донецького кряжу»:**\n\n"
        f"📍 Об'єктів у базі (Кальміус): `{total_objects}`\n"
        f"💡 Запропонованих варіантів: `{total_proposals}`\n"
        f"🗳 Зібрано голосів: `{total_votes}`\n"
        f"🔔 Підписників на дайджест: `{len(subs)}`\n\n"
        f"💡 *Для розсилки використовуйте команду `/broadcast Текст`*"
    )
    await message.answer(text, reply_markup=get_main_reply_menu(message.from_user.id), parse_mode="Markdown")

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

# --- ЗВОРОТНИЙ ЗВ'ЯЗОК ТА ЕКСПЕДИЦІЯ ---

@router.message(F.text == "💬 Зворотний зв'язок та Експедиція")
async def text_feedback_menu(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "💬 **Зворотний зв'язок та Архівна Експедиція**\n\n"
        "Оберіть категорію звернення:"
    )
    await message.answer(text, reply_markup=get_feedback_inline_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "fb_ask_help")
async def cb_feedback_help(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = (
        "❓ **Запитання чи звернення до команди Архіву**\n\n"
        "Напишіть ваше повідомлення нижче. Адміністратор відповість вам безпосередньо у цей чат:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Очікуємо на ваше повідомлення...", reply_markup=get_cancel_reply_keyboard(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "fb_upload_materials")
async def cb_feedback_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveUploadState.waiting_for_file)
    text = (
        "📁 **Архівна Експедиція (Фотофіксація матеріалів)**\n\n"
        "Надішліть старі фотографії, скани документів, таблички вулиць або спогади "
        "одним повідомленням (можна додати текстовий опис):"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Прикріпіть файли або медіа:", reply_markup=get_cancel_reply_keyboard(callback.from_user.id))
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    user_id = message.from_user.id
    await state.clear()
    await message.answer(
        "✅ **Дякуємо!** Ваше повідомлення надіслано команді Архіву.",
        reply_markup=get_main_reply_menu(user_id),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"💬 **Повідомлення підтримки (Архів):**\n\n"
        f"👤 **Від:** @{message.from_user.username or 'немає'} | ID: `{user_id}`\n"
        f"📝 **Текст:**\n{feedback_text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Відповісти на це повідомлення", callback_data=f"reply_to_{user_id}")]
    ])
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка відправки адміну: {e}")

@router.message(ArchiveUploadState.waiting_for_file)
async def process_archive_upload(message: Message, state: FSMContext):
    await state.clear()
    caption = message.caption or "Без опису"
    user_id = message.from_user.id
    user_info = f"👤 **Від:** @{message.from_user.username or 'немає'} | ID: `{user_id}`"

    await message.answer(
        "📸 **Архівні матеріали успішно прийнято!** Дякуємо за поповнення фонду.",
        reply_markup=get_main_reply_menu(user_id),
        parse_mode="Markdown"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Відповісти на матеріали", callback_data=f"reply_to_{user_id}")]
    ])

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID), 
            text=f"📁 **Нові матеріали (Експедиція архіву):**\n{user_info}\n📝 **Опис:** {caption}",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await message.forward(chat_id=int(ADMIN_ID))
    except Exception as e:
        logging.error(f"Помилка пересилки медіа адміну: {e}")

# --- КНОПКА ТА REPLY ДЛЯ ВІДПОВІДІ АДМІНА КОРИСТУВАЧУ ---

@router.callback_query(F.data.startswith("reply_to_"))
async def admin_start_direct_reply(callback: CallbackQuery, state: FSMContext):
    user_id = callback.data.split("_")[2]
    await state.set_state(AdminRejectState.waiting_for_reason)
    await state.update_data(target_user_id=user_id)
    
    await callback.message.answer(f"✍️ **Введіть відповідь для користувача (ID: {user_id}):**")
    await callback.answer()

@router.message(F.chat.id == int(ADMIN_ID))
async def admin_message_router(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    if target_user_id and message.text and not message.text.startswith("/") and message.text != "🛠 Адмін-панель (Статистика)":
        await state.clear()
        try:
            await bot.send_message(
                chat_id=int(target_user_id),
                text=f"💬 **Відповідь від команди Архіву:**\n\n{message.text}",
                parse_mode="Markdown"
            )
            await message.answer("✅ Відповідь успішно надіслано користувачеві!")
        except Exception as e:
            await message.answer(f"⚠️ Помилка надсилання: {e}")
        return

    if message.reply_to_message:
        orig_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        match = re.search(r"ID:\s*`?(\d+)`?", orig_text)
        
        if match:
            user_id = int(match.group(1))
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"💬 **Відповідь від команди Архіву:**\n\n{message.text}",
                    parse_mode="Markdown"
                )
                await message.answer("✅ Відповідь через Reply успішно доставлена!")
            except Exception as e:
                await message.answer(f"⚠️ Не вдалося відправити відповідь: {e}")

# --- ГОЛОСУВАННЯ ТА ПРОПОЗИЦІЇ З САЙТУ ---

@router.message(F.text.contains("Голосую за"))
async def process_site_vote(message: Message):
    match_id = re.search(r"ID:\s*(\d+)", message.text)
    match_variant = re.search(r"Голосую за:\s*(.*?)\s*\(", message.text)

    obj_id = int(match_id.group(1)) if match_id else None
    variant = match_variant.group(1).strip() if match_variant else "обраний варіант"

    if obj_id:
        locations = load_locations()
        updated = False

        for item in locations:
            if item.get("id") == obj_id:
                for prop in item.get("proposals", []):
                    if prop.get("proposed_name", "").strip().lower() == variant.lower():
                        prop["votes"] = prop.get("votes", 0) + 1
                        updated = True
                        break

        if updated:
            save_locations(locations)
            await message.answer(
                f"🌟 **Ваш голос зараховано!**\n\nВи підтримали варіант: **«{variant}»** (ID: `{obj_id}`).",
                reply_markup=get_main_reply_menu(message.from_user.id),
                parse_mode="Markdown"
            )
            return

    await message.answer(
        f"🌟 **Дякуємо!** Ваш голос за варіант **«{variant}»** зафіксовано.",
        reply_markup=get_main_reply_menu(message.from_user.id),
        parse_mode="Markdown"
    )

@router.message(F.text.contains("Пропоную свою назву"))
async def process_site_custom_proposal_start(message: Message, state: FSMContext):
    match_id = re.search(r"ID:\s*(\d+)", message.text)
    match_obj = re.search(r"об['’`\s]*єкта:\s*(.*?)\s*\(", message.text, re.IGNORECASE)

    obj_id = match_id.group(1) if match_id else "N/A"
    obj_name = match_obj.group(1).strip() if match_obj else "об'єкта"

    await state.set_state(SiteProposalState.waiting_for_proposed_name)
    await state.update_data(obj_name=obj_name, obj_id=obj_id)

    text = (
        f"📍 **Ініціювання нової назви (Крок 1 із 3)**\n\n"
        f"Об'єкт: **{obj_name}** (ID: `{obj_id}`)\n\n"
        f"Введіть **варіант нової назви**, яку ви пропонуєте на заміну:"
    )
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(message.from_user.id), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_proposed_name)
async def process_site_proposed_name(message: Message, state: FSMContext):
    await state.update_data(proposed_name=message.text)
    await state.set_state(SiteProposalState.waiting_for_reason)
    
    text = (
        "📝 **Історичне обґрунтування (Крок 2 із 3)**\n\n"
        "Напишіть коротке обґрунтування або причину вибору цієї назви:"
    )
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(message.from_user.id), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_reason)
async def process_site_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text)
    await state.set_state(SiteProposalState.waiting_for_author)
    
    text = (
        "👤 **Інформація про автора (Крок 3 із 3)**\n\n"
        "Вкажіть ваше ім'я, псевдонім або назву громадської ініціативи:"
    )
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(message.from_user.id), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_author)
async def process_site_author_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    author = message.text
    await state.clear()

    obj_name = data.get("obj_name", "невідомий об'єкт")
    obj_id = data.get("obj_id", "N/A")
    proposed_name = data.get("proposed_name")
    reason = data.get("reason")
    user_id = message.from_user.id

    await message.answer(
        "✨ **Дякуємо!** Вашу пропозицію повністю сформовано та надіслано модераторам Архіву.",
        reply_markup=get_main_reply_menu(user_id),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"📥 **Нова пропозиція (Кальміус / Вебпортал):**\n\n"
        f"📌 **Об'єкт:** {obj_name} (ID: `{obj_id}`)\n"
        f"✨ **Запропонована назва:** {proposed_name}\n"
        f"📝 **Обґрунтування:** {reason}\n"
        f"👤 **Авторство:** {author}\n"
        f"🔗 **Користувач:** @{message.from_user.username or 'немає'} (ID: `{user_id}`)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Схвалити", callback_data=f"appr_{obj_id}_{user_id}_{proposed_name[:15]}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"rejl_{user_id}_{obj_id}")
        ]
    ])

    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка надсилання пропозиції адміну: {e}")

# --- МОДЕРАЦІЯ ТА ВІДХИЛЕННЯ ---

@router.callback_query(F.data.startswith("appr_"))
async def approve_proposal_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    obj_id = int(parts[1]) if parts[1].isdigit() else None
    user_id = int(parts[2]) if parts[2].isdigit() else None
    
    text = callback.message.text
    prop_match = re.search(r"Запропонована назва:\s*(.*?)\n", text)
    reason_match = re.search(r"Обґрунтування:\s*(.*?)\n", text)
    
    proposed_name = prop_match.group(1).strip() if prop_match else "Нова назва"
    reason = reason_match.group(1).strip() if reason_match else "Пропозиція громадян"

    if obj_id:
        locations = load_locations()
        for item in locations:
            if item.get("id") == obj_id:
                if "proposals" not in item:
                    item["proposals"] = []
                item["proposals"].append({
                    "proposed_name": proposed_name,
                    "reason": reason,
                    "votes": 1
                })
                break
        save_locations(locations)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено та додано до бази JSON**", parse_mode="Markdown")
    await callback.answer("Схвалено!")

    if user_id:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 **Вітаємо!** Вашу пропозицію щодо назви **«{proposed_name}»** схвалено й додано на сайт Архіву!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Не вдалося відправити сповіщення користувачу: {e}")

@router.callback_query(F.data.startswith("rejl_"))
async def start_reject_process(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    user_id = parts[1]
    obj_id = parts[2]

    await state.set_state(AdminRejectState.waiting_for_reason)
    await state.update_data(target_user_id=user_id, target_obj_id=obj_id)

    await callback.message.answer("⌨️ **Введіть причину відхилення** (вона буде надіслана користувачеві):")
    await callback.answer()

@router.message(AdminRejectState.waiting_for_reason)
async def process_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    if "target_obj_id" not in data:
        return

    reason = message.text
    user_id = int(data.get("target_user_id"))
    obj_id = data.get("target_obj_id")
    await state.clear()

    await message.answer("❌ **Пропозицію відхилено**, причину надіслано автору.")

    if user_id:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ **Вашу пропозицію щодо об'єкта (ID: {obj_id}) було відхилено.**\n\n📌 **Причина:** {reason}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Помилка надсилання причини користувачу: {e}")

# --- АДМІН-КОМАНДИ (/stats ТА /broadcast) ---

@router.message(Command("stats"), F.from_user.id == int(ADMIN_ID))
async def cmd_stats(message: Message):
    locations = load_locations()
    subs = load_subscribers()

    total_objects = len(locations)
    total_proposals = sum(len(item.get("proposals", [])) for item in locations)
    total_votes = sum(
        sum(prop.get("votes", 0) for prop in item.get("proposals", []))
        for item in locations
    )

    text = (
        f"📊 **Статистика платформи «Архів Донецького кряжу»:**\n\n"
        f"📍 Об'єктів у базі (Кальміус): `{total_objects}`\n"
        f"💡 Запропонованих варіантів: `{total_proposals}`\n"
        f"🗳 Зібрано голосів: `{total_votes}`\n"
        f"🔔 Підписників на дайджест: `{len(subs)}`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("broadcast"), F.from_user.id == int(ADMIN_ID))
async def cmd_broadcast(message: Message):
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("Використання: `/broadcast Ваш текст дайджесту`", parse_mode="Markdown")
        return

    subs = load_subscribers()
    success = 0

    for uid in subs:
        try:
            await bot.send_message(chat_id=uid, text=f"📢 **Дайджест оновлень «Архіву Донецького кряжу»:**\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Розсилку завершено! Доставлено: `{success}` з `{len(subs)}` підписників.", parse_mode="Markdown")

# --- ВЕБСЕРВЕР ---

async def handle_root(request):
    return web.Response(text="Archival Multibot Service & API is running!")

async def handle_get_locations(request):
    if os.path.exists(LOCATIONS_FILE):
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        return web.Response(text=data, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})
    return web.Response(text="[]", content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/locations.json", handle_get_locations)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await web_server()
    print("Архівний мультибот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())