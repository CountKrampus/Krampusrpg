from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .auth import current_player_id
from .evolution import evolve_pokemon, get_player_evolution_options
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
from .services import (
    get_pokemon,
    get_player_items,
    get_pokemon_learnset,
    get_species_abilities,
    learn_pokemon_move,
)
from .sprite_resolver import get_pokemon_sprite_data


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
# POKÉMON DETAILS
# =============================================================================

@pc_bp.get("/api/pc/pokemon/<int:pokemon_id>/details")
def pc_pokemon_details(
    pokemon_id: int,
):
    """
    Return full details for one of the player's Pokémon: species, types,
    abilities, current moves, stats, sprite URLs, evolution options, and
    current storage location (Party or PC).

    Backs the Pokémon details panel (Sprint 2 / roadmap Phase 3): click a
    Pokémon in Party or PC to see everything about it in one place.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    pokemon = get_pokemon(
        player_id,
        pokemon_id,
    )

    if pokemon is None:
        return _error_response(
            "Pokémon not found.",
            404,
        )

    species = pokemon.get(
        "species"
    ) or {}

    pokemon["types"] = species.get(
        "type",
        [],
    )

    # Abilities available to this species (from the catalog tables or
    # the species JSON, resolved by get_species_abilities()).
    try:
        pokemon["abilities"] = (
            get_species_abilities(
                species
            )
        )
    except Exception:
        pokemon["abilities"] = []

    # Sprite URLs (normal/shiny/current, resolved for this Pokémon's
    # actual variant + shiny status).
    try:
        pokemon["sprites"] = (
            get_pokemon_sprite_data(
                pokemon
            )
        )
    except Exception:
        pokemon["sprites"] = {}

    # Evolution options this Pokémon currently qualifies for, including
    # stone evolutions whose stone is in the player's bag.
    try:
        pokemon["evolution_options"] = (
            get_player_evolution_options(
                pokemon,
                player_id,
            )
        )
    except Exception:
        pokemon["evolution_options"] = []

    # Where it currently lives (Party vs PC page/slot).
    try:
        pokemon["location"] = (
            get_pokemon_location(
                pokemon_id
            )
        )
    except Exception:
        pokemon["location"] = None

    # Species learnset with per-entry known/learnable flags, so the
    # details panel can offer "learn this move" actions.
    try:
        pokemon["learnset"] = (
            get_pokemon_learnset(
                pokemon
            )
        )
    except Exception:
        pokemon["learnset"] = []

    return jsonify(
        {
            "success": True,
            "pokemon": pokemon,
        }
    )


# =============================================================================
# LEARNSET
# =============================================================================

@pc_bp.get("/api/pc/pokemon/<int:pokemon_id>/learnset")
def pc_pokemon_learnset(
    pokemon_id: int,
):
    """
    Return the species learnset for one of the player's Pokémon.

    Each entry is a move record plus:
    - "level": the level the move is learned at
    - "known": whether this Pokémon already knows the move
    - "level_met": whether this Pokémon's level meets the requirement
    - "learnable": not known yet AND level requirement met
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    pokemon = get_pokemon(
        player_id,
        pokemon_id,
    )

    if pokemon is None:
        return _error_response(
            "Pokémon not found.",
            404,
        )

    try:
        learnset = get_pokemon_learnset(
            pokemon
        )
    except Exception:
        learnset = []

    return jsonify(
        {
            "success": True,
            "pokemon_id": pokemon_id,
            "learnset": learnset,
        }
    )


# =============================================================================
# EQUIP (LEARN) MOVE
# =============================================================================

