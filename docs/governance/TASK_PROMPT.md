# TASK_PROMPT.md — Операционный адаптер к MASTER_PROMPT

Цель этого файла: дать краткий чеклист выполнения задачи **без дублирования и переопределения** правил из `MASTER_PROMPT.md`.

## Нормативный статус документов

Единая система управления агентом строится так:

1. `docs/governance/RULES.md` — миссия, приоритеты, источник истины верхнего уровня.
2. `docs/governance/GIT_DISCIPLINE.md` — обязательный регламент Git.
3. `docs/governance/MASTER_PROMPT.md` — единая нормативная модель поведения агента (классификация FAIL, RELEASE_DECISION, фазы исполнения, формат ответа).
4. `docs/governance/TASK_PROMPT.md` (этот файл) — **операционный адаптер**: повторяет только маршрут выполнения и ссылки на канонику.

`TASK_PROMPT.md` **не вводит новые правила**, **не расширяет** и **не переопределяет** `MASTER_PROMPT.md`.

Если найдено расхождение между `TASK_PROMPT.md` и `MASTER_PROMPT.md`, действует `MASTER_PROMPT.md`.

## Обязательный маршрут выполнения задачи

1. Выполнить preflight-чтение документации (по требованиям `MASTER_PROMPT.md`, раздел 1).
2. Зафиксировать ограничения: `RULES APPLIED`, `RISK MODEL IMPACT`, `DECISION IMPACT` (см. `MASTER_PROMPT.md`, PHASE 2).
3. Подготовить `IMPLEMENTATION PLAN` (см. `MASTER_PROMPT.md`, PHASE 3).
4. Пройти validation gate перед реализацией (см. `MASTER_PROMPT.md`, PHASE 3 / VALIDATION GATE).
5. Выполнить реализацию только после успешных PHASE 1-3 (см. `MASTER_PROMPT.md`, PHASE 4).
6. Выполнить `SELF-CHECK` и исправить все нарушения до финального ответа (см. `MASTER_PROMPT.md`, PHASE 5).

## Обязательный формат ответа (синхронизирован с MASTER_PROMPT)

1. `RULES APPLIED`
2. `RISK MODEL IMPACT`
3. `DECISION IMPACT`
4. `IMPLEMENTATION PLAN`
5. `CODE`
6. `SELF-CHECK`

Если раздел не применим к типу задачи, это явно помечается как `N/A` с коротким обоснованием.

Отсутствие обязательного блока считается нарушением протокола выполнения.
