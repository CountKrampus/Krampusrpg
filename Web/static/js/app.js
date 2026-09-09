async function getPlayer() {
    const response = await fetch("/api/me");

    if (!response.ok) {
        return null;
    }

    return await response.json();
}


async function getPokemon() {
    const response = await fetch("/api/pokemon");

    if (!response.ok) {
        return null;
    }

    return await response.json();
}


async function addPokemonToParty(pokemonId) {
    const response = await fetch(
        `/api/pokemon/${pokemonId}/party`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                action: "add"
            })
        }
    );

    return await response.json();
}


async function removePokemonFromParty(pokemonId) {
    const response = await fetch(
        `/api/pokemon/${pokemonId}/party`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                action: "remove"
            })
        }
    );

    return await response.json();
}
