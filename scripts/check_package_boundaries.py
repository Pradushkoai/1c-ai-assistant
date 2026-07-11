#!/usr/bin/env python3
"""scripts/check_package_boundaries.py

CI-проверка: убедиться, что пакеты не нарушают границы зависимостей.

Правила (см. ADR-0002):
- parsers/ НЕ импортирует из orchestrator/, mcp_servers/, data_layer/, agent/
- data_layer/ НЕ импортирует из orchestrator/, mcp_servers/, agent/
- mcp_servers/ НЕ импортирует из orchestrator/, agent/
- orchestrator/ НЕ импортирует из agent/
                НЕ импортирует из mcp_servers.{metadata,codebase,kb,bsl_ls,git} (только mcp_servers.shared)
- agent/ может импортировать откуда угодно

Запуск: python scripts/check_package_boundaries.py
Exit code: 0 — OK, 1 — нарушение
"""
from __future__ import annotations

import sys
import re
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
PACKAGES_DIR = REPO_ROOT / "packages"

# Запрещённые импорты по пакетам (from X import Y или import X)
FORBIDDEN_IMPORTS: dict[str, list[str]] = {
    "parsers": [
        "orchestrator", "mcp_servers", "data_layer", "agent",
    ],
    "data_layer": [
        "orchestrator", "mcp_servers", "agent",
    ],
    "mcp_servers": [
        "orchestrator", "agent",
    ],
    "orchestrator": [
        "agent",
        "mcp_servers.metadata", "mcp_servers.codebase",
        "mcp_servers.kb", "mcp_servers.bsl_ls", "mcp_servers.git",
        "mcp_servers.facade",
        # Разрешено: mcp_servers.shared.protocol (контракты, не реализация)
    ],
}


def check_package(pkg_name: str) -> list[str]:
    """Проверить пакет на нарушения границ. Возвращает список ошибок."""
    errors: list[str] = []
    pkg_dir = PACKAGES_DIR / pkg_name / "src" / pkg_name
    if not pkg_dir.exists():
        return [f"WARN: package directory not found: {pkg_dir}"]

    forbidden = FORBIDDEN_IMPORTS.get(pkg_name, [])

    for py_file in pkg_dir.rglob("*.py"):
        rel_path = py_file.relative_to(REPO_ROOT)
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"ERROR reading {rel_path}: {exc}")
            continue

        # Ищем import statements
        # `import X` or `from X import Y`
        for line_num, line in enumerate(content.splitlines(), start=1):
            line = line.strip()
            if line.startswith("#"):
                continue

            # from X.Y.Z import ... → X.Y.Z
            m = re.match(r"^from\s+([\w.]+)", line)
            if m:
                module = m.group(1)
            else:
                # import X.Y.Z
                m = re.match(r"^import\s+([\w.]+)", line)
                if m:
                    module = m.group(1)
                else:
                    continue

            # Проверяем, не нарушает ли
            for forbidden_prefix in forbidden:
                if module == forbidden_prefix or module.startswith(forbidden_prefix + "."):
                    errors.append(
                        f"{rel_path}:{line_num}: forbidden import '{module}' "
                        f"in package '{pkg_name}' (forbidden: {forbidden_prefix})"
                    )

    return errors


def main() -> int:
    all_errors: list[str] = []
    for pkg_name in FORBIDDEN_IMPORTS:
        errors = check_package(pkg_name)
        all_errors.extend(errors)

    if all_errors:
        print(f"❌ {len(all_errors)} package boundary violations:\n")
        for err in all_errors:
            print(f"  {err}")
        return 1

    print(f"✅ All package boundaries OK ({len(FORBIDDEN_IMPORTS)} packages checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
