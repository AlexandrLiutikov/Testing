# Release Decision Engine v1

Движок принятия решений о релизе Editors.

---

## 1. Назначение

Decision Engine — центральный компонент системы. Он превращает **сигналы** (результаты проверок) в **решение** (можно ли релизить).

Без Decision Engine тесты — это просто список PASS/FAIL.
С Decision Engine тесты — это **основа для управленческого решения**.

---

## 2. Вход (Input)

Decision Engine получает на вход:

### 2.1. Результаты текущего прогона
```yaml
test_results:
  - case_id: 1
    case_name: "Запуск редактора"
    status: PASS
    module: StartScreen
    critical_path: true
  - case_id: 2
    case_name: "Главное окно редактора"
    status: PASS
    module: StartScreen
    critical_path: true
  - case_id: 3
    case_name: "Создание документа"
    status: FAIL
    module: Editor
    critical_path: true
    failure_type: TEST_FAIL
    failure_severity: MEDIUM
    failure_area: UI_LAYOUT
    failure_detail: "Иконка вкладки смещена на 3px"
  - case_id: 4
    case_name: "Сохранение документа"
    status: FAIL
    module: Editor
    critical_path: true
    failure_type: INFRA_FAIL
    failure_area: INFRASTRUCTURE
    failure_detail: "Tesseract OCR timeout при проверке диалога"
  - case_id: 5
    case_name: "Печать документа"
    status: BLOCKED
    module: Editor
    critical_path: true
    blocked_reason: "Принтер не настроен на стенде"
```

### 2.2. Модель рисков
Из файла модели рисков продукта (`products/<Продукт>/RISK_MODEL.md`, например `products/Editors/RISK_MODEL.md`) — модули, критические пути, допуски.

### 2.3. История (опционально, v2+)
Результаты предыдущих прогонов той же сборки или предыдущих сборок.
Позволяет выявлять тренды: «этот тест стал падать с версии X».

### 2.4. Контекст платформы
```yaml
platform: Windows 11
build: R7-Office-2024.1.234
date: 2026-04-04
```

---

## 3. Выход (Output)

### 3.1. Решение

```yaml
RELEASE_DECISION: GO | GO_WITH_RISK | NO_GO
```

### 3.2. Полный блок решения

```yaml
release_decision:
  verdict: GO_WITH_RISK
  
  reasons:
    - "TEST_FAIL: шаг «Проверка вкладки Вставка» (severity MEDIUM)."
    - "Run confidence: SUFFICIENT. 2 из 12 шагов имеют статус INFRA_FAIL/BLOCKED."

  risks:
    - "MEDIUM / UI_LAYOUT: Смещение иконки вкладки «Вставка» на 3px"

  infra_issues:
    - "Шаг «Проверка диалога сохранения»: Tesseract timeout"

  blocked_cases:
    - "Шаг «Печать»: стенд без настроенного принтера"

  warnings:
    - "LOW: Обнаружен новый UI-элемент во вкладке «Вставка» (шаг 4)"

  recommendations:
    - "Разрешить релиз с учётом выявленных рисков."
    - "Повторить прогон после устранения инфраструктурных ограничений."
    - "Обновить UI-каталог/автотесты по зафиксированным предупреждениям."

  run_confidence: SUFFICIENT
  run_confidence_detail: "2 из 12 шагов имеют статус INFRA_FAIL/BLOCKED; critical coverage: 10/10."

  stats:
    total: 12
    passed: 9
    test_failed: 1
    infra_failed: 1
    blocked: 1
    warnings_total: 4
    critical_path_coverage: "10/10"
```

---

## 4. Логика принятия решения

### 4.1. Алгоритм

```
# --- Шаг 0: оценка достоверности прогона ---
РАССЧИТАТЬ run_confidence по правилам раздела 9
ЕСЛИ run_confidence = INSUFFICIENT
  → решение НЕ МОЖЕТ быть GO
  → рекомендация: повторный прогон после устранения проблем

# --- Шаг 1: отделить типы сбоев ---
# Для принятия решения учитываются ТОЛЬКО TEST_FAIL.
# INFRA_FAIL и BLOCKED не являются продуктовыми сигналами.
# warnings/fallback не являются FAIL-сигналом, но обязаны быть вынесены в отчёт.

# --- Шаг 2: продуктовое решение (по TEST_FAIL) ---
ЕСЛИ есть хотя бы один TEST_FAIL с severity CRITICAL или HIGH
  И он на critical_path
  → NO_GO

ЕСЛИ есть TEST_FAIL с severity CRITICAL или HIGH
  НО он НЕ на critical_path
  → GO_WITH_RISK (объяснить, почему критический сбой вне критического пути допустим)

ЕСЛИ есть TEST_FAIL только с severity MEDIUM
  → GO_WITH_RISK (перечислить риски и рекомендации)

ЕСЛИ есть TEST_FAIL только с severity LOW
  → GO (с пометкой о известных отклонениях)

ЕСЛИ все PASS (нет TEST_FAIL)
  → GO

# --- Шаг 3: корректировка по покрытию ---
ЕСЛИ не все critical_paths покрыты (из-за BLOCKED или INFRA_FAIL)
  → повысить до GO_WITH_RISK (указать непокрытые пути как риск)

# --- Шаг 4: итоговый вердикт ---
ИТОГОВЫЙ ВЕРДИКТ = max(продуктовое решение, корректировка по покрытию, ограничение по run_confidence)
```

