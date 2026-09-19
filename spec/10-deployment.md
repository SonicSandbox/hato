---
type: spec
title: hato — Deployment
desc: The two-package split, what publishing as two repos means, the Windows launcher, and the scheduled-run configuration.
date: 2026-09-07
---

# 10 — Deployment

---

## 🚨 RULED BY SONIC 2026-09-17 — hato SHIPS AS A STANDALONE, NOT AS A PACKAGE

> *"we don't need the pypi. There's not really a reason to build in an import ability right
> now, it's mainly just a github usage that will need the gui for an actual github
> release"*
>
> *"hato is more of a standalone than tsubasa is, in the sense that tsubasa is implemented
> into other codebases, this will likely not be until further notice. As such, it's fine to
> not need the pypi and pip for hato specifically. It will however be the script here that
> runs, etc as the existing functionality."*

**The distinction that decides this section: tsubasa is EMBEDDED, hato is RUN.** tsubasa
earns a PyPI package because other codebases import it — hato is the front door a person
points at a folder. So:

| | |
| --- | --- |
| **How it reaches a user** | The GitHub repository. Clone it, or download the zip |
| **How it runs** | `hato-run.cmd` (drag a folder on) or `python -m hato <folder>` from the clone |
| ⛔ **PyPI** | **Out of scope.** No distribution, no trusted publisher, no token, no `pypi` environment anywhere in the repo |
| ⛔ **`pip install hato`** | **Not the route, and not documented as one.** The README says clone-and-run |
| ▶ **A tagged GitHub release** | Waits for the **GUI** — Sonic named that as its precondition |

⭐ **This costs nothing to run, and that is why the launcher already works from a clone.**
`hato-run.cmd` adds its own folder to `PYTHONPATH` only when `hato\__init__.py` sits beside
it, which is exactly true of a clone and exactly false of an installed copy. The standalone
path was already the one with a test behind it.

⭐ **And it dissolves a gap this spec used to carry.** The line below saying `hato-run.cmd`
*"ships inside the wheel and is copied to a user-chosen location on first run"* was
**unimplementable and is now moot**: `package-data` only reaches inside `hato/`, the
launcher is at the repository root, and moving it into the package would break the very
`PYTHONPATH` guard that makes it work. There is no wheel route, so the launcher is simply
where it belongs.

### What was BUILT before this ruling, and is parked rather than deleted

⚠ **All of it is green and none of it is on the critical path.** Kept because the ruling is
*"not until further notice"*, not *"never"* — and because the audit half earns its keep
whether or not anything is ever uploaded.

| Parked | Where | Worth keeping because |
| --- | --- | --- |
| `pyproject.toml` | repo root | ⭐ **Still load-bearing:** it is what makes the dependency list, the licence notices and the console-script target **checkable**. `tests/test_packaging.py` (27 checks) asserts them against an `ast` walk of the source — which is how `httpx` was caught as a spec fiction and `py7zr`/`rarfile` as guarded extras |
| `hato/dev/` — `stamp` · `audit-wheel` · `scan-secrets` · `scan-content` · `verify-install` | `hato/dev/` | The two scanners are **artifact-independent**: `scan-secrets` and `scan-content` answer *"is a key or a third-party subtitle body in this tree"*, which matters for every public push, not just a wheel. 173 checks, every scanner proven able to fail against a planted positive |
| `.github/workflows/release.yml` | — | Builds and audits; ⛔ **uploads nothing**. Its P6 check — the installed artifact driven from outside every checkout — is the one whose absence shipped tsubasa 0.1.0 broken |
| `LICENSE` · `THIRD_PARTY_LICENSES.md` | repo root | GPL-3.0 requires them regardless of how the code is distributed |

▶ **To finish it later:** a PyPI pending-publisher form, a `publish` job with
`id-token: write`, and the post-publish verification in §*Release shape*. Nothing else is
missing — the audit, the scanners and the clean-venv install check are already built and
have never been the blocker.

---

## The package shape

**Two packages, one source tree.** `hato` declares `tsubasa` as a dependency. tsubasa
declares nothing about hato.

