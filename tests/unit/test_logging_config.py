"""
Testes da configuração de logging feita em main.py.
"""

import logging
from main import app  # noqa: F401


def test_pywa_logger_is_capped_at_info_so_raw_updates_are_never_logged():
    assert logging.getLogger("pywa").level == logging.INFO
