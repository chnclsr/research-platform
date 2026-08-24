"""
Which pages went to the heavy engine, and what it produced for them.

The information is already in every delivery, in `13_raw_sources.jsonl` -- but getting at
it took five steps: find the bundle, unzip it, parse a line that carries the base64 of the
whole source file inline (11.5 MB of it, to reach 212 KB of text), split the markdown on
its page headings, then cross-reference the routing record to see which of those pages the
heavy engine actually produced. That is one command's worth of work spread over five.

    inspect_bundle.py 01M0SBTA6MQ07ETFHPKAJQH9HZ            # routing summary
    inspect_bundle.py 01M0SBTA6MQ07ETFHPKAJQH9HZ --heavy    # + every heavy page's markdown
    inspect_bundle.py 01M0SBTA6MQ07ETFHPKAJQH9HZ --fast     # + every retained fast page
    inspect_bundle.py 01M0SBTA6MQ07ETFHPKAJQH9HZ --all      # + every PDF page
    inspect_bundle.py raw_bundle.zip --page 6               # one page, with its reason
    inspect_bundle.py raw_bundle.zip --out pages/           # one .md per page, to diff
    inspect_bundle.py raw_bundle.zip --pdf inputs/          # the bytes the engine got

A run id is resolved first against RESEARCH_OUTPUT_DIR, where the report sync drops each
finished run as `<date>_<title>_<run_id>_both.zip`, and then against object storage. The
second lookup is the one that matters in practice: the sync is a scheduled task, so a run
that finished minutes ago is not on disk yet, and "wait for the next sync" is the opposite
of one command. Storage copies land in outputs/.bundles/ so a second look is instant. A
path is used as given, and may be the bundle zip or the bare jsonl.

Markdown report names carry the selection mode automatically: `--fast --md report.md`
writes `report_fast.md`, while `--heavy` writes `report_heavy.md`. Directory targets use
the same rule. A suffix the caller already supplied is not duplicated.

The page markdown printed here is the MERGED text, which is the engine's own output with
one transformation: `merge.nest_under_page()` pushes each page's headings down a level so
`# Page N` stays the only level-1 heading. Verified 2026-08-24 against a live run -- undo
that shift and the stored page is byte-identical to what the engine returned.

REPLAYING A PAGE. `--pdf` writes the exact bytes the engine was given, and the summary
prints the block list it was called with. Both matter: measured 2026-08-24, asking for
page 6 alone returns 3599 characters while asking for it inside its original [5,8] block
returns 3522 -- Docling drops running headers it can only recognise across a range. A
replay with different blocks is a different call.
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import zipfile

try:
    from research_platform.parsers.smart_router.pages import (
        ardisik_bloklar, docling_page_range,
    )

    _BLOCKS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on where the bundle is inspected
    _BLOCKS_AVAILABLE = False

RAW_SOURCES = "13_raw_sources.jsonl"
#: Bundles pulled from object storage land here so a second look is instant.
CACHE_DIR = os.path.join("outputs", ".bundles")
#: `sayfa_basliklariyla()` emits exactly this, and passages.py parses it back out.
PAGE_HEADING = re.compile(r"(?m)^# Page (\d+)$")
RUN_ID = re.compile(r"^[0-9A-Z]{26}$")
FAST_ENGINE = "pdf-inspector"


def _output_dir() -> str:
    """Where the report sync drops finished runs."""
    configured = os.environ.get("RESEARCH_OUTPUT_DIR")
    if not configured:
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            with open(os.path.join(here, ".env"), encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("RESEARCH_OUTPUT_DIR="):
                        configured = line.split("=", 1)[1].strip()
                        break
        except OSError:
            pass
    return os.path.expandvars(configured or "%USERPROFILE%/ResearchBackups")


def _from_minio(run_id: str, refresh: bool = False) -> str | None:
    """Pull the bundle straight from object storage, cached under CACHE_DIR.

    The report sync is a scheduled task, so a run that finished minutes ago is not on
    disk yet -- and "wait for the next sync" is the opposite of one command. Storage has
    it the moment the run completes.

    `refresh` drops the cached copy first. A run that is exported again -- because the
    export gained a field, say -- keeps its id, so the cache would go on serving the old
    bundle and the new field would look like it never landed.
    """
    try:
        from minio import Minio

        from research_platform.config import get_settings
    except Exception:
        return None

    settings = get_settings()
    os.makedirs(CACHE_DIR, exist_ok=True)
    cached = os.path.join(CACHE_DIR, f"{run_id}_raw_bundle.zip")
    if os.path.exists(cached):
        if not refresh:
            return cached
        os.unlink(cached)

    # The configured endpoint names the compose service, which does not resolve from the
    # host. Fall back to the published port rather than making the caller know that.
    endpoints = [settings.minio_endpoint]
    if "://" not in settings.minio_endpoint and not settings.minio_endpoint.startswith(
        ("localhost", "127.")
    ):
        endpoints.append("localhost:9000")

    for endpoint in endpoints:
        try:
            client = Minio(
                endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            response = client.get_object(
                settings.minio_bucket, f"runs/{run_id}/raw_bundle.zip"
            )
            try:
                with open(cached, "wb") as handle:
                    handle.write(response.read())
            finally:
                response.close()
                response.release_conn()
            return cached
        except Exception:
            continue
    return None


def _resolve(target: str, refresh: bool = False) -> str:
    if not RUN_ID.match(target):
        if not os.path.exists(target):
            raise SystemExit(
                f"No such file: {target}\n"
                "Pass a bundle path, or just the run id -- the run id is looked up in "
                f"{_output_dir()} and then in object storage."
            )
        return target

    directory = _output_dir()
    matches = sorted(glob.glob(os.path.join(directory, f"*{target}*.zip")))
    if matches and not refresh:
        return matches[-1]

    fetched = _from_minio(target, refresh=refresh)
    if not fetched and matches:
        return matches[-1]
    if fetched:
        return fetched

    raise SystemExit(
        f"No bundle for run {target}: not under {directory}, and object storage did not "
        "return one. The sync task may not have run yet; pass the bundle path directly, "
        "or set RESEARCH_OUTPUT_DIR."
    )


def _records(path: str) -> list[dict]:
    """Accept the bundle zip or the raw dump on its own."""
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            if RAW_SOURCES not in archive.namelist():
                raise SystemExit(
                    f"{os.path.basename(path)} has no {RAW_SOURCES}. result_bundle.zip is "
                    "the synthesis package; use raw_bundle.zip or research_bundle.zip."
                )
            payload = archive.read(RAW_SOURCES).decode("utf-8")
    else:
        with open(path, encoding="utf-8") as handle:
            payload = handle.read()
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _split_pages(content: str) -> dict[int, str]:
    """`# Page N` back into {page number: markdown}."""
    parts = PAGE_HEADING.split(content or "")
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def _timing(parse: dict) -> str | None:
    """Where the parse time went, or None for a record that predates the measurement."""
    toplam = parse.get("duration_ms")
    if toplam is None:
        return None
    parcalar = [f"total {toplam / 1000:.1f}s"]
    gate = parse.get("gate_duration_ms")
    if gate is not None:
        parcalar.append(f"gate {gate / 1000:.1f}s")
    for engine, ms in (parse.get("engine_durations_ms") or {}).items():
        parcalar.append(f"{engine} {ms / 1000:.1f}s")
    return " · ".join(parcalar)


def _fast_state(page: dict) -> str | None:
    """Why the final page still belongs to the fast extractor, if it does.

    `decision` says the router wanted a heavy comparison; `fell_back` says the engine
    did not deliver one. A routed page that did deliver but still ends up on the fast
    engine was quarantined by the output check. Keeping these cases separate is the
    useful part of `--fast`: "Inspector page" otherwise hides two degraded paths among
    the ordinary untouched pages.
    """
    if page.get("engine") != FAST_ENGINE:
        return None
    if page.get("fell_back"):
        return "fallback"
    if page.get("decision"):
        return "quarantined"
    return "untouched"


def _label(number: int, by_number: dict) -> str:
    page = by_number.get(number) or {}
    engine = page.get("engine") or "?"
    reason = json.dumps(page.get("decision") or [])
    state = _fast_state(page)
    parts = [f"page {number}", engine]
    if state:
        parts.append(state)
    parts.append(reason)
    if page.get("karar_gerekcesi"):
        parts.append(str(page["karar_gerekcesi"]))
    return " | ".join(parts)


def _selection_requested(args: argparse.Namespace) -> bool:
    return bool(args.page or args.heavy or args.fast or args.all)


def _wanted(markdown: dict, by_number: dict, args: argparse.Namespace) -> list[int]:
    """Which pages the caller asked to see, in page order."""
    if args.page:
        return [number for number in sorted(set(args.page)) if number in markdown]
    if args.all:
        return sorted(markdown)
    if args.fast:
        return [
            number for number in sorted(markdown)
            if _fast_state(by_number.get(number) or {}) is not None
        ]
    heavy = [n for n in sorted(markdown) if (by_number.get(n) or {}).get("decision")]
    if args.heavy:
        return heavy
    if args.out:
        # --out on its own dumps the whole document; --out --heavy narrows it.
        return sorted(markdown)
    return []


def _show_pages(markdown: dict, by_number: dict, args: argparse.Namespace) -> None:
    if not _selection_requested(args):
        return
    for number in _wanted(markdown, by_number, args):
        print("\n" + "-" * 78)
        print(_label(number, by_number))
        print("-" * 78)
        print(markdown[number])


def _write_pages(markdown: dict, by_number: dict, source_id: str,
                 args: argparse.Namespace) -> None:
    if not args.out:
        return
    directory = os.path.join(args.out, source_id)
    os.makedirs(directory, exist_ok=True)
    written = 0
    for number in _wanted(markdown, by_number, args):
        page = by_number.get(number) or {}
        engine = (page.get("engine") or "fast").replace("/", "-")
        target = os.path.join(directory, f"p{number:04d}_{engine}.md")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(f"<!-- {_label(number, by_number)} -->\n\n{markdown[number]}\n")
        written += 1
    print(f"\n  wrote {written} page files -> {directory}")


def _write_input(version: dict, source_id: str, args: argparse.Namespace) -> None:
    if not (args.pdf and version.get("raw_content")):
        return
    try:
        payload = base64.b64decode(version["raw_content"], validate=True)
    except Exception:
        return
    # Only what the heavy engine could have been given. HTML sources carry raw_content
    # too, and writing those out as .pdf would be a lie.
    if payload[:4] != b"%PDF":
        return
    os.makedirs(args.pdf, exist_ok=True)
    target = os.path.join(args.pdf, f"{source_id}.pdf")
    with open(target, "wb") as handle:
        handle.write(payload)
    print(f"\n  input file -> {target} ({len(payload)} bytes)")


def _report(record: dict, args: argparse.Namespace) -> None:
    source, version = record["source"], record["version"]
    provenance = version.get("provenance") or {}
    parse = provenance.get("parse_provenance") or {}

    print("=" * 78)
    print(f"{provenance.get('document_type')} | {provenance.get('parser_id')} | {source['id']}")
    print(f"  {source['url']}")
    print(f"  content_hash {version.get('content_hash')}")

    if not parse:
        print("  single-extractor parser -- no routing record")
        return

    pages = parse.get("pages") or []
    routed = [page for page in pages if page.get("decision")]
    retained_fast = [page for page in pages if _fast_state(page)]
    fast_states = {
        state: sum(_fast_state(page) == state for page in retained_fast)
        for state in ("untouched", "fallback", "quarantined")
    }
    by_number = {page["page"]: page for page in pages}
    print(f"  pages {len(pages)} | routed heavy {len(routed)} "
          f"| engines {parse.get('engine_counts')}")
    print(f"  retained fast {len(retained_fast)} | states {fast_states}")
    print(f"  device {parse.get('engine_devices')} | degraded={parse.get('degraded')}")
    if parse.get("engine_build"):
        print(f"  build {parse['engine_build']}")
    zaman = _timing(parse)
    if zaman:
        print(f"  time {zaman}")
    if parse.get("notes"):
        print(f"  notes {parse['notes']}")
    if parse.get("fallback_pages"):
        print(f"  KEPT FAST TEXT (engine missed): {parse['fallback_pages']}")
    if parse.get("quarantined_pages"):
        print(f"  QUARANTINED (heavy scored no better): {parse['quarantined_pages']}")

    if routed:
        numbers = [page["page"] for page in routed]
        if _BLOCKS_AVAILABLE:
            blocks = [list(docling_page_range(b)) for b in ardisik_bloklar(numbers)]
            print(f"\n  blocks sent: {json.dumps(blocks)}")
        else:
            print("\n  blocks sent: (research_platform not importable -- not derived)")
        header = f"\n  {'page':>5} {'engine':<16} {'reason':<36} {'fast':>7} {'heavy':>7}"
        print(header)
        for page in routed:
            print(f"  {page['page']:>5} {page.get('engine', ''):<16} "
                  f"{json.dumps(page.get('decision')):<36} "
                  f"{str(page.get('fast_skor')):>7} {str(page.get('heavy_skor')):>7}")

    markdown = _split_pages(version.get("content", ""))
    _show_pages(markdown, by_number, args)
    _write_pages(markdown, by_number, source["id"], args)
    _write_input(version, source["id"], args)


def _markdown_report(record: dict, args: argparse.Namespace) -> list[str]:
    """The same findings as one markdown document, for reading and for sharing.

    Not the stdout text with a `.md` name on it: that is `===` rules and
    space-aligned columns, which renders as one grey blob. The routing record becomes a
    real table, and each page's own markdown is embedded as-is -- tables in it have to
    keep rendering, which rules out fencing it.

    Page content already starts at `##` (its headings were pushed down a level so
    `# Page N` could be the only level-1), so the page heading here is `##` too and the
    content sits beside it rather than under it. Demoting it further would mean altering
    the very text this artifact exists to show.
    """
    source, version = record["source"], record["version"]
    provenance = version.get("provenance") or {}
    parse = provenance.get("parse_provenance") or {}
    lines = [
        f"# {provenance.get('document_type')} · {provenance.get('parser_id')}",
        "",
        f"- source: `{source['id']}`",
        f"- url: <{source['url']}>",
        f"- content_hash: `{version.get('content_hash')}`",
    ]
    if not parse:
        lines += ["- single-extractor parser -- no routing record", ""]
        return lines

    pages = parse.get("pages") or []
    routed = [page for page in pages if page.get("decision")]
    retained_fast = [page for page in pages if _fast_state(page)]
    fast_states = {
        state: sum(_fast_state(page) == state for page in retained_fast)
        for state in ("untouched", "fallback", "quarantined")
    }
    by_number = {page["page"]: page for page in pages}
    lines += [
        f"- pages: {len(pages)} · routed heavy: {len(routed)}",
        f"- retained fast: {len(retained_fast)} · "
        f"untouched: {fast_states['untouched']} · fallback: {fast_states['fallback']} · "
        f"quarantined: {fast_states['quarantined']}",
        f"- engines: `{parse.get('engine_counts')}`",
        f"- device: `{parse.get('engine_devices')}` · degraded: `{parse.get('degraded')}`",
    ]
    if parse.get("engine_build"):
        lines.append(f"- build: `{parse['engine_build']}`")
    zaman = _timing(parse)
    if zaman:
        lines.append(f"- time: {zaman}")
    for label, key in (("kept fast text", "fallback_pages"),
                       ("quarantined", "quarantined_pages")):
        if parse.get(key):
            lines.append(f"- {label}: `{parse[key]}`")
    if routed and _BLOCKS_AVAILABLE:
        numbers = [page["page"] for page in routed]
        blocks = [list(docling_page_range(b)) for b in ardisik_bloklar(numbers)]
        lines.append(f"- blocks sent: `{json.dumps(blocks)}`")

    if routed:
        lines += ["", "| page | engine | reason | fast | heavy |",
                  "|---:|---|---|---:|---:|"]
        for page in routed:
            reasons = ", ".join(f"`{r}`" for r in (page.get("decision") or []))
            lines.append(
                f"| {page['page']} | {page.get('engine', '')} | {reasons} "
                f"| {page.get('fast_skor')} | {page.get('heavy_skor')} |"
            )

    markdown = _split_pages(version.get("content", ""))
    for number in _wanted(markdown, by_number, args):
        page = by_number.get(number) or {}
        reasons = ", ".join(page.get("decision") or []) or "fast path"
        details = [_fast_state(page), reasons, page.get("karar_gerekcesi")]
        detail = " · ".join(str(item) for item in details if item)
        lines += ["", f"## Page {number} — {page.get('engine') or FAST_ENGINE} "
                      f"({detail})", "", markdown[number]]
    lines.append("")
    return lines


def _mode_suffix(args: argparse.Namespace) -> str:
    """Stable filename suffix for the page selection represented by this report."""
    if args.page:
        pages = "-".join(str(number) for number in sorted(set(args.page)))
        return f"_page-{pages}"
    if args.heavy:
        return "_heavy"
    if args.fast:
        return "_fast"
    if args.all:
        return "_all"
    return ""


def _append_mode(path: str, suffix: str) -> str:
    """Insert the mode before the extension, without producing `_fast_fast.md`."""
    if not suffix:
        return path
    stem, extension = os.path.splitext(path)
    if stem.endswith(suffix):
        return path
    return f"{stem}{suffix}{extension}"


def _md_target(destination: str, target: str, args: argparse.Namespace) -> str:
    """A directory destination names the file after the run, a file path is taken as given.

    Reports are read one run at a time but written over and over, and the obvious habit
    -- always `--md outputs/report.md` -- used to let `--fast` and `--heavy` silently
    overwrite one another. The selection suffix is applied to both explicit filenames
    and directory-derived names; pointing at a directory additionally lets the run name
    the file.
    """
    suffix = _mode_suffix(args)
    if not (destination.endswith(("/", "\\")) or os.path.isdir(destination)):
        return _append_mode(destination, suffix)
    stem = target if RUN_ID.match(target) else os.path.basename(target).split(".")[0]
    return os.path.join(destination, f"{stem}{suffix}.md")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Which pages went to the heavy engine, and what it produced.",
    )
    parser.add_argument("target", help="run id, bundle zip, or 13_raw_sources.jsonl")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--page", type=int, action="append", metavar="N",
                           help="print this page's markdown (repeatable)")
    selection.add_argument("--heavy", action="store_true",
                           help="print the markdown of every heavy-routed page")
    selection.add_argument("--fast", action="store_true",
                           help="print every page whose final text came from pdf-inspector")
    selection.add_argument("--all", action="store_true",
                           help="print every PDF page")
    parser.add_argument("--out", metavar="DIR",
                        help="write one .md per page into DIR (all pages, or selection only)")
    parser.add_argument("--pdf", metavar="DIR",
                        help="write the bytes the heavy engine received into DIR")
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch the bundle instead of using the cached copy")
    parser.add_argument("--md", metavar="FILE|DIR",
                        help="write the report as markdown; a directory is named after "
                             "the run, - is stdout")
    args = parser.parse_args()

    records = _records(_resolve(args.target, refresh=args.refresh))
    if not args.md:
        for record in records:
            _report(record, args)
        return

    lines: list[str] = []
    for record in records:
        lines += _markdown_report(record, args)
    document = "\n".join(lines)
    if args.md == "-":
        print(document)
        return
    target = _md_target(args.md, args.target, args)
    # Written here rather than left to a shell redirect: PowerShell picks its own
    # encoding for `>` and a UTF-16 markdown file is a bad surprise.
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(document)
    print(f"wrote {target} ({len(document)} characters)")


if __name__ == "__main__":
    main()
