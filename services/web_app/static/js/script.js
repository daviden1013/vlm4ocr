// --- services/web_app/static/js/script.js ---

// Global variables
let previewErrorMsgElement = null;
let previewArea = null;
let previewPlaceholder = null;
let ocrRawText = ''; // Stores the final concatenated raw content of all pages
let isPreviewMode = true; // Default to preview (rendered) mode
let pageContentsArray = []; // Array to store raw content of each page
let lastReceivedDelimiter = "\n\n---\n\n";
let currentOutputFormat = 'markdown'; // Default, will be updated from dropdown
let pageCounter = 0; // Keep pageCounter global for simplicity here

// Allowed file types for preview and upload
const ALLOWED_MIME_TYPES = [
    'application/pdf', 'image/png', 'image/jpeg', 'image/gif',
    'image/bmp', 'image/webp', 'image/tiff'
];
const ALLOWED_EXTENSIONS = [
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp',
    '.webp', '.tif', '.tiff'
];

// --- Preview Rendering Functions (renderPdfPreview, renderImagePreview, renderConvertedTiffPreview) ---
async function renderPdfPreview(file, displayArea) {
    // console.log("Starting renderPdfPreview...");
    const { pdfjsLib } = globalThis;
    if (!pdfjsLib) {
        console.error("PDF.js library not found!");
        throw new Error('PDF viewer library failed to load.');
    }
    const fileReader = new FileReader();
    return new Promise((resolve, reject) => {
        fileReader.onload = async function() {
            const typedarray = new Uint8Array(this.result);
            try {
                const pdfDoc = await pdfjsLib.getDocument({ data: typedarray }).promise;
                if (pdfDoc.numPages <= 0) {
                     displayArea.innerHTML = '<p class="ocr-status-message" style="color: #ccc;">PDF appears to be empty.</p>';
                     resolve(); return;
                }
                const desiredWidth = displayArea.clientWidth * 0.95;
                for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
                    try {
                        const page = await pdfDoc.getPage(pageNum);
                        const viewportDefault = page.getViewport({ scale: 1 });
                        const scale = desiredWidth / viewportDefault.width;
                        const viewport = page.getViewport({ scale: scale });
                        const canvas = document.createElement('canvas');
                        canvas.height = viewport.height;
                        canvas.width = viewport.width;
                        canvas.style.cssText = 'display: block; margin: 5px auto 10px auto; max-width: 100%; border: 1px solid #ccc;';
                        displayArea.appendChild(canvas);
                        const context = canvas.getContext('2d');
                        await page.render({ canvasContext: context, viewport: viewport }).promise;
                    } catch (pageError) {
                        console.error(`Error processing PDF page ${pageNum}:`, pageError);
                        const pageErrorDiv = document.createElement('div');
                        pageErrorDiv.style.cssText = 'color: red; border: 1px dashed red; padding: 10px; margin: 5px auto 10px auto; max-width: 95%; text-align:center;';
                        pageErrorDiv.textContent = `Error rendering PDF page ${pageNum}: ${pageError.message || pageError}`;
                        displayArea.appendChild(pageErrorDiv);
                    }
                }
                resolve();
            } catch (reason) {
                console.error('Error loading or rendering PDF:', reason);
                reject(new Error(`Error processing PDF: ${reason.message || reason}`));
            }
        };
        fileReader.onerror = () => reject(new Error(`Error reading file: ${fileReader.error}`));
        fileReader.readAsArrayBuffer(file);
    });
}

function renderImagePreview(file, displayArea) {
    // console.log("Starting renderImagePreview for non-TIFF file:", file.name);
    return new Promise((resolve, reject) => {
       if (window.currentPreviewUrl) URL.revokeObjectURL(window.currentPreviewUrl);
        const img = document.createElement('img');
        img.style.cssText = 'max-width: 100%; max-height: 100%; display: block; margin: auto;';
        window.currentPreviewUrl = URL.createObjectURL(file);
        img.src = window.currentPreviewUrl;
        img.onload = () => { displayArea.appendChild(img); resolve(); };
        img.onerror = (err) => {
            URL.revokeObjectURL(window.currentPreviewUrl); window.currentPreviewUrl = null;
            console.error('Error loading image preview for:', file.name, 'Error:', err);
            reject(new Error(`Failed to load image preview for ${file.name}.`));
        };
    });
}

