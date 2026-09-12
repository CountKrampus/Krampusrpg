from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .auth import current_player_id
from .database import get_connection
from .party_storage import (
    MAX_PARTY_SIZE,
    add_to_party,
    get_party,
    move_party_pokemon,
    remove_from_party,
)
from .pc_storage import (
    PC_SLOTS_PER_PAGE,
    deposit_pokemon,
    ensure_pc_schema,
    get_page,
    get_pc_count,
    get_pc_search_filters,
    get_pokemon_location,
    move_pokemon,
    search_pc,
    swap_pokemon,
    withdraw_pokemon,
)


pc_bp = Blueprint(
    "pc",
    __name__,
)


def _require_player() -> int:
    player_id = current_player_id()

    if player_id is None:
        raise PermissionError(
            "Authentication required."
        )

    return int(player_id)


def _error_response(
    message: str,
    status_code: int = 400,
):
    return jsonify(
        {
            "success": False,
            "error": message,
        }
    ), status_code


@pc_bp.get("/pc")
def pc_page():
    try:
        _require_player()
    except PermissionError:
        return render_template(
            "login.html"
        )

    return render_template(
        "pc.html"
    )


@pc_bp.get("/api/pc")
def pc_index():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    try:
        page = int(
            request.args.get(
                "page",
                1,
            )
        )
    except (TypeError, ValueError):
        page = 1

    page = max(
        1,
        page,
    )

    with get_connection() as db:
        ensure_pc_schema(db)

        pc = get_page(
            db,
            player_id,
            page,
        )

    return jsonify(
        {
            "success": True,
            "pc": pc,
        }
    )


@pc_bp.get("/api/pc/page/<int:page>")
def pc_page_api(page: int):
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    if page < 1:
        return _error_response(
            "Page must be at least 1.",
            400,
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        pc = get_page(
            db,
            player_id,
            page,
        )

    return jsonify(
        {
            "success": True,
            "pc": pc,
        }
    )


@pc_bp.get("/api/pc/party")
def pc_party():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    party = get_party(
        player_id
    )

    return jsonify(
        {
            "success": True,
            "party": party,
            "max_party_size": MAX_PARTY_SIZE,
        }
    )


@pc_bp.get("/api/pc/search")
def pc_search():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    name = request.args.get(
        "name",
        "",
    ).strip()

    variant = request.args.get(
        "variant",
        "",
    ).strip()

    pokemon_type = request.args.get(
        "type",
        "",
    ).strip()

    with get_connection() as db:
        ensure_pc_schema(db)

        results = search_pc(
            db,
            player_id,
            name=name or None,
            variant=variant or None,
            pokemon_type=pokemon_type or None,
        )

    return jsonify(
        {
            "success": True,
            "count": len(results),
            "results": results,
        }
    )


@pc_bp.get("/api/pc/filters")
def pc_filters():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        filters = get_pc_search_filters(
            db,
            player_id,
        )

    return jsonify(
        {
            "success": True,
            "filters": filters,
        }
    )


@pc_bp.get("/api/pc/count")
def pc_count():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        count = get_pc_count(
            db,
            player_id,
        )

    return jsonify(
        {
            "success": True,
            "count": count,
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


@pc_bp.get("/api/pc/pokemon/<int:pokemon_id>")
def pc_pokemon_location(
    pokemon_id: int,
):
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        location = get_pokemon_location(
            db,
            player_id,
            pokemon_id,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/api/pc/deposit")
def pc_deposit():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )
    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id is required.",
            400,
        )

    page = data.get("page")
    slot = data.get("slot")

    try:
        page = (
            int(page)
            if page is not None
            else None
        )

        slot = (
            int(slot)
            if slot is not None
            else None
        )
    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "page and slot must be numbers.",
            400,
        )

    try:
        with get_connection() as db:
            ensure_pc_schema(db)

            location = deposit_pokemon(
                db,
                player_id,
                pokemon_id,
                page=page,
                slot=slot,
            )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    except Exception:
        return _error_response(
            "Unable to deposit that Pokémon.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/api/pc/withdraw")
def pc_withdraw():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )
    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id is required.",
            400,
        )

    try:
        with get_connection() as db:
            ensure_pc_schema(db)

            location = withdraw_pokemon(
                db,
                player_id,
                pokemon_id,
            )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    except Exception:
        return _error_response(
            "Unable to withdraw that Pokémon.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/api/pc/move")
def pc_move():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )

        page = int(
            data.get("page")
        )

        slot = int(
            data.get("slot")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id, page and slot are required.",
            400,
        )

    try:
        with get_connection() as db:
            ensure_pc_schema(db)

            location = move_pokemon(
                db,
                player_id,
                pokemon_id,
                page,
                slot,
            )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/api/pc/swap")
def pc_swap():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id_a = int(
            data.get("pokemon_id_a")
        )

        pokemon_id_b = int(
            data.get("pokemon_id_b")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id_a and pokemon_id_b are required.",
            400,
        )

    try:
        with get_connection() as db:
            ensure_pc_schema(db)

            result = swap_pokemon(
                db,
                player_id,
                pokemon_id_a,
                pokemon_id_b,
            )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    return jsonify(
        {
            "success": True,
            "result": result,
        }
    )


@pc_bp.post("/api/pc/party/add")
def pc_party_add():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )
    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id is required.",
            400,
        )

    slot = data.get("slot")

    try:
        if slot is not None:
            slot = int(slot)

        result = add_to_party(
            player_id,
            pokemon_id,
            slot=slot,
        )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    return jsonify(
        {
            "success": True,
            "party": result,
        }
    )


@pc_bp.post("/api/pc/party/remove")
def pc_party_remove():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )
    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id is required.",
            400,
        )

    try:
        result = remove_from_party(
            player_id,
            pokemon_id,
        )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    return jsonify(
        {
            "success": True,
            "party": result,
        }
    )


@pc_bp.post("/api/pc/party/move")
def pc_party_move():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = request.get_json(
        silent=True
    ) or {}

    try:
        pokemon_id = int(
            data.get("pokemon_id")
        )

        slot = int(
            data.get("slot")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "pokemon_id and slot are required.",
            400,
        )

    try:
        result = move_party_pokemon(
            player_id,
            pokemon_id,
            slot,
        )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )

    return jsonify(
        {
            "success": True,
            "party": result,
        }
    )