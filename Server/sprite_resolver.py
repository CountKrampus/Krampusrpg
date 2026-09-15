from __future__ import annotations

from typing import Any

from .config import STATIC_DIR
from .services import get_species, get_variant


def resolve_sprite(
    species_id: str,
    variant: str = "normal",
    shiny: bool = False,
    form: str | None = None,
) -> str:
    """
    Resolve the sprite path for a Pokémon based on species, variant, shiny status, and form.

    Args:
        species_id: The Pokémon species identifier
        variant: The variant (normal, mega, gmax, etc.)
        shiny: Whether the Pokémon is shiny
        form: Alternative form (e.g., "alola", "galar", "hisui")

    Returns:
        Relative path to the sprite file
    """
    # Build base filename
    base_name = species_id.lower()

    # Add form if present
    if form:
        base_name = f"{base_name}-{form.lower()}"

    # Add variant if not normal
    if variant and variant.lower() != "normal":
        base_name = f"{base_name}-{variant.lower()}"

    # Add shiny suffix
    if shiny:
        base_name = f"{base_name}-shiny"

    return f"/static/sprites/{base_name}.png"


def resolve_sprite_url(
    species_id: str,
    variant: str = "normal",
    shiny: bool = False,
    form: str | None = None,
) -> str:
    """
    Get the full URL for a Pokémon sprite.

    This is a convenience wrapper around resolve_sprite that ensures
    the path is properly formatted for web usage.
    """
    sprite_path = resolve_sprite(species_id, variant, shiny, form)
    return sprite_path


def get_pokemon_sprite_data(
    pokemon: dict[str, Any],
) -> dict[str, str]:
    """
    Get all sprite variants for a Pokémon.

    Returns a dictionary with sprite URLs for different states:
    - normal: Standard sprite
    - shiny: Shiny variant
    - back: Back view (for battles)
    - back_shiny: Shiny back view
    """
    species_id = pokemon.get("species_id", "")
    variant = pokemon.get("variant", "normal")
    shiny = bool(pokemon.get("shiny", 0))
    form = pokemon.get("form")

    return {
        "normal": resolve_sprite_url(species_id, variant, False, form),
        "shiny": resolve_sprite_url(species_id, variant, True, form),
        "current": resolve_sprite_url(species_id, variant, shiny, form),
    }


def validate_sprite_exists(
    species_id: str,
    variant: str = "normal",
    shiny: bool = False,
    form: str | None = None,
) -> bool:
    """
    Check if a sprite file exists for the given parameters.

    This is useful for graceful fallback when custom sprites
    don't exist for certain combinations.
    """
    import os
    from pathlib import Path

    sprite_path = resolve_sprite(species_id, variant, shiny, form)
    full_path = STATIC_DIR / sprite_path.lstrip("/static/")

    return full_path.exists()


def get_available_variants(
    species_id: str,
) -> list[str]:
    """
    Get list of available sprite variants for a species.

    Checks the sprite directory for files matching the species pattern.
    """
    import os
    from pathlib import Path

    sprites_dir = STATIC_DIR / "sprites"
    if not sprites_dir.exists():
        return ["normal"]

    species_files = list(sprites_dir.glob(f"{species_id.lower()}-*.png"))
    variants = {"normal"}

    for file in species_files:
        # Extract variant from filename
        # Format: species-variant.png or species-form-variant.png
        name = file.stem
        parts = name.split("-")

        if len(parts) >= 2:
            # Last part is likely the variant
            potential_variant = parts[-1]
            if potential_variant not in ["shiny", "back"]:
                variants.add(potential_variant)

    return sorted(list(variants))


__all__ = [
    "resolve_sprite",
    "resolve_sprite_url",
    "get_pokemon_sprite_data",
    "validate_sprite_exists",
    "get_available_variants",
]
