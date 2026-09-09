from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from src.core import config
from pywa.client import WhatsApp
from src.controllers.menus_controller import router as menus_router
from src.controllers.users_controller import router as users_router
from src.controllers.webhook_controller import setup_webhook_handlers
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "src" / "views" / "static"),
    name="static",
)

app.mount(
    "/assets",
    StaticFiles(directory=BASE_DIR / "src" / "assets"),
    name="assets",
)

templates = config.templates
app.include_router(menus_router)
app.include_router(users_router)

wa = WhatsApp(
    phone_id=os.getenv("WA_PHONE_ID"),
    token=os.getenv("WA_TOKEN"),
    server=app,
    verify_token="chatbotudesc",
    webhook_endpoint="/webhook",
    validate_updates=False,
)

setup_webhook_handlers(wa)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/historico", response_class=HTMLResponse)
def chat_history(request: Request):
    return templates.TemplateResponse(request=request, name="chat_history.html")
