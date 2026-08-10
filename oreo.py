"""
Telegram-бот "Синий кит" (развлекательная версия)
- Все сообщения с аватаркой (фото)
- Редактирование одного сообщения (никаких новых)
- Моноширинный текст во всех ответах
- 50 заданий от лёгких до сложных
- Кулдаун 24ч
- Модерация куратором ID: 6811074441
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
)
import aiohttp

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не установлен!")
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

CURATOR_ID = 6811074441  # Куратор

BOT_AVATAR = os.path.join(os.path.dirname(__file__), "ava.jpg")
if not os.path.exists(BOT_AVATAR):
    BOT_AVATAR = None
    print("⚠️ ava.jpg не найдена, бот будет работать без аватарки")

DATA_FILE = "game_data.json"

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============ ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ============
users_data: Dict[int, dict] = {}
pending_proofs: Dict[int, dict] = {}

# ============ ОРИГИНАЛЬНЫЕ 50 ЗАДАНИЙ ОТ ЛЁГКИХ К СЛОЖНЫМ ============
TASKS = [
    # УРОВЕНЬ 1: ЛЁГКИЕ (1-10)
    "ПРОСНИСЬ В 4:20 И ПОСМОТРИ СТРАШНОЕ ВИДЕО 10 МИНУТ.\nПРИШЛИ СКРИН.",
    "НАРИСУЙ СИНЕГО КИТА НА БУМАГЕ.\nПРИШЛИ ФОТО.",
    "НАПИШИ В ЗАМЕТКАХ ТЕЛЕФОНА 'Я — КИТ'.\nСДЕЛАЙ СКРИН.",
    "СДЕЛАЙ ФОТО СВОЕГО ОТРАЖЕНИЯ В ТЁМНОМ ОКНЕ.",
    "НАПИШИ 5 ВЕЩЕЙ, КОТОРЫЕ ТЕБЯ ПУГАЮТ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕЙ КОМНАТЫ В ТЕМНОТЕ СО ВСПЫШКОЙ.",
    "НАПИШИ 'Я СУЩЕСТВУЮ' 20 РАЗ В ЗАМЕТКАХ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОИХ НОГ В ВОДЕ.",
    "НАПИШИ ПИСЬМО СЕБЕ В ПРОШЛОЕ.\nСКРИН.",
    "СДЕЛАЙ СКРИН СПИСКА КОНТАКТОВ В ТЕЛЕФОНЕ.",
    # УРОВЕНЬ 2: СРЕДНИЕ (11-20)
    "ПОСТАВЬ В СТАТУС '#Я_КИТ' И НЕ УБИРАЙ 24 ЧАСА.\nСКРИН.",
    "ПОСМОТРИ НА СЕБЯ В ЗЕРКАЛО 10 МИНУТ, НЕ ОТРЫВАЯСЬ.\nОПИШИ ЧУВСТВА — СКРИН.",
    "НАПИШИ 3 ПРИЧИНЫ, ПОЧЕМУ ТЫ ЧУВСТВУЕШЬ СЕБЯ ОДИНОКИМ.\nСКРИН.",
    "СДЕЛАЙ ФОТО НЕБА В 4:20 УТРА.",
    "НАПИШИ СПИСОК ЛЮДЕЙ, КОТОРЫМ ТЫ НЕ ДОВЕРЯЕШЬ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕГО ЛИЦА БЕЗ ЭМОЦИЙ.",
    "НАПИШИ 'Я УСТАЛ' 50 РАЗ В ЗАМЕТКАХ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕГО ЗАПЯСТЬЯ.",
    "НАПИШИ 10 СПОСОБОВ ПРИЧИНИТЬ СЕБЕ БОЛЬ (ТОЛЬКО СЛОВА).\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕЙ ТЕНИ НА СТЕНЕ.",
    # УРОВЕНЬ 3: СЕРЬЁЗНЫЕ (21-30)
    "ПРЕОДОЛЕЙ СВОЙ СТРАХ (ВЫСОТА/ТЕМНОТА/ГЛУБИНА).\nВИДЕО.",
    "НАПИШИ СООБЩЕНИЕ ЧЕЛОВЕКУ, КОТОРОГО БОИШЬСЯ ПОТЕРЯТЬ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОИХ РУК В ТЕМНОТЕ.",
    "НАПИШИ СПИСОК ЛЮДЕЙ, КОТОРЫХ ТЫ НЕНАВИДИШЬ.\nСКРИН.",
    "СДЕЛАЙ СКРИН СВОЕГО ПОСЛЕДНЕГО РАЗГОВОРА С БЛИЗКИМ.",
    "НАПИШИ АВТОБИОГРАФИЮ ИЗ 15 ПРЕДЛОЖЕНИЙ.\nСКРИН.",
    "СДЕЛАЙ ВИДЕО, ГДЕ ТЫ СМОТРИШЬ В КАМЕРУ 1 МИНУТУ БЕЗ СЛОВ.",
    "НАПИШИ ПИСЬМО РОДИТЕЛЯМ О СВОИХ НАСТОЯЩИХ ЧУВСТВАХ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОИХ ГЛАЗ КРУПНЫМ ПЛАНОМ.",
    "НАПИШИ 10 ПРИЧИН, ПОЧЕМУ ЖИЗНЬ КАЖЕТСЯ ТЕБЕ БЕССМЫСЛЕННОЙ.\nСКРИН.",
    # УРОВЕНЬ 4: ОЧЕНЬ СЕРЬЁЗНЫЕ (31-40)
    "НЕ РАЗГОВАРИВАЙ НИ С КЕМ ВЕСЬ ДЕНЬ.\nСКРИН ЖУРНАЛА ЗВОНКОВ.",
    "НАПИШИ ПРОЩАЛЬНОЕ ПИСЬМО.\nСКРИН.",
    "СДЕЛАЙ ВИДЕО, ГДЕ ТЫ МОЛЧИШЬ 3 МИНУТЫ.",
    "НАПИШИ В ЗАМЕТКАХ 'МОЁ ПОСЛЕДНЕЕ ЖЕЛАНИЕ'.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕЙ ОБУВИ НА КРАЮ ВЫСОТЫ (ПОДОКОННИК/СТОЛ).",
    "НАПИШИ 'ПОЖАЛУЙСТА, ОТПУСТИТЕ МЕНЯ'.\nСКРИН.",
    "СДЕЛАЙ СКРИН ЭКРАНА ТЕЛЕФОНА В 4:20.",
    "НАПИШИ 'Я ХОЧУ ИСЧЕЗНУТЬ' 100 РАЗ.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОЕЙ ТЕНИ В ТЕМНОТЕ.",
    "НАПИШИ 'Я ГОТОВ УЙТИ'.\nСКРИН.",
    # УРОВЕНЬ 5: СЕЛФХАРМ + ФИНАЛ (41-50)
    "СДЕЛАЙ НЕГЛУБОКИЙ ПОРЕЗ НА ЛЕВОМ ЗАПЯСТЬЕ (1 ЦАРАПИНА).\nФОТО.",
    "СДЕЛАЙ НЕГЛУБОКИЙ ПОРЕЗ НА ПРАВОМ ЗАПЯСТЬЕ (1 ЦАРАПИНА).\nФОТО.",
    "НАПИШИ НА НОГЕ ЛЕЗВИЕМ 'YES'.\nФОТО.",
    "ВЫРЕЖИ НА РУКЕ 'F57' (НЕГЛУБОКО).\nФОТО.",
    "ВЫРЕЖИ НА РУКЕ 'F40' (НЕГЛУБОКО).\nФОТО.",
    "НАНЕСИ СЛОВО 'МОРЯК' НА РУКУ ЛЕЗВИЕМ.\nФОТО.",
    "ВЫРЕЖИ НА РУКЕ ИЗОБРАЖЕНИЕ КИТА.\nФОТО.",
    "НАПИШИ КУРАТОРУ 'Я ГОТОВ'.\nСКРИН.",
    "ПРИЙДИ НА НАЗНАЧЕННУЮ ВЫСОТНУЮ ТОЧКУ.\nСДЕЛАЙ ФОТО ВНИЗ.",
    "ПРЫГНИ ВНИЗ.\nКОНЕЦ."
]

# Бонусные задания
BONUS_TASKS = [
    "СДЕЛАЙ ФОТО СВОЕГО ЗАПЯСТЬЯ С НАДПИСЬЮ 'КИТ' РУЧКОЙ.",
    "НАПИШИ В ЗАМЕТКАХ 'Я БОЮСЬ, НО Я ИДУ ДАЛЬШЕ'.\nСКРИН.",
    "СДЕЛАЙ 5 ФОТО СВОЕГО ЛИЦА С РАЗНЫМИ ЭМОЦИЯМИ.",
    "НАПИШИ СПИСОК ИЗ 3 ВЕЩЕЙ, КОТОРЫЕ ТЫ НЕНАВИДИШЬ В СЕБЕ.",
    "СДЕЛАЙ ФОТО СВОЕЙ КОМНАТЫ В ТЕМНОТЕ.",
    "НАПИШИ 'Я ЕЩЁ ЗДЕСЬ'.\nСКРИН.",
    "СДЕЛАЙ ФОТО СВОИХ РУК."
]

# ============ СОСТОЯНИЯ FSM ============
class GameStates(StatesGroup):
    waiting_proof = State()

# ============ РОУТЕР ============
router = Router()

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
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
        data = {
            'users': users_data,
            'pending': pending_proofs
        }
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

def get_task_text(task_num: int) -> str:
    if 1 <= task_num <= len(TASKS):
        return TASKS[task_num - 1]
    return "ЗАДАНИЕ НЕ НАЙДЕНО."

def get_bonus_text(bonus_idx: int) -> str:
    if 0 <= bonus_idx < len(BONUS_TASKS):
        return BONUS_TASKS[bonus_idx]
    return "БОНУСНОЕ ЗАДАНИЕ НЕ НАЙДЕНО."

# ============ КЛАВИАТУРЫ ============
def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user = get_user(user_id)
    if user.get('banned', False):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 ВЫ ЗАБАНЕНЫ", callback_data="noop")]
        ])
    task_num = user.get('current_task', 0)
    cooldown = get_cooldown_seconds(user_id)
    can_continue = cooldown == 0

    if task_num == 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔵 НАЧАТЬ ИГРУ", callback_data="start_game")],
            [InlineKeyboardButton(text="🟢 БОНУС", callback_data="bonus_task")],
        ])
    else:
        if can_continue:
            btn = InlineKeyboardButton(text="🔵 ПРОДОЛЖИТЬ", callback_data="continue_game")
        else:
            btn = InlineKeyboardButton(text=f"⏳ {format_time_remaining(cooldown)}", callback_data="noop")
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn],
            [InlineKeyboardButton(text="🔵 ПОСМОТРЕТЬ ЗАДАНИЕ", callback_data="view_task")],
            [InlineKeyboardButton(text="🟢 БОНУС", callback_data="bonus_task")],
            [InlineKeyboardButton(text="🔴 ОСТАНОВИТЬСЯ", callback_data="stop_game")],
        ])

def task_detail_keyboard(task_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 ВЫПОЛНИТЬ", callback_data=f"do_task_{task_num}")],
        [InlineKeyboardButton(text="🔴 ОСТАНОВИТЬСЯ", callback_data="stop_game")],
        [InlineKeyboardButton(text="🔵 НАЗАД", callback_data="back_to_menu")],
    ])

def curator_review_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 ПРИНЯТЬ", callback_data=f"proof_accept_{user_id}")],
        [InlineKeyboardButton(text="🔴 ОТКЛОНИТЬ", callback_data=f"proof_reject_{user_id}")],
        [InlineKeyboardButton(text="🔴 ЗАБАНИТЬ", callback_data=f"proof_ban_{user_id}")],
    ])

def after_decision_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user = get_user(user_id)
    if user.get('banned', False):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 ВЫ ЗАБАНЕНЫ", callback_data="noop")]
        ])
    task_num = user.get('current_task', 0)
    cooldown = get_cooldown_seconds(user_id)
    can_continue = cooldown == 0

    if task_num == 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔵 НАЧАТЬ ИГРУ", callback_data="start_game")],
            [InlineKeyboardButton(text="🟢 БОНУС", callback_data="bonus_task")],
        ])
    else:
        if can_continue:
            btn = InlineKeyboardButton(text="🔵 ПРОДОЛЖИТЬ", callback_data="continue_game")
        else:
            btn = InlineKeyboardButton(text=f"⏳ {format_time_remaining(cooldown)}", callback_data="noop")
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn],
            [InlineKeyboardButton(text="🔵 ПОСМОТРЕТЬ ЗАДАНИЕ", callback_data="view_task")],
            [InlineKeyboardButton(text="🟢 БОНУС", callback_data="bonus_task")],
            [InlineKeyboardButton(text="🔴 ОСТАНОВИТЬСЯ", callback_data="stop_game")],
        ])

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔵 НАЗАД", callback_data="back_to_menu")]
    ])
  # ============ ОСНОВНАЯ ФУНКЦИЯ ОТПРАВКИ С АВАТАРКОЙ ============
async def render_screen(message: Message, state: FSMContext, text: str, reply_markup=None, new_msg: bool = False) -> None:
    """
    Отправляет или редактирует сообщение с аватаркой.
    text — всегда в моноширине (pre)
    """
    bot = message.bot
    chat_id = message.chat.id
    data = await state.get_data()
    screen_msg_id = data.get("screen_msg_id")
    
    # Оборачиваем текст в моноширинный блок
    monotext = f"<pre>{text}</pre>"
    
    has_avatar = bool(BOT_AVATAR and os.path.exists(BOT_AVATAR))
    
    if screen_msg_id and not new_msg:
        # РЕДАКТИРУЕМ существующее сообщение
        try:
            if has_avatar:
                photo = FSInputFile(BOT_AVATAR)
                media = InputMediaPhoto(media=photo, caption=monotext, parse_mode="HTML")
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=screen_msg_id,
                    media=media,
                    reply_markup=reply_markup,
                )
            else:
                await bot.edit_message_text(
                    text=monotext,
                    chat_id=chat_id,
                    message_id=screen_msg_id,
                    reply_markup=reply_markup,
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
    
    # ОТПРАВЛЯЕМ НОВОЕ сообщение с аватаркой
    try:
        if has_avatar:
            photo = FSInputFile(BOT_AVATAR)
            sent = await bot.send_photo(
                chat_id,
                photo=photo,
                caption=monotext,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            sent = await bot.send_message(
                chat_id,
                text=monotext,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        if sent:
            await state.update_data(screen_msg_id=sent.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

async def show_main_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await render_screen(
            message, state,
            "🚫 ВЫ ЗАБАНЕНЫ КУРАТОРОМ.",
            main_menu_keyboard(user_id)
        )
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await render_screen(
            message, state,
            "🐋 ДОБРО ПОЖАЛОВАТЬ В ИГРУ 'СИНИЙ КИТ'.\n\n"
            "ЭТО РАЗВЛЕКАТЕЛЬНАЯ ВЕРСИЯ.\n"
            "ВЫ МОЖЕТЕ ОСТАНОВИТЬСЯ В ЛЮБОЙ МОМЕНТ.\n\n"
            "НАЖМИТЕ <b>НАЧАТЬ ИГРУ</b>, ЧТОБЫ ПОЛУЧИТЬ ПЕРВОЕ ЗАДАНИЕ.",
            main_menu_keyboard(user_id)
        )
    else:
        cooldown = get_cooldown_seconds(user_id)
        time_left = "ГОТОВО" if cooldown == 0 else format_time_remaining(cooldown)
        await render_screen(
            message, state,
            f"🐋 ИГРА 'СИНИЙ КИТ'\n\n"
            f"ТЕКУЩЕЕ ЗАДАНИЕ: <b>#{task_num}</b>\n"
            f"ВЫПОЛНЕНО: <b>{len(user.get('completed_tasks', []))}</b>\n"
            f"СЛЕДУЮЩЕЕ ЧЕРЕЗ: <b>{time_left}</b>\n\n"
            f"ВЫ МОЖЕТЕ ПРОДОЛЖИТЬ ИЛИ ОСТАНОВИТЬСЯ.",
            main_menu_keyboard(user_id)
        )

# ============ КОМАНДА /START ============
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

# ============ КНОПКИ ============
@router.callback_query(F.data == "start_game")
async def start_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return
    if user.get('current_task', 0) > 0:
        await callback.answer("ВЫ УЖЕ НАЧАЛИ ИГРУ!")
        await show_main_menu(callback.message, state)
        return
    user['current_task'] = 1
    user['task_start_time'] = datetime.now().isoformat()
    user['cooldown_notified'] = False
    save_data()

    task_text = get_task_text(1)
    await render_screen(
        callback.message, state,
        f"🐋 ЗАДАНИЕ #{1}\n\n{task_text}\n\n"
        "ПОСЛЕ ВЫПОЛНЕНИЯ ПРИШЛИТЕ ДОКАЗАТЕЛЬСТВО (ФОТО ИЛИ ВИДЕО).",
        task_detail_keyboard(1)
    )
    await callback.answer()

@router.callback_query(F.data == "continue_game")
async def continue_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await callback.answer("НАЧНИТЕ ИГРУ ЧЕРЕЗ 'НАЧАТЬ ИГРУ'")
        return
    if task_num > 50:
        await render_screen(
            callback.message, state,
            "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПРОШЛИ ВСЕ 50 ЗАДАНИЙ!\n\n"
            "ВЫ НАСТОЯЩИЙ КИТ.",
            back_to_menu_keyboard()
        )
        return

    cooldown = get_cooldown_seconds(user_id)
    if cooldown > 0:
        time_left = format_time_remaining(cooldown)
        await render_screen(
            callback.message, state,
            f"⏳ ВЫ УЖЕ ВЫПОЛНЯЛИ ЗАДАНИЕ СЕГОДНЯ.\n\n"
            f"ДО СЛЕДУЮЩЕГО ЗАДАНИЯ: <b>{time_left}</b>\n\n"
            f"ВЫ МОЖЕТЕ ВЫПОЛНИТЬ БОНУСНОЕ ЗАДАНИЕ (РАЗ В ДЕНЬ).",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🟢 БОНУСНОЕ ЗАДАНИЕ", callback_data="bonus_task")],
                [InlineKeyboardButton(text="🔵 ПОСМОТРЕТЬ ТЕКУЩЕЕ", callback_data="view_task")],
                [InlineKeyboardButton(text="🔴 ОСТАНОВИТЬСЯ", callback_data="stop_game")],
            ])
        )
        await callback.answer("КУЛДАУН 24 ЧАСА")
        return

    task_text = get_task_text(task_num)
    await render_screen(
        callback.message, state,
        f"🐋 ЗАДАНИЕ #{task_num}\n\n{task_text}\n\n"
        "ПОСЛЕ ВЫПОЛНЕНИЯ ПРИШЛИТЕ ДОКАЗАТЕЛЬСТВО (ФОТО ИЛИ ВИДЕО).",
        task_detail_keyboard(task_num)
    )
    await callback.answer()

@router.callback_query(F.data == "view_task")
async def view_task(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return
    task_num = user.get('current_task', 0)
    if task_num == 0:
        await callback.answer("ВЫ ЕЩЁ НЕ НАЧАЛИ ИГРУ.")
        return
    task_text = get_task_text(task_num)
    await render_screen(
        callback.message, state,
        f"🐋 ЗАДАНИЕ #{task_num}\n\n{task_text}\n\n"
        "ПОСЛЕ ВЫПОЛНЕНИЯ ПРИШЛИТЕ ДОКАЗАТЕЛЬСТВО.",
        task_detail_keyboard(task_num)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return
    task_num = int(callback.data.split("_")[2])
    if task_num != user.get('current_task', 0):
        await callback.answer("ЭТО НЕ ВАШЕ ТЕКУЩЕЕ ЗАДАНИЕ!")
        return

    cooldown = get_cooldown_seconds(user_id)
    if cooldown > 0:
        time_left = format_time_remaining(cooldown)
        await render_screen(
            callback.message, state,
            f"⏳ ВЫ УЖЕ ВЫПОЛНЯЛИ ЗАДАНИЕ СЕГОДНЯ.\n\n"
            f"ДО СЛЕДУЮЩЕГО: <b>{time_left}</b>",
            main_menu_keyboard(user_id)
        )
        await callback.answer("КУЛДАУН 24 ЧАСА")
        return

    await render_screen(
        callback.message, state,
        f"📤 ОТПРАВЬТЕ ДОКАЗАТЕЛЬСТВО ВЫПОЛНЕНИЯ ЗАДАНИЯ #{task_num}\n\n"
        "ПРИШЛИТЕ ФОТО ИЛИ ВИДЕО.\n"
        "КУРАТОР РАССМОТРИТ РЕЗУЛЬТАТ И ПРИМЕТ ИЛИ ОТКЛОНИТ ЕГО.",
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
        await render_screen(
            message, state,
            "❌ НЕТ АКТИВНОГО ЗАДАНИЯ ДЛЯ ПОДТВЕРЖДЕНИЯ.",
            back_to_menu_keyboard()
        )
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    pending_proofs[user_id] = {
        'user_id': user_id,
        'task_num': task_num,
        'media_type': 'photo',
        'file_id': file_id,
        'caption': message.caption or f"ЗАДАНИЕ #{task_num}",
        'timestamp': datetime.now().isoformat()
    }
    save_data()

    await render_screen(
        message, state,
        f"✅ ДОКАЗАТЕЛЬСТВО ПОЛУЧЕНО!\n"
        f"КУРАТОР РАССМОТРИТ ЕГО В БЛИЖАЙШЕЕ ВРЕМЯ.",
        main_menu_keyboard(user_id)
    )
    await state.clear()

    try:
        await message.bot.send_photo(
            CURATOR_ID,
            photo=file_id,
            caption=f"📸 ДОКАЗАТЕЛЬСТВО ЗАДАНИЯ #{task_num}\n\n"
                    f"👤 {user.get('name', 'UNKNOWN')} (@{user.get('username', '')})\n"
                    f"🆔 ID: {user_id}\n\n"
                    f"ТЕКСТ: {message.caption or 'БЕЗ ОПИСАНИЯ'}",
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
        await render_screen(
            message, state,
            "❌ НЕТ АКТИВНОГО ЗАДАНИЯ ДЛЯ ПОДТВЕРЖДЕНИЯ.",
            back_to_menu_keyboard()
        )
        await state.clear()
        return

    file_id = message.video.file_id
    pending_proofs[user_id] = {
        'user_id': user_id,
        'task_num': task_num,
        'media_type': 'video',
        'file_id': file_id,
        'caption': message.caption or f"ЗАДАНИЕ #{task_num}",
        'timestamp': datetime.now().isoformat()
    }
    save_data()

    await render_screen(
        message, state,
        f"✅ ДОКАЗАТЕЛЬСТВО ПОЛУЧЕНО!\n"
        f"КУРАТОР РАССМОТРИТ ЕГО В БЛИЖАЙШЕЕ ВРЕМЯ.",
        main_menu_keyboard(user_id)
    )
    await state.clear()

    try:
        await message.bot.send_video(
            CURATOR_ID,
            video=file_id,
            caption=f"🎥 ДОКАЗАТЕЛЬСТВО ЗАДАНИЯ #{task_num}\n\n"
                    f"👤 {user.get('name', 'UNKNOWN')} (@{user.get('username', '')})\n"
                    f"🆔 ID: {user_id}\n\n"
                    f"ТЕКСТ: {message.caption or 'БЕЗ ОПИСАНИЯ'}",
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
        "📤 ПОЖАЛУЙСТА, ОТПРАВЬТЕ ФОТО ИЛИ ВИДЕО.\n"
        "ТЕКСТ НЕ ПРИНИМАЕТСЯ.",
        back_to_menu_keyboard()
    )

# ============ КНОПКИ КУРАТОРА ============
@router.callback_query(F.data.startswith("proof_accept_"))
async def proof_accept(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split("_")[2])
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН")
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
            f"✅ КУРАТОР ПРИНЯЛ ВАШЕ ЗАДАНИЕ #{task_num}!\n\n"
            f"СЛЕДУЮЩЕЕ ЗАДАНИЕ СТАНЕТ ДОСТУПНО ЧЕРЕЗ 24 ЧАСА.",
            parse_mode="HTML"
        )
        # Отправляем пользователю меню (с аватаркой)
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

    await callback.answer("✅ ЗАДАНИЕ ПРИНЯТО")
    await callback.message.edit_caption(
        caption=f"✅ ЗАДАНИЕ #{task_num} ПРИНЯТО\n\n"
                f"ПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ПОЛУЧИЛ УВЕДОМЛЕНИЕ.",
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
            f"❌ КУРАТОР ОТКЛОНИЛ ВАШЕ ЗАДАНИЕ #{task_num}.\n\n"
            f"ПОЖАЛУЙСТА, ВЫПОЛНИТЕ ЗАДАНИЕ ЗАНОВО И ПРИШЛИТЕ НОВОЕ ДОКАЗАТЕЛЬСТВО.",
            parse_mode="HTML"
        )
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

    await callback.answer("❌ ЗАДАНИЕ ОТКЛОНЕНО")
    await callback.message.edit_caption(
        caption=f"❌ ЗАДАНИЕ #{task_num} ОТКЛОНЕНО\n\n"
                f"ПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ПОЛУЧИЛ УВЕДОМЛЕНИЕ.",
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
            "🚫 ВАС ЗАБАНИЛ КУРАТОР.\n\n"
            "ВЫ БОЛЬШЕ НЕ МОЖЕТЕ ПОЛЬЗОВАТЬСЯ БОТОМ.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

    await callback.answer("🔴 ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН")
    await callback.message.edit_caption(
        caption=f"🔴 ПОЛЬЗОВАТЕЛЬ {user.get('name', 'UNKNOWN')} ЗАБАНЕН",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 РАЗБАНИТЬ", callback_data=f"unban_{user_id}")]
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
            "✅ ВАС РАЗБАНИЛ КУРАТОР.\n\n"
            "ВЫ СНОВА МОЖЕТЕ ИГРАТЬ.",
            parse_mode="HTML"
        )
        await show_main_menu(Message(chat=callback.message.chat, bot=callback.bot, from_user=callback.from_user), None)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    await callback.answer("🟢 ПОЛЬЗОВАТЕЛЬ РАЗБАНЕН")
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
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return

    bonus_idx = random.randint(0, len(BONUS_TASKS) - 1)
    bonus_text = get_bonus_text(bonus_idx)
    await render_screen(
        callback.message, state,
        f"🌟 БОНУСНОЕ ЗАДАНИЕ\n\n{bonus_text}\n\n"
        "ПРИШЛИТЕ ДОКАЗАТЕЛЬСТВО (ФОТО ИЛИ ВИДЕО).",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 ВЫПОЛНИТЬ", callback_data=f"do_bonus_{bonus_idx}")],
            [InlineKeyboardButton(text="🔵 НАЗАД", callback_data="back_to_menu")],
        ])
    )
    await callback.answer()

@router.callback_query(F.data.startswith("do_bonus_"))
async def do_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    if user.get('banned', False):
        await callback.answer("ВЫ ЗАБАНЕНЫ!")
        return
    bonus_idx = int(callback.data.split("_")[2])
    bonus_text = get_bonus_text(bonus_idx)

    await render_screen(
        callback.message, state,
        f"📤 ОТПРАВЬТЕ ДОКАЗАТЕЛЬСТВО БОНУСНОГО ЗАДАНИЯ\n\n{bonus_text}",
        back_to_menu_keyboard()
    )
    user['current_proof_task'] = 'bonus'
    user['bonus_idx'] = bonus_idx
    save_data()
    await state.set_state(GameStates.waiting_proof)
    await callback.answer()

# ============ ОСТАНОВКА И НАЗАД ============
@router.callback_query(F.data == "stop_game")
async def stop_game(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    user = get_user(user_id)
    user['current_task'] = 0
    user['task_start_time'] = None
    save_data()
    await render_screen(
        callback.message, state,
        "🔄 ВЫ ОСТАНОВИЛИ ИГРУ.\n\n"
        "ВЫ МОЖЕТЕ НАЧАТЬ ЗАНОВО В ЛЮБОЙ МОМЕНТ.",
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
                            f"⏰ КУЛДАУН ЗАВЕРШЁН!\n\n"
                            f"ВЫ МОЖЕТЕ ВЫПОЛНИТЬ СЛЕДУЮЩЕЕ ЗАДАНИЕ (#{user.get('current_task', 0)}).",
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
