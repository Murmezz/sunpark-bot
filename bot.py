# -*- coding: utf-8 -*-
"""
Telegram-бот "Меню SUNPARK".

Главное меню — кнопки разделов (Еда / Напитки / Алкоголь).
Нажатие на раздел показывает список блюд этого раздела и кнопку "Назад".

Установка:
    pip install -r requirements.txt

Запуск:
    1. Получите токен бота у @BotFather в Telegram.
    2. Вставьте токен в BOT_TOKEN ниже
       (или задайте переменную окружения BOT_TOKEN и раскомментируйте
       соответствующую строку).
    3. python bot.py
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from menu_data import INFO_TEXT, MENU, MENU_SECTIONS

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN", BOT_TOKEN)

WELCOME_TEXT = "🌿 <b>SUNPARK</b>\nВыберите раздел меню:"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def main_menu_keyboard() -> "InlineKeyboardBuilder":
    """Главное меню: заголовки разделов + кнопки категорий по 2 в ряд."""
    builder = InlineKeyboardBuilder()
    for section_title, keys in MENU_SECTIONS:
        builder.row(InlineKeyboardButton(text=f"— {section_title} —", callback_data="noop"))
        row = []
        for key in keys:
            cat = MENU[key]
            row.append(
                InlineKeyboardButton(text=f"{cat['emoji']} {cat['title']}", callback_data=f"cat:{key}")
            )
            if len(row) == 2:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)
    builder.row(InlineKeyboardButton(text="ℹ️ Информация для гостей", callback_data="info"))
    return builder.as_markup()


def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back"))
    return builder.as_markup()


def format_items(items) -> list:
    lines = []
    for name, desc, price in items:
        lines.append(f"<b>{name}</b>")
        if desc:
            lines.append(f"<i>{desc}</i>")
        lines.append(f"💰 {price}")
        lines.append("")
    return lines


def format_category(key: str) -> str:
    cat = MENU[key]
    lines = [f"<b>{cat['emoji']} {cat['title'].upper()}</b>", ""]

    if "sections" in cat:
        for subtitle, items in cat["sections"]:
            lines.append(f"<u>{subtitle}</u>")
            lines.extend(format_items(items))
    else:
        lines.extend(format_items(cat["items"]))

    if cat.get("footer"):
        lines.append(f"<i>{cat['footer']}</i>")

    return "\n".join(lines).strip()


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@dp.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "back")
async def back_handler(callback: CallbackQuery):
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "info")
async def info_handler(callback: CallbackQuery):
    await callback.message.edit_text(INFO_TEXT, reply_markup=back_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def category_handler(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    if key not in MENU:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    await callback.message.edit_text(format_category(key), reply_markup=back_keyboard())
    await callback.answer()


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
