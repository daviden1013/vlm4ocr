// =================================================================
// == DOM Manipulation Functions
// =================================================================

let pageContentHosts = {};
let currentPageCounter = 0;

// bbox mode state
let bboxFirstResultReceived = false;
let bboxUserChoseTab = false;

/**
 * Maps a label string to a deterministic RGB color using a simple hash.
 * Mirrors bbox.py:_color_for_label (md5 of label → first 3 bytes mod 200).
 */
function colorForLabel(label) {
    // FNV-1a 32-bit hash as a fast JS substitute for md5-first-3-bytes
    let h = 2166136261;
    for (let i = 0; i < label.length; i++) {
        h ^= label.charCodeAt(i);
        h = (h * 16777619) >>> 0;
    }
    const r = (h & 0xff) % 200;
    const g = ((h >>> 8) & 0xff) % 200;
    const b = ((h >>> 16) & 0xff) % 200;
    return `rgb(${r},${g},${b})`;
}

function setButtonState(button, state, originalText) {
    if (state === 'stop') {
        button.disabled = false;
        button.classList.add('btn-stop');
        button.innerHTML = 'Stop';
    } else { // 'idle'
        button.disabled = false;
        button.classList.remove('btn-stop');
        button.innerHTML = originalText;
    }
}

function displayProcessingMessage(outputArea) {
    outputArea.innerHTML = '<p class="ocr-status-message ocr-status-processing">Processing... Please wait.</p>';
    document.getElementById('output-header').style.display = 'none';
    document.getElementById('ocr-toggle-container').style.display = 'none';
    const bboxTabToggle = document.getElementById('bbox-tab-toggle');
    if (bboxTabToggle) bboxTabToggle.style.display = 'none';
    const bboxZoomPanel = document.getElementById('bbox-output-zoom-panel');
    if (bboxZoomPanel) bboxZoomPanel.style.display = 'none';
    pageContentHosts = {};
    currentPageCounter = 0;
    bboxFirstResultReceived = false;
    bboxUserChoseTab = false;
}

function displayOcrError(error, outputArea) {
    console.error('An error occurred:', error);
    outputArea.innerHTML = `<p class="ocr-status-message ocr-status-error">Error: ${error.message}</p>`;
}

function updatePreviewIcon(format) {
    const previewIcon = document.getElementById('preview-icon');
    if (!previewIcon) return;
    let iconClass = 'fa-markdown', title = 'Markdown Preview', lib = 'fab';
    if (format.toLowerCase() === 'html') {
        iconClass = 'fa-code'; title = 'HTML Preview'; lib = 'fas';
    } else if (format.toLowerCase() === 'text') {
        iconClass = 'fa-file-alt'; title = 'Text Preview'; lib = 'fas';
    } else if (format.toLowerCase() === 'json') {
        iconClass = 'fa-brackets-curly'; title = 'JSON Preview'; lib = 'fas';
    }
    previewIcon.className = `${lib} ${iconClass}`;
    previewIcon.title = title;
}

function getOrCreatePageHost(outputArea, outputFormat) {
    if (pageContentHosts[currentPageCounter]) {
        return pageContentHosts[currentPageCounter];
    }
    const pageWrapper = document.createElement('div');
    pageWrapper.id = `page-wrapper-${currentPageCounter}`;
    outputArea.appendChild(pageWrapper);
    let newHost;
    const format = outputFormat.toLowerCase();

    if (format === 'html') {
        const shadowHost = document.createElement('div');
        shadowHost.className = 'ocr-html-shadow-host';
        try {
            const shadowRoot = shadowHost.attachShadow({ mode: 'open' });
            const style = document.createElement('style');
            style.textContent = `:host { display: block; border: 1px dashed #ccc; padding: 10px; margin-bottom: 10px; } body { margin: 0; }`;
            shadowRoot.appendChild(style);
            newHost = shadowRoot;
        } catch (e) { newHost = document.createElement('pre'); }
        pageWrapper.appendChild(shadowHost);
    } else if (format === 'markdown') {
        newHost = document.createElement('div');
        newHost.className = 'ocr-markdown-content';
        pageWrapper.appendChild(newHost);
    } else if (format === 'json') {
        newHost = document.createElement('pre');
        newHost.className = 'ocr-plaintext-content ocr-json-streaming';
        pageWrapper.appendChild(newHost);
    } else if (format === 'bbox') {
        // Wrapper holds both a Raw <pre> and an Image <canvas>
        const rawPre = document.createElement('pre');
        rawPre.className = 'ocr-plaintext-content bbox-raw-sub';
        rawPre.dataset.subview = 'raw';
        pageWrapper.appendChild(rawPre);

        const canvas = document.createElement('canvas');
        canvas.className = 'bbox-output-canvas bbox-image-sub';
        canvas.dataset.subview = 'image';
        canvas.style.display = 'none'; // raw visible by default during streaming
        canvas.style.border = '1px solid #ccc';
        canvas.style.marginBottom = '10px';
        canvas.style.height = 'auto';
        pageWrapper.appendChild(canvas);

        // Return an object that exposes both sub-hosts
        newHost = { rawPre, canvas, pageWrapper };
    } else {
        newHost = document.createElement('pre');
        newHost.className = 'ocr-plaintext-content';
        pageWrapper.appendChild(newHost);
    }
    pageContentHosts[currentPageCounter] = newHost;
    return newHost;
}

