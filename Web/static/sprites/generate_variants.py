from pathlib import Path
from PIL import Image


# ============================================================
# KRAMPUS RPG
# FULL POKÉMON COLOR VARIANT GENERATOR
# ============================================================
#
# FULL RECOLOR VERSION
#
# Every visible pixel is recolored into the selected variant's
# color family.
#
# The original pixel's BRIGHTNESS is preserved so the sprite
# keeps its shading.
#
# Original RGB colors are NOT preserved.
#
# Transparency IS preserved.
#
# ============================================================


# ============================================================
# FOLDERS
# ============================================================

SOURCE_DIR = Path(__file__).parent

OUTPUT_DIR = SOURCE_DIR / "variants"

TEST_FILE = SOURCE_DIR / "test_pokemon.txt"


# ============================================================
# MODE
# ============================================================
#
# True:
#     Only Pokémon listed in test_pokemon.txt are processed.
#
# False:
#     Every PNG directly inside the regular folder is processed.
#
# ============================================================

TEST_MODE = False


# ============================================================
# FILES TO IGNORE
# ============================================================

IGNORED_FILES = {
    "base_sprite.png",
}


# ============================================================
# VARIANT PALETTES
# ============================================================
#
# dark  = shadows / darkest areas
# base  = primary body color
# light = highlights
#
# Every visible pixel is mapped into this palette based on its
# original brightness.
#
# ============================================================

VARIANTS = {

    "ruby": {
        "dark": (70, 5, 12),
        "base": (190, 25, 45),
        "light": (255, 105, 120),
    },

    "sapphire": {
        "dark": (5, 20, 70),
        "base": (30, 90, 205),
        "light": (100, 180, 255),
    },

    "emerald": {
        "dark": (5, 55, 25),
        "base": (25, 150, 80),
        "light": (105, 235, 145),
    },

    "gold": {
        "dark": (75, 45, 3),
        "base": (205, 150, 20),
        "light": (255, 225, 100),
    },

    "silver": {
        "dark": (45, 50, 60),
        "base": (145, 155, 170),
        "light": (225, 230, 240),
    },

    "amethyst": {
        "dark": (45, 8, 75),
        "base": (125, 45, 190),
        "light": (205, 120, 255),
    },

    "obsidian": {
        "dark": (3, 3, 6),
        "base": (30, 35, 45),
        "light": (100, 105, 120),
    },

    "pearl": {
        "dark": (85, 80, 100),
        "base": (205, 195, 215),
        "light": (255, 250, 255),
    },

    "crimson": {
        "dark": (45, 2, 6),
        "base": (145, 10, 25),
        "light": (230, 65, 75),
    },

    "azure": {
        "dark": (3, 45, 80),
        "base": (20, 145, 220),
        "light": (110, 225, 255),
    },

    "toxic": {
        "dark": (35, 65, 3),
        "base": (115, 200, 20),
        "light": (205, 255, 90),
    },

    "inferno": {
        "dark": (70, 8, 2),
        "base": (220, 60, 8),
        "light": (255, 175, 35),
    },

    "frost": {
        "dark": (20, 65, 95),
        "base": (95, 185, 220),
        "light": (220, 250, 255),
    },

    "violet": {
        "dark": (35, 3, 60),
        "base": (110, 25, 170),
        "light": (205, 100, 245),
    },

    "rose": {
        "dark": (80, 15, 45),
        "base": (215, 75, 135),
        "light": (255, 165, 205),
    },

    "lime": {
        "dark": (40, 70, 3),
        "base": (125, 210, 30),
        "light": (215, 255, 100),
    },

    "midnight": {
        "dark": (3, 5, 20),
        "base": (30, 40, 95),
        "light": (100, 115, 190),
    },

    "copper": {
        "dark": (60, 22, 6),
        "base": (175, 85, 35),
        "light": (235, 155, 90),
    },
}


# ============================================================
# COLOR HELPERS
# ============================================================

def clamp(value, minimum, maximum):
    """
    Keep a value inside a specified range.
    """

    return max(
        minimum,
        min(maximum, value)
    )


def lerp(a, b, amount):
    """
    Blend between two numerical values.
    """

    return (
        a +
        (b - a) *
        amount
    )


def lerp_color(color_a, color_b, amount):
    """
    Blend between two RGB colors.
    """

    amount = clamp(
        amount,
        0.0,
        1.0
    )

    return (
        int(
            lerp(
                color_a[0],
                color_b[0],
                amount
            )
        ),

        int(
            lerp(
                color_a[1],
                color_b[1],
                amount
            )
        ),

        int(
            lerp(
                color_a[2],
                color_b[2],
                amount
            )
        ),
    )


def luminance(rgb):
    """
    Calculate perceived brightness.

    Returns approximately 0-255.
    """

    r, g, b = rgb

    return (
        0.2126 * r +
        0.7152 * g +
        0.0722 * b
    )


