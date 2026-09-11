# 🎮 Pokémon System - Quick Reference

## File Structure

```
Game/pokemon/
├── __init__.py              (6 exports)
├── pokemon_data.py          (200 lines)   - Species/moves/abilities/items
├── pokemon_model.py         (380 lines)   - Core Pokémon class
├── party_and_storage.py     (420 lines)   - Party + Krampus PC
└── pokemon_db.py            (310 lines)   - Database CRUD

Server/pokemon_routes.py     (280 lines)   - API endpoints
```

**Total: 1,800+ lines of production code**

---

## Import Examples

```python
# Core classes
from Game.pokemon import Pokemon, Move, Party, KrampusPC, PokemonDB

# Enums
from Game.pokemon import Gender, Status

# Data loaders
from Game.pokemon import (
    get_pokemon_species, get_move, get_ability, get_item,
    POKEMON_SPECIES, MOVES, ABILITIES, ITEMS
)
```

---

## Creating Pokémon

### Method 1: Database (Recommended)
```python
pokemon = PokemonDB.create_pokemon(
    owner_id=1,
    species_id="pikachu",
    level=5,
    nickname="Sparky",
    gender="male",
    shiny=False,
    nature="Jolly"
)
```

### Method 2: Direct Class
```python
pokemon = Pokemon(
    unique_id="pokemon_abc123",
    species_id="charizard",
    owner_id=1,
    level=16,
    gender="female"
)
```

---

## Party Management

```python
party = Party(player_id=1)

party.add(pokemon1)                    # Add Pokémon
party.set_lead(0)                      # Set battle lead
party.swap(0, 1)                       # Rearrange
party.remove(2)                        # Remove by index

lead = party.get_lead()                # Get lead
active = party.get_active_pokemon()    # Get non-fainted
is_full = party.is_full()              # Check capacity

party_dict = party.to_dict()           # JSON output
```

---

## PC Storage

```python
pc = KrampusPC(player_id=1)

# Add Pokémon
pc.add_pokemon(pokemon)                # Auto finds slot
pc.add_pokemon(pokemon, box_id=2)      # Specific box
pc.add_pokemon(pokemon, 2, 15)         # Box 2, slot 15

# Navigate
pc.switch_box(1)                       # Go to Box 2
current_box = pc.get_current_box()    # Get current

# Move between boxes
pc.move_pokemon(0, 5, 1, 10)           # Box 0 slot 5 → Box 1 slot 10

# Query
all_pkmn = pc.get_all_pokemon()        # Get all stored
count = pc.get_pokemon_count()         # Total count
free = pc.get_free_slots()             # Available slots
found = pc.find_pokemon(unique_id)     # Search by ID
```

---

## Pokémon Actions

```python
pokemon.level_up(5)                    # Increase level by 5
pokemon.add_experience(250)            # Add XP (auto-levels at 100*level)
pokemon.take_damage(35)                # Deal damage
pokemon.heal(50)                       # Heal HP
pokemon.apply_status(Status.BURNED)    # Apply status
pokemon.cure_status()                  # Remove status
pokemon.is_fainted()                   # Check if KO'd
pokemon.to_dict()                      # JSON output
```

---

## Stat Calculation

### Getting Current Stats
```python
pokemon.stats.hp              # 45
pokemon.stats.attack          # 78
pokemon.stats.defense         # 62
pokemon.stats.sp_attack       # 89
pokemon.stats.sp_defense      # 91
pokemon.stats.speed           # 72
```

### IV/EV Access
```python
pokemon.ivs.hp                # 0-31 (random)
pokemon.evs.hp                # 0-252 (trained)
pokemon.nature                # "Jolly", "Adamant", etc.
```

---

## Database Operations

```python
# Create
pokemon = PokemonDB.create_pokemon(owner_id, species_id, level, ...)

# Read
pokemon = PokemonDB.get_pokemon(unique_id)
all_pokemon = PokemonDB.get_player_pokemon(player_id)

# Update
PokemonDB.update_pokemon(pokemon)

# Delete
PokemonDB.delete_pokemon(unique_id)     # Soft delete (mark inactive)
```

---

## API Endpoints

