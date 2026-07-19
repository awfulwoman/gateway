#!/usr/bin/env python3
"""One-off migration: import a vCard (.vcf) export into the Radicale addressbook
Gateway's Contacts tools use.

Export contacts from macOS Contacts.app (File > Export > Export vCard...) or from
iCloud, then run this once against the resulting .vcf file. Reads GATEWAY_RADICALE__*
from the gateway's own .env (via gateway.config.Config) — same as the server does.

Idempotent for cards that carry a UID (the common case for an export): re-running
overwrites rather than duplicating, since the UID becomes the Radicale card's stable
filename. Cards with no UID get a fresh one minted on the spot each run, so re-running
the script against such a card *will* duplicate it — noted in the output.

Not part of the gateway package - delete after use.

Usage:
    cd /opt/awfulwoman/gateway && uv run scripts/import_contacts_to_radicale.py <path-to-export.vcf> [--dry-run]
"""
from __future__ import annotations
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import vobject
from gateway.config import Config
from gateway.tools import contacts


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print("Usage: import_contacts_to_radicale.py <path-to-export.vcf> [--dry-run]")
        sys.exit(1)
    vcf_path = args[0]

    config = Config()
    assert config.radicale.base_url, "GATEWAY_RADICALE__BASE_URL required"
    contacts.init(config.radicale)

    with open(vcf_path, encoding="utf-8") as f:
        text = f.read()

    imported = skipped = 0
    for card in vobject.readComponents(text):
        if not hasattr(card, "fn"):
            print("  skipping a card with no FN (name) property")
            skipped += 1
            continue
        fresh_uid = not hasattr(card, "uid")
        if fresh_uid:
            card.add("uid").value = str(uuid.uuid4())
        card_id = card.uid.value
        note = " (no UID in source — will duplicate on re-run)" if fresh_uid else ""
        print(f"  {'would import' if dry_run else 'importing'}: {card.fn.value}{note}")
        if dry_run:
            imported += 1
            continue
        r = contacts._client().put(
            contacts._card_url(card_id), card.serialize(), {"Content-Type": "text/vcard; charset=utf-8"}
        )
        if r.status in (200, 201, 204):
            imported += 1
        else:
            print(f"    failed ({r.status})")
            skipped += 1

    label = "Would import" if dry_run else "Imported"
    print(f"\n{label} {imported} contacts.")
    if skipped:
        print(f"  {skipped} skipped.")


if __name__ == "__main__":
    main()
