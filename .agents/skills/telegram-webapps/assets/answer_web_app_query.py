"""
Backend helper for answerWebAppQuery — inline-bot mode.

When a Mini App is opened via an inline query, the bot must respond with
answerWebAppQuery instead of receiving a message update. This module provides
ready-to-use handlers for FastAPI and Flask.

The frontend sends:
  POST /api/answer-query
  Authorization: tma <initData>
  { "query_id": "...", "result": { "type": "article", ... } }

See also: assets/answer-web-app-query.js (frontend implementation)
See also: references/payments.md for the full flow
"""

import os
import httpx


def _get_bot_token() -> str:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")
    return token


async def call_answer_web_app_query(query_id: str, result: dict) -> dict:
    """
    Call Bot API answerWebAppQuery.

    result must be a valid InlineQueryResult dict, e.g.:
      {
        "type": "article",
        "id": "unique-id",
        "title": "My Result",
        "input_message_content": {"message_text": "Selected: My Result"},
      }

    Raises httpx.HTTPStatusError on failure.
    """
    bot_token = _get_bot_token()
    url = f"https://api.telegram.org/bot{bot_token}/answerWebAppQuery"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"web_app_query_id": query_id, "result": result},
        )
        resp.raise_for_status()
        return resp.json()


# ── FastAPI handler ───────────────────────────────────────────────────────────

try:
    from fastapi import Depends, HTTPException
    from pydantic import BaseModel

    # Import your initData validation dependency
    # from validate_init_data import telegram_auth

    class AnswerQueryRequest(BaseModel):
        query_id: str
        result: dict

    async def answer_web_app_query_endpoint(
        body: AnswerQueryRequest,
        # user=Depends(telegram_auth),  # uncomment to validate auth
    ):
        """
        FastAPI route handler. Wire up as:
            app.post("/api/answer-query")(answer_web_app_query_endpoint)
        """
        try:
            data = await call_answer_web_app_query(body.query_id, body.result)
            return {"ok": True, "data": data}
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Telegram API error: {exc.response.text}",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

except ImportError:
    pass  # FastAPI not installed


# ── Flask handler ─────────────────────────────────────────────────────────────

try:
    import asyncio
    from flask import Flask, request as flask_request, jsonify

    # from validate_init_data import flask_telegram_auth  # uncomment for auth

    def register_flask_route(app: Flask, path: str = "/api/answer-query"):
        """
        Register the answerWebAppQuery route on a Flask app:
            register_flask_route(app)

        Call this once per app instance — Flask raises AssertionError if you
        register the same endpoint name twice.
        """
        # To add initData auth: apply your auth decorator to _handler before add_url_rule,
        # e.g.: _handler = flask_telegram_auth(_handler)
        def _handler():
            body = flask_request.get_json(force=True)
            query_id = body.get("query_id", "")
            result   = body.get("result", {})
            if not query_id:
                return jsonify({"ok": False, "error": "query_id required"}), 400
            try:
                data = asyncio.run(call_answer_web_app_query(query_id, result))
                return jsonify({"ok": True, "data": data})
            except httpx.HTTPStatusError as exc:
                return jsonify({"ok": False, "error": exc.response.text}), 502
            except RuntimeError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 500

        app.add_url_rule(path, "tg_answer_web_app_query", _handler, methods=["POST"])

except ImportError:
    pass  # Flask not installed


# ── python-telegram-bot (PTB) snippet ────────────────────────────────────────
#
# In PTB, answerWebAppQuery is available as context.bot.answer_web_app_query().
# The query_id comes from your HTTP endpoint (sent by the frontend via POST)
# rather than from a bot update — so use the HTTP handler above, not a bot handler.
#
# Example (called inside your HTTP route after validating initData):
#
#   from telegram import InlineQueryResultArticle, InputTextMessageContent
#
#   await bot.answer_web_app_query(
#       web_app_query_id=query_id,
#       result=InlineQueryResultArticle(
#           id="result-1",
#           title="Order submitted",
#           input_message_content=InputTextMessageContent("Your order is confirmed!"),
#       ),
#   )


# ── Example result types ──────────────────────────────────────────────────────

EXAMPLE_ARTICLE = {
    "type": "article",
    "id": "result-1",
    "title": "My Article",
    "input_message_content": {
        "message_text": "The user selected: My Article",
        "parse_mode": "HTML",
    },
    "description": "Subtitle shown in inline results",
}

EXAMPLE_PHOTO = {
    "type": "photo",
    "id": "result-1",
    "photo_url": "https://example.com/photo.jpg",
    "thumbnail_url": "https://example.com/thumb.jpg",
    "photo_width": 800,
    "photo_height": 600,
    "caption": "Photo caption",
}
