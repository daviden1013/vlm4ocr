/**
 * Attaches zoom controls to a scroll container + content wrapper pair.
 * When useCanvasScale is true, scales canvas children via CSS transform instead of
 * resizing the wrapper width (used for the bbox output panel).
 */
function attachZoomPanel({ panelEl, contentWrapperEl, zoomInBtn, zoomOutBtn, zoomResetBtn, zoomLevelDisplay, useCanvasScale = false }) {
    const ZOOM_STEP = 0.25;
    const ZOOM_MIN = 0.25;
    const ZOOM_MAX = 4.0;
    let zoomLevel = 1.0;

    function applyZoom() {
        if (useCanvasScale) {
            // Scale each canvas relative to its fit-to-container base width
            const canvases = contentWrapperEl.querySelectorAll('canvas.bbox-output-canvas');
            canvases.forEach(c => {
                const base = c._baseDisplayWidth || c._intrinsicWidth || c.width;
                c.style.width = (base * zoomLevel) + 'px';
                c.style.height = 'auto';
            });
        } else {
            contentWrapperEl.style.width = (zoomLevel * 100) + '%';
        }
        if (zoomLevelDisplay) zoomLevelDisplay.textContent = Math.round(zoomLevel * 100) + '%';
    }

    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            zoomLevel = Math.min(ZOOM_MAX, parseFloat((zoomLevel + ZOOM_STEP).toFixed(2)));
            applyZoom();
        });
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            zoomLevel = Math.max(ZOOM_MIN, parseFloat((zoomLevel - ZOOM_STEP).toFixed(2)));
            applyZoom();
        });
    }
    if (zoomResetBtn) {
        zoomResetBtn.addEventListener('click', () => {
            zoomLevel = 1.0;
            applyZoom();
        });
    }

    if (panelEl) {
        panelEl.addEventListener('wheel', (e) => {
            if (!e.ctrlKey && !e.metaKey) return;
            e.preventDefault();
            const delta = e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP;
            zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, parseFloat((zoomLevel + delta).toFixed(2))));
            applyZoom();
        }, { passive: false });
    }
}

/**
 * Attaches event listeners to the VLM API select dropdowns on both forms.
 */
function initializeVlmOptionHandlers() {
    // Handler for the single file form
    const singleFileForm = document.getElementById('ocr-form');
    const singleFileSelect = document.getElementById('vlm-api-select');
    if (singleFileSelect) {
        singleFileSelect.addEventListener('change', function () {
            updateConditionalOptions(singleFileForm, this.value, '');
        });
    }

    // Handler for the batch processing form
    const batchForm = document.getElementById('batch-ocr-form');
    const batchSelect = document.getElementById('batch-vlm-api-select');
    if (batchSelect) {
        batchSelect.addEventListener('change', function () {
            updateConditionalOptions(batchForm, this.value, 'batch-');
        });
    }
}

/**
 * Shows the relevant conditional options div and hides the others by toggling a class.
 * @param {HTMLElement} formElement - The form element containing the dropdown.
 * @param {string} selectedApiValue - The value of the selected VLM API.
 * @param {string} idPrefix - The prefix for the div IDs (e.g., 'batch-').
 */
function updateConditionalOptions(formElement, selectedApiValue, idPrefix) {
    // Hide all conditional option divs by removing the 'is-visible' class
    formElement.querySelectorAll('.conditional-options').forEach(div => {
        div.classList.remove('is-visible');
    });

    // Normalize the value to ensure it matches the div ID format
    const normalizedApi = selectedApiValue.replace(/_/g, '-');
    const optionsDivId = `${idPrefix}${normalizedApi}-options`;
    const optionsDiv = document.getElementById(optionsDivId);

    if (optionsDiv) {
        // Show the correct div by adding the 'is-visible' class
        optionsDiv.classList.add('is-visible');
    }
}


/**
 * Initializes handlers for file inputs to show previews or file lists.
 */
