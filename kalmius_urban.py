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

# Стани FSM для 3-крокової подачі власної назви з сайту
class SiteProposalState(StatesGroup):
    waiting_for_proposed_name = State()
    waiting_for_reason = State()
    waiting_for_author = State()

class FeedbackState(StatesGroup):
    message = State()

# --- ЕСТЕТИЧНІ ІНЛАЙН-КЛАВІАТУРИ ---

def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏛 Модуль «КАЛЬМІУС» (Топоніміка)", callback_data="section_kalmius")],
            [InlineKeyboardButton(text="📚 Архів Донецького кряжу", callback_data="section_archive")],
            [InlineKeyboardButton(text="💬 Зворотний зв'язок з командою", callback_data="section_feedback")]
        ]
    )

def get_kalmius_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Переглянути повну базу на сайті", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text="⬅️ Повернутися до головного меню", callback_data="main_menu")]
        ]
    )

def get_cancel_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати та повернутися назад", callback_data="section_kalmius")]
        ]
    )

def get_simple_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="main_menu")]
        ]
    )

# --- РОБОТА З БАЗОЮ ДАНИХ (JSON) ---

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

# --- ГОЛОВНЕ МЕНЮ ТА РОЗДІЛИ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Вітаємо у офіційному мультиботі історико-архівного проєкту!\n\n"
        "Цей цифровий простір об'єднує ініціативи з дослідження, документування та збереження "
        "автентичної спадщини Донеччини. Ми працюємо над тим, щоб відновити історичну правду, "
        "подолати наслідки тоталітарної пропаганди та повернути регіону його справжнє обличчя.\n\n"
        "👇 *Оберіть потрібний розділ за допомогою інтерактивного меню нижче:*"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "🧭 **Головне меню мультибота**\n\n"
        "Ви можете в будь-який момент перемикатися між ключовими напрямами нашої роботи:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "section_kalmius")
