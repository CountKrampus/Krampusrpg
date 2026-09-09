from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "Data"
WEB_DIR = BASE_DIR / "Web"
INSTANCE_DIR = BASE_DIR / "instance"

DATABASE_PATH = INSTANCE_DIR / "krampus_rpg.sqlite3"

SECRET_KEY = "change-this-secret-key-before-public-deployment"

HOST = "127.0.0.1"
PORT = 5000
