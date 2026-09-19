---
type: spec
title: hato — Test Plan
desc: The suites and what each structurally cannot cover, recorded fixtures, the live-API probe specced ahead of the feature it de-risks, and the three environment answers.
date: 2026-09-07
---

# 07 — Test Plan

> **Every launch feature ships with its test, in the same step.** A test not in the runner
> does not exist, and the runner proves it.

---

## ⭐ The rule that shapes everything here

> ⛔ **The default suite makes ZERO network calls.**

Not "few". Zero. Three reasons, and the first is the one that matters:

1. **jimaku's budget is 25 requests/60s and it is someone else's server.** A suite that
   hits it turns every `pytest` into a withdrawal from a shared resource, and a
   watch-mode loop into an outage
2. A suite that depends on a third party fails for reasons that have nothing to do with
   the code. During spec research **AniList returned 403, Jikan 504 and MAL 403 — all at
   the same time.** A suite wired to any of them would have been red all day
3. It keeps the fast feedback loop fast

**How:** recorded fixtures. See below.

---

## The suites

| Suite | Covers | ⛔ What it STRUCTURALLY cannot cover |
| --- | --- | --- |
| `parse` | Filename → title/episode/season, both parsers, the router | Whether the title exists on jimaku |
| `identify` | Normalization, cache hits, the `anime=false` retry, the empty-query guard | Whether jimaku's fuzzy search still ranks the same way |
| `align_episodes` | Range alignment, per-group splitting, offsets, specials, `.5`, multi-episode refusal | Nothing — this is pure arithmetic over fixture data, and it is the highest-value suite here |
| `rank` | AI filtering, ⭐ **`.ass` first** (a `[CHS, JPN]` `.ass` over a `[JPN]` `.srt`), single- vs multi-language **within a format**, offset confidence, ties | Whether the top-ranked file is *actually* the best subtitle. **Only the timing verdict knows** |
| `client` | Request shaping, headers, 429/401 handling, retry ladder, pagination | Whether jimaku's real responses still match the fixtures. **The live probe covers this** |
| `archives` | Extraction, **zip-slip rejection**, size caps, missing `unrar` | Real-world archive variety |
| `existing` | The language reader, flag-token collisions, embedded-track detection, ⭐ **the no-track skip** — zero requests, zero downloads, no refusal row | — |
| `state` | Canonicity rules, negative expiry, refusal recording, corrupt-DB recovery, **re-sync from a kept original** | — |
| `write` | ⭐ **The hand-off**: tsubasa writes `<video>.ja.<ext>` beside the video and leaves the original untouched · kept originals in `subs_dir` · the `.ja` tag on every original · `--out` mirroring · encoding preservation | Whether a media player actually loads it — ⚠ measured once by hand, in Sonic's mpv, 2026-09-17 |
| `endtoend` | A full run against a fixture folder + recorded API + a stub aligner | Anything about the real network or real timing |
| ⭐ `live` | **Opt-in. Excluded from the default run.** See below | — |

⚠ **`rank`'s limitation is the honest one to keep visible.** Ranking decides who goes
first, not who is right. If ranking is wrong, the candidate escalation and the timing
verdict absorb it — which is exactly the design, and the test must not pretend otherwise.

---

## ⭐ Recorded fixtures — the mechanism

**Record once from the live API, replay forever.**

```
tests/fixtures/api/
  search__query_frieren.json          # captured 2026-09-07, HTTP 200
  search__query_empty.json            # the catalogue-dump trap
  search__anime_false_retry.json
  entries_11446_files.json            # 120 files, 5 groups, absolute+seasonal mix
  entries_movie_flag.json
  download__429.headers
  download__401.headers
```

> ✅ **AS CAPTURED, 2026-09-17** — the list above was the plan; this is what exists. Every body
> is the response **byte for byte**, beside a `<name>.meta.json` holding the date, URL, status,
> RESPONSE headers (never a request header) and the body's sha256 — `test_doctor.py` fails if a
> body no longer matches its recorded hash. Three deviations, each forced by a rule that
> outranks the list:
>
> | Planned | Captured | Why |
> | --- | --- | --- |
> | `search__query_empty.json` | `search__query_empty.meta.json` **only** — `entries_returned: 4533` | The body IS the catalogue, and Whitelist 2 forbids mirroring it |
> | `download__429.headers` | ⛔ **not captured** | A 429 exists only past 25 requests/60 s, which Whitelist 2 forbids. The client builds its 429 path from the real headers of the captures below and says so |
> | `download__401.headers` | `search__401_bad_key.json` + meta | A download takes no key, so it cannot 401. The 401 comes from an API call with a deliberately invalid key |
> | — | `search__live_action_anime_default.json` (`[]`) · `search__movie.json` · `entries_invalid_id_files.json` (a 404) · `download__sample.meta.json` · `download__invalid_id.meta.json` | Added: the other half of each trap. ⛔ Download fixtures are **metadata only** — a subtitle body is third-party content |

