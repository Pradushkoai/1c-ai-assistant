"""Тесты для parsers.models — Pydantic v2 моделей.

См. TESTING_POLICY.md:
- smoke тесты (fast)
- property-based через hypothesis
- round-trip, frozen, extra=forbid, JSON Schema export
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, settings
from pydantic import ValidationError, TypeAdapter

from parsers.models import (
    ModelConfig,
    ObjectRef,
    Version,
    ExecutionEnvironment,
    ContextAvailability,
    Region,
    MethodParameter,
    Method,
    BslModule,
    MetadataType,
    AttributeKind,
    Attribute,
    ObjectMetadata,
    CatalogMetadata,
    DocumentMetadata,
    CommonModuleMetadata,
    FormElement,
    FormMetadata,
    PlatformMethod,
    PlatformProperty,
    VersionInfo,
    ConfigMeta,
    ConfigRegistryEntry,
    DependencyEdge,
    CallEdge,
    GraphStats,
)
from datetime import UTC


# ─── Smoke тесты: базовое создание ───────────────────────────────────────────


class TestModelConfig:
    """Базовый конфиг — frozen + extra=forbid + strict."""

    def test_model_config_is_frozen(self):
        """Модели frozen — мутация вызывает ValidationError."""
        ref = ObjectRef(type="Catalog", name="Товары")
        with pytest.raises(ValidationError):
            ref.name = "Другое"  # type: ignore[misc]

    def test_model_config_extra_forbid(self):
        """Лишние поля вызывают ошибку."""
        with pytest.raises(ValidationError):
            ObjectRef(type="Catalog", name="X", extra_field="bad")  # type: ignore[call-arg]

    def test_model_config_strict(self):
        """Strict: int не конвертируется в str автоматически."""
        # version: int field, передаём string — должно упасть в strict mode
        with pytest.raises(ValidationError):
            Version(major="8", minor=3, patch=20)  # type: ignore[arg-type]


# ─── ObjectRef ───────────────────────────────────────────────────────────────


class TestObjectRef:
    """ObjectRef — ссылка на объект метаданных."""

    @pytest.mark.smoke
    def test_from_string_valid(self):
        ref = ObjectRef.from_string("Catalog.Товары")
        assert ref.type == "Catalog"
        assert ref.name == "Товары"

    @pytest.mark.smoke
    def test_from_string_cyrillic(self):
        ref = ObjectRef.from_string("Document.Продажа")
        assert ref.type == "Document"
        assert ref.name == "Продажа"

    def test_from_string_with_dots_in_name(self):
        """Имя может содержать точки (например, 'CommonModule.ОбщегоНазначения')."""
        ref = ObjectRef.from_string("CommonModule.ОбщегоНазначения")
        assert ref.type == "CommonModule"
        assert ref.name == "ОбщегоНазначения"

    def test_from_string_invalid_no_dot(self):
        with pytest.raises(ValueError, match="Invalid ObjectRef"):
            ObjectRef.from_string("invalid")

    def test_from_string_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid ObjectRef"):
            ObjectRef.from_string("")

    def test_from_string_invalid_empty_type(self):
        with pytest.raises(ValueError, match="Invalid ObjectRef"):
            ObjectRef.from_string(".Имя")

    def test_from_string_invalid_empty_name(self):
        with pytest.raises(ValueError, match="Invalid ObjectRef"):
            ObjectRef.from_string("Catalog.")

    def test_str_round_trip(self):
        """str(ObjectRef) → ObjectRef.from_string → исходный ObjectRef."""
        ref = ObjectRef(type="Catalog", name="Товары")
        assert ObjectRef.from_string(str(ref)) == ref

    def test_equality(self):
        assert ObjectRef(type="Catalog", name="X") == ObjectRef(type="Catalog", name="X")
        assert ObjectRef(type="Catalog", name="X") != ObjectRef(type="Document", name="X")


# ─── Version ─────────────────────────────────────────────────────────────────


class TestVersion:
    """Version — версия 1С."""

    @pytest.mark.smoke
    def test_from_string_3_parts(self):
        v = Version.from_string("8.3.20")
        assert v.major == 8
        assert v.minor == 3
        assert v.patch == 20
        assert v.build is None

    def test_from_string_4_parts(self):
        v = Version.from_string("8.3.21.62")
        assert v.major == 8
        assert v.minor == 3
        assert v.patch == 21
        assert v.build == 62

    def test_str_3_parts(self):
        assert str(Version.from_string("8.3.20")) == "8.3.20"

    def test_str_4_parts(self):
        assert str(Version.from_string("8.3.21.62")) == "8.3.21.62"

    def test_from_string_invalid_empty(self):
        with pytest.raises(ValueError, match="Empty"):
            Version.from_string("")

    def test_from_string_invalid_too_few_parts(self):
        with pytest.raises(ValueError, match="Invalid version"):
            Version.from_string("8.3")

    def test_from_string_invalid_non_numeric(self):
        with pytest.raises(ValueError, match="Invalid version"):
            Version.from_string("8.3.X")

    def test_negative_major_raises(self):
        with pytest.raises(ValidationError):
            Version(major=-1, minor=3, patch=20)


# ─── ExecutionEnvironment ────────────────────────────────────────────────────


class TestExecutionEnvironment:
    """ExecutionEnvironment — контекст выполнения."""

    @pytest.mark.smoke
    def test_values(self):
        assert ExecutionEnvironment.SERVER.value == "server"
        assert ExecutionEnvironment.THIN_CLIENT.value == "thin_client"
        assert ExecutionEnvironment.MOBILE_CLIENT.value == "mobile_client"

    def test_all_environments_present(self):
        """Все 9 контекстов определены."""
        envs = list(ExecutionEnvironment)
        assert len(envs) == 9
        assert ExecutionEnvironment.UNKNOWN in envs


# ─── ContextAvailability ─────────────────────────────────────────────────────


class TestContextAvailability:
    """ContextAvailability — доступность в контекстах."""

    @pytest.mark.smoke
    def test_defaults(self):
        """По умолчанию: доступно везде, кроме мобильных."""
        avail = ContextAvailability()
        assert avail.server is True
        assert avail.thin_client is True
        assert avail.mobile_client is False
        assert avail.mobile_application is False

    def test_available_in(self):
        avail = ContextAvailability(server=True, thin_client=False)
        assert avail.available_in(ExecutionEnvironment.SERVER) is True
        assert avail.available_in(ExecutionEnvironment.THIN_CLIENT) is False

    def test_to_dict(self):
        avail = ContextAvailability(server=True, thin_client=False)
        d = avail.to_dict()
        assert d["server"] is True
        assert d["thin_client"] is False
        assert "mobile_client" in d


# ─── Method/Region/BslModule ─────────────────────────────────────────────────


class TestRegion:
    """Region — область BSL-модуля."""

    def test_create(self):
        region = Region(name="ПрограммныйИнтерфейс", start_line=1, end_line=10)
        assert region.name == "ПрограммныйИнтерфейс"
        assert region.parent is None
        assert region.methods == []

    def test_with_parent(self):
        region = Region(
            name="Вложенная",
            start_line=2,
            end_line=5,
            parent="ПрограммныйИнтерфейс",
        )
        assert region.parent == "ПрограммныйИнтерфейс"

    def test_invalid_line_zero(self):
        with pytest.raises(ValidationError):
            Region(name="X", start_line=0, end_line=10)


class TestMethodParameter:
    """MethodParameter — параметр метода."""

    def test_simple(self):
        param = MethodParameter(name="Параметр1")
        assert param.name == "Параметр1"
        assert param.by_value is False
        assert param.has_default is False

    def test_by_value(self):
        param = MethodParameter(name="Параметр1", by_value=True)
        assert param.by_value is True

    def test_with_default(self):
        param = MethodParameter(
            name="Параметр1",
            default_value="0",
            has_default=True,
        )
        assert param.has_default is True
        assert param.default_value == "0"


class TestMethod:
    """Method — метод BSL-модуля."""

    def test_procedure(self):
        m = Method(
            name="Тест",
            is_procedure=True,
            start_line=1,
            end_line=5,
        )
        assert m.is_procedure is True
        assert m.is_export is False
        assert m.is_async is False
        assert m.parameters == []

    def test_export_function(self):
        m = Method(
            name="Сложить",
            is_procedure=False,
            is_export=True,
            start_line=1,
            end_line=3,
            parameters=[
                MethodParameter(name="a"),
                MethodParameter(name="b"),
            ],
        )
        assert m.is_procedure is False
        assert m.is_export is True
        assert len(m.parameters) == 2


class TestBslModule:
    """BslModule — BSL-модуль целиком."""

    def test_create_minimal(self):
        module = BslModule(
            object_ref=ObjectRef.from_string("CommonModule.Тест"),
            module_kind="CommonModule",
            source="// empty",
            line_count=1,
        )
        assert module.object_ref.name == "Тест"
        assert module.methods == []
        assert module.regions == []

    def test_json_schema_export(self):
        """JSON Schema должна генерироваться (для MCP inputSchema)."""
        schema = BslModule.model_json_schema()
        assert "properties" in schema
        assert "object_ref" in schema["properties"]
        assert "source" in schema["properties"]

    def test_round_trip(self):
        """model_dump_json → model_validate_json = исходная модель."""
        module = BslModule(
            object_ref=ObjectRef.from_string("CommonModule.Тест"),
            module_kind="CommonModule",
            source="Процедура Т() КонецПроцедуры",
            methods=[
                Method(name="Т", is_procedure=True, start_line=1, end_line=1),
            ],
            line_count=1,
        )
        dumped = module.model_dump_json()
        restored = BslModule.model_validate_json(dumped)
        assert restored == module


# ─── Metadata models ─────────────────────────────────────────────────────────


class TestAttribute:
    """Attribute — реквизит объекта."""

    def test_default_kind(self):
        attr = Attribute(name="Артикул", type="Строка")
        assert attr.kind == AttributeKind.ATTRIBUTE
        assert attr.required is False

    def test_with_kind(self):
        attr = Attribute(
            name="Товары",
            type="СправочникСсылка.Товары",
            kind=AttributeKind.TABULAR_SECTION,
        )
        assert attr.kind == AttributeKind.TABULAR_SECTION


class TestCatalogMetadata:
    """CatalogMetadata — метаданные справочника."""

    def test_create(self):
        cat = CatalogMetadata(
            object_ref=ObjectRef.from_string("Catalog.Товары"),
            name="Товары",
            code_length=9,
            description_length=50,
        )
        assert cat.metadata_type == MetadataType.CATALOG
        assert cat.code_length == 9
        assert cat.attributes == []

    def test_with_attributes(self):
        cat = CatalogMetadata(
            object_ref=ObjectRef.from_string("Catalog.Товары"),
            name="Товары",
            attributes=[
                Attribute(name="Артикул", type="Строка"),
                Attribute(name="Цена", type="Число"),
            ],
        )
        assert len(cat.attributes) == 2
        assert cat.attributes[0].name == "Артикул"


class TestDocumentMetadata:
    """DocumentMetadata — метаданные документа."""

    def test_create(self):
        doc = DocumentMetadata(
            object_ref=ObjectRef.from_string("Document.Продажа"),
            name="Продажа",
            register_records=["AccumulationRegister.Продажи"],
        )
        assert doc.metadata_type == MetadataType.DOCUMENT
        assert doc.posting == "Allow"
        assert "AccumulationRegister.Продажи" in doc.register_records


class TestCommonModuleMetadata:
    """CommonModuleMetadata — метаданные общего модуля."""

    def test_create_server_module(self):
        cm = CommonModuleMetadata(
            object_ref=ObjectRef.from_string("CommonModule.ОбщегоНазначения"),
            name="ОбщегоНазначения",
            server=True,
            global_=False,
        )
        assert cm.metadata_type == MetadataType.COMMON_MODULE
        assert cm.server is True
        assert cm.global_ is False

    def test_global_field_alias(self):
        """Поле 'global' (Python keyword) доступно через alias 'global_'."""
        cm = CommonModuleMetadata(
            object_ref=ObjectRef.from_string("CommonModule.Глобальный"),
            name="Глобальный",
            server=True,
            **{"global": True},  # type: ignore[arg-type]
        )
        assert cm.global_ is True


class TestFormElement:
    """FormElement — элемент формы (с рекурсивной структурой)."""

    def test_create_leaf(self):
        elem = FormElement(name="ПолеВвода", type="InputField")
        assert elem.children == []

    def test_create_with_children(self):
        parent = FormElement(
            name="Группа",
            type="Group",
            children=[
                FormElement(name="Кнопка1", type="Button"),
                FormElement(name="Кнопка2", type="Button"),
            ],
        )
        assert len(parent.children) == 2


class TestFormMetadata:
    """FormMetadata — метаданные формы."""

    def test_create(self):
        form = FormMetadata(
            object_ref=ObjectRef.from_string("Catalog.Товары"),
            form_name="ФормаСписка",
            title="Товары",
        )
        assert form.form_name == "ФормаСписка"
        assert form.elements == []


# ─── PlatformMethod/PlatformProperty ─────────────────────────────────────────


class TestPlatformMethod:
    """PlatformMethod — метод платформы."""

    def test_create(self):
        m = PlatformMethod(
            name="ЗаписьЖурналаРегистрации",
            signature="ЗаписьЖурналаРегистрации(ИмяСобытия, Уровень, Метаданные, ДанныеСобытия, Комментарий)",
            description="Записывает сообщение в журнал регистрации",
            is_procedure=True,
            availability=ContextAvailability(
                server=True,
                thin_client=False,
                web_client=False,
            ),
        )
        assert m.name == "ЗаписьЖурналаРегистрации"
        assert m.is_procedure is True
        assert m.availability.server is True
        assert m.availability.thin_client is False


class TestPlatformProperty:
    """PlatformProperty — свойство платформы."""

    def test_create(self):
        p = PlatformProperty(
            name="Метаданные",
            description="Текущие метаданные объекта",
            type="Метаданные",
            availability=ContextAvailability(server=True, thin_client=False),
        )
        assert p.name == "Метаданные"
        assert p.availability.server is True


# ─── Config models ───────────────────────────────────────────────────────────


class TestVersionInfo:
    def test_create(self):
        vi = VersionInfo(version="11.4.5.3", edition="Управление торговлей")
        assert vi.version == "11.4.5.3"
        assert vi.edition == "Управление торговлей"


class TestConfigMeta:
    def test_create(self):
        from parsers.models import Version

        cm = ConfigMeta(
            name="УправлениеТорговлей",
            version_info=VersionInfo(version="11.4.5.3"),
            platform_version=Version.from_string("8.3.20"),
        )
        assert cm.name == "УправлениеТорговлей"
        assert cm.default_language == "ru"
        assert cm.object_counts == {}


class TestConfigRegistryEntry:
    def test_create(self):
        from datetime import datetime, timezone

        entry = ConfigRegistryEntry(
            name="ut11",
            version="4.5.3",
            added_at=datetime.now(UTC),
            source_path="/data/configs/ut11/4.5.3",
            index_path="/derived/configs/ut11/4.5.3",
        )
        assert entry.name == "ut11"
        assert entry.is_fresh is None


# ─── Graph models ────────────────────────────────────────────────────────────


class TestDependencyEdge:
    def test_create(self):
        edge = DependencyEdge(
            source=ObjectRef.from_string("Catalog.Товары"),
            target=ObjectRef.from_string("Catalog.Контрагенты"),
            edge_type="Attribute",
            detail="Владелец",
        )
        assert edge.source.name == "Товары"
        assert edge.target.name == "Контрагенты"


class TestCallEdge:
    def test_create(self):
        edge = CallEdge(
            source_module=ObjectRef.from_string("CommonModule.ОбщегоНазначения"),
            source_method="Сложить",
            target_module=None,
            target_method="ВнутренняяФункция",
            line=42,
        )
        assert edge.target_module is None
        assert edge.line == 42

    def test_platform_call(self):
        edge = CallEdge(
            source_module=ObjectRef.from_string("Document.Продажа"),
            source_method="ОбработкаПроведения",
            target_module=None,
            target_method="ЗаписьЖурналаРегистрации",
            line=15,
            is_platform=True,
        )
        assert edge.is_platform is True


class TestGraphStats:
    def test_create(self):
        stats = GraphStats(nodes=100, edges=250, cycles=2, avg_degree=2.5)
        assert stats.nodes == 100
        assert stats.top_hubs == []


# ─── Property-based тесты ────────────────────────────────────────────────────


class TestObjectRefProperty:
    """Property-based тесты для ObjectRef (через hypothesis)."""

    @given(
        ref_type=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Lt")),
        ),
        name=st.text(min_size=1, max_size=20),
    )
    @settings(max_examples=50)
    def test_round_trip(self, ref_type: str, name: str):
        """ObjectRef.from_string(str(ObjectRef(type, name))) == ObjectRef(type, name).

        Property: для любых валидных type и name round-trip через строку сохраняет объект.
        """
        ref = ObjectRef(type=ref_type, name=name)
        restored = ObjectRef.from_string(str(ref))
        assert restored == ref

    @given(
        ref_type=st.text(min_size=1, max_size=20),
        name=st.text(min_size=1, max_size=20),
    )
    @settings(max_examples=50)
    def test_frozen(self, ref_type: str, name: str):
        """ObjectRef всегда frozen — мутация невозможна."""
        ref = ObjectRef(type=ref_type, name=name)
        with pytest.raises(ValidationError):
            ref.name = "other"  # type: ignore[misc]


class TestVersionProperty:
    """Property-based тесты для Version."""

    @given(
        major=st.integers(min_value=0, max_value=100),
        minor=st.integers(min_value=0, max_value=100),
        patch=st.integers(min_value=0, max_value=10000),
        build=st.one_of(st.none(), st.integers(min_value=0, max_value=100000)),
    )
    @settings(max_examples=50)
    def test_round_trip(self, major: int, minor: int, patch: int, build: int | None):
        """Version.from_string(str(Version(...))) == Version(...)."""
        v = Version(major=major, minor=minor, patch=patch, build=build)
        restored = Version.from_string(str(v))
        assert restored == v


# ─── JSON Schema export ──────────────────────────────────────────────────────


class TestJsonSchemaExport:
    """Все модели должны экспортировать JSON Schema (для MCP inputSchema)."""

    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "model_class",
        [
            ObjectRef,
            Version,
            ContextAvailability,
            Region,
            MethodParameter,
            Method,
            BslModule,
            Attribute,
            ObjectMetadata,
            CatalogMetadata,
            DocumentMetadata,
            CommonModuleMetadata,
            FormElement,
            FormMetadata,
            PlatformMethod,
            PlatformProperty,
            VersionInfo,
            ConfigMeta,
            ConfigRegistryEntry,
            DependencyEdge,
            CallEdge,
            GraphStats,
        ],
    )
    def test_json_schema_export(self, model_class):
        """Каждая модель должна генерировать JSON Schema.

        Для рекурсивных моделей (FormElement) schema может содержать $ref
        вместо прямой 'properties' — это нормально.
        """
        schema = model_class.model_json_schema()
        assert isinstance(schema, dict)
        # Либо 'properties' напрямую, либо '$ref' (для рекурсивных типов),
        # либо '$defs' с определением
        assert "properties" in schema or "$ref" in schema or "$defs" in schema
