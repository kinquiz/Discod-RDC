"""
Модуль пользовательского интерфейса (CLI).

Реализует текстовое меню для управления Discord Rich Presence:
- редактирование полей активности "на лету" (каждое изменение сразу
  отправляется в Discord, без перезапуска скрипта);
- управление пресетами (сохранение/загрузка/удаление в presets.json);
- настройки приложения (Client ID) в config.json;
- ручное переподключение к Discord.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import config
from rpc_client import RPCClient, RPCError

ACTIVITY_TYPE_LABELS: dict[str, str] = {
    "PLAYING": "Playing (Играет в …)",
    "LISTENING": "Listening (Слушает …)",
    "WATCHING": "Watching (Смотрит …)",
    "COMPETING": "Competing (Соревнуется в …)",
}
ACTIVITY_TYPE_ORDER = ["PLAYING", "LISTENING", "WATCHING", "COMPETING"]

# Пустой пресет, с которого приложение стартует при первом запуске.
def make_empty_preset() -> dict[str, Any]:
    return {
        "details": "",
        "state": "",
        "activity_type": "PLAYING",
        "large_image": "",
        "large_text": "",
        "small_image": "",
        "small_text": "",
        "buttons": [],
        "timer": "none",
        "countdown_minutes": 0,
    }


def _input(prompt: str, default: str = "") -> str:
    """input() с подсказкой текущего значения и возможностью оставить его без изменений."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def _input_int(prompt: str, default: int = 0) -> int:
    raw = _input(prompt, str(default))
    try:
        return int(raw)
    except ValueError:
        print("Нужно ввести целое число. Оставлено предыдущее значение.")
        return default


