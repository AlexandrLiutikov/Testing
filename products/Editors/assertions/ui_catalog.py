"""Каталог UI-разделов для переиспользования в smoke-кейсах Editors."""

from shared.infra.model_loader import load_yaml_model


_UI_MODEL = load_yaml_model("products/Editors/models/ui/toolbar_tabs.yaml")

START_MENU_EXPECTED = list(_UI_MODEL.get("start_menu", {}).get("expected", []))
START_SCREEN_SECTIONS = dict(_UI_MODEL.get("start_screen", {}).get("sections", {}))

# Каталог вкладок редактора документов:
# - required: признаки, отсутствие которых приводит к FAIL
# - optional: признаки, изменения которых фиксируются как warning
TOOLBAR_TABS = list(_UI_MODEL.get("toolbar_tabs", []))
TOOLBAR_TABS_WARNING_EXPECTED = list(_UI_MODEL.get("toolbar_tabs_warning_expected", []))
TOOLBAR_TAB_CONTROLS_EXPECTED = dict(_UI_MODEL.get("toolbar_tab_controls_expected", {}))

UI_CATALOG_TOLERANCES = dict(_UI_MODEL.get("tolerances", {}))


def diff_ui_items(observed: list, expected: list) -> dict:
    """Сравнить наблюдаемые UI-элементы с эталонным списком."""
    observed_set = {str(x).strip() for x in observed if str(x).strip()}
    expected_set = {str(x).strip() for x in expected if str(x).strip()}
    missing = sorted(expected_set - observed_set)
    extra = sorted(observed_set - expected_set)
    return {"missing": missing, "extra": extra}


def toolbar_tab_names() -> list:
    return [item["name"] for item in TOOLBAR_TABS]


def toolbar_tab_warning_expected_names() -> list:
    """Список вкладок для drift-предупреждений UI_NEW_ELEMENT."""
    if TOOLBAR_TABS_WARNING_EXPECTED:
        return [str(name).strip() for name in TOOLBAR_TABS_WARNING_EXPECTED if str(name).strip()]

    # Fallback для старых моделей: ожидаем smoke-вкладки + базовую «Главная».
    out = []
    seen = set()
    for name in ["Главная", *toolbar_tab_names()]:
        key = str(name).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def toolbar_tab_controls_expected(tab_name: str) -> list:
    """Вернуть каталог ожидаемых контролов внутри активной вкладки."""
    key = str(tab_name).strip()
    if not key:
        return []

    direct = TOOLBAR_TAB_CONTROLS_EXPECTED.get(key, [])
    if isinstance(direct, list) and direct:
        return [str(item).strip() for item in direct if str(item).strip()]

    # Fallback: если раздел controls не задан, используем required+optional.
    for tab in TOOLBAR_TABS:
        if str(tab.get("name", "")).strip() != key:
            continue
        required = [str(x).strip() for x in tab.get("required", []) if str(x).strip()]
        optional = [str(x).strip() for x in tab.get("optional", []) if str(x).strip()]
        return list(dict.fromkeys(required + optional))
    return []


def start_screen_section(section_key: str) -> dict:
    """Вернуть каноническую спецификацию секции стартового экрана.

    Возвращает словарь формата:
    {
      "expected": str,
      "tokens": list[str],
      "need": int,
    }
    """
    raw = START_SCREEN_SECTIONS.get(section_key, {}) or {}
    tokens = [str(x).strip() for x in raw.get("tokens", []) if str(x).strip()]
    need = int(raw.get("need", max(1, len(tokens) if tokens else 1)))
    expected = str(raw.get("expected", "")).strip()
    return {
        "expected": expected,
        "tokens": tokens,
        "need": need,
    }

