/** SAR Redact v2 — PDF viewer
 *
 * Coordinate system:
 *   - PDF coordinates (x0,y0,x1,y1) are in PDF points (72pt = 1 inch).
 *   - render_page_image() renders at zoom=2.0, so image pixels = PDF points × 2.
 *   - We fetch page dimensions in points and use those as the normalisation
 *     denominator, so overlay rects land exactly on the right text regardless
 *     of zoom level or image size.
 */

const CATEGORY_COLOURS = {
  person_name:   'rgba(248,113,113,0.42)',
  nhs_number:    'rgba(167,139,250,0.48)',
  address:       'rgba(74,222,128,0.38)',
  phone_number:  'rgba(74,127,184,0.55)',
  postcode:      'rgba(251,191,36,0.44)',
  email:         'rgba(26,138,158,0.55)',
  date_of_birth: 'rgba(196,51,78,0.48)',
  safeguarding:  'rgba(248,113,113,0.65)',
  sexual_health: 'rgba(124,74,158,0.55)',
  custom_word:   'rgba(201,107,26,0.55)',
  manual:        'rgba(251,191,36,0.58)',
  default:       'rgba(74,127,184,0.38)',
};

const STATUS_OPACITY = {
  approved:         1.0,
  auto_redact:      0.85,
  flagged:          1.0,
  rejected:         0.22,
  excluded_subject: 0.30,
  excluded_staff:   0.30,
};

export class PdfViewer {
  constructor(canvasEl, overlayEl, sarId) {
    this.canvas   = canvasEl;
    this.overlay  = overlayEl;
    this.sarId    = sarId;
    this.filename = null;
    this.zoom     = 1.0;
    this._totalPages   = 0;
    this._currentPage  = 0;
    this._pageCountCache = {};
    this._pageDimsCache  = {};   // { "filename:page": {width, height} }
    this._candidates   = [];
    // PDF point dimensions of the currently displayed page
    this._pdfW = 595;
    this._pdfH = 842;
  }

  async loadFile(filename) {
    this.filename    = filename;
    this._currentPage = 0;
    this._totalPages  = this._pageCountCache[filename] ?? 0;
    if (!this._totalPages) {
      const d = await fetch(
        `/api/sar/${this.sarId}/page-count/${encodeURIComponent(filename)}`
      ).then(r => r.json()).catch(() => ({ page_count: 1 }));
      this._totalPages = d.page_count || 1;
      this._pageCountCache[filename] = this._totalPages;
    }
    await this.goToPage(0);
  }

  async goToPage(n) {
    if (!this.filename) return;
    n = Math.max(0, Math.min(n, this._totalPages - 1));
    this._currentPage = n;
    await this._fetchDims(this.filename, n);
    await this._render();
    this.drawOverlay(this._candidates);
    return n;
  }

  async _fetchDims(filename, page) {
    const key = `${filename}:${page}`;
    if (this._pageDimsCache[key]) {
      const d = this._pageDimsCache[key];
      this._pdfW = d.width;
      this._pdfH = d.height;
      return;
    }
    try {
      const d = await fetch(
        `/api/sar/${this.sarId}/page-dims/${encodeURIComponent(filename)}/${page}`
      ).then(r => r.json());
      this._pdfW = d.width  || 595;
      this._pdfH = d.height || 842;
      this._pageDimsCache[key] = { width: this._pdfW, height: this._pdfH };
    } catch {
      this._pdfW = 595;
      this._pdfH = 842;
    }
  }

  async _render() {
    const url = `/api/sar/${this.sarId}/page-image/${encodeURIComponent(this.filename)}/${this._currentPage}`;
    await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const w = Math.round(img.naturalWidth  * this.zoom);
        const h = Math.round(img.naturalHeight * this.zoom);
        this.canvas.width  = w;
        this.canvas.height = h;
        this.canvas.style.width  = w + 'px';
        this.canvas.style.height = h + 'px';
        const ctx = this.canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        this.overlay.setAttribute('width',  w);
        this.overlay.setAttribute('height', h);
        this.overlay.style.width  = w + 'px';
        this.overlay.style.height = h + 'px';
        // Pixel dimensions of the rendered image before user zoom
        this._renderedW = img.naturalWidth;
        this._renderedH = img.naturalHeight;
        resolve();
      };
      img.onerror = reject;
      img.src = url;
    });
  }

  drawOverlay(candidates) {
    this._candidates = candidates || [];
    if (!this.overlay) return;

    const pageCands = this._candidates.filter(
      c => c.source_file === this.filename && c.page_num === this._currentPage
    );

    // Scale factor: PDF points → canvas pixels
    // renderedW = pdfW * renderZoom (2.0 in serve.py)
    // canvasW   = renderedW * userZoom
    // So: canvasW / pdfW = renderZoom * userZoom
    const scaleX = this.canvas.width  / this._pdfW;
    const scaleY = this.canvas.height / this._pdfH;

    const svg = pageCands.map(c => {
      const colour  = CATEGORY_COLOURS[c.category] || CATEGORY_COLOURS.default;
      const opacity = STATUS_OPACITY[c.status] ?? 1.0;
      const x = (c.x0 * scaleX).toFixed(1);
      const y = (c.y0 * scaleY).toFixed(1);
      const w = Math.max((c.x1 - c.x0) * scaleX, 4).toFixed(1);
      const h = Math.max((c.y1 - c.y0) * scaleY, 4).toFixed(1);
      const stroke = colour.replace(/[\d.]+\)$/, '0.9)');
      return `<rect data-cid="${c.id}"
        x="${x}" y="${y}" width="${w}" height="${h}"
        fill="${colour}" stroke="${stroke}" stroke-width="1.5"
        opacity="${opacity}" rx="2" style="cursor:pointer;" />`;
    }).join('');

    this.overlay.innerHTML = svg;

    this.overlay.querySelectorAll('rect[data-cid]').forEach(r => {
      r.addEventListener('click', () => {
        const ev = new CustomEvent('candidateclick', { detail: r.dataset.cid, bubbles: true });
        this.overlay.dispatchEvent(ev);
      });
    });
  }

  highlightCandidate(candidateId) {
    this.overlay.querySelectorAll('rect').forEach(r => {
      const active = r.dataset.cid === candidateId;
      r.setAttribute('stroke-width',   active ? '3' : '1.5');
      r.setAttribute('stroke-opacity', active ? '1' : '0.9');
    });
  }

  async scrollToCandidate(candidate) {
    if (!candidate) return;
    if (candidate.source_file !== this.filename || candidate.page_num !== this._currentPage) {
      if (candidate.source_file !== this.filename) {
        await this.loadFile(candidate.source_file);
      } else {
        await this.goToPage(candidate.page_num);
      }
    }
    this.highlightCandidate(candidate.id);
    const rect = this.overlay.querySelector(`rect[data-cid="${candidate.id}"]`);
    if (rect) {
      const container = this.canvas.closest('.pdf-scroll');
      if (container) {
        const y = parseFloat(rect.getAttribute('y')) + this.canvas.offsetTop;
        container.scrollTo({ top: y - 120, behavior: 'smooth' });
      }
    }
  }

  zoomIn()  { this.setZoom(Math.min(this.zoom * 1.2, 3.0)); }
  zoomOut() { this.setZoom(Math.max(this.zoom / 1.2, 0.3)); }

  async setZoom(scale) {
    this.zoom = scale;
    if (this.filename) {
      await this._render();
      this.drawOverlay(this._candidates);
    }
  }

  get currentPage() { return this._currentPage; }
  get totalPages()  { return this._totalPages;  }
  get currentFile() { return this.filename;     }
}
