import io, os, re, json, shutil, time, zipfile, threading, logging
from logging.handlers import RotatingFileHandler
from queue import Queue, Empty
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import (Flask, render_template, request, jsonify, send_file,
                   Response, redirect, url_for, session, g)
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

APP_VERSION = "2.1.0"

from sar.updater import start as _start_update_check, get_result as _get_update_result
from sar.practice_config import get_config as _get_practice_config, save_config as _save_practice_config, is_default as _practice_is_default
_start_update_check(APP_VERSION)
SARPACK_FORMAT_VERSION = "1"

from sar.models import (SARRequest, SubjectDetails, RedactionStatus, PIICategory,
                         RedactionCandidate, DetectionSettings)
from sar.pdf_parser import extract_text_spans, render_page_image, get_page_count, get_full_page_text, get_page_dimensions
from sar.detector import detect_pii
from sar.redactor import apply_redactions
from sar.redaction_log import generate_redaction_log
from sar.staff_list import get_staff_list, add_staff_member, remove_staff_member
from sar.custom_words import get_custom_words, add_custom_word, remove_custom_word
from sar.risk_words import check_text_for_risk
from sar.date_extractor import extract_document_date, extract_date_from_filename
from sar.keyword_scanner import scan_keywords
from sar.users import (get_user_by_id, authenticate, create_user, get_all_users,
                        get_gp_users, set_password, delete_user, users_file_exists,
                        get_user_by_username, UsersFileCorrupt)
from sar.fsutil import atomic_write_json, unique_path
from sar.report_templates import (get_all_templates, get_template, save_custom_template,
                                    delete_custom_template)
from sar.report_store import save_report, load_report, load_all_reports, delete_report
from sar.evidence_extractor import extract_evidence
from sar.report_generator import generate_report_pdf

app = Flask(__name__)

# Resolve BASE_DIR to an absolute path regardless of how Python was invoked.
# os.path.dirname(__file__) can return '' when using the embedded Python runtime.
import pathlib
BASE_DIR = pathlib.Path(__file__).resolve().parent

_SECRET_KEY_PATH = BASE_DIR / "data" / ".secret_key"
def _get_or_create_secret_key():
    os.makedirs(_SECRET_KEY_PATH.parent, exist_ok=True)
    if _SECRET_KEY_PATH.exists():
        with open(str(_SECRET_KEY_PATH), "rb") as f: return f.read()
    key = os.urandom(32)
    with open(str(_SECRET_KEY_PATH), "wb") as f: f.write(key)
    try:
        os.chmod(str(_SECRET_KEY_PATH), 0o600)  # owner read/write only
    except Exception:
        pass  # Windows doesn't support chmod — acceptable
    return key
app.secret_key = _get_or_create_secret_key()

# ── Cookie security ────────────────────────────────────────────────────────
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,
    SESSION_COOKIE_SAMESITE  = 'Strict',
    SESSION_COOKIE_SECURE    = False,   # Set True when deploying with HTTPS
    SESSION_COOKIE_NAME      = 'sar_session',
    PERMANENT_SESSION_LIFETIME = 28800, # 8 hours
    MAX_CONTENT_LENGTH       = 1024 * 1024 * 1024,  # 1 GB request cap
)

# ── Logging ────────────────────────────────────────────────────────────────
_LOG_DIR = BASE_DIR / "data" / "logs"
os.makedirs(str(_LOG_DIR), exist_ok=True)
_log_handler = RotatingFileHandler(str(_LOG_DIR / "sar-redact.log"),
                                   maxBytes=2_000_000, backupCount=5, encoding="utf-8")
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler, logging.StreamHandler()])
log = logging.getLogger("sar")

@app.template_filter('fdate')
def format_date(value):
    if not value: return ''
    try:
        dt = datetime.fromisoformat(str(value)[:10])
        import platform
        fmt = '%#d %b %Y' if platform.system() == 'Windows' else '%-d %b %Y'
        return dt.strftime(fmt)
    except Exception: return str(value)[:10]

# Jobs
_job_queues: dict[str, Queue] = {}
def _new_job():
    import uuid as _u
    jid = str(_u.uuid4())[:12]; q = Queue(); _job_queues[jid] = q; return jid, q
def _emit(q, progress, step):
    q.put({"progress": round(progress, 3), "step": step})

