// --- services/web_app/static/js/script.js ---

// Global variables
let previewErrorMsgElement = null;
let previewArea = null;
let ocrRawText = '';
let isPreviewMode = true;
let pageContentsArray = [];
let lastReceivedDelimiter = "\n\n---\n\n";
let currentOutputFormat = 'markdown';
let pageCounter = 0;
let currentPreviewUrl = null;
let pageContentHosts = {}; // To store persistent content hosts for live streaming

const ALLOWED_MIME_TYPES = [
    'application/pdf', 'image/png', 'image/jpeg', 'image/gif',
    'image/bmp', 'image/webp', 'image/tiff'
];
const ALLOWED_EXTENSIONS = [
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp',
    '.webp', '.tif', '.tiff'
];

async function renderPdfPreview(file, displayArea) {
    const { pdfjsLib } = globalThis;
    if (!pdfjsLib) {
        console.error("RenderPdfPreview: PDF.js library (pdfjsLib) not found!"); // Keep critical errors
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
                        canvas.height = viewport.height; canvas.width = viewport.width;
                        canvas.style.cssText = 'display: block; margin: 5px auto 10px auto; max-width: 100%; border: 1px solid #ccc;';
                        displayArea.appendChild(canvas);
                        const context = canvas.getContext('2d');
                        await page.render({ canvasContext: context, viewport: viewport }).promise;
                    } catch (pageError) {
                        console.error(`RenderPdfPreview: Error PDF page ${pageNum}:`, pageError); // Keep critical errors
                        const pErrDiv = document.createElement('div');
                        pErrDiv.style.cssText = 'color:red;border:1px dashed red;padding:10px;margin:5px auto 10px auto;max-width:95%;text-align:center;';
                        pErrDiv.textContent = `Error rendering PDF page ${pageNum}: ${pageError.message || String(pageError)}`;
                        displayArea.appendChild(pErrDiv);
                    }
                }
                resolve();
            } catch (reason) {
                console.error('RenderPdfPreview: Error loading/rendering PDF doc:', reason); // Keep critical errors
                reject(new Error(`Error processing PDF: ${reason.message || String(reason)}`));
            }
        };
        fileReader.onerror = () => reject(new Error(`Error reading file: ${fileReader.error}`));
        fileReader.readAsArrayBuffer(file);
    });
}

function renderImagePreview(file, displayArea) {
    return new Promise((resolve, reject) => {
       if (currentPreviewUrl) URL.revokeObjectURL(currentPreviewUrl);
        const img = document.createElement('img');
        img.style.cssText = 'max-width:100%;max-height:100%;display:block;margin:auto;';
        currentPreviewUrl = URL.createObjectURL(file);
        img.src = currentPreviewUrl;
        img.onload = () => { displayArea.appendChild(img); resolve(); };
        img.onerror = (err) => {
            URL.revokeObjectURL(currentPreviewUrl); currentPreviewUrl = null;
            reject(new Error(`Failed to load image preview for ${file.name}.`));
        };
    });
}

async function renderConvertedTiffPreview(file, displayArea) {
    if (currentPreviewUrl) URL.revokeObjectURL(currentPreviewUrl);
    const formData = new FormData(); formData.append('tiff_file', file);
    try {
        const response = await fetch('/api/preview_tiff', { method: 'POST', body: formData });
        if (!response.ok) {
            const eRes = await response.json().catch(() => ({error:`HTTP error ${response.status}`}));
            throw new Error(eRes.error || `Failed to convert TIFF: ${response.statusText}`);
        }
        const result = await response.json();
        if (result.status === 'success' && result.pages_data && result.pages_data.length > 0) {
            const dWidth = displayArea.clientWidth * 0.95;
            result.pages_data.forEach((base64Data) => {
                const img = document.createElement('img');
                img.style.cssText = `max-width:${dWidth}px;display:block;margin:5px auto 10px auto;border:1px solid #ccc;`;
                img.src = `data:image/${result.format};base64,${base64Data}`;
                img.onerror = () => console.error(`Error loading converted TIFF page image for ${file.name}`); // Keep critical errors
                displayArea.appendChild(img);
            });
            return Promise.resolve();
        } else if (result.pages_data && result.pages_data.length === 0) throw new Error('TIFF conversion returned no pages.');
        else throw new Error(result.error || 'TIFF conversion failed on server.');
    } catch (error) { throw new Error(`Preview failed for ${file.name}: ${error.message}`); }
}