```
Workshop/tsubasa/     the engine — offline, no network dependency at all
Workshop/hato/        the front door — imports tsubasa, adds jimaku
```

```toml
# hato/pyproject.toml
[project]
name = "hato"
license = "GPL-3.0-or-later"
dependencies = ["tsubasa-sync>=0.1", "anitopy", "guessit", "httpx", "py7zr", "rarfile",
                "tomli>=1.1; python_version < '3.11'"]

[project.scripts]
hato = "hato.cli:main"
```

🚨 **AMENDED 2026-09-16 — THE DISTRIBUTION IS `tsubasa-sync`; THE IMPORT IS STILL `tsubasa`.**
This line read `tsubasa>=0.1`, and **`tsubasa` on PyPI is an unrelated project** (an
AI-personas framework, v0.2.2 when checked). Installed as written, hato would have pulled
somebody else's package and failed on its first `import tsubasa` — or worse, not failed.
`import tsubasa` in hato's code is unchanged and correct.

⚠ **Pin a minimum tsubasa version and mean it.** hato calls tsubasa's parser, discovery,
existing-subtitle reader and **`sync()`** — *amended 2026-09-16: this said `align()`, and
`tsubasa.align` is the low-level function over two arrays of cue-start times. The call
that syncs a video with a downloaded subtitle is `tsubasa.sync([(video, path)],
write=True)`.* **When any of those four change shape, hato's minimum bumps.** They are
both yours, which makes this cheap — and easy to forget.

⭐ **As of tsubasa 0.1.0 each of the four has a public name**, checked against a real scan
before release (`tsubasa/spec/05-interface.md` §*For code built on tsubasa*):

| hato needs | tsubasa 0.1.0 |
| --- | --- |
| Discovery | `tsubasa.scan(videos=folder)` → `.videos` |
| Filename → show + episode | `video.title` · `video.season` · `video.episode` · `video.episode_candidates` |
| Existing-subtitle check, per language | `scan.unpaired(lang="ja")` — ⚠ untagged counts as no language, matching `06-edge-cases.md` · `subtitle.lang` · `tsubasa.parse_subtitle_name()` |
| Sync, `Result` passed through | `tsubasa.sync([(video, original)], write=True)` → `SyncReport` of `Result`. ⭐ The explicit path supersedes nothing |
| ⭐ **A video's subtitle tracks** — is one Japanese text, and is there any at all | 🔨 **tsubasa's public track reader, being added by tsubasa's builder 2026-09-17.** Its name was not known when this was written — read `tsubasa.__all__`. ⛔ Never `tsubasa.container` |
| Is the install whole? | `tsubasa.self_check()` — run it in hato's own startup or `--doctor` |

✅ **The floor is `tsubasa-sync>=0.1.6`** — verified against the index 2026-09-18:
0.1.0–0.1.6 published, latest 0.1.6, only 0.1.0 yanked. 0.1.3 added `embedded_subs`; 0.1.5
added the English display-name reader hato's present-check relies on.

🚨 **RAISED FROM 0.1.5 TO 0.1.6 BY SONIC, 2026-09-18, AND IT IS A POLICY RATHER THAN A
CAPABILITY.** The two numbers mean different things and the distinction is worth keeping:
**0.1.5 is the oldest release that WORKS**; **0.1.6 is the latest**, and hato calls nothing
0.1.6 introduced. The floor therefore tracks the engine's current release rather than its
oldest compatible one.

⭐ **Defensible here** because both projects are Sonic's, hato ships clone-and-run rather
than as a package, and the development checkout is already 0.1.6 — nothing is being asked
for that is not present. ⛔ **The cost, stated so it is not rediscovered:** every future
tsubasa release drifts this line, and a floor pinned at latest refuses an install for a
version that would in fact work. `tests/test_packaging.py` asserts the number and keeps the
reason 0.1.5 mattered beneath it, so raising the floor did not delete why a floor exists
(`06-edge-cases.md` §6). ⛔ **Nothing in hato's release waits on tsubasa any more.**

### Development imports the vault checkout

⭐ **During the build, tsubasa is imported from the vault checkout** (`Workshop/tsubasa`) —
one source tree, so a fix lands for both. The release's clean-venv check installs from PyPI
instead.

