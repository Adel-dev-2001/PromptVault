(function () {
    "use strict";

    const promptInput = document.getElementById("prompt_text");
    const charCounter = document.getElementById("charCounter");
    const categoryInput = document.getElementById("category");

    if (promptInput && charCounter) {
        promptInput.addEventListener("input", function () {
            charCounter.textContent = promptInput.value.length + " chars";
        });
    }

    document.querySelectorAll(".tag-pill[data-category]").forEach(function (pill) {
        pill.addEventListener("click", function () {
            if (categoryInput) {
                categoryInput.value = pill.dataset.category || "";
            }
        });
    });

    const fileInput = document.getElementById("image_file");
    const preview = document.getElementById("preview");
    const fileLabel = document.getElementById("fileLabel");
    const dropArea = document.getElementById("dropArea");

    if (!fileInput || !preview || !fileLabel || !dropArea) return;

    function handleFile(file) {
        if (file && file.type.startsWith("image/")) {
            fileLabel.textContent = file.name + " (" + (file.size / 1024).toFixed(1) + " KB)";
            const reader = new FileReader();
            reader.onload = function (event) {
                preview.src = String(event.target.result || "");
                preview.hidden = false;
            };
            reader.readAsDataURL(file);
        }
    }

    fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files.length) {
            handleFile(fileInput.files[0]);
        }
    });

    ["dragenter", "dragover"].forEach(function (eventName) {
        dropArea.addEventListener(eventName, function (event) {
            event.preventDefault();
            event.stopPropagation();
            dropArea.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(function (eventName) {
        dropArea.addEventListener(eventName, function (event) {
            event.preventDefault();
            event.stopPropagation();
            dropArea.classList.remove("dragover");
        });
    });

    dropArea.addEventListener("drop", function (event) {
        const files = event.dataTransfer ? event.dataTransfer.files : null;
        if (files && files.length) {
            fileInput.files = files;
            handleFile(files[0]);
        }
    });
})();
