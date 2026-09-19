# -*- coding: utf-8 -*-
u"""
The `sync()` port -- hato's one door to tsubasa (spec/RUNBOOK.md step 4a).

    from hato import port

    result = port.sync(video, subtitle)              # tsubasa writes the file
    if port.wrote(result):                           # CONFIDENT *and* written
        keep_original(subtitle)

⭐ ONE BACKEND, AND IT IS tsubasa. Ruled 2026-09-16 (Sonic): there is no subsync
adapter. What this module buys is not portability -- it is that every caller
depends on ONE shape, and the suites can drive that shape without opening a
container (`stub_engine` below).

===========================================================================
🚨 tsubasa's `Result` COMES BACK UNCHANGED. NOT A SUBSET, NOT A COPY.
===========================================================================

`spec/RUNBOOK.md` 4a: *returns tsubasa's `Result` unchanged -- every field, not
a re-wrapped subset.* `05-interface.md` §*`Result` carries* lists twenty-odd
fields and three of hato's four pinned shapes ride out on them; a port that
re-wrapped `(outcome, path, reason)` would silently drop `segments`,
`runtime_check`, `dropped_before_zero`, `write_failed` and `superseded` -- and
`03-permissions.md` §*The hand-back path* needs most of them to tell a person
what was measured and what would change it. So `sync()` returns **the identical
object** tsubasa built, and the helpers below READ it rather than rebuild it.

⛔ That is also why `outcome_and_reason()` returns a TUPLE. The read rule turns
*CONFIDENT but nothing written* into an ERROR, and building a second `Result`
to say so would be exactly the re-wrap this module exists to prevent.

===========================================================================
⛔ CONFIDENT IS NOT WRITTEN
===========================================================================

`03-permissions.md`: *CONFIDENT with no `output_path` is an ERROR.* This is not
defensive programming; it is a shape the real engine produces. MEASURED
2026-09-17, both against the real `tsubasa.sync()`:

  * a dry run -> `CONFIDENT`, `output_path=None`, `write_failed=False`,
    `reason="(dry run -- nothing was written)"`
  * a destination that already exists and this run did not account for ->
    `CONFIDENT`, `output_path=None`, **`write_failed=True`**, and a reason
    naming the file and the fix

Reading `outcome == CONFIDENT` alone reports a file that is not on disk, and a
user who is told a subtitle was written stops looking for it. `wrote()` is the
only success test in this project.

===========================================================================
⭐ `results=None` -- THE RESULTS DB. A DELIBERATE CHOICE, TESTED.
===========================================================================

`tsubasa.sync(results=)` takes three values and they are not interchangeable
(`pipeline.py`): `None` means *use the real per-user store*, `False` means
*consult and record nothing*, and an injected store is an internal type hato
may not reach for (`Results` is not in `tsubasa.__all__`; `LEDGER-HOT.md`
forbids internals). hato passes **`None`**, explicitly, and the reasons are in
this order:

1. ⭐ **RECORDING IS THE WHOLE BENEFIT, AND SKIPPING CANNOT HAPPEN HERE.**
   `pipeline._sync_plan` -- the explicit-pair path, the only one hato uses --
   *"records, and it never skips"*: the store is written and never consulted,
   so it can never turn hato's pair into a `SyncReport.settled` entry with no
   `Result` at all. The one way this argument could hurt the port is
   structurally absent. (On a `Scan` it would not be; hato never passes one.)
2. The record is what makes a later `tsubasa <folder>` over the user's own
   library recognise the file hato just placed as **already in sync** instead
   of re-reading the container, re-aligning it, and putting hato's output up
   as a candidate for its own slot.
3. It costs one 128 KiB video sample plus a few kilobyte-sized subtitle hashes
   per SUCCESS, after a network download -- and nothing at all on a refusal
   (`_record_slot` hashes nothing until there is something to record).

⚠ It is passed explicitly rather than left to default, so that a future change
of tsubasa's default is a visible diff here and a red check in `test_port.py`,
not a silent change of behaviour in someone's media folder.

===========================================================================
⛔ `dedupe=False` -- hato NEVER AUTHORISES A TRASH
===========================================================================

`03-permissions.md` Whitelist 1: *on this explicit path tsubasa supersedes
nothing, so nothing is trashed.* hato hands exactly ONE pair, so dedupe has
nothing to choose between and the flag changes no outcome -- MEASURED, the same
CONFIDENT write with `superseded == []` either way. Passing `False` makes the
promise structural instead of incidental: it is the flag that authorises the
supersede step at all, and hato has no business authorising it.

`rename=True` is passed for the opposite reason -- it is load-bearing. It is
what makes the output `<video-basename>.<lang>.<ext>`, which is what a player
auto-loads and what `unpaired(lang="ja")` reads on the next run.
"""
import os
import shutil
import tempfile

