---
type: spec
title: hato — Interface
desc: The ruled CLI output in both modes, the config file, the double-clickable launcher, the naming rules, and the library API.
date: 2026-09-07
---

# 05 — Interface

⭐ **`hato <folder>` is the front door and does the whole job** — walk, skip what is already
there, fetch what is missing, sync, name, dedupe. The user never runs two tools.

---

## The CLI output — RULED 2026-09-07, do not redesign

Sonic ruled **both modes, with the identify block printed on every run.** It inherits
tsubasa's grammar exactly, because a user running both must not have to learn two.

### Mode A — the normal run

```
hato  ~/Anime/Katainaka S2                                     24 videos

  片田舎のおっさん、剣聖になる  S2
  ↳ parsed "Katainaka no Ossan Kenseininaru" → jimaku entry 3841
                                                    2 API calls · 26 files listed

  ✗  07   NOT FOUND   jimaku 3841 has no episode 7 — will retry after 2026-09-14
  ✗  12   REFUSED     2 candidates fetched, both failed timing (81%, 74% match)

  ⊙  01 02 05         subtitle already present — skipped, no request made
  ⊘  08 09            no subtitle track in the video — can't sync yet, nothing downloaded

  ✓  03   ↓ 38 KB   +0.13s   96% · certain    → …S2 - 03.ja.ass
  ✓  04   ↓ 41 KB   +0.12s   95% · certain    → …S2 - 04.ja.ass
  ⚑  06   ↓ 36 KB   -33.07 / -42.96 @3:18   91% · strong · 2 segments
                                              → …S2 - 06.ja.srt

  17 fetched · 3 skipped · 2 can't sync yet · 1 not found · 1 refused     4 API calls · 41.2 s
```

### Mode B — `--dry-run`, the plan

```
hato  ~/Anime  --dry-run                          3 folders · 68 videos

  IDENTIFY                                                        6 API calls
  ✓  Katainaka S2      → jimaku 3841    24 vids · 26 subs
  ✓  Frieren S1        → jimaku  902    28 vids · 28 subs
  ⚠  Random.Show.2019  → no direct match
                         fuzzy "Random Show" → jimaku 7712 (low score)
                         ⤷ LOW CONFIDENCE — will fetch 3 candidates, timing decides

  PLAN                                                      nothing written
     49 to fetch · 14 already present · 2 no subtitle track · 3 uncertain
     ~2.1 MB · est. 8 API calls · est. 90 s

  Run again without --dry-run to apply.
```

### The properties that are not negotiable

| Property | Why |
| --- | --- |
| **Problems first** | The one thing needing attention must not sit below 19 successes |
| **Evidence on every line** | `96% match · certain`, never a bare tick |
| **`old → new` shown** | The user sees what happened to their folder before trusting it |
| ⭐ **What it thinks the show is, up top** | Identification is the step most likely to be silently wrong, and the only one cheap to eyeball before anything downloads |
| ⭐ **API calls spent, on every run** | It is a shared, metered resource. A user who cannot see the cost cannot notice a runaway loop — and it is the first line a bug report needs |
| **A retry date on every NOT_FOUND** | Distinguishes *"nothing yet"* from *"broken"* without the user having to ask |

⚠ **Never show a raw confidence multiple in the default output.** *"4.6× chance"* is an
internal decision statistic and means nothing to a person. `--verbose` and `--json` only.

