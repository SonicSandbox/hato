# -*- coding: utf-8 -*-
u"""The window's half of auto-update -- RUNBOOK 11f. ⛔ NO QT IN THIS MODULE.

Everything the update screens SAY is decided here, from one plain object, and
asserted without a display -- the split `gui/run.py` already makes. `app.py` only
arranges widgets around these answers. The picture is RULED (Sonic, 2026-09-24,
*"I take all your leans"*): `gui-mock/mock-update.html`, mechanism A.

    the pill, on the tab line        `pill()`
    the card                          `card()` -- what's new; `back_card()` for Go back
    its progress                      `progress()` -- Downloaded · Checked ·
                                      Installing · Reopening, one bar
    the banner, after a restart       `banner()` -- the swapper's result.json
    Settings -> Updates, the last card `settings()`

⭐ THE FROZEN RULE (build-ui): when hato decides something on a person's behalf,
the decision gets a surface, and the manual choice stays one click away. An
update downloaded by itself shows as a pill; a failed one says so, says hato will
not try that version again on its own, and offers *Try again*.

⛔ From source, on any OS, hato only TELLS: `git pull` is how a checkout updates,
and it may be somebody's working copy.
"""
import time

READY, TELL, NONE = u"ready", u"tell", u"none"          # `hato.update`'s wire words
SOURCE = u"source"
STEPS = (u"Downloaded", u"Checked", u"Installing", u"Reopening")
#: The Settings card's last line -- where updates come from, and what they touch.
FOOTNOTE = (u"Updates come from github.com/SonicSandbox/hato, and nothing is installed "
            u"unless it carries hato's signature. Your folders, settings, key and "
            u"subtitles live elsewhere and are never touched.")
SOURCE_NOTE = (u"hato never changes the files of a checkout — that is git's job, and it "
               u"may be your working copy. It only tells you when a release is out.")
#: ⭐ The mock's own words (gui-mock/mock-update.html, ruled 2026-09-24).
AUTO_TIP = (u"hato asks GitHub once a day whether a new release is out. It downloads it "
            u"in the background and checks hato's signature on it. The window never "
            u"restarts under you: it waits for Restart now, or for you to close it. With "
            u"hato closed, the tray puts it in place the next time nothing is running."
            u"\n\nOff: hato still tells you, and does nothing else.")


class Updates(object):
    u"""What the window knows about updating hato. Plain values -- `State.updates`."""

    def __init__(self, current=u"", frozen=False):
        self.current = current
        #: ⛔ Not frozen = run from source: TELL only.
        self.frozen = frozen
        #: the last `{"type": "update"}` answer, verbatim -- None until one came
        self.decision = None
        #: when that answer was made, epoch seconds -- for "checked 12 min ago"
        self.checked_at = None
        self.checking = False
        #: the version staged and waiting (`update.staged_version`), or None
        self.staged = None
        #: (done, total) bytes while a download runs; None otherwise
        self.downloading = None
        #: where the card's progress stands: None · "download" · "install"
        self.step = None
        #: the `auto_update` setting
        self.auto = True
        #: the version kept for *Go back* (`update.kept_version`), or None
        self.kept = None
        #: the version not to install automatically (`update.skipped`), or None
        self.skipped = None
        #: the swapper's result.json, read once at start, until dismissed
        self.result = None
        #: the card on screen: None · "ready" · "progress" · "back"
        self.card = None
        #: *When I close hato* was chosen
        self.when_closed = False
        #: *Restart now* was asked while a run was going -- it happens at its end
        self.after_run = False
        #: what the last update action came to, when it failed -- a sentence
        self.said = u""
        #: the checkout's folder, for the source-mode `git pull` line
        self.folder = u""
        #: ⚠ INJECTABLE, so "12 min ago" does not depend on the wall
        self.now = None

    def clock(self):
        return self.now if self.now is not None else time.time()


# ---------------------------------------------------------------------------
# what is on offer
# ---------------------------------------------------------------------------

def _decision(u):
    return u.decision if isinstance(u.decision, dict) else {}


