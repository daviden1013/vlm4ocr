document.addEventListener('DOMContentLoaded', function () {
    // State and Initialization
    initializeVlmOptionHandlers();
    initializeTabSwitching();
    initializeFilePreviewHandlers();
    let pageContentsArray = [];
    let currentOutputFormat = 'markdown';

    // Element Selectors
    const ocrForm = document.getElementById('ocr-form');
    const runOcrButton = document.getElementById('run-ocr-button');
    const ocrOutputArea = document.getElementById('ocr-output-area');
    const outputFormatSelect = document.getElementById('output-format-select');
    const ocrRenderToggle = document.getElementById('ocr-render-toggle-checkbox');
    const copyOcrTextButton = document.getElementById('copy-ocr-text');
    const ocrToggleContainer = document.getElementById('ocr-toggle-container');
    const outputHeader = document.getElementById('output-header');

    // --- Prompt UX helper (handles JSON, bbox, and other formats) ---
    function applyPromptUx(formatValue, detailsId, requiredHintId, bboxHintId, optionalHintId, textareaId) {
        const isJson = formatValue === 'JSON';
        const isBbox = formatValue === 'bbox';
        const details = document.getElementById(detailsId);
        const requiredHint = document.getElementById(requiredHintId);
        const bboxHint = document.getElementById(bboxHintId);
        const optionalHint = document.getElementById(optionalHintId);
        const textarea = document.getElementById(textareaId);

        if (details && (isJson || isBbox)) details.open = true;
        if (requiredHint) requiredHint.style.display = isJson ? 'inline' : 'none';
        if (bboxHint) bboxHint.style.display = isBbox ? 'inline' : 'none';
        if (optionalHint) optionalHint.style.display = (isJson || isBbox) ? 'none' : 'inline';
        if (textarea) {
            if (isJson) {
                textarea.placeholder = 'Required: describe the JSON schema (e.g., {"patient_name": str, "dob": str})';
            } else if (isBbox) {
                textarea.placeholder = "Optional: target extraction (e.g., 'patient name and DOB'). Leave blank for full-text OCR.";
            } else {
                textarea.placeholder = "Provide context about the image/PDF (e.g., 'This is a doctor\\'s note')";
            }
        }
    }

    // --- Event Listener for Output Format Change ---
    if (outputFormatSelect) {
        outputFormatSelect.addEventListener('change', function() {
            currentOutputFormat = this.value;
            updatePreviewIcon(currentOutputFormat);
            applyPromptUx(this.value, 'single-advanced-settings', 'single-user-prompt-required', 'single-user-prompt-bbox', 'single-user-prompt-optional', 'ocr-user-prompt');
            if (pageContentsArray.length > 0) {
                // Pass the element itself
                renderFinalOutput(pageContentsArray, currentOutputFormat, ocrOutputArea, ocrRenderToggle);
            }
        });
        currentOutputFormat = outputFormatSelect.value;
        updatePreviewIcon(currentOutputFormat);
    }

    // --- Event Listener for Form Submission (single file) ---
    let singleOcrAbortController = null;
    const originalSingleButtonText = runOcrButton.innerHTML;

    if (ocrForm) {
        ocrForm.addEventListener('submit', async function (event) {
            event.preventDefault();

            // If already running, abort it
            if (singleOcrAbortController) {
                singleOcrAbortController.abort();
                return;
            }

            // Validate: JSON format requires a non-empty user prompt
            const selectedFormat = document.getElementById('output-format-select').value;
            const userPromptValue = (document.getElementById('ocr-user-prompt').value || '').trim();
            if (selectedFormat === 'JSON' && userPromptValue === '') {
                ocrOutputArea.innerHTML = '<p class="ocr-status-message ocr-status-error">User Prompt is required when using JSON output. Please describe the JSON schema in the Advanced OCR Settings.</p>';
                document.getElementById('single-advanced-settings').open = true;
                return;
            }

            pageContentsArray = [];
            singleOcrAbortController = new AbortController();
            setButtonState(runOcrButton, 'stop', originalSingleButtonText);
            displayProcessingMessage(ocrOutputArea);
            const formData = new FormData(ocrForm);
            currentOutputFormat = formData.get('output_format');
            updatePreviewIcon(currentOutputFormat);
            let streamStarted = false;
            try {
                const response = await submitSingleOcr(formData, singleOcrAbortController.signal);
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        renderFinalOutput(pageContentsArray, currentOutputFormat, ocrOutputArea, ocrRenderToggle);
                        // Show the appropriate toggle for the format. In bbox mode,
                        // output-header visibility is managed by _bboxSetActiveTab
                        // (hidden in Image tab, shown in Raw tab).
                        const bboxTabToggle = document.getElementById('bbox-tab-toggle');
                        if (currentOutputFormat === 'bbox') {
                            ocrToggleContainer.style.display = 'none';
                            if (bboxTabToggle) bboxTabToggle.style.display = 'flex';
                        } else {
                            ocrToggleContainer.style.display = 'flex';
                            if (bboxTabToggle) bboxTabToggle.style.display = 'none';
                            outputHeader.style.display = 'flex';
                        }
                        break;
                    }
                    buffer += decoder.decode(value, { stream: true });
                    let boundary = buffer.lastIndexOf('\n');
                    if (boundary === -1) continue;
                    if (!streamStarted) {
                        ocrOutputArea.innerHTML = '';
                        streamStarted = true;
                    }
                    let completeLines = buffer.substring(0, boundary);
                    buffer = buffer.substring(boundary + 1);
                    completeLines.split('\n').forEach(line => {
                        if (line.trim() === '') return;
                        try {
                            const jsonData = JSON.parse(line);
                            handleStreamItem(jsonData, currentOutputFormat, ocrOutputArea, pageContentsArray);
                        } catch (e) {
                            console.warn("Skipping invalid JSON line:", line, e);
                        }
                    });
                }
            } catch (error) {
                if (error.name === 'AbortError') {
                    ocrOutputArea.innerHTML = '<p class="ocr-status-message">Stopped.</p>';
                } else {
                    displayOcrError(error, ocrOutputArea);
                }
            } finally {
                singleOcrAbortController = null;
                setButtonState(runOcrButton, 'idle', originalSingleButtonText);
            }
        });
    }

    // --- Event Listener for Preview Toggle ---
    if (ocrRenderToggle) {
        ocrRenderToggle.addEventListener('change', function() {
            if (pageContentsArray.length > 0) {
                // Pass the element (this) itself
                renderFinalOutput(pageContentsArray, currentOutputFormat, ocrOutputArea, this);
            }
        });
    }

    // --- Event Listener for Copy Button ---
    if (copyOcrTextButton) {
        copyOcrTextButton.addEventListener('click', function() {
            let textToCopy;
            if (currentOutputFormat === 'bbox') {
                // Collect bboxes from all page raw pre elements and parse them
                const allBboxes = [];
                document.querySelectorAll('.bbox-raw-sub').forEach((pre, idx) => {
                    try {
                        const raw = pre.textContent.replace(/```json|```/g, '').trim();
                        const parsed = JSON.parse(raw);
                        allBboxes.push({ page_idx: idx, bboxes: parsed });
                    } catch (_) {
                        allBboxes.push({ page_idx: idx, bboxes: pre.textContent });
                    }
                });
                textToCopy = JSON.stringify(allBboxes, null, 2);
            } else {
                textToCopy = pageContentsArray.join('\n\n---\n\n');
            }
            copyTextToClipboard(textToCopy, this);
        });
    }

        // =================================================================
    // == Batch Processing Tab Elements
    // =================================================================
    const batchForm = document.getElementById('batch-ocr-form');
    const batchFileInput = document.getElementById('batch-input-file');
    const batchVlmApiSelect = document.getElementById('batch-vlm-api-select');
    const batchOutputFormatSelect = document.getElementById('batch-output-format-select');
    const batchInputFileListArea = document.getElementById('batch-input-file-list-area');
    const batchOutputFileListhArea = document.getElementById('batch-output-file-list-area');
    const runBatchOcrButton = document.getElementById('run-batch-ocr-button');
    const originalBatchButtonText = runBatchOcrButton.innerHTML;

    // Batch state
    let batchEventSource = null;
    let currentBatchId = null;
    let isBatchRunning = false;
    let batchDataTransfer = new DataTransfer();

    // =================================================================
    // == Event Listeners for Batch Tab
    // =================================================================

    if (batchVlmApiSelect) {
        batchVlmApiSelect.addEventListener('change', handleBatchVlmApiChange);
    }

    if (batchOutputFormatSelect) {
        batchOutputFormatSelect.addEventListener('change', function() {
            applyPromptUx(this.value, 'batch-advanced-settings', 'batch-user-prompt-required', 'batch-user-prompt-bbox', 'batch-user-prompt-optional', 'batch-ocr-user-prompt');
        });
    }

    if (batchFileInput) {
        batchFileInput.addEventListener('change', function () {
            const maxFiles = parseInt(batchFileInput.getAttribute('data-max-files'), 10) || 100;
            const newFiles = Array.from(batchFileInput.files);
            const currentCount = batchDataTransfer.files.length;

            if (currentCount + newFiles.length > maxFiles) {
                alert(`You can only select a maximum of ${maxFiles} files.`);
                batchFileInput.value = '';
                return;
            }

            for (const file of newFiles) {
                batchDataTransfer.items.add(file);
            }

            // Reset the input so the same file can be selected again
            batchFileInput.value = '';
            renderBatchFileList();
        });
    }

    if (batchForm) {
        batchForm.addEventListener('submit', handleBatchFormSubmit);
    }


    // =================================================================
    // == Handler Functions for Batch Tab
    // =================================================================

    function setBatchButtonState(state) {
        if (state === 'uploading') {
            runBatchOcrButton.disabled = true;
            runBatchOcrButton.classList.remove('btn-stop');
            runBatchOcrButton.innerHTML = 'Uploading...';
        } else if (state === 'stop') {
            isBatchRunning = true;
            runBatchOcrButton.disabled = false;
            runBatchOcrButton.classList.add('btn-stop');
            runBatchOcrButton.innerHTML = 'Stop';
        } else { // 'idle'
            isBatchRunning = false;
            runBatchOcrButton.disabled = false;
            runBatchOcrButton.classList.remove('btn-stop');
            runBatchOcrButton.innerHTML = originalBatchButtonText;
        }
        // Re-render file list to reflect disabled/enabled state of remove buttons
        renderBatchFileList();
    }

    function stopBatchOcr() {
        if (batchEventSource) {
            batchEventSource.close();
            batchEventSource = null;
        }
        if (currentBatchId) {
            fetch(`/api/cancel_batch/${currentBatchId}`, { method: 'POST' });
            currentBatchId = null;
        }
        setBatchButtonState('idle');
        batchOutputFileListhArea.insertAdjacentHTML(
            'beforeend',
            '<p class="ocr-status-message">Stopped.</p>'
        );
    }

    /**
     * Shows/hides conditional input fields based on the selected VLM API for the batch form.
     */
    function handleBatchVlmApiChange() {
        document.querySelectorAll('#batch-ocr-form .conditional-options').forEach(div => {
            div.style.display = 'none';
        });
        const selectedApi = batchVlmApiSelect.value;
        const optionsDiv = document.getElementById(`batch-${selectedApi}-options`);
        if (optionsDiv) {
            optionsDiv.style.display = 'block';
        }
    }

    function renderBatchFileList() {
        if (!batchInputFileListArea) return;

        batchInputFileListArea.innerHTML = '';

        if (batchDataTransfer.files.length === 0) {
            batchInputFileListArea.innerHTML = '<p class="ocr-status-message">Uploaded files will be listed here.</p>';
            return;
        }

        const header = document.createElement('div');
        header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;';
        const count = document.createElement('span');
        count.style.cssText = 'font-size:0.85em;color:#888;';
        count.textContent = batchDataTransfer.files.length + ' file(s)';
        const removeAllBtn = document.createElement('button');
        removeAllBtn.textContent = 'Remove All';
        removeAllBtn.className = 'batch-remove-all-btn';
        removeAllBtn.style.cssText = isBatchRunning
            ? 'background:#555;color:#999;border:none;border-radius:3px;padding:3px 10px;cursor:not-allowed;font-size:0.85em;font-weight:bold;'
            : 'background:#dc3545;color:#fff;border:none;border-radius:3px;padding:3px 10px;cursor:pointer;font-size:0.85em;font-weight:bold;';
        removeAllBtn.disabled = isBatchRunning;
        removeAllBtn.addEventListener('click', function () {
            batchDataTransfer = new DataTransfer();
            renderBatchFileList();
        });
        header.appendChild(count);
        header.appendChild(removeAllBtn);
        batchInputFileListArea.appendChild(header);

        const list = document.createElement('div');
        list.className = 'list-group';

        for (let i = 0; i < batchDataTransfer.files.length; i++) {
            const file = batchDataTransfer.files[i];
            const listItem = document.createElement('div');
            listItem.className = 'list-group-item';
            listItem.style.cssText = 'display:flex;justify-content:space-between;align-items:center;';
            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;';
            const icon = document.createElement('i');
            icon.className = 'fas fa-file-alt me-2';
            nameSpan.appendChild(icon);
            nameSpan.appendChild(document.createTextNode(file.name));
            const removeBtn = document.createElement('button');
            removeBtn.innerHTML = '&times;';
            removeBtn.title = 'Remove';
            removeBtn.className = 'batch-remove-file-btn';
            removeBtn.style.cssText = isBatchRunning
                ? 'background:none;border:none;color:#555;font-size:1.2em;cursor:not-allowed;padding:0 0 0 8px;line-height:1;flex-shrink:0;'
                : 'background:none;border:none;color:#dc3545;font-size:1.2em;cursor:pointer;padding:0 0 0 8px;line-height:1;flex-shrink:0;';
            removeBtn.disabled = isBatchRunning;
            removeBtn.addEventListener('click', function () {
                batchDataTransfer = removeFileFromDataTransfer(batchDataTransfer, i);
                renderBatchFileList();
            });
            listItem.appendChild(nameSpan);
            listItem.appendChild(removeBtn);
            list.appendChild(listItem);
        }
        batchInputFileListArea.appendChild(list);
    }

    function removeFileFromDataTransfer(dt, index) {
        const newDataTransfer = new DataTransfer();
        for (let i = 0; i < dt.files.length; i++) {
            if (i !== index) {
                newDataTransfer.items.add(dt.files[i]);
            }
        }
        return newDataTransfer;
    }

    /**
     * Handles the submission of the batch OCR form.
     * Two-step: POST to get batch_id, then GET EventSource for streaming results.
     */
    function handleBatchFormSubmit(event) {
        event.preventDefault();

        // If already running, stop it
        if (isBatchRunning) {
            stopBatchOcr();
            return;
        }

        const formData = new FormData(batchForm);
        // Remove the file input from FormData since it's always empty (cleared after each upload)
        formData.delete('batch_input_files');
        // Append accumulated files from batchDataTransfer
        for (let i = 0; i < batchDataTransfer.files.length; i++) {
            formData.append('batch_input_files', batchDataTransfer.files[i]);
        }
        const totalFiles = batchDataTransfer.files.length;

        if (totalFiles === 0) {
            alert("Please select files to process.");
            return;
        }

        // Validate: JSON format requires a non-empty user prompt
        const batchSelectedFormat = formData.get('output_format');
        const batchUserPrompt = (formData.get('user_prompt') || '').trim();
        if (batchSelectedFormat === 'JSON' && batchUserPrompt === '') {
            batchOutputFileListhArea.innerHTML = '<p class="ocr-status-message ocr-status-error">User Prompt is required when using JSON output. Please describe the JSON schema in the Advanced OCR Settings.</p>';
            document.getElementById('batch-advanced-settings').open = true;
            return;
        }

        setBatchButtonState('uploading');
        batchOutputFileListhArea.innerHTML = '<p class="ocr-status-message">Uploading files and initiating batch job...</p>';

        fetch('/api/initiate_batch_ocr', {
            method: 'POST',
            body: formData,
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.error || 'Server error') });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success' && data.batch_id) {
                currentBatchId = data.batch_id;
                setBatchButtonState('stop');
                batchOutputFileListhArea.innerHTML = '<p class="ocr-status-message">Processing... waiting for first file to complete.</p>';
                startStreamingResults(data.batch_id);
            } else {
                throw new Error(data.error || 'Failed to initiate batch job.');
            }
        })
        .catch(err => {
            console.error("Failed to initiate batch OCR:", err);
            batchOutputFileListhArea.innerHTML = `<p class="ocr-status-message text-danger">Error: ${err.message}</p>`;
            setBatchButtonState('idle');
        });
    }

    /**
     * Connects to the SSE endpoint to stream results for a given batch ID.
     * @param {string} batchId - The unique ID for the batch job.
     */
    function startStreamingResults(batchId) {
        batchEventSource = new EventSource(`/api/stream_batch_results/${batchId}`);
        let processedFiles = 0;

        batchEventSource.onmessage = function(e) {
            const message = JSON.parse(e.data);

            if (processedFiles === 0 && message.type !== 'completed') {
                batchOutputFileListhArea.innerHTML = '';
                const list = document.createElement('div');
                list.className = 'list-group';
                list.id = 'batch-output-list-group';
                batchOutputFileListhArea.appendChild(list);
            }

            const outputListGroup = document.getElementById('batch-output-list-group');

            if (message.type === 'result') {
                processedFiles++;
                const link = document.createElement('a');
                link.href = message.download_url;
                link.className = 'list-group-item list-group-item-action list-group-item-success';
                link.setAttribute('download', '');
                const icon = document.createElement('i');
                icon.className = 'fas fa-download me-2';
                link.appendChild(icon);
                link.appendChild(document.createTextNode(` ${message.filename}`));
                outputListGroup.appendChild(link);

            } else if (message.type === 'error') {
                const errorItem = document.createElement('div');
                errorItem.className = 'list-group-item list-group-item-danger';
                const icon = document.createElement('i');
                icon.className = 'fas fa-exclamation-triangle me-2';
                errorItem.appendChild(icon);
                errorItem.appendChild(document.createTextNode(` Error: ${message.filename || 'a file'} - ${message.data}`));
                outputListGroup.appendChild(errorItem);

            } else if (message.type === 'completed') {
                batchEventSource.close();
                batchEventSource = null;
                currentBatchId = null;
                setBatchButtonState('idle');

                const downloadAllLink = document.getElementById('batch-download-all-button');
                downloadAllLink.href = `/api/download_batch_zip/${message.batch_id}`;
                downloadAllLink.classList.remove('btn-disabled');
                downloadAllLink.removeAttribute('aria-disabled');
            }
        };

        batchEventSource.onerror = function(err) {
            console.error("EventSource failed:", err);
            // Only handle as error if we didn't intentionally stop
            if (batchEventSource) {
                batchEventSource.close();
                batchEventSource = null;
                currentBatchId = null;
                setBatchButtonState('idle');
                if (!document.querySelector('#batch-output-list-group .list-group-item-danger')) {
                    const errorPara = document.createElement('p');
                    errorPara.className = 'ocr-status-message text-danger';
                    errorPara.textContent = 'A connection error occurred. Please check the server logs and try again.';
                    batchOutputFileListhArea.appendChild(errorPara);
                }
            }
        };
    }

    // Initialize the VLM options on page load for the batch tab
    handleBatchVlmApiChange();
});

// Utility Functions
function showCopyConfirmation(button) {
    const originalTitle = button.title;
    button.classList.add('fa-check');
    button.classList.remove('fa-copy');
    button.title = 'Copied!';
    setTimeout(() => {
        button.classList.remove('fa-check');
        button.classList.add('fa-copy');
        button.title = originalTitle;
    }, 2000);
}

function copyTextToClipboard(textToCopy, button) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(textToCopy).then(() => {
            showCopyConfirmation(button);
        }).catch(err => console.error('Failed to copy with Clipboard API:', err));
    } else {
        const textArea = document.createElement('textarea');
        textArea.value = textToCopy;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            if (document.execCommand('copy')) {
                showCopyConfirmation(button);
            }
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        document.body.removeChild(textArea);
    }
}