> ✅ **BUILT 5a, 2026-09-17 — `hato/report.py`, rendered by `hato/commands/run.py`.** Both
> modes reproduced, every property above pinned by a check in `tests/test_endtoend.py`, and
> both modes snapshotted. **Six things the mocks did not decide, decided here and written
> down rather than invented quietly:**
>
> 1. 🚨 **The mock's word `certain` no longer exists.** tsubasa removed it from its closed
>    confidence vocabulary on **2026-09-09** — it is a substring of `uncertain`, which
>    re-armed `LEDGER.md` §Interface's defect for any consumer that substring-matches. The
>    four words are **`locked` · `strong` · `fair` · `uncertain`**. The renderer prints
>    `result.verdict_word` verbatim, so the shape above is the mock's and the word is the
>    engine's. ⛔ **Do not "restore" `certain` to this file.**
> 2. 🚨 **Mode B's `~2.1 MB` and `est. 90 s` CANNOT BE COMPUTED** from what `pipeline.run()`
>    returns. A `PLANNED` result carries the first candidate's **name** and no size, the
>    jimaku file dicts never leave the run, and no timing model exists anywhere in this
>    project. **A made-up megabyte count in a plan a person decides on is worse than no
>    count**, so the PLAN block prints `est. N API calls to apply this` — which IS derivable
>    — and omits the other two. *Sonic rules whether the size is worth a `planned_bytes`
>    field on `VideoResult`; that is a `pipeline.py` change, not a renderer one.*
> 3. ⭐ **`--json` emits ONE FINAL `{"type": "run"}` OBJECT** after the per-video ones. *One
>    object per video* and *the API-call count on every run* cannot both hold in a stream
>    with nowhere to put a run total. Every object carries `type`, so a consumer filters
>    rather than guesses.
> 4. ⭐ **`⚑` means: written, and worth a look** — more than one segment (a cut file), or
>    `runtime_check == "failed"`. The mock shows `⚑` on a two-segment row and says no more.
> 5. ⚠ **`--verbose` cannot show *"every API call with its rate-limit headers"*.**
>    `hato/client.py` keeps only the **last** metered call's (`last_rate_headers`). The
>    verbose tail prints that one and says so. Fixing it is a client change.
> 6. ⚠ **A folder path longer than the line is clipped from the LEFT** (`…\Show S2`), the
>    same idiom the output already uses for filenames. The mocks have no answer for a path
>    wider than any terminal, and the alternative is the header running off the screen.
>
> 🚨 **AND A DEFECT IN SOMEBODY ELSE'S FILE, FOUND BY LOOKING AT THE OUTPUT.**
> `pipeline._all_refused` is handed `len(fresh)` — the number of candidates **available** —
> and prints it as *"N candidates fetched and retimed"*. With `--candidates 1` over a
> 13-file episode the refusal reads **"13 candidates fetched and retimed"** when **one** was;
> and because it then tests `offered > tried` (13 > 13) it **withholds the
> *"try `--candidates 3`"* line**, which is the fix the person most needs. That is
> §*Evidence on every line* failing on the row that most depends on it. ⛔ **Not repaired by
> 5a** — the renderer must not rewrite the pipeline's reason into a second source of truth.
> `tests/test_endtoend.py::test_how_many_candidates_were_really_tried_is_recoverable` pins
> the truth that is recoverable (`candidates_tried` in `--json`), and the Mode A snapshot
> carries the wrong sentence so that fixing it shows up as a red check.

### Other modes

| Flag | Behaviour |
| --- | --- |
| `--dry-run` | Mode B. Identification runs (it is cheap and cached); **nothing is downloaded, nothing written** |
| `--json` | NDJSON, one object per video. The same structure the library returns |
| `--verbose` | Adds raw multiples, per-candidate scores, every API call with its rate-limit headers |
| `--force` | Ignores the state DB entirely — re-tries refusals, re-queries negatives |
| `--candidates N` | How many candidates to try before refusing. Default **3** |
| `--out <dir>` | Write there instead of beside the video, **mirroring the source tree** |
| `--subs-dir <dir>` | Where the kept originals go. Default `%LOCALAPPDATA%\hato\subs`. ⛔ Refused inside a scanned folder |
| `--lang <code>` | Default `ja` |
| `--no-recurse` · `--allow-ai` | Opt-outs |
| ⭐ `--archives` | **Opt-IN, default OFF — ruled 2026-09-17.** Unpack `.zip` / `.7z` / `.rar` candidates in the cache dir. ⛔ Off, an archive-only candidate is skipped with a reason that names this flag — never silently |
| `--retry-now` | *Look again now* (RUNBOOK 8e). Ignores the waiting period and nothing else: a file already refused for a video is never downloaded again, and a blacklist still stands |
| `--only <video>` | Repeatable. Only these videos, from the folders given — and such a run leaves `last-run.json` alone. ⛔ A video no walk of this run could reach (outside every folder, in a skipped one, or in a subfolder under `--no-recurse`) exits **2**, never 0 having looked at nothing |
| `--only-list <file>` | The same, one video per line (UTF-8, blank lines ignored) — the window's route past Windows' 32,767-character command line |
| `--wait` | Queue behind a run that holds the lock (up to 3 h) instead of exiting *"busy"*. ⭐ Every run the tray starts passes it: the tray checks the lock and then spawns, and a run starting in that gap used to void the tray's |

> ⚠ **Added 2026-09-22** by Layer 8 and its adversarial pass (`ADVERSARY-2026-09-22.md`).
> The two views that go with them are `hato problems [--json]` (what still needs a person,
> read from the state DB; ⛔ exits **1** with `"ok": false` when that store cannot be
> read, never an empty *"nothing needs you"*) and `hato state --clear [--yes]` (dry
> unless `--yes`) — RUNBOOK 8c and 8g.

---

## Naming and placement

> Keep **one subtitle per (video × language)**. Name it exactly
> `<video-basename>.<lang>[.forced|.sdh].<ext>`.

**This is the one form Plex, Jellyfin and Emby all document.** Verified against each
vendor's own documentation — see `08-research.md`.

### ⭐ Who writes it, and where the original goes — RULED 2026-09-17

**tsubasa writes the synced file. hato keeps the original it was made from.**

