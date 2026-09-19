---
type: spec
title: hato — Verified Research
desc: Every external fact this build rests on, with its source. Read before writing the jimaku client. Findings marked MEASURED were verified live during specification.
date: 2026-09-07
---

# 08 — Verified Research

> **Read this before writing the jimaku client.** Everything here was verified against a
> primary source — the OpenAPI spec, the server's own source, vendor documentation, or a
> live request made during specification. **Nothing here is from memory.**
>
> Items marked **MEASURED** were executed during this session and are reproducible.
> Items marked **UNVERIFIED** are explicitly unproven — do not build load-bearing logic
> on them without checking first.

---

## The jimaku API

Authoritative source: **`https://jimaku.cc/api/openapi.json`** (OpenAPI 3.0.3, title
"Jimaku", version `beta`). ⚠ **`https://jimaku.cc/api/docs` is a JavaScript SPA and returns
a 1.5 KB shell to any fetcher** — read the raw spec, not the docs page. Cross-checked
against the server source at `github.com/Rapptz/jimaku` (AGPL-3.0).

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/entries/search` | Search entries |
| GET | `/api/entries/{id}` | Entry details |
| GET | `/api/entries/{id}/files` | **List files. The one that matters** |
| GET | `/entry/{id}/download/{name}` | Download. ⭐ **No auth, no rate limit** |

**`search` params:** `query` (fuzzy) · `anime` (bool, **default `true`**) · `anilist_id` ·
`tmdb_id` (`(tv|movie):\d+`) · `after` / `before` (UNIX seconds). Returns a **JSON array**,
sorted by score descending.

**`files` params:** `episode` (int, nullable). ⛔ **We never send it** — see `00-INDEX.md`
§Rule 4.

### Response shapes — MEASURED 2026-09-07

`GET /api/entries/search?query=frieren` → HTTP 200:

```json
[{"id":729,"name":"Sousou no Frieren",
  "flags":{"anime":true,"unverified":false,"external":true,"movie":false,"adult":false},
  "last_modified":"2026-02-14T00:37:40Z","anilist_id":154587,
  "english_name":"Frieren: Beyond Journey's End","japanese_name":"葬送のフリーレン"},
 {"id":11446,"name":"Sousou no Frieren 2nd Season", ...}]
