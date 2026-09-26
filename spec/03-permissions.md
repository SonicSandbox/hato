---
type: spec
title: hato — The Actor and Its Field Whitelist
desc: There are no human roles. There is one non-human actor that writes to a user's media folder and talks to someone else's server, and this is the exhaustive list of what it may do.
date: 2026-09-07
---

# 03 — Permissions

**There are no accounts, no roles and no sign-in.** `04-identity.md` does not exist. There
is one API key, and a key is a credential, not an identity.

There is exactly **one actor** — hato itself. It does two things that need governing:
it **writes to files a person cannot easily replace**, and it **makes requests to someone
else's server**.

---

## 🚨 Whitelist 1 — what it may write to the user's media folder

> ⭐ **14z (A-1) — BEFORE anything is written there, the folder is ASKED, never written to**
> (`paths.cannot_write`: the folder opened for the right a new file needs). A folder that
> denies it is an ERROR before any request — the writer under tsubasa otherwise retried
> for days. ⛔ Never `os.access` on Windows: it reads the read-only attribute, not the
> permissions.

⭐ **AMENDED 2026-09-17 (Sonic): tsubasa writes the synced file; hato keeps the original.**
hato itself writes **nothing** into a media folder.

| MAY do | MUST NEVER do |
| --- | --- |
| Hand a finished original to tsubasa: `sync([(video, original)], write=True)` writes `<video-basename>.<lang>[.flag].<ext>` beside the video under **tsubasa's** whitelist. ⭐ On this explicit path tsubasa **supersedes nothing**, so nothing is trashed | 🚨 **Modify the video file. Ever.** Not tags, not container, not one byte |
| The same under `--out <dir>`, mirroring the source tree — **hato computes each video's mirrored directory** and passes it as tsubasa's `out_dir` | 🚨 **Modify a subtitle hato did not create in this run** |
| Keep every original a synced file was made from in `subs_dir` — temp-plus-rename, **never deleted** | ⛔ Delete anything. **Trash only, via tsubasa** |
| ⭐ **14c:** have tsubasa take a video's own Japanese text track out and WRITE it — `extract_subtitle(video, track, write=True, out_dir=…)` writes `<video-basename>.<lang>.<ext>` under **tsubasa's** whitelist: atomically, the track's own format, never over a file that is there. ⛔ hato never writes those bytes itself | |
| | ⛔ **Write into a media folder itself.** The only write there is tsubasa's |
| | 🚨 **Hand tsubasa an original with no language tag in its name.** Measured 2026-09-17: tsubasa then writes `<video>.ass`, `unpaired(lang="ja")` reads that as *no Japanese subtitle*, and every later run fetches again. Name it `<jimaku stem>.ja.<ext>` |
| | ⛔ **Accept a `subs_dir` inside a scanned folder.** The originals would be discovered as candidates for the videos beside them, and a tsubasa run over that folder could supersede them. Config ERROR at startup |
| | ⛔ Write a **partial** file anywhere in the media folder |
| | ⛔ Write scratch, temp, `.part`, logs or extracted archives beside the media |
| | 🚨 **Convert the subtitle format.** A `.ass` stays `.ass` |
| | 🚨 **Re-encode the text.** Same codec in, same codec out |
| | Create directories in the media folder other than a `--out` target the user named |

### Why "nothing partial" is in red

`subsync` shipped the opposite: `analyze` dropped `_ref_2.ass` and a 500 KB `.npy` next to
the subtitles it was reading — **inside a corpus its own README marked read-only.**

**The rule that prevents it:** downloads, archive extraction and alignment all happen in
the working cache. The media folder sees exactly one filesystem operation per success —
**tsubasa's** atomic write of a finished file.

⚠ **Atomic means temp-plus-rename, never truncate-in-place.** `open(path, 'w')` truncates
the moment it opens; if the write then raises, the file is **zero bytes**. This destroyed
`tsubasa/spec/RUNBOOK.md` on 2026-09-07 and it is in the hot ledger for that reason.

---

