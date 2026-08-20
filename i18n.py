"""
Модуль интернационализации (i18n).

Загружает JSON-файлы локализации из каталога locales/ (locales/en.json,
locales/ru.json) и предоставляет функцию t(key, **kwargs) для получения
строки интерфейса на текущем выбранном языке.

Английский (en) — базовый язык: если для ключа нет перевода на текущем
языке, используется английский, а если и там ключа нет — возвращается сам
ключ (чтобы приложение никогда не падало и не показывало пустую строку).

Чтобы добавить новый язык, создайте locales/<code>.json с теми же ключами,
что и в locales/en.json, и переключитесь на него через пункт меню
«Language / Язык» (или вручную впишите "language": "<code>" в config.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LOCALES_DIR = BASE_DIR / "locales"
DEFAULT_LANGUAGE = "en"

_cache: dict[str, dict[str, Any]] = {}
_current_language: str = DEFAULT_LANGUAGE


def available_languages() -> list[str]:
    """Возвращает отсортированный список кодов языков, для которых есть файл в locales/."""
    if not LOCALES_DIR.exists():
        return [DEFAULT_LANGUAGE]
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


def _load_locale(language: str) -> dict[str, Any]:
    if language not in _cache:
        path = LOCALES_DIR / f"{language}.json"
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                _cache[language] = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            _cache[language] = {}
    return _cache[language]


def set_language(language: str) -> None:
    """Устанавливает текущий язык интерфейса. Неизвестный код откатывается на английский."""
    global _current_language
    if language not in available_languages():
        language = DEFAULT_LANGUAGE
    _current_language = language
    _load_locale(language)


def get_language() -> str:
    """Возвращает код текущего выбранного языка."""
    return _current_language


def _lookup(data: dict[str, Any], dotted_key: str) -> str | None:
    node: Any = data
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def t(key: str, **kwargs: Any) -> str:
    """
    Возвращает строку локали по ключу вида "section.subsection.name".

    При отсутствии ключа в текущем языке используется английский (fallback),
    а если ключа нет и там — возвращается сам ключ. Именованные параметры
    подставляются в строку через str.format().
    """
    value = _lookup(_load_locale(_current_language), key)
    if value is None and _current_language != DEFAULT_LANGUAGE:
        value = _lookup(_load_locale(DEFAULT_LANGUAGE), key)
    if value is None:
        value = key
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value


# Псевдоним, упомянутый в требованиях (get_string("key") эквивалентен t("key")).
get_string = t
