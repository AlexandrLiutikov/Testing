# Стандарт оформления HTML-отчета автотестов R7 Office

Этот документ обязателен для всех новых отчетов в проекте `D:\Projects\Testing`.

---

## 1. Имя и расположение
- Файл отчета: `report.html` (или `test_report.html` для совместимости с историей проекта).
- Файл стилей: `report.css` — единый для всего проекта, хранится в `docs/reporting/report.css`. При генерации отчёта копируется в каталог прогона рядом с `report.html`.
- Расположение: в каталоге конкретного прогона `products/<Продукт>/artifacts/<run_id>/`.

## 2. Обязательная структура HTML
- `<!doctype html>` и `<html lang='ru'>`.
- В `<head>` обязательно:
  - `<meta charset='UTF-8'>`
  - `<meta name='viewport' content='width=device-width, initial-scale=1.0'>`
  - `<title>R7 Office Autotest Report</title>`
  - `<link rel='stylesheet' href='report.css'>` — подключение внешнего файла стилей (не дублировать стили в `<style>`)
- В `<body>` обязательно (в этом порядке):
  - Заголовок `Отчет по автотесту R7 Office`.
  - Мета-блок `.meta`.
  - **Блок решения о релизе `.decision`** (новый, обязательный).
  - Таблица результатов шагов.
  - Футер со ссылками на артефакты (`autotest.log` при наличии, `results.json`, `results.csv`).

## 3. Обязательный мета-блок

В блоке `.meta` должны быть строки (в этом порядке):

**Время:**
- `Запуск: YYYY-MM-DD HH:MM:SS`
- `Окончание: YYYY-MM-DD HH:MM:SS`
- `Длительность: N сек`

**Среда выполнения (обязательно):**
- `ОС: <os_name>` — полное имя ОС (например: `Astra Linux 1.7.5`, `Windows 11`, `macOS 14.2`)
- `Архитектура: <arch>` — `x86_64`, `x86`, `arm64`
- `Пакет: <package>` — имя установленного пакета (например: `astra-signed.deb`, `x64.exe`, `arm64.dmg`)
- `Разрешение экрана: <WxH>` — текущее разрешение (например: `1920x1080`)
- `Масштаб: <scale>` — если определяется (например: `100%`, `125%`)
- `Версия редактора: <version>` — версия установленного Editors
- `Стенд: <hostname>` — имя машины (для идентификации)

**Результат:**
- `Результат: <badge>` (PASS/FAIL по шагам)
- `PASS: X | FAIL: Y | BLOCKED: Z | WARN: N | FALLBACK_STEPS: M`

### Пример мета-блока

```html
<div class='meta'>
  <div>Запуск: 2026-04-04 14:30:00</div>
  <div>Окончание: 2026-04-04 14:30:47</div>
  <div>Длительность: 47 сек</div>
  <div class='env-info'>
    ОС: Astra Linux 1.7.5 | Архитектура: x86_64 | Пакет: astra-signed.deb<br>
    Разрешение: 1920x1080 | Масштаб: 100% | Версия: 2024.1.234 | Стенд: test-astra-01
  </div>
  <div>Результат: <span class='badge pass'>PASS</span></div>
  <div>PASS: 5 | FAIL: 0</div>
</div>
```

### CSS для блока среды

Стили класса `.env-info` определены в `report.css`.

## 4. Блок решения о релизе (обязательный)

Размещается **между мета-блоком и таблицей шагов**. Это центральный элемент отчета.

### Структура блока

