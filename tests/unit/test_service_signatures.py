"""
Testes de contrato das assinaturas públicas dos serviços: parâmetros explícitos, sem **kwargs.
"""

import inspect

import pytest

from src.services import menu_service, user_service

WRITE_FUNCTIONS = [
    (menu_service.create_menu, ["session", "data"]),
    (menu_service.update_menu, ["session", "menu_id", "data"]),
    (user_service.create_user, ["session", "data"]),
    (user_service.update_user, ["session", "user_id", "data"]),
]


@pytest.mark.parametrize(("function", "parameters"), WRITE_FUNCTIONS, ids=lambda value: getattr(value, "__name__", ""))
def test_write_functions_take_only_the_session_ids_and_data(function, parameters: list[str]):
    signature = inspect.signature(function)

    assert list(signature.parameters) == parameters
    assert all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_menu_write_functions_reject_loose_fields(session):
    with pytest.raises(TypeError):
        menu_service.create_menu(session, name="x", selection_name="y", message="z")  # type: ignore


def test_user_write_functions_reject_loose_fields(session):
    with pytest.raises(TypeError):
        user_service.create_user(session, login="x", password="y" * 12)  # type: ignore


SESSION_FIRST_FUNCTIONS = [
    menu_service.get_all_menus,
    menu_service.get_root_menus,
    menu_service.get_root_menu,
    menu_service.get_root_children,
    menu_service.get_submenus,
    menu_service.get_menu_by_id,
    menu_service.get_valid_parent_menus,
    menu_service.build_menu_split_view_context,
    menu_service.delete_menu,
    user_service.get_all_users,
    user_service.get_user_by_id,
]


@pytest.mark.parametrize("function", SESSION_FIRST_FUNCTIONS, ids=lambda function: function.__name__)
def test_services_take_a_required_session_as_the_first_parameter(function):
    first = next(iter(inspect.signature(function).parameters.values()))

    assert first.name == "session"
    assert first.default is inspect.Parameter.empty


def test_no_service_module_falls_back_to_the_global_engine():
    from src.services import session_service
    from src.services.webhook import chat_history_log

    modules = [menu_service, user_service, session_service, chat_history_log]

    assert [module.__name__ for module in modules if hasattr(module, "engine")] == []
