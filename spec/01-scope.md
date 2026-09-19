---
type: spec
title: hato — Scope
desc: The objective in Sonic's words, the ruled relationship to tsubasa, launch vs evolution, the stack, and what is irreversible.
date: 2026-09-07
---

# 01 — Scope

## The objective, in Sonic's words

> *"a program that will take the name of a downloaded video, identify the video, using the
> api for something like jimaku.cc, it will download the corresponding subtitles for that
> video (the ep number, etc) and will then use subsync to sync it, and then place the
> subtitles named appropriately in the same folder (or a different one if specified) with
> room to adjust how that works. We will have the ability to provide an individual file or
> a directory and it will find for all the videos. It will also NOT download one if there
> already exists one."*

**Unpacked, each clause is a requirement:**

| Clause | Requirement |
| --- | --- |
| *"take the name of a downloaded video, identify the video"* | Filename → show → jimaku entry. **A hypothesis, never a decision** — see Rule 1 |
| *"the api for **something like** jimaku.cc"* | jimaku is the only source. The calls live in their own module so a second one would be an added file, not a rewrite. ⛔ **OpenSubtitles is out of scope entirely** — ruled |
| *"download the corresponding subtitles (the ep number, etc)"* | Episode alignment. Harder than it sounds — see `02-data-model.md` §*Episode alignment* |
| *"then use subsync to sync it"* | One `sync()` port, backed by **tsubasa only** — ruled 2026-09-16, no subsync adapter. *(Port renamed from `align()` the same day — see `03-permissions.md`)* |
| *"place the subtitles named appropriately"* | `<video-basename>.ja.<ext>` — the one form Plex, Jellyfin **and** Emby all document. ⭐ **Written by tsubasa; the original download is kept in hato's `subs_dir`, never deleted** — ruled 2026-09-17. Measured the same day: it loads **and is selected** in Sonic's mpv |
| *"in the same folder (or a different one if specified)"* | Default beside the video. `--out <dir>` mirrors the source tree rather than flattening |
| *"with room to adjust how that works"* | `--out`, `--lang` and `subs_dir` at launch. ⚠ **The naming template moved to Evolution 2026-09-17** — tsubasa owns naming now, and a template would mean hato writing into media folders itself |
| *"an individual file or a directory"* | Both. Recursive by default, `--no-recurse` opts out |
| *"NOT download one if there already exists one"* | Per **(video × language)**. See `02-data-model.md` §*Canonicity* |

## The one thing that does not exist today

**Nothing fetches Japanese subtitles for a local folder of videos without a media-server
stack behind it.**

Bazarr does this job well and is the closest prior art — but it *"does not scan your
disk… It only manages the series and movies that are indexed in Sonarr and Radarr."*
That means the *arr stack, a media server, and a library that has already been renamed
into `SxxExx` form. **Point-at-a-folder is the gap**, and it is the whole reason this
exists.

---

## ⭐ The relationship to tsubasa — RULED 2026-09-07

> **Two packages. One source tree. `hato` imports `tsubasa`. tsubasa never imports hato.**

Options considered and why this one won are in the conversation record; the short version:

| Rejected | Why |
| --- | --- |
| Two fully independent tools | The filename parser, the discovery walk, the naming rule and the existing-subtitle reader are all shared. **Two copies would drift — a certainty, not a risk** |
| `tsubasa fetch` as a subcommand | tsubasa's *"no network during a sync run"* stops being a **testable property**. It also drags an HTTP stack, retry logic and archive extraction into a tool meant to freeze to one binary — and gives its much larger sync-only audience a jimaku API client they never asked for |

**What the one-way arrow buys:**

- The shared layer exists **once**. A parser fix lands for both by construction
- tsubasa keeps a network dependency of **zero**, so "this tool makes no network calls"
  stays something a test can assert
- **Zero changes to tsubasa's ruled behaviour.** One structural note in its `CONTEXT.md`
  and `10-deployment.md`; nothing in the signed-off spec
- 🚨 **Legal surface stays contained.** hato downloads third-party subtitle files from a
  site with no stated content licence. tsubasa never touches the network and must not
  inherit that ambiguity — it is the one with the mainstream audience

