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
    var followupsEl = document.getElementById('copilot-followups');
    var errorEl = document.getElementById('copilot-error');
    var traceEl = document.getElementById('copilot-trace-id');

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

    function renderClaims(payload) {
        statusEl.style.display = 'none';
        var claims = (payload && payload.claims) || [];
        if (!claims.length) {
            claimsEl.innerHTML = '<div class="text-muted">' + escapeHtml('No verified claims to show yet.') + '</div>';
        } else {
            var html = '';
            claims.forEach(function (c) {
                var chips = (c.source_ids || []).map(function (id) {
                    return '<span class="copilot-source-chip" title="' + escapeHtml(id) + '">' + escapeHtml(id) + '</span>';
                }).join('');
                var caveat = c.caveat ? '<span class="copilot-claim-caveat">(' + escapeHtml(c.caveat) + ')</span>' : '';
                html += '<div class="copilot-claim">';
                html += '<span class="copilot-claim-text">' + escapeHtml(c.text) + '</span> ';
                html += chips + ' ' + caveat;
                html += '</div>';
            });
            claimsEl.innerHTML = html;
        }
        claimsEl.style.display = 'block';

        var missing = (payload && payload.missing_data) || [];
        if (missing.length) {
            missingEl.innerHTML = '<strong>Missing:</strong> ' + missing.map(escapeHtml).join('; ');
            missingEl.style.display = 'block';
        }

        followupsEl.style.display = 'block';
    }

    function fetchBrief(useCase) {
        statusEl.style.display = 'block';
        errorEl.style.display = 'none';
        var formData = new FormData();
        formData.append('csrf_token_form', cfg.csrfToken);
        formData.append('use_case', useCase || 'pre_room_brief');

        fetch(cfg.briefUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        }).then(function (res) {
            return res.json().then(function (json) { return { status: res.status, body: json }; });
        }).then(function (resp) {
            if (resp.body && resp.body.trace_id) {
                traceEl.textContent = 'trace: ' + resp.body.trace_id;
            }
            if (resp.status >= 400 || (resp.body && resp.body.error)) {
                showError((resp.body && resp.body.error) || 'Co-Pilot error: HTTP ' + resp.status);
                return;
            }
            renderClaims(resp.body);
        }).catch(function (err) {
            showError('Co-Pilot fetch failed: ' + (err && err.message ? err.message : 'unknown'));
        });
    }

    document.querySelectorAll('.copilot-followup-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            fetchBrief(btn.getAttribute('data-followup'));
        });
    });

    fetchBrief('pre_room_brief');
})();
