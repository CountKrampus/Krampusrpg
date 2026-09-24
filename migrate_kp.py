"""
Krampus Points Migration Script
================================
Run this once to apply the KP schema to an existing database
and seed default permissions / role assignments.

Usage:
    python migrate_kp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure the project root is importable.
sys.path.insert(0, str(Path(__file__).parent))

from Server.database import get_connection, PERMISSIONS, ROLE_PERMISSIONS
from Server import krampus_points


KP_PERMISSIONS = [
    ("admin.krampus_points.view", "View Krampus Points balances and transactions."),
    ("admin.krampus_points.edit", "Award, deduct, and manage Krampus Points for players."),
    ("admin.kp_shop.view", "View the Krampus Points shop configuration."),
    ("admin.kp_shop.edit", "Create, edit, and delete Krampus Points shop items."),
]


def run_migration() -> None:
    print("=== Krampus Points Migration ===")

    # 1. Ensure schema
    print("[1/3] Creating KP tables...")
    krampus_points.ensure_kp_schema()
    print("  OK")

    # 2. Seed permissions into the permissions table
    print("[2/3] Seeding KP permissions...")
    with get_connection() as db:
        for perm_name, description in KP_PERMISSIONS:
            existing = db.execute(
                "SELECT 1 FROM permissions WHERE permission_name = ? LIMIT 1",
                (perm_name,),
            ).fetchone()
            if existing is None:
                db.execute(
                    "INSERT INTO permissions (permission_name, description) VALUES (?, ?)",
                    (perm_name, description),
                )
                print(f"  Added permission: {perm_name}")
            else:
                print(f"  Already exists: {perm_name}")
        db.commit()

    # 3. Assign permissions to roles
    print("[3/3] Assigning permissions to roles...")

    role_kp_map = {
        "admin": [
            "admin.krampus_points.view",
            "admin.krampus_points.edit",
            "admin.kp_shop.view",
            "admin.kp_shop.edit",
        ],
        "event_staff": [
            "admin.kp_shop.view",
            "admin.kp_shop.edit",
        ],
        "webmaster": [
            "admin.krampus_points.view",
            "admin.krampus_points.edit",
            "admin.kp_shop.view",
            "admin.kp_shop.edit",
        ],
    }

    with get_connection() as db:
        for role_name, perms in role_kp_map.items():
            role_row = db.execute(
                "SELECT id FROM roles WHERE name = ? LIMIT 1", (role_name,)
            ).fetchone()
            if role_row is None:
                print(f"  WARNING: role '{role_name}' not found in DB, skipping.")
                continue

            role_id = role_row["id"]

            for perm_name in perms:
                perm_row = db.execute(
                    "SELECT id FROM permissions WHERE permission_name = ? LIMIT 1",
                    (perm_name,),
                ).fetchone()
                if perm_row is None:
                    print(f"  WARNING: permission '{perm_name}' not in DB, skipping.")
                    continue

                perm_id = perm_row["id"]

                existing_rp = db.execute(
                    "SELECT 1 FROM role_permissions WHERE role_id = ? AND permission_id = ? LIMIT 1",
                    (role_id, perm_id),
                ).fetchone()

                if existing_rp is None:
                    db.execute(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                        (role_id, perm_id),
                    )
                    print(f"  Granted {perm_name} -> {role_name}")
                else:
                    print(f"  Already granted: {perm_name} -> {role_name}")

        db.commit()

    print("\nMigration complete!")
    print("Restart the server to apply all changes.")


if __name__ == "__main__":
    run_migration()