⭐ **`hato <folder>` is the front door and does the whole job**: walk, pair what is already
there, fetch what is missing, sync, name, dedupe. You never run two tools. There is
deliberately **no reverse hook** on tsubasa — it would be the same operation with the
arrow pointing the wrong way, and it is the only part that would have required amending a
signed-off spec.

### 🚨 What hato needs from tsubasa before it can run at all

1. **Filename → show + episode** (tsubasa Track A)
2. **Video discovery in a folder** (Track A)
3. **Existing-subtitle detection + the naming rule** (Track A / step 3a)
4. `sync()` — `tsubasa.sync()`. *(Originally: covered by a subsync adapter so Track B was not
   blocking. See the ruling below.)*

⭐ **UPDATE 2026-09-16 — all four are BUILT, in tsubasa 0.1.0, under public names.** Checked
against a real scan before release, not read off tsubasa's RUNBOOK; the table is in
`10-deployment.md`. One gap was found and closed in the check: discovery was
**language-blind**, so a video carrying only an English subtitle read as covered and hato
would never have fetched for it — `scan.unpaired(lang="ja")` is the fix.

⭐ **RULED 2026-09-16 (Sonic): NO subsync adapter. tsubasa is hato's only sync backend.**
The adapter existed so hato was not blocked on tsubasa's Track B; tsubasa has shipped
(`pip install tsubasa-sync`), so the fallback is dead weight to build, test and maintain.
⚠ The `sync()` PORT stays — as the seam the suite stubs, not as a place to swap engines.

**Items 1–3 are tsubasa's Track A, which its own RUNBOOK builds first regardless.**
Building hato is not a detour around tsubasa — it forces the most valuable third of it to
get built, for two consumers instead of one.

---

## Launch

1. **Video discovery** — a file or a directory, recursive by default
2. **Identification** — filename → normalized title → jimaku entry, cached per show
3. **The jimaku client** — search, list files, download. Rate-limit aware
4. ⭐ **Episode range alignment** — derive the offset locally, per release group
5. ⭐ **Candidate ranking** — every episode has several candidates. **Load-bearing, not a backstop** (measured: 4+ per episode on a real entry). ⭐ **`.ass` first — ruled 2026-09-17**
6. **The existing-subtitle check** — per (video × language), filesystem canonical
7. **The state DB** — a negative cache and attempt log. **Only ever prevents work**
8. **Batch archive support** — `.zip` / `.7z` / `.rar`, unpacked in the cache dir. ⭐ **OFF by default, a setting the person turns on — ruled 2026-09-17 (Sonic):** *"are we concerned about auto-doing that? there may be bad files downloaded in the zip"*. Unpacking a stranger's archive is the one place hato acts on structure it did not author, so it is opt-in
9. **The `sync()` port** — `tsubasa.sync()` behind it, and a stub for the suite. No subsync adapter *(ruled 2026-09-16; renamed from `align()` the same day)*
10. **Placement + naming** — **tsubasa writes** `<video>.ja.<ext>` beside the video, original format preserved; **hato keeps the original in `subs_dir`, never deleted** *(ruled 2026-09-17)*
11. **Candidate escalation** — on REFUSED, try the next candidate, cap 3
12. **CLI** — the identify block, the per-episode lines, `--dry-run`, `--json`
13. ⭐ **`hato-run.cmd`** — double-click, or drag a folder onto it. Also what the OS scheduler points at
14. **The config file** — watched folders, language, output policy, candidate cap
15. **Skipping AI-generated subtitles** by default
16. **Embedded-track short-circuit** — a video with a Japanese text track already has its subtitle, in sync, for free. ⭐ **And a video with NO subtitle track is skipped before download** — tsubasa cannot sync it until its audio path exists *(ruled 2026-09-17)*. Both read through tsubasa's public track reader
17. ⭐ **Kept originals** — every subtitle a synced file was made from stays in `subs_dir`, never deleted, and re-syncs a deleted subtitle with zero network *(ruled 2026-09-17)*

## Evolution

