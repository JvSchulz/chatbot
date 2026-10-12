"""
Testes de que o código morto identificado na revisão do repositório não voltou.
"""

import pytest

from src.controllers import menus_controller, users_controller
from src.services import menu_service, user_service
from src.services.webhook import chat_history_log, message_handler


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (menus_controller, "get_menu_update_payload"),
        (users_controller, "get_user_update_payload"),
        (user_service, "get_current_user"),
        (chat_history_log, "is_first_interaction"),
        (message_handler, "identify_session_mode"),
        (menu_service, "can_toggle_root"),
    ],
)
def test_removed_helpers_stay_removed(module, name: str):
    assert not hasattr(module, name)
