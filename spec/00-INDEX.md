---
type: spec
title: hato — Spec Pack Index
desc: What each numbered part contains, the surfaces vocabulary, and the four rules that outrank everything else in this pack.
date: 2026-09-07
---

# hato — Spec Pack

> **Read this file first, then load only the parts your step's `surfaces:` line names.**
> Part 2 is a fresh agent with only this pack. **Anything not written here is lost.**

`hato` (鳩 — carrier pigeon) takes a downloaded video, works out what it is, fetches the
matching Japanese subtitle from **jimaku.cc**, hands it to [[tsubasa]] to be retimed, and
leaves it beside the video under a name every media player will load.

It **imports** tsubasa. tsubasa never imports it. That one-way arrow is the whole
architecture — see `01-scope.md` §*The relationship to tsubasa*.

---

## The FOUR rules that outrank the rest of this pack

| # | Rule | Consequence if broken |
| --- | --- | --- |
| **1** | 🚨 **The timing check is the REFEREE. hato only ever produces a hypothesis.** | Filename-to-show matching cannot be made reliable — measured, repeatedly, by everyone who has tried. What makes this tool safe is that a wrong guess is *refused by tsubasa*, not written. **Any design that writes a file hato is merely confident about reproduces the one failure that matters** |
| **2** | ⭐ **The network is metered. The disk is not.** | 25 requests/60s on `/api/*`, and **failed requests still consume quota**. Downloads are unmetered and need no auth. Every efficiency decision in this pack falls out of that asymmetry — see Rule 4 |
| **3** | ⛔ **Nothing partial ever touches the user's media folder.** | Downloads, archive extraction and alignment all happen in the cache dir. Only a finished, verified file is written beside the video. `subsync` shipped the opposite and dropped scratch files inside a corpus its own README marked read-only |
| **4** | ⭐ **Ask the efficiency question at EVERY level** (inherited from tsubasa) | Applied here it was worth **13×** before a line was written — see below |

---

## 🚨 Amendments 2026-09-17 — read before any step

Sonic signed the pack off on 2026-09-17 with these rulings, made after a pre-build check
against tsubasa's **code**. Each is written into the file named; this list exists so a cold
agent meets them first.

| Ruling | Where it lives |
| --- | --- |
| ⭐ **The build runs through an ORCHESTRATOR agent** that dispatches builder agents in waves | `RUNBOOK.md` §*How this build runs* |
| **A video with no subtitle track is skipped BEFORE download.** tsubasa has nothing to time it against until its audio path exists. ⛔ Never recorded as a refusal | `03-permissions.md` §*The read rule* · `06-edge-cases.md` §6 |
| ⭐ **`.ass` outranks every other format** — even a `[CHS, JPN]` `.ass` over a `[JPN]` `.srt` | `02-data-model.md` §*Candidate ranking* |
| **tsubasa writes the synced file beside the video; hato keeps every used original in its own `subs_dir`, never deleted.** Verified to load and be selected in Sonic's mpv | `03-permissions.md` §*Whitelist 1* · `05-interface.md` §*Naming* · `RUNBOOK.md` 4c |
| 🚨 **The original handed to tsubasa MUST carry `.ja` in its name.** Untagged, tsubasa writes `<video>.ass`, and hato's next run reads that as *no Japanese subtitle* and fetches again for ever — measured | `LEDGER-HOT.md` · `RUNBOOK.md` 4c |
| **A video's tracks come from tsubasa's PUBLIC track reader**, being added by tsubasa's builder. ⛔ Never `tsubasa.container` | `RUNBOOK.md` T4 · `10-deployment.md` |
| `--name-template` → Evolution. tsubasa owns naming | `01-scope.md` · `05-interface.md` |
| This laptop runs **Python 3.10** — `tomllib` is 3.11+, so `tomli` below it | `01-scope.md` §*stack* · `10-deployment.md` |
| ⭐ **One per-user folder, hato's OWN: `%LOCALAPPDATA%\hato\`** — config, key, log, DB, cache, kept originals; ⛔ not inside tsubasa's. The key is `key.txt` there, ⛔ never `config.toml` | `05-interface.md` §*The config file* |
| **The soft negative is 1 day** (a just-aired episode), and ⭐ **a blacklist** the person controls — ⛔ `--force` does not override it | `02-data-model.md` §Questions 2–3 |
| **A window comes after launch** — manual pairing, the key, folders, recursion, blacklist, the failed list. A shell over `hato --json` | `05-interface.md` §*The window* |

---

## ⭐ Rule 4 applied — the worked example, measured live

> **Before writing any loop, scan or sweep, ask: is every unit of work necessary?**

The naive design fetches one subtitle per episode: `GET /entries/{id}/files?episode=N`,
24 times for a 24-episode season. That is 24 metered calls plus one to resolve the show.

**The measured alternative — verified against the live API on 2026-09-07:**

```
GET /api/entries/11446/files      →  120 files, one call, no episode parameter
```

| Approach | Metered calls per 24-episode season | Notes |
| --- | --- | --- |
| Naive — one call per episode | **26** | Exceeds the 25/60s budget on a single show |
| ⭐ **Fetch the whole file list once, match locally** | **2** | 1 search + 1 files. **13×** fewer |

**And it is not only cheaper — it is more correct.** Passing `episode=N` makes jimaku run
`anitomy` server-side over each filename and `retain()` only the files it could parse a
number from. Batch archives and unconventionally-named files are **silently dropped, with
no error**. Fetching the full list cannot drop anything.

⛔ **Do not use the `episode=` parameter.** Ever. Both reasons above, and a third: the
server sees one request and cannot know what else is in the user's folder, which is what
makes the range alignment in `02-data-model.md` §*Episode alignment* possible at all.

---

## The parts

| File | Contains |
| --- | --- |
| `01-scope.md` | The objective in Sonic's words · launch vs evolution · **the relationship to tsubasa, ruled** · the stack · scale · what is irreversible |
| `02-data-model.md` | The five stores, kept originals included · **canonicity in one line** · the cost model · **episode range alignment** · candidate ranking, **`.ass` first** |
| `03-permissions.md` | The single non-human actor · **the field whitelist** · the three outcomes · the hand-back path |
| `05-interface.md` | The ruled CLI output (both modes) · the config file · the `.cmd` · the library API |
| `06-edge-cases.md` | The catalog, by section, each with a defined behaviour |
| `07-test-plan.md` | Suites and what each **structurally cannot** cover · **recorded fixtures** · the live-API probe |
| `08-research.md` | ⭐ **Verified API facts and licence findings.** Every claim carries a source. **Read before writing the jimaku client** |
| `10-deployment.md` | Release shape · the two-package split · publishing as two repos |
| `RUNBOOK.md` | Dependency-ordered build, with the proof command per step |

`04-identity.md` is **deliberately absent.** There are no accounts, no sign-in and no
users. There is one API key, and it is a credential, not an identity.

---

## Surfaces vocabulary

Used by `RUNBOOK.md` to tell the builder which doctrine to load per step.

| Surface | Means, in this project |
| --- | --- |
| `data` | The state DB, the cache, the config file |
| `logic` | Identification, episode alignment, candidate ranking, the jimaku client |
| `ui` | CLI output and the `.cmd` launcher |
| `delivery` | Packaging, the two-package split, releases |
| `harness` | Recorded fixtures, the suites, the live probe |

`identity` never appears in this project.

---

## Related

[[tsubasa]] — the engine this imports · `Workshop/jimaku-corpus/jimaku-corpus.md` — prior
reconnaissance against the same site · [[Development Doctrine/workflows/dev-build]]
