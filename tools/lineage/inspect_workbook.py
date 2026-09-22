#!/usr/bin/env python3
"""Inspect an XLSX evidence workbook without reading cell values."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


SCHEMA_VERSION = 1
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
ALLOWED_RELATIONSHIP_TYPES = {
    "calcChain",
    "comments",
    "core-properties",
    "customXml",
    "customXmlProps",
    "drawing",
    "extended-properties",
    "hyperlink",
    "officeDocument",
    "printerSettings",
    "sharedStrings",
    "styles",
    "table",
    "theme",
    "vmlDrawing",
    "worksheet",
}
ALLOWED_ENTRY_PATTERNS = (
    re.compile(r"^\[Content_Types\]\.xml$"),
    re.compile(r"^_rels/\.rels$"),
    re.compile(r"^docProps/(?:app|core)\.xml$"),
    re.compile(r"^xl/_rels/workbook\.xml\.rels$"),
    re.compile(r"^xl/(?:calcChain|sharedStrings|styles|workbook)\.xml$"),
    re.compile(r"^xl/theme/theme\d+\.xml$"),
    re.compile(r"^xl/worksheets/sheet\d+\.xml$"),
    re.compile(r"^xl/worksheets/_rels/sheet\d+\.xml\.rels$"),
)
EXTERNAL_FORMULA_PATTERNS = (
    re.compile(r"\[[^\]]+\]"),
    re.compile(r"(?i)(?:https?|file|ftp)://"),
    re.compile(r"\\\\"),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        data = archive.read(name)
    except KeyError as error:
        raise ValueError(f"Workbook is missing required part: {name}") from error
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise ValueError(f"Workbook XML is invalid: {name}: {error}") from error


def relationship_type(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def is_allowed_entry(name: str) -> bool:
    return any(pattern.fullmatch(name) for pattern in ALLOWED_ENTRY_PATTERNS)


def external_formula(text: str) -> bool:
    return any(pattern.search(text) for pattern in EXTERNAL_FORMULA_PATTERNS)


def inspect_workbook(
    workbook_path: Path,
    *,
    reported_path: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    workbook_path = workbook_path.resolve()
    data = workbook_path.read_bytes()
    digest = sha256_bytes(data)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            f"Workbook SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )

    with zipfile.ZipFile(workbook_path) as archive:
        bad_archive_entry_paths = []
        duplicate_entries = []
        seen_entries: set[str] = set()
        entry_names = []
        total_uncompressed_bytes = 0
        total_compressed_bytes = 0
        for info in archive.infolist():
            name = info.filename
            entry_names.append(name)
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                bad_archive_entry_paths.append(name)
            if name in seen_entries:
                duplicate_entries.append(name)
            seen_entries.add(name)
            total_uncompressed_bytes += info.file_size
            total_compressed_bytes += info.compress_size

        workbook_xml = parse_xml(archive, "xl/workbook.xml")
        sheets = [
            sheet.attrib.get("name", "")
            for sheet in workbook_xml.findall(
                f".//{{{MAIN_NS}}}sheet"
            )
        ]

        content_types = parse_xml(archive, "[Content_Types].xml")
        macro_content_types = []
        for element in content_types:
            content_type = element.attrib.get("ContentType", "")
            part_name = element.attrib.get("PartName", "")
            if "macroenabled" in content_type.casefold() or "vbaproject" in (
                content_type.casefold()
            ):
                macro_content_types.append(
                    {
                        "part": part_name,
                        "content_type": content_type,
                    }
                )

        macro_entries = sorted(
            name
            for name in entry_names
            if name.casefold().endswith(".bin")
            or "vbaproject" in name.casefold()
            or "macrosheet" in name.casefold()
        )
        embedded_object_entries = sorted(
            name
            for name in entry_names
            if name.startswith(
                (
                    "xl/activeX/",
                    "xl/ctrlProps/",
                    "xl/embeddings/",
                    "xl/oleObjects/",
                )
            )
        )
        external_link_entries = sorted(
            name
            for name in entry_names
            if name.startswith("xl/externalLinks/")
        )
        media_entries = sorted(
            name for name in entry_names if name.startswith("xl/media/")
        )
        drawing_entries = sorted(
            name for name in entry_names if name.startswith("xl/drawings/")
        )
        unexpected_entries = sorted(
            name
            for name in entry_names
            if not name.endswith("/") and not is_allowed_entry(name)
        )

        relationship_counts: Counter[str] = Counter()
        external_relationships = []
        hyperlink_relationships = []
        unexpected_relationships = []
        relationship_count = 0
        for relationship_part in sorted(
            name for name in entry_names if name.endswith(".rels")
        ):
            root = parse_xml(archive, relationship_part)
            for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
                relationship_count += 1
                type_name = relationship_type(
                    relationship.attrib.get("Type", "")
                )
                relationship_counts[type_name] += 1
                target = relationship.attrib.get("Target", "")
                target_mode = relationship.attrib.get("TargetMode", "")
                record = {
                    "source": relationship_part,
                    "type": type_name,
                    "target_sha256": hashlib.sha256(
                        target.encode("utf-8")
                    ).hexdigest(),
                }
                if type_name not in ALLOWED_RELATIONSHIP_TYPES:
                    unexpected_relationships.append(record)
                if target_mode.casefold() == "external":
                    if type_name == "hyperlink":
                        hyperlink_relationships.append(record)
                    else:
                        external_relationships.append(record)

        formula_count = 0
        external_formula_references = []
        hyperlink_element_count = 0
        for worksheet_name in sorted(
            name
            for name in entry_names
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        ):
            worksheet = parse_xml(archive, worksheet_name)
            hyperlink_element_count += len(
                worksheet.findall(f".//{{{MAIN_NS}}}hyperlink")
            )
            for cell in worksheet.findall(f".//{{{MAIN_NS}}}c"):
                formula = cell.find(f"{{{MAIN_NS}}}f")
                if formula is None:
                    continue
                formula_count += 1
                formula_text = formula.text or ""
                if external_formula(formula_text):
                    external_formula_references.append(
                        {
                            "cell": cell.attrib.get("r"),
                            "formula_sha256": hashlib.sha256(
                                formula_text.encode("utf-8")
                            ).hexdigest(),
                            "source": worksheet_name,
                        }
                    )

        defined_name_count = 0
        external_defined_names = []
        for defined_name in workbook_xml.findall(
            f".//{{{MAIN_NS}}}definedName"
        ):
            defined_name_count += 1
            formula_text = defined_name.text or ""
            if external_formula(formula_text):
                external_defined_names.append(
                    {
                        "formula_sha256": hashlib.sha256(
                            formula_text.encode("utf-8")
                        ).hexdigest(),
                        "name": defined_name.attrib.get("name"),
                    }
                )

    safety_checks = {
        "archive_paths_safe": not bad_archive_entry_paths,
        "no_duplicate_entries": not duplicate_entries,
        "no_macros": not macro_entries and not macro_content_types,
        "no_embedded_objects": not embedded_object_entries,
        "no_external_link_parts": not external_link_entries,
        "no_external_non_hyperlink_relationships": not external_relationships,
        "no_external_formula_references": (
            not external_formula_references and not external_defined_names
        ),
        "no_unexpected_relationships": not unexpected_relationships,
        "no_unexpected_package_entries": not unexpected_entries,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "workbook": {
            "path": reported_path,
            "sha256": digest,
            "size_bytes": len(data),
            "sheet_count": len(sheets),
            "sheet_names": sheets,
        },
        "package": {
            "entry_count": len(entry_names),
            "total_compressed_bytes": total_compressed_bytes,
            "total_uncompressed_bytes": total_uncompressed_bytes,
            "relationship_count": relationship_count,
            "relationship_types": dict(sorted(relationship_counts.items())),
            "media_entries": len(media_entries),
            "drawing_entries": len(drawing_entries),
        },
        "features": {
            "formula_count": formula_count,
            "defined_name_count": defined_name_count,
            "hyperlink_elements": hyperlink_element_count,
            "external_hyperlink_relationships": len(
                hyperlink_relationships
            ),
        },
        "findings": {
            "bad_archive_entry_paths": bad_archive_entry_paths,
            "duplicate_entries": duplicate_entries,
            "macro_entries": macro_entries,
            "macro_content_types": macro_content_types,
            "embedded_object_entries": embedded_object_entries,
            "external_link_entries": external_link_entries,
            "external_relationships": external_relationships,
            "external_formula_references": external_formula_references,
            "external_defined_names": external_defined_names,
            "unexpected_relationships": unexpected_relationships,
            "unexpected_package_entries": unexpected_entries,
        },
        "safety_checks": safety_checks,
        "safe": all(safety_checks.values()),
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telemetry/run-2/validation/workbook-safety.json"),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--expected-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook = args.workbook.resolve()
    repo_root = args.repo_root.resolve()
    try:
        reported_path = workbook.relative_to(repo_root).as_posix()
    except ValueError:
        reported_path = workbook.name
    report = inspect_workbook(
        workbook,
        reported_path=reported_path,
        expected_sha256=args.expected_sha256,
    )
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "safe": report["safe"],
                "sha256": report["workbook"]["sha256"],
                "size_bytes": report["workbook"]["size_bytes"],
                "sheet_count": report["workbook"]["sheet_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