```html
<div class='decision go-with-risk'>
  <div class='decision-badge go-with-risk'>RELEASE DECISION: GO_WITH_RISK</div>
  
  <div class='decision-section'>
    <strong>Обоснование:</strong>
    <ul>
      <li>Все критические пути пройдены (запуск, открытие, сохранение)</li>
      <li>1 сбой в UI-тесте со severity MEDIUM</li>
    </ul>
  </div>

  <div class='decision-section'>
    <strong>Риски:</strong>
    <ul>
      <li><span class='severity medium'>MEDIUM</span> — Смещение иконки вкладки «Вставка» (UI_LAYOUT)</li>
    </ul>
  </div>

  <div class='decision-section'>
    <strong>Рекомендации:</strong>
    <ul>
      <li>Разрешить релиз</li>
      <li>Создать задачу на исправление UI (приоритет LOW)</li>
    </ul>
  </div>

  <div class='decision-section'>
    <strong>INFRA issues:</strong>
    <ul>
      <li>Шаг «Сохранение»: OCR timeout в системном диалоге</li>
    </ul>
  </div>

  <div class='decision-section'>
    <strong>BLOCKED cases:</strong>
    <ul>
      <li>Шаг «Печать»: стенд без настроенного принтера</li>
    </ul>
  </div>

  <div class='decision-section'>
    <strong>Warnings:</strong>
    <ul>
      <li>LOW: Обнаружен новый UI-элемент во вкладке «Вставка»</li>
    </ul>
  </div>

  <div class='decision-stats'>
    Всего шагов: 12 | PASS: 9 | TEST_FAIL: 1 | INFRA_FAIL: 1 | BLOCKED: 1 | WARN: 4 | Критические пути: 5/5
    <br>Run confidence: SUFFICIENT 2 из 12 шагов имеют статус INFRA_FAIL/BLOCKED
  </div>
</div>
```

### Визуальные варианты

| Вердикт | CSS-класс | Цвет фона | Цвет бордера | Цвет текста |
|---|---|---|---|---|
| GO | `.decision.go` | `#dafbe1` | `#1a7f37` | `#1a7f37` |
| GO_WITH_RISK | `.decision.go-with-risk` | `#fff8c5` | `#d4a72c` | `#9a6700` |
| NO_GO | `.decision.no-go` | `#ffebe9` | `#cf222e` | `#cf222e` |

### CSS для блока решения

Стили классов `.decision`, `.decision-badge`, `.decision-section`, `.decision-stats` и `.severity` определены в `report.css`.

## 5. Таблица шагов (фиксированные колонки)
Таблица должна содержать колонки строго в этом порядке:
1. `Step`
2. `Шаг`
3. `Статус`
4. `Severity` (новая колонка — заполняется только для FAIL)
5. `Warnings/Fallback`
6. `Ожидание`
7. `Факт`
8. `Скриншот`

Каждая строка = один проверяемый шаг кейса.

Для строк с FAIL в колонке Severity указывать уровень: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
Для строк с PASS колонка Severity остаётся пустой.
В `Warnings/Fallback` выводятся предупреждения шага и факт fallback (`fallback_source`, `fallback_reason`).

## 6. Статусы и цвета
- PASS: класс `.pass`, зеленый `#1a7f37`
- FAIL: класс `.fail`, красный `#cf222e`
- (опционально) BLOCKED: класс `.blocked` с отличимым цветом

## 7. Скриншоты
- Для каждого ключевого шага обязателен скриншот.
- В ячейке `Скриншот` использовать превью + ссылку на оригинал:
  - `<a href='file.png' target='_blank'><img src='file.png' alt='file.png' class='screenshot-thumb'></a>`
- Класс `screenshot-thumb` определён в `report.css` (не использовать inline-стили на `<img>`).

## 8. CSS (единый визуальный стиль)

Все стили вынесены в файл `report.css` в корне проекта (`D:\Projects\Testing\report.css`).
При генерации отчёта скрипт копирует `report.css` в каталог прогона рядом с `report.html`.
HTML-отчёт подключает стили через `<link rel='stylesheet' href='report.css'>`.

**Запрещено:**
- Дублировать стили в `<style>` внутри HTML.
- Использовать inline-стили (`style="..."`) на элементах — вместо этого применять CSS-классы из `report.css`.

