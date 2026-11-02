"""Local web app for building a small fantasy skirmish warband."""

from __future__ import annotations

import base64
import binascii
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from class_profiles import (
    ATTRIBUTE_COSTS,
    CLASS_PROFILES,
    LEADER_TRAITS,
    TWO_HANDED_WEAPONS,
    WEAPONS,
)

HOST = "127.0.0.1"
PORT = 8000
MIN_BUDGET = 25
MAX_BUDGET = 2000
MAX_WARBAND_NAME_LENGTH = 60
MAX_PHOTO_BYTES = 1_000_000
ATTRIBUTES = tuple(ATTRIBUTE_COSTS)
STATS = ATTRIBUTES
WEAPON_BY_NAME = {weapon["name"]: weapon for weapon in WEAPONS}
PHOTO_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda data: (
        len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ),
}

STAT_LABELS = {
    "speed": "Speed",
    "defense": "Defense",
    "might": "Might",
    "will": "Willpower",
}


class Warband:
    """In-memory roster with a single source of truth for points and validation."""

    def __init__(self) -> None:
        self.name = "Untitled Warband"
        self.budget = 100
        self.characters: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    @property
    def points_used(self) -> int:
        return sum(character["points"] for character in self.characters)

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "name": self.name,
                "budget": self.budget,
                "points_used": self.points_used,
                "remaining": self.budget - self.points_used,
                "characters": [dict(character) for character in self.characters],
                "classes": CLASS_PROFILES,
                "weapons": WEAPONS,
                "attribute_costs": ATTRIBUTE_COSTS,
                "leader_traits": LEADER_TRAITS,
                "two_handed_weapons": sorted(TWO_HANDED_WEAPONS),
                "max_model_points": 25,
                "max_powerful_points": 30,
                "stat_labels": STAT_LABELS,
            }

    def set_name(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Warband name cannot be empty.")
        name = value.strip()
        if len(name) > MAX_WARBAND_NAME_LENGTH:
            raise ValueError(
                f"Warband names must be {MAX_WARBAND_NAME_LENGTH} characters or fewer."
            )
        with self.lock:
            self.name = name
        return self.state()

    def set_budget(self, value: Any) -> dict[str, Any]:
        budget = _integer(value, "Choose a whole-number points limit.")
        if not MIN_BUDGET <= budget <= MAX_BUDGET:
            raise ValueError(f"Points limit must be between {MIN_BUDGET} and {MAX_BUDGET}.")
        with self.lock:
            if budget < self.points_used:
                raise ValueError(
                    f"Your roster already uses {self.points_used} points. "
                    "Remove a character before lowering the limit."
                )
            self.budget = budget
        return self.state()

    def add_character(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Character details must be sent as an object.")
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Give your character a name.")
        name = name.strip()
        if len(name) > 40:
            raise ValueError("Character names must be 40 characters or fewer.")

        role = payload.get("role")
        if not isinstance(role, str) or role not in {"Leader", "Troop", "Powerful"}:
            raise ValueError("Choose Leader, Troop, or Powerful model.")
        classes = payload.get("classes")
        if (
            not isinstance(classes, list)
            or not classes
            or any(not isinstance(name, str) or name not in CLASS_PROFILES for name in classes)
            or len(set(classes)) != len(classes)
        ):
            raise ValueError("Choose one or two distinct available classes.")
        class_limit = 1 if role == "Troop" else 2
        if len(classes) > class_limit:
            raise ValueError(f"{role} models may have at most {class_limit} class.")

        submitted_stats = payload.get("stats")
        if not isinstance(submitted_stats, dict) or set(submitted_stats) != set(ATTRIBUTES):
            raise ValueError("Provide a value for Speed, Defense, Might, and Willpower.")
        stats: dict[str, int | str] = {}
        for attribute, cost_options in ATTRIBUTE_COSTS.items():
            value = submitted_stats[attribute]
            if attribute == "speed":
                speed = _integer(value, "Speed must be 1, 2, or 3.")
                if str(speed) not in cost_options:
                    raise ValueError("Speed must be 1, 2, or 3.")
                stats[attribute] = speed
            elif isinstance(value, str) and value in cost_options:
                stats[attribute] = value
            else:
                raise ValueError(f"Choose a valid {STAT_LABELS[attribute]} dice level.")

        submitted_weapons = payload.get("weapons")
        if (
            not isinstance(submitted_weapons, list)
            or any(not isinstance(name, str) or name not in WEAPON_BY_NAME for name in submitted_weapons)
        ):
            raise ValueError("Choose valid weapons.")
        proficiencies = {
            proficiency
            for class_name in classes
            for proficiency in CLASS_PROFILES[class_name]["proficiencies"]
        }
        incompatible = [
            name for name in submitted_weapons
            if WEAPON_BY_NAME[name]["category"] not in proficiencies
        ]
        if incompatible:
            raise ValueError(
                f"Your selected classes are not proficient with {', '.join(incompatible)}."
            )

        unrestricted_attributes = {"Beast", "Magical Beast", "Monster"}
        if (
            stats["defense"] == "2d10"
            and not any(WEAPON_BY_NAME[name]["category"] == "Shields" for name in submitted_weapons)
            and not unrestricted_attributes.intersection(classes)
            and "Knight" not in classes
        ):
            raise ValueError("2d10 Defense requires a shield or a class that permits it.")
        if (
            stats["might"] == "2d10"
            and not unrestricted_attributes.intersection(classes)
            and not TWO_HANDED_WEAPONS.intersection(submitted_weapons)
        ):
            raise ValueError("2d10 Might requires a two-handed weapon or a class that permits it.")

        leader_trait = payload.get("leader_trait", "")
        if not isinstance(leader_trait, str):
            raise ValueError("Choose a valid leader trait.")
        if role == "Leader":
            if leader_trait not in ("", *LEADER_TRAITS):
                raise ValueError("Choose a valid leader trait.")
            if leader_trait == "Enchanted Weapon" and not submitted_weapons:
                raise ValueError("Enchanted Weapon requires the leader to have a weapon.")
            if leader_trait == "Enchanted Shield" and not any(
                WEAPON_BY_NAME[name]["category"] == "Shields" for name in submitted_weapons
            ):
                raise ValueError("Enchanted Shield requires the leader to have a shield.")
        elif leader_trait:
            raise ValueError("Only the leader may have a leader trait.")

        points = sum(CLASS_PROFILES[name]["points"] for name in classes)
        points += sum(
            ATTRIBUTE_COSTS[attribute][str(value)] for attribute, value in stats.items()
        )
        points += sum(WEAPON_BY_NAME[name]["points"] for name in submitted_weapons)
        if leader_trait == "Hero/Villain":
            points *= 2
        model_limit = 30 if role == "Powerful" else 25
        if points > model_limit:
            raise ValueError(
                f"{role} model costs {points} points; the limit is {model_limit}. "
                "Adjust its classes, attributes, weapons, or leader trait."
            )

        character = {
            "id": uuid.uuid4().hex,
            "name": name,
            "role": role,
            "classes": classes,
            "leader_trait": leader_trait,
            "stats": stats,
            "weapons": submitted_weapons,
            "points": points,
            "photo": None,
        }
        with self.lock:
            if role == "Leader" and any(item["role"] == "Leader" for item in self.characters):
                raise ValueError("A warband can only have one leader.")
            if role != "Leader" and not any(item["role"] == "Leader" for item in self.characters):
                raise ValueError("Create the warband leader first.")
            if role == "Powerful" and any(item["role"] == "Powerful" for item in self.characters):
                raise ValueError("A warband can only have one Powerful (large) model.")
            for class_name in classes:
                class_limit = CLASS_PROFILES[class_name]["limit"]
                if class_limit is not None:
                    existing = sum(
                        class_name in item["classes"] for item in self.characters
                    )
                    if existing >= class_limit:
                        raise ValueError(
                            f"{class_name} is limited to {class_limit} "
                            f"{'model' if class_limit == 1 else 'models'} per warband."
                        )
            if self.points_used + points > self.budget:
                raise ValueError(
                    f"{name} costs {points} points, but only "
                    f"{self.budget - self.points_used} remain. Adjust their stats "
                    "or raise the warband limit."
                )
            self.characters.append(character)
        return self.state()

    def set_character_photo(self, character_id: str, value: Any) -> dict[str, Any]:
        photo = _validated_photo(value)
        with self.lock:
            for character in self.characters:
                if character["id"] == character_id:
                    character["photo"] = photo
                    break
            else:
                raise ValueError("That character is no longer in this warband.")
        return self.state()

    def remove_character(self, character_id: str) -> dict[str, Any]:
        with self.lock:
            for index, character in enumerate(self.characters):
                if character["id"] == character_id:
                    if character["role"] == "Leader" and len(self.characters) > 1:
                        raise ValueError(
                            "A warband must keep its leader while other models remain. "
                            "Remove the other models first."
                        )
                    del self.characters[index]
                    break
            else:
                raise ValueError("That character is no longer in this warband.")
        return self.state()


def _integer(value: Any, message: str) -> int:
    if isinstance(value, bool):
        raise ValueError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    raise ValueError(message)


def _validated_photo(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Choose a JPEG, PNG, or WebP image.")
    match = re.fullmatch(r"data:(image/jpeg|image/png|image/webp);base64,([A-Za-z0-9+/]*={0,2})", value)
    if match is None:
        raise ValueError("Choose a valid JPEG, PNG, or WebP image.")
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("The selected image data is invalid.") from error
    if not image_bytes or len(image_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("Photo must be smaller than 1 MB after processing.")
    if not PHOTO_SIGNATURES[match.group(1)](image_bytes):
        raise ValueError("The selected image does not match its file type.")
    return value


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "WeirdoBuilder/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            try:
                html = (Path(__file__).parent / "index.html").read_bytes()
            except OSError:
                self._send_json(500, {"error": "The app's index.html file could not be read."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/rules":
            self._send_json(200, {
                "classes": CLASS_PROFILES,
                "weapons": WEAPONS,
                "attribute_costs": ATTRIBUTE_COSTS,
                "leader_traits": LEADER_TRAITS,
                "max_model_points": 25,
                "max_powerful_points": 30,
            })
        else:
            self._send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        self._send_json(405, {"error": "Warbands are stored locally and are not accepted by the server."})

    def do_DELETE(self) -> None:
        self._send_json(405, {"error": "Warbands are stored locally and are not accepted by the server."})

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: Any) -> None:
        super().log_message(format_string, *args)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"Warband builder running at http://{HOST}:{PORT}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping warband builder.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
