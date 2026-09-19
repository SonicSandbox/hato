# -*- coding: utf-8 -*-
"""
The things tsubasa does not publish about a subtitle NAME, derived by hato in ONE
module (spec/RUNBOOK.md T1 scope table; orchestrator ruling 2, 2026-09-17).

    release_group(name)    who released it -- never empty
    episode_span(name)     (1, 2) for a file holding episodes 1-2; None for one episode
    is_special(name)       SP / OVA / OAD / NCOP / NCED / S00 / 特別編 / 総集編 / 番外編
    version(name)          2 for `06v2`; 1 when the name carries none
    language_class(name)   "single-ja" | "multi" | "non-ja" | "unknown"
    is_ai(name)            a machine transcription (Whisper and its kin)
    year(name)             the year a name carries, or None
    subtitle_format(name)  "ass" | "ssa" | "srt" | the extension

⛔ NOTHING HERE READS A TITLE, A SEASON OR AN EPISODE NUMBER. Those are tsubasa's,
reached through hato/names.py (LEDGER-HOT.md: never write a second filename
parser). Every rule below reads a TOKEN that tsubasa's public reading leaves out;
`episode_span` only says a name holds SEVERAL episodes, and the numbers it
returns are never used as an episode reading -- a span is refused, not guessed.

⭐ EVERY FUNCTION IS A REQUEST TO TSUBASA. Each docstring's first line says so.
When tsubasa publishes one, the function here becomes a one-line call and its
rule is deleted -- two copies would drift.

⭐ EVERY RULE IS MEASURED, and the count is written beside it. The corpus is
`tsubasa-corpus/naming/catalog.jsonl` (outside the vault): 238,250 real jimaku
filenames, 233,877 distinct, measured by hato's 3a/3b builder on 2026-09-17.
A token that looked plausible and was never seen in it is NOT in a rule --
widen a rule only with a measurement, and write the count down.

⚠ Pure functions of a name. No I/O. `tsubasa.parse_subtitle_name` is the one
tsubasa call made here, and it is public and pure too.
"""
import re

import tsubasa

# ---------------------------------------------------------------------------
# shared token helpers
# ---------------------------------------------------------------------------

#: A bracket or paren group: `[CHS, JPN]`, `(AT-X 1440x1080 MPEG2 AAC)`.
_GROUP = re.compile(r"[\[(]([^\[\]()]*)[\])]")
#: Words inside a group. ⚠ NOT split on `-`: `[SC-Raws]` would read as Chinese.
_GROUP_WORDS = re.compile(r"[\s,&+_/;]+")
_TAG_SPLIT = re.compile(r"[-_]+")


def _stem(name):
    """The name without its final extension (`.srt`, `.7z`)."""
    head, dot, _ext = name.rpartition(".")
    return head if dot else name


def _group_words(name):
    words = []
    for group in _GROUP.findall(_stem(name)):
        words.extend(w for w in _GROUP_WORDS.split(group.casefold()) if w)
    return words


# ---------------------------------------------------------------------------
# subtitle_format
# ---------------------------------------------------------------------------

def subtitle_format(name):
    """tsubasa publishes the extension (Sidecar.ext); the ranking CLASS built on it is hato's."""
    return tsubasa.parse_subtitle_name(name).ext


# ---------------------------------------------------------------------------
# language_class
# ---------------------------------------------------------------------------
# tsubasa's public reading gives `und` for every bracketed language list --
# `[CHS, JPN]`, `[JPN]`, `[CHS]` (RUNBOOK T1). Its sidecar reader resolves the
# dot tag, and hato uses the TAG it returns, never its resolved `lang`:
#   ⚠ measured -- `.ts.ass` resolves to Tsonga (44 names) and `.no-sdh.srt` to
#   Norwegian (13): 57 Japanese files a `lang != "ja"` test would call foreign.
#   `sc-jp` resolves to Sardinian (13) and is Simplified Chinese + Japanese.
#
# Tokens counted in the corpus (bracket/paren words, the last two dot parts,
# and the sidecar tag split on `-`):
#   Japanese  ja 74,995 · jpn 19,179 · jp 18,228 · jap 376 · japanese 236 ·
#             日本語 159 · 日本語字幕 39 · jis 31 · kanji/hir (Kanji+Hir+Eng) 1 ·
#             furigana (JP&furigana) 115
#   Chinese   chs 5,007 · cht 404 · gb 217 · big5 183 · sc 86 · chi 12 (as a tag;
#             `Kobayashi-san Chi no` is a word, and is never in a group or a tag)
#             · tc 2 · cn (ja-cn) 13
#   both      jpsc 1,254 · 简繁日 24 · jptc 1 · 繁日 1
#   English   en/eng/english (ja-en 2,510 · [JPN, ENG] 481)
# ⭐ Chinese tag WITHOUT a Japanese one: 1 of 233,877 names
#   (`[WYQsub]Kizumonogatari Reiketsu Hen[GB][BDRip][1080P].ass`). English
#   without Japanese: 0 once `Kanji+Hir` is read as Japanese.

