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
  ├── 8y  ✅ D2 — the 03:00 switch registers a REAL task (hato/schedule.py)
  └── 8z  ✅ THE ADVERSARIAL PASS — run and CLOSED: ADVERSARY-2026-09-22.md
           79 reproduced + 11 suspected + 32 wrong-reason checks → every row
           fixed (naming its check AND its mutant) / dropped / deferred.
           ✅ RELEASED — all of Layer 8 is in v1.0.2, 2026-09-23 (Step 6)

LAYER 9 — WHICH FORMAT, AND WHAT COUNTS AS ALREADY THERE. Added 2026-09-23
  ├── 9a  ✅ Prefer .ass or .srt; the other kind only if asked        M9a 25/25
  ├── 9b  ✅ An untagged subtitle named for the video is read first   M9b 16/16
  ├── 9c  ✅ tsubasa 0.1.8 RELEASED 2026-09-23: `.jp` reads as Japanese  M9c 2/2
  └── 9z  ✅ THE ADVERSARIAL PASS — ADVERSARY-2026-09-23.md: 22 fixed · 5 dropped ·
           2 deferred; m9za 48 + m9zb 3 + 14 re-aimed, all killed. Closed on 9a;
           ⚠ PARTIAL on 9b + 9c (that agent was stopped before it reported)
           ✅ RELEASED as hato v1.0.3, tag 59a1561, 2026-09-23 (Step 6)

LAYER 10 — D12: RUN NOW CLOSED THE WINDOW (1.0.2, 1.0.3). Added 2026-09-24
  ├── 10a ✅ Run now runs — wired through `lambda _checked=False`; a real click in the
           suite, the CLASS read off the source, and the smoke PRESSES it (6b)
           M10a 3/3 · ✅ RELEASED in v1.0.4
  └── 10b ✅ an error inside the window is written to hato.log and the window stays
           (RULED 2026-09-24: in the next release) · M10b 12/12

LAYER 11 — AUTO-UPDATE. RULED 2026-09-24 (gui-mock/mock-update.html, mechanism A)
  ├── 11a ✅ the release contract: the signed manifest        M11a 13/13
  ├── 11b ✅ the check                                        M11b 14/14
  ├── 11c ✅ staging, while hato runs                         M11c 14/14
  ├── 11d ✅ the swapper + the hand-off                       M11d 42/42
  ├── 11e ✅ the native splash, measured against Chrome's render of the mock   M11e 31/31
  ├── 11f ✅ the window: pill · card · progress · banners · Settings → Updates   M11f 35/35
  ├── 11g ✅ the tray and the 03:00 run install while nothing is open   M11g 24/24
  ├── 11h ✅ the fourth exe, the smoke's REHEARSAL (+ the frozen splash), verify-release   M11h 12/12
  └── 11z ✅ the adversarial pass -- ADVERSARY-2026-09-24.md: 27 fixed · 0 dropped ·
           3 deferred; m11z 58 + 16 older re-aimed · THE GATE 245: 243 killed,
           2 survived -> both closed (G1, G2)
           ✅ RELEASED as hato v1.0.4, tag 41e1515, 2026-09-24 (Step 6) -- the first
           release that updates itself

LAYER 12 — UPDATES YOU CAN SEE. RULED 2026-09-24 (Sonic: "Go do all of your leans")
  ├── 12a ✅ an open window sees what the tray downloaded; Check now never downloads
  │         what is already on disk
  ├── 12b ✅ an open window keeps checking once a day; "checked 12 min ago" moves
  ├── 12c ✅ Check now shows it did something: the button stays (disabled), then
  │         "✓ you have the newest"
  ├── 12d ✅ the version in the footer, one click from Settings → Updates
  ├── 12e ✅ a rate-limited check says GitHub asked hato to wait
  ├── 12f ✅ What's new for the version you have
  └── 12z ✅ the adversarial pass -- ADVERSARY-2026-09-24.md §Layer 12: 21 fixed ·
           0 dropped · 1 deferred; m12 62 + 10 re-aimed · THE GATE 303/303 killed
           ✅ RELEASED as hato v1.0.5 (Step 6) -- the first release an install takes
           by itself

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
> | **8y** | ✅ **2026-09-23** | ⭐ **D2 — the 03:00 switch registers a REAL task.** A real trigger fired the real chain (`pythonw hato-watch.pyw --scheduled` → hato hidden) against an isolated store: cwd `C:\Windows\system32`, exit 0, one log block, 0 API calls — and, two-arm, **no console window**, where a console program started the same way got one. The real schtasks kept the battery settings (a suite check, under its own task name). Every state shot and LOOKED at (L8-17…21) — which caught two defects: *"next run in 4 hours"* beside an OFF switch (a fixture-only field), and *"(Access is denied.)."* · ⚠ and the full runner HUNG on a pre-existing race in `runlock.release()` (a delete refused while a waiter reads the lock), found, proven two-arm and fixed · and the returning-client shot over a copy of Sonic's store caught *"0 videos"* on every real window's title (a fixture-only field; the class swept) and a run's NOTE cut at the window edge mid-path (Qt does not wrap a label unless told to; the class swept — four lines now wrap) | **M8y 83/83** — 4 older mutants re-aimed where D2 moved their code (M8e-12/13, M8zt-44, M8zw-33) |
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

## ⭐ LAYER 9 — WHICH FORMAT, AND WHAT COUNTS AS ALREADY THERE. Added 2026-09-23

> **From a second user's report on 1.0.2**, ruled by Sonic the same day: *"it gets .ass
> instead of .srt subs, .srt would be preferred if possible"* · *"It also got subtitles for
> stuff that already had subtitles. Even though the subs were named after the video, was
> made specifically for that video, and had perfect sync already."*
>
> ⭐ **MEASURED BEFORE ANY CODE** — tsubasa 0.1.7 (what 1.0.2 bundles), through
> `parse_subtitle_name` AND `scan(...).unpaired(lang="ja")`, each name beside `Show - 01.mkv`:
>
> | Name | Read as |
> | --- | --- |
> | `.ja` · `.jpn` · `.ja-JP` · `.ja[cc]` · `.Japanese` / `.japanese` / `.JAPANESE` | Japanese → **skipped** |
> | `.srt` / `.ass` with no language · `.jp` · `.JP` · `.jap` · `.und` · `.en` | not Japanese → **fetched beside it** |
>
> 🚨 **PART 1 DRIFT, recorded:** `06-edge-cases.md` §6 and `present.py`'s docstring still
> called `.Japanese.` a tsubasa defect. tsubasa 0.1.5 fixed it, and
> `test_existing.py::test_the_jellyfin_display_name_is_read_as_japanese` has asserted the
> fix since 2026-09-17. ⚠ It was repeated to Sonic as current on 2026-09-23 — from the
> spec note, not a measurement — and corrected the same hour.

### Step 9a — Prefer .ass or .srt; the other kind only if asked

