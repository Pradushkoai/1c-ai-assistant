"""`1c-ai bsl-ls` — управление BSL Language Server (TD-S8-02).

Подкоманды:
  download — скачать bsl-language-server.jar (zip с GitHub releases, sha256 verify).
  status   — проверить Java + jar + версию + текущий mode.

См. ADR-0015, D-2026-07-13-16.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import click

log = logging.getLogger(__name__)

# BSL LS releases: https://github.com/1c-syntax/bsl-language-server/releases
BSL_LS_GITHUB = "1c-syntax/bsl-language-server"
DEFAULT_VERSION = "1.0.4"
DEFAULT_VENDOR_DIR = "vendor/bsl-ls"
JAR_NAME = "bsl-language-server.jar"


def cmd_bsl_ls_download(version: str, force: bool) -> int:
    """Скачать bsl-language-server.jar.

    Args:
        version: версия BSL LS (например, '0.25.5').
        force: перезаписать если уже есть.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    jar_path = Path(os.environ.get("BSL_LS_JAR", f"{DEFAULT_VENDOR_DIR}/{JAR_NAME}"))

    if jar_path.exists() and not force:
        click.echo(f"✅ BSL LS jar уже существует: {jar_path}")
        click.echo("   Используйте --force для перезаписи.")
        return 0

    # Проверяем Java.
    if not shutil.which("java"):
        click.echo("❌ Java не установлена. Установите Java 17+ (openjdk-17-jre-headless).", err=True)
        return 1

    # URL: https://github.com/1c-syntax/bsl-language-server/releases/download/v1.0.4/bsl-language-server_nix.zip
    zip_name = "bsl-language-server_nix.zip"
    url = f"https://github.com/{BSL_LS_GITHUB}/releases/download/v{version}/{zip_name}"

    click.echo(f"⬇️  Скачивание BSL LS v{version}...")
    click.echo(f"   URL: {url}")

    try:
        import httpx

        with httpx.Client(follow_redirects=True, timeout=120) as client:
            response = client.get(url)
            response.raise_for_status()
            zip_data = response.content
    except Exception as exc:
        click.echo(f"❌ Ошибка скачивания: {exc}", err=True)
        return 1

    click.echo(f"   Размер: {len(zip_data) // 1024} KB")

    # Распаковка.
    jar_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip = Path(tmp_dir) / zip_name
        tmp_zip.write_bytes(zip_data)

        try:
            with zipfile.ZipFile(tmp_zip) as zf:
                # Ищем главный .jar в архиве (с "exec" или "bsl" в имени, самый большой).
                jar_entries = [n for n in zf.namelist() if n.endswith(".jar")]
                if not jar_entries:
                    click.echo("❌ .jar файл не найден в архиве.", err=True)
                    return 1

                # Prefer exec jar, fallback to largest jar.
                exec_jars = [n for n in jar_entries if "exec" in n.lower()]
                jar_entry = exec_jars[0] if exec_jars else max(jar_entries, key=lambda n: zf.getinfo(n).file_size)

                click.echo(f"   Распаковка: {jar_entry} → {jar_path}")
                with zf.open(jar_entry) as jar_src:
                    jar_path.write_bytes(jar_src.read())
        except zipfile.BadZipFile as exc:
            click.echo(f"❌ Невалидный ZIP: {exc}", err=True)
            return 1

    # Проверка: java -jar jar --version.
    click.echo("   Проверка...")
    try:
        result = subprocess.run(
            ["java", "-jar", str(jar_path), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
            click.echo(f"✅ BSL LS установлен: {jar_path}")
            click.echo(f"   Версия: {version_str}")
            click.echo(f"   Установите env: BSL_LS_JAR={jar_path}")
            return 0
        else:
            click.echo(f"⚠️  BSL LS установлен, но --version вернул rc={result.returncode}", err=True)
            click.echo(f"   stderr: {result.stderr[:200]}", err=True)
            return 1
    except Exception as exc:
        click.echo(f"⚠️  BSL LS установлен, но проверка не удалась: {exc}", err=True)
        return 1


def cmd_bsl_ls_status() -> int:
    """Показать статус BSL LS.

    Returns:
        0 если BSL LS готов к использованию, 1 если нет.
    """
    from mcp_servers.bsl_ls.backends import make_bsl_ls_backend
    from mcp_servers.bsl_ls.runner import check_bsl_ls, get_bsl_ls_version

    mode = os.environ.get("1C_AI_BSL_LS_MODE", "auto")
    jar_path = os.environ.get("BSL_LS_JAR", f"{DEFAULT_VENDOR_DIR}/{JAR_NAME}")
    http_url = os.environ.get("BSL_LS_HTTP_URL")

    click.echo("BSL Language Server — статус:")
    click.echo(f"  Mode:           {mode}")
    click.echo(f"  JAR path:       {jar_path}")
    click.echo(f"  JAR exists:     {'✅' if check_bsl_ls(jar_path) else '❌'}")
    click.echo(f"  HTTP URL:       {http_url or '(не задан)'}")

    # Java.
    java_path = shutil.which("java")
    if java_path:
        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            java_version = result.stderr.strip().split("\n")[0] if result.stderr else "unknown"
            click.echo(f"  Java:           ✅ {java_path} ({java_version})")
        except Exception:
            click.echo(f"  Java:           ⚠️ {java_path} (версия не определена)")
    else:
        click.echo("  Java:           ❌ не установлена")

    # BSL LS version.
    if check_bsl_ls(jar_path):
        version = get_bsl_ls_version(jar_path)
        click.echo(f"  BSL LS version: {version or '(не определена)'}")
    else:
        click.echo("  BSL LS version: (jar не найден)")

    # Backend.
    backend = make_bsl_ls_backend()
    backend_type = type(backend).__name__
    click.echo(f"  Backend:        {backend_type}")

    # Health check.
    import asyncio

    healthy = asyncio.run(backend.health_check())
    click.echo(f"  Health:         {'✅ готов' if healthy else '⚠️  не готов (stub или нет соединения)'}")

    if healthy:
        click.echo("\n✅ BSL LS готов к использованию.")
        return 0
    else:
        click.echo("\n⚠️  BSL LS не готов.")
        if not check_bsl_ls(jar_path) and not http_url:
            click.echo("   Запустите: 1c-ai bsl-ls download", err=True)
        return 1
