// --- services/web_app/static/js/script.js (Complete) ---

// Global variables
let previewErrorMsgElement = null;
let previewArea = null;
let previewPlaceholder = null;
let ocrRawText = ''; // This will store the *concatenated raw content of all pages* after cleaning
let isOcrPreviewMode = true; // Default to Markdown preview
let accumulatedOcrTextForAllPages = ''; // Accumulates raw text from all pages for the final ocrRawText variable
let pageContentsArray = []; 
let lastReceivedDelimiter = "\n\n---\n\n"; // Default, will be updated by the stream

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
// These functions remain the same as in our last complete JS version for TIFF multi-page preview.
// For brevity, I'll assume they are correctly defined here.
// Make sure they are present in your actual file.

async function renderPdfPreview(file, displayArea) {
    // ... (implementation from previous step) ...
    console.log("Starting renderPdfPreview...");
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
    // ... (implementation from previous step) ...
    console.log("Starting renderImagePreview for non-TIFF file:", file.name);
    return new Promise((resolve, reject) => {
       if (window.currentPreviewUrl) URL.revokeObjectURL(window.currentPreviewUrl); // Use window scope for currentPreviewUrl if it's global
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
    // ... (implementation from previous step for multi-page TIFF preview) ...
    console.log("Starting renderConvertedTiffPreview for all pages of:", file.name);
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
                img.onload = () => console.log(`Converted TIFF page ${index + 1} preview loaded: ${file.name}`);
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
    // ... (implementation from previous step) ...
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

    console.log(`File selected for preview: ${file.name}, Type: ${file.type}`);

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
         console.log("Preview displayed successfully.");
    } catch (error) {
        console.error('Error displaying preview in displayPreview catch block:', error.message);
        previewArea.innerHTML = ''; 
        previewErrorMsgElement.textContent = error.message; 
        previewErrorMsgElement.style.display = 'block';
        console.log("Preview failed.");
    }
}


document.addEventListener('DOMContentLoaded', () => {
    previewArea = document.getElementById('input-preview-area');
    previewPlaceholder = document.getElementById('preview-placeholder');

    const { pdfjsLib } = globalThis;
    if (pdfjsLib) {
         pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.6.347/pdf.worker.min.js';
    } else {
        console.warn("PDF.js library (pdfjsLib) not found on DOMContentLoaded. PDF preview will fail.");
    }

    const dropZone = document.querySelector('.file-drop-zone');
    const fileInput = document.getElementById('input-file');
    const dropZoneText = dropZone ? dropZone.querySelector('.drop-zone-text') : null;

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

    const vlmApiSelect = document.getElementById('vlm-api-select');
    const openAICompatibleOptionsDiv = document.getElementById('openai-compatible-options');
    const openAIOptionsDiv = document.getElementById('openai-options');
    const azureOptionsDiv = document.getElementById('azure-openai-options');
    const ollamaOptionsDiv = document.getElementById('ollama-options');

    if (vlmApiSelect) {
        vlmApiSelect.addEventListener('change', (event) => {
            const selectedApi = event.target.value;
            [openAICompatibleOptionsDiv, openAIOptionsDiv, azureOptionsDiv, ollamaOptionsDiv].forEach(div => {
                if(div) div.style.display = 'none';
            });
            if (selectedApi === 'openai_compatible' && openAICompatibleOptionsDiv) openAICompatibleOptionsDiv.style.display = 'block';
            else if (selectedApi === 'openai' && openAIOptionsDiv) openAIOptionsDiv.style.display = 'block';
            else if (selectedApi === 'azure_openai' && azureOptionsDiv) azureOptionsDiv.style.display = 'block';
            else if (selectedApi === 'ollama' && ollamaOptionsDiv) ollamaOptionsDiv.style.display = 'block';
        });
         vlmApiSelect.dispatchEvent(new Event('change'));
    }

    const ocrForm = document.getElementById('ocr-form');
    const ocrOutputArea = document.getElementById('ocr-output-area');
    const runOcrButton = document.getElementById('run-ocr-button');
    const ocrToggleContainer = document.getElementById('ocr-toggle-container');
    const ocrRenderToggleCheckbox = document.getElementById('ocr-render-toggle-checkbox');
    const outputHeader = document.getElementById('output-header');
    const copyOcrButton = document.getElementById('copy-ocr-text');

    function setOcrStatusMessage(message, type = 'info') {
        if (!ocrOutputArea) return;
        let className = 'ocr-status-message';
        if (type === 'error') className += ' ocr-status-error';
        else if (type === 'processing') className += ' ocr-status-processing';
        const sanitizedMessage = message.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, '<br>');
        ocrOutputArea.innerHTML = `<p class="${className}">${sanitizedMessage}</p>`;
    }

    if(ocrOutputArea && (!ocrOutputArea.innerHTML.trim() || ocrOutputArea.innerHTML.includes('id="preview-placeholder"'))) {
        setOcrStatusMessage('OCR results will appear here once a file is processed.', 'info');
    }


    if (ocrForm && ocrOutputArea && runOcrButton) {
        ocrForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            setOcrStatusMessage('Processing, please wait...', 'processing');
            runOcrButton.disabled = true;
            if(ocrToggleContainer) ocrToggleContainer.style.display = 'none';
            if(outputHeader) outputHeader.style.display = 'none';
            if(ocrRenderToggleCheckbox) ocrRenderToggleCheckbox.checked = true;
            isOcrPreviewMode = true;
            accumulatedOcrTextForAllPages = ''; // Reset for new submission
            pageContentsArray = [];
            let currentPageMarkdownContent = ''; // Accumulates Markdown for the current page being streamed
            let pageCounter = 0; // To manage divs for pages

            // Clear previous content more thoroughly
            ocrOutputArea.innerHTML = '';
            // Re-add the "Processing..." message after clearing
            setOcrStatusMessage('Processing, please wait...', 'processing');


            const formData = new FormData(ocrForm);

            try {
                const response = await fetch('/api/run_ocr', { method: 'POST', body: formData });
                if (!response.ok) {
                    let errorMsg = `HTTP error! Status: ${response.status}`;
                    try { const errorResult = await response.json(); errorMsg = errorResult.error || errorMsg; }
                    catch (jsonError) { errorMsg = `${errorMsg} - ${response.statusText || 'Server error'}`; }
                    throw new Error(errorMsg);
                }

                // Clear "Processing..." message once stream is confirmed to be starting
                ocrOutputArea.innerHTML = '';

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = ""; // Buffer for incomplete JSON lines

                // Function to create or get the div for the current page
                function getCurrentPageDiv() {
                    let pageDiv = document.getElementById(`ocr-page-${pageCounter}`);
                    if (!pageDiv) {
                        pageDiv = document.createElement('div');
                        pageDiv.id = `ocr-page-${pageCounter}`;
                        pageDiv.className = 'ocr-page-content'; // For potential styling
                        ocrOutputArea.appendChild(pageDiv);
                    }
                    return pageDiv;
                }
                getCurrentPageDiv(); // Create div for the first page

                async function processNdjsonStream() {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            // Process any remaining content in the buffer (e.g., a final JSON line)
                            if (buffer.trim()) {
                                try {
                                    const streamItem = JSON.parse(buffer);
                                    handleStreamItem(streamItem); // This will process the last chunk for currentPageMarkdownContent
                                } catch (e) {
                                    console.error("Error parsing final buffered JSON:", e, "Buffer:", buffer);
                                    // Optionally, display an error or the raw buffer
                                }
                            }
                            buffer = ""; // Clear buffer

                            // Add the content of the very last page (if any) from currentPageMarkdownContent
                            if (currentPageMarkdownContent.trim()) {
                                const cleanedLastPage = currentPageMarkdownContent
                                    .replace(/^```markdown\s*?\n?/i, '')
                                    .replace(/\n?```\s*$/i, '')
                                    .trim();
                                pageContentsArray.push(cleanedLastPage);
                            }
                            currentPageMarkdownContent = ''; // Important to clear it after processing

                            // Final assembly of ocrRawText using the collected page contents and the last known delimiter
                            if (pageContentsArray.length > 0) {
                                // Join pages with the delimiter. If only one page, join does nothing.
                                ocrRawText = pageContentsArray.join(lastReceivedDelimiter);
                                // For a single page, pageContentsArray will have one item, and .join() won't add a delimiter.
                                // If pageContentsArray.length is 1, ocrRawText will be pageContentsArray[0].
                                // This is correct. The .join() method behaves as desired:
                                // ['page1'].join('delim') -> 'page1'
                                // ['page1', 'page2'].join('delim') -> 'page1delimpage2'
                            } else {
                                ocrRawText = "";
                            }
                            
                            console.log('NDJSON Stream complete. Final ocrRawText:', ocrRawText);
                            // accumulatedOcrTextForAllPages is no longer the primary source for ocrRawText if this new system is used.

                            // Restore UI elements
                            isOcrPreviewMode = true; // Default to Markdown preview after processing
                            if(ocrRenderToggleCheckbox) ocrRenderToggleCheckbox.checked = true;
                            if(ocrToggleContainer) ocrToggleContainer.style.display = 'flex'; // Or your preferred display style
                            if(outputHeader) outputHeader.style.display = 'flex'; // Or your preferred display style
                            break; // Exit the loop
                        }

                        // ... (rest of the stream processing logic: buffer += decoder.decode...) ...
                        buffer += decoder.decode(value, { stream: true });
                        let lines = buffer.split('\n');
                        
                        for (let i = 0; i < lines.length - 1; i++) {
                            let line = lines[i].trim();
                            if (line) { 
                                try {
                                    const streamItem = JSON.parse(line);
                                    handleStreamItem(streamItem);
                                } catch (e) {
                                    console.error("Error parsing JSON line:", e, "Line:", line);
                                }
                            }
                        }
                        buffer = lines[lines.length - 1]; 

                        ocrOutputArea.scrollTop = ocrOutputArea.scrollHeight;
                    }
                }

                function handleStreamItem(item) {
                    const pageDiv = getCurrentPageDiv(); // Ensure this function correctly gets/creates the div for the current page

                    if (item.type === "ocr_chunk" && item.data) {
                        currentPageMarkdownContent += item.data;
                        // Live rendering logic for the current pageDiv remains largely the same
                        let textForLiveRender = currentPageMarkdownContent;
                        if (textForLiveRender.toLowerCase().startsWith("```markdown")) {
                            textForLiveRender = textForLiveRender.substring(textForLiveRender.indexOf('\n') + 1);
                            if (textForLiveRender.trim().toLowerCase().endsWith("```")) {
                                textForLiveRender = textForLiveRender.replace(/\n?```\s*$/i, '').trim();
                            }
                        } else if (textForLiveRender.trim().toLowerCase().endsWith("```")) {
                            if (currentPageMarkdownContent.toLowerCase().includes("```markdown")) {
                                textForLiveRender = textForLiveRender.replace(/\n?```\s*$/i, '').trim();
                            }
                        }

                        try {
                            if (typeof marked !== 'undefined') {
                                pageDiv.innerHTML = marked.parse(textForLiveRender);
                            } else {
                                pageDiv.textContent = currentPageMarkdownContent;
                            }
                        } catch (e) {
                            console.error("Error parsing live Markdown chunk:", e);
                            pageDiv.textContent = currentPageMarkdownContent; // Fallback
                        }
                    } else if (item.type === "page_delimiter" && item.data) {
                        // Clean and store the content of the page that just ended
                        const cleanedPage = currentPageMarkdownContent
                            .replace(/^```markdown\s*?\n?/i, '') // Remove leading ```markdown
                            .replace(/\n?```\s*$/i, '')           // Remove trailing ```
                            .trim();
                        pageContentsArray.push(cleanedPage);

                        lastReceivedDelimiter = item.data; // Store the actual delimiter string

                        // Add visual delimiter in the main output area
                        const delimiterElement = document.createElement('hr');
                        delimiterElement.className = 'page-delimiter-hr';
                        ocrOutputArea.appendChild(delimiterElement);
                        
                        // Prepare for next page
                        pageCounter++;
                        currentPageMarkdownContent = ''; // Reset for the next page's content
                        getCurrentPageDiv(); // Create div for the new page
                        
                    } else if (item.type === "error" && item.data) {
                        console.error("Error from stream:", item.data);
                        setOcrStatusMessage(`Stream Error: ${item.data}`, 'error');
                    }
                }

                await processNdjsonStream();

            } catch (error) { // Catch errors from fetch itself or initial response check
                setOcrStatusMessage(`Error: ${error.message}`, 'error');
                accumulatedOcrTextForAllPages = ''; // Clear any partial accumulation
                if(ocrToggleContainer) ocrToggleContainer.style.display = 'none';
                if(outputHeader) outputHeader.style.display = 'none';
                isOcrPreviewMode = false; if(ocrRenderToggleCheckbox) ocrRenderToggleCheckbox.checked = false;
            } finally {
                runOcrButton.disabled = false;
            }
        });

        if (ocrRenderToggleCheckbox) {
            ocrRenderToggleCheckbox.addEventListener('change', () => {
                isOcrPreviewMode = ocrRenderToggleCheckbox.checked;
                // Re-render all content based on accumulatedOcrTextForAllPages
                ocrOutputArea.innerHTML = ''; // Clear existing page divs
                pageCounter = 0; // Reset page counter for re-rendering
                currentPageMarkdownContent = ''; // Reset current page buffer

                if (!ocrRawText && accumulatedOcrTextForAllPages) { // Ensure ocrRawText is populated if toggle happens before stream end
                    ocrRawText = accumulatedOcrTextForAllPages.trim();
                }
                
                // Split ocrRawText by the actual delimiter string used for accumulation.
                // Note: The delimiter itself is not stored in ocrRawText if we want pure content.
                // For simplicity, let's assume ocrRawText will be the full concatenated cleaned markdown for now.
                // A more robust re-render would re-parse ocrRawText which should be the complete, cleaned markdown.
                // The `accumulatedOcrTextForAllPages` might contain delimiters.

                if (isOcrPreviewMode) {
                     try {
                         if (typeof marked === 'undefined') throw new Error("Marked.js library is not loaded!");
                         // Parse the *entire accumulated raw text* which should be the cleaned content
                         // The ocrRawText should be the final, delimiter-stripped, concatenated text.
                         // If page delimiters are part of ocrRawText they'll become <hr> via Markdown.
                         ocrOutputArea.innerHTML = marked.parse(ocrRawText);
                     } catch (renderError) {
                         setOcrStatusMessage(`Error rendering Markdown: ${renderError.message}`, 'error');
                         if(ocrRenderToggleCheckbox) ocrRenderToggleCheckbox.checked = false;
                         isOcrPreviewMode = false;
                     }
                } else { // Raw text mode
                    // Display the raw text, preserving newlines.
                    // ocrRawText should be the concatenation of cleaned page contents.
                    const pre = document.createElement('pre');
                    pre.style.whiteSpace = 'pre-wrap'; // Ensure wrapping for raw text
                    pre.textContent = ocrRawText;
                    ocrOutputArea.appendChild(pre);
                }
            });
        }
        if (copyOcrButton) {
            copyOcrButton.addEventListener('click', () => {
                const textToCopy = ocrRawText.trim(); // ocrRawText should be the final accumulated raw text
                 if (!textToCopy) return;
                navigator.clipboard.writeText(textToCopy).then(() => {
                    copyOcrButton.classList.add('copied'); copyOcrButton.title = 'Copied!';
                    setTimeout(() => { copyOcrButton.classList.remove('copied'); copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                }).catch(err => {
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
        console.warn(`Allowed file based on extension (${extension}) despite unrecognized or generic MIME type: ${file.type}`);
        return true;
    }
    console.log(`File type not allowed: MIME type '${file.type}', Extension: '${extension}'`);
    return false;
}