**surfaces:** `data` `logic` `ui`
**Ruling (Sonic, 2026-09-23, verbatim):** *"i want setting that asks for preference between
the two, but OFF by default is download if the other type doesn't exist. In other words,
even if you prefer one, if it isn't checked, then it won't download the other kind. ie if
prefer .ass, and there is an srt but the toggle is off, it won't download"*

| | |
| --- | --- |
| **Build** | `config.py`: `prefer_format` (`ass` \| `srt`, default `ass`) and `format_fallback` (default `false`); anything else refused on both roads · `rank.py`: the preferred kind first (`.ass` means `.ass` and `.ssa`); with the fallback OFF every other kind is FILTERED, with a reason naming the setting; ON, the old order follows · `pipeline.py`: an episode whose every file is the other kind is NOT_FOUND with its OWN reason and word — ⛔ never *"not on jimaku yet"*, which would be false — and the usual 1-day retry, since the preferred kind may yet be uploaded · the window: a *Subtitle format* card (a painted radio pair + a Check) |
| ⚠ **Upgrade** | An older hato REFUSES a key it does not know, and Sonic's own 1.0.1 tray is running: every run it starts would die on `prefer_format`. ⭐ **Keys newer than 1.0.2 are written only once set away from their default** — the rule *every key written* exists so a CHANGED default cannot move an old install, and a key an old install never had has no old default to protect |
| **Expected** | ⭐ With the defaults an episode offered ONLY as `.srt` is **not downloaded**, and says so — ruled. This changes Sonic's own hato too |
| ✅ **Proof, 2026-09-23** | `hato/formats.py` (stdlib only; the window imports it) · config 4 checks · rank 5 · pipeline 7, among them the switch taking effect at the NEXT run (two arms, the same hour) and no other wait ending · window 10 · **M9a 25/25, first run**; 3 older mutants re-aimed (M3b-01/02, M8zt-49). ⚠ The run suite's `Lab` now says `format_fallback=True` out loud: three checks about other things (the cap, a film, an archive) went red when the default landed. ⚠ Mode A's snapshot moved *"13 offered"* → *"8 offered"* — the full render diffed line by line, that the ONLY change. ⭐ **LOOKED (L9-01…05)**, and looking caught three: the new Needs-you line said everything but WHEN; *"your settings take it now"* read as a fetch in progress; and **four real titles pushed the line's own button off the window** — the older *"not on jimaku yet"* line one title from the same. The mock draws both as a wrapping paragraph; both are `Flowing` now, with a geometry check each |

### Step 9b — A subtitle named for the video, with no language, is read first

**surfaces:** `logic`
**Ruling (Sonic, 2026-09-23):** *"yes, but needs to not report falsely. I don't want this to
be a big issue or feature, just a quick one that errs on the side of 'download' than not,
but does check"*