# Paths
UPLOAD_DIR  = str(BASE_DIR / "uploads")
OUTPUT_DIR  = str(BASE_DIR / "output")
SAR_DATA_DIR= str(BASE_DIR / "data" / "sars")
REPORT_UPLOAD_DIR = str(BASE_DIR / "uploads" / "reports")
REPORT_OUTPUT_DIR = str(BASE_DIR / "output" / "reports")
for _d in (UPLOAD_DIR, OUTPUT_DIR, SAR_DATA_DIR, REPORT_UPLOAD_DIR, REPORT_OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf","tif","tiff","rtf","txt","zip","png","jpg","jpeg","html","htm","cdax"}
def allowed_file(f): return "." in f and f.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS
def _sar_dir(sid): return os.path.join(UPLOAD_DIR, sid)
def _resolve_path(sid, stored):
    """Resolve a stored filename to an absolute path.
    
    Accepts basenames only. Legacy absolute paths from v1 SARs are
    accepted but logged; they will be migrated to basenames on next _save().
    Any path that escapes the expected upload directory is rejected.
    """
    if os.path.isabs(stored):
        # Legacy v1 path — extract basename for safety
        basename = os.path.basename(stored)
    else:
        basename = os.path.basename(stored)  # strip any ../ traversal attempts
    resolved = os.path.join(_sar_dir(sid), basename)
    # Confirm resolved path stays inside the expected upload directory
    upload_root = os.path.realpath(UPLOAD_DIR)
    if not os.path.realpath(resolved).startswith(upload_root):
        raise ValueError(f"Path traversal attempt rejected: {stored!r}")
    return resolved

# Thread-safe store
active_requests: dict[str, SARRequest] = {}
_ar_lock = threading.Lock()
def _get(sid):
    with _ar_lock: return active_requests.get(sid)
def _set(sid, sar):
    with _ar_lock: active_requests[sid] = sar
def _del(sid):
    with _ar_lock:
        active_requests.pop(sid, None)
        _sar_locks.pop(sid, None)
def _all():
    with _ar_lock: return list(active_requests.values())

# Per-SAR locks: serialise mutate-and-save so two concurrent reviewers can't
# interleave a half-mutated snapshot into the JSON file.
_sar_locks: dict[str, threading.Lock] = {}
def _lock_for(sid) -> threading.Lock:
    with _ar_lock:
        return _sar_locks.setdefault(sid, threading.Lock())

# Serialise
def _to_dict(sar):
    return {
        "id": sar.id, "created_at": sar.created_at, "last_modified": sar.last_modified,
        "status": sar.status, "archived": getattr(sar,"archived",False),
        "redaction_failures": getattr(sar,"redaction_failures",[]),
        "due_date": sar.due_date, "notes": sar.notes, "workflow_status": sar.workflow_status,
        "allocated_to": sar.allocated_to, "allocated_to_name": sar.allocated_to_name,
        "clock_paused": sar.clock_paused, "paused_at": sar.paused_at,
        "total_paused_days": sar.total_paused_days, "pause_log": sar.pause_log,
        "subject": {k: getattr(sar.subject, k) for k in
                    ("full_name","first_name","last_name","nhs_number","date_of_birth",
                     "address","phone","email","aliases")},
        "detection_settings": {
            "auto_redact_threshold": sar.detection_settings.auto_redact_threshold,
            "flag_threshold": sar.detection_settings.flag_threshold,
            "enabled_categories": sar.detection_settings.enabled_categories,
        },
        "document_dates": sar.document_dates, "file_order": sar.file_order,
        "main_record_file": sar.main_record_file,
        "pdf_files": [os.path.basename(p) for p in sar.pdf_files],
        "candidates": [
            {"id":c.id,"text":c.text,"category":c.category.value,"status":c.status.value,
             "confidence":c.confidence,"page_num":c.page_num,
             "x0":c.x0,"y0":c.y0,"x1":c.x1,"y1":c.y1,
             "reason":c.reason,"exemption_code":c.exemption_code,
             "risk_flags":c.risk_flags,"source_file":c.source_file}
            for c in sar.candidates
        ],
    }

def _save(sar):
    with _lock_for(sar.id):
        sar.last_modified = datetime.now(timezone.utc).isoformat()
        atomic_write_json(os.path.join(SAR_DATA_DIR, f"{sar.id}.json"), _to_dict(sar))

def _load_all():
    for fname in os.listdir(SAR_DATA_DIR):
        if not fname.endswith(".json"): continue
        try:
            with open(os.path.join(SAR_DATA_DIR, fname)) as f: data = json.load(f)
            sid = data["id"]
            subj = SubjectDetails(**data["subject"])
            cands = [RedactionCandidate(
                id=c["id"],text=c["text"],category=PIICategory(c["category"]),
                status=RedactionStatus(c["status"]),confidence=c["confidence"],
                page_num=c["page_num"],x0=c["x0"],y0=c["y0"],x1=c["x1"],y1=c["y1"],
                reason=c["reason"],exemption_code=c.get("exemption_code",""),
                risk_flags=c.get("risk_flags",[]),source_file=c["source_file"])
                for c in data["candidates"]]
            pdf_files = [_resolve_path(sid, p) for p in data["pdf_files"]]
            sar = SARRequest(
                id=sid, created_at=data.get("created_at",""),
                last_modified=data.get("last_modified",""),
                subject=subj, pdf_files=pdf_files, candidates=cands,
                status=data["status"], due_date=data.get("due_date",""),
                notes=data.get("notes",""), workflow_status=data.get("workflow_status","new"),
                allocated_to=data.get("allocated_to",""),
                allocated_to_name=data.get("allocated_to_name",""),
                document_dates=data.get("document_dates",{}),
                file_order=data.get("file_order",[]),
                main_record_file=data.get("main_record_file",""),
                clock_paused=data.get("clock_paused",False),
                paused_at=data.get("paused_at",""),
                total_paused_days=data.get("total_paused_days",0),
                pause_log=data.get("pause_log",[]),
            )
            sar.archived = data.get("archived", False)
            sar.redaction_failures = data.get("redaction_failures", [])
            ds = data.get("detection_settings")
            if ds:
                sar.detection_settings = DetectionSettings(
                    auto_redact_threshold=ds.get("auto_redact_threshold",0.80),
                    flag_threshold=ds.get("flag_threshold",0.50),
                    enabled_categories=ds.get("enabled_categories",DetectionSettings().enabled_categories))
            if not sar.due_date: sar.compute_due_date()
            for c in cands:
                if not c.risk_flags and c.text: c.risk_flags = check_text_for_risk(c.text)
            active_requests[sid] = sar
        except Exception:
            logging.getLogger("sar").warning("Could not load %s", fname, exc_info=True)


def _migrate_absolute_paths():
    """One-time migration: rewrite any v1 absolute pdf_file paths to basenames.
    Runs at startup, silently skips SARs that are already clean.
    """
    migrated = 0
    for fname in os.listdir(SAR_DATA_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SAR_DATA_DIR, fname)
        try:
            with open(path) as f:
                data = json.load(f)
            original = data.get("pdf_files", [])
            cleaned = [os.path.basename(p) for p in original]
            if cleaned != original:
                data["pdf_files"] = cleaned
                atomic_write_json(path, data)
                migrated += 1
        except Exception:
            pass
    if migrated:
        print(f"[startup] Migrated {migrated} SAR(s) from absolute to relative paths.")

_migrate_absolute_paths()
_load_all()

# Converters (unchanged from v1)
def _tif_to_pdf(p):
    import fitz; doc=fitz.open(p); b=doc.convert_to_pdf(); doc.close()
    out=p.rsplit(".",1)[0]+".pdf"
    with open(out,"wb") as f: f.write(b)
    return out
def _txt_to_pdf(p):
    import fitz
    with open(p,"r",errors="replace") as f: text=f.read()
    doc=fitz.open(); pg=doc.new_page(); pg.insert_textbox(fitz.Rect(50,50,545,792),text,fontsize=10,fontname="helv")
    out=p.rsplit(".",1)[0]+".pdf"; doc.save(out); doc.close(); return out
def _rtf_to_pdf(p):
    from striprtf.striprtf import rtf_to_text
    with open(p,"r",errors="replace") as f: content=f.read()
    plain=rtf_to_text(content)
    import fitz; doc=fitz.open(); pg=doc.new_page()
    pg.insert_textbox(fitz.Rect(50,50,545,792),plain,fontsize=10,fontname="helv")
    out=p.rsplit(".",1)[0]+".pdf"; doc.save(out); doc.close(); return out
def _img_to_pdf(p):
    import fitz; i=fitz.open(p); b=i.convert_to_pdf(); i.close()
    d=fitz.open("pdf",b); out=p.rsplit(".",1)[0]+".pdf"; d.save(out); d.close(); return out
def _html_to_pdf(p):
    import fitz
    with open(p,"rb") as f: b=f.read()
    doc=fitz.open(stream=b,filetype="html"); out=p.rsplit(".",1)[0]+".pdf"; doc.save(out); doc.close(); return out
def _cdax_to_pdf(p):
    import fitz, xml.etree.ElementTree as ET
    try:
        tree=ET.parse(p); root=tree.getroot(); ns={"h":"urn:hl7-org:v3"}
        lines=[]
        te=root.find(".//h:title",ns) or root.find(".//title")
        if te is not None and te.text: lines.append(f"DOCUMENT: {te.text.strip()}")
        for sec in (root.findall(".//h:section",ns) or root.findall(".//section")):
            st=sec.find("h:title",ns) or sec.find("title")
            if st is not None and st.text: lines.append(f"\n{st.text.strip().upper()}")
            for tx in (sec.findall(".//h:text",ns) or sec.findall(".//text")):
                for chunk in "".join(tx.itertext()).split("\n"):
                    s=chunk.strip()
                    if s: lines.append(s)
        plain="\n".join(lines) or "(No text content)"
    except Exception: plain="(Could not parse CDA document)"
    doc=fitz.open(); pg=doc.new_page()
    pg.insert_textbox(fitz.Rect(50,50,545,792),plain,fontsize=9,fontname="helv")
    out=p.rsplit(".",1)[0]+".pdf"; doc.save(out); doc.close(); return out
def _convert_single(filepath, ext):
    m={"tif":_tif_to_pdf,"tiff":_tif_to_pdf,"rtf":_rtf_to_pdf,"txt":_txt_to_pdf,
       "png":_img_to_pdf,"jpg":_img_to_pdf,"jpeg":_img_to_pdf,
       "html":_html_to_pdf,"htm":_html_to_pdf,"cdax":_cdax_to_pdf}
    if ext=="pdf": return filepath
    fn=m.get(ext)
    return fn(filepath) if fn else filepath
# Zip extraction safety caps — one hostile/corrupt upload must not be able to
# fill the disk of a shared server.
ZIP_MAX_ENTRIES = 2000
ZIP_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024   # 4 GB uncompressed across the archive
ZIP_MAX_ENTRY_BYTES = 800 * 1024 * 1024        # 800 MB per file
def _extract_zip(zip_path, sar_dir, emit_fn=None):
    result=[]
    total=0
    with zipfile.ZipFile(zip_path,"r") as zf:
        entries=[e for e in zf.infolist()
                 if not e.filename.endswith("/") and "." in e.filename.split("/")[-1]
                 and e.filename.split(".")[-1].lower() in ALLOWED_EXTENSIONS]
        if len(entries) > ZIP_MAX_ENTRIES:
            raise ValueError(f"Zip contains too many files ({len(entries)} > {ZIP_MAX_ENTRIES})")
        for i,info in enumerate(entries):
            if info.file_size > ZIP_MAX_ENTRY_BYTES:
                raise ValueError(f"Zip entry too large: {info.filename}")
            total += info.file_size
            if total > ZIP_MAX_TOTAL_BYTES:
                raise ValueError("Zip uncompressed size exceeds limit")
            if emit_fn: emit_fn(i+1,len(entries))
            bn=secure_filename(os.path.basename(info.filename))
            if not bn: continue
            dest=unique_path(sar_dir,bn)
            with zf.open(info) as src, open(dest,"wb") as dst: shutil.copyfileobj(src,dst)
            ext=bn.rsplit(".",1)[-1].lower()
            try: result.append(_convert_single(dest,ext))
            except Exception:
                log.warning("Could not convert %s from zip", bn, exc_info=True)
    return result

# Auth
@app.before_request
def load_user():
    g.current_user=None
    try:
        uid=session.get("user_id")
        if uid: g.current_user=get_user_by_id(uid)
        no_users = not users_file_exists()
    except UsersFileCorrupt:
        # A corrupt users file must lock the app down — NOT fall through to
        # /setup where anyone on the network could create a fresh admin.
        log.error("users.json is corrupt — refusing to serve requests")
        return ("User database is corrupt or unreadable. Restore data/users.json "
                "from backup, then restart the server."), 500
    if no_users and request.endpoint not in {"login","setup","static"}:
        return redirect(url_for("setup"))
@app.context_processor
def inject_user(): return {"current_user": g.current_user}

@app.context_processor
def inject_practice(): return {"practice": _get_practice_config()}

@app.context_processor
def inject_csrf(): return {"csrf_token": _get_csrf_token}
def require_login(f):
    @wraps(f)
    def d(*a,**kw):
        if not g.current_user: return redirect(url_for("login"))
        return f(*a,**kw)
    return d
def require_admin(f):
    @wraps(f)
    def d(*a,**kw):
        if not g.current_user: return redirect(url_for("login"))
        if g.current_user.role!="admin": return render_template("403.html"),403
        return f(*a,**kw)
    return d

# Auth routes

# ── CSRF protection ────────────────────────────────────────────────────────
import secrets as _secrets

def _get_csrf_token() -> str:
    """Return (creating if needed) a CSRF token for the current session."""
    if '_csrf' not in session:
        session['_csrf'] = _secrets.token_hex(32)
    return session['_csrf']

@app.before_request
def _csrf_protect():
    """Enforce CSRF token on all mutating requests (login/setup included —
    their forms render the hidden _csrf_token field)."""
    if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
        return
    if request.endpoint == 'static':
        return
    # API routes send X-CSRF-Token header; HTML forms send _csrf_token field
    token_from_header = request.headers.get('X-CSRF-Token', '')
    token_from_form   = request.form.get('_csrf_token', '')
    token             = token_from_header or token_from_form
    session_token     = session.get('_csrf')
    if not session_token or not _secrets.compare_digest(token, session_token):
        if request.is_json or token_from_header:
            return jsonify({'error': 'CSRF validation failed'}), 403
        return render_template('403.html'), 403

# ── Login rate limiting ────────────────────────────────────────────────────
# Sliding window per (client IP, username): 5 failures in 5 minutes locks
# further attempts for the remainder of the window.
_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW_S  = 300
_login_fails: dict[tuple, list] = {}
_login_fails_lock = threading.Lock()

def _login_throttled(ip: str, username: str) -> int:
    """Seconds the caller must still wait, or 0 if allowed."""
    key = (ip, username.lower())
    now = time.time()
    with _login_fails_lock:
        attempts = [t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW_S]
        _login_fails[key] = attempts
        if len(attempts) >= _LOGIN_MAX_FAILS:
            return int(_LOGIN_WINDOW_S - (now - attempts[0])) + 1
    return 0

def _login_record_failure(ip: str, username: str):
    key = (ip, username.lower())
    with _login_fails_lock:
        _login_fails.setdefault(key, []).append(time.time())
        # Opportunistic cleanup so the dict can't grow unbounded
        if len(_login_fails) > 1000:
            cutoff = time.time() - _LOGIN_WINDOW_S
            for k in [k for k, v in _login_fails.items() if not v or v[-1] < cutoff]:
                _login_fails.pop(k, None)

def _login_clear(ip: str, username: str):
    with _login_fails_lock:
        _login_fails.pop((ip, username.lower()), None)

@app.route("/login",methods=["GET","POST"])
def login():
    if not users_file_exists(): return redirect(url_for("setup"))
    if g.current_user: return redirect(url_for("dashboard"))
    error=None
    if request.method=="POST":
        un=request.form.get("username","").strip()
        ip=request.remote_addr or "?"
        wait=_login_throttled(ip,un)
        if wait:
            error=f"Too many failed attempts. Try again in {wait} seconds."
            log.warning("Login throttled for %r from %s", un, ip)
            return render_template("login.html",error=error),429
        u=authenticate(un,request.form.get("password",""))
        if u:
            _login_clear(ip,un)
            session["user_id"]=u.id
            log.info("Login: %s from %s", un, ip)
            return redirect(url_for("dashboard"))
        _login_record_failure(ip,un)
        log.warning("Failed login for %r from %s", un, ip)
        error="Invalid username or password."
    return render_template("login.html",error=error)
@app.route("/logout",methods=["POST"])
def logout(): session.pop("user_id",None); return redirect(url_for("login"))
@app.route("/setup",methods=["GET","POST"])
def setup():
    if users_file_exists(): return redirect(url_for("login"))
    error=None
    if request.method=="POST":
        un=request.form.get("username","").strip(); dn=request.form.get("display_name","").strip()
        pw=request.form.get("password",""); cp=request.form.get("confirm_password","")
        if not un or not dn or not pw: error="All fields are required."
        elif pw!=cp: error="Passwords do not match."
        elif len(pw)<8: error="Password must be at least 8 characters."
        else: create_user(un,dn,"admin",pw,is_superuser=True); return redirect(url_for("login"))
    return render_template("setup.html",error=error)
@app.route("/account")
@require_login
def account(): return render_template("account.html")
@app.route("/account/change-password",methods=["POST"])
@require_login
def change_password():
    cur=request.form.get("current_password",""); new=request.form.get("new_password",""); conf=request.form.get("confirm_password","")
    if not check_password_hash(g.current_user.password_hash,cur): return render_template("account.html",error="Current password is incorrect.")
    if new!=conf: return render_template("account.html",error="New passwords do not match.")
    if len(new)<8: return render_template("account.html",error="Password must be at least 8 characters.")
    set_password(g.current_user.id,new); return render_template("account.html",success="Password updated.")
@app.route("/help")
@require_login
def help_page(): return render_template("help.html")
@app.route("/admin/users")
@require_admin
def admin_users():
    users=[{"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"is_superuser":u.is_superuser} for u in get_all_users()]
    return render_template("admin/users.html",users=users)
@app.route("/admin/users/create",methods=["POST"])
@require_admin
def admin_create_user():
    un=request.form.get("username","").strip(); dn=request.form.get("display_name","").strip()
    role=request.form.get("role","gp"); pw=request.form.get("password",""); su=request.form.get("is_superuser")=="on"
    errors=[]
    if not un: errors.append("Username required.")
    if not dn: errors.append("Display name required.")
    if not pw or len(pw)<8: errors.append("Password must be at least 8 characters.")
    if get_user_by_username(un): errors.append("Username already exists.")
    if errors:
        users=[{"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"is_superuser":u.is_superuser} for u in get_all_users()]
        return render_template("admin/users.html",users=users,errors=errors)
    create_user(un,dn,role,pw,su); return redirect(url_for("admin_users"))
@app.route("/admin/users/<uid>/reset-password",methods=["POST"])
@require_admin
def admin_reset_password(uid):
    pw=( request.json or {}).get("new_password","")
    if len(pw)<8: return jsonify({"error":"Password must be at least 8 characters."}),400
    if not set_password(uid,pw): return jsonify({"error":"User not found."}),404
    return jsonify({"ok":True})
@app.route("/admin/users/<uid>/delete",methods=["POST"])
@require_admin
def admin_delete_user(uid):
    if uid==g.current_user.id: return jsonify({"error":"Cannot delete your own account."}),400
    if not delete_user(uid): return jsonify({"error":"User not found."}),404
    return redirect(url_for("admin_users"))

# Page routes
@app.route("/")
@require_login
def dashboard():
    show_archived=request.args.get("archived")=="1"
    sars=sorted(_all(),key=lambda s:s.created_at,reverse=True)
    summaries=[]
    for sar in sars:
        ia=getattr(sar,"archived",False)
        if ia!=show_archived: continue
        auto=sum(1 for c in sar.candidates if c.status==RedactionStatus.AUTO_REDACT)
        flagged=sum(1 for c in sar.candidates if c.status==RedactionStatus.FLAGGED)
        approved=sum(1 for c in sar.candidates if c.status==RedactionStatus.APPROVED)
        total=len(sar.candidates)
        reviewed=sum(1 for c in sar.candidates if c.status in (
            RedactionStatus.AUTO_REDACT,RedactionStatus.APPROVED,RedactionStatus.REJECTED,
            RedactionStatus.EXCLUDED_SUBJECT,RedactionStatus.EXCLUDED_STAFF))
        summaries.append({"sar":sar,"auto":auto,"flagged":flagged,"approved":approved,
                          "file_count":len(sar.pdf_files),"total_candidates":total,
                          "reviewed":reviewed,"days_remaining":sar.days_remaining})
    all_active=[s for s in _all() if not getattr(s,"archived",False)]
    return render_template("dashboard.html",sar_summaries=summaries,gp_users=get_gp_users(),update=_get_update_result(),practice_unconfigured=_practice_is_default(),
        total_requests=len(all_active),
        reviewing_count=sum(1 for s in all_active if s.status=="reviewing"),
        complete_count=sum(1 for s in all_active if s.status=="complete"),
        overdue_count=sum(1 for s in all_active if s.days_remaining<0 and s.status!="complete"),
        archived_count=sum(1 for s in _all() if getattr(s,"archived",False)),
        show_archived=show_archived)
@app.route("/new")
@require_login
def new_sar_page(): return render_template("index.html")
@app.route("/review/<sid>")
@require_login
def review(sid):
    sar=_get(sid)
    if not sar: return "SAR not found",404
    def fi(bn):
        full=next((p for p in sar.pdf_files if os.path.basename(p)==bn),None)
        return {"name":bn,"pages":get_page_count(full) if full else 1,"date":sar.document_dates.get(bn)}
    fid=[fi(os.path.basename(f)) for f in sar.pdf_files]
    fon=sar.file_order or [os.path.basename(f) for f in sar.pdf_files]
    dm={x["name"]:x for x in fid}
    fif=[dm[bn] for bn in fon if bn in dm]
    mr=sar.main_record_file or (fon[0] if fon else "")
    return render_template("review.html",sar=sar,files_info=fid,files_info_date=fid,files_info_file=fif,main_record_file=mr)
@app.route("/complete/<sid>")
@require_login
def complete(sid):
    sar=_get(sid)
    if not sar: return "SAR not found",404
    red=sum(1 for c in sar.candidates if c.status in (RedactionStatus.AUTO_REDACT,RedactionStatus.APPROVED))
    kpt=sum(1 for c in sar.candidates if c.status==RedactionStatus.REJECTED)
    exc=sum(1 for c in sar.candidates if c.status in (RedactionStatus.EXCLUDED_SUBJECT,RedactionStatus.EXCLUDED_STAFF))
    return render_template("complete.html",sar=sar,redacted_count=red,kept_count=kpt,excluded_count=exc)
@app.route("/staff")
@require_login
def staff_page(): return render_template("staff.html")

# SSE
@app.route("/api/job/<jid>/stream")
@require_login
def job_stream(jid):
    q=_job_queues.get(jid)
    if not q: return jsonify({"error":"Job not found"}),404
    def gen():
        while True:
            try: ev=q.get(timeout=60)
            except Empty: yield ": keepalive\n\n"; continue
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("done") or ev.get("error"): _job_queues.pop(jid,None); break
    return Response(gen(),mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# SAR creation
@app.route("/api/sar/create",methods=["POST"])
@require_login
def create_sar():
    subj=SubjectDetails(
        full_name=request.form.get("full_name","").strip(),
        first_name=request.form.get("first_name","").strip(),
        last_name=request.form.get("last_name","").strip(),
        nhs_number=request.form.get("nhs_number","").strip(),
        date_of_birth=request.form.get("date_of_birth","").strip(),
        address=request.form.get("address","").strip(),
        phone=request.form.get("phone","").strip(),
        email=request.form.get("email","").strip(),
        aliases=json.loads(request.form.get("aliases","[]")),
    )
    if not subj.full_name: return jsonify({"error":"Subject full name is required"}),400
    files=request.files.getlist("pdf_files")
    if not files or all(f.filename=="" for f in files): return jsonify({"error":"At least one file is required"}),400
    sar=SARRequest(subject=subj); sar.archived=False; sar.compute_due_date()
    sd=_sar_dir(sar.id); os.makedirs(sd,exist_ok=True)
    saved=[]
    for f in files:
        if f.filename and allowed_file(f.filename):
            fn=secure_filename(f.filename); fp=unique_path(sd,fn); f.save(fp)
            saved.append((fp,fn.rsplit(".",1)[-1].lower()))
    if not saved: return jsonify({"error":"No valid files uploaded"}),400
    jid,q=_new_job()
    def _proc():
        try:
            nf=len(saved)
            for i,(fp,ext) in enumerate(saved):
                nm=os.path.basename(fp); _emit(q,0.05+0.20*i/nf,f"Preparing {nm}...")
                if ext=="zip":
                    def zp(done,total): _emit(q,0.05+0.20*(i+done/max(total,1))/nf,f"Converting file {done}/{total}...")
                    sar.pdf_files.extend(_extract_zip(fp,sd,emit_fn=zp))
                else: sar.pdf_files.append(_convert_single(fp,ext))
            if not sar.pdf_files: q.put({"error":"No valid files after conversion"}); return
            np=len(sar.pdf_files); _emit(q,0.25,"Reading document dates...")
            for pp in sar.pdf_files:
                bn=os.path.basename(pp); dd=extract_date_from_filename(bn)
                if not dd:
                    try: dd=extract_document_date(get_full_page_text(pp,0))
                    except Exception: dd=None
                sar.document_dates[bn]=dd
            sar.file_order=[os.path.basename(p) for p in sar.pdf_files]
            if not sar.main_record_file and sar.file_order: sar.main_record_file=sar.file_order[0]
            sar.pdf_files.sort(key=lambda p: sar.document_dates.get(os.path.basename(p)) or "9999-99-99")
            ac=[]
            for i,pp in enumerate(sar.pdf_files):
                nm=os.path.basename(pp); _emit(q,0.30+0.65*i/np,f"Analysing {nm}... ({i+1}/{np})")
                ac.extend(detect_pii(pp,extract_text_spans(pp),subj,nm,settings=sar.detection_settings))
            sar.candidates=ac; sar.status="reviewing"
            _set(sar.id,sar); _save(sar)
            q.put({"done":True,"sar_id":sar.id,"total_candidates":len(ac),
                   "auto_redact":sum(1 for c in ac if c.status==RedactionStatus.AUTO_REDACT),
                   "flagged":sum(1 for c in ac if c.status==RedactionStatus.FLAGGED)})
        except Exception as e: q.put({"error":str(e)})
    threading.Thread(target=_proc,daemon=True).start()
    return jsonify({"job_id":jid})

# Candidate API
@app.route("/api/sar/<sid>/candidates")
@require_login
def get_candidates(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    sf=request.args.get("source_file")
    return jsonify({"candidates":[
        {"id":c.id,"text":c.text,"category":c.category.value,"status":c.status.value,
         "confidence":c.confidence,"page_num":c.page_num,"x0":c.x0,"y0":c.y0,"x1":c.x1,"y1":c.y1,
         "reason":c.reason,"exemption_code":c.exemption_code,"risk_flags":c.risk_flags,"source_file":c.source_file}
        for c in sar.candidates if not sf or c.source_file==sf]})
@app.route("/api/sar/<sid>/main_record",methods=["POST"])
@require_login
def set_main_record(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    fn=(request.json or {}).get("filename","")
    if fn not in [os.path.basename(p) for p in sar.pdf_files]: return jsonify({"error":"File not in SAR"}),400
    sar.main_record_file=fn; _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/page-image/<filename>/<int:pn>")
@require_login
def page_image(sid,filename,pn):
    sar=_get(sid)
    if not sar: return "Not found",404
    safe=secure_filename(filename)
    pp=next((p for p in sar.pdf_files if os.path.basename(p)==safe),None)
    if not pp or not os.path.exists(pp): return "File not found",404
    return Response(render_page_image(pp,pn),mimetype="image/png")
@app.route("/api/sar/<sid>/page-count/<filename>")
@require_login
def page_count_route(sid,filename):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    pp=next((p for p in sar.pdf_files if os.path.basename(p)==secure_filename(filename)),None)
    if not pp: return jsonify({"error":"File not found"}),404
    return jsonify({"page_count":get_page_count(pp)})

@app.route("/api/sar/<sid>/page-dims/<filename>/<int:pn>")
@require_login
def page_dims_route(sid, filename, pn):
    sar = _get(sid)
    if not sar: return jsonify({"error": "Not found"}), 404
    pp = next((p for p in sar.pdf_files if os.path.basename(p) == secure_filename(filename)), None)
    if not pp: return jsonify({"error": "File not found"}), 404
    w, h = get_page_dimensions(pp, pn)
    return jsonify({"width": w, "height": h})
@app.route("/api/sar/<sid>/candidate/<cid>/update",methods=["POST"])
@require_login
def update_candidate(sid,cid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    data=request.json or {}
    for c in sar.candidates:
        if c.id==cid:
            if "status" in data:
                try: c.status=RedactionStatus(data["status"])
                except ValueError: return jsonify({"error":"Invalid status"}),400
            if "exemption_code" in data: c.exemption_code=data["exemption_code"]
            break
    _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/batch-update",methods=["POST"])
@require_login
def batch_update(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    data=request.json or {}
    ids=set(data.get("candidate_ids",[]))
    try: st=RedactionStatus(data.get("status",""))
    except Exception: return jsonify({"error":"Invalid status"}),400
    n=sum(1 for c in sar.candidates if c.id in ids and (setattr(c,"status",st) or True))
    _save(sar); return jsonify({"ok":True,"updated":n})
@app.route("/api/sar/<sid>/batch-by-text",methods=["POST"])
@require_login
def batch_by_text(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    data=request.json or {}; txt=data.get("text","").strip().lower()
    try: st=RedactionStatus(data.get("status",""))
    except Exception: return jsonify({"error":"Invalid status"}),400
    n=0
    for c in sar.candidates:
        if c.text.strip().lower()==txt: c.status=st; n+=1
    _save(sar); return jsonify({"ok":True,"updated":n})
@app.route("/api/sar/<sid>/detection-settings",methods=["GET"])
@require_admin
def get_detection_settings(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    return jsonify({"auto_redact_threshold":sar.detection_settings.auto_redact_threshold,
                    "flag_threshold":sar.detection_settings.flag_threshold,
                    "enabled_categories":sar.detection_settings.enabled_categories})
@app.route("/api/sar/<sid>/detection-settings",methods=["PUT"])
@require_admin
def update_detection_settings(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    data=request.json or {}
    if "auto_redact_threshold" in data: sar.detection_settings.auto_redact_threshold=float(data["auto_redact_threshold"])
    if "flag_threshold" in data: sar.detection_settings.flag_threshold=float(data["flag_threshold"])
    if "enabled_categories" in data: sar.detection_settings.enabled_categories=data["enabled_categories"]
    _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/pause-clock",methods=["POST"])
@require_admin
def pause_clock(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    if sar.clock_paused: return jsonify({"error":"Clock already paused"}),400
    sar.clock_paused=True; sar.paused_at=datetime.now(timezone.utc).isoformat()
    _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/resume-clock",methods=["POST"])
@require_admin
def resume_clock(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    if not sar.clock_paused: return jsonify({"error":"Clock not paused"}),400
    try: pd=max(0,(datetime.now().date()-datetime.fromisoformat(sar.paused_at).date()).days)
    except Exception: pd=0
    sar.total_paused_days+=pd
    sar.pause_log.append({"paused_at":sar.paused_at,"resumed_at":datetime.now(timezone.utc).isoformat(),
                          "reason":(request.json or {}).get("reason",""),"days":pd})
    sar.clock_paused=False; sar.paused_at=""
    _save(sar); return jsonify({"ok":True,"paused_days":pd,"total_paused_days":sar.total_paused_days})
@app.route("/api/sar/<sid>/finalise",methods=["POST"])
@require_admin
def finalise_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    od=os.path.join(OUTPUT_DIR,sid); os.makedirs(od,exist_ok=True)
    try:
        rf=[]; failed=[]
        for pp in sar.pdf_files:
            out_path,file_failed=apply_redactions(pp,sar.candidates,od)
            rf.append(os.path.basename(out_path)); failed.extend(file_failed)
        failed_ids={c.id for c in failed}
        lp=generate_redaction_log(sar.candidates,od,sid,failed_ids=failed_ids)
    except Exception as e:
        log.exception("Finalise failed for SAR %s", sid)
        return jsonify({"error":f"Redaction failed: {e}"}),500
    sar.status="complete"; sar.workflow_status="complete"
    sar.redaction_failures=[{"id":c.id,"text":c.text,"source_file":c.source_file,
                             "page_num":c.page_num,"category":c.category.value}
                            for c in failed]
    _save(sar)
    if failed:
        log.warning("SAR %s finalised with %d unplaced redactions", sid, len(failed))
    return jsonify({"redacted_files":rf,"log_file":os.path.basename(lp),
                    "failed_redactions":sar.redaction_failures})
@app.route("/api/sar/<sid>/outputs")
@require_login
def list_outputs(sid):
    od=os.path.join(OUTPUT_DIR,sid)
    if not os.path.isdir(od): return jsonify({"error":"No output files"}),404
    fs=os.listdir(od)
    return jsonify({"redacted_files":[f for f in fs if f.endswith("_redacted.pdf")],
                    "log_file":next((f for f in fs if f.startswith("redaction_log_")),None)})
@app.route("/api/sar/<sid>/download/<filename>")
@require_login
def download_file(sid,filename):
    fp=os.path.join(OUTPUT_DIR,sid,secure_filename(filename))
    if not os.path.exists(fp): return "File not found",404
    return send_file(fp,as_attachment=True)
@app.route("/api/sar/<sid>/download-all")
@require_login
def download_all(sid):
    od=os.path.join(OUTPUT_DIR,sid)
    if not os.path.isdir(od): return "No output files",404
    sar=_get(sid); sn=(((sar.subject.full_name or f"{sar.subject.first_name} {sar.subject.last_name}").strip()) if sar else sid)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(od)):
            fp=os.path.join(od,fn)
            if os.path.isfile(fp): zf.write(fp,fn)
    buf.seek(0)
    return send_file(buf,mimetype="application/zip",as_attachment=True,download_name=f"{secure_filename(sn) or sid}_redacted.zip")
@app.route("/api/sar/<sid>/export")
@require_login
def export_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",json.dumps({"format_version":SARPACK_FORMAT_VERSION,"app_version":APP_VERSION,
            "sar_id":sar.id,"export_timestamp":datetime.now(timezone.utc).isoformat(),
            "last_modified":sar.last_modified,"subject_name":sar.subject.full_name,
            "workflow_status":sar.workflow_status},indent=2))
        zf.writestr("sar.json",json.dumps(_to_dict(sar),indent=2))
        for pp in sar.pdf_files:
            if os.path.exists(pp): zf.write(pp,f"pdfs/{os.path.basename(pp)}")
    buf.seek(0)
    return send_file(buf,mimetype="application/zip",as_attachment=True,
                     download_name=secure_filename(f"SAR_{sar.subject.full_name or sar.id}_{sar.id}.sarpack").replace(" ","_"))
@app.route("/api/sar/import",methods=["POST"])
@require_admin
def import_sar():
    f=request.files.get("sarpack")
    if not f: return jsonify({"error":"No file provided"}),400
    try:
        buf=io.BytesIO(f.read())
        with zipfile.ZipFile(buf,"r") as zf:
            if "manifest.json" not in zf.namelist() or "sar.json" not in zf.namelist():
                return jsonify({"error":"Invalid .sarpack file"}),400
            sd=json.loads(zf.read("sar.json"))
    except Exception as e: return jsonify({"error":f"Could not read .sarpack: {e}"}),400
    sid2=sd.get("id")
    if _get(sid2):
        ex=_get(sid2)
        return jsonify({"conflict":True,"sar_id":sid2,"existing_modified":ex.last_modified,
                        "import_modified":sd.get("last_modified"),"subject_name":sd.get("subject",{}).get("full_name","")})
    buf.seek(0); _do_import(buf,sd); return jsonify({"ok":True,"sar_id":sid2})
@app.route("/api/sar/import/force",methods=["POST"])
@require_admin
def import_sar_force():
    f=request.files.get("sarpack")
    if not f: return jsonify({"error":"No file provided"}),400
    try:
        buf=io.BytesIO(f.read()); buf.seek(0)
        with zipfile.ZipFile(buf,"r") as zf: sd=json.loads(zf.read("sar.json"))
        buf.seek(0); _do_import(buf,sd)
    except Exception as e: return jsonify({"error":f"Force import failed: {e}"}),500
    return jsonify({"ok":True,"sar_id":sd.get("id")})
def _do_import(buf,sd):
    sid2=sd["id"]; sdir=_sar_dir(sid2); os.makedirs(sdir,exist_ok=True)
    buf.seek(0)
    with zipfile.ZipFile(buf,"r") as zf:
        for name in zf.namelist():
            if name.startswith("pdfs/"):
                bn=os.path.basename(name)
                if bn:
                    with zf.open(name) as src, open(os.path.join(sdir,bn),"wb") as dst: dst.write(src.read())
    atomic_write_json(os.path.join(SAR_DATA_DIR,f"{sid2}.json"),sd)
    _load_all()

# Manual redact, delete, archive, notes
@app.route("/api/sar/<sid>/manual-redact",methods=["POST"])
@require_login
def manual_redact(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    d=request.json
    c=RedactionCandidate(text="[Manual redaction]",category=PIICategory.MANUAL,
        status=RedactionStatus.APPROVED,confidence=1.0,page_num=d["page_num"],
        x0=d["x0"],y0=d["y0"],x1=d["x1"],y1=d["y1"],
        reason="Manually drawn redaction",source_file=d["source_file"])
    sar.candidates.append(c); _save(sar)
    return jsonify({"id":c.id,"text":c.text,"category":c.category.value,"status":c.status.value,
                    "confidence":c.confidence,"page_num":c.page_num,"x0":c.x0,"y0":c.y0,"x1":c.x1,"y1":c.y1,
                    "reason":c.reason,"source_file":c.source_file})
@app.route("/api/sar/<sid>/delete",methods=["POST"])
@require_admin
def delete_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    for d in [os.path.join(UPLOAD_DIR,sid),os.path.join(OUTPUT_DIR,sid)]:
        if os.path.isdir(d): shutil.rmtree(d)
    jp=os.path.join(SAR_DATA_DIR,f"{sid}.json")
    if os.path.exists(jp): os.remove(jp)
    _del(sid); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/archive",methods=["POST"])
@require_admin
def archive_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    sar.archived=True; _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/unarchive",methods=["POST"])
@require_admin
def unarchive_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    sar.archived=False; _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/delete-page",methods=["POST"])
@require_admin
def delete_page(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    d=request.json or {}; fn=d.get("filename"); pn=d.get("page_num")
    pp=next((p for p in sar.pdf_files if os.path.basename(p)==fn),None)
    if not pp: return jsonify({"error":"File not found"}),404
    # Preserve the document as originally received before any destructive edit
    orig_dir=os.path.join(_sar_dir(sid),"originals"); os.makedirs(orig_dir,exist_ok=True)
    orig_copy=os.path.join(orig_dir,os.path.basename(pp))
    if not os.path.exists(orig_copy): shutil.copy2(pp,orig_copy)
    import fitz; doc=fitz.open(pp)
    if pn is None or pn<0 or pn>=len(doc): doc.close(); return jsonify({"error":"Invalid page number"}),400
    doc.delete_page(pn); doc.save(pp,incremental=False); npc=len(doc); doc.close()
    sar.candidates=[c for c in sar.candidates if not (c.source_file==fn and c.page_num==pn)]
    for c in sar.candidates:
        if c.source_file==fn and c.page_num>pn: c.page_num-=1
    _save(sar); return jsonify({"ok":True,"new_page_count":npc})
@app.route("/api/sar/<sid>/notes",methods=["GET"])
@require_login
def get_notes(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    return jsonify({"notes":sar.notes})
@app.route("/api/sar/<sid>/notes",methods=["PUT"])
@require_login
def update_notes(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    sar.notes=(request.json or {}).get("notes",""); _save(sar); return jsonify({"ok":True})
@app.route("/api/sar/<sid>/reparse",methods=["POST"])
@require_login
def reparse_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    keys={(c.source_file,c.page_num,round(c.x0,1),round(c.y0,1),c.text.lower()) for c in sar.candidates}
    new=[]
    for pp in sar.pdf_files:
        if not os.path.exists(pp): continue
        for c in detect_pii(pp,extract_text_spans(pp),sar.subject,os.path.basename(pp),settings=sar.detection_settings):
            k=(c.source_file,c.page_num,round(c.x0,1),round(c.y0,1),c.text.lower())
            if k not in keys: keys.add(k); new.append(c)
    sar.candidates.extend(new); _save(sar); return jsonify({"ok":True,"new_found":len(new)})
@app.route("/api/sar/<sid>/redetect",methods=["POST"])
@require_admin
def redetect_sar(sid):
    """Update subject details + full re-detection, preserving existing decisions. Returns job_id."""
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    sp=(request.json or {}).get("subject",{})
    for field in ("first_name","last_name","full_name","nhs_number","date_of_birth","address","phone","email","aliases"):
        if field in sp: setattr(sar.subject,field,sp[field])
    if sar.subject.first_name or sar.subject.last_name:
        sar.subject.full_name=f"{sar.subject.first_name} {sar.subject.last_name}".strip()
    mem={(c.text.strip().lower(),c.category.value):c.status.value for c in sar.candidates
         if c.status.value not in ("flagged","auto_redact")}
    jid,q=_new_job()
    def _proc():
        try:
            pf=[p for p in sar.pdf_files if os.path.exists(p)]; n=len(pf)
            nc=[]
            for i,pp in enumerate(pf):
                nm=os.path.basename(pp); _emit(q,0.1+0.85*i/max(n,1),f"Re-scanning {nm}... ({i+1}/{n})")
                for c in detect_pii(pp,extract_text_spans(pp),sar.subject,nm,settings=sar.detection_settings):
                    r=mem.get((c.text.strip().lower(),c.category.value))
                    if r: c.status=RedactionStatus(r)
                    nc.append(c)
            sar.candidates=nc+[c for c in sar.candidates if c.category==PIICategory.MANUAL]
            _save(sar); q.put({"done":True,"sar_id":sar.id,"total_candidates":len(sar.candidates)})
        except Exception as e: q.put({"error":str(e)})
    threading.Thread(target=_proc,daemon=True).start()
    _save(sar); return jsonify({"job_id":jid})
@app.route("/api/sar/<sid>/document-date",methods=["POST"])
@require_login
def set_document_date(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    d=request.get_json(); fn=d.get("filename",""); ds=d.get("date")
    if fn not in [os.path.basename(p) for p in sar.pdf_files]: return jsonify({"error":"File not found"}),400
    sar.document_dates[fn]=ds
    sar.pdf_files.sort(key=lambda p: sar.document_dates.get(os.path.basename(p)) or "9999-99-99")
    _save(sar); return jsonify({"ok":True})

# Custom words / staff
@app.route("/api/custom-words",methods=["GET"])
@require_login
def list_custom_words(): return jsonify(get_custom_words())
@app.route("/api/custom-words",methods=["POST"])
@require_login
def add_custom_word_route():
    d=request.json; phrase=d.get("phrase","").strip()
    if not phrase: return jsonify({"error":"Phrase is required"}),400
    add_custom_word(phrase,bool(d.get("case_sensitive",False))); return jsonify({"ok":True})
@app.route("/api/custom-words/<path:phrase>",methods=["DELETE"])
@require_login
def delete_custom_word(phrase): remove_custom_word(phrase); return jsonify({"ok":True})
@app.route("/api/staff",methods=["GET"])
@require_login
def list_staff(): return jsonify(get_staff_list())
@app.route("/api/staff",methods=["POST"])
@require_login
def add_staff():
    d=request.json; name=d.get("name","").strip()
    if not name: return jsonify({"error":"Name is required"}),400
    add_staff_member(name,d.get("role","")); return jsonify({"ok":True})
@app.route("/api/staff/<name>",methods=["DELETE"])
@require_login
def delete_staff(name): remove_staff_member(name); return jsonify({"ok":True})

# Workflow
@app.route("/api/sar/<sid>/allocate",methods=["POST"])
@require_admin
def allocate_sar(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    gid=(request.json or {}).get("user_id","")
    if not gid: sar.allocated_to=""; sar.allocated_to_name=""; sar.workflow_status="new"
    else:
        gp=get_user_by_id(gid)
        if not gp: return jsonify({"error":"User not found"}),404
        sar.allocated_to=gp.id; sar.allocated_to_name=gp.display_name; sar.workflow_status="in_review"
    _save(sar); return jsonify({"ok":True,"workflow_status":sar.workflow_status})
@app.route("/api/sar/<sid>/workflow",methods=["POST"])
@require_login
def update_workflow(sid):
    sar=_get(sid)
    if not sar: return jsonify({"error":"Not found"}),404
    ns=(request.json or {}).get("status")
    if ns not in {"ready_for_signoff","in_review"}: return jsonify({"error":"Invalid status"}),400
    if g.current_user.role=="gp":
        if sar.allocated_to!=g.current_user.id: return jsonify({"error":"Not authorised"}),403
        if ns!="ready_for_signoff": return jsonify({"error":"GPs may only submit for sign-off"}),403
    sar.workflow_status=ns; _save(sar); return jsonify({"ok":True,"workflow_status":sar.workflow_status})

# Reports
@app.route("/reports")
@require_login
def reports_dashboard():
    reps=load_all_reports(); reps.sort(key=lambda r:r.get("created_at",""),reverse=True)
    return render_template("reports_dashboard.html",reports=reps,templates=get_all_templates())
@app.route("/reports/new")
@require_login
def new_report_page(): return render_template("reports_new.html",templates=get_all_templates())
@app.route("/reports/<rid>")
@require_login
def report_review(rid):
    rep=load_report(rid)
    if not rep: return "Report not found",404
    tpl=get_template(rep["template_id"])
    fi=[{"name":os.path.basename(f),"pages":get_page_count(f),"date":rep.get("document_dates",{}).get(os.path.basename(f))}
        for f in rep.get("pdf_files",[]) if os.path.exists(f)]
    return render_template("reports_review.html",report=rep,template=tpl,files_info=fi)
@app.route("/api/reports/create",methods=["POST"])
@require_login
def create_report():
    tid=request.form.get("template_id",""); tpl=get_template(tid)
    if not tpl: return jsonify({"error":"Template not found"}),400
    pat={k:request.form.get(k,"").strip() for k in ("full_name","date_of_birth","nhs_number","address","gp_name","gp_practice")}
    if not pat["full_name"]: return jsonify({"error":"Patient name is required"}),400
    files=request.files.getlist("pdf_files")
    if not files or all(f.filename=="" for f in files): return jsonify({"error":"At least one file is required"}),400
    import uuid as _u; rid=str(_u.uuid4())[:12]; rd=os.path.join(REPORT_UPLOAD_DIR,rid); os.makedirs(rd,exist_ok=True)
    saved=[]
    for f in files:
        if f.filename and allowed_file(f.filename):
            fn=secure_filename(f.filename); fp=unique_path(rd,fn); f.save(fp)
            saved.append((fp,fn.rsplit(".",1)[-1].lower()))
    if not saved: return jsonify({"error":"No valid files uploaded"}),400
    cb=g.current_user.id; cbn=g.current_user.display_name; ca=datetime.now(timezone.utc).isoformat()
    jid,jq=_new_job()
    def _proc():
        try:
            nf=len(saved); pf=[]
            for i,(fp,ext) in enumerate(saved):
                nm=os.path.basename(fp); _emit(jq,0.05+0.20*i/nf,f"Preparing {nm}...")
                if ext=="zip":
                    def zp(done,total): _emit(jq,0.05+0.20*(i+done/max(total,1))/nf,f"Converting {done}/{total}...")
                    pf.extend(_extract_zip(fp,rd,emit_fn=zp))
                else: pf.append(_convert_single(fp,ext))
            if not pf: jq.put({"error":"No valid files after conversion"}); return
            _emit(jq,0.27,"Reading dates..."); dd={}
            for pp in pf:
                bn=os.path.basename(pp); d=extract_date_from_filename(bn)
                if not d:
                    try: d=extract_document_date(get_full_page_text(pp,0))
                    except Exception: d=None
                dd[bn]=d
            pf.sort(key=lambda p: dd.get(os.path.basename(p)) or "9999-99-99")
            qs=sorted(tpl.get("questions",[]),key=lambda x:x.get("order",0)); nq=len(qs); ans=[]
            for i,q in enumerate(qs):
                short=q["text"][:50]+("..." if len(q["text"])>50 else "")
                _emit(jq,0.30+0.65*i/max(nq,1),f"Q{i+1}/{nq}: {short}")
                ans.append({"question_id":q["id"],"question_text":q["text"],
                            "question_type":q.get("question_type","free_text"),"options":q.get("options",[]),
                            "answer":"","evidence":extract_evidence(pf,q),"reviewed":False})
            _emit(jq,0.96,"Scanning keywords...")
            rd2={"id":rid,"created_at":ca,"last_modified":ca,"template_id":tid,"template_name":tpl["name"],
                 "patient":pat,"pdf_files":pf,"document_dates":dd,"answers":ans,
                 "keyword_flags":scan_keywords(pf,qs),"status":"in_progress","created_by":cb,"created_by_name":cbn}
            save_report(rd2); jq.put({"done":True,"report_id":rid,"total_questions":len(ans)})
        except Exception as e: jq.put({"error":str(e)})
    threading.Thread(target=_proc,daemon=True).start()
    return jsonify({"job_id":jid})
@app.route("/api/reports/<rid>/answer",methods=["POST"])
@require_login
def save_report_answer(rid):
    rep=load_report(rid)
    if not rep: return jsonify({"error":"Not found"}),404
    d=request.get_json(); qid=d.get("question_id","")
    for a in rep.get("answers",[]):
        if a["question_id"]==qid: a["answer"]=d.get("answer",""); a["reviewed"]=d.get("reviewed",False); break
    save_report(rep); return jsonify({"ok":True})
@app.route("/api/reports/<rid>/evidence/<qid>")
@require_login
def get_report_evidence(rid,qid):
    rep=load_report(rid)
    if not rep: return jsonify({"error":"Not found"}),404
    for a in rep.get("answers",[]):
        if a["question_id"]==qid: return jsonify({"evidence":a.get("evidence",[])})
    return jsonify({"error":"Question not found"}),404
@app.route("/api/reports/<rid>/re-extract",methods=["POST"])
@require_login
def re_extract_evidence(rid):
    rep=load_report(rid)
    if not rep: return jsonify({"error":"Not found"}),404
    tpl=get_template(rep["template_id"])
    if not tpl: return jsonify({"error":"Template not found"}),400
    qbi={q["id"]:q for q in tpl.get("questions",[])}
    for a in rep.get("answers",[]):
        q=qbi.get(a["question_id"])
        if q: a["evidence"]=extract_evidence(rep["pdf_files"],q)
    rep["keyword_flags"]=scan_keywords(rep["pdf_files"],tpl.get("questions",[]))
    save_report(rep); return jsonify({"ok":True})
@app.route("/api/reports/<rid>/generate",methods=["POST"])
@require_login
def generate_report(rid):
    rep=load_report(rid)
    if not rep: return jsonify({"error":"Not found"}),404
    op=generate_report_pdf(rep,os.path.join(REPORT_OUTPUT_DIR,rid))
    rep["status"]="complete"; save_report(rep); return jsonify({"ok":True,"filename":os.path.basename(op)})
@app.route("/api/reports/<rid>/download/<filename>")
@require_login
def download_report(rid,filename):
    fp=os.path.join(REPORT_OUTPUT_DIR,rid,secure_filename(filename))
    if not os.path.exists(fp): return "File not found",404
    return send_file(fp,as_attachment=True)
@app.route("/api/reports/<rid>/page-image/<filename>/<int:pn>")
@require_login
def report_page_image(rid,filename,pn):
    rep=load_report(rid)
    if not rep: return "Not found",404
    fp=os.path.join(REPORT_UPLOAD_DIR,rid,secure_filename(filename))
    if not os.path.exists(fp): return "File not found",404
    return Response(render_page_image(fp,pn),mimetype="image/png")
@app.route("/api/reports/<rid>/delete",methods=["POST"])
@require_admin
def delete_report_route(rid):
    delete_report(rid)
    for d in [os.path.join(REPORT_UPLOAD_DIR,rid),os.path.join(REPORT_OUTPUT_DIR,rid)]:
        if os.path.isdir(d): shutil.rmtree(d)
    return jsonify({"ok":True})

# Templates
@app.route("/api/templates")
@require_login
def list_templates(): return jsonify(get_all_templates())
@app.route("/api/templates",methods=["POST"])
@require_admin
def create_template():
    d=request.get_json()
    if not d.get("name"): return jsonify({"error":"Template name is required"}),400
    import uuid as _u
    t={"id":f"tpl_{str(_u.uuid4())[:8]}","name":d["name"],"category":d.get("category","custom"),
       "description":d.get("description",""),"is_builtin":False,"questions":d.get("questions",[])}
    save_custom_template(t); return jsonify({"ok":True,"template_id":t["id"]})
@app.route("/api/templates/<tid>",methods=["DELETE"])
@require_admin
def delete_template_route(tid):
    t=get_template(tid)
    if t and t.get("is_builtin"): return jsonify({"error":"Cannot delete built-in templates"}),400
    if not delete_custom_template(tid): return jsonify({"error":"Not found"}),404
    return jsonify({"ok":True})



@app.route("/api/practice-config", methods=["GET"])
@require_login
def get_practice_config_route():
    return jsonify(_get_practice_config())

@app.route("/api/practice-config", methods=["POST"])
@require_admin
def save_practice_config_route():
    data = request.json or {}
    _save_practice_config(data)
    return jsonify({"ok": True})

@app.route("/api/update-check")
@require_login
def update_check():
    return jsonify(_get_update_result())

@app.errorhandler(403)
def forbidden(e): return render_template("403.html"),403
@app.errorhandler(404)
def not_found(e): return render_template("403.html"),404

if __name__=="__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
