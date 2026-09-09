from Server.database import init_db, seed_database

if __name__ == "__main__":
    init_db()
    seed_database()
    print("Krampus RPG database initialized.")