_JA = frozenset(u"ja jpn jp jap japanese jis kanji hiragana hir furigana "
                u"日本語 日本語字幕 日本語字幕版".split())
_ZH = frozenset(u"chs cht gb big5 sc tc chi cn zh zho".split())
_OTHER = frozenset(u"en eng english".split())
_BOTH = frozenset(u"jpsc jptc 简繁日 繁日".split())
_SIDECAR_FLAGS = re.compile(r"\[[^\]]*\]")

LANGUAGE_CLASSES = ("single-ja", "unknown", "multi", "non-ja")


def _language_tokens(name):
    tokens = set(_group_words(name))
    parts = _stem(name).split(".")
    for part in parts[1:][-2:]:
        tokens.update(w for w in re.split(r"[\s,&+_\-]+", part.casefold()) if w)
    tag = tsubasa.parse_subtitle_name(name).tag
    if tag:
        tokens.update(w for w in _TAG_SPLIT.split(_SIDECAR_FLAGS.sub("", tag).casefold()) if w)
    return tokens


def language_class(name):
    """tsubasa does not publish a language CLASS for a bracketed list like `[CHS, JPN]` -- a candidate for tsubasa to expose."""
    tokens = _language_tokens(name)
    both = bool(tokens & _BOTH)
    ja = both or bool(tokens & _JA)
    foreign = both or bool(tokens & _ZH) or bool(tokens & _OTHER)
    if ja and foreign:
        return "multi"
    if ja:
        return "single-ja"
    if foreign:
        return "non-ja"
    return "unknown"


# ---------------------------------------------------------------------------
# is_ai
# ---------------------------------------------------------------------------
# The spec names `whisper` / `whisperai` (02-data-model.md §Candidate ranking).
# ⚠ A bare substring is WRONG, measured: 166 names contain "whisper", and 22 of
# them are titles -- Whisper of the Heart (5), Fate/strange Fake -Whispers of
# Dawn- (7), Ghost in the Shell -- Ghost Whisper(s) (6), Moonlight Whispers (2),
# The Whispered City (2). Every AI marker measured is a LABEL: joined to "AI",
# inside a bracket or paren group, a "generated by/using" phrase, or a lowercase
# leading word. Each shape, with its count:
_AI_ANYWHERE = (
    # WhisperAI · Whisper AI · _WhisperAI · [WhisperAI-Cleaned&Quality Checked]   (45)
    re.compile(r"whisper[\s_\-]*ai(?![a-z])", re.I),
    # [AI Generated] · [AI-Generated] · [Auto Generated] · [Whisper Generated]
    # · [Generated by Whisper] · [Generated by Gemini 2.5 Pro] · generated using Whisper (150)
    re.compile(r"(?<![a-z])(?:(?:ai|auto|whisper)[\s_\-]*generated|generated\s+(?:by|using))(?![a-z])", re.I),
    # S1 - 08.subgen.large-v3-turbo.jpn.srt -- subgen runs Whisper             (13)
    re.compile(r"(?<![a-z])subgen(?![a-z])", re.I),
    # whisper Muv-Luv Alternative - S01E08 - ... · whisper Kimi Ga Nozomu Eien  (27)
    # ⚠ case-SENSITIVE: "Whisper of the Heart.srt" starts with the title word.
    re.compile(r"^whisper\s"),
)
_WORD_WHISPER = re.compile(r"(?<![a-z])whisper(?![a-z])")
_WORD_AI = re.compile(r"(?<![a-z])ai(?![a-z])")
_MACHINE_TEXT = re.compile(r"transcri|translat")


