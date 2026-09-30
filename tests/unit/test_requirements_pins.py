"""
Testes de que as dependências estão fixadas em versões exatas e batem com o ambiente instalado.
"""

import re
from importlib.metadata import version
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENT_FILES = ["requirements.txt", "requirements-dev.txt"]
PINNED_LINE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9,_-]+\])?==(?P<version>[0-9][A-Za-z0-9.+!-]*)$")


def requirement_lines(filename: str) -> list[str]:
    lines = (PROJECT_ROOT / filename).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith(("#", "-r"))]


@pytest.mark.parametrize("filename", REQUIREMENT_FILES)
def test_every_requirement_is_pinned_to_an_exact_version(filename: str):
    unpinned = [line for line in requirement_lines(filename) if not PINNED_LINE.match(line)]

    assert unpinned == []


@pytest.mark.parametrize("filename", REQUIREMENT_FILES)
def test_pinned_versions_match_the_installed_environment(filename: str):
    mismatches = []
    for line in requirement_lines(filename):
        match = PINNED_LINE.match(line)
        assert match is not None
        if version(match["name"]) != match["version"]:
            mismatches.append(f"{line} (instalado: {version(match['name'])})")

    assert mismatches == []


def test_dev_requirements_include_the_runtime_ones():
    first_line = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()[0]

    assert first_line == "-r requirements.txt"


def test_ci_workflow_placeholder_is_gone():
    assert not (PROJECT_ROOT / ".github" / "workflow.yaml").exists()
