---
type: spec
title: hato — Edge Cases
desc: The catalog, by section. Each has a defined behaviour, because a shrug is not a behaviour.
date: 2026-09-07
---

# 06 — Edge Cases

**A shrug is not a behaviour.** Every case below has an answer, and where the answer is
*"refuse and say why"* that is a decision, not a gap.

---

## 1. Identification

| Case | Behaviour |
| --- | --- |
| Filename parses to an **empty** title | 🚨 **Hard ERROR before any request.** An empty `query` scores 100 on jimaku and returns the entire catalogue |
| Both parsers disagree on the title | Try anitopy's first; on no match, try guessit's. Two cheap attempts beat one clever arbitration |
| Search returns **many** entries | Take the top-scored, but ⚠ **if the top two scores are close, mark the show LOW CONFIDENCE** and raise the candidate cap. Do not silently pick |
| Search returns `[]` for a real show | Retry once with `anime=false` — the flag gates **before** the ID match and defaults true. Only then record a hard negative |
| The show is **live action / tokusatsu** | Same path. `anime=false` is what finds it |
| Title is Japanese, filename is romaji (or vice versa) | jimaku matches `name`, `english_name` **and** `japanese_name` in one call. No alias table needed on our side |
| Resolved to the **wrong show** | ⛔ Not detectable here. **The timing verdict catches it** — that is Rule 1, and it is why identification is allowed to be a hypothesis |
| A season folder holds **two different shows** | Group videos by parsed title, resolve each independently. Never assume one folder is one show |
| Two shows normalize to the **same** cache key | Include the parsed season/year in the key. A collision would serve the wrong entry from cache forever |

## 2. Episode alignment

| Case | Behaviour |
| --- | --- |
| Video has **no episode number** (a film) | Movie path — see §3 |
| Entry uses **absolute** numbering, videos are **seasonal** | Range alignment derives the offset. Measured live: entry 11446 spans 1–38 for a 10-episode season |
| Groups within one entry use **different** conventions | 🚨 Align **per release group**. Pooling them produces nonsense — measured, 5 groups on one entry |
| Only **one** video, no range to align against | ⚠ **The known soft spot.** Try the literal number first, then candidates, then refuse. State it in the output |
| Video count ≠ entry file count | Normal. Align on the **overlap**; report the rest as NOT_FOUND |
| Entry has episodes 1–8, folder has 1–12 | Fetch the 8. The other 4 are NOT_FOUND with a retry date. **Not an error** |
| Specials / OVA / NCOP / NCED | Parsers mangle these (anitopy turns `NCOP1` into episode 1). ⚠ **If the parsed type is a special, do not range-align** — try a literal filename match, else refuse |
| **`.5` episodes** (`13.5`) | Match literally on the string. ⛔ Never round or truncate to 13 |
| **`v2` / `v3`** version tags | Strip for matching, keep for ranking — prefer the higher version |
| A file holding **two episodes** (`01-02`) | ⛔ **Refuse. RULED.** Two subtitle files cannot cleanly become one, and a wrong guess writes a half-wrong file |
| A **VIDEO** holding two episodes | ⛔ **Refuse, BEFORE identification — ruled at 4b's build, 2026-09-17.** See the note below: refusing it inside `episodes.align` is too late |
| Candidates in **several formats** | ⭐ **`.ass` first — RULED 2026-09-17.** Even a `[CHS, JPN]` `.ass` over a `[JPN]` `.srt`. Within one format, single-language first |

> 🚨 **DEFECT, MEASURED AT 4b's BUILD (2026-09-17) — a multi-episode VIDEO never reaches
> `episodes.align`'s refusal.** `hato/episodes.py` refuses one correctly, and 06 §1 rules
> that videos are grouped **by parsed title** so one folder can hold two shows. But tsubasa
> 0.1.4 reads `frieren S2 - 01-02.mkv` as title **`frieren 02`** — the second episode number
> is glued into the title — so the video becomes a SHOW OF ITS OWN, is identified on its own
> (one metered call, on a wrong title), and align's refusal is never reached. Measured
> outcome: **ERROR**, which `03-permissions.md` says must never be conflated with a refusal.
>
> ⭐ **Built in 4b:** the fetch loop refuses it on the name, through `hato/tokens.py`'s
> `episode_span` — the same function `episodes.py` uses — after the present-check and before
> the video hash, so it costs nothing and spends no quota.
>
> ⚠ **THE SAME SHAPE, NOT FIXED: a SPECIAL splits a show too.** `frieren S2 - SP1.mkv` reads
> as title `frieren SP1`, so it is identified separately — **one extra metered call per
> special-bearing title**, and its own resolution-cache entry. The outcome is still right
> (jimaku's fuzzy search usually finds the show, and `episodes.py` then matches the special
> literally or refuses it), so it is recorded rather than worked around. It is the same root
> cause as RUNBOOK T1's table: **tsubasa publishes no episode TYPE.** ⛔ Do not write a
> second title parser in hato to paper over it.

