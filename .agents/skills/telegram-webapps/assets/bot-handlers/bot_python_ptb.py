"""
Telegram bot handlers for Mini App — python-telegram-bot (PTB ≥ 20.x, async).

Copy this into your bot project and call register_handlers(app).

Covers:
  • /start — sends an InlineKeyboardButton that opens the Mini App
  • web_app_data — receives tg.sendData() payloads (keyboard-button mode)

For inline-button mode the Mini App POSTs to your backend using initData as auth
(see validate_init_data.py) — there is no bot-side handler needed for that path.
answerWebAppQuery() is only needed for inline-mode bots; see the Telegram docs if
your bot is set up as an inline bot.
"""

import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

MINI_APP_URL = "https://your-miniapp.example.com"  # ← replace with your deployed URL


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a button that opens the Mini App inside Telegram."""
    keyboard = [[InlineKeyboardButton("Open App", web_app=WebAppInfo(url=MINI_APP_URL))]]
    await update.effective_message.reply_text(
        "Tap to open:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle data sent by tg.sendData() from the Mini App.

    This only fires when the Mini App was opened from a reply keyboard button
    (web_app type). If the app was opened via an inline button or direct link,
    use HTTP POST + initData validation instead — sendData() is unavailable there.
    """
    raw = update.effective_message.web_app_data.data
    try:
        data = json.loads(raw)
        await update.effective_message.reply_text(f"Received: {data}")
    except Exception:
        await update.effective_message.reply_text(f"Raw data: {raw}")


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))


# ── Standalone runner (quick local test) ─────────────────────────────────────

if __name__ == "__main__":
    import os

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN env var is not set")

    app = Application.builder().token(token).build()
    register_handlers(app)
    print(f"Bot running. Send /start to open {MINI_APP_URL}")
    app.run_polling()
