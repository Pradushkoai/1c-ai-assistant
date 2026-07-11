"""Тесты для mcp_servers.kb — KBCollection + KbServer."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.kb import KBCollection, KbServer


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def kb_dir() -> Path:
    """Путь к knowledge-base/ из корня проекта."""
    # tests/ -> .. -> knowledge-base/
    return Path(__file__).parent.parent.parent / "knowledge-base"


@pytest.fixture
def kb_collection(kb_dir: Path) -> KBCollection:
    """KBCollection загруженная из реальной knowledge-base/."""
    return KBCollection(kb_dir)


@pytest.fixture
def kb_server(kb_dir: Path) -> KbServer:
    """KbServer с реальной KB."""
    return KbServer(kb_dir)


# ─── KBCollection — загрузка ────────────────────────────────────────────────


class TestKBLoading:
    @pytest.mark.smoke
    def test_loads_patterns(self, kb_collection: KBCollection):
        assert len(kb_collection.patterns) >= 5

    @pytest.mark.smoke
    def test_loads_antipatterns(self, kb_collection: KBCollection):
        assert len(kb_collection.antipatterns) >= 10

    def test_pattern_ids(self, kb_collection: KBCollection):
        ids = set(kb_collection.patterns.keys())
        assert "transaction-wrapper" in ids
        assert "posting-handler" in ids
        assert "session-cache" in ids
        assert "deferred-modal" in ids
        assert "bsp-value-retrieval" in ids

    def test_antipattern_ids(self, kb_collection: KBCollection):
        ids = set(kb_collection.antipatterns.keys())
        assert "query-in-loop" in ids
        assert "try-catch-silent" in ids
        assert "metadata-on-client" in ids
        assert "select-star" in ids
        assert "transaction-without-try" in ids

    def test_stats(self, kb_collection: KBCollection):
        stats = kb_collection.stats()
        assert stats["patterns"] >= 5
        assert stats["antipatterns"] >= 10
        assert stats["critical_antipatterns"] >= 5


# ─── KBCollection — get_pattern ──────────────────────────────────────────────


class TestGetPattern:
    def test_get_existing(self, kb_collection: KBCollection):
        pattern = kb_collection.get_pattern("posting-handler")
        assert pattern is not None
        assert pattern["title"] == "Обработчик проведения документа"
        assert "code_template" in pattern

    def test_get_nonexistent(self, kb_collection: KBCollection):
        assert kb_collection.get_pattern("nonexistent") is None

    def test_list_by_category(self, kb_collection: KBCollection):
        transaction_patterns = kb_collection.list_patterns(category="transaction")
        assert len(transaction_patterns) >= 1
        assert all(p["category"] == "transaction" for p in transaction_patterns)


# ─── KBCollection — get_antipattern ──────────────────────────────────────────


class TestGetAntipattern:
    def test_get_existing(self, kb_collection: KBCollection):
        ap = kb_collection.get_antipattern("query-in-loop")
        assert ap is not None
        assert ap["severity"] == "critical"

    def test_get_nonexistent(self, kb_collection: KBCollection):
        assert kb_collection.get_antipattern("nonexistent") is None

    def test_list_by_severity(self, kb_collection: KBCollection):
        critical = kb_collection.list_antipatterns(severity="critical")
        assert len(critical) >= 5
        assert all(ap["severity"] == "critical" for ap in critical)


# ─── KBCollection — search ───────────────────────────────────────────────────


class TestSearch:
    def test_search_finds_pattern(self, kb_collection: KBCollection):
        results = kb_collection.search("posting-handler")
        assert len(results) > 0
        ids = [r["id"] for r in results]
        assert "posting-handler" in ids

    def test_search_finds_antipattern(self, kb_collection: KBCollection):
        results = kb_collection.search("запрос в цикле")
        assert len(results) > 0

    def test_search_top_k(self, kb_collection: KBCollection):
        results = kb_collection.search("запрос", top_k=3)
        assert len(results) <= 3

    def test_search_category_filter(self, kb_collection: KBCollection):
        results = kb_collection.search("транзакция", category="pattern")
        assert all(r["type"] == "pattern" for r in results)

    def test_search_no_results(self, kb_collection: KBCollection):
        results = kb_collection.search("несуществующийтермин12345")
        assert results == []


# ─── KBCollection — detect_antipatterns ──────────────────────────────────────


class TestDetectAntipatterns:
    @pytest.mark.smoke
    def test_detect_query_in_loop(self, kb_collection: KBCollection):
        code = """Для Каждого СтрокаТовары Из Товары Цикл
    Запрос = Новый Запрос;
    Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";
КонецЦикла;"""
        findings = kb_collection.detect_antipatterns(code)
        ids = [f["antipattern_id"] for f in findings]
        assert "query-in-loop" in ids

    def test_detect_select_star(self, kb_collection: KBCollection):
        code = 'Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";'
        findings = kb_collection.detect_antipatterns(code)
        ids = [f["antipattern_id"] for f in findings]
        assert "select-star" in ids

    def test_detect_metadata_on_client(self, kb_collection: KBCollection):
        code = "Если Метаданные.Справочники.Товары.ДлинаКода = 9 Тогда"
        findings = kb_collection.detect_antipatterns(code)
        ids = [f["antipattern_id"] for f in findings]
        assert "metadata-on-client" in ids

    def test_detect_clean_code(self, kb_collection: KBCollection):
        code = """Процедура Тест()
    Сообщить("Hello");
