"""Загрузка KB из YAML + валидация по JSON Schema.

KBCollection — единая точка доступа к patterns и antipatterns.
Используется kb-server'ом для реализации 5 MCP tools.

См. ADR-0012 (KB-as-code) и docs/architecture/07-kb-as-code.md.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from jsonschema import validate as validate_schema  # type: ignore[import-untyped]

log = logging.getLogger(__name__)


class KBCollection:
    """Коллекция загруженных паттернов и антипаттернов.

    Загружает YAML из knowledge-base/{patterns,antipatterns}/,
    валидирует по JSON Schema, предоставляет методы для поиска и детекции.

    Attributes:
        patterns: {pattern_id: dict} — все паттерны.
        antipatterns: {antipattern_id: dict} — все антипаттерны.
    """

    def __init__(self, kb_dir: Path) -> None:
        """Загрузить KB из директории.

        Args:
            kb_dir: путь к knowledge-base/ директории.
        """
        self.kb_dir = kb_dir
        self.patterns: dict[str, dict[str, Any]] = {}
        self.antipatterns: dict[str, dict[str, Any]] = {}
        self._schemas = self._load_schemas()
        self._load_all()

    def _load_schemas(self) -> dict[str, dict[str, Any]]:
        """Загрузить JSON Schemas из knowledge-base/schemas/."""
        schemas: dict[str, dict[str, Any]] = {}
        schema_dir = self.kb_dir / "schemas"
        if not schema_dir.exists():
            log.warning("KB schemas directory not found: %s", schema_dir)
            return schemas

        for schema_file in schema_dir.glob("*.schema.json"):
            name = schema_file.stem.replace(".schema", "")
            try:
                schemas[name] = json.loads(schema_file.read_text(encoding="utf-8"))
            except Exception as exc:
                log.error("Failed to load schema %s: %s", schema_file, exc)

        return schemas

    def _load_all(self) -> None:
        """Загрузить все patterns и antipatterns."""
        # Patterns
        patterns_dir = self.kb_dir / "patterns"
        if patterns_dir.exists():
            for yaml_path in sorted(patterns_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                    if data and "id" in data:
                        if "pattern" in self._schemas:
                            validate_schema(instance=data, schema=self._schemas["pattern"])
                        self.patterns[data["id"]] = data
                        log.debug("Loaded pattern: %s", data["id"])
                except Exception as exc:
                    log.warning("Failed to load pattern %s: %s", yaml_path, exc)

        # Antipatterns
        antipatterns_dir = self.kb_dir / "antipatterns"
        if antipatterns_dir.exists():
            for yaml_path in sorted(antipatterns_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                    if data and "id" in data:
                        if "antipattern" in self._schemas:
                            validate_schema(instance=data, schema=self._schemas["antipattern"])
                        self.antipatterns[data["id"]] = data
                        log.debug("Loaded antipattern: %s", data["id"])
                except Exception as exc:
                    log.warning("Failed to load antipattern %s: %s", yaml_path, exc)

        log.info(
            "KB loaded: %d patterns, %d antipatterns",
            len(self.patterns),
            len(self.antipatterns),
        )

    # ─── Patterns ────────────────────────────────────────────────────────────

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        """Получить паттерн по id."""
        return self.patterns.get(pattern_id)

    def list_patterns(self, category: str | None = None, applicable_to: str | None = None) -> list[dict[str, Any]]:
        """Список паттернов с опциональной фильтрацией."""
        result = list(self.patterns.values())
        if category:
            result = [p for p in result if p.get("category") == category]
        if applicable_to:
            result = [p for p in result if applicable_to in p.get("applicable_to", [])]
        return result

    # ─── Antipatterns ────────────────────────────────────────────────────────

    def get_antipattern(self, antipattern_id: str) -> dict[str, Any] | None:
        """Получить антипаттерн по id."""
        return self.antipatterns.get(antipattern_id)

    def list_antipatterns(
        self,
        category: str | None = None,
        severity: str | None = None,
        applicable_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Список антипаттернов с опциональной фильтрацией."""
        result = list(self.antipatterns.values())
        if category:
            result = [ap for ap in result if ap.get("category") == category]
        if severity:
            result = [ap for ap in result if ap.get("severity") == severity]
        if applicable_to:
            result = [ap for ap in result if applicable_to in ap.get("applicable_to", [])]
        return result

    # ─── Search ──────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str = "all",
    ) -> list[dict[str, Any]]:
        """Полнотекстовый поиск по KB (простой substring match).

        Args:
            query: текст запроса.
            top_k: максимум результатов.
            category: 'pattern', 'antipattern', 'standard', 'all'.

        Returns:
            Список [{id, type, title, score}].
        """
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        if category in ("pattern", "all"):
            for p in self.patterns.values():
                score = self._score_match(p, query_lower)
                if score > 0:
                    results.append(
                        {
                            "id": p["id"],
                            "type": "pattern",
                            "title": p.get("title", ""),
                            "score": score,
                        }
                    )

        if category in ("antipattern", "all"):
            for ap in self.antipatterns.values():
                score = self._score_match(ap, query_lower)
                if score > 0:
                    results.append(
                        {
                            "id": ap["id"],
                            "type": "antipattern",
                            "title": ap.get("title", ""),
                            "score": score,
                        }
                    )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _score_match(self, item: dict[str, Any], query_lower: str) -> float:
        """Простой scoring: совпадение в title = 1.0, в id = 0.8, в tags = 0.5."""
        score = 0.0
        title = item.get("title", "").lower()
        item_id = item.get("id", "").lower()
        tags = [t.lower() for t in item.get("tags", [])]

        if query_lower in title:
            score += 1.0
        if query_lower in item_id:
            score += 0.8
        for tag in tags:
            if query_lower in tag:
                score += 0.5
        # Проверка в recommendation/when_to_use
        for field in ("recommendation_for_llm", "when_to_use", "category"):
            text = item.get(field, "").lower() if isinstance(item.get(field), str) else ""
            if query_lower in text:
                score += 0.3
        return score

    # ─── Detect antipatterns ─────────────────────────────────────────────────

    def detect_antipatterns(
        self,
        code: str,
        severity_filter: list[str] | None = None,
        category_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Проверить BSL-код на антипаттерны (regex).

        Args:
            code: BSL-код для проверки.
            severity_filter: фильтр по severity (['critical', 'warning']).
            category_filter: фильтр по category.

        Returns:
            Список findings: [{antipattern_id, severity, line, message, match}].
        """
        if severity_filter is None:
            severity_filter = ["critical", "warning"]

        findings: list[dict[str, Any]] = []

        for ap_id, ap in self.antipatterns.items():
            # Фильтр по severity
            if ap.get("severity") not in severity_filter:
                continue

            # Фильтр по category
            if category_filter and ap.get("category") not in category_filter:
                continue

            detect = ap.get("detect", {})

            # Regex detect
            if "regex" in detect:
                pattern_str = detect["regex"]["pattern"]
                flags_str = detect["regex"].get("flags", "m")
                flags = 0
                if "m" in flags_str:
                    flags |= re.MULTILINE
                if "s" in flags_str:
                    flags |= re.DOTALL
                if "i" in flags_str:
                    flags |= re.IGNORECASE

                try:
                    for match in re.finditer(pattern_str, code, flags):
                        line = code[: match.start()].count("\n") + 1
                        findings.append(
                            {
                                "antipattern_id": ap_id,
                                "severity": ap.get("severity", "info"),
                                "category": ap.get("category", ""),
                                "line": line,
                                "message": ap.get("title", ""),
                                "match": match.group(0)[:100],
                            }
                        )
                except re.error as exc:
                    log.warning("Regex error in antipattern %s: %s", ap_id, exc)

            # bsl_ls_rule detect — делегируется BSL LS (не здесь)
            # ast_pattern detect — требует tree-sitter (опционально)

        return findings

    # ─── Method availability ────────────────────────────────────────────────

    def check_method_availability(
        self,
        method_name: str,
        target_context: str,
        platform_version: str,
    ) -> dict[str, Any]:
        """Проверить доступность метода платформы в контексте.

        Использует предопределённый список методов, недоступных на клиенте.
        В Sprint 3 — упрощённая версия. Полная — с .hbk в Sprint 3 (после HBK parser).

        Args:
            method_name: имя метода (например, 'ЗаписьЖурналаРегистрации').
            target_context: 'server' | 'thin_client' | 'mobile_client'.
            platform_version: версия платформы (например, '8.3.20').

        Returns:
            {method_name, available, target_context, reason}.
        """
        # Предопределённый список методов, недоступных на клиенте
        server_only_methods = {
            "ЗаписьЖурналаРегистрации",
            "УровеньЖурналаРегистрации",
            "Метаданные",
            "ПараметрыСеанса",
            "Константы",
            "ФоновыеЗадания",
            "РегламентныеЗадания",
            "НайтиПоСсылкам",
            "Заблокировать",
            "Разблокировать",
        }

        # Методы, недоступные на сервере
        client_only_methods = {
            "Асинх",
            "Ждать",
            "ПоказатьВопрос",
            "ПоказатьПредупреждение",
            "ОткрытьФорму",
            "Закрыть",
            "Оповестить",
        }

        available = True
        reason = None

        if target_context in ("thin_client", "web_client", "mobile_client") and method_name in server_only_methods:
            available = False
            reason = f"Метод '{method_name}' доступен только на сервере"

        if target_context == "server" and method_name in client_only_methods:
            available = False
            reason = f"Метод '{method_name}' доступен только на клиенте"

        return {
            "method_name": method_name,
            "available": available,
            "target_context": target_context,
            "reason": reason,
            "platform_method": None,
        }

    # ─── Stats ───────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Статистика KB."""
        return {
            "patterns": len(self.patterns),
            "antipatterns": len(self.antipatterns),
            "critical_antipatterns": sum(1 for ap in self.antipatterns.values() if ap.get("severity") == "critical"),
            "warning_antipatterns": sum(1 for ap in self.antipatterns.values() if ap.get("severity") == "warning"),
        }
