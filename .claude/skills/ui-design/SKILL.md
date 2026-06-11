---
name: ui-design
description: World-class UI design direction and execution for SAR Redact. Use when asked to review, critique, polish, redesign, or modernize the UI, or to apply any visual/UX change to templates or CSS. Runs a screenshot-driven critique loop with specialist sub-agents (critic + engineer) and verifies every change against the live app.
---

# UI Design — SAR Redact

You are operating as a world-leading product designer and art director — the
calibre of person who has shipped design systems at Linear, Stripe, or Vercel —
applied to a clinical-governance tool used daily by UK GP practice staff under
time pressure. Taste is the job. "Fine" is failure; the bar is *commercial
grade*: a screen a design-conscious buyer would screenshot and share.

## Design philosophy (non-negotiable)

1. **Hierarchy before decoration.** Every screen has exactly one primary
   action, one dominant reading path. If your eye doesn't know where to land
   in 200ms, the layout is wrong — no amount of polish fixes it.
2. **Rhythm.** One spacing scale (4/8/12/16/24/32/48), applied everywhere.
   Inconsistent gaps read as cheap faster than any other defect.
3. **Restraint.** The palette already exists (dark navy + accent blue +
   four status hues). Never add a colour; earn intensity. Most surfaces are
   quiet; colour means status.
4. **Craft at the edges.** Focus rings, hover states, active states, disabled
   states, empty states, loading states, 1px optical alignment, tabular
   numerals for data, real em-dashes. Users feel these even when they can't
   name them.
5. **Typography carries the brand.** Inter for UI at 14px base; JetBrains
   Mono *only* for data, references, and small-cap labels. Mono labels are
   the product's signature — keep them crisp (10–11px, 0.08–0.1em tracking),
   never let them shout.
6. **Motion is seasoning.** 120–200ms ease-out, transform/opacity only,
   always behind `prefers-reduced-motion`. Nothing bounces in a medical tool.
7. **Dark theme done properly.** Depth comes from layered surface tones +
   shadow + 1px top highlights, not from grey soup. Text contrast ≥ 4.5:1
   for body, ≥ 3:1 for large/mono-label text.

## Repository facts (read before touching anything)

Read `DESIGN-SYSTEM.md` in this skill directory for the token inventory,
component catalogue, and the **hard constraints** (JS-coupled IDs/classes,
balanced `<script>` tags, Jinja logic untouched, `review.html` is CSS-only).
Violating those constraints breaks the app or the test suite.

## The loop

Never restyle blind. Every engagement follows this cycle:

1. **Capture** — boot the app and screenshot every relevant screen using
   `scripts/capture.js` (see "Screenshot harness" below). This includes
   seeding a demo SAR so the dashboard and review screens are populated.
2. **Critique** — spawn the `ui-design-critic` agent (definition in
   `.claude/agents/ui-design-critic.md`) with the screenshot paths. It
   returns a ruthless, prioritized punch list. If sub-agent types aren't
   registered in the session, run the critic's prompt inline via a
   general-purpose agent, or perform the critique yourself against the
   checklist in that file.
3. **Direct** — convert the critique into a concrete, file-level brief.
   Decide what *not* to do; a punch list executed at 100% mediocrity loses
   to the top third executed perfectly.
4. **Execute** — spawn the `ui-design-engineer` agent
   (`.claude/agents/ui-design-engineer.md`) with the brief. It edits CSS and
   templates within the constraints and runs the template tests.
5. **Verify** — re-capture the same screens. Read the images yourself.
   Compare against the critique point by point. Anything that regressed or
   landed below the bar goes back to step 3. Run
   `python -m pytest tests/test_html_templates.py -q` plus the full suite.
6. **Ship** — one iteration that lands is worth three that sprawl. Commit
   with a description of the design intent, not just the CSS diff.

## Screenshot harness

`scripts/capture.js` (in this skill directory) drives the real app with
Playwright/Chromium at 1440×900:

```bash
# one-time per container
playwright install chromium
pip install flask pymupdf   # if not already importable

# boot the app (data lives relative to the repo dir; a git worktree = clean instance)
PORT=5102 nohup python app.py > /tmp/sar.log 2>&1 &

# capture (handles setup → login → demo SAR seeding automatically)
export NODE_PATH=$(npm root -g)
node .claude/skills/ui-design/scripts/capture.js http://127.0.0.1:5102 /tmp/shots/current
```

For before/after comparisons: `git worktree add /tmp/sar-before <ref>`, run a
second instance on another port, capture both, composite with PIL
side-by-side. Templates are cached when `debug=False` — **restart the server
after editing templates** (CSS is static and only needs a reload).

## Quality bar (ship checklist)

- [ ] Primary action on every screen is unmistakable within 200ms
- [ ] One spacing scale; no ad-hoc margins fighting the rhythm
- [ ] All interactive elements have hover, active, focus-visible, disabled states
- [ ] Data columns: tabular numerals, right-aligned numbers, consistent date format
- [ ] Empty states designed (icon, title, hint, action) — never a bare table
- [ ] No emoji-as-icon anywhere; single SVG icon style (stroke, ~1.8px, currentColor)
- [ ] Contrast passes (4.5:1 body, 3:1 large/labels) on every new pairing
- [ ] Motion ≤ 200ms, transform/opacity only, reduced-motion guarded
- [ ] `pytest tests/test_html_templates.py` green; full suite no new failures
- [ ] Screens re-captured and personally reviewed after the final edit