### 4.2. Таблица решений (компактная)

| Worst FAIL severity | На critical path? | Решение |
|---|---|---|
| CRITICAL | Да | **NO_GO** |
| CRITICAL | Нет | **GO_WITH_RISK** |
| HIGH | Да | **NO_GO** |
| HIGH | Нет | **GO_WITH_RISK** |
| MEDIUM | Любой | **GO_WITH_RISK** |
| LOW | Любой | **GO** |
| Нет FAIL | — | **GO** |

### 4.3. Дополнительные правила

- **Непокрытый critical path** = автоматически `GO_WITH_RISK` (даже если все тесты PASS).
- **Множественные MEDIUM** — если более 3 MEDIUM-сбоев (`TEST_FAIL`) в одном модуле, повысить до `NO_GO` (паттерн указывает на системную проблему).
- **Platform-specific FAIL** — если сбой только на одной ОС, а на остальных PASS, это `GO_WITH_RISK` для конкретной платформы.
- **BLOCKED на critical path** — если BLOCKED кейс — единственный, покрывающий critical path, это `GO_WITH_RISK` с пометкой «путь не проверен» (см. раздел 7).
- **INFRA_FAIL** — не учитывается как продуктовый сбой. Снижает `run_confidence`. При множественных `INFRA_FAIL` рекомендуется повторный прогон (см. раздел 8).
- **INFRA_FAIL ≠ NO_GO** — инфраструктурный сбой **никогда** не приводит к продуктовому `NO_GO`. Вместо этого прогон маркируется как недостоверный.
- **Warnings/Fallback** — не меняют вердикт напрямую, но обязаны отражаться в `release_decision.warnings` и в отчёте на уровне шагов.

---

## 5. Формат в отчёте

Блок решения размещается:
- В `results.json` — поле `release_decision` (полный YAML/JSON-блок)
- В `report.html` — визуальный блок между мета-блоком и таблицей шагов
- В `report.md` — секция `## Решение о релизе`

### Визуальные стили для HTML

Стили классов `.decision`, `.decision-badge`, `.decision-section`, `.decision-stats` и `.severity` определены в общем файле стилей `report.css` (корень проекта).
При генерации отчёта `report.css` копируется в каталог прогона — см. `REPORT_STYLE_RULES.md`.

---

## 6. Мультиплатформенный прогон

При запуске по нескольким ОС решение формируется **для каждой платформы отдельно** и **сводное**:

```yaml
platform_decisions:
  - platform: Windows 11
    verdict: GO
  - platform: Astra Linux
    verdict: GO_WITH_RISK
    risks: ["Смещение UI на панели инструментов"]
  - platform: macOS 14
    verdict: GO

overall_verdict: GO_WITH_RISK
overall_reason: "Astra Linux: GO_WITH_RISK (UI-смещение). Остальные платформы: GO."
```

Сводное решение = **наихудшее** из платформенных.

---

## 7. Обработка BLOCKED-кейсов

### 7.1 Определение

`BLOCKED` — кейс, который невозможно исполнить по внешней причине: редактор не установлен, лицензия истекла, тестовый файл отсутствует, предыдущий кейс цепочки не прошёл.

BLOCKED — **не** является сигналом о качестве продукта. Он означает, что **сигнал не был получен**.

### 7.2 Влияние на решение

```
ЕСЛИ BLOCKED-кейс находится на critical_path
  И нет других кейсов, покрывающих тот же critical_path
  → покрытие критического пути снижено
  → GO_WITH_RISK (с указанием «недостаточное покрытие: <путь> не проверен»)

ЕСЛИ BLOCKED-кейс НЕ на critical_path
  → решение принимается по остальным кейсам
  → BLOCKED фиксируется в секции рисков как «непроверенная область»

ЕСЛИ количество BLOCKED > 30% от общего числа кейсов
  → прогон считается недостоверным (см. раздел 9)
  → решение о релизе не может быть принято
```

### 7.3 Формат в результатах

```yaml
blocked_cases:
  - case_id: 5
    case_name: "Печать документа"
    blocked_reason: "Принтер не настроен на стенде"
    critical_path: true
    impact: "Критический путь 'печать' не покрыт"
```

