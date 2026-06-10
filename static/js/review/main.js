/** SAR Redact v2 — review orchestrator */

import { PdfViewer }      from './pdf-viewer.js';
import { CandidateManager } from './candidates.js';
import { DrawManager }    from './draw.js';
import { FilterManager }  from './filters.js';
import { initShortcuts }  from './shortcuts.js';
import * as api           from './api.js';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

document.addEventListener('DOMContentLoaded', async () => {
  const sarId    = window.SAR_ID;
  if (!sarId) return;

  // ── Elements ───────────────────────────────────────────────────────────────
  const canvasEl     = $('#pdf-canvas');
  const overlayEl    = $('#redact-overlay');
  const fileSelect   = $('#file-select');
  const prevBtn      = $('#prev-page-btn');
  const nextBtn      = $('#next-page-btn');
  const pageIndicator= $('#page-indicator');
  const zoomInBtn    = $('#zoom-in-btn');
  const zoomOutBtn   = $('#zoom-out-btn');
  const zoomLevel    = $('#zoom-level');
  const drawModeBtn  = $('#draw-mode-btn');
  const legendBtn    = $('#legend-btn');
  const legendPanel  = $('#legend-panel');
  const pageNavBtn   = $('#page-nav-btn');
  const pageNavPanel = $('#page-nav-panel');
  const pageNavGrid  = $('#page-nav-grid');
  const settingsBtn  = $('#settings-btn');
  const settingsModal= $('#settings-modal');
  const finaliseBtn  = $('#finalise-btn');
  const candidateList= $('#candidates-list');
  const progressFill = $('#sidebar-progress-fill');
  const reviewedLabel= $('#reviewed-count');
  const searchInput  = $('#search-input');
  const notesTa      = $('#notes-ta');
  const allocSel     = $('#allocate-select');
  const workflowBtn  = $('#workflow-btn');

  // ── Modules ────────────────────────────────────────────────────────────────
  const viewer = new PdfViewer(canvasEl, overlayEl, sarId);
  const cmgr   = new CandidateManager(candidateList, progressFill, reviewedLabel, onCandidateAction);
  const draw   = new DrawManager($('#pdf-canvas-container'), onManualDraw);
  const fmgr   = new FilterManager(({ filter, sort }) => {
    cmgr.setFilter(filter);
    cmgr.setSort(sort);
  });

  // ── Load initial file ──────────────────────────────────────────────────────
  let currentFile = window.MAIN_RECORD || (window.FILES_DATE?.[0]?.name ?? '');
  if (currentFile) {
    if (fileSelect) fileSelect.value = currentFile;
    await viewer.loadFile(currentFile);
    updatePageIndicator();
    buildPageNav();
  }
  await loadCandidates();

  // ── File selection ─────────────────────────────────────────────────────────
  fileSelect?.addEventListener('change', async () => {
    currentFile = fileSelect.value;
    await viewer.loadFile(currentFile);
    updatePageIndicator();
    buildPageNav();
    cmgr.setFilter({ status: fmgr.filter.status, search: fmgr.filter.search });
    viewer.drawOverlay(cmgr.getAll());
  });

  // File order buttons
  $('#sort-date-btn')?.addEventListener('click', () => {
    populateFileSelect(window.FILES_DATE);
    $('#sort-date-btn').classList.add('active');
    $('#sort-file-btn').classList.remove('active');
  });
  $('#sort-file-btn')?.addEventListener('click', () => {
    populateFileSelect(window.FILES_FILE);
    $('#sort-file-btn').classList.add('active');
    $('#sort-date-btn').classList.remove('active');
  });

  function populateFileSelect(filesArr) {
    if (!fileSelect || !filesArr) return;
    fileSelect.innerHTML = filesArr.map(f =>
      `<option value="${f.name}"${f.name === currentFile ? ' selected' : ''}>${f.name} (${f.pages}pp${f.date ? ' · ' + f.date : ''})</option>`
    ).join('');
  }

  // ── Pagination ─────────────────────────────────────────────────────────────
  prevBtn?.addEventListener('click', () => goPage(viewer.currentPage - 1));
  nextBtn?.addEventListener('click', () => goPage(viewer.currentPage + 1));

  async function goPage(n) {
    await viewer.goToPage(n);
    viewer.drawOverlay(cmgr.getAll());
    updatePageIndicator();
    updatePageNav();
  }

  function updatePageIndicator() {
    if (pageIndicator) pageIndicator.textContent = `${viewer.currentPage + 1} / ${viewer.totalPages || '—'}`;
  }

  // ── Page navigator ─────────────────────────────────────────────────────────
  function buildPageNav() {
    if (!pageNavGrid) return;
    const total = viewer.totalPages;
    pageNavGrid.innerHTML = Array.from({ length: total }, (_, i) =>
      `<div class="page-nav-thumb${i === viewer.currentPage ? ' current' : ''}" data-page="${i}">p${i+1}</div>`
    ).join('');
    pageNavGrid.querySelectorAll('.page-nav-thumb').forEach(el => {
      el.addEventListener('click', () => goPage(parseInt(el.dataset.page)));
    });
  }

  function updatePageNav() {
    if (!pageNavGrid) return;
    pageNavGrid.querySelectorAll('.page-nav-thumb').forEach(el => {
      el.classList.toggle('current', parseInt(el.dataset.page) === viewer.currentPage);
    });
    updatePageIndicator();
  }

  // ── Zoom ───────────────────────────────────────────────────────────────────
  zoomInBtn?.addEventListener('click', () => doZoom('in'));
  zoomOutBtn?.addEventListener('click', () => doZoom('out'));

  async function doZoom(dir) {
    if (dir === 'in') viewer.zoomIn(); else viewer.zoomOut();
    if (zoomLevel) zoomLevel.textContent = Math.round(viewer.zoom * 100) + '%';
    draw.setZoom(viewer.zoom);
    await viewer.goToPage(viewer.currentPage);
    viewer.drawOverlay(cmgr.getAll());
  }

  // ── Draw mode ──────────────────────────────────────────────────────────────
  let drawEnabled = false;
  drawModeBtn?.addEventListener('click', toggleDrawMode);

  function toggleDrawMode() {
    drawEnabled = !drawEnabled;
    drawModeBtn?.classList.toggle('active', drawEnabled);
    drawEnabled ? draw.enable() : draw.disable();
    draw.setZoom(viewer.zoom);
  }

  async function onManualDraw({ x0, y0, x1, y1 }) {
    // draw.js gives coordinates in CSS pixels / userZoom = natural image pixels
    // (natural = rendered at PDF's native renderZoom, before userZoom scaling)
    // drawOverlay expects PDF points. Convert:
    //   pdfPt = naturalPixel * pdfW / naturalW
    //   naturalW = canvas.width / viewer.zoom
    const naturalW = viewer.canvas.width  / viewer.zoom;
    const naturalH = viewer.canvas.height / viewer.zoom;
    const scaleX   = viewer._pdfW / naturalW;
    const scaleY   = viewer._pdfH / naturalH;

    const pdfCoords = {
      x0: x0 * scaleX,
      y0: y0 * scaleY,
      x1: x1 * scaleX,
      y1: y1 * scaleY,
      page_num:    viewer.currentPage,
      source_file: currentFile,
    };

    try {
      await api.manualRedact(sarId, pdfCoords);
      const updated = await api.getCandidates(sarId);
      cmgr.setCandidates(updated.candidates);
      viewer.drawOverlay(cmgr.getAll());
    } catch (e) {
      console.error('Manual redact error:', e);
    }
  }

  // ── Panels ─────────────────────────────────────────────────────────────────
  legendBtn?.addEventListener('click', () => {
    legendPanel?.classList.toggle('hidden');
    pageNavPanel?.classList.add('hidden');
  });
  pageNavBtn?.addEventListener('click', () => {
    pageNavPanel?.classList.toggle('hidden');
    legendPanel?.classList.add('hidden');
  });

  // ── Settings modal ─────────────────────────────────────────────────────────
  settingsBtn?.addEventListener('click', async () => {
    try {
      const s = await api.getDetectionSettings(sarId);
      const autoEl = $('#ds-auto'), flagEl = $('#ds-flag');
      const autoV  = $('#ds-auto-v'), flagV = $('#ds-flag-v');
      if (autoEl) { autoEl.value = s.auto_redact_threshold; if (autoV) autoV.textContent = s.auto_redact_threshold.toFixed(2); }
      if (flagEl) { flagEl.value = s.flag_threshold;        if (flagV) flagV.textContent = s.flag_threshold.toFixed(2); }
    } catch {}
    settingsModal?.classList.remove('hidden');
  });
  window.saveSettings = async () => {
    const settings = {
      auto_redact_threshold: parseFloat($('#ds-auto').value),
      flag_threshold: parseFloat($('#ds-flag').value),
    };
    await api.updateDetectionSettings(sarId, settings);
    settingsModal?.classList.add('hidden');
  };

  // ── Candidate overlay click ────────────────────────────────────────────────
  overlayEl?.addEventListener('candidateclick', e => {
    const cid = e.detail;
    cmgr.setActiveCard(cid);
    viewer.highlightCandidate(cid);
  });

  // ── Candidate actions ──────────────────────────────────────────────────────
  async function onCandidateAction({ candidateId, action, status, candidate }) {
    if (action === 'select') {
      viewer.highlightCandidate(candidateId);
      // If on different page/file, jump
      if (candidate.source_file !== currentFile) {
        currentFile = candidate.source_file;
        if (fileSelect) fileSelect.value = currentFile;
        await viewer.loadFile(currentFile);
        updatePageIndicator();
        buildPageNav();
        viewer.drawOverlay(cmgr.getAll());
      } else if (candidate.page_num !== viewer.currentPage) {
        await goPage(candidate.page_num);
      }
      return;
    }
    if (action === 'status') {
      try {
        await api.updateCandidate(sarId, candidateId, { status });
        cmgr.updateCandidate(candidateId, status);
        viewer.drawOverlay(cmgr.getAll());
      } catch (e) {
        // Rollback
        cmgr.updateCandidate(candidateId, candidate.status);
        console.error('Status update failed:', e);
      }
    }
  }

  // ── Load candidates ────────────────────────────────────────────────────────
  async function loadCandidates() {
    try {
      const data = await api.getCandidates(sarId);
      cmgr.setCandidates(data.candidates);
      viewer.drawOverlay(data.candidates);
    } catch (e) {
      candidateList.innerHTML = `<div class="alert alert-error" style="margin:8px;">Failed to load candidates: ${e.message}</div>`;
    }
  }

  // ── Filter buttons ─────────────────────────────────────────────────────────
  window.setFilter = (status) => {
    fmgr.setFilter(status);
    $$('[id^="filter-"]').forEach(b => b.classList.remove('active'));
    $(`#filter-${status}`)?.classList.add('active');
  };
  window.setSort = (sort) => {
    fmgr.setSort(sort);
    $$('[id^="sort-page-btn"],[id^="sort-conf-btn"]').forEach(b => b.classList.remove('active'));
    $(`#sort-${sort}-btn`)?.classList.add('active');
  };
  window.setFileOrder = (order) => {
    populateFileSelect(order === 'date' ? window.FILES_DATE : window.FILES_FILE);
  };

  searchInput?.addEventListener('input', () => fmgr.setSearch(searchInput.value));

  // ── Notes autosave ─────────────────────────────────────────────────────────
  let notesTimer = null;
  notesTa?.addEventListener('input', () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(() => api.updateNotes(sarId, notesTa.value).catch(() => {}), 1500);
  });

  // ── Finalise ───────────────────────────────────────────────────────────────
  finaliseBtn?.addEventListener('click', async () => {
    const stats = cmgr.getStats();
    const msg = `Finalise this SAR?\n\n${stats.approved + stats.auto} redactions · ${stats.total - stats.approved - stats.auto} not redacted\n\nThis will generate the redacted PDF output.`;
    if (!confirm(msg)) return;
    finaliseBtn.disabled = true;
    finaliseBtn.textContent = 'Finalising…';
    try {
      const result = await api.finalise(sarId);
      const failed = result?.failed_redactions || [];
      if (failed.length) {
        alert(`WARNING: ${failed.length} approved redaction(s) could not be placed on the page and REMAIN VISIBLE in the output.\n\nThey are listed on the next screen and in the audit log — redact them manually before disclosure.`);
      }
      window.location.href = '/complete/' + sarId;
    } catch (e) {
      alert('Finalise failed: ' + e.message);
      finaliseBtn.disabled = false;
      finaliseBtn.textContent = 'Finalise';
    }
  });

  // ── Allocation / workflow ──────────────────────────────────────────────────
  window.allocateSar = async () => {
    if (!allocSel) return;
    try { await api.allocate(sarId, allocSel.value); } catch (e) { alert(e.message); }
  };
  window.submitWorkflow = async () => {
    const isAdmin = window.IS_ADMIN;
    const status  = isAdmin ? 'ready_for_signoff' : 'ready_for_signoff';
    try { await api.updateWorkflow(sarId, status); location.reload(); } catch (e) { alert(e.message); }
  };

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  initShortcuts({
    approve:        () => cmgr.activateCurrentStatus('approved'),
    reject:         () => cmgr.activateCurrentStatus('rejected'),
    excludeSubject: () => cmgr.activateCurrentStatus('excluded_subject'),
    excludeStaff:   () => cmgr.activateCurrentStatus('excluded_staff'),
    flag:           () => cmgr.activateCurrentStatus('flagged'),
    next:           () => cmgr.activateNext(),
    prev:           () => cmgr.activatePrev(),
    zoomIn:         () => doZoom('in'),
    zoomOut:        () => doZoom('out'),
    drawMode:       () => toggleDrawMode(),
    toggleLegend:   () => { legendPanel?.classList.toggle('hidden'); pageNavPanel?.classList.add('hidden'); },
    togglePageNav:  () => { pageNavPanel?.classList.toggle('hidden'); legendPanel?.classList.add('hidden'); },
    approveAll:     async () => {
      const ids = cmgr.getFilteredCandidates().map(c => c.id);
      await api.batchUpdate(sarId, ids, 'approved');
      await loadCandidates();
      viewer.drawOverlay(cmgr.getAll());
    },
    rejectAll: async () => {
      const ids = cmgr.getFilteredCandidates().map(c => c.id);
      await api.batchUpdate(sarId, ids, 'rejected');
      await loadCandidates();
      viewer.drawOverlay(cmgr.getAll());
    },
    closePanels: () => {
      legendPanel?.classList.add('hidden');
      pageNavPanel?.classList.add('hidden');
      settingsModal?.classList.add('hidden');
    },
  });
});
