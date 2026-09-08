from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from src.core import config

router = APIRouter(prefix="/menus", tags=["menu"])

templates = config.templates


@router.get("", response_class=HTMLResponse)
def menu_list(request: Request):
    return templates.TemplateResponse(request=request, name="menu_list.html")


@router.get("/novo", response_class=HTMLResponse)
def menu_form(request: Request):
    return templates.TemplateResponse(request=request, name="menu_form.html")
