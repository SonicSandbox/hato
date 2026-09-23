# Third-party components and attribution

hato itself is **GPL-3.0-or-later** (see `LICENSE`). This file lists what it
depends on, what it does **not** redistribute, and under what terms.

> ⚠ **Every licence below was read from that project's own installed metadata
> on 2026-09-17** (`importlib.metadata`), or from its PyPI JSON — not from
> memory. It is still not a substitute for reading them. If you redistribute a
> build, confirm the terms of the exact versions you ship.

---

## Bundled in the Python package

**hato's own artwork, and nothing else of anyone's.** `hato/data/` carries the
hato icon exported at seven sizes plus a `.ico`, and three surasura icons for
the optional integration — all original work by the author of this project,
under the same GPL-3.0-or-later terms. No vocabulary, no corpus, no
third-party binaries. Everything else hato needs it either generates at
runtime or finds on the machine.

> ⚠ **This section used to say "Nothing," and that was wrong twice** — it
> overlooked the icons above and said nothing at all about the Windows
> download below. Corrected 2026-09-18 after an adversarial pass; recorded
> rather than quietly edited, because this is the file a reader trusts to
> decide whether the project is licence-honest.

---

## Bundled in the Windows standalone download

🚨 **The `hato-<version>-windows-x64.zip` on the Releases page is a different
artifact from the Python package, and it conveys other people's code.** It is
built with PyInstaller in `--onedir` form and contains, beside hato itself:

| Bundled | Licence | Note |
| --- | --- | --- |
| **CPython** (`python3.dll`, `python310.dll`, the standard library) | **PSF-2.0** | The interpreter, so nothing needs installing |
| **PyQt6** and the Qt libraries it wraps | **GPL-3.0** | The window only. ⭐ Compatible with hato's own GPL-3.0-or-later, and the reason this download can be distributed at all |
| **OpenSSL** (`libssl`, `libcrypto`) | **Apache-2.0** | Via CPython's `ssl` module |
| **numpy** | **BSD-3-Clause** | tsubasa's alignment |
| **PyInstaller bootloader** | **GPL-2.0-with-exception** | The exception explicitly permits distributing the frozen application under its own terms |
| the runtime dependencies listed below | as listed | py7zr, rarfile, requests, certifi and their own dependencies |

⛔ **`LICENSE` and this file travel inside that zip**, at its top level. GPLv3
§4 and §6 require the licence to accompany conveyed object code, and a
download is conveying. `packaging/package_standalone.py` refuses to build the
archive if either is missing, and `packaging/smoke_standalone.py` asserts both
are present in the *unpacked* copy.

▶ **Corresponding Source** for that binary is this repository, including
`packaging/` — the spec and scripts that control the build.

> 🚨 **No subtitle content ships, ever.** See *Subtitle content* below — it is
> the one licence question this project exists inside, and the answer is that
> hato redistributes none of it.

---

## Runtime dependencies

| Package | Why hato needs it | Licence | Read from |
| --- | --- | --- | --- |
| **tsubasa-sync** (imported as `tsubasa`) | The engine. Filename parsing, video discovery, the existing-subtitle reader, the embedded-track reader, and `sync()` — the retiming that makes a downloaded subtitle usable | **GPL-3.0-or-later** | PyPI JSON for 0.1.5 |
| **requests** | The jimaku and Kitsu HTTP calls — `hato/client.py`, `hato/kitsu.py` | **Apache-2.0** | metadata of 2.28.2 |
| **tomli** | `config.toml` on Python 3.10. `tomllib` is stdlib from 3.11, and `hato/config.py` branches on exactly that; the dependency carries the marker `python_version < "3.11"` | **MIT** | metadata of 2.4.1 |

### Through the engine's `parsing` extra

hato declares **`tsubasa-sync[parsing]`**, because `spec/01-scope.md` ratifies
*anitopy primary, guessit fallback* and `LEDGER-HOT.md` forbids a second
filename parser inside hato — the parser is the engine's, so the extra is the
only truthful way to ask for it. Both of these therefore arrive in every hato
install, and **both require their notices to be carried**:

| Package | What it does | Licence | Obligation |
| --- | --- | --- | --- |
| **anitopy** | Anime release-name parsing | **MPL-2.0** | Carry this notice. File-level copyleft applies only if you modify anitopy's own files — hato does not; it never touches them |
| **guessit** | Western release-name parsing, the fallback | **LGPL-3.0-or-later** | Carry this notice. ⛔ Do not vendor and relicense. Used as an unmodified library dependency, which is what the LGPL permits |

---

## Optional — the `archives` extra

Both are reached through a guarded lazy import (`hato/archives.py`). Absent,
a `.7z` or `.rar` candidate is a **named skip**, never a crash — and archive
support is off by default.

| Package | Extra | What it does | Licence | Read from |
| --- | --- | --- | --- | --- |
| **py7zr** | `archives` | Reads `.7z` batch archives | **LGPL-2.1-or-later** | metadata of 1.1.3 |
| **rarfile** | `archives` | Reads `.rar` batch archives | **ISC** | metadata of 4.5 |

---

## Optional — the `gui` extra

Reached through a guarded import (`hato/gui/app.py`), behind a lazy one
(`hato.gui.main()`). Absent, `python -m hato.gui` prints an instruction naming
the extra and exits 2 — and **hato itself is unaffected**: the CLI does the
whole job with no window, which is why this is an extra rather than a
dependency.

