(function () {
    'use strict';

    var cfg = window.OE_COPILOT_CONFIG || {};
    var card = document.getElementById('copilot-card');
    if (!card || !cfg.briefUrl) {
        return;
    }

    var statusEl = document.getElementById('copilot-status');
    var claimsEl = document.getElementById('copilot-claims');
    var missingEl = document.getElementById('copilot-missing');
    var refusalEl = null;
    var followupsEl = document.getElementById('copilot-followups');
    var askEl = document.getElementById('copilot-ask');
    var askForm = document.getElementById('copilot-ask-form');
    var askInput = document.getElementById('copilot-ask-input');
    var askBtn = document.getElementById('copilot-ask-btn');
    var feedbackEl = document.getElementById('copilot-feedback');
    var feedbackStatusEl = document.getElementById('copilot-feedback-status');
    var errorEl = document.getElementById('copilot-error');
    var traceEl = document.getElementById('copilot-trace-id');

    var lastTraceId = null;
    var lastPacketsSummary = [];
    var inFlight = false;

    // Last 3 turns of verified source IDs only (no model prose).
    window.OE_COPILOT_HISTORY = window.OE_COPILOT_HISTORY || [];

    function showError(msg) {
        statusEl.style.display = 'none';
        errorEl.style.display = 'block';
        errorEl.textContent = msg;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function ensureRefusalEl() {
        if (refusalEl) {
            return refusalEl;
        }
        refusalEl = document.createElement('div');
        refusalEl.className = 'copilot-refusal';
        refusalEl.id = 'copilot-refusal';
        refusalEl.style.display = 'none';
        if (claimsEl && claimsEl.parentNode) {
            claimsEl.parentNode.insertBefore(refusalEl, claimsEl);
        }
        return refusalEl;
    }

    function buildSourceChip(id) {
        var meta = (lastPacketsSummary || []).find(function (s) { return s.source_id === id; });
        var chip = document.createElement('span');
        chip.className = 'copilot-source-chip';
        chip.setAttribute('data-source-id', id);
        chip.setAttribute('role', 'button');
        chip.setAttribute('tabindex', '0');
        chip.textContent = id;
        chip.title = meta
            ? (meta.label + ' • ' + (meta.observed_at || 'unknown date') + ' • ' + (meta.freshness || ''))
            : id;
        chip.addEventListener('click', function (ev) {
            ev.stopPropagation();
            showPopover(chip, id);
        });
        chip.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                showPopover(chip, id);
            }
        });
        return chip;
    }

    var POPOVER_RECORD_PATHS = {
        'lists': '/interface/patient_file/summary/stats_full.php',
        'prescriptions': '/interface/patient_file/summary/pnotes_full.php',
        'lists_allergy': '/interface/patient_file/summary/stats_full.php',
        'procedure_result': '/interface/orders/orders_results.php',
        'procedure_order': '/interface/orders/orders_results.php',
        'immunizations': '/interface/patient_file/summary/immunizations.php'
    };

    function dismissPopover() {
        var existing = document.getElementById('copilot-popover');
        if (existing && existing.parentNode) {
            existing.parentNode.removeChild(existing);
        }
        document.removeEventListener('click', dismissPopover);
    }

    function showPopover(chipEl, sourceId) {
        dismissPopover();
        var meta = (lastPacketsSummary || []).find(function (s) { return s.source_id === sourceId; });
        var pop = document.createElement('div');
        pop.id = 'copilot-popover';
        pop.className = 'copilot-popover';

        var html = '';
        html += '<div class="copilot-popover-header"><strong>Source detail</strong></div>';
        html += '<dl class="copilot-popover-body">';
        html += '<dt>ID</dt><dd>' + escapeHtml(sourceId) + '</dd>';
        if (meta) {
            html += '<dt>Field</dt><dd>' + escapeHtml(meta.label || '') + '</dd>';
            html += '<dt>Table</dt><dd>' + escapeHtml(meta.source_table || '') + '</dd>';
            html += '<dt>Observed</dt><dd>' + escapeHtml(meta.observed_at || 'unknown') + '</dd>';
            html += '<dt>Freshness</dt><dd>' + escapeHtml(meta.freshness || 'unknown') + '</dd>';
        } else {
            html += '<dt>Detail</dt><dd>(packet metadata unavailable)</dd>';
        }
        html += '</dl>';

        var recordPath = meta && POPOVER_RECORD_PATHS[meta.source_table];
        if (recordPath) {
            html += '<div class="copilot-popover-footer">';
            html += '<a href="' + escapeHtml(recordPath) + '" target="_blank" rel="noopener">Open record</a>';
            html += '</div>';
        }
        pop.innerHTML = html;

        chipEl.parentNode.insertBefore(pop, chipEl.nextSibling);
        setTimeout(function () {
            document.addEventListener('click', dismissPopover);
        }, 0);
    }

    function renderRefusal(payload) {
        statusEl.style.display = 'none';
        var el = ensureRefusalEl();
        var refusals = (payload && payload.refusals) || ['Request declined.'];
        el.innerHTML = '<span class="copilot-refusal-pill">'
            + escapeHtml(refusals[0])
            + '</span>';
        el.style.display = 'block';

        // Keep prior brief intact below; do not wipe claimsEl/missingEl.
        followupsEl.style.display = 'block';
        askEl.style.display = 'block';
    }

    function renderClaims(payload) {
        statusEl.style.display = 'none';
        // Hide any prior refusal pill on a fresh successful turn.
        if (refusalEl) {
            refusalEl.style.display = 'none';
        }

        lastPacketsSummary = (payload && payload.packets_summary) || [];

        var claims = (payload && payload.claims) || [];
        if (!claims.length) {
            claimsEl.innerHTML = '<div class="text-muted">' + escapeHtml('No verified claims to show yet.') + '</div>';
        } else {
            claimsEl.innerHTML = '';
            claims.forEach(function (c) {
                var row = document.createElement('div');
                row.className = 'copilot-claim';

                var textSpan = document.createElement('span');
                textSpan.className = 'copilot-claim-text';
                textSpan.textContent = c.text;
                row.appendChild(textSpan);
                row.appendChild(document.createTextNode(' '));

                (c.source_ids || []).forEach(function (sid) {
                    row.appendChild(buildSourceChip(sid));
                    row.appendChild(document.createTextNode(' '));
                });

                if (c.caveat) {
                    var caveat = document.createElement('span');
                    caveat.className = 'copilot-claim-caveat';
                    caveat.textContent = '(' + c.caveat + ')';
                    row.appendChild(caveat);
                }
                claimsEl.appendChild(row);
            });
        }
        claimsEl.style.display = 'block';

        var missing = (payload && payload.missing_data) || [];
        if (missing.length) {
            missingEl.innerHTML = '<strong>Missing:</strong> ' + missing.map(escapeHtml).join('; ');
            missingEl.style.display = 'block';
        } else {
            missingEl.style.display = 'none';
            missingEl.innerHTML = '';
        }

        // Bookkeeping for prior_turn_source_ids forwarding.
        var verifiedIds = [];
        claims.forEach(function (c) {
            (c.source_ids || []).forEach(function (sid) { verifiedIds.push(sid); });
        });
        window.OE_COPILOT_HISTORY.push({ trace_id: payload && payload.trace_id, source_ids: verifiedIds });
        if (window.OE_COPILOT_HISTORY.length > 3) {
            window.OE_COPILOT_HISTORY.shift();
        }

        followupsEl.style.display = 'block';
        askEl.style.display = 'block';
        feedbackEl.style.display = 'block';
        feedbackStatusEl.textContent = '';
    }

    function priorTurnIds() {
        var seen = {};
        var out = [];
        for (var i = 0; i < window.OE_COPILOT_HISTORY.length; i++) {
            var ids = window.OE_COPILOT_HISTORY[i].source_ids || [];
            for (var j = 0; j < ids.length; j++) {
                var id = ids[j];
                if (!seen[id]) {
                    seen[id] = true;
                    out.push(id);
                    if (out.length >= 20) {
                        return out;
                    }
                }
            }
        }
        return out;
    }

    function fetchBrief(useCase, question) {
        if (inFlight) {
            return;
        }
        inFlight = true;
        statusEl.style.display = 'block';
        errorEl.style.display = 'none';
        if (askBtn) { askBtn.disabled = true; }
        if (askInput) { askInput.disabled = true; }

        var formData = new FormData();
        formData.append('csrf_token_form', cfg.csrfToken);
        formData.append('use_case', useCase || 'pre_room_brief');
        if (question) {
            formData.append('question', question);
        }
        var prior = priorTurnIds();
        if (prior.length) {
            formData.append('prior_turn_source_ids', JSON.stringify(prior));
        }

        fetch(cfg.briefUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        }).then(function (res) {
            return res.json().then(function (json) { return { status: res.status, body: json }; });
        }).then(function (resp) {
            if (resp.body && resp.body.trace_id) {
                traceEl.textContent = 'trace: ' + resp.body.trace_id;
                lastTraceId = resp.body.trace_id;
            }
            if (resp.status >= 400 || (resp.body && resp.body.error)) {
                showError((resp.body && resp.body.error) || 'Co-Pilot error: HTTP ' + resp.status);
                return;
            }
            if (resp.body && resp.body.answer_type === 'refusal') {
                renderRefusal(resp.body);
                return;
            }
            renderClaims(resp.body);
        }).catch(function (err) {
            showError('Co-Pilot fetch failed: ' + (err && err.message ? err.message : 'unknown'));
        }).finally(function () {
            inFlight = false;
            if (askBtn) { askBtn.disabled = false; }
            if (askInput) {
                askInput.disabled = false;
                askInput.value = '';
                askInput.style.height = '';
            }
        });
    }

    function sendFeedback(verdict, btn) {
        if (!lastTraceId || !cfg.feedbackUrl) {
            return;
        }
        var formData = new FormData();
        formData.append('csrf_token_form', cfg.csrfToken);
        formData.append('trace_id', lastTraceId);
        formData.append('verdict', verdict);

        document.querySelectorAll('.copilot-feedback-btn').forEach(function (b) {
            b.disabled = true;
        });
        feedbackStatusEl.textContent = 'Sending feedback…';

        fetch(cfg.feedbackUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        }).then(function (res) {
            return res.json().then(function (json) { return { status: res.status, body: json }; });
        }).then(function (resp) {
            if (resp.status >= 400 || (resp.body && resp.body.error)) {
                feedbackStatusEl.textContent = 'Feedback failed.';
                document.querySelectorAll('.copilot-feedback-btn').forEach(function (b) {
                    b.disabled = false;
                });
                return;
            }
            feedbackStatusEl.textContent = 'Thanks — feedback recorded.';
            if (btn) {
                btn.classList.add('active');
            }
        }).catch(function () {
            feedbackStatusEl.textContent = 'Feedback failed.';
            document.querySelectorAll('.copilot-feedback-btn').forEach(function (b) {
                b.disabled = false;
            });
        });
    }

    document.querySelectorAll('.copilot-followup-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            fetchBrief(btn.getAttribute('data-followup'));
        });
    });

    document.querySelectorAll('.copilot-feedback-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            sendFeedback(btn.getAttribute('data-verdict'), btn);
        });
    });

    if (askForm && askInput) {
        askForm.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var q = (askInput.value || '').trim();
            if (q) {
                fetchBrief('free_text_followup', q);
            }
        });
        askInput.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' && !ev.shiftKey) {
                ev.preventDefault();
                var q = (askInput.value || '').trim();
                if (q) {
                    fetchBrief('free_text_followup', q);
                }
            }
        });
        // Auto-grow up to 3 rows.
        askInput.addEventListener('input', function () {
            askInput.style.height = '';
            var maxH = 3 * 22;
            askInput.style.height = Math.min(askInput.scrollHeight, maxH) + 'px';
        });
    }

    fetchBrief('pre_room_brief');

    // -----------------------------------------------------------------------
    // Wk2 Workstream A: PDF.js bbox overlay (Plan §6, AgDR-0039/0040)
    //
    // When the user clicks a source chip whose packet carries bbox + page_index
    // data, this overlay renders the PDF page and draws a highlight rectangle
    // over the cited region.
    //
    // OE_COPILOT_CONFIG.pdfWorkerSrc must point to pdf.worker.min.js.
    // The overlay is destroyed on the next chip click or outside click.
    // -----------------------------------------------------------------------

    var bboxOverlayEl = null;

    function destroyBboxOverlay() {
        if (bboxOverlayEl && bboxOverlayEl.parentNode) {
            bboxOverlayEl.parentNode.removeChild(bboxOverlayEl);
        }
        bboxOverlayEl = null;
    }

    function showBboxOverlay(pdfUrl, pageIndex, bbox) {
        destroyBboxOverlay();

        if (!window.pdfjsLib) {
            return;
        }
        if (cfg.pdfWorkerSrc) {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.pdfWorkerSrc;
        }

        var overlay = document.createElement('div');
        overlay.className = 'copilot-bbox-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-label', 'Citation location in document');

        var closeBtn = document.createElement('button');
        closeBtn.className = 'copilot-bbox-close';
        closeBtn.textContent = '×';
        closeBtn.setAttribute('aria-label', 'Close citation overlay');
        closeBtn.addEventListener('click', destroyBboxOverlay);
        overlay.appendChild(closeBtn);

        var canvasWrapper = document.createElement('div');
        canvasWrapper.className = 'copilot-bbox-canvas-wrapper';
        var canvas = document.createElement('canvas');
        canvasWrapper.appendChild(canvas);
        overlay.appendChild(canvasWrapper);

        document.body.appendChild(overlay);
        bboxOverlayEl = overlay;

        var loadingTask = window.pdfjsLib.getDocument(pdfUrl);
        loadingTask.promise.then(function (pdfDoc) {
            return pdfDoc.getPage(pageIndex + 1);
        }).then(function (page) {
            var viewport = page.getViewport({ scale: 1.5 });
            canvas.width = viewport.width;
            canvas.height = viewport.height;

            var ctx = canvas.getContext('2d');
            page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function () {
                if (!bbox || bbox.length !== 4) {
                    return;
                }
                var x0 = bbox[0], y0 = bbox[1], x1 = bbox[2], y1 = bbox[3];
                var rx = x0 * viewport.width;
                var ry = y0 * viewport.height;
                var rw = (x1 - x0) * viewport.width;
                var rh = (y1 - y0) * viewport.height;

                ctx.save();
                ctx.strokeStyle = '#e05c00';
                ctx.lineWidth = 2;
                ctx.fillStyle = 'rgba(224, 92, 0, 0.15)';
                ctx.fillRect(rx, ry, rw, rh);
                ctx.strokeRect(rx, ry, rw, rh);
                ctx.restore();
            });
        }).catch(function () {
            destroyBboxOverlay();
        });

        overlay.addEventListener('click', function (ev) {
            if (ev.target === overlay) {
                destroyBboxOverlay();
            }
        });
    }

    // Augment source chip clicks: if the packet has bbox + page_index,
    // show the overlay in addition to the popover.
    var _origShowPopover = showPopover;
    showPopover = function (chipEl, sourceId) {
        _origShowPopover(chipEl, sourceId);
        var meta = (lastPacketsSummary || []).find(function (s) { return s.source_id === sourceId; });
        if (
            meta &&
            meta.bbox && meta.bbox.length === 4 &&
            meta.page_index !== undefined && meta.page_index !== null &&
            meta.doc_url && cfg.showBboxOverlay !== false
        ) {
            showBboxOverlay(meta.doc_url, meta.page_index, meta.bbox);
        }
    };

    // -----------------------------------------------------------------------
    // Wk2 Workstream A: document upload form handling
    // -----------------------------------------------------------------------

    var uploadForm = document.getElementById('copilot-upload-form');
    var uploadStatus = document.getElementById('copilot-upload-status');

    function showUploadStatus(msg, isError) {
        if (!uploadStatus) { return; }
        uploadStatus.textContent = msg;
        uploadStatus.className = 'copilot-upload-status' + (isError ? ' copilot-upload-error' : '');
        uploadStatus.style.display = 'block';
    }

    if (uploadForm && cfg.uploadLabUrl && cfg.uploadIntakeUrl) {
        uploadForm.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var fileInput = uploadForm.querySelector('input[type="file"]');
            var docTypeSelect = uploadForm.querySelector('select[name="doc_type"]');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                showUploadStatus('Please select a file.', true);
                return;
            }
            var file = fileInput.files[0];
            var docType = docTypeSelect ? docTypeSelect.value : 'lab_pdf';
            var url = docType === 'intake_form' ? cfg.uploadIntakeUrl : cfg.uploadLabUrl;

            var formData = new FormData();
            formData.append('file', file, file.name);

            showUploadStatus('Uploading…', false);
            uploadForm.querySelector('button[type="submit"]').disabled = true;

            fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                body: formData,
            }).then(function (res) {
                return res.json().then(function (json) { return { status: res.status, body: json }; });
            }).then(function (resp) {
                uploadForm.querySelector('button[type="submit"]').disabled = false;
                if (resp.status >= 400) {
                    showUploadStatus('Upload failed: ' + escapeHtml(JSON.stringify(resp.body.detail || resp.body)), true);
                    return;
                }
                var count = (resp.body && resp.body.extracted_field_count) || 0;
                showUploadStatus('Extracted ' + count + ' field(s). Refreshing brief…', false);
                setTimeout(function () { fetchBrief('pre_room_brief'); }, 1200);
            }).catch(function () {
                uploadForm.querySelector('button[type="submit"]').disabled = false;
                showUploadStatus('Upload failed (network error).', true);
            });
        });
    }
})();
