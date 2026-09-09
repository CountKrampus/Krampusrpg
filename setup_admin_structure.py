from pathlib import Path


# ============================================================
# Krampus RPG
# Admin System Structure Setup
#
# This script ONLY creates new folders/files.
# Existing files are NEVER overwritten.
# ============================================================


PROJECT_DIR = Path(__file__).resolve().parent

SERVER_DIR = PROJECT_DIR / "Server"
ADMIN_DIR = SERVER_DIR / "admin"

TEMPLATES_DIR = ADMIN_DIR / "templates" / "admin"
COMPONENTS_DIR = TEMPLATES_DIR / "components"

STATIC_DIR = ADMIN_DIR / "static"
CSS_DIR = STATIC_DIR / "css"
JS_DIR = STATIC_DIR / "js"


# ============================================================
# DIRECTORIES
# ============================================================

DIRECTORIES = [
    ADMIN_DIR,

    TEMPLATES_DIR,
    COMPONENTS_DIR,

    STATIC_DIR,
    CSS_DIR,
    JS_DIR,
]


# ============================================================
# PYTHON FILES
# ============================================================

PYTHON_FILES = [
    ADMIN_DIR / "__init__.py",

    # Authentication / permissions
    ADMIN_DIR / "permissions.py",
    ADMIN_DIR / "decorators.py",

    # Admin routing
    ADMIN_DIR / "routes.py",

    # Admin business logic
    ADMIN_DIR / "services.py",

    # Audit logging
    ADMIN_DIR / "audit.py",

    # Admin form/data validation
    ADMIN_DIR / "forms.py",
]


# ============================================================
# HTML TEMPLATES
# ============================================================

HTML_FILES = [
    TEMPLATES_DIR / "base.html",

    TEMPLATES_DIR / "dashboard.html",

    TEMPLATES_DIR / "players.html",
    TEMPLATES_DIR / "pokemon.html",
    TEMPLATES_DIR / "items.html",
    TEMPLATES_DIR / "quests.html",

    TEMPLATES_DIR / "promos.html",
    TEMPLATES_DIR / "events.html",

    TEMPLATES_DIR / "reports.html",
    TEMPLATES_DIR / "audit_log.html",

    TEMPLATES_DIR / "roles.html",
    TEMPLATES_DIR / "settings.html",
    TEMPLATES_DIR / "database.html",
]


# ============================================================
# REUSABLE TEMPLATE COMPONENTS
# ============================================================

COMPONENT_FILES = [
    COMPONENTS_DIR / "sidebar.html",
    COMPONENTS_DIR / "navbar.html",
    COMPONENTS_DIR / "alerts.html",
    COMPONENTS_DIR / "stat_card.html",
]


# ============================================================
# STATIC FILES
# ============================================================

STATIC_FILES = [
    CSS_DIR / "admin.css",
    JS_DIR / "admin.js",
]


# ============================================================
# ALL NEW FILES
# ============================================================

FILES = (
    PYTHON_FILES
    + HTML_FILES
    + COMPONENT_FILES
    + STATIC_FILES
)


# ============================================================
# CREATE DIRECTORIES
# ============================================================

def create_directories():
    print()
    print("=" * 65)
    print("Creating admin directories")
    print("=" * 65)

    for directory in DIRECTORIES:
        if directory.exists():
            print(f"[EXISTS]  {directory}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"[CREATED] {directory}")


# ============================================================
# CREATE FILES
# ============================================================

def create_files():
    print()
    print("=" * 65)
    print("Creating admin files")
    print("=" * 65)

    for file_path in FILES:

        if file_path.exists():
            print(f"[SKIPPED] {file_path}")
            continue

        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(
            "",
            encoding="utf-8"
        )

        print(f"[CREATED] {file_path}")


# ============================================================
# DISPLAY STRUCTURE
# ============================================================

def display_structure():
    print()
    print("=" * 65)
    print("Admin system structure")
    print("=" * 65)
    print()

    print("Server/")
    print("└── admin/")
    print("    ├── __init__.py")
    print("    ├── permissions.py")
    print("    ├── decorators.py")
    print("    ├── routes.py")
    print("    ├── services.py")
    print("    ├── audit.py")
    print("    ├── forms.py")
    print("    │")
    print("    ├── templates/")
    print("    │   └── admin/")
    print("    │       ├── base.html")
    print("    │       ├── dashboard.html")
    print("    │       ├── players.html")
    print("    │       ├── pokemon.html")
    print("    │       ├── items.html")
    print("    │       ├── quests.html")
    print("    │       ├── promos.html")
    print("    │       ├── events.html")
    print("    │       ├── reports.html")
    print("    │       ├── audit_log.html")
    print("    │       ├── roles.html")
    print("    │       ├── settings.html")
    print("    │       ├── database.html")
    print("    │       │")
    print("    │       └── components/")
    print("    │           ├── sidebar.html")
    print("    │           ├── navbar.html")
    print("    │           ├── alerts.html")
    print("    │           └── stat_card.html")
    print("    │")
    print("    └── static/")
    print("        ├── css/")
    print("        │   └── admin.css")
    print("        └── js/")
    print("            └── admin.js")
    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 65)
    print("       KRAMPUS RPG ADMIN SYSTEM SETUP")
    print("=" * 65)
    print()

    print("Project:")
    print(f"  {PROJECT_DIR}")
    print()

    # Make sure this is actually the project root.
    if not SERVER_DIR.exists():

        print("[ERROR] Server directory was not found.")
        print()

        print("Expected:")
        print(f"  {SERVER_DIR}")
        print()

        print(
            "Place this script in the root of the "
            "KrampusRPG project."
        )

        return

    create_directories()
    create_files()
    display_structure()

    print("=" * 65)
    print("Setup complete!")
    print("=" * 65)
    print()

    print(
        "Existing files were NOT modified or overwritten."
    )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()