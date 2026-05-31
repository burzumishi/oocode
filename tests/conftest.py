"""Fixtures compartidas para todos los tests de OOCode."""
import sys
import os
import shutil
import pytest
from pathlib import Path

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Directorio temporal dentro del home (evita bloqueo de _safe_path que rechaza /tmp)
_TEST_TMP = Path.home() / ".oocode" / "_test_tmp"


@pytest.fixture(autouse=True)
def _cleanup_test_tmp():
    """Limpia el directorio de test al finalizar cada test."""
    yield
    if _TEST_TMP.exists():
        shutil.rmtree(_TEST_TMP, ignore_errors=True)


@pytest.fixture
def tmp_dir():
    """Directorio temporal dentro de home/ para tests que usan _safe_path."""
    _TEST_TMP.mkdir(parents=True, exist_ok=True)
    return _TEST_TMP


@pytest.fixture
def tmp_path(tmp_dir):
    """Override de tmp_path de pytest con directorio dentro de home."""
    return tmp_dir


@pytest.fixture
def sample_py_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text(
        "def hello(name: str) -> str:\n"
        "    return f'Hello, {name}!'\n\n"
        "class Greeter:\n"
        "    def greet(self):\n"
        "        return hello('world')\n"
    )
    return f


@pytest.fixture
def sample_c_file(tmp_path):
    f = tmp_path / "sample.c"
    f.write_text(
        "#include <stdio.h>\n\n"
        "int add(int a, int b) {\n"
        "    return a + b;\n"
        "}\n\n"
        "int main(void) {\n"
        "    printf(\"%d\\n\", add(1, 2));\n"
        "    return 0;\n"
        "}\n"
    )
    return f


@pytest.fixture
def sample_json_file(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": "value", "num": 42}')
    return f