**How, on this machine (2026-09-17):** one line in the user's site-packages —
`…\AppData\Roaming\Python\Python310\site-packages\hato-dev-tsubasa.pth` containing the path
to `Workshop/tsubasa`. ⛔ **Nothing ships it**, and deleting that one file undoes it. A
`pip install -e` was not used: the vault checkout has no `pyproject.toml` (it is clone-only),
and installing the public clone instead would silently run hato against a **different tree**
from the one its tests import.

🚨 **This was invisible for a whole build.** `conftest` puts the checkout on `sys.path` for
the suite, so 693 checks were green while `python -m hato sync` died on
`ModuleNotFoundError: No module named 'tsubasa'` — **found by running the product, not by a
check.** `tests/test_wiring.py` now runs the entry point in a subprocess with `PYTHONPATH`
dropped, so it cannot reopen silently. ⚠ That check failing is a statement about the
product, not the harness: the tool cannot run.

---

## Publishing — two repos, decided at release time

⭐ **Develop in one tree. Publish as two repos.**

| | |
| --- | --- |
| **Why two** | Each needs its own README and front page — that is how people find and evaluate a tool. tsubasa competes in a crowded space (ffsubsync has 7,868 stars); a sync tool buried in a subfolder of a downloader repo is invisible to the audience that would star it |
| **Why not now** | You are developing in TheForge either way. This is a release-time decision and it is reversible |
| **Cost** | Pushing two directories to two remotes, and a version bump when the shared layer changes |

🚨 **The reason it must not be one package is not tidiness.** hato downloads third-party
subtitle content from a site with no stated content licence. tsubasa never touches the
network. **Keeping that ambiguity inside hato protects the project with the mainstream
audience.**

---

## Release shape

> ⚠ **Read `doctrine/release` before running the release block. Pipe nothing inside it.**

**GitHub releases first.** PyPI later, and the same PyO3 sdist trap tsubasa documents
applies transitively — if hato ever pulls a compiled tsubasa accelerator, a user with no
Rust toolchain must still get a working install. **tsubasa's two-package split is what
handles that; hato inherits it and must not defeat it** by pinning the accel extra.

> 🚨 **SUPERSEDED 2026-09-18. THE SHIPPING ARTIFACT IS A WINDOWS STANDALONE ZIP, NOT A
> WHEEL.** `hato-<version>-windows-x64.zip` — three executables (`hato.exe` the window,
> `hato-cli.exe` the command line, `hato-watch.exe` the tray) plus a bundled CPython, so
> nothing needs installing. ⛔ `LICENSE` and `THIRD_PARTY_LICENSES.md` travel inside it,
> because GPLv3 §4/§6 require the licence to accompany conveyed object code, and
> `packaging/` is published as its Corresponding Source. Built by
> `packaging/hato.spec`; see RUNBOOK 7g.
>
> ⚠ The row below saying `hato-run.cmd` *"ships inside the wheel"* was already
> contradicted by this file's own §RULED, which calls it **unimplementable and moot** —
> `package-data` only reaches inside `hato/`, and the launcher lives at the repository
> root. Kept, struck, and dated rather than deleted.

| Artifact | Notes |
| --- | --- |
| ~~`hato-<version>.whl`~~ | ~~Pure Python. No compiled anything~~ — parked; no PyPI route was ruled |
| ~~`hato-run.cmd`~~ | ~~Ships **inside** the wheel~~ — never implementable; it is a repository file |
| Source tarball | GPL-3.0 requires the source be available. It is the repo |

**Version stamping:** a content hash, never a timestamp, never hand-bumped.

---

## ⭐ The Windows launcher

`hato-run.cmd` is the only user-facing artifact that is not a Python entry point.

```
hato-run.cmd                 → runs every folder in config.toml, prints, PAUSES
hato-run.cmd D:\Anime\Show   → runs that folder instead
<drag a folder onto it>      → same thing; Windows passes the path as %1
```

⚠ **Four things it must get right**, none of which a developer shell would catch:

