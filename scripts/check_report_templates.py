"""Offline pre-copy guard for a complete, approved native template set. No network/writes."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

MIME = {"docs": "application/vnd.google-apps.document",
        "cumulative": "application/vnd.google-apps.presentation",
        "monthly": "application/vnd.google-apps.presentation"}
SHEETS_MIME = {role: "application/vnd.google-apps.spreadsheet"
               for role in ("sheets_monthly", "sheets_cumulative")}
NATIVE_MIME = {**MIME, **SHEETS_MIME}
CUMULATIVE_ROLES = {"cumulative", "sheets_cumulative"}



def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def native_document(value):
    """Use the structured native object, never the tool envelope's duplicated text."""
    if isinstance(value, dict) and "structuredContent" in value:
        if value.get("isError") is True or not isinstance(value["structuredContent"], dict):
            raise ValueError("failed or malformed native read envelope")
        return value["structuredContent"]
    return value


def stable_native(value, field=None):
    """Ignore signed Slides URLs and Docs imageProperties.contentUri only."""
    if isinstance(value, dict):
        return {k: stable_native(v, k) for k, v in value.items()
                if k != "contentUrl" and not (field == "imageProperties" and k == "contentUri")}
    if isinstance(value, list):
        return [stable_native(v, field) for v in value]
    return value


def native_digest(value):
    raw = native_document(value)
    return digest(raw if isinstance(raw, dict) and "spreadsheetId" in raw else stable_native(raw))


def neutral_slot(value):
    if not isinstance(value, str):
        return False
    if value.strip() == "—":
        return True
    tokens = re.compile(r"\{\{[A-Z0-9_]+\}\}")
    return bool(tokens.search(value)) and not re.search(r"[{}]", tokens.sub("", value))


