---
type: runbook
title: hato — Build Order
desc: Dependency-ordered. Every step carries what it builds, the command that proves it landed, and the surfaces whose doctrine it must load.
date: 2026-09-07
---

# hato — Build Order

> Walk top to bottom. **Advance as far as possible**; stop only for a credential a human
> must mint, a decision the spec genuinely lacks, or a destructive action.
>
> ⛔ **A step with no PROOF command is not a step. It is a wish.**
>
> **Per step:** load the doctrine its `surfaces:` line names, build it, write the test
> WITH it, register the test, break the fix and watch it fail, run the suites, LOOK at
> the output.

---

## ⭐ How this build runs — an ORCHESTRATOR agent (RULED 2026-09-17)

> Sonic: *"make sure … the /dev-build hato uses an orchestrator agent to do it."*
> **Binding for every `/dev-build hato`, including a resume.**

**One orchestrator agent owns the build. Builder agents build the steps.** The orchestrator
is the cold agent `dev-build` describes — it starts from this pack and nothing else.

| The ORCHESTRATOR owns | A BUILDER owns |
| --- | --- |
| The order, the commitment list, and every stop | Only the files its brief names |
| `run_tests.py` and the suite list — ⛔ **registers each suite the moment its file lands**, or the orphan check breaks the runner for every other agent | Its own suite plus hermetic neighbours. ⛔ **Never the full runner** |
| Wiring a new module into existing ones, **serially**, after the builder returns | ⛔ **Never edits an existing source file** |
| Running every step's **Prove** command itself, and LOOKING at the output | Breaking each fix once and watching the named check go red |
| Checksumming the source tree before and after every parallel wave | Recording a spec defect instead of building around it |
| Ticking rows here · `LEDGER.md` · `CONTEXT.md` · **`HANDOFF.md` on any stop** | — |
| The adversarial pass — dispatching, holding every fix until all return, reviewing the SEAMS itself | — |

### The waves

| Wave | Steps | Shape |
| --- | --- | --- |
| **0** | 0a → 0b | The orchestrator itself: wiring, the green baseline, `hato doctor`, and **the one deliberate live capture** |
| **1** | 1a → 1b | One builder |
| **2** | 2a → 2b → 2c **‖** 3a → 3b **‖** 3c | ⭐ **Three builders at once** — client, matcher, archives. They meet only at the list of file dicts (§*Layers 2 and 3 are safe to run concurrently*) |
| **3** | 4a → 4b → 4c | One builder, serial — the pipeline touches every earlier module. **4b needs T4** |
| **4** | 5a → 5b → 5c | One builder; the orchestrator runs 5c's real scheduled task itself |
| **5** | **The adversarial pass** | One adversary per surface: client · matching + ranking · pipeline + the hand-off to tsubasa · CLI + launcher. **Its own phase, not a tidy-up** |
| **6** | Release | ⛔ **IRREVERSIBLE — stops for Sonic's go** |

**Every builder brief carries:** its step sections **quoted, not pointed at** · the doctrine
its `surfaces:` line names · its file territory · its own probe/mutant number range · the
`LEDGER-HOT.md` traps that apply · and an explicit override: **build your step only.**
`dev-build` says *walk the runbook top to bottom*, and three builders obeying it each build
the whole project.

⛔ **Nobody edits `Workshop/tsubasa/`.** Another session builds there — including T4, the
public track reader hato needs. If `import tsubasa` breaks mid-build, run
`git log -- Workshop/tsubasa` before debugging anything.

⛔ **A run that writes beside videos uses COPIES.** Real media lives outside the vault
(`tsubasa/CONTEXT.md` §*Corpus*); copy it into a temp dir first. **The first run against
Sonic's own library is Sonic's to make** — the final report says exactly what to run and
what to look at.

**The four hard stops, and only these:** `CREDENTIAL` — jimaku answers 401 · `IRREVERSIBLE`
— publishing, or writing into Sonic's real library · `ARCHITECTURAL` — a shape this pack
does not decide · `NEEDS-EYES` — output that departs from `05-interface.md`'s ruled mocks.
**Everything else is advanced through.**

---

## The dependency graph

```
LAYER 0 — wiring and the probe
  ├── 0a  Skeleton, config resolution, keystore read
  └── 0b  ⭐ hato doctor + --capture      ← THE PROBE. Ships BEFORE the client.
                                            It is what generates every fixture.

LAYER T — THE SHARED LAYER. Built in the TSUBASA package, imported by hato.
  ├── T1  Filename parse                          ✅ DONE in tsubasa
  ├── T2  Video discovery                         ✅ DONE in tsubasa
  ├── T3  Existing-subtitle reader + naming rule  ✅ DONE in tsubasa
  └── T4  ⭐ Public track reader                   🔨 tsubasa's builder, 2026-09-17
                                                     hato never builds it

LAYER 1 — hato's own foundations. NO NETWORK.
  ├── 1a  Working cache (content-hash keyed)
  └── 1b  State DB: canonicity, negative cache, refusal recording

LAYER 2 — the jimaku client. Built against 0b's captured fixtures.
  ├── 2a  Client: headers, rate limits, retries, the four traps
  ├── 2b  Search + resolution cache
  └── 2c  File listing (no episode= param, ever)

LAYER 3 — pure logic. NO NETWORK. Genuinely concurrent with Layer 2.
  ├── 3a  ⭐ Episode range alignment, PER RELEASE GROUP
  ├── 3b  ⭐ Candidate ranking
  └── 3c  Archive extraction + zip-slip guard

LAYER 4 — the pipeline
  ├── 4a  sync() port, backed by tsubasa
  ├── 4b  The fetch loop + candidate escalation      (needs T4)
  └── 4c  Keep the original, hand it to tsubasa, --out mirroring

LAYER 5 — surface
  ├── 5a  CLI output, both modes
  ├── 5b  Config file
  └── 5c  hato-run.cmd + scheduled run

LAYER 7 — THE WINDOW. Added 2026-09-18; the design is RULED (gui-mock/mock2.html).
  ├── 7a  ⭐ The config WRITER + a non-file key route   ← NOTHING sat behind Settings
  ├── 7b  ⭐ The progress stream                        ← NOTHING sat behind "as it happens"
  ├── 7c  The window: shell, theme, Subtitles
  ├── 7d  The window: Needs you — the picker
  ├── 7e  The window: Settings
  ├── 7f  The tray watcher — a SEPARATE process, ctypes only
  └── 7g  The exe

LAYER 8 — NEEDS YOU PERSISTS, AND EVERY WAIT SAYS SO. Added 2026-09-22 (HANDOFF §4)
  ├── 8a  ✅ A dry run writes nothing
  ├── 8b  ✅ The record keeps what a pick needs     (subtitle_hash, match_rate)
  ├── 8c  ✅ The open-problems view                 ← hato problems
  ├── 8d  ✅ The gate keeps the candidates          (pipeline.py:965)
  ├── 8e  ✅ Needs you persists, and says when
  ├── 8f  ✅ Probably not out yet  + Wait for it    (amended: D11, the slide)
  ├── 8g  ✅ Clear hato's memory                    (amended: dry unless --yes)
  ├── 8h  ✅ The retry actually happens             (the tray wakes at the due time)
  ├── 8j  ✅ Try harder · 8k ✅ network drive → D8, a defect in the RELEASED bytes
  ├── S01 · S02 ✅ the tray's two deferred silent losses (ADVERSARY-2026-09-18)
  └── 8z  ✅ THE ADVERSARIAL PASS — run and CLOSED: ADVERSARY-2026-09-22.md
           79 reproduced + 11 suspected + 32 wrong-reason checks → every row
           fixed (naming its check AND its mutant) / dropped / deferred.
           ⛔ Still UNRELEASED — 1.0.2 is Sonic's call

LAYER 6 — release
```

### 🚨 Layers 2 and 3 are safe to run concurrently

They share no code and meet at exactly one boundary: **the list of file dicts**. Layer 3
builds against `tests/fixtures/api/entries_11446_files.json` — a real capture — and never
needs the client. Layer 2 builds against the same file and never needs the matcher.

⛔ **Two agents on Layers 2 and 3 must read [[Development Doctrine/workflows/dev-parallel]]
first.**

### ✅ Layer T is DONE — in tsubasa. hato only imports it

T1–T3 shipped as tsubasa's Track A and are public in `tsubasa-sync` 0.1.1+ — the names are in
`10-deployment.md`. **T4, the public track reader, is being built by tsubasa's own session
(2026-09-17).** ⛔ **Do not write a second parser, walker or track reader inside hato "for
now,"** and ⛔ do not edit `Workshop/tsubasa/` — that is the one decision this spec exists to
prevent (`01-scope.md` §*The relationship to tsubasa*). If T4 has not landed when 4b needs
it, 4b is **BLOCKED ON TSUBASA**: build everything else and say so.

---

## Step 0a — Skeleton and wiring — ✅ DONE 2026-09-17

