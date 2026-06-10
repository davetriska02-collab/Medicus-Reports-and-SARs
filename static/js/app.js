/** SAR Redact v2 — new SAR creation page */

const files = [];
const uploadZone = document.getElementById('upload-zone');
const fileInput  = document.getElementById('file-input');
const fileChips  = document.getElementById('file-chips');

// ── Upload zone ────────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => addFiles(fileInput.files));
uploadZone.addEventListener('dragover',  e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', ()  => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  addFiles(e.dataTransfer.files);
});

function addFiles(fileList) {
  for (const f of fileList) {
    if (!files.find(x => x.name === f.name)) files.push(f);
  }
  renderChips();
  clearFileError();
}

function removeFile(i) { files.splice(i, 1); renderChips(); }

function renderChips() {
  fileChips.innerHTML = files.map((f, i) => {
    const ext = f.name.split('.').pop().toUpperCase();
    return `<div class="file-chip">
      <span class="file-chip-ext">${ext}</span>
      ${f.name}
      <span class="file-chip-remove" onclick="removeFile(${i})">×</span>
    </div>`;
  }).join('');
}

function clearFileError() {
  const el = document.getElementById('file-error');
  if (el) el.style.display = 'none';
}

// ── Aliases ────────────────────────────────────────────────────────────────
function addAlias() {
  const list = document.getElementById('alias-list');
  const row  = document.createElement('div');
  row.className = 'alias-row';
  const idx = list.children.length;
  row.innerHTML = `<input type="text" class="alias-input" placeholder="Alias or previous name">
    <button type="button" class="alias-remove" onclick="this.parentElement.remove()">×</button>`;
  list.appendChild(row);
  row.querySelector('input').focus();
}

function getAliases() {
  return [...document.querySelectorAll('.alias-input')]
    .map(i => i.value.trim())
    .filter(Boolean);
}

// ── Submit ─────────────────────────────────────────────────────────────────
function submitSar() {
  const fullName = document.getElementById('full_name').value.trim();
  if (!fullName) { showError('submit-error', 'Subject full name is required.'); return; }
  if (!files.length) { showFileError('At least one file is required.'); return; }

  const fd = new FormData();
  fd.append('full_name',    fullName);
  fd.append('first_name',   document.getElementById('first_name').value.trim());
  fd.append('last_name',    document.getElementById('last_name').value.trim());
  fd.append('nhs_number',   document.getElementById('nhs_number').value.trim());
  fd.append('date_of_birth',document.getElementById('date_of_birth').value);
  fd.append('address',      document.getElementById('address').value.trim());
  fd.append('phone',        document.getElementById('phone').value.trim());
  fd.append('email',        document.getElementById('email').value.trim());
  fd.append('aliases',      JSON.stringify(getAliases()));
  fd.append('request_date', document.getElementById('request_date')?.value || '');
  fd.append('id_verified',  document.getElementById('id_verified')?.value.trim() || '');
  fd.append('scope_notes',  document.getElementById('scope_notes')?.value.trim() || '');
  files.forEach(f => fd.append('pdf_files', f));

  document.getElementById('submit-btn').disabled = true;
  document.getElementById('submit-btn').textContent = 'Uploading…';
  document.getElementById('main-form').style.display = 'none';
  document.getElementById('progress-card').style.display = 'block';

  fetch('/api/sar/create', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      if (data.error) { showSubmitError(data.error); return; }
      startJobStream(data.job_id);
    })
    .catch(err => showSubmitError(err.message));
}

function startJobStream(jobId) {
  const es = new EventSource('/api/job/' + jobId + '/stream');
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    const pct = Math.round((ev.progress || 0) * 100);
    document.getElementById('job-fill').style.width = pct + '%';
    document.getElementById('job-pct').textContent  = pct + '%';
    if (ev.step) document.getElementById('job-step').textContent = ev.step;
    if (ev.done) {
      es.close();
      window.location.href = '/review/' + ev.sar_id;
    }
    if (ev.error) {
      es.close();
      showSubmitError(ev.error);
      document.getElementById('main-form').style.display = 'grid';
      document.getElementById('progress-card').style.display = 'none';
      document.getElementById('submit-btn').disabled = false;
      document.getElementById('submit-btn').textContent = 'Start SAR Analysis';
    }
  };
  es.onerror = () => {
    es.close();
    showSubmitError('Connection lost. Please try again.');
    document.getElementById('main-form').style.display = 'grid';
    document.getElementById('progress-card').style.display = 'none';
    document.getElementById('submit-btn').disabled = false;
    document.getElementById('submit-btn').textContent = 'Start SAR Analysis';
  };
}

function showError(id, msg) {
  const el = document.getElementById(id);
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}
function showFileError(msg) {
  const el = document.getElementById('file-error');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}
function showSubmitError(msg) {
  showError('submit-error', msg);
  document.getElementById('job-step').textContent = 'Error: ' + msg;
  document.getElementById('job-step').style.color = 'var(--red)';
}

// Default request_date to today
const _rdInput = document.getElementById('request_date');
if (_rdInput && !_rdInput.value) {
  _rdInput.value = new Date().toISOString().slice(0, 10);
}

// Auto-fill full_name from first+last
['first_name','last_name'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', () => {
    const fn = document.getElementById('first_name').value.trim();
    const ln = document.getElementById('last_name').value.trim();
    const full = document.getElementById('full_name');
    if (full && !full._userEdited) full.value = [fn, ln].filter(Boolean).join(' ');
  });
});
document.getElementById('full_name')?.addEventListener('input', function() {
  this._userEdited = this.value !== '';
});
