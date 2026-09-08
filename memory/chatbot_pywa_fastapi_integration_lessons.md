---
name: chatbot_pywa_fastapi_integration_lessons
description: "PyWa and FastAPI integration lessons in chatbot - webhook endpoint root collision, callback_url Meta error #15, modular controller registration pattern avoiding Pylance type errors and circular imports, silent logs without basicConfig, and Brazilian wa_id 9th digit gotcha"
metadata:
  type: gotchas
---

# PyWa & FastAPI Integration Lessons

## 1. Webhook Endpoint Root Collision
- **Issue:** Initializing `wa = WhatsApp(server=app)` without specifying `webhook_endpoint` defaults to `"/"`. PyWa registers `GET /` requiring Meta verification query parameters (`hub.challenge`, `hub.verify_token`).
- **Impact:** Any browser visiting `http://localhost:8000/` hits PyWa's challenge endpoint first and returns `422 Unprocessable Entity`.
- **Fix:** Always provide an explicit webhook endpoint: `webhook_endpoint="/webhook"`.

## 2. Automatic Callback Registration Trap (Meta Error #15)
- **Issue:** Supplying `callback_url="https://.../webhook"` causes PyWa to launch a background thread to auto-register the webhook with Meta Graph API (`POST /{app_id}/subscriptions`).
- **Failure:** PyWa's HTTP session pins `Authorization: Bearer <WA_TOKEN>` (a user access token) in request headers, which overrides the App token query parameter. Meta rejects the request with `WhatsAppError (code=15: 'This method must be called with an app access_token')`.
- **Fix:** Do not pass `callback_url` to `WhatsApp(...)`. Configure the webhook URL and verify token manually in the Meta Developer Portal under WhatsApp > Configuration > Webhook, and subscribe to `messages`.

## 3. Controller Modularization, Circular Imports, and Pylance Errors
- **Circular Imports:** Importing `main.app` into `webhook_controller.py` while `main.py` imports `webhook_controller` causes `AttributeError: partially initialized module 'main'`.
- **Pylance / Pyright Type Errors:** Decorating functions on the class with `@WhatsApp.on_message(...)` and `@WhatsApp.on_message_status()` works at runtime, but PyWa's type stubs define them with `self: WhatsApp` (instance methods). The type checker flags `Argument of type Filter[Message] cannot be assigned to parameter self` and `No overloads for on_message_status match the provided arguments`.
- **Clean Architecture Pattern:** In `webhook_controller.py`, define:
  ```python
  def setup_webhook_handlers(wa: WhatsApp):
      @wa.on_message(filters.text)
      def handle_message(client: WhatsApp, msg: Message):
          ...
      @wa.on_message_status()
      def handle_status(_: WhatsApp, status: MessageStatus):
          ...
  ```
  In `main.py`, instantiate `wa = WhatsApp(server=app, ...)` and call `setup_webhook_handlers(wa)`. This prevents circular imports, ensures 0 type errors/squiggles in IDEs, and maintains proper typing.

## 4. Silent Logs Under Uvicorn
- **Issue:** Removing `logging.basicConfig(...)` from controllers leaves Python's root logger at default level `WARNING` (30). Custom loggers (e.g. `logging.getLogger("Chatbot")`) drop all `logger.info(...)` calls silently.
- **Fix:** Call `logging.basicConfig(level=logging.INFO)` once at the top of `main.py` directly after `load_dotenv()`, or route handler logs through `logging.getLogger("uvicorn.error")`.

## 5. Brazilian WhatsApp Number Normalization (9th-digit Trap)
- **Issue:** Older Brazilian WhatsApp accounts were registered before the 9th digit rule and possess 12-digit `wa_id`s on Meta's servers (e.g. `554797865306`).
- **Failure:** Arbitrarily mutating `sender_phone` by inserting a `9` to form a 13-digit number (`5547997865306`) and passing it to `client.send_message(to=target_phone)` causes Meta delivery errors (`#131030` or `#131026`) because Meta treats it as a different contact outside the 24-hour customer service window.
- **Fix:** For internal database storage, normalizing numbers is acceptable. For outbound replies via WhatsApp, always reply directly via `msg.reply_text(...)` or use the unmodified `msg.from_user.wa_id`.