async def cb_kalmius(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "🏛 **Модуль «КАЛЬМІУС» — Переосмислення простору**\n\n"
        "Цей модуль присвячений процесам деколонізації, дерадянізації та відновлення історичної топонімики "
        "міст і селищ Донеччини (зокрема Донецька та Маріуполя).\n\n"
        "Тут ви можете досліджувати об'єкти, що підлягають перейменуванню згідно з чинним законодавством України, "
        "а також пропонувати власні альтернативи та брати участь у громадських обговореннях безпосередньо через наш вебпортал."
    )
    await callback.message.edit_text(text, reply_markup=get_kalmius_menu(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "section_archive")
async def cb_archive(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📚 **Архів Донецького кряжу**\n\n"
        "Незалежна платформа збереження історичної, архітектурної, урбаністичної та культурної спадщини "
        "східного регіону України.\n\n"
        "На нашому порталі зібрані унікальні матеріали, мапи, дослідження та документи, що розкривають справжню "
        "історію нашого краю поза радянськими міфами."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Відкрити вебпортал архіву", url="https://highlandsarchive.donetsk.ua")],
            [InlineKeyboardButton(text="⬅️ На головну", callback_data="main_menu")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "section_feedback")
async def cb_feedback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackState.message)
    text = (
        "💬 **Зворотний зв'язок з дослідницькою командою**\n\n"
        "Маєте зауваження, доповнення до архіву, архівні матеріали чи пропозиції щодо співпраці?\n"
        "Напишіть ваше повідомлення нижче, і наша команда опрацює його найближчим часом:"
    )
    await callback.message.edit_text(text, reply_markup=get_simple_cancel_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.message(FeedbackState.message)
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text
    await state.clear()
    await message.answer(
        "✅ **Дякуємо!** Ваше повідомлення успішно надіслано адміністраторам проєкту.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"💬 **Нове звернення (Зворотний зв'язок):**\n\n"
        f"👤 **Від:** @{message.from_user.username or 'немає юзернейма'} (ID: `{message.from_user.id}`)\n"
        f"📝 **Повідомлення:**\n{feedback_text}"
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка відправки повідомлення адміну: {e}")

# --- ОБРОБКА ГОЛОСУВАННЯ З САЙТУ ---

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
                f"🌟 **Ваш голос зараховано!**\n\n"
                f"Ви підтримали варіант: **«{variant}»** для об'єкта (ID: `{obj_id}`). "
                f"Дякуємо за активну участь у деколонізації простору!",
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
            return

    await message.answer(
        f"🌟 **Дякуємо!** Ваш голос за варіант **«{variant}»** успішно зафіксовано.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

# --- 3-Х КРОКОВИЙ СЦЕНАРІЙ ПОДАЧІ ВЛАСНОЇ НАЗВИ З САЙТУ ---

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
        f"Будь ласка, введіть **варіант нової назви**, яку ви пропонуєте на заміну:"
    )
    await message.answer(text, reply_markup=get_cancel_inline_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_proposed_name)
async def process_site_proposed_name(message: Message, state: FSMContext):
    await state.update_data(proposed_name=message.text)
    await state.set_state(SiteProposalState.waiting_for_reason)
    
    text = (
        "📝 **Історичне обґрунтування (Крок 2 із 3)**\n\n"
        "Напишіть короткий опис, історичну довідку або пояснення, чому саме ця назва є доречною "
        "та як вона пов'язана з культурною спадщиною регіону:"
    )
    await message.answer(text, reply_markup=get_cancel_inline_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_reason)
async def process_site_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text)
    await state.set_state(SiteProposalState.waiting_for_author)
    
    text = (
        "👤 **Інформація про автора (Крок 3 із 3)**\n\n"
        "Вкажіть ваше ім'я, псевдонім або назву громадської ініціативи, які будуть вказані як автор пропозиції:"
    )
    await message.answer(text, reply_markup=get_cancel_inline_keyboard(), parse_mode="Markdown")

@router.message(SiteProposalState.waiting_for_author)
async def process_site_author_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    author = message.text
    await state.clear()

    obj_name = data.get("obj_name", "невідомий об'єкт")
    obj_id = data.get("obj_id", "N/A")
    proposed_name = data.get("proposed_name")
    reason = data.get("reason")

    await message.answer(
        "✨ **Чудово!** Вашу пропозицію повністю сформовано, задокументовано та передано на розгляд модераторам проєкту. "
        "Дякуємо за ваш внесок у розвиток нашої спільної пам'яті!",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"📥 **Нова структурована пропозиція з вебпорталу!**\n\n"
        f"📌 **Об'єкт:** {obj_name} (ID: `{obj_id}`)\n"
        f"✨ **Запропонована назва:** {proposed_name}\n"
        f"📝 **Обґрунтування:** {reason}\n"
        f"👤 **Авторство:** {author}\n"
        f"🔗 **Користувач Telegram:** @{message.from_user.username or 'немає'} (ID: `{message.from_user.id}`)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Схвалити пропозицію", callback_data="approve"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data="reject")
        ]
    ])

    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=admin_msg, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка надсилання пропозиції адміну: {e}")

# --- МОДЕРАЦІЯ АДМІНОМ ---

@router.callback_query(F.data == "approve")
async def approve_proposal(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n✅ **СТАТУС: Схвалено адміністратором**", parse_mode="Markdown")
    await callback.answer("Пропозицію успішно схвалено!")

@router.callback_query(F.data == "reject")
async def reject_proposal(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n❌ **СТАТУС: Відхилено**", parse_mode="Markdown")
    await callback.answer("Пропозицію відхилено.")

# --- ВЕБСЕРВЕР ДЛЯ RENDER ---

async def handle_root(request):
    return web.Response(text="Archival Multibot & API Service is running successfully!")

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
    print("Мультибот та вебсервер успішно запущені й готові до роботи!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())