def is_ai(name):
    """tsubasa does not publish an AI-generation marker -- a candidate for tsubasa to expose."""
    if any(rule.search(name) for rule in _AI_ANYWHERE):
        return True
    for group in _GROUP.findall(name):
        words = group.casefold()
        if _WORD_WHISPER.search(words):
            return True                 # (Whisper) · [Generated by Whisper]           (1 + above)
        if _WORD_AI.search(words) and _MACHINE_TEXT.search(words):
            return True                 # (AI transcribed, some errors) · (Bad transcription,
            #                             possibly AI) · (AI Translated From English)  (53)
    return False                        # ⚠ [AI-Raws] (18), [FREESUBTITLES.AI]: a word, no verb


# ---------------------------------------------------------------------------
# is_special
# ---------------------------------------------------------------------------
# The spec: "Specials / OVA / NCOP / NCED ... if the parsed type is a special, do
# not range-align" (06-edge-cases.md §2). tsubasa's public reading of a special
# carries a FAKE episode -- `SP1` -> 1, `OVA - 01` -> 1, `OAD 02` -> 2 (RUNBOOK
# T1) -- which is exactly what must never reach a range. Counted:
#   SP / SPn   945   (`[SP05]`, `SP36`, `孤独のグルメSP`; ⚠ also the drama title
#                     `SP` -- harmless here: a special is matched LITERALLY, and a
#                     video of that drama carries the same token)
#   OVA        373 · OAD 45 · NCOP/NCED 16 (tsubasa already skips these)
#   S00Exx     134   (the season-zero convention)
#   特別編 · 総集編 · 番外編   222
# ⚠ NOT a rule, measured: "Special" (379, mostly titles -- `Special Rescue
# Police Winspector`), OP/ED (339, mostly CRC32 hex and `[OP&ED Subs Included]`).
_SPECIAL = re.compile(
    r"(?<![A-Za-z])(SP)\d{0,3}(?![A-Za-z])"                 # SP, SP1, [SP05]  (uppercase only)
    r"|(?<![A-Za-z])(OVA|OAD)\d{0,3}(?![A-Za-z])"
    r"|(?<![A-Za-z])(NCOP|NCED)\d{0,3}(?![A-Za-z])"
    r"|(?<![A-Za-z0-9])(S00)E\d{1,4}(?![0-9])"
    u"|(特別編|総集編|番外編)",
    re.I)


def _special_marker(name):
    """The special token a name carries, folded (`sp`, `ova`, `s00`, `総集編`), or None.
    The one rule behind is_special AND the literal match hato/episodes.py makes."""
    for m in _SPECIAL.finditer(_stem(name)):
        token = next(g for g in m.groups() if g)
        if token.casefold() == "sp" and token != "SP":
            continue                    # `sp` / `Sp` is a word; only uppercase SP is the marker
        return token.casefold()
    return None


def is_special(name):
    """tsubasa does not publish an episode TYPE, so a special reads as a plain episode -- a candidate for tsubasa to expose."""
    return _special_marker(name) is not None


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------
# tsubasa strips the version for matching (`06v2` -> episode 6, RUNBOOK T1) and
# publishes nothing of it; the spec keeps it for RANKING (06-edge-cases.md §2).
#   <digit>v<n>      1,498   `07v2` · `S01E06v2` · `13.5v2` · `176v2` · `1640+977v9` (NanakoRaws uses v9)
#   ]v<n> · .v<n>.   `[JPN]v2.ass` · `[90A0DFAC]v2.srt` · `22.v2.srt` · `H.264.V2-MagicStar`
#   <digit> v<n>     `UBW - 00 v2 [1280×720 …]` · `1648+938 v2 (EX-CS2 …)`
#   ⚠ NOT a version, measured: `Kamen Rider V3` (a title), `large-v3-turbo` (a
#   Whisper model), `(OCR v3)` -- none has a digit or a closing bracket before the v.
_VERSION = re.compile(r"(?:(?<=[0-9])|(?<=[0-9]\s)|(?<=[\])])|(?<=\.))v(\d{1,2})(?=$|[\s.\-\[(_])", re.I)


def version(name):
    """tsubasa does not publish the release version (`06v2`) -- a candidate for tsubasa to expose."""
    found = [int(v) for v in _VERSION.findall(_stem(name))]
    return max(found) if found else 1