function handleStreamItem(item, outputFormat, outputArea, pageContentsArray) {
    const format = outputFormat.toLowerCase();

    if (item.type === 'ocr_chunk' && typeof item.data === 'string') {
        pageContentsArray[currentPageCounter] = (pageContentsArray[currentPageCounter] || '') + item.data;
        const host = getOrCreatePageHost(outputArea, outputFormat);

        if (format === 'bbox') {
            // Stream raw response text into the Raw <pre>
            host.rawPre.textContent = pageContentsArray[currentPageCounter];
        } else if (host.nodeType === Node.DOCUMENT_FRAGMENT_NODE) { // ShadowRoot for HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = pageContentsArray[currentPageCounter];
            const style = host.querySelector('style');
            host.innerHTML = '';
            if (style) host.appendChild(style);
            while (tempDiv.firstChild) {
                host.appendChild(tempDiv.firstChild);
            }
        } else {
             if (format === 'markdown' && typeof marked !== 'undefined') {
                host.innerHTML = marked.parse(pageContentsArray[currentPageCounter].replace(/```markdown|```/g, ''));
             } else {
                host.textContent = pageContentsArray[currentPageCounter];
             }
        }

        const scrollThreshold = 50;
        const userScrolledUp = outputArea.scrollHeight - outputArea.scrollTop - outputArea.clientHeight > scrollThreshold;
        if (!userScrolledUp && outputArea.scrollHeight > outputArea.clientHeight) {
            outputArea.scrollTop = outputArea.scrollHeight;
        }

    } else if (item.type === 'bbox_result' && format === 'bbox') {
        const { page_idx, bboxes, image_width, image_height } = item.data;
        const host = pageContentHosts[page_idx] || getOrCreatePageHost(outputArea, outputFormat);
        const canvas = host.canvas;

        // Draw the source image then overlay bboxes
        const previewSources = document.querySelectorAll('#preview-content-wrapper > img, #preview-content-wrapper > canvas');
        const previewSource = previewSources[page_idx];

        canvas.width = image_width;
        canvas.height = image_height;
        // Store intrinsic size for zoom scaling
        canvas._intrinsicWidth = image_width;
        canvas._intrinsicHeight = image_height;
        // Compute base display width (fit container) so zoom 1.0 = fit
        const containerInnerWidth = outputArea.clientWidth - 40; // account for padding
        canvas._baseDisplayWidth = containerInnerWidth > 0 && containerInnerWidth < image_width
            ? containerInnerWidth
            : image_width;
        canvas.style.width = canvas._baseDisplayWidth + 'px';

        const ctx = canvas.getContext('2d');
        if (previewSource) {
            ctx.drawImage(previewSource, 0, 0, image_width, image_height);
        } else {
            ctx.fillStyle = '#f0f0f0';
            ctx.fillRect(0, 0, image_width, image_height);
        }

        // Determine rendering mode from user prompt
        const userPromptEl = document.getElementById('ocr-user-prompt');
        const hasUserPrompt = !!(userPromptEl && userPromptEl.value.trim());

        // Draw each bbox
        bboxes.forEach(b => {
            const [x0, y0, x1, y1] = b.bbox;
            const lineWidth = Math.max(1, Math.round(image_width / 500));
            const fontSize = Math.max(10, Math.round(image_width / 80));
            const padH = Math.round(fontSize * 0.2);

            const boxColor = hasUserPrompt
                ? colorForLabel(b.label || 'word')
                : `rgb(${Math.floor(Math.random()*200)},${Math.floor(Math.random()*200)},${Math.floor(Math.random()*200)})`;

            ctx.strokeStyle = boxColor;
            ctx.lineWidth = lineWidth;
            ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);

            // Build tag parts: { text, font } rendered left-to-right
            const parts = [];
            if (hasUserPrompt && b.label) {
                parts.push({ text: b.label, font: `bold ${fontSize}px sans-serif` });
            }
            if (hasUserPrompt && b.label && b.text) {
                parts.push({ text: '; ', font: `bold ${fontSize}px sans-serif` });
            }
            if (b.text) {
                parts.push({ text: b.text, font: `italic ${fontSize}px sans-serif` });
            }
            if (parts.length === 0) return;

            // Measure combined tag width
            let totalW = 0;
            parts.forEach(p => { ctx.font = p.font; totalW += ctx.measureText(p.text).width; });

            const tagH = fontSize + padH * 2;
            const tagY0 = Math.max(y0 - tagH, 0);

            ctx.fillStyle = boxColor;
            ctx.fillRect(x0, tagY0, totalW + padH * 2, tagH);

            ctx.fillStyle = '#fff';
            ctx.textBaseline = 'top';
            let xCursor = x0 + padH;
            parts.forEach(p => {
                ctx.font = p.font;
                ctx.fillText(p.text, xCursor, tagY0 + padH);
                xCursor += ctx.measureText(p.text).width;
            });
            ctx.textBaseline = 'alphabetic'; // restore default
        });

        // Auto-flip to Image tab on first bbox_result (unless user already chose a tab)
        if (!bboxFirstResultReceived && !bboxUserChoseTab) {
            bboxFirstResultReceived = true;
            _bboxSetActiveTab('image');
        }

    } else if (item.type === 'page_delimiter') {
        const wrapper = document.getElementById(`page-wrapper-${currentPageCounter}`);
        if (wrapper) {
            const hr = document.createElement('hr');
            hr.className = 'page-delimiter-hr';
            wrapper.insertAdjacentElement('afterend', hr);
        }
        currentPageCounter++;
    } else if (item.type === 'error') {
        displayOcrError(new Error(item.data), outputArea);
    }
}

