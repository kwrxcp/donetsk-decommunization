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
UPLOADS_DIR = "uploads"

os.makedirs(UPLOADS_DIR, exist_ok=True)

# Инициализация файла настроек сайта, если его нет
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"tech_works": False, "silence_works": False}, f)

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"tech_works": False, "silence_works": False}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка збереження налаштувань сайту: {e}")

# --- FSM СТАНЫ ---
class SiteProposalState(StatesGroup):
    waiting_for_proposed_name = State()
    waiting_for_reason = State()
    waiting_for_author = State()

class FeedbackState(StatesGroup):
    message = State()

class ArchiveUploadState(StatesGroup):
    waiting_for_file = State()

class AdminReplyState(StatesGroup):
    waiting_for_admin_text = State()

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
            data = json.load(f)
            return [int(x) for x in data]
    except Exception as e:
        return []

def save_subscribers(data):
    try:
        unique_subs = list(set([int(x) for x in data]))
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_subs, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка запису підписників: {e}")

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
        keyboard_rows.append([KeyboardButton(text="🛠 Адмін-панель (Статистика)")])

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_cancel_reply_keyboard(user_id: int):
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

# --- НАВІГАЦІЯ ТА СТАРТ ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    add_subscriber(user_id)
    
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
    text = "💬 **Зворотний зв'язок та Архівна Експедиція**\n\nОберіть категорію звернення:"
    await message.answer(text, reply_markup=get_feedback_inline_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "fb_ask_help")
async def cb_feedback_help(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = "❓ **Запитання чи звернення до команди Архіву**\n\nНапишіть ваше повідомлення нижче. Адміністратор відповість вам у цей чат:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Очікуємо на ваше повідомлення...", reply_markup=get_cancel_reply_keyboard(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "fb_upload_materials")
async def cb_feedback_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveUploadState.waiting_for_file)
    text = "📁 **Архівна Експедиція (Фотофіксація)**\n\nНадішліть фотографії, скани документів або матеріали одним повідомленням:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("Прикріпіть файли або медіа:", reply_markup=get_cancel_reply_keyboard(callback.from_user.id))
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    user_id = message.from_user.id
    await state.clear()
    await message.answer("✅ **Дякуємо!** Ваше повідомлення надіслано команді Архіву.", reply_markup=get_main_reply_menu(user_id), parse_mode="Markdown")

    admin_msg = (
        f"💬 **Нове звернення від користувача!**\n\n"
        f"👤 **Від:** @{message.from_user.username or 'немає'} (ID: `{user_id}`)\n"
        f"📝 **Текст:**\n{feedback_text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Відповісти користувачу", callback_data=f"admin_reply_{user_id}")]
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

    await message.answer("📸 **Архівні матеріали успішно прийнято!** Дякуємо за внесок.", reply_markup=get_main_reply_menu(user_id), parse_mode="Markdown")

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
    except Exception as e:
        logging.error(f"Помилка пересилки медіа адміну: {e}")

