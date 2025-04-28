// --- Modified static/js/script.js ---

// Global variables (consider scoping them better if app grows)
let previewErrorMsg = null;
let previewArea = null;
let previewPlaceholder = null;
let ocrRawText = ''; // Variable to store the raw text from OCR
let isOcrPreviewMode = false; // Track current mode (false = raw, true = preview)
let accumulatedOcrText = '';
let currentPreviewUrl = null; // To revoke previous object URLs

// Allowed file types for preview and upload
const ALLOWED_MIME_TYPES = [
    'application/pdf',
    'image/png',
    'image/jpeg', // Covers .jpg and .jpeg
    'image/gif',
    'image/bmp',
    'image/webp'
];
const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']; // For simple checks


// --- Preview Rendering Functions (Unchanged) ---

// Function to render the PDF preview (Enhanced Debugging)
async function renderPdfPreview(file, displayArea) {
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
            // pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.6.347/pdf.worker.min.js'; // Set globally once
            console.log("PDF.js worker source set.");

            const loadingTask = pdfjsLib.getDocument({ data: typedarray });
            console.log("PDF document loading task created.");

            try {
                const pdfDoc = await loadingTask.promise;
                console.log(`PDF loaded successfully. Number of pages: ${pdfDoc.numPages}`);

                if (pdfDoc.numPages <= 0) {
                     console.warn("PDF has 0 pages.");
                     displayArea.innerHTML = '<p id="preview-placeholder" style="color: #ccc; text-align: center; margin-top: 20px;">PDF appears to be empty.</p>';
                     resolve();
                     return;
                }

                const desiredWidth = displayArea.clientWidth * 0.95;
                console.log(`Target render width: ${desiredWidth}px`);

                for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
                    console.log(`--- Starting page ${pageNum} ---`);
                    try {
                        const page = await pdfDoc.getPage(pageNum);
                        console.log(`Page ${pageNum}: Acquired page object.`);

                        const viewportDefault = page.getViewport({ scale: 1 });
                        const scale = desiredWidth / viewportDefault.width;
                        const viewport = page.getViewport({ scale: scale });
                        console.log(`Page ${pageNum}: Viewport created. Scale: ${scale.toFixed(2)}, Width: ${viewport.width.toFixed(0)}px, Height: ${viewport.height.toFixed(0)}px`);

                        const canvas = document.createElement('canvas');
                        canvas.id = `pdf-canvas-${pageNum}`;
                        canvas.height = viewport.height;
                        canvas.width = viewport.width;
                        canvas.style.display = 'block';
                        canvas.style.margin = '5px auto 10px auto';
                        canvas.style.maxWidth = '100%';
                        canvas.style.border = '1px solid #ccc';
                        console.log(`Page ${pageNum}: Canvas element created with id ${canvas.id}.`);

                        displayArea.appendChild(canvas);
                        console.log(`Page ${pageNum}: Canvas appended to display area.`);

                        const context = canvas.getContext('2d');
                        const renderContext = {
                            canvasContext: context,
                            viewport: viewport
                        };
                        console.log(`Page ${pageNum}: Render context created. Starting render...`);

                        await page.render(renderContext).promise;
                        console.log(`Page ${pageNum}: Render complete.`);

                    } catch (pageError) {
                        console.error(`Error processing page ${pageNum}:`, pageError);
                        const pageErrorDiv = document.createElement('div');
                        pageErrorDiv.id = `page-error-${pageNum}`;
                        pageErrorDiv.style.cssText = 'color: red; border: 1px dashed red; padding: 10px; margin: 5px auto 10px auto; max-width: 95%;';
                        pageErrorDiv.textContent = `Error rendering page ${pageNum}: ${pageError.message || pageError}`;
                        displayArea.appendChild(pageErrorDiv);
                    }
                     console.log(`--- Finished page ${pageNum} ---`);
                }

                console.log("All pages processed (or attempted). Resolving promise.");
                resolve();

            } catch (reason) {
                console.error('Error loading or rendering PDF (outer catch):', reason);
                 const errorP = displayArea.querySelector('#preview-render-error');
                 if (errorP) {
                      errorP.textContent = `Error processing PDF: ${reason.message || reason}`;
                      errorP.style.display = 'block';
                 } else {
                     displayArea.innerHTML = `<p id="preview-render-error" style="color: red;">Error processing PDF: ${reason.message || reason}</p>`;
                 }
                 const placeholderP = displayArea.querySelector('#preview-placeholder');
                 if (placeholderP) placeholderP.style.display = 'none';

                reject(new Error(`Error processing PDF: ${reason.message || reason}`));
            }
        };

        fileReader.onerror = function() {
            console.error('Error reading file:', fileReader.error);
            reject(new Error(`Error reading file: ${fileReader.error}`));
        }
        console.log("Reading file as ArrayBuffer...");
        fileReader.readAsArrayBuffer(file);
    });
}

