(function () {
    "use strict";

    // Activate non-blocking external stylesheets once loaded when CSP forbids inline onload handlers.
    document.querySelectorAll("link[data-async-css]").forEach(function (link) {
        link.media = link.dataset.asyncCss || "all";
    });

    function showToast(message) {
        const toast = document.getElementById("toastNotification");
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("visible");
        window.setTimeout(function () {
            toast.classList.remove("visible");
        }, 2500);
    }

    function markCopiedButton(btn) {
        if (!btn) return;
        const icon = btn.querySelector("i");
        const previousClass = icon ? icon.className : "";
        if (icon) {
            icon.className = "fas fa-check";
        }
        btn.classList.add("copied");
        window.setTimeout(function () {
            if (icon) {
                icon.className = previousClass;
            }
            btn.classList.remove("copied");
        }, 1800);
    }

    function fallbackCopy(text, btn) {
        const tempArea = document.createElement("textarea");
        tempArea.value = text;
        tempArea.setAttribute("readonly", "");
        tempArea.className = "sr-only";
        document.body.appendChild(tempArea);
        tempArea.select();
        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (_err) {
            copied = false;
        }
        document.body.removeChild(tempArea);
        if (copied) {
            showToast("Prompt copied to clipboard.");
            markCopiedButton(btn);
        } else {
            showToast("Unable to copy prompt.");
        }
    }

    function copyPrompt(text, btn) {
        if (!navigator.clipboard || !navigator.clipboard.writeText) {
            fallbackCopy(text, btn);
            return;
        }
        navigator.clipboard
            .writeText(text)
            .then(function () {
                showToast("Prompt copied to clipboard.");
                markCopiedButton(btn);
            })
            .catch(function () {
                fallbackCopy(text, btn);
            });
    }

    document.addEventListener("submit", function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.classList.contains("js-confirm-form")) {
            return;
        }
        const message = form.dataset.confirm || "Are you sure?";
        if (!window.confirm(message)) {
            event.preventDefault();
        }
    });

    document.addEventListener("keydown", function (event) {
        const activeTag = document.activeElement ? document.activeElement.tagName : "";
        if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(activeTag)) {
            const searchInput = document.getElementById("searchInput");
            if (searchInput) {
                event.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        } else if (event.key === "Escape") {
            const modal = document.querySelector(".modal-overlay.active");
            if (modal) {
                modal.classList.remove("active");
                document.body.classList.remove("modal-open");
            }
        }
    });

    window.PromptVault = {
        showToast: showToast,
        copyPrompt: copyPrompt,
    };
})();
