# -*- coding: utf-8 -*-
u"""
What still needs a person -- the open problems hato remembers, checked against
the disk (RUNBOOK 8c; HANDOFF.md §4a).

    rows = problems.open_problems(cfg, db, cache)
    # [{"type": "video", "source": "memory", "outcome": "REFUSED",
    #   "tried_before": [...], "retry_after": "...", ...}, ...]

===========================================================================
🚨 WHY THIS EXISTS: A PROBLEM EPISODE VANISHED FROM "NEEDS YOU"
===========================================================================

The window painted Needs you from `last-run.json`, and that file is a
SNAPSHOT of ONE run on purpose -- a 3 a.m. run overwriting it is a feature, and
⛔ it is not to be made cumulative. So an episode whose every file was refused
disappeared the moment a run looked somewhere else, and the pick a person was
offered yesterday was gone today. This is the store that outlives a run: a
VIEW over the state DB, filtered by the filesystem.

===========================================================================
⭐ THE DB PROPOSES, THE DISK DECIDES
===========================================================================

`StateDB.problems()` never looks at the disk. A problem it proposes is listed
only while ALL of these still hold, each asked of the filesystem:

    under a configured folder          `paths.under_any`, component-wise
    and not under a skipped one        the run drops those too (RUNBOOK 7e)
    no subtitle present for it         `present.Presence`, in the folder
                                       `keep.target_dir` names -- beside the
                                       video, or `--out`'s mirror of it
    the file is there, and is the      its head+tail hash still equals the
    SAME video                         row's. A different rip at the same path
                                       is a different video: the next run
                                       decides it, not this view
    not left to its own Japanese       while `skip_embedded` is on, a video
    track                              carrying one is what the next run
                                       SKIPS -- it needs nobody (Z14-4)

⚠ ADVISORY IN ONE DIRECTION ONLY. The DB may say *problem* while the disk says
*resolved*; the disk wins and the row is simply not listed.

===========================================================================
⛔ A READ. NOTHING IS WRITTEN, NOTHING IS REQUESTED
===========================================================================

No DB row -- not even the backfill a run makes when it finds a subtitle -- no
file, no cache entry, no request (`LEDGER-HOT.md`: the state DB may only ever
PREVENT work). What is read: the state DB, one directory listing per folder,
128 KiB of each video that survives it, a stat per remembered file, and
tsubasa's `scan()` -- once per folder, and it opens nothing. ⭐ And while
`skip_embedded` is on, the track list of each video still standing -- the
container's header, the question a run asks of every video (Z14-4).

===========================================================================
⭐ THE SHAPE IS THE RUN'S, BY CONSTRUCTION
===========================================================================

Each row is `report.as_dict` of a `pipeline.VideoResult` -- the function a
run's `--json` goes through -- so the window can merge the two with no second
copy of the field names to drift. Two keys are added: `source` is `"memory"`,
so a consumer can always tell a remembered row from a live one, and
`newest_offered` (RUNBOOK 8f). `attempts` is empty -- it means THIS run, and
there is no run here -- and `candidates_offered` is None, because how many
files the entry offered is not something the DB holds. `tried_before` carries
every file tried since the video last succeeded, each with its file as it is
on disk now, or `path: null` when it is gone -- and a gone one is still listed.

The outcome is the latest row's, with ONE translation. A NOT_FOUND that follows
tried files is the soft negative `_all_refused` records once every file it
downloaded was refused, so that episode is a pick waiting for its retry:
REFUSED. With nothing tried, it stays NOT_FOUND. ⚠ Except a FORMAT wait (9a),
which stays NOT_FOUND whatever was tried before it.
"""
import os

import tsubasa

from hato import cache as _cache, episodes, formats, keep, paths, pipeline, present, report, state

#: `source` on every row this module makes. ⭐ A run's rows and these are merged
#: into one list (RUNBOOK 8e); this is how a consumer tells them apart.
SOURCE = u"memory"


