"""
Telegram-бот "Синий кит" (развлекательная версия)
- Все задания ТОЛЬКО в Alert-окнах
- Кнопки под клавиатурой: "МОЙ ПУТЬ" и "ДОПОЛНИТЕЛЬНО"
- "ПОСМОТРЕТЬ ЗАДАНИЕ" показывает текущее задание
- Цветные кнопки: danger, success, primary
- Кулдаун 24ч
"""

import asyncio
import logging
import os
import sys
import json
import random
import math
from datetime import datetime
from typing import Optional, Dict

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    FSInputFile,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не установлен!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

CURATOR_ID = 6811074441

BOT_AVATAR = os.path.join(os.path.dirname(__file__), "ava.jpg")
if not os.path.exists(BOT_AVATAR):
    BOT_AVATAR = None
    print("⚠️ ava.jpg не найдена")

DATA_FILE = "game_data.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

users_data: Dict[int, dict] = {}
pending_proofs: Dict[int, dict] = {}

TASKS = [
    {"text": "ПРОСНИСЬ В 4:20 И ПОСМОТРИ СТРАШНОЕ ВИДЕО 10 МИНУТ.", "proof": "скриншот"},
    {"text": "НАРИСУЙ СИНЕГО КИТА НА БУМАГЕ.", "proof": "фото"},
    {"text": "НАПИШИ В ЗАМЕТКАХ ТЕЛЕФОНА 'Я — КИТ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕГО ОТРАЖЕНИЯ В ТЁМНОМ ОКНЕ.", "proof": "фото"},
    {"text": "НАПИШИ 5 ВЕЩЕЙ, КОТОРЫЕ ТЕБЯ ПУГАЮТ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕЙ КОМНАТЫ В ТЕМНОТЕ СО ВСПЫШКОЙ.", "proof": "фото"},
    {"text": "НАПИШИ 'Я СУЩЕСТВУЮ' 20 РАЗ В ЗАМЕТКАХ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОИХ НОГ В ВОДЕ.", "proof": "фото"},
    {"text": "НАПИШИ ПИСЬМО СЕБЕ В ПРОШЛОЕ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ СКРИН СПИСКА КОНТАКТОВ В ТЕЛЕФОНЕ.", "proof": "скриншот"},
    {"text": "ПОСТАВЬ В СТАТУС '#Я_КИТ' И НЕ УБИРАЙ 24 ЧАСА.", "proof": "скриншот"},
    {"text": "ПОСМОТРИ НА СЕБЯ В ЗЕРКАЛО 10 МИНУТ, НЕ ОТРЫВАЯСЬ.\nОПИШИ ЧУВСТВА.", "proof": "скриншот"},
    {"text": "НАПИШИ 3 ПРИЧИНЫ, ПОЧЕМУ ТЫ ЧУВСТВУЕШЬ СЕБЯ ОДИНОКИМ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО НЕБА В 4:20 УТРА.", "proof": "фото"},
    {"text": "НАПИШИ СПИСОК ЛЮДЕЙ, КОТОРЫМ ТЫ НЕ ДОВЕРЯЕШЬ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕГО ЛИЦА БЕЗ ЭМОЦИЙ.", "proof": "фото"},
    {"text": "НАПИШИ 'Я УСТАЛ' 50 РАЗ В ЗАМЕТКАХ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕГО ЗАПЯСТЬЯ.", "proof": "фото"},
    {"text": "НАПИШИ 10 СПОСОБОВ ПРИЧИНИТЬ СЕБЕ БОЛЬ (ТОЛЬКО СЛОВА).", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕЙ ТЕНИ НА СТЕНЕ.", "proof": "фото"},
    {"text": "ПРЕОДОЛЕЙ СВОЙ СТРАХ (ВЫСОТА/ТЕМНОТА/ГЛУБИНА).", "proof": "видео"},
    {"text": "НАПИШИ СООБЩЕНИЕ ЧЕЛОВЕКУ, КОТОРОГО БОИШЬСЯ ПОТЕРЯТЬ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОИХ РУК В ТЕМНОТЕ.", "proof": "фото"},
    {"text": "НАПИШИ СПИСОК ЛЮДЕЙ, КОТОРЫХ ТЫ НЕНАВИДИШЬ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ СКРИН СВОЕГО ПОСЛЕДНЕГО РАЗГОВОРА С БЛИЗКИМ.", "proof": "скриншот"},
    {"text": "НАПИШИ АВТОБИОГРАФИЮ ИЗ 15 ПРЕДЛОЖЕНИЙ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ВИДЕО, ГДЕ ТЫ СМОТРИШЬ В КАМЕРУ 1 МИНУТУ БЕЗ СЛОВ.", "proof": "видео"},
    {"text": "НАПИШИ ПИСЬМО РОДИТЕЛЯМ О СВОИХ НАСТОЯЩИХ ЧУВСТВАХ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОИХ ГЛАЗ КРУПНЫМ ПЛАНОМ.", "proof": "фото"},
    {"text": "НАПИШИ 10 ПРИЧИН, ПОЧЕМУ ЖИЗНЬ КАЖЕТСЯ ТЕБЕ БЕССМЫСЛЕННОЙ.", "proof": "скриншот"},
    {"text": "НЕ РАЗГОВАРИВАЙ НИ С КЕМ ВЕСЬ ДЕНЬ.", "proof": "скриншот"},
    {"text": "НАПИШИ ПРОЩАЛЬНОЕ ПИСЬМО.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ВИДЕО, ГДЕ ТЫ МОЛЧИШЬ 3 МИНУТЫ.", "proof": "видео"},
    {"text": "НАПИШИ В ЗАМЕТКАХ 'МОЁ ПОСЛЕДНЕЕ ЖЕЛАНИЕ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕЙ ОБУВИ НА КРАЮ ВЫСОТЫ (ПОДОКОННИК/СТОЛ).", "proof": "фото"},
    {"text": "НАПИШИ 'ПОЖАЛУЙСТА, ОТПУСТИТЕ МЕНЯ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ СКРИН ЭКРАНА ТЕЛЕФОНА В 4:20.", "proof": "скриншот"},
    {"text": "НАПИШИ 'Я ХОЧУ ИСЧЕЗНУТЬ' 100 РАЗ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕЙ ТЕНИ В ТЕМНОТЕ.", "proof": "фото"},
    {"text": "НАПИШИ 'Я ГОТОВ УЙТИ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ НЕГЛУБОКИЙ ПОРЕЗ НА ЛЕВОМ ЗАПЯСТЬЕ (1 ЦАРАПИНА).", "proof": "фото"},
    {"text": "СДЕЛАЙ НЕГЛУБОКИЙ ПОРЕЗ НА ПРАВОМ ЗАПЯСТЬЕ (1 ЦАРАПИНА).", "proof": "фото"},
    {"text": "НАПИШИ НА НОГЕ ЛЕЗВИЕМ 'YES'.", "proof": "фото"},
    {"text": "ВЫРЕЖИ НА РУКЕ 'F57' (НЕГЛУБОКО).", "proof": "фото"},
    {"text": "ВЫРЕЖИ НА РУКЕ 'F40' (НЕГЛУБОКО).", "proof": "фото"},
    {"text": "НАНЕСИ СЛОВО 'МОРЯК' НА РУКУ ЛЕЗВИЕМ.", "proof": "фото"},
    {"text": "ВЫРЕЖИ НА РУКЕ ИЗОБРАЖЕНИЕ КИТА.", "proof": "фото"},
    {"text": "НАПИШИ КУРАТОРУ 'Я ГОТОВ'.", "proof": "скриншот"},
    {"text": "ПРИЙДИ НА НАЗНАЧЕННУЮ ВЫСОТНУЮ ТОЧКУ.", "proof": "фото"},
    {"text": "ПРЫГНИ ВНИЗ. КОНЕЦ.", "proof": "видео"},
]

BONUS_TASKS = [
    {"text": "СДЕЛАЙ ФОТО СВОЕГО ЗАПЯСТЬЯ С НАДПИСЬЮ 'КИТ' РУЧКОЙ.", "proof": "фото"},
    {"text": "НАПИШИ В ЗАМЕТКАХ 'Я БОЮСЬ, НО Я ИДУ ДАЛЬШЕ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ 5 ФОТО СВОЕГО ЛИЦА С РАЗНЫМИ ЭМОЦИЯМИ.", "proof": "фото"},
    {"text": "НАПИШИ СПИСОК ИЗ 3 ВЕЩЕЙ, КОТОРЫЕ ТЫ НЕНАВИДИШЬ В СЕБЕ.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОЕЙ КОМНАТЫ В ТЕМНОТЕ.", "proof": "фото"},
    {"text": "НАПИШИ 'Я ЕЩЁ ЗДЕСЬ'.", "proof": "скриншот"},
    {"text": "СДЕЛАЙ ФОТО СВОИХ РУК.", "proof": "фото"},
]

class GameStates(StatesGroup):
    waiting_proof = State()

router = Router()

def load_data():
    global users_data, pending_proofs
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                users_data = {int(k): v for k, v in data.get('users', {}).items()}
                pending_proofs = {int(k): v for k, v in data.get('pending', {}).items()}
            logger.info(f"✅ Загружено пользователей: {len(users_data)}")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            users_data = {}
            pending_proofs = {}

def save_data():
    try:
        data = {'users': users_data, 'pending': pending_proofs}
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

def get_user(user_id: int) -> dict:
    if user_id not in users_data:
        users_data[user_id] = {
            'current_task': 0,
            'completed_tasks': [],
            'last_task_time': None,
            'banned': False,
            'name': '',
            'username': '',
            'current_proof_task': None,
            'cooldown_notified': False,
            'has_started': False,
        }
        save_data()
    return users_data[user_id]

def get_cooldown_seconds(user_id: int) -> int:
    user = get_user(user_id)
    last_time = user.get('last_task_time')
    if not last_time:
        return 0
    dt = datetime.fromisoformat(last_time)
    diff = (datetime.now() - dt).total_seconds()
    if diff >= 86400:
        return 0
    return int(86400 - diff)

def format_time_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "0 СЕК"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0:
        parts.append(f"{h}Ч")
    if m > 0:
        parts.append(f"{m}М")
    if s > 0:
        parts.append(f"{s}С")
    return " ".join(parts)

def get_task(task_num: int) -> dict:
    if 1 <= task_num <= len(TASKS):
        return TASKS[task_num - 1]
    return {"text": "ЗАДАНИЕ НЕ НАЙДЕНО.", "proof": "фото"}

def get_task_text(task_num: int) -> str:
    return get_task(task_num)["text"]

def get_task_proof_type(task_num: int) -> str:
    return get_task(task_num)["proof"]

def get_bonus_task(bonus_idx: int) -> dict:
    if 0 <= bonus_idx < len(BONUS_TASKS):
        return BONUS_TASKS[bonus_idx]
    return {"text": "БОНУСНОЕ ЗАДАНИЕ НЕ НАЙДЕНО.", "proof": "фото"}

def get_bonus_text(bonus_idx: int) -> str:
    return get_bonus_task(bonus_idx)["text"]

def get_bonus_proof_type(bonus_idx: int) -> str:
    return get_bonus_task(bonus_idx)["proof"]

# ============ REPLY-КЛАВИАТУРА (ПОД ПОЛЕМ ВВОДА) ============
def get_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    user = get_user(user_id)
    if user.get('banned', False):
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚫 ВЫ ЗАБАНЕНЫ")]],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐋 МОЙ ПУТЬ"), KeyboardButton(text="ℹ️ ДОПОЛНИТЕЛЬНО")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ============ INLINE-КЛАВИАТУРЫ ============
def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user = get_user(user_id)
    if user.get('banned', False):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ВЫ ЗАБАНЕНЫ", callback_data="noop")]
        ])
    task_num = user.get('current_task', 0)
    cooldown = get_cooldown_seconds(user_id)
    can_continue = cooldown == 0

    if task_num == 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="НАЧАТЬ ИГРУ", callback_data="start_game", style="primary")],
        ])
    else:
        if can_continue:
            btn = InlineKeyboardButton(text="НОВОЕ ЗАДАНИЕ", callback_data="continue_game", style="primary")
        else:
            btn = InlineKeyboardButton(text=f"⏳ {format_time_remaining(cooldown)}", callback_data="noop")
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn],
            [InlineKeyboardButton(text="ПОСМОТРЕТЬ ЗАДАНИЕ", callback_data="view_task", style="primary")],
            [InlineKeyboardButton(text="БОНУСНОЕ ЗАДАНИЕ", callback_data="bonus_task", style="success")],
            [InlineKeyboardButton(text="ОСТАНОВИТЬСЯ", callback_data="stop_game", style="danger")],
        ])

