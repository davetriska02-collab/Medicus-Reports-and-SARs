"""Weekly compliance document review loop.

Called by the GitHub Actions 'docs-review' workflow. Uses Claude Haiku to
assess whether the DPIA and DCB0129 clinical safety case need updating given
recent code changes, then creates or updates GitHub issues if action is needed.

Environment variables (set by the workflow):
  ANTHROPIC_API_KEY  — repository secret
  GH_TOKEN           — provided automatically by GitHub Actions
  REPO               — owner/repo string (e.g. davetriska02-collab/Medicus-Reports-and-SARs)
  LOOK_BACK_DAYS     — how far back to look in git history (default 30)
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCS = [
    {
        "path": REPO_ROOT / "docs/trust-pack/DPIA.md",
        "name": "DPIA (Data Protection Impact Assessment)",
        "issue_title": "DPIA may need updating — automated compliance review",
    },
    {
        "path": REPO_ROOT / "docs/trust-pack/CLINICAL_SAFETY_CASE.md",
        "name": "DCB0129 Clinical Safety Case",
        "issue_title": "Clinical Safety Case may need updating — automated compliance review",
    },
]

ISSUE_LABEL = "compliance-review"

# Code paths that affect compliance documents
WATCHED_PATHS = ["app.py", "sar/", "serve.py", "templates/"]

# Model: Haiku — cheap, fast, adequate for doc-diff review
HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ── Git helpers ──────────────────────────────────────────────────────────────

def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO_ROOT)
    return r.stdout.strip()


def recent_commit_log(days: int) -> str:
    return _git("log", f"--since={days} days ago", "--oneline", "--",
                *WATCHED_PATHS)


def recent_diff_stat(days: int) -> str:
    # Find the oldest commit within the window
    first_hash = _git("log", f"--since={days} days ago", "--format=%H",
                      "--reverse", "-1", "--", *WATCHED_PATHS)
    if not first_hash:
        return ""
    return _git("diff", f"{first_hash}~1", "HEAD", "--stat", "--",
                *WATCHED_PATHS)


# ── Claude Haiku review ──────────────────────────────────────────────────────

def review_doc(client, doc_name: str, doc_content: str,
               commit_log: str, diff_stat: str, days: int) -> dict:
    import anthropic  # noqa: local import keeps top-level import optional

    prompt = f"""You are reviewing a medical software compliance document to decide whether \
it needs updating after recent code changes.

## Document under review: {doc_name}

{doc_content}

---

## Code changes in the last {days} days

### Commit log
```
{commit_log or "(no commits in this window)"}
```

### Changed-files summary
```
{diff_stat or "(no relevant file changes)"}
```

---

Assess:
1. Does the document accurately reflect the current software given these changes?
2. Are there new features, data flows, or risks that should be documented?
3. Which specific sections appear outdated?

Reply with JSON only — no prose, no markdown fences:
{{
  "update_needed": true | false,
  "confidence": "high" | "medium" | "low",
  "summary": "<one sentence>",
  "sections_to_update": ["<section name>", ...],
  "rationale": "<2-3 sentences>"
}}"""

    msg = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Strip accidental markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].strip()
    return json.loads(text)


# ── GitHub issue helpers ─────────────────────────────────────────────────────

def _gh(*args: str, input_text: str | None = None) -> tuple[int, str]:
    r = subprocess.run(
        ["gh", *args],
        capture_output=True, text=True,
        input=input_text,
    )
    return r.returncode, r.stdout.strip()


def ensure_label(repo: str):
    _gh("label", "create", ISSUE_LABEL,
        "--repo", repo,
        "--description", "Automated compliance document review",
        "--color", "0075ca",
        "--force")


def find_open_issue(repo: str, title: str) -> int | None:
    rc, out = _gh("issue", "list",
                  "--repo", repo,
                  "--label", ISSUE_LABEL,
                  "--state", "open",
                  "--json", "number,title")
    if rc != 0 or not out:
        return None
    for issue in json.loads(out):
        if issue["title"] == title:
            return issue["number"]
    return None


def create_or_update_issue(repo: str, title: str, body: str):
    existing = find_open_issue(repo, title)
    if existing:
        rc, _ = _gh("issue", "comment", str(existing),
                    "--repo", repo, "--body", body)
        status = f"updated issue #{existing}"
    else:
        rc, _ = _gh("issue", "create",
                    "--repo", repo,
                    "--title", title,
                    "--label", ISSUE_LABEL,
                    "--body", body)
        status = "created new issue"
    if rc == 0:
        print(f"  GitHub: {status}: {title}")
    else:
        print(f"  WARNING: could not {status} (gh returned {rc})")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping review")
        sys.exit(0)

    repo = os.environ.get("REPO", "").strip()
    days = int(os.environ.get("LOOK_BACK_DAYS", "30"))

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        print("anthropic package not installed — run: pip install anthropic")
        sys.exit(1)

    commit_log = recent_commit_log(days)
    diff_stat = recent_diff_stat(days)

    if not commit_log:
        print(f"No relevant code changes in the last {days} days — nothing to review")
        sys.exit(0)

    print(f"Reviewing compliance docs against {days} days of changes "
          f"({commit_log.count(chr(10)) + 1} commits)...")

    if repo:
        ensure_label(repo)

    any_action = False
    for doc in DOCS:
        doc_path: Path = doc["path"]
        doc_name: str = doc["name"]
        issue_title: str = doc["issue_title"]

        if not doc_path.exists():
            print(f"WARNING: {doc_path.relative_to(REPO_ROOT)} not found — skipping")
            continue

        print(f"\n[{doc_name}]")
        try:
            result = review_doc(
                client, doc_name, doc_path.read_text(),
                commit_log, diff_stat, days,
            )
        except Exception as exc:
            print(f"  Review failed: {exc}")
            continue

        update_needed = result.get("update_needed", False)
        confidence = result.get("confidence", "low")
        print(f"  update_needed={update_needed}  confidence={confidence}")
        print(f"  {result.get('summary', '')}")

        if update_needed and confidence in ("high", "medium"):
            any_action = True
            sections = result.get("sections_to_update") or []
            rationale = result.get("rationale", "")
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            body = (
                f"## Automated compliance review — {date_str}\n\n"
                f"**Document:** {doc_name}  \n"
                f"**Confidence:** {confidence}  \n"
                f"**Summary:** {result.get('summary', '')}\n\n"
                f"### Rationale\n{rationale}\n\n"
                f"### Sections to review\n"
                + (
                    "\n".join(f"- {s}" for s in sections)
                    if sections else "- See rationale above"
                )
                + f"\n\n### Code changes that triggered this review\n"
                  f"<details>\n<summary>Commit log (last {days} days)</summary>\n\n"
                  f"```\n{commit_log}\n```\n</details>\n\n"
                  f"---\n*Generated by the weekly compliance review loop "
                  f"(Claude Haiku). Please review, update the document, and "
                  f"close this issue when done.*"
            )

            if repo:
                create_or_update_issue(repo, issue_title, body)
            else:
                print(f"  (REPO not set — would create issue: {issue_title})")
        else:
            print("  No update required (or confidence too low to act)")

    if not any_action:
        print("\nAll compliance documents appear up to date.")


if __name__ == "__main__":
    main()
