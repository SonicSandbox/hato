# -*- coding: utf-8 -*-
"""Is there a SUCCESSFUL `tests` run for this commit? One word, then the detail.

    gh api "repos/$GH_REPO/actions/workflows/ci.yml/runs?head_sha=$SHA" > runs.json
    python .github/scripts/ci_verdict.py runs.json

Prints exactly one line beginning with one of:

    success   a completed `tests` run for this commit concluded success
    pending   a run exists and has not finished -- the caller should wait
    failed    a run finished and did not succeed
    missing   no run at all for this commit, or the payload could not be read

⛔ IT ALWAYS EXITS 0. The caller is a `while` loop under `set -e`, and a
non-zero exit there would abort the loop rather than produce a verdict -- which
is how a release gate turns into a release. The VERDICT is the output; the exit
code carries nothing.

===========================================================================
⭐ WHY THIS IS A FILE AND NOT THREE LINES OF SHELL
===========================================================================
`release.yml` does not re-run the suite, the three-OS matrix, the examples or
the degradation paths. The process doc's note on the sibling project's version:

  "⚠ It does not run the examples. It trusts `ci.yml` on the same commit -- so
   CI green on the tagged commit is a PRECONDITION, not a formality."

There it was a tick-box in a pre-tag checklist. Here it is a job `publish`
needs, which means THIS PARSER IS THE GATE. ⛔ `doctrine/tooling`: never
diagnose through an inline shell one-liner -- and a `grep -q success` over that
JSON would answer `success` for a payload containing
`"conclusion": null, "status": "in_progress"`, because the word `success` also
appears in every run's `check_suite_url`... and because the payload lists EVERY
run for the commit, including re-runs and failures. A per-run decision cannot be
made by a whole-document grep.

⚠ AND IT PREFERS THE NEWEST RUN. A commit can carry a failed run and then a
successful re-run; taking "any success" would also accept the reverse -- an old
success followed by a real failure -- so the answer comes from the latest
completed attempt, and the line says which one it read.
"""
import io
import json
import os
import sys

#: What GitHub calls a finished run.
COMPLETED = "completed"


def load(path):
    """-> (dict, None) or (None, reason). ⛔ Never raises."""
    if not os.path.exists(path):
        return None, "%s does not exist" % path
    try:
        with io.open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, "%s could not be read: %s: %s" % (path, type(exc).__name__, exc)
    if not isinstance(payload, dict):
        return None, "%s is not a JSON object" % path
    return payload, None


def verdict(payload):
    """-> one line, starting with success / pending / failed / missing."""
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        # ⚠ An error payload from the API is also a dict, and its `message` is
        # the only useful thing in it -- "Resource not accessible by
        # integration" means the job is missing `actions: read`, which is a
        # very different problem from "CI has not run".
        message = payload.get("message")
        if message:
            return "missing the API answered: %s" % message
        return ("missing no tests run for this commit at all. release.yml does "
                "not re-run the suite, so there is no evidence it passed.")

    # ⚠ Newest first. `run_number` and `run_attempt` are integers; `created_at`
    # is a string and sorts correctly as ISO-8601, but only to the second.
    def order(run):
        return (run.get("run_number") or 0, run.get("run_attempt") or 0,
                run.get("created_at") or "")

    ordered = sorted(runs, key=order, reverse=True)
    finished = [r for r in ordered if r.get("status") == COMPLETED]
    if not finished:
        newest = ordered[0]
        return ("pending %d run(s), newest is #%s status=%r -- not finished"
                % (len(ordered), newest.get("run_number"),
                   newest.get("status")))

    newest = finished[0]
    conclusion = newest.get("conclusion")
    where = "#%s attempt %s (%s)" % (newest.get("run_number"),
                                     newest.get("run_attempt"),
                                     newest.get("html_url") or "no url")
    if conclusion == "success":
        return "success the newest completed tests run %s concluded success" % where
    return ("failed the newest completed tests run %s concluded %r. Fix it, "
            "push, and tag the commit CI went green on." % (where, conclusion))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        sys.stdout.write("missing usage: ci_verdict.py <runs.json>\n")
        return 0
    payload, reason = load(argv[0])
    if payload is None:
        sys.stdout.write("missing %s\n" % reason)
        return 0
    sys.stdout.write("%s\n" % verdict(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
