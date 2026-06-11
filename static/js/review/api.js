/** SAR Redact v2 — API module */

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function _json(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.error || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const getCandidates = (sarId, sourceFile) => {
  const qs = sourceFile ? `?source_file=${encodeURIComponent(sourceFile)}` : '';
  return _json(`/api/sar/${sarId}/candidates${qs}`);
};

export const updateCandidate = (sarId, candidateId, data) =>
  _json(`/api/sar/${sarId}/candidate/${candidateId}/update`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data)
  });

export const batchUpdate = (sarId, candidateIds, status) =>
  _json(`/api/sar/${sarId}/batch-update`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ candidate_ids: candidateIds, status })
  });

export const batchByText = (sarId, text, status) =>
  _json(`/api/sar/${sarId}/batch-by-text`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ text, status })
  });

export const finalise = (sarId) =>
  _json(`/api/sar/${sarId}/finalise`, { method: 'POST' });

export const getNotes = (sarId) => _json(`/api/sar/${sarId}/notes`);

export const updateNotes = (sarId, notes) =>
  _json(`/api/sar/${sarId}/notes`, {
    method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify({ notes })
  });

export const manualRedact = (sarId, data) =>
  _json(`/api/sar/${sarId}/manual-redact`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data)
  });

export const deletePage = (sarId, filename, pageNum) =>
  _json(`/api/sar/${sarId}/delete-page`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ filename, page_num: pageNum })
  });

export const pauseClock = (sarId) =>
  _json(`/api/sar/${sarId}/pause-clock`, { method: 'POST' });

export const resumeClock = (sarId, reason = '') =>
  _json(`/api/sar/${sarId}/resume-clock`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ reason })
  });

export const allocate = (sarId, userId) =>
  _json(`/api/sar/${sarId}/allocate`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ user_id: userId })
  });

export const updateWorkflow = (sarId, status) =>
  _json(`/api/sar/${sarId}/workflow`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ status })
  });

export const archiveSar = (sarId) =>
  _json(`/api/sar/${sarId}/archive`, { method: 'POST' });

export const unarchiveSar = (sarId) =>
  _json(`/api/sar/${sarId}/unarchive`, { method: 'POST' });

export const redetect = (sarId, subjectPatch = {}) =>
  _json(`/api/sar/${sarId}/redetect`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ subject: subjectPatch })
  });

export const getDetectionSettings = (sarId) =>
  _json(`/api/sar/${sarId}/detection-settings`);

export const updateDetectionSettings = (sarId, settings) =>
  _json(`/api/sar/${sarId}/detection-settings`, {
    method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(settings)
  });

export const getPageCount = (sarId, filename) =>
  _json(`/api/sar/${sarId}/page-count/${encodeURIComponent(filename)}`);

export const resolveFailure = (sarId, candId, dismissed = false) =>
  _json(`/api/sar/${sarId}/failures/${candId}/resolve`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ dismissed }),
  });

export const findOnPage = (sarId, filename, page, text) =>
  _json(`/api/sar/${sarId}/find-on-page?file=${encodeURIComponent(filename)}&page=${page}&text=${encodeURIComponent(text)}`);
