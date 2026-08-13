import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp

# ================= НАСТРОЙКИ =================
# ВАЖНО: цветные кнопки (style=...) требуют aiogram >= 3.20 (Bot API 9.4)
BOT_TOKEN = "8993735158:AAG-BR_RxeXfhambwpMOsLtxeHzDqpHdS_c"
CHANNEL_ID = -1004420294467
WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))

SELLER_USERNAMES = ["Negot_iopp", "godcop"]
# ============================================

PRICE_LIST = [
    (50, 3.49, 6.49),
    (75, 5.49, 8.49),
    (100, 6.99, 9.99),
    (150, 10.49, 13.49),
    (250, 17.49, 20.49),
    (350, 24.49, 27.49),
    (500, 34.99, 37.99),
    (750, 52.49, 55.49),
    (1000, 69.99, 72.99),
    (1500, 104.99, 107.99),
    (2500, 174.99, 177.99),
    (5000, 349.99, 352.99),
    (10000, 699.99, 702.99),
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= КЛАВИАТУРЫ =================
def get_subscribe_keyboard() -> InlineKeyboardMarkup:
    """Подписка на канал — синяя (primary), проверка — зелёная (success)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="ПОДПИСАТЬСЯ НА КАНАЛ",
            url="https://t.me/+WPfMvpVjCehlNDQ6",
            style="primary"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Я ПОДПИСАЛСЯ — ПРОВЕРИТЬ",
            callback_data="check_sub",
            style="success"
        )
    )
    return builder.as_markup()

def get_menu_keyboard() -> InlineKeyboardMarkup:
    """Пакеты звёзд — синие (primary), по 2 в ряд"""
    builder = InlineKeyboardBuilder()
    for stars, official, our in PRICE_LIST:
        btn_text = f"{stars} ⭐ — {our:.2f} BYN"
        builder.button(
            text=btn_text,
            callback_data=f"package_{stars}",
            style="primary"
        )
    builder.adjust(2)
    return builder.as_markup()

def get_order_keyboard() -> InlineKeyboardMarkup:
    """Кнопки оплаты (продавцы) — зелёные (success), назад — стандартная"""
    builder = InlineKeyboardBuilder()
    for username in SELLER_USERNAMES:
        builder.row(
            InlineKeyboardButton(
                text=f"Написать @{username}",
                url=f"https://t.me/{username}",
                style="success"
            )
        )
    builder.row(
        InlineKeyboardButton(text="НАЗАД К ПАКЕТАМ", callback_data="back_to_menu")
    )
    return builder.as_markup()

# ================= ПРОВЕРКА ПОДПИСКИ =================
async def check_subscription(user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# ================= ПОКАЗ МЕНЮ =================
async def show_menu(message_or_callback):
    """Показывает главное меню с пакетами"""
    menu_text = (
        "<b>ВЫБЕРИ ПАКЕТ ЗВЁЗД</b> ⭐\n\n"
        "<i>Нажми на нужный пакет ниже</i>"
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(
            menu_text, parse_mode="HTML", reply_markup=get_menu_keyboard()
        )
    else:  # CallbackQuery
        await message_or_callback.message.edit_text(
            menu_text, parse_mode="HTML", reply_markup=get_menu_keyboard()
        )

async def show_subscribe_prompt(message_or_callback):
    """Показывает запрос на подписку"""
    subscribe_text = (
        "<b>ДЛЯ ИСПОЛЬЗОВАНИЯ БОТА НЕОБХОДИМА ПОДПИСКА НА КАНАЛ</b>\n\n"
        "<i>Подпишись и нажми кнопку ниже для проверки.</i>"
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(
            subscribe_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )
    else:
        await message_or_callback.message.edit_text(
            subscribe_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )

# ================= /start =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id):
        await show_menu(message)
    else:
        await show_subscribe_prompt(message)

# ================= "Я ПОДПИСАЛСЯ — ПРОВЕРИТЬ" =================
@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if await check_subscription(user_id):
        await show_menu(callback)
    else:
        error_text = (
            "<b>ТЫ ЕЩЁ НЕ ПОДПИСАЛСЯ!</b>\n\n"
            "<i>Подпишись на канал и нажми кнопку снова.</i>"
        )
        await callback.answer("Подписка не найдена", show_alert=True)
        await callback.message.edit_text(
            error_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )

# ================= ВЫБОР ПАКЕТА =================
@dp.callback_query(F.data.startswith("package_"))
async def process_package(callback: CallbackQuery):
    await callback.answer()

    # На всякий случай перепроверяем подписку — вдруг человек отписался
    if not await check_subscription(callback.from_user.id):
        await show_subscribe_prompt(callback)
        return

    stars = int(callback.data.split("_")[1])
    package_info = next((p for p in PRICE_LIST if p[0] == stars), None)

    if package_info:
        official, our = package_info[1], package_info[2]
        order_text = (
            f"<b>ЗАКАЗ ПРИНЯТ</b>\n\n"
            f"Пакет: <b>{stars} ⭐</b>\n"
            f"Официальная цена: {official:.2f} BYN\n"
            f"Твоя цена: <b>{our:.2f} BYN</b>\n\n"
            f"Напиши одному из продавцов для оплаты:"
        )
        await callback.message.edit_text(
            order_text, parse_mode="HTML", reply_markup=get_order_keyboard()
        )

# ================= НАЗАД К МЕНЮ =================
@dp.callback_query(F.data == "back_to_menu")
async def process_back_to_menu(callback: CallbackQuery):
    await callback.answer()
    await show_menu(callback)

# ================= WEBHOOK HANDLER ДЛЯ RENDER =================
async def webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = types.Update(**data)
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
                    logger.info(f"Keep-alive: {resp.status}")
            except Exception:
                pass
            await asyncio.sleep(150)

async def on_startup(app: web.Application) -> None:
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"
    try:
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен: {webhook_url}")
        me = await bot.get_me()
        logger.info(f"Бот запущен: @{me.username}")
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
    app["keep_alive_task"] = asyncio.create_task(keep_alive_loop())

async def on_shutdown(app: web.Application) -> None:
    task = app.get("keep_alive_task")
    if task:
        task.cancel()
    try:
        await bot.delete_webhook()
        logger.info("Webhook удален")
    except Exception:
        pass

# ================= ЗАПУСК =================
async def main() -> None:
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

    logger.info(f"Сервер запущен на порту {WEB_SERVER_PORT}")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Остановка...")
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
