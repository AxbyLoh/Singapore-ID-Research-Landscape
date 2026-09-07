#!/usr/bin/env python3
"""Build/refresh data/directory_of_experts.csv from the CDA Directory of Experts.

    # live fetch (needs network access to www.cda.gov.sg)
    python3 fetch_experts.py --out ../data/directory_of_experts.csv

    # offline: parse HTML the user saved or pasted
    python3 fetch_experts.py --from-html saved/*.html --out ../data/directory_of_experts.csv

    # see what would change, without writing
    python3 fetch_experts.py --dry-run

Merge semantics: rows are matched on profile_url (falling back to expert_id).
Existing rows are UPDATED in place -- manually edited fields listed in
--preserve (default: pubmed_author_query, orcid, domains, notes, active) are
never overwritten. Rows already in the CSV that the fetch did not return are
KEPT, not deleted, and their `notes` gains a 'not seen on <date>' marker.

This script never invents an expert. If it cannot reach the site and no HTML is
supplied, it exits non-zero and changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

BASE = "https://www.cda.gov.sg"
LISTING = BASE + "/professionals/research/directory-of-experts/"
PROFILE_RE = re.compile(r"/professionals/research/directory-of-experts/([a-z0-9][a-z0-9\-]+)/?$", re.I)

TITLES = [
    "clinical associate professor", "clinical assistant professor",
    "adjunct associate professor", "adjunct assistant professor",
    "associate professor", "assistant professor", "clinical professor",
    "adjunct professor", "professor", "a/prof", "asst prof", "assoc prof",
    "prof", "dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "mdm",
]

FIELDNAMES = [
    "expert_id", "full_name", "display_name", "name_variants",
    "pubmed_author_query", "orcid", "designation", "institution", "department",
    "research_areas", "domains", "profile_url", "source", "date_added",
    "last_verified", "active", "notes",
]

DEFAULT_PRESERVE = ["pubmed_author_query", "orcid", "domains", "notes", "active"]

LABELS = {
    "designation": ["designation", "appointment", "position", "title"],
    "institution": ["institution", "organisation", "organization", "affiliation", "employer"],
    "department": ["department", "division", "unit"],
    "research_areas": ["research area", "research areas", "research interest",
                       "research interests", "areas of expertise", "expertise",
                       "specialty", "specialties", "speciality"],
}


# --------------------------------------------------------------------------
# HTML handling
# --------------------------------------------------------------------------

class LinkHarvester(HTMLParser):
    """Collects directory profile links and their anchor text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = {}          # href -> anchor text
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if not href:
            return
        path = href.split("?")[0].split("#")[0]
        if PROFILE_RE.search(path):
            self._href = urljoin_simple(path)
            self._buf = []

    def handle_data(self, data):
        if self._href:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join("".join(self._buf).split())
            if text and (self._href not in self.links or len(text) > len(self.links[self._href])):
                self.links[self._href] = text
            elif self._href not in self.links:
                self.links[self._href] = text
            self._href = None
            self._buf = []


class TextExtractor(HTMLParser):
    """Flattens a page to text lines, dropping script/style, keeping headings."""

    SKIP = {"script", "style", "noscript", "svg"}
    BREAK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "section", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0
        self.title = ""
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag in self.BREAK:
            self.parts.append("\n")
        if tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in self.BREAK:
            self.parts.append("\n")
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._in_h1 and data.strip() and not self.title:
            self.title = " ".join(data.split())

    def lines(self):
        text = "".join(self.parts)
        out = []
        for raw in text.split("\n"):
            s = " ".join(raw.split())
            if s:
                out.append(s)
        return out


def urljoin_simple(path):
    if path.startswith("http"):
        return path.split("?")[0].rstrip("/") + "/"
    return BASE + "/" + path.strip("/") + "/"


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; sg-id-research-landscape-skill/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


# --------------------------------------------------------------------------
# Field extraction
# --------------------------------------------------------------------------

def strip_title(name):
    n = " ".join((name or "").split())
    low = n.lower()
    for t in sorted(TITLES, key=len, reverse=True):
        if low.startswith(t + " "):
            return n[len(t) + 1:].strip(), n[:len(t)].strip()
    return n, ""


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def name_variants(full_name):
    """Candidate PubMed author forms.

    Singapore rosters mix surname-first (Chinese, Malay, Indian) and
    surname-last (Western) orders, and the site does not say which. We emit
    BOTH readings; build_queries.py ORs them under a Singapore affiliation
    filter, which suppresses most false hits. Prune by hand for prolific or
    common names.
    """
    toks = [t for t in re.split(r"[\s,]+", full_name or "") if t]
    toks = [t for t in toks if not re.fullmatch(r"\(.*\)", t)]
    if not toks:
        return []
    out = []
    if len(toks) == 1:
        return [toks[0]]
    # reading A: first token is the surname (Chinese/Malay convention)
    ini_a = "".join(t[0] for t in toks[1:]).upper()
    out.append("%s %s" % (toks[0], ini_a))
    # reading B: last token is the surname (Western convention)
    ini_b = "".join(t[0] for t in toks[:-1]).upper()
    out.append("%s %s" % (toks[-1], ini_b))
    # first initial only, both readings -- PubMed indexes many older records this way
    out.append("%s %s" % (toks[0], ini_a[:1]))
    out.append("%s %s" % (toks[-1], ini_b[:1]))
    seen, uniq = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _collect_block(lines, start):
    """Lines following a standalone heading, up to the next heading/prose."""
    block = []
    for nxt in lines[start:start + 12]:
        low = nxt.lower().rstrip(":").strip()
        if low in LABELS_FLAT or low.rstrip("s") in LABELS_FLAT:
            break
        if len(nxt) > 80 or nxt.endswith("."):
            break
        block.append(nxt)
    return block


