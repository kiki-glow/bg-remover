const fileInput = document.getElementById("file-input");
const form = document.getElementById("upload-form");
const originalImage = document.getElementById("original-image");
const processedImage = document.getElementById("processed-image");
const downloadBtn = document.getElementById("download-btn");
const previewPlaceholder = document.getElementById("preview-placeholder");
const statusEl = document.getElementById("status");
const uploadArea = document.getElementById("upload-area");

// ✅ FIX 1: Show selected filename + preview in upload area immediately on file select
fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;

    // Show image preview inside upload area
    const reader = new FileReader();
    reader.onload = (e) => {
        uploadArea.innerHTML = `
            <img src="${e.target.result}" 
                 style="max-height:160px; max-width:100%; border-radius:12px; object-fit:contain;">
            <div class="upload-hint" style="margin-top:10px;">${file.name}</div>
        `;
    };
    reader.readAsDataURL(file);
    uploadArea.classList.add("has-file");
});

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = fileInput.files[0];
    if (!file) {
        statusEl.textContent = "Please select an image first.";
        return;
    }

    statusEl.textContent = "Processing...";
    statusEl.className = "status busy";

    // Show original in preview area
    const originalUrl = URL.createObjectURL(file);
    originalImage.src = originalUrl;
    originalImage.style.display = "block";
    processedImage.style.display = "none";
    previewPlaceholder.style.display = "none";

    const formData = new FormData();
    formData.append("file", file);

    let response;
    try {
        response = await fetch("http://localhost:8000/remove-bg", {
            method: "POST",
            body: formData,
        });
    } catch (err) {
        statusEl.textContent = `❌ Could not reach server. Is FastAPI running on port 8000?`;
        statusEl.className = "status error";
        return;
    }

    if (!response.ok) {
        const errorText = await response.text();
        statusEl.textContent = `❌ Server error ${response.status}: ${errorText}`;
        statusEl.className = "status error";
        return;
    }

    // ✅ FIX 2: Verify the response is actually an image, not an error JSON
    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("image")) {
        const text = await response.text();
        statusEl.textContent = `❌ Unexpected response from server: ${text}`;
        statusEl.className = "status error";
        return;
    }

    const blob = await response.blob();
    const imageUrl = URL.createObjectURL(blob);

    processedImage.src = imageUrl;
    processedImage.style.display = "block";

    // Show slider
    const sliderContainer = document.getElementById("slide-container");
    const slider = document.getElementById("comparison-slider");
    sliderContainer.classList.remove("hidden");
    slider.value = 50;
    originalImage.style.clipPath = "inset(0 50% 0 0)";

    // Download button
    downloadBtn.classList.remove("hidden");
    downloadBtn.onclick = () => {
        const a = document.createElement("a");
        a.href = imageUrl;
        a.download = "background-removed.png";
        document.body.appendChild(a);
        a.click();
        a.remove();
    };

    statusEl.textContent = "✅ Done!";
    statusEl.className = "status success";
});

// Comparison slider
const slider = document.getElementById("comparison-slider");
slider.addEventListener("input", () => {
    const value = slider.value;
    originalImage.style.clipPath = `inset(0 ${100 - value}% 0 0)`;
});
