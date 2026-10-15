import os
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Отримання змінних середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "8672495955")

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

# Стани FSM для коментаря при відхиленні
class RejectState(StatesGroup):
    waiting_for_reason = State()

# Клавіатури
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏛 КАЛЬМІУС"), KeyboardButton(text="📚 АРХІВ ДОНЕЦЬКОГО КРЯЖУ")],
            [KeyboardButton(text="➕ Запропонувати перейменування")]
        ],
        resize_keyboard=True
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
        "Тут ви можете пропонувати нові назви для об'єктів або звертатися до адміністрації."
    )
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(F.text == "🏛 КАЛЬМІУС")
async def btn_kalmius(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🏛 **Модуль «КАЛЬМІУС»**\n\n"
        "Розділ міської топоніміки та деколонізації простору Донеччини та Маріуполя.\n"
        "Ви можете переглянути актуальну базу або подати власну пропозицію щодо перейменування об'єкта."
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "📚 АРХІВ ДОНЕЦЬКОГО КРЯЖУ")
async def btn_archive(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "📚 **Архів Донецького кряжу**\n\n"
        "Платформа збереження історичної, архітектурної та культурної спадщини регіону.\n"
        "Вебпортал: highlandsarchive.donetsk.ua"
    )
    await message.answer(text, parse_mode="Markdown")

# --- СЦЕНАРІЙ ПОДАЧІ ПРОПОЗИЦІЇ ---

@router.message(F.text == "➕ Запропонувати перейменування")
async def start_proposal(message: Message, state: FSMContext):
    await state.set_state(ProposalState.city)
    await message.answer("Вкажіть місто (наприклад, Донецьк або Маріуполь):")

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

    # Повідомлення користувачу
    await message.answer("Дякуємо! Ваша пропозиція успішно відправлена на модерацію.", reply_markup=get_main_keyboard())

    # Відправка адміністратору
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
        sent_msg = await bot.send_message(chat_id=int(ADMIN_ID), text=admin_text, reply_markup=kb, parse_mode="Markdown")
        # Зберігаємо дані заявки в сховищі або через метадані callback (тут спрощено передаємо дані)
    except Exception as e:
        logging.error(f"Не вдалося надіслати заявку адміну: {e}")

# --- МОДЕРАЦІЯ АДМІНОМ ---

@router.callback_query(F.data == "approve")
async def approve_proposal(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено**", parse_mode="Markdown")
    await callback.answer("Пропозицію схвалено!")

@router.callback_query(F.data == "reject")
async def reject_proposal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n❌ **СТАТУС: Відхилено**", parse_mode="Markdown")
    await callback.answer("Пропозицію відхилено.")

async def main():
    print("Бот успішно запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())