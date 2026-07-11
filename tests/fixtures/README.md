# tests/fixtures/README.md
# Тестовые данные для 1C AI Assistant.

## mini_config/

Минимальная 1С конфигурация для тестов парсеров и индексеров.

Состав:
- `Configuration.xml` — корневой файл конфигурации (1 catalog + 1 document + 1 common module)
- `Catalogs/Товары/Товары.xml` — справочник с 2 атрибутами (Артикул, Цена)
- `Documents/Продажа/Продажа.xml` — документ с 2 атрибутами (Контрагент, Сумма) + 1 register record
- `CommonModules/ОбщегоНазначения/ОбщегоНазначения.xml` — общий модуль (server=true)

Использование в тестах:
```python
@pytest.fixture
def mini_config_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "mini_config"
```

## bsl_samples/

BSL-файлы для тестов парсера:

- `simple_module.bsl` — 1 процедура + 1 функция, без областей
- `with_regions.bsl` — с #Область ... #КонецОбласти (4 области)
- `with_methods.bsl` — 5+ методов, разные сигнатуры (Спринт 2)
- `with_async.bsl` — Асинх Функция (Спринт 2)
- `with_antipatterns.bsl` — query-in-loop, try-catch-silent (Спринт 3)
- `well_formed.bsl` — эталон по стандартам 1С (Спринт 3)

## Создание mini_config.zip

Для теста `1c-ai config add --zip`:

```bash
cd tests/fixtures
zip -r mini_config.zip mini_config/
```

Файл `mini_config.zip` коммитится в репо (он маленький, ~5 КБ).