# ---------------------------------------------------------------------------
# episode_span
# ---------------------------------------------------------------------------
# ⛔ A file holding two episodes is REFUSED, not guessed (RUNBOOK 3a). tsubasa
# reads the FIRST number and says nothing: `Show - 01-02` -> episode 1 with the
# title `Show 02`; `01+02` -> 1 (RUNBOOK T1). Shapes counted:
#   E39-40 · E04-E07 · S01E01-E02 · S01E01E02 · EP01-02     571
#   #1~3 · ＃01～02 · #01-#03                                 (in 301 `~` hits)
#   620+621 · 238+276+279                                     504
#   第15-16話 · 第8～14話                                     42
#   OVA - 01-02 · Show - 01-12 [BD]                           (fansub ` - ` form)
# ⚠ NOT a span, measured: dates (`2023-06-02`, `[11-16_19-00-00]`, `(89～93年)`),
# resolutions (`1920-1440x1080`), CRC32 hex (`[E17E865F]`). A span must read
# forward (last > first) and be a plausible run (at most 199 episodes).
_RANGE = u"(\\d{1,4})\\s*[-~〜～]\\s*(?:#|＃|E[Pp]?)?(\\d{1,4})"
_SPAN_RULES = (
    # ` - 01-02 ` · `_-_01-02_`
    re.compile(u"(?:^|\\s-\\s|_-_)" + _RANGE + u"(?=$|[\\s_.\\[(])"),
    # E39-40 · E04-E07 · S01E01-02 · S01E01-E02 · S01E01E02 · EP01-02
    re.compile(u"(?<![A-Za-z0-9])(?:S\\d{1,2})?E[Pp]?(\\d{1,4})\\s*(?:[-~〜～]\\s*(?:E[Pp]?)?|E[Pp]?)"
               u"(\\d{1,4})(?![0-9A-Za-z])"),
    # #1~3 · ＃01～02 · #01-#03 -- and never the `#16-2023-06-02` of a dated capture
    re.compile(u"[#＃]" + _RANGE + u"(?![0-9])(?!\\s*[-/.]\\s*\\d)"),
    # 第15-16話
    re.compile(u"第" + _RANGE + u"\\s*話"),
)
_PLUS = re.compile(r"(?:^|\s-\s|_-_)(\d{1,4}(?:\+\d{1,4})+)(?=$|[\s_.\[(])")
_SPAN_MAX = 199


def episode_span(name):
    """tsubasa does not publish that one file holds several episodes -- a candidate for tsubasa to expose."""
    stem = _stem(name)
    m = _PLUS.search(stem)
    if m:
        numbers = tuple(int(n) for n in m.group(1).split("+"))
        if len(set(numbers)) > 1:
            return numbers
    for rule in _SPAN_RULES:
        for m in rule.finditer(stem):
            first, last = int(m.group(1)), int(m.group(2))
            if first < last <= first + _SPAN_MAX:
                return (first, last)
    return None


# ---------------------------------------------------------------------------
# year
# ---------------------------------------------------------------------------
# anitopy glues a year into the title (`Kimi.no.Na.wa.2016` -> `Kimi no Na wa
# 2016`, RUNBOOK T1) and `(2016)` is dropped without being published.
#   (19xx|20xx) in parens/brackets   4,872   `Pocket Monsters (2023)`, `(1979)`
#   dot/space-delimited 19xx|20xx    3,894   `Giant.Rumble.1964.1080p`
# ⚠ NOT a year, measured: a date (`(2020.10.04)`, `2023-06-02`, `2023年07月10日`);
# a resolution -- the first draft read `[1440-1920@KFMVFR…]` and `1920×1080` as
# 1920, so a bare year must sit between `.`, space or `_`; and `Blade Runner
# 2049 (2017)` -- a bracketed year wins over a bare one.
_YEAR_BRACKETED = re.compile(r"[(\[]((?:19|20)\d\d)[)\]]")
_YEAR_BARE = re.compile(r"(?:^|(?<=[.\s_]))((?:19|20)\d\d)(?=$|[.\s_])(?![.\s_]\d{1,2}[.\-/]\d)")


def year(name):
    """tsubasa does not publish a year (anitopy glues it into the title) -- a candidate for tsubasa to expose."""
    stem = _stem(name)
    found = _YEAR_BRACKETED.findall(stem) or _YEAR_BARE.findall(stem)
    return int(found[-1]) if found else None