```
D:\Anime\Frieren S2\
  Frieren S2 - 01.mkv
  Frieren S2 - 01.ja.ass                     ← tsubasa's synced copy. mpv loads it
%LOCALAPPDATA%\hato\subs\Sousou no Frieren 2nd Season\
  [Group] Sousou no Frieren - 29 [...][JPN].ja.ass    ← the original, kept for good
```

| Rule | Why |
| --- | --- |
| 🚨 **The original carries `.ja` before its extension** | Measured: untagged, tsubasa writes `<video>.ass` — and `unpaired(lang="ja")` reads that as *no Japanese subtitle*, so every run fetches again |
| **`subs_dir` sits outside every scanned folder** | Inside one, the originals are discovered as candidates for the videos beside them |
| **Only USED originals are kept** | A refused candidate stays in the disposable cache, its hash recorded so it is never fetched again |
| ⭐ **Measured in Sonic's own mpv, 2026-09-17** (`sub-auto=fuzzy`) | `<video>.ja.ass` beside the video loaded **and was the selected track**, ahead of an embedded English one — `08-research.md` §*mpv* |

| Rule | Why |
| --- | --- |
| `ja` (or `jpn`) | Both are safe on all three. Japanese has **no ISO 639-2 B/T split**, so it dodges the `fre`/`fra` class of problem entirely |
| ⛔ **Never `ja-JP`** | Correct BCP 47 and **broken on Jellyfin** |
| ⛔ **Never `jap`** | Not a valid ISO code and never was. Pure folk abbreviation |
| ⛔ **Never a bare flag without a language first** | `sdh` is a real ISO 639-3 code |
| **Original format preserved** | `.ass` stays `.ass`. Converting to `.srt` destroys styling and is not this tool's business |

### `--out` mirrors, never flattens

```
~/Anime/Katainaka S2/ep01.mkv   --out ~/Subs   →  ~/Subs/Katainaka S2/ep01.ja.ass
```

⛔ **Flattening would collide** the moment two shows both have an `ep01`.

> ⚠ **AMBIGUOUS, AND DECIDED AT 4b's BUILD (2026-09-17).** That line names the VIDEO, not the
> scanned root, and the two readings give different rules — `out / relpath(video_dir, root)`
> if the root was `~/Anime`, or `out / root.name / relpath(...)` if it was
> `~/Anime/Katainaka S2`. Both produce the line exactly as written, for their own root.
>
> ⭐ **Built: `out / relpath(video_dir, root)` — the tree BELOW the scanned root.** The other
> reading collides on this file's own documented config: `folders = ["D:/Anime",
> "E:/Downloads/Anime"]` both end in `Anime`, so every show of the second would land on the
> first's. Under the rule built they merge per show, which is what a person means by
> *mirroring*. A video sitting directly in the root therefore lands directly in `--out`.
>
> 🚨 **The present-check asks the same function** (`hato/keep.py::target_dir`). That is the
> defect `03-permissions.md` recorded at 4a — under `--out` the previous run's file is in the
> mirrored directory, and a present-check looking beside the video makes hato re-fetch every
> run while tsubasa refuses the write for ever. **Sonic rules if the other reading was meant.**

### ~~The naming template~~ — moved to Evolution 2026-09-17

tsubasa owns naming now (§*Who writes it* above), so a hato-side template would mean hato
writing into a media folder itself — exactly what the ruling removed. If it returns, it
lands as a **tsubasa** option. The token set it had, kept as the record: `{video}` ·
`{lang}` · `{ext}` · `{flags}`.

---

## The config file

⭐ **RULED 2026-09-17: everything hato keeps lives in ONE per-user folder, and it is hato's
own.** Sonic asked for it *"localized"*, tried a shared `SonicSandbox\Hato` vendor folder,
reverted that, and left the rest of the choice here: **hato keeps its own root; it does not
live inside tsubasa's.**

```
%LOCALAPPDATA%\hato\                      (~/.local/share/hato elsewhere)
  config.toml        settings. ⛔ NEVER the key
                     ⚠ off Windows this ONE file is XDG's, at ~/.config/hato/config.toml
                       — settled 2026-09-17: config is config, data is data. Everything
                       else in this box is in the root on every platform
  key.txt            the jimaku key — what the window writes, and what a stranger fills in
  hato.log           the run log
  state.db           attempts, negatives, the blacklist
  cache\             downloads in flight, archives, refused candidates — disposable
  subs\              ⭐ kept originals, never deleted
  hato.lock          one run at a time