async function renderConvertedTiffPreview(file, displayArea) {
    // console.log("Starting renderConvertedTiffPreview for all pages of:", file.name);
    if (window.currentPreviewUrl) { URL.revokeObjectURL(window.currentPreviewUrl); window.currentPreviewUrl = null; }
    const formData = new FormData();
    formData.append('tiff_file', file);
    try {
        const response = await fetch('/api/preview_tiff', { method: 'POST', body: formData });
        if (!response.ok) {
            const errorResult = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
            throw new Error(errorResult.error || `Failed to convert TIFF: ${response.statusText}`);
        }
        const result = await response.json();
        if (result.status === 'success' && result.pages_data && result.pages_data.length > 0) {
            const desiredWidth = displayArea.clientWidth * 0.95;
            result.pages_data.forEach((base64PageData, index) => {
                const img = document.createElement('img');
                img.style.cssText = `max-width: ${desiredWidth}px; display: block; margin: 5px auto 10px auto; border: 1px solid #ccc;`;
                img.src = `data:image/${result.format};base64,${base64PageData}`;
                // img.onload = () => console.log(`Converted TIFF page ${index + 1} preview loaded: ${file.name}`);
                img.onerror = () => {
                    console.error(`Error loading converted TIFF page ${index + 1} for ${file.name}`);
                    const pageErrorDiv = document.createElement('div');
                    pageErrorDiv.style.cssText = 'color: red; border: 1px dashed red; padding: 10px; margin: 5px auto 10px auto; text-align:center; max-width: 95%;';
                    pageErrorDiv.textContent = `Error loading preview for page ${index + 1}`;
                    displayArea.appendChild(pageErrorDiv);
                };
                displayArea.appendChild(img);
            });
            return Promise.resolve();
        } else if (result.pages_data && result.pages_data.length === 0) {
             throw new Error('TIFF conversion returned no pages.');
        } else {
            throw new Error(result.error || 'TIFF conversion failed on server or returned unexpected data.');
        }
    } catch (error) {
        console.error('Error during multi-page TIFF preview conversion/display:', error);
        throw new Error(`Preview failed for ${file.name}: ${error.message}`);
    }
}

async function displayPreview(file) {
    previewArea = document.getElementById('input-preview-area');
    previewPlaceholder = document.getElementById('preview-placeholder');
    previewArea.innerHTML = '';

    if (!document.getElementById('preview-render-error-dynamic')) {
        previewErrorMsgElement = document.createElement('p');
        previewErrorMsgElement.id = 'preview-render-error-dynamic';
        previewErrorMsgElement.className = 'ocr-status-message ocr-status-error';
        previewErrorMsgElement.style.display = 'none';
        previewArea.appendChild(previewErrorMsgElement);
    } else {
        previewErrorMsgElement = document.getElementById('preview-render-error-dynamic');
    }
    previewErrorMsgElement.style.display = 'none';

    if (!file) {
        previewArea.innerHTML = '<p id="preview-placeholder" class="ocr-status-message" style="color: #ccc;">Upload a file to see the preview</p>';
        return;
    }

    const loadingPlaceholder = document.createElement('p');
    loadingPlaceholder.id = 'preview-loading-placeholder';
    loadingPlaceholder.className = 'ocr-status-message ocr-status-processing';
    loadingPlaceholder.textContent = 'Loading preview...';
    previewArea.appendChild(loadingPlaceholder);

    if (!isFileTypeAllowed(file)) {
        previewArea.innerHTML = '';
        previewErrorMsgElement.textContent = `Cannot preview: Unsupported file type (${file.type || file.name.split('.').pop()}). Please use PDF, TIFF, or a supported image format.`;
        previewErrorMsgElement.style.display = 'block';
        return;
    }

    try {
        const fileExtension = file.name.split('.').pop().toLowerCase();
        previewArea.innerHTML = '';

        if (file.type === 'application/pdf' || fileExtension === 'pdf') {
            await renderPdfPreview(file, previewArea);
        } else if (file.type === 'image/tiff' || fileExtension === 'tif' || fileExtension === 'tiff') {
            await renderConvertedTiffPreview(file, previewArea);
        } else {
            await renderImagePreview(file, previewArea);
        }
    } catch (error) {
        previewArea.innerHTML = '';
        previewErrorMsgElement.textContent = error.message;
        previewErrorMsgElement.style.display = 'block';
    }
}

