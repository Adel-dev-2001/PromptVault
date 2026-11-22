(function () {
    "use strict";

    const STORAGE_KEY = "promptvault_vault_items";
    const MAX_FILE_BYTES = 10 * 1024 * 1024;
    const MAX_IMAGE_PIXELS = 20000000;
    const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
    const CATEGORY_REGEX = /^[\p{L}\p{Nd}_ \-]{1,30}$/u;

    const state = {
        prompts: [],
        sort: "newest",
        selectedCat: "",
        showFav: false,
        q: "",
        currentModalText: "",
    };

    let pendingUploadDataUrl = "";

    const staticFallback = document.getElementById("staticFallback");
    const viewGallery = document.getElementById("viewGallery");
    const viewAdd = document.getElementById("viewAdd");
    const viewEdit = document.getElementById("viewEdit");
    const viewAbout = document.getElementById("viewAbout");
    const navGallery = document.getElementById("navGallery");
    const navAbout = document.getElementById("navAbout");
    const flashContainer = document.getElementById("flashContainer");
    const galleryGrid = document.getElementById("galleryGrid");
    const emptyState = document.getElementById("emptyState");
    const emptyStateText = document.getElementById("emptyStateText");
    const resetFiltersBtn = document.getElementById("resetFiltersBtn");
    const filterGroup = document.getElementById("filterGroup");
    const searchInput = document.getElementById("searchInput");
    const searchClearBtn = document.getElementById("searchClearBtn");
    const sortNewest = document.getElementById("sortNewest");
    const sortOldest = document.getElementById("sortOldest");
    const detailsModal = document.getElementById("detailsModal");
    const modalImage = document.getElementById("modalImage");
    const modalCategory = document.getElementById("modalCategory");
    const modalPromptText = document.getElementById("modalPromptText");
    const modalDateText = document.getElementById("modalDateText");
    const modalCharCountText = document.getElementById("modalCharCountText");
    const modalDownloadBtn = document.getElementById("modalDownloadBtn");
    const modalCopyBtn = document.getElementById("modalCopyBtn");
    const modalCloseBtn = document.getElementById("modalCloseBtn");
    const fileInput = document.getElementById("image_file");
    const preview = document.getElementById("preview");
    const fileLabel = document.getElementById("fileLabel");
    const dropArea = document.getElementById("dropArea");

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function isSafeImageDataUrl(url) {
        return (
            typeof url === "string" &&
            /^data:image\/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=]+$/i.test(url)
        );
    }

    function safeImageSrc(url) {
        return isSafeImageDataUrl(url) ? url : "";
    }

    function toTitleCase(str) {
        return str.replace(/\S+/g, function (txt) {
            return txt.charAt(0).toUpperCase() + txt.slice(1).toLowerCase();
        });
    }

    function isValidCategory(name) {
        return typeof name === "string" && name.trim().length > 0 && CATEGORY_REGEX.test(name);
    }

    function normalizeAndValidateCategory(rawValue) {
        const trimmed = String(rawValue || "").replace(/^ +| +$/g, "");
        return toTitleCase(trimmed);
    }

    function buildDownloadFilename(item) {
        const safeSlug = String(item.category || "prompt")
            .toLowerCase()
            .replace(/\s+/g, "-")
            .replace(/[^a-z0-9_-]/g, "");
        const prefix = safeSlug || "prompt";
        return prefix + "-" + item.id + ".png";
    }

    function showFlash(message, category) {
        const kind = category === "error" ? "error" : "success";
        const icon = kind === "success" ? "check-circle" : "exclamation-circle";
        flashContainer.innerHTML =
            '<div class="flash flash-' +
            kind +
            '" role="alert">' +
            '<i class="fas fa-' +
            icon +
            '" aria-hidden="true"></i>' +
            "<span>" +
            escapeHtml(message) +
            "</span></div>";
        flashContainer.hidden = false;
        window.setTimeout(function () {
            flashContainer.hidden = true;
        }, 4000);
    }

    function loadPrompts() {
        try {
            localStorage.removeItem("promptvault_items_v1");
            const raw = localStorage.getItem(STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            if (!Array.isArray(parsed)) {
                state.prompts = [];
                return;
            }
            state.prompts = parsed.filter(function (item) {
                return (
                    item &&
                    typeof item.id === "number" &&
                    typeof item.prompt_text === "string" &&
                    isValidCategory(item.category) &&
                    isSafeImageDataUrl(item.image_path)
                );
            });
        } catch (_err) {
            state.prompts = [];
        }
    }

    function savePrompts() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state.prompts));
        } catch (_err) {
            showFlash("Browser localStorage capacity exceeded.", "error");
        }
    }

    function resetUploadSelection(errorMessage) {
        pendingUploadDataUrl = "";
        fileInput.value = "";
        fileLabel.textContent = "Click to browse or drag an image here";
        preview.src = "";
        preview.hidden = true;
        if (errorMessage) {
            showFlash(errorMessage, "error");
        }
    }

    function navigateTo(view, itemId) {
        viewGallery.hidden = view !== "gallery";
        viewAdd.hidden = view !== "add";
        viewEdit.hidden = view !== "edit";
        viewAbout.hidden = view !== "about";

        navGallery.classList.toggle("active", view === "gallery");
        navAbout.classList.toggle("active", view === "about");
        if (view === "gallery") {
            navGallery.setAttribute("aria-current", "page");
            navAbout.removeAttribute("aria-current");
        } else if (view === "about") {
            navAbout.setAttribute("aria-current", "page");
            navGallery.removeAttribute("aria-current");
        } else {
            navGallery.removeAttribute("aria-current");
            navAbout.removeAttribute("aria-current");
        }

        if (view === "gallery") {
            renderGallery();
        } else if (view === "add") {
            document.getElementById("addPromptForm").reset();
            document.getElementById("addCharCounter").textContent = "0 chars";
            resetUploadSelection("");
        } else if (view === "edit" && itemId != null) {
            const item = state.prompts.find(function (p) {
                return p.id === itemId;
            });
            if (!item) {
                showFlash("Item not found.", "error");
                navigateTo("gallery");
                return;
            }
            document.getElementById("editItemId").value = String(item.id);
            document.getElementById("editPreviewImg").src = safeImageSrc(item.image_path);
            document.getElementById("edit_prompt_text").value = item.prompt_text;
            document.getElementById("edit_category").value = item.category;
            document.getElementById("editCharCounter").textContent =
                item.prompt_text.length + " chars";
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function renderFilterChips(categories) {
        const allActive = !state.selectedCat && !state.showFav;
        let html =
            '<li><a href="#all" class="filter-chip ' +
            (allActive ? "active" : "") +
            '" data-filter-type="all"' +
            (allActive ? ' aria-current="true"' : "") +
            ">All</a></li>" +
            '<li><a href="#favorites" class="filter-chip fav-chip ' +
            (state.showFav ? "active" : "") +
            '" data-filter-type="favorites"' +
            (state.showFav ? ' aria-current="true"' : "") +
            '><i class="fas fa-heart" aria-hidden="true"></i> Favorites</a></li>';

        categories.forEach(function (cat) {
            const isActive = state.selectedCat === cat && !state.showFav;
            html +=
                '<li><a href="#cat-' +
                encodeURIComponent(cat) +
                '" class="filter-chip ' +
                (isActive ? "active" : "") +
                '" data-filter-type="category" data-category="' +
                escapeHtml(cat) +
                '"' +
                (isActive ? ' aria-current="true"' : "") +
                ">" +
                escapeHtml(cat) +
                "</a></li>";
        });
        filterGroup.innerHTML = html;
    }

    function renderCardHtml(p) {
        const shortAlt =
            p.prompt_text.length > 80 ? p.prompt_text.slice(0, 80) + "..." : p.prompt_text;
        const dateOnly = String(p.timestamp || "").slice(0, 10);
        const safeSrc = escapeHtml(safeImageSrc(p.image_path));
        const downloadName = escapeHtml(buildDownloadFilename(p));
        const favTitle = p.is_favorite ? "Remove from favorites" : "Mark as favorite";

        return (
            '<article class="card">' +
            '<div class="image-box">' +
            '<img src="' +
            safeSrc +
            '" alt="Prompt artwork: ' +
            escapeHtml(shortAlt) +
            '" loading="lazy">' +
            '<div class="card-overlay">' +
            '<button type="button" class="overlay-btn" title="View Details" aria-label="View prompt details" data-action="details" data-id="' +
            p.id +
            '"><i class="fas fa-expand-alt" aria-hidden="true"></i></button>' +
            '<button type="button" class="overlay-btn" title="Copy Prompt" aria-label="Copy prompt text" data-action="copy" data-id="' +
            p.id +
            '"><i class="fas fa-copy" aria-hidden="true"></i></button>' +
            '<a href="' +
            safeSrc +
            '" download="' +
            downloadName +
            '" class="overlay-btn" title="Download Original" aria-label="Download image"><i class="fas fa-download" aria-hidden="true"></i></a>' +
            '<button type="button" class="overlay-btn" title="Edit Prompt" aria-label="Edit prompt" data-action="edit" data-id="' +
            p.id +
            '"><i class="fas fa-pen" aria-hidden="true"></i></button>' +
            '<button type="button" class="overlay-btn danger" title="Delete Prompt" aria-label="Delete prompt entry" data-action="delete" data-id="' +
            p.id +
            '"><i class="fas fa-trash" aria-hidden="true"></i></button>' +
            "</div>" +
            '<div class="fav-form">' +
            '<button type="button" class="fav-btn ' +
            (p.is_favorite ? "is-fav" : "") +
            '" title="' +
            escapeHtml(favTitle) +
            '" aria-label="Toggle favorite" data-action="favorite" data-id="' +
            p.id +
            '"><i class="fas fa-heart" aria-hidden="true"></i></button>' +
            "</div></div>" +
            '<div class="card-content">' +
            '<div class="card-meta-header">' +
            '<span class="category-badge">' +
            escapeHtml(p.category) +
            "</span>" +
            '<button type="button" class="btn-text-copy" title="Quick Copy" aria-label="Copy prompt" data-action="copy" data-id="' +
            p.id +
            '"><i class="fas fa-copy" aria-hidden="true"></i> Copy</button>' +
            "</div>" +
            '<p class="prompt-text" title="' +
            escapeHtml(p.prompt_text) +
            '">&quot;' +
            escapeHtml(p.prompt_text) +
            "&quot;</p>" +
            '<div class="card-footer">' +
            '<span class="timestamp"><i class="fas fa-clock" aria-hidden="true"></i> ' +
            escapeHtml(dateOnly) +
            "</span>" +
            '<button type="button" class="card-view-link" data-action="details" data-id="' +
            p.id +
            '">Details <i class="fas fa-arrow-right" aria-hidden="true"></i></button>' +
            "</div></div></article>"
        );
    }

    function renderGallery() {
        if (staticFallback) {
            staticFallback.hidden = true;
        }
        const categories = Array.from(
            new Set(
                state.prompts.map(function (p) {
                    return p.category;
                })
            )
        ).sort();
        const favCount = state.prompts.filter(function (p) {
            return p.is_favorite === 1;
        }).length;

        document.getElementById("statTotal").textContent = String(state.prompts.length);
        document.getElementById("statCategories").textContent = String(categories.length);
        document.getElementById("statFavorites").textContent = String(favCount);

        renderFilterChips(categories);

        let filtered = state.prompts.slice();
        if (state.showFav) {
            filtered = filtered.filter(function (p) {
                return p.is_favorite === 1;
            });
        } else if (state.selectedCat) {
            filtered = filtered.filter(function (p) {
                return p.category === state.selectedCat;
            });
        }

        if (state.q) {
            const query = state.q.toLowerCase();
            filtered = filtered.filter(function (p) {
                return (
                    p.prompt_text.toLowerCase().includes(query) ||
                    p.category.toLowerCase().includes(query)
                );
            });
        }

        filtered.sort(function (a, b) {
            if (state.sort === "newest") {
                return b.timestamp.localeCompare(a.timestamp) || b.id - a.id;
            }
            return a.timestamp.localeCompare(b.timestamp) || a.id - b.id;
        });

        if (filtered.length === 0) {
            galleryGrid.hidden = true;
            emptyState.hidden = false;
            if (state.q) {
                emptyStateText.innerHTML =
                    'No results matching query "<strong>' + escapeHtml(state.q) + '</strong>".';
            } else if (state.selectedCat) {
                emptyStateText.innerHTML =
                    'No prompts found in category "<strong>' +
                    escapeHtml(state.selectedCat) +
                    '</strong>" yet.';
            } else if (state.showFav) {
                emptyStateText.textContent = "You have not favorited any prompts yet.";
            } else {
                emptyStateText.textContent =
                    "Your prompt vault is empty. Start archiving your prompts in this browser demo.";
            }
            resetFiltersBtn.hidden = !(state.q || state.selectedCat || state.showFav);
            return;
        }

        emptyState.hidden = true;
        galleryGrid.hidden = false;
        galleryGrid.innerHTML = filtered.map(renderCardHtml).join("");
    }

    function openDetailsModal(id) {
        const item = state.prompts.find(function (p) {
            return p.id === id;
        });
        if (!item) return;

        modalImage.src = safeImageSrc(item.image_path);
        modalImage.alt = "Artwork for prompt: " + item.prompt_text.slice(0, 60);
        modalCategory.textContent = item.category;
        modalPromptText.textContent = item.prompt_text;
        modalDateText.textContent = "Added on " + String(item.timestamp || "").slice(0, 10);
        modalCharCountText.textContent = item.prompt_text.length + " chars";
        modalDownloadBtn.href = safeImageSrc(item.image_path);
        modalDownloadBtn.setAttribute("download", buildDownloadFilename(item));

        state.currentModalText = item.prompt_text;
        detailsModal.classList.add("active");
        document.body.classList.add("modal-open");
    }

    function closeModal() {
        detailsModal.classList.remove("active");
        document.body.classList.remove("modal-open");
    }

    function validatePromptAndCategory(prompt, rawCategory) {
        const category = normalizeAndValidateCategory(rawCategory);
        if (!prompt || !category) {
            showFlash("Please fill in all fields.", "error");
            return null;
        }
        if (!isValidCategory(category)) {
            showFlash(
                "Category can only contain letters, numbers, spaces, - and _ (max 30 characters).",
                "error"
            );
            return null;
        }
        return category;
    }

    function bindCharCounter(textareaId, counterId) {
        const input = document.getElementById(textareaId);
        const counter = document.getElementById(counterId);
        if (input && counter) {
            input.addEventListener("input", function () {
                counter.textContent = input.value.length + " chars";
            });
        }
    }

    function processUploadedFile(file) {
        if (!file) return;
        if (!ALLOWED_TYPES.includes(file.type)) {
            resetUploadSelection(
                "Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp)."
            );
            return;
        }
        if (file.size > MAX_FILE_BYTES) {
            resetUploadSelection("Upload too large. The file must not exceed 10 MB.");
            return;
        }

        const reader = new FileReader();
        reader.onload = function (event) {
            const dataUrl = String(event.target.result || "");
            if (!isSafeImageDataUrl(dataUrl)) {
                resetUploadSelection("Unsupported image data.");
                return;
            }
            const img = new Image();
            img.onload = function () {
                if (img.width * img.height > MAX_IMAGE_PIXELS) {
                    resetUploadSelection("Image dimensions exceed 20 million pixels.");
                    return;
                }
                pendingUploadDataUrl = dataUrl;
                fileLabel.textContent = file.name + " (" + (file.size / 1024).toFixed(1) + " KB)";
                preview.src = dataUrl;
                preview.hidden = false;
            };
            img.onerror = function () {
                resetUploadSelection("Please upload a valid image file.");
            };
            img.src = dataUrl;
        };
        reader.readAsDataURL(file);
    }

    document.addEventListener("DOMContentLoaded", function () {
        loadPrompts();
        renderGallery();

        document.querySelectorAll("[data-nav]").forEach(function (el) {
            el.addEventListener("click", function (event) {
                event.preventDefault();
                navigateTo(el.dataset.nav);
            });
        });

        document.getElementById("searchForm").addEventListener("submit", function (event) {
            event.preventDefault();
        });

        searchInput.addEventListener("input", function () {
            state.q = searchInput.value.trim();
            searchClearBtn.hidden = !state.q;
            renderGallery();
        });

        searchClearBtn.addEventListener("click", function (event) {
            event.preventDefault();
            state.q = "";
            searchInput.value = "";
            searchClearBtn.hidden = true;
            renderGallery();
        });

        resetFiltersBtn.addEventListener("click", function () {
            state.q = "";
            state.selectedCat = "";
            state.showFav = false;
            searchInput.value = "";
            searchClearBtn.hidden = true;
            renderGallery();
        });

        sortNewest.addEventListener("click", function (event) {
            event.preventDefault();
            state.sort = "newest";
            sortNewest.classList.add("active");
            sortOldest.classList.remove("active");
            renderGallery();
        });

        sortOldest.addEventListener("click", function (event) {
            event.preventDefault();
            state.sort = "oldest";
            sortOldest.classList.add("active");
            sortNewest.classList.remove("active");
            renderGallery();
        });

        filterGroup.addEventListener("click", function (event) {
            const link = event.target.closest("a[data-filter-type]");
            if (!link) return;
            event.preventDefault();
            if (link.dataset.filterType === "all") {
                state.selectedCat = "";
                state.showFav = false;
            } else if (link.dataset.filterType === "favorites") {
                state.showFav = true;
                state.selectedCat = "";
            } else if (link.dataset.filterType === "category") {
                state.selectedCat = link.dataset.category || "";
                state.showFav = false;
            }
            renderGallery();
        });

        galleryGrid.addEventListener("click", function (event) {
            const btn = event.target.closest("[data-action]");
            if (!btn) return;
            const id = Number.parseInt(btn.dataset.id, 10);
            if (Number.isNaN(id)) return;

            const action = btn.dataset.action;
            if (action === "details") {
                openDetailsModal(id);
            } else if (action === "copy") {
                const item = state.prompts.find(function (p) {
                    return p.id === id;
                });
                if (item && window.PromptVault) {
                    window.PromptVault.copyPrompt(item.prompt_text, btn);
                }
            } else if (action === "edit") {
                navigateTo("edit", id);
            } else if (action === "favorite") {
                const favItem = state.prompts.find(function (p) {
                    return p.id === id;
                });
                if (favItem) {
                    favItem.is_favorite = favItem.is_favorite ? 0 : 1;
                    savePrompts();
                    renderGallery();
                }
            } else if (action === "delete") {
                if (
                    window.confirm("Are you sure you want to delete this prompt and its artwork?")
                ) {
                    state.prompts = state.prompts.filter(function (p) {
                        return p.id !== id;
                    });
                    savePrompts();
                    renderGallery();
                    showFlash("Deleted successfully.", "success");
                }
            }
        });

        detailsModal.addEventListener("click", function (event) {
            if (event.target === detailsModal) {
                closeModal();
            }
        });
        modalCloseBtn.addEventListener("click", closeModal);
        modalCopyBtn.addEventListener("click", function () {
            if (window.PromptVault) {
                window.PromptVault.copyPrompt(state.currentModalText, modalCopyBtn);
            }
        });

        document.querySelectorAll(".tag-pill[data-category]").forEach(function (pill) {
            pill.addEventListener("click", function () {
                document.getElementById("category").value = pill.dataset.category || "";
            });
        });

        bindCharCounter("prompt_text", "addCharCounter");
        bindCharCounter("edit_prompt_text", "editCharCounter");

        document.getElementById("addPromptForm").addEventListener("submit", function (event) {
            event.preventDefault();
            const prompt = document.getElementById("prompt_text").value.trim();
            const cat = validatePromptAndCategory(
                prompt,
                document.getElementById("category").value
            );
            if (!cat) return;
            if (!isSafeImageDataUrl(pendingUploadDataUrl)) {
                showFlash("Please select a valid image file.", "error");
                return;
            }

            const now = new Date().toISOString().replace("T", " ").slice(0, 19);
            const nextId =
                state.prompts.reduce(function (max, p) {
                    return Math.max(max, p.id);
                }, 0) + 1;

            state.prompts.unshift({
                id: nextId,
                image_path: pendingUploadDataUrl,
                prompt_text: prompt,
                category: cat,
                is_favorite: 0,
                timestamp: now,
            });
            savePrompts();
            navigateTo("gallery");
            showFlash("Prompt added successfully.", "success");
        });

        document.getElementById("editPromptForm").addEventListener("submit", function (event) {
            event.preventDefault();
            const id = Number.parseInt(document.getElementById("editItemId").value, 10);
            const newPrompt = document.getElementById("edit_prompt_text").value.trim();
            const newCat = validatePromptAndCategory(
                newPrompt,
                document.getElementById("edit_category").value
            );
            if (!newCat) return;

            const item = state.prompts.find(function (p) {
                return p.id === id;
            });
            if (item) {
                item.prompt_text = newPrompt;
                item.category = newCat;
                savePrompts();
                navigateTo("gallery");
                showFlash("Updated successfully.", "success");
            }
        });

        fileInput.addEventListener("change", function () {
            if (fileInput.files && fileInput.files.length) {
                processUploadedFile(fileInput.files[0]);
            }
        });

        ["dragenter", "dragover"].forEach(function (evt) {
            dropArea.addEventListener(evt, function (event) {
                event.preventDefault();
                event.stopPropagation();
                dropArea.classList.add("dragover");
            });
        });

        ["dragleave", "drop"].forEach(function (evt) {
            dropArea.addEventListener(evt, function (event) {
                event.preventDefault();
                event.stopPropagation();
                dropArea.classList.remove("dragover");
            });
        });

        dropArea.addEventListener("drop", function (event) {
            const files = event.dataTransfer ? event.dataTransfer.files : null;
            if (files && files.length) {
                processUploadedFile(files[0]);
            }
        });
    });
})();