## 🚨 Whitelist 2 — what it may do to jimaku's server

hato is a client against infrastructure run by someone else for free, with **no ToS and no
attribution requirement**. That makes restraint a design constraint, not a legal one.

| MAY | MUST NEVER |
| --- | --- |
| `GET /api/entries/search` — **1 call per unresolved show** | ⛔ Exceed 25 requests / 60 s. **Failed requests count** |
| `GET /api/entries/{id}/files` — **1 call per show**, no `episode=` param | ⛔ Send an empty `query` — it returns the entire catalogue |
| `GET /entry/{id}/download/{name}` — unmetered, unauthenticated | ⛔ **Scrape the HTML site.** `robots.txt` is `User-agent: * → Disallow: /` for everything that is not a named search engine. **The key-gated API is the sanctioned path** |
| Re-request after a documented expiry | ⛔ Re-query a show the negative cache says to leave alone |
| | ⛔ Enumerate or mirror the catalogue |
| | ⛔ Redistribute downloaded subtitle content |

### The rate limiter, concretely

**Verified live 2026-09-07:** `x-ratelimit-limit: 25`, plus `x-ratelimit-remaining` and
`x-ratelimit-reset`.

- **Read the headers and obey them.** Do not model the budget locally and hope
- On **429**, honour `x-ratelimit-reset-after`. Both it and `reset` may be fractional
- 🚨 **A 401 still consumes quota.** A bad key burns the budget silently — fail loudly on
  the first 401 and stop, rather than retrying 24 times
- ⭐ **Never use a constant delay.** A request every 1.500 s forever is a strange shape in
  someone's access log. jimaku-corpus jitters its waits; do the same

---

## The three outcomes — plus one this tool needs that tsubasa does not

Every video resolves to exactly one. **There is no fifth, and no silent success.**

| Outcome | Means | Action |
| --- | --- | --- |
| **CONFIDENT** | Fetched, aligned, the timing holds, **and tsubasa wrote the file** | Written beside the video by tsubasa; the original kept in `subs_dir`. ⛔ CONFIDENT with no `output_path` is an ERROR |
| **REFUSED** | Fetched, but the alignment is not trustworthy | ⛔ **Not written.** Reason stated. Recorded against the subtitle's hash so it is never re-downloaded |
| **ERROR** | Could not be read, parsed, or extracted | ⛔ **Not written.** Reason stated |
| ⭐ **NOT_FOUND** | The source has nothing for this episode | ⛔ **Not an error.** Reason stated, with the date it will be retried |

🚨 **NOT_FOUND and ERROR must never be conflated.** *"jimaku has no episode 7"* is a
normal, expected, recurring state that resolves itself when someone uploads one.
*"the download returned 500"* is a fault. `subsync` was bitten twice by exactly this class
of confusion — a real failure disguised as a different one, both times.

🚨 **And REFUSED must never be conflated with NOT_FOUND.** A refusal means *we found
something and it was probably the wrong thing* — which is a signal that the
**identification** may be wrong, not the availability.

⭐ **"No subtitle track" is a SKIP, not a fifth outcome** *(ruled 2026-09-17)*. It is decided
before anything is fetched, so there is nothing to have refused — and recording it as a
refusal would blacklist a good subtitle for when tsubasa can sync from audio.

---

## The hand-back path

A refusal is only useful if a person can act on it. Every non-confident outcome states:

1. **What was measured** — match percentage and the verdict word, from tsubasa
2. **Why it fell short** — which guard failed, in plain language
3. **What would change it** — a retry date, a `--candidates` bump, or an explicit pair

*"It failed"* is not actionable and is not acceptable output.

Per the ruled surface: **problems surface FIRST**, above the successes. The one thing
needing attention never sits below 23 things that worked.

---

## Does anything here contact a person?

**No.** No email, no push, no telemetry. **Phone notifications on scheduled runs were
ruled out by Sonic on 2026-09-07** — so that entire class of risk, including the
documented case of a test suite sending real notifications from fixtures, is absent by
construction.

