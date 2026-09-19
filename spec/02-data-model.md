---
type: spec
title: hato — Data Model
desc: The five stores (kept originals included), canonicity in one line, the cost model, and the two mechanisms measured against the live API — episode range alignment and candidate ranking.
date: 2026-09-07
---

# 02 — Data Model

No accounts, no server, no rows owned by people. **Five things hold state**, and two of them
are never deleted by hato.

| Store | Keyed on | Lives | Disposable? |
| --- | --- | --- | --- |
| **Resolution cache** — show → jimaku entry | normalized title | per-user app data | yes — rebuildable at 2 API calls per show |
| **State DB** — attempts and refusals | content hash | per-user app data | yes — rebuilding costs re-downloads, not correctness |
| **Working cache** — downloads in flight, refused candidates, extracted archives | content hash | per-user app data | yes — always |
| ⭐ **Kept originals** — the subtitle each synced file was made from | jimaku entry + filename | `subs_dir`, default `<root>\subs\<entry name>\` | ⛔ **Never deleted by hato** — ruled 2026-09-17. Re-downloadable, and the source of a zero-network re-sync |

| 🚨 **The user's subtitle files** — written by tsubasa | path | their media folder | **NO** |

⭐ **`<root>` is hato's own per-user folder: `%LOCALAPPDATA%\hato\`**
(`~/.local/share/hato` elsewhere) — config, key, log, state DB, cache and kept originals all
inside it, and ⛔ **not inside tsubasa's**. `HATO_CACHE` relocates the whole thing. See
`05-interface.md` §*The config file*.

---

## ⭐ Canonicity, in one line

> **The filesystem is canonical for "does a subtitle exist." The state DB is advisory —
> it only ever PREVENTS work, never causes it.**

The consequences, all mandatory:

| Situation | Behaviour |
| --- | --- |
| DB says synced, file is **gone** | **Re-sync from the kept original** if it is still in `subs_dir` — zero network. Otherwise re-fetch. The disk won |
| File is there, DB knows **nothing** | **Skip**, and backfill the DB row. ⚠ **UNREACHABLE AS BUILT — recorded at 4b, 2026-09-17.** 1b ruled that *"the present-skip path never hashes just to backfill"*, and the read rule puts the present-check FIRST precisely so a quiet re-run costs N stats and no 128 KiB reads — so the run never holds the hash a `present` row needs. `state.record_present` is therefore built, tested and **called by nothing**. A backfilled row changes no decision (no kept original → the same re-fetch), so the cost model wins; ⛔ do not add a hash to reach it. **For Sonic: keep the accessor for the window, or delete it.** |
| DB and disk **agree** | Skip. Zero network |
| DB is **deleted entirely** | Everything still works. The next run re-derives from disk and pays for some re-downloads |

⛔ **The DB may never be the reason a file gets written.** If a bug makes it claim
something exists that does not, the worst outcome is a skipped fetch — never an
overwrite.

### What "already exists" means — RULED

**Per (video × language).** An `.en.srt` sitting beside the video does **not** mean the
Japanese subtitle is present. This matches tsubasa's own one-per-(video × language) rule
so the two cannot disagree about what a folder contains.

🚨 **Reading that language correctly is where both reference implementations have live
bugs.** See `08-research.md` §*Existing-subtitle detection*. The two rules that fix them:

1. ⭐ **Parse the language BEFORE trimming flag tokens.** `hi` is Hindi, `fo` is Faroese,
   `sdh` is Southern Kurdish. Only `cc` is collision-free
2. ⭐ **Strip flags as whole dot-delimited tokens, never substrings.** Bazarr's substring
   test makes `Show.chi.srt` Chinese-**and**-hearing-impaired, and `Show.hin.srt` Hindi
   -and-hearing-impaired

⚠ **This reader lives in tsubasa** (it needs it for dedupe) and hato imports it. Write it
once, correctly, there.

---

## The state DB

SQLite, one file, per-user app data. It answers two questions the filename cannot.

### Question 1 — *"have I already tried this, and how did it go?"*

| Column | Notes |
| --- | --- |
| `video_hash` | Head 64 KB + tail 64 KB + filesize. 🚨 **Never hash a whole video** |
| `video_path` | Advisory only — for reporting. The hash survives a rename |
| `subtitle_hash` | Content hash of the **downloaded file**, so the same file is never re-fetched |
| `jimaku_entry` · `jimaku_filename` | Provenance. What was tried |
| `outcome` | `CONFIDENT` · `REFUSED` · `ERROR` · `NOT_FOUND` |
| `reason` | 🚨 Never empty on a non-confident outcome |
| `attempted_at` | Drives negative-cache expiry |

**⭐ The refusal rule — RULED.** When a fetch succeeds but the timing check REFUSES it:

- Record the refusal **against that subtitle's content hash**
- ⛔ **Never re-download the same file.** It failed on its timing, and timing is
  deterministic — a second attempt costs bandwidth to reach the identical verdict
- ✅ **Do try the next candidate** if the entry has one that has not been tried
- `--force` ignores every row in this table
- ⛔ **A video with no subtitle track is NOT a refusal** *(ruled 2026-09-17)*. It is skipped
  before anything downloads and never recorded against a subtitle's hash — a refusal row
  would blacklist a good subtitle for ever, including after tsubasa can sync from audio

> ⚠ **PART 1 DEFECT, resolved at build time 2026-09-17 (orchestrator) — "against that subtitle's
> content hash" alone is the wrong key.** Timing is deterministic for a **pair**, not for a
> subtitle: a file refused against the wrong video (a wrong episode hypothesis) can be exactly
> right for its own video, and a global per-subtitle blacklist locks it out for ever. **Ruled for
> step 1b: a refusal is keyed per (video × subtitle × language).** Before a download a candidate is
> identified by `(jimaku_entry, jimaku_filename, size, last_modified)` from the file list, so
> *"never re-download the same file"* holds with no request; a re-upload (size or
> last_modified changed) is a new candidate. Every row carries `lang`, and a CONFIDENT row
> carries `output_path` and `kept_path` so a deleted subtitle re-syncs from its kept original.
> ⚠ The **resolution cache** is its own store (step 2b), not a table here.

### Question 2 — *"is it worth asking jimaku about this show again?"*

The negative cache. Without it, a nightly run re-queries the API for every show that has
nothing, forever — the exact *"constant redundant operations"* failure the doctrine names.

| Negative | Meaning | Retry after |
| --- | --- | --- |
| **Soft** — entry exists, no file for this episode | ⭐ **AMENDED 2026-09-17 (Sonic).** A just-aired episode is exactly the case to keep checking: *"if there is a video without subs yet (it was just released) so you would try again a day later each time (not soon unless prompted)"* | **1 day** |
| **Hard** — no entry matched at all | The show may still be added later | **30 days** |

`--force` ignores both — and *"unless prompted"* **is** `--force`, or the window's Retry
button on one row.

⚠ **What the 1-day soft negative costs:** one `files` call per day per show that still has a
gap. The resolution stays cached for ever, so it is **1 metered call, not 2**, and a show with
nothing missing makes none at all.

> ⚠ **The spec was silent about WHERE "configurable" lives — built 1c as a constructor
> argument, not a config key.** `state.SOFT_DAYS` / `HARD_DAYS` are the defaults and
> `StateDB(soft_days=…, hard_days=…)` overrides them; a window Retry or a later config key
> passes one number to one place. ⛔ **Not added to `config.toml`:** the schema there is
> closed and refuses an unknown key by name (`05-interface.md`), so a `retry_soft_days` line
> is a spec change for Sonic to rule, not a builder's to invent. `hato state --stat` prints
> both windows, so whatever is in force is visible. A window below 1 day is refused — it
> would re-ask jimaku about the same gap on every run of the day.

### ⭐ Question 3 — *"has the user said never to fetch this one?"* — ADDED 2026-09-17

The blacklist. Sonic: *"there is a video in there that doesn't need / won't have subs, that
you could easily blacklist it."*

| Column | Notes |
| --- | --- |
| `video_hash` | The same head + tail hash. Survives a rename |
| `video_path` | Advisory, for display |
| `added_at` · `note` | When, and why if the person said |

- ⛔ **It may only ever PREVENT work**, like every other row here. Checked in the read rule
  **before the container is opened**, so a blacklisted video costs one hash and nothing else
- **Reversible from the CLI and from the window** — removing the row is all it takes
- ⚠ **`--force` does NOT override it.** `--force` overrules *the tool's* judgement; a
  blacklist is *the person's* instruction, and overriding that is a different thing entirely.
  `hato blacklist --remove <video>` is the way back

> ✅ **BUILT 1c, 2026-09-17.** Table `blacklist` in the state DB (schema **1 → 2**; an older
> file gains the table on open and keeps its rows). State API: `blacklist_add` (idempotent —
> re-adding keeps the FIRST `added_at`, and an empty note never wipes one that is there) ·
> `blacklist_remove` · `blacklist_list` · `blacklisted(video_hash)`, the lookup the fetch loop
> calls before the container is opened.
>
> ⭐ **The force rule is a property of the code, not of its callers:** `skip_reason(video_hash,
> lang, force=False)` checks the blacklist FIRST and does not look at `force` until after it,
> so a fetch loop cannot get the order wrong. It answers `Skip(kind, reason, retry_after)`
> with `kind` in `blacklist` / `negative`, or None. ⚠ **The blacklist is NOT per language** —
> *"this video won't have subs"* is about the video.
>
> CLI: `hato blacklist <video> [--note "…"]` · `--remove <video>` · `--list [--json]`. The
> video is named by path and stored by hash, so a rename finds the same row; ⚠ a removal falls
> back to the recorded path when the file is gone, because a row the person wants off cannot
> be held hostage by a deleted file. `--list` creates no DB where there is none.

---

## ⚠ The cost model

| | |
| --- | --- |
| **Cost when nothing changed** | *N* stats + one DB read. **Zero network calls.** A folder whose subtitles are all present makes no request at all — identification is never even reached |
| **Cost at 10× the data** | Linear in **file count**, not bytes. Resolution is cached per **show**, so 10× the episodes of the same show costs the same 2 API calls |

🚨 **The expensive shape is many different shows, not many episodes.** *"A few a day from
different series"* is the worst case for quota and the best case for the resolution cache
— each show pays 2 calls once, then never again.

---

## ⭐ Identification — the resolution chain

```
filename
  → parse (anitopy, guessit fallback)        → title, episode, season hints
  → normalize                                 → strip group tags, resolution, codec, CRC32
  → [cache hit?] ──────────────────── yes ──→ jimaku entry id.  ZERO API calls
  → jimaku  GET /api/entries/search?query=   → 1 call
  → [no match] → Kitsu fuzzy → AniList id → jimaku ?anilist_id=   → 2 calls, rare
  → cache the result, keyed on the normalized title