async function displayPreview(file) {
    previewArea = document.getElementById('input-preview-area');
    if (!previewArea) { console.error("displayPreview: previewArea not found!"); return; } // Keep critical error
    previewArea.innerHTML = '';
    if (!document.getElementById('preview-render-error-dynamic')) {
        previewErrorMsgElement = document.createElement('p');
        previewErrorMsgElement.id = 'preview-render-error-dynamic';
        previewErrorMsgElement.className = 'ocr-status-message ocr-status-error';
        previewErrorMsgElement.style.display = 'none';
        previewArea.appendChild(previewErrorMsgElement);
    } else previewErrorMsgElement = document.getElementById('preview-render-error-dynamic');
    previewErrorMsgElement.style.display = 'none';

    if (!file) {
        previewArea.innerHTML = '<p id="preview-placeholder" class="ocr-status-message" style="color:#ccc;">Upload file for preview</p>';
        return;
    }
    const loadingP = document.createElement('p');
    loadingP.id = 'preview-loading-placeholder'; loadingP.className = 'ocr-status-message ocr-status-processing';
    loadingP.textContent = 'Loading preview...'; previewArea.appendChild(loadingP);

    if (!isFileTypeAllowed(file)) {
        previewArea.innerHTML = '';
        previewErrorMsgElement.textContent = `Unsupported file type (${file.type || file.name.split('.').pop()}).`;
        previewErrorMsgElement.style.display = 'block'; return;
    }
    try {
        const ext = file.name.split('.').pop().toLowerCase(); previewArea.innerHTML = '';
        if (file.type==='application/pdf' || ext==='pdf') await renderPdfPreview(file, previewArea);
        else if (file.type==='image/tiff' || ext==='tif' || ext==='tiff') await renderConvertedTiffPreview(file, previewArea);
        else await renderImagePreview(file, previewArea);
    } catch (error) {
        previewArea.innerHTML = '';
        previewErrorMsgElement.textContent = error.message || "Unknown preview error.";
        previewErrorMsgElement.style.display = 'block';
    }
}

function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return String(unsafe);
    return unsafe.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
}