import tsubasa

#: The three outcome strings, which are tsubasa's and hato's at once.
#:
#: ⚠ A SECOND COPY OF THE VOCABULARY LIVES IN `hato/state.py` and a third in
#: `tsubasa.verdict` (not exported -- `Result.outcome` is a plain string). They
#: are defined again here so that importing the port costs no sqlite and no DB
#: module, and `test_port.py` pins all three against each other AND against
#: what the real engine returns, so the copies cannot drift.
CONFIDENT = u"CONFIDENT"
REFUSED = u"REFUSED"
ERROR = u"ERROR"

#: What `tsubasa.parse_subtitle_name` returns for a name with no language.
#: 🚨 `LEDGER-HOT.md`: an `und` original makes tsubasa write `<video>.<ext>`
#: with NO tag, `unpaired(lang="ja")` then reads the video as unsubtitled, and
#: every later run fetches again. `output_name()` below reproduces that exactly
#: rather than hiding it -- a stub that invented `<video>.und.srt` would let a
#: pipeline check pass over the live defect.
UND = u"und"

#: ⭐ The `results=` argument, named so the choice is visible and one check can
#: pin it. See the module docstring.
RESULTS = None


class PortError(RuntimeError):
    u"""tsubasa returned no outcome for a pair hato handed it.

    ⛔ Never raised by an outcome hato dislikes -- REFUSED and ERROR are
    outcomes and come back as `Result`s. This is *the engine did not answer the
    question*, which `03-permissions.md` says cannot happen (*every video
    resolves to exactly one outcome; there is no silent success*), so it is
    loud rather than turned into an ERROR row that would look like the video's
    fault.
    """


# ---------------------------------------------------------------------------
# the port
# ---------------------------------------------------------------------------

def sync(video, subtitle, write=True, out_dir=None, engine=None):
    u"""Hand ONE pair to tsubasa. -> tsubasa's `Result`, unchanged.

    `video` · `subtitle`
        paths. The subtitle is the finished download, already named
        `<jimaku stem>.ja.<ext>` by the caller (`03-permissions.md`, and
        `LEDGER-HOT.md`'s untagged-original trap).
    `write`
        ⭐ **True by default, and that is deliberate here** where tsubasa's own
        default is False. Ruled 2026-09-17: *the real call writes* -- tsubasa
        places the file and hato never does. A caller wanting a measurement
        passes `write=False` and gets CONFIDENT with no `output_path`, which
        `wrote()` correctly calls *not written*.
    `out_dir`
        the video's MIRRORED directory under `--out`, computed by the caller
        (`03-permissions.md`: only hato knows the library root). None means
        beside the video.
    `engine`
        ⛔ A SEAM, the same shape as tsubasa's own `reader=` / `sender=` /
        `results=`: the real engine is the default so it is never *code that
        never runs here*, and a suite that must not open a container passes
        `stub_engine(...)`. 🚨 A port exercised only against its stub is proof
        of the stub -- `test_port.py` carries a contract test against the real
        `tsubasa.sync()` for that reason, and so must anything that changes
        this function.
    """
    engine = tsubasa.sync if engine is None else engine
    video = os.fspath(video)
    subtitle = os.fspath(subtitle)
    report = engine([(video, subtitle)],
                    write=write,
                    rename=True,           # load-bearing: <video>.<lang>.<ext>
                    dedupe=False,          # hato never authorises a trash
                    out_dir=os.fspath(out_dir) if out_dir else None,
                    results=RESULTS)
    return _only_result(report, video, subtitle)