def page(u):
    u"""The release's own page -- ⛔ only ever one on hato's repository. The page
    comes from GitHub's answer, which the signature does not cover, and it is put
    into a link: anything else falls back to the releases list."""
    from hato import update
    url = _decision(u).get(u"page")
    prefix = u"https://github.com/%s/releases" % update.REPO
    # ⛔ C8 (ADVERSARY 2026-09-24): `…/hato/../../evil-org/…` passed a prefix check and
    # resolved to someone else's page -- no `.`/`..` segment, no escape at all
    if isinstance(url, str) and (url == prefix or url.startswith(prefix + u"/")) \
            and not any(c in url for c in u"\"'<> \\%?#") \
            and not any(part in (u".", u"..") for part in url[len(prefix):].split(u"/")):
        return url
    return update.RELEASES_PAGE


def offered(u):
    u"""-> the version on offer (a READY or TELL answer), or None.

    ⛔ NEVER ONE THAT IS NOT NEWER THAN THIS COPY -- LOOKED 2026-09-24: an answer
    saved before an update, read back after it, put *"hato 1.0.5 is out · Install"*
    beside *"Updated to 1.0.5"*. The command judges again too; this is the last
    word before a person reads it."""
    from hato import update
    decision = _decision(u)
    version = decision.get(u"version")
    if decision.get(u"kind") in (READY, TELL) and version \
            and update.is_newer(version, u.current):
        return version
    # ⭐ C9: installing what is ALREADY here needs no network -- one check that could
    # not tell (offline) hid a downloaded, verified release for a day
    if u.staged and update.is_newer(u.staged, u.current):
        return u.staged
    return None


def installable(u):
    u"""True when THIS copy can install what is on offer: frozen, and READY."""
    version = offered(u)
    return bool(u.frozen and version and (_decision(u).get(u"kind") == READY
                                          or u.staged == version))


def downloads_by_itself(u):
    u"""True when hato should fetch the offer without being asked: installable,
    automatic, not already here, not a version a person turned away."""
    version = offered(u)
    return bool(installable(u) and u.auto and u.staged != version
                and u.skipped != version and u.downloading is None)


def megabytes(size):
    u"""67_400_000 -> '67 MB'; nothing known -> u''."""
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return u""
    return u"%d MB" % max(1, int(round(size / 1e6)))


