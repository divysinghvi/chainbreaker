"""Export / import gzipped crawl snapshots (the deployable artefact)."""
import gzip
import json

from .. import config
from ..analysis.redact import redact_crawl
from .load import load


def path_for(ds: str):
    return config.SNAPSHOTS / f"{ds}.crawl.json.gz"


def export(ds: str, redact: bool = False) -> str:
    crawl = json.loads((config.CACHE / ds / "crawl.json").read_text())
    if redact:
        crawl = redact_crawl(crawl)
    p = path_for(ds)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt") as f:
        json.dump(crawl, f, separators=(",", ":"))
    return str(p)


def read(ds: str) -> dict:
    with gzip.open(path_for(ds), "rt") as f:
        return json.load(f)


def import_(ds: str) -> dict:
    return load(ds, read(ds))