// Function to render an image preview
function renderImagePreview(file, displayArea) {
    console.log("Starting renderImagePreview...");
    return new Promise((resolve, reject) => {
       if (currentPreviewUrl) {
           console.log("Revoking previous image URL:", currentPreviewUrl);
           URL.revokeObjectURL(currentPreviewUrl);
           currentPreviewUrl = null;
       }

        const img = document.createElement('img');
        img.style.maxWidth = '100%';
        img.style.maxHeight = '100%';
        img.style.display = 'block';
        img.style.margin = 'auto';

        currentPreviewUrl = URL.createObjectURL(file);
        img.src = currentPreviewUrl;
        console.log("Created new image URL:", currentPreviewUrl);

        img.onload = () => {
            console.log(`Image preview loaded: ${file.name}`);
            displayArea.appendChild(img);
            resolve();
        };
        img.onerror = (err) => {
            console.error('Error loading image preview:', err);
            URL.revokeObjectURL(currentPreviewUrl);
            currentPreviewUrl = null;
            const errorP = displayArea.querySelector('#preview-render-error');
            if(errorP) {
                 errorP.textContent = 'Failed to load image preview.';
                 errorP.style.display = 'block';
            } else {
                displayArea.innerHTML = `<p id="preview-render-error" style="color: red;">Failed to load image preview.</p>`;
            }
            const placeholderP = displayArea.querySelector('#preview-placeholder');
            if (placeholderP) placeholderP.style.display = 'none';

            reject(new Error('Failed to load image preview.'));
        };
    });
}

// --- Unified Preview Handler (Unchanged) ---
async function displayPreview(file) {
    console.log("DisplayPreview called.");
    previewArea = document.getElementById('input-preview-area');

    let placeholderP = null;
    let errorP = null;

    if (previewArea) {
         console.log("Clearing preview area.");
         previewArea.innerHTML = '';

         placeholderP = document.createElement('p');
         placeholderP.id = 'preview-placeholder';
         placeholderP.style.cssText = 'color: #ccc; text-align: center; padding: 20px; font-style: italic; display: block;';
         placeholderP.textContent = 'Loading preview...';
         previewArea.appendChild(placeholderP);
         previewPlaceholder = placeholderP;

         errorP = document.createElement('p');
         errorP.id = 'preview-render-error';
         errorP.style.cssText = 'color: red; display: none; text-align: center; padding: 10px;';
         previewArea.appendChild(errorP);
         previewErrorMsg = errorP;

    } else {
         console.error("Preview area element not found!");
         return;
    }

    if (!file) {
        console.log("No file provided for preview.");
        if (placeholderP) {
             placeholderP.textContent = 'Upload a file to see the preview';
             placeholderP.style.display = 'block';
        }
        if (errorP) {
             errorP.style.display = 'none';
        }
        return;
    }

    console.log(`File selected for preview: ${file.name}, Type: ${file.type}`);

    if (!isFileTypeAllowed(file)) {
        console.log(`Invalid file type for preview: ${file.type || file.name}`);
        if(errorP) {
            errorP.textContent = `Cannot preview: Unsupported file type (${file.type || file.name.split('.').pop()}). Please use PDF or a supported image format.`;
            errorP.style.display = 'block';
        }
        if(placeholderP) placeholderP.style.display = 'none';
        return;
    }

    if(placeholderP) placeholderP.style.display = 'none';
    if(errorP) errorP.style.display = 'none';

    try {
         console.log("Determining preview type...");
         if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
            console.log("Calling renderPdfPreview...");
            await renderPdfPreview(file, previewArea);
            console.log("renderPdfPreview finished.");
        } else {
            console.log("Calling renderImagePreview...");
            await renderImagePreview(file, previewArea);
            console.log("renderImagePreview finished.");
        }
         if(placeholderP) placeholderP.style.display = 'none';
         if(errorP) errorP.style.display = 'none';
         console.log("Preview displayed successfully.");

    } catch (error) {
        console.error('Error displaying preview:', error);
        if (errorP) {
             errorP.textContent = `Preview Error: ${error.message}`;
             errorP.style.display = 'block';
        }
        if (placeholderP) placeholderP.style.display = 'none';
        console.log("Preview failed.");
    }
}


