/**
 * Telegram bot handlers for Mini App — node-telegram-bot-api
 *
 * Copy this into your bot project and call registerHandlers(bot).
 *
 * Covers:
 *   • /start — sends an inline button that opens the Mini App
 *   • web_app_data — receives tg.sendData() payloads (keyboard-button mode)
 *
 * For inline-button mode the Mini App POSTs to your backend using initData as auth
 * (see validate-init-data.js) — no bot-side handler is needed for that path.
 * answerWebAppQuery() is only needed for inline-mode bots; see the Telegram docs
 * if your bot supports inline queries.
 */

'use strict';

const TelegramBot = require('node-telegram-bot-api');

const MINI_APP_URL = 'https://your-miniapp.example.com'; // ← replace with your deployed URL

/**
 * Register Mini App handlers on an existing TelegramBot instance.
 * @param {TelegramBot} bot
 */
function registerHandlers(bot) {
  // /start — send an inline button that opens the Mini App inside Telegram
  bot.onText(/\/start/, async (msg) => {
    await bot.sendMessage(msg.chat.id, 'Tap to open:', {
      reply_markup: {
        inline_keyboard: [[
          { text: 'Open App', web_app: { url: MINI_APP_URL } },
        ]],
      },
    });
  });

  // Handle tg.sendData() payloads from the Mini App.
  // Only fires when the app was opened from a reply keyboard button (web_app type).
  // If opened via inline button or direct link → use HTTP POST + initData validation.
  bot.on('message', async (msg) => {
    if (!msg.web_app_data) return;

    let data;
    try {
      data = JSON.parse(msg.web_app_data.data);
    } catch {
      data = msg.web_app_data.data;
    }
    await bot.sendMessage(msg.chat.id, `Received: ${JSON.stringify(data, null, 2)}`);
  });
}

module.exports = { registerHandlers, MINI_APP_URL };

// ── Standalone runner (quick local test) ─────────────────────────────────────

if (require.main === module) {
  const token = process.env.BOT_TOKEN;
  if (!token) throw new Error('BOT_TOKEN env var is not set');

  const bot = new TelegramBot(token, { polling: true });
  registerHandlers(bot);
  console.log(`Bot running. Send /start to open ${MINI_APP_URL}`);
}
