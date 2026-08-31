from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "src" / "views" / "static"),
    name="static",
)

templates = Jinja2Templates(directory=BASE_DIR / "src" / "views" / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/menus", response_class=HTMLResponse)
def menu_list(request: Request):
    return templates.TemplateResponse(request=request, name="menu_list.html")


@app.get("/menus/novo", response_class=HTMLResponse)
def menu_form(request: Request):
    return templates.TemplateResponse(request=request, name="menu_form.html")


@app.get("/usuarios", response_class=HTMLResponse)
def user_form(request: Request):
    return templates.TemplateResponse(request=request, name="user_form.html")


@app.get("/historico", response_class=HTMLResponse)
def chat_history(request: Request):
    return templates.TemplateResponse(request=request, name="chat_history.html")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")