function initializeFilePreviewHandlers() {
    const fileInput = document.getElementById('input-file');
    const dropZone = document.querySelector('#single-file-pane .file-drop-zone');
    const dropZoneText = dropZone ? dropZone.querySelector('.drop-zone-text') : null;
    const previewArea = document.getElementById('input-preview-area');
    const previewContentWrapper = document.getElementById('preview-content-wrapper');

    let currentPreviewUrl = null; // For revoking image object URLs

    if (!fileInput || !dropZone || !previewArea || !previewContentWrapper) {
        console.error("File preview initialization failed: one or more required elements not found.");
        return;
    }

    // --- ZOOM STATE ---
    attachZoomPanel({
        panelEl: previewArea,
        contentWrapperEl: previewContentWrapper,
        zoomInBtn: document.getElementById('zoom-in-btn'),
        zoomOutBtn: document.getElementById('zoom-out-btn'),
        zoomResetBtn: document.getElementById('zoom-reset-btn'),
        zoomLevelDisplay: document.getElementById('zoom-level-display'),
    });

    // bbox output zoom panel
    const bboxOutputArea = document.getElementById('ocr-output-area');
    const bboxOutputWrapper = document.getElementById('ocr-output-area');
    attachZoomPanel({
        panelEl: bboxOutputArea,
        contentWrapperEl: bboxOutputArea,
        zoomInBtn: document.getElementById('bbox-zoom-in-btn'),
        zoomOutBtn: document.getElementById('bbox-zoom-out-btn'),
        zoomResetBtn: document.getElementById('bbox-zoom-reset-btn'),
        zoomLevelDisplay: document.getElementById('bbox-zoom-level-display'),
        useCanvasScale: true,
    });

    // --- RENDER FUNCTIONS ---

    /**
     * Renders a preview for standard image types (PNG, JPEG, etc.).
     */
    function renderImagePreview(file) {
        if (currentPreviewUrl) {
            URL.revokeObjectURL(currentPreviewUrl);
        }
        const img = document.createElement('img');
        img.style.cssText = 'max-width:100%; height:auto; display:block; margin:auto;';
        currentPreviewUrl = URL.createObjectURL(file);
        img.src = currentPreviewUrl;
        img.onload = () => {
            previewContentWrapper.innerHTML = '';
            previewContentWrapper.appendChild(img);
        };
        img.onerror = () => {
            previewContentWrapper.innerHTML = '<p class="ocr-status-message ocr-status-error">Could not preview image.</p>';
            URL.revokeObjectURL(currentPreviewUrl);
            currentPreviewUrl = null;
        };
    }

    /**
     * Renders a multi-page preview of a PDF file onto canvas elements.
     */
    async function renderPdfPreview(file) {
        if (typeof pdfjsLib === 'undefined') {
            previewContentWrapper.innerHTML = '<p class="ocr-status-message ocr-status-error">PDF Viewer library (PDF.js) is not loaded.</p>';
            return;
        }
        if (currentPreviewUrl) {
            URL.revokeObjectURL(currentPreviewUrl);
            currentPreviewUrl = null;
        }
        const fileReader = new FileReader();
        fileReader.onload = async function() {
            try {
                const typedarray = new Uint8Array(this.result);
                const pdfDoc = await pdfjsLib.getDocument({ data: typedarray }).promise;
                previewContentWrapper.innerHTML = '';
                for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
                    const page = await pdfDoc.getPage(pageNum);
                    const viewport = page.getViewport({ scale: 1.5 });
                    const canvas = document.createElement('canvas');
                    const context = canvas.getContext('2d');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;
                    canvas.style.cssText = 'display: block; margin-bottom: 10px; width: 100%; height: auto; border: 1px solid #ccc;';
                    previewContentWrapper.appendChild(canvas);
                    await page.render({ canvasContext: context, viewport: viewport }).promise;
                }
            } catch (error) {
                console.error("PDF preview error:", error);
                previewContentWrapper.innerHTML = `<p class="ocr-status-message ocr-status-error">Error rendering PDF preview: ${error.message}</p>`;
            }
        };
        fileReader.readAsArrayBuffer(file);
    }

    /**
     * Fetches and renders a preview for a TIFF file by converting it on the server.
     */
    async function renderTiffPreview(file) {
        if (currentPreviewUrl) {
            URL.revokeObjectURL(currentPreviewUrl);
            currentPreviewUrl = null;
        }
        const formData = new FormData();
        formData.append('tiff_file', file);
        try {
            const response = await fetch('/api/preview_tiff', { method: 'POST', body: formData });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
                throw new Error(errorData.error);
            }
            const result = await response.json();
            previewContentWrapper.innerHTML = '';
            if (result.status === 'success' && result.pages_data) {
                result.pages_data.forEach(base64Data => {
                    const img = document.createElement('img');
                    img.style.cssText = 'display: block; margin-bottom: 10px; max-width: 100%; border: 1px solid #ccc;';
                    img.src = `data:image/png;base64,${base64Data}`;
                    previewContentWrapper.appendChild(img);
                });
            } else {
                throw new Error(result.error || 'TIFF conversion failed on server.');
            }
        } catch (error) {
            console.error("TIFF preview error:", error);
            previewContentWrapper.innerHTML = `<p class="ocr-status-message ocr-status-error">Error rendering TIFF preview: ${error.message}</p>`;
        }
    }

    /**
     * Orchestrates the display of a file preview based on its type.
     */
    function displayPreview(file) {
        previewContentWrapper.innerHTML = '';
        if (!file) {
            previewContentWrapper.innerHTML = '<p class="ocr-status-message" style="color:#ccc;">Upload a file to see a preview</p>';
            if (currentPreviewUrl) {
                URL.revokeObjectURL(currentPreviewUrl);
                currentPreviewUrl = null;
            }
            return;
        }
        previewContentWrapper.innerHTML = '<p class="ocr-status-message ocr-status-processing">Loading preview...</p>';

        const fileType = file.type;
        const fileName = file.name.toLowerCase();

        if (fileType === 'application/pdf' || fileName.endsWith('.pdf')) {
            renderPdfPreview(file);
        } else if (fileType === 'image/tiff' || fileName.endsWith('.tiff') || fileName.endsWith('.tif')) {
            renderTiffPreview(file);
        } else if (fileType.startsWith('image/')) {
            renderImagePreview(file);
        } else {
            previewContentWrapper.innerHTML = `<p class="ocr-status-message">Preview for this file type is not supported.</p>`;
            if (currentPreviewUrl) {
                URL.revokeObjectURL(currentPreviewUrl);
                currentPreviewUrl = null;
            }
        }
    }

    // --- Event Listeners ---

    // Drag and Drop Listeners
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, e => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'));
    });
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'));
    });

    dropZone.addEventListener('drop', (e) => {
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile) {
            fileInput.files = e.dataTransfer.files;
            dropZoneText.textContent = `Selected: ${droppedFile.name}`;
            displayPreview(droppedFile);
        }
    });

    // File Input 'change' Listener
    fileInput.addEventListener('change', () => {
        const selectedFile = fileInput.files[0];
        if (selectedFile) {
            dropZoneText.textContent = `Selected: ${selectedFile.name}`;
            displayPreview(selectedFile);
        } else {
            dropZoneText.textContent = 'Drag & drop file or click to select';
            displayPreview(null);
        }
    });
}