document.addEventListener('DOMContentLoaded', () => {
    // --- Get references to elements ---
    previewErrorMsg = document.getElementById('preview-render-error');
    previewArea = document.getElementById('input-preview-area');
    previewPlaceholder = document.getElementById('preview-placeholder');


    // --- Initialize PDF.js Worker ---
    const { pdfjsLib } = globalThis;
    if (pdfjsLib) {
         pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.6.347/pdf.worker.min.js';
         console.log("PDF.js worker source set.");
    } else {
        console.warn("PDF.js library (pdfjsLib) not found on DOMContentLoaded. PDF preview will fail.");
    }

    // --- File Drag and Drop Logic (Unchanged) ---
    const dropZone = document.querySelector('.file-drop-zone');
    const fileInput = document.getElementById('input-file');
    const dropZoneText = dropZone ? dropZone.querySelector('.drop-zone-text') : null;

    if (dropZone && fileInput && dropZoneText) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
        });

        dropZone.addEventListener('drop', (event) => {
            let file = null;
            if (event.dataTransfer.files.length > 0) {
                 const droppedFile = event.dataTransfer.files[0];
                 if (isFileTypeAllowed(droppedFile)) { // Use helper function
                      fileInput.files = event.dataTransfer.files;
                      file = droppedFile;
                      dropZoneText.textContent = `File selected: ${file.name}`;
                      console.log(`File ${file.name} selected via drop.`);
                 } else {
                     dropZoneText.textContent = 'Please drop a supported file (PDF, PNG, JPG, etc.).';
                     fileInput.value = '';
                 }
            } else {
                 dropZoneText.textContent = 'Drag & drop PDF or Image here';
                 fileInput.value = '';
            }
            displayPreview(file);
        }, false);

        fileInput.addEventListener('change', () => {
             let file = null;
             if (fileInput.files.length > 0) {
                 file = fileInput.files[0];
                 dropZoneText.textContent = `File selected: ${file.name}`;
                 console.log(`File ${file.name} selected via click.`);
             } else {
                 dropZoneText.textContent = 'Drag & drop PDF or Image here';
             }
            displayPreview(file);
        });
    }
    // --- End File Drag and Drop Logic ---

    // --- Conditional VLM Options Logic (Unchanged) ---
    const vlmApiSelect = document.getElementById('vlm-api-select');
    const openAICompatibleOptionsDiv = document.getElementById('openai-compatible-options');
    const openAIOptionsDiv = document.getElementById('openai-options');
    const azureOptionsDiv = document.getElementById('azure-openai-options');
    const ollamaOptionsDiv = document.getElementById('ollama-options');

    if (vlmApiSelect && openAICompatibleOptionsDiv && openAIOptionsDiv && azureOptionsDiv && ollamaOptionsDiv) {
        vlmApiSelect.addEventListener('change', (event) => {
            const selectedApi = event.target.value;
            console.log("VLM API Selection Changed:", selectedApi);
            [openAICompatibleOptionsDiv, openAIOptionsDiv, azureOptionsDiv, ollamaOptionsDiv].forEach(div => {
                div.classList.remove('visible');
                div.style.display = 'none';
            });
            if (selectedApi === 'openai_compatible') {
                openAICompatibleOptionsDiv.classList.add('visible');
                openAICompatibleOptionsDiv.style.display = 'block';
            } else if (selectedApi === 'openai') {
                openAIOptionsDiv.classList.add('visible');
                openAIOptionsDiv.style.display = 'block';
            } else if (selectedApi === 'azure_openai') {
                azureOptionsDiv.classList.add('visible');
                azureOptionsDiv.style.display = 'block';
            } else if (selectedApi === 'ollama') { 
                ollamaOptionsDiv.classList.add('visible');
                ollamaOptionsDiv.style.display = 'block';
            }
        });
         vlmApiSelect.dispatchEvent(new Event('change'));
    } else {
        console.error("Could not find all elements needed for conditional VLM options.");
    }
    // --- End Conditional VLM Options Logic ---

    // --- OCR Form Submission Logic (Unchanged - logic remains the same) ---
    const ocrForm = document.getElementById('ocr-form');
    const ocrOutputArea = document.getElementById('ocr-output-area');
    const ocrLoadingIndicator = document.getElementById('ocr-loading-indicator');
    const ocrErrorMessage = document.getElementById('ocr-error-message');
    const runOcrButton = document.getElementById('run-ocr-button');
    const ocrToggleContainer = document.getElementById('ocr-toggle-container');
    const ocrRenderToggleCheckbox = document.getElementById('ocr-render-toggle-checkbox');
    const outputHeader = document.getElementById('output-header');
    const copyOcrButton = document.getElementById('copy-ocr-text');

    if (ocrForm && ocrOutputArea && ocrLoadingIndicator && ocrErrorMessage && runOcrButton && ocrToggleContainer && ocrRenderToggleCheckbox && outputHeader && copyOcrButton) {
        ocrForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            ocrLoadingIndicator.style.display = 'block';
            ocrErrorMessage.style.display = 'none';
            ocrErrorMessage.textContent = '';
            ocrOutputArea.innerHTML = '';
            runOcrButton.disabled = true;
            ocrToggleContainer.style.display = 'none';
            outputHeader.style.display = 'none';

            ocrRenderToggleCheckbox.checked = true;
            isOcrPreviewMode = true;

            ocrRawText = '';
            accumulatedOcrText = '';

            const formData = new FormData(ocrForm);

            try {
                const response = await fetch('/api/run_ocr', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    let errorMsg = `HTTP error! Status: ${response.status}`;
                    try {
                        const errorResult = await response.json();
                        errorMsg = errorResult.error || errorMsg;
                    } catch (jsonError) {
                         console.warn("Response was not JSON, using status code for error.", response.statusText)
                         errorMsg = `${errorMsg} - ${response.statusText}`;
                    }
                    throw new Error(errorMsg);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                const outputAreaElement = ocrOutputArea;

                async function processTextStream() {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            console.log('Stream complete.');
                            const cleanedFinalText = accumulatedOcrText
                                .replace(/```markdown/g, '')
                                .replace(/```/g, '')
                                .trim();
                            ocrRawText = cleanedFinalText;

                            try {
                                if (typeof marked === 'undefined') {
                                     throw new Error("Marked.js library not loaded!");
                                }
                                outputAreaElement.innerHTML = marked.parse(ocrRawText);
                                console.log('Final Markdown rendered.');
                            } catch (renderError) {
                                 console.error("Error rendering final Markdown:", renderError);
                                 outputAreaElement.textContent = `Error rendering preview: ${renderError.message}\n\nRaw text:\n${ocrRawText}`;
                            }

                            isOcrPreviewMode = true;
                            ocrRenderToggleCheckbox.checked = true;
                            ocrToggleContainer.style.display = 'flex';
                            outputHeader.style.display = 'flex';
                            console.log('Final Markdown displayed. Toggle and header visible.');
                            break;
                        }

                        const chunkText = decoder.decode(value, { stream: true });
                        accumulatedOcrText += chunkText;

                        const cleanedAccumulatedText = accumulatedOcrText
                            .replace(/```markdown/g, '')
                            .replace(/```/g, '');

                        try {
                             if (typeof marked === 'undefined') {
                                 console.warn("Marked.js not ready during stream, showing raw text chunk.");
                                 outputAreaElement.textContent = cleanedAccumulatedText;
                             } else {
                                 outputAreaElement.innerHTML = marked.parse(cleanedAccumulatedText);
                             }
                        } catch (parseError) {
                             console.error("Error parsing markdown during stream:", parseError, "Text:", cleanedAccumulatedText);
                             outputAreaElement.textContent = cleanedAccumulatedText;
                        }
                        outputAreaElement.scrollTop = outputAreaElement.scrollHeight;
                    }
                }

                await processTextStream();

            } catch (error) {
                console.error('Error submitting OCR form or processing stream:', error);
                ocrErrorMessage.textContent = `Error: ${error.message}`;
                ocrErrorMessage.style.display = 'block';
                ocrOutputArea.textContent = 'Processing failed.';
                ocrRawText = '';
                accumulatedOcrText = '';
                ocrToggleContainer.style.display = 'none';
                outputHeader.style.display = 'none';
                isOcrPreviewMode = false;
                ocrRenderToggleCheckbox.checked = false;
            } finally {
                ocrLoadingIndicator.style.display = 'none';
                runOcrButton.disabled = false;
            }
        });

         ocrRenderToggleCheckbox.addEventListener('change', () => {
            isOcrPreviewMode = ocrRenderToggleCheckbox.checked;
            console.log('New isOcrPreviewMode:', isOcrPreviewMode);

            if (isOcrPreviewMode) {
                 console.log('Attempting to render Markdown...');
                 try {
                     if (typeof marked === 'undefined') {
                          throw new Error("Marked.js library is not loaded!");
                     }
                     const cleanedTextForMarkdown = (ocrRawText || "")
                         .replace(/```markdown/g, '')
                         .replace(/```/g, '')
                         .trim();
                     const htmlOutput = marked.parse(cleanedTextForMarkdown);
                     ocrOutputArea.innerHTML = htmlOutput;
                     console.log('Markdown rendered.');
                 } catch (renderError) {
                     console.error("Error rendering Markdown:", renderError);
                     ocrOutputArea.textContent = `Error rendering preview: ${renderError.message}`;
                     ocrRenderToggleCheckbox.checked = false;
                     isOcrPreviewMode = false;
                 }
            } else {
                console.log('Switching back to Raw Text view...');
                ocrOutputArea.textContent = ocrRawText || "";
                console.log('Raw text displayed.');
            }
        });

        copyOcrButton.addEventListener('click', () => {
             if (!ocrRawText || ocrRawText.trim() === '') {
                 console.log('Copy clicked, but no text to copy.');
                 return;
             }
            const textToCopy = (ocrRawText || "")
                 .replace(/```markdown/g, '')
                 .replace(/```/g, '')
                 .trim();

             if (!textToCopy) {
                  console.log('Copy clicked, but text is empty after cleaning.');
                  return;
             }

            navigator.clipboard.writeText(textToCopy).then(() => {
                console.log('Cleaned text copied to clipboard successfully!');
                copyOcrButton.classList.add('copied');
                copyOcrButton.title = 'Copied!';
                setTimeout(() => {
                    copyOcrButton.classList.remove('copied');
                    copyOcrButton.title = 'Copy Raw Text';
                }, 1500);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
                copyOcrButton.title = 'Copy failed!';
                 setTimeout(() => { copyOcrButton.title = 'Copy Raw Text'; }, 1500);
            });
        });

    } else {
        console.error('Could not find all required elements for OCR form submission and preview toggle.');
    }
    // --- End OCR Form Submission Logic ---


    // --- NER Form Submission Logic Placeholder (REMOVED) ---
    // All code related to 'ner-form', 'ner-input-text', etc. has been removed.
    // ...

});

// Helper function to check if file type is allowed (Unchanged)
function isFileTypeAllowed(file) {
    if (!file) return false;
    if (ALLOWED_MIME_TYPES.includes(file.type)) return true;
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    if (ALLOWED_EXTENSIONS.includes(extension)) {
        console.warn(`Allowed file based on extension (${extension}) despite type: ${file.type}`);
        return true;
    }
    console.log(`File type not allowed: ${file.type}, Extension: ${extension}`);
    return false;
}


// --- End of Modified static/js/script.js ---