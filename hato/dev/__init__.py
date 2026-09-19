# -*- coding: utf-8 -*-
"""
hato's RELEASE TOOLING -- the five commands spec/RUNBOOK.md §Step 6 invokes.

    python -m hato.dev stamp                       write the version + content hash
    python -m hato.dev stamp --check               ⛔ the gate in front of the upload
    python -m hato.dev audit-wheel dist/*.whl      the wheel's manifest, claim by claim
    python -m hato.dev scan-secrets dist/          no secret anywhere in the artifact
    python -m hato.dev scan-content dist/          no third-party subtitle BODY
    python -m hato.dev verify-install --no-unrar   a clean venv, outside every checkout

⭐ EVERY COMMAND IS A LIST OF NAMED CLAIMS. Exit 0 only when all of them hold;
exit 1 with ONE line on stderr naming the claim that failed and what it saw;
exit 2 when the tool itself could not run (doctrine/verification: a tooling
fault gets its own exit code and announces itself as one). ⛔ Never a traceback.

⚠ THIS PACKAGE IS DEV TOOLING AND NOTHING IMPORTS IT AT RUNTIME. `hato/__init__.py`
does not import it, `hato.cli` does not know it exists, and no shipping module
reads anything under here -- so whether the packaging step carries `hato/dev/`
into the wheel is a size decision, never a correctness one (pitfall P6 is about
a dev file the INSTALLED package READS).

⛔ NOTHING HERE MAY HARDCODE A PATH ON THE BUILD MACHINE. The keystore path, the
vault's ffmpeg and `Workshop/patch-kit` are all facts about one laptop
(spec/RUNBOOK.md 0a); every path is resolved from `--root`, from this package's
own location, or from the argument the operator passed.
"""

__all__ = ["claims", "anchor", "stamp", "wheel", "scan", "install"]
