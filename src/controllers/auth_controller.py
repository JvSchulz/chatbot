from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from src.core import config

router = APIRouter(prefix="/login", tags=["login"])

templates = config.templates


@router.get("", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")