### 🚨 OPEN GAP, 2026-09-17 — two captures the code writes and the folder does not hold

**A human with the key must run `hato doctor --capture` once to close this.** Found by the
adversarial pass on the client and the probe; recorded rather than filled, because ⛔ **a
hand-written `.meta.json` under `tests/fixtures/api/` claims bytes jimaku sent** and would
turn every offline check into a check on our own guess.

| Stem `doctor` captures | Status | What it is for |
| --- | --- | --- |
| `search__query_sousou_no_frieren` | ⛔ **no file** | What tsubasa's parse of a REAL release name sends as the query. Without it, identification can only be driven offline from `query=frieren` — a string no filename produces |
| `search__no_match` | ⛔ **no file** | A query matching nothing: the path to the `anime=false` retry and the Kitsu fallback, whose checks otherwise run on stand-ins derived from other recordings |

Both were added to `hato/doctor.py` by the 2b builder on 2026-09-17 and `--capture` was never
re-run. ⭐ **The drift cannot repeat silently:** `doctor.CAPTURE_STEMS` is now checked from
both ends by the `doctor` suite — a real capture run must write exactly it, and every stem
must have a fixture **or** a named entry in the suite's written gap register, which may not
name a stem that is present. Re-running the capture forces the register to shrink; adding a
capture without re-running turns the suite red.

| Rule | Why |
| --- | --- |
| ⭐ **Every fixture records the date and the URL it came from** | A fixture with no provenance cannot be re-verified when the API changes |
| **Fixtures are real captured bytes**, never hand-written JSON | A hand-written fixture encodes what you *believed* the API returns. Two of this project's traps — absent-vs-null keys and the group-numbering split — would both have been invisible in a hand-written one |
| ⛔ **Never edit a fixture to make a test pass** | Re-capture it, and if the API changed that is the finding |
| **`entries_11446_files.json` is the crown jewel** | It contains the absolute/seasonal split, 5 release groups, and the `[CHS, JPN]` vs `[JPN]` pair. **Every alignment and ranking case is derivable from this one file** |

---

## Where test data comes from, and what marks it

| | |
| --- | --- |
| **Videos** | ⛔ **No real media in TheForge.** Generate zero-byte or few-KB stub files with real release filenames. The filename is the input; hato never reads video bytes except for the head/tail hash and tsubasa's track read |
| **Filename corpus** | ⚠ **Moved:** `InfiniteVoid/WorldDominationLite/tsubasa-corpus/naming/` — outside the vault — holds the widest sample of real Japanese subtitle filenames there is, plus `catalog.jsonl` (238,250 filenames). `Workshop/jimaku-corpus/` now holds only the scraper and its doc. **The parser itself is tsubasa's, already built and gated** |
| ⭐ **A real video, for the tsubasa contract test** | ⛔ Still never in TheForge. **Build it in a temp dir** with the bundled ffmpeg (`Workshop/media-kit/bin/`): `lavfi` `testsrc` + `anullsrc` + an embedded text subtitle track carrying **enough cues for a CONFIDENT verdict**, plus a shifted copy of those cues as the "download". Measured 2026-09-17: a 6 s, one-cue `.mkv` builds in about a second and mpv reads its tracks — a verdict needs far more cues than one |
| **What marks it as test data** | Everything lives under `tests/`, and the harness sets `HATO_CACHE` and `HATO_CONFIG` to a temp dir. ⛔ **No test may read or write the real cache, the real DB, or the real keystore** |
| **Teardown is verified** | The runner asserts the temp dir is gone **and** that the real cache dir's mtime is unchanged. A teardown nobody checks is a teardown that silently stopped working |
| 🚨 **Two suites can collide through `TSUBASA_CACHE`** | **MEASURED 2026-09-17, at 4b/4c's build.** The harness points `TSUBASA_CACHE` at ONE temp root for the whole run, and tsubasa's results DB keys a record on the **SUBTITLE's content** — two syncs of completely *different videos* against the same cue text wrote the **same record file**, the second overwriting the first. So two suites whose download comes from `_media`'s DEFAULT cue geometry share one record, and whichever runs first claims it — turning `test_port.py`'s *"the store gained exactly one record"* red **inside another suite's file**, the hardest kind of failure to read. `run_tests.py write port` and `pipeline port` were red; `existing port` green; each suite alone green. ⭐ **The rule: any suite that runs the real `tsubasa.sync()` gives `_media.build()` a distinct `count`**, and says in the fixture why — `port` 75, `write` 61, `pipeline` 67 |
| ⛔ **No assertion hardcodes a production count** | Derive from the fixture. `len(fixture)` — never `120` |

