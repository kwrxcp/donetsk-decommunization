import os
import re
import json
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Логування
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "8672495955")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: Змінна BOT_TOKEN не знайдена!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

LOCATIONS_FILE = "locations.json"

# FSM для подачі власної назви за об'єктом з сайту
class SiteProposalState(StatesGroup):
    waiting_for_custom_name = State()

# FSM для загальної подачі
class ProposalState(StatesGroup):
    city = State()
    old_name = State()
    proposed_name = State()
    description = State()

class FeedbackState(StatesGroup):
    message = State()

# --- КЛАВІАТУРИ (ТІЛЬКИ INLINE) ---

def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏛 Модуль «КАЛЬМІУС»", callback_data="section_kalmius")],
            [InlineKeyboardButton(text="📚 Архів Донецького кряжу", callback_data="section_archive")],
            [InlineKeyboardButton(text="💬 Зворотний зв'язок", callback_data="section_feedback")]
        ]
    )

def get_kalmius_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Запропонувати перейменування", callback_data="kalmius_propose")],
            [InlineKeyboardButton(text="🌐 Переглянути базу на сайті", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text="⬅️ На головну", callback_data="main_menu")]
        ]
    )

def get_cancel_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="main_menu")]
        ]
    )

# --- РОБОТА З JSON ---

def load_locations():
    if not os.path.exists(LOCATIONS_FILE):
        return []
    try:
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Помилка читання locations.json: {e}")
        return []

def save_locations(data):
    try:
        with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Помилка запису в locations.json: {e}")

# --- ОБРОБКА КОМАНД І МЕНЮ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Вітаємо у мультиботі історико-архівного проєкту!\n\n"
        "Цей бот об'єднує ініціативи з дослідження та збереження спадщини Донеччини. "
        "Оберіть потрібний розділ за допомогою меню нижче:"
    )
    await message.answer(text, reply_markup=get_main_menu())

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "Головне меню мультибота. Оберіть розділ:"
    await callback.message.edit_text(text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "section_kalmius")
async def cb_kalmius(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "🏛 **Модуль «КАЛЬМІУС»**\n\n"
        "Топоніміка, деколонізація та переосмислення міського простору Донеччини та Маріуполя.\n"
        "Тут ви можете подати пропозицію щодо перейменування об'єкта до загальної бази даних."
    )
    await callback.message.edit_text(text, reply_markup=get_kalmius_menu(), parse_mode="Markdown")
    await callback.answer()

# --- ПЕРЕХВАТ КОМАНД З САЙТУ (ГНУЧКІ ФІЛЬТРИ) ---

# 1. Обробка голосування з сайту
@router.message(F.text.contains("Голосую за"))
async def process_site_vote(message: Message):
    # Шукаємо ID об'єкта (цифри після ID:) та назву варіанта
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
                    # Порівнюємо без урахування регістру
                    if prop.get("proposed_name", "").strip().lower() == variant.lower():
                        prop["votes"] = prop.get("votes", 0) + 1
                        updated = True
                        break

        if updated:
            save_locations(locations)
            await message.answer(
                f"✅ Ваш голос за **«{variant}»** (Об'єкт ID: {obj_id}) успішно враховано!",
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
            return

    # Якщо ID знайдено, але конкретний варіант в JSON ще не записаний
    await message.answer(
        f"✅ Дякуємо! Ваш голос за **«{variant}»** прийнято та збережено.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

# 2. Обробка пропозиції власної назви з сайту
@router.message(F.text.contains("Пропоную свою назву"))
async def process_site_custom_proposal_start(message: Message, state: FSMContext):
    # Витягуємо ID та назву вулиці незалежно від типу апострофа
    match_id = re.search(r"ID:\s*(\d+)", message.text)
    match_obj = re.search(r"об['’`\s]*єкта:\s*(.*?)\s*\(", message.text, re.IGNORECASE)

    obj_id = match_id.group(1) if match_id else "N/A"
    obj_name = match_obj.group(1).strip() if match_obj else "об'єкта"

    await state.set_state(SiteProposalState.waiting_for_custom_name)
    await state.update_data(obj_name=obj_name, obj_id=obj_id)

    text = (
        f"📍 **Подача власної назви**\n\n"
        f"Об'єкт: **{obj_name}** (ID: `{obj_id}`)\n\n"
        f"Введіть запропоновану назву та коротке обґрунтування одним повідомленням:"
    )
    await message.answer(text, reply_markup=get_cancel_inline_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_custom_name)
async def process_site_custom_proposal_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    custom_text = message.text
    obj_name = data.get("obj_name", "невідомий об'єкт")
    obj_id = data.get("obj_id", "N/A")

    await message.answer(
        "✅ Дякуємо! Вашу пропозицію прийнято та відправлено модераторам.",
        reply_markup=get_main_menu()
    )

    admin_msg = (
        f"📥 **Нова пропозиція з сайту!**\n\n"
        f"📌 **Об'єкт:** {obj_name} (ID: `{obj_id}`)\n"
        f"✨ **Запропонована назва / обґрунтування:**\n{custom_text}\n\n"
        f"👤 **Користувач:** @{message.from_user.username or 'без_юзернейма'} (ID: `{message.from_user.id}`)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Схвалити", callback_data="approve"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data="reject")
        ]
    ])

    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не вдалося відправити модерацію: {e}")

# --- ІНШІ РОЗДІЛИ (АРХІВ ТА ЗВОРОТНИЙ ЗВ'ЯЗОК) ---

@router.callback_query(F.data == "section_archive")
async def cb_archive(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📚 **Архів Донецького кряжу**\n\n"
        "Платформа збереження історичної, архітектурної та культурної спадщини регіону.\n"
        "Вебпортал: highlandsarchive.donetsk.ua"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити портал", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text="⬅️ На головну", callback_data="main_menu")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "section_feedback")
async def cb_feedback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = "💬 **Зворотний зв'язок**\n\nНапишіть ваші запитання чи пропозиції:"
    await callback.message.edit_text(text, reply_markup=get_cancel_inline_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    await state.clear()
    await message.answer("Дякуємо! Повідомлення надіслано адміністрації.", reply_markup=get_main_menu())

    admin_msg = f"💬 **Зворотний зв'язок:**\n\nвід @{message.from_user.username or 'без_юзернейма'}:\n{feedback_text}"
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg)
    except Exception as e:
        logging.error(f"Помилка відправки адміну: {e}")

@router.callback_query(F.data == "approve")
async def approve_proposal(callback: CallbackQuery):
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено**", parse_mode="Markdown")
    await callback.answer("Схвалено!")

@router.callback_query(F.data == "reject")
async def reject_proposal(callback: CallbackQuery):
    await callback.message.edit_text(callback.message.text + "\n\n❌ **СТАТУС: Відхилено**", parse_mode="Markdown")
    await callback.answer("Відхилено.")

# --- ВЕБСЕРВЕР ---

async def handle_root(request):
    return web.Response(text="Bot is running!")

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
    print("Мультибот запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())