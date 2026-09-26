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

⭐ **The floor is `tsubasa-sync>=0.1.8` — RAISED 2026-09-23 (RUNBOOK 9c), AND THIS TIME IT
IS A CAPABILITY:** 0.1.8 is the first release reading `.jp.` (Japan's country code where a
language goes) as Japanese, and the present-check relies on it — on 0.1.7 a user's
`.jp.srt` read as no language and hato fetched beside it. `tests/test_packaging.py` refuses
a requirement admitting 0.1.7, and `test_existing` finds a `.jp.` sidecar by name. ⚠ The
history below is kept: 0.1.3 added `embedded_subs`; 0.1.5 added the English display-name
reader; 0.1.6 was a policy floor (below).

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
(`06-edge-cases.md` §6). ⚠ **CI installs the engine from the index, so a floor raise
releases tsubasa FIRST** — ✅ tsubasa 0.1.8 went to PyPI 2026-09-23 and was verified from
the published bytes before hato 1.0.3's sync was pushed.

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

> ⭐ **14z — two more checks on the BUILT bytes, run by every release's smoke:** 5d, *Save them
> beside the video* through the frozen CLI over a real MKV (the track out at 0 requests, the next
> run present, the doctor's extractor OK and tsubasa at the floor); and the rehearsal's arm 3,
> *Go back* with that choice saved, against the REAL released version (C-1: the published 1.0.7
> refused the key 1.0.8 writes).

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

> 🚨 **AND THE HASH IS OVER CONTENT, NOT OVER BYTES — amended 2026-09-19 after it
> failed two tagged releases.** `stamp.digest()` normalises `\r\n` to `\n` before
> hashing, skipping any file containing a NUL byte (git's own text/binary test).
> Hashing raw bytes made the stamp valid on exactly one machine: `sync_from_vault.py`
> copies vault bytes verbatim, so the publish clone's **working tree** is LF, while
> git rewrites line endings on every checkout. Measured: 72/72 here, **50 differ** in a
> fresh Windows checkout, **9 differ** on Linux CI — all line endings, zero content.
> ⚠ The trade, stated: the stamp no longer notices a file whose only change is its
> endings. `.gitattributes` is what guarantees those, on every checkout, which a hash
> never could. Full detail in `LEDGER.md` §delivery.

---

## ✅ RELEASED — `v1.0.1`, 2026-09-19

| | |
| --- | --- |
| **v1.0.0** | 2026-09-19. Six real defects found by using it; see the 1.0.1 notes |
| ⭐ **v1.0.1** | `hato-1.0.1-windows-x64.zip` — **tag `3114321`, every gate green**: `tests` 12/12 *(recorded as 13/13 until 2026-09-23; the run has 12 jobs)*, `release` 2/2 (stamp gate included), suite 27/1616, smoke 20/20 against the copy unpacked outside the repo, and the **published asset downloaded and hash-verified** against the local artifact |
| ⭐ **v1.0.2** | `hato-1.0.2-windows-x64.zip`, 2026-09-23 — Layer 8, its adversarial pass, and D2 (the daily run registers a real task). Stamp `sha256:a5bf7e16…`; local zip `sha256 6dc4d797…72615`, 70,650,768 bytes; suite 29 suites / 1,982 checks; smoke **29/29** against the copy unpacked outside the repo; mutation gate 766/766 + M8y 83/83. ⭐ **Tag `6a2cf25`, every gate green:** `tests` 12/12 jobs, `release` 2/2, and the **published asset downloaded and hash-verified** against the local artifact. ⚠ Its first push (`559f5ce`) was red on 11 of 12 jobs and was never tagged — `LEDGER.md` §harness. The full mutation gate over the released tree: **849/849**. |
| ⭐ **v1.0.3** | `hato-1.0.3-windows-x64.zip`, 2026-09-23 — Layer 9: the subtitle-format preference, the untagged read, and the floor `tsubasa-sync>=0.1.8` (`.jp.`; tsubasa released FIRST and verified from its published bytes). Stamp `sha256:444c550d…`; local zip `sha256 adc8f136…ef0f`, 70,689,311 bytes; suite 29 suites / 2,055 checks; smoke **29/29** against the copy unpacked outside the repo. ⭐ **Tag `59a1561`, every gate green:** `tests` 12/12 jobs **on the first push**, `release` 2/2, and the **published asset downloaded and hash-verified** against the local artifact. The full mutation gate over the released tree: **943/943** (66 min). |
| 🚨 **D12 — in 1.0.2 AND 1.0.3** | Pressing *Run now* closes the window (Sonic, 2026-09-24, on two machines; four `0xc0000409` faults in his event log). Every gate above was green through it: no check pressed the button. **Fixed and RELEASED in 1.0.4** (2026-09-24) — `RUNBOOK.md` §*LAYER 10*; the smoke now presses it (6b), red on the 1.0.3 zip |
| ⭐ **v1.0.4** | `hato-1.0.4-windows-x64.zip` + `update.json` + `update.json.sig`, 2026-09-24 — LAYER 11 (hato updates itself), D12, 10b. Stamp `sha256:e6a857f5…`, 83 files; zip `sha256 70664555…7d58`, 77,016,517 bytes; suite 33 suites / 2,424 checks; smoke **45/45** against the copy unpacked outside the repo, the update REHEARSAL both ways. ⭐ **Tag `41e1515`, every gate green:** `tests` 12/12 jobs **on the first push**, `release` 2/2, and `verify-release` 9 held / 1 skipped by design (the three published assets identical to the local files). ⚠ `min_from` 1.0.4 — the first release with an updater; a 1.0.3 install is updated by hand, once |
| ⭐ **v1.0.5** | `hato-1.0.5-windows-x64.zip` + `update.json` + `update.json.sig`, 2026-09-24 — LAYER 12 (updates you can see) and its adversarial pass. Stamp `sha256:d957e21f…`, 83 files; zip `sha256 aec32726…97bf`, 77,034,241 bytes; suite 33 suites / 2,467 checks; smoke **45/45** against the copy unpacked outside the repo, the REHEARSAL updating the released 1.0.4 both ways. ⭐ **Tag `4d87a21`, every gate green:** `tests` 12/12 jobs **on the first push**, `release` 2/2, and `verify-release` **10 held / 0 skipped** — `an_install_takes_it` RAN: a copy at 1.0.4 heard *ready 1.0.5*. ⭐ **The first real auto-update:** the published 1.0.4 took the published 1.0.5 end to end (9/9) |
| ⭐ **v1.0.6** | `hato-1.0.6-windows-x64.zip` + `update.json` + `update.json.sig`, 2026-09-25 — LAYER 13 (nothing flashes, nothing glitches, what was slow is measured), its adversarial pass, and the pill's dot (Sonic's ruling). Stamp `sha256:f2dad263…`, 83 files — the stamp rehearsal's own hash; zip `sha256 ad6722fa…b187a`, 77,042,111 bytes; the stamped runner 33 suites / 2,499 checks; smoke **45/45** against the copy unpacked outside the repo, the REHEARSAL updating the released 1.0.5 both ways. ⭐ **Tag `927a28f`, every gate green:** `tests` 12/12 jobs **on the first push**, `release` 2/2, `verify-release` **10 held / 0 skipped** (a copy at 1.0.4 heard *ready 1.0.6*). ⭐ **The published 1.0.5 took the published 1.0.6 end to end** (9/9) — ⚠ the one download 1.0.5's own code makes: an open 1.0.5 window may flash once more fetching it |
| ⭐ **v1.0.7** | `hato-1.0.7-windows-x64.zip` + `update.json` + `update.json.sig`, 2026-09-25 — LAYER 14's first step (14a: *"When the video already has Japanese subtitles inside it"* — leave them there, or download from jimaku anyway) and its adversarial pass (a pick copied to surasura; a switched-back video no longer a pick; the keyboard kept across a Settings rebuild). Stamp `sha256:1b1b2588…`, 83 files — the stamp rehearsal's own hash; zip `sha256 01c99516…19141`, 77,054,334 bytes; the stamped runner 33 suites / 2,510 checks; smoke **45/45** against the copy unpacked outside the repo, the REHEARSAL updating the released 1.0.6 both ways. ⭐ **Tag `b85cffe`, every gate green:** `tests` 12/12 jobs **on the first push**, `release` 2/2, `verify-release` **10 held / 0 skipped** (a copy at 1.0.4 heard *ready 1.0.7*). ⭐ **The published 1.0.6 took the published 1.0.7 end to end** (9/9). ⚠ Still bundles tsubasa **0.1.8** — 14c needs 0.1.9 |

🚨 **THE RELEASE SEQUENCE IS IN `LEDGER.md` §delivery, as *"THE RELEASE SEQUENCE THAT
ACTUALLY HOLDS"*.** It is one list and it lives in one place; do not restate it here.
Two things from it that are easy to skip and expensive to skip:

- ⛔ **`package_standalone.py` does not freeze.** It packages whatever is already in
  `dist/standalone/hato`, so a skipped PyInstaller step ships the *previous* build with
  the *current* version number on it.
- ⛔ **The release API creates the tag at the DEFAULT BRANCH HEAD.** Nothing may be
  pushed between the green run and the tag, or the tag names a commit nothing tested.

⚠ **`v1.0.1` was cut twice.** The first cut was tagged at a commit whose stamp was
still the raw-byte kind, so `release.yml` was red on it. Sonic ruled the re-cut
2026-09-19 — delete the release and tag, rebuild, re-tag — on the grounds that the
asset had no third-party downloads and `1.0.1` should keep meaning *the six user-visible
fixes* rather than spending a version number on invisible tooling. ⛔ **The guard that
allows this refuses above one download**, and the one it tolerates is the hash
verification's own fetch. Above that, cut a new version instead: re-cutting a release
somebody already holds changes what that number means.

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

⭐ **hato registers it itself — the window's *"every day at"* switch (RUNBOOK 8y, D2,
2026-09-23).** `hato/schedule.py`, and ⛔ **Task Scheduler is the only state**: no config key
says the daily run is on; the switch reads the task on every open (`config.schedule` is only
the time to register at).

| | |
| --- | --- |
| **Registered** | `schtasks /create /tn hato /xml <file> /f` from hato's own XML: battery settings **written out** (`DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries` false, `StartWhenAvailable` true), `WakeToRun` false, no `UserId` (it lands under the person's own SID, unelevated — measured), a start boundary **never already past** |
| **What it runs** | `hato-watch.exe --scheduled` (from a clone `pythonw hato-watch.pyw --scheduled`) — the watcher's windowless program, which runs `hato-cli --quiet --wait` hidden and hands back its exit code. 🚨 **Never a console program**: measured two-arm 2026-09-23, a console program started by Task Scheduler got a **visible console window**; this chain got none |
| **Read back** | `schtasks /query /xml` after every write. 🚨 Its XML **declares UTF-16 and is written in the console's OEM code page** — `日本` comes back `??` — so a command is compared on its ASCII skeleton |
| **Proven for real** | a real trigger fired the real chain against an isolated store: working directory `C:\Windows\system32`, no stdout, exit 0, one log block, 0 API calls |

⚠ A task named `hato` made by hand from the README reads **ON** and says what differs — a
different program, no battery start, no catch-up — and switching it off and on replaces it
with hato's own.

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
