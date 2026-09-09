"""
Krampus RPG Admin Forms / Validation

Centralized validation helpers for administrative actions.

This module intentionally does not depend on Flask-WTF so the
admin system can use the project's existing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ============================================================
# VALIDATION RESULT
# ============================================================

@dataclass
class ValidationResult:
    """
    Result returned by admin validation functions.
    """

    valid: bool
    errors: list[str]

    @property
    def first_error(self) -> str | None:
        """
        Return the first validation error, if one exists.
        """

        if not self.errors:
            return None

        return self.errors[0]


# ============================================================
# BASIC VALIDATORS
# ============================================================

def validate_required(
    value: Any,
    field_name: str,
) -> str | None:
    """
    Validate that a value exists and isn't blank.
    """

    if value is None:
        return f"{field_name} is required."

    if isinstance(value, str) and not value.strip():
        return f"{field_name} is required."

    return None


def validate_integer(
    value: Any,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> tuple[int | None, str | None]:
    """
    Validate and convert a value to an integer.
    """

    if value is None or value == "":
        return None, f"{field_name} is required."

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None, f"{field_name} must be a whole number."

    if minimum is not None and number < minimum:
        return (
            None,
            f"{field_name} must be at least {minimum}.",
        )

    if maximum is not None and number > maximum:
        return (
            None,
            f"{field_name} must be no greater than {maximum}.",
        )

    return number, None


def validate_string(
    value: Any,
    field_name: str,
    minimum_length: int | None = None,
    maximum_length: int | None = None,
) -> tuple[str | None, str | None]:
    """
    Validate a string and optionally enforce its length.
    """

    if value is None:
        return None, f"{field_name} is required."

    value = str(value).strip()

    if not value:
        return None, f"{field_name} is required."

    if (
        minimum_length is not None
        and len(value) < minimum_length
    ):
        return (
            None,
            f"{field_name} must be at least "
            f"{minimum_length} characters.",
        )

    if (
        maximum_length is not None
        and len(value) > maximum_length
    ):
        return (
            None,
            f"{field_name} must be no more than "
            f"{maximum_length} characters.",
        )

    return value, None


# ============================================================
# ROLE VALIDATION
# ============================================================

def validate_role_name(
    role_name: Any,
) -> ValidationResult:
    """
    Validate a role name against the known role list.
    """

    from .permissions import ALL_ROLES

    errors: list[str] = []

    if role_name is None:
        errors.append("Role is required.")

        return ValidationResult(
            valid=False,
            errors=errors,
        )

    role_name = str(role_name).strip().lower()

    if role_name not in ALL_ROLES:
        errors.append(
            f"Invalid role: {role_name}"
        )

    return ValidationResult(
        valid=not errors,
        errors=errors,
    )


# ============================================================
# PERMISSION VALIDATION
# ============================================================

def validate_permission_name(
    permission: Any,
) -> ValidationResult:
    """
    Validate a permission name.
    """

    from .permissions import ALL_PERMISSIONS

    errors: list[str] = []

    if permission is None:
        errors.append(
            "Permission is required."
        )

        return ValidationResult(
            valid=False,
            errors=errors,
        )

    permission = str(permission).strip()

    if permission not in ALL_PERMISSIONS:
        errors.append(
            f"Invalid permission: {permission}"
        )

    return ValidationResult(
        valid=not errors,
        errors=errors,
    )


def validate_permissions(
    permissions: list[Any],
) -> ValidationResult:
    """
    Validate a list of permissions.
    """

    from .permissions import ALL_PERMISSIONS

    errors: list[str] = []

    if permissions is None:
        permissions = []

    for permission in permissions:

        permission = str(permission).strip()

        if permission not in ALL_PERMISSIONS:
            errors.append(
                f"Invalid permission: {permission}"
            )

    return ValidationResult(
        valid=not errors,
        errors=errors,
    )


# ============================================================
# PLAYER VALIDATION
# ============================================================

def validate_player_id(
    player_id: Any,
) -> tuple[int | None, ValidationResult]:
    """
    Validate a player database ID.
    """

    value, error = validate_integer(
        player_id,
        "Player ID",
        minimum=1,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


# ============================================================
# POKÉMON VALIDATION
# ============================================================

def validate_pokemon_id(
    pokemon_id: Any,
) -> tuple[int | None, ValidationResult]:
    """
    Validate a Pokémon database ID.
    """

    value, error = validate_integer(
        pokemon_id,
        "Pokémon ID",
        minimum=1,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


def validate_pokemon_level(
    level: Any,
) -> tuple[int | None, ValidationResult]:
    """
    Validate a Pokémon level.
    """

    value, error = validate_integer(
        level,
        "Level",
        minimum=1,
        maximum=100,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


# ============================================================
# ITEM VALIDATION
# ============================================================

def validate_item_quantity(
    quantity: Any,
) -> tuple[int | None, ValidationResult]:
    """
    Validate an item quantity.

    Zero is allowed when an administrator intentionally wants
    to remove an item from an inventory.
    """

    value, error = validate_integer(
        quantity,
        "Quantity",
        minimum=0,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


# ============================================================
# EVENT / PROMO VALIDATION
# ============================================================

def validate_event_name(
    name: Any,
) -> tuple[str | None, ValidationResult]:
    """
    Validate an event name.
    """

    value, error = validate_string(
        name,
        "Event name",
        minimum_length=1,
        maximum_length=100,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


def validate_promo_name(
    name: Any,
) -> tuple[str | None, ValidationResult]:
    """
    Validate a Daily Promo name.
    """

    value, error = validate_string(
        name,
        "Promo name",
        minimum_length=1,
        maximum_length=100,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


# ============================================================
# SETTINGS VALIDATION
# ============================================================

def validate_setting_name(
    name: Any,
) -> tuple[str | None, ValidationResult]:
    """
    Validate a site setting name.
    """

    value, error = validate_string(
        name,
        "Setting name",
        minimum_length=1,
        maximum_length=100,
    )

    if error:
        return (
            None,
            ValidationResult(
                valid=False,
                errors=[error],
            ),
        )

    return (
        value,
        ValidationResult(
            valid=True,
            errors=[],
        ),
    )


def validate_setting_value(
    value: Any,
) -> ValidationResult:
    """
    Validate a site setting value.

    Values are ultimately stored as strings, but empty values
    are allowed because some settings may intentionally be blank.
    """

    if value is None:
        return ValidationResult(
            valid=False,
            errors=["Setting value is required."],
        )

    return ValidationResult(
        valid=True,
        errors=[],
    )


# ============================================================
# ROLE CHANGE VALIDATION
# ============================================================

def validate_role_change(
    target_player_id: Any,
    new_role: Any,
) -> ValidationResult:
    """
    Validate a request to change a player's role.
    """

    errors: list[str] = []

    player_id, player_result = validate_player_id(
        target_player_id
    )

    if not player_result.valid:
        errors.extend(
            player_result.errors
        )

    role_result = validate_role_name(
        new_role
    )

    if not role_result.valid:
        errors.extend(
            role_result.errors
        )

    return ValidationResult(
        valid=not errors,
        errors=errors,
    )


# ============================================================
# BOOLEAN VALIDATION
# ============================================================

def validate_boolean(
    value: Any,
    field_name: str = "Value",
) -> tuple[bool | None, str | None]:
    """
    Convert common form values to a boolean.
    """

    if isinstance(value, bool):
        return value, None

    if value is None:
        return None, f"{field_name} is required."

    normalized = str(value).strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True, None

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False, None

    return (
        None,
        f"{field_name} must be true or false.",
    )