---

## ⭐ The live probe — specced ahead of the feature it de-risks

**Everything about jimaku leaves the process, so the suite can only ever prove hato
*asked* correctly.** The other half needs the real thing — and answering it first costs
almost nothing while answering it last can invalidate the client's whole shape.

`hato doctor` — its own deliverable, built **before** the fetch loop.

| Readout | Measured, not assumed |
| --- | --- |
| Key found, and **where** it was read from | keystore path or env var |
| `GET /api/entries/search?query=frieren` | HTTP status |
| **The three rate-limit headers**, verbatim | `limit` / `remaining` / `reset` |
| `GET /api/entries/{id}/files` | file count, and whether keys match the expected shape |
| One unmetered download | HTTP status, byte count, sniffed encoding |
| tsubasa importable, its version, and `tsubasa.self_check()` | ⚠ `self_check().ok` false is a line, not a crash — it names what is missing |
| `unrar` present? | Governs whether `.rar` candidates are offered |
| Cache and config paths, and whether they are writable | — |
| ⭐ **A `--capture` flag** | Writes the responses straight into `tests/fixtures/api/` with today's date. **This is how fixtures get re-captured, so the loop closes** |

> ⭐ **`--capture` is why this works.** The whole round trip can be driven, and the suite
> refreshed, with none of the fetch loop built.

⚠ **`hato doctor` is the only thing in this project that may hit the live API by default,
and it is run deliberately** — the first capture by the build's orchestrator (ruled
2026-09-17), every later one by a human when the API changes. The `live` suite wraps it for CI and is excluded from
`run_tests.py`'s default list, with the reason inline — *not* by discipline, by the
runner's own configuration.

---

## The three environment questions

| Question | Answer |
| --- | --- |
| **What will this be judged on, and how?** | Windows 10, Sonic's laptop, run three ways: `hato <folder>` in a terminal, `hato-run.cmd` double-clicked, and Task Scheduler. ⚠ **All three must be exercised** — the scheduler runs with a different working directory, a different `%LOCALAPPDATA%` resolution in some configurations, and no console. A tool that only ever ran from a developer shell has tested none of that |
| **What cannot be verified locally?** | Whether jimaku's live responses still match the fixtures · whether real subtitle content aligns · whether Task Scheduler's environment resolves the keystore path. The first is `hato doctor`; the second needs real media outside the vault; **the third needs one real scheduled run and is the easiest to forget** |
| **Is a display/scale layer in scope?** | No GUI at launch. The CLI must not assume a colour terminal — ⭐ **detect and degrade**, because the `.cmd` and the scheduler capture output differently and ANSI escapes in a log file are noise |

## The three *code that never runs locally* questions

| Question | Answer |
| --- | --- |
| **Which surfaces do not exist locally?** | None. Everything runs locally. **This is the one class of risk this project structurally does not have** |
| **Which controls render but are inert?** | None since 2026-09-16: tsubasa exists, and the subsync adapter was ruled out. ⚠ **The `sync()` port must still be exercised against the REAL `tsubasa.sync()` by at least one contract test** — a port tested only through its stub proves the stub. ⚠ **And the track reader, until tsubasa's T4 lands** — ⛔ never ship its stub as the real backend |
| **Anything built either/or rather than rendered and hidden?** | The `.rar` path — absent when `unrar` is missing. ⚠ **CI must run at least one job without `unrar`**, or the graceful-degradation branch is never executed |

---

## The three guards

1. ⭐ **Every harness row carries a marker.** Cache and config are redirected to a temp
   dir by the runner itself, not by each test remembering to
2. ⭐ **Teardown is verified**, not assumed — the runner asserts it
3. ⛔ **No assertion hardcodes a production count.** Derive from the fixture

## Registration self-check

`run_tests.py` **enumerates the test files on disk** and fails if any is not in the suite
list. Written down, this rule failed twice on tsubasa's source project and the build still
ended with four orphaned harnesses. **The runner that enumerates is what fixed it
permanently.**
