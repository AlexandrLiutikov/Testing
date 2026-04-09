"""Каталог UI-разделов для переиспользования в smoke-кейсах Editors."""

START_MENU_EXPECTED = [
    "Главная",
    "Шаблоны",
    "Локальные файлы",
    "Совместная работа",
    "Настройки",
    "О программе",
]

# Каталог вкладок редактора документов:
# - required: признаки, отсутствие которых приводит к FAIL
# - optional: признаки, изменения которых фиксируются как warning
TOOLBAR_TABS = [
    {
        "name": "Файл",
        "required": ["Сведения", "Сохранить как"],
        "optional": ["Скачать как", "Версия"],
        "need": 2,
    },
    {
        "name": "Вставка",
        "required": ["Таблица", "Изображение"],
        "optional": ["Диаграмма", "Колонтитулы"],
        "need": 2,
    },
    {
        "name": "Рисование",
        "required": ["Перо"],
        "optional": ["Маркер", "Ластик"],
        "need": 1,
    },
    {
        "name": "Макет",
        "required": ["Поля", "Ориентация"],
        "optional": ["Размер", "Колонки"],
        "need": 2,
    },
    {
        "name": "Ссылки",
        "required": ["Оглавление"],
        "optional": ["Сноска", "Гиперссылка", "Закладка"],
        "need": 1,
    },
    {
        "name": "Совместная работа",
        "required": ["Комментарий"],
        "optional": ["Сравнить"],
        "need": 1,
    },
    {
        "name": "Защита",
        "required": ["Зашифровать"],
        "optional": ["Подпись"],
        "need": 1,
    },
    {
        "name": "Вид",
        "required": ["Масштаб"],
        "optional": ["Линейка", "Непечатаемые"],
        "need": 1,
    },
    {
        "name": "Плагины",
        "required": ["Макросы"],
        "optional": ["Менеджер"],
        "need": 1,
    },
]


def diff_ui_items(observed: list, expected: list) -> dict:
    """Сравнить наблюдаемые UI-элементы с эталонным списком."""
    observed_set = {str(x).strip() for x in observed if str(x).strip()}
    expected_set = {str(x).strip() for x in expected if str(x).strip()}
    missing = sorted(expected_set - observed_set)
    extra = sorted(observed_set - expected_set)
    return {"missing": missing, "extra": extra}


def toolbar_tab_names() -> list:
    return [item["name"] for item in TOOLBAR_TABS]

