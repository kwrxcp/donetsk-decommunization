import os
import re
import json
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗ ДАННЫХ ---

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

# --- КЛАВИАТУРЫ ---

def get_main_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏛 Модуль «КАЛЬМІУС»")],
            [KeyboardButton(text="📚 Архів Донецького кряжу")],
            [KeyboardButton(text="💬 Зворотний зв'язок")]
        ],
        resize_keyboard=True
    )

def get_cancel_reply_keyboard():
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
            [InlineKeyboardButton(text="🌐 Відкрити вебпортал архіву", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text=btn_text, callback_data=action)]
        ]
    )

# --- ОСНОВНЫЕ КОМАНДЫ И НАВИГАЦИЯ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Вітаємо у офіційному мультиботі історико-архівного проєкту!\n\n"
        "Цей цифровий простір об'єднує ініціативи з дослідження, документування та збереження "
        "автентичної спадщини Донеччини. Ми працюємо над тим, щоб відновити історичну правду, "
        "подолати наслідки тоталітарної пропаганди та повернути регіону його справжнє обличчя.\n\n"
        "👇 *Оберіть потрібний розділ за допомогою клавіатури нижче:*"
    )
    await message.answer(text, reply_markup=get_main_reply_menu(), parse_mode="Markdown")

@router.message(F.text == "❌ Скасувати")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Дію скасовано. Повертаємось до головного меню:", reply_markup=get_main_reply_menu())

@router.message(F.text == "🏛 Модуль «КАЛЬМІУС»")
async def text_kalmius(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🏛 **Модуль «КАЛЬМІУС» — Переосмислення простору**\n\n"
        "Цей модуль присвячений процесам деколонізації, дерадянізації та відновлення історичної топонімики "
        "міст і селищ Донеччини (зокрема Донецька та Маріуполя).\n\n"
        "Ви можете переглянути повну базу та подати пропозиції на нашому вебпорталі:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити базу на сайті", url="https://highlandsarchive.donetsk.ua")]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.message(F.text == "📚 Архів Донецького кряжу")
async def text_archive(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "📚 **Архів Донецького кряжу**\n\n"
        "Незалежна платформа збереження історичної, архітектурної, урбаністичної та культурної спадщини "
        "східного регіону України.\n\n"
        "Ви можете підписатися на сповіщення про нові матеріали проєкту прямо у цьому боті:"
    )
    await message.answer(text, reply_markup=get_digest_keyboard(message.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data.in_({"subscribe_digest", "unsubscribe_digest"}))
async def toggle_digest_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    subs = load_subscribers()
    
    if callback.data == "subscribe_digest":
        if user_id not in subs:
            subs.append(user_id)
            save_subscribers(subs)
        await callback.answer("Ви успішно підписалися на дайджест оновлень!", show_alert=True)
    else:
        if user_id in subs:
            subs.remove(user_id)
            save_subscribers(subs)
        await callback.answer("Ви відписалися від оновлень.", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=get_digest_keyboard(user_id))

# --- РАЗДЕЛ "ЗВОРОТНІЙ ЗВ'ЯЗОК" С ДВУМЯ КНОПКАМИ ---

@router.message(F.text == "💬 Зворотний зв'язок")
async def text_feedback_menu(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "💬 **Розділ зворотного зв'язку**\n\n"
        "Оберіть потрібну категорію звернення:"
    )
    await message.answer(text, reply_markup=get_feedback_inline_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "fb_ask_help")
async def cb_feedback_help(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = (
        "❓ **Запитання або пропозиції до команди**\n\n"
        "Напишіть ваше повідомлення нижче. Адміністратор відповість вам безпосередньо у цей чат:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Очікуємо на ваше повідомлення...", reply_markup=get_cancel_reply_keyboard())
    await callback.answer()

@router.callback_query(F.data == "fb_upload_materials")
async def cb_feedback_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveUploadState.waiting_for_file)
    text = (
        "📁 **Експедиція та Фотофіксація**\n\n"
        "Надішліть будь-який файл, архівний документ, фотографію або табличку вулиці "
        "одним повідомленням (можна додати текстовий опис):"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Прикріпіть файл або фото:", reply_markup=get_cancel_reply_keyboard())
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    await state.clear()
    await message.answer(
        "✅ **Дякуємо!** Ваше повідомлення успішно надіслано адміністраторам.",
        reply_markup=get_main_reply_menu(),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"💬 **Нове повідомлення підтримки!**\n\n"
        f"👤 **Від:** @{message.from_user.username or 'немає'} | ID: `{message.from_user.id}`\n"
        f"📝 **Текст:**\n{feedback_text}"
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка відправки адміну: {e}")

@router.message(ArchiveUploadState.waiting_for_file)
async def process_archive_upload(message: Message, state: FSMContext):
    await state.clear()
    caption = message.caption or "Без опису"
    user_info = f"👤 **Від:** @{message.from_user.username or 'немає'} | ID: `{message.from_user.id}`"

    await message.answer(
        "📸 **Матеріали успішно отримано!** Дякуємо за внесок у розбудову Архіву.",
        reply_markup=get_main_reply_menu(),
        parse_mode="Markdown"
    )

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID), 
            text=f"📁 **Нові архівні матеріали!**\n{user_info}\n📝 **Опис:** {caption}",
            parse_mode="Markdown"
        )
        await message.forward(chat_id=int(ADMIN_ID))
    except Exception as e:
        logging.error(f"Помилка пересилки медиа админу: {e}")

# --- ОБРАБОТКА ГОЛОСОВАНИЯ И ПРОПОЗИЦИЙ С САЙТА ---

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
                reply_markup=get_main_reply_menu(),
                parse_mode="Markdown"
            )
            return

    await message.answer(
        f"🌟 **Дякуємо!** Ваш голос за варіант **«{variant}»** зафіксовано.",
        reply_markup=get_main_reply_menu(),
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
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_proposed_name)
async def process_site_proposed_name(message: Message, state: FSMContext):
    await state.update_data(proposed_name=message.text)
    await state.set_state(SiteProposalState.waiting_for_reason)
    
    text = (
        "📝 **Історичне обґрунтування (Крок 2 із 3)**\n\n"
        "Напишіть коротке обґрунтування або причину вибору цієї назви:"
    )
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_reason)
async def process_site_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text)
    await state.set_state(SiteProposalState.waiting_for_author)
    
    text = (
        "👤 **Інформація про автора (Крок 3 із 3)**\n\n"
        "Вкажіть ваше ім'я, псевдонім або назву громадської ініціативи:"
    )
    await message.answer(text, reply_markup=get_cancel_reply_keyboard(), parse_mode="Markdown")

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
        "✨ **Дякуємо!** Вашу пропозицію повністю сформовано та надіслано на розгляд модераторам.",
        reply_markup=get_main_reply_menu(),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"📥 **Нова пропозиція з вебпорталу!**\n\n"
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

