"""Loader для file-model-backed конфигураций продукта."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=64)
def load_yaml_model(relative_path: str) -> Dict[str, Any]:
    """Загрузить YAML-модель из репозитория по относительному пути.

    Args:
        relative_path: путь относительно корня репозитория.

    Returns:
        Словарь модели.
    """
    model_path = (REPO_ROOT / relative_path).resolve()
    if not model_path.is_file():
        raise FileNotFoundError(
            f"YAML model not found: {relative_path} ({model_path})"
        )

    if REPO_ROOT not in model_path.parents:
        raise ValueError(f"Model path is outside repo root: {model_path}")

    with model_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"YAML model must be an object: {relative_path} (type={type(data)!r})"
        )
    return data