def open_problems(cfg, db, cache, now=None):
    u"""-> [row], every open problem the disk still agrees with, in reading order.

    `cfg`    a `config.Config`: its folders, skipped folders, `lang` and `out`
    `db`     an open `state.StateDB`. ⛔ Only read
    `cache`  a `cache.Cache` -- where `keep.remembered_file` finds each file
    `now`    accepted for the caller's clock and deliberately NOT read: every
             value in a row is absolute (an ISO date), so the view is the same
             whenever it is taken. *"in 14h"* is the command's wording.

    Sorted by (title casefolded, season or 0, episode or 0, path).
    """
    look = present.Presence(cfg.lang)
    # 🚨 THE RESOLVED TAG, NEVER THE CONFIG'S SPELLING. A run records rows under
    # `look.lang` -- `jpn` becomes `ja` -- so asking the DB with the raw setting
    # found nothing, and every remembered problem vanished for anybody who wrote
    # `lang = "jpn"`, the spelling hato's own error message suggests
    # (ADVERSARY 2026-09-22 F1).
    lang = look.lang
    out = cfg.out or None
    kept = []
    for problem in db.problems(lang):
        video = _on_disk(problem.video_path) if problem.video_path else None
        if not video:
            continue                    # no path was recorded: nothing to look at
        problem = problem._replace(video_path=video)
        root = _root(video, cfg.folders)
        if root is None:
            continue                    # outside every configured folder
        if paths.under_any(video, cfg.skip_folders):
            continue                    # inside a folder the person skips
        if look.find(video, keep.target_dir(video, root, out)) is not None:
            continue                    # ⭐ resolved on disk -- and the DB is not told
        if not _same_video(video, problem.video_hash):
            continue                    # gone, unreadable, or a different rip
        # ⚠ LEAVE only: under *Save them beside the video* (14c) the next run takes
        # them out -- or downloads, and the row is a real one until it does.
        if formats.embedded_choice(cfg.skip_embedded, cfg.extract_embedded) \
                == formats.EMBEDDED_LEAVE and _left_inside(video, lang):
            continue                    # ⭐ Z14-4 -- the next run leaves it alone
        kept.append(problem)
    parsed = _parsed(p.video_path for p in kept)
    # ⭐ 14z (C4) -- UNDER *Save them beside the video*, WHY IT WAS NOT TAKEN OUT. The
    # run's row said so and the DB never held it, so once the run was over every
    # remembered row -- the pick, both strips -- said nothing. From the header
    # (`pipeline.why_not_taken`): these rows are asked for often, a walk costs seconds.
    saving = formats.embedded_choice(cfg.skip_embedded, cfg.extract_embedded) \
        == formats.EMBEDDED_SAVE
    rows = [_row(p, parsed.get(paths.normalised(p.video_path)), lang, cache,
                 _why_not_taken(p.video_path, lang, cfg.prefer_format) if saving
                 else None)
            for p in kept]
    rows.sort(key=_order)
    return rows


def _on_disk(video):
    u"""The spelling the filesystem holds for `video` now. -> path

    ⚠ A file renamed by CASE ONLY keeps the old spelling in the DB, and the
    present-check matches subtitle names case-sensitively -- so a subtitle saved
    beside it under the new spelling was never found, and the row asked for
    ever (ADVERSARY 2026-09-22 F15). One listing of its folder answers it.
    """
    folder, name = os.path.split(video)
    try:
        entries = os.listdir(folder or u".")
    except OSError:
        return video
    if name in entries:
        return video
    folded = name.casefold()
    for entry in entries:
        if entry.casefold() == folded:
            return os.path.join(folder, entry)
    return video


def _root(video, folders):
    u"""The configured folder `video` is under. -> str or None

    ⚠ The FIRST in config order, because that is the root a run walks it from
    (`pipeline._discover` admits a video once, from the first root that finds
    it) -- and under `--out` the root decides the mirrored folder.
    """
    for folder in folders:
        if paths.under_any(video, (folder,)):
            return folder
    return None


def _same_video(video, video_hash):
    u"""Is the file at `video` still the video the DB means? -> bool

    ⭐ One 128 KiB read answers both *is it there* and *is it the same rip*.
    ⚠ A file that cannot be read is not provably the same video, so it is not
    listed; the next run reads it and says what is wrong.
    """
    try:
        return _cache.video_hash(video) == video_hash
    except OSError:
        return False                    # gone, or unreadable


def _left_inside(video, lang):
    u"""Does `video` carry its own `lang` text track? -> bool

    🚨 THE LAYER 14 PASS (Z14-4) -- DATA-F16 (ADVERSARY 2026-09-22), one click away
    since 14a. A download refused under *"Download from jimaku anyway"* kept
    asking for a pick after the person chose *"Leave them there"* again -- for
    ever: every run skips such a video BEFORE anything is recorded, so nothing
    ever settled its row. ⭐ The run's own question (`present.read_tracks`): what
    the next run would do decides what still needs the person.

    ⚠ A video that cannot be read IS listed -- the next run says what is wrong.
    """
    try:
        return present.read_tracks(video, lang).kind == present.EMBEDDED
    except Exception:                   # noqa: BLE001 -- unreadable stays listed
        return False