---

## 8. Обработка INFRA_FAIL

### 8.1 Определение

`INFRA_FAIL` — сбой среды выполнения, инструмента или драйвера, не связанный с качеством продукта: Tesseract не установлен, UIA timeout без видимой причины, скриншот не сохранился, нет доступа к тестовому файлу.

INFRA_FAIL **не является** продуктовым сигналом. Он означает, что **инструмент тестирования не смог выполнить проверку**.

### 8.2 Влияние на решение

```
ЕСЛИ есть INFRA_FAIL на critical_path
  И нет успешного повторного прогона того же кейса
  → прогон по данному кейсу недостоверен
  → GO_WITH_RISK (с указанием «кейс <N> не дал достоверного результата из-за INFRA_FAIL»)

ЕСЛИ INFRA_FAIL только на некритических кейсах
  → решение принимается по остальным кейсам
  → INFRA_FAIL фиксируется как «снижение покрытия»

ЕСЛИ количество INFRA_FAIL > 20% от общего числа шагов
  → прогон считается недостоверным (см. раздел 9)
  → рекомендация: повторный прогон после устранения инфраструктурных проблем
```

### 8.3 Обязательные действия

- При `INFRA_FAIL` на critical_path **рекомендуется** повторный прогон кейса.
- `INFRA_FAIL` **никогда** не приводит к продуктовому `NO_GO`. Вместо этого прогон маркируется как недостоверный.
- В секции `release_decision` инфраструктурные сбои выносятся в отдельный блок `infra_issues`, а не в `blocking_failures`.

### 8.4 Формат в результатах

```yaml
infra_issues:
  - case_id: 3
    step_id: "case3_step2"
    step_name: "Проверка текста через OCR"
    infra_reason: "Tesseract не установлен на стенде"
    recommendation: "Установить Tesseract и повторить прогон"
```

---

## 9. Достоверность прогона (Run Confidence)

### 9.1 Определение

Достоверность прогона — оценка того, можно ли на основании результатов прогона принимать решение о релизе.

Прогон считается **достоверным**, если:
- все critical paths покрыты хотя бы одним шагом со статусом `PASS` или `TEST_FAIL`;
- доля `BLOCKED` + `INFRA_FAIL` не превышает пороговых значений;
- инфраструктура работала штатно.

### 9.2 Уровни достоверности

| Уровень | Условие | Можно ли принимать решение? |
|---------|---------|----------------------------|
| **FULL** | Все шаги выполнены (`PASS` или `TEST_FAIL`), нет `BLOCKED` и `INFRA_FAIL` | Да, решение полностью обосновано |
| **SUFFICIENT** | `BLOCKED` + `INFRA_FAIL` ≤ 20% шагов, все critical paths покрыты | Да, с оговоркой о непроверенных областях |
| **DEGRADED** | `BLOCKED` + `INFRA_FAIL` > 20% но ≤ 50%, или 1 critical path не покрыт | `GO_WITH_RISK` — решение возможно, но прогон неполный |
| **INSUFFICIENT** | `BLOCKED` + `INFRA_FAIL` > 50%, или ≥ 2 critical paths не покрыты | Решение **не может быть принято**. Требуется повторный прогон |

### 9.3 Формат в блоке решения

```yaml
release_decision:
  verdict: GO_WITH_RISK
  run_confidence: SUFFICIENT
  run_confidence_detail: "2 из 10 шагов имеют статус INFRA_FAIL/BLOCKED. Все critical paths покрыты."

  reasons:
    - "Все критические пути пройдены"
  
  infra_issues:
    - "Шаг 5 BLOCKED: принтер не настроен"
    - "Шаг 8 INFRA_FAIL: Tesseract timeout"

  stats:
    total: 10
    passed: 7
    test_failed: 1
    infra_failed: 1
    blocked: 1
    warnings_total: 2
    critical_path_coverage: "5/5 (100%)"
```

### 9.4 Обязательные правила

- Блок `run_confidence` **обязателен** в каждом `release_decision`.
- При `run_confidence: INSUFFICIENT` вердикт **не может** быть `GO`. Допускается только `GO_WITH_RISK` (с явным указанием на недостоверность) или рекомендация повторного прогона.
- `INFRA_FAIL` и `BLOCKED` **обязательно** отображаются в отдельных секциях отчёта, а не смешиваются с продуктовыми `TEST_FAIL`.

---

## 10. Эволюция (v2+)

Планируемые расширения:
- **Учёт истории**: тренды сбоев, регрессии, flaky-тесты
- **Confidence score**: вместо бинарного GO/NO_GO — числовая оценка уверенности (0.0–1.0)
- **Auto-triage**: автоматическая классификация сбоев по паттернам из истории
- **Сравнение сборок**: diff между текущей и предыдущей стабильной сборкой