# --- СИСТЕМА ВІДПОВІДЕЙ АДМІНА ---
@router.callback_query(F.data.startswith("admin_reply_"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext):
    target_user_id = callback.data.split("_")[2]
    await state.set_state(AdminReplyState.waiting_for_admin_text)
    await state.update_data(target_user_id=target_user_id)
    
    await callback.message.answer(
        f"✍️ **Введіть текст відповіді для користувача (ID: `{target_user_id}`):**\n"
        f"*(Надішліть повідомлення або натисніть «Скасувати»)*",
        reply_markup=get_cancel_reply_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(AdminReplyState.waiting_for_admin_text, F.from_user.id == int(ADMIN_ID))
async def send_admin_reply_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    if not target_user_id:
        await message.answer("⚠️ Помилка: ID користувача втрачено.", reply_markup=get_main_reply_menu(message.from_user.id))
        return

    try:
        await bot.send_message(
            chat_id=int(target_user_id),
            text=f"💬 **Відповідь від команди Архіву:**\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.answer("✅ **Відповідь успішно доставлена користувачу!**", reply_markup=get_main_reply_menu(message.from_user.id))
    except Exception as e:
        await message.answer(f"⚠️ Не вдалося відправити відповідь: {e}", reply_markup=get_main_reply_menu(message.from_user.id))

# --- АДМІН-ПАНЕЛЬ ТА КЕРУВАННЯ САЙТОМ ---
@router.message(F.text == "🛠 Адмін-панель (Статистика)", F.from_user.id == int(ADMIN_ID))
@router.message(Command("stats"), F.from_user.id == int(ADMIN_ID))
async def cmd_stats(message: Message):
    locations = load_locations()
    subs = load_subscribers()
    settings = load_settings()

    total_objects = len(locations)
    total_proposals = sum(len(item.get("proposals", [])) for item in locations)
    total_votes = sum(sum(prop.get("votes", 0) for prop in item.get("proposals", [])) for item in locations)

    tech_status = "🟢 Вимкнені" if not settings.get("tech_works") else "🔴 УВІМКНЕНІ"
    silence_status = "🟢 Вимкнена" if not settings.get("silence_works") else "🔴 УВІМКНЕНА"

    text = (
        f"📊 **Адмін-панель платформи «Архів Донецького кряжу»:**\n\n"
        f"📍 Об'єктів у базі: `{total_objects}`\n"
        f"💡 Запропонованих варіантів: `{total_proposals}`\n"
        f"🗳 Зібрано голосів: `{total_votes}`\n"
        f"🔔 Підписників на дайджест: `{len(subs)}`\n\n"
        f"🛠 **Статус на сайті:**\n"
        f"• Технічні роботи: {tech_status}\n"
        f"• Хвилина мовчання: {silence_status}\n\n"
        f"💡 *Для розсилки введіть команду:* `/broadcast Ваш текст`"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛠 Тех. роботи (Увімк/Вимк)", callback_data="toggle_tech"),
            InlineKeyboardButton(text="⏳ Хвилина мовчання (Увімк/Вимк)", callback_data="toggle_silence")
        ]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.in_({"toggle_tech", "toggle_silence"}))
async def toggle_site_modes(callback: CallbackQuery):
    settings = load_settings()
    if callback.data == "toggle_tech":
        settings["tech_works"] = not settings.get("tech_works", False)
        status = "увімкнено" if settings["tech_works"] else "вимкнено"
        await callback.answer(f"Технічні роботи на сайті {status}!", show_alert=True)
    elif callback.data == "toggle_silence":
        settings["silence_works"] = not settings.get("silence_works", False)
        status = "увімкнено" if settings["silence_works"] else "вимкнено"
        await callback.answer(f"Хвилина мовчання на сайті {status}!", show_alert=True)
    
    save_settings(settings)
    
    # Обновляем текст админ-панели
    locations = load_locations()
    subs = load_subscribers()
    tech_status = "🟢 Вимкнені" if not settings.get("tech_works") else "🔴 УВІМКНЕНІ"
    silence_status = "🟢 Вимкнена" if not settings.get("silence_works") else "🔴 УВІМКНЕНА"

    text = (
        f"📊 **Адмін-панель платформи «Архів Донецького кряжу»:**\n\n"
        f"📍 Об'єктів у базі: `{len(locations)}`\n"
        f"🔔 Підписників на дайджест: `{len(subs)}`\n\n"
        f"🛠 **Статус на сайті:**\n"
        f"• Технічні роботи: {tech_status}\n"
        f"• Хвилина мовчання: {silence_status}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛠 Тех. роботи (Увімк/Вимк)", callback_data="toggle_tech"),
            InlineKeyboardButton(text="⏳ Хвилина мовчання (Увімк/Вимк)", callback_data="toggle_silence")
        ]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except:
        pass

@router.message(Command("broadcast"), F.from_user.id == int(ADMIN_ID))
async def cmd_broadcast(message: Message):
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ **Помилка!** Вкажіть текст розсилки.", parse_mode="Markdown")
        return

    subs = load_subscribers()
    if not subs:
        await message.answer("⚠️ У базі немає жодного підписника для розсилки.")
        return

    success = 0
    failed = 0
    await message.answer(f"⏳ **Розпочинаємо розсилку для {len(subs)} підписників...**")

    for uid in subs:
        try:
            await bot.send_message(
                chat_id=int(uid), 
                text=f"📢 **Дайджест оновлень «Архіву Донецького кряжу»:**\n\n{text_to_send}", 
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1

    await message.answer(f"✅ **Розсилку завершено!**\nДоставлено: `{success}`\nПомилок: `{failed}`", parse_mode="Markdown")

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
    return web.Response(text='{"tech_works": false, "silence_works": false}', content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

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
    print("Архівний мультибот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())