def _why_not_taken(video, lang, prefer):
    u"""⭐ 14z (C4) -- `pipeline.why_not_taken` for one remembered video. -> words or
    None. ⚠ A video that cannot be read says nothing here: its row says why."""
    try:
        return pipeline.why_not_taken(video, present.read_tracks(video, lang), lang,
                                      prefer) or None
    except Exception:                   # noqa: BLE001 -- the row stays as it was
        return None


def _parsed(videos):
    u"""{normalised path: tsubasa's item}, for every folder these videos sit in.

    ⭐ ONE `scan()` PER FOLDER, not one per video (`spec/00-INDEX.md` Rule 4).
    ⛔ NEVER A SECOND PARSER: title, season and episode are tsubasa's reading of
    the name or nothing. A video it does not list -- a creditless opening, a
    folder it could not walk -- is named by its file and given no number.
    """
    found, seen = {}, set()
    for video in videos:
        folder = os.path.dirname(os.path.abspath(video))
        key = paths.normalised(folder)
        if key in seen:
            continue
        seen.add(key)
        try:
            listed = tsubasa.scan(videos=folder, recurse=False).videos
        except Exception:
            continue                    # unlisted: named by its file, never guessed
        for item in listed:
            found[paths.normalised(item.path)] = item
    return found


def _outcome(latest, candidates):
    u"""The latest row's outcome, as a run would have reported it. -> text

    ⚠ A video whose name carries no episode number is REFUSED by the run and
    recorded as a soft negative -- read back as NOT_FOUND it was filed under
    "not on jimaku yet", and a person waited a day for jimaku when the fix is a
    rename (ADVERSARY 2026-09-22 F20). Told apart by hato's OWN sentence.
    """
    if latest.outcome == state.NOT_FOUND:
        if formats.only_as(latest.reason):
            # ⭐ 9a -- A FORMAT WAIT IS A WAIT, whatever was tried before it. With
            # files refused in an earlier run it read as a pick -- *"the timing did
            # not hold"* -- and the format, and the button that takes it, were
            # never mentioned (ADVERSARY 2026-09-23 #5). The tried files still
            # travel as `tried_before`.
            return state.NOT_FOUND
        if candidates:
            return state.REFUSED
        return state.REFUSED if latest.reason == episodes.NO_EPISODE else state.NOT_FOUND
    return latest.outcome


def _row(problem, item, lang, cache, not_taken=None):
    u"""One problem -> the NDJSON object a run would have printed for it."""
    latest = problem.latest
    video = problem.video_path
    if item is not None:
        title, season, episode = item.title, item.season, item.episode
    else:
        title, season, episode = os.path.splitext(os.path.basename(video))[0], None, None
    # ⚠ The same mapping as `pipeline._remembered`, which is a method of a live
    # run and so cannot be called from here. ⛔ Nothing is downloaded: a file
    # that is gone is listed with no path.
    earlier = tuple(
        pipeline.Remembered(row.jimaku_filename, row.outcome, row.reason,
                            row.jimaku_size or 0, row.match_rate,
                            keep.remembered_file(row, lang, cache), row.attempted_at)
        for row in problem.candidates)
    result = pipeline.VideoResult(
        video, _outcome(latest, problem.candidates), latest.reason,
        name=os.path.basename(video), title=title, season=season, episode=episode,
        jimaku_entry=latest.jimaku_entry, jimaku_filename=latest.jimaku_filename,
        candidates_offered=None, retry_after=latest.retry_after, tried_before=earlier,
        newest_offered=latest.newest_offered)
    result.not_taken = not_taken                            # ⭐ 14z (C4)
    row = report.as_dict(result)
    row[u"source"] = SOURCE
    return row


def _number(value):
    u"""An episode as a sort key. ⚠ Numeric, so 2 comes before 10."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


def _order(row):
    return ((row[u"title"] or u"").casefold(), row[u"season"] or 0,
            _number(row[u"episode"]), row[u"video"])


__all__ = ["SOURCE", "open_problems"]
