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
    get_pc_page_count,
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
    """
    Return the currently authenticated player ID.

    Raises:
        PermissionError: If no authenticated player exists.
    """
    player_id = current_player_id()

    if player_id is None:
        raise PermissionError("Authentication required.")

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


def _get_json():
    """
    Safely return a JSON request body.

    Flask may return None for an empty or invalid JSON body.
    """
    return request.get_json(
        silent=True
    ) or {}


def _optional_int(
    value,
    default=None,
):
    """
    Convert an optional value to int.

    Returns default when value is None or empty.
    Raises ValueError for invalid numeric input.
    """
    if value is None or value == "":
        return default

    return int(value)


@pc_bp.get("/pc")
def pc_page():
    """
    Render the Pokémon PC interface.
    """
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
    """
    Get one PC page.

    PC storage is database-backed and has unlimited pages,
    with PC_SLOTS_PER_PAGE slots on each page.
    """
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
    except (
        TypeError,
        ValueError,
    ):
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

        page_count = get_pc_page_count(
            db,
            player_id,
        )

        total_count = get_pc_count(
            db,
            player_id,
        )

    return jsonify(
        {
            "success": True,
            "pc": pc,
            "page": page,
            "page_count": page_count,
            "total_count": total_count,
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


@pc_bp.get("/api/pc/page/<int:page>")
def pc_page_api(page: int):
    """
    Get a specific PC page.
    """
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

        page_count = get_pc_page_count(
            db,
            player_id,
        )

        total_count = get_pc_count(
            db,
            player_id,
        )

    return jsonify(
        {
            "success": True,
            "pc": pc,
            "page": page,
            "page_count": page_count,
            "total_count": total_count,
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


@pc_bp.get("/api/pc/party")
def pc_party():
    """
    Return the player's current six-Pokémon Party.
    """
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
    """
    Search the player's entire PC.

    Supported filters:
        name
        variant
        type
        shiny

    Filters can be combined.
    """
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

    shiny_value = request.args.get(
        "shiny",
        "",
    ).strip().lower()

    shiny = None

    if shiny_value in {
        "1",
        "true",
        "yes",
        "on",
    }:
        shiny = True

    elif shiny_value in {
        "0",
        "false",
        "no",
        "off",
    }:
        shiny = False

    with get_connection() as db:
        ensure_pc_schema(db)

        results = search_pc(
            db,
            player_id,
            name=name or None,
            variant=variant or None,
            pokemon_type=pokemon_type or None,
            shiny=shiny,
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
    """
    Return available search/filter values for the player's PC.
    """
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
    """
    Return the player's total number of Pokémon currently in the PC.
    """
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

        page_count = get_pc_page_count(
            db,
            player_id,
        )

    return jsonify(
        {
            "success": True,
            "count": count,
            "page_count": page_count,
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


@pc_bp.get("/api/pc/pokemon/<int:pokemon_id>")
def pc_pokemon_location(
    pokemon_id: int,
):
    """
    Return the storage location of a player's Pokémon.

    A Pokémon can be:
        party
        pc
        unassigned
    """
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
    """
    Deposit an owned Pokémon directly into the PC.

    Party Pokémon should normally use the Party remove endpoint,
    which automatically transfers them into PC storage.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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
        page = _optional_int(
            data.get("page")
        )

        slot = _optional_int(
            data.get("slot")
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
    """
    Withdraw a Pokémon from PC storage.

    Withdrawing removes the PC location record.
    It does not delete the Pokémon.

    Adding the withdrawn Pokémon to the Party is a separate
    operation through /api/pc/party/add.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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
    """
    Move a Pokémon to a specific PC page and slot.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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

    if page < 1:
        return _error_response(
            "Page must be at least 1.",
            400,
        )

    if slot < 1 or slot > PC_SLOTS_PER_PAGE:
        return _error_response(
            f"Slot must be between 1 and {PC_SLOTS_PER_PAGE}.",
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

    except Exception:
        return _error_response(
            "Unable to move that Pokémon.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/api/pc/swap")
def pc_swap():
    """
    Swap the PC locations of two Pokémon.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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

    if pokemon_id_a == pokemon_id_b:
        return _error_response(
            "A Pokémon cannot be swapped with itself.",
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

    except Exception:
        return _error_response(
            "Unable to swap those Pokémon.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "result": result,
        }
    )


@pc_bp.post("/api/pc/party/add")
def pc_party_add():
    """
    Add an owned Pokémon to the player's Party.

    If the Pokémon is currently in the PC, its PC location is
    removed automatically by party_storage.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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
        slot = _optional_int(
            data.get("slot")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _error_response(
            "slot must be a number.",
            400,
        )

    if slot is not None:
        if slot < 1 or slot > MAX_PARTY_SIZE:
            return _error_response(
                f"Party slot must be between 1 and {MAX_PARTY_SIZE}.",
                400,
            )

    try:
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

    except Exception:
        return _error_response(
            "Unable to add that Pokémon to the Party.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "party": result,
        }
    )


@pc_bp.post("/api/pc/party/remove")
def pc_party_remove():
    """
    Remove a Pokémon from the Party.

    IMPORTANT:
    This does NOT delete the Pokémon.

    Party -> PC is automatic.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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

    except Exception:
        return _error_response(
            "Unable to move that Pokémon to the PC.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "party": get_party(
                player_id
            ),
            "location": result,
        }
    )


@pc_bp.post("/api/pc/party/move")
def pc_party_move():
    """
    Move a Pokémon to a different Party slot.

    Party size remains limited to six.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    data = _get_json()

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

    if slot < 1 or slot > MAX_PARTY_SIZE:
        return _error_response(
            f"Party slot must be between 1 and {MAX_PARTY_SIZE}.",
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

    except Exception:
        return _error_response(
            "Unable to move that Pokémon in the Party.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "party": get_party(
                player_id
            ),
            "result": result,
        }
    )