def extract_profile(lines, display_name):
    """Best-effort labelled-field extraction. Leaves fields blank when unsure."""
    got = {"designation": "", "institution": "", "department": "", "research_areas": []}

    for i, line in enumerate(lines):
        low = line.lower().rstrip(":").strip()
        for field, labels in LABELS.items():
            if got[field]:
                continue
            for lab in labels:
                if low.startswith(lab + ":") or low.startswith(lab + " :"):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        got[field] = split_areas(value) if field == "research_areas" else value
                    break
                if low in (lab, lab + "s"):
                    block = _collect_block(lines, i + 1)
                    if block:
                        got[field] = block if field == "research_areas" else block[0]
                    break

    if isinstance(got["research_areas"], list):
        areas = []
        for chunk in got["research_areas"]:
            areas.extend(split_areas(chunk))
        got["research_areas"] = "|".join(
            dict.fromkeys(a.strip(" ,;.") for a in areas if a.strip()))

    if not got["institution"]:
        # fall back to a known Singapore institution named anywhere on the page
        resolver = _resolver()
        for line in lines:
            r = resolver.resolve(line)
            if r["institution"] and r["country"] == "Singapore":
                got["institution"] = r["institution"]
                break

    return got


LABELS_FLAT = {l for labs in LABELS.values() for l in labs}

_RESOLVER = None


def _resolver():
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = idlib.AffiliationResolver()
    return _RESOLVER


def split_areas(value):
    parts = re.split(r"\s*[|;,]\s*|\s+and\s+", value)
    return [p for p in (x.strip() for x in parts) if p]


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------

def crawl_live(max_pages, delay, verbose):
    import time
    links = {}
    for page in range(1, max_pages + 1):
        url = LISTING if page == 1 else "%s?page=%d" % (LISTING, page)
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            if page == 1:
                raise
            idlib.eprint("  listing page %d failed (%s); stopping pagination" % (page, exc))
            break
        h = LinkHarvester()
        h.feed(html)
        new = {k: v for k, v in h.links.items() if k not in links}
        if verbose:
            idlib.eprint("  page %d: %d profile links (%d new)" % (page, len(h.links), len(new)))
        if not new:
            break
        links.update(new)
        time.sleep(delay)

    people = []
    for url, anchor in sorted(links.items()):
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            idlib.eprint("  profile failed %s (%s) -- keeping name only" % (url, exc))
            people.append(build_row(anchor, url, {}))
            continue
        te = TextExtractor()
        te.feed(html)
        lines = te.lines()
        display = te.title or anchor
        people.append(build_row(display, url, extract_profile(lines, display)))
        time.sleep(delay)
    return people


def crawl_html_files(paths, verbose):
    links = {}
    profiles = {}
    for path in paths:
        html = open(path, encoding="utf-8", errors="replace").read()
        h = LinkHarvester()
        h.feed(html)
        links.update({k: v for k, v in h.links.items() if k not in links})
        te = TextExtractor()
        te.feed(html)
        lines = te.lines()
        is_listing = len(h.links) >= 2
        if te.title and not is_listing:
            # a saved profile page: key it by whichever directory URL it advertises
            own = [u for u in h.links
                   if slugify(u.rstrip("/").split("/")[-1]) in slugify(te.title)
                   or slugify(te.title) in slugify(u.rstrip("/").split("/")[-1])]
            key = own[0] if own else urljoin_simple(slugify(te.title))
            profiles[key] = (te.title, lines)
        if verbose:
            idlib.eprint("  %s: %d links, title=%r" % (os.path.basename(path), len(h.links), te.title))

    people = []
    for url, anchor in sorted(links.items()):
        display, lines = profiles.get(url, (anchor, []))
        people.append(build_row(display, url, extract_profile(lines, display) if lines else {}))
    for url, (display, lines) in profiles.items():
        if url not in links:
            people.append(build_row(display, url, extract_profile(lines, display)))
    return [p for p in people if p["expert_id"] not in ("directory-of-experts", "")]


def build_row(display_name, url, fields):
    full, _title = strip_title(display_name)
    slug = url.rstrip("/").split("/")[-1] if url else slugify(full)
    return {
        "expert_id": slug or slugify(full),
        "full_name": full,
        "display_name": " ".join((display_name or "").split()),
        "name_variants": "|".join(name_variants(full)),
        "pubmed_author_query": "",
        "orcid": "",
        "designation": fields.get("designation", ""),
        "institution": fields.get("institution", ""),
        "department": fields.get("department", ""),
        "research_areas": fields.get("research_areas", ""),
        "domains": "",
        "profile_url": url,
        "source": "cda_directory",
        "date_added": "",
        "last_verified": "",
        "active": "yes",
        "notes": "",
    }


