/** SAR Redact v2 — candidate list */

const STATUS_LABEL = {
  auto_redact:      'Auto',
  approved:         'Approved',
  rejected:         'Kept',
  excluded_subject: 'Excl. Subject',
  excluded_staff:   'Excl. Staff',
  flagged:          'Flagged',
};

const REVIEWED_STATUSES = new Set(['auto_redact','approved','rejected','excluded_subject','excluded_staff']);

export class CandidateManager {
  constructor(listEl, progressEl, reviewedLabelEl, onAction) {
    this.listEl      = listEl;
    this.progressEl  = progressEl;
    this.labelEl     = reviewedLabelEl;
    this.onAction    = onAction;   // ({candidateId, status, action}) => void
    this._all        = [];
    this._filtered   = [];
    this._activeId   = null;
    this._filter     = { status: null, search: '' };
    this._sort       = 'page';
  }

  setCandidates(candidates) {
    this._all = candidates;
    this._applyFilter();
    this.renderList();
    this.updateProgress();
  }

  setFilter(filterObj) {
    Object.assign(this._filter, filterObj);
    this._applyFilter();
    this.renderList();
  }

  setSort(sort) {
    this._sort = sort;
    this._applyFilter();
    this.renderList();
  }

  _applyFilter() {
    let cands = this._all.slice();
    const { status, search } = this._filter;
    if (status === 'pending') {
      cands = cands.filter(c => !REVIEWED_STATUSES.has(c.status) && c.status !== 'flagged');
    } else if (status) {
      cands = cands.filter(c => c.status === status);
    }
    if (search) {
      const q = search.toLowerCase();
      cands = cands.filter(c => c.text.toLowerCase().includes(q) || c.category.includes(q));
    }
    // Sort
    if (this._sort === 'confidence') {
      cands.sort((a,b) => b.confidence - a.confidence);
    } else if (this._sort === 'status') {
      const order = ['flagged','auto_redact','approved','rejected','excluded_subject','excluded_staff'];
      cands.sort((a,b) => (order.indexOf(a.status) - order.indexOf(b.status)) || a.page_num - b.page_num);
    } else {
      cands.sort((a,b) => a.page_num - b.page_num || (a.y0 - b.y0));
    }
    this._filtered = cands;
  }

  renderList() {
    if (!this._filtered.length) {
      this.listEl.innerHTML = '<div style="text-align:center;padding:28px 12px;color:var(--t5);font-size:12px;">No candidates match the current filter.</div>';
      return;
    }
    const frag = document.createDocumentFragment();
    for (const c of this._filtered) frag.appendChild(this._makeCard(c));
    this.listEl.innerHTML = '';
    this.listEl.appendChild(frag);
  }

  _makeCard(c) {
    const div = document.createElement('div');
    div.className = `candidate-card status-${c.status}${c.id === this._activeId ? ' active' : ''}`;
    div.dataset.cid = c.id;
    const hasRisk = c.risk_flags && c.risk_flags.length > 0;
    const confPct = Math.round((c.confidence || 0) * 100);
    div.innerHTML = `
      <div class="cand-header">
        <span class="cand-cat">${c.category.replace(/_/g,' ')}</span>
        <span class="cand-conf">${confPct}%${hasRisk ? ' ⚑' : ''}</span>
      </div>
      <div class="cand-text${hasRisk ? ' risk' : ''}" title="${c.text}">${_truncate(c.text, 80)}</div>
      <div style="font-family:var(--mono);font-size:9px;color:var(--t5);margin-bottom:6px;">p${c.page_num + 1}</div>
      <div class="cand-actions">
        <button class="cand-btn cand-btn-approve${c.status==='approved'?' sel':''}" data-action="approved">Approve</button>
        <button class="cand-btn cand-btn-reject${c.status==='rejected'?' sel':''}"  data-action="rejected">Keep</button>
        <button class="cand-btn cand-btn-exsub${c.status==='excluded_subject'?' sel':''}"   data-action="excluded_subject">Excl.S</button>
        <button class="cand-btn cand-btn-exstaff${c.status==='excluded_staff'?' sel':''}" data-action="excluded_staff">Excl.C</button>
      </div>`;

    // Card click → jump to page
    div.addEventListener('click', e => {
      if (e.target.matches('button[data-action]')) return;
      this.setActiveCard(c.id);
      this.onAction({ candidateId: c.id, action: 'select', candidate: c });
    });

    // Button clicks
    div.querySelectorAll('button[data-action]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const newStatus = btn.dataset.action;
        this.updateCandidate(c.id, newStatus);
        this.onAction({ candidateId: c.id, action: 'status', status: newStatus, candidate: c });
      });
    });

    return div;
  }

  setActiveCard(candidateId) {
    this._activeId = candidateId;
    this.listEl.querySelectorAll('.candidate-card').forEach(el => {
      el.classList.toggle('active', el.dataset.cid === candidateId);
    });
    const active = this.listEl.querySelector(`.candidate-card[data-cid="${candidateId}"]`);
    if (active) active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  updateCandidate(candidateId, newStatus) {
    const c = this._all.find(x => x.id === candidateId);
    if (c) c.status = newStatus;
    // Re-render that card in place
    const el = this.listEl.querySelector(`[data-cid="${candidateId}"]`);
    if (el) {
      const newEl = this._makeCard(c);
      el.replaceWith(newEl);
    }
    this.updateProgress();
    this._applyFilter();
  }

  updateProgress() {
    const total    = this._all.length;
    const reviewed = this._all.filter(c => REVIEWED_STATUSES.has(c.status)).length;
    const flagged  = this._all.filter(c => c.status === 'flagged').length;
    const pct = total ? Math.round(reviewed / total * 100) : 0;
    if (this.progressEl) this.progressEl.style.width = pct + '%';
    if (this.labelEl)    this.labelEl.textContent = `${reviewed}/${total}${flagged ? ` · ${flagged} flagged` : ''}`;
  }

  getStats() {
    const c = this._all;
    return {
      total:    c.length,
      reviewed: c.filter(x => REVIEWED_STATUSES.has(x.status)).length,
      flagged:  c.filter(x => x.status === 'flagged').length,
      auto:     c.filter(x => x.status === 'auto_redact').length,
      approved: c.filter(x => x.status === 'approved').length,
    };
  }

  getActiveIndex() { return this._filtered.findIndex(c => c.id === this._activeId); }
  getFilteredCandidates() { return this._filtered; }
  getAll() { return this._all; }

  activateNext() {
    const idx = this.getActiveIndex();
    const next = this._filtered[idx + 1];
    if (next) { this.setActiveCard(next.id); this.onAction({ candidateId: next.id, action: 'select', candidate: next }); }
  }

  activatePrev() {
    const idx = this.getActiveIndex();
    const prev = this._filtered[idx - 1];
    if (prev) { this.setActiveCard(prev.id); this.onAction({ candidateId: prev.id, action: 'select', candidate: prev }); }
  }

  getActiveCandidate() { return this._all.find(c => c.id === this._activeId) || null; }

  activateCurrentStatus(status) {
    const c = this.getActiveCandidate();
    if (!c) return;
    this.updateCandidate(c.id, status);
    this.onAction({ candidateId: c.id, action: 'status', status, candidate: c });
    this.activateNext();
  }
}

function _truncate(str, max) {
  if (!str) return '';
  if (str.length <= max) return str;
  return str.slice(0, max - 1) + '…';
}
