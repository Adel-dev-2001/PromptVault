(function () {
    "use strict";

    const dataElement = document.getElementById("promptDataset");
    if (!dataElement) return;

    let promptDataset = [];
    try {
        promptDataset = JSON.parse(dataElement.textContent || "[]");
    } catch (_err) {
        promptDataset = [];
    }

    const modal = document.getElementById("detailsModal");
    const modalImage = document.getElementById("modalImage");
    const modalCategory = document.getElementById("modalCategory");
    const modalPromptText = document.getElementById("modalPromptText");
    const modalDateText = document.getElementById("modalDateText");
    const modalCharCountText = document.getElementById("modalCharCountText");
    const modalDownloadBtn = document.getElementById("modalDownloadBtn");
    const modalCopyBtn = document.getElementById("modalCopyBtn");
    const modalCloseBtn = document.getElementById("modalCloseBtn");
    const galleryGrid = document.getElementById("galleryGrid");

    const modalController = window.PromptVault
        ? window.PromptVault.createModalController(modal, modalCloseBtn)
        : null;

    let currentPromptText = "";

    function openDetailsModal(index, triggerEl) {
        const item = promptDataset[index];
        if (!item || !modalController) return;

        modalImage.src = item.imagePath;
        modalImage.alt = "Artwork for prompt: " + item.promptText.slice(0, 60);
        modalCategory.textContent = item.category;
        modalPromptText.textContent = item.promptText;
        modalDateText.textContent = "Added on " + item.date;
        modalCharCountText.textContent = item.promptText.length + " chars";
        modalDownloadBtn.href = item.downloadUrl;

        currentPromptText = item.promptText;
        modalController.open(triggerEl);
    }

    if (galleryGrid) {
        galleryGrid.addEventListener("click", function (event) {
            const target = event.target.closest("[data-action]");
            if (!target) return;
            const index = Number.parseInt(target.dataset.promptIndex, 10);
            if (Number.isNaN(index) || !promptDataset[index]) return;

            if (target.dataset.action === "details") {
                openDetailsModal(index, target);
            } else if (target.dataset.action === "copy" && window.PromptVault) {
                window.PromptVault.copyPrompt(promptDataset[index].promptText, target);
            }
        });
    }

    if (modalCopyBtn) {
        modalCopyBtn.addEventListener("click", function () {
            if (window.PromptVault) {
                window.PromptVault.copyPrompt(currentPromptText, modalCopyBtn);
            }
        });
    }
})();
