"""tests/conftest.py — общие fixtures для всех тестов.

См. TESTING_POLICY.md раздел 5.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Базовые пути
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"


# ─── Path fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def fixtures_dir() -> Path:
    """Директория с тестовыми данными."""
    return FIXTURES_DIR


@pytest.fixture
def mini_config_dir() -> Path:
    """Распакованная мини-конфигурация 1С для тестов парсеров."""
    return FIXTURES_DIR / "mini_config"


@pytest.fixture
def mini_config_zip() -> Path:
    """ZIP-архив с мини-конфигурацией для теста `1c-ai config add`."""
    return FIXTURES_DIR / "mini_config.zip"


@pytest.fixture
def bsl_samples_dir() -> Path:
    """Директория с .bsl файлами для тестов BSL парсера."""
    return FIXTURES_DIR / "bsl_samples"


@pytest.fixture
def simple_module_bsl(bsl_samples_dir: Path) -> str:
    """Содержимое simple_module.bsl."""
    return (bsl_samples_dir / "simple_module.bsl").read_text(encoding="utf-8")


@pytest.fixture
def with_regions_bsl(bsl_samples_dir: Path) -> str:
    """Содержимое with_regions.bsl."""
    return (bsl_samples_dir / "with_regions.bsl").read_text(encoding="utf-8")


# ─── PathManager fixture ────────────────────────────────────────────────────


@pytest.fixture
def tmp_paths(tmp_path: Path) -> Any:
    """PathManager с временными директориями.

    Создаёт paths.env во временной директории, возвращает PathManager.
    Директории data/, derived/, runtime/ НЕ создаются (для тестов validate()).

    Returns:
        PathManager, настроенный на tmp_path.
    """
    from data_layer.path_manager import PathManager

    env_content = f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR={tmp_path}/kb
VENDOR_DIR={tmp_path}/vendor
"""
    env_path = tmp_path / "paths.env"
    env_path.write_text(env_content.strip(), encoding="utf-8")

    pm = PathManager(env_path=env_path)
    return pm


# ─── Markers ─────────────────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    """Регистрация custom markers (дублирует pyproject.toml для safety)."""
    for marker in [
        "smoke: critical path tests (run with: pytest -m smoke)",
        "snapshot: MCP contract snapshot tests",
        "golden: end-to-end pipeline tests",
        "benchmark: performance benchmarks (not run by default)",
        "integration: requires external services (containers)",
        "property: hypothesis-based property tests",
    ]:
        config.addinivalue_line("markers", marker)
