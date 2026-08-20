"""
Модуль конфигурации приложения.

Отвечает за чтение и запись двух файлов:
- config.json  — общие настройки приложения (Client ID приложения Discord).
- presets.json — сохранённые пользователем пресеты активности (Rich Presence).

Файлы лежат рядом со скриптом, поэтому их можно свободно редактировать вручную
в любом текстовом редакторе, а не только через интерфейс приложения.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Каталог, в котором лежит сам скрипт — используем его как базу для путей,
# чтобы приложение работало одинаково независимо от текущей рабочей директории.
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PRESETS_PATH = BASE_DIR / "presets.json"

# Значения по умолчанию, которые используются, если файл ещё не существует
# или повреждён.
DEFAULT_CONFIG: dict[str, Any] = {
    "client_id": ""
}

DEFAULT_PRESETS: dict[str, Any] = {
    "presets": {}
}


class ConfigError(Exception):
    """Ошибка чтения или записи файлов конфигурации (config.json / presets.json)."""


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """Читает JSON-файл, возвращая значение по умолчанию при отсутствии/ошибке чтения."""
    if not path.exists():
        return json.loads(json.dumps(default))  # глубокая копия
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("корневой элемент JSON должен быть объектом")
            return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"[config] Не удалось прочитать {path.name}: {exc}. "
              f"Будут использованы значения по умолчанию.")
        return json.loads(json.dumps(default))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    """Сохраняет словарь в JSON-файл с человекочитаемым форматированием."""
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        raise ConfigError(f"Не удалось сохранить {path.name}: {exc}")


def load_config() -> dict[str, Any]:
    """Загружает config.json (создавая файл со значениями по умолчанию при первом запуске)."""
    if not CONFIG_PATH.exists():
        save_config(dict(DEFAULT_CONFIG))
    config = _load_json(CONFIG_PATH, DEFAULT_CONFIG)
    # Дозаполняем отсутствующие ключи значениями по умолчанию,
    # чтобы старые config.json оставались совместимы после обновления приложения.
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    return config


def save_config(config: dict[str, Any]) -> None:
    """Сохраняет config.json."""
    _save_json(CONFIG_PATH, config)


def load_presets() -> dict[str, Any]:
    """Загружает presets.json (создавая пустой файл при первом запуске)."""
    if not PRESETS_PATH.exists():
        save_presets(dict(DEFAULT_PRESETS))
    presets = _load_json(PRESETS_PATH, DEFAULT_PRESETS)
    presets.setdefault("presets", {})
    return presets


def save_presets(presets: dict[str, Any]) -> None:
    """Сохраняет presets.json."""
    _save_json(PRESETS_PATH, presets)
