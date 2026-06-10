/** SAR Redact v2 — manual redaction draw mode */

export class DrawManager {
  constructor(containerEl, onDraw) {
    this.container = containerEl;
    this.onDraw    = onDraw;
    this.enabled   = false;
    this.zoom      = 1.0;
    this._rect     = null;
    this._start    = null;
    this._bound    = {
      down:  this._onDown.bind(this),
      move:  this._onMove.bind(this),
      up:    this._onUp.bind(this),
      tdown: this._onTouchDown.bind(this),
      tmove: this._onTouchMove.bind(this),
      tup:   this._onTouchUp.bind(this),
    };
  }

  setZoom(z) { this.zoom = z; }

  enable() {
    if (this.enabled) return;
    this.enabled = true;
    this.container.style.cursor = 'crosshair';
    this.container.addEventListener('mousedown',  this._bound.down);
    this.container.addEventListener('mousemove',  this._bound.move);
    this.container.addEventListener('mouseup',    this._bound.up);
    this.container.addEventListener('touchstart', this._bound.tdown, { passive: false });
    this.container.addEventListener('touchmove',  this._bound.tmove, { passive: false });
    this.container.addEventListener('touchend',   this._bound.tup);
  }

  disable() {
    if (!this.enabled) return;
    this.enabled = false;
    this.container.style.cursor = '';
    this.container.removeEventListener('mousedown',  this._bound.down);
    this.container.removeEventListener('mousemove',  this._bound.move);
    this.container.removeEventListener('mouseup',    this._bound.up);
    this.container.removeEventListener('touchstart', this._bound.tdown);
    this.container.removeEventListener('touchmove',  this._bound.tmove);
    this.container.removeEventListener('touchend',   this._bound.tup);
    this._removeRect();
  }

  _coords(e) {
    const cr = this.container.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - cr.left, y: clientY - cr.top };
  }

  _onDown(e) { if (e.button !== 0) return; this._start = this._coords(e); this._createRect(this._start.x, this._start.y); }
  _onMove(e) { if (!this._start) return; this._updateRect(this._start, this._coords(e)); }
  _onUp(e)   { if (!this._start) return; this._finish(this._start, this._coords(e)); this._start = null; }
  _onTouchDown(e) { e.preventDefault(); this._start = this._coords(e); this._createRect(this._start.x, this._start.y); }
  _onTouchMove(e) { e.preventDefault(); if (!this._start) return; this._updateRect(this._start, this._coords(e)); }
  _onTouchUp(e)   { if (!this._start) return; this._finish(this._start, this._coords(e)); this._start = null; }

  _createRect(x, y) {
    this._removeRect();
    const r = document.createElement('div');
    r.className = 'draw-rect';
    r.style.cssText = `left:${x}px;top:${y}px;width:0;height:0;`;
    this.container.appendChild(r);
    this._rect = r;
  }

  _updateRect(start, cur) {
    if (!this._rect) return;
    const x = Math.min(start.x, cur.x), y = Math.min(start.y, cur.y);
    const w = Math.abs(cur.x - start.x), h = Math.abs(cur.y - start.y);
    this._rect.style.left   = x + 'px';
    this._rect.style.top    = y + 'px';
    this._rect.style.width  = w + 'px';
    this._rect.style.height = h + 'px';
  }

  _finish(start, end) {
    const w = Math.abs(end.x - start.x), h = Math.abs(end.y - start.y);
    this._removeRect();
    if (w < 8 || h < 8) return;  // too small — ignore
    const z = this.zoom || 1;
    this.onDraw({
      x0: Math.min(start.x, end.x) / z,
      y0: Math.min(start.y, end.y) / z,
      x1: Math.max(start.x, end.x) / z,
      y1: Math.max(start.y, end.y) / z,
    });
  }

  _removeRect() {
    if (this._rect) { this._rect.remove(); this._rect = null; }
  }
}