⚠ **But hato reaches a third party's server**, which the suite must not do casually. See
`07-test-plan.md` — **the default suite makes zero network calls**, and the one live probe
is opt-in and excluded from it.

---

## The read rule, in pseudocode

So the builder implements one thing rather than inferring it from cells.

```
clashes = one_target_per_video(discovered_videos)  # ⭐ (target dir, video STEM), across the WHOLE run

for video in discovered_videos:
    target = target_dir(video)                                  # the video's own dir, or --out's MIRROR of it
    if video in clashes:                         return REFUSED(names_the_other_video)
                                                 # ⛔ BEFORE the present-check: once one of the two has been
                                                 # written for, *present* is true for BOTH and the loser reads
                                                 # the winner's file as its own — measured, see the table below
    if sidecar_exists(video, lang, target):      return SKIP("subtitle already present")  # opens nothing
                                                 # 🚨 under --out the earlier file is in the MIRRORED dir, never
                                                 # beside the video — measured at 4a: miss it and hato re-fetches
                                                 # every run and tsubasa refuses the write for ever
    if db.blacklisted(video):                    return SKIP("blacklisted by you")  # ⛔ --force does NOT override
    tracks = track_reader(video)                                # T4, tsubasa's public reader
    if has_text_track(tracks, lang):             return SKIP("embedded track present")
    if not tracks:                               return SKIP("no subtitle track, can't sync yet")  # ⛔ never a refusal
    if db.negative(video) and not force:         return SKIP("no source, retry after D")
                                                 # ⚠ HARD **or** SOFT, unexpired. Checking only the hard one
                                                 # re-lists the entry's files every run for an episode jimaku
                                                 # does not have yet — the cost the negative cache exists to stop

    kept = kept_original_for(video)                             # subs_dir, zero network
    if kept and format_taken(kept):              return resync(video, kept)  # the synced file was deleted
                                                 # ⚠ 9a (ADVERSARY 2026-09-23 #3): only in a format the
                                                 # person's settings still take -- `.ass` kept, `.srt` chosen
                                                 # and the `.ass` deleted re-timed the `.ass` straight back,
                                                 # and the present-check then said "already there" for good

    entry = resolution_cache.get(title) or resolve(title)      # <= 2 API calls, cached
    if not entry:                                return NOT_FOUND(record_hard_negative)

    files = files_cache.get(entry) or list_files(entry)        # 1 API call, no episode=
    cands = rank(align_by_group(files, video_range))           # .ass first
    cands = [c for c in cands if not db.tried(c.hash)]         # never re-fetch a refusal

    for c in cands[:candidate_cap]:
        path   = download_to_cache(c, tag=lang)                # unmetered; "<stem>.ja.<ext>" REQUIRED
        result = sync(video, path, write=True)                 # the port: tsubasa writes <video>.ja.<ext>
        if result.outcome == CONFIDENT:
            if not result.output_path:                         # CONFIDENT is not WRITTEN
                return ERROR(why_nothing_was_written(result))
            keep_original(path)                                # temp+rename into subs_dir, never deleted
            return CONFIDENT
        db.record(c.hash, result.outcome, result.reason)

    db.record_soft_negative(video, "all %d candidates refused by timing" % len(cands))
    return REFUSED(reason_of_best_attempt)       # ⚠ but see ESCALATION below -- a whole show refused is
                                                 # evidence about the ENTRY, not about the subtitles
    # ⭐ ESCALATION, once per show, added 2026-09-17 after a live run. jimaku keeps ONE
    # ENTRY PER SEASON, and a name with no season in it ties them all, so a LOW CONFIDENCE
    # pick can easily be the wrong season. Two shapes, both measured on a real library:
    #
    #   the entry offers NOTHING for any video   -> try the next entry the search scored
    #   every candidate is REFUSED by timing     -> same, and only ADOPT it if one wins
    #
    # `Re Zero … - 52/54/55` resolved to entry 332 (season 1), which offered five wrong
    # candidates per video; all fifteen were refused. Escalating found **7615, 3rd Season**
    # and wrote all three, at 80%, 57% and 63%. ⛔ Bounded to ALTERNATE_ENTRIES, ⛔ never
    # for a movie entry or a confident pick, and ⭐ the resolution cache is REPOINTED at
    # whatever worked, so the extra call is paid once per show rather than every run.
                                                 # refused re-lists the entry on every run to learn nothing new
```

