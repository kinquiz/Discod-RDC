"""
Модуль пользовательского интерфейса (CLI).

Реализует текстовое меню для управления Discord Rich Presence:
- редактирование полей активности "на лету" (каждое изменение сразу
  отправляется в Discord, без перезапуска скрипта);
- управление пресетами (сохранение/загрузка/удаление в presets.json);
- настройки приложения (Client ID, язык интерфейса) в config.json;
- ручное переподключение к Discord.

Все строки интерфейса берутся из локализации через i18n.t() —
см. locales/en.json и locales/ru.json.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import config
import i18n
from i18n import t
from rpc_client import RPCClient, RPCError

ACTIVITY_TYPE_ORDER = ["PLAYING", "LISTENING", "WATCHING", "COMPETING"]

# Ограничения Discord RPC: details/state — максимум 128 символов,
# название кнопки — максимум 32 символа. Проверяем на своей стороне,
# чтобы не узнавать об этом только из невнятной ошибки Discord.
DETAILS_STATE_MAX_LENGTH = 128
BUTTON_LABEL_MAX_LENGTH = 32


def _activity_type_label(key: str) -> str:
    return t(f"activity_type.{key.lower()}")


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
        print(t("error.invalid_integer"))
        return default


class App:
    """Основной класс приложения: хранит состояние и обрабатывает меню."""

    def __init__(self) -> None:
        self.cfg = config.load_config()
        i18n.set_language(self.cfg.get("language", i18n.DEFAULT_LANGUAGE))
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
            print(t("common.success_prefix", message=success_message))
        except RPCError as exc:
            print(t("common.error_prefix", error=exc))

    def apply(self) -> None:
        """Отправляет текущее состояние в Discord и печатает результат/ошибку."""
        self._run_rpc(lambda: self.rpc.update(self.current), t("rpc.status_updated"))

    def print_status(self) -> None:
        p = self.current
        empty = t("common.empty_placeholder")
        print(t("status.header"))
        print(t("status.type", value=_activity_type_label(p["activity_type"])))
        print(t("status.details", value=p["details"] or empty))
        print(t("status.state", value=p["state"] or empty))
        print(t("status.large_image", image=p["large_image"] or empty, text=p["large_text"] or empty))
        print(t("status.small_image", image=p["small_image"] or empty, text=p["small_text"] or empty))
        if p["buttons"]:
            for i, b in enumerate(p["buttons"], 1):
                print(t("status.button_line", n=i, label=b.get("label", ""), url=b.get("url", "")))
        else:
            print(t("status.no_buttons"))
        timer_desc_map = {
            "none": t("timer_desc.off"),
            "elapsed": t("timer_desc.elapsed"),
            "countdown": t("timer_desc.countdown", minutes=p.get("countdown_minutes", 0)),
        }
        timer_desc = timer_desc_map.get(p["timer"], p["timer"])
        print(t("status.timer", desc=timer_desc))
        discord_state = t("common.connected") if self.rpc.connected else t("common.disconnected")
        print(t("status.discord", state=discord_state))
        print(t("status.active_preset", name=self.current_preset_name or t("common.not_saved")))
        print(t("status.footer"))

    # ------------------------------------------------------------------ #
    # Редактирование полей
    # ------------------------------------------------------------------ #

    def edit_details(self) -> None:
        new_value = _input(t("field.details"), self.current["details"])
        if len(new_value) > DETAILS_STATE_MAX_LENGTH:
            print(t("error.details_too_long", max=DETAILS_STATE_MAX_LENGTH, length=len(new_value)))
            return
        self.current["details"] = new_value
        self.apply()

    def edit_state(self) -> None:
        new_value = _input(t("field.state"), self.current["state"])
        if len(new_value) > DETAILS_STATE_MAX_LENGTH:
            print(t("error.state_too_long", max=DETAILS_STATE_MAX_LENGTH, length=len(new_value)))
            return
        self.current["state"] = new_value
        self.apply()

    def edit_activity_type(self) -> None:
        print(t("menu.choose_activity_type"))
        for i, key in enumerate(ACTIVITY_TYPE_ORDER, 1):
            print(f"  {i}. {_activity_type_label(key)}")
        print(t("menu.streaming_not_supported"))
        choice = _input(t("prompt.type_number"), "")
        if choice.isdigit() and 1 <= int(choice) <= len(ACTIVITY_TYPE_ORDER):
            self.current["activity_type"] = ACTIVITY_TYPE_ORDER[int(choice) - 1]
            self.apply()
        else:
            print(t("error.invalid_choice_unchanged"))

    def edit_large_image(self) -> None:
        print(t("hint.large_image_asset"))
        print(t("hint.large_image_url"))
        self.current["large_image"] = _input(t("field.large_image"), self.current["large_image"])
        self.current["large_text"] = _input(t("field.large_text"), self.current["large_text"])
        self.apply()

    def edit_small_image(self) -> None:
        self.current["small_image"] = _input(t("field.small_image"), self.current["small_image"])
        self.current["small_text"] = _input(t("field.small_text"), self.current["small_text"])
        self.apply()

    def edit_buttons(self) -> None:
        print(t("hint.buttons_limit"))
        buttons: list[dict[str, str]] = []
        for i in (1, 2):
            print(t("label.button_header", n=i))
            existing = self.current["buttons"][i - 1] if len(self.current["buttons"]) >= i else {"label": "", "url": ""}
            label = _input(t("field.button_label"), existing.get("label", ""))
            if not label:
                continue
            if len(label) > BUTTON_LABEL_MAX_LENGTH:
                print(t("error.button_label_too_long", max=BUTTON_LABEL_MAX_LENGTH, length=len(label)))
                continue
            url = _input(t("field.button_url"), existing.get("url", ""))
            if not url.startswith(("http://", "https://")):
                print(t("error.button_url_invalid"))
                continue
            buttons.append({"label": label, "url": url})
        self.current["buttons"] = buttons
        self.apply()

    def edit_timer(self) -> None:
        print(t("menu.timer_header"))
        print(t("menu.timer_off"))
        print(t("menu.timer_elapsed"))
        print(t("menu.timer_countdown"))
        choice = _input(t("prompt.choice"), "")
        if choice == "1":
            self.current["timer"] = "none"
        elif choice == "2":
            self.current["timer"] = "elapsed"
        elif choice == "3":
            minutes = _input_int(
                t("field.countdown_minutes"), self.current.get("countdown_minutes", 30) or 30
            )
            if minutes <= 0:
                print(t("error.countdown_minutes_invalid"))
                return
            self.current["timer"] = "countdown"
            self.current["countdown_minutes"] = minutes
        else:
            print(t("error.invalid_choice_unchanged"))
            return
        self.apply()

    # ------------------------------------------------------------------ #
    # Пресеты
    # ------------------------------------------------------------------ #

    def list_presets(self) -> list[str]:
        names = sorted(self.presets_data["presets"].keys())
        if not names:
            print(t("presets.none_saved"))
        else:
            print(t("presets.saved_header"))
            for i, name in enumerate(names, 1):
                marker = t("presets.current_marker") if name == self.current_preset_name else ""
                print(f"  {i}. {name}{marker}")
        return names

    def save_preset(self) -> None:
        name = _input(t("field.preset_name"), self.current_preset_name or "")
        if not name:
            print(t("error.name_empty"))
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
            print(t("common.error_prefix", error=exc))
            return
        self.current_preset_name = name
        print(t("presets.saved", name=name))

    def load_preset(self) -> None:
        names = self.list_presets()
        if not names:
            return
        choice = _input(t("prompt.preset_load"), "")
        name = self._resolve_preset_name(choice, names)
        if name is None:
            print(t("error.preset_not_found"))
            return
        preset = copy.deepcopy(self.presets_data["presets"][name])
        # Дозаполняем недостающие поля (на случай старого формата пресета).
        merged = make_empty_preset()
        merged.update(preset)
        self.current = merged
        self.current_preset_name = name
        print(t("presets.loaded", name=name))
        self.apply()

    def delete_preset(self) -> None:
        names = self.list_presets()
        if not names:
            return
        choice = _input(t("prompt.preset_delete"), "")
        name = self._resolve_preset_name(choice, names)
        if name is None:
            print(t("error.preset_not_found"))
            return
        confirm = _input(t("confirm.delete_preset", name=name), t("common.no"))
        yes_words = {w.strip().lower() for w in t("confirm.yes_words").split(",") if w.strip()}
        if confirm.strip().lower() in yes_words:
            removed = self.presets_data["presets"].pop(name)
            try:
                config.save_presets(self.presets_data)
            except config.ConfigError as exc:
                self.presets_data["presets"][name] = removed  # откатываем удаление
                print(t("common.error_prefix", error=exc))
                return
            if self.current_preset_name == name:
                self.current_preset_name = None
            print(t("presets.deleted", name=name))

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
        print(t("settings.current_client_id", value=self.cfg.get("client_id") or t("common.not_set")))
        new_id = _input(t("field.client_id"), self.cfg.get("client_id", ""))
        if new_id != self.cfg.get("client_id"):
            previous_id = self.cfg.get("client_id", "")
            self.cfg["client_id"] = new_id
            try:
                config.save_config(self.cfg)
            except config.ConfigError as exc:
                self.cfg["client_id"] = previous_id
                print(t("common.error_prefix", error=exc))
                return
            self.rpc.set_client_id(new_id)
            print(t("settings.client_id_saved"))

    def edit_language(self) -> None:
        current_label = t(f"label.language_{i18n.get_language()}")
        print(t("settings.language_current", value=current_label))
        print(t("menu.choose_language"))
        languages = i18n.available_languages()
        for i, code in enumerate(languages, 1):
            print(f"  {i}. {t(f'label.language_{code}')}")
        choice = _input(t("prompt.language_choice"), "")
        if choice.isdigit() and 1 <= int(choice) <= len(languages):
            new_language = languages[int(choice) - 1]
            i18n.set_language(new_language)
            self.cfg["language"] = new_language
            try:
                config.save_config(self.cfg)
            except config.ConfigError as exc:
                print(t("common.error_prefix", error=exc))
                return
            print(t("settings.language_saved"))
        else:
            print(t("error.invalid_choice_unchanged"))

    def reconnect(self) -> None:
        self.rpc.disconnect()
        self._run_rpc(self.rpc.connect, t("rpc.connected_success"))

    def clear_status(self) -> None:
        self._run_rpc(self.rpc.clear, t("rpc.status_cleared"))

    # ------------------------------------------------------------------ #
    # Главное меню
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        print(t("app.title"))
        if not self.cfg.get("client_id"):
            print(t("app.client_id_not_set"))
        else:
            self.reconnect()

        # Ключи, а не готовые переводы: язык можно сменить прямо во время работы
        # (пункт «Language / Язык»), поэтому подписи переводятся заново на каждой
        # итерации цикла — иначе меню осталось бы на старом языке до перезапуска.
        menu: list[tuple[str, Callable[[], None]]] = [
            ("menu.show_status", self.print_status),
            ("menu.edit_details", self.edit_details),
            ("menu.edit_state", self.edit_state),
            ("menu.edit_activity_type", self.edit_activity_type),
            ("menu.edit_large_image", self.edit_large_image),
            ("menu.edit_small_image", self.edit_small_image),
            ("menu.edit_buttons", self.edit_buttons),
            ("menu.edit_timer", self.edit_timer),
            ("menu.save_preset", self.save_preset),
            ("menu.load_preset", self.load_preset),
            ("menu.delete_preset", self.delete_preset),
            ("menu.list_presets", self.list_presets),
            ("menu.settings", self.edit_settings),
            ("menu.language", self.edit_language),
            ("menu.reconnect", self.reconnect),
            ("menu.resend_status", self.apply),
            ("menu.clear_status", self.clear_status),
        ]

        while True:
            print(t("menu.header"))
            for i, (label_key, _) in enumerate(menu, 1):
                print(f"  {i}. {t(label_key)}")
            print(f"  0. {t('menu.exit')}")

            choice = input(f"{t('prompt.choice')}: ").strip()
            if choice == "0":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(menu):
                _, action = menu[int(choice) - 1]
                try:
                    action()
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # неожиданная ошибка — не роняем приложение
                    print(t("common.error_prefix", error=t("error.unexpected", error=exc)))
            else:
                print(t("error.invalid_choice"))

        self.rpc.disconnect()
        print(t("app.disconnected_bye"))
