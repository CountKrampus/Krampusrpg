from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .auth import current_player_id
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


# =============================================================================
# HELPERS
# =============================================================================

def _require_player() -> int:
    """
    Return the currently authenticated player ID.

    Raises:
        PermissionError: If no authenticated player exists.
    """
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


def _get_json() -> dict:
    """
    Safely return a JSON request body.
    """
    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        return {}

    return data


def _optional_int(
    value,
    default=None,
):
    """
    Convert an optional value to int.
    """
    if value is None or value == "":
        return default

    return int(value)


def _parse_shiny(value):
    """
    Convert common query-string representations of shiny into
    True, False, or None.
    """
    if value is None:
        return None

    text = str(value).strip().lower()

    if text == "":
        return None

    if text in {
        "1",
        "true",
        "yes",
        "on",
        "shiny",
    }:
        return True

    if text in {
        "0",
        "false",
        "no",
        "off",
        "normal",
        "non-shiny",
    }:
        return False

    return None


# =============================================================================
# PC PAGE
# =============================================================================

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


# =============================================================================
# PC DATA
# =============================================================================

@pc_bp.get("/api/pc")
def pc_index():
    """
    Return one PC page.

    PC storage:
        - database-backed
        - 30 slots per page
        - unlimited pages
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

    try:
        pc = get_page(
            player_id,
            page,
        )

        page_count = get_pc_page_count(
            player_id,
        )

        total_count = get_pc_count(
            player_id,
        )

    except Exception:
        return _error_response(
            "Unable to load the Pokémon PC.",
            500,
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
    Return a specific PC page.
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

    try:
        pc = get_page(
            player_id,
            page,
        )

        page_count = get_pc_page_count(
            player_id,
        )

        total_count = get_pc_count(
            player_id,
        )

    except Exception:
        return _error_response(
            "Unable to load the Pokémon PC.",
            500,
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


# =============================================================================
# PARTY
# =============================================================================

@pc_bp.get("/api/pc/party")
def pc_party():
    """
    Return the player's current Party.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    try:
        party = get_party(
            player_id
        )
    except Exception:
        return _error_response(
            "Unable to load the Party.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "party": party,
            "max_party_size": MAX_PARTY_SIZE,
        }
    )


@pc_bp.post("/api/pc/party/add")
def pc_party_add():
    """
    Add an owned Pokémon to the Party.

    If it is currently in the PC, the Party storage layer is
    responsible for moving it out of PC storage atomically.
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
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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

    try:
        party = get_party(
            player_id
        )
    except Exception:
        party = result

    return jsonify(
        {
            "success": True,
            "party": party,
            "result": result,
        }
    )


@pc_bp.post("/api/pc/party/remove")
def pc_party_remove():
    """
    Remove a Pokémon from the Party.

    The storage layer automatically moves it into PC storage.
    The Pokémon itself is never deleted.
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
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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

    try:
        party = get_party(
            player_id
        )
    except Exception:
        party = []

    return jsonify(
        {
            "success": True,
            "party": party,
            "location": result,
        }
    )


@pc_bp.post("/api/pc/party/move")
def pc_party_move():
    """
    Move a Pokémon to another Party slot.
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
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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

    try:
        party = get_party(
            player_id
        )
    except Exception:
        party = []

    return jsonify(
        {
            "success": True,
            "party": party,
            "result": result,
        }
    )


# =============================================================================
# PC SEARCH
# =============================================================================

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

    if not pokemon_type:
        pokemon_type = request.args.get(
            "pokemon_type",
            "",
        ).strip()

    shiny = _parse_shiny(
        request.args.get(
            "shiny"
        )
    )

    try:
        results = search_pc(
            player_id=player_id,
            search=name or None,
            variant=variant or None,
            pokemon_type=pokemon_type or None,
            shiny=shiny,
        )
    except Exception:
        return _error_response(
            "Unable to search the Pokémon PC.",
            500,
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
    Return available PC search filters.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    try:
        filters = get_pc_search_filters(
            player_id
        )
    except Exception:
        return _error_response(
            "Unable to load PC search filters.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "filters": filters,
        }
    )


# =============================================================================
# PC COUNTS
# =============================================================================

@pc_bp.get("/api/pc/count")
def pc_count():
    """
    Return the player's total PC Pokémon count.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    try:
        count = get_pc_count(
            player_id
        )

        page_count = get_pc_page_count(
            player_id
        )

    except Exception:
        return _error_response(
            "Unable to load PC counts.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "count": count,
            "page_count": page_count,
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


# =============================================================================
# POKÉMON LOCATION
# =============================================================================

@pc_bp.get("/api/pc/pokemon/<int:pokemon_id>")
def pc_pokemon_location(
    pokemon_id: int,
):
    """
    Return the storage location of a Pokémon.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    try:
        location = get_pokemon_location(
            pokemon_id
        )
    except Exception:
        return _error_response(
            "Unable to determine Pokémon location.",
            500,
        )

    location_player_id = location.get(
        "player_id"
    )

    if location_player_id is not None:
        if int(location_player_id) != int(player_id):
            return _error_response(
                "You do not own this Pokémon.",
                403,
            )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


# =============================================================================
# DEPOSIT
# =============================================================================

@pc_bp.post("/api/pc/deposit")
def pc_deposit():
    """
    Deposit an unassigned owned Pokémon into PC storage.

    A Pokémon currently in the Party should use the Party remove
    endpoint so the Party -> PC transition remains atomic.
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
        result = deposit_pokemon(
            player_id,
            pokemon_id,
            page=page,
            slot=slot,
        )
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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
            "location": result,
        }
    )


# =============================================================================
# WITHDRAW
# =============================================================================

@pc_bp.post("/api/pc/withdraw")
def pc_withdraw():
    """
    Withdraw a Pokémon from the PC.

    IMPORTANT:
    PC -> Party is atomic.

    The Pokémon will never be intentionally left unassigned.
    If the Party is full, the PC record remains untouched.
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
        result = withdraw_pokemon(
            player_id,
            pokemon_id,
        )
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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

    try:
        party = get_party(
            player_id
        )
    except Exception:
        party = []

    return jsonify(
        {
            "success": True,
            "location": result,
            "party": party,
        }
    )


# =============================================================================
# MOVE
# =============================================================================

@pc_bp.post("/api/pc/move")
def pc_move():
    """
    Move a Pokémon to an empty PC position.
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
        result = move_pokemon(
            player_id,
            pokemon_id,
            page,
            slot,
        )
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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
            "location": result,
        }
    )


# =============================================================================
# SWAP
# =============================================================================

@pc_bp.post("/api/pc/swap")
def pc_swap():
    """
    Swap two Pokémon currently stored in the PC.

    The storage layer performs the swap atomically.
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
        # Support an alternate client naming convention.
        try:
            pokemon_id_a = int(
                data.get("source_pokemon_id")
            )

            pokemon_id_b = int(
                data.get("target_pokemon_id")
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
        result = swap_pokemon(
            player_id,
            pokemon_id_a,
            pokemon_id_b,
        )
    except PermissionError as exc:
        return _error_response(
            str(exc),
            403,
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


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@pc_bp.errorhandler(404)
def pc_not_found(error):
    return _error_response(
        "PC endpoint not found.",
        404,
    )


@pc_bp.errorhandler(405)
def pc_method_not_allowed(error):
    return _error_response(
        "Method not allowed.",
        405,
    )