def sheets_inventory(raw, allow_links):
    """Typed cells and stable native IDs, including hidden tabs and grid offsets."""
    texts = {"/properties/title": raw["properties"]["title"]}
    links, ids, chart_ids = {}, set(), set()
    sheets = raw["sheets"]
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("Sheets read has no worksheets")
    for sheet in sheets:
        properties = sheet["properties"]
        if not isinstance(properties, dict):
            raise ValueError("Sheets properties must be an object")
        ident = properties["sheetId"]
        if type(ident) is not int or ident < 0 or ident in ids:
            raise ValueError("Sheets duplicate/invalid sheetId")
        ids.add(ident)
        if properties.get("sheetType", "GRID") != "GRID" or not isinstance(sheet.get("data"), list):
            raise ValueError("Sheets unsupported worksheet type or absent grid data")
        base = f"/@sheetId/{ident}"
        texts[base + "/properties/title"] = properties["title"]
        grid_size = properties["gridProperties"]
        if (not isinstance(grid_size, dict)
                or any(type(grid_size.get(k)) is not int or grid_size[k] <= 0 for k in ("rowCount", "columnCount"))):
            raise ValueError("Sheets invalid grid dimensions")
        cells = set()
        for grid in sheet["data"]:
            if not isinstance(grid, dict) or not isinstance(grid.get("rowData", []), list):
                raise ValueError("Sheets grid/rows must be native objects/lists")
            row, col = grid.get("startRow", 0), grid.get("startColumn", 0)
            if any(type(n) is not int or n < 0 for n in (row, col)):
                raise ValueError("Sheets invalid grid offset")
            for r, row_data in enumerate(grid.get("rowData", []), row):
                if not isinstance(row_data, dict) or not isinstance(row_data.get("values", []), list):
                    raise ValueError("Sheets row/cells must be native objects/lists")
                for c, cell in enumerate(row_data.get("values", []), col):
                    if r >= grid_size["rowCount"] or c >= grid_size["columnCount"] or (r, c) in cells:
                        raise ValueError("Sheets overlapping/out-of-bounds cell")
                    cells.add((r, c))
                    if not isinstance(cell, dict):
                        raise ValueError("Sheets CellData must be an object")
                    entered = cell.get("userEnteredValue", {})
                    if not isinstance(entered, dict) or not isinstance(entered.get("formulaValue", ""), str):
                        raise ValueError("Sheets invalid userEnteredValue/formula")
                    formula = entered.get("formulaValue", "")
                    if ("dataSourceTable" in cell or "dataSourceFormula" in cell
                            or re.search(r"\b(?:IMAGE|IMPORT\w*)\s*\(", formula, re.I)):
                        raise ValueError("Sheets external/image cells need separate source/asset support")
                    if cell:
                        texts[f"{base}/cells/{r}/{c}"] = json.dumps(
                            cell, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for chart in sheet.get("charts", []):
            ident = chart["chartId"]
            if type(ident) is not int or ident < 0 or ident in chart_ids:
                raise ValueError("Sheets duplicate/invalid chartId")
            chart_ids.add(ident)
            if not allow_links:
                raise ValueError("Sheets charts require complete chart/source inventory")
            pointer = f"{base}/@chartId/{ident}/spec"
            spec = chart["spec"]
            if not isinstance(spec, dict):
                raise ValueError("Sheets chart spec must be an object")
            for key in ("title", "subtitle", "altText"):
                if key in spec:
                    texts[pointer + "/" + key] = spec[key]
            links[pointer] = digest(spec)
    if any(not isinstance(v, str) for v in texts.values()):
        raise ValueError("Sheets title/cell inventory must use native strings")
    return texts, {}, links


def sheets_slot(pointer, value):
    if "/cells/" not in pointer:
        return neutral_slot(value)
    cell = json.loads(value)
    if not isinstance(cell, dict):
        return False
    entered = cell.get("userEnteredValue", {})
    if set(entered) != {"stringValue"} or not neutral_slot(entered["stringValue"]):
        return False
    return (cell.get("effectiveValue", entered) == entered
            and cell.get("formattedValue", entered["stringValue"]) == entered["stringValue"]
            and not ({"note", "hyperlink", "textFormatRuns", "chipRuns", "pivotTable"} & cell.keys()))


def sheets_placeholders(pointer, value):
    def contains(item):
        if isinstance(item, dict):
            return any(contains(v) for v in item.values())
        if isinstance(item, list):
            return any(contains(v) for v in item)
        return isinstance(item, str) and ("{{" in item or "}}" in item)
    return contains(json.loads(value) if "/cells/" in pointer else value)


def sheets_read_revision(raw, current, template, run, base):
    """Sheets has no revisionId: bracket a complete read with native Drive File.version."""
    read = current["sheets_read"]
    if (read["request"] != {"includeGridData": True} or read["request"]["includeGridData"] is not True
            or read["unreadable"] != [] or read["unsupported_objects"] != []
            or not isinstance(read["supplemental_review_source"], str) or not read["supplemental_review_source"]):
        raise ValueError("Sheets partial read or unreviewed/unsupported supplemental objects")
    ids = [s["properties"]["sheetId"] for s in raw["sheets"]]
    declared = read["sheet_ids"]
    if (not isinstance(declared, list) or any(type(i) is not int for i in declared)
            or len(set(ids)) != len(ids) or len(declared) != len(ids) or set(declared) != set(ids)):
        raise ValueError("Sheets complete worksheet coverage missing")
    before_at, after_at = (datetime.fromisoformat(read[k]) for k in ("before_at", "after_at"))
    started, observed = (datetime.fromisoformat(run["started_at"]), datetime.fromisoformat(current["checked_at"]))
    if (before_at.tzinfo is None or after_at.tzinfo is None
            or not started <= before_at <= after_at <= observed):
        raise ValueError("Sheets Drive reads do not bracket this run's native snapshot")
    for name in ("drive_before_path", "drive_after_path"):
        metadata = native_document(read_json(base, read[name]))
        if (any(metadata[k] != current[k] for k in ("id", "mimeType", "trashed", "parents", "owners"))
                or not isinstance(metadata["version"], str)
                or not re.fullmatch(r"[0-9]+", metadata["version"])
                or metadata["version"] != template["revision"]):
            raise ValueError("Sheets Drive identity/version changed; reapproval required")
    return template["revision"]



def inventory(value, path="", allow_links=False, stable_images=False):
    """Native text/assets; Slides objectId locators stay stable when pages are inserted."""
    if not path and isinstance(value, dict) and "spreadsheetId" in value:
        return sheets_inventory(value, allow_links)

    texts, images, links = {}, {}, {}
    if isinstance(value, dict):
        if "objectId" in value:
            path = "/@objectId/" + value["objectId"]
        for key, item in value.items():
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key == "textRun" and isinstance(item, dict) and "content" in item:
                texts[pointer + "/content"] = item["content"]
            if key == "renderedText" and isinstance(item, str):
                texts[pointer] = item
            if key in {"sheetsChart", "linkedContentReference"}:
                if not allow_links:
                    raise ValueError("linked monthly data is not neutral; use a template placeholder")
                links[pointer] = digest(stable_native(item))
            if key in {"image", "embeddedObject"} and isinstance(item, dict):
                images[pointer] = digest(stable_native({k: v for k, v in item.items() if k != "sourceUrl"}
                                                      if stable_images else item))
            more_text, more_images, more_links = inventory(item, pointer, allow_links, stable_images)
            if texts.keys() & more_text.keys() or images.keys() & more_images.keys() or links.keys() & more_links.keys():
                raise ValueError("duplicate native inventory locator")
            texts.update(more_text)
            images.update(more_images)
            links.update(more_links)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            more_text, more_images, more_links = inventory(item, path + "/" + str(index), allow_links, stable_images)
            if texts.keys() & more_text.keys() or images.keys() & more_images.keys() or links.keys() & more_links.keys():
                raise ValueError("duplicate native inventory locator")
            texts.update(more_text)
            images.update(more_images)
            links.update(more_links)
    return texts, images, links


def evidence_path(base, relative):
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("evidence path escapes its run/registry directory")
    return path


def read_json(base, relative):
    return json.loads(evidence_path(base, relative).read_text(encoding="utf-8"))


def image_hashes(base, paths):
    return {locator: hashlib.sha256(evidence_path(base, path).read_bytes()).hexdigest()
            for locator, path in paths.items()}


def frozen_history(template, base, raw, client, new_month, collection_months, actual_image_hashes,
                   *, append_month=True):
    """Validate immutable accepted months, reused for pre-copy and filled-output readback."""
    if not isinstance(collection_months, list) or any(
            not isinstance(m, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", m)
            for m in collection_months):
        raise ValueError("collection months must be an explicit calendar-month list")
    raw = native_document(raw)
    texts, images, _ = inventory(raw, allow_links=True)
    _, properties, _ = inventory(raw, allow_links=True, stable_images=True)
    frozen_text, frozen_images, months = {}, {}, []
    for entry in template["frozen_months"]:
        month = entry["month"]
        if (not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month) or month in months
                or (append_month and month >= new_month)):
            raise ValueError("duplicate/invalid frozen month or requested month already frozen")
        snapshot = read_json(base, entry["snapshot_path"])
        if (digest(snapshot) != entry["sha256"] or snapshot["month"] != month
                or snapshot["client_id"] != client or not snapshot["accepted_report_id"]
                or not snapshot["acceptance_source"] or not snapshot["source_hashes"]
                or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in snapshot["source_hashes"].values())):
            raise ValueError("unaccepted/changed frozen snapshot or missing source hashes")
        if not snapshot["texts"] and not snapshot["images"]:
            raise ValueError("empty frozen-month inventory")
        if (frozen_text.keys() & snapshot["texts"].keys()
                or frozen_images.keys() & snapshot["images"].keys()):
            raise ValueError("overlapping frozen month zones")
        if (any(texts.get(p) != v for p, v in snapshot["texts"].items())
                or any(properties.get(p) != v["properties_sha256"]
                       or actual_image_hashes.get(p) != v["file_sha256"]
                       for p, v in snapshot["images"].items())):
            raise ValueError("accepted historical text/image changed or removed")
        frozen_text.update(snapshot["texts"])
        # Signed content URLs may differ between copies; properties + actual image files are the oracle.
        frozen_images.update({p: images[p] for p in snapshot["images"]})
        months.append(month)
    if not months or set(months) & set(collection_months):
        raise ValueError("missing frozen months or recollection of accepted history requested")
    return frozen_text, frozen_images, months