def _only_result(report, video, subtitle):
    u"""The one `Result` a one-pair run owes. -> `Result`

    ⛔ NOT `report[0]`. One pair in, one outcome out is the contract
    `03-permissions.md` states, and the two ways it could be broken are both
    silent: an empty report (the results DB settling the video, a future
    tsubasa skipping something) would raise `IndexError` four frames from the
    cause, and a report carrying several would quietly report the first.
    """
    results = list(report)
    if len(results) == 1:
        return results[0]
    raise PortError(
        u"tsubasa returned %d results for the single pair %s <- %s, and "
        u"03-permissions.md says every video resolves to exactly one outcome. "
        u"summary: %s%s"
        % (len(results), os.path.basename(video), os.path.basename(subtitle),
           _summary(report), _settled(report)))


def _summary(report):
    try:
        return report.summary()
    except Exception:                      # a stub need not carry one
        return u"(no summary)"


def _settled(report):
    settled = list(getattr(report, "settled", ()) or ())
    if not settled:
        return u""
    return (u" -- and %d video(s) came back SETTLED, which on the explicit "
            u"path pipeline._sync_plan says cannot happen: %r"
            % (len(settled), settled))


# ---------------------------------------------------------------------------
# reading the result -- the two questions the read rule asks
# ---------------------------------------------------------------------------

def wrote(result):
    u"""Did a file actually land? -> bool

    🚨 THE ONLY SUCCESS TEST IN THIS PROJECT. `03-permissions.md`: *CONFIDENT
    with no `output_path` is an ERROR.*
    """
    return result.outcome == CONFIDENT and bool(result.output_path)


def nothing_was_written(result):
    u"""CONFIDENT, and no file landed. -> bool

    🚨 THIS IS NEVER A TIMING REFUSAL, AND THE FETCH LOOP MUST NOT TREAT IT AS
    ONE. The pair **aligned** -- `match_rate` 1.0, verdict `locked`, measured on
    the real engine with a file sitting where the mirrored directory had to go.
    What failed is the DESTINATION, which is the same destination for every
    other candidate, so escalating buys nothing and a *"none held by timing"*
    soft negative is a false statement that then silences the video for a day
    even after the disk is fixed. `outcome_and_reason()` already mints the ERROR;
    this is the question *"is it this candidate's fault?"*, answered no.

    ⚠ Both shapes count -- a dry run (`write_failed False`) and a blocked write
    (`write_failed True`). Neither is a verdict on the subtitle, and hato only
    ever calls with `write=True`, so the first cannot arise from its own loop.
    """
    return result is not None and result.outcome == CONFIDENT and not result.output_path


def why_nothing_was_written(result):
    u"""tsubasa's OWN words for why a confident pair produced no file. -> text

    ⛔ Never a sentence hato composed about a measurement it did not make.
    tsubasa sets `reason` on exactly this path -- `"(dry run -- nothing was
    written)"`, or `"NOT WRITTEN: <what stopped it>"` with `write_failed=True`
    -- and its reason names the fix, which `03-permissions.md` §*The hand-back
    path* requires and *"it failed"* does not satisfy.
    """
    reason = (result.reason or u"").strip()
    if reason:
        return reason
    notes = [n for n in (result.notes or ()) if (n or u"").strip()]
    if notes:
        return u"; ".join(notes)
    # ⚠ Reached only if tsubasa ever stops populating either -- so it says that
    # out loud instead of returning the empty string `03-permissions.md`
    # forbids (*"it failed" is not actionable and is not acceptable output*).
    return (u"%s reported %s and no output file, and gave no reason -- which "
            u"is itself the fault. Video: %s. Subtitle: %s."
            % (u"tsubasa", result.outcome, result.video, result.subtitle))


def outcome_and_reason(result):
    u"""What hato should ACT on. -> (outcome, reason)

    The read rule in `03-permissions.md`, as two values rather than a rebuilt
    object::

        if result.outcome == CONFIDENT and not result.output_path:
            return ERROR(why_nothing_was_written(result))

    ⚠ `reason` is empty for a real success and never empty for anything else
    -- tsubasa's `Result` constructor already refuses a non-confident outcome
    with no reason, and the ERROR this function mints carries tsubasa's.
    """
    if nothing_was_written(result):
        return ERROR, why_nothing_was_written(result)
    return result.outcome, (result.reason or u"")