# --- МОДЕРАЦИЯ И ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ---

@router.callback_query(F.data.startswith("appr_"))
async def approve_proposal_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    obj_id = int(parts[1]) if parts[1].isdigit() else None
    user_id = int(parts[2]) if parts[2].isdigit() else None
    
    # Витягуємо назву та обґрунтування з тексту повідомлення
    text = callback.message.text
    prop_match = re.search(r"Запропонована назва:\s*(.*?)\n", text)
    reason_match = re.search(r"Обґрунтування:\s*(.*?)\n", text)
    
    proposed_name = prop_match.group(1).strip() if prop_match else "Нова назва"
    reason = reason_match.group(1).strip() if reason_match else "Пропозиція громадян"

    # Автоматичний запис у locations.json
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
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено та додано до JSON**", parse_mode="Markdown")
    await callback.answer("Схвалено!")

    # Сповіщення користувачеві
    if user_id:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 **Вітаємо!** Вашу пропозицію щодо назви **«{proposed_name}»** успішно схвалено та додано на сайт!",
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
    await state.update_data(target_user_id=user_id, target_obj_id=obj_id, msg_id=callback.message.message_id)

    await callback.message.answer("⌨️ **Введіть причину відхилення** (вона буде надіслана користувачеві):")
    await callback.answer()

@router.message(AdminRejectState.waiting_for_reason)
async def process_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    reason = message.text
    user_id = int(data.get("target_user_id"))
    obj_id = data.get("target_obj_id")
    await state.clear()

    await message.answer("❌ **Пропозицію відхилено**, а причину надіслано користувачеві.")

    if user_id:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ **Вашу пропозицію щодо об'єкта (ID: {obj_id}) було відхилено.**\n\n📌 **Причина:** {reason}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Помилка надсилання причини користувачу: {e}")

# --- ПЕРЕПИСКА И REPLY АДМИНА КОРИСТУВАЧЕВІ ---

@router.message(F.chat.id == int(ADMIN_ID) & F.reply_to_message)
async def reply_to_user_from_admin(message: Message):
    orig_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    match = re.search(r"ID:\s*`?(\d+)`?", orig_text)
    
    if match:
        user_id = int(match.group(1))
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 **Відповідь від адміністрації:**\n\n{message.text}",
                parse_mode="Markdown"
            )
            await message.answer("✅ Відповідь успішно доставлена користувачеві!")
        except Exception as e:
            await message.answer(f"⚠️ Не вдалося відправити відповідь: {e}")

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
        f"📊 **Статистика мультибота та платформи:**\n\n"
        f"📍 Усього об'єктів у базі: `{total_objects}`\n"
        f"💡 Усього запропонованих варіантів: `{total_proposals}`\n"
        f"🗳 Зібрано голосів: `{total_votes}`\n"
        f"🔔 Підписників на дайджест: `{len(subs)}`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("broadcast"), F.from_user.id == int(ADMIN_ID))
async def cmd_broadcast(message: Message):
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("Використання: `/broadcast Ваш текст розсилки`", parse_mode="Markdown")
        return

    subs = load_subscribers()
    success = 0

    for uid in subs:
        try:
            await bot.send_message(chat_id=uid, text=f"📢 **Дайджест оновлень Архіву:**\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Розсилку завершено! Отримали: `{success}` з `{len(subs)}` підписників.", parse_mode="Markdown")

# --- ВЕБСЕРВЕР ---

async def handle_root(request):
    return web.Response(text="Archival Multibot Service is running!")

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
    print("Мультибот повністю запущеній!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())