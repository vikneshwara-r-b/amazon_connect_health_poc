// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
// nosemgrep: insecure-document-method, insecure-innerhtml, html-in-template-string
// Justification: same convention as js/main.js — renders data from a trusted AWS API
// (HealthLake, via the backend proxy), all dynamic values wrapped with escapeHtml().

// ==========================================================================
// PATIENT PORTAL — live HealthLake data for Diagnoses, Vital Signs,
// Recent Labs, and the Lab results tab.
//
// A single backend route (/api/fhir/patient/<id>/summary?section=...) is
// fetched once per section at a large _count; the "Recent" panels and the
// full Lab results tab both read from that same response and slice
// client-side, rather than issuing separate requests.
// ==========================================================================

(function () {
    const SECTION_CACHE = {}; // patientId -> { diagnoses, vitals, labs } fetch results

    function backendUrl() {
        return window.BACKEND_URL || 'http://localhost:5000';
    }

    async function fetchSection(patientId, section) {
        // HealthLake's FHIR search API caps _count at 100 (higher values 400).
        const url = `${backendUrl()}/api/fhir/patient/${encodeURIComponent(patientId)}/summary?section=${section}&_count=100`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HealthLake summary fetch failed for ${section}: ${response.status}`);
        }
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || `HealthLake summary request failed for ${section}`);
        }
        return data.results || [];
    }

    function formatDate(isoDate) {
        if (!isoDate) return '';
        const d = new Date(isoDate);
        if (isNaN(d.getTime())) return isoDate;
        return d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' });
    }

    function renderDiagnoses(results) {
        const content = document.getElementById('diagnosesContent');
        if (!content) return;
        if (!results.length) {
            content.innerHTML = '<div class="section-note">No active diagnoses</div>';
            return;
        }
        const rows = results.map(c =>
            `<div class="diagnosis-item">(${escapeHtml(c.code || '')}) ${escapeHtml(c.name || 'Unknown')}</div>`
        ).join('');
        content.innerHTML =
            `<div class="section-subheader">Chronic diagnoses</div>${rows}` +
            `<div class="section-subheader">Acute diagnoses</div><div class="section-note">No active Acute diagnoses</div>`;
    }

    function mostRecentPerVital(results) {
        const byCode = new Map();
        for (const o of results) {
            const key = o.code || o.name;
            const existing = byCode.get(key);
            if (!existing || (o.date && o.date > existing.date)) {
                byCode.set(key, o);
            }
        }
        return Array.from(byCode.values());
    }

    function renderVitalSigns(results) {
        const content = document.getElementById('vitalSignsContent');
        const headerText = document.getElementById('vitalSignsHeaderText');
        if (!content) return;
        if (!results.length) {
            content.innerHTML = '<div class="section-note">No vital signs recorded</div>';
            if (headerText) headerText.textContent = 'Vital signs';
            return;
        }
        const latest = mostRecentPerVital(results);
        const rows = latest.map(v =>
            `<div class="section-detail">• ${escapeHtml(v.name || 'Unknown')}: ${escapeHtml(v.value)} ${escapeHtml(v.unit || '')}</div>`
        ).join('');
        content.innerHTML = rows;
        const newestDate = results.reduce((max, v) => (v.date && v.date > max ? v.date : max), '');
        if (headerText) headerText.textContent = newestDate ? `Vital signs (Last: ${formatDate(newestDate)})` : 'Vital signs';
    }

    function renderRecentLabs(results) {
        const content = document.getElementById('recentLabsContent');
        if (!content) return;
        if (!results.length) {
            content.innerHTML = '<div class="section-note">No lab results available</div>';
            return;
        }
        const recent = results.slice(0, 5);
        const newestDate = results.reduce((max, r) => (r.date && r.date > max ? r.date : max), '');
        const rows = recent.map(r =>
            `<div class="section-detail">• ${escapeHtml(r.name || 'Unknown')}: ${escapeHtml(r.value)} ${escapeHtml(r.unit || '')}</div>`
        ).join('');
        content.innerHTML =
            (newestDate ? `<div class="section-subheader">Last drawn: ${escapeHtml(formatDate(newestDate))}</div>` : '') + rows;
    }

    function renderFullLabHistory(results) {
        const pane = document.getElementById('labResultsTabContent');
        if (!pane) return;
        if (!results.length) {
            pane.innerHTML = '<div class="section" style="padding: 16px;"><div class="section-note">No lab results available</div></div>';
            return;
        }
        const sorted = [...results].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        const rows = sorted.map(r => `
            <div class="section-detail" style="padding: 8px 12px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between;">
                <span>${escapeHtml(r.name || 'Unknown')}</span>
                <span>${escapeHtml(r.value)} ${escapeHtml(r.unit || '')}</span>
                <span>${escapeHtml(formatDate(r.date))}</span>
            </div>`).join('');
        pane.innerHTML = `
            <div class="section">
                <div class="section-header">Lab results — full history</div>
                <div class="section-content" style="padding: 0;">${rows}</div>
            </div>`;
    }

    // Public: called from index.html's loadPatientInsights() when a patient is opened.
    window.loadPatientClinicalSections = async function (patientId) {
        renderDiagnoses.pending = true;
        try {
            const [diagnoses, vitals, labs] = await Promise.all([
                fetchSection(patientId, 'diagnoses'),
                fetchSection(patientId, 'vitals'),
                fetchSection(patientId, 'labs')
            ]);
            SECTION_CACHE[patientId] = { diagnoses, vitals, labs };
            renderDiagnoses(diagnoses);
            renderVitalSigns(vitals);
            renderRecentLabs(labs);
        } catch (e) {
            console.error('[patient-data] Failed to load HealthLake clinical sections:', e);
            const diagContent = document.getElementById('diagnosesContent');
            const vitalContent = document.getElementById('vitalSignsContent');
            const labContent = document.getElementById('recentLabsContent');
            if (diagContent) diagContent.innerHTML = '<div class="section-note">Unable to load diagnoses</div>';
            if (vitalContent) vitalContent.innerHTML = '<div class="section-note">Unable to load vitals</div>';
            if (labContent) labContent.innerHTML = '<div class="section-note">Unable to load labs</div>';
        }
    };

    async function loadFullLabHistory(patientId) {
        const pane = document.getElementById('labResultsTabContent');
        if (!pane) return;
        pane.innerHTML = '<div class="section-note" style="padding: 16px;">Loading lab history…</div>';
        try {
            const cached = SECTION_CACHE[patientId];
            const labs = cached ? cached.labs : await fetchSection(patientId, 'labs');
            renderFullLabHistory(labs);
        } catch (e) {
            console.error('[patient-data] Failed to load full lab history:', e);
            pane.innerHTML = '<div class="section-note" style="padding: 16px;">Unable to load lab history</div>';
        }
    }

    // Tab switching: Profile <-> Lab results (the app's first real tab-switch handler —
    // other tabs are currently dead links with no content pane logic).
    document.addEventListener('DOMContentLoaded', function () {
        const tabLabResults = document.getElementById('tabLabResults');
        const tabProfile = document.getElementById('tabProfile');
        const contentArea = document.querySelector('.content-area');
        const labPane = document.getElementById('labResultsTabContent');
        if (!tabLabResults || !tabProfile || !contentArea || !labPane) return;

        function setActiveTab(activeTab) {
            document.querySelectorAll('.tab-nav .tab').forEach(t => t.classList.remove('active'));
            activeTab.classList.add('active');
        }

        tabLabResults.addEventListener('click', function (e) {
            e.preventDefault();
            setActiveTab(tabLabResults);
            contentArea.style.display = 'none';
            labPane.style.display = 'flex';
            if (window.currentPatientId) {
                loadFullLabHistory(window.currentPatientId);
            }
        });

        tabProfile.addEventListener('click', function (e) {
            e.preventDefault();
            setActiveTab(tabProfile);
            labPane.style.display = 'none';
            contentArea.style.display = 'flex';
            // Note: if a consultation has already ended, injectClinicalDocIntoEHR() (main.js)
            // has replaced .content-area's innerHTML with the SOAP note — this tab switch
            // doesn't restore the original Diagnoses/Vitals/Labs panels in that case, which
            // is a pre-existing limitation of that one-way replacement, not something this
            // tab handler fixes.
        });
    });
})();
