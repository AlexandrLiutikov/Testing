"""Каталог UI-разделов для переиспользования в smoke-кейсах Editors."""

from shared.infra.model_loader import load_yaml_model


_UI_MODEL = load_yaml_model("products/Editors/models/ui/toolbar_tabs.yaml")

START_MENU_EXPECTED = list(_UI_MODEL.get("start_menu", {}).get("expected", []))
START_SCREEN_SECTIONS = dict(_UI_MODEL.get("start_screen", {}).get("sections", {}))

# Каталог вкладок редактора документов:
# - required: признаки, отсутствие которых приводит к FAIL
# - optional: признаки, изменения которых фиксируются как warning
TOOLBAR_TABS = list(_UI_MODEL.get("toolbar_tabs", []))

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

