# Шаг 7 — KB-as-code формат

> **ADR-0012:** KB-as-code — YAML-правила + Markdown-описания, ревью через PR
> **Зависимости:** Шаг 5 (`kb.get_pattern`, `kb.get_antipattern`, `kb.check_antipatterns`), Шаг 6 (роли)
> **Артефакт:** `knowledge-base/{patterns,antipatterns,prompts,schemas}/`

## 1. Зачем YAML, а не Markdown

Старый репо (`1c-ai-dev-env`) хранил KB как Markdown (`knowledge_base/antipatterns/common_antipatterns.md`). Это работало для человека (читабельно), но не для машины:
- нельзя автоматически детектить антипаттерн в коде (нет `detect:` блока)
- нельзя валидировать структуру (JSON Schema не к Markdown)
- нельзя сгенерировать system prompt для Coder'а (`recommendation_for_llm` поле)
- нельзя версионировать отдельные правила (один коммит = одно правило)

YAML решает это:
- структурированный `detect:` блок (regex / AST / bsl_ls_rule)
- JSON Schema валидация при загрузке
- одно правило = один файл = один PR
- Markdown-описание живёт рядом (человек читает, машина парсит YAML)

**Принцип:** YAML — для машины (детект + генерация промпта), Markdown — для человека (расширенное описание). Они **комплиментарны**, не взаимоисключающи.

## 2. Структура `knowledge-base/`

```
knowledge-base/
├── index.json                    ← реестр всех элементов
├── schemas/                      ← JSON Schemas (валидация)
│   ├── antipattern.schema.json
│   ├── pattern.schema.json
│   ├── subtask.schema.json       ← для Plan structured output
│   ├── code-output.schema.json   ← для Coder structured output
│   └── review-output.schema.json ← для Review decide
├── standards/                    ← СТО 1С, БСП, корпоративные (Markdown)
│   ├── sto-1c/
│   ├── bsp/
│   └── corporate/
├── patterns/                     ← YAML-эталоны (положительные примеры)
│   ├── transaction-wrapper.yaml
│   ├── posting-handler.yaml
│   ├── session-cache.yaml
│   ├── bsp-value-retrieval.yaml
│   └── deferred-modal.yaml
├── antipatterns/                 ← YAML с detect-паттернами
│   ├── query-in-loop.yaml
│   ├── point-access-in-loop.yaml
│   ├── hardcoded-predefined.yaml
│   ├── modal-call-in-client.yaml
│   ├── try-catch-silent.yaml
│   ├── transaction-without-try.yaml
│   ├── select-star.yaml
│   ├── function-in-where.yaml
│   └── commit-in-loop.yaml
├── prompts/                      ← Jinja2 системные промпты
│   ├── planner.system.j2
│   ├── gatherer.system.j2
│   ├── coder.system.j2
│   ├── reviewer.system.j2
│   └── validator.system.j2
└── examples/                     ← .bsl файлы good/bad
    ├── query-in-loop/
    │   ├── bad.bsl
    │   └── good.bsl
    └── ...
```

## 3. JSON Schema для антипаттерна