/**
 * Switches the active bbox sub-view ('raw' or 'image') across all page wrappers.
 */
function _bboxSetActiveTab(tab) {
    const bboxTabRaw = document.getElementById('bbox-tab-raw');
    const bboxTabImage = document.getElementById('bbox-tab-image');
    const bboxZoomPanel = document.getElementById('bbox-output-zoom-panel');
    const outputHeader = document.getElementById('output-header');

    Object.values(pageContentHosts).forEach(host => {
        if (!host || !host.rawPre) return;
        host.rawPre.style.display = tab === 'raw' ? '' : 'none';
        host.canvas.style.display = tab === 'image' ? '' : 'none';
    });

    if (bboxTabRaw) bboxTabRaw.classList.toggle('bbox-pill-active', tab === 'raw');
    if (bboxTabImage) bboxTabImage.classList.toggle('bbox-pill-active', tab === 'image');
    if (bboxZoomPanel) bboxZoomPanel.style.display = tab === 'image' ? 'flex' : 'none';
    // Hide the copy-button header in image view (avoids vertical misalignment with preview)
    if (outputHeader) outputHeader.style.display = tab === 'image' ? 'none' : 'flex';
}

/**
 * Renders the final output. The Markdown logic now mirrors the streaming logic.
 */
function renderFinalOutput(pageContentsArray, outputFormat, outputArea, toggleElement) {
    const format = outputFormat.toLowerCase();

    // For bbox mode the canvases are already rendered incrementally — just wire up tabs/zoom.
    if (format === 'bbox') {
        const bboxTabToggle = document.getElementById('bbox-tab-toggle');
        if (bboxTabToggle) {
            bboxTabToggle.style.display = 'flex';
            const rawBtn = document.getElementById('bbox-tab-raw');
            const imageBtn = document.getElementById('bbox-tab-image');
            if (rawBtn) rawBtn.addEventListener('click', () => { bboxUserChoseTab = true; _bboxSetActiveTab('raw'); });
            if (imageBtn) imageBtn.addEventListener('click', () => { bboxUserChoseTab = true; _bboxSetActiveTab('image'); });
        }
        return;
    }

    outputArea.innerHTML = '';
    const isPreviewMode = toggleElement ? toggleElement.checked : true;
    const rawText = pageContentsArray.join('\n\n---\n\n');

    if (!isPreviewMode) {
        const pre = document.createElement('pre');
        pre.className = 'ocr-rawtext-content';
        pre.textContent = rawText;
        outputArea.appendChild(pre);
        return;
    }

    if (format === 'html') {
        if (pageContentsArray.length > 0) {
            const combinedHtml = pageContentsArray.join(`<hr class='page-delimiter-hr page-delimiter-html-view'>`);
            let wrapper = document.createElement('div');
            wrapper.className = 'ocr-page-content-rendered-wrapper html-wrapper single-html-container';
            const iframe = document.createElement('iframe');
            iframe.style.cssText = 'width: 100%; border: none; height: 75vh;';
            const baseStyle = `<style>html,body{margin:0;padding:0;height:100%;overflow:auto;}body{font-family:sans-serif;color:#212529;background-color:#fff;padding:10px;}hr.page-delimiter-html-view{border:0;height:1px;background-color:#ced4da;margin:25px 5px;}</style>`;
            iframe.srcdoc = baseStyle + combinedHtml;
            iframe.onerror = () => {
                wrapper.innerHTML = `<p class='ocr-status-error'>Error loading HTML content into preview.</p><pre>${combinedHtml}</pre>`;
            };
            wrapper.appendChild(iframe);
            outputArea.appendChild(wrapper);
        } else {
            outputArea.innerHTML = '<p class="ocr-status-message">No HTML content to display.</p>';
        }
    } else if (format === 'markdown' && typeof marked !== 'undefined') {
        // --- THIS IS THE KEY FIX ---
        // Iterate and render each page separately, just like the stream handler.
        pageContentsArray.forEach((pageContent, index) => {
            const pageDiv = document.createElement('div');
            pageDiv.className = 'ocr-markdown-content';
            const cleanedContent = pageContent.replace(/```markdown|```/g, '');
            pageDiv.innerHTML = marked.parse(cleanedContent);
            outputArea.appendChild(pageDiv);

            // Add a delimiter between pages, but not after the last one
            if (index < pageContentsArray.length - 1) {
                const hr = document.createElement('hr');
                hr.className = 'page-delimiter-hr';
                outputArea.appendChild(hr);
            }
        });
    } else if (format === 'json') {
        pageContentsArray.forEach((pageContent, index) => {
            const pre = document.createElement('pre');
            const code = document.createElement('code');
            code.className = 'language-json';

            const stripped = pageContent.replace(/```json|```/g, '').trim();
            let displayText = stripped;
            try {
                const parsed = JSON.parse(stripped);
                displayText = JSON.stringify(parsed, null, 2);
            } catch (_) {
                // Not valid JSON yet — show raw text without highlight
                pre.className = 'ocr-plaintext-content';
                pre.textContent = stripped;
                outputArea.appendChild(pre);
                if (index < pageContentsArray.length - 1) {
                    const hr = document.createElement('hr');
                    hr.className = 'page-delimiter-hr';
                    outputArea.appendChild(hr);
                }
                return;
            }

            if (typeof hljs !== 'undefined') {
                code.innerHTML = hljs.highlight(displayText, { language: 'json' }).value;
            } else {
                code.textContent = displayText;
            }
            pre.appendChild(code);
            outputArea.appendChild(pre);

            if (index < pageContentsArray.length - 1) {
                const hr = document.createElement('hr');
                hr.className = 'page-delimiter-hr';
                outputArea.appendChild(hr);
            }
        });
    } else { // text
        const pre = document.createElement('pre');
        pre.className = 'ocr-plaintext-content';
        pre.textContent = rawText;
        outputArea.appendChild(pre);
    }
}