def ago(seconds):
    u"""-> 'just now' · '12 min ago' · '3 h ago' · '2 days ago'."""
    if seconds is None:
        return u""
    seconds = max(0, int(seconds))
    if seconds < 90:
        return u"just now"
    if seconds < 3600:
        return u"%d min ago" % (seconds // 60)
    if seconds < 2 * 86400:
        return u"%d h ago" % (seconds // 3600)
    return u"%d days ago" % (seconds // 86400)


def _tells():
    from hato.commands.update import TELLS
    return TELLS


def prose(text):
    u"""A sentence from `hato update` (or the swapper), in the WINDOW's voice: the
    command line writes `--` and may start lower-case, and the window writes `—`
    and a capital (LOOKED, 2026-09-24: *"the download does not match the release --
    it was damaged…"* in the card). ⭐ Converted here, once -- the command keeps its
    own style for a terminal."""
    text = (text or u"").strip().replace(u" -- ", u" — ")
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------------------
# the pill
# ---------------------------------------------------------------------------

#: What a pill click does.
TO_CARD, TO_SETTINGS = u"card", u"settings"


def pill(u):
    u"""-> None, or (text, action text, action) for the tab line.

    ⛔ Quiet while an AUTOMATIC download runs: nothing to decide yet, and a
    percentage there would be a second progress bar nobody asked for."""
    version = offered(u)
    if version is None:
        return None
    decision = _decision(u)
    if not u.frozen or decision.get(u"reason") == SOURCE:
        return (u"hato %s is out" % version, u"How to update", TO_SETTINGS)
    if decision.get(u"kind") == TELL:
        return (u"hato %s is out" % version, u"Download", TO_CARD)
    if u.staged == version:
        if u.after_run:
            return (u"hato %s installs after this run" % version, u"Details", TO_CARD)
        if u.when_closed:
            return (u"hato %s installs when you close hato" % version, u"Restart now",
                    TO_CARD)
        return (u"hato %s is ready" % version, u"Restart", TO_CARD)
    if u.downloading is not None and u.card is None:
        return None
    return (u"hato %s is out" % version, u"Install", TO_CARD)


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------

#: The card's actions.
RESTART, LATER, CLOSE, PAGE, GO_BACK = u"restart", u"later", u"close", u"page", u"goback"


def card(u, running=False):
    u"""The what's-new card -> {title: (before, version, after), sub, critical,
    notes, link: (text, url), footer, buttons: [(text, action, accent)]}.

    `running`: a run is going -- *Restart now* then waits for it to end."""
    decision = _decision(u)
    version = offered(u) or u""
    link = page(u)
    notes = [n for n in (decision.get(u"notes") or []) if isinstance(n, str)]
    if decision.get(u"kind") == TELL:
        return {u"title": (u"hato ", version, u" is out"),
                u"sub": u"You have %s" % u.current,
                u"critical": u"", u"said": u"", u"notes": notes,
                u"link": (u"Everything in %s" % version, link),
                u"footer": prose(_tells().get(decision.get(u"reason"), u"")),
                u"buttons": [(u"Not now", CLOSE, False),
                             (u"Download it myself", PAGE, True)]}
    staged = u.staged == version
    sub = [u"You have %s" % u.current]
    if staged:
        sub.append(u"downloaded and checked")
    size = megabytes(decision.get(u"size"))
    if size:
        sub.append(size)
    go = u"Restart after this run" if running else (
        u"Restart now" if staged else u"Download and restart")
    return {u"title": (u"hato ", version, u" is ready" if staged else u" is out"),
            u"sub": u" · ".join(sub),
            u"critical": (u"This one fixes something important, so hato is asking now "
                          u"instead of waiting.") if decision.get(u"critical") else u"",
            #: ⭐ a download that failed is said HERE, where it was asked for
            u"said": prose(u.said),
            u"notes": notes,
            u"link": (u"Everything in %s" % version, link),
            u"footer": (u"hato closes, puts %s in place and opens again by itself — a few "
                        u"seconds. Your folders, settings, key and subtitles are not "
                        u"touched." % version),
            u"buttons": [(u"When I close hato", LATER, False) if staged
                         else (u"Not now", CLOSE, False),
                         (go, RESTART, True)]}


def progress(u):
    u"""The card while it installs -> {title, sub, steps: [(name, 'done'|'now'|'todo')],
    bar: 0..1, footer}. ⭐ The bar is ONE bar over the four steps: a download fills
    the first quarter as its bytes arrive."""
    version = offered(u) or u.staged or u""
    if u.step == u"install":
        at, fraction = 2, 0.5
    elif u.step == u"download" and u.downloading:
        done, total = u.downloading
        at, fraction = 0, (float(done) / total if total else 0.0)
    elif u.step == u"download":
        at, fraction = 0, 0.0
    else:
        at, fraction = 2, 0.0
    steps = [(name, u"done" if i < at else u"now" if i == at else u"todo")
             for i, name in enumerate(STEPS)]
    if at == 0 and u.downloading:
        # ⭐ WHILE the bytes arrive the step says so, with how far: *"Downloaded"*
        # over a download still running read as done (LOOKED, 2026-09-24).
        steps[0] = (u"Downloading %d%%" % int(100 * fraction), u"now")
    return {u"title": (u"Updating to ", version, u""),
            u"sub": u"hato closes and opens again by itself",
            u"steps": steps,
            u"bar": min(1.0, (at + max(0.0, min(1.0, fraction))) / len(STEPS)),
            u"footer": (u"Nothing of yours is touched. If anything goes wrong, hato puts "
                        u"%s back and opens that instead." % u.current)}


def back_card(u):
    u"""*Go back to X?* -- the same card, asking. ⭐ Reversible: the version left is
    kept, so going back can itself be undone."""
    kept = u.kept or u""
    return {u"title": (u"Go back to ", kept, u"?"),
            u"sub": u"You have %s" % u.current,
            u"critical": u"", u"said": prose(u.said), u"notes": [], u"link": None,
            u"footer": (u"hato closes, puts %s back and opens again by itself. %s is kept, "
                        u"so you can return to it — and hato won't install it again on "
                        u"its own." % (kept, u.current)),
            u"buttons": [(u"Cancel", CLOSE, False), (u"Go back", GO_BACK, True)]}


# ---------------------------------------------------------------------------
# the banner, after a restart
# ---------------------------------------------------------------------------

DISMISS, AGAIN = u"dismiss", u"again"


def banner(u):
    u"""-> None, or {kind: 'ok'|'warn', lead, rest, detail, notes, link, actions}.

    From the swapper's result.json, read once at the start after a swap."""
    result = u.result if isinstance(u.result, dict) else None
    if not result:
        return None
    to, was = result.get(u"to") or u"", result.get(u"from") or u""
    decision = _decision(u)
    if result.get(u"status") == u"success":
        if result.get(u"going_back"):
            return {u"kind": u"ok", u"lead": u"Back on %s" % to,
                    u"rest": u" — %s is kept, and hato won't install it again on its "
                             u"own." % was,
                    u"detail": u"", u"notes": [], u"link": None, u"actions": []}
        notes = decision.get(u"notes") if decision.get(u"version") == to else None
        return {u"kind": u"ok", u"lead": u"Updated to %s" % to,
                u"rest": u" · %s · everything of yours is where it was" % _when(result, u),
                u"detail": u"",
                u"notes": [n for n in (notes or []) if isinstance(n, str)],
                u"link": (u"Everything in %s" % to, page(u)) if notes else None,
                u"actions": []}
    touched = result.get(u"touched")
    if result.get(u"going_back"):
        # ⛔ C5 (ADVERSARY 2026-09-24): a failed Go back read *"The update to 1.0.4
        # didn't finish ... won't try 1.0.4 again"*, and *Try again* staged the
        # FORWARD release. It is a Go back, and trying again goes back again.
        return {u"kind": u"warn", u"lead": u"Going back to %s didn't finish" % to,
                u"rest": (u", so hato put %s back — nothing else changed." % was
                          if touched else u", so nothing was changed."),
                u"detail": u"What happened is written in hato.log.",
                u"notes": [], u"link": None,
                u"actions": [(u"Try again", ASK_BACK, True)]}
    if touched:
        lead, rest = (u"The update to %s didn't finish" % to,
                      u", so hato put %s back — nothing else changed." % was)
    else:
        lead, rest = (u"The update to %s didn't start" % to, u", so nothing was changed.")
    # ⚠ C3b: only a swap that TOUCHED the folder turns its release away
    return {u"kind": u"warn", u"lead": lead, u"rest": rest,
            u"detail": u"What happened is written in hato.log." + (
                u" hato won't try %s again on its own." % to if touched else u""),
            u"notes": [], u"link": None,
            u"actions": [(u"Download it myself", PAGE, False), (u"Try again", AGAIN, True)]}


def _when(result, u):
    u"""The swap's own moment, said the way a person would."""
    try:
        import datetime
        at = datetime.datetime.strptime(result.get(u"at") or u"", u"%Y-%m-%dT%H:%M:%S")
        seconds = u.clock() - time.mktime(at.timetuple())
    except (TypeError, ValueError, OverflowError):
        return u"just now"
    return u"just now" if seconds < 600 else u"at %s" % at.strftime(u"%H:%M")


# ---------------------------------------------------------------------------
# Settings -> Updates
# ---------------------------------------------------------------------------

CHECK, INSTALL, COPY, ASK_BACK = u"check", u"install", u"copy", u"askback"


def settings(u, running=False):
    u"""The Updates card -> {mode: 'frozen'|'source', dot: 'ok'|'accent'|'dim',
    lead, rest, button: (text, action) or None, link, auto, kept, git, copy, note,
    said}. ⛔ From source there is no switch and no *Go back* -- controls vanish
    where they would be meaningless; the `git pull` line is the instruction."""
    decision = _decision(u)
    version = offered(u)
    out = {u"mode": u"frozen" if u.frozen else u"source", u"button": None,
           u"link": None, u"git": None, u"copy": None, u"kept": None,
           u"said": prose(u.said), u"auto": None, u"note": FOOTNOTE}
    checked = (u" · checked %s" % ago(u.clock() - u.checked_at)
               if u.checked_at is not None else u"")
    if not u.frozen:
        out[u"note"] = SOURCE_NOTE
        if version:
            out.update(dot=u"accent", lead=u"hato %s is out" % version,
                       rest=u" · you have %s, run from source" % u.current,
                       link=(u"What's new", page(u)),
                       git=(u"git pull", u" in %s, then start hato again"
                            % (u.folder or u"hato's folder")),
                       copy=(u"Copy", COPY))
        else:
            out.update(dot=u"ok" if decision.get(u"kind") == NONE else u"dim",
                       lead=u"hato %s" % u.current,
                       rest=u" · run from source" + (u" · up to date" + checked
                                                     if decision.get(u"kind") == NONE
                                                     else u""),
                       button=(u"Check now", CHECK) if not u.checking else None)
        return out
    if u.checking:
        out.update(dot=u"dim", lead=u"hato %s" % u.current, rest=u" · checking…")
    elif version and u.staged == version:
        out.update(dot=u"accent", lead=u"hato %s is ready" % version,
                   rest=u" · you have %s" % u.current,
                   button=(u"Restart after this run" if running else u"Restart now", RESTART))
    elif version and u.downloading is not None:
        done, total = u.downloading
        out.update(dot=u"accent", lead=u"hato %s" % version,
                   rest=u" · downloading — %d%%" % (100 * done // total if total else 0))
    elif version and decision.get(u"kind") == READY:
        out.update(dot=u"accent", lead=u"hato %s is out" % version,
                   rest=u" · you have %s" % u.current, button=(u"Install", INSTALL))
    elif version:
        out.update(dot=u"accent", lead=u"hato %s is out" % version,
                   rest=u" · " + prose(_tells().get(decision.get(u"reason"), u"")),
                   button=(u"Download", PAGE))
    elif decision.get(u"kind") == NONE and decision.get(u"version"):
        out.update(dot=u"ok", lead=u"hato %s" % u.current, rest=u" · up to date" + checked,
                   button=(u"Check now", CHECK))
    elif decision.get(u"kind") == NONE:
        out.update(dot=u"dim", lead=u"hato %s" % u.current,
                   rest=u" · could not check — GitHub did not answer" + checked,
                   button=(u"Check now", CHECK))
    else:
        out.update(dot=u"dim", lead=u"hato %s" % u.current, rest=u" · not checked yet",
                   button=(u"Check now", CHECK))
    out[u"auto"] = (u"Update automatically",
                    u" · downloads quietly, restarts only when you say — or while hato "
                    u"is closed", AUTO_TIP)
    if u.kept:
        out[u"kept"] = (u"%s is kept, in case this one misbehaves." % u.kept,
                        (u"Go back to %s" % u.kept, ASK_BACK))
    return out


#: ⭐ EVERY action any of the functions above can hand the window -- the window's
#: one dispatcher is checked against this list, so a new button cannot be inert.
ACTIONS = (RESTART, LATER, CLOSE, PAGE, GO_BACK, DISMISS, AGAIN, CHECK, INSTALL, COPY,
           ASK_BACK)

__all__ = ["ACTIONS", "AGAIN", "ASK_BACK", "AUTO_TIP", "CHECK", "CLOSE", "COPY", "DISMISS",
           "FOOTNOTE", "GO_BACK", "INSTALL", "LATER", "NONE", "PAGE", "READY", "RESTART",
           "SOURCE", "SOURCE_NOTE", "STEPS", "TELL", "TO_CARD", "TO_SETTINGS", "Updates",
           "ago", "back_card", "banner", "card", "downloads_by_itself", "installable",
           "megabytes", "offered", "page", "pill", "progress", "prose", "settings"]