/**
 * Appends a single empty key/value row to an advanced-params container.
 */
function appendAdvancedParamRow(container) {
    const row = document.createElement('div');
    row.className = 'param-row';
    row.innerHTML = `
        <input type="text" class="param-key" list="advanced-params-keys" placeholder="e.g. top_p" autocomplete="off">
        <input type="text" class="param-value" placeholder='e.g. 0.95 or {"max_soft_tokens": 1120}' autocomplete="off">
        <button type="button" class="remove-param-btn" title="Remove parameter"><i class="fas fa-times"></i></button>
    `;
    container.appendChild(row);
}

/**
 * Wires up the "Advanced Parameters" key/value editors (single + batch panels).
 * Each editor starts with one empty row; the "Add parameter" button appends rows,
 * and each row's remove button deletes it (keeping at least one row present).
 */
function initializeAdvancedParams() {
    document.querySelectorAll('.advanced-params').forEach(container => {
        appendAdvancedParamRow(container);
    });

    document.querySelectorAll('.add-param-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const container = document.getElementById(btn.dataset.target);
            if (container) appendAdvancedParamRow(container);
        });
    });

    document.querySelectorAll('.advanced-params').forEach(container => {
        container.addEventListener('click', (e) => {
            const removeBtn = e.target.closest('.remove-param-btn');
            if (!removeBtn) return;
            const rows = container.querySelectorAll('.param-row');
            if (rows.length > 1) {
                removeBtn.closest('.param-row').remove();
            } else {
                // Keep one row; just clear it
                const row = removeBtn.closest('.param-row');
                row.querySelector('.param-key').value = '';
                row.querySelector('.param-value').value = '';
            }
        });
    });
}

/**
 * Collects an advanced-params editor into a plain object.
 * Each value is parsed as JSON when possible (numbers, booleans, objects, arrays);
 * anything that isn't valid JSON is kept as a raw string.
 * @param {string} containerId - id of the `.advanced-params` container.
 * @returns {Object} the collected key/value parameters (empty if none).
 */
function collectAdvancedParams(containerId) {
    const container = document.getElementById(containerId);
    const params = {};
    if (!container) return params;

    container.querySelectorAll('.param-row').forEach(row => {
        const key = row.querySelector('.param-key').value.trim();
        const rawValue = row.querySelector('.param-value').value.trim();
        if (!key || rawValue === '') return;

        let value;
        try {
            // Strict JSON: 0.95 -> number, true/false -> boolean,
            // {"...": ...} -> object, "text" -> string.
            value = JSON.parse(rawValue);
        } catch (err) {
            // Not valid JSON. Accept Python-style booleans/null case-insensitively
            // (True/False/None), otherwise keep the raw text as a string (e.g. high).
            const lower = rawValue.toLowerCase();
            if (lower === 'true') value = true;
            else if (lower === 'false') value = false;
            else if (lower === 'none' || lower === 'null') value = null;
            else value = rawValue;
        }
        params[key] = value;
    });

    return params;
}