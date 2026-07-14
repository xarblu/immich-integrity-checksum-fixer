#!/usr/bin/env python3

"""
Basic script reads the Immich Checksum Mismatch report CSV
from stdin and recalculates all bad checksums
"""

import pathlib
import hashlib
import subprocess
import csv
import sys
import argparse

from typing import Any


def log(*args: Any) -> None:
    print(args, file=sys.stderr)


def sha1sum(path: pathlib.Path) -> str | None:
    sha1 = hashlib.sha1()

    with path.open("rb") as fd:
        while chunk := fd.read(4096):
            sha1.update(chunk)

    return sha1.hexdigest()


def dbQuery(query: str) -> Any:
    """
    Execute a database query

    I know this is a comically bad way to do it
    but it requires no libraries and is simple
    """
    wrap = ["podman", "exec", "-i", "systemd-immich-database"]

    cmd = wrap + [
        "psql",
        "-U", "postgres",
        "--dbname", "immich",
        "--no-align", "--field-separator-zero",
        "--command", query
    ]

    proc = subprocess.run(cmd, check=True, capture_output=True)

    rows: list[bytes] = proc.stdout.splitlines()

    # at least header + row count
    if len(rows) < 2:
        raise ValueError("psql did not return at least 2 rows"
                         " (header + row count)")

    fields: list[str] = []
    records: list[dict[str, str]] = []

    for i, row in enumerate(rows):
        if i <= 0:
            fields = [x.decode() for x in row.split(b"\0")]
            continue

        if i >= len(rows) - 1:
            break

        records.append({x[0]: x[1].decode()
                        for x in zip(fields, row.split(b"\0"))})

    return records


def dbChecksum(id: str) -> str:
    """
    Fetch the assets checksum from the database
    """
    assets = dbQuery("SELECT encode(\"checksum\", 'hex') "
                     "FROM \"asset\" "
                     f"WHERE \"id\" = '{id}';")

    if len(assets) != 1:
        raise ValueError(f"Query returned {len(assets)} assets")

    log(assets)
    return assets[0]["checksum"]


def main() -> int:
    with open(sys.argv[1], newline='') as fd:
        report = csv.DictReader(fd)

        for row in report:
            path = pathlib.Path(row["path"])
            diskSha1 = sha1sum(path)
            dbSha1 = dbChecksum(row["assetId"])

            if diskSha1 != dbSha1:
                log(f"Checksum mismatch: DB: {dbSha1} Disk: {diskSha1}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
