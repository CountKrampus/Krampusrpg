/* ============================================================
   Krampus RPG Admin — Roadmap drag & drop
   Cards can be dragged between status columns; the drop posts
   to the move endpoint and reloads so the server state stays
   authoritative.
   ============================================================ */

(function () {
    "use strict";

    var board = document.querySelector(".roadmap-board-admin");

    if (!board) {
        return;
    }

    var draggedCardId = null;

    function findColumn(el) {
        while (el && el !== document.body) {
            if (el.classList && el.classList.contains("roadmap-drop-column")) {
                return el;
            }
            el = el.parentNode;
        }
        return null;
    }

    board.querySelectorAll(".roadmap-draggable").forEach(function (card) {
        card.addEventListener("dragstart", function (event) {
            draggedCardId = card.getAttribute("data-card-id");

            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", draggedCardId);
            }

            card.classList.add("roadmap-drag-over");
        });

        card.addEventListener("dragend", function () {
            card.classList.remove("roadmap-drag-over");
            draggedCardId = null;

            board.querySelectorAll(".roadmap-drop-column").forEach(function (column) {
                column.classList.remove("roadmap-drop-target", "roadmap-drop-hover");
            });
        });
    });

    board.querySelectorAll(".roadmap-drop-column").forEach(function (column) {
        column.addEventListener("dragover", function (event) {
            event.preventDefault();

            if (event.dataTransfer) {
                event.dataTransfer.dropEffect = "move";
            }

            column.classList.add("roadmap-drop-target");
        });

        column.addEventListener("dragenter", function (event) {
            event.preventDefault();
            column.classList.add("roadmap-drop-hover");
        });

        column.addEventListener("dragleave", function () {
            column.classList.remove("roadmap-drop-hover");
        });

        column.addEventListener("drop", function (event) {
            event.preventDefault();
            column.classList.remove("roadmap-drop-target", "roadmap-drop-hover");

            var cardId = draggedCardId;

            if (!cardId) {
                cardId = event.dataTransfer
                    ? event.dataTransfer.getData("text/plain")
                    : null;
            }

            if (!cardId) {
                return;
            }

            var status = column.getAttribute("data-status");
            var moveUrlTemplate = board.getAttribute("data-move-url-template");

            if (!moveUrlTemplate) {
                return;
            }

            var moveUrl = moveUrlTemplate.replace("/cards/0/move", "/cards/" + cardId + "/move");

            var form = document.createElement("form");
            form.method = "post";
            form.action = moveUrl;
            form.style.display = "none";

            var statusInput = document.createElement("input");
            statusInput.type = "hidden";
            statusInput.name = "status";
            statusInput.value = status;

            form.appendChild(statusInput);
            document.body.appendChild(form);
            form.submit();
        });
    });
})();