# ---------------------------------------------------------------------------
# release_group
# ---------------------------------------------------------------------------
# The spec: "group the entry's files by release group -- the bracketed prefix"
# (02-data-model.md). ⚠ PART 1 DEFECT, ruled for 3a: an unbracketed file's group
# comes from the rest of its name, and a file whose group cannot be told apart
# is aligned ALONE, never pooled. Measured over the corpus:
#   leading [Group]                         71,417 of 233,877
#   unbracketed                            162,449
#     distributor token                     netflix 34,551 · amazon 12,894 · hulu 7,884 ·
#                                           bandai 3,676 · nf 2,330 · amzn 2,028 · fod 903 ·
#                                           u-next 719 · abema 704 · kktv 562 · viki 545 ·
#                                           dsnp 540 · tver 518 · dmmtv 478 · wowow 471 ·
#                                           abema-tv 322 · cr 57 · disney+ 53 · telasa 47 ·
#                                           dmm 45 · iqiyi 44 · unext 21 · nhk+ 20 · paravi 17
#     source token                          webrip 54,897 · web-dl 15,401 · hdtv 4,022 ·
#                                           bd 1,398 · bluray 544 · dvd 452 · bdrip 138 ·
#                                           web 136 · dvdrip 132 · blu-ray 68 · tvrip 22 ·
#                                           [TV] (bracketed)
#     scene `-Group` after a codec or date  16,756  (-MagicStar 6,006 · -JPTVclub 4,406 ·
#                                           -dougal 882 ...)
#     an encoder descriptor group           `[1440-1920x1080@KFMVFR.hevc10_crf 20]`,
#                                           `(AT-X 1280x720 x264 AAC)`
#     none of these -> ALONE                ~76,000 (`タイトル ＃01.srt`, `Sazae-san (2020.10.04).srt`)
# Entry 11446's 20 unbracketed files are TWO releases, measured on the capture:
# `…WEBRip.Amazon.ja-jp[sdh].srt` (10) and `…WEBRip.Netflix.ja[cc].srt` (10).

_LEADING_BRACKET = re.compile(r"^\s*\[([^\[\]]+)\]")
_DISTRIBUTORS = frozenset(u"netflix amazon hulu bandai nf amzn fod u-next abema kktv viki dsnp "
                          u"tver dmmtv wowow abema-tv cr disney+ telasa dmm iqiyi unext nhk+ paravi".split())
_SOURCES = frozenset(u"webrip web-dl hdtv bd bluray dvd bdrip web dvdrip blu-ray tvrip".split())
_DOT_TOKENS = re.compile(r"[.\s_]+")
_SCENE = re.compile(r"(?:x26[45]|h\.?26[45]|264|265|hevc|avc|aac[\d.]*|ac3|flac|dts|ddp[\d.]*|xvid|"
                    r"mpeg2|\d{1,2}bit|web-?dl|webrip|hdtv|bluray|remux|\d{4}-\d{2}-\d{2}|v\d)"
                    r"-([A-Za-z][A-Za-z0-9@_]{1,24})$", re.I)
_DESCRIPTOR = re.compile(r"\d{3,4}x\d{3,4}|@|hevc|x26[45]|h\.?26[45]|mpeg2", re.I)


def release_group(name):
    """tsubasa does not publish a release group -- a candidate for tsubasa to expose."""
    m = _LEADING_BRACKET.match(name)
    if m and m.group(1).strip():
        return m.group(1).strip()
    fingerprint = _unbracketed_fingerprint(name)
    return fingerprint or name or u"(unnamed)"


def _unbracketed_fingerprint(name):
    """The release-constant tokens of an unbracketed name, casing kept --
    distributor and source tokens, then descriptor groups, then the scene group,
    then the sidecar tag: `WEBRip.Amazon.ja-jp[sdh]` -- or "" when nothing tells
    it apart. ⚠ The tag alone never makes a group: `.ja.srt` is everyone's."""
    side = tsubasa.parse_subtitle_name(name)
    stem = side.stem
    parts = []
    scene = _SCENE.search(stem)
    for token in _DOT_TOKENS.split(stem):
        low = token.casefold()
        if low in _DISTRIBUTORS or low in _SOURCES:
            parts.append(token)
    for group in _GROUP.findall(stem):
        if group.strip().casefold() == "tv":
            parts.append("[%s]" % group.strip())
        elif _DESCRIPTOR.search(group):
            parts.append("(%s)" % group.strip())
    if scene:
        parts.append("-" + scene.group(1))
    if not parts:
        return ""
    if side.tag:
        parts.append(side.tag)
    return ".".join(parts)
