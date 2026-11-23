(function () {
    "use strict";

    const FOCUSABLE_SELECTOR =
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), ' +
        'select:not([disabled]), [tabindex]:not([tabindex="-1"])';

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

    function createModalController(modalEl, closeBtnEl) {
        if (!modalEl) {
            return {
                open: function () {},
                close: function () {},
                isOpen: function () {
                    return false;
                },
            };
        }

        let triggerEl = null;

        function isOpen() {
            return modalEl.classList.contains("active");
        }

        function getFocusableElements() {
            return Array.from(modalEl.querySelectorAll(FOCUSABLE_SELECTOR)).filter(function (el) {
                return !el.hidden && el.offsetParent !== null;
            });
        }

        function close() {
            if (!isOpen()) return;
            modalEl.classList.remove("active");
            document.body.classList.remove("modal-open");
            document.removeEventListener("keydown", handleModalKeydown);
            if (triggerEl && typeof triggerEl.focus === "function") {
                triggerEl.focus();
            }
            triggerEl = null;
        }

        function handleModalKeydown(event) {
            if (!isOpen()) return;
            if (event.key === "Escape") {
                event.preventDefault();
                close();
                return;
            }
            if (event.key === "Tab") {
                const focusable = getFocusableElements();
                if (focusable.length === 0) {
                    event.preventDefault();
                    return;
                }
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (event.shiftKey) {
                    if (
                        document.activeElement === first ||
                        !modalEl.contains(document.activeElement)
                    ) {
                        event.preventDefault();
                        last.focus();
                    }
                } else if (
                    document.activeElement === last ||
                    !modalEl.contains(document.activeElement)
                ) {
                    event.preventDefault();
                    first.focus();
                }
            }
        }

        function open(openerEl) {
            triggerEl = openerEl || document.activeElement;
            modalEl.classList.add("active");
            document.body.classList.add("modal-open");
            document.addEventListener("keydown", handleModalKeydown);
            // Force layout so visibility: visible takes effect before moving focus into the dialog.
            void modalEl.offsetWidth;
            const target = closeBtnEl || getFocusableElements()[0];
            if (target && typeof target.focus === "function") {
                target.focus();
            }
        }

        modalEl.addEventListener("click", function (event) {
            if (event.target === modalEl) {
                close();
            }
        });

        if (closeBtnEl) {
            closeBtnEl.addEventListener("click", close);
        }

        return {
            open: open,
            close: close,
            isOpen: isOpen,
        };
    }

    function initMobileNavigation() {
        const toggleBtn = document.getElementById("navToggle");
        const mainNav = document.getElementById("mainNav");
        if (!toggleBtn || !mainNav) return;

        function setMenuOpen(open) {
            mainNav.classList.toggle("open", open);
            toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
            const icon = toggleBtn.querySelector("i");
            if (icon) {
                icon.className = open ? "fas fa-times" : "fas fa-bars";
            }
        }

        toggleBtn.addEventListener("click", function () {
            setMenuOpen(!mainNav.classList.contains("open"));
        });

        mainNav.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                setMenuOpen(false);
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && mainNav.classList.contains("open")) {
                setMenuOpen(false);
                toggleBtn.focus();
            }
        });

        const desktopQuery = window.matchMedia("(min-width: 769px)");
        function handleViewportChange() {
            if (desktopQuery.matches && mainNav.classList.contains("open")) {
                setMenuOpen(false);
            }
        }
        if (typeof desktopQuery.addEventListener === "function") {
            desktopQuery.addEventListener("change", handleViewportChange);
        } else if (typeof desktopQuery.addListener === "function") {
            desktopQuery.addListener(handleViewportChange);
        }
    }

    function initResponsiveSearchPlaceholder() {
        const searchInput = document.getElementById("searchInput");
        if (!searchInput) return;
        const desktopText = searchInput.dataset.placeholderDesktop || searchInput.placeholder;
        const mobileText = searchInput.dataset.placeholderMobile || "Search prompts...";
        const mobileQuery = window.matchMedia("(max-width: 768px)");

        function syncPlaceholder() {
            searchInput.placeholder = mobileQuery.matches ? mobileText : desktopText;
        }

        syncPlaceholder();
        if (typeof mobileQuery.addEventListener === "function") {
            mobileQuery.addEventListener("change", syncPlaceholder);
        } else if (typeof mobileQuery.addListener === "function") {
            mobileQuery.addListener(syncPlaceholder);
        }
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
        }
    });

    initMobileNavigation();
    initResponsiveSearchPlaceholder();

    window.PromptVault = {
        showToast: showToast,
        copyPrompt: copyPrompt,
        createModalController: createModalController,
    };
})();