**Базовая тема (определена в `report.css`):**
- `body`: `Segoe UI, Arial, sans-serif`, фон `#f7f9fc`
- `table`/`th`/`td`: границы `#d0d7de`
- `th` фон: `#f0f4f8`
- `.meta`: белый блок с рамкой и скруглением
- `.decision`: см. раздел 4
- `.screenshot-thumb`: превью скриншотов (см. раздел 7)

При необходимости изменить оформление — редактировать только `report.css` в корне проекта.

## 9. Контентные требования
- Тексты шага (`Шаг`, `Ожидание`, `Факт`) должны быть конкретными и проверяемыми.
- Нельзя писать общий текст без факта выполнения.
- Для FAIL обязательно указывать причину сбоя и на каком шаге.

## 10. Совместимость
- Отчет должен открываться локально в браузере без внешних CDN/скриптов.
- Все ссылки должны быть относительными к папке прогона.
- Файл `report.css` должен присутствовать в каталоге прогона рядом с `report.html`.

## 11. Контроль перед публикацией
Перед завершением прогона проверить:
- HTML открывается без ошибок.
- Все изображения доступны по ссылкам.
- Количество строк в таблице соответствует количеству шагов кейса.
- Итоговые счетчики PASS/FAIL совпадают с таблицей.
- **Блок решения о релизе присутствует и содержит вердикт, обоснование и рекомендации.**

## 12. Формулировки Факт (без тех-деталей)
- В колонке Факт писать только пользовательски значимый результат шага.
- Не указывать внутренний технический способ проверки (OCR, UIA, координаты, эвристики).
- Пример правильно: Окно подключения появилось. / После нажатия Esc окно закрыто.
- Пример неправильно: Подтверждено по OCR-признакам.

## 13. Сводный отчет (run_all)

При мультикейсовом прогоне сводный `report_all.html` содержит:
- Мета-блок с общей статистикой
- **Блок сводного решения о релизе** (агрегация по всем кейсам)
- Таблицу результатов по кейсам (с ссылками на детальные отчеты)

Сводное решение = наихудший вердикт из всех кейсов + полная аргументация.

## 14. Структура results.json

Файл `results.json` обязан содержать поля `environment` и `release_decision`:

```json
{
  "environment": {
    "os_family": "Linux",
    "os_name": "Astra Linux 1.7.5",
    "os_version": "1.7.5",
    "architecture": "x86_64",
    "package": "astra-signed.deb",
    "screen_resolution": "1920x1080",
    "display_scale": "100%",
    "editor_version": "2024.1.234",
    "editor_path": "/opt/r7-office/desktopeditors",
    "hostname": "test-astra-01",
    "run_timestamp": "2026-04-04 14:30:00"
  },
  "case_meta": {
    "case_id": 1,
    "case_name": "Запуск редактора",
    "area": "Editors/Общее",
    "risk_level": "HIGH",
    "critical_path": true
  },
  "steps": [ ... ],
  "summary": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "infra_failed": 0,
    "blocked": 0,
    "warning_steps": 0,
    "warnings_total": 0,
    "fallback_steps": 0
  },
  "run_confidence": "FULL",
  "run_confidence_detail": "0 из 3 шагов имеют статус INFRA_FAIL/BLOCKED; critical coverage: 3/3.",
  "release_decision": {
    "verdict": "GO",
    "reasons": ["Все шаги пройдены, критический путь покрыт"],
    "risks": [],
    "infra_issues": [],
    "blocked_cases": [],
    "warnings": [],
    "recommendations": ["Релиз разрешён"],
    "run_confidence": "FULL",
    "run_confidence_detail": "Прогон без инфраструктурных потерь сигнала.",
    "stats": {
      "total": 3,
      "passed": 3,
      "test_failed": 0,
      "infra_failed": 0,
      "blocked": 0,
      "warnings_total": 0,
      "critical_path_coverage": "1/1"
    }
  }
}
```