⛔ **Note what is NOT in that loop:** no network call inside the candidate loop except the
unmetered download, and no metered call at all once the caches are warm.

⚠ **AMENDED 2026-09-16 — the port is `sync()`, not `align()`.** This loop read
`align(video, path)`, and `tsubasa.align` is a different function: the low-level aligner
over two arrays of cue-start times. A builder reading *"tsubasa's align()"* would have
called it with two paths. Behind the port, tsubasa's adapter is
`tsubasa.sync([(video, path)], write=True)`, and `sidecar_exists(video, lang)` is
`scan.unpaired(lang=...)` — both public as of tsubasa 0.1.0 (`10-deployment.md`).

🚨 **PART 1 DEFECT, MEASURED BY THE BUILD 2026-09-17 — `sidecar_exists` is NOT `scan.unpaired(lang=)`.**
The equivalence above was checked against a one-show scan. Against the real engine
(orchestrator probe, zero-byte stubs, tsubasa 0.1.3 checkout):

| Library | `unpaired(lang="ja")` says | Truth |
| --- | --- | --- |
| `Alpha Show - 01 (1080p).ja.ass` + `Alpha Show - 01.mkv` + `Bravo Tale - 01.mkv`, one folder | Bravo 01 **covered** — offered Alpha's `.ja.ass` at identity score **0.0** | Bravo 01 has no subtitle |
| the same in sibling folders `Alpha Show/` `Bravo Tale/`, and with `S01E01` names | Bravo 01 **covered** | Bravo 01 has no subtitle |
| `Show - 02.mkv` + only `Show - 02.ja.forced.srt` | **covered** | `06-edge-cases.md` §6: *a forced sub is not a full sub* |

The episode index offers every same-numbered subtitle in the walk — correctly, for tsubasa,
whose timing then decides — so *"no Japanese subtitle was offered"* is a much weaker fact than
*"this video has its Japanese subtitle"*. In a real library one show's episode 1 would stop hato
ever fetching episode 1 of every other show, **silently and for good.**