### Party
```
GET    /api/pokemon/party
POST   /api/pokemon/party/add
DELETE /api/pokemon/party/remove/<index>
```

### PC Storage
```
GET    /api/pokemon/pc
POST   /api/pokemon/pc/switch-box/<box_id>
```

### Pokémon
```
POST   /api/pokemon/create
GET    /api/pokemon/<unique_id>
POST   /api/pokemon/<unique_id>/update
DELETE /api/pokemon/<unique_id>
```

### Info
```
GET    /api/pokemon/species/<species_id>
GET    /api/pokemon/stats/summary
```

---

## Status Conditions

```python
Status.HEALTHY      # Normal state
Status.BURNED       # Fire damage effect
Status.POISONED     # Poison damage
Status.PARALYZED    # Reduced speed
Status.ASLEEP       # Can't attack
Status.FROZEN       # Can't attack
Status.CONFUSED     # May self-damage
```

---

## Natures

**5 Neutral**: Hardy, Docile, Serious, Bashful, Quirky

**Attack-boosting** (Atk ↑): Lonely, Brave, Adamant, Naughty

**Defense-boosting** (Def ↑): Bold, Relaxed, Impish, Lax

**Speed-boosting** (Spe ↑): Timid, Hasty, Jolly, Naive

**Sp. Atk-boosting** (SpA ↑): Modest, Mild, Quiet, Rash

**Sp. Def-boosting** (SpD ↑): Calm, Gentle, Sassy, Careful

---

## Game Data Loading

```python
# Load species data
species = get_pokemon_species("pikachu")
# Returns: name, type, base_stats, abilities, catch_rate, etc.

# Load move data
move = get_move("thunderbolt")
# Returns: name, type, power, accuracy, pp, target

# Load ability data
ability = get_ability("static")
# Returns: name, description

# Load item data
item = get_item("potion")
# Returns: name, description, effect, amount
```

---

## Constants

```python
Party.MAX_SIZE           # 6
PokemonBox.SIZE          # 30
KrampusPC.MAX_BOXES      # 21

# Total capacity
630 storage + 6 party = 636 total per player

# Natures
len(NATURES)             # 25

# Status conditions
len(Status)              # 6
```

---

## Common Patterns

### Get player's team
```python
from Game.pokemon import PokemonDB, Party

def get_player_team(player_id):
    party = Party(player_id)
    all_pokemon = PokemonDB.get_player_pokemon(player_id)
    for pokemon in all_pokemon[:6]:
        party.add(pokemon)
    return party
```

### Find Pokémon
```python
def find_pokemon_in_pc(player_id, unique_id):
    pc = KrampusPC(player_id)
    return pc.find_pokemon(unique_id)  # Returns (box_id, slot) or None
```

### Calculate team total level
```python
def team_average_level(player_id):
    all_pokemon = PokemonDB.get_player_pokemon(player_id)
    if not all_pokemon:
        return 0
    return sum(p.level for p in all_pokemon) / len(all_pokemon)
```

---

## Tips & Tricks

- ✅ **Pokémon are unique**: Each has a UUID, can't have duplicates
- ✅ **Soft delete**: Deleted Pokémon stay in DB, just marked inactive
- ✅ **Auto PC organization**: `pc.add_pokemon()` finds first free slot
- ✅ **Lead matters**: Lead Pokémon goes first in battle
- ✅ **Stats are read-only**: Calculated from base + IV + EV + level + nature
- ✅ **Caching**: Game data (species, moves, etc.) is cached in memory

---

## Error Handling

```python
# Always check for None
pokemon = PokemonDB.get_pokemon(unique_id)
if pokemon is None:
    print("Pokémon not found!")

# Party operations return bool
if not party.add(pokemon):
    print("Party is full!")

# PC operations return None on failure
removed = pc.remove_pokemon(box_id, slot)
if removed is None:
    print("Slot was empty!")
```

---

## Performance Notes

- 📊 **IVs/EVs**: Randomized on creation, not regenerated
- 📊 **Stats**: Calculated once per level-up
- 📊 **Database**: Uses transactions for consistency
- 📊 **Storage**: 630 slots × 30 (per box) is efficiently organized

---

**Ready to build battles on top of this!** 🚀