```

`GET /api/entries/11446/files` → **120 files**, keys exactly:
`['last_modified', 'name', 'size', 'url']`.

🚨 **There is no episode field on a file.** Episode number exists only inside `name`.

⚠ **Optional fields are absent keys, not `null`** — the server uses
`skip_serializing_if = "Option::is_none"`. Use `.get()`, never `["key"]`.

⚠ The Rust field `last_updated_at` serializes as **`last_modified`**.

### Authentication — MEASURED

- Header name is **`Authorization`**
- 🚨 **The token is used RAW. There is no `Bearer` prefix.** The server reads the header,
  calls `.to_str()`, and passes the string straight to the session validator
- All five `/api/*` endpoints require it. **Downloads do not** — the download handler takes
  no auth extractor at all
- Key from `https://jimaku.cc/account` → "Developer Access"

### Rate limiting — MEASURED

`x-ratelimit-limit: 25`, `x-ratelimit-remaining`, `x-ratelimit-reset`,
`x-ratelimit-reset-after`.

- **25 requests / 60 s per IP**, applied to the whole `/api` router
- 🚨 **Failed requests consume quota.** The limiter is an outer layer, so a 401 costs the
  same as a 200
- `reset` and `reset-after` may be **fractional**
- Downloads are not on this limiter

### 🚨 The four traps

1. **`anime` defaults to `true` and gates BEFORE the ID match.** `SearchQuery::apply`
   runs `if self.anime != entry.flags.is_anime() { return None }` first. A live-action
   entry returns `[]`. **Retry with `anime=false`**
2. ⛔ **No `query` at all → score 100 → the entire catalogue is returned.** An empty
   normalized title must never become a request
3. **`episode=N` silently drops files.** The server runs `anitomy` over each filename and
   `retain()`s only what it could parse. Batch archives and odd names vanish with no error
4. **An invalid entry id does not 404** — it returns HTTP 200 and serves the site index.
   Guard: the post-redirect path must still be `/entry/<id>`, and every file's `url` must
   start with `/entry/<id>/download/`

### Terms of use

- **There is no ToS.** `/terms`, `/tos`, `/rules`, `/privacy` all 404. No attribution
  requirement, no stated restriction on automated access
- 🚨 **`robots.txt` is the only stated restriction, and it is `User-agent: * → Disallow: /`**
  for everything that is not a named search engine. **The key-gated API is the sanctioned
  path; HTML scraping is not.** ⚠ Note that `Workshop/jimaku-corpus/jimaku-corpus.mjs`
  scrapes the HTML page — that predates this finding and is a separate matter, but **hato
  must use the API**
- The site software is AGPL-3.0. That covers the code, not the subtitles
- **UNVERIFIED: redistribution rights for the subtitle content itself.** No licence is
  stated anywhere. It is user-uploaded fansub work. ⛔ **Download to the user's machine at
  their request; never mirror, bundle or republish**

---

## ⭐ MEASURED — the live probe that shaped the design

`GET /api/entries/11446/files` (*Sousou no Frieren 2nd Season*), 2026-09-07:

```
120 files · 5 release groups, 20 files each:
   Haruhana · KitaujiSub · NanakoRaws · Nekomoe kissaten&LoliHouse · shincaps

episode numbers seen:  1 .. 38    distinct: 20
candidates per number: 4
```

⚠ **Noticed 2026-09-17: these numbers do not sum.** Five groups of 20 files is 100, not 120,
and 20 numbers × 4 candidates is 80. **Re-derive every count from the capture**
(`hato doctor --capture`), never from this prose.

> ✅ **RE-DERIVED FROM THE BUILD'S CAPTURE, 2026-09-17** (`tests/fixtures/api/entries_11446_files.json`,
> 9 metered calls, the one deliberate live run). **The 120 are 5 bracketed groups × 20 PLUS 20
> files with NO bracketed group at all** — ⚠ *corrected the same day by the 3a builder, who read
> all 20: they are TWO releases, **10 Amazon** (`葬送のフリーレン.S02E01.じゃあ行こうか.WEBRip.Amazon.ja-jp[sdh].srt`)
> and **10 Netflix** (`….S02E31.好きな場所.WEBRip.Netflix.ja[cc].srt`); the orchestrator had looked at
> the first six.* That is why the prose did not sum, and 🚨 **grouping by the bracketed prefix alone
> puts two releases into one nameless bucket** — episode alignment must give an unbracketed file a
> group of its own (`02-data-model.md` §*Episode alignment*). Amazon mixes conventions inside one
> release (`S02E06.第34話` reads as absolute 34); ⚠ **Netflix reads season 2 WITH absolute numbers
> (31–38)**, so "a season was read" does not mean "seasonal numbering". · **80 `.ass`, 40 `.srt`** · language tags **30
> `[CHS, JPN]` · 30 `[JPN]` · 60 untagged** · sizes 19,652–111,780 B. ⛔ Episode counts are the
> parser's to derive, in 3a — not restated here.

### ✅ MEASURED 2026-09-17 — the build's live capture (`hato doctor --capture`)

Every line below is read off `tests/fixtures/api/*.meta.json`. Where it corrects something
written above, the correction is marked.

| Fact | Measured | Consequence |
| --- | --- | --- |
| 🚨 **An invalid entry id through the API is a real 404**, not a 200 | `GET /api/entries/999999/files` → **HTTP 404** `{"error":"This entry could not be found","code":6}`. The unmetered `/entry/999999/download/x.srt` → **404**, empty body | ⚠ **Corrects trap 4 for hato's routes.** The *"200 + site index"* trap is the HTML page `/entry/<id>` only, which hato never requests. The url-prefix guard stays as defence; a 404 is the primary signal |
| ⚠ **A file's `url` is ABSOLUTE and percent-encoded** | `https://jimaku.cc/entry/11446/download/%5BHaruhana%5D%20Sousou…` — 120 of 120 | The guard *"url starts with `/entry/<id>/download/`"* must test the URL's **path** (after parsing), and its host |
| ⚠ **`x-ratelimit-reset` is an integer epoch** on these responses, and **`x-ratelimit-reset-after` is ABSENT** on 200, 401 and 404 | `reset: 1789634200`; no `reset-after` in any capture | A client must not require `reset-after` outside a 429. ⚠ The 429 itself was **not provoked** — it needs >25 requests/60 s, which Whitelist 2 forbids — so its header set remains UNVERIFIED |
| **anime=true gates a live-action show** — confirmed | `query=Kamen Rider Decade` → `[]`; with `anime=false` → 9 results | Trap 1 holds |
| **An empty query returns the catalogue** — confirmed | `query=` → **4,533 entries** in one call (the anime=true subset) | Trap 2 holds. Kept as a count only |
| A movie-flagged entry | `query=Kimi no Na wa` → entry **440**, `flags.movie: true` | `entries_movie_flag.json` |
| Absent keys, not nulls — confirmed | `tmdb_id` absent on at least one `query=frieren` result | Use `.get()` |
| A bad key | **HTTP 401** `{"error":"unauthorized","code":7}` | ⚠ *"A 401 consumes quota"* is **neither confirmed nor refuted** by this run: `remaining` read 22 before and after the 401, with ~2 s of refill between. The source-reading claim stands |
| A download | HTTP 200, 19,652 B, UTF-8 with BOM, no auth header sent | Unmetered, as documented |

**Three findings, each of which changed the spec:**

1. 🚨 **Absolute and seasonal numbering coexist inside ONE entry.** A 10-episode season
   whose files span 1–38 means some groups restart at 1 and others continue season 1's
   count. → **Range-align per release group, never pooled.** `02-data-model.md`
2. ⭐ **Multi-language files sit alongside single-language ones**, same episode, same
   group:

   ```
   104571 B  [Haruhana] Sousou no Frieren - 29 [...][CHS, JPN].ass
    49646 B  [Haruhana] Sousou no Frieren - 29 [...][JPN].ass
    51683 B  [Nekomoe kissaten&LoliHouse] ... - 29 [...][CHS, JPN].ass
    26706 B  [Nekomoe kissaten&LoliHouse] ... - 29 [...][JPN].ass
   ```

   The dual-language file is ~2× the size and interleaves Chinese. → **Prefer
   single-language.** Confirmed across two independent groups, so it is a convention
3. **Every episode had 4 candidates.** *(⚠ Re-measured 2026-09-17 after range alignment: **12
   files from 7 releases per episode** — the prose counted one numbering only.)* → **Candidate ranking is load-bearing here**, unlike
   in tsubasa where Sonic correctly called it a robustness backstop

---

## Filename parsing — the benchmark

No published comparison of these two existed. One was generated during research by
installing both and running them against **both** projects' own labelled corpora.

| | anime corpus (182 files) | Western TV corpus (551 files) |
| --- | --- | --- |
| **anitopy 2.1.1** | **86.9%** title+episode | 58.9% |
| **guessit 4.4.0** | 54.7% | **91.4%** |

⚠ Each corpus was labelled by its own project's maintainers, so treat the absolute numbers
as soft. **The direction and magnitude of the gap reproduce in guessit's own independently
run cross-parser suite.**

⭐ **Decision: anitopy primary, guessit fallback**, routed by a cheap detector — leading
`[Group]`, an 8-hex CRC32 token, or ` - NN ` → anime path. Real precedent:
`Audionut/Upload-Assistant` pins both and does exactly this.

### The silent failures to guard

| Input | Result | Why it matters |
| --- | --- | --- |
| `[Judas] Show - S01E06v2.mkv` | guessit → **`type: movie`**, no season, no episode | The control without `v2` parses perfectly. **Fails silently into a plausible movie record** |
| `Re ZERO ... Season 2 - 15` | guessit → `season: [2,3,…,15]` — **14 seasons** | Known limitation, won't fix |
| `Show - 125.mkv` | guessit → `season 1, episode 25` | An absolute number split into S/E. Silent and plausible |
| `[Group] 86 - Eighty Six - 01` | guessit → `episode: [86, 1]` | Numbers in titles get eaten |
| `Kimi.no.Na.wa.2016...` | anitopy → `anime_title: 'Kimi no Na wa 2016'` | Year glued into the title |
| `[Coalgirls] Toradora! - NCOP1` | anitopy → title `'Toradora! - NCOP'`, episode `1` | Specials pollute the title and fake an episode |
| — | Both flip `episode` between **str and list** without warning | Type instability. Normalize at the boundary |

**Licences:** `anitopy` **MPL-2.0**, `guessit` **LGPL-3.0-or-later**. Both fine as
dependencies. ⛔ Do not vendor guessit into differently-licensed source.

---

## Identity resolution — why jimaku's own search is the primary path

| Query | AniList | Kitsu |
| --- | --- | --- |
| `Attack on Titan` | correct #1 | correct |
| `attack on titan s2` | **0 results** | correct |
| `Sousou no Friern` (typo) | **0 results** | correct #1 |
| `steins gata` (typo) | **0 results** | correct #1 |
| `[SubsPlease] Sousou no Frieren - 01 (1080p) [F1B2C3D4]` | **0 results** | — |

🚨 **AniList's search is token-exact, not fuzzy.** One unmatched token zeroes the query.

**Three more reasons not to build on AniList:**

- ⚠ **It 403s without a `Referer` header** — newly observed, undocumented, and the body
  says *"The AniList API has been temporarily disabled due to severe stability issues"*,
  so a client that trusts the message wrongly concludes the service is down
- Live rate limit is **30/min**, not the documented 90
- ToS: *"Hoarding or mass collection of data from the AniList API is strictly prohibited"*
- **MEASURED during research: AniList returned 403, Jikan 504 and MAL 403 simultaneously**

⭐ **Fallback order if jimaku's own search misses: Kitsu → `/mappings` → AniList id →
jimaku `?anilist_id=`.** Kitsu is Apache-2.0, needs no auth, and is genuinely typo-tolerant.
⚠ It is high-recall/**low-precision** — junk input returns 76 confident results — so score
candidates locally against `canonicalTitle`, `titles{}` and `abbreviatedTitles[]`. Never
trust position. ⚠ Percent-encode CJK explicitly; unencoded `葬送のフリーレン` silently
returned *Attack on Titan*.

### ⛔ Datasets NOT to depend on

| Dataset | Status |
| --- | --- |
| `manami/anime-offline-database` | **Archived read-only 2026-07-04.** Frozen forever. Only 49.8% have an AniList id, **0% have TVDB ids**. ODbL share-alike |
| `Fribb/anime-lists` | **No licence file at all.** All rights reserved. Also an unlicensed derivative of ODbL data |
| `Anime-Lists` (ScudLee) | **No licence file.** A CC0 request has sat unanswered since 2026-07-25 |
| TheTVDB | No free tier. Commercial contract or per-user subscription |
| ⭐ `erengy/anime-relations` | **PUBLIC DOMAIN.** 545 rules, absolute → entry + local episode. **The only cleanly-licensed dataset in the space.** Accelerator, never a dependency |

⚠ **ODbL, if any derived index is ever considered:** extracting a substantial part into a
new database is a *Derivative Database* and triggers share-alike; emitting a resolved id to
a user is a *Produced Work* and does not. **Resolve at runtime, cache on the user's
machine, ship no data file** — clean on every count.

---

## Media-server sidecar naming

Verified against each vendor's own documentation.

| Purpose | Filename | Plex | Jellyfin | Emby |
| --- | --- | --- | --- | --- |
| Japanese | `<video>.ja.srt` | ✅ | ✅ | ✅ |
| Japanese, forced | `<video>.ja.forced.srt` | ✅ | ✅ | ✅ |
| Japanese, SDH | `<video>.ja.sdh.srt` | ✅ | ✅ | ✅ |

Safe extensions across all three: **`.srt` `.ass` `.ssa` `.vtt`**.

| Trap | Detail |
| --- | --- |
| ⛔ `.ja-JP.srt` | Correct BCP 47, **broken on Jellyfin** — its hyphenated table holds only `fr-ca`, `pt-pt`, `pt-br`, `zh-*` |
| ⛔ `jap` | **Never a valid ISO code.** Zero occurrences in the LoC list or the IANA registry |
| ⛔ A bare flag with no language | `sdh` is a real ISO 639-3 code (Southern Kurdish) |
| ⚠ `hi` / `fo` | **Hindi** and **Faroese**. Only `cc` is collision-free |
| ⚠ 20 ISO 639-2 B/T splits | `fre`/`fra`, `ger`/`deu`, `chi`/`zho`, `dut`/`nld`… **Japanese has none**, so it dodges this — but the pattern does not generalise if `--lang` is ever widened |

### mpv — Sonic's player. MEASURED 2026-09-17

A temp `.mkv` with an embedded English text track, `Show - 01.ja.ass` beside it, run through
Sonic's installed mpv with Sonic's own `%APPDATA%\mpv\mpv.conf` (`sub-auto=fuzzy`):

```
     Subs  --sid=1 --slang=eng (subrip)
 (+) Subs  --sid=2 --slang=ja 'Show - 01.ja.ass' (ass) (external)
```

⭐ **`<video>.ja.ass` beside the video loads and is the selected track**, ahead of the
embedded English one. mpv reads `ja` from the name. ⚠ The same run printed
`mpv.conf:3: unparseable extra characters: ': jpn, jp, en'`, and the same for line 4 —
Sonic's `alang:` / `slang:` lines use `:` and are **ignored**, so the selection above
happened without them.

### Existing-subtitle detection — both reference tools have live bugs

| | subliminal 2.7.1 (MIT) | Bazarr `subliminal_patch` (GPL-3.0) |
| --- | --- | --- |
| Root match | prefix | exact |
| `.ja.forced.srt` | 🚨 reads as **`und`** — it expects `.ja.fo.` | works |
| Flag matching | whole token | 🚨 **substring** |
| Consequence | A correctly-named forced sub reads as "no subtitle" and is re-downloaded forever | `Show.chi.srt` → Chinese **+ hearing-impaired**. `Show.hin.srt` → Hindi **+ hearing-impaired** |

⭐ **Two one-line rules fix both, and each project got one of them wrong in the opposite
direction:**

1. **Parse the language BEFORE trimming flag tokens**
2. **Strip flags as whole dot-delimited tokens, never substrings**

⚠ **Write this reader once, in tsubasa** (it needs it for dedupe), and import it.

---

## Prior art — what not to rebuild

| Tool | Licence | Why we are not it |
| --- | --- | --- |
| **Bazarr** — has a full Jimaku provider, 417 lines | **GPL-3.0** | *"Does not scan your disk"* — requires Sonarr/Radarr and a media server. ⭐ **But under our GPL-3.0 licence its provider is readable and vendorable, and it already solves the retry ladders** |
| `jimaku-dl` | GPL-3.0 | Standalone Python jimaku client. Closest existing thing. Readable |
| `Emby.Jimaku` ("Jimakufin") | GPL-3.0 | Needs a TVDB id on the parent series |
| `subliminal` | MIT | **No jimaku provider, and no `anilist_id` field at all** — it cannot represent the key jimaku needs |

---

## Credentials

**One credential, minted and verified.**

| | |
| --- | --- |
| **What** | jimaku.cc API key |
| **Where** | `InfiniteVoid/keystore/hato-jimaku.txt` — last line is the key; the header above it is documentation |
| **Env override** | `HATO_JIMAKU_KEY` |
| **Status** | ✅ **Minted and verified 2026-09-07** — `search?query=frieren` → HTTP 200, `x-ratelimit-limit: 25` |
| **Mint / revoke** | `https://jimaku.cc/account` → "Developer Access" |
| **Use** | `Authorization: <key>` — raw, no `Bearer` |

🚨 **Never write it inside TheForge, not even for a minute.** The vault auto-commits every
~5 minutes and git history has no undo. The keystore sits outside every repo by
construction — `git rev-parse --show-toplevel` there returns *"fatal: not a git
repository"*, and that check was run before the key was placed.

⛔ **Nothing else needs minting.** Everything in the RUNBOOK can be done without a human.
