"""Check native-copy readbacks; supplied receipts are evidence, never permissions."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from check_report_templates import digest, native_document, read_json, sheets_inventory


def cell_inventory(raw):
    document = deepcopy(native_document(raw))
    for sheet in document["sheets"]:
        sheet.pop("charts", None)
    texts, _, _ = sheets_inventory(document, allow_links=True)
    texts.pop("/properties/title")  # A copy intentionally has its own filename.
    for pointer, value in texts.items():
        if "/cells/" in pointer and "errorValue" in json.loads(value).get("effectiveValue", {}):
            raise ValueError("formula error: " + pointer)
    return texts


def charts(raw):
    result = {}
    for sheet in raw["sheets"]:
        for chart in sheet.get("charts", []):
            key = f'{sheet["properties"]["sheetId"]}/{chart["chartId"]}'
            if not isinstance(chart["spec"], dict):
                raise ValueError("invalid chart specification")
            title = chart["spec"].get("title", "")
            if key in result or type(chart["chartId"]) is not int or not isinstance(title, str):
                raise ValueError("invalid/duplicate chart inventory")
            result[key] = title
    return result


def check(plan_path, receipt_path):
    issues = []
    counts = {}
    try:
        plan = json.loads(plan_path.read_text())
        run = json.loads(receipt_path.read_text())
        base = receipt_path.parent
        if plan["schema_version"] != 1 or run["schema_version"] != 1:
            raise ValueError("unsupported copy-check schema")
        if not plan["approval_source"] or run["plan_sha256"] != digest(plan):
            raise ValueError("missing approval or changed check plan")
        profile = native_document(read_json(base, run["profile_path"]))
        if profile["email"] != plan["account_email"]:
            raise ValueError("selected account mismatch")
        source = native_document(read_json(base, run["source_path"]))
        output = native_document(read_json(base, run["output_path"]))
        source_id, output_id = source["spreadsheetId"], output["spreadsheetId"]
        copied = native_document(read_json(base, run["copy_action_path"]))
        if (source_id != plan["source_id"] or not output_id or output_id == source_id
                or copied.get("success") is not True or copied["id"] != output_id):
            raise ValueError("copy identity mismatch; never write the source")
        for key, ident in (("source_drive_path", source_id), ("output_drive_path", output_id)):
            metadata = native_document(read_json(base, run[key]))
            owners = [p.get("emailAddress") for p in metadata.get("permissions", [])
                      if p.get("role") == "owner"]
            if (metadata["id"] != ident or metadata["mime_type"] != "application/vnd.google-apps.spreadsheet"
                    or plan["folder_id"] not in metadata["parent_ids"]
                    or plan["account_email"] not in owners):
                raise ValueError("native file owner/folder mismatch")
        properties = lambda doc: [s["properties"] for s in doc["sheets"]]
        if properties(source) != properties(output):
            raise ValueError("worksheet structure/order/hidden state changed")
        if any(output["properties"].get(k) != v for k, v in source["properties"].items() if k != "title"):
            raise ValueError("spreadsheet properties changed")
        original, actual = cell_inventory(source), cell_inventory(output)
        if digest(original) != plan["source_cells_sha256"]:
            raise ValueError("approved source cells changed")
        if actual != original:
            different = sorted(k for k in actual.keys() | original.keys() if actual.get(k) != original.get(k))
            raise ValueError("unexpected cell/formula/format change: " + ", ".join(different[:8]))
        if digest(charts(source)) != plan["source_charts_sha256"]:
            raise ValueError("approved source chart inventory changed")
        if charts(source) != charts(output):
            raise ValueError("chart inventory changed")
        # Full source ChartSpec may be unavailable: require recorded setup/source-range review.
        required = {"coverage", "charts", "visual", "calculations", "history"}
        if set(run["reviews"]) != required:
            raise ValueError("incomplete direct report checks")
        for name in sorted(required):
            review = run["reviews"][name]
            path = base / review["path"]
            # Resolve with the shared path boundary before touching a supplied file.
            read_json(base, review["path"])
            if (review["result"] != "PASS" or not review["observation"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != review["sha256"]):
                raise ValueError("missing/changed review evidence: " + name)
        counts = {"worksheets": len(source["sheets"]), "cell_records": sum("/cells/" in k for k in actual),
                  "charts": len(charts(output)), "source_id": source_id, "output_id": output_id}
    except (OSError, KeyError, ValueError, TypeError) as error:
        issues.append(str(error))
    return {"status": "BLOCKED" if issues else "PASS_LIMITED", "issues": issues, **counts,
            "limitation": "Compares supplied native cell/structure readbacks and review receipts. "
                          "No File.version/full source ChartSpec equality, live permission, evidence authenticity, "
                          "independent review or employee-device support is proved."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    result = check(args.plan, args.receipt)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(result["status"] == "BLOCKED")