// Helper to escape HTML for pre display
function escapeHtml(unsafe) {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}


document.addEventListener('DOMContentLoaded', () => {
    // Cache DOM elements
    previewArea = document.getElementById('input-preview-area');
    previewPlaceholder = document.getElementById('preview-placeholder');
    const ocrOutputArea = document.getElementById('ocr-output-area');
    const ocrForm = document.getElementById('ocr-form');
    const runOcrButton = document.getElementById('run-ocr-button');
    const ocrToggleContainer = document.getElementById('ocr-toggle-container');
    const previewToggleCheckbox = document.getElementById('ocr-render-toggle-checkbox');
    const outputHeader = document.getElementById('output-header');
    const copyOcrButton = document.getElementById('copy-ocr-text');
    const outputFormatSelect = document.getElementById('output-format-select');
    const previewIcon = document.getElementById('preview-icon');
    const dropZone = document.querySelector('.file-drop-zone');
    const fileInput = document.getElementById('input-file');
    const dropZoneText = dropZone ? dropZone.querySelector('.drop-zone-text') : null;
    const vlmApiSelect = document.getElementById('vlm-api-select');
    const openAICompatibleOptionsDiv = document.getElementById('openai-compatible-options');
    const openAIOptionsDiv = document.getElementById('openai-options');
    const azureOptionsDiv = document.getElementById('azure-openai-options');
    const ollamaOptionsDiv = document.getElementById('ollama-options');


    const { pdfjsLib } = globalThis;
    if (pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.6.347/pdf.worker.min.js';
    } else {
        console.warn("PDF.js library (pdfjsLib) not found on DOMContentLoaded. PDF preview will fail.");
    }

    if (dropZone && fileInput && dropZoneText) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over')));
        ['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over')));

        dropZone.addEventListener('drop', (event) => {
            let file = null;
            if (event.dataTransfer.files.length > 0) {
                const droppedFile = event.dataTransfer.files[0];
                if (isFileTypeAllowed(droppedFile)) {
                    fileInput.files = event.dataTransfer.files; file = droppedFile;
                    dropZoneText.textContent = `File selected: ${file.name}`;
                } else {
                    dropZoneText.textContent = 'Please drop a supported file (PDF, TIFF, PNG, JPG, etc.).';
                    fileInput.value = '';
                }
            } else {
                dropZoneText.textContent = 'Drag & drop PDF, TIFF, or Image here'; fileInput.value = '';
            }
            displayPreview(file);
        });
        fileInput.addEventListener('change', () => {
            let file = null;
            if (fileInput.files.length > 0) {
                file = fileInput.files[0];
                dropZoneText.textContent = `File selected: ${file.name}`;
            } else {
                dropZoneText.textContent = 'Drag & drop PDF, TIFF, or Image here';
            }
            displayPreview(file);
        });
    }

    if (vlmApiSelect) {
        vlmApiSelect.addEventListener('change', (event) => {
            const selectedApi = event.target.value;
            [openAICompatibleOptionsDiv, openAIOptionsDiv, azureOptionsDiv, ollamaOptionsDiv].forEach(div => {
                if (div) div.style.display = 'none';
            });
            if (selectedApi === 'openai_compatible' && openAICompatibleOptionsDiv) openAICompatibleOptionsDiv.style.display = 'block';
            else if (selectedApi === 'openai' && openAIOptionsDiv) openAIOptionsDiv.style.display = 'block';
            else if (selectedApi === 'azure_openai' && azureOptionsDiv) azureOptionsDiv.style.display = 'block';
            else if (selectedApi === 'ollama' && ollamaOptionsDiv) ollamaOptionsDiv.style.display = 'block';
        });
        if (vlmApiSelect.value === "") { // Ensure initial state is also handled if no option is pre-selected
             [openAICompatibleOptionsDiv, openAIOptionsDiv, azureOptionsDiv, ollamaOptionsDiv].forEach(div => {
                if (div) div.style.display = 'none';
            });
        } else {
            vlmApiSelect.dispatchEvent(new Event('change'));
        }
    }

    function updatePreviewIcon(format) {
        if (!previewIcon) return;
        let iconClass = 'fa-markdown'; let iconTitle = 'Markdown Preview'; let iconLibPrefix = 'fab';
        if (format === 'html') { iconClass = 'fa-code'; iconTitle = 'HTML Preview'; iconLibPrefix = 'fas'; }
        else if (format === 'text') { iconClass = 'fa-file-alt'; iconTitle = 'Text Preview'; iconLibPrefix = 'fas'; }
        previewIcon.className = `${iconLibPrefix} ${iconClass}`; previewIcon.title = iconTitle;
    }

    if (outputFormatSelect) {
        outputFormatSelect.addEventListener('change', (event) => {
            currentOutputFormat = event.target.value.toLowerCase();
            updatePreviewIcon(currentOutputFormat);
            if (pageContentsArray.length > 0 && isPreviewMode) { renderFinalOutput(); }
        });
        currentOutputFormat = outputFormatSelect.value.toLowerCase(); // Initialize
        updatePreviewIcon(currentOutputFormat);
    }

    function setOcrStatusMessage(message, type = 'info') {
        if (!ocrOutputArea) return;
        let className = 'ocr-status-message';
        if (type === 'error') className += ' ocr-status-error';
        else if (type === 'processing') className += ' ocr-status-processing';
        ocrOutputArea.innerHTML = `<p class="${className}">${escapeHtml(message).replace(/\n/g, '<br>')}</p>`;
    }

    if (ocrOutputArea && (!ocrOutputArea.innerHTML.trim() || ocrOutputArea.innerHTML.includes('id="preview-placeholder"'))) {
        setOcrStatusMessage('OCR results will appear here once a file is processed.', 'info');
    }

    function getCurrentPageDivForLiveStream() {
        const pageDivWrapperId = `ocr-live-page-wrapper-${pageCounter}`;
        const shadowHostId = `ocr-live-page-shadowhost-${pageCounter}`;
        let pageDivWrapper = document.getElementById(pageDivWrapperId);
        let shadowHost;

        if (!pageDivWrapper) {
            pageDivWrapper = document.createElement('div');
            pageDivWrapper.id = pageDivWrapperId;
            pageDivWrapper.className = 'ocr-page-content-live-wrapper';

            shadowHost = document.createElement('div');
            shadowHost.id = shadowHostId;
            shadowHost.className = 'ocr-page-content-shadow-host';

            pageDivWrapper.appendChild(shadowHost);
            ocrOutputArea.appendChild(pageDivWrapper);
        } else {
            shadowHost = document.getElementById(shadowHostId);
            if (!shadowHost) {
                console.error(`CRITICAL: Shadow host ${shadowHostId} missing. Recreating.`);
                shadowHost = document.createElement('div');
                shadowHost.id = shadowHostId;
                shadowHost.className = 'ocr-page-content-shadow-host';
                pageDivWrapper.innerHTML = ''; // Clear wrapper before adding new host
                pageDivWrapper.appendChild(shadowHost);
            }
        }

        if (currentOutputFormat === 'html' && shadowHost && !shadowHost.shadowRoot) {
            try {
                const shadow = shadowHost.attachShadow({ mode: 'open' });
                const style = document.createElement('style');
                style.textContent = `
                    :host { display: block; background-color: #f8f9fa; padding: 10px; font-family: sans-serif; color: #212529; }
                    body { margin: 0; background-color: inherit; color: inherit; } /* For VLM generated body tags */
                    a { color: #0056b3; } a:hover { color: #003d80; }
                `;
                shadow.appendChild(style);
            } catch (e) {
                console.error(`Failed to attach Shadow DOM for page ${pageCounter}:`, e, shadowHost);
                shadowHost.dataset.shadowDomFailed = "true";
            }
        }
        return shadowHost;
    }

    if (ocrForm && ocrOutputArea && runOcrButton) {
        ocrForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            pageCounter = 0; // Reset page counter for new submission
            ocrRawText = '';
            pageContentsArray = [];
            let currentPageRawOutput = ''; // Local to this submission

            // Update currentOutputFormat based on form for this run
            const formData = new FormData(ocrForm);
            currentOutputFormat = formData.get('output_format').toLowerCase();
            updatePreviewIcon(currentOutputFormat);

            ocrOutputArea.innerHTML = ''; // Clear previous results/status
            setOcrStatusMessage('Processing, please wait...', 'processing');
            runOcrButton.disabled = true;
            if (ocrToggleContainer) ocrToggleContainer.style.display = 'none';
            if (outputHeader) outputHeader.style.display = 'none';
            if (previewToggleCheckbox) previewToggleCheckbox.checked = true; // Default to preview
            isPreviewMode = true;

            getCurrentPageDivForLiveStream(); // Prepare area for page 0 live stream

            try {
                const response = await fetch('/api/run_ocr', { method: 'POST', body: formData });
                if (!response.ok) {
                    let errorMsg = `HTTP error! Status: ${response.status}`;
                    try { const errorResult = await response.json(); errorMsg = errorResult.error || errorMsg; }
                    catch (jsonError) { errorMsg = `${errorMsg} - ${response.statusText || 'Server error'}`; }
                    throw new Error(errorMsg);
                }

                // Clear "Processing..." message once stream is confirmed
                // ocrOutputArea.innerHTML = ''; // Already done above, live divs will be added.

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";

                async function processNdjsonStream() {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            if (buffer.trim()) {
                                try {
                                    const streamItem = JSON.parse(buffer);
                                    handleStreamItem(streamItem); 
                                } catch (e) { console.error("Error parsing final buffered JSON:", e, "Buffer:", buffer); }
                            }
                            buffer = "";

                            if (currentPageRawOutput.trim()) {
                                pageContentsArray.push(currentPageRawOutput);
                            }
                            // currentPageRawOutput = ''; // Already reset after pushing or in delimiter

                            ocrRawText = pageContentsArray.join(lastReceivedDelimiter);
                            
                            isPreviewMode = true; 
                            if(previewToggleCheckbox) previewToggleCheckbox.checked = true;
                            renderFinalOutput(); 

                            if(ocrToggleContainer) ocrToggleContainer.style.display = 'flex';
                            if(outputHeader) outputHeader.style.display = 'flex';
                            break; 
                        }

                        buffer += decoder.decode(value, { stream: true });
                        let lines = buffer.split('\n');
                        
                        for (let i = 0; i < lines.length - 1; i++) {
                            let line = lines[i].trim();
                            if (line) { 
                                try {
                                    const streamItem = JSON.parse(line);
                                    handleStreamItem(streamItem);
                                } catch (e) { console.error("Error parsing JSON line:", e, "Line:", line); }
                            }
                        }
                        buffer = lines[lines.length - 1]; 
                        if(ocrOutputArea) ocrOutputArea.scrollTop = ocrOutputArea.scrollHeight;
                    }
                }

                function handleStreamItem(item) {
                    const liveContentHost = getCurrentPageDivForLiveStream();

                    if (item.type === "ocr_chunk" && item.data) {
                        currentPageRawOutput += item.data;
                        let displayData = currentPageRawOutput;

                        if (isPreviewMode) {
                            if (currentOutputFormat === 'markdown') {
                                let tempDisplayData = displayData.replace(/^```markdown\s*?\n?/i, '').replace(/\n?```\s*$/i, '').trim();
                                try {
                                    if (typeof marked !== 'undefined') liveContentHost.innerHTML = marked.parse(tempDisplayData);
                                    else liveContentHost.textContent = tempDisplayData;
                                } catch(e) { liveContentHost.textContent = tempDisplayData; }
                            } else if (currentOutputFormat === 'html') {
                                if (liveContentHost.shadowRoot && liveContentHost.dataset.shadowDomFailed !== "true") {
                                    liveContentHost.shadowRoot.innerHTML = displayData;
                                } else {
                                    liveContentHost.innerHTML = `<p class='ocr-status-message ocr-status-error' style='text-align:left; font-size:0.8em; padding:5px;'>Live HTML preview using Shadow DOM failed. Displaying raw HTML:</p><pre style='max-height:200px; overflow-y:auto; border:1px solid #ccc; padding:5px;'>${escapeHtml(displayData)}</pre>`;
                                }
                            } else { // Plain text
                                liveContentHost.textContent = displayData;
                            }
                        } else { 
                           liveContentHost.textContent = displayData;
                        }
                    } else if (item.type === "page_delimiter" && item.data) {
                        pageContentsArray.push(currentPageRawOutput);
                        lastReceivedDelimiter = item.data;
                        currentPageRawOutput = ''; // Reset for the next page

                        const delimiterElement = document.createElement('hr');
                        delimiterElement.className = 'page-delimiter-hr';
                        ocrOutputArea.appendChild(delimiterElement);
                        
                        pageCounter++; 
                        getCurrentPageDivForLiveStream(); // Prepare for next page's live stream
                        
                    } else if (item.type === "error" && item.data) {
                        console.error("Error from stream:", item.data);
                        let targetErrorDiv = liveContentHost;
                        if (currentOutputFormat === 'html' && liveContentHost.shadowRoot) {
                            targetErrorDiv = liveContentHost.shadowRoot;
                        }
                        targetErrorDiv.innerHTML = `<p class="ocr-status-error">Stream Error: ${escapeHtml(item.data)}</p>`;
                        
                        // Finalize what we have
                        if(currentPageRawOutput.trim()) pageContentsArray.push(currentPageRawOutput);
                        ocrRawText = pageContentsArray.join(lastReceivedDelimiter);
                        currentPageRawOutput = ''; // Clear for future
                        // Potentially stop further processing or display final output here.
                        renderFinalOutput(); // Show what has been processed so far
                        if(ocrToggleContainer) ocrToggleContainer.style.display = 'flex';
                        if(outputHeader) outputHeader.style.display = 'flex';
                        // No 'break' here, stream completion will handle it or reader will be done.
                    }
                }
                await processNdjsonStream();
            } catch (error) { 
                setOcrStatusMessage(`Error: ${error.message}`, 'error');
                ocrRawText = ''; pageContentsArray = [];
                if(ocrToggleContainer) ocrToggleContainer.style.display = 'none';
                if(outputHeader) outputHeader.style.display = 'none';
                isPreviewMode = false; if(previewToggleCheckbox) previewToggleCheckbox.checked = false;
            } finally {
                runOcrButton.disabled = false;
            }
        });

        function renderFinalOutput() {
            if (!ocrOutputArea) return;
            ocrOutputArea.innerHTML = ''; // Clear ALL previous content

            if (isPreviewMode) {
                if (pageContentsArray.length === 0 && ocrRawText.trim()) {
                     console.warn("renderFinalOutput: pageContentsArray empty, rendering ocrRawText directly.");
                     const pre = document.createElement('pre');
                     pre.textContent = ocrRawText;
                     ocrOutputArea.appendChild(pre);
                     return;
                }

                pageContentsArray.forEach((pageContent, index) => {
                    let contentToRender = pageContent;
                    // The wrapper for each page's content (Markdown div, HTML iframe, or Text pre)
                    let pageElementWrapper = document.createElement('div');
                    pageElementWrapper.className = 'ocr-page-content-rendered-wrapper'; // Use this for common styling if needed

                    if (currentOutputFormat === 'markdown') {
                        let mdHost = document.createElement('div');
                        mdHost.className = 'ocr-markdown-content'; // Specific class for markdown content
                        let cleanedPageMarkdown = contentToRender.replace(/^```markdown\s*?\n?/i, '').replace(/\n?```\s*$/i, '').trim();
                        try {
                            if (typeof marked !== 'undefined') mdHost.innerHTML = marked.parse(cleanedPageMarkdown);
                            else throw new Error("Marked.js not loaded");
                        } catch (e) {
                            console.error("Markdown parsing error for page:", e);
                            mdHost.textContent = cleanedPageMarkdown; 
                        }
                        pageElementWrapper.appendChild(mdHost);
                    } else if (currentOutputFormat === 'html') {
                        pageElementWrapper.className = 'ocr-page-content-rendered-wrapper html-wrapper'; // Add specific class

                        const iframe = document.createElement('iframe');
                        iframe.style.width = '100%';
                        iframe.style.border = 'none';
                        // No explicit height here, hoping content + injected style will work.

                        iframe.setAttribute('sandbox', 'allow-scripts');
                        // The scrolling attribute is deprecated but doesn't hurt.
                        // Setting to "no" attempts to prevent the iframe from showing its own scrollbars,
                        // relying on the outer container to scroll.
                        iframe.setAttribute('scrolling', 'no');


                        // Inject a simple style to help the iframe's content expand.
                        // This assumes the VLM content will be within a <body> tag.
                        const iframeBaseStyle = `
                            <style>
                                html, body {
                                    margin: 0;
                                    padding: 0;
                                    height: auto; /* Let content determine height */
                                    overflow-y: hidden; /* Try to prevent iframe's own vertical scrollbar */
                                }
                                /* You might add a default font matching the main page if needed */
                                body { font-family: sans-serif; color: #212529; background-color: #ffffff; padding:10px; }
                            </style>
                        `;
                        iframe.srcdoc = iframeBaseStyle + contentToRender;

                        iframe.onerror = () => {
                            console.error("Error loading content into iframe for page " + index);
                            pageElementWrapper.innerHTML = `<p class='ocr-status-error'>Error loading HTML preview for this page.</p><pre>${escapeHtml(contentToRender)}</pre>`;
                        };

                        // The onload height adjustment is generally problematic for sandboxed srcdoc.
                        // We are relying on the content and the injected style above.
                        // If it still doesn't work, a large min-height on the iframe via CSS is a fallback.

                        pageElementWrapper.appendChild(iframe);
                    } else { // Plain text
                        const pre = document.createElement('pre');
                        pre.className = 'ocr-plaintext-content'; // Specific class for plaintext
                        pre.textContent = contentToRender;
                        pageElementWrapper.appendChild(pre);
                    }
                    ocrOutputArea.appendChild(pageElementWrapper);

                    if (index < pageContentsArray.length - 1) {
                        const delimiterElement = document.createElement('hr');
                        delimiterElement.className = 'page-delimiter-hr';
                        ocrOutputArea.appendChild(delimiterElement);
                    }
                });

            } else { // Raw text mode
                const pre = document.createElement('pre');
                pre.className = 'ocr-rawtext-content';
                pre.textContent = ocrRawText; 
                ocrOutputArea.appendChild(pre);
            }
            // Scroll the main ocrOutputArea if needed, not individual page wrappers.
            if(ocrOutputArea) ocrOutputArea.scrollTop = ocrOutputArea.scrollHeight;
        }
        
        if (previewToggleCheckbox) {
            previewToggleCheckbox.addEventListener('change', () => {
                isPreviewMode = previewToggleCheckbox.checked;
                renderFinalOutput();
            });
        }

        if (copyOcrButton) {
            copyOcrButton.addEventListener('click', () => {
                const textToCopy = ocrRawText.trim(); 
                 if (!textToCopy) return;
                navigator.clipboard.writeText(textToCopy).then(() => {
                    copyOcrButton.classList.add('copied'); copyOcrButton.title = 'Copied!';
                    setTimeout(() => { copyOcrButton.classList.remove('copied'); copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                }).catch(err => {
                    console.error("Copy failed:", err);
                    copyOcrButton.title = 'Copy failed!'; setTimeout(() => { copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                });
            });
        }
    }
});

function isFileTypeAllowed(file) {
    if (!file) return false;
    if (ALLOWED_MIME_TYPES.includes(file.type)) return true;
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    if (ALLOWED_EXTENSIONS.includes(extension)) {
        return true;
    }
    return false;
}