1. ⭐ **It must not depend on the working directory.** Task Scheduler starts processes
   somewhere unexpected. Resolve every path absolutely, from `%LOCALAPPDATA%` or the
   script's own location — never from `.`
2. **It must `pause` when run interactively and NOT when scheduled.** A scheduled run that
   pauses waits forever, holding the lock, and the next run exits on the lock file
3. ⭐ **Output must degrade when it is not a console.** ANSI colour escapes in a log file
   are noise. Detect and strip
4. **It must exit with a real code.** `0` = ran; non-zero = it could not run at all.
   ⛔ **Refusals and NOT_FOUNDs are not failures** — they are normal outcomes and must not
   turn a scheduled task red

---

## Scheduled runs

**The OS scheduler, not a resident daemon.** Same coverage, nothing running in the
background.

| | |
| --- | --- |
| **Windows** | Task Scheduler → `hato-run.cmd --quiet`. ⚠ Run it once **from the scheduler** during the build and read the log. Its environment resolves `%LOCALAPPDATA%` and the keystore path differently from a developer shell, and **this is the single most likely thing to be discovered broken in production**. ✅ **DONE 2026-09-17** — see the battery trap below |
| **Linux / macOS** | cron or a systemd timer calling `hato --quiet` |
| **Log** | `%LOCALAPPDATA%\hato\hato.log`, rotated after `log.keep` runs |
| **Overlap** | A lock file. The second process exits cleanly with a message, never races |

🚨 **THE BATTERY TRAP — MEASURED 2026-09-17, and it is the one that would have shipped.**
`schtasks /create` defaults to **"No Start On Batteries, Stop On Battery Mode"**. On a laptop
running on battery the task sits at `Status: Queued`, **never runs, and reports
`Last Result: 0`** — the scheduler's value for *never run* is the same as its value for
*succeeded*. Measured here: no log line, no output, nothing done, and every signal green.

```powershell
# register it so it actually runs — settings, not the default
$action   = New-ScheduledTaskAction -Execute "<path>\hato-run.cmd" -Argument "--quiet"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries -StartWhenAvailable
$trigger  = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "hato" -Action $action -Settings $settings -Trigger $trigger
```

⛔ **Never trust `Last Result` — read hato's own log.** One scheduled run appends exactly one
`=== hato <timestamp> ===` block; measured, so a doubled run is visible by counting.

✅ **What the real scheduled run proved (2026-09-17):** the launcher resolves
`%LOCALAPPDATA%\hato` with no working directory to help it, detects the console, passes
`--quiet`, writes the log, exits **0**, and one run leaves exactly one log entry. The video it
was pointed at carried a Japanese track, so it short-circuited at *"already inside the
video"* for **0 API calls** — the embedded-track skip, working in production.

⛔ **No phone notifications** — ruled out 2026-09-07. **The log is the record**, and it is
not optional for a run nobody watches.

---

## Migration to another machine

| Moves | Does not move |
| --- | --- |
| `config.toml` | The working cache — rebuildable |
| The state DB, if you want to keep the negative cache and refusal history | The resolution cache — 2 API calls per show to rebuild |
| The keystore file | |

⛔ **Never sync the state DB between machines while both are running.** SQLite over a
sync service corrupts. If both machines need it, let each keep its own — the cost of a
cold cache is a handful of API calls.

---

## What is project-specific about this release

Everything generic lives in `doctrine/release`. Only these are particular to hato:

1. ⛔ **No secret ships.** The key is read at runtime from the keystore or the environment.
   A release build must be greppable-clean — **and the check for that belongs in CI, not
   in someone's memory**
2. **The `unrar` dependency is optional and external.** The release notes say so, and CI
   runs at least one job **without** it so the degradation path is actually executed
3. ⚠ **The GPL-3.0 notice and the dependency licence list ship with the artifact** —
   `anitopy` is MPL-2.0 and `guessit` is LGPL-3.0, and both require their notices to be
   carried
4. 🚨 **No subtitle content, no corpus and no fixture containing third-party subtitle text
   may ship in the release artifact.** API-response fixtures are fine — they are metadata.
   **Subtitle bodies are not ours to redistribute**
