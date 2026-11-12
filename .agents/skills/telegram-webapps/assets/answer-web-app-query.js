/**
 * answerWebAppQuery — frontend helper for inline-bot mode.
 *
 * When the Mini App is opened from an INLINE QUERY (not a bot button), the
 * user's selection must be delivered via answerWebAppQuery on the bot backend.
 * This is different from tg.sendData() which only works from reply keyboard
 * buttons.
 *
 * Flow:
 *   1. User opens Mini App via inline query (the app gets tg.initDataUnsafe.query_id)
 *   2. User makes a choice inside the app
 *   3. App calls your backend with the choice + initData for auth
 *   4. Backend calls Bot API answerWebAppQuery with the inline result
 *   5. The chosen item appears in the chat
 *
 * Usage (plain <script> tag, not ESM):
 *   <script src="./answer-web-app-query.js"></script>
 *   <script>
 *     // tg.initDataUnsafe.query_id must be set (only when opened via inline query)
 *     answerWebAppQuery('/api/answer-query', {
 *       type: 'article',
 *       title: 'My result',
 *       input_message_content: { message_text: 'Selected!' },
 *     }).then(() => window.Telegram.WebApp.close());
 *   </script>
 *
 * See also: answer_web_app_query.py (Python backend implementation)
 * See also: references/payments.md for the full inline-bot flow
 */

/**
 * Send the user's selection to your backend, which calls answerWebAppQuery.
 *
 * tg (window.Telegram.WebApp) is read at call time, not at script load time,
 * so it works even when the SDK or mock isn't loaded yet when this script runs.
 *
 * @param {string} backendUrl  Your API endpoint (e.g. '/api/answer-query')
 * @param {object} result      InlineQueryResult object (see Bot API docs)
 *   Must include at minimum: { type, ... }
 *   Common types: 'article' (text), 'photo', 'video', 'document'
 *   An 'id' field is auto-generated if omitted.
 * @returns {Promise<void>}    Resolves on success, throws on failure
 */
window.answerWebAppQuery = async function answerWebAppQuery(backendUrl, result) {
  // Read tg at call time — not at script parse time — so mock/SDK can load first.
  const tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) throw new Error('answerWebAppQuery: window.Telegram.WebApp is not available');

  const queryId = tg.initDataUnsafe && tg.initDataUnsafe.query_id;
  if (!queryId) {
    throw new Error(
      'answerWebAppQuery: tg.initDataUnsafe.query_id is not set. ' +
      'This function only works when the Mini App was opened from an inline query.'
    );
  }

  const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

  const response = await fetch(backendUrl, {
    method: 'POST',
    headers: {
      'Authorization': 'tma ' + tg.initData,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query_id: queryId,
      result: Object.assign({ id }, result),
    }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error('answerWebAppQuery: backend returned HTTP ' + response.status + ': ' + text);
  }
};

// ── Example: send an article result ──────────────────────────────────────────
//
// answerWebAppQuery('/api/answer-query', {
//   type: 'article',
//   title: 'My Result',
//   input_message_content: { message_text: 'The user selected: My Result' },
// }).then(() => window.Telegram.WebApp.close());

// ── Example: send a photo result ─────────────────────────────────────────────
//
// answerWebAppQuery('/api/answer-query', {
//   type: 'photo',
//   photo_url: 'https://example.com/photo.jpg',
//   thumbnail_url: 'https://example.com/thumb.jpg',
//   photo_width: 800,
//   photo_height: 600,
// });
