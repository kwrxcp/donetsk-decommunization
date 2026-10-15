import asyncio
import json
import logging
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# Настройки
TOKEN = "8846214515:AAFONSDRYxx6tI5-gucP85KvHAnH6tcFcM4"  # Замените на ваш токен
ADMIN_ID = 8672495955
DATA_FILE = "locations.json"

logging.basicConfig(level=logging.INFO)
router = Router()


# Состояния FSM
class SuggestionState(StatesGroup):
    waiting_for_proposal_name = State()
    waiting_for_proposal_reason = State()


class AdminRejectState(StatesGroup):
    waiting_for_comment = State()


# Утилиты для работы с JSON
def load_locations():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_locations(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- СТАРТ И ГЛАВНОЕ МЕНЮ ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()

    # Обработка диплинков вида /start prop_X (предложение названия)
    if len(args) > 1 and args[1].startswith("prop_"):
        try:
            obj_id = int(args[1].replace("prop_", ""))
            locations = load_locations()
            obj = next((item for item in locations if item["id"] == obj_id), None)
            if obj:
                await state.update_data(target_obj_id=obj_id)
                await message.answer(
                    f"📝 Ви обрали об'єкт: <b>{obj.get('current_name')}</b>.\n"
                    "Введіть вашу пропозицію нової назви:"
                )
                await state.set_state(SuggestionState.waiting_for_proposal_name)
                return
        except ValueError:
            pass

    text = (
        "Вітаємо у боті історико-архівного проєкту <b>«Архів Донецького кряжу»</b>!\n\n"
        "Цей бот супроводжує портал декомунізації та переосмислення міського простору Донеччини. "
        "Тут ви можете пропонувати нові назви для об'єктів або звертатися до адміністрації."
    )
    await message.answer(text, parse_mode="HTML")


# --- ЛОГИКА ДОБАВЛЕНИЯ ПРЕДЛОЖЕНИЙ ПОЛЬЗОВАТЕЛЯМИ ---
@router.message(SuggestionState.waiting_for_proposal_name)
async def process_proposal_name(message: Message, state: FSMContext):
    await state.update_data(prop_name=message.text.strip())
    await message.answer(
        "Тепер коротко обґрунтуйте вашу пропозицію (чому саме ця назва чи чим вона важлива для регіону):"
    )
    await state.set_state(SuggestionState.waiting_for_proposal_reason)


@router.message(SuggestionState.waiting_for_proposal_reason)
async def process_proposal_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    obj_id = data.get("target_obj_id")
    prop_name = data.get("prop_name")
    prop_reason = message.text.strip()

    locations = load_locations()
    obj = next((item for item in locations if item["id"] == obj_id), None)

    if not obj:
        await message.answer("Помилку: об'єкт не знайдено.")
        await state.clear()
        return

    # Отправка предложения администратору на модерацию
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Схвалити",
                    callback_data=f"adm_acc_{obj_id}_{prop_name[:20]}",
                ),
                InlineKeyboardButton(
                    text="❌ Відхилити",
                    callback_data=f"adm_rej_{obj_id}_{message.from_user.id}",
                ),
            ]
        ]
    )

    admin_text = (
        "🔔 <b>Нова пропозиція з сайту/бота!</b>\n\n"
        f"<b>Об'єкт:</b> {obj.get('current_name')} (ID: {obj_id})\n"
        f"<b>Запропонована назва:</b> {prop_name}\n"
        f"<b>Обґрунтування:</b> {prop_reason}\n"
        f"<b>Користувач:</b> @{message.from_user.username or 'немає'} (ID: {message.from_user.id})"
    )

    try:
        # Сохраняем временно текст предложения для админ-панели в state или передаем в callback
        await message.bot.send_message(
            ADMIN_ID,
            admin_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Схвалити",
                            callback_data=f"acc_{obj_id}|{prop_name}|{message.from_user.id}",
                        ),
                        InlineKeyboardButton(
                            text="❌ Відхилити з коментарем",
                            callback_data=f"rej_{obj_id}|{prop_name}|{message.from_user.id}",
                        ),
                    ]
                ]
            ),
            parse_mode="HTML",
        )
        await message.answer(
            "Дякуємо! Вашу пропозицію надіслано модераторам архіву на розгляд."
        )
    except Exception as e:
        logging.error(f"Не вдалося надіслати адміну: {e}")
        await message.answer(
            "Сталася помилка при відправці. Спробуйте пізніше."
        )

    await state.clear()