## 3. Movies — in scope, RULED

| Case | Behaviour |
| --- | --- |
| Entry has `flags.movie == true` | ⛔ **Skip episode matching entirely.** Every file on the entry is a candidate for the one video |
| jimaku's `episode=` param on a movie entry | Ignored server-side anyway. We never send it |
| Several films in one folder | One video per parsed title. Match on title + year |
| A film with several cuts (theatrical / director's) | ⚠ **The timing verdict is the only discriminator.** Escalate through candidates; refuse if none holds |

## 4. Downloading

| Case | Behaviour |
| --- | --- |
| **429** | Honour `x-ratelimit-reset-after`. It may be fractional |
| **401** | 🚨 **Stop the whole run immediately** and say the key is bad. A 401 still consumes quota — retrying burns the budget silently |
| Download 404s | The file list is stale. Re-fetch the list **once**, then ERROR |
| Download is truncated or empty | ERROR. ⛔ Never write a zero-byte subtitle |
| Download is **HTML** (an error page) | ERROR. Sniff the first bytes — a subtitle never starts with `<!DOCTYPE` |
| Network drops mid-run | Retry 5 s / 15 s / 45 s. After 6 consecutive failures **that never reached a server**, stop and say so — do not grind through 200 files failing individually |
| The same file appears twice on an entry | Dedupe by name before ranking |

## 5. Archives

| Case | Behaviour |
| --- | --- |
| ⭐ **Archives are OFF by default — RULED 2026-09-17** | The person turns them on (`archives = true`, or `--archives`). ⛔ While off, an archive candidate is **skipped with a reason that names the flag** — never silently dropped, and never unpacked |
| Entry offers only a `.zip` / `.7z` / `.rar`, archives ON | Download and unpack **in the cache dir**. RULED |
| `.rar` and no `unrar` binary | ⚠ **Degrade gracefully.** Skip that candidate with a clear reason. Never a crash |
| 🚨 **Archive path traversal** (`../../`) | ⛔ **Reject the entry outright.** Never extract a member whose resolved path escapes the extraction root. This is the classic zip-slip and it is a real attack on user-uploaded content |
| Archive is a **zip bomb** | Cap extracted size and member count. Abort with ERROR past the cap |
| Archive holds a whole season | Extract, then run normal per-episode alignment across its members |
| Archive holds non-subtitle junk | Ignore silently. Junk is expected input |
| Nested archives | ⛔ Do not recurse. One level, then ERROR |

## 6. The existing-subtitle check

| Case | Behaviour |
| --- | --- |
| `<video>.ja.srt` present | SKIP. Zero requests |
| `<video>.en.srt` present, no `.ja` | **Fetch.** The check is per (video × language) |
| `<video>.srt` with no language tag | Language is `und`. ⚠ **Treat as NOT the target language** and fetch — but never overwrite it; the new file gets the `.ja` suffix and both coexist |
| `<video>.Japanese.srt` | Recognise the English display name — Jellyfin and Emby both document it. 🚨 **DEFECT, MEASURED 2026-09-17 (4b's builder) — tsubasa 0.1.4 does NOT.** See below |
| `<video>.chi.srt` | Chinese. 🚨 **Not hearing-impaired.** Whole-token matching only — this is Bazarr's live bug |
| `<video>.hi.srt` | **Hindi.** Parse the language before trimming flags |
| `<video>.ja.forced.srt` only | A forced sub is not a full sub. **Fetch the full one** |
| Video has an **embedded Japanese text track** | ⭐ **SKIP the fetch. RULED.** It is already there and already in sync — zero network, zero alignment |
| Video has an embedded **bitmap** track (PGS/VobSub) | **Not** a text subtitle. Fetch normally — tsubasa times against a bitmap track too |
| Video has **no subtitle track at all** — a raw | ⭐ **SKIP before identification — RULED 2026-09-17.** tsubasa has nothing to time against until its audio path exists. Zero requests, zero downloads, ⛔ **never recorded as a refusal**. Output: *no subtitle track in the video — can't sync yet* |
| The user deleted a subtitle on purpose | It comes back next run — **re-synced from its kept original, zero network**. ⚠ Documented, not a bug — the filesystem is canonical, and a deliberate absence is indistinguishable from a missing one |

> 🚨 **DEFECT, MEASURED AT 4b's BUILD (2026-09-17) — `<video>.Japanese.srt` reads `und`.**
> `tsubasa.parse_subtitle_name` 0.1.4, in three casings (`Japanese`, `japanese`, `JAPANESE`),
> answers `lang="und"` and hands back the stem `Show - 01.Japanese`. So a Jellyfin- or
> Emby-named sidecar reads as **absent** and hato fetches beside it.
>
> ⛔ **hato does not fix it, deliberately.** The language reader lives in tsubasa and a
> second one here would drift (`LEDGER-HOT.md`). It lands on the SAFE side of the
> present-check asymmetry — one unmetered download and a visible duplicate that is never
> overwritten, rather than a permanent silent never-fetch — and it is pinned by
> `test_existing.py::test_the_jellyfin_display_name_is_a_recorded_spec_defect`, which goes
> **red the day tsubasa learns the display name** so this row can be un-flagged.
> **RULED 2026-09-17 (Sonic): leave it here, and send tsubasa the suggestion.** Re-measured
> the same day on **tsubasa 0.1.5** — unchanged, and wider than three casings:
>
> ```
> Show - 01.Japanese.srt        lang=und      Show - 01.English.srt   lang=und
> Show - 01.japanese.srt        lang=und      Show - 01.ja.srt        lang=ja
> Show - 01.JAPANESE.srt        lang=und      Show - 01.jpn.srt       lang=ja
> Show - 01.Japanese.forced.srt lang=und  ⚠ the FLAG is lost with the language
> ```
>
> **The suggestion to pass on, in tsubasa's own terms:** map the English display names onto
> the codes already in `sidecar.py`'s ONE ISO-639 table — it is a second spelling of a
> language it already knows, not a new concept. ⚠ Three constraints, each of which is a bug
> tsubasa already fixed once in the other direction: match **case-insensitively**; match as a
> **whole dot-delimited token**, never a substring (the rule that stops `.chi.` reading as
> Chinese-and-hearing-impaired); and keep `lang_tag` as the person wrote it (`Japanese`)
> while `lang` resolves to `ja`, which is the split `Result` already carries. ⭐ Its own
> dedupe wants this independently: today `Show.ja.srt` and `Show.Japanese.srt` are two
> languages, so neither supersedes the other and both survive a dedupe run.

## 7. State and re-runs

| Case | Behaviour |
| --- | --- |
| Re-run, nothing changed | *N* stats + 1 DB read. **Zero network** |
| DB says synced, file gone | Re-sync from the kept original if it is still in `subs_dir`; otherwise re-fetch. Disk wins |
| File present, DB empty | Skip, backfill the row |
| DB deleted | Everything works. Re-derives from disk |
| DB **corrupt** | ⛔ Do not crash. Rename it aside, start fresh, say so in one line |
| Video renamed | Hash matches, DB row still applies |
| Video **replaced** with a different rip | Hash differs — treated as new. Correct: the timing may differ |
| Two hato processes at once | SQLite WAL + a lock file. Second one exits with a clear message rather than racing |

## 8. Files, encodings and paths

| Case | Behaviour |
| --- | --- |
| 🚨 **Japanese filenames on Windows** | **Hit during spec research.** Windows Python defaults to **cp1252** and `json.load(open(path))` raises `UnicodeDecodeError` on Japanese content. ⛔ **Always pass `encoding='utf-8'` explicitly** — every open, every request decode, and `sys.stdout.reconfigure(encoding='utf-8')` before printing |
| Windows-illegal characters in a jimaku filename | Map to fullwidth twins (`:` → `：`) as jimaku-corpus does. ⛔ Never drop them — it changes the shape |
| `MAX_PATH` overrun | Truncate the stem with a short hash suffix. Never silently fail the write |
| Subtitle is Shift-JIS | 🚨 **Preserve it.** Sniff the codec, write the same one back. A Shift-JIS file decoded with `errors="replace"` had all 346 cues turn to U+FFFD while the ASCII timestamps survived — so the tool said CONFIDENT and wrote perfect timing with no readable text |
| BOM present | Preserve it |
| CRLF vs LF | Preserve it |
| Media folder is read-only or on a full disk | ERROR with the real reason. ⛔ Never leave a partial file |
| Media on a network share | Works. tsubasa's trash falls back to `.tsubasa-trash/` where the OS has none — and on hato's explicit-pair path it trashes nothing |
| ⛔ **`subs_dir` inside a scanned folder** | **Config ERROR at startup.** The kept originals would be discovered as candidates for the videos beside them |
| A kept original's name is **already taken** in `subs_dir` | Same content hash → reuse it. Different content → keep both, the new one under a short hash suffix. ⛔ Never overwrite |

## 9. Concurrency and interruption

| Case | Behaviour |
| --- | --- |
| Ctrl-C mid-download | Cache file is discarded. Nothing beside the media. Safe by construction |
| Ctrl-C mid-write | Atomic rename means the file is either the old one or the new one. Never a hybrid |
| Killed mid-run | Next run re-derives from disk. The DB is advisory |
| Scheduled run overlaps a manual one | Lock file. Second exits cleanly |