> ✅ **Proved by running every command below** (orchestrator, 2026-09-17): `0.1.0.dev0` ·
> `config --show` from three working directories identical (a check) · `config --check-key`
> found, last 4 only · the runner green · `--verify-registration` OK. Suites `wiring`, `config`,
> `runner`; mutants `M0a-01…21`, all killed. ⚠ **What the break-checks found before anything
> shipped:** two runner checks that passed on state they did not create — the network
> kill-switch check read the PARENT process's `HATO_NO_NETWORK`, and the missing-harness check
> passed on pytest's own "file not found". Both fixed, both now mutants.
>
> ⭐ **Built beyond the rows, because the spec's rules needed a mechanism:** `hato.config.json`
> (the suite list, as tsubasa's convention) · `HATO_CACHE` relocates the WHOLE per-user root —
> cache, DB, default `subs_dir`, default log — so a test cannot reach the real one · every
> override must be absolute · the network is off in every default suite twice over
> (`HATO_NO_NETWORK=1` for subprocesses, a socket guard in-process) · the runner verifies its
> own teardown and fails with exit 5 if a test touched the real store · the Layer-1 mutation
> gate is `node _mutants.mjs` (app-kit's engine, a Python witness shim), excused from the runner
> by construction.

**surfaces:** `harness` `data`

| What | Command | Proves |
| --- | --- | --- |
| Package imports | `python -c "import hato; print(hato.__version__)"` | Layout is right |
| Config resolves | `python -m hato config --show` | Found from any cwd, honours `HATO_CONFIG` |
| **Key resolves** | `python -m hato config --check-key` | Reads the keystore **or** `HATO_JIMAKU_KEY`. ⛔ **Prints only the last 4 characters** |
| Runner runs | `python run_tests.py` | Suite list + harness dir are right |
| **Registration self-check** | `python run_tests.py --verify-registration` | Enumerates test files on disk; **fails on any not in the suite list** |

**Then get a GREEN baseline.** If it is not green before you start, you cannot tell what
you broke.

⚠ **Set `PYTHONUTF8=1` in the runner and document it.** Windows Python defaults to cp1252
and **will** raise `UnicodeDecodeError` on Japanese content — this was hit during
specification, on the very first parse of a real jimaku response.

⚠ **The machine, checked 2026-09-17:** Python **3.10.0** — `tomllib` is 3.11+, so read TOML
through `tomli` below it · `anitopy` 2.1.1, `guessit` 4.4.0 and `requests` 2.28 installed;
`py7zr`, `rarfile` and `httpx` not · no `unrar` or `7z` on PATH · ffmpeg and ffprobe at
`Workshop/media-kit/bin/` (⛔ never hardcoded into shipping code) · mpv at
`C:\Program Files\mpv\mpv.exe`.

⭐ **tsubasa is imported from the vault checkout, `Workshop/tsubasa`** — one source tree.
Add a wiring check that `tsubasa.__file__` resolves there, so a pip-installed `tsubasa-sync`
can never silently shadow it during the build.

---

## Step 0b — ⭐ `hato doctor`, the probe — ✅ DONE 2026-09-17

> ✅ **Proved live, once, deliberately** (orchestrator, 2026-09-17): `hato doctor --capture` —
> **9 metered calls, 2 unmetered downloads**, every line resolved or MISSING, exit 0. Captured
> into a temp dir OUTSIDE the vault, scanned for the key in five encodings (0 hits), then
> installed byte-identical into `tests/fixtures/api/` (19 files). Suite `doctor` (27 checks,
> including the recorded capture); mutants `M0b-01…12`, all killed. ⭐ **The capture corrected the
> spec in five places** — `08-research.md` §*MEASURED 2026-09-17*: the 120 files are 5 groups +
> **20 unbracketed files** (10 Amazon + 10 Netflix — corrected by the 3a builder); an invalid id through the API is a **404**, not a 200; file
> URLs are **absolute**; `reset-after` is **absent** outside a 429; the 401-quota claim is
> **inconclusive** from live data. ⚠ **Its own check caught a near-leak before the live run:**
> the invalid-id probe recorded the response's "first bytes", which would have committed
> subtitle text had that route ever served one — now kept only when it is an HTML page.
> T4 line: `tsubasa.embedded_subs`, read through on a generated `.mkv` (2 text tracks) and
> a raw one (0 tracks).

**surfaces:** `harness` `logic`
**depends on:** 0a

**This ships before the client it de-risks.** Everything about jimaku leaves the process,
so the suite can only ever prove hato *asked* correctly. Answering the other half first
costs almost nothing; answering it last can invalidate the client's shape.

| | |
| --- | --- |
| **Build** | `hato doctor` — a readout, not a library. Raw requests are fine here |
| **Prove** | `hato doctor` prints: key source · search HTTP status · **the three rate-limit headers verbatim** · file count and key names from a `files` call · one unmetered download with byte count and sniffed encoding · tsubasa import + version, and `tsubasa.self_check()` ·  `unrar` present? · cache and config paths, writable? |
| **Test** | `tests/test_doctor.py` — asserts the readout **shape**, against recorded fixtures. Never the live values |
| **Expected** | Every line resolved or explicitly `MISSING`. ⛔ No line may be blank |

⭐ **`--capture` is the load-bearing half.** It writes each response into
`tests/fixtures/api/` with today's date and the source URL. **This is how every fixture in
Layer 2 and Layer 3 gets created, and re-created when the API changes.** Without it the
fixtures are hand-written, and a hand-written fixture encodes what you believed the API
returns — which would have hidden two of this project's traps.

```bash
hato doctor --capture          # populates tests/fixtures/api/
```

⚠ **Capture at minimum:** `search?query=frieren` · `search` with an empty query · a
`search` needing the `anime=false` retry · `entries/11446/files` (**the crown jewel** —
120 files, 5 groups, absolute+seasonal mix, the `[CHS, JPN]`/`[JPN]` pair) · a movie-flagged
entry · a 429 header set · a 401 header set.

🚨 **This is the only step that hits the live API by default, and it is run deliberately.**
Budget: 25 requests / 60 s. Six captures is well inside it. ⭐ **Ruled 2026-09-17: the
orchestrator runs the first capture itself** — Sonic said build now. After that a human
re-runs it when the API changes. ⛔ Never the suite.

⚠ **Two additions (2026-09-17):** a readout line saying whether tsubasa's public track reader
(T4) is present and under what name · and **derive every count from the capture** —
`08-research.md`'s probe numbers do not sum.

---

## Step T1 — Filename parsing *(in the tsubasa package)* — ✅ DONE, do not build

✅ **Built in tsubasa and public:** `video.title` · `video.season` · `video.episode` ·
`video.episode_candidates`. The table below is kept as the record of what it had to guard.

> 🚨 **SCOPE OF THAT ✅, MEASURED BY hato's BUILD 2026-09-17** (orchestrator probe: zero-byte
> stubs, `tsubasa.scan()`, the 0.1.3 checkout). The public reading is **only** those four
> fields plus `lang`/`lang_tag`, and **only for files that exist** (`scan()` requires its roots
> to). This step's Prove promised *"title, episode, season, **type**"* — type is not public, and
> neither is anything else 3a and 3b need:
>
> | Name | Public reading | What hato needs and does not get |
> | --- | --- | --- |
> | `[Group] Show - 01-02 [JPN].ass` | title `Show 02`, episode **1** | multi-episode → REFUSE |
> | `[Group] Show - SP1 [JPN].ass` · `Show OVA - 01.ass` | title `Show SP1` / `Show OVA`, episode **1** | a special → never range-aligned |
> | `[Group] Show - 06v2 [JPN].ass` | episode 6 | the version, for ranking |
> | `… [CHS, JPN].ass` · `… [CHS].ass` | `lang` **und** | the language class, for ranking |
> | `… [whisperai].srt` | nothing | the AI filter |
> | `Kimi.no.Na.wa.2016.1080p.BluRay.mkv` | title **`Kimi no Na wa 2016`** | the year (the anitopy glue, still present) |
> | any leading `[Group]` | nothing | the release group |
> | ✅ `S01E06v2` · `13.5` · `NCOP1` (skipped, with reason) · `ja[cc]` · `S2 - 03` · `2nd Season - 03` | right | — |
>
> ⭐ **Consequence, ruled at build time (orchestrator):** hato reads title/season/episode ONLY
> through tsubasa (`hato/names.py`, stubs). The seven gaps above are derived by hato in ONE
> module of token rules — none of them a title, season or episode parse — each marked as a
> candidate for tsubasa to publish. **A decision for Sonic** (final report): ask tsubasa to
> publish them, which deletes that module.

**surfaces:** `logic`
**depends on:** 0a

| | |
| --- | --- |
| **Build** | anitopy primary, guessit fallback, plus the router: leading `[Group]`, an 8-hex CRC32 token, or ` - NN ` → anime path |
| **Prove** | `python -m tsubasa.dev parse "<filename>"` prints title, episode, season, type for any input |
| **Test** | Against `catalog.jsonl` — **the widest sample of real Japanese subtitle filenames there is, already built.** ⚠ Now at `InfiniteVoid/WorldDominationLite/tsubasa-corpus/naming/`, outside the vault |
| **Expected** | Derived from the corpus, never a pinned count |

🚨 **Guard the measured silent failures explicitly, each with its own test:** guessit typing
`S01E06v2` as a **movie**; `Season 2 - 15` expanding to 14 seasons; `Show - 125` splitting
into S01E25; `86 - Eighty Six` eating the title number; anitopy gluing the year into
`Kimi no Na wa 2016`; anitopy turning `NCOP1` into episode 1. **Normalize `episode` to a
list at the boundary — both parsers flip between str and list without warning.**

---

## Step T2 — Video discovery *(in the tsubasa package)* — ✅ DONE, do not build

✅ **Built in tsubasa and public:** `tsubasa.scan(videos=folder)` → `.videos`. ⚠ It opens
nothing inside the tree it is given.

**surfaces:** `logic`
**depends on:** 0a

| | |
| --- | --- |
| **Build** | Walk a path or an iterable of paths. Recursive by default. Video extensions only, junk ignored silently |
| **Prove** | `python -m tsubasa.dev scan <dir>` lists what it found and what it skipped |
| **Test** | A fixture tree with videos, subtitles, junk, nested dirs, and a Japanese-named file |
| **Expected** | Every video found; every non-video ignored **without an error** |

---

## Step T3 — Existing-subtitle reader and the naming rule *(in the tsubasa package)* — ✅ DONE, do not build

✅ **Built in tsubasa and public:** `scan.unpaired(lang="ja")` · `subtitle.lang` ·
`tsubasa.parse_subtitle_name()`. ⚠ **Embedded-track detection was never part of it** — that
is T4.

**surfaces:** `logic` `data`
**depends on:** T2

| | |
| --- | --- |
| **Build** | `<video>.<lang>[.flag].<ext>` — both write and read. Plus embedded-text-track detection |
| **Prove** | `python -m tsubasa.dev subs <video>` lists every sidecar with its parsed language and flags |
| **Test** | The full collision table in `08-research.md` |
| **Expected** | `.ja` `ja` · `.jpn` `ja` · `.Japanese` `ja` · `.ja.forced` `ja`+forced · `.chi` Chinese **not HI** · `.hi` **Hindi** · `.ja-JP` recognised on read, ⛔ **never written** |

🚨 **The two rules, and each reference implementation got a different one wrong:**
**parse the language BEFORE trimming flags**, and **strip flags as whole dot-delimited
tokens, never substrings**. Write a test that fails under each project's bug specifically.

---

## Step T4 — ⭐ The public track reader *(tsubasa's builder — NOT hato's)*

**surfaces:** `logic`
**status:** 🔨 **Being added by tsubasa's own session, 2026-09-17** — Sonic gave it the job

> ✅ **LANDED IN THE VAULT CHECKOUT 2026-09-17 (~01:07), observed by hato's orchestrator:**
> `tsubasa.embedded_subs(video, lang=None)` → `EmbeddedSubtitles` (`ok`, `reason`, `tracks`)
> of `EmbeddedSubtitle` (`index`, `lang`, `tag`, `codec`, `text`, `bitmap`, `forced`, `default`,
> `name`), in `tsubasa.__all__`, `__version__` 0.1.3 — tsubasa's own RUNBOOK 3f. ⭐ **It answers
> BOTH questions** (`lang=None` gives every track, text or bitmap), so the Part 1 defect above
> does not arise. ⚠ **Not released:** 0.1.3's tag waits for Sonic's go and the name is his to
> veto, so hato builds against the checkout and its `tsubasa-sync` floor waits with it.
> ⚠ `ok=False` (unreadable) is a third answer this pack's read rule never covered — see 4b.

| | |
| --- | --- |
| **hato needs** | For one video, every subtitle track: **text or bitmap**, and its language. That answers both questions 4b asks — *is there a Japanese TEXT track* (skip: already subtitled) and *is there ANY subtitle track at all* (if not, skip: tsubasa has nothing to time against) |
| **Prove** | `hato doctor` names the function and reads one real video through it |
| ⛔ **Never** | `tsubasa.container`, or any other internal. Not "for now" |

⚠ **If what lands answers only *"has a Japanese track"*,** the no-track question has no public
answer. Record it as a Part 1 defect and say so in the report — ⛔ do not reach into
internals to fill the gap.

---

## Step 1a — Working cache — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 1 builder; proved by the orchestrator** — `hato cache --stat` read on an
> empty and a populated temp store (the empty one creates nothing); suite `cache` **71 checks**
> green through the runner; mutants `M1a-01…21` all killed (builder's run). ⭐ The 128 KiB read
> is PROVEN by counting bytes through a wrapper at sizes 0–4 MiB, not asserted.
> `safe_name` details this pack left open (builder's, accepted): over-long = 255 UTF-16 units or
> UTF-8 bytes; on Windows the whole path is kept within 259; reserved device names get `_`.

**surfaces:** `data`
**depends on:** 0a

| | |
| --- | --- |
| **Build** | Content-hash keyed dir under `%LOCALAPPDATA%\hato`. `HATO_CACHE` overrides |
| **Prove** | `hato cache --stat` shows path, size, entry count |
| **Test** | Hash stability; `HATO_CACHE` honoured; a temp dir used under test |
| **Expected** | 🚨 **Head 64 KB + tail 64 KB + filesize. Never hash a whole video** |

⛔ **Never beside the media.** `subsync` wrote a 500 KB `.npy` next to the subtitles it was
reading, inside a corpus marked read-only.

---

## Step 1b — State DB — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 1 builder; proved by the orchestrator** — `hato state --stat` read on an
> empty and a populated temp store; suite `state` **64 checks** green through the runner; mutants
> `M1b-01…35` all killed (builder's run). The run lock (06 §7) lives here too: exclusive create,
> a dead run's lock taken over — pid AND process creation time, so a reused pid is not obeyed.
> ⭐ **Three Part 1 defects the builder found, ruled by the orchestrator:**
> (1) *Backfill vs "opens nothing"* — a backfill row is keyed on the video hash, a 128 KiB read,
> while a present subtitle "opens nothing" and a quiet re-run is "N stats + 1 DB read". **Ruled:
> the present-skip path never hashes just to backfill**; a backfill is written only when the
> run already holds that video's hash. A backfilled row changes no decision (no kept original →
> the same re-fetch), so the cost model wins. (2) The refusal key and the accessor names — the
> read rule's `db.tried(c.hash)` / `db.hard_negative(video)` are `refused(...)` / `negative(...)`
> (`02-data-model.md` note). (3) *Archive members have no refusal identity* — **ruled for 4b:**
> a member is `jimaku_filename = "<archive name>::<member name>"`, with the archive's size and
> last_modified. Accepted as built: a REFUSED row requires its candidate, a CONFIDENT row its
> `output_path`, a soft negative its entry — each also a schema CHECK.

**surfaces:** `data`
**depends on:** 1a

| | |
| --- | --- |
| **Build** | SQLite, WAL, one accessor. Schema per `02-data-model.md` |
| **Prove** | `hato state --stat` prints row counts by outcome and the next retry dates |
| **Test** | The canonicity table in full, plus expiry, refusal recording and corrupt-DB recovery |
| **Expected** | DB says synced + file gone → **re-fetch**. File present + DB empty → **skip and backfill**. DB deleted → everything still works |

⛔ **One accessor over the records. Nothing else touches the store.**
⛔ **The DB may never be the reason a file gets written.**

---

## Step 1c — ⭐ The key file, the daily retry, the blacklist — ✅ DONE 2026-09-17

**surfaces:** `data`
**depends on:** 1b
**added 2026-09-17**, after 1b was already built — Sonic's rulings the same day. ⛔ Must land
**before 5a**, so the CLI output and its snapshot carry the blacklist skip line.

| | |
| --- | --- |
| **Build** | ① **`key.txt` in hato's OWN root, `%LOCALAPPDATA%\hato\`** — ⚠ the root does not move, and hato does **not** live inside tsubasa's folder; the only path change is the non-Windows default, `~/.cache/hato` → `~/.local/share/hato`, because the root holds kept originals (`05-interface.md` §*The config file*) · ② key precedence `$HATO_JIMAKU_KEY` → `$HATO_KEYFILE` → `<root>\key.txt` → the dev keystore, plus `hato key --show` / `--set-from` · ③ the soft negative at **1 day**, configurable · ④ the **blacklist** table, its state API and `hato blacklist` |
| **Prove** | `hato config --show` names the root · `hato key --show` prints source + last four only · `hato blacklist --list` round-trips an add and a remove · `hato state --stat` shows the new retry dates |
| **Test** | The expiry test moves 7 → 1 · a blacklisted video is skipped **with `--force` still set** · the key never appears in `config.toml`, a log, or an error message · off Windows the root is `~/.local/share/hato` |
| **Expected** | ⛔ The DB still only ever PREVENTS work. ⛔ The key is never printed beyond its last four characters |

---

## Step 2a — The jimaku client — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 2 client builder; proved by the orchestrator** — suite `client` **71
> checks** green through the runner with the network guard armed (zero calls possible), one check
> driving the REAL `requests` stack against a loopback server; mutants `M2a-01…34` all killed
> (builder's `--scratch` run). ⭐ **Decisions the pack left open, accepted:** a 5xx is reported
> once and **never retried** (a retry spends quota on a server that just said it is failing) ·
> a 3xx is refused, never followed · downloads capped at **32 MiB** (the largest jimaku file
> measured 16.3 MiB) · a 429 wait may add up to 120 s, a `reset`-derived wait is capped at the
> 60 s window, every wait +0.25–1.25 s jitter, metered calls spaced 1–2 s · the unreachable
> ladder 5/15/45 s ×1.0–1.25, the 6th consecutive no-answer raises `Unreachable` for the rest of
> the run · `metered` counts HTTP answers from `/api` (401/404/429 included) · downloads strip any
> `Authorization`, so `~/.netrc` cannot add the key · the url guard: https, host exactly
> `jimaku.cc`, `/entry/<digits>/download/<name>`, one bad file refuses the whole list.

**surfaces:** `logic`
**depends on:** 0b, 1a

| | |
| --- | --- |
| **Build** | `Authorization: <key>` **raw, no Bearer**. Rate-limit header handling, jittered pacing, the retry ladder (5 s / 15 s / 45 s), the six-consecutive-unreachable stop |
| **Prove** | `hato doctor` still green, **and** `python run_tests.py client` green with **zero** network calls |
| **Test** | Every trap in `08-research.md`, driven off captured fixtures |
| **Expected** | 429 honours `reset-after` · **401 stops the whole run immediately** · empty query is a hard error before the request · invalid-id 200 detected via the url-prefix guard |
| ⚠ **Amended 2026-09-17 by the capture** | An invalid entry id through the API is **HTTP 404** (`entries_invalid_id_files.json`) — handle the 404 as the primary signal; the url-prefix guard stays as defence, applied to the **path** of an absolute, percent-encoded URL. `reset-after` is absent outside a 429, and no 429 was captured (Whitelist 2) — derive the 429 double from real captured headers and label it derived |

🚨 **A 401 consumes quota.** Retrying a bad key 24 times burns the budget silently. Fail
loud, fail once.

---

## Step 2b — Search and the resolution cache — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 2 client builder; proved by the orchestrator** — `hato identify "frieren
> S2 - 01.mkv" --fixtures` → entry **11446** *Sousou no Frieren 2nd Season*, score 82 · confident,
> **1 API call**; the second run **0 calls, cache hit**. Suite `identify` **52 checks**; mutants
> `M2b-01…26` all killed. ⚠ **Offline proof uses the recorded `query=frieren`:** a real release
> name sends `query=Sousou no Frieren`, which the first capture never recorded — offline it
> refuses honestly with 0 calls spent. The live end-to-end run proves that path, and
> `hato doctor --capture` now records it (plus a no-match query) for next time.
> ⭐ **Part 1 defects, resolved as built:** the Kitsu path costs **2 Kitsu + 3 jimaku** calls
> (search, the `anime=false` retry, then `?anilist_id=`), not "2" · *"search returns `[]`"* is
> really *"nothing reaches the local match floor (0.6)"* — `query=frieren` also returns 13
> unrelated entries · a season mismatch halves a score; LOW CONFIDENCE = top two within 0.05,
> a season mismatch, or similarity under 0.75 · the key is `[v1, folded title, season, year]`,
> punctuation kept, *no season* distinct from season 1. ⚠ **Ruled for 4b (the builder's lean):**
> a show whose every attempted video ends REFUSED has its resolution entry **cleared**, so a
> wrong identification is not cached for ever.

**surfaces:** `logic` `data`
**depends on:** 2a, T1

| | |
| --- | --- |
| **Build** | Normalized title → entry, cached forever. The `anime=false` retry. The Kitsu→AniList fallback |
| **Prove** | `hato identify "<filename>"` prints the entry, the score, and **how many API calls it cost** |
| **Test** | Cache hit costs **0** calls; miss costs 1; the live-action path costs 2 |
| **Expected** | A second run over the same show makes **zero** metered requests |

⚠ **Include the parsed season/year in the cache key.** A collision would serve the wrong
entry from cache forever.

---

## Step 2c — File listing — ✅ DONE 2026-09-17

> ✅ **Proved by the orchestrator** — `hato files 11446 --fixtures` lists **120 files · 5.2 MB**,
> names and sizes, **1 API call**; a check asserts `episode=` is in no request URL from any
> method. Mutants `M2c-01…07` all killed.

**surfaces:** `logic`
**depends on:** 2a

| | |
| --- | --- |
| **Build** | `GET /entries/{id}/files`. ⛔ **Never send `episode=`** |
| **Prove** | `hato files <entry-id>` lists names and sizes |
| **Test** | Against the 120-file fixture |
| **Expected** | All 120 returned. A test asserts the `episode=` param is **never** in any request URL |

---

## Step 3a — ⭐ Episode range alignment — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 2 matcher builder; proved by the orchestrator** — `hato align --explain`
> on a 10-episode stub folder against the recorded entry: Haruhana/KitaujiSub/Nekomoe/Netflix at
> **+28**, NanakoRaws/shincaps at **0**, Amazon split into its seasonal part (1–5, 9–10 at 0) and
> its absolute part (34–36 at +28, landing on the episodes 6–8 the rest of its release leaves
> open) — **12 files from 7 releases per episode**. Suites `tokens` **123** · `align_episodes`
> **27** checks; mutants `M3a-01…42` all killed. ⭐ **Measured on the corpus (233,877 names):**
> bracket-only grouping collided 957 files into one slot across 150 entries; the built grouping,
> 243 (one release carrying two captures of an episode). ⭐ **Accepted as built:** a fit that
> ties is broken by the gaps the release's own parts leave open → an offset another release
> fitted cleanly → the literal number → both anchors (a partial release nothing can place is
> offered at both, and timing refuses the wrong one) · a special's "literal match" = same special
> marker + same episode reading · folders spanning seasons split by season. The seven tokens
> tsubasa does not publish live in `hato/tokens.py`, each with its corpus count.

**surfaces:** `logic`
**depends on:** T1 *(fixtures only — not 2c)*

| | |
| --- | --- |
| **Build** | Group files by release group → extract each group's episode range → align against the video range → derive the offset |
| **Prove** | `hato align --explain <folder> <entry-id>` prints, per group, its range, the derived offset, and the resulting per-episode mapping |
| **Test** | The 120-file fixture. Plus: specials, `.5`, `v2`, multi-episode, single-video, count mismatch |
| **Expected** | 🚨 On entry 11446, groups resolve to **different offsets** and all of them become candidates. A test asserts that pooling the groups produces a **worse** result — that is the finding this step exists for |

⛔ **A file holding two episodes is REFUSED, not guessed.** ⛔ **A parsed special is never
range-aligned.**

> 🚨 **MEASURED ON THE REAL CAPTURE 2026-09-17 (orchestrator), through tsubasa's public parse:**
> `Haruhana`, `KitaujiSub`, `Nekomoe kissaten&LoliHouse` read **episodes 29–38, season None**
> (absolute) · `NanakoRaws`, `shincaps` read **season 2, episodes 1–10** (seasonal) · the 20
> unbracketed files (⚠ corrected by the 3a builder: 10 Amazon + 10 Netflix; Netflix reads season 2
> with ABSOLUTE numbers 31–38) — **Amazon is MIXED INSIDE ONE RELEASE**: those whose episode title carries
> `第NN話` read the ABSOLUTE number with season None (`S02E06.第34話 討伐要請` → **34**), the rest
> read `S02Exx` → season 2. Both are right in their own convention, so ⚠ **a group's range is not
> one numbering** — split by whether a season was read before aligning. Reading every name alone
> or grouped by bracket gave identical answers on this entry.

---

## Step 3b — ⭐ Candidate ranking — ✅ DONE 2026-09-17

> ✅ **Proved by the orchestrator** — `hato rank --explain 11446 3 --folder …`: all 8 `.ass` before
> any `.srt`; within a format Japanese-only → untagged → Japanese + another; size compared only
> inside one format and language class; a whole-range fit before a partial one; every row says
> why it sits above the next. Suite `rank` **24 checks**; mutants `M3b-01…34` all killed.
> ⭐ **Accepted as built (each reversible):** untagged files rank between Japanese-only and
> dual-language (on jimaku an untagged file is almost always Japanese-only) · the AI filter
> catches labelled machine subtitles (whisper markers, Gemini, `[AI Generated]`, subgen — 289
> corpus hits) but NOT titles like *Whisper of the Heart* · a Chinese-only file is filtered out
> (**exactly 1** of 238,250 corpus names — kept because `.ass` first would otherwise try it before
> every Japanese `.srt` and save it as `.ja.ass`) · tsubasa's resolved `lang` is never used for
> ranking (measured: `.ts.ass` reads Tsonga, `.no-sdh` Norwegian, `.sc-jp` Sardinian).

**surfaces:** `logic`
**depends on:** 3a

| | |
| --- | --- |
| **Build** | AI filter → ⭐ **`.ass` first (RULED 2026-09-17)**, then `.ssa`, `.srt`, the rest → single- over multi-language **within a format** → offset confidence → size within a format and language class → group already seen to succeed |
| **Prove** | `hato rank --explain <entry-id> <episode>` prints every candidate with its score and the reason for its position |
| **Test** | ⭐ A `[CHS, JPN]` `.ass` outranks a `[JPN]` `.srt` · within `.ass`, `[JPN]` outranks `[CHS, JPN]` for the same episode and group · a `whisper`-tagged file is excluded unless `--allow-ai` — **even as `.ass`** |
| **Expected** | Ranking chooses **who goes first**, never who is right |

⚠ **Never compare size across a format or a language class.** The dual-language file is
bigger *because* it carries a second language, and an `.ass` carries style headers an `.srt`
does not — size is a signal only within one format and one language class.

---

## Step 3c — Archive extraction — ✅ DONE 2026-09-17

> ✅ **Built by the Wave 2 archives builder; proved by the orchestrator** — `hato extract` on a
> generated season zip: 3 subtitles into the cache, the `.nfo` skipped; on a zip-slip archive:
> refused WHOLE, nothing extracted, exit 1. Suite `archives` **92 checks**; mutants `M3c-01…49`
> all killed. 🚨 **A DEFECT THE SPEC HAD NO ROW FOR, measured:** `py7zr` 1.1.3 **hangs for ever** on
> a hostile `.7z` whose header overstates a member's size (COPY, Deflate, BCJ-x86+COPY coders) —
> anyone who can upload to jimaku could stall a scheduled run holding its lock. Guarded: 64 empty
> decompressor answers in a row → `ArchiveError`; tested per coder under a thread timeout. ⚠ The
> guard reaches into py7zr internals, so **py7zr must be pinned at release**. ⭐ **Accepted:** caps
> 64 MiB per member · 512 MiB total · 10,000 members (the largest real subtitle 15.3 MiB) · an
> unflagged zip name is tried as **UTF-8 before cp932** — deviating from the ruling, on a
> measurement: 0 of 114,156 cp932 corpus names are valid UTF-8, while 10% of UTF-8 names decode
> as cp932 gibberish · a `.rar` with no tool (unrar, unar, 7z, 7zz, bsdtar all absent here) is
> checked BEFORE parsing — rarfile parses a bare RAR3 signature as a valid empty archive · no
> subtitle, empty, duplicate names, password-protected → ERROR; an unsupported method → skip.

**surfaces:** `logic`
**depends on:** 1a

| | |
| --- | --- |
| **Build** | zip / 7z / rar → the **cache dir**. Size and member caps |
| **Prove** | `hato extract <archive>` lists members and the extraction root |
| **Test** | 🚨 **A zip-slip fixture** (`../../evil.srt`) · a size-bomb · a nested archive · a `.rar` with `unrar` absent |
| **Expected** | Path traversal → **entry rejected outright**. Missing `unrar` → candidate skipped with a reason, ⛔ **never a crash** |

---

## Step 4a — The `sync()` port — ✅ DONE 2026-09-17

**surfaces:** `logic`
**depends on:** T3

🚨 **AMENDED 2026-09-16 — this step was named for `align()`, and that name belongs to a
different tsubasa function.** `tsubasa.align(R, A, duration)` aligns two arrays of
cue-start times; it takes no paths. The tsubasa backend of this port is
**`tsubasa.sync([(video, path)], write=...)`**, which returns a `SyncReport` of `Result`
— the shape `05-interface.md` passes through unchanged. ⭐ tsubasa 0.1.0 also has
`self_check()`, `scan.unpaired(lang=)` and the episode properties this pipeline needs;
`10-deployment.md` maps each one.

⭐ **RULED 2026-09-16 (Sonic): NO subsync adapter.** tsubasa is the only backend. This step
was *one function, two backends*; it is now one function, one backend, and the stub the
suite needs.

| | |
| --- | --- |
| **Build** | One `sync()` function over `tsubasa.sync([(video, original)], write=...)`. Shaped to tsubasa's `Result` **exactly**. ⭐ **Ruled 2026-09-17: the real call writes** (`write=True`) — tsubasa places the file; hato never does. Decide tsubasa's `results=` argument deliberately, and test the choice |
| **Prove** | `hato sync <video> <sub>` returns tsubasa's `Result` unchanged — every field, not a re-wrapped subset |
| **Test** | A stub behind the port for the suite, plus ONE contract test that runs the real `tsubasa.sync()` through it, on a real video built in a temp dir (`07-test-plan.md`): the output is `<video stem>.ja.<ext>` **beside the video**, the original is **byte-identical and still where it was**, nothing is trashed, and nothing else appears in the folder |
| **Expected** | Callers depend on the port, never on tsubasa directly. ⛔ **CONFIDENT is not WRITTEN** — success is CONFIDENT *and* an `output_path` |

⚠ **The contract test runs the real tsubasa from day one.** A port exercised only against its
own stub is proof of the stub.

---

## Step 4b — The fetch loop — ✅ DONE 2026-09-17

**surfaces:** `logic`
**depends on:** 2b, 2c, 3b, 4a, 1b, **T4**

| | |
| --- | --- |
| **Build** | The pseudocode in `03-permissions.md` §*The read rule*, verbatim — **the 2026-09-17 version** |
| **Prove** | `hato <fixture-folder> --dry-run` then a full run against recorded API + stub aligner |
| **Test** | Each of the four outcomes; escalation on REFUSED; the cap; **a refused hash is never re-downloaded**; ⭐ **a video with no subtitle track makes zero requests, zero downloads and no refusal row**; a deleted synced file is **re-synced from its kept original with zero network**; a folder whose subtitles are all present **opens no container** |
| **Expected** | ⛔ **Zero metered calls inside the candidate loop.** A test asserts the call count for a warm-cache run is **0** |

> 🚨 **DEFECT, RECORDED AT 4b's BUILD (2026-09-17) — nothing in this pack opens an ARCHIVE
> inside the fetch loop.** `06-edge-cases.md` §5 rules that an entry offering only a
> `.zip`/`.7z`/`.rar` is downloaded and unpacked in the cache and its members aligned
> normally; `config.archives` is a documented key; and **step 3c built the extractor** —
> zip-slip guard, caps, the py7zr stall guard, 92 checks. But the read rule in
> `03-permissions.md`, which 4b implements verbatim, has **no step that opens one**, and 4b's
> row above does not name it. `hato/episodes.py` drops every non-subtitle file before
> ranking, so an archive is never a candidate.
>
> ⭐ **Built instead of guessed the shape:** every archive on an entry is named in a show
> note (`pipeline._archive_note`), so a person can see what was not tried and unpack it with
> `hato extract` + `hato sync`. Measured against the recorded movie entry, which really
> carries one. **The missing shape is a decision for Sonic, not a builder's to invent:**
> where the download sits (an archive is downloaded before alignment, unmetered but large),
> what a member's candidate identity is (1b already ruled `"<archive>::<member>"`), and
> whether extraction is cached across runs. `config.archives` is inert until then.

---

## Step 4c — Keep the original, hand it to tsubasa — ✅ DONE 2026-09-17

**surfaces:** `data`
**depends on:** 4b, T3

⭐ **REWRITTEN 2026-09-17 — Sonic's ruling: tsubasa writes the synced file; hato keeps the
original.** *"the subs would be in a specific hato folder … don't delete them but rather have
tsubasa create the name convention exactly as the video file. That way we have the src sub
used as well as the new one."*

| | |
| --- | --- |
| **Build** | The finished download is named `<jimaku stem>.ja.<ext>` → `tsubasa.sync([(video, it)], write=True)`, with `out_dir` set to the video's **mirrored** directory only under `--out` → on CONFIDENT **and** written, the original moves into `subs_dir/<entry name>/` by temp-plus-rename, **never deleted**. A `subs_dir` inside a scanned folder is a config ERROR |
| **Prove** | Run against a fixture tree built in a temp dir; list each video folder **and** `subs_dir` — exactly one new `<video stem>.ja.<ext>` beside each synced video, exactly one original per synced file, nothing else |
| **Test** | 🚨 **The `.ja` tag on the original** — remove it and watch a check go red: tsubasa writes `<video>.ass` and the next run fetches again · encoding preserved (Shift-JIS round-trip) · BOM · CRLF · `--out` mirrors · a same-name original with different content is kept under a hash suffix, never overwritten · `subs_dir` inside a scanned folder refused |
| **Expected** | 🚨 **Nothing new in the media folder except tsubasa's finished file.** A test asserts **no** `.part`, `.tmp`, original or extracted archive member lands there |

⚠ **Write first, keep second.** The original moves into `subs_dir` only after tsubasa reports a
written file — so `subs_dir` holds exactly the originals that were **used**, and a refused
candidate stays in the disposable cache with its hash recorded.

⚠ **Temp-plus-rename, never truncate-in-place**, for everything hato writes into `subs_dir`.
`open(path,'w')` truncates on open; if the write then raises, the file is zero bytes. This
destroyed `tsubasa/spec/RUNBOOK.md` on 2026-09-07.

---

## Step 4d — ⭐ Archive candidates, OFF by default — ✅ DONE 2026-09-17

**surfaces:** `logic` `data`
**depends on:** 3c (built), 4b (built)
**added 2026-09-17** — 3c built the extractor and **nothing ever called it**, recorded at 4b
as `_archive_note`. Sonic ruled the shape the same day.

| | |
| --- | --- |
| **Build** | An archive candidate is unpacked **only when archives are on** (`archives = true`, or `--archives`; ⭐ **the default is OFF**). Unpack in the cache dir, take the member matching the episode, hand that member to the port exactly as a plain download. ⛔ While off, the candidate is **skipped with a reason naming the flag** — never silently dropped |
| **Prove** | `hato <fixture-folder>` twice, with and without `--archives`, against a captured entry whose only candidate is a `.zip` |
| **Test** | Off: zero extractions, the reason names `--archives`, the archive is still never unpacked · On: the member is chosen by episode and synced · a zip-slip archive is refused **with archives on** · a `.rar` with no `unrar` degrades with a reason · nested → ERROR, one level only |
| **Expected** | ⛔ Nothing is ever unpacked into the media folder, on or off. The existing 92 archive checks already hold the extractor's guards — this step only adds the caller and the gate |

⚠ **Why off:** unpacking a stranger's archive is the one place hato acts on structure it did
not author. The guards are real (zip-slip rejected before a byte is read, size and member
caps, subtitles only, junk ignored) — the default is conservative because the person, not the
tool, should choose to run them.

---

## Step 5a — CLI output — ✅ DONE 2026-09-17

**surfaces:** `ui`
**depends on:** 4c

| | |
| --- | --- |
| **Build** | Both modes from `05-interface.md`, exactly as ruled — **including the `⊘` no-track line added 2026-09-17** |
| **Prove** | Run against the fixture folder and **LOOK at the output**, both modes, in a real terminal |
| **Test** | Snapshot the rendered output; assert problems sort **above** successes; assert the API-call count line is present |
| **Expected** | ⛔ **No raw confidence multiple in default output.** ⛔ **Colour degrades when stdout is not a TTY** |

---

## Step 5b — Config — ✅ DONE 2026-09-17 (built at 0a)

> ✅ **Proved by the orchestrator** — `hato config --show` run from the project root and two
> unrelated temp directories produced **byte-identical** output (md5 compared, not eyeballed); the
> same claim is a check in `test_wiring.py`. Missing file → documented defaults · `HATO_CONFIG`
> honoured · an unknown key refused by name · a key-shaped field refused with the reason · a
> relative path refused (the scheduler starts elsewhere) · `candidates = true` refused — suite
> `config` 27 checks, mutants `M0a-05…08`. `tomli` 2.4.1 was already installed (pytest 9 pulls
> it in on Python < 3.11). ⚠ **What this step cannot show alone:** that the RUN reads it the same
> way (CLI flags over config, `config.folders` when no folder is given) — verified with 4b and 5c.

**surfaces:** `data`
**depends on:** 5a

| | |
| --- | --- |
| **Build** | TOML per `05-interface.md`, **including `subs_dir`**. One config, read identically by CLI, `.cmd` and scheduler. ⚠ `tomli` on Python < 3.11 — this laptop is 3.10 |
| **Prove** | `hato config --show` from three different working directories gives the same answer |
| **Test** | Missing file → documented defaults, not a crash. `HATO_CONFIG` honoured |
| **Expected** | ⛔ **No key in the config file, ever** |

---

## Step 5c — `hato-run.cmd` and the scheduled run — ✅ DONE 2026-09-17, run for real

**surfaces:** `ui` `delivery`
**depends on:** 5b

| | |
| --- | --- |
| **Build** | The launcher per `10-deployment.md` |
| **Prove** | Three ways, **all three exercised**: double-click · drag a folder onto it · **run it once from Task Scheduler and read the log** |
| **Test** | Exit codes: `0` when it ran, non-zero only when it could not. **A refusal is not a failure** |
| **Expected** | No pause when scheduled · absolute paths only · no ANSI in the log |

🚨 **The scheduled run is the most likely thing to be found broken in production**, because
its environment resolves `%LOCALAPPDATA%` and the keystore path differently from a
developer shell. ⛔ **Do not mark this step done without one real scheduled execution and a
log you have read.**

⭐ **The orchestrator does it (2026-09-17):** register a one-off task clearly named
`hato-build-check`, point it at a temp **copy** of a folder, run it once, read the log, then
delete the task. Reversible, and nothing for Sonic to do.

---

## ⭐ LAYER 7 — THE WINDOW. Added 2026-09-18

> **The design is RULED and approved** (Sonic, 2026-09-18: *"It's perfect."*).
> ⛔ **Implement `gui-mock/mock2.html`; do not redesign it.** `05-interface.md` §*The window*
> carries the requirements verbatim; `gui-mock/MEMORY.md` carries the watcher measurement.
>
> **The toolkit is PyQt6**, taken as the spec's own ⭐ lean and assigned by `HANDOFF.md` §9.
> 6.11.0 is installed here, it is GPL-3.0 (hato's own licence), it needs nothing on a
> stranger's machine, and it is the friendliest of the three to freeze.
>
> 🚨 **TWO STEPS HERE EXIST BECAUSE A "VERIFIED" CLAIM WAS FALSE.** `HANDOFF.md` §4d says
> *"this section previously claimed 'NO new capability — verified', and that was FALSE"* —
> an adversarial pass caught the config writer. **7b is the same defect, found the same way
> and one row further down the same table**: that table marks *"Paint the run"* ✅ against
> `hato <folders> --json`, which is true about the OBJECTS and false about the WHEN. The
> objects are all emitted after `pipeline.run()` returns (`hato/commands/run.py`), so the
> ruled requirement *"show the process as it does it automatically"* had nothing behind it
> either. ⭐ **Verifying that a command exists is not verifying that it answers the
> question the interface asks of it.**

---

## Step 7a — ⭐ The config writer, and a non-file key route — ✅ DONE 2026-09-18

> ✅ **Proved by the orchestrator.** `hato config --set candidates=5` → `--show --json`
> reports 5 from `config.toml` · `--add-folder` / `--remove-folder` / `--add-skip` round-trip
> · a relative path and `lang=jap` are refused by **config.py's own sentences** · a key piped
> through `hato key --set-from -` lands in `key.txt` with no second file on disk. Suite
> `config_write` **41 checks**; mutants `M7a-01…14` (13 live, one id retired), **all killed**.
>
> 🚨 **THREE MUTANTS SURVIVED THE FIRST PASS, and all three were defects in the CHECKS:**
>
> | Survivor | What it exposed |
> | --- | --- |
> | the literal-string branch | **Both branches were right.** The basic-string fallback escapes backslashes properly, so disabling the literal branch changed nothing. The docstring called it *"a correctness fix rather than a style"* and that was **false** — corrected, and the mutant re-aimed at the escaping, which is the real guard |
> | the `isabs` guard in `_folder_list` | **Redundant.** `config.parse` refuses a relative path in the same sentence before anything is written. ⭐ Disposition: the guard was REMOVED, not the check weakened — a second validator contradicts this step's own *one writer, one schema, one validator* |
> | the key's comment guard | 🚨 **The check passed for a reason other than its name.** The case was `"# not a key"`, which contains SPACES, so the *space* guard caught it and the comment guard could be deleted unnoticed. Now `"#notakey"`, and the cases are parametrised one per run — ⛔ **a loop over overlapping cases lets any single guard be deleted silently** |

**surfaces:** `data`
**depends on:** 5b

**Part 1 defect, recorded:** `hato config` is READ-ONLY (`--show` / `--check-key`), and
`hato/config.py` exposes `parse()` and `load()` with no `save`, `write` or `dump`. Settings
(Tab 3) edits watched folders, skipped folders, the schedule and the key, and **two-thirds
of it had no mechanism.**

⛔ **The window must not edit `config.toml` itself.** `config.py` owns a closed schema that
refuses unknown keys by name, refuses relative paths and refuses key-shaped fields; a second
writer means two programs disagreeing about one file, which is the defect class `LEDGER.md`
§data already records as *"two roads into one setting"*. **One writer, one schema, one
validator** — and the writer round-trips through `parse()`, so nothing can be written that
hato would refuse to read back.

⚠ **This does not violate *"the window decides nothing."*** That rule is about the DOMAIN —
which subtitle is right — and the timing verdict remains the referee. Recording which
folders a person chose is not a judgement about subtitles.

| | |
| --- | --- |
| **Build** | `config.dumps(cfg)` → TOML · `config.save(cfg, path)` temp-plus-rename · `hato config --set k=v` · `--add-folder` / `--remove-folder` / `--add-skip` / `--remove-skip` · ⭐ `skip_folders` as a new schema key (the mock's *Skip these folders*) · `hato key --set-from -` reading **stdin**, so a GUI key field never writes the secret to disk first |
| **Prove** | `hato config --set candidates=5` then `hato config --show --json` reports 5 from `config.toml` · `--add-folder` round-trips · an invalid value is refused **by the same sentence** the file gets · `printf '%s' KEY \| hato key --set-from -` then `hato key --show` |
| **Test** | Every refusal reachable by both roads · a write that raises leaves the OLD file intact (temp-plus-rename) · ⛔ **the key never reaches `config.toml`** · a comment-only file survives a `--set` or is documented as not surviving · `--set-from -` leaves no temp file behind |
| **Expected** | ⛔ Anything `parse()` refuses, `save()` refuses FIRST. A written file re-reads to an identical `Config` |

🚨 **Never `open(path,'w')`.** `LEDGER-HOT.md`: it truncates on open, and a raise after that
leaves zero bytes. This destroyed `tsubasa/spec/RUNBOOK.md` on 2026-09-07.

---

## Step 7b — ⭐ The progress stream — ✅ DONE 2026-09-18

> ✅ **Proved by the orchestrator, and LOOKED at.** A real run emits
> `start · found · (video · result)×N · <the video objects> · run`, in that order. Suites
> `pipeline` **83 checks** (+5) and `endtoend` **74** (+5).
>
> 🚨 **AND LOOKING IS WHAT FOUND THE DEFECT — every check was green.** The `result` report
> sat inside the candidate loop, which is **one of seven callers** of `_keep_result`. So a
> run where every video was settled at the gate — already subtitled, blacklisted, no track,
> waiting on a retry — emitted `start`, `found`, and then **nothing at all** until the run
> object. ⭐ **That is the commonest run there is:** a library where nothing new has arrived.
> The checks were green because the fixture behind them only holds videos that need fetching.
> Moved to `_keep_result`, the one funnel every outcome passes through, and pinned by
> `test_a_run_decided_entirely_at_the_gate_still_reports_every_video`.

**surfaces:** `ui`
**depends on:** 5a

**Part 1 defect, recorded:** `05-interface.md` §*The window* rules *"Show the automatic run
as it happens"* — Sonic: *"normally it would do it automatically and just show the process
as it does it automatically"* — and the mock paints a live footer (`running — Tetsunabe no
Jan`). **`hato --json` cannot feed that.** `report.ndjson(run_report)` is built from a
finished report and every line is written after `pipeline.run()` returns, so a shell over it
can show a spinner and nothing else.

⭐ **Shape: `--progress`, additive, opt-in, and the existing grammar is untouched.** hato
emits `{"type": "progress", ...}` NDJSON lines on stdout as work happens; the per-video
`{"type":"video"}` objects and the final `{"type":"run"}` object are unchanged and still
come at the end. **Without the flag the output is byte-identical to today**, and the suite
already filters on `type` (`tests/test_endtoend.py:513`), so a new type cannot break a
consumer that does not ask for it.

⚠ **Why not stream the video objects instead** — the obvious move. It changes the emission
point of every existing object and the ordering the plain render depends on, to buy the
same information. A separate typed line costs one `if` and cannot regress anything.

| | |
| --- | --- |
| **Build** | An optional `on_progress` callback through `pipeline.run()`, called at the points a person would name — folder scanned, show identified, video started, candidate tried, video finished. `--progress` wires it to a stdout emitter; without it the callback is `None` and no branch runs |
| **Prove** | `hato <fixture-folder> --json --progress` shows progress lines arriving **before** the run object · without `--progress`, the stream is unchanged for a consumer that did not ask for it |
| **Test** | 🚨 **A check that would go red if the lines were buffered to the end** — assert a progress line is emitted before the pipeline returns, not merely that one exists · the byte-identical claim, both directions · every progress object carries `type` · ⛔ no key, path secret or subtitle body in any progress line |
| **Expected** | ⛔ Nothing reaches stdout in `--json` mode that is not NDJSON. A progress line is NDJSON |

---

## Steps 7c–7e — The window — ✅ BUILT 2026-09-18

> ✅ **PyQt6 6.11.0. `hato/gui/`: `run.py` (the driver, ⛔ no Qt) · `theme.py` · `branding.py`
> · `app.py` · `__main__.py`.** Suites `gui_run` **23** + `gui_widgets` **121**; mutants
> `M7c-01…40` and the driver's share of `M7a`, **all killed**. Full runner **26 suites / 1490
> checks GREEN**. ⭐ **`python -m hato.gui` launches and runs** — verified end to end, not
> only as widgets.
>
> 🚨 **`QT_QPA_PLATFORM=offscreen` ON WINDOWS LOADS ZERO FONTS.** The first shots came back
> as **tofu** — every string a row of boxes. The PNG is real, the geometry is real, and the
> typography is fiction, so an offscreen shot is a picture of a window nobody can read. ⛔ It
> was the ORCHESTRATOR'S OWN recommended recipe. Shoot with the real platform plugin and
> `WA_DontShowOnScreen`. ▶ `LEDGER.md` §harness.
>
> **Found by LOOKING, none by an assertion:** blacklist rows drawn over each other (an
> `Ignored` size policy claimed the row and starved its fixed-width siblings) · paragraphs
> silently truncated with no ellipsis · the count badge painted on top of its own tab label ·
> ⭐ **91% rendered green** — the mock colours by tsubasa's VERDICT WORD (`locked` green,
> `strong`/`fair` amber), not by a percentage threshold · an info dot drawn as a rounded
> square · a failure line allotted zero width, so it was invisible.
>
> 🚨 **AND A FIXTURE THAT MADE THE PICTURE LIE.** One hard-coded candidate pool was shared by
> every row, so the **Frieren** row offered an `[Erai-raws] Re Zero 3rd - 54` file at 57%
> where the mock has its own NanakoRaws file at 31%. Every check passed — they assert the
> row's SHAPE, and the shape was right. ⭐ *A mock's seed data is shipped content, because
> the picture is the deliverable.* Pinned by a check that every candidate's episode matches
> the row offering it.
>
> ⚠ **Not reproduced in Qt:** the mock's 1px hover lift — a `pos` animation inside a layout
> is overwritten by the next layout pass; the animated glow ships instead, on the same curve.
> ⚠ **Qt is an optional extra (`gui`), not a dependency** — the CLI does the whole job, and
> an absent toolkit gives an instruction naming the extra rather than a traceback.

**surfaces:** `ui`
**depends on:** 7b

⛔ **NO TOOLKIT IMPORT IN THE RUNNER MODULE.** tsubasa's `gui/run.py` opens with that rule
and gives the reason: the subprocess, the decoding, the parse and the counts are where the
failures live, and *"a check that needs a window to run is a check that gets skipped on
CI."* hato's `gui/run.py` is the same split — everything below the painting is asserted
without a display.

🚨 **Four things about the child that read as failure and are not** (tsubasa's, measured):
**exit 1** is *"something was REFUSED"*, the whole value proposition — ⛔ only exit **2**
means the command could not run · **output on stderr** is deliberate, it is where the
summary goes so a pipe stays pure NDJSON · **zero rows** is three different states ·
**a flagged result** is CONFIDENT and repaired a cut.

🚨 **And the console window.** A GUI parent has no console, so every child allocates its own
and it flashes over the app and steals focus. `CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW`,
per `tsubasa/gui/run.py` §`no_console_kwargs`.

| | |
| --- | --- |
| **Build** | `hato/gui/`: `run.py` (the subprocess + NDJSON reader, ⛔ no Qt) · `theme.py` (the measured tokens from `gui-mock/theme.css`, as QSS) · `branding.py` (the mark, from the logo pack) · `app.py` (the window: title bar, the three tabs, the footer) · the **Subtitles** tab — a row is **episode · % · the file it was paired with**, everything else behind a click |
| **Prove** | Launch it against a fixture folder and **LOOK at a screenshot of every tab**, at the mock's own size and clamped to 1024×620 |
| **Test** | `run.py` fully, with no display: argv construction · the frozen vs source branch · `CREATE_NO_WINDOW` present on Windows · NDJSON parse, including a malformed line · 🚨 **the counts PARTITION** — clean + needs-a-pick + errored + skipped + already-had == rows, asserted · ⛔ **the word "refused" appears nowhere in any string the interface can show** — a check that greps the built UI strings |
| **Expected** | ⛔ The window decides nothing. It spawns `hato --json --progress` and paints what comes back |

⚠ **Every value derives from one state object.** The mock's own notes record the badge and
the footer tally both showing a stale hardcoded count — *the same number, hardcoded twice*.

---

## Step 7d — The window: Needs you — the picker

**surfaces:** `ui`
**depends on:** 7c

| | |
| --- | --- |
| **Build** | An accordion, **one open at a time**. ⭐ **Clicking a candidate IS "use this pair"** — no confirm button; it commits via `hato sync <video> <subtitle>`, the row collapses to green **naming the file it used**, and the next unresolved row opens. Blacklist stays a button, because it is a different decision. The candidates come from the stream's own `attempts` (`name`, `bytes`, `match_rate`) — ⛔ never the whole jimaku list |
| **Prove** | Drive a pick end to end against a fixture and LOOK at it: before, open, and after — the collapsed row must still say what happened to it |
| **Test** | A pick spawns `hato sync` with **exactly** that pair · a refused pick leaves the row asking, not claiming · the count badge and the footer tally both derive from state and agree · reopening and re-picking works · ⛔ the accordion animates to CONTENT height, never a cap |
| **Expected** | ⭐ Rule 1 holds even when the person chooses: **the timing verdict still refuses a wrong pair.** The worst case is no file, never a bad one |

---

## Step 7e — The window: Settings

**surfaces:** `ui` `data`
**depends on:** 7a, 7d

| | |
| --- | --- |
| **Build** | Schedule + time · folders · skipped folders · the key · the blacklist. Every write goes through 7a's subcommands. ⭐ **hato detects the blacklist rows whose video is no longer on disk and offers to remove them in one action** — *"it's likely they will not clean it"* |
| **Prove** | Change each setting in the window, then `hato config --show --json` from a shell agrees. LOOK at the tab — 🚨 **this is the screen native controls cluster on** |
| **Test** | Each control round-trips through the real config file · a refusal renders as hato's own sentence, not a stack trace · the stale-blacklist detector against a fixture where some videos exist and some do not · ⛔ the key field never writes a temp file |
| **Expected** | ⛔ No native Windows-blue control anywhere. `build-ui`: *a control's SHAPE is a claim about its behaviour* |

---

## Step 7f — The tray watcher — ✅ BUILT 2026-09-18 (the watching half)

> ✅ **`hato/watch.py` — `ctypes` only.** Suite `watch` **26 checks**; mutants `M7f-01…09`
> (8 live, one id retired), **all killed**. ⭐ The POLICY runs on a **fake clock**, so a check
> about a sixty-second settle does not take sixty seconds, and the Win32 half is as thin as
> it can be.
>
> ⭐ **The architecture is a CHECK, not an intention:** a static check reads the module's own
> source and fails if it imports a GUI toolkit or `hato.pipeline` — the entire reason this is
> a separate 13.4 MB process rather than a resident Qt one at 30.6. Mutant M7f-08 proves that
> check can fail.
>
> ⚠ **A redundant guard removed, after M7f-03 SURVIVED.** A list of download suffixes
> (`.part`, `.crdownload`, `.!ut`, `.tmp`) caught nothing: every one is appended AFTER the
> extension, so the video-suffix test rejects them with or without it. **Measured** — `.!qB`
> and `.aria2` were rejected too and were never in the list. ⭐ And the case it claimed to
> guard (a downloader that writes the final name and grows it in place) defeats any name
> test; `SettleTimer` is what handles it, which is Sonic's one-minute ruling doing its second
> job.
>
> ✅ **THE TRAY IS BUILT — `hato/tray.py`, `Shell_NotifyIcon` over ctypes.** `python -m
> hato.watch` is a real program: it reads the folders through the ONE config reader, watches
> each, and sits in the tray with **Open hato · Run now · Stop watching**. Suite `watch`
> **36 checks**; mutants `M7f-01…13`, all killed. ⭐ **Resolving the tray and window APIs
> costs nothing measurable on top of the watching** — 13.4 MB either way (`MEMORY.md`), which
> is what makes a ctypes tray worth the work against Qt's 30.6.
>
> 🚨 **A TICK HUNG OFF THE BOTTOM OF A MESSAGE LOOP NEVER FIRES.** `GetMessageW` BLOCKS until
> a message arrives, and a tray process on an idle machine gets none for hours — so the
> settle timer would have been polled only while somebody was clicking the icon. **A watcher
> that works only while being watched.** `SetTimer` + `WM_TIMER` is what makes the loop wake
> on its own. ⛔ Caught while writing it, not by a check: the message loop is the one part of
> this that no headless check can reach.
>
> ⚠ **Three things ctypes will not forgive, all guarded:** a `WNDPROC` held only in a local is
> freed and Windows calls into dead memory at the first message · an exception crossing back
> into a `WNDPROC` kills the process with no traceback · `TrackPopupMenu` on a window that is
> not foreground leaves the menu on screen until the next click elsewhere.
>
> ⛔ **`open_window()` SPAWNS; it does not import.** `from hato.gui import main` here would
> load Qt into the tray process permanently and undo the whole measurement — and the import
> check that forbids it now walks with `ast`, because a regex over `from X import Y` sees only
> `X` and the one spelling anybody would type (`from hato import gui`) was the one it could
> not see.
>
> ▶ **NEEDS-EYES, and it is the only way:** that the icon appears, the menu opens and the
> balloon reads right cannot be checked headlessly. ▶ Also still to build: the Settings
> toggle that registers the watcher to start with Windows.

**surfaces:** `delivery`
**depends on:** 7a

🚨 **Sonic:** *"it needs to be SO SO SO small in memory while it watches… basically 0
resources if possible… basically in the tray."* **Measured** (`gui-mock/MEMORY.md`):
bare python **12.7 MB**, + a real watch handle and buffer **13.4 MB**, a resident Qt tray
**30.6 MB**. ⭐ **The watching costs 0.7 MB; the rest is the interpreter.**

| | |
| --- | --- |
| **Build** | `ctypes` only — ⛔ no GUI toolkit, ⛔ no hato pipeline import. Opens a directory handle, waits, and spawns `hato` when a file has been still for **1 minute** (Sonic's, and it is also what lets a download finish). ⛔ **Off by default** |
| **Prove** | Run it, drop a file, read the log — **and measure its RSS with `psutil`** and put the real number in the UI |
| **Test** | The settle timer · a file still growing is not fired on · ⛔ **a check that the module imports neither Qt nor `hato.pipeline`** · the spawn is `CREATE_NO_WINDOW` |
| **Expected** | ⛔ A number in an interface is a claim. `gui-mock/MEMORY.md` records *"~12 MB"* shipping in the UI before anything had measured it; it was 13.4 |

⚠ **Say the seasonal caveat plainly:** for a season still airing the subtitle is published
hours to days after the episode, so a run fired on arrival finds nothing **and** records a
miss that holds the retry until tomorrow. For a finished show it works.

---

## Step 7g — The exe — ✅ BUILT 2026-09-18

> ✅ **`packaging/` — `hato.spec` · `entry_cli.py` · `entry_gui.py` ·
> `entry_watch.py` · `smoke_standalone.py`.** Built with PyInstaller 6.18.0,
> onedir, **three executables from ONE `COLLECT`**, 142 MB bundle:
>
> | | | |
> | --- | --- | --- |
> | ⭐ **`hato.exe`** | windowed | **THE WINDOW — the one file a person clicks** |
> | `hato-cli.exe` | console | the command line, spawned for every run |
> | `hato-watch.exe` | windowed | the resident tray watcher |
>
> 🚨 **RULED BY SONIC 2026-09-18, AFTER THE FIRST BUILD:** *"i don't want it
> 'gui', i want it to be hato as the main one ... i can just click on hato.exe
> and it will handle everything else."* The first build had `hato.exe` as the
> CLI and `hato-gui.exe` as the window; they were swapped and every caller
> updated. ⛔ Anything meaning *"run a scan"* must spawn `hato-cli.exe` —
> spawning `hato.exe` opens a second window instead.
>
> ⚠ **ONE BINARY CANNOT DO BOTH JOBS**, and this was asked: `console` is
> compiled in. A console build flashes a terminal every time the window opens;
> a windowed build has no valid stdout, so `--version` prints nowhere and the
> window cannot read its child. Three files, one of which is ever clicked.
>
> **Proof command — it was run, and it is the step's gate:**
> ```
> python -m PyInstaller --noconfirm --distpath dist/standalone --workpath build/standalone packaging/hato.spec
> python packaging/smoke_standalone.py
> ```
> ⭐ **15 checks, 0 failed, against the BUILT BYTES.** Suite `packaging` gained
> **7 checks** (34 total) that guard the spec from the source side. Full runner
> **26 suites / 1569 checks GREEN**, no isolation fault.
>
> 🚨 **TWO DEFECTS FOUND BEFORE THE FIRST BUILD, both of which produce a bundle
> that builds cleanly and fails in use:**
>
> | Found | What it would have done |
> | --- | --- |
> | **`cli.py` dispatches every subcommand through `importlib.import_module(COMMANDS[name])`** | PyInstaller cannot see an import built from a dict, so **all 13 commands would have shipped dead** while `--version` worked and the build looked perfect. The spec now reads `COMMANDS` itself, so a command added later freezes automatically |
> | **tsubasa's `__pyinstaller` hook is NOT registered** in `pyinstaller40` entry points here (only numpy, hooks-contrib, yt_dlp — tsubasa is a source checkout) | tsubasa's data tables would be silently absent. Its own spec records the cost: the build *"still runs and exits 0"* while settled-by-name falls **80.0% → 51.4%**. `hookspath` now points at tsubasa's own hook rather than copying its patterns |
>
> ⭐ **The three exe NAMES are a contract with code that already shipped** —
> `cli_argv`, `watch_argv` and `open_window` each resolve a sibling of
> `sys.executable` by name. `test_the_three_FROZEN_names_are_exactly_what_the_code_SPAWNS`
> round-trips them through the real functions with `sys.frozen` faked, so a
> rename now fails a check instead of producing a bundle that dies at the first
> spawn. Verified by breaking it.
>
> ⭐ **Qt is excluded from the CLI and watcher analyses** — the 13.4-vs-30.6 MB
> argument expressed as a build. Measured on the frozen bytes: the watcher
> loads **no Qt at all** and is **30.9 MB against the window's 97.3**, a 66 MB
> saving.
>
> ⚠ **A CHECK THAT WAS WRONG IN THIS PROJECT'S OWN FAVOURITE WAY, and the
> record is worth more than the fix.** The first size assertion was `< 30.0 MB`,
> borrowed from `watch.py`'s header where 30.6 is a **source-mode** Qt tray. It
> failed on a completely healthy build, because freezing adds ~15 MB to every
> process (watcher 15.8 → 30.9, window 81 → 97.3). ⛔ **A measurement is about
> the thing it was measured on.** A probe settled it rather than an argument:
> the frozen watcher loads `python3.dll`, `python310.dll` and 57 ordinary
> Windows DLLs — nothing leaked in. The check now compares the watcher against
> the **window**, same host, same build.
>
> ⚠ **AND THE SCREENSHOT LIED THE SAME WAY.** The first capture sized its
> bitmap from `GetWindowRect` (logical px) while `PrintWindow` renders
> **device** px — at DPI 240 / scale 2.5 that is a 1113×695 crop of a 2782×1738
> window, 16% of the area. The empty state sits below the crop, so it read as
> *"the no-folders state does not render"*. ⛔ It renders perfectly.
> `gui-shots/frozen-01-window.png` is the correct capture.
>
> ⭐ **AND THE DISTRIBUTABLE — `packaging/package_standalone.py`.**
> `hato-<version>-windows-x64.zip`, **265 files, 67.0 MB from 140.7 MB on disk
> (48%)**, everything under one top-level `hato/` so unzipping produces a
> folder rather than 1,200 loose files on somebody's Desktop.
>
> 🚨 **THE ZIP IS NOT ABOUT COMPRESSION. IT IS THE ONLY ARTIFACT TESTED THE WAY
> A STRANGER RECEIVES IT**, and it earned that on its first run. `--verify`
> unpacks into a temp directory with no relationship to this tree and runs the
> smoke against THOSE bytes.
>
> | What it caught, immediately | |
> | --- | --- |
> | **A check that was green for the wrong reason** | `paths.key_file_candidates` falls through to *"the source tree's own keystore, which exists on this machine only"*. The bundle lives in `dist/`, **inside the repo** — so it silently inherited the developer's key and `a run completes` passed. Unpacked elsewhere it correctly refused, and the check went red |
> | **The fix** | Every smoke child now pins `HATO_KEYFILE` at an absent path, so it behaves like a stranger's machine wherever the bundle sits. ⭐ The one check became TWO: *no key → refuses with an instruction and no traceback* (a downloader's first experience) and *with a stand-in key → exit 0* |
> | **My own packager crashed printing `⛔`** | cp1252 console. ⛔ Worse than cosmetic: the one message that mattered — *"the unpacked copy failed its smoke test, do not publish this"* — became a traceback about character encoding. Streams now reconfigure to UTF-8 with `errors="replace"` |
>
> ⭐ **Final: 16 checks, 0 failed, on the UNPACKED copy.** ⛔ **No secret in the
> artifact** — all 265 entries audited; the only `key` matches are Cryptodome's
> `PublicKey` module and two package-metadata `top_level.txt` files.
>
> ```
> python packaging/package_standalone.py --to "<somewhere>"
> ```
>
> ▶ **Still open:** a tagged GitHub release (Sonic's go, IRREVERSIBLE) and the
> run-at-startup option, which now has an exe to register.

**surfaces:** `delivery`
**depends on:** 7c, 7f

⭐ **tsubasa already solved the freeze and its tooling is the template** —
`WorldDominationLite/tsubasa-git/packaging/`: `tsubasa.spec`, `package_standalone.py`,
`smoke_standalone.py`, `make_icon.py`. A zip with no Python in it.

| | |
| --- | --- |
| **Prove** | Build it, then run the **published bytes** on this machine: the window opens, a run completes, the tray watcher starts |
| **Test** | A smoke script that drives the frozen artifact, not the source tree |
| **Expected** | ⚠ `PYTHONIOENCODING` **does nothing to a frozen child** — measured on tsubasa; the bootloader runs Python isolated. The parent's `errors="replace"` is what keeps the window alive |

---

## Step 7h — Startup, open-video, and the README — ✅ DONE 2026-09-18

**surfaces:** `ui`, `logic`
**depends on:** 7e, 7g

> Four things Sonic asked for once the exe existed and he could actually hold it.
>
> ⭐ **1 · START WITH WINDOWS.** `hato/startup.py` + a switch in Settings →
> *When it runs*. Suite `startup`, **12 checks**, registered in
> `hato.config.json`. Two rulings inside it:
>
> | | |
> | --- | --- |
> | **It registers the TRAY WATCHER, not the window** | Starting with the computer is about hato working while nobody is looking. A window at every login is the opposite of a background tool |
> | 🚨 **THE REGISTRY IS THE ONLY STATE — there is no config key** | A `start_with_windows = true` would be a second answer to a question Windows already answers, and they drift the moment anybody edits startup items in Task Manager, leaving the switch ON while nothing runs |
>
> 🚨 **AND MEASURING FIRST CHANGED THE IMPLEMENTATION.** `hato` is **not
> installed as a distribution** — `import hato` raises `ModuleNotFoundError`
> from any directory but its own. ⛔ So `pythonw -m hato.watch` in a Run key
> would have failed at every boot **and failed invisibly**, because `pythonw`
> has no console to print the traceback to. Hence **`hato-watch.pyw`** at the
> repository root: a script's own folder goes on `sys.path`. Verified by
> running it from `/tmp`. Frozen installs register `hato-watch.exe` instead.
> ⚠ The control VANISHES off Windows, per the standing rule.
>
> ⭐ **2 · OPEN THE VIDEO FROM A ROW.** A quiet `#openvid` button inside the
> panel a click already opens. ⛔ **Additive on purpose** — the row's click
> means *expand*, and a double-click would be a second invisible meaning
> nobody discovers and everybody triggers by accident.
>
> 🚨 **ITS FIRST CHECK WAS DEFECTIVE AND A MUTANT SURVIVED IT.** The check
> asserted only that a button EXISTED with a receiver — and `output_path` is
> truthy too, so swapping the video for the subtitle still produced a button.
> The helper's own check drove `open_in_player` directly and never went
> through the panel, so **the seam between them was the one thing untested.**
> The check now drives the click and compares paths; re-breaking it fails
> naming `ep01.ja.ass` where `ep01.mkv` belongs. **Mutant M7c-48.**
>
> ⭐ **3 · NO UNDERLINED LINKS**, and *Send feedback* / *Star on GitHub* on the
> tab line. `theme.LINK_CSS` is the one anchor style all four links share.
> ⛔ A link needs BOTH halves — the palette carries the colour (Qt ignores a
> stylesheet rule for it) and the anchor style carries the decoration, which
> no palette role can express. Verified on all four anchors, not just the two
> that were asked about.
>
> ⭐ **4 · THE README REWRITTEN.** Logo, four screenshots doing the explaining,
> and the CLI block moved into a collapsed section as an EXAMPLE rather than
> the opening. Sonic: *"That's at the top and too technical for the top."*
> ⚠ `gui-shots/shoot.py` regenerated all 13 shots first, so what the README
> shows is the build it ships with — and the alt text's claims were checked
> against the images rather than assumed.

---

## ⭐ LAYER 8 — NEEDS YOU PERSISTS, AND EVERY WAIT SAYS SO. Added 2026-09-22

> **Specified by Sonic in `HANDOFF.md` §4 (2026-09-22) and governed by one FROZEN rule,
> now in `workflows/build-ui.md` §*Standing Rules*:** *when the app decides something on a
> person's behalf, the decision needs a surface — say it was handled, say when it resolves,
> and keep the manual choice one click away.*
>
> 🚨 **PART 1 DEFECT, recorded: §4 had no runbook steps.** These are them. ⚠ **Layer 8 is
> edits to a SHIPPED app**, so unlike Layers 1–7 almost every step changes an existing
> file. The orchestrator makes those edits serially; a builder is dispatched only for a
> step that is a new module (8c) or a read-only investigation (8k).
>
> ⭐ **MEASURED BEFORE ANY CODE (2026-09-22, `--dry-run --json` + a read-only DB probe +
> a two-arm pick probe on a real pair).** Five things beyond §4, each with its evidence:
>
> | # | Found | Evidence |
> | --- | --- | --- |
> | D1 | 🚨 **`--dry-run` overwrites the window's memory.** `commands/run.py` calls `lastrun.save` for every run, dry or not, and the window paints a PLANNED row as *"something went wrong"* | The handoff's own first command did it: `last-run.json` saved 18:35:42, 68 rows, `dry_run: true` |
> | D2 | 🚨 **The title bar's *"runs automatically at 03:00"* switch registers nothing.** `config.py` says so itself (*"Registering a real Windows scheduled task is still unbuilt"*); no task named hato exists | Not one of 148 recorded attempts is near 03:00 local. The retry that *"fetched unprompted"* on 09-21 00:05 was a run someone else triggered — a new download reaching the tray. ✅ **BUILT as 8y, 2026-09-23 — Sonic ruled *"yes to the run automatically"*** |
> | D3 | ⛔ **"Try 3 more candidates" cannot try anything for 24 hours.** It runs the video's folder without `--force`, and every REFUSED row has just recorded a soft negative, so the gate answers SKIPPED/negative | `pipeline.py:965` — the same line as 4a's second cause |
> | D4 | ⛔ **After the retry window, an episode whose offered candidates were all refused comes back REFUSED with ZERO attempts** — `_all_refused(already=True)` passes `()` — so the pick row it produces has nothing to pick | `pipeline.py:1354` |
> | D5 | 🚨 **The window never loads the blacklist.** `state.blacklist` starts `[]` and is only ever filtered; the card, its count and the stale-row sweep are fed by test fixtures alone | `app.py:333` — no loader anywhere |
> | D6 | 🚨 **A manual pick of a shown candidate cannot succeed, and the window says it did.** Every card on *Needs you* is a candidate the timing check already refused; `hato sync` runs the SAME deterministic check. `commit_pair` paints *"paired · <name>"* in green without reading the child | Two arms, real pair (Tsuihou 12 + NanakoRaws E12, write=False, results=False): **no force → REFUSED, 70%, same reason as the DB row**; tsubasa `force=True` → *"WRITTEN UNDER --force. The pairing was accepted; the alignment was NOT"* |
> | D7 | 🚨 **Every manual pick ever made died on a usage error.** The window ran `hato sync <video> <sub> --json`, and `sync` had no `--json`: exit 2, nothing written — under a row already painted *paired* | The child's own stderr, read for the first time in 8e |
> | D8 | 🚨 **The RELEASED 1.0.1 exe cannot scan a folder holding a name only guessit can read.** tsubasa asks guessit about a Western-style name its own parsers cannot number; guessit imports babelfish, which reads `data/iso-3166-1.txt` at import, and PyInstaller 6.18 has no hook for any of the three — code in the archive, data not. `parse_guessit` guards only `ImportError`, so the **whole folder** fails: *"none of the 1 folder(s) given could be scanned (FileNotFoundError …)"*. ⚠ The likely cause of 4f's *"network drive: FAILED"* — unproven without Sonic's message | Two arms × two builds on the released bytes: `The.Show.Special.1080p.WEB.x264-GRP.mkv` → **exit 1**; an anime name → exit 0; source mode → exit 0 both. The `_internal/` of 1.0.1 has no `babelfish/`, `guessit/` or `rebulk/` at all |
> | D9 | ⚠ **A mapped drive and its UNC path are two strings.** `Z:\Anime` and `\\nas\share\Anime` name one folder, and `under_any` compares spellings — a skip folder written one way does not cover a video found the other | Read from source during 4f's investigation. **Deferred** (below) — not a reproduction |
> | D10 | 🚨 **A real row's season is printed as a bare number.** The wire carries tsubasa's INT; every window fixture carried the STRING `"S2"`. Real runs showed *"2 · 3 added"* beside a show and *"· 4"* after a filename, which reads as a count | The first shot seeded with `hato problems`'s real rows (L8-14) |
> | D11 | 🚨 **The fit SLIDES a release that is behind the folder.** It takes the offset where most videos land, so S04E01–22 against videos 21–23 lands three at −1 and two at the true 0. Timing refuses every file it then offers (the safety net holds) — but an airing episode reaches *Needs you* as a pick of OTHER episodes' files, and `max − offset` of that placement says it is on offer | Sonic's own Iruma-kun S4 23 (2026-09-20) was offered **E22, E20 and E03** — the fit's anchors, exactly. Reproduced on the real `episodes.align` (`test_sonics_iruma_s4_23_…`, whose control asserts the slide) |
>
> ⛔ **Do not redo:** the 24-hour retry (`state.py` `SOFT_DAYS`), `paths.under_any`, and
> the state key surviving a move (`cache.py` `video_hash`). ⛔ **`last-run.json` stays a
> SNAPSHOT** — a 3 a.m. run overwriting it is a feature; persistence comes from a view over
> the state DB.

> ## ✅ LAYER 8 BUILT, 2026-09-22 — every step, its proof, its mutants
>
> | Step | Status | The proof that was RUN | Mutants |
> | --- | --- | --- | --- |
> | 8a | ✅ | a dry run leaves `last-run.json` byte-identical; `--only` leaves it too; the loader reads 1.0.1's dry snapshot as no memory | M8a 4/4 |
> | 8b | ✅ | ⭐ **the RELEASED 1.0.1 exe read a migrated copy of Sonic's DB exactly as an untouched one** (148 rows, persistent, nothing set aside) — `state --stat --json`, both arms | M8b 11/11 |
> | 8c | ✅ | `hato problems` over a copy of Sonic's DB: **2 open** (Iruma-kun S4 23, Slime S4 23), 2.1 s; the other refusals in his history were found on retries 09-21 — checked row by row | M8c 31/31 |
> | 8d | ✅ | run 1 refuses → run 2 inside the window carries all of them, with rates and files | M8d 6/6 |
> | 8e | ✅ | the window, shot at every state (L8-01…16) and LOOKED at; D6 leans *use it anyway* (`PICK_OVERRIDES_TIMING`, a ruling); D7 closed (`hato sync --json`) | M8e 33/33 |
> | 8f | ✅ **amended** | Sonic's own shapes: Iruma 23 and Honzuki 22 highlight, Tsuihou 12 and Tetsunabe 09 do not — on the real alignment | M8f 27/27 |
> | 8g | ✅ **amended** | the dry count over copies of Sonic's two stores: 60 videos, 148 tries, 14 shows; a second dry count left both byte-identical | M8g 20/20 |
> | 8h | ✅ | a fake clock: a date passes → one run; never twice; a date already due at start is the catch-up run's; dates seconds apart are one run | M8h 14/14 |
> | 8j | ✅ in 8e | *Try 3 more* is `--retry-now --only <video> --candidates 3` (D3) | M8e-17 |
> | 8k | ✅ **measured** | → D8, above: a real defect in the released bytes, fixed in `packaging/hato.spec` and proven on NEW bytes — smoke **23/23** on the zip unpacked outside the repo, including *"a name only guessit reads is scanned"* | — |
> | S01 · S02 | ✅ | ADVERSARY-2026-09-18's two deferred silent losses, closed: the tray waits for a held lock instead of spawning into it; the settings are re-read on the tick and the watchers follow | M8s 12/12 |
> | **8y** | ✅ **2026-09-23** | ⭐ **D2 — the 03:00 switch registers a REAL task.** A real trigger fired the real chain (`pythonw hato-watch.pyw --scheduled` → hato hidden) against an isolated store: cwd `C:\Windows\system32`, exit 0, one log block, 0 API calls — and, two-arm, **no console window**, where a console program started the same way got one. The real schtasks kept the battery settings (a suite check, under its own task name). Every state shot and LOOKED at (L8-17…21) — which caught two defects: *"next run in 4 hours"* beside an OFF switch (a fixture-only field), and *"(Access is denied.)."* · ⚠ and the full runner HUNG on a pre-existing race in `runlock.release()` (a delete refused while a waiter reads the lock), found, proven two-arm and fixed · and the returning-client shot over a copy of Sonic's store caught *"0 videos"* on every real window's title (a fixture-only field; the class swept) and a run's NOTE cut at the window edge mid-path (Qt does not wrap a label unless told to; the class swept — four lines now wrap) | **M8y 82/82** — 4 older mutants re-aimed where D2 moved their code (M8e-12/13, M8zt-44, M8zw-33) |
>
> 🚨 **PART 1 DEFECTS, recorded where they were found:**
>
> - **8f's formula could not have worked.** *"max(episodes) − offset"* reads a placement,
>   and D11 slides the placement exactly when the episode is late. Built instead
>   (`episodes.newest_offered`): a release in the video's own season is read at its own
>   number (a same-season release cannot number an episode LOWER, so a negative placement is
>   the slide; one positive offset is a release numbering on through the season); another
>   numbering counts at ONE offset; a guess, or a release placed nowhere, counts for nothing.
>   And 4c asked for a BUTTON, which the step never named: **Wait for it** on every pick,
>   highlighted only one past the newest, putting the row away until its own retry date
>   (`window-waits.json`, kept by the window; a new date or the date passing brings it back).
> - **8g, dry by default.** `doctrine/robustness` §destructive: `hato state --clear` only
>   COUNTS; `--yes` clears. ⛔ And the dry count takes **no run lock** — the window asks for it
>   to draw its card, and a lock taken for that made a tray run starting at the same moment
>   scan nothing.
> - **8h's file** is `retries-due.json` (the run writes the state DB's future retry dates;
>   the tray reads them through `hato.retries`, stdlib only). Dates seconds apart coalesce
>   into one run — a run fired between two finds the second still waiting.
>
> ⏸ **Deferred, with the reason:** D9 (no reproduction; the fix is a canonical-path compare
> that must not break `under_any`'s measured prefix rules) · D11's cause in the fit itself
> (the matcher is the load-bearing core; 8f says what it does rather than changing it —
> **a ruling for Sonic**, with a lean in `HANDOFF.md`).
>
> ## ✅ 8z — THE ADVERSARIAL PASS: RUN AND CLOSED 2026-09-22/23
>
> Three fresh agents, one per surface (window · data · tray and packaging), each working
> in its own `%TEMP%` copy. **79 findings reproduced, 11 suspected, and 32 checks shown to
> pass for the wrong reason** — after every step above was ticked, with its mutants killed.
> ⭐ **Every 🚨 finding sat at a SEAM between two halves that were each green:** a run's
> copy of a row against memory's copy (A5 — one click wrote the wrong episode's file), an
> exit code's meaning (A12), the run's language against the stored one (F1), the entry that
> was escalated to against the one that was recorded (F13), the window against an OLDER tray
> (V1), and the retry file rewritten by a run that holds the lock across a due date (R1).
>
> ▶ **`ADVERSARY-2026-09-22.md` is the register: 94 fixed · 6 dropped · 4 deferred**, every
> `fixed` row naming the check that catches it and the mutants that prove the check can
> fail. Three builders wrote one mutant list per surface (`m8zw` 72 · `m8zd` 56 · `m8zt`
> 59 — **187, every one killed**) and put every fix back; 31 older mutants whose code the
> fixes had moved were re-aimed.
>
> 🚨 **Putting the fixes back found 30 pieces of them no check could see** — each survived
> every check near it until one was written for it. ⭐ The builders found them with GAP
> PROBES: a candidate mutation run against whole suite files, expected to survive; one
> that does is a piece of a fix nothing would miss.
>
> 🚨 **And the fix pass found these, all recorded there:** F4e — a whole-show release read
> as the gap between two counts, which produced the rule *season 1 and the absolute count
> are one count; between the absolute count and a later season the offset is never 0 and
> runs one way* (and whose first fix, reasoned rather than measured, broke Sonic's own
> Tsuihou 12) · P1 — the D1 fix tripped the dependency-truth check, correctly · H1 — a
> witness that SKIPS in the mutation copy (no ffmpeg there) reads as a survivor · and the
> window's merge ordering rows by `time.monotonic()`, which ties on Windows.
>
> **Proof, as run:** the rebuilt exe's smoke **26/26** on the zip unpacked outside the repo,
> including the two new checks — 5d (each parser numbers a name inside the frozen build,
> two-arm: it fails in guessit's own words with babelfish's data removed from a copy) and 9
> (the notice names all **37** packages the bytes carry) · ⭐ **the full mutation gate, 2026-09-23:
> 766 mutants, 762 killed in the run (80 min); the 4 it reported were stale mutants in OLDER
> lists, each fixed and re-run killed against the current tree (`GATE-1…4` in the register) —
> 766/766** · the full runner: see `CONTEXT.md`'s Stage line · the Layer 8 reshoot, LOOKED at.

### Step 8a — A dry run writes nothing

**surfaces:** `data` `ui`
**depends on:** 7i (the run writes `last-run.json`)

| | |
| --- | --- |
| **Build** | `commands/run.py` skips `lastrun.save` on `--dry-run` · the window's loader treats a snapshot whose summary says `dry_run` as no rows (the file already on Sonic's disk is one, and 1.0.1 still writes them) |
| **Prove** | `hato <folder> --dry-run --json` leaves `last-run.json` byte-identical, mtime unchanged; a real run over the same fixture rewrites it |
| **Test** | both directions, through `cli.main` · the window loading a dry-run snapshot shows no rows and says nothing false |
| **Expected** | ⛔ `--dry-run`'s help says *"write nothing"*, and now it is true |

### Step 8b — The record keeps what a pick needs

**surfaces:** `data`
**depends on:** 1b

| | |
| --- | --- |
| **Build** | `attempts.subtitle_hash` — the column `02-data-model.md` specifies and nothing ever filled — gets the downloaded candidate's content hash · a new nullable `match_rate` · a new nullable `newest_offered` (8f) · `Cache.find(digest, name)` and a size-checked name lookup for rows written before this step |
| **Prove** | a refusal recorded now round-trips to the cached file and its rate; Sonic's real DB opens unchanged under the frozen 1.0.1 exe's reader (additive columns, **no version bump**) |
| **Test** | an old-shape v2 DB gains the columns on open and keeps every row · an INSERT naming only the old columns still works (that is what 1.0.1 does) · a legacy row finds its blob by name and size, and refuses a same-name blob of another size |
| **Expected** | ⛔ No `SCHEMA_VERSION` bump: a v3 file would make the running 1.0.1 exe fall back to an in-memory DB and repeat every download |

### Step 8c — The open-problems view

**surfaces:** `data` `logic`
**depends on:** 8b

| | |
| --- | --- |
| **Build** | `StateDB.problems(lang)` — per video, its latest state and every candidate tried since its last success, blacklist excluded · `hato/problems.py` filters that by the DISK (the video exists, is under a configured folder and not a skipped one, and has no subtitle present) and shapes each as a `{"type": "video"}` row · `hato problems [--json]` |
| **Prove** | against a copy of a fixture DB: a refused episode, a waiting one and a resolved one → exactly the first two, each with its candidates and when it is next looked at |
| **Test** | each kind · a subtitle appearing removes the row with no DB write · blacklisted, outside-the-folders and missing videos are excluded · legacy rows · ⛔ zero network |
| **Expected** | ⛔ The DB still only PREVENTS work; this is a read. The disk decides what is resolved |

### Step 8d — The gate keeps the candidates

**surfaces:** `logic`
**depends on:** 8b

| | |
| --- | --- |
| **Build** | Every problem outcome carries `tried_before` — the candidates tried in EARLIER runs, from the DB, with their local file: the negative skip (`pipeline.py:965`), `_all_refused(already=True)` (D4), a fresh REFUSED, and a CONFIDENT that follows earlier refusals (*"found on a retry"*). `attempts` keeps meaning *this run* |
| **Prove** | run 1 refuses 3 → run 2 inside the window: the SKIPPED/negative row carries all 3 with their rates and paths |
| **Test** | each of the four shapes · ⛔ nothing is downloaded or requested to build `tried_before` |
| **Expected** | ⛔ The outcome words do not change. A skip is still a skip; it now says what it is waiting on |

### Step 8e — Needs you persists, and says when

**surfaces:** `ui`
**depends on:** 8c, 8d

| | |
| --- | --- |
| **Build** | The window merges `hato problems --json` with the run's rows into ONE Needs-you list (a pure function in `gui/run.py`) · a row reads *"retrying in 14h"* / *"retry due — next run"* · the pick uses every candidate ever tried and **reads the child's verdict** before it says *paired* (D6) · *Look again now* on a row (`--retry-now --only <video>`, D3) · Settings says the interval · a success after refusals says it was found on a retry · the blacklist card loads the real blacklist (D5) |
| **Prove** | the real window over a lab: refuse → reopen → re-run inside the window → the row is still there, with its candidates and its countdown. LOOK at every state |
| **Test** | the merge, both ways · a refused pick leaves the row asking · every new control is wired · ⛔ the word *refused* never reaches a person |
| **Expected** | ⭐ The ruled design, extended, not redesigned |

### Step 8f — *Probably not out yet*

**surfaces:** `logic` `ui`
**depends on:** 8d, 8e

| | |
| --- | --- |
| **Build** | At a NOT_FOUND or all-refused ending the pipeline records `newest_offered` — the newest episode any PLACED release offers, in the video's own numbering (per release: `max(episodes) - offset`). The window highlights *wait for it* only when the video's episode is exactly one higher |
| **Prove** | Sonic's own history: Iruma-kun S4 23 (newest offered E22) and Honzuki S4 22 (newest E21) highlight; Tsuihou 12 and Tetsunabe 09 do not |
| **Test** | seasonal and absolute releases in one entry (06 §2) · a release placed nowhere counts for nothing · the unhighlighted case still offers the button |

### Step 8g — Clear hato's memory

**surfaces:** `data` `ui`
**depends on:** 8c

| | |
| --- | --- |
| **Build** | `hato state --clear [--blacklist]` under the run lock: attempts, retries and remembered shows; the blacklist only when asked · Settings: a card that names what goes and what stays, and a themed confirm |
| **Test** | refused while a run holds the lock · counts reported · the blacklist survives unless named · ⛔ no subtitle, kept original, setting or key is touched |

### Step 8h — The retry actually happens

**surfaces:** `delivery` (a resident process)
**depends on:** 8c

| | |
| --- | --- |
| **Build** | Every real run writes the next due retry to a small file; the tray watcher wakes at it and runs · the window's countdown is honest about what will run it (tray on → *"in 14h"*; off → *"the next time hato runs"*) |
| **Test** | a fake clock: due passes → one run; not twice for the same due; a due in the past at start is covered by the catch-up run · ⛔ the watcher still imports neither a toolkit nor the pipeline |

### Step 8j — Try harder works (4e) · Step 8k — Network drive (4f): measure first

8j is 8e's *Look again now* with a larger cap. 8k is a read-only investigation (a builder,
isolated store); **no code until it has a failure message.**

### Step 8y — D2: the 03:00 switch registers a real task

**surfaces:** `ui` `delivery` · shelling out
**depends on:** 7e, 7f, 7h (`startup.py` is the model)

| | |
| --- | --- |
| **Build** | `hato/schedule.py` — ⛔ **Task Scheduler is the only state** (no config key; `schedule` is only the time). Registered from hato's own XML with the battery settings written out; the start never already past; READ BACK after every write · `watch.py --scheduled` — the windowless program the task starts, which runs hato hidden with `--wait` and hands back its exit code (logged when not 0) · the window: the switch read from the task on open, asking Windows on a click, the time field re-registering, a note beside it when the task is off or changed in Task Scheduler or refused, *"next run in 22h"* derived, the retry sentences naming the daily run, and no switch where nothing can schedule |
| **Prove** | 🚨 **One real scheduled execution, its log read** (`10-deployment.md`) — and two-arm: the real chain shows no console window where a console program does |
| **Test** | `test_schedule.py` over **recorded** schtasks output (the SID and machine name scrubbed), a fake schtasks that prints back in the console's code page, and ONE real-scheduler check under its own name · `test_gui_widgets.py` §D2 · ⛔ the suite runs with `HATO_NO_SCHEDULER=1` (`conftest.py`) |
| **Expected** | ⛔ Nothing in the suite, the smoke or the build registers the person's own `hato` task — **turning it on is theirs to do** |

🚨 **PART 1 DEFECT, recorded: `05-interface.md` specified this switch — *"registers or
removes the Windows scheduled task, and says when it next runs"* — and no step ever built
it.** 7e built the time field and the config value; nothing owned the task. It shipped in
1.0.0 and 1.0.1 as a switch that could not be turned off and turned nothing on.

---

## Step 6 — Release — ✅ TAGGED AND SHIPPED: `v1.0.1`, 2026-09-19. ⛔ NO PyPI, RULED

> ⭐ **`v1.0.1` IS LIVE AND EVERY GATE IS GREEN** — `tests` 13/13, `release` 2/2 with the
> stamp gate passing for the first time, suite 27 suites / 1616 checks, smoke 20/20
> against the copy unpacked outside the repo, and the **published asset downloaded and
> hash-verified** against the local artifact. Tag `3114321`.
>
> ▶ **The sequence, the traps and the two cuts of 1.0.1 are in `spec/10-deployment.md`
> §*RELEASED* and `LEDGER.md` §delivery.** ⛔ Do not restate them here; the block below
> is the *wheel/audit* half, which is parked.
>
> ⚠ **The line below saying a tagged release "waits for the GUI" is SATISFIED** — the
> window shipped at 7c–7h and the release followed. Kept for the record of the gate.

> ✅ **`github.com/SonicSandbox/hato` — first commit `15f06c6`, 123 files, 41,391 lines.**
> Pushed by the orchestrator on Sonic's go, after: the deploy key verified against the repo
> by `ssh -T` (⛔ with `IdentitiesOnly=yes` — `~/.ssh`'s default key belongs to another
> project), the remote confirmed **empty** so the first push was exactly the reviewed tree,
> the full runner green at **22 suites / 1258 checks**, and the staged tree audited: no
> strays, and `key_bytes_absent` proven over 141 files in 5 encodings.
>
> 🚨 **RULED BY SONIC, 2026-09-17 — NO PyPI AND NO pip ROUTE.** *"we don't need the pypi…
> it's mainly just a github usage that will need the gui for an actual github release"* and
> *"hato is more of a standalone than tsubasa is, in the sense that tsubasa is implemented
> into other codebases."* **tsubasa is EMBEDDED; hato is RUN.** The delivery shape and what
> is parked rather than deleted are in `10-deployment.md` §*RULED*.
> ⛔ `release.yml` has **no publish job at all** — no token, no `id-token: write`, no `pypi`
> environment. Structurally absent, not gated by an `if:`.
>
> ▶ **A tagged GitHub release waits for the GUI**, which is Sonic's named precondition.
>
> ⚠ **THE FIRST CI RUN WAS RED ON ALL 12 MATRIX JOBS, AND EVERY CAUSE WAS PORTABILITY** —
> read before assuming the suite travels. Diagnosed with **no `gh` and no token**, through
> the `::error::` annotation channel, which is the one of five that works anonymously (P14).
>
> | Cause | Fix |
> | --- | --- |
> | **ffmpeg** — 18 of 22 failures per job. `tests/_media.py` resolved the vault's bundled copy through `media.ffmpegRelative`, correct in the vault and meaningless on a runner (`D:\a\hato\media-kit\…`) | `ffmpeg()` now tries the configured path → ⛔ **raises IN the vault, never skips** (it is bundled there and deliberately off PATH, so a skip would retire the only real-engine check) → PATH outside it → skip last. Verified: the vault still runs them, **zero skips** |
> | **`ModuleNotFoundError: py7zr`** — a whole test module could not import | ⚠ **A SEAM DEFECT between two parallel builders.** `ci.yml` said "no extra can be named" from the spec's dependency list while the packaging builder was concurrently making them `[project.optional-dependencies] archives`. Both right alone; nobody owned the boundary. Now `pip install -e ".[archives]"` |
> | **The Python register refused 3.11–3.13** | ⭐ **The check working.** Recorded in `PROVEN_PYTHONS` with the run id, stating it proves *the suite executed* — ⛔ **not** that hato works there. Classifiers stay at 3.10 until a green run |
> | **`audit-wheel: launcher`** — the wheel job | ⭐ **The claim was asserting a spec line the ruling retired.** `hato-run.cmd` "ships inside the wheel" was never implementable (`package-data` cannot reach the repo root, and moving it breaks the launcher's own PYTHONPATH guard). **Inverted**: it now asserts the launcher is AT the root, where clone-and-run needs it. Both directions pinned |

**surfaces:** `delivery`

⚠ **Read `doctrine/release` before running this block. PIPE NOTHING inside it.**

> ⛔ **THIS BLOCK NO LONGER PUBLISHES ANYTHING — it builds and AUDITS.** Kept, and worth
> running, because every claim below is about the artifact and two of them are about the
> tree: `scan-secrets` answers *"is the key anywhere in what I am about to make public"*,
> which matters for every push whether or not a wheel is ever uploaded.
>
> ⚠ **`python -m build` is NOT installed on this machine, and must not be** (pitfall P24 —
> the build frontend is not part of Python). Put it in a **throwaway venv** and build from
> there; test the wheel in a **second, clean** venv. Measured 2026-09-17: that is how the
> local wheel was built to reproduce CI's `audit-wheel` failure.
>
> ⚠ **`stamp` is for a released version number.** Skipping it leaves `audit-wheel`'s
> `version_matches_stamp` as a **SKIP, not a pass** — correct while nothing is released, and
> a real gap the moment something is.

```bash
# 1. stamp — a CONTENT HASH, never a timestamp, never hand-bumped
#    ⛔ only when a version is actually being released
python -m hato.dev stamp --release X.Y.Z

# 2. build both artifacts — from a THROWAWAY venv, never the system interpreter
python -m build

# 3. audit the wheel's manifest
python -m hato.dev audit-wheel dist/hato-*.whl
```

**Then prove it — four separate claims:**

```bash
# no secret anywhere in the artifact
python -m hato.dev scan-secrets dist/

# no third-party subtitle CONTENT in the artifact (fixtures are metadata; bodies are not ours)
python -m hato.dev scan-content dist/

# a clean-venv install runs, with no Rust toolchain and no unrar present
python -m hato.dev verify-install --no-unrar

# the installed version equals the stamped one -- a SEPARATE check
hato --version
```

⚠ **The licence notices for `anitopy` (MPL-2.0) and `guessit` (LGPL-3.0) ship with the
artifact.** Both require it.