```

⚠ **`HATO_CACHE` relocates the WHOLE root** (not just `cache\`), which is what keeps a test
run out of the real folder. `HATO_CONFIG` overrides the config file. Both must be absolute.

⚠ **surasura does not exist yet** (checked 2026-09-17), so nothing pairs with this today —
**hato sets the convention and surasura follows it.** tsubasa already ships using
`%LOCALAPPDATA%\tsubasa`; moving it into the same vendor folder is a published-tool
migration and is **not** hato's to do.

⚠ **Nothing is migrated automatically.** If an older `%LOCALAPPDATA%\hato` folder exists,
`hato doctor` says so in one line and ⛔ moves nothing, deletes nothing.

> ✅ **BUILT 1c, 2026-09-17 — one path corrected, and only one.** The non-Windows default is
> now **`~/.local/share/hato`**, not `~/.cache/hato`: the root holds `subs\`, the kept
> originals hato must never delete, and `~/.cache` is the one directory a user or a cleanup
> tool may wipe. Windows never moved. The migration line above is what that produces off
> Windows: `hato doctor` names an orphaned `~/.cache/hato` in one line and touches nothing —
> and stays silent on Windows and whenever `HATO_CACHE` has relocated the root.
>
> ⚠ **DEFECT, recorded not guessed: the config file is the one thing NOT in the root off
> Windows.** The layout box above puts `config.toml` inside the root, but `paths.py` has
> always returned `~/.config/hato/config.toml` there (XDG's own answer), and 1c was ruled to
> change exactly one path. **Windows is unaffected** — both readings give
> `%LOCALAPPDATA%\hato\config.toml`. Sonic rules which one is right before hato runs anywhere
> but Windows.
>
> ⚠ **DEFECT, outside 1c's territory: `run_tests.py`'s `real_data_root()` still names
> `~/.cache/hato`.** It is the guard that proves a test run left the real store alone, so off
> Windows it would now watch a folder hato no longer uses. One line, the orchestrator's file.

TOML at `<root>\config.toml`. `HATO_CONFIG` overrides. **Read identically by the CLI, the `.cmd` and the scheduled run**
— there is exactly one config, not three.

```toml
folders    = ["D:/Anime", "E:/Downloads/Anime"]
lang       = "ja"
out        = ""            # empty = beside the video
subs_dir   = ""            # empty = %LOCALAPPDATA%\hato\subs — kept originals, never deleted
candidates = 3
archives   = false         # ⭐ OFF by default, ruled 2026-09-17 — unpacking a stranger's
                           #   archive is the one place hato acts on structure it did not
                           #   author. Turn it on here, or per-run with --archives
allow_ai   = false
recurse    = true

