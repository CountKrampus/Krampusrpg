(function () {
    "use strict";

    let currentPage = 1;
    let highestPage = 1;
    let selectedPokemon = null;

    const elements = {
        grid: document.getElementById("pc-grid"),
        totalCount: document.getElementById("pc-total-count"),
        currentPage: document.getElementById("pc-current-page"),
        pageLabel: document.getElementById("pc-page-label"),
        pageInput: document.getElementById("pc-page-input"),

        search: document.getElementById("pc-search"),
        variant: document.getElementById("pc-variant"),
        type: document.getElementById("pc-type"),

        searchButton: document.getElementById("pc-search-button"),
        clearButton: document.getElementById("pc-clear-button"),

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


    async function api(
        url,
        options
    ) {
        const response = await fetch(
            url,
            options || {},
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
            pokemon.species_id ||
            pokemon.name ||
            "Unknown"
        );
    }


    function speciesId(pokemon) {
        return (
            pokemon.species_id ||
            pokemon.species ||
            pokemon.id ||
            ""
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

        const base =
            "/static/sprites/";

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
                species + ".png"
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
            pokemon.pokemon_id ||
            pokemon.id ||
            "";

        element.dataset.slot =
            slot;

        const sprite =
            createImage(
                pokemon
            );

        const spriteWrapper =
            document.createElement("div");

        spriteWrapper.className =
            "pc-slot-sprite";

        spriteWrapper.appendChild(
            sprite
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
                document.createElement(
                    "span"
                );

            shiny.className =
                "pc-slot-shiny";

            shiny.textContent = "✨";

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
                document.createElement(
                    "span"
                );

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
                    slot
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

        elements.currentPage.textContent =
            currentPage;

        elements.pageLabel.textContent =
            "Page " + currentPage;

        elements.pageInput.value =
            currentPage;

        elements.grid.innerHTML = "";

        const slots =
            Array.isArray(data.slots)
                ? data.slots
                : [];

        for (
            let slot = 1;
            slot <= 30;
            slot++
        ) {
            const record =
                slots.find(
                    function (item) {
                        return Number(
                            item.slot
                        ) === slot;
                    }
                );

            if (
                record &&
                record.pokemon
            ) {
                elements.grid.appendChild(
                    renderPokemonSlot(
                        slot,
                        record.pokemon
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

        elements.firstPage.disabled =
            currentPage <= 1;

        elements.prevPage.disabled =
            currentPage <= 1;

        elements.nextPage.disabled =
            currentPage >= highestPage;

        elements.lastPage.disabled =
            currentPage >= highestPage;
    }


    async function loadPage(
        page
    ) {
        page = Math.max(
            1,
            Number(page) || 1
        );

        try {
            const data =
                await api(
                    "/api/pc?page=" +
                    encodeURIComponent(
                        page
                    )
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

            elements.totalCount.textContent =
                data.count ?? 0;

        } catch (error) {
            elements.totalCount.textContent =
                "0";
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
            /*
             * The PC remains usable even if
             * filters cannot be loaded.
             */
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


    async function searchPC() {
        const name =
            elements.search.value.trim();

        const variant =
            elements.variant.value.trim();

        const type =
            elements.type.value.trim();

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

            elements.searchResults.hidden =
                false;

            elements.storageSection.hidden =
                true;

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    function renderSearchResults(
        results
    ) {
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
                            pokemon.slot
                        );
                    }
                );

                elements.resultsGrid.appendChild(
                    result
                );
            }
        );
    }


    function closeSearch() {
        elements.searchResults.hidden =
            true;

        elements.storageSection.hidden =
            false;
    }


    function openDetails(
        pokemon,
        page,
        slot
    ) {
        selectedPokemon =
            pokemon;

        elements.detailName.textContent =
            speciesName(
                pokemon
            );

        elements.detailImage.src =
            spriteUrl(
                pokemon
            );

        elements.detailImage.alt =
            speciesName(
                pokemon
            );

        elements.detailSpecies.textContent =
            capitalize(
                speciesId(
                    pokemon
                )
            );

        elements.detailLevel.textContent =
            pokemon.level ??
            "—";

        elements.detailVariant.textContent =
            capitalize(
                pokemon.variant ||
                "normal"
            );

        elements.detailType.textContent =
            formatTypes(
                pokemon
            );

        elements.detailHp.textContent =
            (
                pokemon.current_hp ??
                "?"
            ) +
            " / " +
            (
                pokemon.max_hp ??
                "?"
            );

        elements.detailLocation.textContent =
            "Page " +
            (
                page ??
                pokemon.page ??
                "?"
            ) +
            " · Slot " +
            (
                slot ??
                pokemon.slot ??
                "?"
            );

        elements.details.hidden =
            false;

        elements.details.scrollIntoView(
            {
                behavior: "smooth",
                block: "nearest"
            }
        );
    }


    function formatTypes(
        pokemon
    ) {
        if (
            Array.isArray(
                pokemon.types
            )
        ) {
            return pokemon.types
                .map(
                    function (type) {
                        if (
                            typeof type ===
                            "object"
                        ) {
                            return (
                                type.name ||
                                type.id ||
                                ""
                            );
                        }

                        return type;
                    }
                )
                .filter(Boolean)
                .map(capitalize)
                .join(" / ");
        }

        if (
            Array.isArray(
                pokemon.type
            )
        ) {
            return pokemon.type
                .map(capitalize)
                .join(" / ");
        }

        if (pokemon.type) {
            return capitalize(
                pokemon.type
            );
        }

        return "—";
    }


    function closeDetails() {
        selectedPokemon =
            null;

        elements.details.hidden =
            true;
    }


    async function withdrawSelected() {
        if (!selectedPokemon) {
            return;
        }

        const pokemonId =
            selectedPokemon.pokemon_id ||
            selectedPokemon.id;

        if (!pokemonId) {
            showMessage(
                "This Pokémon does not have a valid database ID."
            );
            return;
        }

        try {
            await api(
                "/api/pc/withdraw",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify(
                        {
                            pokemon_id:
                                Number(
                                    pokemonId
                                )
                        }
                    )
                }
            );

            showMessage(
                "Pokémon withdrawn to your party."
            );

            closeDetails();

            await Promise.all(
                [
                    loadPage(
                        currentPage
                    ),
                    loadCount()
                ]
            );

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    async function moveSelected() {
        if (!selectedPokemon) {
            return;
        }

        const pokemonId =
            selectedPokemon.pokemon_id ||
            selectedPokemon.id;

        const page =
            window.prompt(
                "Destination PC page:",
                String(
                    selectedPokemon.page ||
                    currentPage
                )
            );

        if (page === null) {
            return;
        }

        const slot =
            window.prompt(
                "Destination slot (1-30):",
                String(
                    selectedPokemon.slot ||
                    1
                )
            );

        if (slot === null) {
            return;
        }

        const destinationPage =
            Number(page);

        const destinationSlot =
            Number(slot);

        if (
            !Number.isInteger(
                destinationPage
            ) ||
            destinationPage < 1
        ) {
            showMessage(
                "Page must be 1 or greater."
            );
            return;
        }

        if (
            !Number.isInteger(
                destinationSlot
            ) ||
            destinationSlot < 1 ||
            destinationSlot > 30
        ) {
            showMessage(
                "Slot must be between 1 and 30."
            );
            return;
        }

        try {
            await api(
                "/api/pc/move",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify(
                        {
                            pokemon_id:
                                Number(
                                    pokemonId
                                ),
                            page:
                                destinationPage,
                            slot:
                                destinationSlot
                        }
                    )
                }
            );

            showMessage(
                "Pokémon moved successfully."
            );

            closeDetails();

            await loadPage(
                destinationPage
            );

            await loadCount();

        } catch (error) {
            showMessage(
                error.message
            );
        }
    }


    function renderParty() {
        /*
         * Party data is currently supplied by
         * the dashboard/application layer.
         *
         * This creates the six-slot visual
         * structure now. Party API integration
         * will be connected when the dedicated
         * party system is finalized.
         */

        elements.partyGrid.innerHTML =
            "";

        for (
            let index = 1;
            index <= 6;
            index++
        ) {
            const slot =
                document.createElement(
                    "div"
                );

            slot.className =
                "pc-party-slot pc-party-empty";

            slot.innerHTML =
                "<span>" +
                index +
                "</span>";

            elements.partyGrid.appendChild(
                slot
            );
        }
    }


    function bindEvents() {
        elements.searchButton.addEventListener(
            "click",
            searchPC
        );

        elements.search.addEventListener(
            "keydown",
            function (event) {
                if (
                    event.key ===
                    "Enter"
                ) {
                    searchPC();
                }
            }
        );

        elements.clearButton.addEventListener(
            "click",
            function () {
                elements.search.value =
                    "";

                elements.variant.value =
                    "";

                elements.type.value =
                    "";

                closeSearch();

                loadPage(
                    currentPage
                );
            }
        );

        elements.closeSearch.addEventListener(
            "click",
            closeSearch
        );

        elements.firstPage.addEventListener(
            "click",
            function () {
                loadPage(1);
            }
        );

        elements.prevPage.addEventListener(
            "click",
            function () {
                loadPage(
                    currentPage - 1
                );
            }
        );

        elements.nextPage.addEventListener(
            "click",
            function () {
                loadPage(
                    currentPage + 1
                );
            }
        );

        elements.lastPage.addEventListener(
            "click",
            function () {
                loadPage(
                    highestPage
                );
            }
        );

        elements.pageGo.addEventListener(
            "click",
            function () {
                loadPage(
                    elements.pageInput.value
                );
            }
        );

        elements.pageInput.addEventListener(
            "keydown",
            function (event) {
                if (
                    event.key ===
                    "Enter"
                ) {
                    loadPage(
                        elements.pageInput.value
                    );
                }
            }
        );

        elements.detailClose.addEventListener(
            "click",
            closeDetails
        );

        elements.withdrawButton.addEventListener(
            "click",
            withdrawSelected
        );

        elements.moveButton.addEventListener(
            "click",
            moveSelected
        );
    }


    async function initialize() {
        bindEvents();

        renderParty();

        await Promise.all(
            [
                loadPage(1),
                loadCount(),
                loadFilters()
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