def task_detail_keyboard(task_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВЫПОЛНИТЬ", callback_data=f"do_task_{task_num}", style="success")],
        [InlineKeyboardButton(text="ОСТАНОВИТЬСЯ", callback_data="stop_game", style="danger")],
    ])

def curator_review_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ПРИНЯТЬ", callback_data=f"proof_accept_{user_id}", style="success"),
         InlineKeyboardButton(text="ОТКЛОНИТЬ", callback_data=f"proof_reject_{user_id}", style="danger")],
        [InlineKeyboardButton(text="ЗАБАНИТЬ", callback_data=f"proof_ban_{user_id}", style="danger")],
    ])

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="НАЗАД", callback_data="back_to_menu", style="primary")]
    ])

def cooldown_bonus_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="БОНУСНОЕ ЗАДАНИЕ", callback_data="bonus_task", style="success")],
        [InlineKeyboardButton(text="ПОСМОТРЕТЬ ЗАДАНИЕ", callback_data="view_task", style="primary")],
        [InlineKeyboardButton(text="ОСТАНОВИТЬСЯ", callback_data="stop_game", style="danger")],
    ])

def bonus_keyboard(bonus_idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВЫПОЛНИТЬ", callback_data=f"do_bonus_{bonus_idx}", style="success")],
        [InlineKeyboardButton(text="ОСТАНОВИТЬСЯ", callback_data="stop_game", style="danger")],
    ])
  # ============ ОСНОВНАЯ ФУНКЦИЯ ОТПРАВКИ В ЧАТ ============