- ~~**A GUI entry point** — ⛔ **not at launch.**~~ ✅ **SUPERSEDED 2026-09-18: THE WINDOW
  IS BUILT AND SHIPPED** (`hato/gui/`, PyQt6, RUNBOOK 7c–7e), together with a resident
  tray watcher (`hato/watch.py`) and a Windows standalone build. ⚠ The prediction below
  was also wrong about its shape: it is **not** "a dumb terminal that runs a command and
  streams output" and **not** tkinter — it is a three-tab window with its own state, and
  the toolkit is an optional extra so the CLI never pays for it. Struck rather than
  deleted, because the reasoning is the record of why it waited.
  Once tsubasa's tkinter window exists it is a
  two-line reuse (the window is a dumb terminal that runs a command and streams output).
  Until then, `hato-run.cmd` covers both the routine case and the ad-hoc one, because
  **dropping a folder onto a `.cmd` passes it as an argument**
  - ⭐ **2026-09-17 — the precondition is MET and Sonic asked for it.** tsubasa's window
    shipped (its RUNBOOK 3d, 2026-09-10): `gui/app.py` is the only module that imports
    tkinter, `gui/run.py` spawns `python -m tsubasa --json` and paints the NDJSON off a
    thread, **`gui/settings.py` GENERATES its panel from a `SCHEMA`** and `gui/scale.py` is
    the DPI layer. hato's `--json` is the same NDJSON contract, so the same shell fits.
  - **What Sonic asked it to do**, in Sonic's words — *"set up settings, the folder, check
    whether it is auto or just on launch through hato"*: the `config.toml` fields, the
    watched folders and `subs_dir`, and ⭐ **an auto-run toggle that registers or removes the
    Windows scheduled task** and says when it next runs. ⚠ **That toggle is new — nothing in
    either project has it**, it changes state outside the app, and it must be reversible,
    never silently re-registered, and never left behind by an uninstall.
  - ⛔ **Its layout needs a ruling with PICTURES before it is built**, the way tsubasa's 3d
    did — and ⚠ that step's adversarial pass returned **29 findings against 36 green
    checks**, almost all from LOOKING at the shipped window. Budget it as its own build.
- A second source, if jimaku ever goes away. The client module boundary is the whole
  preparation — do not build an abstract provider base class
- Per-language operation beyond Japanese. The language field is structured from day one
  (tsubasa requires it anyway); only the fetch side is Japanese-specific
- A resident daemon. ⛔ **Not at launch** — the OS scheduler pointed at `hato-run.cmd` does
  the same job with nothing running in the background
- ⭐ **Raw videos — no subtitle track inside.** Syncable once tsubasa's audio path (its
  RUNBOOK B6) ships. **37.5% of 120 real videos had no track** (`tsubasa/spec/08-probes.md`
  §E). Sonic ruled 2026-09-17 not to wait: most of Sonic's videos carry a track
- **`--name-template`** — moved here 2026-09-17. tsubasa owns naming; if it returns it lands
  as a tsubasa option, never as hato writing into a media folder

## Explicitly dropped — not launch, not evolution

| Dropped | Why |
| --- | --- |
| **OpenSubtitles** | Ruled out by Sonic. Also **20 downloads/day** on the free tier, which cannot sweep a library — it would be a single-file rescue misrepresented as a second provider |
| **Kitsunekko direct** | No API at all — a PHP directory listing, and `robots.txt` is `Disallow: /`. jimaku continuously mirrors it, so hitting it directly is strictly worse |
| **Animetosho as a subtitle source** | It is a release mirror, not language-indexed. Subtitles are inside per-release archives |
| **Phone notifications on scheduled runs** | Ruled out by Sonic. **The log stays** — a run nobody watches must leave a record |
| **The TVDB / XEM / anime-lists numbering stack** | See below |

### ⛔ Why the episode-numbering datasets are NOT used

Media servers need TVDB `absoluteNumber` → XEM scene maps → `anime-lists` offset brackets
→ AniList, because they must *display* a canonical episode number. **hato displays
nothing.** It matches a video file to a subtitle file, and **both sides are release-group
filenames from the same universe.**

Measured reasons not to take the dependency anyway:

- **62.5% of anime series have no XEM map at all** — including One Piece, the single
  most-cited case
- **38% of the shows that DO have a map use scene numbering that differs from TVDB's**,
  and which convention a given release used is not inferable from its filename
- **Fribb's `anime-lists` and ScudLee's `Anime-Lists` have no licence file whatsoever.**
  All rights reserved. Bazarr ships against them anyway; that is Bazarr's exposure
- `manami/anime-offline-database` was **archived read-only 2026-07-04** and is frozen
  forever

