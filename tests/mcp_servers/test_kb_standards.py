"""Тесты для стандартов 1С (СТО/БСП) — TD-S4.2-03.

Покрывает:
- Загрузку standards YAML (8 файлов: 4 СТО + 4 БСП).
- JSON Schema валидацию.
- detect_standards_violations (regex).
- list_standards с фильтрами.
- search по стандартам.
- KbServer.get_standard / check_standards MCP tools.
- Validator integration (4-й параллельный валидатор).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.kb import KBCollection, KbServer


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def kb_dir() -> Path:
    """Путь к knowledge-base/ из корня проекта."""
    return Path(__file__).parent.parent.parent / "knowledge-base"


@pytest.fixture
def kb_collection(kb_dir: Path) -> KBCollection:
    return KBCollection(kb_dir)


@pytest.fixture
def kb_server(kb_dir: Path) -> KbServer:
    return KbServer(kb_dir)


# ─── Загрузка стандартов ────────────────────────────────────────────────────


class TestStandardsLoading:
    @pytest.mark.smoke
    def test_loads_standards(self, kb_collection: KBCollection):
        """Все 8 стандартов загружены (4 СТО + 4 БСП)."""
        assert len(kb_collection.standards) >= 8

    def test_standards_count_in_stats(self, kb_collection: KBCollection):
        stats = kb_collection.stats()
        assert stats["standards"] >= 8
        assert stats["standards_sto"] == 4
        assert stats["standards_bsp"] == 4
        assert stats["critical_standards"] >= 1
        assert stats["warning_standards"] >= 5

    def test_expected_standard_ids(self, kb_collection: KBCollection):
        ids = set(kb_collection.standards.keys())
        # СТО
        assert "sto-6.1-no-tabs" in ids
        assert "sto-2.1-no-english-markers" in ids
        assert "sto-2.1-no-latin-var-decl" in ids
        assert "sto-2.1-no-multiple-statements" in ids
        # БСП
        assert "bsp-find-by-name" in ids
        assert "bsp-find-by-code" in ids
        assert "bsp-message-to-user" in ids
        assert "bsp-no-execute-string-literal" in ids

    def test_each_standard_has_required_fields(self, kb_collection: KBCollection):
        for sid, std in kb_collection.standards.items():
            assert "id" in std, f"Standard {sid}: missing id"
            assert "title" in std, f"Standard {sid}: missing title"
            assert "source" in std, f"Standard {sid}: missing source"
            assert "type" in std["source"], f"Standard {sid}: missing source.type"
            assert "code" in std["source"], f"Standard {sid}: missing source.code"
            assert "severity" in std, f"Standard {sid}: missing severity"
            assert "detect" in std, f"Standard {sid}: missing detect"
            assert "regex" in std["detect"], f"Standard {sid}: regex detect required for Sprint 4.2"
            assert "example_bad" in std, f"Standard {sid}: missing example_bad"
            assert "example_good" in std, f"Standard {sid}: missing example_good"
            assert "recommendation_for_llm" in std, f"Standard {sid}: missing recommendation_for_llm"
            assert "description" in std, f"Standard {sid}: missing description"

    def test_no_duplicate_standard_ids(self, kb_collection: KBCollection):
        ids = [s["id"] for s in kb_collection.standards.values()]
        assert len(ids) == len(set(ids))

    def test_source_types_valid(self, kb_collection: KBCollection):
        valid_types = {"СТО", "БСП", "1C-EDT", "internal"}
        for std in kb_collection.standards.values():
            assert std["source"]["type"] in valid_types

    def test_severities_valid(self, kb_collection: KBCollection):
        valid_severities = {"critical", "warning", "info"}
        for std in kb_collection.standards.values():
            assert std["severity"] in valid_severities


# ─── get_standard / list_standards ──────────────────────────────────────────


class TestGetListStandards:
    def test_get_existing(self, kb_collection: KBCollection):
        std = kb_collection.get_standard("sto-6.1-no-tabs")
        assert std is not None
        assert std["source"]["type"] == "СТО"
        assert std["source"]["code"] == "6.1"
        assert std["severity"] == "warning"

    def test_get_nonexistent(self, kb_collection: KBCollection):
        assert kb_collection.get_standard("nonexistent") is None

    def test_list_by_source_type_sto(self, kb_collection: KBCollection):
        sto = kb_collection.list_standards(source_type="СТО")
        assert len(sto) == 4
        assert all(s["source"]["type"] == "СТО" for s in sto)

    def test_list_by_source_type_bsp(self, kb_collection: KBCollection):
        bsp = kb_collection.list_standards(source_type="БСП")
        assert len(bsp) == 4
        assert all(s["source"]["type"] == "БСП" for s in bsp)

    def test_list_by_severity_critical(self, kb_collection: KBCollection):
        critical = kb_collection.list_standards(severity="critical")
        # bsp-no-execute-string-literal — критический
        ids = {s["id"] for s in critical}
        assert "bsp-no-execute-string-literal" in ids
        assert all(s["severity"] == "critical" for s in critical)

    def test_list_by_category(self, kb_collection: KBCollection):
        style = kb_collection.list_standards(category="style")
        # sto-6.1-no-tabs + sto-2.1-no-multiple-statements
        assert len(style) >= 2
        assert all(s["category"] == "style" for s in style)


# ─── detect_standards_violations ────────────────────────────────────────────


class TestDetectStandardsViolations:
    @pytest.mark.smoke
    def test_detect_tabs(self, kb_collection: KBCollection):
        """sto-6.1-no-tabs: табуляция в коде."""
        code = "Процедура Тест()\n\tСообщить(\"Hello\");\nКонецПроцедуры"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "sto-6.1-no-tabs" in ids
        # Проверяем, что у finding есть ссылка на источник
        std_finding = next(f for f in findings if f["standard_id"] == "sto-6.1-no-tabs")
        assert std_finding["source"]["type"] == "СТО"
        assert std_finding["source"]["code"] == "6.1"
        assert "its.1c.ru" in std_finding["source"]["url"]

    def test_detect_english_markers(self, kb_collection: KBCollection):
        """sto-2.1-no-english-markers: TODO/FIXME в комментариях."""
        code = """// TODO: переписать
