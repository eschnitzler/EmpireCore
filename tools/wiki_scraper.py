#!/usr/bin/env python3
"""
Wiki data scraper - Extract unit and building data from GGE wikis.
"""

import json
import os

# Manual data for now - starter database
UNITS_DATABASE = {
    "620": {
        "id": 620,
        "name": "Militia",
        "kingdom": "green",
        "cost": {"wood": 10, "stone": 0, "food": 10},
        "training_time": 30,
        "speed": 5,
        "carry_capacity": 50,
    }
}

BUILDINGS_DATABASE = {
    "keep": {"name": "Keep", "type": "main"},
    "woodcutter": {"name": "Woodcutter", "type": "resource", "produces": "wood"},
}

MAP_OBJECTS = {"32": {"type_id": 32, "name": "Barbarian Camp", "safe_target": True}}

os.makedirs("data", exist_ok=True)

with open("data/units.json", "w") as f:
    json.dump(UNITS_DATABASE, f, indent=2)

with open("data/buildings.json", "w") as f:
    json.dump(BUILDINGS_DATABASE, f, indent=2)

with open("data/map_objects.json", "w") as f:
    json.dump(MAP_OBJECTS, f, indent=2)

print("✅ Created starter databases in data/ directory")
print(f"   - units.json ({len(UNITS_DATABASE)} units)")
print(f"   - buildings.json ({len(BUILDINGS_DATABASE)} buildings)")
print(f"   - map_objects.json ({len(MAP_OBJECTS)} types)")