⭐ **`anime-relations.txt` (Taiga/erengy) is public domain** and directly encodes
*absolute N → which entry, which local episode* for 545 shows. **Treat it as an
accelerator, never a dependency** — the same rule tsubasa applies to its alias table.

---

## Scale — and what changes at 10×

Sonic: *"Generally I would point at a few a day from different series, or all of a single
series."*

| | |
| --- | --- |
| **Typical run** | A handful of files, or one season |
| **Library over time** | Grows; re-runs must stay cheap |
| **At 10×** | Linear in **file count**. A plain loop is correct — ⛔ **do not build an indexed join**, tsubasa's O(videos × subtitles) concern does not apply here because hato never pairs two folders against each other |

🚨 **The binding constraint is not compute, it is the 25 req/60s API budget** — and the
worst case for it is *"a few a day from different series"*, because each different series
costs its own resolution and cannot be amortised. **This is exactly what the resolution
cache exists for:** a show resolves once, forever.

---

## What is irreversible

**Only one thing: writing to the user's media folder.** Everything else is a cache that
can be deleted.

hato itself writes **nothing** into a media folder *(ruled 2026-09-17)*. It calls
`tsubasa.sync([(video, original)], write=True)`, and on that explicit path tsubasa
**supersedes nothing**, so nothing is trashed. Every one of tsubasa's mitigations still
applies in full, and this pack does not restate them — see `tsubasa/spec/01-scope.md`
§*What is irreversible* and `03-permissions.md`.

The mitigations hato adds on its own account:

- ⛔ **Nothing partial ever lands beside the media.** Download, extract and align in the
  cache dir; write the finished file only
- **Nothing is written unless the verdict is CONFIDENT**
- `--dry-run` prints every intended action, makes **zero** network calls beyond
  identification, and writes nothing

---

## The ratified stack

| Choice | Ruled | Why |
| --- | --- | --- |
| **Language** | **Python** | It imports tsubasa directly — no subprocess, no JSON boundary, no version skew against the thing it exists to feed. The filename parsers are Python too |
| **Licence** | **GPL-3.0** | Matches tsubasa and surasura. It also unlocks reading Bazarr's jimaku provider (GPL-3.0, 417 lines, already solves the retry ladders) and Sonarr's parser table |
| **Sync backend** | **tsubasa, through one `sync()` port** | ⭐ **Ruled 2026-09-16: no subsync adapter** — tsubasa has shipped, so a fallback is weight with no job. The port stays as the suite's seam, shaped to tsubasa's `Result` exactly. ⚠ *Renamed from `align()` the same day: `tsubasa.align` is the low-level cue-array aligner, and the name invited calling it with two paths* |
| **Filename parsing** | **anitopy primary, guessit fallback** | Benchmarked head-to-head — see `08-research.md`. Both are dependencies, neither is vendored |
| **Subtitle source** | **jimaku.cc only** | Ruled |
| **HTTP** | `httpx` or `requests` — builder's choice | Nothing here needs async. One request at a time is well within budget |
| **Archives** | `zipfile` (stdlib) · `py7zr` · `rarfile` | ⚠ `.rar` needs an external `unrar`; degrade gracefully if absent, never error |
| **Config** | **TOML** at `%LOCALAPPDATA%\hato\config.toml` | `tomllib` is stdlib on 3.11+. ⚠ **This laptop runs Python 3.10.0** (checked 2026-09-17) — read through `tomli` below 3.11 |

### Dependency licence check

| Package | Licence | Status |
| --- | --- | --- |
| `anitopy` | **MPL-2.0** | Fine as a dependency. File-level copyleft only if you modify its files |
| `guessit` | **LGPL-3.0-or-later** | Fine as a dependency. ⛔ Do not vendor and relicense |
| Bazarr / Sonarr source | **GPL-3.0** | ✅ Readable **and** vendorable, because hato is GPL-3.0 |
| jimaku server source | **AGPL-3.0** | Reference only — do not vendor. AGPL's network clause is not something to inherit casually |

⚠ **The subtitle *content* on jimaku carries no stated licence.** It is user-uploaded
fansub work. hato downloads it **to the user's own machine at their own request** and
redistributes nothing. ⛔ **Never bundle, mirror or republish subtitle content.**