async def render_screen(message: Message, state: FSMContext, text: str, inline_markup=None) -> None:
    bot = message.bot
    chat_id = message.chat.id
    user_id = message.from_user.id
    data = await state.get_data()
    screen_msg_id = data.get("screen_msg_id")
    
    monotext = f"<pre>{text}</pre>"
    has_avatar = bool(BOT_AVATAR and os.path.exists(BOT_AVATAR))
    
    if screen_msg_id:
        try:
            if has_avatar:
                photo = FSInputFile(BOT_AVATAR)
                media = InputMediaPhoto(media=photo, caption=monotext, parse_mode="HTML")
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=screen_msg_id,
                    media=media,
                    reply_markup=inline_markup,
                )
            else:
                await bot.edit_message_text(
                    text=monotext,
                    chat_id=chat_id,
                    message_id=screen_msg_id,
                    reply_markup=inline_markup,
                    parse_mode="HTML",
                )
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать {screen_msg_id}: {e}")
            try:
                await bot.delete_message(chat_id, screen_msg_id)
            except Exception:
                pass
            await state.update_data(screen_msg_id=None)
    
    try:
        if has_avatar:
            photo = FSInputFile(BOT_AVATAR)
            sent = await bot.send_photo(
                chat_id,
                photo=photo,
                caption=monotext,
                reply_markup=inline_markup,
                parse_mode="HTML"
            )
        else:
            sent = await bot.send_message(
                chat_id,
                text=monotext,
                reply_markup=inline_markup,
                parse_mode="HTML"
            )
        if sent:
            await state.update_data(screen_msg_id=sent.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

async def show_main_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await render_screen(message, state, "🚫 ВЫ ЗАБАНЕНЫ КУРАТОРОМ.", main_menu_keyboard(user_id))
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await render_screen(
            message, state,
            "🐋 ДОБРО ПОЖАЛОВАТЬ В ИГРУ 'СИНИЙ КИТ'.\n\nЭТО РАЗВЛЕКАТЕЛЬНАЯ ВЕРСИЯ.\nВЫ МОЖЕТЕ ОСТАНОВИТЬСЯ В ЛЮБОЙ МОМЕНТ.\n\nНАЖМИТЕ <b>НАЧАТЬ ИГРУ</b>.",
            main_menu_keyboard(user_id)
        )
    else:
        cooldown = get_cooldown_seconds(user_id)
        time_left = "ГОТОВО" if cooldown == 0 else format_time_remaining(cooldown)
        await render_screen(
            message, state,
            f"🐋 ИГРА 'СИНИЙ КИТ'\n\nТЕКУЩЕЕ ЗАДАНИЕ: <b>#{task_num}</b>\nВЫПОЛНЕНО: <b>{len(user.get('completed_tasks', []))}</b>\nОСТАЛОСЬ: <b>{50 - len(user.get('completed_tasks', []))}</b>\nСЛЕДУЮЩЕЕ ЧЕРЕЗ: <b>{time_left}</b>",
            main_menu_keyboard(user_id)
        )

# ============ /START ============
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    try:
        await message.delete()
    except Exception:
        pass
    await state.clear()
    user = get_user(user_id)
    user['name'] = message.from_user.full_name
    user['username'] = message.from_user.username or ""
    save_data()
    await show_main_menu(message, state)

# ============ НАЧАТЬ ИГРУ (ТОЛЬКО ALERT) ============
@router.callback_query(F.data == "start_game")
async def start_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    if user.get('current_task', 0) > 0:
        await callback.answer("ВЫ УЖЕ НАЧАЛИ ИГРУ!", show_alert=True)
        await show_main_menu(callback.message, state)
        return
    user['current_task'] = 1
    user['task_start_time'] = datetime.now().isoformat()
    user['cooldown_notified'] = False
    user['has_started'] = True
    save_data()

    task_text = get_task_text(1)
    proof_type = get_task_proof_type(1)
    await callback.answer(
        f"🐋 ЗАДАНИЕ #1\n\n{task_text}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}\n\nПОСЛЕ ВЫПОЛНЕНИЯ ПРИШЛИТЕ {proof_type.upper()}.",
        show_alert=True
    )
    await render_screen(
        callback.message, state,
        f"🐋 ЗАДАНИЕ #1 ПОЛУЧЕНО!\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}\n\nНАЖМИТЕ 'ВЫПОЛНИТЬ', КОГДА ГОТОВЫ ОТПРАВИТЬ ДОКАЗАТЕЛЬСТВО.",
        task_detail_keyboard(1)
    )
    await callback.answer()

# ============ НОВОЕ ЗАДАНИЕ (ТОЛЬКО ALERT) ============
@router.callback_query(F.data == "continue_game")
async def continue_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await callback.answer("НАЧНИТЕ ИГРУ ЧЕРЕЗ 'НАЧАТЬ ИГРУ'", show_alert=True)
        return
    if task_num > 50:
        await callback.answer("🎉 ВЫ ПРОШЛИ ВСЕ 50 ЗАДАНИЙ!", show_alert=True)
        return

    cooldown = get_cooldown_seconds(user_id)
    if cooldown > 0:
        time_left = format_time_remaining(cooldown)
        await callback.answer(
            f"⏳ КУЛДАУН 24 ЧАСА\n\nДО СЛЕДУЮЩЕГО ЗАДАНИЯ: {time_left}\n\nВЫ МОЖЕТЕ ВЫПОЛНИТЬ БОНУСНОЕ ЗАДАНИЕ.",
            show_alert=True
        )
        await render_screen(
            callback.message, state,
            f"⏳ КУЛДАУН АКТИВЕН\n\nДО СЛЕДУЮЩЕГО ЗАДАНИЯ: {time_left}",
            cooldown_bonus_keyboard()
        )
        return

    task_text = get_task_text(task_num)
    proof_type = get_task_proof_type(task_num)
    await callback.answer(
        f"🐋 ЗАДАНИЕ #{task_num}\n\n{task_text}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}\n\nПОСЛЕ ВЫПОЛНЕНИЯ ПРИШЛИТЕ {proof_type.upper()}.",
        show_alert=True
    )
    await render_screen(
        callback.message, state,
        f"🐋 ЗАДАНИЕ #{task_num}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}\n\nНАЖМИТЕ 'ВЫПОЛНИТЬ', КОГДА ГОТОВЫ ОТПРАВИТЬ ДОКАЗАТЕЛЬСТВО.",
        task_detail_keyboard(task_num)
    )
    await callback.answer()

# ============ ПОСМОТРЕТЬ ЗАДАНИЕ (ТОЛЬКО ALERT) — ПОКАЗЫВАЕТ ТЕКУЩЕЕ ============
@router.callback_query(F.data == "view_task")
async def view_task(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await callback.answer("ВЫ ЕЩЁ НЕ НАЧАЛИ ИГРУ.", show_alert=True)
        return
    task_text = get_task_text(task_num)
    proof_type = get_task_proof_type(task_num)
    await callback.answer(
        f"🐋 ТЕКУЩЕЕ ЗАДАНИЕ #{task_num}\n\n{task_text}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}",
        show_alert=True
    )
    await callback.answer()

# ============ ВЫПОЛНИТЬ ============
@router.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    task_num = int(callback.data.split("_")[2])
    if task_num != user.get('current_task', 0):
        await callback.answer("ЭТО НЕ ВАШЕ ТЕКУЩЕЕ ЗАДАНИЕ!", show_alert=True)
        return

    cooldown = get_cooldown_seconds(user_id)
    if cooldown > 0:
        time_left = format_time_remaining(cooldown)
        await callback.answer(
            f"⏳ КУЛДАУН АКТИВЕН\n\nДО СЛЕДУЮЩЕГО ЗАДАНИЯ: {time_left}",
            show_alert=True
        )
        return

    proof_type = get_task_proof_type(task_num)
    await callback.answer(
        f"📤 ОТПРАВЬТЕ ДОКАЗАТЕЛЬСТВО\n\nЗАДАНИЕ #{task_num}\nТИП: {proof_type.upper()}",
        show_alert=True
    )
    await render_screen(
        callback.message, state,
        f"📤 ОТПРАВЬТЕ {proof_type.upper()} ДЛЯ ЗАДАНИЯ #{task_num}\n\nКУРАТОР РАССМОТРИТ И ПРИМЕТ ИЛИ ОТКЛОНИТ.",
        back_to_menu_keyboard()
    )
    user['current_proof_task'] = task_num
    save_data()
    await state.set_state(GameStates.waiting_proof)
    await callback.answer()
  # ============ ОБРАБОТКА ДОКАЗАТЕЛЬСТВ ============
@router.message(GameStates.waiting_proof, F.photo)
async def proof_photo(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    task_num = user.get('current_proof_task')
    if not task_num:
        await render_screen(message, state, "❌ НЕТ АКТИВНОГО ЗАДАНИЯ.", back_to_menu_keyboard())
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    task_text = get_task_text(task_num)
    proof_type = get_task_proof_type(task_num)
    
    pending_proofs[user_id] = {
        'user_id': user_id,
        'task_num': task_num,
        'task_text': task_text,
        'proof_type': proof_type,
        'media_type': 'photo',
        'file_id': file_id,
        'caption': message.caption or f"ЗАДАНИЕ #{task_num}",
        'timestamp': datetime.now().isoformat()
    }
    save_data()

    await render_screen(
        message, state,
        f"✅ ДОКАЗАТЕЛЬСТВО ПОЛУЧЕНО!\nКУРАТОР РАССМОТРИТ ЕГО В БЛИЖАЙШЕЕ ВРЕМЯ.",
        main_menu_keyboard(user_id)
    )
    await state.clear()

    try:
        await message.bot.send_photo(
            CURATOR_ID,
            photo=file_id,
            caption=f"📸 ДОКАЗАТЕЛЬСТВО ЗАДАНИЯ #{task_num}\n\n"
                    f"📝 ЗАДАНИЕ: {task_text}\n"
                    f"📌 ТИП: {proof_type.upper()}\n\n"
                    f"👤 {user.get('name', 'UNKNOWN')} (@{user.get('username', '')})\n"
                    f"🆔 ID: {user_id}\n\n"
                    f"📎 КОММЕНТАРИЙ: {message.caption or 'БЕЗ ОПИСАНИЯ'}",
            reply_markup=curator_review_keyboard(user_id),
            parse_mode="HTML"
        )
        logger.info(f"📸 Доказательство от {user_id} для задания #{task_num} отправлено куратору")
    except Exception as e:
        logger.error(f"Ошибка отправки куратору: {e}")

    user['current_proof_task'] = None
    save_data()

@router.message(GameStates.waiting_proof, F.video)
async def proof_video(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    task_num = user.get('current_proof_task')
    if not task_num:
        await render_screen(message, state, "❌ НЕТ АКТИВНОГО ЗАДАНИЯ.", back_to_menu_keyboard())
        await state.clear()
        return

    file_id = message.video.file_id
    task_text = get_task_text(task_num)
    proof_type = get_task_proof_type(task_num)
    
    pending_proofs[user_id] = {
        'user_id': user_id,
        'task_num': task_num,
        'task_text': task_text,
        'proof_type': proof_type,
        'media_type': 'video',
        'file_id': file_id,
        'caption': message.caption or f"ЗАДАНИЕ #{task_num}",
        'timestamp': datetime.now().isoformat()
    }
    save_data()

    await render_screen(
        message, state,
        f"✅ ДОКАЗАТЕЛЬСТВО ПОЛУЧЕНО!\nКУРАТОР РАССМОТРИТ ЕГО В БЛИЖАЙШЕЕ ВРЕМЯ.",
        main_menu_keyboard(user_id)
    )
    await state.clear()

    try:
        await message.bot.send_video(
            CURATOR_ID,
            video=file_id,
            caption=f"🎥 ДОКАЗАТЕЛЬСТВО ЗАДАНИЯ #{task_num}\n\n"
                    f"📝 ЗАДАНИЕ: {task_text}\n"
                    f"📌 ТИП: {proof_type.upper()}\n\n"
                    f"👤 {user.get('name', 'UNKNOWN')} (@{user.get('username', '')})\n"
                    f"🆔 ID: {user_id}\n\n"
                    f"📎 КОММЕНТАРИЙ: {message.caption or 'БЕЗ ОПИСАНИЯ'}",
            reply_markup=curator_review_keyboard(user_id),
            parse_mode="HTML"
        )
        logger.info(f"🎥 Доказательство от {user_id} для задания #{task_num} отправлено куратору")
    except Exception as e:
        logger.error(f"Ошибка отправки куратору: {e}")

    user['current_proof_task'] = None
    save_data()

@router.message(GameStates.waiting_proof)
async def proof_invalid(message: Message, state: FSMContext) -> None:
    await render_screen(
        message, state,
        "📤 ПОЖАЛУЙСТА, ОТПРАВЬТЕ ФОТО ИЛИ ВИДЕО.\nТЕКСТ НЕ ПРИНИМАЕТСЯ.",
        back_to_menu_keyboard()
    )
  # ============ КНОПКИ КУРАТОРА ============
@router.callback_query(F.data.startswith("proof_accept_"))
async def proof_accept(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split("_")[2])
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН", show_alert=True)
        return
    task_num = user.get('current_task', 0)
    if task_num > 0 and task_num <= 50:
        user['last_task_time'] = datetime.now().isoformat()
        user['cooldown_notified'] = False
        if task_num not in user.get('completed_tasks', []):
            user.setdefault('completed_tasks', []).append(task_num)
        next_task = task_num + 1
        if next_task <= 50:
            user['current_task'] = next_task
        else:
            user['current_task'] = 51
    if user_id in pending_proofs:
        del pending_proofs[user_id]
    save_data()

    try:
        await callback.bot.send_message(
            user_id,
            f"✅ КУРАТОР ПРИНЯЛ ВАШЕ ЗАДАНИЕ #{task_num}!\n\nСЛЕДУЮЩЕЕ ЗАДАНИЕ ЧЕРЕЗ 24 ЧАСА.",
            parse_mode="HTML"
        )
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователю {user_id}: {e}")

    await callback.answer("✅ ЗАДАНИЕ ПРИНЯТО", show_alert=True)
    await callback.message.edit_caption(
        caption=f"✅ ЗАДАНИЕ #{task_num} ПРИНЯТО\n\nПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ПОЛУЧИЛ УВЕДОМЛЕНИЕ.",
        reply_markup=None,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("proof_reject_"))
async def proof_reject(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split("_")[2])
    user = get_user(user_id)
    task_num = user.get('current_task', 0)
    if user_id in pending_proofs:
        del pending_proofs[user_id]
    save_data()

    try:
        await callback.bot.send_message(
            user_id,
            f"❌ КУРАТОР ОТКЛОНИЛ ВАШЕ ЗАДАНИЕ #{task_num}.\n\nВЫПОЛНИТЕ ЗАНОВО И ПРИШЛИТЕ НОВОЕ ДОКАЗАТЕЛЬСТВО.",
            parse_mode="HTML"
        )
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователю {user_id}: {e}")

    await callback.answer("❌ ЗАДАНИЕ ОТКЛОНЕНО", show_alert=True)
    await callback.message.edit_caption(
        caption=f"❌ ЗАДАНИЕ #{task_num} ОТКЛОНЕНО\n\nПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ПОЛУЧИЛ УВЕДОМЛЕНИЕ.",
        reply_markup=None,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("proof_ban_"))
async def proof_ban(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split("_")[2])
    user = get_user(user_id)
    user['banned'] = True
    if user_id in pending_proofs:
        del pending_proofs[user_id]
    save_data()

    try:
        await callback.bot.send_message(
            user_id,
            "🚫 ВАС ЗАБАНИЛ КУРАТОР.\n\nВЫ БОЛЬШЕ НЕ МОЖЕТЕ ИГРАТЬ.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователю {user_id}: {e}")

    await callback.answer("🔴 ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН", show_alert=True)
    await callback.message.edit_caption(
        caption=f"🔴 ПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ЗАБАНЕН",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="РАЗБАНИТЬ", callback_data=f"unban_{user_id}", style="success")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("unban_"))
async def unban_user(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split("_")[1])
    user = get_user(user_id)
    user['banned'] = False
    save_data()
    try:
        await callback.bot.send_message(
            user_id,
            "✅ ВАС РАЗБАНИЛ КУРАТОР.\n\nВЫ СНОВА МОЖЕТЕ ИГРАТЬ.",
            parse_mode="HTML"
        )
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователю {user_id}: {e}")
    await callback.answer("🟢 ПОЛЬЗОВАТЕЛЬ РАЗБАНЕН", show_alert=True)
    await callback.message.edit_caption(
        caption=f"🟢 ПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} РАЗБАНЕН",
        reply_markup=None,
        parse_mode="HTML"
    )

# ============ БОНУСНОЕ ЗАДАНИЕ ============
@router.callback_query(F.data == "bonus_task")
async def bonus_task(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    if user.get('current_task', 0) == 0:
        await callback.answer("СНАЧАЛА НАЧНИТЕ ИГРУ ЧЕРЕЗ 'НАЧАТЬ ИГРУ'!", show_alert=True)
        return

    bonus_idx = random.randint(0, len(BONUS_TASKS) - 1)
    bonus_text = get_bonus_text(bonus_idx)
    proof_type = get_bonus_proof_type(bonus_idx)
    await callback.answer(
        f"🌟 БОНУСНОЕ ЗАДАНИЕ\n\n{bonus_text}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}\n\nПРИШЛИТЕ {proof_type.upper()}.",
        show_alert=True
    )
    await render_screen(
        callback.message, state,
        f"🌟 БОНУСНОЕ ЗАДАНИЕ\n\n{bonus_text}\n\n📌 ТИП ДОКАЗАТЕЛЬСТВА: {proof_type.upper()}",
        bonus_keyboard(bonus_idx)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("do_bonus_"))
async def do_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("🚫 ВЫ ЗАБАНЕНЫ!", show_alert=True)
        return
    bonus_idx = int(callback.data.split("_")[2])
    bonus_text = get_bonus_text(bonus_idx)
    proof_type = get_bonus_proof_type(bonus_idx)

    await callback.answer(
        f"📤 ОТПРАВЬТЕ ДОКАЗАТЕЛЬСТВО\n\n{bonus_text}\n\nТИП: {proof_type.upper()}",
        show_alert=True
    )
    await render_screen(
        callback.message, state,
        f"📤 ОТПРАВЬТЕ {proof_type.upper()} ДЛЯ БОНУСНОГО ЗАДАНИЯ",
        back_to_menu_keyboard()
    )
    user['current_proof_task'] = 'bonus'
    user['bonus_idx'] = bonus_idx
    save_data()
    await state.set_state(GameStates.waiting_proof)
    await callback.answer()

# ============ ОСТАНОВКА ============
@router.callback_query(F.data == "stop_game")
async def stop_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    user['current_task'] = 0
    user['task_start_time'] = None
    user['has_started'] = False
    save_data()
    await callback.answer("🔄 ВЫ ОСТАНОВИЛИ ИГРУ", show_alert=True)
    await render_screen(
        callback.message, state,
        "🔄 ВЫ ОСТАНОВИЛИ ИГРУ.\n\nВЫ МОЖЕТЕ НАЧАТЬ ЗАНОВО.",
        main_menu_keyboard(user_id)
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await show_main_menu(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()

# ============ ОБРАБОТЧИК КНОПКИ "МОЙ ПУТЬ" (REPLY) — ВСЁ В ALERT ============
@router.message(F.text == "🐋 МОЙ ПУТЬ")
async def reply_my_path(message: Message) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user.get('banned', False):
        await message.answer("🚫 ВЫ ЗАБАНЕНЫ!", reply_markup=get_reply_keyboard(user_id))
        return
    
    task_num = user.get('current_task', 0)
    completed = len(user.get('completed_tasks', []))
    remaining = 50 - completed
    
    if task_num == 0:
        await message.answer(
            f"🐋 ВЫ ЕЩЁ НЕ НАЧАЛИ ИГРУ.\n\nВЫПОЛНЕНО: 0\nОСТАЛОСЬ: 50",
            reply_markup=get_reply_keyboard(user_id)
        )
        return
    
    progress_bar = '█' * int((completed/50)*20) + '░' * (20 - int((completed/50)*20))
    await message.answer(
        f"🐋 ВАШ ПУТЬ\n\n"
        f"ТЕКУЩЕЕ ЗАДАНИЕ: #{task_num}\n"
        f"ВЫПОЛНЕНО: {completed} из 50\n"
        f"ОСТАЛОСЬ: {remaining}\n\n"
        f"ПРОГРЕСС: {progress_bar}",
        reply_markup=get_reply_keyboard(user_id)
    )

# ============ ОБРАБОТЧИК КНОПКИ "ДОПОЛНИТЕЛЬНО" (REPLY) — ALERT ============
@router.message(F.text == "ℹ️ ДОПОЛНИТЕЛЬНО")
async def reply_additional(message: Message) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user.get('banned', False):
        await message.answer("🚫 ВЫ ЗАБАНЕНЫ!", reply_markup=get_reply_keyboard(user_id))
        return
    
    await message.answer(
        f"ℹ️ ИНФОРМАЦИЯ\n\n"
        f"ПРИ ОТКАЗЕ ВЫПОЛНЕНИЯ ЗАДАНИЯ ВАМ НИЧЕГО НЕ ГРОЗИТ.\n"
        f"НЕ СТОИТ БОЯТЬСЯ.\n\n"
        f"ИГРА СОЗДАНА ДЛЯ РАЗВЛЕЧЕНИЯ.\n"
        f"ВЫ МОЖЕТЕ ОСТАНОВИТЬСЯ В ЛЮБОЙ МОМЕНТ.",
        reply_markup=get_reply_keyboard(user_id)
    )

# ============ ФОН: ПРОВЕРКА КУЛДАУНА ============
async def cooldown_checker(bot: Bot):
    while True:
        try:
            now = datetime.now()
            for user_id, user in users_data.items():
                if user.get('banned', False):
                    continue
                if user.get('current_task', 0) == 0:
                    continue
                if user.get('cooldown_notified', False):
                    continue
                last_time = user.get('last_task_time')
                if not last_time:
                    continue
                dt = datetime.fromisoformat(last_time)
                diff = (now - dt).total_seconds()
                if diff >= 86400:
                    user['cooldown_notified'] = True
                    save_data()
                    try:
                        await bot.send_message(
                            user_id,
                            f"⏰ КУЛДАУН ЗАВЕРШЁН!\n\nВЫ МОЖЕТЕ ВЗЯТЬ НОВОЕ ЗАДАНИЕ (#{user.get('current_task', 0)}).",
                            parse_mode="HTML"
                        )
                        logger.info(f"Уведомление о кулдауне отправлено {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления о кулдауне {user_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в cooldown_checker: {e}")
        await asyncio.sleep(60)
      # ============ WEBHOOK ============
async def webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})

async def keep_alive_loop() -> None:
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        return
    url = f"https://{hostname}/health"
    await asyncio.sleep(10)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=10) as resp:
                    logger.info(f"🔄 Keep-alive: {resp.status}")
            except Exception:
                pass
            await asyncio.sleep(150)

async def on_startup(app: web.Application) -> None:
    load_data()
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"
    if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    try:
        await bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook: {webhook_url}")
        me = await bot.get_me()
        logger.info(f"✅ Бот: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка старта: {e}")
    app["keep_alive_task"] = asyncio.create_task(keep_alive_loop())
    asyncio.create_task(cooldown_checker(bot))

async def on_shutdown(app: web.Application) -> None:
    task = app.get("keep_alive_task")
    if task:
        task.cancel()
    try:
        await bot.delete_webhook()
    except Exception:
        pass

# ============ ЗАПУСК ============
async def main() -> None:
    global bot, dp
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logger.info(f"🚀 Сервер на порту {WEB_SERVER_PORT}")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка...")
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
