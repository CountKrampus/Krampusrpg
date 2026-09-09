from __future__ import annotations


def calculate_damage(
    attack: int,
    defense: int,
    power: int,
    level: int,
) -> int:
    attack = max(1, attack)
    defense = max(1, defense)
    power = max(1, power)
    level = max(1, level)

    damage = (
        (
            ((2 * level // 5) + 2)
            * power
            * attack
            // defense
        )
        // 50
    ) + 2

    return max(1, damage)


def apply_damage(current_hp: int, damage: int) -> int:
    return max(
        0,
        current_hp - max(0, damage),
    )