# ---------------------------------------------------------------------------
# ⭐ the stub seam
# ---------------------------------------------------------------------------

def output_name(video, subtitle, out_dir=None):
    u"""Where tsubasa will put the finished file. -> path

    ⛔ **FOR THE STUB AND FOR TESTS. Production reads `result.output_path`.**
    A second answer to a question the run has already answered is a defect
    waiting to happen; this exists only so `stub_engine()` can put a file where
    the real engine would have, and `test_port.py` pins it against the real
    engine's answer on a real video.

    The rule is `05-interface.md` §*Naming and dedupe*:
    `<video-basename>.<lang>[.flags].<ext>`, with the **resolved** language
    read by tsubasa's own public `parse_subtitle_name`.

    🚨 `und` GETS NO TAG, deliberately -- that is what the real engine does
    (measured: `[Group] Show - 01 [JPN].srt` -> `Show - 01.srt`) and it is the
    `LEDGER-HOT.md` trap that makes every later run re-fetch. A stub that
    smoothed it over would hide the defect from every pipeline check.
    """
    side = tsubasa.parse_subtitle_name(os.path.basename(os.fspath(subtitle)))
    parts = [os.path.splitext(os.path.basename(os.fspath(video)))[0]]
    if side.lang != UND:
        parts.append(side.lang)
    parts.extend(side.flags)
    parts.append(side.ext)
    folder = os.fspath(out_dir) if out_dir else os.path.dirname(os.fspath(video))
    return os.path.join(folder, u".".join(parts))


def stub_engine(outcome=CONFIDENT, verdict_word=u"locked", reason=None,
                writes=True, calls=None, **fields):
    u"""A stand-in for `tsubasa.sync`, for suites that must not open a video.

        calls = []
        r = port.sync(video, sub, engine=port.stub_engine(calls=calls))

    ⭐ IT BUILDS A REAL `tsubasa.Result`, not a look-alike. The constructor
    enforces four invariants hato's callers rely on (no confident result
    without a word, no refusal without a reason, no ERROR carrying an
    `output_path`), so a stub that faked the object would be laxer than
    production and would pass things the engine refuses.

    `writes`
        ⛔ **The CONFIDENT-is-not-WRITTEN switch.** `writes=False` with
        `outcome=CONFIDENT` produces the shape the real engine returns when a
        write is blocked: no `output_path`, `write_failed=True`, and a reason
        opening *NOT WRITTEN*. `write=False` at the call site produces the
        other one, the dry run.
    `calls`
        a list. Each call appends `(pairs, kwargs)` -- which is how a check
        sees what the port asked for (`results=`, `dedupe=`, `out_dir=`).
    `fields`
        any `Result` field, overriding the defaults.

    ⚠ IT IS A STUB AND IT SAYS SO: it measures nothing. Its `match_rate` and
    `segments` are whatever you pass. Nothing about the ALIGNMENT may be
    proved through it -- only the port's own contract, and the pipeline's.
    """
    if outcome != CONFIDENT:
        verdict_word = None
        # ⚠ `None` IS THE SENTINEL, NOT FALSINESS. `reason or default` silently
        # replaced an explicitly EMPTY reason with a sentence, so a check aimed
        # at *what happens when tsubasa says nothing* was scored against text
        # the stub itself had written. Found by that check going red.
        if reason is None:
            reason = (u"stubbed %s -- no measurement was made, and this reason "
                      u"exists because tsubasa's Result refuses a "
                      u"non-confident outcome without one" % outcome)

    def engine(pairs, **kwargs):
        pairs = list(pairs)
        if calls is not None:
            calls.append((pairs, dict(kwargs)))
        results = []
        for video, subtitle in pairs:
            results.append(_stub_result(video, subtitle, outcome, verdict_word,
                                        reason, writes, kwargs, fields))
        return tsubasa.SyncReport(results)

    return engine