```json
// knowledge-base/schemas/antipattern.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Antipattern",
  "description": "Антипаттерн 1С-разработки с детект-правилами",
  "type": "object",
  "required": [
    "id", "title", "category", "severity", "applicable_to",
    "detect", "example_bad", "example_good",
    "recommendation_for_llm", "recommendation_for_reviewer"
  ],
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9-]*$",
      "description": "Уникальный id (kebab-case)"
    },
    "title": {
      "type": "string",
      "minLength": 5,
      "maxLength": 100
    },
    "category": {
      "type": "string",
      "enum": [
        "queries", "transactions", "client_server", "style",
        "architecture", "security", "performance", "metadata"
      ]
    },
    "severity": {
      "type": "string",
      "enum": ["critical", "warning", "info"]
    },
    "applicable_to": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "module_object", "module_form", "module_manager",
          "module_common", "module_command"
        ]
      },
      "minItems": 1
    },
    "platform_versions": {
      "type": "object",
      "properties": {
        "since": {"type": "string", "description": "8.3.10"},
        "until": {"type": "string"}
      }
    },
    "detect": {
      "type": "object",
      "description": "Как детектить антипаттерн",
      "oneOf": [
        {"required": ["regex"]},
        {"required": ["ast_pattern"]},
        {"required": ["bsl_ls_rule"]}
      ],
      "properties": {
        "regex": {
          "type": "object",
          "required": ["pattern"],
          "properties": {
            "pattern": {"type": "string"},
            "flags": {"type": "string", "default": "m"},
            "context_lines": {"type": "integer", "minimum": 0, "default": 2}
          }
        },
        "ast_pattern": {
          "type": "object",
          "description": "tree-sitter AST query (требует [ast] extras)",
          "required": ["query"],
          "properties": {
            "query": {"type": "string"},
            "language": {"type": "string", "default": "bsl"}
          }
        },
        "bsl_ls_rule": {
          "type": "object",
          "description": "Ссылка на правило BSL Language Server",
          "required": ["code"],
          "properties": {
            "code": {"type": "string", "description": "BSL-WS-001"},
            "severity_override": {
              "type": "string",
              "enum": ["critical", "warning", "info"]
            }
          }
        }
      }
    },
    "example_bad": {
      "type": "string",
      "description": "BSL-код с антипаттерном",
      "minLength": 10
    },
    "example_good": {
      "type": "string",
      "description": "Исправленный BSL-код",
      "minLength": 10
    },
    "recommendation_for_llm": {
      "type": "string",
      "description": "Что сказать Coder'у в retry-промпте",
      "minLength": 20
    },
    "recommendation_for_reviewer": {
      "type": "string",
      "description": "Что учесть Reviewer'у при анализе"
    },
    "tags": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

## 4. Пример антипаттерна

```yaml
# knowledge-base/antipatterns/query-in-loop.yaml
id: query-in-loop
title: "Запрос в цикле"
category: queries
severity: critical
applicable_to:
  - module_object
  - module_form
  - module_manager
  - module_common
platform_versions:
  since: "8.0.0"

detect:
  regex:
    pattern: |
      Для\s+Каждого\s+\w+\s+Из\s+\w+\s+Цикл
      .*?
      Запрос\s*=\s*Новый\s+Запрос
    flags: ms
    context_lines: 3
  # Альтернативно — AST:
  # ast_pattern:
  #   query: "(foreach_statement body: (method_call name: 'Выполнить'))"

example_bad: |
  Для Каждого СтрокаТаблицы Из ТаблицаТоваров Цикл
      Запрос = Новый Запрос;
      Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары ГДЕ Код = &Код";
      Запрос.УстановитьПараметр("Код", СтрокаТаблицы.Код);
      Результат = Запрос.Выполнить();
  КонецЦикла;

example_good: |
  Коды = Новый Массив;
  Для Каждого СтрокаТаблицы Из ТаблицаТоваров Цикл
      Коды.Добавить(СтрокаТаблицы.Код);
  КонецЦикла;
  
  Запрос = Новый Запрос;
  Запрос.Текст = "ВЫБРАТЬ Код, Наименование FROM Справочник.Товары ГДЕ Код В (&Коды)";
  Запрос.УстановитьПараметр("Коды", Коды);
  Результат = Запрос.Выполнить();

recommendation_for_llm: |
  Запросы в цикле — критический антипаттерн производительности.
  Замените на:
  1. Соберите все ключи в массив внутри цикла.
  2. После цикла выполните ОДИН запрос с условием `ГДЕ Поле В (&Массив)`.
  3. Результат разверните по ключам через Соответствие.

recommendation_for_reviewer: |
  Проверьте, что для каждой циклической конструкции с запросом
  есть обоснование (комментарий) ИЛИ замена на batch-запрос.
  Если ни того, ни другого — critical finding.

tags:
  - performance
  - queries
  - n+1
