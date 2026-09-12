from __future__ import annotations

from flask import Blueprint, jsonify, request

from .auth import current_player_id
from .pc_storage import (
    PC_SLOTS_PER_PAGE,
    deposit_pokemon,
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
    url_prefix="/api/pc",
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


@pc_bp.get("")
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
    except ValueError:
        page = 1

    if page < 1:
        page = 1

    return jsonify(
        {
            "success": True,
            "pc": get_page(
                player_id,
                page,
            ),
        }
    )


@pc_bp.get("/page/<int:page>")
def pc_page(page: int):
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

    return jsonify(
        {
            "success": True,
            "pc": get_page(
                player_id,
                page,
            ),
        }
    )


@pc_bp.get("/search")
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

    results = search_pc(
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


@pc_bp.get("/filters")
def pc_filters():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    return jsonify(
        {
            "success": True,
            "filters": get_pc_search_filters(
                player_id
            ),
        }
    )


@pc_bp.get("/count")
def pc_count():
    try:
        player_id = _require_player()
    except PermissionError as exc:
        return _error_response(
            str(exc),
            401,
        )

    return jsonify(
        {
            "success": True,
            "count": get_pc_count(
                player_id
            ),
            "slots_per_page": PC_SLOTS_PER_PAGE,
        }
    )


@pc_bp.get("/pokemon/<int:pokemon_id>")
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

    try:
        location = get_pokemon_location(
            player_id,
            pokemon_id,
        )
    except ValueError as exc:
        return _error_response(
            str(exc),
            404,
        )

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/deposit")
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

        location = deposit_pokemon(
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

    return jsonify(
        {
            "success": True,
            "location": location,
        }
    )


@pc_bp.post("/withdraw")
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
        location = withdraw_pokemon(
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
            "location": location,
        }
    )


@pc_bp.post("/move")
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
        location = move_pokemon(
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


@pc_bp.post("/swap")
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
        success = swap_pokemon(
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
            "success": success,
        }
    )