def _stub_result(video, subtitle, outcome, verdict_word, reason, writes,
                 kwargs, fields):
    side = tsubasa.parse_subtitle_name(os.path.basename(os.fspath(subtitle)))
    destination = output_name(video, subtitle, kwargs.get("out_dir"))
    written, failed = None, False
    text = reason

    if outcome == CONFIDENT:
        # ⚠ `is None`, not falsiness -- see the note in `stub_engine`.
        if not kwargs.get("write"):
            # The measured dry-run shape, verbatim in form.
            text = u"(dry run -- nothing was written)" if text is None else text
        elif writes:
            try:
                _copy_atomically(subtitle, destination)
            except FileExistsError:
                # 🚨 THE STUB MAY NOT DO WHAT THE ENGINE REFUSES TO DO. Measured
                # 2026-09-17 on the real `tsubasa.sync()`: a destination that is
                # already there comes back CONFIDENT, `write_failed=True`, no
                # `output_path`, and a reason opening `NOT WRITTEN`. The stub
                # used to `os.replace` straight over it -- so every pipeline
                # check in the project ran on an engine that overwrites a
                # person's file, and the one shape the media folder must never
                # see was unreachable from the suite that drives the fetch loop.
                failed = True
                if text is None:
                    text = (u"NOT WRITTEN: %s already exists and is not one of the "
                            u"files this run accounted for, so writing would "
                            u"destroy it." % destination)
            else:
                written = destination
                text = u"" if text is None else text
        else:
            failed = True
            if text is None:
                text = (u"NOT WRITTEN: the stub was told not to write. The "
                        u"pair aligned; the file is not there.")

    values = dict(outcome=outcome, reason=text or u"", verdict_word=verdict_word,
                  segments=[(None, -7.0)], match_rate=1.0,
                  excess_over_chance=5.0, raw_excess=5.0, runtime_check=u"held",
                  reference_kind=u"text track",
                  reference=u"stubbed -- no container was opened",
                  output_path=written, write_failed=failed,
                  lang=side.lang, lang_tag=side.tag)
    values.update(fields)
    return tsubasa.Result(os.fspath(video), os.fspath(subtitle), **values)


def _copy_atomically(source, destination):
    u"""🚨 TEMP-PLUS-RENAME, even in a stub, and ⛔ NEVER OVER A FILE THAT IS
    THERE (`LEDGER-HOT.md`, and `keep._place` has the same two lines).

    `open(path, 'w')` truncates the moment it opens; a raise after that leaves
    zero bytes. This destroyed `tsubasa/spec/RUNBOOK.md` on 2026-09-07. A stub
    that wrote the lazy way would be the shape a tired builder copies.

    ⛔ `os.replace` OVERWRITES, silently, and this had no existence check -- so
    the stub every pipeline check runs on destroyed a file the real engine
    refuses to touch. The destination is checked immediately before the rename,
    so a file appearing between the check and it is refused too, and
    `FileExistsError` is the caller's cue to return the engine's own
    *CONFIDENT + `write_failed`* shape rather than a success.

    ⚠ The BYTES are copied, never re-encoded -- `LEDGER-HOT.md`: *sniff the
    codec, write the same one back*. A retime is length-preserving anyway, so
    a copy is the closest cheap thing to what the engine produces.
    """
    folder = os.path.dirname(destination) or u"."
    if not os.path.isdir(folder):
        os.makedirs(folder)
    if os.path.lexists(destination):
        raise FileExistsError(17, u"refusing to write over a file this run did "
                                  u"not account for", destination)
    handle, temporary = tempfile.mkstemp(prefix=u".hato-stub-", dir=folder)
    os.close(handle)
    try:
        shutil.copyfile(os.fspath(source), temporary)
        if os.path.lexists(destination):
            raise FileExistsError(17, u"refusing to write over a file this run "
                                      u"did not account for", destination)
        os.replace(temporary, destination)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


__all__ = ["CONFIDENT", "REFUSED", "ERROR", "UND", "RESULTS", "PortError",
           "sync", "wrote", "nothing_was_written", "why_nothing_was_written",
           "outcome_and_reason", "output_name", "stub_engine"]