# ============================================================
# LOAD TEST POKÉMON
# ============================================================

def load_test_pokemon():
    """
    Read Pokémon names from test_pokemon.txt.

    One Pokémon per line.

    Blank lines are ignored.

    Lines beginning with # are comments.
    """

    if not TEST_FILE.exists():

        print()

        print(
            "[ERROR] Test file not found:"
        )

        print(
            f"        {TEST_FILE}"
        )

        print()

        print(
            "Create a file named:"
        )

        print(
            "        test_pokemon.txt"
        )

        print()

        print(
            "Example:"
        )

        print(
            "        pikachu"
        )

        print(
            "        charizard"
        )

        print(
            "        bulbasaur"
        )

        print(
            "        gengar"
        )

        print(
            "        mewtwo"
        )

        return set()

    pokemon = set()

    try:

        with open(
            TEST_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:

                name = line.strip().lower()

                # Ignore blank lines
                if not name:
                    continue

                # Ignore comments
                if name.startswith("#"):
                    continue

                # Remove .png if someone included it
                if name.endswith(".png"):
                    name = name[:-4]

                pokemon.add(name)

    except Exception as error:

        print()

        print(
            "[ERROR] Could not read "
            "test_pokemon.txt"
        )

        print(error)

        return set()

    return pokemon


# ============================================================
# BUILD FULL VARIANT PALETTE
# ============================================================

def build_palette(variant):
    """
    Create a 256-step palette.

    Every possible brightness value from 0-255 gets mapped
    to a color belonging to the selected variant.
    """

    data = VARIANTS[variant]

    dark = data["dark"]

    base = data["base"]

    light = data["light"]

    palette = []

    for brightness in range(256):

        normalized = (
            brightness / 255.0
        )

        # ----------------------------------------------------
        # DARK → BASE
        # ----------------------------------------------------

        if normalized < 0.35:

            amount = (
                normalized /
                0.35
            )

            color = lerp_color(
                dark,
                base,
                amount
            )

        # ----------------------------------------------------
        # BASE → LIGHT
        # ----------------------------------------------------

        else:

            amount = (
                normalized - 0.35
            ) / 0.65

            color = lerp_color(
                base,
                light,
                amount
            )

        palette.append(color)

    return palette


# ============================================================
# RECOLOR SPRITE
# ============================================================

def recolor_sprite(image, variant):
    """
    Completely recolor the sprite.

    ORIGINAL COLOR:
        ignored

    ORIGINAL BRIGHTNESS:
        preserved

    TRANSPARENCY:
        preserved

    Example:

        Yellow Pikachu
              ↓
        Ruby Pikachu

        Blue Pokémon
              ↓
        Gold Pokémon

        Green Pokémon
              ↓
        Sapphire Pokémon

    Every visible pixel becomes part of the new color family.
    """

    palette = build_palette(
        variant
    )

    source = image.convert(
        "RGBA"
    )

    width, height = source.size

    output = Image.new(
        "RGBA",
        (width, height),
        (0, 0, 0, 0)
    )

    source_pixels = source.load()

    output_pixels = output.load()

    # --------------------------------------------------------
    # Process every pixel
    # --------------------------------------------------------

    for y in range(height):

        for x in range(width):

            r, g, b, a = (
                source_pixels[x, y]
            )

            # ------------------------------------------------
            # Transparency
            # ------------------------------------------------

            if a == 0:

                output_pixels[x, y] = (
                    0,
                    0,
                    0,
                    0
                )

                continue

            # ------------------------------------------------
            # Determine original brightness
            # ------------------------------------------------

            brightness = luminance(
                (r, g, b)
            )

            brightness = int(
                clamp(
                    brightness,
                    0,
                    255
                )
            )

            # ------------------------------------------------
            # Replace ENTIRE COLOR
            # ------------------------------------------------

            new_color = palette[
                brightness
            ]

            output_pixels[x, y] = (
                new_color[0],
                new_color[1],
                new_color[2],
                a
            )

    return output


# ============================================================
# PROCESS ONE POKÉMON
# ============================================================

def process_pokemon(source_file):

    pokemon_name = (
        source_file.stem.lower()
    )

    print()

    print("-" * 70)

    print(
        f"Processing: {pokemon_name}"
    )

    print("-" * 70)

    # --------------------------------------------------------
    # Open source
    # --------------------------------------------------------

    try:

        image = Image.open(
            source_file
        ).convert("RGBA")

    except Exception as error:

        print(
            f"[ERROR] Could not open "
            f"{source_file.name}"
        )

        print(
            error
        )

        return 0

    # --------------------------------------------------------
    # Pokémon output directory
    # --------------------------------------------------------

    output_folder = (
        OUTPUT_DIR /
        pokemon_name
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    generated = 0

    # --------------------------------------------------------
    # Generate all variants
    # --------------------------------------------------------

    for variant in VARIANTS:

        output_file = (
            output_folder /
            f"{pokemon_name}-{variant}.png"
        )

        try:

            result = recolor_sprite(
                image,
                variant
            )

            result.save(
                output_file,
                "PNG",
                optimize=True
            )

            generated += 1

            print(
                f"  [OK] {variant}"
            )

        except Exception as error:

            print(
                f"  [ERROR] {variant}"
            )

            print(
                f"          {error}"
            )

    print()

    print(
        f"Generated "
        f"{generated}/{len(VARIANTS)} variants."
    )

    return generated


# ============================================================
# FIND POKÉMON FILES
# ============================================================

def find_pokemon_files(test_pokemon):
    """
    Find PNG files directly inside SOURCE_DIR.

    Does NOT search inside:

        female/
        right/
        variants/

    This is intentional because your Pokémon sprites are
    directly inside the regular folder.
    """

    files = []

    for file in SOURCE_DIR.iterdir():

        # Must be a file
        if not file.is_file():
            continue

        # Must be PNG
        if file.suffix.lower() != ".png":
            continue

        # Ignore prototype/test image
        if file.name.lower() in IGNORED_FILES:
            continue

        # ----------------------------------------------------
        # TEST MODE
        # ----------------------------------------------------

        if TEST_MODE:

            if file.stem.lower() not in test_pokemon:
                continue

        files.append(file)

    return sorted(
        files,
        key=lambda x: x.stem.lower()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 70)

    print(
        " KRAMPUS RPG"
    )

    print(
        " FULL POKÉMON COLOR VARIANT GENERATOR"
    )

    print("=" * 70)

    print()

    # --------------------------------------------------------
    # Paths
    # --------------------------------------------------------

    print(
        "Source folder:"
    )

    print(
        f"  {SOURCE_DIR}"
    )

    print()

    print(
        "Output folder:"
    )

    print(
        f"  {OUTPUT_DIR}"
    )

    print()

    # --------------------------------------------------------
    # Load test list
    # --------------------------------------------------------

    test_pokemon = set()

    if TEST_MODE:

        test_pokemon = (
            load_test_pokemon()
        )

        if not test_pokemon:

            print()

            print(
                "[ERROR] No Pokémon were "
                "loaded from test_pokemon.txt."
            )

            print()

            input(
                "Press ENTER to exit..."
            )

            return

        print(
            "MODE: TEST"
        )

        print()

        print(
            "Pokémon from test_pokemon.txt:"
        )

        for pokemon in sorted(
            test_pokemon
        ):

            print(
                f"  - {pokemon}"
            )

    else:

        print(
            "MODE: FULL COLLECTION"
        )

    print()

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Find Pokémon
    # --------------------------------------------------------

    pokemon_files = (
        find_pokemon_files(
            test_pokemon
        )
    )

    if not pokemon_files:

        print(
            "[ERROR] No matching Pokémon "
            "PNG files were found."
        )

        print()

        if TEST_MODE:

            print(
                "Check that the names in "
                "test_pokemon.txt match "
                "the PNG filenames."
            )

            print()

            print(
                "For example:"
            )

            print(
                "  pikachu.txt entry"
            )

            print(
                "  pikachu.png source"
            )

        print()

        input(
            "Press ENTER to exit..."
        )

        return

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    print(
        f"Pokémon found: "
        f"{len(pokemon_files)}"
    )

    print(
        f"Variants per Pokémon: "
        f"{len(VARIANTS)}"
    )

    print(
        f"Total files to generate: "
        f"{len(pokemon_files) * len(VARIANTS)}"
    )

    print()

    print(
        "FULL RECOLOR MODE:"
    )

    print(
        "  Original colors will be replaced."
    )

    print(
        "  Original brightness/shading will be preserved."
    )

    print(
        "  Transparency will be preserved."
    )

    print(
        "  Original Pokémon files will NOT be modified."
    )

    print()

    # --------------------------------------------------------
    # Start confirmation
    # --------------------------------------------------------

    input(
        "Press ENTER to begin..."
    )

    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------

    total_generated = 0

    for index, pokemon_file in enumerate(
        pokemon_files,
        start=1
    ):

        print()

        print(
            f"[{index}/{len(pokemon_files)}]"
        )

        total_generated += (
            process_pokemon(
                pokemon_file
            )
        )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    print()

    print("=" * 70)

    print(
        " GENERATION COMPLETE"
    )

    print("=" * 70)

    print()

    print(
        f"Pokémon processed: "
        f"{len(pokemon_files)}"
    )

    print(
        f"Variants per Pokémon: "
        f"{len(VARIANTS)}"
    )

    print(
        f"Files generated: "
        f"{total_generated}"
    )

    print()

    print(
        "Output:"
    )

    print(
        f"  {OUTPUT_DIR}"
    )

    print()

    print("=" * 70)

    input(
        "Press ENTER to exit..."
    )


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":

    main()