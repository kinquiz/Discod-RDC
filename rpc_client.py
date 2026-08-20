"""
Модуль для работы с Discord Rich Presence через библиотеку pypresence.

Инкапсулирует:
- подключение и переподключение к локально запущенному клиенту Discord
  (Discord IPC работает только с приложением Discord, открытым на этом же компьютере);
- отправку (обновление) статуса активности на основании пресета;
- перевод ошибок pypresence в понятные пользователю сообщения (RPCError).
"""

from __future__ import annotations

import time
from typing import Any, Optional

from pypresence import Presence
from pypresence.types import ActivityType
from pypresence.exceptions import (
    ConnectionTimeout,
    DiscordError,
    DiscordNotFound,
    InvalidID,
    InvalidPipe,
    PipeClosed,
    PyPresenceException,
    ResponseTimeout,
    ServerError,
)

# Discord RPC поддерживает только эти 4 типа активности
# (тип STREAMING формально существует, но не реализован на стороне Discord для RPC).
ACTIVITY_TYPE_MAP: dict[str, ActivityType] = {
    "PLAYING": ActivityType.PLAYING,
    "LISTENING": ActivityType.LISTENING,
    "WATCHING": ActivityType.WATCHING,
    "COMPETING": ActivityType.COMPETING,
}

# Ошибки, при которых имеет смысл один раз автоматически переподключиться
# и повторить отправку статуса (обычно это значит, что Discord был перезапущен).
_RECOVERABLE_ERRORS = (PipeClosed, InvalidPipe, BrokenPipeError, ConnectionResetError, OSError)


class RPCError(Exception):
    """Ошибка RPC-клиента с сообщением, понятным конечному пользователю."""


class RPCClient:
    """Обёртка над pypresence.Presence с автоматическим переподключением."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._rpc: Optional[Presence] = None
        self.connected: bool = False

    def set_client_id(self, client_id: str) -> None:
        """Меняет Client ID и сбрасывает текущее соединение (если было)."""
        if client_id != self.client_id:
            self.disconnect()
        self.client_id = client_id

    def connect(self) -> None:
        """Устанавливает соединение с локальным клиентом Discord."""
        if not self.client_id:
            raise RPCError(
                "Client ID не задан. Укажите его в config.json "
                "или через пункт меню «Настройки»."
            )
        try:
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self.connected = True
        except DiscordNotFound:
            self.connected = False
            raise RPCError(
                "Discord не запущен. Запустите приложение Discord и попробуйте снова."
            )
        except InvalidPipe:
            self.connected = False
            raise RPCError(
                "Не удалось найти канал (pipe) Discord. Discord точно запущен на этом компьютере?"
            )
        except InvalidID:
            self.connected = False
            raise RPCError(
                "Неверный Client ID. Проверьте значение application id "
                "в Discord Developer Portal и в config.json."
            )
        except ConnectionTimeout:
            self.connected = False
            raise RPCError("Превышено время ожидания подключения к Discord.")
        except DiscordError as exc:
            self.connected = False
            raise RPCError(f"Discord вернул ошибку при подключении: {exc.message} (код {exc.code}).")
        except PyPresenceException as exc:
            self.connected = False
            raise RPCError(f"Не удалось подключиться к Discord: {exc}")

    def ensure_connected(self) -> None:
        """Переподключается, если соединение отсутствует."""
        if not self.connected or self._rpc is None:
            self.connect()

    def disconnect(self) -> None:
        """Закрывает соединение, если оно было открыто."""
        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:
                pass
        self.connected = False
        self._rpc = None

    def _call_with_reconnect(self, func: Any) -> Any:
        """
        Выполняет func() (без аргументов). Если соединение с Discord оборвано
        (например, Discord был закрыт и открыт заново), выполняет одну попытку
        переподключения и повторяет вызов. Любые другие ошибки пробрасывает как есть —
        их переводит в понятное сообщение сам вызывающий код.
        """
        try:
            return func()
        except _RECOVERABLE_ERRORS:
            self.connected = False
            self.connect()
            return func()

    def update(self, preset: dict[str, Any]) -> None:
        """
        Обновляет статус активности на основании пресета.

        При обрыве соединения (например, Discord был закрыт и открыт заново)
        выполняется одна попытка автоматического переподключения перед тем,
        как сообщить об ошибке пользователю.
        """
        self.ensure_connected()
        self._call_with_reconnect(lambda: self._send_update(preset))

    def clear(self) -> None:
        """Очищает текущий статус активности в Discord."""
        self.ensure_connected()
        try:
            self._call_with_reconnect(lambda: self._rpc.clear())
        except PyPresenceException as exc:
            raise RPCError(f"Не удалось очистить статус: {exc}")

    def _send_update(self, preset: dict[str, Any]) -> None:
        """Формирует payload из пресета и отправляет его в Discord."""
        activity_type = ACTIVITY_TYPE_MAP.get(
            preset.get("activity_type", "PLAYING"), ActivityType.PLAYING
        )

        kwargs: dict[str, Any] = {
            "activity_type": activity_type,
            "details": preset.get("details") or None,
            "state": preset.get("state") or None,
            "large_image": preset.get("large_image") or None,
            "large_text": preset.get("large_text") or None,
            "small_image": preset.get("small_image") or None,
            "small_text": preset.get("small_text") or None,
        }

        # Кнопки: Discord поддерживает не более двух кнопок со ссылками.
        buttons = [
            {"label": b["label"], "url": b["url"]}
            for b in preset.get("buttons", [])
            if b.get("label") and b.get("url")
        ]
        if buttons:
            kwargs["buttons"] = buttons[:2]

        # Таймер: либо "прошло времени" от текущего момента,
        # либо обратный отсчёт до заданной длительности в минутах.
        timer = preset.get("timer", "none")
        if timer == "elapsed":
            kwargs["start"] = int(time.time())
        elif timer == "countdown":
            minutes = preset.get("countdown_minutes") or 0
            if minutes > 0:
                kwargs["end"] = int(time.time() + minutes * 60)

        # Убираем ключи со значением None, activity_type и buttons передаём всегда,
        # если они заданы.
        clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}

        try:
            self._rpc.update(**clean_kwargs)
        except (PipeClosed, InvalidPipe):
            # Пробрасываем наверх как есть — это обрабатывает _call_with_reconnect(),
            # который выполнит переподключение и повторит попытку.
            raise
        except ServerError as exc:
            raise RPCError(
                f"Discord отклонил обновление статуса: {exc}. "
                f"Проверьте названия ключей ассетов (картинок) и ссылки в кнопках."
            )
        except ResponseTimeout:
            raise RPCError("Discord не ответил вовремя. Попробуйте повторить обновление.")
        except PyPresenceException as exc:
            raise RPCError(f"Ошибка pypresence: {exc}")
