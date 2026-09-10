from pathlib import Path

from livereload import Server

from Server.app import create_app


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "Web"

TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


app = create_app()


if __name__ == "__main__":
    server = Server(app.wsgi_app)

    server.watch(str(TEMPLATES_DIR))
    server.watch(str(STATIC_DIR))

    print()
    print("=" * 60)
    print("KRAMPUS RPG DEVELOPMENT SERVER")
    print("=" * 60)
    print()
    print("Local:   http://127.0.0.1:5050")
    print("Network: http://192.168.2.248:5050")
    print()
    print("LiveReload is ENABLED.")
    print("Save an HTML, CSS, or JavaScript file to reload the browser.")
    print()
    print("=" * 60)
    print()

    server.serve(
        host="0.0.0.0",
        port=5050,
        restart_delay=0.5,
    )