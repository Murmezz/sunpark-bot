// Telegram bot handlers for Mini App — Go (go-telegram-bot-api/telegram-bot-api v5)
//
// Copy this file into your bot project and call RegisterHandlers(bot).
//
// Covers:
//   - /start — sends an inline button that opens the Mini App
//   - web_app_data — receives tg.sendData() payloads (keyboard-button mode)
//
// For inline-button mode the Mini App POSTs to your backend using initData as
// auth (see validate_init_data.go) — no bot-side handler is needed for that path.
// answerWebAppQuery() is only needed for inline-mode bots; see the Telegram docs.
//
// Dependencies:
//   go get github.com/go-telegram-bot-api/telegram-bot-api/v5

package main

import (
	"encoding/json"
	"fmt"
	"html"
	"log"
	"os"
	"strings"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

const miniAppURL = "https://your-miniapp.example.com" // ← replace with your deployed URL

// RegisterHandlers attaches Mini App handlers to an existing bot update loop.
// Call this before starting the bot's update loop.
func RegisterHandlers(bot *tgbotapi.BotAPI, updates tgbotapi.UpdatesChannel) {
	for update := range updates {
		if update.Message == nil {
			continue
		}

		switch {
		case update.Message.IsCommand() && update.Message.Command() == "start":
			handleStart(bot, update.Message)

		case update.Message.WebAppData != nil:
			handleWebAppData(bot, update.Message)
		}
	}
}

// handleStart sends an inline button that opens the Mini App inside Telegram.
func handleStart(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	keyboard := tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.InlineKeyboardButton{
				Text:   "Open App",
				WebApp: &tgbotapi.WebAppInfo{URL: miniAppURL},
			},
		),
	)
	reply := tgbotapi.NewMessage(msg.Chat.ID, "Tap to open:")
	reply.ReplyMarkup = keyboard

	if _, err := bot.Send(reply); err != nil {
		log.Printf("start handler: send error: %v", err)
	}
}

// handleWebAppData receives data sent by tg.sendData() from the Mini App.
// Only fires when the app was opened from a reply keyboard button (web_app type).
// If opened via inline button or direct link → use HTTP POST + initData validation.
func handleWebAppData(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	raw := msg.WebAppData.Data

	// Try to pretty-print JSON; fall back to raw string.
	var pretty strings.Builder
	var parsed interface{}
	if err := json.Unmarshal([]byte(raw), &parsed); err == nil {
		enc := json.NewEncoder(&pretty)
		enc.SetIndent("", "  ")
		if err := enc.Encode(parsed); err == nil {
			raw = pretty.String()
		}
	}

	reply := tgbotapi.NewMessage(msg.Chat.ID, fmt.Sprintf("Received:\n<pre>%s</pre>", html.EscapeString(raw)))
	reply.ParseMode = tgbotapi.ModeHTML

	if _, err := bot.Send(reply); err != nil {
		log.Printf("web_app_data handler: send error: %v", err)
	}
}

// ── Standalone runner (quick local test) ─────────────────────────────────────

func main() {
	token := os.Getenv("BOT_TOKEN")
	if token == "" {
		log.Fatal("BOT_TOKEN env var is not set")
	}

	bot, err := tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatalf("bot init: %v", err)
	}
	bot.Debug = false

	log.Printf("Bot running as @%s. Send /start to open %s", bot.Self.UserName, miniAppURL)

	cfg := tgbotapi.NewUpdate(0)
	cfg.Timeout = 60
	updates := bot.GetUpdatesChan(cfg)

	RegisterHandlers(bot, updates)
}