⭐ **Ruled for step 4b (orchestrator, build time):** a subtitle is PRESENT for (video × lang) only
when a subtitle **in the video's own directory** parses (`tsubasa.parse_subtitle_name`) to that
`lang`, is **not forced**, and has a **stem equal to the video's basename** — the canonical
`<video>.<lang>[.flags].<ext>` every player loads. Names only; nothing opened. The asymmetry that
decides it: a false *present* is a permanent silent never-fetch, a false *absent* is one download
and a visible duplicate that is never overwritten (tsubasa's explicit path supersedes nothing).
An un-renamed `[Group] Show - 04 [JPN].ja.ass` therefore does not count, and the fetched copy is
written beside it.

⚠ **THREE MORE GAPS IN THE LOOP ABOVE, ruled for step 4b at build time (orchestrator, 2026-09-17)** —
each is the conservative reading of a rule already in this pack:

| Gap | Ruled | Why |
| --- | --- | --- |
| `track_reader(video)` can answer **"could not read it"** — tsubasa's `embedded_subs(...).ok is False` (e.g. a non-Matroska container with no ffmpeg on PATH). `.tracks` then RAISES | **ERROR, before any download**, with tsubasa's reason verbatim (it names the fix). ⛔ Not a refusal row. Zero requests | tsubasa's `sync()` reads the same container, so a download would only reach the same ERROR afterwards — Rule 2, the network is metered. ⚠ tsubasa's own RUNBOOK 3f says a fetcher should "fetch as normal" on `ok=False`; that predates hato's no-track skip |
| A video whose only tracks are **neither text nor bitmap** (a codec tsubasa's allow-lists do not know) | Same SKIP as no track: *"no usable subtitle track — can't sync yet"*. ⛔ Never a refusal | tsubasa has nothing it can time against; the rule's intent, not its letter (`if not tracks`) |
| The loop checks only `db.hard_negative` — a **soft** negative (*entry exists, no file for this episode*, 7 days) is never consulted, so every run re-lists files for a NOT FOUND episode | `db.negative(video)` — hard **or** soft, unexpired — skips with its retry date, unless `--force` | `02-data-model.md` §*Question 2*: without it a nightly run re-queries forever, the failure the negative cache exists to stop |
| A video whose **every** candidate has been refused re-lists the entry's files on every run to find nothing new to try | When the candidates run out with no CONFIDENT, record a **soft negative** too (*"all N candidates refused by timing"*) — so the next listing waits 7 days for a new upload | The cost model: *"N stats + one DB read"* on a run where nothing changed. A refused video would otherwise cost one metered call per run, for good |
| `--dry-run`: `01-scope.md` says *"zero network calls beyond identification"*, while the ruled Mode B mock shows **6 API calls for 3 shows** and a subs count per show | **Identification includes the file listing** — ≤ 2 metered calls per show (search + files), each at most once per run. Nothing is downloaded, nothing written, no row recorded | The ruled mock is the interface; the count it shows is only reachable by listing files |
| 06 §1: a **LOW CONFIDENCE** identification *"raises the candidate cap"* — by how much is not said | The cap for that show is `candidates + 2`, and the output says so | A value, not a shape; the timing verdict still decides |

⭐ **MEASURED AT 4a's BUILD (2026-09-17, the port builder)** — three things this pack does
not say, each answered against the real engine rather than reasoned about:

| Gap | Ruled / recorded | How it was found |
| --- | --- | --- |
| `tsubasa.sync(results=)` — its results DB. This pack never names the argument, and its three values are not interchangeable | ⭐ hato passes **`results=None`** (the real per-user store), **explicitly**. `pipeline._sync_plan` — the explicit-pair path, the only one hato uses — *"records, and it never skips"*, so the store can never settle a pair hato asked about and return no `Result` at all; and the record is what stops a later `tsubasa <folder>` re-reading the container and re-aligning the file hato just placed. `results=False` would record nothing. It is passed explicitly so a change of tsubasa's default is a visible diff, not a silent change in someone's media folder | Pinned twice in `test_port.py`: the call, and the store gaining **exactly one** record on the real run |
| ⛔ *"CONFIDENT with no `output_path` is an ERROR"* is one row in the table above, and it is **TWO shapes** | `write_failed=False` → a **dry run**; nobody asked for bytes. `write_failed=True` → the write was attempted or blocked and **did not land**, and tsubasa's `reason` opens `NOT WRITTEN:` and names the fix. ⛔ **5a must not print one line for both** — *"you asked for a dry run"* and *"it could not be written"* are different sentences, and `write_failed` appears nowhere else in this pack | Measured on the real engine, both shapes: `write=False`, and a destination that already existed |
| 🚨 `sidecar_exists(video, lang)` looks in the **video's own directory** (ruled above) — but under `--out` the previous run's file is in the **mirrored** directory | ✅ **CLOSED AT 4b/4c's BUILD, 2026-09-17.** Was: with `--out` set, the present-check never sees the earlier output, so hato re-fetches the same episode on every run; tsubasa then **refuses** the write (*"already exists and is not one of the files this run accounted for, so writing would destroy it"*) and returns CONFIDENT + `write_failed` + no file, for ever. **Built:** `hato/keep.py::target_dir(video, root, out)` is the ONE answer, asked by the present-check and by the write alike, so the two cannot disagree. Breaking it turns the real-engine `--out` check into an ERROR — watched, and it is the failure above, exactly | Measured: an existing destination is refused, never overwritten |

🚨 **AMENDED 2026-09-17 — FOUR CHANGES TO THE LOOP ABOVE, each a defect the adversarial
pass MEASURED on the write surface.** The read rule is the specification, so a change to it
is a change here and not only in `hato/pipeline.py`.

| Change | What was measured | Ruled |
| --- | --- | --- |
| ⭐ **A NEW FIRST STEP: `if another video targets the same file: return REFUSED`** — checked across the WHOLE run, before any download, naming the other video | Two videos can resolve to one output path three ways: two roots on one command line with `--out` (`mirrored_dir` returns `out` itself for a video in the root, so both flatten); two roots sharing a relative subpath; and with no `--out` at all, `Show - 01.mkv` + `Show - 01.mp4` in one folder. Run 1: A written, B refused by tsubasa. **Run 2: both report SKIPPED — subtitle already present, and B's "subtitle" is A's file** | ⛔ **Refused, not resolved.** hato cannot know which the person meant, and picking one silently condemns the other to a wrong subtitle it will never be told about. ⚠ **BEFORE the present-check**, because once a file exists the present-check answers *yes* for both — the key is (target folder, video **STEM**), since `present.py` matches a sidecar on its stem whatever extension the download had |
| ⛔ **The blacklist is asked BEFORE hato's own episode-span refusal** | A video whose NAME holds two episodes came back as *hato's* refusal even when the person had blacklisted it, so `hato blacklist --list` disagreed with the run | The loop above already says blacklist **second, right after the present-check**. The span refusal is hato's own judgement and costs nothing, which is why it had been slipped above it. ⭐ The person's instruction is not a cost question; it costs one 128 KiB hash |
| 🚨 **A failed WRITE is an ERROR, it stops the candidate loop, and it records NO negative** | A file where the mirrored directory had to go: tsubasa returns `CONFIDENT, write_failed=True`, `match_rate` 1.0. hato reported *"REFUSED — none held (100% match)"* — self-contradicting — and recorded a soft negative *"all refused by timing"*, so run 2 skipped with a false reason and the video went quiet for a day **even after the disk was fixed** | ⛔ *CONFIDENT with no `output_path` is an ERROR* was already the rule and `port.outcome_and_reason` obeyed it; the candidate loop then treated "not CONFIDENT" uniformly. The pair **aligned** — the destination is what failed, and it is the same destination for every other candidate, so escalating cannot help |
| ⚠ **A video that cannot be numbered records a SOFT negative** | `frieren S2.mkv`, a film in a season folder: `episodes.align` refuses it, nothing was recorded, and the entry was re-listed on every run to reach the identical refusal — **measured `[2, 1, 1, 1]` metered calls over four identical runs** | The same rule as *"every candidate refused"* two rows up in the table above: a refusal no row remembers is one metered call per run, for good. ⛔ Still no ATTEMPT row — a REFUSED row must name a candidate and there is none — but a soft negative names only the entry |

⛔ **AND ONE STARTUP REFUSAL GAINED A SECOND DOOR.** *"Never accept a `subs_dir` inside a
scanned folder"* (Whitelist 1) was enforced; **`--out` was not**, and it is the worse of the
two — a kept original keeps jimaku's name, while an `--out` file carries the **video's own
basename**, which is the name a walk pairs on. Measured: `hato D:\Anime --out D:\Anime\Subs`,
then `tsubasa D:\Anime` → `superseded = [...\Subs\frieren S2 - 01.ja.ass]`. Both are now
refused at startup through one exception base, so a third folder cannot be added with its
handler left behind.

⭐ **AMENDED 2026-09-17 (Sonic) — tsubasa writes; hato keeps the original.** This loop had
hato writing (`atomic_write_beside`) while the note above said `write=True`; the ruling
settled it for tsubasa. The loop was also reordered so the cheapest check runs first — a
folder whose subtitles are all present never opens a container — and gained the no-track
skip, the `.ja` tag, the kept-original re-sync, and *CONFIDENT is not WRITTEN*.
`track_reader` is tsubasa's public track reader (RUNBOOK T4).
