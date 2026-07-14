/**
 * Gathers form data for single OCR, adds 'advanced_params', and submits.
 * @returns {Promise<Response>} A promise that resolves to the raw Response object for streaming.
 */
async function getOCR() {
    const form = document.getElementById('ocr-form');
    const formData = new FormData(form);

    // Collect advanced parameters (routed to extra_body / options on the backend)
    const advancedParams = collectAdvancedParams('advanced-params-single');
    if (Object.keys(advancedParams).length > 0) {
        formData.append('advanced_params', JSON.stringify(advancedParams));
    }

    return submitSingleOcr(formData);
}

/**
 * Submits the single file OCR form data to the backend and returns the streaming response.
 * @param {FormData} formData - The form data to submit.
 * @returns {Promise<Response>} A promise that resolves to the raw Response object.
 */
async function submitSingleOcr(formData, signal) {
    const response = await fetch('/api/run_ocr', {
        method: 'POST',
        body: formData,
        signal: signal,
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with status ${response.status}`);
    }
    // Return the entire response object so we can read its stream
    return response;
}

/**
 * Gathers form data for batch OCR, adds 'advanced_params', and submits.
 * @returns {Promise<object>} A promise that resolves to the JSON response from the batch endpoint.
 */
async function getBatchOCR() {
    const form = document.getElementById('batch-ocr-form');
    const formData = new FormData(form);

    // Collect advanced parameters (routed to extra_body / options on the backend)
    const advancedParams = collectAdvancedParams('advanced-params-batch');
    if (Object.keys(advancedParams).length > 0) {
        formData.append('advanced_params', JSON.stringify(advancedParams));
    }

    return submitBatchOcr(formData);
}

/**
 * Submits the batch OCR form data to the backend and returns the JSON response.
 * @param {FormData} formData - The form data to submit.
 *s * @returns {Promise<object>} A promise that resolves to the JSON response (e.g., list of files).
 */
async function submitBatchOcr(formData) {
    const response = await fetch('/api/run_batch_ocr', { // Assuming this is the batch endpoint
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with status ${response.status}`);
    }
    // Assuming batch returns JSON, not a stream
    return response.json();
}


/**
 * Submits text to the backend to be rendered as HTML.
 * @param {string} text - The text to render.
 * @returns {Promise<object>} A promise that resolves to the JSON response with the HTML.
 */
async function renderMarkdown(text) {
    const response = await fetch('/api/render_markdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with status ${response.status}`);
    }

    return response.json();
}