document.addEventListener('DOMContentLoaded', () => {
    previewArea = document.getElementById('input-preview-area');
    const ocrOutputArea = document.getElementById('ocr-output-area');
    const ocrForm = document.getElementById('ocr-form');
    const runOcrButton = document.getElementById('run-ocr-button');
    const previewToggleCheckbox = document.getElementById('ocr-render-toggle-checkbox');
    const outputFormatSelect = document.getElementById('output-format-select');
    const previewIcon = document.getElementById('preview-icon');
    const dropZone = document.querySelector('.file-drop-zone');
    const fileInput = document.getElementById('input-file');
    const dropZoneText = dropZone ? dropZone.querySelector('.drop-zone-text') : null;
    const vlmApiSelect = document.getElementById('vlm-api-select');
    const ocrToggleContainer = document.getElementById('ocr-toggle-container');
    const outputHeader = document.getElementById('output-header');
    const copyOcrButton = document.getElementById('copy-ocr-text');

    const conditionalOptionsDivs = {
        'openai_compatible': document.getElementById('openai-compatible-options'),
        'openai': document.getElementById('openai-options'),
        'azure_openai': document.getElementById('azure-openai-options'),
        'ollama': document.getElementById('ollama-options')
    };

    if (typeof pdfjsLib === 'undefined') {
        console.error("DOMContentLoaded: PDF.js (pdfjsLib) not loaded. PDF previews will fail."); // Keep critical error
    } else {
        try {
            pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.6.347/pdf.worker.min.js';
        } catch (e) {
            console.error("DOMContentLoaded: Error configuring PDF.js worker:", e); // Keep critical error
        }
    }
    if (typeof marked === 'undefined') {
        console.warn("DOMContentLoaded: Marked.js not loaded. Markdown preview will fallback to plain text."); // Keep important warning
    }

    if (dropZone && fileInput && dropZoneText) {
        ['dragenter','dragover','dragleave','drop'].forEach(evName=>dropZone.addEventListener(evName,(e)=>{e.preventDefault();e.stopPropagation();},false));
        ['dragenter','dragover'].forEach(evName=>dropZone.addEventListener(evName,()=>dropZone.classList.add('drag-over')));
        ['dragleave','drop'].forEach(evName=>dropZone.addEventListener(evName,()=>dropZone.classList.remove('drag-over')));
        dropZone.addEventListener('drop',(event)=>{
            let f=null;
            if(event.dataTransfer.files.length>0){
                const dF=event.dataTransfer.files[0];
                if(isFileTypeAllowed(dF)){
                    fileInput.files=event.dataTransfer.files;f=dF;
                    dropZoneText.textContent=`Selected: ${f.name}`;
                } else {
                    dropZoneText.textContent='Unsupported type.';fileInput.value='';
                }
            } else {
                dropZoneText.textContent='Drag & drop file';fileInput.value='';
            }
            displayPreview(f);
        });
        fileInput.addEventListener('change',()=>{
            let f=null;
            if(fileInput.files.length>0){
                f=fileInput.files[0];
                dropZoneText.textContent=`Selected: ${f.name}`;
            } else {
                dropZoneText.textContent='Drag & drop file';
            }
            displayPreview(f);
        });
    }

    if (vlmApiSelect) {
        vlmApiSelect.addEventListener('change',(event)=>{
            const selApi=event.target.value;
            Object.values(conditionalOptionsDivs).forEach(div=>{if(div)div.style.display='none';});
            if(conditionalOptionsDivs[selApi])conditionalOptionsDivs[selApi].style.display='block';
        });
        vlmApiSelect.dispatchEvent(new Event('change'));
    }

    function updatePreviewIcon(format) {
        if(!previewIcon)return;
        let iC='fa-markdown',iT='Markdown Preview',iL='fab';
        if(format==='html'){iC='fa-code';iT='HTML Preview';iL='fas';}
        else if(format==='text'){iC='fa-file-alt';iT='Text Preview';iL='fas';}
        previewIcon.className=`${iL} ${iC}`;previewIcon.title=iT;
    }

    if (outputFormatSelect) {
        outputFormatSelect.addEventListener('change',(event)=>{
            currentOutputFormat=event.target.value.toLowerCase();
            updatePreviewIcon(currentOutputFormat);
            if(ocrRawText.trim() && isPreviewMode) renderFinalOutput();
        });
        currentOutputFormat=outputFormatSelect.value.toLowerCase();
        updatePreviewIcon(currentOutputFormat);
    }

    function setOcrStatusMessage(message,type='info') {
        if(!ocrOutputArea)return;
        let cN='ocr-status-message';
        if(type==='error')cN+=' ocr-status-error';
        else if(type==='processing')cN+=' ocr-status-processing';
        ocrOutputArea.innerHTML=`<p class="${cN}">${escapeHtml(message).replace(/\n/g,'<br>')}</p>`;
    }

    if (ocrOutputArea && (!ocrOutputArea.innerHTML.trim() || ocrOutputArea.querySelector('#preview-placeholder'))) {
        setOcrStatusMessage('OCR results appear here.','info');
    }

    function getCurrentPageDivForLiveStream() {
        if (pageContentHosts[pageCounter]) {
            return pageContentHosts[pageCounter];
        }

        const pageDivWrapperId = `ocr-live-page-wrapper-${pageCounter}`;
        let pageDivWrapper = document.getElementById(pageDivWrapperId);
        if (!pageDivWrapper) {
            pageDivWrapper = document.createElement('div');
            pageDivWrapper.id = pageDivWrapperId;
            pageDivWrapper.className = 'ocr-page-content-live-wrapper';
            ocrOutputArea.appendChild(pageDivWrapper);
        }

        let newContentHost;
        const commonMarginBottom = "10px";

        if (isPreviewMode) {
            if (currentOutputFormat === 'markdown') {
                newContentHost = document.createElement('div');
                newContentHost.className = 'ocr-markdown-content';
                newContentHost.style.padding = "10px"; newContentHost.style.backgroundColor = "#f8f9fa";
                newContentHost.style.border = "1px solid #dee2e6"; newContentHost.style.borderRadius = "3px";
                newContentHost.style.marginBottom = commonMarginBottom;
                pageDivWrapper.appendChild(newContentHost);
            } else if (currentOutputFormat === 'text') {
                newContentHost = document.createElement('pre');
                newContentHost.className = 'ocr-plaintext-content';
                newContentHost.style.marginBottom = commonMarginBottom;
                pageDivWrapper.appendChild(newContentHost);
            } else if (currentOutputFormat === 'html') {
                const shadowHostId = `ocr-live-page-shadowhost-${pageCounter}`;
                const shadowHost = document.createElement('div');
                shadowHost.id = shadowHostId; shadowHost.className = 'ocr-page-content-shadow-host';
                shadowHost.style.marginBottom = commonMarginBottom;
                try {
                    const shadow = shadowHost.attachShadow({ mode: 'open' });
                    const style = document.createElement('style');
                    style.textContent = `:host{display:block;background-color:#f8f9fa;padding:10px;font-family:sans-serif;color:#212529}body{margin:0;background-color:inherit;color:inherit}a{color:#0056b3}a:hover{color:#003d80}hr.page-delimiter-hr{border:0;height:1px;background-color:#ced4da;margin:25px 5px;}`;
                    shadow.appendChild(style); newContentHost = shadow;
                } catch (e) {
                    console.error(`Error creating shadow DOM for HTML, using fallback <pre> for page ${pageCounter}.`, e); // Keep error
                    const preFall = document.createElement('pre'); preFall.style.cssText='max-height:200px;overflow-y:auto;border:1px solid #ccc;padding:5px;';
                    shadowHost.appendChild(preFall); newContentHost=preFall;
                }
                pageDivWrapper.appendChild(shadowHost);
            } else {
                newContentHost = pageDivWrapper;
            }
        } else { // Raw text mode
            newContentHost = document.createElement('pre');
            newContentHost.className = 'ocr-rawtext-content';
            newContentHost.style.marginBottom = commonMarginBottom;
            pageDivWrapper.appendChild(newContentHost);
        }
        pageContentHosts[pageCounter] = newContentHost;
        return newContentHost;
    }


    if (ocrForm && ocrOutputArea && runOcrButton) {
        ocrForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            pageCounter = 0;
            ocrRawText = '';
            pageContentsArray = [];
            pageContentHosts = {}; // Reset persistent hosts
            let currentPageRawOutput = '';

            const formData = new FormData(ocrForm);
            currentOutputFormat = formData.get('output_format').toLowerCase();
            updatePreviewIcon(currentOutputFormat);
            isPreviewMode = previewToggleCheckbox ? previewToggleCheckbox.checked : true;

            ocrOutputArea.innerHTML = '';
            setOcrStatusMessage('Processing, please wait...', 'processing');

            runOcrButton.disabled = true;
            if(ocrToggleContainer) ocrToggleContainer.style.display = 'none';
            if(outputHeader) outputHeader.style.display = 'none';

            let streamStarted = false;

            try {
                const response = await fetch('/api/run_ocr', { method: 'POST', body: formData });
                if (!response.ok) {
                    let eMsg = `HTTP error ${response.status}`;
                    try{ const eRes = await response.json(); eMsg = eRes.error || eMsg;} catch(_){}
                    throw new Error(eMsg);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";

                async function processNdjsonStream() {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            if(buffer.trim()){
                                try{const item=JSON.parse(buffer); handleStreamItem(item);}
                                catch(e){ console.error("Final buffer parse error",e,buffer); } // Keep critical error
                            }
                            buffer="";

                            if (currentPageRawOutput.trim()) {
                                let cleaned = currentPageRawOutput;
                                if (currentOutputFormat === 'markdown') cleaned = cleaned.replace(/^```markdown\s*?\n?/i, '').replace(/\n?```\s*$/i, '').trim();
                                else cleaned = cleaned.trim();
                                pageContentsArray.push(cleaned);
                            }
                            ocrRawText = pageContentsArray.join(lastReceivedDelimiter);
                            isPreviewMode = previewToggleCheckbox ? previewToggleCheckbox.checked : true;
                            renderFinalOutput();
                            if(ocrToggleContainer) ocrToggleContainer.style.display = 'flex';
                            if(outputHeader) outputHeader.style.display = 'flex';
                            break;
                        }

                        buffer += decoder.decode(value, {stream:true});
                        let lines = buffer.split('\n');
                        for(let i=0; i<lines.length-1; i++){
                            let line=lines[i].trim();
                            if(line){
                                if (!streamStarted) {
                                    ocrOutputArea.innerHTML = '';
                                    streamStarted = true;
                                }
                                try{ const item=JSON.parse(line); handleStreamItem(item); }
                                catch(e){ console.error("Line parse error",e,"Line content:",line); } // Keep critical error
                            }
                        }
                        buffer = lines[lines.length-1];
                        // requestAnimationFrame(() => {
                        //    if(ocrOutputArea.scrollHeight > ocrOutputArea.clientHeight) ocrOutputArea.scrollTop = ocrOutputArea.scrollHeight;
                        // });
                    }
                }

                function handleStreamItem(item) {
                    const liveContentHost = getCurrentPageDivForLiveStream();
                    if (!liveContentHost) { console.error("handleStreamItem: liveContentHost is null!"); return; } // Keep critical error

                    if (item.type === "ocr_chunk" && typeof item.data === 'string') {
                        currentPageRawOutput += item.data;
                        if (isPreviewMode) {
                            if (currentOutputFormat === 'markdown') {
                                let markdownToParseLive = currentPageRawOutput.replace(/```markdown/gi, '').replace(/```/g, '');
                                try {
                                    if (typeof marked !== 'undefined' && marked.parse) liveContentHost.innerHTML = marked.parse(markdownToParseLive);
                                    else { liveContentHost.textContent = markdownToParseLive; }
                                } catch (e) { console.error(`Live MD parse error for page ${pageCounter}:`, e); liveContentHost.textContent = markdownToParseLive; } // Keep critical error
                            } else if (currentOutputFormat === 'html') {
                                if (liveContentHost.nodeName === 'PRE') liveContentHost.textContent = currentPageRawOutput;
                                else if (liveContentHost.nodeType === Node.DOCUMENT_FRAGMENT_NODE) { // ShadowRoot
                                    const style = liveContentHost.querySelector('style'); liveContentHost.innerHTML = ''; if(style)liveContentHost.appendChild(style.cloneNode(true));
                                    const cDiv = document.createElement('div'); cDiv.innerHTML = currentPageRawOutput; while(cDiv.firstChild)liveContentHost.appendChild(cDiv.firstChild);
                                } else liveContentHost.textContent = currentPageRawOutput;
                            } else { // Plain text
                                liveContentHost.textContent = currentPageRawOutput;
                            }
                        } else { // Raw text mode
                            liveContentHost.textContent = currentPageRawOutput;
                        }
                    } else if (item.type === "page_delimiter" && item.data) {
                        let cleanedContent = currentPageRawOutput;
                        if (currentOutputFormat === 'markdown') cleanedContent = cleanedContent.replace(/^```markdown\s*?\n?/i,'').replace(/\n?```\s*$/i,'').trim();
                        else cleanedContent = cleanedContent.trim();
                        pageContentsArray.push(cleanedContent);
                        lastReceivedDelimiter = item.data;

                        const currentWrapper = document.getElementById(`ocr-live-page-wrapper-${pageCounter}`);
                        if(currentWrapper) {
                            const hr = document.createElement('hr'); hr.className='page-delimiter-hr';
                            currentWrapper.insertAdjacentElement('afterend', hr);
                        }
                        pageCounter++;
                        currentPageRawOutput = '';
                    } else if (item.type === "error" && item.data) {
                        console.error("Stream error reported:", item.data); // Keep critical error
                        const eP = document.createElement('p'); eP.className="ocr-status-error";eP.innerHTML=`Stream Error: ${escapeHtml(item.data)}`;
                        if(liveContentHost?.appendChild) liveContentHost.appendChild(eP); else ocrOutputArea.appendChild(eP);
                    }
                     // Auto-scroll ocrOutputArea to keep current content in view
                    if (ocrOutputArea.scrollHeight > ocrOutputArea.clientHeight) {
                        ocrOutputArea.scrollTop = ocrOutputArea.scrollHeight;
                    }
                }
                await processNdjsonStream();
            } catch (error) {
                setOcrStatusMessage(`Error: ${error.message}`, 'error');
                ocrRawText = ''; pageContentsArray = []; pageContentHosts = {};
                if(ocrToggleContainer) ocrToggleContainer.style.display = 'none';
                if(outputHeader) outputHeader.style.display = 'none';
                if(previewToggleCheckbox) { previewToggleCheckbox.checked = false; isPreviewMode = false; }
            } finally {
                runOcrButton.disabled = false;
            }
        });


        function renderFinalOutput() {
            if (!ocrOutputArea) { console.error("renderFinalOutput: ocrOutputArea not found!"); return; } // Keep critical error
            ocrOutputArea.innerHTML = '';

            if (pageContentsArray.length === 0 && ocrRawText.trim()) {
                pageContentsArray = [ocrRawText];
            } else if (pageContentsArray.length === 0 && !ocrRawText.trim()){
                setOcrStatusMessage('No content to display.', 'info'); return;
            }

            if (isPreviewMode) {
                if (currentOutputFormat === 'markdown') {
                    pageContentsArray.forEach((pageContent, index) => {
                        let mdHost = document.createElement('div');
                        mdHost.className = 'ocr-markdown-content ocr-page-content-rendered-wrapper';
                        try {
                            if (typeof marked !== 'undefined' && marked.parse) mdHost.innerHTML = marked.parse(pageContent);
                            else mdHost.textContent = pageContent;
                        }
                        catch (e) { console.error(`Error parsing markdown for page ${index}:`, e); mdHost.textContent = pageContent; } // Keep critical error
                        ocrOutputArea.appendChild(mdHost);
                        if (index < pageContentsArray.length - 1) {
                            const hr = document.createElement('hr'); hr.className = 'page-delimiter-hr'; ocrOutputArea.appendChild(hr);
                        }
                    });
                } else if (currentOutputFormat === 'html') {
                    if (pageContentsArray.length > 0) {
                        const combinedHtml = pageContentsArray.join(`<hr class='page-delimiter-hr page-delimiter-html-view'>`);
                        let wrapper = document.createElement('div'); wrapper.className = 'ocr-page-content-rendered-wrapper html-wrapper single-html-container';
                        const iframe = document.createElement('iframe'); iframe.style.width = '100%'; iframe.style.border = 'none';
                        const baseStyle = `<style>html,body{margin:0;padding:0;height:100%;overflow:auto;}body{font-family:sans-serif;color:#212529;background-color:#fff;padding:10px;}hr.page-delimiter-html-view{border:0;height:1px;background-color:#ced4da;margin:25px 5px;}</style>`;
                        iframe.srcdoc = baseStyle + combinedHtml;
                        iframe.onerror = () => {
                            console.error("Error loading iframe srcdoc."); // Keep critical error
                            wrapper.innerHTML = `<p class='ocr-status-error'>Error loading HTML content into preview.</p><pre>${escapeHtml(combinedHtml)}</pre>`;
                        };
                        wrapper.appendChild(iframe); ocrOutputArea.appendChild(wrapper);
                    } else {
                        setOcrStatusMessage('No HTML content to display.', 'info');
                    }
                } else { // Plain text
                    pageContentsArray.forEach((pageContent, index) => {
                        const pre = document.createElement('pre');
                        pre.className = 'ocr-plaintext-content ocr-page-content-rendered-wrapper';
                        pre.textContent = pageContent;
                        ocrOutputArea.appendChild(pre);
                        if (index < pageContentsArray.length - 1) {
                            const hr = document.createElement('hr'); hr.className = 'page-delimiter-hr'; ocrOutputArea.appendChild(hr);
                        }
                    });
                }
            } else { // Raw text mode
                const pre = document.createElement('pre'); pre.className = 'ocr-rawtext-content';
                pre.textContent = ocrRawText;
                ocrOutputArea.appendChild(pre);
            }
            if(ocrOutputArea.scrollHeight > ocrOutputArea.clientHeight) ocrOutputArea.scrollTop = 0;
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
                if (!textToCopy) {
                    copyOcrButton.title = 'Nothing to copy!';
                    setTimeout(() => { copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                    return;
                }
                navigator.clipboard.writeText(textToCopy)
                    .then(() => {
                        copyOcrButton.classList.add('copied'); copyOcrButton.title = 'Copied!';
                        setTimeout(() => { copyOcrButton.classList.remove('copied'); copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                    })
                    .catch(err => {
                        console.error("Copy failed:", err); // Keep critical error
                        copyOcrButton.title = 'Copy failed!';
                        setTimeout(() => { copyOcrButton.title = 'Copy Raw Text'; }, 1500);
                    });
            });
        }
    } else {
        console.error("DOMContentLoaded: Essential OCR form elements not found. OCR functionality will be disabled."); // Keep critical error
    }
}); // End of DOMContentLoaded

function isFileTypeAllowed(file) {
    if (!file) return false;
    if (ALLOWED_MIME_TYPES.includes(file.type)) return true;
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    if (ALLOWED_EXTENSIONS.includes(extension)) return true;
    return false;
}