@pc_bp.post("/api/pc/pokemon/<int:pokemon_id>/moves")
def pc_pokemon_learn_move(
    pokemon_id: int,
):
    """
    Teach one of the player's Pokémon a move from its learnset.

    Expects a JSON body: {"move": "vine_whip"} and, when all 4 move
    slots are full, {"replace_slot": 1-4} to swap out the move in that
    slot. All validation (learnset membership, level gate, duplicate,
    slot bounds) happens server-side.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    # Ownership check: get_pokemon() only returns a row when
    # owner_id == player_id.
    pokemon = get_pokemon(
        player_id,
        pokemon_id,
    )

    if pokemon is None:
        return _error_response(
            "Pokémon not found.",
            404,
        )

    data = _get_json()

    move_id = data.get(
        "move"
    )

    if not move_id or not str(move_id).strip():
        return _error_response(
            "move is required.",
            400,
        )

    replace_slot = data.get(
        "replace_slot"
    )

    if replace_slot is not None:
        try:
            replace_slot = int(replace_slot)

            if not 1 <= replace_slot <= 4:
                raise ValueError
        except (TypeError, ValueError):
            return _error_response(
                "replace_slot must be between 1 and 4.",
                400,
            )

    from .database import get_connection

    try:
        with get_connection() as db:
            result = learn_pokemon_move(
                db,
                pokemon_id,
                str(move_id),
                replace_slot=replace_slot,
            )
    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
        )
    except Exception:
        return _error_response(
            "Failed to learn move.",
            500,
        )

    # Re-fetch through the normal details path so the response carries
    # the same shape the details panel expects.
    updated = get_pokemon(
        player_id,
        pokemon_id,
    )

    try:
        updated_learnset = (
            get_pokemon_learnset(updated)
            if updated
            else []
        )
    except Exception:
        updated_learnset = []

    return jsonify(
        {
            "success": True,
            "learned": result,
            "moves": (
                updated.get("moves", [])
                if updated
                else []
            ),
            "learnset": updated_learnset,
        }
    )


# =============================================================================
# EVOLVE
# =============================================================================

@pc_bp.post("/api/pc/pokemon/<int:pokemon_id>/evolve")
def pc_pokemon_evolve(
    pokemon_id: int,
):
    """
    Evolve one of the player's Pokémon into a target species.

    Expects a JSON body: {"to_species": "ivysaur"}

    All validation happens server-side: the Pokémon must belong to the
    caller and the target must be one of the evolution options the
    Pokémon currently qualifies for (from the seeded evolution rules),
    so a client can never request an arbitrary species.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    # Ownership check: get_pokemon() only returns a row when
    # owner_id == player_id (same pattern as the nickname route).
    pokemon = get_pokemon(
        player_id,
        pokemon_id,
    )

    if pokemon is None:
        return _error_response(
            "Pokémon not found.",
            404,
        )

    data = _get_json()

    to_species = data.get(
        "to_species"
    )

    if not to_species or not str(to_species).strip():
        return _error_response(
            "to_species is required.",
            400,
        )

    item = data.get(
      "item"
    )

    try:
        evolve_pokemon(
            pokemon_id,
            str(to_species),
            player_id=player_id,
            item=(
                str(item).strip().lower()
                if item and str(item).strip()
                else None
            ),
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
            "Evolution failed.",
            500,
        )

    # Re-fetch through the normal details path so the response carries
    # the same shape the details panel expects.
    updated = get_pokemon(
        player_id,
        pokemon_id,
    )

    if updated is None:
        return _error_response(
            "Evolution failed.",
            500,
        )

    species = updated.get(
        "species"
    ) or {}

    updated["types"] = species.get(
        "type",
        [],
    )

    try:
        updated["abilities"] = (
            get_species_abilities(
                species
            )
        )
    except Exception:
        updated["abilities"] = []

    try:
        updated["evolution_options"] = (
            get_player_evolution_options(
                updated,
                player_id,
            )
        )
    except Exception:
        updated["evolution_options"] = []

    try:
        updated["location"] = (
            get_pokemon_location(
                pokemon_id
            )
        )
    except Exception:
        updated["location"] = None

    return jsonify(
        {
            "success": True,
            "pokemon": updated,
        }
    )


# =============================================================================
# INVENTORY (read-only, backs the evolution stone flow)
# =============================================================================

@pc_bp.get("/api/pc/inventory")
def pc_inventory():
    """
    Return the player's item inventory (id, name, quantity).

    Read-only; used by the PC panel to decide which item-based
    evolutions (e.g. stone evolutions) the player can actually perform.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    items = get_player_items(player_id)

    return jsonify(
        {
            "success": True,
            "items": items,
        }
    )


# =============================================================================
# NICKNAME
# =============================================================================

@pc_bp.post("/api/pc/pokemon/<int:pokemon_id>/nickname")
def pc_pokemon_nickname(
    pokemon_id: int,
):
    """
    Rename (or clear the nickname of) one of the player's Pokémon.
    """
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    # Ownership check: get_pokemon() only returns a row when
    # owner_id == player_id, so a None result here also covers
    # "this Pokémon belongs to someone else" without leaking that
    # distinction to the caller.
    pokemon = get_pokemon(
        player_id,
        pokemon_id,
    )

    if pokemon is None:
        return _error_response(
            "Pokémon not found.",
            404,
        )

    data = _get_json()

    nickname = data.get(
        "nickname"
    )

    if nickname is not None:
        nickname = str(
            nickname
        ).strip()[:32]

        if not nickname:
            nickname = None

    from .database import get_connection

    with get_connection() as db:
        db.execute(
            """
            UPDATE pokemon
            SET nickname = ?
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                nickname,
                pokemon_id,
                player_id,
            ),
        )
        db.commit()

    return jsonify(
        {
            "success": True,
            "nickname": nickname,
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