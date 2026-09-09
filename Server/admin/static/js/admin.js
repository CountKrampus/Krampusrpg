"use strict";

/*
 * Krampus RPG
 * Admin Dashboard JavaScript
 */


/* =========================================================
   Mobile Sidebar
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    const menuToggle = document.getElementById("adminMenuToggle");
    const sidebar = document.querySelector(".admin-sidebar");

    if (!menuToggle || !sidebar) {
        return;
    }

    menuToggle.addEventListener("click", () => {
        const isOpen = sidebar.classList.toggle("open");

        menuToggle.setAttribute(
            "aria-expanded",
            isOpen ? "true" : "false"
        );
    });

    /*
     * Close the mobile sidebar when clicking outside of it.
     */
    document.addEventListener("click", (event) => {
        if (!sidebar.classList.contains("open")) {
            return;
        }

        if (
            sidebar.contains(event.target) ||
            menuToggle.contains(event.target)
        ) {
            return;
        }

        sidebar.classList.remove("open");

        menuToggle.setAttribute(
            "aria-expanded",
            "false"
        );
    });
});


/* =========================================================
   Confirmation Helpers
   ========================================================= */

function adminConfirm(message) {
    return window.confirm(
        message || "Are you sure you want to continue?"
    );
}


/*
 * Automatically handle elements using:
 *
 * data-confirm="Are you sure?"
 */
document.addEventListener("click", (event) => {
    const element = event.target.closest("[data-confirm]");

    if (!element) {
        return;
    }

    const message = element.getAttribute("data-confirm");

    if (!adminConfirm(message)) {
        event.preventDefault();
    }
});


/* =========================================================
   Flash Alert Dismissal
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    const alerts = document.querySelectorAll(".admin-alert");

    alerts.forEach((alert) => {
        const closeButton = alert.querySelector(
            ".admin-alert-close"
        );

        if (!closeButton) {
            return;
        }

        closeButton.addEventListener("click", () => {
            alert.remove();
        });
    });
});


/* =========================================================
   Auto-Hide Temporary Alerts
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    const alerts = document.querySelectorAll(
        ".admin-alert-success"
    );

    alerts.forEach((alert) => {
        setTimeout(() => {
            if (!document.body.contains(alert)) {
                return;
            }

            alert.remove();
        }, 6000);
    });
});


/* =========================================================
   Table Row Helpers
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    const tables = document.querySelectorAll(
        ".admin-table"
    );

    tables.forEach((table) => {
        const rows = table.querySelectorAll("tbody tr");

        rows.forEach((row) => {
            row.addEventListener("mouseenter", () => {
                row.classList.add("admin-row-hover");
            });

            row.addEventListener("mouseleave", () => {
                row.classList.remove("admin-row-hover");
            });
        });
    });
});


/* =========================================================
   Form Submission Protection
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll(
        "form[data-confirm-submit]"
    );

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message =
                form.getAttribute("data-confirm-submit");

            if (!adminConfirm(message)) {
                event.preventDefault();
            }
        });
    });
});


/* =========================================================
   Utility: Disable Button After Submit
   ========================================================= */

function preventDoubleSubmit(form) {
    if (!form) {
        return;
    }

    const submitButtons = form.querySelectorAll(
        'button[type="submit"], input[type="submit"]'
    );

    submitButtons.forEach((button) => {
        button.disabled = true;

        if (button.tagName.toLowerCase() === "button") {
            button.dataset.originalText =
                button.textContent;

            button.textContent = "Saving...";
        }
    });
}


/*
 * Forms using:
 *
 * data-prevent-double-submit
 *
 * will disable their submit buttons after submission.
 */
document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll(
        "form[data-prevent-double-submit]"
    );

    forms.forEach((form) => {
        form.addEventListener("submit", () => {
            preventDoubleSubmit(form);
        });
    });
});


/* =========================================================
   Global Admin Utilities
   ========================================================= */

window.KrampusAdmin = {
    confirm: adminConfirm,
    preventDoubleSubmit: preventDoubleSubmit
};