def check(registry_path, preflight_path, required_roles):
    issues, verified = [], []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        run = json.loads(preflight_path.read_text(encoding="utf-8"))
        roles = set(required_roles)
        if not roles or not roles <= NATIVE_MIME.keys() or len(roles) != len(required_roles):
            raise ValueError("required roles must be nonempty, unique and supported")
        if registry["schema_version"] != 3 or run["schema_version"] != 3:
            raise ValueError("unsupported schema")
        if not registry["client_id"] or registry["client_id"] != run["client_id"]:
            raise ValueError("client mismatch")
        if not registry["reports_folder_id"] or not registry["account_email"]:
            raise ValueError("missing registry folder/account")
        if set(registry["required_roles"]) != roles:
            raise ValueError("registry does not cover the profile-required roles")
        if run["account_email"] != registry["account_email"] or not run["link_id"]:
            raise ValueError("selected Google account mismatch")
        started = datetime.fromisoformat(run["started_at"])
        if started.tzinfo is None or not run["run_id"]:
            raise ValueError("missing run identity/timezone")
        templates = registry["templates"]
        if (len(templates) != len(roles) or {t["role"] for t in templates} != roles
                or len({t["id"] for t in templates}) != len(roles)):
            raise ValueError("missing, incomplete or duplicate template set")
        files = run["files"]
        if len(files) != len(roles) or len({f["id"] for f in files}) != len(roles):
            raise ValueError("missing or duplicate current template reads")
        selected = next(t for t in templates if t["role"] == run["selected_role"])
        if run["copy_source_id"] != selected["id"]:
            raise ValueError("copy source is not the registered template/base")
        excluded = set(registry["reference_and_report_ids"])
        for template in templates:
            try:
                role, ident = template["role"], template["id"]
                if not ident or ident in excluded:
                    raise ValueError("reference/past report used as template")
                current = next(f for f in files if f["id"] == ident)
                observed = datetime.fromisoformat(current["checked_at"])
                if (observed.tzinfo is None or observed < started
                        or observed > datetime.now(started.tzinfo)
                        or current["run_id"] != run["run_id"]
                        or current["link_id"] != run["link_id"]):
                    raise ValueError("cached read or wrong connection/run")
                if current["mimeType"] != NATIVE_MIME[role] or current["trashed"] is not False:
                    raise ValueError("wrong native MIME or deleted file")
                if (registry["reports_folder_id"] not in current["parents"]
                        or registry["account_email"] not in
                        [o["emailAddress"] for o in current["owners"]]):
                    raise ValueError("wrong owner or template folder")
                raw = native_document(read_json(preflight_path.parent, current["native_path"]))
                if not isinstance(raw, dict):
                    raise ValueError("native read must be an object")
                sheets = role in SHEETS_MIME
                raw_id = raw.get("spreadsheetId") if sheets else raw.get("documentId") if role == "docs" else raw.get("presentationId")
                revision = sheets_read_revision(raw, current, template, run, preflight_path.parent) if sheets else raw["revisionId"]
                if (raw_id != ident or not isinstance(template["revision"], str) or not template["revision"]
                        or revision != template["revision"]):
                    raise ValueError("native ID/revision changed; reapproval required")
                if native_digest(raw) != template["approved_sha256"]:
                    raise ValueError("native content differs from approved snapshot")
                approval = read_json(registry_path.parent, template["approval_path"])
                if (approval["result"] != "APPROVED" or not approval["owner_decision_source"]
                        or (approval["id"], approval["revision"], approval["approved_sha256"])
                        != (ident, template["revision"], template["approved_sha256"])):
                    raise ValueError("missing exact template/base approval")
                cumulative = role in CUMULATIVE_ROLES
                expected_kind = "cumulative_base" if cumulative else "neutral_template"
                if template["semantic_kind"] != expected_kind:
                    raise ValueError("wrong role semantics")
                texts, images, links = inventory(raw, allow_links=cumulative or sheets)
                slots, static = template["text_slots"], template["static_text"]
                if (not slots and not cumulative) or set(slots) & set(static):
                    raise ValueError("missing/overlapping text slot mapping")
                if any(not isinstance(s, str) for s in static.values()):
                    raise ValueError("static text must be native text strings")
                if any(sheets_placeholders(p, s) if sheets else "{{" in s or "}}" in s
                       for p, s in static.items()):
                    raise ValueError("embedded placeholders must be mapped as text slots, not static")
                if any(not (sheets_slot(p, s) if sheets else neutral_slot(s)) for p, s in slots.items()):
                    raise ValueError("monthly value/date in a neutral slot")
                actual_hashes = image_hashes(preflight_path.parent, current["image_paths"])
                expected_images = {}
                mutable_images = template.get("mutable_images", {})
                if not isinstance(mutable_images, dict):
                    raise ValueError("mutable image mapping must be an object")
                if mutable_images and not cumulative:
                    raise ValueError("mutable images apply only to a cumulative base")
                if template["allowed_images"].keys() & mutable_images.keys():
                    raise ValueError("mutable/static image zones overlap")
                for pointer, spec in {**template["allowed_images"], **mutable_images}.items():
                    if (images.get(pointer) != spec["properties_sha256"]
                            or actual_hashes.get(pointer) != spec["file_sha256"]):
                        raise ValueError("template image properties/file changed or missing")
                    expected_images[pointer] = spec["properties_sha256"]
                expected_text = {**static, **slots}
                if cumulative:
                    if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", run["new_month"]):
                        raise ValueError("invalid new month")
                    frozen_text, frozen_images, months = frozen_history(
                        template, registry_path.parent, raw, registry["client_id"],
                        run["new_month"], run["collection_months"],
                        actual_hashes, append_month=run["selected_role"] in CUMULATIVE_ROLES)
                    mutable = template["mutable_text"]
                    if (expected_text.keys() & mutable.keys() or expected_text.keys() & frozen_text.keys()
                            or mutable.keys() & frozen_text.keys() or expected_images.keys() & frozen_images.keys()):
                        raise ValueError("mutable/static/frozen zones overlap")
                    if not mutable or any(not isinstance(s, str) for s in mutable.values()):
                        raise ValueError("missing mutable cumulative blocks")
                    expected_text = {**expected_text, **mutable, **frozen_text}
                    expected_images = {**expected_images, **frozen_images}
                if cumulative or sheets:
                    if set(links) != set(template["linked_data"]) or set(links) != set(current["linked_data_paths"]):
                        raise ValueError("missing linked cumulative chart/source inventory")
                    for pointer, spec in template["linked_data"].items():
                        data = read_json(preflight_path.parent, current["linked_data_paths"][pointer])
                        if links[pointer] != spec["object_sha256"] or digest(data) != spec["source_sha256"]:
                            raise ValueError("linked cumulative chart/source changed")
                if texts != expected_text or images != expected_images:
                    raise ValueError("unmapped text/image or stale monthly material")
                verified.append({"role": role, "id": ident, "revision": template["revision"],
                                 "texts": len(texts), "images": len(images),
                                 "frozen_months": months if cumulative else []})
            except (OSError, KeyError, ValueError, TypeError, StopIteration) as error:
                issues.append(f"{template.get('role', '?')}: {error}")
    except (OSError, KeyError, ValueError, TypeError, StopIteration) as error:
        issues.append(str(error) or "selected template/current read missing")
    return {"status": "BLOCKED" if issues else "PASS_LIMITED", "issues": issues,
            "verified": verified,
            "limitation": "Offline identity/content guard. Evidence authenticity, human approval, "
                          "complete connector export and visual neutrality require separate review; "
                          "no Google copy or live permission probe is performed."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("preflight", type=Path)
    parser.add_argument("--roles", nargs="+", required=True, choices=NATIVE_MIME)
    parser.add_argument("--output-native", type=Path,
                        help="Additionally compare filled cumulative output to accepted frozen zones")
    parser.add_argument("--output-image-manifest", type=Path,
                        help="JSON locator -> relative native image file path from the filled output")
    args = parser.parse_args()
    result = check(args.registry, args.preflight, args.roles)
    if not result["issues"] and args.output_native:
        try:
            registry = json.loads(args.registry.read_text(encoding="utf-8")); run = json.loads(args.preflight.read_text(encoding="utf-8"))
            if run["selected_role"] not in CUMULATIVE_ROLES:
                raise ValueError("output history check applies only to a cumulative report")
            if args.output_image_manifest is None:
                raise ValueError("filled output needs its actual image manifest")
            template = next(t for t in registry["templates"] if t["role"] == run["selected_role"])
            frozen_history(template, args.registry.parent, json.loads(args.output_native.read_text(encoding="utf-8")),
                           registry["client_id"], run["new_month"], run["collection_months"],
                           image_hashes(args.output_image_manifest.parent,
                                        json.loads(args.output_image_manifest.read_text(encoding="utf-8"))))
            result["output_history"] = "PASS_LIMITED"
        except (OSError, KeyError, ValueError, TypeError, StopIteration) as error:
            result["issues"].append(str(error)); result["status"] = "BLOCKED"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["issues"]))
