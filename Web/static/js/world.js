/*
 * Krampus RPG — World Exploration & Catching
 *
 * Flow: pick an area -> POST /api/world/encounter -> wild Pokémon
 * appears with per-ball catch chances -> throw a ball via
 * POST /api/world/catch -> server consumes the ball and, on success,
 * stores the Pokémon in Party/PC.
 */

(function () {

    "use strict";

    var currentEncounter = null;

    var elements = {
        areasGrid: document.getElementById(
            "world-areas-grid"
        ),

        encounterSection: document.getElementById(
            "world-encounter-section"
        ),

        encounterTitle: document.getElementById(
            "world-encounter-title"
        ),

        encounterImage: document.getElementById(
            "world-encounter-image"
        ),

        encounterShiny: document.getElementById(
            "world-encounter-shiny"
        ),

        encounterSpecies: document.getElementById(
            "world-encounter-species"
        ),

        encounterLevel: document.getElementById(
            "world-encounter-level"
        ),

        encounterType: document.getElementById(
            "world-encounter-type"
        ),

        encounterClose: document.getElementById(
            "world-encounter-close"
        ),

        ballButtons: document.getElementById(
            "world-ball-buttons"
        ),

        ballHint: document.getElementById(
            "world-ball-hint"
        ),

        ballTotal: document.getElementById(
            "world-ball-total"
        ),

        encounterResult: document.getElementById(
            "world-encounter-result"
        ),

        message: document.getElementById(
            "world-message"
        )
    };


    function showMessage(text) {
        if (!elements.message) {
            return;
        }

        elements.message.textContent = text;
        elements.message.hidden = false;

        window.clearTimeout(
            showMessage.timeout
        );

        showMessage.timeout = window.setTimeout(
            function () {
                elements.message.hidden = true;
            },
            4000
        );
    }


    function capitalize(value) {
        if (!value) {
            return "";
        }

        return String(value)
            .replace(/[-_]/g, " ")
            .replace(/\b\w/g, function (letter) {
                return letter.toUpperCase();
            });
    }


    async function api(url, body) {
        var options = {
            method: "GET"
        };

        if (body !== undefined) {
            options.method = "POST";

            options.headers = {
                "Content-Type": "application/json"
            };

            options.body = JSON.stringify(body);
        }

        var response = await window.fetch(url, options);

        var data = null;

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


    /*
     * Render the ball tray with catch chances for the current
     * encounter.
     */
    function renderBalls(balls) {
        if (!elements.ballButtons) {
            return;
        }

        elements.ballButtons.innerHTML = "";

        var total = 0;

        (balls || []).forEach(function (ball) {
            total += ball.quantity;

            var button = document.createElement("button");

            button.type = "button";
            button.className = "world-ball-button";

            button.innerHTML =
                "<span class=\"world-ball-name\">" +
                escapeHtml(ball.name) +
                "</span>" +
                "<span class=\"world-ball-meta\">" +
                "x" + ball.quantity +
                (currentEncounter
                    ? " · " + ball.catch_chance + "% catch"
                    : "") +
                "</span>";

            button.disabled = ball.quantity <= 0;

            button.addEventListener(
                "click",
                function () {
                    throwBall(ball.item_id);
                }
            );

            elements.ballButtons.appendChild(button);
        });

        if (elements.ballTotal) {
            elements.ballTotal.textContent = String(total);
        }

        if (elements.ballHint) {
            elements.ballHint.hidden =
                total > 0;
        }
    }


    function escapeHtml(value) {
        var div = document.createElement("div");

        div.textContent = value;

        return div.innerHTML;
    }


    /*
     * Show a wild encounter returned by the server.
     */
    function showEncounter(data) {
        currentEncounter = data.encounter;

        if (
            !currentEncounter ||
            !elements.encounterSection
        ) {
            return;
        }

        if (elements.encounterTitle) {
            elements.encounterTitle.textContent =
                "A wild " +
                (currentEncounter.species_name || "Pokémon") +
                " appeared!";
        }

        if (elements.encounterImage) {
            elements.encounterImage.src =
                currentEncounter.sprite_url ||
                ("/static/sprites/" +
                    encodeURIComponent(currentEncounter.species_id) +
                    ".png");
        }

        if (elements.encounterShiny) {
            elements.encounterShiny.hidden =
                !currentEncounter.shiny;
        }

        if (elements.encounterSpecies) {
            elements.encounterSpecies.textContent =
                currentEncounter.species_name || "—";
        }

        if (elements.encounterLevel) {
            elements.encounterLevel.textContent =
                "Lv. " + currentEncounter.level;
        }

        if (elements.encounterType) {
            var types = currentEncounter.types || [];

            elements.encounterType.textContent =
                types.length
                    ? types.map(capitalize).join(" / ")
                    : "—";
        }

        if (elements.encounterResult) {
            elements.encounterResult.hidden = true;
        }

        renderBalls(data.balls);

        elements.encounterSection.hidden = false;

        elements.encounterSection.scrollIntoView({
            behavior: "smooth",
            block: "nearest"
        });
    }


    async function searchArea(areaId, button) {
        if (button) {
            button.disabled = true;
        }

        try {
            var data = await api(
                "/api/world/encounter",
                { area: areaId }
            );

            if (!data.encounter) {
                showMessage(
                    data.message ||
                    "Nothing seems to be around here..."
                );

                if (elements.encounterSection) {
                    elements.encounterSection.hidden = true;
                }

                return;
            }

            showEncounter(data);
        } catch (error) {
            showMessage(
                (error && error.message) ||
                "The search failed."
            );
        } finally {
            if (button) {
                button.disabled = false;
            }
        }
    }


    async function throwBall(ballId) {
        if (!currentEncounter) {
            return;
        }

        var buttons = elements.ballButtons
            ? Array.prototype.slice.call(
                  elements.ballButtons.querySelectorAll("button")
              )
            : [];

        buttons.forEach(function (b) {
            b.disabled = true;
        });

        try {
            var data = await api(
                "/api/world/catch",
                {
                    encounter: currentEncounter,
                    ball: ballId
                }
            );

            if (elements.encounterResult) {
                if (data.caught) {
                    var pokemon = data.pokemon || {};

                    elements.encounterResult.className =
                        "world-encounter-result caught";

                    elements.encounterResult.textContent =
                        "Gotcha! " +
                        (pokemon.species_name || "The Pokémon") +
                        " was caught" +
                        (pokemon.shiny ? " — and it's SHINY! ✨" : "") +
                        "!";

                    // The catch ended the encounter.
                    currentEncounter = null;

                    if (elements.encounterTitle) {
                        elements.encounterTitle.textContent =
                            "Caught!";
                    }
                } else {
                    elements.encounterResult.className =
                        "world-encounter-result failed";

                    elements.encounterResult.textContent =
                        "Oh no! It broke free" +
                        " (" + data.roll +
                        " needed " + data.catch_chance +
                        ")!";
                }

                elements.encounterResult.hidden = false;
            }

            // Ball counts changed (one consumed).
            renderBalls(data.balls);
        } catch (error) {
            showMessage(
                (error && error.message) ||
                "The throw failed."
            );

            buttons.forEach(function (b) {
                b.disabled = false;
            });
        }
    }


    function setupEvents() {
        if (elements.areasGrid) {
            elements.areasGrid.addEventListener(
                "click",
                function (event) {
                    var button = event.target.closest(
                        ".world-area-card"
                    );

                    if (!button || button.disabled) {
                        return;
                    }

                    // Highlight the active area.
                    elements.areasGrid
                        .querySelectorAll(".world-area-card")
                        .forEach(function (card) {
                            card.classList.remove(
                                "world-area-active"
                            );
                        });

                    button.classList.add(
                        "world-area-active"
                    );

                    searchArea(
                        button.dataset.area,
                        button
                    );
                }
            );
        }

        if (elements.encounterClose) {
            elements.encounterClose.addEventListener(
                "click",
                function () {
                    currentEncounter = null;

                    if (elements.encounterSection) {
                        elements.encounterSection.hidden = true;
                    }
                }
            );
        }
    }


    function initialize() {
        setupEvents();
    }


    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initialize
        );
    } else {
        initialize();
    }

})();
