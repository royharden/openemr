/* Clinical Co-Pilot — Lab Trends widget (Plan §7.1, AgDR-0088).
 *
 * Renders one mini line-chart per analyte for the current chart's pid.
 * Data source: same-origin `lab_trends.php` endpoint (session-cookie
 * auth, ACL `patients/med`, patient-scope bind).
 *
 * Hand-rolled SVG was chosen over Chart.js to avoid the
 * vendor/SRI/LICENSE-NOTICE work that Plan §3.1 / AgDR-0072 did for
 * pdf.js. The trend widget needs exactly one shape (a single
 * polyline with point markers on a reference-range band); Chart.js is
 * overkill for that. If a future feature needs grouped bars, area
 * fills, or scale animation, revisit and vendor Chart.js then.
 *
 * Render contract:
 *   window.OE_COPILOT_LAB_TRENDS_CONFIG = {
 *     endpoint: "<module>/public/api/lab_trends.php",
 *     minObservations: 3,
 *     containerId: "copilot-lab-trends",
 *   };
 *
 * If the endpoint returns an empty `series` array, the widget hides
 * itself entirely — the demo recording stays clean on charts with no
 * extracted labs yet.
 */
(function () {
    'use strict';

    var SVG_NS = 'http://www.w3.org/2000/svg';
    var CHART_WIDTH = 320;     // px — fits the chart sidebar
    var CHART_HEIGHT = 140;    // px — short enough for stacked tiles
    var CHART_MARGIN = { top: 16, right: 12, bottom: 26, left: 36 };

    function elem(tag, attrs, text) {
        var el = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                el.setAttribute(k, attrs[k]);
            });
        }
        if (text !== undefined && text !== null) {
            el.textContent = String(text);
        }
        return el;
    }

    function svgElem(tag, attrs, text) {
        var el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                el.setAttribute(k, attrs[k]);
            });
        }
        if (text !== undefined && text !== null) {
            el.textContent = String(text);
        }
        return el;
    }

    /**
     * Parse "YYYY-MM-DD" into a numeric day-since-epoch for x-axis math.
     * Returns null on unparsable input.
     */
    function parseDay(s) {
        if (typeof s !== 'string' || s.length < 10) {
            return null;
        }
        var t = Date.parse(s.slice(0, 10) + 'T00:00:00Z');
        if (isNaN(t)) {
            return null;
        }
        return Math.floor(t / 86400000);
    }

    function formatDateLabel(s) {
        if (typeof s !== 'string' || s.length < 10) {
            return '';
        }
        var parts = s.slice(0, 10).split('-');
        if (parts.length !== 3) {
            return s.slice(0, 10);
        }
        return String(Number(parts[1])) + '/' + String(Number(parts[2])) + '/' + parts[0].slice(2);
    }

    /**
     * Build a single SVG line chart for one analyte series.
     * Returns the SVGSVGElement.
     */
    function renderSvgChart(series) {
        var pts = (series.observations || [])
            .map(function (o, index) {
                return {
                    day: parseDay(o.date),
                    value: typeof o.value === 'number' ? o.value : null,
                    date: o.date,
                    abnormal: o.abnormal,
                    index: index,
                };
            })
            .filter(function (p) {
                return p.day !== null && p.value !== null;
            })
            .sort(function (a, b) {
                if (a.day !== b.day) {
                    return a.day - b.day;
                }
                return a.index - b.index;
            });

        var svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('viewBox', '0 0 ' + CHART_WIDTH + ' ' + CHART_HEIGHT);
        svg.setAttribute('class', 'copilot-lab-trend-chart');
        svg.setAttribute('role', 'img');
        svg.setAttribute(
            'aria-label',
            'Trend chart for ' + (series.label || series.loinc)
                + ' (' + pts.length + ' observations)'
        );

        if (pts.length === 0) {
            svg.appendChild(svgElem('text', {
                x: CHART_WIDTH / 2,
                y: CHART_HEIGHT / 2,
                'text-anchor': 'middle',
                fill: '#888',
                'font-size': '11',
            }, 'no numeric observations'));
            return svg;
        }

        var xMin = pts[0].day;
        var xMax = pts[pts.length - 1].day;
        if (xMin === xMax) { xMax = xMin + 1; }

        var yMin = Math.min.apply(null, pts.map(function (p) { return p.value; }));
        var yMax = Math.max.apply(null, pts.map(function (p) { return p.value; }));
        if (yMin === yMax) {
            yMin -= 1;
            yMax += 1;
        }
        // Pad the y-domain by 10% so points don't ride the axes.
        var yPad = (yMax - yMin) * 0.10;
        yMin = yMin - yPad;
        yMax = yMax + yPad;

        function xPx(day) {
            return CHART_MARGIN.left + ((day - xMin) / (xMax - xMin))
                * (CHART_WIDTH - CHART_MARGIN.left - CHART_MARGIN.right);
        }
        function yPx(value) {
            return CHART_HEIGHT - CHART_MARGIN.bottom
                - ((value - yMin) / (yMax - yMin))
                * (CHART_HEIGHT - CHART_MARGIN.top - CHART_MARGIN.bottom);
        }

        // Y-axis grid lines (3 ticks).
        var yTicks = [yMin, (yMin + yMax) / 2, yMax];
        yTicks.forEach(function (v) {
            var y = yPx(v);
            svg.appendChild(svgElem('line', {
                x1: CHART_MARGIN.left,
                x2: CHART_WIDTH - CHART_MARGIN.right,
                y1: y, y2: y,
                stroke: '#e5e7eb',
                'stroke-width': '1',
            }));
            svg.appendChild(svgElem('text', {
                x: CHART_MARGIN.left - 6,
                y: y + 3,
                'text-anchor': 'end',
                fill: '#6b7280',
                'font-size': '10',
            }, Math.round(v * 10) / 10));
        });

        // X-axis ticks: first + last collection date. Compact labels keep
        // the mini-card readable at dashboard tile widths; identical dates
        // render once so start/end text cannot collide.
        var xTickPoints = [pts[0]];
        if (pts[pts.length - 1].date !== pts[0].date) {
            xTickPoints.push(pts[pts.length - 1]);
        }
        xTickPoints.forEach(function (p, i) {
            svg.appendChild(svgElem('text', {
                x: xPx(p.day),
                y: CHART_HEIGHT - 8,
                'text-anchor': xTickPoints.length === 1 ? 'start' : (i === 0 ? 'start' : 'end'),
                fill: '#6b7280',
                'font-size': '10',
            }, formatDateLabel(p.date)));
        });

        // Polyline connecting all points.
        var pathD = pts.map(function (p, i) {
            return (i === 0 ? 'M ' : 'L ') + xPx(p.day) + ' ' + yPx(p.value);
        }).join(' ');
        svg.appendChild(svgElem('path', {
            d: pathD,
            stroke: '#2563eb',
            'stroke-width': '2',
            fill: 'none',
        }));

        // Point markers — colored by abnormal flag (H/L red, otherwise blue).
        pts.forEach(function (p) {
            var fill = '#2563eb';
            if (p.abnormal === 'H' || p.abnormal === 'L') {
                fill = '#dc2626';
            }
            var marker = svgElem('circle', {
                cx: xPx(p.day),
                cy: yPx(p.value),
                r: '3.5',
                fill: fill,
                stroke: '#fff',
                'stroke-width': '1.5',
            });
            var titleNode = svgElem('title', null,
                series.label + ': ' + p.value
                + (series.unit ? ' ' + series.unit : '')
                + (p.abnormal ? ' [' + p.abnormal + ']' : '')
                + ' (' + p.date + ')'
            );
            marker.appendChild(titleNode);
            svg.appendChild(marker);
        });

        return svg;
    }

    /**
     * Build one tile (title + chart + summary).
     */
    function renderTile(series) {
        var tile = elem('div', { class: 'copilot-lab-trend-tile' });

        var header = elem('div', { class: 'copilot-lab-trend-header' });
        header.appendChild(elem('span', { class: 'copilot-lab-trend-label' }, series.label || series.loinc));
        header.appendChild(elem('span', { class: 'copilot-lab-trend-loinc' }, 'LOINC ' + series.loinc));
        tile.appendChild(header);

        tile.appendChild(renderSvgChart(series));

        var meta = elem('div', { class: 'copilot-lab-trend-meta' });
        var n = (series.observations || []).length;
        meta.appendChild(elem('span', null, n + ' observation' + (n === 1 ? '' : 's')));
        if (series.unit) {
            meta.appendChild(elem('span', { class: 'copilot-lab-trend-unit' }, 'units: ' + series.unit));
        }
        if (series.reference_range) {
            meta.appendChild(elem('span', { class: 'copilot-lab-trend-range' }, 'ref: ' + series.reference_range));
        }
        tile.appendChild(meta);

        return tile;
    }

    /**
     * Fetch + render. On any failure (network, empty payload), hide
     * the container so the chart sidebar doesn't display an empty
     * shell with no data behind it.
     */
    function render() {
        var cfg = window.OE_COPILOT_LAB_TRENDS_CONFIG;
        if (!cfg || !cfg.endpoint || !cfg.containerId) {
            return;
        }
        var container = document.getElementById(cfg.containerId);
        if (!container) {
            return;
        }

        var url = cfg.endpoint;
        if (cfg.minObservations) {
            url += (url.indexOf('?') === -1 ? '?' : '&')
                + 'min_observations=' + encodeURIComponent(cfg.minObservations);
        }

        fetch(url, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        }).then(function (res) {
            if (!res.ok) { throw new Error('HTTP ' + res.status); }
            return res.json();
        }).then(function (payload) {
            var series = (payload && Array.isArray(payload.series)) ? payload.series : [];
            if (series.length === 0) {
                container.style.display = 'none';
                return;
            }
            container.innerHTML = '';
            var heading = elem('h4', { class: 'copilot-lab-trend-heading' }, 'Co-Pilot lab trends');
            container.appendChild(heading);

            var grid = elem('div', { class: 'copilot-lab-trend-grid' });
            series.forEach(function (s) {
                grid.appendChild(renderTile(s));
            });
            container.appendChild(grid);
            container.style.display = '';
        }).catch(function () {
            // Silent failure — the trend widget is auxiliary; a broken
            // fetch shouldn't break the Co-Pilot card itself.
            container.style.display = 'none';
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
})();
