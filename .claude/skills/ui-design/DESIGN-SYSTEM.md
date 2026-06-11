# SAR Redact — Design System Reference

Single stylesheet: `static/css/main.css`. All tokens in `:root`. Server-rendered
Jinja templates in `templates/` (+ `templates/admin/`), most extend `base.html`;
`login.html` and `setup.html` are standalone full documents.

## Tokens

| Group | Tokens |
|---|---|
| Surfaces | `--bg` (page) → `--bg-e` (card) → `--bg-ee` (raised) |
| Lines | `--border`, `--border-hi` |
| Text ramp | `--t1` (primary) → `--t5` (faintest); body uses `--t1`–`--t3`, labels `--t4` |
| Accent | `--accent`, `--accent-hi`, `--accent-glow` |
| Status | `--green/-d`, `--red/-d`, `--amber/-d`, `--purple/-d`, `--blue-d` (`-d` = 12–15% tinted backgrounds) |
| Type | `--font` (Inter stack), `--mono` (JetBrains Mono) |
| Shape | `--r-sm/md/lg` (6/8/12px) |
| Depth | `--shadow-sm/md/lg`, `--ring` (focus) |
| Layout | `--nav-h`, `--toolbar-h`, `--sidebar-w` |

Fonts load from Google Fonts in `base.html`, `login.html`, `setup.html` —
keep the three `<head>`s in sync when changing weights.

## Component catalogue (classes in main.css)

- **Chrome**: `.navbar`, `.nav-brand`, `.nav-practice`, `.nav-links`,
  `.nav-user`, `.nav-signout`, `.nav-role-badge`
- **Layout**: `.container` (1100px), `.container-wide` (1400px),
  `.page-header`, `.heading-rule`, `.section-head`
- **Actions**: `.btn` + `.btn-primary/secondary/ghost/danger`, `.btn-sm`
- **Surfaces**: `.card`, `.form-card`, `.stat-card`, `.settings-panel`,
  `.modal` / `.modal-overlay`
- **Data**: `.sar-table` (CSS-grid rows, not `<table>`), `.report-table`,
  `.users-table`, `.pill-*` status pills, `.days-*` countdown colours
- **Forms**: `.form-grid`, `.form-group`, `.upload-zone`, `.file-chip`,
  `.threshold-row` sliders, `.check-row`
- **Feedback**: `.alert-*`, `.update-banner`, `.urgency-strip` +
  `.urgency-badge-*`, `.empty-state`, `.job-progress`
- **Review screen**: `.review-layout`, `.review-toolbar`, `.candidate-card`
  (+ `status-*` modifiers), `.cand-btn-*`, `.group-occ`, `.colour-legend`,
  `.page-navigator`
- **Auth**: `.auth-wrap`, `.auth-box`, `.auth-brand`, `.auth-brand-icon`

Icons are inline SVG: stroke `currentColor`, stroke-width ≈ 1.8, round
caps/joins, 13–18px. Match this style exactly; never mix filled and stroked
icon families, never use emoji.

## HARD CONSTRAINTS

1. **JS-coupled hooks.** Never rename/remove element `id`s, `name`
   attributes, or classes referenced from `static/js/**` or inline
   `<script>` blocks. Grep before touching any class. Known hot hooks:
   `#upload-zone #file-input #file-chips #import-zone #transfer-section
   #conflict-modal #job-fill #job-step #job-pct #demo-sar-btn
   #demo-sar-label #update-banner #page-indicator #zoom-level`, classes
   `status-approved/rejected/excluded_* /auto_redact/flagged`, `cand-btn-*`,
   `group-occ`, `pill-*`, `days-*`, `.modal-overlay`, `.hidden`,
   `.drag-over`. Adding classes is always safe; renaming is not.
2. **Balanced scripts.** `tests/test_html_templates.py` fails the build on
   unbalanced `<script>` tags or `window.X =` assignments stranded outside
   script blocks. Run it after every template edit.
3. **Visual layer only.** No changes to Jinja logic, routes, form fields,
   or CSRF handling. Note: HTML entities inside `{{ ... }}` expressions get
   escaped — use literal characters (`—` not `&mdash;`) inside Jinja strings.
4. **`review.html` is CSS-only.** The PDF review screen is densely
   JS-coupled (`static/js/review/*.js`). Restyle through existing classes in
   `main.css`; no structural HTML changes without explicit sign-off.
5. **Dark navy identity stays.** Refine, don't rebrand. No light mode, no
   new hues.
6. **Audience reality.** Users are practice staff on 1366×768 work PCs,
   often keyboard-driven (the review screen has shortcut keys). Density is a
   feature; whitespace serves scanning, not aesthetics for their own sake.
