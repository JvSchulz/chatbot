from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from src.core import config

router = APIRouter(prefix="/usuarios", tags=["usuario"])

templates = config.templates


@router.get("", response_class=HTMLResponse)
def user_form(request: Request):
    return templates.TemplateResponse(request=request, name="user_form.html")
