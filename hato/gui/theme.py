# -*- coding: utf-8 -*-
u"""
The window's palette and stylesheet. RUNBOOK 7c.

    from hato.gui import theme
    widget.setStyleSheet(theme.qss())
    pen = QColor(theme.ACCENT)

===========================================================================
[X] NO QT IN THIS FILE, AND NO COLOUR ANYWHERE ELSE
===========================================================================

Two rules, and both are checkable:

1. **Qt-free**, for the same reason `hato.gui.run` is: the palette is data,
   and a check about the palette that needs a display is a check that gets
   skipped. `qss()` returns a string; building a `QColor` out of one of these
   constants is the caller's business.

2. **Every colour the window can paint is named here.** A literal in `app.py`
   is a second palette that drifts from the measured one, so
   `test_gui_widgets.py` greps `app.py` for hex and fails on a hit. If a new
   surface is needed, it gets a name in this file first.

===========================================================================
MEASURED, NOT EYEBALLED
===========================================================================

`gui-mock/theme.css` carries the arithmetic; these are its values verbatim.
`spec/05-interface.md` defines *"modern UX with high integrity"* as a contrast
floor and a consistent ramp, so the numbers are load-bearing:

    candidate                     L*     on panel #1c1f25   dL* from accent
    accent coral #f8a890         76.1        8.64                 --
    deep garnet  #c02040 AS TEXT 42.2        2.77  FAILS AA      33.9
    crimson      #ef4d6d AS TEXT 56.8        4.68  passes        19.3
    deep garnet  #c02040 AS FILL, cream type #f8f0e0 -> 5.26  passes

[!] SO THE FAILURE COLOUR IS A **FILL**, NEVER AN INK. `REFUSED_FILL` is a
GROUND and only ever carries `REFUSED_TYPE` on it. `color: #c02040` on the
panel is 2.77 against a 4.5 floor and is a defect, which is why the two are
named apart and why `REFUSED_INK` (the crimson) exists for the one place a
fill will not fit.

[*] And it separates from the accent BY MECHANISM, not merely by hue: one is
a fill, the other is an ink. tsubasa spends a coral-red on REFUSED and hato's
accent IS coral, so hue alone would have put a failure and the accent in the
same family.

===========================================================================
WHAT QSS CANNOT DO, AND WHERE IT IS HANDLED INSTEAD
===========================================================================

Qt's stylesheet language is CSS-shaped, not CSS. It has no `transition`, no
`transform`, no `box-shadow`, no `letter-spacing`, no `text-transform` and no
`::placeholder`. Those are handled in `app.py`:

    transition / transform  -> QPropertyAnimation, driven by EASE/FAST/SLOW
    box-shadow              -> QGraphicsDropShadowEffect, animated on hover
    letter-spacing          -> QFont.setLetterSpacing
    text-transform          -> the string is upper-cased in Python
    ::placeholder           -> QPalette.ColorRole.PlaceholderText

[!] AND A PLAIN `QWidget` DOES NOT PAINT ITS OWN STYLESHEET BACKGROUND. Every
styled container in `app.py` derives from one base class whose `paintEvent`
draws `PE_Widget`; without it these rules are silently inert on containers,
which looks exactly like a stylesheet that did not load.
"""

# ---------------------------------------------------------------------------
# ground and type
# ---------------------------------------------------------------------------

BG = u"#15171b"           #: the window behind everything
SURFACE = u"#1c1f25"      #: the panel the content sits on
RAISED = u"#232830"       #: a control that stands off the panel
LINE = u"#2b3038"         #: a divider
LINE_HI = u"#3a414c"      #: a border that is meant to be seen
INK = u"#e7e9ec"          #: primary type
INK_DIM = u"#8b929c"      #: secondary type
INK_FAINT = u"#5f6670"    #: tertiary type, and every placeholder

