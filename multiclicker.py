"""
Wel's Toolbox - Systeme modulaire d'automatisation de clics/touches
--------------------------------------------------------------------
Systemes :
  1. Clic Alterné       - alterne clic gauche/droit le plus vite possible
  2. Auto Clic          - spam une touche/bouton en boucle, cadence réglable
  3. Maintien            - appuie et garde une touche/bouton enfoncé
  4. Anti-AFK             - bouge la souris ou appuie une touche périodiquement

Déclencheurs : touche clavier OU bouton souris (y compris boutons
latéraux "pouce" et molette). Échap = arrêt d'urgence de tout, réservé.

Profils : sauvegarde/charge des configurations complètes nommées.

Jeu "Rouages" : mini-jeu incrémental (clic, générateurs, améliorations,
index de succès, rebirth) qui progresse aussi via l'usage réel de l'app.

Pour ajouter un nouveau système d'automatisation plus tard : crée une
classe héritant de ClickModule et ajoute-la à self.modules.
"""

import json
import os
import sys
import subprocess
import threading
import time
import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from pynput import mouse, keyboard

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROFILES_FILE = os.path.join(BASE_DIR, "profiles.json")
GAME_FILE = os.path.join(BASE_DIR, "game_save.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

STARTUP_FOLDER = os.path.join(os.environ.get("APPDATA", BASE_DIR), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_BAT_NAME = "MultiClicker_AutoStart.bat"

# ---- Themes disponibles dans les parametres ----
# "wels_dark"/"wels_light" sont generes a partir des themes integres darkly/flatly
# (voir register_wels_themes) avec l'accent recolore en orange. Les autres sont des
# themes integres a ttkbootstrap, geres tels quels (pas de code couleur Wel's impose).
THEME_LABELS = {
    "wels_dark": "Wel's (Sombre)",
    "wels_light": "Wel's (Clair)",
    "darkly": "Autre - Sombre bleu",
    "flatly": "Autre - Clair neutre",
    "cyborg": "Autre - Cyborg",
    "minty": "Autre - Clair vert",
}
AVAILABLE_THEMES = list(THEME_LABELS.keys())


# ---- Themes "Wel's" = les themes sombre/clair d'origine, juste l'accent bleu remplace par de l'orange ----
ACCENT_ORANGE = "#FF7A1A"
ACCENT_TEXT = "#1E1A16"


def clone_with_orange_accent(style, base_theme, new_name, new_type):
    """Reprend un theme integre existant tel quel (fonds, gris, etc.) et ne change
    que la couleur d'accent primaire/selection (bleu -> orange)."""
    from ttkbootstrap.style import ThemeDefinition, Colors
    style.theme_use(base_theme)
    b = style.colors
    colors = Colors(
        primary=ACCENT_ORANGE,
        secondary=b.secondary,
        success=b.success,
        info=b.info,
        warning=b.warning,
        danger=b.danger,
        bg=b.bg,
        fg=b.fg,
        selectbg=ACCENT_ORANGE,
        selectfg=ACCENT_TEXT,
        border=b.border,
        inputfg=b.inputfg,
        inputbg=b.inputbg,
        light=b.light,
        dark=b.dark,
        active=b.active,
    )
    return ThemeDefinition(name=new_name, themetype=new_type, colors=colors)


def register_wels_themes(style):
    """Enregistre les variantes Wel's. Renvoie True si au moins une a reussi.
    Tout en try/except : si l'API n'est pas compatible, l'app continue quand meme
    (repli automatique sur un theme integre standard)."""
    try:
        from ttkbootstrap.style import ThemeDefinition, Colors  # noqa: F401 (verifie juste la disponibilite)
    except Exception as e:
        print("Themes Wel's indisponibles (API ttkbootstrap incompatible):", e)
        return False

    ok = False
    try:
        style.register_theme(clone_with_orange_accent(style, "darkly", "wels_dark", "dark"))
        ok = True
    except Exception as e:
        print("Erreur creation wels_dark:", e)
    try:
        style.register_theme(clone_with_orange_accent(style, "flatly", "wels_light", "light"))
        ok = True
    except Exception as e:
        print("Erreur creation wels_light:", e)
    return ok


def load_app_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults = {"theme": "wels_dark", "toasts_enabled": True}
                defaults.update(data)
                return defaults
        except Exception:
            pass
    return {"theme": "wels_dark", "toasts_enabled": True}


def save_app_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Erreur sauvegarde settings:", e)


def is_startup_enabled():
    return os.path.exists(os.path.join(STARTUP_FOLDER, STARTUP_BAT_NAME))


def set_startup_enabled(enabled):
    path = os.path.join(STARTUP_FOLDER, STARTUP_BAT_NAME)
    if enabled:
        script_path = os.path.join(BASE_DIR, "multiclicker.py")
        content = f'@echo off\ncd /d "{BASE_DIR}"\nstart "" pythonw "{script_path}"\n'
        os.makedirs(STARTUP_FOLDER, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        if os.path.exists(path):
            os.remove(path)

# ---- Mise a jour automatique via GitHub ----
APP_VERSION = "1.3.1"
GITHUB_USER = "PolarAct"         # <-- ton pseudo GitHub
GITHUB_REPO = "multi-clicker"    # <-- le nom de ton depot
GITHUB_BRANCH = "main"
VERSION_CHECK_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/version.json"
SCRIPT_UPDATE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/multiclicker.py"

mouse_controller = mouse.Controller()
keyboard_controller = keyboard.Controller()

MOUSE_BUTTON_MAP = {
    "left": mouse.Button.left,
    "right": mouse.Button.right,
    "middle": mouse.Button.middle,
}
for _name in ("x1", "x2"):
    if hasattr(mouse.Button, _name):
        MOUSE_BUTTON_MAP[_name] = getattr(mouse.Button, _name)

MOUSE_LABELS = {
    "left": "Clic Gauche",
    "right": "Clic Droit",
    "middle": "Clic Molette",
    "x1": "Bouton Pouce (arrière)",
    "x2": "Bouton Pouce (avant)",
}

RESERVED_IDENTIFIER = "KEY:Key.esc"

MODULE_ICONS = {
    "Clic Alterné": "🖱️",
    "Auto Clic": "🔫",
    "Maintien": "✋",
    "Anti-AFK": "💤",
}

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1548772612438757567/nJ-vt9zWLeQ4azYb97H_T-CTDBJE1ri8pOuYjEAGg5PEYO3gqclDJtAt7xLjPqWOPs_D"
DISCORD_USER_ID = "1053781308851097742"  # wel_lb


def send_discord_message(content):
    """Envoie un message stylé (embed) au salon Discord relié au webhook, avec un vrai ping de l'utilisateur.
    Leve une exception (avec message clair) en cas d'echec."""
    import requests
    from datetime import datetime, timezone

    payload = {
        "content": f"<@{DISCORD_USER_ID}>",
        "allowed_mentions": {"users": [DISCORD_USER_ID]},
        "embeds": [
            {
                "title": "📩 Nouveau message — Wel's Toolbox",
                "description": content[:4000],
                "color": 0x5865F2,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Envoyé depuis l'onglet Aide & Suggestions"},
            }
        ],
    }
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.status_code


# ----------------------------------------------------------------------
# UTILITAIRES - identifiants unifiés touche/bouton
# ----------------------------------------------------------------------
def key_identifier(key):
    try:
        if key.char is not None:
            return f"KEY:{key.char}"
    except AttributeError:
        pass
    return f"KEY:{key}"


def mouse_identifier(button):
    return f"MOUSE:{button.name}"


def display_name(identifier):
    if not identifier:
        return "Aucune"
    kind, _, value = identifier.partition(":")
    if kind == "MOUSE":
        return MOUSE_LABELS.get(value, f"Souris {value}")
    if value.startswith("Key."):
        return value.replace("Key.", "").upper()
    return value


def parse_keyboard_value(value):
    if value.startswith("Key."):
        name = value[len("Key."):]
        return getattr(keyboard.Key, name)
    return value


def perform_action_click(identifier):
    kind, _, value = identifier.partition(":")
    if kind == "MOUSE":
        btn = MOUSE_BUTTON_MAP.get(value)
        if btn is not None:
            mouse_controller.click(btn)
    else:
        k = parse_keyboard_value(value)
        keyboard_controller.press(k)
        keyboard_controller.release(k)


def perform_action_press(identifier):
    kind, _, value = identifier.partition(":")
    if kind == "MOUSE":
        btn = MOUSE_BUTTON_MAP.get(value)
        if btn is not None:
            mouse_controller.press(btn)
    else:
        keyboard_controller.press(parse_keyboard_value(value))


def perform_action_release(identifier):
    kind, _, value = identifier.partition(":")
    if kind == "MOUSE":
        btn = MOUSE_BUTTON_MAP.get(value)
        if btn is not None:
            mouse_controller.release(btn)
    else:
        keyboard_controller.release(parse_keyboard_value(value))


def format_number(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n < 1000:
        return f"{n:.0f}" if n == int(n) else f"{n:.1f}"
    for unit in ["K", "M", "B", "T", "Qa", "Qi"]:
        n /= 1000.0
        if n < 1000:
            return f"{n:.2f}{unit}"
    return f"{n:.2f}Sx"


# ----------------------------------------------------------------------
# CLASSE DE BASE - tous les systemes d'automatisation en heritent
# ----------------------------------------------------------------------
class ClickModule:
    def __init__(self, name, app):
        self.name = name
        self.app = app
        self.active = False
        self.hotkey = None
        self.thread = None
        self._stop_event = threading.Event()

    def toggle(self):
        if self.active:
            self.stop()
        else:
            self.start()

    def start(self):
        self.active = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._safe_run, daemon=True)
        self.thread.start()
        self.app.on_module_state_change(self)

    def stop(self):
        self.active = False
        self._stop_event.set()
        self.app.on_module_state_change(self)

    def unassign_hotkey(self):
        if self.active:
            self.stop()
        self.hotkey = None

    def driven_identifiers(self):
        return set()

    def _safe_run(self):
        try:
            self.run()
        except Exception as e:
            print(f"[{self.name}] erreur : {e}")

    def run(self):
        raise NotImplementedError

    def to_dict(self):
        return {"hotkey": self.hotkey}

    def from_dict(self, data):
        self.hotkey = data.get("hotkey")


# ----------------------------------------------------------------------
# SYSTEME 1 : Clic alterne gauche/droite
# ----------------------------------------------------------------------
class AlternateClickModule(ClickModule):
    def __init__(self, app):
        super().__init__("Clic Alterné", app)
        self.delay_ms = 1

    def run(self):
        left = True
        while not self._stop_event.is_set():
            mouse_controller.click(mouse.Button.left if left else mouse.Button.right)
            self.app.register_real_action()
            left = not left
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000)

    def driven_identifiers(self):
        return {"MOUSE:left", "MOUSE:right"}

    def to_dict(self):
        d = super().to_dict()
        d["delay_ms"] = self.delay_ms
        return d

    def from_dict(self, data):
        super().from_dict(data)
        self.delay_ms = data.get("delay_ms", 1)


# ----------------------------------------------------------------------
# SYSTEME 2 : Auto clic (touche clavier OU bouton souris)
# ----------------------------------------------------------------------
class AutoClickModule(ClickModule):
    def __init__(self, app):
        super().__init__("Auto Clic", app)
        self.action_id = "MOUSE:left"
        self.delay_ms = 50

    def run(self):
        while not self._stop_event.is_set():
            perform_action_click(self.action_id)
            self.app.register_real_action()
            time.sleep(max(self.delay_ms, 1) / 1000)

    def driven_identifiers(self):
        return {self.action_id}

    def to_dict(self):
        d = super().to_dict()
        d["action_id"] = self.action_id
        d["delay_ms"] = self.delay_ms
        return d

    def from_dict(self, data):
        super().from_dict(data)
        if "action_id" in data:
            self.action_id = data["action_id"]
        elif "button" in data:
            self.action_id = f"MOUSE:{data['button']}"
        self.delay_ms = data.get("delay_ms", self.delay_ms)


# ----------------------------------------------------------------------
# SYSTEME 3 : Maintien (touche clavier OU bouton souris)
# ----------------------------------------------------------------------
class HoldModule(ClickModule):
    def __init__(self, app):
        super().__init__("Maintien", app)
        self.action_id = "MOUSE:left"

    def start(self):
        perform_action_press(self.action_id)
        self.app.register_real_action()
        self.active = True
        self.app.on_module_state_change(self)

    def stop(self):
        perform_action_release(self.action_id)
        self.active = False
        self.app.on_module_state_change(self)

    def run(self):
        pass

    def driven_identifiers(self):
        return {self.action_id}

    def to_dict(self):
        d = super().to_dict()
        d["action_id"] = self.action_id
        return d

    def from_dict(self, data):
        super().from_dict(data)
        if "action_id" in data:
            self.action_id = data["action_id"]
        elif "button" in data:
            self.action_id = f"MOUSE:{data['button']}"


# ----------------------------------------------------------------------
# SYSTEME 4 : Anti-AFK
# ----------------------------------------------------------------------
class AntiAFKModule(ClickModule):
    def __init__(self, app):
        super().__init__("Anti-AFK", app)
        self.interval_sec = 60
        self.mode = "mouse"  # "mouse" ou "key"
        self.action_id = "KEY:Key.shift"

    def run(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.interval_sec):
                break
            if self.mode == "mouse":
                mouse_controller.move(4, 0)
                time.sleep(0.05)
                mouse_controller.move(-4, 0)
            else:
                perform_action_click(self.action_id)
            self.app.register_real_action()

    def driven_identifiers(self):
        if self.mode == "key":
            return {self.action_id}
        return set()

    def to_dict(self):
        d = super().to_dict()
        d["interval_sec"] = self.interval_sec
        d["mode"] = self.mode
        d["action_id"] = self.action_id
        return d

    def from_dict(self, data):
        super().from_dict(data)
        self.interval_sec = data.get("interval_sec", self.interval_sec)
        self.mode = data.get("mode", self.mode)
        self.action_id = data.get("action_id", self.action_id)


# ----------------------------------------------------------------------
# PROFILS - sauvegarde/chargement de configurations completes
# ----------------------------------------------------------------------
def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        return {}
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_profiles(profiles):
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Erreur sauvegarde profils:", e)


# ----------------------------------------------------------------------
# JEU "ROUAGES" - mini jeu incrémental (clic, generateurs, index, rebirth)
# ----------------------------------------------------------------------
GENERATORS = [
    {"id": "stagiaire", "name": "Stagiaire Motivé", "icon": "🧑‍💼", "base_cost": 15, "base_prod": 0.1},
    {"id": "robot", "name": "Robot Clique-Bouton", "icon": "🤖", "base_cost": 100, "base_prod": 1},
    {"id": "script", "name": "Script Automatisé", "icon": "📜", "base_cost": 1100, "base_prod": 8},
    {"id": "serveur", "name": "Serveur Dédié", "icon": "🖥️", "base_cost": 12000, "base_prod": 47},
    {"id": "datacenter", "name": "Datacenter", "icon": "🏢", "base_cost": 130000, "base_prod": 260},
    {"id": "ia", "name": "IA Autonome", "icon": "🧠", "base_cost": 1400000, "base_prod": 1400},
]

UPGRADES = [
    {"id": "click1", "name": "Clic Renforcé I", "desc": "+1 Rouage par clic manuel.",
     "cost": 100, "type": "click", "value": 1},
    {"id": "click2", "name": "Clic Renforcé II", "desc": "+3 Rouages par clic manuel.",
     "cost": 5000, "type": "click", "value": 3},
    {"id": "stagiaire_boost", "name": "Stagiaires Motivés", "desc": "x2 production des Stagiaires. (5 requis)",
     "cost": 500, "type": "generator_mult", "target": "stagiaire", "value": 2, "requires_owned": 5},
    {"id": "serveur_boost", "name": "Optimisation Serveurs", "desc": "x2 production des Serveurs Dédiés. (5 requis)",
     "cost": 50000, "type": "generator_mult", "target": "serveur", "value": 2, "requires_owned": 5},
]

ACHIEVEMENTS = [
    {"id": "first_click", "name": "Premier Clic", "icon": "👆",
     "desc": "Clique une fois manuellement.", "check": lambda s: s["manual_clicks"] >= 1},
    {"id": "gears_100", "name": "Petit Tas", "icon": "⚙️",
     "desc": "Accumule 100 Rouages au total.", "check": lambda s: s["total_gears_earned"] >= 100},
    {"id": "gears_1000", "name": "Belle Réserve", "icon": "⚙️",
     "desc": "Accumule 1 000 Rouages au total.", "check": lambda s: s["total_gears_earned"] >= 1000},
    {"id": "gears_100000", "name": "Petite Fortune", "icon": "💰",
     "desc": "Accumule 100 000 Rouages au total.", "check": lambda s: s["total_gears_earned"] >= 100000},
    {"id": "gears_1000000", "name": "Magnat", "icon": "🏆",
     "desc": "Accumule 1 000 000 Rouages au total.", "check": lambda s: s["total_gears_earned"] >= 1000000},
    {"id": "one_gen", "name": "Premier Employé", "icon": "🧑‍💼",
     "desc": "Possède au moins 1 générateur.", "check": lambda s: sum(s["generators"].values()) >= 1},
    {"id": "ten_gen", "name": "Petite Équipe", "icon": "👥",
     "desc": "Possède au moins 10 générateurs au total.", "check": lambda s: sum(s["generators"].values()) >= 10},
    {"id": "all_gen", "name": "Collection Complète", "icon": "📦",
     "desc": "Possède au moins 1 de chaque générateur.",
     "check": lambda s: all(s["generators"].get(g["id"], 0) >= 1 for g in GENERATORS)},
    {"id": "real_100", "name": "Utilisateur Assidu", "icon": "🖱️",
     "desc": "L'app a effectué 100 clics/actions réels.", "check": lambda s: s["real_actions_total"] >= 100},
    {"id": "real_10000", "name": "Machine Bien Huilée", "icon": "⚡",
     "desc": "L'app a effectué 10 000 clics/actions réels.", "check": lambda s: s["real_actions_total"] >= 10000},
    {"id": "first_rebirth", "name": "Renaissance", "icon": "✨",
     "desc": "Effectue ton premier Rebirth.", "check": lambda s: s["rebirths"] >= 1},
    {"id": "five_rebirth", "name": "Cycle Éternel", "icon": "🌀",
     "desc": "Effectue 5 Rebirths.", "check": lambda s: s["rebirths"] >= 5},
]


def default_game_state():
    return {
        "gears": 0.0,
        "total_gears_earned": 0.0,
        "manual_clicks": 0,
        "real_actions_total": 0,
        "real_actions_pending": 0,
        "generators": {g["id"]: 0 for g in GENERATORS},
        "upgrades_bought": [],
        "achievements_unlocked": [],
        "shards": 0,
        "rebirths": 0,
    }


class GameState:
    def __init__(self, app):
        self.app = app
        self.data = default_game_state()
        self.load()

    def load(self):
        if not os.path.exists(GAME_FILE):
            return
        try:
            with open(GAME_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            base = default_game_state()
            base.update(saved)
            base["generators"] = {**default_game_state()["generators"], **saved.get("generators", {})}
            self.data = base
        except Exception as e:
            print("Erreur chargement jeu:", e)

    def save(self):
        try:
            with open(GAME_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Erreur sauvegarde jeu:", e)

    def multiplier(self):
        return 1 + self.data["shards"] * 0.02

    def click_power(self):
        bonus = sum(u["value"] for u in UPGRADES if u["type"] == "click" and u["id"] in self.data["upgrades_bought"])
        return (1 + bonus) * self.multiplier()

    def generator_production(self, gen):
        owned = self.data["generators"].get(gen["id"], 0)
        if owned <= 0:
            return 0.0
        mult = 1.0
        for u in UPGRADES:
            if u["type"] == "generator_mult" and u["target"] == gen["id"] and u["id"] in self.data["upgrades_bought"]:
                mult *= u["value"]
        return owned * gen["base_prod"] * mult

    def total_production(self):
        return sum(self.generator_production(g) for g in GENERATORS) * self.multiplier()

    def generator_cost(self, gen):
        owned = self.data["generators"].get(gen["id"], 0)
        return gen["base_cost"] * (1.15 ** owned)

    def _add_gears(self, amount):
        self.data["gears"] += amount
        self.data["total_gears_earned"] += amount

    def manual_click(self):
        gain = self.click_power()
        self._add_gears(gain)
        self.data["manual_clicks"] += 1
        return gain

    def buy_generator(self, gen_id):
        gen = next(g for g in GENERATORS if g["id"] == gen_id)
        cost = self.generator_cost(gen)
        if self.data["gears"] >= cost:
            self.data["gears"] -= cost
            self.data["generators"][gen_id] = self.data["generators"].get(gen_id, 0) + 1
            return True
        return False

    def can_buy_upgrade(self, up):
        if up["id"] in self.data["upgrades_bought"]:
            return False
        if self.data["gears"] < up["cost"]:
            return False
        if "requires_owned" in up and self.data["generators"].get(up.get("target"), 0) < up["requires_owned"]:
            return False
        return True

    def buy_upgrade(self, up_id):
        up = next(u for u in UPGRADES if u["id"] == up_id)
        if self.can_buy_upgrade(up):
            self.data["gears"] -= up["cost"]
            self.data["upgrades_bought"].append(up_id)
            return True
        return False

    def potential_shard_gain(self):
        available = int(self.data["total_gears_earned"] // 1_000_000)
        return max(0, available - self.data["shards"])

    def do_rebirth(self):
        gain = self.potential_shard_gain()
        if gain <= 0:
            return 0
        self.data["shards"] += gain
        self.data["rebirths"] += 1
        self.data["gears"] = 0.0
        self.data["generators"] = {g["id"]: 0 for g in GENERATORS}
        self.data["upgrades_bought"] = []
        return gain

    def register_real_action(self):
        self.data["real_actions_total"] += 1
        self.data["real_actions_pending"] += 1

    def tick(self, dt):
        prod = self.total_production()
        if prod > 0 and dt > 0:
            self._add_gears(prod * dt)

        pending = self.data["real_actions_pending"]
        if pending > 0:
            converted = min(pending, 200)  # plafond anti-abus par tick
            self._add_gears(converted * 0.5 * self.multiplier())
            self.data["real_actions_pending"] = 0

        newly = []
        for ach in ACHIEVEMENTS:
            if ach["id"] not in self.data["achievements_unlocked"] and ach["check"](self.data):
                self.data["achievements_unlocked"].append(ach["id"])
                newly.append(ach)
        return newly


# ----------------------------------------------------------------------
# APPLICATION / INTERFACE
# ----------------------------------------------------------------------
class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wel's Toolbox")
        self.root.geometry("680x780")
        self.root.resizable(False, False)

        self.capture_target = None
        self.status_widgets = {}
        self.hotkey_labels = {}
        self.action_labels = {}
        self._game_save_counter = 0
        self.settings = load_app_settings()

        self._load_icons()

        # ---> Pour ajouter un nouveau systeme d'automatisation, ajoute-le ici <---
        self.modules = [
            AlternateClickModule(self),
            AutoClickModule(self),
            HoldModule(self),
            AntiAFKModule(self),
        ]

        self.load_config()
        self.game = GameState(self)

        self.build_ui()

        self.kb_listener = keyboard.Listener(on_press=self.on_key_press)
        self.kb_listener.start()
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        self.mouse_listener.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(1000, self.game_loop_tick)
        self.root.after(30000, self.autosave_loop)
        self.root.after(3000, lambda: self.check_for_updates(manual=False))

    def _load_icons(self):
        """Charge le logo (plume orange) pour la barre de titre Windows et pour le header de l'app."""
        icon_path = os.path.join(BASE_DIR, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print("Erreur chargement icone fenetre:", e)

        header_icon_path = os.path.join(BASE_DIR, "icon_header.png")
        self._header_icon = None
        if os.path.exists(header_icon_path):
            try:
                self._header_icon = tk.PhotoImage(file=header_icon_path)
            except Exception as e:
                print("Erreur chargement icone header:", e)
                self._header_icon = None

    # ================= UI GENERALE =================
    def build_ui(self):
        self.apply_notebook_style()
        self.always_on_top = False
        self.compact_mode = False
        self.compact_panel = None
        self.compact_rows = {}
        self._normal_geometry = "680x780"

        header = tb.Frame(self.root, bootstyle="dark")
        header.pack(fill="x")
        title_row = tb.Frame(header, bootstyle="dark")
        title_row.pack(fill="x", padx=20, pady=(18, 0))

        title_left = tb.Frame(title_row, bootstyle="dark")
        title_left.pack(side="left")
        if self._header_icon is not None:
            tb.Label(title_left, image=self._header_icon, bootstyle="inverse-dark").pack(side="left", padx=(0, 10))
        title_text_col = tb.Frame(title_left, bootstyle="dark")
        title_text_col.pack(side="left")
        tb.Label(title_text_col, text="Wel's", font=("Segoe UI", 20, "bold"),
                  bootstyle="inverse-dark").pack(anchor="w")
        tb.Label(title_text_col, text="TOOLBOX", font=("Segoe UI", 9, "bold"),
                  bootstyle="inverse-dark").pack(anchor="w")

        header_btn_row = tb.Frame(title_row, bootstyle="dark")
        header_btn_row.pack(side="right")
        self.compact_btn = tb.Button(header_btn_row, text="🗗", width=3, bootstyle="outline-secondary",
                                       command=self.toggle_compact_mode)
        self.compact_btn.pack(side="left", padx=(0, 6))
        self.pin_btn = tb.Button(header_btn_row, text="📌", width=3, bootstyle="outline-secondary",
                                   command=self.toggle_always_on_top)
        self.pin_btn.pack(side="left", padx=(0, 6))
        tb.Button(header_btn_row, text="Vérifier les mises à jour", bootstyle="outline-primary",
                   command=lambda: self.check_for_updates(manual=True)).pack(side="left")

        tb.Label(header, text=f"Système modulaire d'automatisation de clics et de touches • v{APP_VERSION}",
                  font=("Segoe UI", 10), bootstyle="inverse-dark").pack(anchor="w", padx=20, pady=(6, 16))

        self.notebook = tb.Notebook(self.root, bootstyle="dark")
        self.notebook.pack(fill="both", expand=True, padx=16, pady=16)
        self.populate_notebook()

        self.footer = tb.Frame(self.root)
        self.footer.pack(fill="x", padx=16, pady=(0, 14))
        tb.Label(self.footer, text="Échap = arrêt d'urgence de tous les systèmes actifs",
                  font=("Segoe UI", 8, "bold"), bootstyle="light").pack(side="left")
        tb.Button(self.footer, text="Réinitialiser toutes les touches", bootstyle="outline-secondary",
                   command=self.reset_all_hotkeys).pack(side="right")

    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        self.pin_btn.config(bootstyle="primary" if self.always_on_top else "outline-secondary")

    def toggle_compact_mode(self):
        self.compact_mode = not self.compact_mode
        self.compact_btn.config(bootstyle="primary" if self.compact_mode else "outline-secondary")
        if self.compact_mode:
            self._normal_geometry = self.root.geometry()
            self.notebook.pack_forget()
            self.footer.pack_forget()
            if self.compact_panel is None:
                self.build_compact_panel()
            self.refresh_compact_panel()
            self.compact_panel.pack(fill="both", expand=True, padx=16, pady=(0, 16))
            self.root.geometry("320x300")
        else:
            if self.compact_panel is not None:
                self.compact_panel.pack_forget()
            self.notebook.pack(fill="both", expand=True, padx=16, pady=16)
            self.footer.pack(fill="x", padx=16, pady=(0, 14))
            self.root.geometry(self._normal_geometry)

    def build_compact_panel(self):
        self.compact_panel = tb.Frame(self.root)
        tb.Label(self.compact_panel, text="Automatisations", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        self.compact_rows = {}
        for module in self.modules:
            row = tb.Frame(self.compact_panel)
            row.pack(fill="x", pady=3)
            icon = MODULE_ICONS.get(module.name, "⚙️")
            tb.Label(row, text=f"{icon} {module.name}", font=("Segoe UI", 9)).pack(side="left")
            badge = tb.Label(row, text="Actif" if module.active else "Inactif",
                               bootstyle="primary-inverse" if module.active else "secondary-inverse",
                               font=("Segoe UI", 8, "bold"), padding=(6, 2))
            badge.pack(side="right")
            tb.Button(row, text="⏻", width=3, bootstyle="outline-primary",
                       command=lambda m=module: m.toggle()).pack(side="right", padx=(0, 6))
            self.compact_rows[module] = badge

    def refresh_compact_panel(self):
        if not self.compact_rows:
            return
        for module, badge in self.compact_rows.items():
            if module.active:
                badge.config(text="Actif", bootstyle="primary-inverse")
            else:
                badge.config(text="Inactif", bootstyle="secondary-inverse")

    def apply_notebook_style(self):
        """Met en valeur l'onglet actuellement selectionne (fond colore = couleur primaire
        du theme actif), quel que soit le notebook (principal ou sous-notebooks). Supprime
        aussi l'anneau de focus par defaut de Tk (qui encadrait tout le contenu en orange
        et faisait mal rendre le texte des onglets)."""
        try:
            style = self.root.style
            colors = style.colors
            style.configure(".", focuscolor=colors.bg)
            style.configure("TNotebook", focuscolor=colors.bg, borderwidth=0)
            style.configure("TNotebook.Tab", padding=(14, 8), focuscolor=colors.bg)
            style.map("TNotebook.Tab",
                      background=[("selected", colors.primary)],
                      foreground=[("selected", colors.selectfg)])
        except Exception as e:
            print("Erreur style onglets (non bloquant):", e)

    def _ensure_scrollbar_style(self):
        """Cree une fois un style de scrollbar fin et gris neutre (independant de l'accent orange)."""
        if getattr(self, "_scrollbar_style_ready", False):
            return
        try:
            style = self.root.style
            colors = style.colors
            style.configure("Wels.Vertical.TScrollbar",
                              troughcolor=colors.bg, background=colors.border,
                              bordercolor=colors.bg, arrowsize=10, width=8, relief="flat")
            style.map("Wels.Vertical.TScrollbar", background=[("active", colors.secondary)])
            self._scrollbar_style_ready = True
        except Exception as e:
            print("Erreur style scrollbar:", e)

    def make_scrollable(self, parent):
        """Enveloppe un contenu dans une zone qui defile verticalement, mais UNIQUEMENT si
        le contenu depasse effectivement la hauteur visible. La barre est fine, grise, et ne
        s'affiche que pendant le defilement (molette ou glisser), puis disparait apres 2s
        d'inactivite. Renvoie le frame interieur dans lequel construire le contenu normalement."""
        self._ensure_scrollbar_style()
        try:
            bg = self.root.style.colors.bg
        except Exception:
            bg = None

        canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
        if bg:
            canvas.configure(bg=bg)
        scrollbar = tb.Scrollbar(parent, orient="vertical", command=canvas.yview,
                                   style="Wels.Vertical.TScrollbar")
        inner = tb.Frame(canvas)

        state = {"visible": False, "needs_scroll": False, "hide_job": None}

        def hide_scrollbar():
            if state["visible"]:
                scrollbar.pack_forget()
                state["visible"] = False
            state["hide_job"] = None

        def show_scrollbar():
            if not state["needs_scroll"]:
                return
            if not state["visible"]:
                scrollbar.pack(side="right", fill="y")
                state["visible"] = True
            if state["hide_job"]:
                canvas.after_cancel(state["hide_job"])
            state["hide_job"] = canvas.after(2000, hide_scrollbar)

        def update_scrollregion(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            content_h = inner.winfo_reqheight()
            visible_h = canvas.winfo_height()
            state["needs_scroll"] = content_h > visible_h
            if not state["needs_scroll"]:
                hide_scrollbar()

        inner.bind("<Configure>", update_scrollregion)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_configure(e):
            canvas.itemconfig(window_id, width=e.width)
            update_scrollregion()
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(ev):
            if not state["needs_scroll"]:
                return
            canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")
            show_scrollbar()

        def _on_enter(_e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_leave(_e):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)
        scrollbar.bind("<Button-1>", lambda e: state["hide_job"] and canvas.after_cancel(state["hide_job"]))
        scrollbar.bind("<ButtonRelease-1>", lambda e: show_scrollbar())

        canvas.pack(side="left", fill="both", expand=True)
        # La scrollbar n'est PAS empaquetee ici : elle n'apparait que si besoin (voir show_scrollbar)
        return inner

    def populate_notebook(self):
        for tab_id in self.notebook.tabs():
            self.notebook.nametowidget(tab_id).destroy()

        self.status_widgets = {}
        self.hotkey_labels = {}
        self.action_labels = {}

        automation_frame = tb.Frame(self.notebook, padding=(12, 12))
        self.notebook.add(automation_frame, text="  🖱️ Automatisation  ")
        self.build_automation_section(automation_frame)

        profiles_frame = tb.Frame(self.notebook, padding=20)
        self.notebook.add(profiles_frame, text="  📂 Profils  ")
        self.build_profiles_tab(profiles_frame)

        game_frame = tb.Frame(self.notebook, padding=16)
        self.notebook.add(game_frame, text="  🎮 Rouages  ")
        self.build_game_tab(game_frame)

        feedback_frame = tb.Frame(self.notebook, padding=20)
        self.notebook.add(feedback_frame, text="  💬 Aide  ")
        self.build_feedback_tab(feedback_frame)

        settings_frame = tb.Frame(self.notebook, padding=20)
        self.notebook.add(settings_frame, text="  ⚙️ Paramètres  ")
        self.build_settings_tab(settings_frame)

        future_frame = tb.Frame(self.notebook, padding=20)
        self.notebook.add(future_frame, text="  + Ajouter  ")
        tb.Label(future_frame, text="D'autres systèmes pourront être ajoutés ici plus tard.",
                  font=("Segoe UI", 10), bootstyle="secondary", justify="center").pack(pady=60)

    def build_automation_section(self, parent):
        tb.Label(parent, text="Systèmes d'automatisation", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 4))
        tb.Label(parent, text="Active/désactive chaque système avec son déclencheur assigné, "
                              "à tout moment pendant que tu joues ou travailles.",
                  font=("Segoe UI", 9), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(0, 10))

        sub_notebook = tb.Notebook(parent, bootstyle="dark")
        sub_notebook.pack(fill="both", expand=True)

        for module in self.modules:
            frame = tb.Frame(sub_notebook, padding=20)
            icon = MODULE_ICONS.get(module.name, "⚙️")
            sub_notebook.add(frame, text=f"  {icon} {module.name}  ")
            self.build_module_ui(frame, module)

    # ================= TABS DES SYSTEMES =================
    def build_module_ui(self, frame, module):
        top = tb.Frame(frame)
        top.pack(fill="x")
        icon = MODULE_ICONS.get(module.name, "⚙️")
        tb.Label(top, text=f"{icon} {module.name}", font=("Segoe UI", 15, "bold")).pack(side="left")

        status_badge = tb.Label(top, text="Inactif", bootstyle="secondary-inverse",
                                  font=("Segoe UI", 9, "bold"), padding=(10, 3))
        status_badge.pack(side="right")
        self.status_widgets[module] = status_badge

        tb.Separator(frame).pack(fill="x", pady=14)

        body = self.make_scrollable(frame)

        hk_card = tb.Frame(body, bootstyle="secondary")
        hk_card.pack(fill="x", pady=(0, 16))
        hk_inner = tb.Frame(hk_card, padding=12)
        hk_inner.pack(fill="x")

        tb.Label(hk_inner, text="Déclencheur (touche clavier ou bouton souris)",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor="w")
        hk_value_label = tb.Label(hk_inner, text=display_name(module.hotkey),
                                    font=("Segoe UI", 14, "bold"),
                                    bootstyle="light" if module.hotkey else "secondary")
        hk_value_label.pack(anchor="w", pady=(2, 10))
        self.hotkey_labels[module] = hk_value_label

        btn_row = tb.Frame(hk_inner)
        btn_row.pack(fill="x")
        tb.Button(btn_row, text="Assigner...", bootstyle="primary",
                   command=lambda m=module: self.start_capture(m, "hotkey")).pack(side="left")
        tb.Button(btn_row, text="Désassigner", bootstyle="outline-secondary",
                   command=lambda m=module: self.unassign_hotkey(m)).pack(side="left", padx=(8, 0))

        if isinstance(module, AlternateClickModule):
            tb.Label(body, text="Délai entre les clics", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            delay_val_lbl = tb.Label(body, text=f"{module.delay_ms} ms", bootstyle="light")
            delay_val_lbl.pack(anchor="w", pady=(2, 6))

            def on_delay_change(v, m=module, lbl=delay_val_lbl):
                m.delay_ms = int(float(v))
                lbl.config(text=f"{m.delay_ms} ms")

            tb.Scale(body, from_=0, to=100, orient="horizontal", bootstyle="secondary",
                      value=module.delay_ms, command=on_delay_change).pack(fill="x")
            tb.Label(body, text="0 ms = vitesse maximale • alterne toujours clic gauche / clic droit",
                      font=("Segoe UI", 8), bootstyle="secondary").pack(anchor="w", pady=(4, 0))

        elif isinstance(module, AutoClickModule):
            self.build_action_picker(body, module, "Touche / bouton à cliquer")

            tb.Label(body, text="Intervalle entre les clics", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 0))
            delay_val_lbl = tb.Label(body, text=f"{module.delay_ms} ms", bootstyle="light")
            delay_val_lbl.pack(anchor="w", pady=(2, 6))

            def on_delay_change2(v, m=module, lbl=delay_val_lbl):
                m.delay_ms = int(float(v))
                lbl.config(text=f"{m.delay_ms} ms")

            tb.Scale(body, from_=1, to=1000, orient="horizontal", bootstyle="secondary",
                      value=module.delay_ms, command=on_delay_change2).pack(fill="x")

        elif isinstance(module, HoldModule):
            self.build_action_picker(body, module, "Touche / bouton à maintenir")
            tb.Label(body, text="Appuie sur le déclencheur pour maintenir, rappuie pour relâcher.",
                      font=("Segoe UI", 9), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(16, 0))

        elif isinstance(module, AntiAFKModule):
            tb.Label(body, text="Mode", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            mode_var = tk.StringVar(value=module.mode)
            row = tb.Frame(body)
            row.pack(anchor="w", pady=(4, 12))
            tb.Radiobutton(row, text="Bouger la souris", variable=mode_var, value="mouse", bootstyle="toolbutton",
                            command=lambda m=module, v=mode_var: setattr(m, "mode", v.get())).pack(side="left", padx=(0, 6))
            tb.Radiobutton(row, text="Appuyer sur une touche", variable=mode_var, value="key", bootstyle="toolbutton",
                            command=lambda m=module, v=mode_var: setattr(m, "mode", v.get())).pack(side="left")

            self.build_action_picker(body, module, "Touche à appuyer (si mode « touche »)")

            tb.Label(body, text="Intervalle entre les actions", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 0))
            delay_val_lbl = tb.Label(body, text=f"{module.interval_sec} s", bootstyle="light")
            delay_val_lbl.pack(anchor="w", pady=(2, 6))

            def on_interval_change(v, m=module, lbl=delay_val_lbl):
                m.interval_sec = int(float(v))
                lbl.config(text=f"{m.interval_sec} s")

            tb.Scale(body, from_=5, to=600, orient="horizontal", bootstyle="secondary",
                      value=module.interval_sec, command=on_interval_change).pack(fill="x")
            tb.Label(body, text="Empêche d'être déconnecté pour inactivité en simulant une activité périodique.",
                      font=("Segoe UI", 8), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(6, 0))

    def build_action_picker(self, frame, module, title):
        tb.Label(frame, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        action_label = tb.Label(frame, text=display_name(module.action_id),
                                  font=("Segoe UI", 13, "bold"), bootstyle="light")
        action_label.pack(anchor="w", pady=(2, 8))
        self.action_labels[module] = action_label
        tb.Button(frame, text="Choisir...", bootstyle="primary",
                   command=lambda m=module: self.start_capture(m, "action")).pack(anchor="w")
        tb.Label(frame, text="Accepte n'importe quelle touche du clavier ou bouton de la souris.",
                  font=("Segoe UI", 8), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(4, 0))

    # ================= CAPTURE TOUCHE / BOUTON =================
    def start_capture(self, module, field):
        label = self.hotkey_labels[module] if field == "hotkey" else self.action_labels[module]
        self.capture_target = (module, field, label)
        label.config(text="Appuie sur une touche ou un bouton souris...", bootstyle="light")

    def unassign_hotkey(self, module):
        module.unassign_hotkey()
        self.hotkey_labels[module].config(text="Aucune", bootstyle="secondary")
        self.save_config()

    def reset_all_hotkeys(self):
        for module in self.modules:
            module.unassign_hotkey()
            self.hotkey_labels[module].config(text="Aucune", bootstyle="secondary")
        self.save_config()

    def on_key_press(self, key):
        if key == keyboard.Key.esc:
            self.root.after(0, self.emergency_stop)
            return
        self.handle_input(key_identifier(key))

    def on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return
        self.handle_input(mouse_identifier(button))

    def handle_input(self, identifier):
        if self.capture_target:
            module, field, label = self.capture_target
            if identifier == RESERVED_IDENTIFIER:
                self.root.after(0, lambda: label.config(text="Échap est réservé, choisis une autre touche", bootstyle="danger"))
                return
            if field == "hotkey":
                for m in self.modules:
                    if m is not module and m.hotkey == identifier:
                        m.hotkey = None
                        if m in self.hotkey_labels:
                            other_label = self.hotkey_labels[m]
                            self.root.after(0, lambda l=other_label: l.config(text="Aucune", bootstyle="secondary"))
                module.hotkey = identifier
            else:
                module.action_id = identifier

            name = display_name(identifier)
            self.root.after(0, lambda: label.config(text=name, bootstyle="light"))
            self.capture_target = None
            self.save_config()
            return

        for module in self.modules:
            if module.hotkey and module.hotkey == identifier:
                if module.active and identifier in module.driven_identifiers():
                    continue
                module.toggle()

    def emergency_stop(self):
        for module in self.modules:
            if module.active:
                module.stop()

    def on_module_state_change(self, module):
        badge = self.status_widgets.get(module)
        compact_badge = self.compact_rows.get(module) if self.compact_rows else None

        def update():
            if badge:
                if module.active:
                    badge.config(text="Actif", bootstyle="primary-inverse")
                else:
                    badge.config(text="Inactif", bootstyle="secondary-inverse")
            if compact_badge:
                if module.active:
                    compact_badge.config(text="Actif", bootstyle="primary-inverse")
                else:
                    compact_badge.config(text="Inactif", bootstyle="secondary-inverse")
        self.root.after(0, update)

    def register_real_action(self):
        if hasattr(self, "game"):
            self.game.register_real_action()

    # ================= PROFILS =================
    def build_profiles_tab(self, frame):
        tb.Label(frame, text="📂 Profils", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tb.Label(frame, text="Sauvegarde des configurations complètes (déclencheurs, cadences, cibles) "
                              "et bascule entre elles en un clic.",
                  font=("Segoe UI", 9), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(4, 16))

        self.profiles_combo = tb.Combobox(frame, state="readonly", bootstyle="light")
        self.profiles_combo.pack(fill="x", pady=(0, 10))
        self.refresh_profiles_list()

        btn_row = tb.Frame(frame)
        btn_row.pack(fill="x", pady=(0, 10))
        tb.Button(btn_row, text="Charger", bootstyle="primary",
                   command=self.on_load_profile).pack(side="left", padx=(0, 6))
        tb.Button(btn_row, text="Enregistrer sous...", bootstyle="primary",
                   command=self.on_save_profile).pack(side="left", padx=(0, 6))
        tb.Button(btn_row, text="Supprimer", bootstyle="outline-secondary",
                   command=self.on_delete_profile).pack(side="left")

        self.profiles_status_lbl = tb.Label(frame, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.profiles_status_lbl.pack(anchor="w", pady=(8, 0))

    def refresh_profiles_list(self):
        profiles = load_profiles()
        names = list(profiles.keys())
        self.profiles_combo["values"] = names
        if names and not self.profiles_combo.get():
            self.profiles_combo.set(names[0])

    def on_save_profile(self):
        from ttkbootstrap.dialogs import Querybox
        name = Querybox.get_string(prompt="Nom du profil :", title="Enregistrer le profil")
        if not name:
            return
        profiles = load_profiles()
        profiles[name] = {module.name: module.to_dict() for module in self.modules}
        save_profiles(profiles)
        self.refresh_profiles_list()
        self.profiles_combo.set(name)
        self.profiles_status_lbl.config(text=f"Profil « {name} » enregistré.")

    def on_load_profile(self):
        name = self.profiles_combo.get()
        if not name:
            return
        profiles = load_profiles()
        data = profiles.get(name)
        if not data:
            return
        for module in self.modules:
            if module.active:
                module.stop()
            if module.name in data:
                module.from_dict(data[module.name])
        self.save_config()
        self.populate_notebook()
        # populate_notebook() reconstruit un nouvel onglet Profils (nouveaux widgets) ;
        # on y réaffiche la confirmation et on resélectionne le profil chargé.
        self.profiles_combo.set(name)
        self.profiles_status_lbl.config(text=f"Profil « {name} » chargé.")
        self.show_toast(f"Profil « {name} » chargé.", "success")

    def on_delete_profile(self):
        name = self.profiles_combo.get()
        if not name:
            return
        profiles = load_profiles()
        if name in profiles:
            del profiles[name]
            save_profiles(profiles)
            self.refresh_profiles_list()
            self.profiles_combo.set("")
            self.profiles_status_lbl.config(text=f"Profil « {name} » supprimé.")

    # ================= JEU "ROUAGES" =================
    def build_game_tab(self, parent):
        header = tb.Frame(parent, padding=(0, 0, 0, 10))
        header.pack(fill="x")
        self.game_gears_label = tb.Label(header, text="", font=("Segoe UI", 16, "bold"), bootstyle="light")
        self.game_gears_label.pack(anchor="w")
        self.game_prod_label = tb.Label(header, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.game_prod_label.pack(anchor="w")

        tb.Button(parent, text="⚙️\nCLIQUER", bootstyle="primary",
                   command=self.on_game_click).pack(pady=10, ipadx=18, ipady=18)

        sub_notebook = tb.Notebook(parent, bootstyle="dark")
        sub_notebook.pack(fill="both", expand=True, pady=(10, 0))

        shop_frame = tb.Frame(sub_notebook, padding=14)
        sub_notebook.add(shop_frame, text="  🛒 Boutique  ")
        self.build_shop_ui(shop_frame)

        index_frame = tb.Frame(sub_notebook, padding=14)
        sub_notebook.add(index_frame, text="  📖 Index  ")
        self.build_index_ui(index_frame)

        rebirth_frame = tb.Frame(sub_notebook, padding=14)
        sub_notebook.add(rebirth_frame, text="  ✨ Rebirth  ")
        self.build_rebirth_ui(rebirth_frame)

        self.refresh_game_ui()

    def build_shop_ui(self, frame):
        self.gen_rows = {}
        tb.Label(frame, text="Générateurs", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        for gen in GENERATORS:
            row = tb.Frame(frame, bootstyle="secondary")
            row.pack(fill="x", pady=3)
            inner = tb.Frame(row, padding=8)
            inner.pack(fill="x")
            left = tb.Frame(inner)
            left.pack(side="left", fill="x", expand=True)
            tb.Label(left, text=f"{gen['icon']} {gen['name']}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            info_lbl = tb.Label(left, text="", font=("Segoe UI", 8), bootstyle="secondary")
            info_lbl.pack(anchor="w")
            buy_btn = tb.Button(inner, text="Acheter", bootstyle="primary",
                                  command=lambda g=gen: self.on_buy_generator(g["id"]))
            buy_btn.pack(side="right")
            self.gen_rows[gen["id"]] = {"info": info_lbl, "buy_btn": buy_btn}

        tb.Label(frame, text="Améliorations", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(16, 8))
        self.upg_rows = {}
        for up in UPGRADES:
            row = tb.Frame(frame, bootstyle="secondary")
            row.pack(fill="x", pady=3)
            inner = tb.Frame(row, padding=8)
            inner.pack(fill="x")
            left = tb.Frame(inner)
            left.pack(side="left", fill="x", expand=True)
            tb.Label(left, text=up["name"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tb.Label(left, text=up["desc"], font=("Segoe UI", 8), bootstyle="secondary",
                      wraplength=340, justify="left").pack(anchor="w")
            buy_btn = tb.Button(inner, text=f"{format_number(up['cost'])} ⚙️", bootstyle="primary",
                                  command=lambda u=up: self.on_buy_upgrade(u["id"]))
            buy_btn.pack(side="right")
            self.upg_rows[up["id"]] = {"buy_btn": buy_btn}

    def build_index_ui(self, frame):
        tb.Label(frame, text="Débloque des succès en jouant et en utilisant l'app !",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor="w", pady=(0, 10))
        grid = tb.Frame(frame)
        grid.pack(fill="both", expand=True)
        self.achievement_labels = {}
        cols = 2
        for i, ach in enumerate(ACHIEVEMENTS):
            card = tb.Frame(grid, bootstyle="secondary")
            card.grid(row=i // cols, column=i % cols, padx=5, pady=5, sticky="nsew")
            grid.columnconfigure(i % cols, weight=1)
            inner = tb.Frame(card, padding=10)
            inner.pack(fill="both", expand=True)
            title_lbl = tb.Label(inner, text="🔒 ???", font=("Segoe UI", 10, "bold"))
            title_lbl.pack(anchor="w")
            desc_lbl = tb.Label(inner, text="Verrouillé", font=("Segoe UI", 8), bootstyle="secondary",
                                  wraplength=230, justify="left")
            desc_lbl.pack(anchor="w")
            self.achievement_labels[ach["id"]] = (title_lbl, desc_lbl)

    def build_rebirth_ui(self, frame):
        tb.Label(frame, text="✨ Rebirth", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tb.Label(frame, text="Réinitialise tes Rouages, générateurs et améliorations pour obtenir "
                              "des Éclats permanents qui boostent ta production pour toujours (+2%/Éclat).",
                  font=("Segoe UI", 9), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(4, 16))

        self.rebirth_info_lbl = tb.Label(frame, text="", font=("Segoe UI", 11, "bold"), bootstyle="light")
        self.rebirth_info_lbl.pack(anchor="w", pady=(0, 10))

        self.rebirth_btn = tb.Button(frame, text="Rebirth", bootstyle="primary", command=self.on_rebirth)
        self.rebirth_btn.pack(anchor="w")

    def on_game_click(self):
        self.game.manual_click()
        self._process_game_events(0)
        self.refresh_game_ui()

    def on_buy_generator(self, gen_id):
        if self.game.buy_generator(gen_id):
            self._process_game_events(0)
            self.refresh_game_ui()

    def on_buy_upgrade(self, up_id):
        if self.game.buy_upgrade(up_id):
            self._process_game_events(0)
            self.refresh_game_ui()

    def on_rebirth(self):
        gained = self.game.do_rebirth()
        if gained > 0:
            self._process_game_events(0)
            self.refresh_game_ui()
            self.show_toast(f"🌀 Rebirth effectué ! +{gained} Éclat(s)", "warning")
            self.game.save()

    def _process_game_events(self, dt):
        newly = self.game.tick(dt)
        for ach in newly:
            self.show_toast(f"🏆 Succès débloqué : {ach['name']}", "success")

    def game_loop_tick(self):
        self._process_game_events(1.0)
        self.refresh_game_ui()
        self._game_save_counter += 1
        if self._game_save_counter >= 5:
            self.game.save()
            self._game_save_counter = 0
        self.root.after(1000, self.game_loop_tick)

    def refresh_game_ui(self):
        d = self.game.data
        self.game_gears_label.config(text=f"⚙️ {format_number(d['gears'])} Rouages")
        self.game_prod_label.config(
            text=f"+{format_number(self.game.total_production())}/s  •  "
                 f"{format_number(self.game.click_power())} par clic  •  "
                 f"✨ {d['shards']} Éclats  •  🌀 {d['rebirths']} Rebirths")

        for gen in GENERATORS:
            row = self.gen_rows[gen["id"]]
            owned = d["generators"].get(gen["id"], 0)
            cost = self.game.generator_cost(gen)
            prod = self.game.generator_production(gen)
            row["info"].config(text=f"Possédés : {owned}  •  Produit : {format_number(prod)}/s  •  "
                                      f"Coût : {format_number(cost)} ⚙️")
            row["buy_btn"].config(state="normal" if d["gears"] >= cost else "disabled")

        for up in UPGRADES:
            row = self.upg_rows[up["id"]]
            if up["id"] in d["upgrades_bought"]:
                row["buy_btn"].config(text="Achetée ✓", state="disabled", bootstyle="secondary")
            else:
                can = self.game.can_buy_upgrade(up)
                row["buy_btn"].config(text=f"{format_number(up['cost'])} ⚙️",
                                        state="normal" if can else "disabled",
                                        bootstyle="primary" if can else "secondary")

        for ach in ACHIEVEMENTS:
            title_lbl, desc_lbl = self.achievement_labels[ach["id"]]
            if ach["id"] in d["achievements_unlocked"]:
                title_lbl.config(text=f"{ach['icon']} {ach['name']}")
                desc_lbl.config(text=ach["desc"])
            else:
                title_lbl.config(text="🔒 ???")
                desc_lbl.config(text="Verrouillé")

        gain = self.game.potential_shard_gain()
        if gain > 0:
            self.rebirth_info_lbl.config(text=f"Tu peux gagner {gain} Éclat(s) en faisant un Rebirth maintenant.")
            self.rebirth_btn.config(state="normal")
        else:
            needed = 1_000_000 - (int(d["total_gears_earned"]) % 1_000_000)
            self.rebirth_info_lbl.config(text=f"Encore {format_number(needed)} Rouages (au total) avant le prochain Éclat.")
            self.rebirth_btn.config(state="disabled")

    def show_toast(self, message, style="info"):
        if not self.settings.get("toasts_enabled", True):
            return
        try:
            from ttkbootstrap.toast import ToastNotification
            ToastNotification(title="Wel's Toolbox", message=message, duration=3500, bootstyle=style).show_toast()
        except Exception as e:
            print("Toast erreur:", e)

    # ================= AIDE / SUGGESTIONS (DISCORD) =================
    def build_feedback_tab(self, frame):
        tb.Label(frame, text="💬 Aide & Suggestions", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tb.Label(frame, text="Un bug, une idée de système à ajouter, une question ? Écris ton message "
                              "ci-dessous : il est envoyé directement au développeur.",
                  font=("Segoe UI", 9), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(4, 14))

        text_card = tb.Frame(frame, bootstyle="secondary")
        text_card.pack(fill="x", pady=(0, 10))
        self.feedback_text = tk.Text(text_card, height=8, wrap="word", bg="#2b2b2b", fg="white",
                                       insertbackground="white", relief="flat", font=("Segoe UI", 10),
                                       padx=10, pady=10)
        self.feedback_text.pack(fill="both", expand=True, padx=2, pady=2)

        btn_row = tb.Frame(frame)
        btn_row.pack(fill="x")
        self.feedback_send_btn = tb.Button(btn_row, text="Envoyer", bootstyle="primary",
                                             command=self.on_send_feedback)
        self.feedback_send_btn.pack(side="left")
        self.feedback_status_lbl = tb.Label(btn_row, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.feedback_status_lbl.pack(side="left", padx=(10, 0))

    def on_send_feedback(self):
        message = self.feedback_text.get("1.0", "end").strip()
        if not message:
            self.feedback_status_lbl.config(text="Écris un message avant d'envoyer.", bootstyle="danger")
            return
        self.feedback_send_btn.config(state="disabled")
        self.feedback_status_lbl.config(text="Envoi en cours...", bootstyle="secondary")
        threading.Thread(target=self._send_feedback_thread, args=(message,), daemon=True).start()

    def _send_feedback_thread(self, message):
        try:
            send_discord_message(message)
            self.root.after(0, lambda: self._on_feedback_sent(True))
        except Exception as e:
            err = str(e)
            print("Erreur envoi feedback:", err)
            self.root.after(0, lambda: self._on_feedback_sent(False, err))

    def _on_feedback_sent(self, success, error=None):
        self.feedback_send_btn.config(state="normal")
        if success:
            self.feedback_status_lbl.config(text="✅ Message envoyé, merci !", bootstyle="light")
            self.feedback_text.delete("1.0", "end")
            self.show_toast("Message envoyé avec succès !", "success")
        else:
            detail = f" — {error[:100]}" if error else ""
            self.feedback_status_lbl.config(text=f"❌ Échec de l'envoi{detail}", bootstyle="danger")
            self.show_toast("Échec de l'envoi du message.", "danger")

    # ================= MISE A JOUR AUTOMATIQUE =================
    @staticmethod
    def _version_tuple(v):
        try:
            return tuple(int(x) for x in str(v).split("."))
        except ValueError:
            return (0,)

    def check_for_updates(self, manual=False):
        threading.Thread(target=self._check_updates_thread, args=(manual,), daemon=True).start()

    def _check_updates_thread(self, manual):
        try:
            import requests
            # Le CDN de GitHub (raw.githubusercontent.com) met les fichiers en cache.
            # On ajoute un parametre unique a chaque requete pour forcer une version fraiche.
            cache_bust = f"?nocache={int(time.time())}"
            resp = requests.get(VERSION_CHECK_URL + cache_bust, timeout=8,
                                  headers={"Cache-Control": "no-cache"})
            resp.raise_for_status()
            info = resp.json()
            remote_version = info.get("version", "0.0.0")
            if self._version_tuple(remote_version) > self._version_tuple(APP_VERSION):
                notes = info.get("notes", "")
                self.root.after(0, lambda: self._prompt_update(remote_version, notes))
            elif manual:
                self.root.after(0, lambda: self.show_toast("Tu as déjà la dernière version.", "info"))
        except Exception as e:
            print("Erreur vérification maj:", e)
            if manual:
                self.root.after(0, lambda: self.show_toast("Impossible de vérifier les mises à jour.", "danger"))

    def _prompt_update(self, remote_version, notes):
        from ttkbootstrap.dialogs import Messagebox
        message = f"Nouvelle version disponible : {remote_version} (actuelle : {APP_VERSION})\n\n{notes}\n\nInstaller maintenant ?"
        result = Messagebox.yesno(message, title="Mise à jour disponible")
        if result == "Yes":
            self.show_toast("Téléchargement de la mise à jour...", "info")
            threading.Thread(target=self._download_update_thread, args=(remote_version,), daemon=True).start()

    def _download_update_thread(self, expected_version):
        try:
            import re
            import requests
            cache_bust = f"?nocache={int(time.time())}"
            resp = requests.get(SCRIPT_UPDATE_URL + cache_bust, timeout=15,
                                  headers={"Cache-Control": "no-cache"})
            resp.raise_for_status()
            new_code = resp.text

            # Verifie que le fichier telecharge correspond bien a la version annoncee
            # (evite d'installer une version encore en cache cote CDN par erreur).
            match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', new_code)
            downloaded_version = match.group(1) if match else None
            if downloaded_version != expected_version:
                self.root.after(0, lambda: self.show_toast(
                    "Le fichier téléchargé n'est pas encore à jour côté serveur (cache). "
                    "Réessaie dans 1-2 minutes.", "warning"))
                return

            script_path = os.path.abspath(__file__)
            tmp_path = script_path + ".new"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_code)
            self.root.after(0, lambda: self._finalize_update(script_path, tmp_path))
        except Exception as e:
            print("Erreur téléchargement maj:", e)
            self.root.after(0, lambda: self.show_toast("Échec du téléchargement de la mise à jour.", "danger"))

    def _finalize_update(self, script_path, tmp_path):
        try:
            os.replace(tmp_path, script_path)
            self.show_toast("Mise à jour installée ! Redémarrage...", "success")
            self.root.after(1500, self.restart_app)
        except Exception as e:
            print("Erreur application maj:", e)
            self.show_toast("Échec de l'installation de la mise à jour.", "danger")

    def restart_app(self):
        self.save_config()
        self.game.save()
        self.kb_listener.stop()
        self.mouse_listener.stop()
        script = os.path.abspath(__file__)
        subprocess.Popen([sys.executable, script], cwd=os.path.dirname(script))
        self.root.destroy()
        sys.exit(0)

    # ================= PARAMETRES =================
    def build_settings_tab(self, frame):
        tb.Label(frame, text="⚙️ Paramètres", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 16))

        tb.Label(frame, text="Thème visuel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        try:
            registered = set(self.root.style.theme_names())
        except Exception:
            registered = set(AVAILABLE_THEMES)
        available_labels = {k: v for k, v in THEME_LABELS.items() if k in registered}
        if not available_labels:
            available_labels = THEME_LABELS

        current_theme_key = self.settings.get("theme", "wels_dark")
        if current_theme_key not in available_labels:
            current_theme_key = next(iter(available_labels))
        theme_var = tk.StringVar(value=available_labels.get(current_theme_key, current_theme_key))
        theme_combo = tb.Combobox(frame, state="readonly", values=list(available_labels.values()),
                                    textvariable=theme_var, bootstyle="light")
        theme_combo.pack(fill="x", pady=(4, 18))
        theme_combo.bind("<<ComboboxSelected>>",
                           lambda e: self.on_theme_change(self._theme_key_from_label(theme_var.get())))

        startup_var = tk.BooleanVar(value=is_startup_enabled())
        tb.Checkbutton(frame, text="Lancer Wel's Toolbox au démarrage de Windows",
                        variable=startup_var, bootstyle="round-toggle",
                        command=lambda: self.on_toggle_startup(startup_var.get())).pack(anchor="w", pady=(0, 12))

        toast_var = tk.BooleanVar(value=self.settings.get("toasts_enabled", True))
        tb.Checkbutton(frame, text="Afficher les notifications (succès, mises à jour...)",
                        variable=toast_var, bootstyle="round-toggle",
                        command=lambda: self.on_toggle_toasts(toast_var.get())).pack(anchor="w", pady=(0, 24))

        tb.Separator(frame).pack(fill="x", pady=(0, 20))

        tb.Label(frame, text="Zone dangereuse", font=("Segoe UI", 11, "bold"), bootstyle="danger").pack(anchor="w", pady=(0, 10))
        tb.Button(frame, text="Réinitialiser mes données (déclencheurs, profils, jeu)", bootstyle="outline-secondary",
                   command=self.on_reset_data).pack(anchor="w", pady=(0, 10))
        tb.Button(frame, text="🗑️ Désinstaller Wel's Toolbox de mon PC", bootstyle="danger",
                   command=self.on_uninstall).pack(anchor="w")
        tb.Label(frame, text="Supprime définitivement tous les fichiers, dossiers et données de l'application.",
                  font=("Segoe UI", 8), bootstyle="secondary", wraplength=560, justify="left").pack(anchor="w", pady=(6, 0))

    @staticmethod
    def _theme_key_from_label(label):
        for key, value in THEME_LABELS.items():
            if value == label:
                return key
        return "wels_dark"

    def on_theme_change(self, theme_name):
        try:
            self.root.style.theme_use(theme_name)
            self.apply_notebook_style()
            self.settings["theme"] = theme_name
            save_app_settings(self.settings)
        except Exception as e:
            print("Erreur changement theme:", e)
            self.show_toast("Impossible d'appliquer ce thème.", "danger")

    def on_toggle_startup(self, enabled):
        try:
            set_startup_enabled(enabled)
            self.show_toast("Démarrage automatique activé." if enabled else "Démarrage automatique désactivé.", "info")
        except Exception as e:
            print("Erreur toggle startup:", e)
            self.show_toast("Impossible de modifier le démarrage automatique.", "danger")

    def on_toggle_toasts(self, enabled):
        self.settings["toasts_enabled"] = enabled
        save_app_settings(self.settings)

    def on_reset_data(self):
        from ttkbootstrap.dialogs import Messagebox
        confirm = Messagebox.yesno(
            "Ça va effacer tes déclencheurs assignés, tes profils sauvegardés et ta progression "
            "du jeu Rouages (mais ne désinstalle PAS l'application). Continuer ?",
            title="Réinitialiser mes données")
        if confirm != "Yes":
            return
        for module in self.modules:
            if module.active:
                module.stop()
            module.hotkey = None
        for f in (CONFIG_FILE, PROFILES_FILE, GAME_FILE):
            if os.path.exists(f):
                os.remove(f)
        self.game = GameState(self)
        self.populate_notebook()
        self.show_toast("Données réinitialisées.", "success")

    def on_uninstall(self):
        from ttkbootstrap.dialogs import Messagebox
        confirm = Messagebox.yesno(
            "Cette action va supprimer DÉFINITIVEMENT Wel's Toolbox de ton PC :\n"
            "• Tous les fichiers de l'application\n"
            "• Tes configurations, profils et ta progression du jeu\n"
            "• Le raccourci sur le Bureau et le démarrage automatique\n\n"
            "Cette action est IRRÉVERSIBLE. Continuer ?",
            title="⚠️ Désinstaller Wel's Toolbox")
        if confirm != "Yes":
            return
        confirm2 = Messagebox.yesno(
            "Es-tu VRAIMENT sûr ? Il n'y a aucun retour en arrière possible après ça.",
            title="Dernière confirmation")
        if confirm2 != "Yes":
            return
        self._perform_uninstall()

    def _perform_uninstall(self):
        install_dir = BASE_DIR
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "Wel's Toolbox.lnk")
        startup_path = os.path.join(STARTUP_FOLDER, STARTUP_BAT_NAME)
        cleanup_bat = os.path.join(os.environ.get("TEMP", BASE_DIR), "multiclicker_uninstall.bat")

        script = (
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'rmdir /s /q "{install_dir}"\r\n'
            f'del /f /q "{shortcut_path}" 2>nul\r\n'
            f'del /f /q "{startup_path}" 2>nul\r\n'
            'del /f /q "%~f0"\r\n'
        )
        try:
            with open(cleanup_bat, "w", encoding="utf-8") as f:
                f.write(script)
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(["cmd", "/c", cleanup_bat], creationflags=creation_flags)
        except Exception as e:
            print("Erreur lancement desinstallation:", e)

        for module in self.modules:
            if module.active:
                module.stop()
        self.kb_listener.stop()
        self.mouse_listener.stop()
        self.root.destroy()
        sys.exit(0)

    # ================= SAUVEGARDE / CHARGEMENT CONFIG =================
    def save_config(self):
        data = {module.name: module.to_dict() for module in self.modules}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Erreur sauvegarde config:", e)

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for module in self.modules:
                if module.name in data:
                    module.from_dict(data[module.name])
        except Exception as e:
            print("Erreur chargement config:", e)

    def autosave_loop(self):
        """Sauvegarde automatique de la config et du jeu toutes les 30s, en plus
        des sauvegardes déclenchées par les actions (touches assignées, achats, etc.)."""
        self.save_config()
        self.game.save()
        self.root.after(30000, self.autosave_loop)

    def on_close(self):
        for module in self.modules:
            if module.active:
                module.stop()
        self.kb_listener.stop()
        self.mouse_listener.stop()
        self.save_config()
        self.game.save()
        self.root.destroy()


if __name__ == "__main__":
    try:
        _startup_settings = load_app_settings()
        root = tb.Window(themename="darkly")  # theme de base valide, remplace juste apres si possible
        _wels_available = register_wels_themes(root.style)
        _initial_theme = _startup_settings.get("theme", "wels_dark")
        if not _wels_available and _initial_theme.startswith("wels_"):
            _initial_theme = "darkly"
        try:
            root.style.theme_use(_initial_theme)
        except Exception as e:
            print("Theme demande indisponible, repli sur darkly:", e)
            try:
                root.style.theme_use("darkly")
            except Exception:
                pass
        app = AutoClickerApp(root)
        root.mainloop()
    except Exception:
        import traceback
        crash_log = os.path.join(BASE_DIR, "crash_log.txt")
        try:
            with open(crash_log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