# --------------------------------------------------------------------------
# Merge + write
# --------------------------------------------------------------------------

def merge(existing, fetched, today, preserve):
    by_url = {}
    by_id = {}
    for r in existing:
        if r.get("profile_url"):
            by_url[r["profile_url"].rstrip("/") + "/"] = r
        if r.get("expert_id"):
            by_id[r["expert_id"]] = r

    added, updated, unchanged = [], [], []
    seen_keys = set()

    for new in fetched:
        key = (new.get("profile_url") or "").rstrip("/") + "/"
        old = by_url.get(key) or by_id.get(new["expert_id"])
        if old is None:
            new["date_added"] = today
            new["last_verified"] = today
            added.append(new)
            continue
        seen_keys.add(id(old))
        changed = False
        for field in FIELDNAMES:
            if field in preserve or field in ("date_added",):
                continue
            if field == "last_verified":
                continue
            nv = new.get(field, "")
            if nv and nv != old.get(field, ""):
                old[field] = nv
                changed = True
        old["last_verified"] = today
        old.setdefault("date_added", today)
        (updated if changed else unchanged).append(old)

    stale = []
    for r in existing:
        if id(r) in seen_keys:
            continue
        if r.get("source") == "cda_directory" and fetched:
            marker = "not seen in fetch on %s" % today
            if marker not in (r.get("notes") or ""):
                r["notes"] = "; ".join(x for x in [r.get("notes", ""), marker] if x)
        stale.append(r)

    merged = []
    seen = set()
    for r in updated + unchanged + stale + added:
        k = (r.get("profile_url") or "").rstrip("/") or r.get("expert_id")
        if k in seen:
            continue
        seen.add(k)
        merged.append(r)
    merged.sort(key=lambda r: (r.get("full_name") or "").lower())
    return merged, added, updated, stale


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=idlib.EXPERTS_PATH, help="CSV to write (default: skill data file)")
    ap.add_argument("--from-html", nargs="+", metavar="FILE",
                    help="parse saved HTML instead of fetching (globs allowed)")
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (be polite)")
    ap.add_argument("--preserve", nargs="*", default=DEFAULT_PRESERVE,
                    help="columns never overwritten by a fetch")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    today = dt.date.today().isoformat()

    if args.from_html:
        paths = []
        for pat in args.from_html:
            paths.extend(sorted(glob.glob(pat)) or [pat])
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            idlib.eprint("No readable HTML files matched --from-html.")
            return 1
        print("Parsing %d saved HTML file(s)..." % len(paths))
        fetched = crawl_html_files(paths, args.verbose)
    else:
        print("Fetching %s ..." % LISTING)
        try:
            fetched = crawl_live(args.max_pages, args.delay, args.verbose)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            idlib.eprint("")
            idlib.eprint("Could not reach %s: %s" % (BASE, exc))
            idlib.eprint("")
            idlib.eprint("Nothing was written. Options:")
            idlib.eprint("  1. Run this script from a machine/network that can reach cda.gov.sg.")
            idlib.eprint("  2. Save the directory listing and profile pages as HTML and re-run with")
            idlib.eprint("     --from-html page1.html page2.html profiles/*.html")
            idlib.eprint("  3. Add rows to the CSV by hand (see data/directory_of_experts.EXAMPLE.csv).")
            idlib.eprint("")
            idlib.eprint("Do NOT fabricate roster entries -- they silently corrupt every downstream")
            idlib.eprint("search, co-authorship edge and network view.")
            return 2

    if not fetched:
        idlib.eprint("No expert profiles found. The page structure may have changed;")
        idlib.eprint("inspect the HTML and adjust PROFILE_RE / extract_profile(). Nothing written.")
        return 3

    existing = idlib.read_csv(args.out)
    merged, added, updated, stale = merge(existing, fetched, today, set(args.preserve))

    print("")
    print("Fetched : %d profiles" % len(fetched))
    print("Added   : %d" % len(added))
    print("Updated : %d" % len(updated))
    print("Kept    : %d (in CSV but not returned by this fetch)" % len(stale))
    print("Total   : %d rows" % len(merged))

    incomplete = [r for r in merged if not r.get("institution") or not r.get("research_areas")]
    if incomplete:
        print("")
        print("%d row(s) are missing institution and/or research_areas -- the profile page" % len(incomplete))
        print("layout did not expose them. Fill these in by hand; leave blank rather than guess:")
        for r in incomplete[:10]:
            print("  - %s (%s)" % (r["full_name"], r["profile_url"]))
        if len(incomplete) > 10:
            print("  ... and %d more" % (len(incomplete) - 10))

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    idlib.write_csv(args.out, merged, FIELDNAMES)
    print("\nWrote %s" % os.path.abspath(args.out))
    print("Review name_variants before searching: each name yields both a surname-first")
    print("and a surname-last reading, and common surnames need pruning by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