КонецПроцедуры"""
        findings = kb_collection.detect_antipatterns(code)
        assert findings == []

    def test_detect_severity_filter(self, kb_collection: KBCollection):
        code = 'Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";'
        # Только critical — select-star это warning, не должно попасть
        findings = kb_collection.detect_antipatterns(code, severity_filter=["critical"])
        ids = [f["antipattern_id"] for f in findings]
        assert "select-star" not in ids

    def test_findings_have_line_numbers(self, kb_collection: KBCollection):
        code = """Строка1
Строка2
Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";"""
        findings = kb_collection.detect_antipatterns(code)
        assert len(findings) > 0
        assert findings[0]["line"] >= 3


# ─── KBCollection — check_method_availability ────────────────────────────────


class TestCheckMethodAvailability:
    def test_server_method_on_client(self, kb_collection: KBCollection):
        result = kb_collection.check_method_availability("ЗаписьЖурналаРегистрации", "thin_client", "8.3.20")
        assert result["available"] is False

    def test_server_method_on_server(self, kb_collection: KBCollection):
        result = kb_collection.check_method_availability("ЗаписьЖурналаРегистрации", "server", "8.3.20")
        assert result["available"] is True

    def test_client_method_on_server(self, kb_collection: KBCollection):
        result = kb_collection.check_method_availability("ОткрытьФорму", "server", "8.3.20")
        assert result["available"] is False

    def test_unknown_method_available(self, kb_collection: KBCollection):
        result = kb_collection.check_method_availability("НовыйЗапрос", "server", "8.3.20")
        assert result["available"] is True


# ─── KbServer — MCP tools ────────────────────────────────────────────────────


class TestKbServer:
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_get_pattern(self, kb_server: KbServer):
        result = await kb_server.get_pattern("posting-handler")
        assert result.pattern_id == "posting-handler"
        assert result.title == "Обработчик проведения документа"
        assert result.code_template is not None

    @pytest.mark.asyncio
    async def test_get_pattern_not_found(self, kb_server: KbServer):
        with pytest.raises(ValueError, match="not found"):
            await kb_server.get_pattern("nonexistent")

    @pytest.mark.asyncio
    async def test_get_antipattern(self, kb_server: KbServer):
        result = await kb_server.get_antipattern("query-in-loop")
        assert result.antipattern_id == "query-in-loop"
        assert result.severity == "critical"

    @pytest.mark.asyncio
    async def test_search_kb(self, kb_server: KbServer):
        result = await kb_server.search_kb("транзакция")
        assert result.query == "транзакция"
        assert len(result.results) > 0

    @pytest.mark.asyncio
    async def test_check_method_availability(self, kb_server: KbServer):
        result = await kb_server.check_method_availability("ЗаписьЖурналаРегистрации", "thin_client", "8.3.20")
        assert result.available is False

    @pytest.mark.asyncio
    async def test_check_antipatterns(self, kb_server: KbServer):
        code = """Для Каждого Стр Из Товары Цикл
    Запрос = Новый Запрос;
КонецЦикла;"""
        result = await kb_server.check_antipatterns(code)
        assert len(result.findings) > 0

    def test_health_check(self, kb_server: KbServer):
        assert kb_server.health_check() is True


# ─── KB YAML валидность ──────────────────────────────────────────────────────


class TestKBValidity:
    def test_all_patterns_have_required_fields(self, kb_collection: KBCollection):
        for pid, p in kb_collection.patterns.items():
            assert "id" in p, f"Pattern {pid}: missing id"
            assert "title" in p, f"Pattern {pid}: missing title"
            assert "category" in p, f"Pattern {pid}: missing category"
            assert "when_to_use" in p, f"Pattern {pid}: missing when_to_use"
            assert "code_template" in p, f"Pattern {pid}: missing code_template"
            assert "example_good" in p, f"Pattern {pid}: missing example_good"
            assert "applicable_to" in p, f"Pattern {pid}: missing applicable_to"

    def test_all_antipatterns_have_required_fields(self, kb_collection: KBCollection):
        for aid, ap in kb_collection.antipatterns.items():
            assert "id" in ap, f"Antipattern {aid}: missing id"
            assert "title" in ap, f"Antipattern {aid}: missing title"
            assert "severity" in ap, f"Antipattern {aid}: missing severity"
            assert "detect" in ap, f"Antipattern {aid}: missing detect"
            assert "example_bad" in ap, f"Antipattern {aid}: missing example_bad"
            assert "example_good" in ap, f"Antipattern {aid}: missing example_good"
            assert "recommendation_for_llm" in ap, f"Antipattern {aid}: missing recommendation_for_llm"

    def test_all_antipatterns_have_regex_detect(self, kb_collection: KBCollection):
        """Все 10 антипаттернов имеют regex detect (для Sprint 3)."""
        for aid, ap in kb_collection.antipatterns.items():
            detect = ap.get("detect", {})
            assert "regex" in detect, f"Antipattern {aid}: missing regex detect (required for Sprint 3)"

    def test_no_duplicate_ids(self, kb_collection: KBCollection):
        pattern_ids = [p["id"] for p in kb_collection.patterns.values()]
        assert len(pattern_ids) == len(set(pattern_ids))

        ap_ids = [ap["id"] for ap in kb_collection.antipatterns.values()]
        assert len(ap_ids) == len(set(ap_ids))
