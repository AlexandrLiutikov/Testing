# Инструкции по запуску автотестов R7 Office

---

## 1. Подготовка стенда (выполняется один раз)

### 1.1 Системные требования

- Python 3.8+
- Tesseract OCR (установлен как системный пакет)
- R7 Office Desktop Editors (установлен на стенде)

### 1.2 Создание виртуального окружения

Из корня проекта (`D:\Projects\Testing`):

```bash
python setup_env.py
```

Скрипт автоматически:
1. Создаёт `.venv` (если не существует).
2. Определяет текущую ОС.
3. Устанавливает общие и платформо-специфичные зависимости.

---

## 2. Запуск тестов

### 2.1 Активация окружения

Все скрипты запускаются через Python из виртуального окружения:

```bash
# Windows:
.venv\Scripts\python <скрипт>

# Linux / macOS:
.venv/bin/python <скрипт>
```

### 2.2 Запуск отдельного кейса

```bash
# Кейс 1: Запуск редактора
.venv\Scripts\python products\Editors\scenarios\smoke\1_Запуск_редактора.py

# Кейс 2: Главное окно редактора (требует выполненного кейса 1)
.venv\Scripts\python products\Editors\scenarios\smoke\2_Главное_окно_редактора.py
```

Параметры:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `--editor-path` | Путь к исполняемому файлу редактора | `C:\Program Files\R7-Office\Editors\DesktopEditors.exe` |
| `--output-dir` | Каталог для артефактов | каталог продукта (`products/Editors`) |

Пример:

```bash
.venv\Scripts\python products\Editors\scenarios\smoke\1_Запуск_редактора.py --editor-path "D:\R7\DesktopEditors.exe"
```

### 2.3 Запуск цепочки кейсов (run_all.py)

Оркестратор запускает кейсы последовательно, передавая состояние между ними (редактор остаётся открытым между кейсами).

```bash
# Все доступные кейсы:
.venv\Scripts\python products\Editors\run_all.py

# Только указанные кейсы:
.venv\Scripts\python products\Editors\run_all.py --cases 1 2

# С указанием пути к редактору:
.venv\Scripts\python products\Editors\run_all.py --editor-path "D:\R7\DesktopEditors.exe"
```

Параметры run_all.py:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `--cases` | Номера кейсов через пробел | все доступные (`1 2`) |
| `--editor-path` | Путь к исполняемому файлу редактора | `C:\Program Files\R7-Office\Editors\DesktopEditors.exe` |
| `--output-dir` | Корневой каталог для артефактов | `products/Editors` |

---

## 3. Артефакты

### 3.1 Отдельный кейс

Артефакты сохраняются в:

```
products/Editors/artifacts/case<N>_<платформа>_<timestamp>/
  report.html       — HTML-отчёт
  report.md         — Markdown-отчёт
  results.json      — результаты в JSON (включая release_decision)
  results.csv       — результаты в CSV
  report.css        — стили (копия из docs/reporting/)
  *.png             — скриншоты шагов
```

### 3.2 Цепочка кейсов (run_all)

Сводные артефакты сохраняются в:

```
products/Editors/artifacts/multi_<платформа>_<timestamp>/
  report_all.html    — сводный HTML-отчёт
  results_all.json   — агрегированные результаты (включая release_decision)
  results_all.csv    — агрегированные результаты в CSV
  report.css         — базовые стили
  report_all.css     — стили сводного отчёта
  case<N>.log        — логи stdout каждого кейса
```

---

## 4. Интерпретация результатов

### 4.1 Stdout

Каждый скрипт выводит ключевые переменные в stdout:

```
RUN_DIR=<путь к папке прогона>
STATUS=PASS|FAIL
VERDICT=GO|GO_WITH_RISK|NO_GO
REPORT_HTML=<путь к HTML-отчёту>
```

run_all.py дополнительно выводит:

```
CASES_RUN=<количество>
OVERALL_RESULT=PASS|FAIL
OVERALL_VERDICT=GO|GO_WITH_RISK|NO_GO
PASS=<N> FAIL=<M>
```

### 4.2 Решение о релизе (RELEASE_DECISION)

Каждый прогон формирует рекомендацию:

| Вердикт | Значение |
|---------|----------|
| **GO** | Рекомендация: можно релизить |
| **GO_WITH_RISK** | Рекомендация: можно релизить с известными ограничениями |
| **NO_GO** | Рекомендация: релизить нельзя |

Сводный вердикт = наихудший из вердиктов отдельных кейсов.

---

## 5. Цепочка кейсов — правила

Кейсы в цепочке связаны по предусловиям/постусловиям:

- **Кейс 1** (Запуск редактора): предусловие — редактор не запущен. Постусловие — редактор остаётся открытым.
- **Кейс 2** (Главное окно): предусловие — редактор запущен (после кейса 1). Постусловие — редактор остаётся открытым.
- **Последний кейс цепочки**: закрывает редактор.

При запуске отдельного кейса вне цепочки — кейс закрывает редактор после выполнения (standalone-режим).

---

## 6. Устранение проблем

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Убедитесь, что запускаете через `.venv` Python |
| Кейс 2 падает с «редактор не найден» | Сначала выполните кейс 1 или запустите через `run_all.py` |
| Tesseract не найден | Установите Tesseract OCR как системный пакет |
| Скриншоты пустые | Проверьте разрешение экрана и масштаб |
| Кодировка отчёта | Все файлы сохраняются в UTF-8 |

---

## 7. Структура проекта

```
Testing/
  docs/
    governance/AGENTS.md          — философия и правила агентов
    methodology/SCRIPT_RULES.md   — правила написания скриптов
    methodology/REPORT_STYLE_RULES.md — стандарт оформления отчётов
    reporting/report.css          — стили HTML-отчёта (единый для проекта)
    reporting/report_all.css      — стили сводного отчёта
    LAUNCH_INSTRUCTIONS.md        — этот файл
  shared/
    infra/                        — общая инфраструктура (отчёты, скриншоты, среда, решения)
    drivers/                      — платформенные адаптеры
  products/
    Editors/
      RISK_MODEL.md               — модель рисков Editors
      DECISION_ENGINE.md          — движок решений Editors
      run_all.py                  — оркестратор запуска кейсов
      actions/                    — semantic actions продукта
      assertions/                 — semantic assertions продукта
      scenarios/smoke/            — тест-сценарии
      test_data/                  — эталонные файлы
      artifacts/                  — результаты прогонов
  setup_env.py                    — подготовка виртуального окружения
  requirements.txt                — общие зависимости
```
