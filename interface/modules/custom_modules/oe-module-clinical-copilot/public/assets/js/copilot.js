(function () {
    'use strict';

    // Plan_wk2_Claude_Next06 (refinement 2026-05-13) — relocate the
    // combined Co-Pilot + Upload-Docs row above the Allergies / Medical
    // Problems / Medications three-card row. The event hook in
    // src/Events/PatientDemographics/RenderEvent.php fires
    // EVENT_SECTION_LIST_RENDER_BEFORE inside the section-list iterator,
    // so the row's initial DOM position is below the three-card row;
    // this hoists it to the user's preferred position without editing
    // core OpenEMR demographics.php.
    function relocateTopRow() {
        var ourRow = document.getElementById('copilot-top-row');
        if (!ourRow) { return; }
        // Find the row that contains the Allergies / Medical Problems /
        // Medications cards. The canonical demographics.php structure is
        // <div class="main mb-1"><div class="row"> ... 3 cards ... </div>
        // — the FIRST .row inside .main is reliably the three-card row.
        var mainContainer = document.querySelector('.main.mb-1, div.main');
        if (!mainContainer) { return; }
        var threeCardRow = mainContainer.querySelector(':scope > .row');
        if (!threeCardRow || threeCardRow === ourRow) { return; }
        // Idempotent: already-relocated rows stay put.
        if (ourRow.previousElementSibling === null && ourRow.parentNode === mainContainer) {
            return;
        }
        mainContainer.insertBefore(ourRow, threeCardRow);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', relocateTopRow);
    } else {
        relocateTopRow();
    }

    var cfg = window.OE_COPILOT_CONFIG || {};
    var card = document.getElementById('copilot-card');

    // Plan_wk2_Claude_Next07_v2 §B.1 fix (2026-05-13T23:55Z): the upload-form
    // handler must run on surfaces that do NOT have a #copilot-card — i.e.
    // the new pre-patient intake_upload.php page. Before this fix the IIFE
    // early-returned when card was missing, silently disabling the upload
    // handler on the pre-patient page so submits did nothing.
    //
    // Function declarations (fetchBrief, makeShowUploadStatus, escapeHtml,
    // fetchMedicationReconciliation) are hoisted to the top of this IIFE
    // scope, so they are callable here even though they are defined below
    // the early-return. The card-conditional calls (fetchBrief +
    // fetchMedicationReconciliation) are guarded inside the handler so the
    // pre-patient surface does not try to refresh a brief that does not
    // exist.
    initUploadHandlers();

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

        // AgDR-0065 — for DocumentFact packets that have been written to the
        // native lab chain, render dual links: OpenEMR Lab Review (clinician
        // surface) and FHIR Observation (machine-readable surface).
        var footerLinks = [];
        if (meta && meta.openemr_lab_review_url) {
            footerLinks.push(
                '<a href="' + escapeHtml(meta.openemr_lab_review_url)
                + '" target="_blank" rel="noopener">View in OpenEMR Lab Review</a>'
            );
        }
        if (meta && meta.fhir_observation_url) {
            footerLinks.push(
                '<a href="' + escapeHtml(meta.fhir_observation_url)
                + '" target="_blank" rel="noopener">View as FHIR Observation</a>'
            );
        }
        var recordPath = meta && POPOVER_RECORD_PATHS[meta.source_table];
        if (recordPath && footerLinks.length === 0) {
            footerLinks.push(
                '<a href="' + escapeHtml(recordPath)
                + '" target="_blank" rel="noopener">Open record</a>'
            );
        }
        if (footerLinks.length > 0) {
            html += '<div class="copilot-popover-footer">' + footerLinks.join(' · ') + '</div>';
        }
        pop.innerHTML = html;

        chipEl.parentNode.insertBefore(pop, chipEl.nextSibling);
        setTimeout(function () {
            document.addEventListener('click', dismissPopover);
        }, 0);

        // AgDR-0072 / Phase 6.2 — clicking a chip pins its source in the
        // persistent right-side preview drawer (replaces the old one-shot
        // bbox modal pattern). The drawer UPDATES in place rather than
        // stacking modals.
        if (
            meta &&
            meta.doc_url &&
            meta.page_index !== undefined && meta.page_index !== null &&
            cfg.showSourcePreview !== false
        ) {
            openOrUpdateDrawer(meta);
        }
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
    // Wk2 Phase 6.2 / AgDR-0072: PDF.js click-to-source preview drawer.
    //
    // Replaces the previous one-shot bbox-overlay modal pattern with a
    // persistent right-side drawer that PINS the most-recently-clicked
    // source. Clicking another chip UPDATES the drawer rather than stacking
    // modals or reopening. Layers:
    //
    //   1. Persistent right-side panel (single drawer DOM, lazy-created,
    //      reused thereafter; tracked by currentDrawerSource).
    //   2. Page-level navigation (Page Up/Down at drawer bottom for
    //      multi-page lab reports such as a CMP).
    //   3. Source metadata header (source_type, source_id, page_or_section,
    //      quote_or_value, "View in OpenEMR Lab Review", "View as FHIR
    //      Observation" links from chip metadata).
    //   4. Quote-not-found graceful state — when bbox is null, render the
    //      page at 1.5x scale with a banner explaining no text layer is
    //      available.
    //
    // The old class names (.copilot-bbox-overlay, .copilot-bbox-canvas-
    // wrapper, .copilot-bbox-close) are SUPERSEDED by .copilot-preview-
    // drawer-* and were removed from copilot.css in the same change.
    // -----------------------------------------------------------------------

    var currentDrawerSource = null;
    var drawerEl = null;
    var drawerCanvas = null;
    var drawerHeaderEl = null;
    var drawerBannerEl = null;
    var drawerNavEl = null;
    var drawerPrevBtn = null;
    var drawerNextBtn = null;
    var drawerPageLabel = null;
    var drawerPdfDoc = null;
    var drawerPdfUrl = null;
    var drawerNumPages = 0;
    var currentPageIndex = 0;
    var currentBbox = null;
    var currentMeta = null;

    function buildDrawer() {
        if (drawerEl) {
            return drawerEl;
        }

        drawerEl = document.createElement('div');
        // Use setAttribute so the literal class="copilot-preview-drawer"
        // appears in source (smoke-test contract: copilot_drawer_smoke.php
        // pins this exact substring to keep JS and CSS class names in sync).
        drawerEl.setAttribute('class', 'copilot-preview-drawer hidden');
        drawerEl.setAttribute('role', 'complementary');
        drawerEl.setAttribute('aria-label', 'Source preview drawer');

        var closeBtn = document.createElement('button');
        closeBtn.className = 'copilot-preview-drawer-close';
        closeBtn.type = 'button';
        closeBtn.textContent = '×';
        closeBtn.setAttribute('aria-label', 'Close source preview');
        closeBtn.addEventListener('click', closeDrawer);
        drawerEl.appendChild(closeBtn);

        drawerHeaderEl = document.createElement('div');
        drawerHeaderEl.className = 'copilot-preview-drawer-header';
        drawerEl.appendChild(drawerHeaderEl);

        drawerBannerEl = document.createElement('div');
        drawerBannerEl.className = 'copilot-preview-drawer-banner';
        drawerBannerEl.style.display = 'none';
        drawerEl.appendChild(drawerBannerEl);

        var canvasWrapper = document.createElement('div');
        canvasWrapper.className = 'copilot-preview-drawer-canvas-wrapper';
        drawerCanvas = document.createElement('canvas');
        canvasWrapper.appendChild(drawerCanvas);
        drawerEl.appendChild(canvasWrapper);

        drawerNavEl = document.createElement('div');
        drawerNavEl.className = 'copilot-preview-drawer-nav';

        drawerPrevBtn = document.createElement('button');
        drawerPrevBtn.type = 'button';
        drawerPrevBtn.className = 'copilot-preview-drawer-nav-btn';
        drawerPrevBtn.textContent = 'Page Up';
        drawerPrevBtn.setAttribute('aria-label', 'Previous page');
        drawerPrevBtn.addEventListener('click', function () {
            if (currentPageIndex > 0) {
                currentPageIndex -= 1;
                // Bbox only applies to the original cited page — clear it
                // when the user navigates to a neighbouring page.
                renderDrawerPage(null);
            }
        });
        drawerNavEl.appendChild(drawerPrevBtn);

        drawerPageLabel = document.createElement('span');
        drawerPageLabel.className = 'copilot-preview-drawer-nav-label';
        drawerNavEl.appendChild(drawerPageLabel);

        drawerNextBtn = document.createElement('button');
        drawerNextBtn.type = 'button';
        drawerNextBtn.className = 'copilot-preview-drawer-nav-btn';
        drawerNextBtn.textContent = 'Page Down';
        drawerNextBtn.setAttribute('aria-label', 'Next page');
        drawerNextBtn.addEventListener('click', function () {
            if (currentPageIndex < drawerNumPages - 1) {
                currentPageIndex += 1;
                renderDrawerPage(null);
            }
        });
        drawerNavEl.appendChild(drawerNextBtn);

        drawerEl.appendChild(drawerNavEl);

        document.body.appendChild(drawerEl);
        return drawerEl;
    }

    function renderDrawerHeader(meta) {
        if (!drawerHeaderEl) { return; }
        var rows = [];
        rows.push('<div class="copilot-preview-drawer-title">Source preview</div>');
        rows.push('<dl class="copilot-preview-drawer-meta">');
        if (meta.source_type) {
            rows.push('<dt>Type</dt><dd>' + escapeHtml(meta.source_type) + '</dd>');
        }
        if (meta.source_id) {
            rows.push('<dt>ID</dt><dd>' + escapeHtml(meta.source_id) + '</dd>');
        }
        if (meta.page_or_section) {
            rows.push('<dt>Section</dt><dd>' + escapeHtml(meta.page_or_section) + '</dd>');
        }
        if (meta.quote_or_value) {
            rows.push('<dt>Quote</dt><dd>' + escapeHtml(meta.quote_or_value) + '</dd>');
        }
        rows.push('</dl>');

        var links = [];
        if (meta.openemr_lab_review_url) {
            links.push(
                '<a href="' + escapeHtml(meta.openemr_lab_review_url)
                + '" target="_blank" rel="noopener">View in OpenEMR Lab Review</a>'
            );
        }
        if (meta.fhir_observation_url) {
            links.push(
                '<a href="' + escapeHtml(meta.fhir_observation_url)
                + '" target="_blank" rel="noopener">View as FHIR Observation</a>'
            );
        }
        if (links.length > 0) {
            rows.push('<div class="copilot-preview-drawer-links">' + links.join(' · ') + '</div>');
        }

        drawerHeaderEl.innerHTML = rows.join('');
    }

    function updateDrawerNavState() {
        if (!drawerNavEl) { return; }
        if (drawerNumPages <= 1) {
            drawerNavEl.style.display = 'none';
            return;
        }
        drawerNavEl.style.display = 'flex';
        drawerPrevBtn.disabled = currentPageIndex <= 0;
        drawerNextBtn.disabled = currentPageIndex >= drawerNumPages - 1;
        drawerPageLabel.textContent = 'Page ' + (currentPageIndex + 1) + ' of ' + drawerNumPages;
    }

    function renderDrawerPage(bboxForThisPage) {
        if (!drawerPdfDoc || !drawerCanvas) { return; }
        // Quote-not-found graceful state: when bbox is unavailable, render
        // the full page slightly larger (1.5x) so the clinician can scan
        // it visually for the cited quote.
        var scale = (bboxForThisPage && bboxForThisPage.length === 4) ? 1.0 : 1.5;

        drawerPdfDoc.getPage(currentPageIndex + 1).then(function (page) {
            var viewport = page.getViewport({ scale: scale });
            drawerCanvas.width = viewport.width;
            drawerCanvas.height = viewport.height;
            var ctx = drawerCanvas.getContext('2d');
            page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function () {
                if (!bboxForThisPage || bboxForThisPage.length !== 4) {
                    return;
                }
                var x0 = bboxForThisPage[0], y0 = bboxForThisPage[1];
                var x1 = bboxForThisPage[2], y1 = bboxForThisPage[3];
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
        });

        updateDrawerNavState();
    }

    function renderDrawerBanner(meta) {
        if (!drawerBannerEl) { return; }
        var hasBbox = meta.bbox && meta.bbox.length === 4;
        var hasPage = meta.page_index !== undefined && meta.page_index !== null;
        if (!hasBbox && hasPage) {
            var quote = meta.quote_or_value || '';
            drawerBannerEl.innerHTML = 'This document has no text layer; bbox unavailable.'
                + ' Quote: \'' + escapeHtml(quote) + '\'.';
            drawerBannerEl.style.display = 'block';
        } else {
            drawerBannerEl.innerHTML = '';
            drawerBannerEl.style.display = 'none';
        }
    }

    function openOrUpdateDrawer(meta) {
        if (!window.pdfjsLib || !meta || !meta.doc_url) {
            return;
        }
        if (cfg.pdfWorkerSrc) {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.pdfWorkerSrc;
        }

        buildDrawer();
        drawerEl.classList.remove('hidden');
        currentDrawerSource = meta.source_id || null;
        currentMeta = meta;
        currentPageIndex = (meta.page_index !== undefined && meta.page_index !== null)
            ? meta.page_index : 0;
        currentBbox = (meta.bbox && meta.bbox.length === 4) ? meta.bbox : null;

        renderDrawerHeader(meta);
        renderDrawerBanner(meta);

        // Reuse the loaded PDF document when the chip points at the same
        // doc_url so we don't re-fetch on every chip click within a report.
        if (drawerPdfUrl === meta.doc_url && drawerPdfDoc) {
            renderDrawerPage(currentBbox);
            return;
        }

        drawerPdfUrl = meta.doc_url;
        window.pdfjsLib.getDocument(meta.doc_url).promise.then(function (pdfDoc) {
            drawerPdfDoc = pdfDoc;
            drawerNumPages = pdfDoc.numPages;
            renderDrawerPage(currentBbox);
        }).catch(function () {
            closeDrawer();
        });
    }

    function closeDrawer() {
        if (drawerEl) {
            drawerEl.classList.add('hidden');
        }
        currentDrawerSource = null;
    }

    // -----------------------------------------------------------------------
    // Wk2 Workstream A: document upload form handling
    //
    // Plan_wk2_Claude_Next06 — the same upload form now appears in TWO cards
    // on the patient chart: the standalone "Upload documents" card at the
    // top, and the embedded form inside the Clinical Co-Pilot card. Wiring
    // is by class (`form.copilot-upload-form`) so every form on the page
    // gets the same handler; descendant lookups are form-scoped so the two
    // cards don't fight over IDs.
    // -----------------------------------------------------------------------

    function makeShowUploadStatus(uploadStatus) {
        return function showUploadStatus(msg, isError) {
            if (!uploadStatus) { return; }
            uploadStatus.textContent = msg;
            uploadStatus.className = 'copilot-upload-status' + (isError ? ' copilot-upload-error' : '');
            uploadStatus.style.display = 'block';
        };
    }

    function formatUploadError(body, status) {
        if (!body || typeof body !== 'object') {
            return 'Upload failed (HTTP ' + status + ').';
        }
        if (body.error === 'csrf_failure') {
            return 'Upload failed: this page had an expired security token. Refresh the upload page and try again.';
        }
        if (body.error === 'ambiguous_dob') {
            var rawDob = body.raw ? ' "' + body.raw + '"' : '';
            var candidates = Array.isArray(body.candidates) && body.candidates.length
                ? ' It could mean ' + body.candidates.join(' or ') + '.'
                : '';
            return 'Upload needs review: the intake DOB' + rawDob + ' is ambiguous.' + candidates
                + ' Use an intake with a month name or ISO date, or create the patient manually.';
        }
        if (typeof body.detail === 'string' && body.detail !== '') {
            return 'Upload failed: ' + body.detail;
        }
        if (typeof body.error === 'string' && body.error !== '') {
            return 'Upload failed: ' + body.error;
        }
        return 'Upload failed: ' + JSON.stringify(body);
    }

    // AgDR-0077 / Plan §6.3 — fetch and render the medication-reconciliation
    // panel. Called automatically after a medication_list upload; idempotent
    // (re-fetches on each upload). The endpoint compares the latest extracted
    // medication list against the patient's OpenEMR `prescriptions` rows and
    // returns a structured array of confirmed / newly_listed /
    // possibly_discontinued rows. Hidden by default — only shown when at
    // least one row comes back.
    function fetchMedicationReconciliation() {
        var container = document.getElementById('copilot-medication-reconciliation');
        if (!container || !cfg.medicationReconciliationUrl) { return; }
        fetch(cfg.medicationReconciliationUrl, {
            method: 'GET',
            credentials: 'same-origin',
        }).then(function (res) {
            return res.json().then(function (json) { return { status: res.status, body: json }; });
        }).then(function (resp) {
            if (resp.status >= 400 || !resp.body || !Array.isArray(resp.body.rows) || resp.body.rows.length === 0) {
                container.style.display = 'none';
                return;
            }
            renderMedicationReconciliation(container, resp.body.rows, resp.body.summary || {});
            container.style.display = 'block';
        }).catch(function () {
            container.style.display = 'none';
        });
    }

    function renderMedicationReconciliation(container, rows, summary) {
        var statusBadge = function (status) {
            var label = status;
            var cls = 'badge badge-secondary';
            if (status === 'confirmed') { cls = 'badge badge-success'; label = 'confirmed'; }
            else if (status === 'newly_listed') { cls = 'badge badge-warning'; label = 'newly listed'; }
            else if (status === 'possibly_discontinued') { cls = 'badge badge-danger'; label = 'possibly d/c'; }
            return '<span class="' + cls + '">' + escapeHtml(label) + '</span>';
        };
        var rowHtml = rows.map(function (row) {
            return '<tr>'
                + '<td>' + escapeHtml(row.drug_name || '') + '</td>'
                + '<td>' + escapeHtml(row.extracted_dose || '') + '</td>'
                + '<td>' + escapeHtml(row.prescription_dose || '') + '</td>'
                + '<td>' + statusBadge(row.status || 'unknown') + '</td>'
                + '</tr>';
        }).join('');
        var summaryHtml = ''
            + '<span class="text-muted small mr-2">'
            + escapeHtml('Confirmed: ' + (summary.confirmed || 0)
                + ' · New: ' + (summary.newly_listed || 0)
                + ' · Possibly d/c: ' + (summary.possibly_discontinued || 0))
            + '</span>';
        container.innerHTML =
            '<div class="card mt-2 copilot-medrec-card">'
            + '<div class="card-header copilot-medrec-header">'
            + '<i class="fa fa-pills mr-2"></i>'
            + '<strong>Medication reconciliation</strong> '
            + summaryHtml
            + '</div>'
            + '<div class="card-body p-2">'
            + '<table class="table table-sm copilot-medrec-table">'
            + '<thead><tr><th>Drug</th><th>Extracted dose</th><th>Rx record dose</th><th>Status</th></tr></thead>'
            + '<tbody>' + rowHtml + '</tbody>'
            + '</table>'
            + '</div>'
            + '</div>';
    }

    // Plan_wk2_Claude_Next07_v2 §B.1 fix: extracted into a function so it
    // can be called BEFORE the no-card early-return above. Function
    // declarations hoist to the top of the IIFE, so this is callable from
    // the top-of-IIFE invocation point regardless of textual position.
    //
    // The handler runs whenever ANY of the upload routes are seeded into
    // OE_COPILOT_CONFIG — the in-chart cards seed lab+intake+medlist+create;
    // the pre-patient surface seeds only createPatientUrl. Previously the
    // gate required `cfg.uploadLabUrl && cfg.uploadIntakeUrl`, which the
    // pre-patient surface fails — fix is to OR-in `cfg.createPatientUrl`.
    function initUploadHandlers() {
        var hasInChartUrls = !!(cfg.uploadLabUrl && cfg.uploadIntakeUrl);
        var hasCreateOnly = !!cfg.createPatientUrl;
        if (!hasInChartUrls && !hasCreateOnly) {
            return;
        }
        var uploadForms = document.querySelectorAll('form.copilot-upload-form');
        uploadForms.forEach(function (uploadForm) {
            var uploadStatus = uploadForm.querySelector('.copilot-upload-status');
            var showUploadStatus = makeShowUploadStatus(uploadStatus);

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
                // AgDR-0066 + AgDR-0077 — four upload modes:
                //   lab_pdf                       → upload_lab.php          (existing patient)
                //   intake_form                   → upload_intake.php       (existing patient)
                //   medication_list               → upload_medication_list.php (Plan §6.3)
                //   intake_form_create_patient    → create_patient_from_intake.php (demo mode)
                var isCreatePatient = (docType === 'intake_form_create_patient');
                var isMedicationList = (docType === 'medication_list');
                var url;
                if (isCreatePatient) {
                    url = cfg.createPatientUrl;
                } else if (docType === 'intake_form') {
                    url = cfg.uploadIntakeUrl;
                } else if (isMedicationList && cfg.uploadMedicationListUrl) {
                    url = cfg.uploadMedicationListUrl;
                } else {
                    url = cfg.uploadLabUrl;
                }
                if (!url) {
                    showUploadStatus('Upload not available on this page for the selected document type.', true);
                    return;
                }

                var formData = new FormData();
                formData.append('file', file, file.name);
                formData.append('csrf_token_form', cfg.csrfToken || '');

                var startMsg = isCreatePatient
                    ? 'Extracting intake → creating demo patient…'
                    : 'Uploading…';
                showUploadStatus(startMsg, false);
                var submitBtn = uploadForm.querySelector('button[type="submit"]');
                if (submitBtn) { submitBtn.disabled = true; }

                var timeoutMs = isCreatePatient ? 120000 : 90000;
                var controller = window.AbortController ? new AbortController() : null;
                var timeoutId = window.setTimeout(function () {
                    if (controller) { controller.abort(); }
                }, timeoutMs);
                var fetchOptions = {
                    method: 'POST',
                    credentials: 'same-origin',
                    body: formData
                };
                if (controller) {
                    fetchOptions.signal = controller.signal;
                }

                fetch(url, fetchOptions).then(function (res) {
                    window.clearTimeout(timeoutId);
                    // The endpoint can return text/html (e.g. when not
                    // authenticated and OpenEMR's session bootstrap emits
                    // its login-redirect <script>). Guard the JSON parse so
                    // we surface a readable error instead of a silent
                    // throw-into-catch.
                    return res.text().then(function (body) {
                        var ct = res.headers.get('content-type') || '';
                        if (ct.indexOf('application/json') === -1) {
                            return { status: res.status, body: null, raw: body, isJson: false };
                        }
                        try {
                            return { status: res.status, body: JSON.parse(body), isJson: true };
                        } catch (e) {
                            return { status: res.status, body: null, raw: body, isJson: false };
                        }
                    });
                }).then(function (resp) {
                    if (submitBtn) { submitBtn.disabled = false; }
                    if (!resp.isJson) {
                        showUploadStatus(
                            'Upload failed (server returned non-JSON, HTTP ' + resp.status + '). Check that you are still logged in.',
                            true
                        );
                        return;
                    }
                    if (resp.status >= 400) {
                        showUploadStatus(formatUploadError(resp.body, resp.status), true);
                        return;
                    }
                    // Plan_wk2_Claude_Next08 §W1 — surface the sidecar's
                    // Langfuse trace ID on every successful upload. Format
                    // matches the existing Co-Pilot card's brief chip
                    // ("trace: <id>") so the visual signal is consistent
                    // across the brief surface and the four upload modes.
                    // Defensive: tolerate missing or non-string trace_id.
                    var traceId = (resp.body && typeof resp.body.trace_id === 'string') ? resp.body.trace_id : '';
                    var traceSuffix = traceId ? ' [trace: ' + traceId.slice(0, 8) + '…]' : '';
                    if (isCreatePatient && resp.body && resp.body.redirect_url) {
                        var demo = resp.body.demographics || {};
                        var label = [demo.fname, demo.lname].filter(Boolean).join(' ') || 'new patient';
                        showUploadStatus(
                            'Created demo patient ' + escapeHtml(label) + ' (pid ' + resp.body.pid + ').' + traceSuffix + ' Redirecting…',
                            false
                        );
                        // Give the user a beat to read the status before navigating.
                        setTimeout(function () { window.location.href = resp.body.redirect_url; }, 1500);
                        return;
                    }
                    var count = (resp.body && resp.body.extracted_field_count) || 0;
                    // AgDR-0063 — raw-doc SHA dedup: surface the duplicate signal so
                    // the user understands the upload was idempotent. Extraction
                    // still runs against the existing document body.
                    var isDuplicate = !!(resp.body && resp.body.duplicate);
                    var prefix = isDuplicate
                        ? 'Document already on file — using existing copy. '
                        : '';
                    showUploadStatus(prefix + 'Extracted ' + count + ' field(s).' + traceSuffix, false);
                    // The fetchBrief + fetchMedicationReconciliation refresh
                    // calls only make sense inside a chart with a Co-Pilot
                    // card. Guard them so the pre-patient surface does not
                    // crash trying to refresh a brief that is not on the page.
                    if (card && cfg.briefUrl && typeof fetchBrief === 'function') {
                        showUploadStatus(prefix + 'Extracted ' + count + ' field(s).' + traceSuffix + ' Refreshing brief…', false);
                        setTimeout(function () { fetchBrief('pre_room_brief'); }, 1200);
                        if (isMedicationList && cfg.medicationReconciliationUrl && typeof fetchMedicationReconciliation === 'function') {
                            setTimeout(function () { fetchMedicationReconciliation(); }, 1300);
                        }
                    }
                }).catch(function (err) {
                    window.clearTimeout(timeoutId);
                    if (submitBtn) { submitBtn.disabled = false; }
                    if (err && err.name === 'AbortError') {
                        showUploadStatus('Upload timed out before the server responded. No patient was created; refresh and try again.', true);
                    } else {
                        showUploadStatus('Upload failed (network error).', true);
                    }
                });
            });
        });
    }
})();