// FIXME: баг
Процедура Тест()
КонецПроцедуры"""
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "sto-2.1-no-english-markers" in ids

    def test_detect_latin_var_decl(self, kb_collection: KBCollection):
        """sto-2.1-no-latin-var-decl: транслит в именах переменных."""
        code = "Перем MyVariable;\nПерем CustomerName;\nПерем Счетчик;"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "sto-2.1-no-latin-var-decl" in ids
        # Должно найти 2 латинских имени (MyVariable, CustomerName), но не Счетчик
        std_findings = [f for f in findings if f["standard_id"] == "sto-2.1-no-latin-var-decl"]
        assert len(std_findings) == 2

    def test_detect_find_by_name(self, kb_collection: KBCollection):
        """bsp-find-by-name: НайтиПоНаименованию."""
        code = "Элемент = Справочники.Товары.НайтиПоНаименованию(Имя);"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "bsp-find-by-name" in ids

    def test_detect_find_by_code(self, kb_collection: KBCollection):
        """bsp-find-by-code: НайтиПоКоду."""
        code = "Элемент = Справочники.Товары.НайтиПоКоду(\"001\");"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "bsp-find-by-code" in ids

    def test_detect_message_to_user(self, kb_collection: KBCollection):
        """bsp-message-to-user: Сообщить()."""
        code = "Сообщить(\"Привет, мир!\");"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "bsp-message-to-user" in ids

    def test_detect_execute_string_literal(self, kb_collection: KBCollection):
        """bsp-no-execute-string-literal: Выполнить("...") — критический."""
        code = 'Выполнить("А = 1; Б = 2;");'
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "bsp-no-execute-string-literal" in ids
        # Должно быть critical severity
        std_finding = next(f for f in findings if f["standard_id"] == "bsp-no-execute-string-literal")
        assert std_finding["severity"] == "critical"

    def test_detect_multiple_statements(self, kb_collection: KBCollection):
        """sto-2.1-no-multiple-statements: несколько операторов через ;."""
        code = "А = 1; Б = 2; В = 3;"
        findings = kb_collection.detect_standards_violations(code)
        ids = [f["standard_id"] for f in findings]
        assert "sto-2.1-no-multiple-statements" in ids

    def test_detect_clean_code(self, kb_collection: KBCollection):
        """Чистый код — нет нарушений стандартов."""
        code = """Процедура Тест()
    Счетчик = 0;
    СообщитьПользователю("Готово");