| | |
| --- | --- |
| **Build** | `present.Presence.find`: when no Japanese-NAMED sidecar is there, an UNTAGGED one with the video's exact stem and a text-subtitle extension is READ (bounded) — Japanese only on strong evidence, then *present* and the skip names the file and says its text is what said so · ⭐ anything uncertain (undecodable, short, mixed, not text) → **fetch, exactly as before** · only for Japanese: any other wanted language is never read |
| **Test** | synthetic fixtures only — ⛔ never a jimaku body (`scan-content`): Japanese `.srt`/`.ass` in UTF-8, UTF-8-BOM, UTF-16 and cp932 · English · Chinese · Chinese+Japanese in one file · English with a Japanese song · too short · binary · a Japanese `.nfo` (not a subtitle) |
| **Measured** | ✅ Over **163 real Japanese subtitles** (copies of Sonic's kept originals and download cache, read-only): at least **290** dialogue lines · kana in at least **0.65** of the lines · kana at least **0.68** of kana + kanji. The nearest wrong answers: Chinese + Japanese in one file **0.45** kana · English with a Japanese song **0.13** of lines · Chinese **0** · Chinese in GBK does not decode, and Big5 decodes as Shift-JIS into HALF-width katakana. ⭐ Set at **100 lines · 0.40 · 0.55**, a margin each side |
| ✅ **Proof, 2026-09-23** | `present.reads_as_japanese` · 14 checks in `test_existing.py` §2b + one two-arm end-to-end (`test_endtoend.py`: Japanese inside → skipped, zero downloads, the reason says so; English inside → fetched) · **M9b 16/16** — ⚠ two survived the first run, both CHECK gaps: the folder is listed alphabetically, so the named file won before the untagged one was ever seen (both orders now), and a threshold check whose arms were computed FROM the constant moved with it (an absolute 60-line arm now) |

### Step 9c — tsubasa reads `.jp` as Japanese

**surfaces:** `logic` — **in tsubasa**, where the name reader lives (`LEDGER-HOT.md`: never a
second parser here)

| | |
| --- | --- |
| **Build** | tsubasa `sidecar.py`: `jp` → `ja`, whole token, case-folded like every other tag · its checks and mutant there · ⭐ measured against tsubasa's filename corpus before it lands (*"widen this only with a measurement"*) — `hato/tokens.py` already counts `jp` **18,228** times among the jimaku corpus's tokens |
| ⛔ **Then** | tsubasa 0.1.8 is an **IRREVERSIBLE** publish — Sonic's go · after it, hato's floor → `>=0.1.8` and a present-check for `.jp` |
| ✅ **Proof, 2026-09-23** | `tsubasa/sidecar.py` `_COUNTRY_AS_LANGUAGE = {"jp": "ja"}`. ⭐ **Measured before it landed** over the corpus's dev slice (the sealed slice never read): **271 of 17,790** real filenames move, every one `und` → `ja`, every one ending `.jp.<ext>` (248 `jp` · 22 `JP` · 1 `Jp`) — and **nothing else moves**. 3 checks in tsubasa's `test_sidecar.py` (every casing and shape, the slot, the position rule, the corpus measurement pinned) · both mutants killed in a scratch copy (`PYTHONDONTWRITEBYTECODE=1`) |
| ✅ **Released, 2026-09-23** | ⭐ **tsubasa `v0.1.8`** = `5be457c`: CI 16/16, release 4/4, verified from the PUBLISHED bytes — PyPI install outside any checkout, and the downloaded zip (`SHA256SUMS` OK, smoke 44/0/0 on real media); two-arm against 0.1.7 on a real episode from the INSTALLED packages. **hato's half:** the floor `tsubasa-sync[parsing]>=0.1.8` (`test_packaging` refuses 0.1.7) · `test_existing` `test_the_country_code_jp_is_read_as_japanese_by_name` · `mutants/m9c.mjs` **2/2** — M9c-01 breaks `jp` at tsubasa's SOURCE in the scratch copy (a patch after import never reached it — `LEDGER.md` §harness) |

### Step 9z — THE ADVERSARIAL PASS: RUN 2026-09-23 · closed on 9a, PARTIAL on 9b + 9c

Two fresh agents, split by surface: **9a** — the format setting (config, ranking, the run,
the window, an older hato reading the file) · **9b + 9c** — the untagged read and
tsubasa's `.jp.`. ⛔ Nothing was edited while they ran: the fixes were built in a private
copy (`%TEMP%\hato-s8\dev9`) and ported with a digest check that the vault had not moved.

⚠ **9b + 9c's agent was STOPPED before it reported** (an interrupt), and is not resumed
without Sonic's word. Its 24 probes on disk were triaged instead, every finding reproduced
before it was fixed — so that half of the pass is **PARTIAL, and says so**.

▶ **`ADVERSARY-2026-09-23.md` is the register: 22 fixed · 5 dropped · 2 deferred**, every
`fixed` row naming its check and its mutants. `m9za` **48** · `m9zb` **3** · **14** older
mutants re-aimed (M9a ×9, M3a ×2, M9b ×3) — **every one killed**.

🚨 **The worst, both at SEAMS:** a **1.0.2 tray** was taken for this build — it already
writes `retries` — so Settings said nothing while every run it started died on the new keys
(9a-1: a new capability token, `formats`); and **a part of a large file was judged** — a
4.5 MB `[CHS, JPN]` .ass read Japanese from its karaoke: a false *"already there"*, the one
answer Sonic's ruling forbids (9b-1: never judge a part; read 16 MB).

**Also:** *"offered"* meant any file, in any format, to the escalation and the archive pass
(9a-2) · a re-sync wrote a format the person had stopped taking (9a-3) · a wait named only
its commonest kind (9a-4) · five surfaces called a format wait *"not on jimaku"*, *"not
found"*, a pick, or a download (9a-5…8) · one Needs-you line for refused and taken rows
(9a-9) · a film's `.7z` offered as its subtitle (9a-10) · the look-again racing the write
(9a-11) · a failed download called a timing refusal (9a-b2) · 9c turning a `.JP`-named
video's own `.JP.srt` into a tagged file (9b-3).

**Proof, as run:** the full runner over the vault **29 suites / 2,054 checks GREEN**, exit 0
(`%TEMP%\hato-s8\d3\full-run-12.log`) · ⭐ **every Layer 9 mutant over the vault's own tree:
94/94 killed** (M9za 48 · M9zb 3 · M9a 25 · M9b 16 · M3a-16/19; 8m 57s, `EXIT=0`,
`mut-vault-9.log`) ·
six screens re-shot and LOOKED (`L9-01…06`, the sixth new: refused and taken kinds on two
lines).

---

## 🚨 LAYER 10 — D12: RUN NOW CLOSED THE WINDOW. Added 2026-09-24 · ✅ RELEASED in `v1.0.4`

> **From Sonic's report on 1.0.3, 2026-09-24:** *"it crashes gui on 'run' button is clicked.
> Reproduced on 2 machines. The automatic detection and run still seems to work great."*
>
> | # | Found | Evidence |
> | --- | --- | --- |
> | D12 | 🚨 **Pressing Run now closes the window — in 1.0.2 and 1.0.3.** `clicked` carries `checked`, and PyQt hands it to the slot's first positional parameter. 8e (2026-09-22) gave `start_run` an `argv=None` for the look-again, and the title bar's button was wired straight to the method — so every press arrived as `start_run(False)`: `Runner(argv=False)` → `list(False)` → a `TypeError` out of a slot, which PyQt6 answers with `qFatal`. 1.0.0 and 1.0.1 had `start_run(self)`, and were fine. ⭐ **Why the rest kept working:** the tray, the 03:00 run, a dropped folder and *Look again* start runs by other roads, none through this button | ⭐ **Sonic's own event log:** `Desktop\hato\hato.exe` — the released 1.0.3 bytes, by hash — died **four times** (09-24 00:38 ×3, 13:59), `0xc0000409` in `Qt6Core.dll` 6.11.2. **Two arms, source:** a real click → `Runner` handed `False` → the process dies `0xC0000409` (offscreen and the real desktop alike); the direct `start_run()` every check made → a real command, the run finishes. **Two arms, the released 1.0.3 zip unpacked outside the repo:** Run now pressed through UI Automation → dies `0xC0000409`; the Settings tab pressed the same way → alive, so the instrument is clean. A hook arm (an `excepthook` stops PyQt aborting) shows the text: `TypeError: 'bool' object is not iterable` at `app.py` `start_run` → `run.py` `Runner.__init__` |
>
> ⛔ **Why every check was green:** `test_run_now_builds_the_argv_run_py_owns` is named for
> the button and calls `start_run()` — the function under it — exactly
> `doctrine/verification`'s first row: *"a sign-out test called the library function instead
> of clicking the control."* And the smoke drove the built window only to ask whether it was
> VISIBLE; nothing anywhere pressed a control.

### Step 10a — Run now runs

**surfaces:** `ui` `harness` `delivery`

| | |
| --- | --- |
| **Build** | `gui/app.py`: the button wired through the file's own idiom — `lambda _checked=False: self.start_run()` — with the reason at the site. ⛔ `start_run` keeps its signature: the look-again passes `argv=` and `targeted=` by name, and a second guard beside the lambda would witness neither |
| **Test** | `test_gui_widgets.py` `test_CLICKING_run_now_starts_the_run_it_names` — a real click through Qt's event path: the command `run.py` owns, and *starting…* on the footer · ⭐ `test_no_method_wired_to_a_signal_has_a_default_a_click_would_fill` — the CLASS, read off the source of every `hato/gui` module: every `.connect(self.<method>)` whose method takes a DEFAULTED positional parameter is refused, with a control proving the reader finds the shipped shape. ⚠ It cannot see a lambda's own default; the `_c=False` idiom guards those on real buttons, and the three without it sit on `Clickable`s, whose `clicked` carries nothing · ⭐ `packaging/smoke_standalone.py` **6b** — Run now PRESSED in the built window through UI Automation (no pointer moves): the window stays up, the run writes `last-run.json`, the footer says *done* |
| ✅ **Proof, 2026-09-24** | the baseline before any edit: the full runner **29 suites / 2,055 checks GREEN** · the two new checks green; each red with the wiring put back, and the message names it (*"handed the run False … the click's `checked` flag reached `start_run`"*, *"line 2183: self.start_run(argv, targeted)"*) · **M10a 3/3** killed (`--scratch`, 15 s), the anchor preflight **946** mutants, 0 problems · `gui_widgets` **291** + `gui_run` 60 GREEN · LOOKED: a real click in the real window → *starting…* → *done*, *last run 14:23* · ⭐ smoke **6b** against the RELEASED 1.0.3 zip: **30/31, the one failure *"the WINDOW DIED on the press, exit 0xC0000409"*** · ⭐ the fixed tree frozen into `%TEMP%` (PyInstaller 6.18, Qt 6.11.2 — the release's toolchain), zipped by `build_zip()` outside the vault: **smoke 31/31** on the unpacked copy, 6b *"pressed; the run wrote its record, the footer says done"* · LOOKED at the built window after the press: *done*, *last run 14:31* · the full runner over the fixed tree **29 suites / 2,057 checks GREEN**, `EXIT=0` (`_runs/20260924-143221`) · then, the reader widened to every `hato/gui` module: `gui_widgets` **291** GREEN, the preflight 946/0, **M10a 3/3** again |
| ⏸ **Release** | `1.0.4` is **IRREVERSIBLE** (a public tag and asset) and the release NUMBER is declared by a human (`hato/dev/stamp.py`) — Sonic's go. Nothing was stamped: `package_standalone.py` names its zip from the source version, so a zip made before the stamp would have overwritten the released 1.0.3 artifact. ⭐ The fixed tree was frozen into `%TEMP%` instead |
| ⭐ **RULED 2026-09-24 (Sonic)** | *"Don't publish 1.0.4 yet, I want to include the logging in this next update AND one more thing"* — the logging is **10b** below; the one more thing is **LAYER 11**, auto-update |

### Step 10b — An error inside the window is written down, and the window stays

**surfaces:** `ui` `harness`
**Ruled (Sonic, 2026-09-24):** *"I want to include the logging in this next update."* The picture
it was ruled on: D12's own crash with a prototype net — the window stays up and the footer says
*"something went wrong — it is written in hato.log"* (`%TEMP%\hato-runbtn\safety-net.png`).

| | |
| --- | --- |
| **Why** | PyQt6 aborts the process on any exception that leaves a slot (`qFatal`, `0xC0000409`), and the windowed exe has no console, so the traceback goes nowhere: D12 reached Sonic as a window vanishing with no word, twice a release |
| **Build** | `gui/app.py` `ErrorNet`, put up FIRST in `main()` (before Qt), the window handed to it the moment it exists: it takes `sys.excepthook` (PyQt's documented way to carry on instead of aborting) and `threading.excepthook`; writes the traceback to hato.log through `watch.complain(text, who="window")` — the tray's own never-raising writer, now naming its caller, so one file holds runs, the tray and the window; the footer says `ERROR_LINE` and its tooltip names the file · `HatoWindow.error_caught`: a run whose CHILD never started is over (⚠ asked of the child, not the object: after D12's shape `_runner` still held the previous run) · `_render_after_error` catches its own error, so a failing repaint can never report itself for ever · the same traceback is WRITTEN once and SAID every time |
| **Test** | `test_gui_widgets.py` §10b, 9 checks (8, one run for two shapes), each with a SENTINEL hook put in first — a net that failed to install FAILS its check instead of aborting the suite: an error in a real click · D12's shape with no earlier run and with a finished one · a live child left alone · the repaint cannot loop · once written, always said · a thread's error written, never painted · the real block in the real log, never counted as a run · `main()` puts the net up before Qt |
| ✅ **Proof, 2026-09-24** | ⭐ **two arms through the REAL `main()`**, a scratch copy with D12 put back: without the net the press killed the process `0xC0000409` (above); with it the window STAYED — `running` reset, the footer *"something went wrong — it is written in hato.log"*, and hato.log holds `=== hato window 15:40:21 ===` with the full traceback. LOOKED. · **M10b 12/12** (M10b-12 re-aimed when LOOKING moved the tooltip off `wrap()`, and re-killed) · the preflight 958/0 · ⚠ **measured and dropped:** the frozen window's `sys.stderr.write` on a refused config does NOT raise (two arms on the built bytes: the window opened and showed the error) — the stream exists and nobody reads it, which is why the log is the channel · the full runner **29 suites / 2,066 checks GREEN**, `EXIT=0` (`_runs/20260924-154117`; `gui_widgets` 291 → 300) |

---

## ⭐ LAYER 11 — AUTO-UPDATE. RULED 2026-09-24 (*"I take all your leans"*) · BUILT 11a–11h + 11z the same day · ✅ RELEASED in `v1.0.4`, 2026-09-24

> **Asked by Sonic, 2026-09-24:** *"I have another python app ... surasura ... they have an auto
> update feature ... tell me if you think this would be worth implementing and how you would
> suggest implementing it ... super high quality ... follow our design language and be in a nice
> spot ... The dialog or whatever needs to be pretty as it auto-updates. It needs to show that it's
> updating. It needs to automatically restart ... Some users will still be using this on Linux."*
> The reference, read in full: `InfiniteVoid/SonicInfinite/Auto_Update_Architecture.md` (surasura
> v2.2 — stage while running, a separate swapper exe, back up / swap / verify / roll back, never
> loop). ▶ **The picture: `gui-mock/mock-update.html`** (click through 8 states, A/B toggle) and
> `gui-mock/shots-update/` (12 shots, every one LOOKED at).
>
> ⭐ **MEASURED BEFORE ANY DESIGN** (probes in `%TEMP%\hato-runbtn\`, on a copy of the fixed build
> installed under `…\ツール置き場\hato`, its own store):
>
> | Fact | Measured |
> | --- | --- |
> | What can be renamed while hato runs | a running **exe: yes**; **`_internal/`: no**, nor the install folder (`WinError 5`) — while the window OR the tray runs |
> | 🚨 Who holds the folder after the window closes | **the tray** — `main()` starts it whenever watching is on, and it outlives the window by design. Nothing else: a folder never run, or run only by the CLI, renames freely |
> | Frozen window, start → visible | **0.89 · 1.23 · 1.68 s** — the gap a restart leaves on screen |
> | Download sizes | full zip **67.4 MB** · the three exes alone **19.0 MB** · `_internal` unpacked **121.8 MB** |
> | Integrity for free | GitHub's API gives each asset's sha256: 1.0.3's zip reads `sha256:adc8f136…ef0f` — the hash recorded at release. Unauthenticated limit **60/h** |
> | Authenticity for free | the bundle already carries PyCryptodome **3.23.0** with a native **Ed25519** (`_ed25519.pyd`, via py7zr): sign + verify works, a changed byte is refused |
>
> **Recommendation: YES — for the Windows exe.** D12 is the case for it: the fix exists and
> reaches nobody until each person notices, downloads 67 MB, stops the tray (the folder is locked
> while it runs — measured), unzips over the running folder and restarts. Four releases in five
> days. And hato is BETTER placed than surasura: everything of the person's already lives in
> `%LOCALAPPDATA%\hato`, so the program folder can be replaced wholesale.
>
> **What changes from surasura's design, and why:**
>
> | surasura | hato | Why |
> | --- | --- | --- |
> | a small "app package" (exe + templates) + a full zip when the runtime changes; `runtime_baseline` + a requirements tripwire | ⭐ **the whole program, every time** | the installed bytes are then EXACTLY the bytes the release gate smoke-tested unpacked; no baseline to forget; a tsubasa, Qt or Python bump just works. Cost: 67 MB a release instead of 19 |
> | one exe to swap; the helper waits on ONE pid | **four exes + the tray**; the swapper waits for EVERY process whose image lives in the install folder | the tray holds the folder (measured); a run the tray started holds it too |
> | files swapped by copy (`copytree` a `.new`, then rename) | **every top-level entry renamed** on one volume — old → `previous\`, staged → in place | instant and atomic per entry; 122 MB never copied twice. Staging lives on the install's own VOLUME (`%LOCALAPPDATA%\hato\update\` when it is the same volume, so a synced Desktop never uploads it) |
> | `updater.exe` ships once and can never update itself | ⭐ **the NEW version's swapper** runs, copied out of the staged payload | a fix to the swapper travels with the release that needs it |
> | verified by the new exe's sha256 | sha256 ✓ **and** the new window must become VISIBLE (EnumWindows + IsWindowVisible) within 20 s — else roll back and start the old one | LEDGER-HOT: never verify a spawn by asking whether it survived |
> | sha256 from `update.json`, both on GitHub | + **an Ed25519 signature** from a key kept in `InfiniteVoid/keystore/`, checked with hato's own public key | auto-update turns "whoever can publish a release" into "whoever can run code on every install" — and a GitHub token is live today (HANDOFF §4) |
> | "the user decides": nothing downloads until a click | ⭐ downloads and checks quietly; the WINDOW never restarts under a person (pill → card → *Restart now*, or *When I close hato*); with no window open, the tray / the 03:00 run installs it when nothing is running | Sonic: *"as it auto-updates … automatically restart"*; the frozen rule: the decision gets a surface, the manual choice stays one click away |
> | status-bar text; the app vanishes during the swap | the pill / card / steps / progress, a **native splash** while no window exists (drawn by the swapper, the tray's ctypes technique), *"Updated to 1.0.5 ✓"* with what's new, *"put back"* on failure, a Settings card with *Check now* and *Go back to 1.0.4* | Sonic: *"pretty … show that it's updating"* |
> | a source checkout refuses | ⭐ **any OS, from source: tell, never touch** — *"hato 1.0.5 is out · `git pull`"* in the same spot; `hato update --check` in a terminal; nothing at import time | it may be somebody's working tree; the library API stays side-effect free |
>
> **The pieces:** `hato/update.py` (check · stage · the two JSON contracts; stdlib + requests +
> Cryptodome) · `hato update --check/--stage --progress/--apply/--rollback` (the window drives it
> through the Runner and its NDJSON progress, exactly as it drives a run; the tray calls the same
> command) · `hato-update.exe` (onefile, windowless, stdlib + ctypes — a static check that it
> imports nothing from hato, as the tray has) · the window's pill / card / notes / Settings card ·
> the tray's idle install · the packager's `update.json` + `update.json.sig` from the SAME zip ·
> ⭐ **the smoke's REHEARSAL: unpack the previous release, stage the new build from a local
> source, apply it through the real swapper, assert the new window is visible and reports the new
> version — then force a failure and assert 1.0.x is back.**
>
> **What it can never do:** update a **1.0.3** install (no updater inside it — everyone installs
> 1.0.4 by hand once, as surasura's 1.9 users did) · update a source checkout (by design) · update
> a folder it cannot write (a Program Files install is told to download instead) · survive BOTH
> GitHub and the signing key being compromised.
>
> ✅ **RULED 2026-09-24 (Sonic): *"I take all your leans"*** — 1 **A**, the pill + the card ·
> 2 **automatic**: download and check quietly, the window never restarts under a person, the
> tray or the 03:00 run installs while no window is open and nothing runs · 3 **signed** — and his
> question answered first: the PRIVATE key stays on his machine (`InfiniteVoid/keystore/`), only
> the PUBLIC half ships inside hato, so other people's installs need nothing and hold nothing ·
> 4 **the whole folder** · 5 **the native splash** · 6 **the previous version kept** for *Go back*.
>
> **The steps, in dependency order.** Each ships with its checks, its mutant list (`m11x.mjs`)
> and, where anything is drawn, a shot that is LOOKED at.
>
> | Step | surfaces | What | Its proof |
> | --- | --- | --- | --- |
> | **11a** | `data` `delivery` | ⭐ **The release contract.** `hato/update.py`: the manifest (`update.json` — version, the zip's name / size / sha256, `min_from`, `critical`, the short notes, the bundle's top-level entries with each exe's sha256), its strict parser (anything missing or odd → refused), X.Y.Z comparison, and the Ed25519 check against `PUBLIC_KEYS` (a tuple, so a key can be rotated). `hato.dev update-manifest` builds + signs one from a zip; `hato.dev keygen` writes the PRIVATE key to the keystore (⛔ refuses any path inside TheForge) and prints the public half | parse / sign / verify / refuse checks; a flipped byte, a wrong key, a missing signature each refused |
> | **11b** | `logic` | **The check.** `releases/latest` (one metered-free call; `HATO_NO_NETWORK` → silent NONE), the manifest + signature, the zip's GitHub `digest` must EQUAL the manifest's sha256 → `NONE` · `READY` (frozen on Windows, a writable folder, newer, signed, `min_from` met) · `TELL` (newer, but this install cannot apply it — from source, another OS, an unwritable folder: say it, never touch) · at most once a day unless *Check now*; the answer kept in `update-state.json` | recorded fixtures of the real API shape; offline, 403, 404, unsigned, a bad signature, a digest that disagrees, equal / older / newer, source mode |
> | **11c** | `logic` `data` | **Staging, while hato runs.** Download with progress, sha256 against BOTH, extract through `archives.py`'s escape guard, the manifest's entries present and each exe's sha256 right, the staged `hato-cli.exe --version` equal to the manifest's (frozen) · staged on the install's own VOLUME · `pending.json` written temp-plus-rename · `hato update --check/--stage --progress/--apply/--rollback` (NDJSON, the Runner's grammar) | a local source; a corrupt download, an escaping member, a missing entry, a wrong version — each leaves nothing behind |
> | **11d** | `logic` `delivery` | ⭐ **The swapper.** `hato/swap.py` (stdlib + ctypes ONLY — a static check, as the tray has) frozen ONEFILE as `hato-update.exe`, and the NEW version's copy is the one that runs: waits for every process whose image is in the install folder (≤ 60 s, else aborts untouched), renames every entry old → `previous\`, staged → in place, checks each exe's sha256, restarts the tray if it was running, starts the window if asked and waits for it to be VISIBLE (≤ 20 s) — any failure renames everything back and starts the old one · `result.json` · a person's own files in the folder are never touched | as plain Python under `…\ツール置き場\`: swap, each failure rolled back, a live process → untouched, unknown files kept, the relaunch asserted by window, not by survival |
> | **11e** | `ui` | **The splash** — drawn by the swapper in Win32 (the tray's technique): the mark, *"Updating hato to X"*, a moving accent line; gone when the new window is on screen | a PrintWindow shot, LOOKED at against `mock-update.html` state 4 |
> | **11f** | `ui` | **The window.** The pill; the card (what's new — ⛔ remote text, so `safe()` and never rich text — *When I close hato* / *Restart now*); the progress (four steps, one bar) driven by `--stage --progress`; the hand-off (the tray stopped and remembered, the swapper started from the staged copy, then the window quits); *Updated to X ✓* and *put back* from `result.json`; a `critical` release opens the card once; Settings → **Updates**, LAST (version, *checked*, *Check now*, *Update automatically* — `auto_update`, written only once changed, the 1.0.2 rule — *Go back to X* only while `previous\` exists); from source, the instruction and no switch | real clicks for every control; LOOKED at against the mock, state by state |
> | **11g** | `logic` | **The tray and the 03:00 run** check and stage daily when automatic, and install while NO window is open and NO run holds the lock | a fake clock; a window open, a lock held → nothing installed |
> | **11h** | `delivery` | The fourth exe in the bundle and the smoke (present · `--selftest` · imports nothing from hato) · ⭐ **the REHEARSAL**: a copy of 1.0.3 as the "installed" folder, the new build as the payload, the REAL new swapper → the new window visible and `--version` new; then a broken payload → rolled back, 1.0.3's window back · the release sequence gains: manifest + signature from the SAME zip, verified the way a client verifies, three assets, and the published three downloaded and verified again | the smoke green on the unpacked zip; the rehearsal both ways |
> | **11z** | — | the adversarial pass over LAYER 11, split by surface (check+stage · swapper · window+tray), before the release | a register: fixed / dropped / deferred |
>
> ✅ **1.0.4 AUTHORIZED (Sonic, 2026-09-24):** *"Once you have everything working properly, all
> of it tested as normal, if thre is nothing in the way you are free to upload it as the next
> hato update to github. The important one is going to be the updater"* — released after
> 11z and the full gates, never before.
>
> ✅ **11a BUILT 2026-09-24.** `hato/update.py` (the contract) · `hato/dev/signing.py`
> (`keygen`, `update-manifest`, registered in `hato.dev`) · `paths.signing_key_file` +
> `keystore.signingRelative` · the `update` extra (pycryptodomex, named in the notices) ·
> `scan-secrets` gained `no_private_key_block`. ⭐ **The real key was made**:
> `InfiniteVoid/keystore/hato-update-signing.pem`, outside every work tree (git asked, not
> assumed), its public half in `PUBLIC_KEYS` and a check that the keystore key IS one hato trusts.
> Proof: suite `update` 61 · devtools +2 · **M11a 13/13** — ⚠ M11a-06 SURVIVED first: the
> `'..'` case carried an empty hash, so the FILE rule refused it and the NAME rule could be
> deleted unseen; the case now carries a valid hash (LEDGER.md: a check another guard rescued)
> · and the packaging suite caught three honest gaps before they shipped (the import-name map,
> the notice, an unguarded import in `signing.py`).
>
> ✅ **11b BUILT 2026-09-24** — `update.check` + the once-a-day state, against a fake GitHub
> serving the RECORDED answer's shape (`tests/fixtures/update/releases_latest_1.0.3.json`,
> captured with one unauthenticated GET; every synthetic asset is a copy of the recorded one).
> The real 1.0.3 release reads as *up to date* on 1.0.3 and as TELL(no manifest) on 1.0.2 — the
> first real case this code meets. **M11b 14/14.**
> ✅ **11c BUILT 2026-09-24** — `update.stage` (download counted and hashed, members judged by
> `archives.unsafe_name` — now public, ONE copy of the rules — links refused, the unpacked
> program exactly the manifest's, `pending.json` temp-plus-rename, a failure leaves nothing) and
> `hato update --check [--if-due] / --stage [--progress] [--json]` in `cli.COMMANDS`. Suite
> `update` 110. **M11c 14/14** — ⚠ found by thinking the mutants through BEFORE running them:
> deleting the download's size cap would have survived (the final size check refuses the file
> too, AFTER reading all of it), so the cap's check now counts the bytes READ.
>
> ✅ **11d BUILT 2026-09-24** — `hato/swap.py` (stdlib + ctypes; an `ast` walk holds it to
> that), frozen ONEFILE as `hato-update.exe` · the hand-off: `update.hand_off` copies the NEW
> version's swapper to the staging root and starts it detached; `go_back_pending`,
> `kept_version`, `staged_version`, `skip`, `reconcile` · `hato update --apply / --rollback /
> --auto` · `watch.stop_running_watcher`, one copy for the window and the tray. Proof: suite
> `swap` under a Japanese-named folder with the operating system handed in, the REAL
> Toolhelp32 listing driven once · **M11d 42/42**. ⚠ Found by reading before running, each now
> with its check: Go back's tidy deleted the version it went back to · a program started
> through its 8.3 SHORT path was missed (two-arm) · ways out that could raise · an install
> with no window had no proof (the new `hato-cli --version` must say `to`) · a window that
> opens and dies passed (a 3 s settle) · staging never swept its leftovers.
>
> ✅ **11e BUILT 2026-09-24** — by the orchestrator: the builder was stopped by an interrupt
> and, per the rule, not relaunched. `hato/splash.py`: a layered window with per-pixel alpha
> on its own thread; every pixel but the words computed in plain Python (the shadow, the
> gradient, anti-aliased corners, hato's mark read from its own PNG and scaled by area, the
> sweep), the words by GDI on the opaque card. ⭐ **Measured against the mock's own
> renderer:** headless Chrome drew the mock's `.splash` CSS; its shadow fits a gaussian of
> sigma 35 over the inset rect (rms 0.004) and is the check's reference; a side-by-side of
> the two cards matched to the row. **The two hand-offs around it:** the swapper takes it
> down at FIRST SIGHT of the new window, not after the 3 s settle; the window keeps itself,
> saying *Installing*, until the splash is up (at most 8 s) — and stays open, restarting its
> tray, if the swapper has already exited. Go back says *Going back to hato X*. Proof: suite
> `splash` 28 — pixels without a window, then the REAL window: its styles, focus, DPI,
> placement, what Windows composed, close — `swap` +3 · `gui_updates` +3 · `packaging` +1 ·
> **M11e 31/31** (⚠ M11e-02 SURVIVED first: the corner check's bar sat inside the card's own
> gradient) · paint 0.26 s, a frame 0.6 ms, 1.6 % of a core at DPI 240 · LOOKED on the real
> desktop and beside Chrome's render.
>
> ✅ **11f BUILT 2026-09-24** — `hato/gui/updating.py` (the view, no Qt) + the window's
> wiring: the pill, the card, the four-step progress, the banners, Settings → **Updates**
> (last), from source the instruction and no switch; the `auto_update` key, written only once
> switched off (`config.NEWER_THAN_1_0_3`), and an older tray that would refuse it SAID, with
> its fix. Proof: suite `gui_updates`, real clicks for every control · **M11f 35/35** · 12
> shots LOOKED — four defects found only by looking (Qt dropped a pill radius over half its
> height; a QLabel dropped the spaces in *"hato 1.0.5 is"*; a card measured before polish;
> *Downloaded* while downloading) · and the remembered answer offered the version already
> running (fixed in the command AND the view).
>
> ✅ **11g BUILT 2026-09-24** — the tray's `UpdateKeeper` (an hourly `hato update --auto`
> child; install when no window is open and no run holds the lock), `window_open` by the
> program file, `install_when_idle`, and the 03:00 run's `update_now` when no tray watches;
> the tray's pid line carries `updates`. **M11g 24/24** — ⚠ M11g-04 SURVIVED first: its
> check let time pass and read a stale timer; split into two.
>
> ✅ **11h BUILT 2026-09-24** — the fourth exe (ONEFILE, copied into the folder AFTER the
> COLLECT) and `entry_update.py --selftest` · ⭐ **the REHEARSAL** in `smoke_standalone.py`:
> the newest released zip installed under `…\ツール置き場\`, this build staged from a local
> copy through the real `update.stage`, the REAL frozen swapper both ways — a new version
> that cannot start is put back and the old window returns; the new one goes in, its window
> SAYS *Updated to X*, the old one is kept for Go back, and the splash is seen on screen,
> composed in the card's colour, and gone as the new window came (smoke over the unpacked
> zip, 2026-09-24: **44 checks, 43 green** — the one red was the CHECK: a onefile exe runs
> its code in a CHILD process, so the splash is not the pid `Popen` returned; fixed, and
> proven at the next smoke) · `hato.dev
> verify-release` downloads the three published assets and verifies them the way a client
> does. ⚠ **Three defects found by designing the rehearsal, each fixed with a check:** *Updated
> to X* could never show (the result lands after the window looked — the window now polls) ·
> the new version's CRASH DIALOG is a visible window of its pid (the proof asks for hato's
> title) · an earlier swap's result was shown by the next swap's window (removed at the start
> of every swap) · and zipping an unpacked release wrote the licence twice. **M11h 12/12.**
>
> ✅ **11z RUN 2026-09-24 — `ADVERSARY-2026-09-24.md`: 27 fixed · 0 dropped · 3 deferred.**
> Three adversaries by surface (A check + stage · B swapper + splash · C window + tray),
> read-only on the vault; the fixes built in a private copy and PORTED by a script that
> refused any file the vault had moved (22 files, no drift). ⭐ The worst were SEAMS: the
> window's own start-up starting a second tray while the swapper started its own — two
> trays, or a rollback the window's tray made impossible (S3, found by the orchestrator's
> review and reproduced by C) · `verify-release` asking the TAG's release while every install
> asks `latest` (A4) · a person closing the new window read as a crash (C7). Also: a
> nested `update.json` switched every check off (A1) · `--apply` could DOWNGRADE (A3) · two
> installs shared one staging folder (A6) · the swapper trusted every path it was handed
> (B1). And the FULL runner caught what no Layer 11 suite could: `auto_update` unregistered
> in the library API's schema check (R1). `m11z` 58 mutants + 16 older re-aimed.
> ⭐ **The gate** (`--scratch`, every Layer 11 list + the re-aimed): **245 — 243 killed, 2
> SURVIVED, both closed** — G1: a stage listing NO entries read as waiting (`all()` of
> nothing is true; now refused, M11z-A5b — and M11f-29 retired, equivalent once it is) ·
> G2: the check that closed C9 stopped at *Restart now*'s NAME, and the mutant made the
> button do nothing — it PRESSES it now. ⚠ **Read for TRAVEL before the push:** two
> checks would have failed on the Linux and macOS jobs, on the platform and not on hato
> (Windows-spelled paths in a fake listing; `--auto`'s fixture faking a frozen build but
> not Windows) — fixed. The register's §*The gate*.

---

## ⭐ LAYER 12 — UPDATES YOU CAN SEE. RULED 2026-09-24

> **Asked by Sonic after 1.0.4 shipped:** *"Is there a button for 'check for an update' in the
> settings so they could manually check? And any UX quality of life related to that?"* The
> button existed (Settings → Updates, *Check now*). Reading the code for the answer found two
> real gaps and four small ones, put to him as a table with leans. ✅ **RULED: *"Go do all of
> your leans, I agree in all cases"*** — and on releasing them: *"Yes, and that's a great way
> i will be able to test the update too."* ⛔ The seventh row, a *Check for updates* item in
> the tray menu, was leaned OUT (the tray updates by itself; choices live in the window).
>
> **Why it matters:** 1.0.5 is the first release any install takes BY ITSELF — Sonic installs
> 1.0.4 by hand and watches it update. Every step below is about an update that happened
> being SEEN (the frozen rule: a decision made on a person's behalf needs a surface).

| Step | surfaces | What | Its proof |
| --- | --- | --- | --- |
| **12a** | `logic` `ui` | 🚨 **An open window sees what the tray downloaded.** It read *what is staged* only at start and when a swap result landed, so a release the tray downloaded behind an open window showed no pill — and the tray will not install under an open window, so it waited silently until hato closed. *Check now* then downloaded all 77 MB AGAIN (the in-memory `staged` was stale and `hato update --stage` never asked the disk). The minute tick re-reads `update.staged_version` (disk only); the check's answer and *Restart now* read the disk before choosing to download; `--stage` answers *staged* without a byte when that version is already whole on disk | a stage appearing on disk mid-life → the pill at the next minute · *Check now* answering READY for a staged version → no download, *Restart now* · `--stage` over a whole stage → the fetcher never called |
| **12b** | `logic` `ui` | **An open window keeps checking.** It asked GitHub only as it opened; left open for days it never asked again, and *"checked 12 min ago"* stood still unless something else on screen was dated. The minute tick runs the once-a-day check when it is DUE (`update.due`, in-process — no spawn otherwise), and re-renders while the line carries a *checked … ago* | due → one `--check --if-due`; not due → nothing spawned; the line moves with the clock |
| **12c** | `ui` | **Check now shows it did something.** The button STAYS, disabled, while checking — it used to vanish, and the row's height jumped (the layout must not depend on the state) · *checking…* is held at least half a second · a manual check that finds nothing says *"✓ you have the newest"* for a few seconds | the pressed button disabled and the row the same height · an instant answer applied only after the hold · the confirmation, then the plain line |
| **12d** | `ui` | **The version in the footer.** *hato 1.0.4*, left of *Created by*; a click opens Settings with the Updates card in view | the footer's text from `State`; the click lands on the card |
| **12e** | `logic` `ui` | **A rate-limited check says so.** GitHub answers 403/429 when an address asks too often (60 an hour unauthenticated) and hato said *"GitHub did not answer"*. `update.fetch` marks the refusal, the check answers NONE with the reason `rate_limited` (still never remembered), and the window and the terminal say *"GitHub asked hato to wait — try again within the hour"* | a 403 with `X-RateLimit-Remaining: 0` and a 429 → the reason; a plain 500 → not; the sentence in both places |
| **12f** | `ui` | **What's new, for the version you have.** Once the *Updated to X* banner is dismissed there was no way back to its notes: a *What's new* link on the Updates line whenever nothing is on offer, to this version's own release page (built from `__version__`, never from an answer) | the link in the no-offer states, absent while something is on offer, and its address |
| **12z** | — | the adversarial pass over Layer 12 → a register; then **release 1.0.5** by `LEDGER.md` §delivery — the first release an install takes on its own | the register; `verify-release`'s `an_install_takes_it` RUNS (min_from 1.0.4) |

> ✅ **12a–12f BUILT 2026-09-24**, each with its checks (`gui_updates` · `update` · `watch`)
> and its mutants (`m12.mjs` M12-01…27); the states shot and LOOKED — two defects found
> only by looking: the footer's own gap sat inside *"hato 1.0.4 │ Created by"* (V1), and
> the wait was cut off by its own link, so every sentence line of the card now WRAPS (V2).
>
> ✅ **12z RUN 2026-09-24 — `ADVERSARY-2026-09-24.md` §*Layer 12*: 21 fixed · 0 dropped · 1
> deferred.** One adversary over the layer (8 reproduced, 6 check-only, 3 suspected), the
> orchestrator's review, a re-shoot LOOKED state by state, and ⭐ a **stamp rehearsal** —
> the suites over a copy stamped 1.0.5 — which found three checks failing and two gone
> vacuous at the next number (T1: fixtures publishing 1.0.5 against the real
> `__version__`). 🚨 The worst were the class 12a was built to close, one level down: a
> stage ANOTHER version prepared read as *ready* for ever — `hand_off` had the wall and
> `staged_version` did not (L12-1); and a window beside the tray asked *"is a check due?"* of
> the file the tray writes too — never due, so it never asked and never read the tray's
> answer (L12-2). Also: a check that could not tell erased an offer on screen (L12-15, the
> review), and the window's voice capitalised the name — *"Hato can't write…"*, in 1.0.4
> already (V3, the re-shoot). `m12` +35 (M12-28…62), 10 re-aimed.
> ⭐ **The gate** (`--scratch`, `^(M11|M12)`, over the vault after the fixes): **303
> mutants, 303 killed, 0 survived** (48 min, `EXIT=0`); M12-62, written after it began, run
> alone: killed; the same filter over the tree BEFORE the fixes had killed 269/269 — every
> finding was a defect no mutant yet described. Stamp `1.0.5` (`sha256:d957e21f…`, 83
> files) → the full runner over the stamped tree: **33 suites / 2,467 checks GREEN**.

---

## Step 6 — Release — ✅ TAGGED AND SHIPPED: `v1.0.4`, 2026-09-24 (`v1.0.3` and `v1.0.2` 2026-09-23, `v1.0.1` 2026-09-19). ⛔ NO PyPI, RULED

> ⭐ **`v1.0.4` IS LIVE — THE FIRST RELEASE THAT UPDATES ITSELF** — LAYER 11, D12 and 10b.
> Stamp `1.0.4` (`sha256:e6a857f5…`, 83 files) → the full runner **33 suites / 2,424 checks**
> over the stamped tree → freeze → smoke **45/45** on the zip unpacked outside the repo, its
> REHEARSAL updating the released 1.0.3 through the new swapper both ways (a version that
> cannot start put back; the new one in WITH its tray — exactly one — saying *Updated to
> 1.0.4*; the frozen splash LOOKED) → `update-manifest` (signed; read back 3/3) → sync →
> `41e1515` → `tests` **12/12 jobs on the FIRST push** → `_release_1_0_0.py --go`: tag
> `v1.0.4` = `41e1515`, THREE assets → `verify-release` **9 held · 1 skipped by design** (every
> published byte identical to the local file; zip `sha256 70664555…7d58`, 77,016,517 bytes;
> GitHub's digest agrees) → `release` **2/2** on the tag. ⭐ The real client against the real
> release, two arms: before publishing a copy numbered 1.0.3 heard `none 1.0.3`; after,
> `tell 1.0.4 too_old` — reached only past the signature and GitHub's digest. Before all of
> it, the Layer 11 gate: 245 mutants, 243 killed, both survivors closed (G1, G2), their
> re-run 33/33.

> ⭐ **`v1.0.3` IS LIVE AND EVERY GATE IS GREEN** — Layer 9. **tsubasa `v0.1.8` first**
> (`5be457c`; CI 16/16, release 4/4, verified from its published bytes and two-arm against
> 0.1.7), because hato's floor rose to it and CI installs the engine from PyPI. Then the
> sequence in `LEDGER.md` §delivery, unchanged: stamp `1.0.3` (`sha256:444c550d…`, 77 files) →
> the full runner **29 suites / 2,055 checks** over the stamped tree → freeze → smoke **29/29**
> on the zip unpacked outside the repo → sync `59a1561` → `tests` **12/12 jobs on the FIRST
> push** → tag `v1.0.3` = `59a1561` → `release` **2/2** → the **published asset downloaded and
> hash-verified** (`sha256 adc8f136…ef0f`, 70,689,311 bytes). Then, on Sonic's go, the full
> mutation gate over the released tree: **943/943** (66 min, `EXIT=0`). ⚠ Found on the way, both in
> `LEDGER.md` §harness: the new `.jp` check folded its own casings on Windows' case-blind
> paths, and its first witness patched a table tsubasa had already merged at import.

> ⭐ **`v1.0.2` IS LIVE AND EVERY GATE IS GREEN** — Layer 8, its adversarial pass and D2.
> Tag `6a2cf25`: `tests` **12/12 jobs**, `release` **2/2**, suite 29 suites / 1,982 checks,
> smoke **29/29** against the copy unpacked outside the repo, and the **published asset
> downloaded and hash-verified** against the local artifact (`sha256 6dc4d797…72615`).
> ⚠ **Its first push, `559f5ce`, was red on 11 of 12 jobs and was never tagged** — four
> checks that assumed Windows and one REAL lock race (`LEDGER.md` §harness, *"IT DID NOT
> TRAVEL AGAIN"*). ⭐ The full mutation gate over the released tree: **849/849** (53 min,
> `EXIT=0`).

> ⭐ **`v1.0.1` WENT LIVE WITH EVERY GATE GREEN** — `tests` 12/12 *(recorded as 13/13 until
> 2026-09-23; the run has 12 jobs)*, `release` 2/2 with the
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