```

⭐ **jimaku's own fuzzy search is the primary path**, not AniList. Reasons, all measured:

- It costs **1 call and no third party**. It matches `name`, `english_name` **and**
  `japanese_name`, so a Japanese filename resolves directly
- **Verified live 2026-09-07:** `?query=frieren` → `Sousou no Frieren` first,
  `Sousou no Frieren 2nd Season` second
- 🚨 **AniList's search is token-exact, not fuzzy.** `Sousou no Friern` (one typo) →
  **0 results**. A release filename → **0 results**. It is a confirmer, never a discoverer
- AniList's ToS prohibits *"hoarding or mass collection"*, which a library sweep sits
  close to. jimaku has **no ToS at all**

### 🚨 Three traps in the search call

1. **`anime` defaults to `true` and gates BEFORE the ID match.** A live-action or
   tokusatsu entry returns `[]`, not an error. **Retry with `anime=false`**
2. ⛔ **An empty `query` scores 100 and returns the entire catalogue.** An empty
   normalized title must be a **hard error**, never a request
3. **Optional fields are absent keys, not `null`** (`skip_serializing_if`). Use `.get()`

---

## ⭐ Episode alignment — the mechanism, measured

**The problem, seen live.** Entry 11446 is *Sousou no Frieren 2nd Season*. Its 120 files
carry episode numbers spanning **1 to 38**, with only 20 distinct values — because
different release groups number the same episodes differently. Some restart at 1 for the
season; others continue the absolute count from season 1.

⛔ **You cannot tell which convention a file uses from the file alone.** This is the same
finding that makes the whole TVDB/XEM stack necessary for media servers.

⭐ **But hato does not need that stack, because it can see both sides.** It has the entry's
whole file list *and* the user's whole folder. Two integer ranges:

```
videos on disk        1  2  3 …  10
group A's files      29 30 31 …  38     → offset 28
group B's files       1  2  3 …  10     → offset 0
```

**The algorithm:**

1. Group the entry's files **by release group** — the bracketed prefix
2. For each group, extract its episode numbers into a sorted range
3. Align that range against the video range; the offset is the difference
4. **A group whose range length matches the video count and aligns cleanly is a strong
   hypothesis.** Several groups producing different offsets is fine — they all become
   candidates

🚨 **Do the grouping per release group, not across the whole entry.** Measured on entry
11446: five groups (`Haruhana`, `KitaujiSub`, `NanakoRaws`, `Nekomoe kissaten&LoliHouse`,
`shincaps`), and the numbering convention is **not consistent between them**. Aligning the
pooled set produces nonsense.

> ⚠ **PART 1 DEFECT, found by the build's capture 2026-09-17:** entry 11446 has **20 files with
> no bracketed prefix at all** — two releases (corrected by the 3a builder, who read all 20):
> **10 Amazon** (`葬送のフリーレン.S02E01.じゃあ行こうか.WEBRip.Amazon.ja-jp[sdh].srt`) and **10 Netflix**
> (`….S02E31.好きな場所.WEBRip.Netflix.ja[cc].srt`). *"The bracketed prefix"* gives every such file the
> same empty group, so they would be pooled — the exact failure this section forbids. **Built in
> 3a:** an unbracketed file's group is derived from its distributor/source tokens
> (`WEBRip.Amazon.ja-jp[sdh]`, `WEBRip.Netflix.ja[cc]`), and a file whose group cannot be told apart
> is aligned **alone**, never pooled. ⚠ Amazon's `S02E06.第34話` reads as absolute 34, and Netflix
> reads season 2 with ABSOLUTE numbers — so parts are split by release and by the season value
> read, and fitted on the numbers alone.

### Where this breaks, stated honestly

**A single video file with no folder to derive a range from.** There is no second range to
align against. That case falls through to candidate escalation and the timing verdict.
Write it down rather than pretending otherwise — it is the known soft spot.

---

## ⭐ Candidate ranking — load-bearing, not a backstop

🚨 **This is where hato differs most from tsubasa.** Sonic's note there — *"most people
won't have multiple subs of the same show"* — makes ranking a robustness backstop.
**Here, multiple candidates is the norm on every single episode.**

**Measured on entry 11446:** every episode number had **4 candidates** *(⚠ re-measured by the build
2026-09-17 after per-release range alignment: **12 files from 7 releases per episode**)*, from 5 release
groups, 120 files for one season.

Ranking, in order:

1. ⛔ **Not AI-generated.** Skip anything matching `whisper` / `whisperai` in the filename
   by default. Whisper output has plausible timing and hallucinated text — actively
   harmful for study. `--allow-ai` overrides. ⚠ **A filter, not a rank** — an AI-generated
   `.ass` is still excluded
2. ⭐ **`.ass` over every other format — RULED 2026-09-17.** Sonic: *"prioritize .ass above
   all else. even if it has chinese, i'd prefer .ass subs over srt."* **A `[CHS, JPN]` `.ass`
   outranks a `[JPN]` `.srt`.** After `.ass`: `.ssa`, then `.srt`, then everything else
3. ⭐ **Single-language over multi-language, within a format.** Measured, across two
   independent groups: `…[CHS, JPN].ass` (104,571 B) and `…[JPN].ass` (49,646 B) are the
   same episode. **The dual-language file is roughly double the size and interleaves
   Chinese.** Prefer the `[JPN]`-only file
4. **The offset hypothesis with the cleanest range alignment**
5. Higher cue count and wider runtime coverage — proxied by file size *within* a format and
   a language class, never across one (an `.ass` carries style headers an `.srt` does not)
6. Tie → prefer a group already seen to succeed for this show

⚠ **Rank, then escalate.** The ranking picks who goes first; the **timing verdict decides
who wins.** `--candidates N` caps how many get tried (default 3). Downloads are unmetered,
so escalation costs bandwidth only.

---

## Does any record own a file?

**Yes — two, and they have opposite rules.**

| File | Owned by | Rule |
| --- | --- | --- |
| A download in flight, or a refused candidate, in the cache | hato | Disposable. Delete freely |
| ⭐ **A kept original, in `subs_dir`** | hato | ⛔ **Never deleted by hato** — ruled 2026-09-17 |
| The synced subtitle, beside the video — **written by tsubasa** | **the user** | 🚨 Everything in `03-permissions.md` applies |