| Package | Extra | What it does | Licence | Read from |
| --- | --- | --- | --- | --- |
| **PyQt6** | `gui` | The window's toolkit | **GPL-3.0** | the `LICENSE` file shipped inside `pyqt6-6.11.0.dist-info/licenses/`, read 2026-09-18 |

⚠ **Read from the shipped licence file, not from metadata.** PyQt6's
`Metadata-Version` carries **no `License` field and no licence classifier** —
`importlib.metadata` returns `None` — so the only honest source is the
`LICENSE` text in its own `dist-info`, which is the GNU GPL version 3.

⭐ **This is the one dependency whose licence constrains hato's own, and it
agrees with it.** Riverbank publishes PyQt6 under the GPL or a commercial
licence; hato is GPL-3.0, so the GPL side applies and no obligation is added
beyond the one hato already carries. `spec/05-interface.md` chose PyQt6 over
PySide6 (LGPL) for exactly this reason — *"GPL-3.0, which matches hato's own
licence"*. ⛔ Anyone relicensing hato away from the GPL must revisit this row
before shipping a window.

---

## Not bundled, acquired separately

| Component | Licence | Note |
| --- | --- | --- |
| **`unrar` / `unar` / `bsdtar`** | Varies by build; UnRAR's own licence is **non-free and forbids reverse-engineering the RAR algorithm** | ⛔ **Never bundled by this repository.** `rarfile` shells out to whichever tool is on `PATH`; `rarfile.tool_setup()` is called first, so a machine with no tool produces a skip. Anyone redistributing a build alongside such a tool must satisfy that tool's own terms |
| **ffmpeg / ffprobe** | LGPL-2.1+ or GPL-2+ depending on build | Never bundled, and never read by shipping code. The suites use a copy from this workspace to build test videos; the engine finds its own |

---

## 🚨 Subtitle content

**The subtitle files on jimaku.cc carry no stated licence.** They are
user-uploaded fansub work.

- hato **downloads** them to the user's own machine, at that user's own
  request, one file at a time.
- hato **redistributes nothing**. ⛔ No subtitle content, no corpus and no
  fixture containing third-party subtitle text is in this package, this
  repository or any release artifact. The recorded API fixtures under
  `tests/fixtures/` are response **metadata** — file lists, names, sizes — and
  the two download fixtures are metadata only, deliberately.
- ⛔ **Never bundle, mirror or republish subtitle content.**

---

## Reference implementations consulted

Named because the GPL-3.0 choice was made partly to permit it, and because
credit is owed for prior art even where no code was copied:

- **Bazarr** (GPL-3.0) — its jimaku provider, and the retry ladders it had
  already solved
- **Sonarr** (GPL-3.0) — its release-name parser table
- **jimaku** server (AGPL-3.0) — **read only.** ⛔ Nothing vendored; AGPL's
  network clause is not something to inherit casually
- **anime-relations.txt** (Taiga / erengy, public domain) — an accelerator for
  absolute-to-seasonal episode mapping, never a dependency
- **subsync** — the predecessor the engine rebuilds

⛔ **Fribb's `anime-lists` and ScudLee's `Anime-Lists` have no licence file at
all**, and are deliberately not used. See `spec/01-scope.md`.

---

## Transitively, through the packages above

Not hato's choices, and listed only because a redistributor has to know they
are in the tree. Read from installed metadata on 2026-09-17:

| Via | Packages |
| --- | --- |
| `requests` | certifi (MPL-2.0) · urllib3 (MIT) · charset-normalizer (MIT) · idna (BSD-3-Clause) · **chardet (LGPL, v2 or later)** · PySocks (BSD) |
| `guessit` | rebulk (MIT) · babelfish (BSD-3-Clause) · python-dateutil (dual BSD / Apache-2.0) · six (MIT) · importlib_metadata (Apache-2.0) · zipp (MIT) · packaging (dual Apache-2.0 / BSD) |
| `py7zr` | several LGPL-2.1-or-later components — pyppmd, pybcj, inflate64, multivolumefile — plus texttable (MIT), brotli (MIT), psutil (BSD-3-Clause), pycryptodomex (BSD / public domain), backports.zstd (PSF-2.0) · and through psutil: pyreadline3 (BSD), setuptools (MIT) |
| `tsubasa-sync` | numpy (BSD-3-Clause) |
| `PyQt6` | PyQt6-sip (BSD-2-Clause) |
| the build's own imports | PyYAML (MIT) · cffi (MIT) with pycparser (BSD) · platformdirs (MIT) · typing_extensions (PSF-2.0) · backports.tarfile (MIT) |

⚠ **The second half of this table was MISSING until 2026-09-22** — the 1.0.1
download carried every package above and this file named only the first
fifteen (ADVERSARY 2026-09-22 D2). The list is now read from the FROZEN BUILD
itself — what its archives actually hold — not from what `pyproject.toml`
declares; see below.

## Verifying this file

`tests/test_packaging.py` derives the list of names that must appear here
**from `pyproject.toml`**, so adding a dependency without its notice fails the
suite. ⭐ And `packaging/smoke_standalone.py` reads the FROZEN BUILD's own
archives — every third-party top-level module it carries — and fails the
release when one is not named here. It cannot check that a licence
*identifier* above is still correct — that needs reading the project, which
is what the note at the top says.