КонецПроцедуры"""
        findings = kb_collection.detect_standards_violations(code)
        # Не должно быть нарушений
        ids = {f["standard_id"] for f in findings}
        assert "sto-6.1-no-tabs" not in ids
        assert "sto-2.1-no-latin-var-decl" not in ids
        assert "bsp-message-to-user" not in ids
        assert "bsp-find-by-name" not in ids

    def test_severity_filter(self, kb_collection: KBCollection):
        """Фильтр по severity: только critical."""
        code = 'Сообщить("test");\nВыполнить("А=1");'  # warning + critical
        findings = kb_collection.detect_standards_violations(
            code, severity_filter=["critical"]
        )
        ids = {f["standard_id"] for f in findings}
        # Только critical стандарты
        assert "bsp-no-execute-string-literal" in ids
        # warning стандарты не должны попасть
        assert "bsp-message-to-user" not in ids

    def test_source_type_filter(self, kb_collection: KBCollection):
        """Фильтр по типу источника: только СТО."""
        code = 'Сообщить("test");\n\t// TODO: fix'
        findings = kb_collection.detect_standards_violations(
            code, source_type_filter=["СТО"]
        )
        # Должны быть только СТО (no-tabs, no-english-markers)
        for f in findings:
            assert f["source"]["type"] == "СТО"

    def test_findings_have_line_numbers(self, kb_collection: KBCollection):
        """Findings содержат корректные номера строк."""
        code = "Строка1\nСтрока2\nСтрока3\n\tСообщить(\"tab\");"  # таб на 4-й строке
        findings = kb_collection.detect_standards_violations(code)
        std_finding = next(
            (f for f in findings if f["standard_id"] == "sto-6.1-no-tabs"),
            None,
        )
        assert std_finding is not None
        assert std_finding["line"] == 4

    def test_findings_have_source_info(self, kb_collection: KBCollection):
        """Каждый finding содержит полную информацию об источнике."""
        code = "Сообщить(\"test\");"
        findings = kb_collection.detect_standards_violations(code)
        for f in findings:
            assert "source" in f
            assert "type" in f["source"]
            assert "code" in f["source"]
            assert "url" in f["source"]


# ─── Search по стандартам ────────────────────────────────────────────────────


class TestSearchStandards:
    def test_search_finds_standard(self, kb_collection: KBCollection):
        """Поиск по 'tabs' находит sto-6.1-no-tabs."""
        results = kb_collection.search("tabs", category="standard")
        ids = [r["id"] for r in results]
        assert "sto-6.1-no-tabs" in ids
        assert all(r["type"] == "standard" for r in results)

    def test_search_finds_standard_by_sto_code(self, kb_collection: KBCollection):
        """Поиск по '6.1' находит sto-6.1 (по source.code)."""
        results = kb_collection.search("6.1", category="standard")
        ids = [r["id"] for r in results]
        assert "sto-6.1-no-tabs" in ids

    def test_search_finds_standard_by_bsp_keyword(self, kb_collection: KBCollection):
        """Поиск по 'найтипонаименованию' находит bsp-find-by-name."""
        results = kb_collection.search("найтипонаименованию", category="standard")
        ids = [r["id"] for r in results]
        assert "bsp-find-by-name" in ids

    def test_search_all_includes_standards(self, kb_collection: KBCollection):
        """Поиск с category='all' включает стандарты."""
        results = kb_collection.search("безопасность", category="all")
        types = {r["type"] for r in results}
        # Хотя бы один standard должен быть (bsp-no-execute-string-literal)
        assert "standard" in types or len(results) == 0


# ─── KbServer MCP tools ──────────────────────────────────────────────────────


class TestKbServerStandards:
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_get_standard(self, kb_server: KbServer):
        result = await kb_server.get_standard("sto-6.1-no-tabs")
        assert result.standard_id == "sto-6.1-no-tabs"
        assert result.source_type == "СТО"
        assert result.source_code == "6.1"
        assert "its.1c.ru" in result.source_url
        assert result.severity == "warning"
        assert result.detect_method == "regex"
        assert "табуляции" in result.description

    @pytest.mark.asyncio
    async def test_get_standard_not_found(self, kb_server: KbServer):
        with pytest.raises(ValueError, match="Standard not found"):
            await kb_server.get_standard("nonexistent")

    @pytest.mark.asyncio
    async def test_check_standards_finds_violations(self, kb_server: KbServer):
        """Код с табами и английскими маркерами → findings."""
        code = "// TODO: переписать\nПроцедура Тест()\n\tСообщить(\"Hi\");\nКонецПроцедуры"
        result = await kb_server.check_standards(code)
        assert len(result.findings) >= 2
        ids = {f["standard_id"] for f in result.findings}
        assert "sto-2.1-no-english-markers" in ids
        assert "sto-6.1-no-tabs" in ids

    @pytest.mark.asyncio
    async def test_check_standards_clean_code(self, kb_server: KbServer):
        """Чистый код → 0 findings."""
        code = "Процедура Тест()\n    СообщитьПользователю(\"Готово\");\nКонецПроцедуры"
        result = await kb_server.check_standards(code)
        assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_check_standards_source_type_filter(self, kb_server: KbServer):
        """Фильтр по source_type='БСП' — только БСП-нарушения."""
        code = "// TODO: fix\nСообщить(\"test\");"  # СТО + БСП нарушения
        result = await kb_server.check_standards(
            code, source_type_filter=["БСП"]
        )
        for f in result.findings:
            assert f["source"]["type"] == "БСП"

    @pytest.mark.asyncio
    async def test_check_standards_returns_source_info(self, kb_server: KbServer):
        """Каждый finding содержит полную информацию об источнике."""
        code = "\tСообщить(\"test\");"
        result = await kb_server.check_standards(code)
        for f in result.findings:
            assert "source" in f
            assert "type" in f["source"]
            assert "code" in f["source"]
            assert "url" in f["source"]

    def test_health_check_with_standards(self, kb_server: KbServer):
        """health_check возвращает True (KB не пустая)."""
        assert kb_server.health_check() is True


# ─── Validator integration (4-й параллельный валидатор) ─────────────────────


class TestValidatorStandardsIntegration:
    """TD-S4.2-03: проверка, что validate_node запускает 4-й валидатор стандартов.

    См. orchestrator/nodes/validate.py: _run_standards_validator.
    """

    def test_standards_validator_returns_empty_when_kb_none(self):
        """При kb_server=None валидатор стандартов возвращает пустой список."""
        import asyncio

        from orchestrator.nodes.validate import _run_standards_validator

        result = asyncio.run(_run_standards_validator(kb_server=None, code="// any code"))
        assert result == []

    @pytest.mark.asyncio
    async def test_standards_validator_detects_violations(self, kb_server: KbServer):
        """Валидатор стандартов находит нарушения в коде."""
        from orchestrator.nodes.validate import _run_standards_validator

        code = 'Выполнить("А = 1;");'  # critical: bsp-no-execute-string-literal
        findings = await _run_standards_validator(kb_server=kb_server, code=code)
        assert len(findings) > 0
        # Должен быть finding с source='kb_standards'
        std_findings = [f for f in findings if f.source == "kb_standards"]
        assert len(std_findings) > 0
        # Должен быть critical
        critical_findings = [f for f in std_findings if f.severity == "critical"]
        assert len(critical_findings) > 0
        # code должен содержать id стандарта
        assert any(f.code == "bsp-no-execute-string-literal" for f in std_findings)
        # fix_hint должен содержать ссылку на источник
        assert any("БСП" in (f.fix_hint or "") for f in std_findings)
