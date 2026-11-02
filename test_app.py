import base64
import unittest

from app import (
    ATTRIBUTE_COSTS,
    CLASS_PROFILES,
    MAX_PHOTO_BYTES,
    MAX_WARBAND_NAME_LENGTH,
    STATS,
    WEAPONS,
    Warband,
)


def fighter(
    name="Aster",
    role="Leader",
    classes=None,
    stats=None,
    weapons=None,
    leader_trait="",
):
    return {
        "name": name,
        "role": role,
        "classes": classes or ["Fighter"],
        "stats": stats or {"speed": "2", "defense": "2d6", "might": "2d6", "will": "2d6"},
        "weapons": weapons or [],
        "leader_trait": leader_trait,
    }


class WarbandTests(unittest.TestCase):
    def setUp(self):
        self.warband = Warband()

    def test_warband_name_can_be_edited_and_is_trimmed(self):
        state = self.warband.set_name("  The Ashen Company  ")
        self.assertEqual(state["name"], "The Ashen Company")
        self.assertEqual(self.warband.state()["name"], "The Ashen Company")

    def test_invalid_warband_names_are_rejected_without_changing_name(self):
        for name in ("", "   ", "x" * (MAX_WARBAND_NAME_LENGTH + 1), None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.warband.set_name(name)
        self.assertEqual(self.warband.state()["name"], "Untitled Warband")

    def test_rulebook_classes_and_weapon_data_are_loaded(self):
        self.assertEqual(len(CLASS_PROFILES), 27)
        self.assertEqual(CLASS_PROFILES["Wretch"]["points"], 0)
        self.assertEqual(CLASS_PROFILES["Monster"]["limit"], 1)
        self.assertIsNone(CLASS_PROFILES["Fighter"]["limit"])
        self.assertEqual(len(WEAPONS), 54)
        self.assertEqual(self.warband.state()["attribute_costs"], ATTRIBUTE_COSTS)

    def test_attribute_and_class_costs_are_summed(self):
        result = self.warband.add_character(fighter(
            classes=["Fighter", "Knight"],
            stats={"speed": "3", "defense": "2d10", "might": "2d8", "will": "2d6"},
            weapons=["Shield"],
        ))
        expected = (
            1 + 1
            + ATTRIBUTE_COSTS["speed"]["3"]
            + ATTRIBUTE_COSTS["defense"]["2d10"]
            + ATTRIBUTE_COSTS["might"]["2d8"]
            + ATTRIBUTE_COSTS["will"]["2d6"]
            + 1
        )
        self.assertEqual(result["characters"][0]["points"], expected)

    def test_leader_may_take_two_classes_and_troop_may_not(self):
        result = self.warband.add_character(fighter(classes=["Fighter", "Knight"]))
        self.assertEqual(result["characters"][0]["classes"], ["Fighter", "Knight"])
        with self.assertRaisesRegex(ValueError, "at most 1 class"):
            self.warband.add_character(fighter(
                name="Bryn", role="Troop", classes=["Fighter", "Knight"]
            ))

    def test_only_one_leader_and_powerful_model_are_allowed(self):
        self.warband.add_character(fighter())
        with self.assertRaisesRegex(ValueError, "only have one leader"):
            self.warband.add_character(fighter(name="Bryn"))
        self.warband.add_character(fighter(name="Grom", role="Powerful"))
        with self.assertRaisesRegex(ValueError, "only have one Powerful"):
            self.warband.add_character(fighter(name="Brak", role="Powerful"))

    def test_leader_must_be_created_before_troops_or_powerful_models(self):
        for role in ("Troop", "Powerful"):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "leader first"):
                self.warband.add_character(fighter(role=role))

    def test_powerful_model_may_cost_30_points_but_not_be_leader(self):
        expensive = fighter(
            role="Powerful",
            classes=["Monster", "Beast"],
            stats={"speed": "3", "defense": "2d10", "might": "2d10", "will": "2d10"},
            weapons=["Claws"],
        )
        self.warband.add_character(fighter())
        result = self.warband.add_character(expensive)
        self.assertEqual(result["characters"][-1]["points"], 30)
        with self.assertRaisesRegex(ValueError, "limit is 25"):
            Warband().add_character({
                **expensive,
                "role": "Leader",
                "classes": ["Monster", "Beast"],
            })

    def test_regular_model_cannot_exceed_25_points(self):
        self.warband.add_character(fighter())
        with self.assertRaisesRegex(ValueError, "limit is 25"):
            self.warband.add_character(fighter(
                name="Bryn",
                role="Troop",
                stats={"speed": "3", "defense": "2d10", "might": "2d10", "will": "2d8"},
                weapons=["Shield", "Greatsword"],
            ))

    def test_2d10_attribute_weapon_and_class_requirements(self):
        with self.assertRaisesRegex(ValueError, "2d10 Defense requires"):
            self.warband.add_character(fighter(stats={
                "speed": "2", "defense": "2d10", "might": "2d6", "will": "2d6",
            }))
        with self.assertRaisesRegex(ValueError, "2d10 Might requires"):
            self.warband.add_character(fighter(stats={
                "speed": "2", "defense": "2d6", "might": "2d10", "will": "2d6",
            }))
        self.warband.add_character(fighter(classes=["Knight"], stats={
            "speed": "2", "defense": "2d10", "might": "2d6", "will": "2d6",
        }))
        self.warband.add_character(fighter(
            name="Grom",
            role="Troop",
            classes=["Monster"],
            stats={"speed": "2", "defense": "2d10", "might": "2d10", "will": "2d6"},
        ))

    def test_limited_classes_are_capped_across_the_warband(self):
        self.warband.add_character(fighter(classes=["Fighter", "Knight"]))
        self.warband.add_character(fighter(name="Bryn", role="Troop", classes=["Knight"]))
        with self.assertRaisesRegex(ValueError, "Knight is limited to 2"):
            self.warband.add_character(fighter(name="Cora", role="Troop", classes=["Knight"]))

    def test_weapon_proficiency_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "not proficient with"):
            self.warband.add_character(fighter(classes=["Fighter"], weapons=["Wand"]))
        self.warband.add_character(fighter(classes=["Magic User"], weapons=["Wand"]))

    def test_hero_villain_doubles_leader_cost(self):
        ordinary = self.warband.add_character(fighter())["characters"][0]["points"]
        heroic = Warband().add_character(fighter(leader_trait="Hero/Villain"))["characters"][0]["points"]
        self.assertEqual(heroic, ordinary * 2)

    def test_leader_traits_cannot_be_assigned_to_troops(self):
        self.warband.add_character(fighter())
        with self.assertRaisesRegex(ValueError, "Only the leader"):
            self.warband.add_character(fighter(
                name="Bryn", role="Troop", leader_trait="Tactician"
            ))

    def test_invalid_attributes_and_class_names_are_rejected(self):
        invalid_attributes = (
            {"speed": "4", "defense": "2d6", "might": "2d6", "will": "2d6"},
            {"speed": "2", "defense": "2d12", "might": "2d6", "will": "2d6"},
        )
        for stats in invalid_attributes:
            with self.subTest(stats=stats), self.assertRaises(ValueError):
                self.warband.add_character(fighter(stats=stats))
        with self.assertRaisesRegex(ValueError, "available classes"):
            self.warband.add_character(fighter(classes=["Unknown"]))

    def test_warband_budget_rejects_over_budget_model(self):
        self.warband.set_budget(25)
        self.warband.add_character(fighter())
        self.warband.add_character(fighter(name="Bryn", role="Troop"))
        self.warband.add_character(fighter(name="Cora", role="Troop"))
        with self.assertRaisesRegex(ValueError, "only 1 remain"):
            self.warband.add_character(fighter(name="Dax", role="Troop"))
        self.assertEqual(len(self.warband.state()["characters"]), 3)

    def test_remove_character_frees_points(self):
        result = self.warband.add_character(fighter())
        character_id = result["characters"][0]["id"]
        result = self.warband.remove_character(character_id)
        self.assertEqual(result["characters"], [])
        self.assertEqual(result["points_used"], 0)
        self.assertEqual(result["remaining"], 100)

    def test_leader_cannot_be_removed_while_other_models_remain(self):
        state = self.warband.add_character(fighter())
        leader_id = state["characters"][0]["id"]
        state = self.warband.add_character(fighter(name="Bryn", role="Troop"))
        troop_id = next(item["id"] for item in state["characters"] if item["role"] == "Troop")
        with self.assertRaisesRegex(ValueError, "must keep its leader"):
            self.warband.remove_character(leader_id)
        self.warband.remove_character(troop_id)
        self.assertEqual(self.warband.remove_character(leader_id)["characters"], [])

    def test_leader_equipment_traits_require_matching_equipment(self):
        with self.assertRaisesRegex(ValueError, "requires the leader to have a weapon"):
            self.warband.add_character(fighter(leader_trait="Enchanted Weapon"))
        with self.assertRaisesRegex(ValueError, "requires the leader to have a shield"):
            self.warband.add_character(fighter(leader_trait="Enchanted Shield"))
        self.warband.add_character(fighter(
            leader_trait="Enchanted Shield", weapons=["Shield"]
        ))

    def test_character_photo_can_be_attached_and_replaced(self):
        state = self.warband.add_character(fighter())
        character_id = state["characters"][0]["id"]
        first_photo = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xfffirst").decode()
        second_photo = "data:image/png;base64," + base64.b64encode(
            b"\x89PNG\r\n\x1a\nsecond"
        ).decode()
        state = self.warband.set_character_photo(character_id, first_photo)
        self.assertEqual(state["characters"][0]["photo"], first_photo)
        state = self.warband.set_character_photo(character_id, second_photo)
        self.assertEqual(state["characters"][0]["photo"], second_photo)

    def test_invalid_or_mismatched_character_photos_are_rejected(self):
        state = self.warband.add_character(fighter())
        character_id = state["characters"][0]["id"]
        invalid_photos = (
            "not an image",
            "data:image/gif;base64,R0lGODlh",
            "data:image/png;base64," + base64.b64encode(b"not png").decode(),
            "data:image/jpeg;base64,%%%",
            "data:image/jpeg;base64," + base64.b64encode(
                b"\xff\xd8\xff" + b"x" * MAX_PHOTO_BYTES
            ).decode(),
        )
        for photo in invalid_photos:
            with self.subTest(photo=photo[:32]), self.assertRaises(ValueError):
                self.warband.set_character_photo(character_id, photo)
        self.assertIsNone(self.warband.state()["characters"][0]["photo"])

    def test_photo_for_missing_character_is_rejected(self):
        photo = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xffphoto").decode()
        with self.assertRaisesRegex(ValueError, "no longer in this warband"):
            self.warband.set_character_photo("missing", photo)


if __name__ == "__main__":
    unittest.main()
