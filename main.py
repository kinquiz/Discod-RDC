#!/usr/bin/env python3
"""
Discord Rich Presence клиент — точка входа.

Запуск:
    python main.py

Перед первым запуском укажите Client ID приложения (application id),
созданного в Discord Developer Portal, в файле config.json —
это можно сделать вручную или через пункт меню «Настройки» после запуска.
Подробности — в README.md.
"""

from __future__ import annotations

import sys

from config import ConfigError
from i18n import t
from ui import App


def main() -> None:
    try:
        app = App()
    except ConfigError as exc:
        print(t("common.error_prefix", error=t("app.config_error", error=exc)))
        sys.exit(1)
    try:
        app.run()
    except KeyboardInterrupt:
        print(t("app.interrupted"))
        app.rpc.disconnect()
        sys.exit(0)


if __name__ == "__main__":
    main()
