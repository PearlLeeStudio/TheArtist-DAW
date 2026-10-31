"""Download fixed, attributed evaluation sources; never training or product assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

MUTOPIA = (
    ("bach-bwv846-prelude", 5),
    ("bach-bwv847-prelude", 550),
    ("mozart-k2-minuet", 1770),
    ("beethoven-op2-1-allegro", 1211),
    ("schumann-op68-1", 647),
    ("greensleeves-satb", 1247),
    ("amazing-grace", 1832),
    ("greensleeves-guitar", 1943),
)
MOZART = ("K279-1", "K280-1", "K281-1", "K282-1", "K283-1", "K284-1",
          "K309-1", "K310-1", "K311-1", "K330-1", "K332-1", "K545-1")
LICENSES = ("Public Domain", "Creative Commons Attribution-ShareAlike 2.5",
            "Creative Commons Attribution-ShareAlike 4.0", "Creative Commons Attribution 4.0",
            "Creative Commons Attribution-ShareAlike 3.0")


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "TheArtist-evaluation/1"}), timeout=40) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Evaluation source exceeds 8 MiB")
    return data


def plain(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", value)).split())


def save(url: str, path: Path) -> dict:
    data = path.read_bytes() if path.exists() else fetch(url)
    if not path.exists():
        path.write_bytes(data)
    return {"url": url, "file": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if not args.directory.is_absolute():
        parser.error("Use an absolute directory")
    args.directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name, identifier in MUTOPIA:
        url = f"https://www.mutopiaproject.org/cgibin/piece-info.cgi?id={identifier}"
        page = fetch(url).decode("utf8")
        text = plain(page)
        copyright_text = text.split("Copyright:", 1)[1].split("Last updated:", 1)[0].strip()
        license_name = next((license_ for license_ in LICENSES if copyright_text == license_), None)
        if not license_name:
            raise ValueError(f"Review source license before downloading {name}: {copyright_text}")
        links = [(urljoin(url, href), plain(label)) for href, label in
                 re.findall(r'<a\b[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', page, re.S | re.I)]
        files = {}
        for kind, suffix, label in (("pdf", ".pdf", "A4 PDF"), ("midi", ".mid", "MIDI file"),
                                     ("lilypond", ".ly", "LilyPond file")):
            source = next(link for link, title in links if label in title and link.endswith(suffix))
            files[kind] = save(source, args.directory / (name + suffix))
        records.append({"id": name, "sourcePage": url, "license": license_name,
                        "title": plain(re.search(r"<h2[^>]*>(.*?)</h2>", page, re.S).group(1)),
                        "maintainer": text.split("Maintainer:", 1)[1].split("|", 1)[0].split("Disclaimer", 1)[0].strip(),
                        "files": files})
        print(json.dumps({"source": name, "license": license_name, "files": list(files)}), flush=True)
    dcml = []
    for name in MOZART:
        url = f"https://raw.githubusercontent.com/DCMLab/mozart_piano_sonatas/v2.3/harmonies/{name}.harmonies.tsv"
        dcml.append({"id": name, **save(url, args.directory / (name + ".harmonies.tsv"))})
    result = {"mutopia": records,
              "dcml": {"version": "v2.3", "license": "CC BY-NC-SA 4.0",
                       "licenseUrl": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
                       "source": "https://dcmlab.github.io/mozart_piano_sonatas/",
                       "citation": "Hentschel, Neuwirth & Rohrmeier. The Annotated Mozart Sonatas: Score, harmony, and cadence. doi:10.5334/tismir.63",
                       "use": "Noncommercial research evaluation only; not added to training, retrieval, or product deployment.",
                       "files": dcml}}
    (args.directory / "sources.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Prepared {len(records)} score editions and {len(dcml)} annotated movements.")


if __name__ == "__main__":
    main()
