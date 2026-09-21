from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT_DIR / "instance" / "krampus_rpg.sqlite3"
ITEMS_JSON = ROOT_DIR / "Data" / "items.json"


def import_items():
    """Import items from JSON to database."""
    print("Importing items from JSON...")

    # Load items from JSON
    with open(ITEMS_JSON, 'r') as f:
        items_data = json.load(f)

    print(f"Found {len(items_data)} items in JSON")

    # Connect to database
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row

    # Clear existing items
    db.execute("DELETE FROM items")
    db.commit()
    print("Cleared existing items")

    # Import items
    imported_count = 0
    for item in items_data:
        try:
            db.execute("""
                INSERT INTO items (id, name, type, price, sell_price, heal, effect, custom, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("id"),
                item.get("name"),
                item.get("type"),
                item.get("price", 0),
                item.get("sell_price", 0),
                item.get("heal"),
                item.get("effect"),
                1 if item.get("custom") else 0,
                item.get("description", "")
            ))
            imported_count += 1
            print(f"  Imported: {item.get('name')}")
        except Exception as e:
            print(f"  Error importing {item.get('name')}: {e}")

    db.commit()

    # Verify
    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Total items in database: {count}")

    # List all items
    items = db.execute("SELECT * FROM items ORDER BY price").fetchall()
    print("\nItems in database:")
    for item in items:
        print(f"  {item['name']} ({item['type']}) - ${item['price']}")

    db.close()
    print(f"\nSuccessfully imported {imported_count} items!")


if __name__ == "__main__":
    import_items()
