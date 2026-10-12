"""
Testes unitários dos auxiliares puros do handler: payload de menu, máscara de usuário e destino de resposta.
"""

import pytest
from src.services.webhook.message_handler import (
    mask_user_id,
    parse_menu_id,
    redact,
    resolve_reply_target,
)


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("menu:5", 5),
        ("menu:0", 0),
        ("menu:007", 7),
        ("menu:abc", None),
        ("menu:", None),
        ("menu:-1", None),
        ("menu:1.5", None),
        ("menu: 5", None),
        ("menu:٣", None),
        ("menu:999999999999999999", 999999999999999999),
        ("menu:1000000000000000000", None),
        ("menu:9223372036854775808", None),
        pytest.param("menu:" + "9" * 4301, None, id="4301-digits"),
        ("action:root", None),
        ("outro:5", None),
        ("", None),
    ],
)
def test_parse_menu_id(payload: str, expected: int | None):
    assert parse_menu_id(payload) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("5547998765432", "***5432"),
        ("BR.1234567890123", "***0123"),
        ("12345", "***2345"),
        ("1234", "***"),
        ("", "***"),
        (None, "***"),
    ],
)
def test_mask_user_id_keeps_only_the_last_four_characters(value: str | None, expected: str):
    assert mask_user_id(value) == expected


def test_resolve_reply_target_uses_normalized_wa_id_when_present():
    assert resolve_reply_target("BR.1000000000001", "554788884444") == "5547988884444"


def test_resolve_reply_target_keeps_13_digit_wa_id():
    assert resolve_reply_target("BR.1000000000001", "5547988884444") == "5547988884444"


@pytest.mark.parametrize("wa_id", [None, "", "   "])
def test_resolve_reply_target_falls_back_to_bsuid_without_wa_id(wa_id: str | None):
    assert resolve_reply_target("BR.1000000000001", wa_id) == "BR.1000000000001"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Recipient 554799998888 not allowed", "Recipient *** not allowed"),
        ("12345678 e 1234567", "*** e 1234567"),
        ("user BR.1234567890123 blocked", "user *** blocked"),
        ("user US.42 blocked", "user *** blocked"),
        ("Re-engagement message window expired", "Re-engagement message window expired"),
        ("erro 131047 (código)", "erro 131047 (código)"),
        ("", ""),
    ],
)
def test_redact_masks_long_digit_runs_and_bsuids(text: str, expected: str):
    assert redact(text) == expected
