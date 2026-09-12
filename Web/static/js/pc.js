(function () {
    "use strict";

    let currentPage = 1;
    let highestPage = 1;
    let selectedPokemon = null;
    let selectedLocation = null;

    const elements = {
        grid: document.getElementById("pc-grid"),

        totalCount: document.getElementById(
            "pc-total-count"
        ),

        currentPage: document.getElementById(
            "pc-current-page"
        ),

        pageLabel: document.getElementById(
            "pc-page-label"
        ),

        pageInput: document.getElementById(
            "pc-page-input"
        ),

        search: document.getElementById(
            "pc-search"
        ),

        variant: document.getElementById(
            "pc-variant"
        ),

        type: document.getElementById(
            "pc-type"
        ),

        searchButton: document.getElementById(
            "pc-search-button"
        ),

        clearButton: document.getElementById(
            "pc-clear-button"
        ),

        searchResults: document.getElementById(
            "pc-search-results"
        ),

        resultsGrid: document.getElementById(
            "pc-results-grid"
        ),

        storageSection: document.getElementById(
            "pc-storage-section"
        ),

        closeSearch: document.getElementById(
            "pc-close-search"
        ),

        firstPage: document.getElementById(
            "pc-first-page"
        ),

        prevPage: document.getElementById(
            "pc-prev-page"
        ),

        nextPage: document.getElementById(
            "pc-next-page"
        ),

        lastPage: document.getElementById(
            "pc-last-page"
        ),

        pageGo: document.getElementById(
            "pc-page-go"
        ),

        partyGrid: document.getElementById(
            "pc-party-grid"
        ),

        details: document.getElementById(
            "pc-details"
        ),

        detailName: document.getElementById(
            "pc-detail-name"
        ),

        detailImage: document.getElementById(
            "pc-detail-image"
        ),

        detailSpecies: document.getElementById(
            "pc-detail-species"
        ),

        detailLevel: document.getElementById(
            "pc-detail-level"
        ),

        detailVariant: document.getElementById(
            "pc-detail-variant"
        ),

        detailType: document.getElementById(
            "pc-detail-type"
        ),

        detailHp: document.getElementById(
            "pc-detail-hp"
        ),

        detailLocation: document.getElementById(
            "pc-detail-location"
        ),

        detailClose: document.getElementById(
            "pc-detail-close"
        ),

        withdrawButton: document.getElementById(
            "pc-withdraw-button"
        ),

        moveButton: document.getElementById(
            "pc-move-button"
        ),

        message: document.getElementById(
            "pc-message"
        )
    };


    function showMessage(message) {
        if (!elements.message) {
            return;
        }

        elements.message.textContent = message;
        elements.message.hidden = false;

        window.clearTimeout(
            showMessage.timeout
        );

        showMessage.timeout = window.setTimeout(
            function () {
                elements.message.hidden = true;
            },
            3000
        );
    }


    async function api(url, options) {
        const response = await fetch(
            url,
            options || {}
        );

        let data = null;

        try {
            data = await response.json();
        } catch (error) {
            throw new Error(
                "The server returned an invalid response."
            );
        }

        if (!response.ok || data.success === false) {
            throw new Error(
                data.error ||
                "The request could not be completed."
            );
        }

        return data;
    }


    async function post(url, body) {
        return api(
            url,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            }
        );
    }


    function capitalize(value) {
        if (!value) {
            return "";
        }

        return String(value)
            .replace(/[-_]/g, " ")
            .replace(
                /\b\w/g,
                function (letter) {
                    return letter.toUpperCase();
                }
            );
    }


    function speciesName(pokemon) {
        if (!pokemon) {
            return "Unknown";
        }

        return (
            pokemon.nickname ||
            pokemon.species_name ||
            pokemon.name ||
            pokemon.species_id ||
            "Unknown"
        );
    }


    function speciesId(pokemon) {
        if (!pokemon) {
            return "";
        }

        return (
            pokemon.species_id ||
            pokemon.species ||
            ""
        );
    }


    function pokemonId(pokemon) {
        if (!pokemon) {
            return null;
        }

        return (
            pokemon.pokemon_id ||
            pokemon.id ||
            null
        );
    }


    function spriteUrl(pokemon) {
        const species = String(
            speciesId(pokemon)
        )
            .toLowerCase()
            .replace(/\s+/g, "-");

        const variant = String(
            pokemon.variant || "normal"
        )
            .toLowerCase()
            .replace(/\s+/g, "-");

        const base = "/static/sprites/";

        if (
            variant &&
            variant !== "normal"
        ) {
            return (
                base +
                encodeURIComponent(
                    species +
                    "-" +
                    variant +
                    ".png"
                )
            );
        }

        return (
            base +
            encodeURIComponent(
                species +
                ".png"
            )
        );
    }


    function createImage(
        pokemon,
        className
    ) {
        const image = document.createElement(
            "img"
        );

        image.className =
            className || "";

        image.alt =
            speciesName(pokemon);

        image.src =
            spriteUrl(pokemon);

        image.onerror = function () {
            if (
                image.dataset.fallback === "1"
            ) {
                image.style.visibility =
                    "hidden";

                return;
            }

            image.dataset.fallback = "1";

            const species = String(
                speciesId(pokemon)
            )
                .toLowerCase()
                .replace(/\s+/g, "-");

            image.src =
                "/static/sprites/" +
                encodeURIComponent(
                    species + ".png"
                );
        };

        return image;
    }


    function renderEmptySlot(slot) {
        const element =
            document.createElement("div");

        element.className =
            "pc-slot pc-slot-empty";

        element.innerHTML =
            '<span class="pc-slot-number">' +
            slot +
            "</span>" +
            '<div class="pc-slot-empty-mark">+</div>';

        return element;
    }


    function renderPokemonSlot(
        slot,
        pokemon
    ) {
        const element =
            document.createElement("div");

        element.className =
            "pc-slot";

        element.dataset.pokemonId =
            pokemonId(pokemon) || "";

        element.dataset.slot =
            slot;

        const spriteWrapper =
            document.createElement("div");

        spriteWrapper.className =
            "pc-slot-sprite";

        spriteWrapper.appendChild(
            createImage(pokemon)
        );

        element.appendChild(
            spriteWrapper
        );

        const slotNumber =
            document.createElement("span");

        slotNumber.className =
            "pc-slot-number";

        slotNumber.textContent =
            slot;

        element.appendChild(
            slotNumber
        );

        if (
            pokemon.shiny === true ||
            pokemon.shiny === 1 ||
            pokemon.shiny === "1"
        ) {
            const shiny =
                document.createElement("span");

            shiny.className =
                "pc-slot-shiny";

            shiny.textContent =
                "✨";

            element.appendChild(
                shiny
            );
        }

        const name =
            document.createElement("div");

        name.className =
            "pc-slot-name";

        name.textContent =
            speciesName(pokemon);

        element.appendChild(
            name
        );

        const meta =
            document.createElement("div");

        meta.className =
            "pc-slot-meta";

        const level =
            document.createElement("span");

        level.className =
            "pc-slot-level";

        level.textContent =
            "Lv. " +
            (
                pokemon.level ??
                "?"
            );

        meta.appendChild(
            level
        );

        if (
            pokemon.variant &&
            pokemon.variant !== "normal"
        ) {
            const variant =
                document.createElement("span");

            variant.className =
                "pc-slot-variant";

            variant.textContent =
                capitalize(
                    pokemon.variant
                );

            meta.appendChild(
                variant
            );
        }

        element.appendChild(
            meta
        );

        element.addEventListener(
            "click",
            function () {
                openDetails(
                    pokemon,
                    currentPage,
                    slot,
                    "pc"
                );
            }
        );

        return element;
    }


    function renderPC(data) {
        currentPage =
            Number(
                data.page || 1
            );

        highestPage =
            Math.max(
                1,
                Number(
                    data.highest_page || 1
                )
            );

        if (elements.currentPage) {
            elements.currentPage.textContent =
                currentPage;
        }

        if (elements.pageLabel) {
            elements.pageLabel.textContent =
                "Page " + currentPage;
        }

        if (elements.pageInput) {
            elements.pageInput.value =
                currentPage;
        }

        if (!elements.grid) {
            return;
        }

        elements.grid.innerHTML = "";

        const slots =
            Array.isArray(data.slots)
                ? data.slots
                : [];

        const bySlot = {};

        slots.forEach(
            function (record) {
                if (!record) {
                    return;
                }

                bySlot[
                    Number(record.slot)
                ] = record.pokemon || null;
            }
        );

        for (
            let slot = 1;
            slot <= 30;
            slot++
        ) {
            const pokemon =
                bySlot[slot];

            if (pokemon) {
                elements.grid.appendChild(
                    renderPokemonSlot(
                        slot,
                        pokemon
                    )
                );
            } else {
                elements.grid.appendChild(
                    renderEmptySlot(
                        slot
                    )
                );
            }
        }

        if (elements.firstPage) {
            elements.firstPage.disabled =
                currentPage <= 1;
        }

        if (elements.prevPage) {
            elements.prevPage.disabled =
                currentPage <= 1;
        }

        if (elements.nextPage) {
            elements.nextPage.disabled =
                currentPage >= highestPage;
        }

        if (elements.lastPage) {
            elements.lastPage.disabled =
                currentPage >= highestPage;
        }
    }


    async function loadPage(page) {
        page = Math.max(
            1,
            Number(page) || 1
        );

        try {
            const data =
                await api(
                    "/api/pc?page=" +
                    encodeURIComponent(page)
                );

            renderPC(
                data.pc
            );

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    async function loadCount() {
        try {
            const data =
                await api(
                    "/api/pc/count"
                );

            if (elements.totalCount) {
                elements.totalCount.textContent =
                    data.count ?? 0;
            }

        } catch (error) {
            if (elements.totalCount) {
                elements.totalCount.textContent =
                    "0";
            }
        }
    }


    async function loadFilters() {
        try {
            const data =
                await api(
                    "/api/pc/filters"
                );

            const filters =
                data.filters || {};

            populateSelect(
                elements.variant,
                filters.variants || [],
                "All Variants"
            );

            populateSelect(
                elements.type,
                filters.types || [],
                "All Types"
            );

        } catch (error) {
            // Filters are optional.
        }
    }


    function populateSelect(
        select,
        values,
        defaultText
    ) {
        if (!select) {
            return;
        }

        select.innerHTML = "";

        const first =
            document.createElement(
                "option"
            );

        first.value = "";
        first.textContent =
            defaultText;

        select.appendChild(
            first
        );

        values.forEach(
            function (value) {
                const option =
                    document.createElement(
                        "option"
                    );

                if (
                    typeof value === "object"
                ) {
                    option.value =
                        value.id ||
                        value.value ||
                        value.name ||
                        "";

                    option.textContent =
                        value.name ||
                        value.label ||
                        capitalize(
                            option.value
                        );
                } else {
                    option.value =
                        String(value);

                    option.textContent =
                        capitalize(
                            String(value)
                        );
                }

                select.appendChild(
                    option
                );
            }
        );
    }


    /*
     * ============================================================
     * PARTY
     * ============================================================
     *
     * Party is now loaded directly from:
     *
     *     GET /api/pc/party
     *
     * The database Party table is authoritative.
     */

    async function loadParty() {
        if (!elements.partyGrid) {
            return;
        }

        try {
            const data =
                await api(
                    "/api/pc/party"
                );

            renderParty(
                data.party || [],
                Number(
                    data.max_party_size || 6
                )
            );

        } catch (error) {
            console.error(
                "Unable to load Party:",
                error
            );

            showMessage(
                "Unable to load your party."
            );

            renderParty(
                [],
                6
            );
        }
    }


    function renderParty(
        party,
        maxPartySize
    ) {
        if (!elements.partyGrid) {
            return;
        }

        elements.partyGrid.innerHTML =
            "";

        const bySlot = {};

        party.forEach(
            function (pokemon) {
                const slot =
                    Number(
                        pokemon.slot
                    );

                if (
                    slot >= 1 &&
                    slot <= maxPartySize
                ) {
                    bySlot[slot] =
                        pokemon;
                }
            }
        );

        for (
            let slot = 1;
            slot <= maxPartySize;
            slot++
        ) {
            const pokemon =
                bySlot[slot];

            if (pokemon) {
                elements.partyGrid.appendChild(
                    renderPartyPokemon(
                        slot,
                        pokemon
                    )
                );
            } else {
                elements.partyGrid.appendChild(
                    renderPartyEmpty(
                        slot
                    )
                );
            }
        }

        const limit =
            document.querySelector(
                ".pc-party-limit"
            );

        if (limit) {
            limit.textContent =
                party.length +
                " / " +
                maxPartySize;
        }
    }


    function renderPartyEmpty(slot) {
        const element =
            document.createElement("div");

        element.className =
            "pc-party-slot pc-party-slot-empty";

        element.innerHTML =
            '<span class="pc-party-slot-number">' +
            slot +
            "</span>" +
            '<div class="pc-party-empty-mark">+</div>' +
            '<div class="pc-party-empty-text">Empty</div>';

        return element;
    }


    function renderPartyPokemon(
        slot,
        pokemon
    ) {
        const element =
            document.createElement("div");

        element.className =
            "pc-party-slot";

        element.dataset.pokemonId =
            pokemonId(pokemon) || "";

        element.dataset.slot =
            slot;

        const number =
            document.createElement("span");

        number.className =
            "pc-party-slot-number";

        number.textContent =
            slot;

        element.appendChild(
            number
        );

        const spriteWrapper =
            document.createElement("div");

        spriteWrapper.className =
            "pc-party-sprite";

        spriteWrapper.appendChild(
            createImage(
                pokemon,
                "pc-party-image"
            )
        );

        element.appendChild(
            spriteWrapper
        );

        const name =
            document.createElement("div");

        name.className =
            "pc-party-name";

        name.textContent =
            speciesName(pokemon);

        element.appendChild(
            name
        );

        const level =
            document.createElement("div");

        level.className =
            "pc-party-level";

        level.textContent =
            "Lv. " +
            (
                pokemon.level ??
                "?"
            );

        element.appendChild(
            level
        );

        if (
            pokemon.shiny === true ||
            pokemon.shiny === 1 ||
            pokemon.shiny === "1"
        ) {
            const shiny =
                document.createElement(
                    "span"
                );

            shiny.className =
                "pc-party-shiny";

            shiny.textContent =
                "✨";

            element.appendChild(
                shiny
            );
        }

        element.addEventListener(
            "click",
            function () {
                openDetails(
                    pokemon,
                    null,
                    slot,
                    "party"
                );
            }
        );

        return element;
    }


    async function addPartyPokemon(
        pokemon
    ) {
        const id =
            pokemonId(pokemon);

        if (!id) {
            return;
        }

        try {
            await post(
                "/api/pc/party/add",
                {
                    pokemon_id: Number(id)
                }
            );

            showMessage(
                speciesName(pokemon) +
                " was added to your party."
            );

            await Promise.all(
                [
                    loadPage(currentPage),
                    loadCount(),
                    loadParty()
                ]
            );

            closeDetails();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    async function removePartyPokemon(
        pokemon
    ) {
        const id =
            pokemonId(pokemon);

        if (!id) {
            return;
        }

        try {
            await post(
                "/api/pc/party/remove",
                {
                    pokemon_id: Number(id)
                }
            );

            showMessage(
                speciesName(pokemon) +
                " was removed from your party."
            );

            await Promise.all(
                [
                    loadPage(currentPage),
                    loadCount(),
                    loadParty()
                ]
            );

            closeDetails();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    async function movePartyPokemon(
        pokemon,
        destinationSlot
    ) {
        const id =
            pokemonId(pokemon);

        if (!id) {
            return;
        }

        try {
            await post(
                "/api/pc/party/move",
                {
                    pokemon_id: Number(id),
                    slot: Number(
                        destinationSlot
                    )
                }
            );

            showMessage(
                "Party order updated."
            );

            await loadParty();

            closeDetails();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    /*
     * ============================================================
     * SEARCH
     * ============================================================
     */

    async function searchPC() {
        const name =
            elements.search
                ? elements.search.value.trim()
                : "";

        const variant =
            elements.variant
                ? elements.variant.value.trim()
                : "";

        const type =
            elements.type
                ? elements.type.value.trim()
                : "";

        if (
            !name &&
            !variant &&
            !type
        ) {
            showMessage(
                "Enter a search term or choose a filter."
            );

            return;
        }

        const params =
            new URLSearchParams();

        if (name) {
            params.set(
                "name",
                name
            );
        }

        if (variant) {
            params.set(
                "variant",
                variant
            );
        }

        if (type) {
            params.set(
                "type",
                type
            );
        }

        try {
            const data =
                await api(
                    "/api/pc/search?" +
                    params.toString()
                );

            renderSearchResults(
                data.results || []
            );

            if (elements.searchResults) {
                elements.searchResults.hidden =
                    false;
            }

            if (elements.storageSection) {
                elements.storageSection.hidden =
                    true;
            }

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    function renderSearchResults(
        results
    ) {
        if (!elements.resultsGrid) {
            return;
        }

        elements.resultsGrid.innerHTML =
            "";

        if (!results.length) {
            const empty =
                document.createElement(
                    "div"
                );

            empty.className =
                "pc-result";

            empty.textContent =
                "No Pokémon matched your search.";

            elements.resultsGrid.appendChild(
                empty
            );

            return;
        }

        results.forEach(
            function (pokemon) {
                const result =
                    document.createElement(
                        "div"
                    );

                result.className =
                    "pc-result";

                result.appendChild(
                    createImage(
                        pokemon
                    )
                );

                const name =
                    document.createElement(
                        "div"
                    );

                name.className =
                    "pc-result-name";

                name.textContent =
                    speciesName(
                        pokemon
                    );

                result.appendChild(
                    name
                );

                const location =
                    document.createElement(
                        "div"
                    );

                location.className =
                    "pc-result-location";

                location.textContent =
                    "Page " +
                    (
                        pokemon.page ??
                        "?"
                    ) +
                    " · Slot " +
                    (
                        pokemon.slot ??
                        "?"
                    );

                result.appendChild(
                    location
                );

                result.addEventListener(
                    "click",
                    function () {
                        openDetails(
                            pokemon,
                            pokemon.page,
                            pokemon.slot,
                            "pc"
                        );
                    }
                );

                elements.resultsGrid.appendChild(
                    result
                );
            }
        );
    }


    function clearSearch() {
        if (elements.search) {
            elements.search.value =
                "";
        }

        if (elements.variant) {
            elements.variant.value =
                "";
        }

        if (elements.type) {
            elements.type.value =
                "";
        }

        if (elements.searchResults) {
            elements.searchResults.hidden =
                true;
        }

        if (elements.storageSection) {
            elements.storageSection.hidden =
                false;
        }

        if (elements.resultsGrid) {
            elements.resultsGrid.innerHTML =
                "";
        }

        loadPage(
            currentPage
        );
    }


    /*
     * ============================================================
     * DETAILS
     * ============================================================
     */

    function openDetails(
        pokemon,
        page,
        slot,
        location
    ) {
        if (!elements.details) {
            return;
        }

        selectedPokemon =
            pokemon;

        selectedLocation =
            location || "pc";

        if (elements.detailName) {
            elements.detailName.textContent =
                speciesName(pokemon);
        }

        if (elements.detailImage) {
            elements.detailImage.src =
                spriteUrl(pokemon);

            elements.detailImage.alt =
                speciesName(pokemon);

            elements.detailImage.onerror =
                function () {
                    this.onerror =
                        null;

                    const species =
                        String(
                            speciesId(pokemon)
                        )
                            .toLowerCase()
                            .replace(
                                /\s+/g,
                                "-"
                            );

                    this.src =
                        "/static/sprites/" +
                        encodeURIComponent(
                            species +
                            ".png"
                        );
                };
        }

        if (elements.detailSpecies) {
            elements.detailSpecies.textContent =
                capitalize(
                    speciesId(pokemon)
                );
        }

        if (elements.detailLevel) {
            elements.detailLevel.textContent =
                pokemon.level ??
                "—";
        }

        if (elements.detailVariant) {
            elements.detailVariant.textContent =
                capitalize(
                    pokemon.variant ||
                    "normal"
                );
        }

        if (elements.detailType) {
            elements.detailType.textContent =
                pokemon.type_name ||
                pokemon.type ||
                "—";
        }

        if (elements.detailHp) {
            elements.detailHp.textContent =
                (
                    pokemon.current_hp ??
                    "—"
                ) +
                " / " +
                (
                    pokemon.max_hp ??
                    "—"
                );
        }

        if (elements.detailLocation) {
            if (location === "party") {
                elements.detailLocation.textContent =
                    "Party · Slot " +
                    (
                        slot ??
                        "?"
                    );
            } else {
                elements.detailLocation.textContent =
                    "PC · Page " +
                    (
                        page ??
                        "?"
                    ) +
                    " · Slot " +
                    (
                        slot ??
                        "?"
                    );
            }
        }

        updateDetailButtons();

        elements.details.hidden =
            false;

        elements.details.scrollIntoView({
            behavior: "smooth",
            block: "nearest"
        });
    }


    function updateDetailButtons() {
        if (!elements.withdrawButton) {
            return;
        }

        if (
            selectedLocation === "party"
        ) {
            elements.withdrawButton.textContent =
                "Remove from Party";

            elements.withdrawButton.disabled =
                false;

            if (elements.moveButton) {
                elements.moveButton.textContent =
                    "Move Party Slot";
                elements.moveButton.disabled =
                    false;
            }

            return;
        }

        elements.withdrawButton.textContent =
            "Withdraw to Party";

        elements.withdrawButton.disabled =
            false;

        if (elements.moveButton) {
            elements.moveButton.textContent =
                "Move Pokémon";

            elements.moveButton.disabled =
                false;
        }
    }


    function closeDetails() {
        selectedPokemon =
            null;

        selectedLocation =
            null;

        if (elements.details) {
            elements.details.hidden =
                true;
        }
    }


    async function handlePrimaryDetailAction() {
        if (!selectedPokemon) {
            return;
        }

        if (
            selectedLocation === "party"
        ) {
            await removePartyPokemon(
                selectedPokemon
            );

            return;
        }

        await withdrawPokemon(
            selectedPokemon
        );
    }


    async function withdrawPokemon(
        pokemon
    ) {
        const id =
            pokemonId(pokemon);

        if (!id) {
            return;
        }

        try {
            await post(
                "/api/pc/withdraw",
                {
                    pokemon_id: Number(id)
                }
            );

            showMessage(
                speciesName(pokemon) +
                " was moved to your party."
            );

            await Promise.all(
                [
                    loadPage(currentPage),
                    loadCount(),
                    loadParty()
                ]
            );

            closeDetails();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    async function handleMoveAction() {
        if (!selectedPokemon) {
            return;
        }

        if (
            selectedLocation === "party"
        ) {
            const requested =
                window.prompt(
                    "Move this Pokémon to party slot 1-6:"
                );

            if (
                requested === null ||
                requested.trim() === ""
            ) {
                return;
            }

            const destination =
                Number(
                    requested
                );

            if (
                !Number.isInteger(
                    destination
                ) ||
                destination < 1 ||
                destination > 6
            ) {
                showMessage(
                    "Party slot must be between 1 and 6."
                );

                return;
            }

            await movePartyPokemon(
                selectedPokemon,
                destination
            );

            return;
        }

        const requestedPage =
            window.prompt(
                "Enter the destination PC page:",
                String(
                    selectedPokemon.page ||
                    currentPage
                )
            );

        if (
            requestedPage === null
        ) {
            return;
        }

        const requestedSlot =
            window.prompt(
                "Enter the destination PC slot (1-30):",
                String(
                    selectedPokemon.slot ||
                    1
                )
            );

        if (
            requestedSlot === null
        ) {
            return;
        }

        const page =
            Number(
                requestedPage
            );

        const slot =
            Number(
                requestedSlot
            );

        if (
            !Number.isInteger(page) ||
            page < 1
        ) {
            showMessage(
                "PC page must be at least 1."
            );

            return;
        }

        if (
            !Number.isInteger(slot) ||
            slot < 1 ||
            slot > 30
        ) {
            showMessage(
                "PC slot must be between 1 and 30."
            );

            return;
        }

        const id =
            pokemonId(
                selectedPokemon
            );

        try {
            await post(
                "/api/pc/move",
                {
                    pokemon_id: Number(id),
                    page: page,
                    slot: slot
                }
            );

            showMessage(
                "Pokémon moved."
            );

            await Promise.all(
                [
                    loadPage(page),
                    loadCount(),
                    loadParty()
                ]
            );

            closeDetails();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    /*
     * ============================================================
     * EVENT HANDLERS
     * ============================================================
     */

    function setupEvents() {
        if (elements.searchButton) {
            elements.searchButton.addEventListener(
                "click",
                searchPC
            );
        }

        if (elements.clearButton) {
            elements.clearButton.addEventListener(
                "click",
                clearSearch
            );
        }

        if (elements.search) {
            elements.search.addEventListener(
                "keydown",
                function (event) {
                    if (
                        event.key === "Enter"
                    ) {
                        event.preventDefault();
                        searchPC();
                    }
                }
            );
        }

        if (elements.closeSearch) {
            elements.closeSearch.addEventListener(
                "click",
                function () {
                    clearSearch();
                }
            );
        }

        if (elements.firstPage) {
            elements.firstPage.addEventListener(
                "click",
                function () {
                    loadPage(1);
                }
            );
        }

        if (elements.prevPage) {
            elements.prevPage.addEventListener(
                "click",
                function () {
                    loadPage(
                        currentPage - 1
                    );
                }
            );
        }

        if (elements.nextPage) {
            elements.nextPage.addEventListener(
                "click",
                function () {
                    loadPage(
                        currentPage + 1
                    );
                }
            );
        }

        if (elements.lastPage) {
            elements.lastPage.addEventListener(
                "click",
                function () {
                    loadPage(
                        highestPage
                    );
                }
            );
        }

        if (elements.pageGo) {
            elements.pageGo.addEventListener(
                "click",
                function () {
                    const page =
                        Number(
                            elements.pageInput.value
                        );

                    loadPage(
                        page
                    );
                }
            );
        }

        if (elements.pageInput) {
            elements.pageInput.addEventListener(
                "keydown",
                function (event) {
                    if (
                        event.key === "Enter"
                    ) {
                        event.preventDefault();

                        loadPage(
                            Number(
                                elements.pageInput.value
                            )
                        );
                    }
                }
            );
        }

        if (elements.detailClose) {
            elements.detailClose.addEventListener(
                "click",
                closeDetails
            );
        }

        if (elements.withdrawButton) {
            elements.withdrawButton.addEventListener(
                "click",
                handlePrimaryDetailAction
            );
        }

        if (elements.moveButton) {
            elements.moveButton.addEventListener(
                "click",
                handleMoveAction
            );
        }
    }


    /*
     * ============================================================
     * INITIALIZATION
     * ============================================================
     */

    async function initialize() {
        setupEvents();

        /*
         * IMPORTANT:
         * Party is loaded independently from PC storage.
         * This means a Pokémon that is already in the database
         * Party table will appear immediately, even when the
         * current PC page is empty.
         */
        await Promise.all(
            [
                loadPage(1),
                loadCount(),
                loadFilters(),
                loadParty()
            ]
        );
    }


    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initialize
        );
    } else {
        initialize();
    }

})();