[log]
path = ""                  # empty = %LOCALAPPDATA%\hato\hato.log
keep = 10                  # rotate after N runs
```

⚠ **The API key is NOT in this file.** It is read at runtime from
`InfiniteVoid/keystore/hato-jimaku.txt`, or `$HATO_JIMAKU_KEY`. See `08-research.md`
§*Credentials*.

---

## ⭐ `hato-run.cmd` — the double-clickable launcher

~~**Ruled: no GUI at launch.**~~ ✅ **SUPERSEDED 2026-09-18 — the window shipped**
(RUNBOOK 7c–7e), and so did a tray watcher and a Windows standalone build. ⚠ This
launcher is still exactly what it says for anyone running from a clone; it is no longer
the *only* way in. Struck and dated rather than deleted.

This covers both cases the GUI would have.

| How it is used | Behaviour |
| --- | --- |
| **Double-click** | Runs every folder in `config.toml`, prints, **stays open** |
| ⭐ **Drag a folder onto it** | Windows passes the path as `%1` — runs that folder instead. This is the folder picker, at zero cost |
| **Task Scheduler points at it** | Same thing, with `--quiet`, appending to the log |

⚠ **Three things a scheduled run makes non-optional**, because nobody is watching:

1. **It writes a log**, or a 3am failure is invisible forever
2. ⛔ **It never blocks on a prompt.** No "overwrite? y/n", ever. Not one
3. **Failures survive to the next time someone looks** — the problems-first grammar
   already does this, and the log preserves it

A GUI entry point lands later as a two-line reuse of tsubasa's window, which is a dumb
terminal that runs a command and streams its output. **Not at launch.**

> ✅ **BUILT 5c, 2026-09-17 — `hato-run.cmd` at the project root.** All four requirements
> hold and each has a check in `tests/test_endtoend.py` that goes red when it is removed.
>
> | Requirement | How, and where it is proved |
> | --- | --- |
> | Never depends on the working directory | Every path from `%~dp0`, `%LOCALAPPDATA%` or `%HATO_CACHE%`. Proved by running it from three unrelated directories and comparing the output |
> | Pauses interactively, never when scheduled | `--quiet` ⇒ never · stdout not a console ⇒ never · `HATO_NO_PAUSE` ⇒ never. ⭐ The console test is **asked of Python** (`sys.stdout.isatty()`), which inherits exactly the script's stdout — batch has no way to ask |
> | Strips colour off a console | The launcher passes `--no-color` when stdout is not a console, **and** hato's own `isatty` says the same. Two agreeing mechanisms, so the launcher's half is pinned in its SOURCE — no behavioural check can tell them apart |
> | Exits 0 when it ran | A refusal exits 0, proved end to end through a real `cmd.exe` |
>
> ⭐ **`HATO_RUN_PAUSE=1|0` forces the pause decision** — the escape hatch for an environment
> where the detection is wrong, and the only way a headless suite can reach the pause branch.
> ⭐ **`HATO_PYTHON`** names the interpreter (else `py -3`, else `python`).
> ⭐ **`HATO_RUN_DEBUG`** prints what the script decided, to stderr — the first thing to set
> when a scheduled run misbehaves.
>
> 🚨 **THE LOG IS WRITTEN BY hato, NOT BY THE `.cmd`** — one config, not three: a batch file
> cannot read `log.path` out of TOML and cannot rotate by runs. Every run appends its full
> plain render under a `=== hato <when> ===` banner and trims the file to `log.keep` runs,
> temp-plus-rename. The launcher appends **one line** of its own, and only when hato exited
> non-zero or never started — the failures hato never got to record.
>
> 🚨 **A MEASURED BATCH TRAP, found by a check going red:** `echo ... exited %CODE%>>"%LOG%"`
> parses the trailing `1` of `exited 1` as the **stdout stream number** and swallows it — the
> log read *"hato exited "* on the one line that exists to carry the code. The redirect goes
> **first**: `>>"%LOG%" echo ...`.
>
> ⚠ **AMBIGUOUS AND DECIDED — a second run that meets the lock EXITS 0.** *"The second
> process exits cleanly with a message"* and *"non-zero = it could not run at all"* disagree
> on this one case. Built as **0**, because the overlap this spec itself names — *a scheduled
> run overlaps a manual one* — is a normal consequence of scheduling, and a nightly task that
> goes red whenever somebody runs hato by hand is a false alarm that trains its owner to
> ignore real ones. The message says plainly that nothing was scanned. **Sonic rules if the
> other reading was meant.**
>
> ⚠ **BARE `hato` IS THE RUN, NOT THE USAGE SCREEN** (`hato/cli.py`). The double-click case
> above and `10-deployment.md`'s `hato --quiet` both pass no folder, so "no arguments" has to
> mean *do the job over `config.toml`'s folders*. With nothing configured either, it prints
> the usage screen **and** the sentence naming the fix, and exits 2. `--help` is unchanged.
>
> ⛔ **NOT EXERCISED BY THE SUITE, and it is the step's own Prove line:** one real **Task
> Scheduler** execution. Its environment resolves `%LOCALAPPDATA%` and the keystore
> differently from any shell, and `10-deployment.md` calls it the single most likely thing to
> be found broken in production. Also unexercised: a real console, where the pause is reached
> by detection rather than by `HATO_RUN_PAUSE`.

---

## ⭐ The window — requirements RULED 2026-09-17, built AFTER launch

⛔ **Still not at launch**, and it stays a dumb shell over the CLI: it spawns
`python -m hato --json` and paints the NDJSON, exactly as tsubasa's `gui/run.py` does.
⭐ **The precondition is met** — tsubasa's window shipped 2026-09-10 and generates its
settings panel from a `SCHEMA` (`01-scope.md` §*Evolution*).

> Sonic, 2026-09-17: ***"Needs to be super simple UI."*** Everything in this table is a
> requirement.
>
> ✅ **THE LAYOUT IS NOW RULED — 2026-09-18, on pictures, over three rounds.**
> *"It's much better"* → *"It's perfect."* ⛔ **Implement it; do not redesign it.**
> ▶ **The ruled design lives in `gui-mock/` — open `mock2.html` and click it.**
> `shots-final/` carries every state; `theme.css` and `probe-refused.css` carry the measured
> palette; `MEMORY.md` carries the watcher measurement. What was settled:
>
> | Ruled | Detail |
> | --- | --- |
> | **Tabs, in this priority order** | **1 Subtitles** (everything found and added) · **2 Needs you** (with a count) · **3 Settings**. Sonic: *"the view should be in priority"* |
> | ⭐ **A row is THREE things** | episode · % match · the subtitle it was paired with. *"only show the %, the ones that were paired."* Everything else is behind a click, or an ⓘ on hover |
> | 🚨 **The word "refused" never appears** | *"when it says 'refused' it's quite alarming."* It is the engine's verdict, not something to say to a person. Rows read *needs a pick* |
> | ⭐ **Failures live in their own tab, and therefore go QUIET** | Separating them removed the need for a loud chip: being in that tab is the signal. The deep garnet survives only as a 2px left edge and the count badge |
> | ⭐ **Clicking a candidate IS "use this pair"** | *"if they click on one, it should count as 'use this pair'. If they want to reselct, they can always reselect it."* No confirm button. One open at a time, animated collapse, and the next unresolved row opens as it closes |
> | **The blacklist is built for length** | Dates, a count, a filter, capped scroll — and ⭐ **hato detects the entries whose video has rotated off disk and offers to remove them**, because *"it's likely they will not clean it"* |
> | **Skipped folders** | An exclusion list beside the watched folders — *"someone might say 'desktop' and then not want a certain folder checked on desktop"* |
> | **Schedule** | A configurable time, plus a **Run now** control in the title bar |
> | **Credit line** | `Created by SonicSandbox | GitHub`, inline on the footer, left of the API-call count — as tsubasa carries it |
>
> 🚨 **A SETTING THAT DID NOTHING WAS OFFERED AND CAUGHT.** Round 2 proposed *"watch and
> pick new videos up on the next run"* and marked it **Recommended**. Sonic: *"what is the
> difference between it queueing if it's open and it just running next time? Isn't that
> basically the same exact thing?"* **It was** — a scheduled run already scans and finds new
> files; the filesystem is the queue. ⛔ **Before offering an option, state what it changes
> about the outcome.** It was replaced by the **Run now** control he proposed instead.

> 🚨 **TWO PART 1 DEFECTS, RECORDED AT THE WINDOW'S BUILD (2026-09-18).** Both are the same
> mistake: **a capability was checked for EXISTENCE and marked verified, when the question
> the interface asks of it is different.**
>
> | The requirement | What was marked ✅ | What was actually missing |
> | --- | --- | --- |
> | Settings edits folders, skips, schedule, key | `hato config --show` | ⛔ **`config` is READ-ONLY.** No `save`, `write` or `dump` anywhere in `hato/config.py`. Two-thirds of Tab 3 had no mechanism. Caught by an adversarial pass, recorded in `HANDOFF.md` §4d |
| ⭐ *"show the process as it does it automatically"* | `hato <folders> --json` — per-video objects, then `{"type":"run"}` | 🚨 **The objects are all emitted AFTER the run finishes.** `report.ndjson()` is built from a finished `RunReport`, so a shell over it can paint a spinner and nothing else. Found the same way, one row further down the same table |
>
> ▶ Built as **RUNBOOK 7a** (a config writer through the one existing schema, plus
> `hato key --set-from -` so a GUI key field never writes the secret to disk) and **7b**
> (`--progress`, additive and opt-in; without the flag the output is byte-identical).

| It must | In Sonic's words, and what it means |
| --- | --- |
| ⭐ **Show the automatic run as it happens** | *"normally it would do it automatically and just show the process as it does it automatically."* The automatic run is the default and the common case; everything below is available around it. ▶ **RUNBOOK 7b** — this had no mechanism until 2026-09-18 |
| ⭐ **Offer MANUAL PAIRING as an option** | *"show the files downloaded from jimaku (that are in transit) with the option to pair each file with its video manually … like a picker of some sorts, super simple."* Two lists — the videos in the current selection, and **only the viable candidates already pulled for them**. ⛔ Never the whole jimaku file list |
| **Hold the jimaku API key** | *"so when we release it others can easily add it."* 🚨 ⛔ **Never into `config.toml`** — see the open question below |
| **Take several folders** | *"the folder(s) they want to do (which can be multiple)"* |
| **A recursive toggle** | *"so it would find all files"* |
| ⭐ **A blacklist of videos** | *"a video in there that doesn't need / won't have subs, that you could easily blacklist it."* The store is `02-data-model.md` §Question 3; the window only adds and removes rows |
| ⭐ **The repeatedly-failed list** | *"a video without subs yet (it was just released) so you would try again a day later each time (not soon unless prompted)."* The soft negative is now **1 day**, and *"unless prompted"* is a Retry on one row |
| **Say what already has subtitles** | *"so that's visible but not the focus"* |
| **The auto-run switch** | Registers or removes the Windows scheduled task, and says when it next runs. ✅ **BUILT 2026-09-23 (RUNBOOK 8y — it had shipped as a switch that registered nothing, D2).** `hato/schedule.py`: Task Scheduler is the only state, read on every open; the task starts `hato-watch --scheduled` (no console window); *"next run in 22h"* is derived from the task and the clock; a task switched off or changed in Task Scheduler says so beside the switch; no switch where nothing can schedule |

⭐ **Manual pairing is a solved mechanism, not a new one.** hato already hands tsubasa an
explicit pair (`sync([(video, subtitle)], write=True)`), so a manual pick only replaces
hato's own ranking — **the timing verdict still rules and still refuses a wrong pair.**
That is Rule 1 holding even when the person is the one choosing.

⭐ **The failed list and the picker belong together.** A REFUSED row is precisely where a
person can help: *we fetched something and the timing says it is probably the wrong thing.*
A NOT_FOUND row is not — there is nothing to pair yet, only a retry date.

🚨 ~~**OPEN** — where does a stranger's key go?~~ ✅ **ANSWERED AND BUILT 1c, 2026-09-17:
`<root>\key.txt`.** `config.toml` is forbidden (`LEDGER.md` §data) and the keystore path is
Sonic's own machine, so the key is a plain file in hato's own per-user folder — owner-only
where the OS has permissions, written temp-plus-rename, and **refused outright into a git
working tree** (the vault auto-commits; history has no undo).

| | |
| --- | --- |
| **Precedence** | `$HATO_JIMAKU_KEY` → `$HATO_KEYFILE` → `<root>\key.txt` → the dev keystore. ⛔ **`HATO_KEYFILE`, when set, never falls through**, even to a file that is not there — that is what keeps a test run out of the real keystore |
| **The stranger's path** | `hato key --set-from <file>` copies the key in; `hato key --show` prints the SOURCE and the **last four characters**, never more |
| **The window** | Writes the same file through the same code (`credentials.save_key_from`), so the two cannot disagree |

⭐ **`keyring` was not needed.** The OS credential store buys secrecy from other *users* on
the same machine; `%LOCALAPPDATA%` already is per-user, and a file is what a person can see,
edit and delete without a tool. ⛔ Never the repo, never the config file, never a log.

### ⭐ The look — BRANDING, given 2026-09-17

**The assets:** a `hato-logo-pack` folder outside the repository — 21 PNGs, **no vector source**.
A faceted origami courier in flight carrying a message, coral through garnet. Three cuts:
`original` (the colour mark), `grayscale` (charcoal silhouette, for light grounds),
`wordmark` (the mark above lowercase *hato* in charcoal). Icons 16–1024, wordmark 256–1024.
⛔ **Only the sizes the window actually uses get copied into the package**; the 1024 masters
stay out of the wheel, and ⛔ nothing here is re-drawn or re-coloured — the mark is approved.

**The palette, sampled from `hato-original-512.png`** (opaque pixels only, 8-bit buckets, so
these are the mark's real values rather than an impression of them):

| Role in the mark | Hex | Share |
| --- | --- | --- |
| Paper / cream highlight | `#F8F0E0` | 4.5% |
| Blush | `#F8D0C0` | 6.5% |
| ⭐ **Coral — the accent** | `#F8A890` | 7.9% |
| Coral-red | `#F86868` · `#F05058` | 7.0% · 4.0% |
| Garnet | `#E03048` | 5.3% |
| Deep garnet | `#C02040` | 5.0% |
| Charcoal (the wordmark's type) | `#202030` | 13.2% of the wordmark |

**Sonic's direction, verbatim — this is the brief, not a summary of it:**

> *"NOT legacy or old theme. I want modern looking, that has the family connection to
> tsubasa but is its own distinct. It has coral accent like in the logo. When hovering over
> buttons, there is action, everything looks modern and premium and interactable yet also
> simple and magic. … Something very simple yet extremely magical and potent, and colors
> utilize modern UX with high integrity."*

**What "family, but distinct" means concretely** — measured from tsubasa's own window:

| Shared with tsubasa | hato's own |
| --- | --- |
| The dark ground and the table grammar: `BG #15171b` · `PANEL #1c1f25` · `EDGE #2b3038` · `INK #e7e9ec` · `DIM #8b929c`; problems pinned at the top; drop a folder to run | ⭐ **The accent.** tsubasa's is blue `#6aa8d8`; hato's is the logo's coral |
| ⛔ The architecture rule: **the window decides nothing** — it spawns `hato --json` and paints what comes back | The mark, the wordmark, and a lighter, warmer surface treatment |
| The DPI layer — this machine is **239.6 dpi, ratio 2.496**, and Tk scales fonts while leaving `padx`, `rowheight` and `geometry()` in raw pixels | hato's own outcome hues, forced by the collision below |

🚨 **The collision to solve before any palette is drawn:** tsubasa spends a **coral-red**
(`#e0736c`) on **REFUSED**. If hato's accent is coral, the accent and a failure read as the
same colour — the opposite of *high integrity*. One of them moves: ⭐ the accent keeps the
bright coral `#F8A890`, and **refused leaves the coral family entirely.**

⭐ **Measure the palette; do not eyeball it.** [[color-kit]] exists for exactly this — WCAG
contrast, per-tier mixes, contrast floors, ramp shifts, contact sheets. *"Modern UX with
high integrity"* is a contrast floor and a consistent ramp, not a mood.

**Hover and motion:** every interactive element answers the pointer — ⛔ nothing that looks
clickable may sit inert. *Premium* here reads as **restraint plus response**: one accent, one
type hierarchy, generous space, and motion only where it tells you something (a row settling
as it resolves, a control lifting under the pointer). ⛔ No decoration that does not report.

### Sonic's rulings on the window, 2026-09-17

| Ruled | Consequence |
| --- | --- |
| ⭐ **A web view is fine — but it must be the PROGRAM'S OWN WINDOW.** *"not in chrome or something. Otherwise i'd rather do tkinter"* | An embedded view with no browser chrome, no tab strip, no address bar. ⛔ A localhost URL opened in the user's browser is **refused by this ruling**, not merely discouraged |
| **Dark, with coral as the key accent** | The ground stays in tsubasa's family; the accent is the mark's coral |
| **The collision is the builder's to solve** — *"It could be a deeper red for the failure"* | ⭐ Taken: the accent keeps the bright coral, **failure goes DEEP** — garnet/crimson, far from the accent in lightness and chroma, and never adjacent to it in one row. Proven with [[color-kit]], not by eye |
| 🚨 **It ships from GitHub and must stay portable, like tsubasa** | The toolkit is judged on what a **stranger's** machine needs, not on what this one has |

**Measured on this machine, 2026-09-17** — the facts the choice turns on:

| Fact | Measured |
| --- | --- |
| WebView2 Evergreen runtime | ✅ **installed, 153.0.4234.32** — notable, because this is Windows 10 **LTSC** and Edge is not present at all |
| `PyQt6` | ✅ already installed here (GPL-3.0 — **compatible with hato's own licence**) |
| `tkinter` | ✅ 8.6, always there |
| `customtkinter` · `pywebview` · `pythonnet`/`clr` · `PySide6` · `flet` | ⛔ none installed |

🚨 **THE TOOLKIT IS STILL OPEN — the LAYOUT is ruled, the toolkit is not.** ⚠ Do not read
the layout approval as a toolkit ruling; they were separate questions and only one was put
to Sonic. ⭐ **The lean is Qt** (`PyQt6`, GPL-3.0, already installed and matching hato's own
licence): it is the only one of the three that does hover, easing, shadow and rounded
corners as first-class, it needs nothing on a stranger's machine, and it is the friendliest
to freeze into the exe. ⚠ **Measured 2026-09-18:** a resident Qt tray is **30.6 MB** against
a `ctypes` watcher's **13.4 MB**, which is why the watcher is a separate process whatever
the window is built in (`gui-mock/MEMORY.md`).

*Magical and premium with hover action* is precisely where plain tkinter stops: no easing,
no shadow, no blur, and every rounded corner costs a canvas.

| | How it works | What a stranger's machine needs | What it can never do |
| --- | --- | --- | --- |
| ⭐ **Qt** (`PySide6`, LGPL — or `PyQt6`, GPL, which matches hato) | Its own native window; hover, easing, shadows and rounded corners are first-class; `QSS` is CSS-shaped | **Nothing but the wheel** — self-contained, and the friendliest of the three to freeze | Be small: ~70 MB installed |
| **An embedded web view** (`pywebview` over WebView2) | Same `hato --json` subprocess; the surface is HTML/CSS, so the visual ceiling is highest per line | ⚠ **The WebView2 runtime** — on Win11 always, on Win10 usually, on LTSC **not guaranteed** (it is here) — plus `pythonnet` | Promise it just works on a machine without that runtime |
| **`customtkinter`** | tkinter underneath, so tsubasa's `scale.py` and generated settings panel carry over | ~1 MB, pure Python | Animate, blur or cast a shadow — flat-modern is its ceiling |

⚠ Whichever wins, the window stays a shell: it spawns the CLI and paints NDJSON, and ⛔ it
decides nothing. ⭐ **The mock defines the design and the toolkit merely implements it** — so
two or three rendered layouts go to Sonic first, in whatever medium renders fastest, and the
toolkit is chosen to match the one he picks. That is how tsubasa's window was settled, and a
picture turned a stalled decision into a five-word answer.

---

## The library API

surasura and any future caller consume this. The CLI is a thin wrapper over it.

```python
from hato import scan, identify, fetch, Result

# Discovery — filesystem + cache only. ZERO network. Never writes.
plan = scan("/media/anime/s2")
plan = scan(["/media/a", "/media/b"], lang="ja")

# Identification — cached; costs API calls only for unresolved shows. Still writes nothing.
plan = identify(plan)

# Acquisition + alignment — the only call that touches the filesystem or downloads.
results: list[Result] = fetch(plan, write=True)
```

### `Result` carries

`video` · `outcome` (CONFIDENT / REFUSED / ERROR / NOT_FOUND) · `reason` ·
`jimaku_entry` · `jimaku_filename` · `candidates_tried` · `tsubasa` (tsubasa's `Result`,
verbatim — offset, match rate, verdict word, segments) · `output_path` · `kept_path` ·
`api_calls` · `bytes_downloaded` · `retry_after`

⚠ *Renamed 2026-09-17: the field was `align`, which is the name of a different tsubasa
function (`03-permissions.md`). `kept_path` is the original in `subs_dir`.*

**`reason` is never empty on a non-confident outcome.**

⭐ **`tsubasa` is tsubasa's `Result` passed through unchanged, not re-wrapped.** A caller
that already understands tsubasa understands this, and the two can never disagree about
what a run did.

### Three constraints inherited from tsubasa

1. ⛔ **Never assumes it owns a directory.** Takes paths *or* iterables of paths
2. ⛔ **Ignores non-video files silently.** Junk is expected input, not an error
3. ⛔ **Returns structured results. Prints nothing. Writes nothing unless told**