# --- АДМИН-ПАНЕЛЬ: МОДЕРАЦИЯ И КОММЕНТАРИИ ---
@router.callback_query(F.data.startswith("acc_"))
async def admin_accept_proposal(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    _, raw_data = callback.data.split("_", 1)
    parts = raw_data.split("|")
    obj_id = int(parts[0])
    prop_name = parts[1]
    user_id = int(parts[2])

    locations = load_locations()
    obj = next((item for item in locations if item["id"] == obj_id), None)

    if obj:
        if "proposals" not in obj:
            obj["proposals"] = []
        # Добавляем в список предложений объекта
        obj["proposals"].append(
            {
                "proposed_name": prop_name,
                "reason": "Запропоновано відвідувачем архіву",
                "votes": 1,
            }
        )
        save_locations(locations)

        # Уведомляем пользователя
        try:
            await callback.bot.send_message(
                user_id,
                f"✅ Вашу пропозицію <b>«{prop_name}»</b> для об'єкта схвалено та додано до каталогу!",
                parse_mode="HTML",
            )
        except:
            pass

        await callback.message.edit_text(
            callback.message.text
            + "\n\n<b>[СТАТУС: СХВАЛЕНО ✅]</b>",
            parse_mode="HTML",
        )
        await callback.answer("Пропозицію успішно схвалено!")


@router.callback_query(F.data.startswith("rej_"))
async def admin_reject_prompt(
    callback: CallbackQuery, state: FSMContext
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    _, raw_data = callback.data.split("_", 1)
    parts = raw_data.split("|")
    obj_id = int(parts[0])
    prop_name = parts[1]
    user_id = int(parts[2])

    # Сохраняем данные для шага ввода комментария
    await state.update_data(
        rej_obj_id=obj_id,
        rej_prop_name=prop_name,
        rej_user_id=user_id,
        orig_message_id=callback.message.message_id,
    )

    await callback.message.answer(
        "✍️ Введіть причину/коментар чому цю пропозицію відхилено (адмін-модерація):"
    )
    await state.set_state(AdminRejectState.waiting_for_comment)
    await callback.answer()


@router.message(AdminRejectState.waiting_for_comment)
async def admin_process_rejection_comment(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    user_id = data.get("rej_user_id")
    prop_name = data.get("rej_prop_name")
    comment = message.text.strip()
    orig_msg_id = data.get("orig_message_id")

    # Отправляем пользователю уведомление с комментарием админа
    try:
        await message.bot.send_message(
            user_id,
            f"❌ На жаль, вашу пропозицію <b>«{prop_name}»</b> було відхилено модератором.\n\n"
            f"💬 <b>Коментар архітиву / причини:</b>\n{comment}",
            parse_mode="HTML",
        )
        await message.answer("✅ Відмова з коментарем успішно надіслана користувачу.")
    except Exception as e:
        await message.answer(f"Не вдалося повідомити користувача: {e}")

    # Обновляем сообщение у админа
    try:
        await message.bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=orig_msg_id,
            text=f"❌ Пропозицію «{prop_name}» відхилено.\n💬 Коментар адміна: {comment}",
        )
    except:
        pass

    await state.clear()


# --- РАССЫЛКА (Broadcast) ДЛЯ АДМИНА ---
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Використання: /broadcast Текст повідомлення для всіх користувачів"
        )
        return

    broadcast_text = parts[1]
    # Здесь можно реализовать логику рассылки по базе пользователей (если сохраняете их в БД/JSON)
    await message.answer("Функція розсилки активована (потрібна база унікальних chat_id).")


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущено успішно!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())