class App:
    """Основной класс приложения: хранит состояние и обрабатывает меню."""

    def __init__(self) -> None:
        self.cfg = config.load_config()
        self.presets_data = config.load_presets()
        self.rpc = RPCClient(self.cfg.get("client_id", ""))
        self.current: dict[str, Any] = make_empty_preset()
        self.current_preset_name: str | None = None

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #

    def _run_rpc(self, action: Callable[[], None], success_message: str) -> None:
        """Выполняет RPC-действие, печатая единообразное сообщение об успехе/ошибке."""
        try:
            action()
            print(f"✔ {success_message}")
        except RPCError as exc:
            print(f"✘ {exc}")

    def apply(self) -> None:
        """Отправляет текущее состояние в Discord и печатает результат/ошибку."""
        self._run_rpc(lambda: self.rpc.update(self.current), "Статус обновлён в Discord.")

    def print_status(self) -> None:
        p = self.current
        print("\n--- Текущая активность --------------------------------")
        print(f"  Тип:            {ACTIVITY_TYPE_LABELS.get(p['activity_type'], p['activity_type'])}")
        print(f"  Details (верх): {p['details'] or '—'}")
        print(f"  State (низ):    {p['state'] or '—'}")
        print(f"  Большая картинка: {p['large_image'] or '—'}  (текст: {p['large_text'] or '—'})")
        print(f"  Малая картинка:   {p['small_image'] or '—'}  (текст: {p['small_text'] or '—'})")
        if p["buttons"]:
            for i, b in enumerate(p["buttons"], 1):
                print(f"  Кнопка {i}: {b['label']} -> {b['url']}")
        else:
            print("  Кнопки: —")
        timer_desc = {
            "none": "выключен",
            "elapsed": "прошло времени (от текущего момента)",
            "countdown": f"обратный отсчёт ({p.get('countdown_minutes', 0)} мин.)",
        }.get(p["timer"], p["timer"])
        print(f"  Таймер: {timer_desc}")
        print(f"  Discord: {'подключено' if self.rpc.connected else 'нет соединения'}")
        print(f"  Активный пресет: {self.current_preset_name or '(не сохранён)'}")
        print("---------------------------------------------------------\n")

    # ------------------------------------------------------------------ #
    # Редактирование полей
    # ------------------------------------------------------------------ #

    def edit_details(self) -> None:
        self.current["details"] = _input("Details (верхняя строка статуса)", self.current["details"])
        self.apply()

    def edit_state(self) -> None:
        self.current["state"] = _input("State (нижняя строка статуса)", self.current["state"])
        self.apply()

    def edit_activity_type(self) -> None:
        print("\nВыберите тип активности:")
        for i, key in enumerate(ACTIVITY_TYPE_ORDER, 1):
            print(f"  {i}. {ACTIVITY_TYPE_LABELS[key]}")
        print("  (Streaming не поддерживается Discord через RPC-подключение)")
        choice = _input("Номер типа", "")
        if choice.isdigit() and 1 <= int(choice) <= len(ACTIVITY_TYPE_ORDER):
            self.current["activity_type"] = ACTIVITY_TYPE_ORDER[int(choice) - 1]
            self.apply()
        else:
            print("Некорректный выбор, значение не изменено.")

    def edit_large_image(self) -> None:
        print("Укажите ключ ассета из Developer Portal (Rich Presence -> Art Assets)")
        print("либо прямую ссылку на изображение (https://...), если Discord её поддержит.")
        self.current["large_image"] = _input("Large image (ключ или URL)", self.current["large_image"])
        self.current["large_text"] = _input("Подсказка при наведении (large_text)", self.current["large_text"])
        self.apply()

    def edit_small_image(self) -> None:
        self.current["small_image"] = _input("Small image (ключ или URL)", self.current["small_image"])
        self.current["small_text"] = _input("Подсказка при наведении (small_text)", self.current["small_text"])
        self.apply()

    def edit_buttons(self) -> None:
        print("\nDiscord поддерживает не более двух кнопок со ссылками.")
        buttons: list[dict[str, str]] = []
        for i in (1, 2):
            print(f"-- Кнопка {i} (оставьте название пустым, чтобы пропустить) --")
            existing = self.current["buttons"][i - 1] if len(self.current["buttons"]) >= i else {"label": "", "url": ""}
            label = _input("  Название кнопки", existing.get("label", ""))
            if not label:
                continue
            url = _input("  Ссылка (https://...)", existing.get("url", ""))
            if not url.startswith(("http://", "https://")):
                print("  Ссылка должна начинаться с http:// или https://, кнопка пропущена.")
                continue
            buttons.append({"label": label, "url": url})
        self.current["buttons"] = buttons
        self.apply()

    def edit_timer(self) -> None:
        print("\nТаймер:")
        print("  1. Выключить")
        print("  2. Прошло времени (elapsed) — считать от момента применения")
        print("  3. Обратный отсчёт (countdown) — до конца заданного количества минут")
        choice = _input("Выбор", "")
        if choice == "1":
            self.current["timer"] = "none"
        elif choice == "2":
            self.current["timer"] = "elapsed"
        elif choice == "3":
            minutes = _input_int(
                "Через сколько минут закончится", self.current.get("countdown_minutes", 30) or 30
            )
            if minutes <= 0:
                print("Количество минут должно быть больше нуля. Таймер не изменён.")
                return
            self.current["timer"] = "countdown"
            self.current["countdown_minutes"] = minutes
        else:
            print("Некорректный выбор, значение не изменено.")
            return
        self.apply()

    # ------------------------------------------------------------------ #
    # Пресеты
    # ------------------------------------------------------------------ #

    def list_presets(self) -> list[str]:
        names = sorted(self.presets_data["presets"].keys())
        if not names:
            print("Сохранённых пресетов пока нет.")
        else:
            print("\nСохранённые пресеты:")
            for i, name in enumerate(names, 1):
                marker = " (текущий)" if name == self.current_preset_name else ""
                print(f"  {i}. {name}{marker}")
        return names

    def save_preset(self) -> None:
        name = _input("Имя пресета для сохранения", self.current_preset_name or "")
        if not name:
            print("Имя не может быть пустым.")
            return
        previous = self.presets_data["presets"].get(name)
        self.presets_data["presets"][name] = copy.deepcopy(self.current)
        try:
            config.save_presets(self.presets_data)
        except config.ConfigError as exc:
            # Откатываем изменение в памяти, чтобы не разойтись с содержимым файла.
            if previous is None:
                del self.presets_data["presets"][name]
            else:
                self.presets_data["presets"][name] = previous
            print(f"✘ {exc}")
            return
        self.current_preset_name = name
        print(f"Пресет «{name}» сохранён в presets.json.")

    def load_preset(self) -> None:
        names = self.list_presets()
        if not names:
            return
        choice = _input("Номер или имя пресета для загрузки", "")
        name = self._resolve_preset_name(choice, names)
        if name is None:
            print("Пресет не найден.")
            return
        preset = copy.deepcopy(self.presets_data["presets"][name])
        # Дозаполняем недостающие поля (на случай старого формата пресета).
        merged = make_empty_preset()
        merged.update(preset)
        self.current = merged
        self.current_preset_name = name
        print(f"Пресет «{name}» загружен.")
        self.apply()

    def delete_preset(self) -> None:
        names = self.list_presets()
        if not names:
            return
        choice = _input("Номер или имя пресета для удаления", "")
        name = self._resolve_preset_name(choice, names)
        if name is None:
            print("Пресет не найден.")
            return
        confirm = _input(f"Удалить пресет «{name}»? (да/нет)", "нет")
        if confirm.lower() in ("да", "yes", "y", "д"):
            removed = self.presets_data["presets"].pop(name)
            try:
                config.save_presets(self.presets_data)
            except config.ConfigError as exc:
                self.presets_data["presets"][name] = removed  # откатываем удаление
                print(f"✘ {exc}")
                return
            if self.current_preset_name == name:
                self.current_preset_name = None
            print(f"Пресет «{name}» удалён.")

    @staticmethod
    def _resolve_preset_name(choice: str, names: list[str]) -> str | None:
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            return names[int(choice) - 1]
        if choice in names:
            return choice
        return None

    # ------------------------------------------------------------------ #
    # Настройки и подключение
    # ------------------------------------------------------------------ #

    def edit_settings(self) -> None:
        print(f"\nТекущий Client ID: {self.cfg.get('client_id') or '(не задан)'}")
        new_id = _input("Новый Client ID (application id из Discord Developer Portal)", self.cfg.get("client_id", ""))
        if new_id != self.cfg.get("client_id"):
            previous_id = self.cfg.get("client_id", "")
            self.cfg["client_id"] = new_id
            try:
                config.save_config(self.cfg)
            except config.ConfigError as exc:
                self.cfg["client_id"] = previous_id
                print(f"✘ {exc}")
                return
            self.rpc.set_client_id(new_id)
            print("Client ID сохранён в config.json. Подключение будет установлено при следующем действии.")

    def reconnect(self) -> None:
        self.rpc.disconnect()
        self._run_rpc(self.rpc.connect, "Подключение к Discord установлено.")

    def clear_status(self) -> None:
        self._run_rpc(self.rpc.clear, "Статус очищен.")

    # ------------------------------------------------------------------ #
    # Главное меню
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        print("=== Discord Rich Presence клиент ===")
        if not self.cfg.get("client_id"):
            print("Client ID не задан. Настройте его в пункте меню «Настройки» "
                  "или впишите вручную в config.json.")
        else:
            self.reconnect()

        menu: list[tuple[str, Callable[[], None]]] = [
            ("Показать текущий статус", self.print_status),
            ("Изменить Details (верхняя строка)", self.edit_details),
            ("Изменить State (нижняя строка)", self.edit_state),
            ("Изменить тип активности", self.edit_activity_type),
            ("Изменить большое изображение", self.edit_large_image),
            ("Изменить малое изображение", self.edit_small_image),
            ("Изменить кнопки", self.edit_buttons),
            ("Изменить таймер", self.edit_timer),
            ("Сохранить текущий статус как пресет", self.save_preset),
            ("Загрузить пресет", self.load_preset),
            ("Удалить пресет", self.delete_preset),
            ("Список пресетов", self.list_presets),
            ("Настройки (Client ID)", self.edit_settings),
            ("Переподключиться к Discord", self.reconnect),
            ("Отправить статус повторно", self.apply),
            ("Очистить статус", self.clear_status),
        ]

        while True:
            print("\nМеню:")
            for i, (label, _) in enumerate(menu, 1):
                print(f"  {i}. {label}")
            print("  0. Выход")

            choice = input("Выбор: ").strip()
            if choice == "0":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(menu):
                _, action = menu[int(choice) - 1]
                try:
                    action()
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # неожиданная ошибка — не роняем приложение
                    print(f"✘ Непредвиденная ошибка: {exc}")
            else:
                print("Некорректный выбор.")

        self.rpc.disconnect()
        print("Отключено. До встречи!")
