/** SAR Redact v2 — filter state */

export class FilterManager {
  constructor(onFilterChange) {
    this.onFilterChange = onFilterChange;
    this.filter = { status: null, search: '' };
    this.sort   = 'page';
  }

  setFilter(status) {
    this.filter.status = (status === 'all' || status === this.filter.status) ? null : status;
    this._emit();
  }

  setSearch(text) {
    this.filter.search = text;
    this._emit();
  }

  setSort(sort) {
    this.sort = sort;
    this._emit();
  }

  _emit() {
    this.onFilterChange({ filter: { ...this.filter }, sort: this.sort });
  }

  applyFilter(candidates) {
    let r = candidates.slice();
    const { status, search } = this.filter;
    const REVIEWED = new Set(['auto_redact','approved','rejected','excluded_subject','excluded_staff']);
    if (status === 'pending') r = r.filter(c => !REVIEWED.has(c.status) && c.status !== 'flagged');
    else if (status)          r = r.filter(c => c.status === status);
    if (search) {
      const q = search.toLowerCase();
      r = r.filter(c => c.text.toLowerCase().includes(q) || c.category.includes(q));
    }
    const ORDER = ['flagged','auto_redact','approved','rejected','excluded_subject','excluded_staff'];
    if (this.sort === 'confidence')  r.sort((a,b) => b.confidence - a.confidence);
    else if (this.sort === 'status') r.sort((a,b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.page_num - b.page_num);
    else                             r.sort((a,b) => a.page_num - b.page_num || a.y0 - b.y0);
    return r;
  }

  getFilteredStats(candidates) {
    return {
      showing: this.applyFilter(candidates).length,
      total:   candidates.length,
    };
  }
}
