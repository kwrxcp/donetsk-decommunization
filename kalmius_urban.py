import os
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

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Отримання змінних середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "8672495955")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: Змінна BOT_TOKEN не знайдена в Environment Variables!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

LOCATIONS_FILE = "locations.json"

# Стани FSM для подачі пропозиції
class ProposalState(StatesGroup):
    city = State()
    old_name = State()
    proposed_name = State()
    description = State()

# Інлайн-клавіатура головного меню
def get_main_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏛 КАЛЬМІУС", callback_data="menu_kalmius"),
                InlineKeyboardButton(text="📚 АРХІВ", callback_data="menu_archive")
            ],
            [
                InlineKeyboardButton(text="➕ Запропонувати перейменування", callback_data="menu_propose")
            ]
        ]
    )

def load_locations():
    if not os.path.exists(LOCATIONS_FILE):
        return []
    try:
        with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_location(data):
    locations = load_locations()
    locations.append(data)
    with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(locations, f, ensure_ascii=False, indent=4)

# --- ОБРОБНИКИ КОМАНД ТА КНОПОК ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Вітаємо у боті історико-архівного проєкту «Архів Донецького кряжу»!\n\n"
        "Цей бот супроводжує портал декомунізації та переосмислення міського простору Донеччини. "
        "Оберіть потрібний розділ за допомогою кнопок нижче:"
    )
    await message.answer(text, reply_markup=get_main_inline_keyboard())

@router.callback_query(F.data == "menu_kalmius")
async def cb_kalmius(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "🏛 **Модуль «КАЛЬМІУС»**\n\n"
        "Розділ міської топоніміки та деколонізації простору Донеччини та Маріуполя.\n"
        "Ви можете переглянути актуальну базу або подати власну пропозицію щодо перейменування об'єкта."
    )
    await callback.message.edit_text(text, reply_markup=get_main_inline_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_archive")
async def cb_archive(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📚 **Архів Донецького кряжу**\n\n"
        "Платформа збереження історичної, архітектурної та культурної спадщини регіону.\n"
        "Вебпортал: highlandsarchive.donetsk.ua"
    )
    await callback.message.edit_text(text, reply_markup=get_main_inline_keyboard(), parse_mode="Markdown")
    await callback.answer()

# --- СЦЕНАРІЙ ПОДАЧІ ПРОПОЗИЦІЇ ---

@router.callback_query(F.data == "menu_propose")
async def cb_start_proposal(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProposalState.city)
    await callback.message.answer("Вкажіть місто (наприклад, Донецьк або Маріуполь):")
    await callback.answer()

@router.message(ProposalState.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(ProposalState.old_name)
    await message.answer("Введіть поточну / стару назву об'єкта (наприклад, вул. Леніна):")

@router.message(ProposalState.old_name)
async def process_old_name(message: Message, state: FSMContext):
    await state.update_data(old_name=message.text)
    await state.set_state(ProposalState.proposed_name)
    await message.answer("Введіть пропоновану нову назву (або історичну альтернативу):")

@router.message(ProposalState.proposed_name)
async def process_proposed_name(message: Message, state: FSMContext):
    await state.update_data(proposed_name=message.text)
    await state.set_state(ProposalState.description)
    await message.answer("Додайте короткий опис / обґрунтування пропозиції:")

@router.message(ProposalState.description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    data = await state.get_data()
    await state.clear()

    await message.answer("Дякуємо! Ваша пропозиція успішно відправлена на модерацію.", reply_markup=get_main_inline_keyboard())

    admin_text = (
        f"📥 **Нова пропозиція перейменування!**\n\n"
        f"🌆 **Місто:** {data['city']}\n"
        f"📌 **Стара назва:** {data['old_name']}\n"
        f"✨ **Запропонована назва:** {data['proposed_name']}\n"
        f"📝 **Обґрунтування:** {data['description']}\n"
        f"👤 **Від користувача:** @{message.from_user.username or 'без_юзернейма'} (ID: `{message.from_user.id}`)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Схвалити", callback_data="approve"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data="reject")
        ]
    ])

    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не вдалося надіслати заявку адміну: {e}")

@router.callback_query(F.data == "approve")
async def approve_proposal(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено**", parse_mode="Markdown")
    await callback.answer("Пропозицію схвалено!")

@router.callback_query(F.data == "reject")
async def reject_proposal(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n❌ **СТАТУС: Відхилено**", parse_mode="Markdown")
    await callback.answer("Пропозицію відхилено.")

# --- МІНІ-ВЕБСЕРВЕР ДЛЯ RENDER WEB SERVICE ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Вебсервер запущено на порті {PORT}")

async def main():
    # Запускаємо вебсервер і поллінг бота одночасно
    await web_server()
    print("Бот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())