# -*- coding: utf-8 -*-
"""
hato/tokens.py -- the facts about a NAME that tsubasa does not publish.

Every rule is checked BOTH ways: the shape it exists for, and the look-alike it
must not take. A rule that says yes to everything passes every positive check;
only the look-alikes tell it apart.

⭐ The names are REAL jimaku filenames -- the capture (tests/fixtures/api), or the
naming corpus that justified the rule (tsubasa-corpus/naming/catalog.jsonl,
233,877 distinct names, measured 2026-09-17) -- except those marked
"(constructed)", which put a measured token into a minimal name.

What it structurally cannot cover: the corpus itself. It lives outside the vault,
so this suite quotes its shapes; the counts behind each rule sit beside the rule
in tokens.py, and re-measuring them is a probe's job, not a suite's.
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from hato import tokens

ROOT = Path(__file__).resolve().parents[1]
FILES = json.loads((ROOT / "tests" / "fixtures" / "api" / "entries_11446_files.json")
                   .read_text(encoding="utf-8"))
NAMES = [f["name"] for f in FILES]
BRACKETED = [n for n in NAMES if n.startswith("[")]
UNBRACKETED = [n for n in NAMES if not n.startswith("[")]


# ---------------------------------------------------------------------------
# the module's own contract
# ---------------------------------------------------------------------------

SEVEN = ("release_group", "episode_span", "is_special", "version", "language_class", "is_ai", "year")


def test_every_rule_says_on_its_first_line_that_tsubasa_does_not_publish_it():
    for name in SEVEN:
        first = inspect.getdoc(getattr(tokens, name)).splitlines()[0]
        assert "tsubasa does not publish" in first and "candidate for tsubasa to expose" in first, (name, first)


def test_tokens_never_reads_a_title_a_season_or_an_episode():
    """⛔ LEDGER-HOT.md: never a second parser. Nothing in tokens.py may touch a
    reading tsubasa owns -- checked on the syntax tree, so a comment cannot hide
    a use and a use cannot hide in a comment."""
    tree = ast.parse(Path(tokens.__file__).read_text(encoding="utf-8"))
    touched = sorted({node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
                     & {"title", "season", "episode", "episode_candidates", "scan", "read_names"})
    imported = sorted({alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                       for alias in node.names} & {"names", "read_names", "scan"})
    assert touched == [] and imported == [], (touched, imported)


# ---------------------------------------------------------------------------
# release_group
# ---------------------------------------------------------------------------

def test_a_bracketed_name_belongs_to_its_bracketed_prefix():
    assert BRACKETED, "the capture holds bracketed releases"
    for n in BRACKETED:
        assert tokens.release_group(n) == n[1:n.index("]")], n


def test_the_captures_unbracketed_files_are_two_releases_not_one_nameless_bucket():
    """🚨 LEDGER.md §logic: a bracket-only grouper put all 20 into one nameless
    bucket. Measured on the capture: 10 `WEBRip.Amazon` and 10 `WEBRip.Netflix`
    -- the expectation is read off the distributor token, not off tokens.py."""
    by_distributor = {}
    for n in UNBRACKETED:
        by_distributor.setdefault(n.split(".WEBRip.")[1].split(".")[0], set()).add(n)
    by_group = {}
    for n in UNBRACKETED:
        by_group.setdefault(tokens.release_group(n), set()).add(n)
    assert len(by_distributor) >= 2, by_distributor
    assert sorted(map(sorted, by_group.values())) == sorted(map(sorted, by_distributor.values())), sorted(by_group)
    assert all(g and g not in BRACKETED for g in by_group), sorted(by_group)


def test_a_group_is_never_empty():
    extra = [u"", u"[] Show - 01.ass", u".srt", u"[ ] Show - 01.ass"]
    assert [n for n in NAMES + extra if not tokens.release_group(n)] == []


@pytest.mark.parametrize("a,b", [
    # the scene group tells two otherwise identical releases apart (constructed from -MagicStar / -NSBC)
    (u"Koi.Desu.Yankee.kun.to.Hakujou.Girl.EP04.1080p.HULU.WEB-DL.AAC2.0.H.264-MagicStar.srt",
     u"Koi.Desu.Yankee.kun.to.Hakujou.Girl.EP04.1080p.HULU.WEB-DL.AAC2.0.H.264-NSBC.srt"),
    # the distributor does, with the same source and the same tag (constructed from measured tokens)
    (u"今日から俺は.S01E03.WEB-DL.Hulu.ja.srt", u"今日から俺は.S01E03.WEB-DL.FOD.ja.srt"),
    # the encoder descriptor does, too
    (u"マー姉ちゃん（０７６） - [1920-1440x1080@KFMVFR.hevc10_crf 20][字].ass",
     u"マー姉ちゃん（０７６） - [1440-FHD@KFMVFR.hevc10_crf 20_p 5][字].ass"),
])
def test_unbracketed_releases_are_told_apart_by_the_rest_of_their_name(a, b):
    assert tokens.release_group(a) != tokens.release_group(b)


@pytest.mark.parametrize("a,b", [
    (u"Koi.Desu.Yankee.kun.to.Hakujou.Girl.EP04.1080p.HULU.WEB-DL.AAC2.0.H.264-MagicStar.srt",
     u"Koi.Desu.Yankee.kun.to.Hakujou.Girl.EP05.1080p.HULU.WEB-DL.AAC2.0.H.264-MagicStar.srt"),
    (u"今日から俺は.S01E03.WEB-DL.Hulu.ja.srt", u"今日から俺は.S01E04.WEB-DL.Hulu.ja.srt"),
    (u"マー姉ちゃん（０７６） - [1920-1440x1080@KFMVFR.hevc10_crf 20][字].ass",
     u"マー姉ちゃん（０７７） - [1920-1440x1080@KFMVFR.hevc10_crf 20][字].ass"),
    (u"Brave Raideen - E48 [TV].srt", u"Brave Raideen - E49 [TV].srt"),
])
def test_one_unbracketed_releases_episodes_share_one_group(a, b):
    """The other half: a rule that told everything apart would align every file
    ALONE and pass the check above."""
    assert tokens.release_group(a) == tokens.release_group(b) != a


def test_a_name_with_nothing_that_tells_its_release_apart_is_aligned_alone():
    """Ruled for 3a: never pooled. ~40,700 corpus names have this shape."""
    a, b = u"カム・カム・エヴリバディ ＃036.srt", u"カム・カム・エヴリバディ ＃037.srt"
    assert (tokens.release_group(a), tokens.release_group(b)) == (a, b)


def test_a_language_tag_alone_never_makes_a_release():
    a, b = u"Show - 01.ja.srt", u"Another Show - 02.ja.srt"         # (constructed)
    assert tokens.release_group(a) != tokens.release_group(b)


# ---------------------------------------------------------------------------
# episode_span
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,span", [
    (u"[Group] Show - 01-02 [JPN].ass", (1, 2)),                  # RUNBOOK T1: tsubasa reads episode 1
    (u"[shincaps] Katekyou Hitman REBORN! - 193-194 (KIDS 1440x1080 MPEG2 AAC).srt", (193, 194)),
    (u"[shincaps] Takunomi. - 01-12 (AT-X 1440x1080 MPEG2 AAC).srt", (1, 12)),
    (u"Brave Raideen - E49-50 [TV].srt", (49, 50)),
    (u"Ashita No Joe 2 - E21-E24 - [TV].srt", (21, 24)),
    (u"[MagicStar] -50kg no Cinderella EP07-EP08 END [WEBDL] [1080p].srt", (7, 8)),
    (u"Show.S01E01E02.WEBRip.ja.srt", (1, 2)),                    # (constructed)
    (u"Show.S01E01-02.WEBRip.ja.srt", (1, 2)),                    # (constructed)
    (u"スローループ #01-#04 [字]-2024-03-02-JPTVclub.srt", (1, 4)),
    (u"愛という名のもとに＃07～12.srt", (7, 12)),
    (u"MAJOR 4th season 第15-16話 (BSP).ass", (15, 16)),
    (u"[NanakoRaws] Doraemon (1979) - 238+276+279 (EX-CS2 1920x1080 x265 AAC).srt", (238, 276, 279)),
    (u"[HorribleSubs] Momokuri - 13+14 [1080p].ass", (13, 14)),
])
def test_a_name_holding_several_episodes_reads_as_a_span(name, span):
    assert tokens.episode_span(name) == span


@pytest.mark.parametrize("name", [
    u"[字]静かなるドン-中山秀征版-【連日】#16-2023-06-02-JPTVclub.srt",                     # a dated capture
    u"[Elitist_Fags]_Stitch!_Zutto_Saikou_no_Tomodachi_-_15_[11-16_19-00-00]_(TV_ASAHI_1440x1080_MPEG2_TS).ass",
    u"[SumiSora][CLANNAD-AfterStory-][DVDRip][24][x264_aac][GB_Big5_JIS](E17E865F).ass",       # CRC32 hex
    u"[Erai-raws] Tougen Anki - 17 [1080p NF WEB-DL AVC AAC][JPN][9E344E61].ass",
    u"笑ゥせぇるすまん (89～93年)【デジタルリマスター版】.S01E50.家庭教師／余生.WEBRip.Netflix.ja[cc].srt",
    u"[Group] 86 - Eighty Six - 01 [JPN].ass",                                                 # a number in the title
    u"[Elitist Fags] Whisper of the Heart (1995)  07-09 21-00-00 (NTV 1440x1080 MPEG2 TS).ass",
    u"マー姉ちゃん（０７６） - [1920-1440x1080@KFMVFR.hevc10_crf 20][字].ass",                 # a resolution
    u"Lone Wolf and Family - 01+01.srt",                                                       # (constructed) not two episodes
    # ⚠ refused ONLY by the bound -- 40 corpus names have this shape
    u"HUNTER～その女たち、賞金稼ぎ～＃08-02.srt",                                              # episode 8, part 2
    u"[CBM] Monster - 11 - 511 Kinderheim [6C70C4E4].srt",                                     # 511 is the title
    u"[UTW]_Shinsekai_Yori_-_04_[BD][h264-720p_AC3][E6817E15].srt",                            # CRC32 again
])
def test_a_look_alike_is_not_a_span(name):
    assert tokens.episode_span(name) is None


def test_every_file_in_the_capture_holds_one_episode():
    assert [n for n in NAMES if tokens.episode_span(n)] == []


# ---------------------------------------------------------------------------
# is_special
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,marker", [
    (u"[Group] Show - SP1 [JPN].ass", u"sp"),                                   # RUNBOOK T1: reads episode 1
    (u"[Kamigami&VCB-Studio] Sekko Boys [SP05][Ma10p 1080p][x265 aac].jp.ass", u"sp"),
    (u"(2016.01.01)_孤独のグルメSP.srt", u"sp"),
    (u"[Group] Show OVA - 01.ass", u"ova"),                                      # RUNBOOK T1: reads episode 1
    (u"夏目友人帳.S04OVA01.ニャンコ先生とはじめてのおつかい.WEBRip.Netflix.ja[cc].srt", u"ova"),
    (u"[Kamigami] Hoozuki no Reitetsu - OAD 03 [DVD 576p x264 AAC][JPN].ass", u"oad"),
    (u"今日から俺は.S00E11.スペシャルドラマ未公開シーン復活版.WEB-DL.Hulu.ja.srt", u"s00"),
    (u"おちょやん 総集編#2（後編） - [1440-1920x1080@KFMVFR.hevc10_crf 20][字].ass", u"総集編"),
    (u"あんぱん 特別編（１）「健ちゃんのプロポーズ」 - [1440-1920@KFMVFR.hevc10_crf 20_p 8][字].ass", u"特別編"),
    (u"[XKsub] Hyouka - [NCOP01][優しさの理由][CHS, JPN].ass", u"ncop"),
])
def test_a_special_is_recognised_with_its_marker(name, marker):
    assert tokens.is_special(name) and tokens._special_marker(name) == marker


@pytest.mark.parametrize("name", [
    u"Special Rescue Police Winspector 003.srt",                 # "Special" is a title word (measured: 379, mostly titles)
    u"[Erai-raws] Dungeon Meshi - 17 [720p][JPN][7ED50C17].ass",  # OP/ED inside CRC32 hex
    u"[SOFCJ-Raws] Rurouni Kenshin - 94 (DVDRip 768x576 x264 VFR 10bit FLAC) [OP&ED Subs Included].ass",
    u"SPY x FAMILY - 01 [JPN].ass",                               # (constructed) SP inside a word
    u"[Group] Show - 01 [sp].ass",                                # (constructed) lowercase is a word, not the marker
])
def test_a_look_alike_is_not_a_special(name):
    assert not tokens.is_special(name)


def test_nothing_in_the_capture_is_a_special():
    assert [n for n in NAMES if tokens.is_special(n)] == []


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,v", [
    (u"[Group] Show - 06v2 [JPN].ass", 2),                                      # RUNBOOK T1: episode 6
    (u"[Judas] Kaijuu 8 Gou - S01E06v2.srt", 2),
    (u"[HaSub] Yuru Yuri San Hai! - 08v3 [720 AVC][CHT, JPN].ass", 3),
    (u"[NanakoRaws] Onegai AiPri S01E23v9 (TVA TV 1080p HEVC AAC).ass", 9),
    (u"[Group] Show - 13.5v2 [JPN].ass", 2),                                    # (constructed)
    (u"[Kamigami] Kyoukai no kanata - 05 [1920×1080 x264 AAC][JPN].v2.ass", 2),
    (u"[kamigami] Haikyuu!! S4 - 21 [1080p x265 Ma10p AAC][JPN]v2.ass", 2),
    (u"Umi.no.Hajimari.EP01.1080p.AMZN.WEB-DL.DDP2.0.H.264.V2-MagicStar.srt", 2),
    (u"[kamigami] Fate stay night UBW - 00 v2 [1280×720 x264 AAC].ass", 2),
])
def test_the_release_version_is_read(name, v):
    assert tokens.version(name) == v


@pytest.mark.parametrize("name", [
    u"Kamen Rider V3 - E17 [TV].srt",              # a title
    u"S1 - 08.subgen.large-v3-turbo.jpn.srt",      # a Whisper model name
    u"Perfect Blue (OCR v3) Perfect!.srt",
    u"[Haruhana] Sousou no Frieren - 31 [WebRip][HEVC-10bit 1080p][JPN].ass",
])
def test_a_name_without_a_release_version_is_version_1(name):
    assert tokens.version(name) == 1


# ---------------------------------------------------------------------------
# language_class
# ---------------------------------------------------------------------------

def test_the_captures_language_classes_follow_its_tags():
    """Expectation read off the literal tags, independently of tokens.py:
    `[CHS, JPN]` is two languages, `[JPN]` / `.ja…` is Japanese only, and the
    broadcast captions (NanakoRaws, shincaps) carry no tag at all."""
    def expected(n):
        if u"[CHS, JPN]" in n:
            return "multi"
        if u"[JPN]" in n or u".ja-jp[" in n or u".ja[" in n:
            return "single-ja"
        return "unknown"
    got = dict((n, tokens.language_class(n)) for n in NAMES)
    assert got == dict((n, expected(n)) for n in NAMES)
    assert set(got.values()) == {"multi", "single-ja", "unknown"}


@pytest.mark.parametrize("name,cls", [
    (u"[Kamigami] Ao Haru Ride - 04 [1280x720 x264 AAC][JPN, CHS].ass", "multi"),
    (u"[Kamigami] Shingeki no Kyojin - #3.25 OAD2 [1024x576 x264 AAC][CHT, JPN].ass", "multi"),
    (u"[AC] Psycho-Pass 2 (2014) - 05 [Blu-Ray][720p][Lucifer22][JPN, ENG].ass", "multi"),
    (u"[Nekomoe kissaten] Uma Musume [04][BDRip].JPSC.ass", "multi"),
    (u"[AC] Boku dake ga Inai Machi - 05 [720p][Lucifer22].ja-en.ass", "multi"),
    (u"[NoBody][DARLING in the FRANXX][08][BDRip][1920x1080_AVC_FLACx2].chs&jpn.ass", "multi"),
    (u"[SGS][Kimi_to_Boku][02][1280x720][H.264_AAC][7F95DF72].sc-jp.ass", "multi"),     # tsubasa: Sardinian
    (u"[Nekomoe kissaten] Munou na Nana 10 [WebRip].ja-cn.ass", "multi"),
    (u"Spirited Away (Kanji+Hir+Eng).srt", "multi"),
    (u"[MILKs&LoliHouse] Everyday Host - 02 [WebRip][JPN].ass", "single-ja"),
    (u"ワンピース ＴＨＥ ＭＯＶＩＥ デッドエンドの冒険.WEBRip.Amazon.ja-jp[sdh].srt", "single-ja"),
    (u"[Judas] Anne Shirley - S01E16v2.jp.srt", "single-ja"),
    (u"[WYQsub]Kizumonogatari Reiketsu Hen[GB][BDRip][1080P].ass", "non-ja"),         # the corpus's only one
    (u"[GRUNNRAW] Yumeiro Patissiere SP Professional - 13 (NTV MPEG2-TS 1440x1080).ts.ass", "unknown"),  # tsubasa: Tsonga
    (u"[HorribleSubs] BOFURI - 01 [1080p].no-sdh.srt", "unknown"),                    # tsubasa: Norwegian
    (u"[shincaps] Kobayashi-san Chi no Maid Dragon - 08 (AT-X 1440x1080 MPEG2 AAC).ass", "unknown"),  # Chi is a word
    (u"[SC-Raws] Show - 01.ass", "unknown"),                                           # (constructed) SC in a group name
])
def test_the_language_class_is_read_from_tags_never_from_a_resolved_code(name, cls):
    assert tokens.language_class(name) == cls


# ---------------------------------------------------------------------------
# is_ai
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    u"[Group] Show - 01 [whisperai].srt",                      # RUNBOOK T1's shape
    u"[WhisperAI] Yamada-kun to 7-nin no Majo - 03.srt",
    u"AhoGirl_S01E04_WhisperAI.srt",
    u"[Whisper Generated] Saikin Yatotta Maid ga Ayashii - 05.jpn.srt",
    u"ムカムカパラダイス(1993) 第25話 「蘭華のヒ・ミ・ツ」 (640x480 x265) [Generated by Whisper].ja.srt",
    u"whisper Muv-Luv Alternative - S01E08 - 帝都動乱.srt",
    u"Rainbow Nisha Rokubou no Shichinin (Whisper).zip",
    u"[Erai-raws] Oresuki - Oretachi no Game Set (Whisper AI).srt",
    u"[bb] IDOLM@STER꞉ XENOGLOSSIA - 14 [480p][Generated by Gemini 2.5 Pro].v2.srt",
    u"(Hi10)_Brynhildr_in_the_Darkness_-_11 [AI Generated][Minor Mistakes].srt",
    u"[Auto Generated] Persona 5 EP03 (Has Errors).srt",
    u"GTO EP40 (Bad transcription, possibly AI).srt",
    u"Aria The Animation S01E03 (AI transcribed, some errors).srt",
    u"S1 - 08.subgen.large-v3-turbo.jpn.srt",
])
def test_an_ai_generated_name_is_recognised(name):
    assert tokens.is_ai(name)


@pytest.mark.parametrize("name", [
    u"Whisper of the Heart (1995).srt",                         # titles -- 22 of the corpus's 166 "whisper" names
    u"Whisper of the Heart.srt",
    u"[Elitist Fags] Whisper of the Heart (1995)  07-09 21-00-00 (NTV 1440x1080 MPEG2 TS).ass",
    u"[shincaps] Fate strange Fake -Whispers of Dawn- (AT-X 1440x1080 MPEG2 AAC).ass",
    u"Ghost in the Shell Arise - Border 2 Ghost Whisper (2013) 720p BRRiP x264 AAC [Team Nanban].ja.srt",
    u"The.Whispered.City.2000.1080p.BluRay.FLAC2.0.H265.10bit-dougal.srt",
    u"[AI-Raws] 地球へ… 01 (BD HEVC 1920x1080 FLAC 日本語字幕)[D4C3E].SUP.7z",   # a group called AI
    u"[NanakoRaws] AI no Idenshi - 01 (1080p).ass",
    u"[NanakoRaws] Jijou wo Shiranai Tenkousei ga Guigui Kuru. - 01 (1080p).[FREESUBTITLES.AI].srt",
    u"[Shiniori-Raws] Serial Experiments Lain - 01 (BD 1440x1080 x264 10bit AAC) (Bad transcription, missing lines).srt",
])
def test_a_look_alike_is_not_ai(name):
    assert not tokens.is_ai(name)


def test_nothing_in_the_capture_is_ai():
    assert [n for n in NAMES if tokens.is_ai(n)] == []


# ---------------------------------------------------------------------------
# year
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,y", [
    (u"Kimi.no.Na.wa.2016.1080p.BluRay.mkv", 2016),          # RUNBOOK T1: anitopy glues it into the title
    (u"[NanakoRaws] Pocket Monsters (2023) - 069 (WEB-DL 1920x1080 x264 AAC).srt", 2023),
    (u"Blade Runner 2049 (2017).ja.srt", 2017),               # the bracketed year wins
    (u"53.Stages.of.the.Road.1959.1080p.HDTV.AAC2.0.H265.10bit-dougal.ass", 1959),
])
def test_a_year_is_read(name, y):
    assert tokens.year(name) == y


@pytest.mark.parametrize("name", [
    u"(2020.10.04)_ドクターY～外科医・加地秀樹～SP.srt",                                  # a date
    u"マー姉ちゃん（０７６） - [1920-1440x1080@KFMVFR.hevc10_crf 20][字].ass",           # a resolution
    u"[Kamigami] Ikoku Meiro no Croisee Nai - 02 (BD x264 Hi10P 1920×1080 FLAC).jp.ass",
    u"2023年07月10日02時00分-ああ、ラブホテル ～秘密～ 「第１話 狐と狸_運命の２人」[字]_ＷＯＷＯＷプライム.ts.ass",
    u"[字][再]世にも奇妙な物語 23夏SP 2023.06.17 WEBDL-Cosmo.srt",
])
def test_a_look_alike_is_not_a_year(name):
    assert tokens.year(name) is None


def test_nothing_in_the_capture_carries_a_year():
    assert [(n, tokens.year(n)) for n in NAMES if tokens.year(n)] == []


# ---------------------------------------------------------------------------
# subtitle_format
# ---------------------------------------------------------------------------

def test_the_format_is_the_extension_folded():
    assert [tokens.subtitle_format(n) for n in NAMES] == [n.rsplit(".", 1)[1].lower() for n in NAMES]
    assert tokens.subtitle_format(u"Show - 01.ASS") == "ass"
    assert tokens.subtitle_format(
        u"[Anime Land] Kimi no Na wa. (Dual Audio) (BDRip 4K 2160p HEVC HDR10 DTS-HDx2) [2BCD73C2].sup.7z") == "7z"
