/** SAR Redact v2 — keyboard shortcuts */

const IGNORED_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export function initShortcuts(callbacks) {
  const {
    approve, reject, excludeSubject, excludeStaff, flag,
    next, prev, zoomIn, zoomOut, drawMode,
    toggleLegend, togglePageNav, approveAll, rejectAll,
    manualMode, closePanels
  } = callbacks;

  function handler(e) {
    const tag = document.activeElement?.tagName;
    if (IGNORED_TAGS.has(tag)) return;
    const k = e.key;
    const ctrl = e.ctrlKey || e.metaKey;

    if (ctrl && k === 'a') { e.preventDefault(); approveAll?.(); return; }
    if (ctrl && k === 'r') { e.preventDefault(); rejectAll?.(); return; }

    switch (k) {
      case 'a': case 'A': approve?.(); break;
      case 'r': case 'R': reject?.(); break;
      case 'x': case 'X': excludeSubject?.(); break;
      case 't': case 'T': excludeStaff?.(); break;
      case 'f': case 'F': flag?.(); break;
      case 's': case 'S': case 'j': case 'J': case 'ArrowRight': next?.(); break;
      case 'k': case 'K': case 'ArrowLeft': prev?.(); break;
      case '+': case '=': zoomIn?.(); break;
      case '-': case '_': zoomOut?.(); break;
      case 'd': case 'D': drawMode?.(); break;
      case 'l': case 'L': toggleLegend?.(); break;
      case 'n': case 'N': togglePageNav?.(); break;
      case 'm': case 'M': manualMode?.(); break;
      case 'Escape': closePanels?.(); break;
    }
  }

  document.addEventListener('keydown', handler);
  return () => document.removeEventListener('keydown', handler);
}
