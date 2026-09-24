# -*- coding: utf-8 -*-
u"""
Subtitle TEXT for the checks that read one (RUNBOOK 9b), built at run time.

    import _subtitles as subs           # tests/ is on sys.path
    subs.srt(subs.lines(subs.JA, 300)).encode("utf-8")
    subs.ass(subs.lines(subs.JA, 300), drawings=600)

⛔ EVERY LINE BELOW WAS WRITTEN FOR THIS SUITE. hato never bundles or mirrors a
subtitle (`LEDGER-HOT.md`: they carry no stated licence), and `hato.dev
scan-content` flags a subtitle body in the tree -- so nothing here is ever a
jimaku file, and no timing line appears in this source: `srt()` and `ass()`
write them when a check runs. ⚠ Kept SHORT for the same scanner: it counts
Japanese characters per file, and a few phrases repeated are all a count needs.

⭐ The phrases are ordinary dialogue on purpose -- kana and kanji in the
proportions real dialogue has -- because what 9b measures is the SHARE of kana,
and a check fed only hiragana would pass a threshold nothing real meets.
"""

JA = (u"おはよう、今日はいい天気だね。",
      u"本当に？じゃあ一緒に出かけようか。",
      u"待って！まだ準備ができていないの。",
      u"大丈夫、ゆっくりでいいよ。",
      u"先生に呼ばれてるから先に行ってて。",
      u"わかった。駅で待ってるね。")

#: The same six lines in Chinese. ⚠ No kana at all, which is the point.
ZH = (u"早上好，今天天气真不错。",
      u"真的吗？那我们一起出去吧。",
      u"等一下！我还没准备好。",
      u"没关系，慢慢来就好。",
      u"老师叫我过去，你们先走吧。",
      u"知道了，我在车站等你。")

EN = (u"Good morning, the weather is nice today.",
      u"Really? Then let's go out together.",
      u"Wait! I'm not ready yet.",
      u"It's fine, take your time.",
      u"The teacher called me, so go on ahead.",
      u"Got it. I'll wait at the station.")


def lines(pool, count):
    u"""`count` lines cycled from `pool`. -> [text]"""
    return [pool[i % len(pool)] for i in range(count)]


def _clock(seconds, comma):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if comma:
        return u"%02d:%02d:%02d,%03d" % (hours, minutes, secs, 0)
    return u"%d:%02d:%02d.%02d" % (hours, minutes, secs, 0)


def srt(texts):
    u"""An SRT body, one cue per text, two seconds apart. -> text"""
    cues = []
    for n, text in enumerate(texts, 1):
        cues.append(u"%d\n%s %s %s\n%s\n" % (n, _clock(2 * n, True), u"-" * 2 + u">",
                                          _clock(2 * n + 1, True), text))
    return u"\n".join(cues)


def ass(texts, drawings=0):
    u"""An ASS script, one event per text, plus `drawings` vector-shape events. -> text"""
    head = (u"[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer, Start, End, "
            u"Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    events = []
    for n, text in enumerate(texts, 1):
        events.append(u"%s: 0,%s,%s,Default,,0,0,0,,%s" % (
            u"Dialogue", _clock(2 * n, False), _clock(2 * n + 1, False), text))
    for n in range(drawings):
        events.append(u"%s: 0,%s,%s,Sign,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}" % (
            u"Dialogue", _clock(n, False), _clock(n + 1, False)))
    return head + u"\n".join(events) + u"\n"