# ---------------------------------------------------------------------------
# the accent -- the logo's own coral, sampled from hato-original-512.png
# ---------------------------------------------------------------------------

ACCENT = u"#f8a890"
ACCENT_QUIET = u"#c9705a"

# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------

OK = u"#7fc8a0"           #: written and confident
LOOK = u"#e8c07a"         #: written, worth a look

#: [!] A FILL. See the measurement block above. Only ever with REFUSED_TYPE on
#: it, and [X] never as `color:`.
REFUSED_FILL = u"#c02040"
REFUSED_TYPE = u"#f8f0e0"
#: The text-weight fallback (4.68). Dense cells only -- a remove affordance.
REFUSED_INK = u"#ef4d6d"

NOT_FOUND = u"#7a8290"    #: nothing on jimaku yet; a retry date, not a fault
PRESENT = u"#5f6670"      #: already subtitled: visible, not the focus
NO_TRACK = u"#6d7480"     #: no subtitle track in the video; cannot sync yet

# ---------------------------------------------------------------------------
# surfaces the mock names by value -- so app.py never has to
# ---------------------------------------------------------------------------

HOVER = u"#20242b"          #: a row or card under the pointer
TITLE_TOP = u"#20242b"      #: the title bar's gradient, top stop
TITLE_BOTTOM = u"#1c1f25"   #: ... and bottom stop
STRIP = u"#191c22"          #: the tab strip and the footer
CARD = u"#1a1d23"           #: a settings card, and a candidate at rest
CARD_ON = u"#241f22"        #: the chosen candidate, and the stale-rows notice
TIP = u"#0f1115"            #: a tooltip ground
SWITCH_ON = u"#3a2028"      #: the switch track when it is on
GO_HOVER = u"#2a2024"       #: the accent button under the pointer
BL_LINE = u"#1e2228"        #: the hairline between blacklist rows
SHADOW = u"#000000"         #: the window's own drop shadow

#: The credit link. [*] Deliberately outside the coral family: a hyperlink
#: that is the accent colour reads as an accent, not as something to click.
#: ⚠ LIGHTENED 2026-09-18. Sonic: *"the purple used for github is too dark."*
#: ⭐ TWO THINGS WERE WRONG AND ONLY ONE WAS THE COLOUR. What rendered was Qt's
#: OWN visited-link colour, not this token at all -- a widget under an app-wide
#: stylesheet ignores its palette for links, so `setColor(Link, ...)` was
#: having no effect. The colour is now written INLINE in the HTML, where
#: nothing can override it. Same class as the Windows-blue radio: a control
#: painted from somewhere you are not looking.
#: Measured on the footer's own ground (#191c22): 7fa8d8 6.90, a8c8e8 9.83.
LINK = u"#a8c8e8"

#: ⭐ THE ANCHOR STYLE, IN ONE PLACE -- every `<a href>` this window renders.
#: ⚠ A link needs BOTH halves: the colour is set here AND on the widget's
#: palette, because Qt paints the link colour from the palette and ignores a
#: stylesheet rule. ⛔ But the DECORATION comes only from here -- there is no
#: palette role for it, and Qt underlines every anchor by default.
#: Sonic, 2026-09-18: *"remove the underlines."*
LINK_CSS = u"color:%s; text-decoration:none;" % LINK
LINK_HOVER = u"#c2dcff"

# ---------------------------------------------------------------------------
# motion
# ---------------------------------------------------------------------------
# Sonic: *"When hovering over buttons, there is action... modern and premium and
# interactable yet also simple and magic."* [X] And: no decoration that does not
# report. So ONE easing curve, ONE lift distance, ONE glow -- restraint plus
# response, not effects.

FAST = 120                          #: ms -- a colour answering the pointer
SLOW = 260                          #: ms -- a panel changing size
#: The two control points of `cubic-bezier(.2,.7,.3,1)`. A tuple, not a
#: `QEasingCurve`, because this file stays Qt-free.
EASE = ((0.2, 0.7), (0.3, 1.0))
LIFT = 3                            #: px -- how far a hovered control rises
GLOW = 14                           #: px -- the blur of the glow under it