```

## 5. JSON Schema для паттерна

```json
// knowledge-base/schemas/pattern.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Pattern",
  "description": "Эталонный паттерн 1С-разработки",
  "type": "object",
  "required": [
    "id", "title", "when_to_use", "code_template", "variables",
    "example_good", "applicable_to"
  ],
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9-]*$"
    },
    "title": {"type": "string", "minLength": 5, "maxLength": 100},
    "category": {
      "type": "string",
      "enum": [
        "transaction", "form", "query", "integration",
        "caching", "validation", "posting", "report"
      ]
    },
    "when_to_use": {
      "type": "string",
      "minLength": 20,
      "description": "Когда применять паттерн"
    },
    "when_not_to_use": {
      "type": "string",
      "description": "Когда НЕ применять (анти-кейсы)"
    },
    "applicable_to": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "module_object", "module_form", "module_manager",
          "module_common", "module_command"
        ]
      }
    },
    "code_template": {
      "type": "string",
      "description": "Шаблон с {{variables}}"
    },
    "variables": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "description", "type"],
        "properties": {
          "name": {"type": "string"},
          "description": {"type": "string"},
          "type": {"type": "string", "description": "Catalog | Document | ..."},
          "required": {"type": "boolean", "default": true}
        }
      }
    },
    "example_good": {"type": "string", "minLength": 10},
    "depends_on_patterns": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Другие паттерны, которые этот использует"
    },
    "avoids_antipatterns": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Антипаттерны, которые этот паттерн предотвращает"
    },
    "tags": {"type": "array", "items": {"type": "string"}}
  }
}
```

## 6. Пример паттерна

```yaml
# knowledge-base/patterns/posting-handler.yaml
id: posting-handler
title: "Обработчик проведения документа"
category: posting
when_to_use: |
  Используйте этот паттерн при реализации ОбработкаПроведения
  для документов, которые делают движения по регистрам.
  Паттерн обеспечивает:
  - транзакционную целостность (НачатьТранзакцию / ЗафиксироватьТранзакцию)
  - обработку ошибок (Исключение / ОтменитьТранзакцию)
  - запись в журнал регистрации при сбое
  - явное управление блокировками
when_not_to_use: |
  Не используйте, если документ не делает движения по регистрам
  (только расчёт или печать). В этом случае транзакция не нужна.

applicable_to:
  - module_object

code_template: |
  Процедура ОбработкаПроведения(Отказ, ДанныеДляЗаписи)
      // {{document_name}}.ОбработкаПроведения
      
      НачатьТранзакцию();
      Попытка
          // Подготовка данных
          {{preparation_code}}
          
          // Запись движений
          {{movement_code}}
          
          ЗафиксироватьТранзакцию();
      Исключение
          ОтменитьТранзакцию();
          ЗаписьЖурналаРегистрации(
              "Проведение.{{document_name}}",
              УровеньЖурналаРегистрации.Ошибка,
              ,
              ,
              ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())
          );
          Отказ = Истина;
          ВызватьИсключение;
      КонецПопытки;
  КонецПроцедуры

variables:
  - name: document_name
    description: Имя документа (например, "РеализацияТоваровУслуг")
    type: Document
    required: true
  - name: preparation_code
    description: Код подготовки данных для движений
    type: code
    required: true
  - name: movement_code
    description: Код записи в регистры
    type: code
    required: true

example_good: |
  Процедура ОбработкаПроведения(Отказ, ДанныеДляЗаписи)
      // РеализацияТоваровУслуг.ОбработкаПроведения
      
      НачатьТранзакцию();
      Попытка
          // Подготовка данных
          НаборЗаписей = РегистрыНакопления.Продажи.СоздатьНаборЗаписей();
          НаборЗаписей.Отбор.Регистратор.Установить(Ссылка);
          
          // Запись движений
          Для Каждого СтрокаТовары Из Товары Цикл
              Движение = НаборЗаписей.Добавить();
              Движение.Период = Дата;
              Движение.Номенклатура = СтрокаТовары.Номенклатура;
              Движение.Количество = СтрокаТовары.Количество;
              Движение.Сумма = СтрокаТовары.Сумма;
          КонецЦикла;
          
          НаборЗаписей.Записать();
          ЗафиксироватьТранзакцию();
      Исключение
          ОтменитьТранзакцию();
          ЗаписьЖурналаРегистрации(
              "Проведение.РеализацияТоваровУслуг",
              УровеньЖурналаРегистрации.Ошибка,
              ,
              ,
              ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())
          );
          Отказ = Истина;
          ВызватьИсключение;
      КонецПопытки;
  КонецПроцедуры

depends_on_patterns:
  - transaction-wrapper

avoids_antipatterns:
  - try-catch-silent
  - transaction-without-try

tags:
  - posting
  - transaction
  - documents
