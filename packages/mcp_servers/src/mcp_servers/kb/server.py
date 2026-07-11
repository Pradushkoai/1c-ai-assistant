"""KbServer — реализация 5 KB MCP tools.

Использует KBCollection для доступа к YAML-правилам.

См. ADR-0010 (MCP tool contracts) и ADR-0012 (KB-as-code).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .contracts import (
    CheckAntipatternsOutput,
    CheckMethodAvailabilityOutput,
    GetAntipatternOutput,
    GetPatternOutput,
    SearchKbOutput,
)
from .loader import KBCollection

log = logging.getLogger(__name__)

DEFAULT_KB_DIR = "knowledge-base"


class KbServer:
    """Реализация 5 KB MCP tools через KBCollection.

    Attributes:
        kb: KBCollection с загруженными patterns/antipatterns.
    """

    def __init__(
        self,
        kb_dir: str | Path | None = None,
        platform_methods_db: str | Path | None = None,
    ) -> None:
        """Инициализация.

        Args:
            kb_dir: путь к knowledge-base/ директории.
                По умолчанию — './knowledge-base' (или из env).
            platform_methods_db: путь к derived/platform/{version}/platform-methods.db.
                Если None — пробуется env PLATFORM_METHODS_DB, иначе None (хардкод-fallback).
        """
        if kb_dir is None:
            import os

            kb_dir = os.environ.get("KNOWLEDGE_BASE_DIR", DEFAULT_KB_DIR)
        self.kb_dir = Path(kb_dir)

        if platform_methods_db is None:
            import os

            env_db = os.environ.get("PLATFORM_METHODS_DB")
            if env_db:
                platform_methods_db = env_db
        self.platform_methods_db = Path(platform_methods_db) if platform_methods_db else None

        self.kb = KBCollection(self.kb_dir, platform_methods_db=self.platform_methods_db)

    async def get_pattern(self, pattern_id: str, target_object_type: str | None = None) -> GetPatternOutput:
        """Получить эталонный паттерн по id."""
        pattern = self.kb.get_pattern(pattern_id)
        if pattern is None:
            raise ValueError(f"Pattern not found: {pattern_id}")

        # Фильтр по применимости
        if target_object_type and target_object_type not in pattern.get("applicable_to", []):
            raise ValueError(f"Pattern '{pattern_id}' not applicable to '{target_object_type}'")

        return GetPatternOutput(
            pattern_id=pattern["id"],
            title=pattern.get("title", ""),
            when_to_use=pattern.get("when_to_use", ""),
            code_template=pattern.get("code_template"),
            variables=pattern.get("variables", []),
            example_good=pattern.get("example_good", ""),
        )

    async def get_antipattern(self, antipattern_id: str) -> GetAntipatternOutput:
        """Получить описание антипаттерна по id."""
        ap = self.kb.get_antipattern(antipattern_id)
        if ap is None:
            raise ValueError(f"Antipattern not found: {antipattern_id}")

        detect = ap.get("detect", {})
        if "regex" in detect:
            detect_method = "regex"
        elif "ast_pattern" in detect:
            detect_method = "ast_pattern"
        elif "bsl_ls_rule" in detect:
            detect_method = "bsl_ls_rule"
        else:
            detect_method = "unknown"

        return GetAntipatternOutput(
            antipattern_id=ap["id"],
            title=ap.get("title", ""),
            severity=ap.get("severity", "info"),
            detect_method=detect_method,
            recommendation_for_llm=ap.get("recommendation_for_llm", ""),
            example_bad=ap.get("example_bad", ""),
            example_good=ap.get("example_good", ""),
        )

    async def search_kb(
        self,
        query: str,
        top_k: int = 5,
        category: str = "all",
    ) -> SearchKbOutput:
        """Полнотекстовый поиск по KB."""
        results = self.kb.search(query, top_k=top_k, category=category)
        return SearchKbOutput(query=query, results=results)

    async def check_method_availability(
        self,
        method_name: str,
        target_context: str,
        platform_version: str,
    ) -> CheckMethodAvailabilityOutput:
        """Проверить доступность метода платформы в контексте."""
        result = self.kb.check_method_availability(
            method_name=method_name,
            target_context=target_context,
            platform_version=platform_version,
        )
        # Прокидываем platform_method из KBCollection (если метод найден в БД).
        # Sprint 3.1 (2026-07-12): ранее здесь всегда было None — баг.
        platform_method_dict = result.get("platform_method")
        platform_method_obj = None
        if platform_method_dict is not None:
            try:
                from parsers.models import ContextAvailability, PlatformMethod

                avail_dict = platform_method_dict.get("availability", {})
                platform_method_obj = PlatformMethod(
                    name=platform_method_dict["name"],
                    signature=platform_method_dict.get("signature", ""),
                    description=platform_method_dict.get("description", ""),
                    is_procedure=False,
                    availability=ContextAvailability(
                        server=avail_dict.get("server", True),
                        thin_client=avail_dict.get("thin_client", True),
                        web_client=avail_dict.get("web_client", True),
                        mobile_client=avail_dict.get("mobile_client", False),
                        external_connection=avail_dict.get("external_connection", True),
                    ),
                )
            except Exception as exc:
                log.warning("Failed to build PlatformMethod: %s", exc)
                platform_method_obj = None

        return CheckMethodAvailabilityOutput(
            method_name=result["method_name"],
            available=result["available"],
            target_context=result["target_context"],
            reason=result.get("reason"),
            platform_method=platform_method_obj,
        )

    async def check_antipatterns(
        self,
        code: str,
        severity_filter: list[str] | None = None,
        category_filter: list[str] | None = None,
    ) -> CheckAntipatternsOutput:
        """Проверить BSL-код на антипаттерны."""
        findings = self.kb.detect_antipatterns(
            code=code,
            severity_filter=severity_filter,
            category_filter=category_filter,
        )
        return CheckAntipatternsOutput(findings=findings)

    def health_check(self) -> bool:
        """Проверить, что KB загружена."""
        return len(self.kb.patterns) > 0 or len(self.kb.antipatterns) > 0