#: The mark, at the size the title bar draws it.
MARK_PX = 40
#: Every icon size copied into `hato/data/`. [X] Real exports, all of them --
#: `branding.py` hands the whole set to one QIcon and Qt picks; nothing is
#: resampled from the 1024 master, which never enters the wheel.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def colors():
    u"""Every colour token, by name. -> {name: '#rrggbb'}

    [*] SO A CHECK CAN ENUMERATE THEM. The "no literal outside this file" rule
    is only enforceable if the permitted set is something a test can read.
    """
    return dict((name, value) for name, value in sorted(globals().items())
                if name.isupper() and isinstance(value, str)
                and value.startswith(u"#"))


# ---------------------------------------------------------------------------
# the stylesheet
# ---------------------------------------------------------------------------
# [!] `%`-formatting, NOT an f-string or `.format()`: QSS is made of braces and
# doubling every one of them is how a rule goes missing. There is no literal
# `%` anywhere in the sheet.

_SHEET = u"""
/* ---- ground ------------------------------------------------------------ */
/* [!] THE JAPANESE FALLBACK HAS TO BE A FONT THAT IS THERE. Measured on this
 * machine 2026-09-18: `Segoe UI Variable Text` is ABSENT (Windows 10 LTSC
 * 2019, exactly as `spec/05-interface.md` predicted) and so is `Meiryo`;
 * `Yu Gothic UI` is present and is Windows 10's own Japanese UI face. Every
 * show title in this corpus is Japanese, so naming only fonts that do not
 * exist is how the headings become tofu. */
QWidget {
    color: %(INK)s;
    font-family: "Segoe UI Variable Text", "Segoe UI", "Yu Gothic UI",
                 "Meiryo", sans-serif;
    font-size: 13px;
}
QToolTip {
    background: %(TIP)s;
    color: %(INK_DIM)s;
    border: 1px solid %(LINE_HI)s;
    border-radius: 7px;
    padding: 8px 10px;
    font-size: 12px;
}

#window { background: %(SURFACE)s; }

/* 🚨 EVERY DIALOG, NOT JUST THE NAMED WINDOW. Sonic, 2026-09-19, on the
 * published 1.0.0: *"the API key window was white and ugly on this version."*
 *
 * ⛔ THE RULE ABOVE SETS LIGHT TEXT ON EVERY QWidget AND A BACKGROUND ON ONE
 * OBJECT NAME. A dialog is a top-level window of its own, so it matched the
 * colour rule and not the background one -- light ink on Qt's default light
 * grey, which is why its heading was invisible rather than merely wrong.
 *
 * ⚠ AND IT WAS NEVER FROZEN-SPECIFIC. It reproduces from source, and it was
 * "verified" earlier by asserting the dialog HAD a stylesheet -- 16,440
 * characters of one. Nothing asserted what those characters produced.
 * `tests/test_gui_widgets.py` now samples the rendered pixel. */
QDialog { background: %(SURFACE)s; }
#shell  { background: %(BG)s; }

/* ---- title bar --------------------------------------------------------- */
#titlebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 %(TITLE_TOP)s, stop:1 %(TITLE_BOTTOM)s);
    border-bottom: 1px solid %(LINE)s;
}
#wordmarkHa { font-size: 21px; font-weight: 650; color: %(INK)s; }
#wordmarkTo { font-size: 21px; font-weight: 650; color: %(ACCENT)s; }
#titlesub   { font-size: 11px; color: %(INK_FAINT)s; }
#autolabel  { font-size: 11px; color: %(INK_DIM)s; }
#autotime   { font-size: 11px; font-weight: 600; color: %(INK)s; }

/* ---- tabs -------------------------------------------------------------- */
#tabstrip { background: %(STRIP)s; border-bottom: 1px solid %(LINE)s; }
#tab {
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    color: %(INK_DIM)s;
    font-size: 13px;
    padding: 11px 15px 10px 15px;
    text-align: center;
}
#tab:hover              { color: %(INK)s; }
#tab[selected="true"]   { color: %(INK)s; border-bottom: 2px solid %(ACCENT)s; }
#tab:focus              { outline: none; color: %(INK)s; }

/* [*] THE ONLY PLACE THE DEEP GARNET IS LOUD: a count that needs a person.
 * A FILL with cream type on it -- 5.26, clears AA. It goes quiet at zero
 * rather than showing a garnet nought. */
#badge {
    background: %(REFUSED_FILL)s;
    color: %(REFUSED_TYPE)s;
    border-radius: 9px;
    font-size: 10px;
    font-weight: 700;
    padding: 0px 5px;
}
#badge[zero="true"] { background: %(LINE)s; color: %(INK_FAINT)s; }

/* ---- panes and scrolling ----------------------------------------------- */
#body, #pane { background: %(SURFACE)s; }
QScrollArea { background: %(SURFACE)s; border: 0; }
QScrollArea > QWidget > QWidget { background: %(SURFACE)s; }

QScrollBar:vertical {
    background: %(SURFACE)s;
    width: 10px;
    margin: 0px;
    border: 0;
}
QScrollBar::handle:vertical {
    background: %(LINE)s;
    border-radius: 4px;
    min-height: 28px;
    margin: 0px 3px 0px 3px;
}
QScrollBar::handle:vertical:hover { background: %(LINE_HI)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; border: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: %(SURFACE)s;
    height: 10px;
    margin: 0px;
    border: 0;
}
QScrollBar::handle:horizontal {
    background: %(LINE)s;
    border-radius: 4px;
    min-width: 28px;
    margin: 3px 0px 3px 0px;
}
QScrollBar::handle:horizontal:hover { background: %(LINE_HI)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; border: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---- a show heading ---------------------------------------------------- */
#showtitle { font-size: 13px; font-weight: 600; color: %(INK)s; }
#showmeta  { font-size: 11px; color: %(INK_FAINT)s; }
/* [!] THE RADIUS MUST NOT EXCEED HALF THE BOX. The dot is 15x15 and this said
 * 8px, so Qt clamped it and drew a ROUNDED SQUARE -- a shape that reads as a
 * button rather than as the quiet circular marker the design uses. Caught by
 * looking; every assertion about the tooltip was green. */
#info {
    border: 1px solid %(LINE_HI)s;
    border-radius: 7px;
    color: %(INK_FAINT)s;
    font-size: 9px;
    background: transparent;
    padding: 0px;
}
#info:hover { color: %(ACCENT)s; border: 1px solid %(ACCENT_QUIET)s; }

/* ---- THE ROW: episode . percent . what it was paired with -------------- */
#row { background: transparent; border-left: 2px solid transparent; }
#row:hover                { background: %(HOVER)s; border-left: 2px solid %(LINE_HI)s; }
#row[expanded="true"]     { background: %(HOVER)s; border-left: 2px solid %(ACCENT)s; }
#ep { font-size: 13px; color: %(INK)s; }
#pc { font-size: 13px; font-weight: 650; color: %(OK)s; }
#pc[tier="look"] { color: %(LOOK)s; }
#pc[tier="none"] { color: %(INK_FAINT)s; }
#nm { font-size: 12px; color: %(INK_DIM)s; }
/* [!] ON HOVER ONLY. Eight static markers down a calm list is eight things to
 * look at for no information. The colour carries the state; the OPACITY is
 * animated in app.py, because QSS has no transition. */
#chev { color: %(INK_FAINT)s; font-size: 9px; background: transparent; }
#chev[on="true"] { color: %(ACCENT)s; }

#detkey { font-size: 11px; color: %(INK_FAINT)s; }
#detval { font-size: 11px; color: %(INK_DIM)s; }
#detval[lead="true"] { color: %(INK)s; font-weight: 600; }

/* ---- one quiet line, not nineteen pills -------------------------------- */
#had  { font-size: 11px; color: %(PRESENT)s; }
#hadb { font-size: 11px; color: %(INK_FAINT)s; }
#hadb[kind="notfound"] { color: %(NOT_FOUND)s; }
#hadb[kind="notrack"]  { color: %(NO_TRACK)s; }

/* ---- needs a pick ------------------------------------------------------ */
/* [*] THE GARNET IS A 2px LEFT EDGE AND THAT IS THE WHOLE TREATMENT. In its
 * own tab a failure does not have to be findable among nineteen successes:
 * being here IS the signal. Once paired the edge becomes the success green,
 * because the row has stopped asking. */
#pickhead { background: transparent; border-left: 2px solid %(REFUSED_FILL)s; }
#pickhead:hover { background: %(HOVER)s; }
#pickhead[done="true"] { border-left: 2px solid %(OK)s; }
#pickhead[done="forced"] { border-left: 2px solid %(LOOK)s; }
/* ⭐ RUNBOOK 8f -- PROBABLY NOT OUT YET. The row is not asking, it is waiting,
 * so the edge takes the grey that already means "not on jimaku yet" instead of
 * the garnet that means "needs a person". The pick stays one click away. */
#pickhead[late="true"] { border-left: 2px solid %(NOT_FOUND)s; }
#who  { font-size: 13px; color: %(INK)s; }
#whoi { font-size: 11px; color: %(INK_FAINT)s; }
#best { font-size: 11px; color: %(INK_FAINT)s; }
#best[done="true"] { color: %(OK)s; }
#best[done="forced"] { color: %(LOOK)s; }
#best[late="true"] { color: %(INK_DIM)s; }
#pickrule { background: %(LINE)s; }

#cand {
    background: %(CARD)s;
    border: 1px solid %(LINE)s;
    border-radius: 8px;
}
#cand:hover { background: %(HOVER)s; border: 1px solid %(ACCENT_QUIET)s; }
#cand[chosen="true"] { background: %(CARD_ON)s; border: 1px solid %(ACCENT)s; }
/* ⛔ A card that cannot be used does not answer the pointer (ADVERSARY 2026-09-22
 * A10/A13/A32) -- and one whose file is gone reads as absent, not as a choice. */
#cand:disabled { background: %(CARD)s; border: 1px solid %(LINE)s; }
#cand[chosen="true"]:disabled { background: %(CARD_ON)s; border: 1px solid %(ACCENT)s; }
#cand[gone="true"] { background: transparent; border: 1px dashed %(LINE)s; }
#cand[gone="true"] #nm2 { color: %(INK_FAINT)s; }
#nm2     { font-size: 12px; color: %(INK)s; }
#candsub { font-size: 11px; color: %(INK_FAINT)s; }
#rate    { font-size: 12px; color: %(INK_DIM)s; }

/* ---- buttons ----------------------------------------------------------- */
/* 🚨 THE CORAL IS ON EVERY BUTTON, NOT ONLY THE PRIMARY ONE (2026-09-18).
 * Sonic: *"in the settings i need the buttons to also have the orange or
 * something around them. It just all feels super 'unselectable'... Needs to be
 * a bit more present so they know where to look and where to click."*
 *
 * ⭐ AND IT WAS NOT A MATTER OF DEGREE. Button type was `--ink-dim`, the same
 * family as ordinary secondary text -- so nothing but a thin grey border said
 * a button was a button. A control that reads like a paragraph is a control
 * nobody clicks.
 *
 * Measured on the button's OWN ground, `--raised` (lighter than the card
 * behind it, so a card-ground measurement would have flattered it) --
 * `gui-mock/probe-cardtitle.css`:
 *
 *     --ink-dim       4.72   what it was: legible, and invisible AS A CONTROL
 *     --accent-quiet  4.20   ❌ under AA -- ⛔ the muted coral CANNOT be type
 *     --accent        7.76   ✅  <- taken
 *
 * ⚠ THE MUTED CORAL FAILING IS THE USEFUL PART. The instinctive move is the
 * quieter coral for ordinary buttons and the bright one for the primary; that
 * is unbuildable, because the quiet one is not legible as text. So the two
 * ranks separate by FILL instead: an ordinary button is coral on the panel, a
 * primary one is coral on a coral-tinted ground. Separation by mechanism, the
 * same way REFUSED separates from the accent. */
QPushButton {
    background: %(RAISED)s;
    border: 1px solid %(ACCENT_QUIET)s;
    border-radius: 7px;
    color: %(ACCENT)s;
    font-size: 12px;
    padding: 6px 13px;
}
QPushButton:hover    { background: %(GO_HOVER)s; border: 1px solid %(ACCENT)s; }
QPushButton:pressed  { background: %(GO_HOVER)s; border: 1px solid %(ACCENT)s; }
QPushButton:focus    { outline: none; border: 1px solid %(ACCENT)s; }
/* ⚠ A disabled control must stop looking clickable, which now means losing the
 * coral entirely -- not merely dimming it. */
QPushButton:disabled { background: %(RAISED)s; color: %(INK_FAINT)s;
                       border: 1px solid %(LINE)s; }
/* The PRIMARY action, one rank up: the same coral on a coral-tinted ground. */
#btnGo         { background: %(GO_HOVER)s; border: 1px solid %(ACCENT)s;
                 color: %(ACCENT)s; }
#btnGo:hover   { background: %(GO_HOVER)s; border: 1px solid %(ACCENT)s; }
/* ⭐ *Open video*, inside an expanded row. ⚠ DELIBERATELY QUIET -- smaller and
 * dimmer than an ordinary button. It is a convenience sitting beside the facts
 * of a finished run, not an action the person came to this row to take, and a
 * full-weight button there would read as the point of the panel. */
#openvid       { font-size: 11px; padding: 3px 10px; color: %(INK_DIM)s;
                 border: 1px solid %(LINE_HI)s; }
#openvid:hover { color: %(ACCENT)s; border: 1px solid %(ACCENT_QUIET)s; }
/* the small remove affordance. [!] The crimson, not the fill: this is text. */
#x {
    background: transparent;
    border: 0;
    color: %(INK_FAINT)s;
    font-size: 12px;
    padding: 0px 5px;
}
#x:hover  { color: %(REFUSED_INK)s; }
#x:focus  { outline: none; color: %(REFUSED_INK)s; }

/* ---- settings ---------------------------------------------------------- */
#card     { background: %(CARD)s; border: 1px solid %(LINE)s; border-radius: 9px; }
/* [!] THE RULE BELONGS TO THE CONTAINER, and the label inside it is a
 * DIFFERENT id -- they shared one and the card grew two underlines, a long
 * one across the card and a short one under the four words of the heading. */
#cardhead {
    background: transparent;
    border-bottom: 1px solid %(LINE)s;
}
/* 🚨 `INK`, NOT `INK_FAINT`, AND IT IS A CONTRAST FIX (2026-09-18).
 * Sonic, off the running window: *"The text for titles in settings and such is
 * too light... It reads as the hint text. For example Jimaku key, folders."*
 *
 * ⭐ "IT READS AS THE HINT TEXT" WAS THE LITERAL DIAGNOSIS. `#cardtitle` and
 * `#hint` were the SAME token, so nothing distinguished a section heading from
 * a de-emphasised aside -- the uppercase and the tracking were carrying the
 * whole job on their own.
 *
 * Measured on the card's own ground (#1a1d23, DARKER than --surface, so a
 * measurement against --surface would have flattered it) --
 * `gui-mock/probe-cardtitle.css`:
 *
 *     --ink-faint   2.91   ❌ under the 4.5 AA floor
 *     --ink-dim     5.38   ✅
 *     --ink        13.88   ✅  <- taken
 *
 * ⚠ At 11px, 650 weight and uppercase this is low-mass type; full ink reads as
 * a crisp label rather than as shouting, and spec/05-interface.md defines
 * "modern UX with high integrity" as a contrast floor, not a mood. */
/* ⚠ WHITE, AND CORAL WAS TRIED AND RULED OUT. Round two made this the accent
 * (8.84, perfectly legible) on the reasoning that it would mark a section the
 * way the buttons now mark a control. Sonic, round three: *"I still want the
 * header text white, not coral. But the button outline coral is great."*
 *
 * ⭐ THE DISTINCTION HE IS DRAWING IS WORTH KEEPING: coral means CLICKABLE.
 * Spending it on a heading, which does nothing when clicked, spends the one
 * signal that tells somebody where to act. ⛔ Do not re-propose it. */
#cardtitle {
    background: transparent;
    border: 0;
    color: %(INK)s;
    font-size: 11px;
    font-weight: 650;
}
/* ⚠ Raised with the title it sits beside -- 2.91 to 5.38. A count rendered in
 * the hint colour next to a heading in full ink reads as a different kind of
 * thing entirely, which is not what "· 34 videos" is. */
#cardcount { color: %(INK_DIM)s; font-size: 11px; font-weight: 400; }
/* The one line a brand-new install reads, under the mark. Full ink and larger
 * than body type: it is not an aside, it is the entire content of the tab. */
#emptylead { font-size: 15px; color: %(INK)s; background: transparent; }
/* ⚠ The CRIMSON, not the deep garnet -- this is TEXT. The garnet measures 2.77
 * as an ink and is only ever a fill; `--refused-ink` is the text-weight one
 * that clears the floor. Same rule the row treatment records. */
#keybad { font-size: 12px; color: %(REFUSED_INK)s; background: transparent; }
#hint  { font-size: 11px; color: %(INK_FAINT)s; }
#code  { font-size: 12px; color: %(INK_DIM)s; }
#dotok { font-size: 12px; color: %(OK)s; }
#stale {
    background: %(CARD_ON)s;
    border: 1px solid %(ACCENT_QUIET)s;
    border-radius: 7px;
}
#stalelead { font-size: 11px; color: %(INK)s; font-weight: 600; }
#staletext { font-size: 11px; color: %(INK_DIM)s; }

QLineEdit {
    background: %(BG)s;
    border: 1px solid %(LINE_HI)s;
    border-radius: 6px;
    color: %(INK)s;
    font-size: 12px;
    padding: 5px 9px;
    selection-background-color: %(ACCENT_QUIET)s;
    selection-color: %(REFUSED_TYPE)s;
}
QLineEdit:hover { border: 1px solid %(LINE_HI)s; }
QLineEdit:focus { outline: none; border: 1px solid %(ACCENT)s; }

/* [!] A NATIVE CONTROL IS THEMED BY ITS HOST, NOT BY YOU. An unstyled radio
 * paints Windows blue (#0078d4), which is the one hue this palette does not
 * contain -- caught by LOOKING at a shot, not by any assertion. These rules
 * are the backstop for any plain Qt control that reaches the window; the
 * checkbox the design actually uses is painted in `app.py` so its tick is a
 * tick. [X] A CHECKBOX IS NOT A RADIO: square box, never a circle. A shape is
 * a claim about behaviour. */
QCheckBox { background: transparent; color: %(INK)s; font-size: 12px; spacing: 10px; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid %(LINE_HI)s;
    border-radius: 4px;
    background: %(BG)s;
}
QCheckBox::indicator:hover     { border: 1px solid %(ACCENT_QUIET)s; }
QCheckBox::indicator:checked   { border: 1px solid %(ACCENT)s; background: %(ACCENT)s; }
QCheckBox::indicator:disabled  { border: 1px solid %(LINE)s; background: %(SURFACE)s; }
QCheckBox:focus { outline: none; }

QRadioButton { background: transparent; color: %(INK)s; font-size: 12px; spacing: 10px; }
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid %(LINE_HI)s;
    border-radius: 8px;
    background: %(BG)s;
}
QRadioButton::indicator:hover    { border: 1px solid %(ACCENT_QUIET)s; }
QRadioButton::indicator:checked  { border: 4px solid %(ACCENT)s; background: %(BG)s; }
QRadioButton:focus { outline: none; }

QComboBox {
    background: %(RAISED)s;
    border: 1px solid %(LINE_HI)s;
    border-radius: 6px;
    color: %(INK)s;
    font-size: 12px;
    padding: 4px 9px;
}
QComboBox:hover { border: 1px solid %(ACCENT_QUIET)s; }
QComboBox:focus { outline: none; border: 1px solid %(ACCENT)s; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView {
    background: %(RAISED)s;
    border: 1px solid %(LINE_HI)s;
    color: %(INK)s;
    selection-background-color: %(HOVER)s;
    selection-color: %(ACCENT)s;
    outline: none;
}

/* ---- the blacklist, built for a list nobody will prune ----------------- */
#blist { background: %(BG)s; border: 1px solid %(LINE)s; border-radius: 7px; }
#blrow { background: transparent; border-bottom: 1px solid %(BL_LINE)s; }
#blrow:hover { background: %(SURFACE)s; }
#blcode { font-size: 12px; color: %(INK_DIM)s; }
/* [X] Deemphasise, don't delete: a row whose video is gone is dimmed and
 * labelled, never removed without being asked. */
#blcode[gone="true"] { color: %(INK_FAINT)s; }
#blnote { font-size: 11px; color: %(INK_FAINT)s; }
#blwhen { font-size: 11px; color: %(INK_FAINT)s; }

/* ---- footer ------------------------------------------------------------ */
#footer { background: %(STRIP)s; border-top: 1px solid %(LINE)s; }
#live   { font-size: 12px; color: %(ACCENT)s; }
#sep    { font-size: 12px; color: %(INK_FAINT)s; }
#tally  { font-size: 12px; color: %(INK_DIM)s; }
#credit { font-size: 11px; color: %(INK_FAINT)s; }
/* ⭐ The two links sitting right of the tabs -- feedback and the repo.
   ⛔ The COLOUR is not set here and must not be: Qt paints an <a href> from
   the PALETTE, so `link_label` sets it there. A rule here would look like it
   was working and be ignored. */
#tablink { font-size: 12px; padding: 0 2px; }
#right  { font-size: 12px; color: %(INK_FAINT)s; }
"""


def qss():
    u"""The whole stylesheet, with every token substituted. -> unicode"""
    return _SHEET % colors()


__all__ = ["qss", "colors", "BG", "SURFACE", "RAISED", "LINE", "LINE_HI",
           "INK", "INK_DIM", "INK_FAINT", "ACCENT", "ACCENT_QUIET", "OK",
           "LOOK", "REFUSED_FILL", "REFUSED_TYPE", "REFUSED_INK", "NOT_FOUND",
           "PRESENT", "NO_TRACK", "HOVER", "TITLE_TOP", "TITLE_BOTTOM",
           "STRIP", "CARD", "CARD_ON", "TIP", "SWITCH_ON", "GO_HOVER",
           "BL_LINE", "SHADOW", "LINK", "LINK_CSS", "LINK_HOVER",
           "FAST", "SLOW", "EASE", "LIFT", "GLOW", "MARK_PX", "ICON_SIZES"]