```

## 7. JSON Schemas для structured outputs

### 7.1. Subtask schema (для Plan decompose)

```json
// knowledge-base/schemas/subtask.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Subtask",
  "type": "object",
  "required": ["id", "name", "target_module", "description", "acceptance_criteria"],
  "properties": {
    "id": {"type": "string", "format": "uuid"},
    "name": {"type": "string", "minLength": 3, "maxLength": 100},
    "target_module": {
      "type": "string",
      "pattern": "^(Catalog|Document|CommonModule|InformationRegister|DataProcessor|Report)\\.[A-Za-zА-Яа-я0-9]+(\\.(ObjectModule|ManagerModule|FormModule|CommonModule))?$"
    },
    "description": {"type": "string", "minLength": 20},
    "inputs": {"type": "array", "items": {"type": "string"}},
    "outputs": {"type": "array", "items": {"type": "string"}},
    "acceptance_criteria": {
      "type": "array",
      "minItems": 1,
      "items": {"type": "string", "minLength": 10}
    },
    "constraints": {
      "type": "object",
      "properties": {
        "dont_list": {"type": "array", "items": {"type": "string"}},
        "must_list": {"type": "array", "items": {"type": "string"}},
        "available_modules": {"type": "array", "items": {"type": "string"}},
        "target_context": {"type": "string", "enum": ["server", "thin_client", "mobile_client"]}
      }
    },
    "max_iterations": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3}
  }
}
```

### 7.2. Code output schema (для Coder)

```json
// knowledge-base/schemas/code-output.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CodeOutput",
  "type": "object",
  "required": ["code", "explanation"],
  "properties": {
    "code": {"type": "string", "minLength": 10},
    "explanation": {
      "type": "string",
      "minLength": 20,
      "description": "Почему именно такой код (для трассировки)"
    },
    "regions_used": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Какие #Области использованы"
    },
    "patterns_applied": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ID паттернов из KB, которые применили"
    },
    "antipatterns_avoided": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ID антипаттернов, которые осознанно избежали"
    }
  }
}
```

### 7.3. Review output schema (для Review decide)

```json
// knowledge-base/schemas/review-output.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ReviewOutput",
  "required": ["decision", "findings", "rationale"],
  "properties": {
    "decision": {"type": "string", "enum": ["proceed", "retry", "escalate"]},
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "category", "message", "recommendation"],
        "properties": {
          "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
          "category": {
            "type": "string",
            "enum": ["antipattern", "context_violation", "pattern_mismatch", "style"]
          },
          "code": {"type": "string", "description": "query-in-loop | CTX001 | ..."},
          "message": {"type": "string"},
          "line": {"type": "integer", "minimum": 1},
          "recommendation": {"type": "string"}
        }
      }
    },
    "rationale": {"type": "string", "minLength": 20}
  }
}
```

## 8. Jinja2 системные промпты

### 8.1. Coder system prompt

```jinja2
{# knowledge-base/prompts/coder.system.j2 #}
Ты — Senior 1C-разработчик с 10+ годами опыта.

## Твоя задача
Сгенерировать BSL-код для подзадачи '{{ subtask.name }}' в модуле {{ subtask.target_module }}.

## Описание подзадачи
{{ subtask.description }}

## Критерии приёмки
{% for criteria in subtask.acceptance_criteria %}
- {{ criteria }}
{% endfor %}

## Собранный контекст
{{ gather_result.context_summary }}

## Применённый паттерн
{% if applied_pattern %}
{{ applied_pattern.code_template }}
{% else %}
Паттерн не выбран — действуй по стандартам 1С.
{% endif %}

## Ограничения
{% for dont in subtask.constraints.dont_list %}
- НЕ {{ dont }}
{% endfor %}

{% for must in subtask.constraints.must_list %}
- ОБЯЗАТЕЛЬНО {{ must }}
{% endfor %}

## Доступные модули
{% for module in subtask.constraints.available_modules %}
- {{ module }}
{% endfor %}

{% if prev_iteration %}
## Предыдущая попытка (не прошла валидацию)
### Код
```
{{ prev_iteration.code }}
```

### Конкретные ошибки (исправь ТОЛЬКО их, остальное не трогай)
{% for check in prev_iteration.failed_checks %}
- [{{ check.severity }}] {{ check.code }} (строка {{ check.line }}): {{ check.message }}
  Подсказка: {{ check.fix_hint }}
{% endfor %}
{% endif %}

{% if constraints_reminder %}
## НАПОМИНАНИЕ
{{ constraints_reminder }}
{% endif %}

## Требования к выводу
Верни JSON с полями:
- `code` — BSL-код (с табами, без `ё`, без EM DASH)
- `explanation` — краткое обоснование решений
- `patterns_applied` — ID паттернов, которые применил
- `antipatterns_avoided` — ID антипаттернов, которые осознанно избежал

Не пиши ничего кроме JSON.
```

### 8.2. Reviewer system prompt

```jinja2
{# knowledge-base/prompts/reviewer.system.j2 #}
Ты — Tech Lead 1С-разработки. Тебе на ревью — код от Junior.

## Контекст
- Подзадача: {{ subtask.name }} ({{ subtask.target_module }})
- Итерация: {{ iteration_number }}

## Код на ревью
```
{{ code }}
```

## Результаты валидации (детерминированной)
{% for finding in validate_result.findings %}
- [{{ finding.severity }}] {{ finding.code }}: {{ finding.message }}
{% endfor %}

## Релевантные антипаттерны (для справки)
{% for ap in relevant_antipatterns %}
- `{{ ap.id }}` ({{ ap.severity }}): {{ ap.title }}
  {{ ap.recommendation_for_reviewer }}
{% endfor %}

## Похожие модули в кодовой базе (для сравнения)
{% for similar in similar_modules %}
- {{ similar.object_ref }} (score: {{ similar.score }})
{% endfor %}

## Твоя задача
Реши: код можно коммитить, нужна доработка, или эскалация к человеку?

Критерии:
- `proceed` — нет critical findings, code следует паттернам
- `retry` — есть findings, но они исправимы (warning/info + <3 critical)
- `escalate` — 3+ critical findings, или паттерн грубо нарушен

Верни JSON с полями:
- `decision`: "proceed" | "retry" | "escalate"
- `findings`: список с severity, category, message, recommendation
- `rationale`: почему такое решение
```

## 9. `index.json` — реестр

```json
// knowledge-base/index.json
{
  "version": "1.0.0",
  "generated_at": "2026-07-11T10:00:00Z",
  "patterns": [
    {
      "id": "posting-handler",
      "title": "Обработчик проведения документа",
      "category": "posting",
      "file": "patterns/posting-handler.yaml"
    },
    {
      "id": "transaction-wrapper",
      "title": "Транзакционный wrapper",
      "category": "transaction",
      "file": "patterns/transaction-wrapper.yaml"
    }
  ],
  "antipatterns": [
    {
      "id": "query-in-loop",
      "title": "Запрос в цикле",
      "category": "queries",
      "severity": "critical",
      "file": "antipatterns/query-in-loop.yaml"
    },
    {
      "id": "try-catch-silent",
      "title": "Молчаливый catch",
      "category": "transactions",
      "severity": "critical",
      "file": "antipatterns/try-catch-silent.yaml"
    }
  ],
  "prompts": [
    {"role": "PLANNER", "file": "prompts/planner.system.j2"},
    {"role": "GATHERER", "file": "prompts/gatherer.system.j2"},
    {"role": "CODER", "file": "prompts/coder.system.j2"},
    {"role": "VALIDATOR", "file": "prompts/validator.system.j2"},
    {"role": "REVIEWER", "file": "prompts/reviewer.system.j2"}
  ]
}
```

## 10. Загрузка и валидация

```python
# packages/mcp_servers/src/mcp_servers/kb/loader.py
"""Загрузка KB из YAML + валидация по JSON Schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import yaml
from jsonschema import validate, ValidationError


class KBCollection:
    """Коллекция загруженных паттернов и антипаттернов."""

    def __init__(self, kb_dir: Path) -> None:
        self.kb_dir = kb_dir
        self.patterns: dict[str, dict[str, Any]] = {}
        self.antipatterns: dict[str, dict[str, Any]] = {}
        self._schemas = self._load_schemas()
        self._load_all()

    def _load_schemas(self) -> dict[str, dict]:
        return {
            "pattern": json.loads((self.kb_dir / "schemas/pattern.schema.json").read_text()),
            "antipattern": json.loads((self.kb_dir / "schemas/antipattern.schema.json").read_text()),
        }

    def _load_all(self) -> None:
        for yaml_path in (self.kb_dir / "patterns").glob("*.yaml"):
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            validate(instance=data, schema=self._schemas["pattern"])
            self.patterns[data["id"]] = data

        for yaml_path in (self.kb_dir / "antipatterns").glob("*.yaml"):
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            validate(instance=data, schema=self._schemas["antipattern"])
            self.antipatterns[data["id"]] = data

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        return self.patterns.get(pattern_id)

    def get_antipattern(self, antipattern_id: str) -> dict[str, Any] | None:
        return self.antipatterns.get(antipattern_id)

    def detect_antipatterns(self, code: str) -> list[dict[str, Any]]:
        """Прогнать код по всем anti-patterns с regex-detect."""
        import re
        findings: list[dict[str, Any]] = []
        for ap_id, ap in self.antipatterns.items():
            detect = ap.get("detect", {})
            if "regex" in detect:
                pattern = detect["regex"]["pattern"]
                flags_str = detect["regex"].get("flags", "m")
                flags = 0
                if "m" in flags_str: flags |= re.MULTILINE
                if "s" in flags_str: flags |= re.DOTALL
                if "i" in flags_str: flags |= re.IGNORECASE
                for match in re.finditer(pattern, code, flags):
                    findings.append({
                        "antipattern_id": ap_id,
                        "severity": ap["severity"],
                        "line": code[:match.start()].count("\n") + 1,
                        "message": ap["title"],
                        "match": match.group(0),
                    })
            # ast_pattern и bsl_ls_rule — обрабатываются отдельно
        return findings
```

## 11. CI-проверка KB

```python
# tests/kb/test_kb_valid.py
"""CI-проверка: все YAML в KB валидны по JSON Schema."""
import pytest
from pathlib import Path
from mcp_servers.kb.loader import KBCollection


class TestKBValidity:
    def test_all_patterns_valid(self):
        kb = KBCollection(Path("knowledge-base"))
        assert len(kb.patterns) >= 5, "Should have at least 5 patterns"

    def test_all_antipatterns_valid(self):
        kb = KBCollection(Path("knowledge-base"))
        assert len(kb.antipatterns) >= 10, "Should have at least 10 antipatterns"

    def test_no_duplicate_ids(self):
        kb = KBCollection(Path("knowledge-base"))
        # Если бы были дубликаты, _load_all бы перезаписал — проверяем через файлы
        pattern_files = list(Path("knowledge-base/patterns").glob("*.yaml"))
        pattern_ids = []
        for f in pattern_files:
            import yaml
            data = yaml.safe_load(f.read_text())
            pattern_ids.append(data["id"])
        assert len(pattern_ids) == len(set(pattern_ids)), "Duplicate pattern IDs"

    def test_detect_works(self):
        """Хотя бы один антипаттерн детектится в примере bad."""
        kb = KBCollection(Path("knowledge-base"))
        bad_code = """
        Для Каждого СтрокаТовары Из Товары Цикл
            Запрос = Новый Запрос;
            Запрос.Текст = "ВЫБРАТЬ *";
        КонецЦикла;
        """
        findings = kb.detect_antipatterns(bad_code)
        assert any(f["antipattern_id"] == "query-in-loop" for f in findings)

    def test_recommendation_for_llm_present(self):
        """Каждый антипаттерн имеет recommendation_for_llm — для retry-промпта."""
        kb = KBCollection(Path("knowledge-base"))
        for ap_id, ap in kb.antipatterns.items():
            assert "recommendation_for_llm" in ap, f"{ap_id} missing recommendation_for_llm"
            assert len(ap["recommendation_for_llm"]) >= 20
```

## 12. Взаимосвязь с другими шагами

| Шаг | Связь |
|---|---|
| Шаг 4 (Pipeline contracts) | `ValidationFinding`, `ReviewFinding` используют `severity` и `category` из KB-схем |
| Шаг 5 (MCP tool contracts) | `kb.get_pattern`, `kb.get_antipattern`, `kb.check_antipatterns` парсят YAML |
| Шаг 6 (TOOL_GROUPS) | VALIDATOR и REVIEWER вызывают KB tools — роли зафиксированы |
| Шаг 8 (Facade) | `explain` tool может вернуть KB-описание (для пользователя) |

---

**Шаг 7 завершён.** Следующий — Шаг 8: Agent-Facade lifecycle tools — 7 tools (`plan`, `gather`, `generate`, `validate`, `review`, `explain`, `run_cli`) + `data_status`, которые видит внешний клиент (Cursor).
