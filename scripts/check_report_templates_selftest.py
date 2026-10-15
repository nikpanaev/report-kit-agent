"""Independent failure cases for the offline pre-copy guard; temporary fixtures only."""
from copy import deepcopy
import json
import hashlib
import base64
import subprocess
import sys
from pathlib import Path
import tempfile

from check_report_templates import check, digest, native_digest, stable_native, neutral_slot, inventory, frozen_history, MIME


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    registry = {"schema_version": 3, "client_id": "fixture", "account_email": "owner@example.test",
                "reports_folder_id": "reports", "required_roles": list(MIME),
                "reference_and_report_ids": ["july-report", "reference"], "templates": []}
    run = {"schema_version": 3, "client_id": "fixture", "account_email": "owner@example.test",
           "link_id": "connection", "run_id": "new-run", "started_at": "2026-10-08T09:00:00+03:00",
           "selected_role": "docs", "copy_source_id": "template-docs", "files": [],
           "new_month": "2026-09", "collection_months": ["2026-09"]}
    native = {}
    image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    (root / "accepted-june.png").write_bytes(image)
    file_hash = hashlib.sha256(image).hexdigest()
    for role in MIME:
        ident = "template-" + role
        raw = {"documentId" if role == "docs" else "presentationId": ident, "revisionId": "r1",
               "body": {"content": [{"textRun": {"content": "Учебный клиент\n"}},
                                     {"textRun": {"content": "Отчёт за {{MONTH}} — {{PERIOD}}\n"}},
                                     {"textRun": {"content": "—" if role == "cumulative" else "{{VIEWS}}"}},
                                     {"image": {"contentUrl": "fixture-logo"}}]}}
        if role == "cumulative":
            raw["body"]["content"][1]["textRun"]["content"] = "Июнь–Июль 2026"
            raw["slides"] = [{"objectId": "june-page", "pageElements": [
                {"objectId": "june-value", "textRun": {"content": "Июнь: 1 234 просмотров"}},
                {"objectId": "june-post", "image": {"contentUrl": "accepted-june-post.png"}}]}]
        if role == "docs":
            raw["body"]["content"][3] = {"embeddedObject": {
                "imageProperties": {"contentUri": "accepted-docs-signed-uri",
                                    "sourceUri": "accepted-docs-source"}}}
        texts, images, links = inventory(raw)
        slots = {p: s for p, s in texts.items() if "{{" in s or s.strip() == "—"}
        entry = {"role": role, "semantic_kind": "cumulative_base" if role == "cumulative" else "neutral_template", "id": ident, "revision": "r1", "approved_sha256": native_digest(raw),
                 "text_slots": slots, "static_text": {p: s for p, s in texts.items() if p not in slots},
                 "allowed_images": {p: {"properties_sha256": v, "file_sha256": file_hash} for p, v in images.items()}, "approval_path": role + "-approval.json"}
        if role == "cumulative":
            mutable_pointer = "/body/content/1/textRun/content"
            entry["static_text"].pop(mutable_pointer)
            entry["mutable_text"] = {mutable_pointer: "Июнь–Июль 2026"}
            frozen_text = {p: v for p, v in texts.items() if p.startswith("/@objectId/june-")}
            frozen_images = {p: v for p, v in images.items() if p.startswith("/@objectId/june-")}
            for pointer in frozen_text: entry["static_text"].pop(pointer)
            for pointer in frozen_images: entry["allowed_images"].pop(pointer)
            snapshot = {"client_id": "fixture", "month": "2026-06", "accepted_report_id": "accepted-june",
                        "acceptance_source": "fixture-direct-owner-acceptance", "source_hashes": {"posts": "a" * 64},
                        "texts": frozen_text, "images": {p: {"properties_sha256": inventory(raw, stable_images=True)[1][p], "file_sha256": file_hash}
                                                         for p in frozen_images}}
            (root / "june-frozen.json").write_text(json.dumps(snapshot), encoding="utf-8")
            entry["frozen_months"] = [{"month": "2026-06", "snapshot_path": "june-frozen.json", "sha256": digest(snapshot)}]
            entry["linked_data"] = {}
        approval = {"result": "APPROVED", "owner_decision_source": "fixture-owner-decision",
                    "id": ident, "revision": "r1", "approved_sha256": native_digest(raw)}
        (root / entry["approval_path"]).write_text(json.dumps(approval), encoding="utf-8")
        registry["templates"].append(entry)
        run["files"].append({"id": ident, "mimeType": MIME[role], "trashed": False,
                             "parents": ["reports"], "owners": [{"emailAddress": "owner@example.test"}],
                             "checked_at": "2026-10-08T09:01:00+03:00", "run_id": "new-run",
                             "link_id": "connection", "native_path": role + ".json", "linked_data_paths": {}, "image_paths": {p: "accepted-june.png" for p in images}})
        native[role] = raw

    def execute(reg=registry, pre=run, snapshots=native):
        (root / "registry.json").write_text(json.dumps(reg), encoding="utf-8")
        (root / "preflight.json").write_text(json.dumps(pre), encoding="utf-8")
        for role, raw in snapshots.items():
            (root / (role + ".json")).write_text(json.dumps(raw), encoding="utf-8")
        return check(root / "registry.json", root / "preflight.json", list(MIME))

    assert execute()["status"] == "PASS_LIMITED"
    assert neutral_slot("Отчёт за {{MONTH}} — {{PERIOD}}\n")
    assert not neutral_slot("Отчёт за июль 2026")
    assert not neutral_slot("Отчёт {{MONTH}} {{broken}}")
    refreshed = deepcopy(native)
    def refresh_urls(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "contentUrl": value[key] = "new-signed-url"
                else: refresh_urls(item)
        elif isinstance(value, list):
            for item in value: refresh_urls(item)
    refresh_urls(refreshed)
    refreshed["docs"]["body"]["content"][3]["embeddedObject"]["imageProperties"]["contentUri"] = "fresh-docs-signed-uri"
    # No registry/approval hash regeneration: a second read with only signed URL drift passes.
    assert execute(snapshots=refreshed)["status"] == "PASS_LIMITED"
    enveloped = {role: {"isError": False, "structuredContent": raw,
                       "content": [{"type": "text", "text": json.dumps(raw)}]}
                 for role, raw in refreshed.items()}
    assert execute(snapshots=enveloped)["status"] == "PASS_LIMITED"
    cases = []

    def reject(name, reg=registry, pre=run, snapshots=native):
        result = execute(reg, pre, snapshots)
        assert result["status"] == "BLOCKED" and result["issues"], name
        cases.append(name)

    # Historical images/numbers are valid for cumulative only, and survive new page insertion.
    cumulative = registry["templates"][1]
    candidate = deepcopy(native["cumulative"])
    candidate["body"]["content"][1]["textRun"]["content"] = "Июнь–Сентябрь 2026"
    candidate["slides"].insert(0, {"objectId": "september-page", "pageElements": [
        {"objectId": "september-value", "textRun": {"content": "Новый сентябрь"}}]})
    actual_hashes = {p: file_hash for p in json.loads((root / "june-frozen.json").read_text(encoding="utf-8"))["images"]}
    candidate["slides"][1]["pageElements"][1]["image"]["contentUrl"] = "new-copy-signed-url"
    assert frozen_history(cumulative, root, candidate, "fixture", "2026-09", ["2026-09"], actual_hashes)[2] == ["2026-06"]
    output_run = deepcopy(run); output_run["selected_role"] = "cumulative"
    output_run["copy_source_id"] = "template-cumulative"
    assert execute(pre=output_run)["status"] == "PASS_LIMITED"
    (root / "output.json").write_text(json.dumps(candidate), encoding="utf-8")
    (root / "output-images.json").write_text(json.dumps({p: "accepted-june.png" for p in actual_hashes}), encoding="utf-8")
    command = [sys.executable, str(Path(__file__).with_name("check_report_templates.py")),
               str(root / "registry.json"), str(root / "preflight.json"), "--roles", *MIME,
               "--output-native", str(root / "output.json"), "--output-image-manifest", str(root / "output-images.json")]
    process = subprocess.run(command, capture_output=True, text=True)
    assert process.returncode == 0 and json.loads(process.stdout)["output_history"] == "PASS_LIMITED", process.stdout
    assert subprocess.run(command[:-2], capture_output=True).returncode == 1

    def history_reject(name, raw=candidate, template=cumulative, collection=None, hashes=actual_hashes):
        try:
            frozen_history(template, root, raw, "fixture", "2026-09",
                           ["2026-09"] if collection is None else collection, hashes)
        except (ValueError, KeyError, TypeError) as error:
            if name.startswith("historical") and "recollection" not in name:
                assert "accepted historical text/image changed or removed" in str(error), (name, str(error))
            if "recollection" in name:
                assert "recollection" in str(error), str(error)
            cases.append(name)
        else:
            raise AssertionError(name)

    bad = deepcopy(candidate); bad["slides"][1]["pageElements"][0]["textRun"]["content"] = "Июнь: 999 просмотров"
    history_reject("historical value changed in filled output", raw=bad)
    history_reject("historical image file changed in filled output", hashes={p: "b" * 64 for p in actual_hashes})
    bad = deepcopy(candidate); bad["slides"][1]["pageElements"][1]["image"]["cropProperties"] = {"leftOffset": 0.5}
    history_reject("historical image properties changed in filled output", raw=bad)
    bad = deepcopy(candidate); bad["slides"].pop(1)
    history_reject("historical slide removed", raw=bad)
    history_reject("historical month recollection requested", collection=["2026-06", "2026-09"])
    history_reject("malformed historical collection declaration", collection="2026-09")
    bad = deepcopy(cumulative); bad["frozen_months"] = []
    history_reject("missing frozen month ledger", template=bad)
    bad = deepcopy(cumulative); bad["frozen_months"] *= 2
    history_reject("duplicate frozen month", template=bad)
    bad = deepcopy(cumulative); bad["frozen_months"][0]["sha256"] = "b" * 64
    history_reject("frozen snapshot hash changed", template=bad)
    bad = deepcopy(run); bad["new_month"] = "2026-06"
    bad["selected_role"] = "cumulative"; bad["copy_source_id"] = "template-cumulative"
    reject("requested month already accepted", pre=bad)
    bad = deepcopy(registry); bad["templates"][1]["semantic_kind"] = "neutral_template"
    reject("cumulative treated as neutral monthly template", reg=bad)
    bad = deepcopy(registry)
    frozen_pointer = next(iter(json.loads((root / "june-frozen.json").read_text(encoding="utf-8"))["texts"]))
    bad["templates"][1]["mutable_text"][frozen_pointer] = "Июнь: 1 234 просмотров"
    reject("historical zone declared mutable", reg=bad)

    # All roles are still checked when the monthly period is already in the accepted base.
    reused = deepcopy(run); reused["new_month"] = "2026-06"; reused["collection_months"] = []
    for role in ("docs", "monthly"):
        reused["selected_role"] = role; reused["copy_source_id"] = "template-" + role
        assert execute(pre=reused)["status"] == "PASS_LIMITED"
    bad = deepcopy(reused); bad["collection_months"] = ["2026-06"]
    reject("monthly cannot recollect accepted month", pre=bad)
    bad = deepcopy(registry); bad["templates"][1]["frozen_months"][0]["sha256"] = "b" * 64
    reject("monthly still checks cumulative history", reg=bad, pre=reused)
    bad = deepcopy(registry); bad["templates"] = [t for t in bad["templates"] if t["role"] != "cumulative"]
    reject("monthly still requires cumulative role", reg=bad, pre=reused)

    # Dated aggregate media has its own exact pre-copy mapping, never a decor exemption.
    reg = deepcopy(registry); entry = reg["templates"][1]
    aggregate_pointer = "/body/content/3/image"
    entry["mutable_images"] = {aggregate_pointer: entry["allowed_images"].pop(aggregate_pointer)}
    assert execute(reg=reg)["status"] == "PASS_LIMITED"
    for malformed in (None, []):
        bad = deepcopy(reg); bad["templates"][1]["mutable_images"] = malformed
        reject("malformed mutable image mapping " + repr(malformed), reg=bad)
    bad = deepcopy(reg); bad["templates"][1]["allowed_images"][aggregate_pointer] = entry["mutable_images"][aggregate_pointer]
    reject("mutable image overlaps decor", reg=bad)
    bad = deepcopy(reg); pointer = next(iter(json.loads((root / "june-frozen.json").read_text(encoding="utf-8"))["images"]))
    bad["templates"][1]["mutable_images"][pointer] = {"properties_sha256": inventory(native["cumulative"])[1][pointer], "file_sha256": file_hash}
    reject("historical image declared mutable", reg=bad)
    bad = deepcopy(reg); bad["templates"][1]["mutable_images"][aggregate_pointer]["file_sha256"] = "b" * 64
    reject("mutable image current bytes changed", reg=bad)
    bad = deepcopy(reg); bad["templates"][1]["mutable_images"][aggregate_pointer]["properties_sha256"] = "b" * 64
    reject("mutable image current properties changed", reg=bad)
    bad = deepcopy(registry); bad["templates"][0]["mutable_images"] = {aggregate_pointer: entry["mutable_images"][aggregate_pointer]}
    reject("Docs cannot exempt dated media as mutable", reg=bad)

    # Promotion freezes September, then September monthly reuses it without collecting it again.
    promoted_native = deepcopy(native)
    september = {"objectId": "september-page", "pageElements": [
        {"objectId": "september-value", "textRun": {"content": "Сентябрь: 100 просмотров"}},
        {"objectId": "september-post", "image": {"sourceUrl": "fixture-september-post"}}]}
    promoted_native["cumulative"]["slides"].append(september)
    st, si, _ = inventory(september, stable_images=True)
    september_snapshot = {"client_id": "fixture", "month": "2026-09",
                          "accepted_report_id": "fixture-accepted-september",
                          "acceptance_source": "fixture-direct-owner-acceptance",
                          "source_hashes": {"september": "c" * 64}, "texts": st,
                          "images": {p: {"properties_sha256": h, "file_sha256": file_hash}
                                     for p, h in si.items()}}
    (root / "september-frozen.json").write_text(json.dumps(september_snapshot), encoding="utf-8")
    promoted = deepcopy(reg); promoted_entry = promoted["templates"][1]
    promoted_entry["frozen_months"].append({"month": "2026-09", "snapshot_path": "september-frozen.json",
                                          "sha256": digest(september_snapshot)})
    promoted_entry["approved_sha256"] = native_digest(promoted_native["cumulative"])
    promoted_run = deepcopy(run); promoted_run.update(selected_role="monthly", copy_source_id="template-monthly",
                                                     collection_months=[])
    promoted_run["files"][1]["image_paths"].update({p: "accepted-june.png" for p in si})
    approval_path = root / promoted_entry["approval_path"]; saved_approval = approval_path.read_text(encoding="utf-8")
    approval = json.loads(saved_approval); approval["approved_sha256"] = promoted_entry["approved_sha256"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    assert execute(promoted, promoted_run, promoted_native)["status"] == "PASS_LIMITED"
    bad = deepcopy(promoted_run); bad["selected_role"] = "cumulative"; bad["copy_source_id"] = "template-cumulative"
    reject("cannot append accepted September again", reg=promoted, pre=bad, snapshots=promoted_native)
    bad = deepcopy(promoted_run); bad["collection_months"] = ["2026-09"]
    reject("cannot recollect September for monthly", reg=promoted, pre=bad, snapshots=promoted_native)
    bad = deepcopy(promoted_native); bad["cumulative"]["slides"][-1]["pageElements"][0]["textRun"]["content"] = "Сентябрь: 999 просмотров"
    try:
        frozen_history(promoted_entry, root, bad["cumulative"], "fixture", "2026-09", [],
                       {**actual_hashes, **{p: file_hash for p in si}}, append_month=False)
    except ValueError as error:
        assert "accepted historical" in str(error); cases.append("monthly reuse protects September values")
    else:
        raise AssertionError("monthly reused changed September values")
    approval_path.write_text(saved_approval, encoding="utf-8")

    # An approved cumulative linked chart needs its exact frozen source read; no LiveDune fetch.
    linked_native = deepcopy(native); linked_native["cumulative"]["sheetsChart"] = {
        "spreadsheetId": "accepted-source", "contentUrl": "chart-signed-url"}
    reg = deepcopy(registry); linked_entry = reg["templates"][1]
    _, _, linked_inventory = inventory(linked_native["cumulative"], allow_links=True)
    pointer = next(iter(linked_inventory)); data = {"2026-06": {"views": 1234}}
    (root / "linked-data.json").write_text(json.dumps(data), encoding="utf-8")
    linked_entry["linked_data"] = {pointer: {"object_sha256": linked_inventory[pointer], "source_sha256": digest(data)}}
    linked_entry["approved_sha256"] = native_digest(linked_native["cumulative"])
    pre = deepcopy(run); pre["files"][1]["linked_data_paths"] = {pointer: "linked-data.json"}
    approval_path = root / linked_entry["approval_path"]; original = approval_path.read_text(encoding="utf-8")
    approval = json.loads(original); approval["approved_sha256"] = linked_entry["approved_sha256"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    assert execute(reg, pre, linked_native)["status"] == "PASS_LIMITED"
    linked_refresh = deepcopy(linked_native); linked_refresh["cumulative"]["sheetsChart"]["contentUrl"] = "new-chart-signed-url"
    assert execute(reg, pre, linked_refresh)["status"] == "PASS_LIMITED"
    (root / "linked-data.json").write_text(json.dumps({"2026-06": {"views": 999}}), encoding="utf-8")
    reject("historical linked chart data changed", reg=reg, pre=pre, snapshots=linked_native)
    approval_path.write_text(original, encoding="utf-8")

    for count in (0, 1, 2):
        bad = deepcopy(registry); bad["templates"] = bad["templates"][:count]
        reject(f"incomplete set {count}/3", reg=bad)
    bad = deepcopy(registry); bad["required_roles"] = ["docs"]
    reject("self-declared smaller set", reg=bad)
    bad = deepcopy(registry); bad["schema_version"] = 2
    reject("old raw-hash registry schema", reg=bad)
    bad = deepcopy(registry); pointer = next(iter(bad["templates"][0]["text_slots"]))
    bad["templates"][0]["static_text"][pointer] = bad["templates"][0]["text_slots"].pop(pointer)
    reject("mixed embedded token run declared static", reg=bad)
    bad = deepcopy(enveloped); bad["docs"]["isError"] = True
    reject("failed read envelope", snapshots=bad)
    bad = deepcopy(native); bad["docs"]["body"]["content"][0]["textRun"]["content"] = "Другой клиент"
    reject("actual text mutation", snapshots=bad)
    bad = deepcopy(native); bad["docs"]["body"]["content"][3]["embeddedObject"]["imageProperties"]["sourceUri"] = "different-source"
    reject("Docs sourceUri is not silently excluded", snapshots=bad)
    bad = deepcopy(native); bad["docs"]["contentUri"] = "unrelated-non-image-field"
    reject("contentUri outside imageProperties is retained", snapshots=bad)
    bad = deepcopy(native); bad["monthly"]["body"]["content"][3]["image"]["sourceUrl"] = "different-real-source"
    reject("sourceUrl is not silently excluded", snapshots=bad)
    bad = deepcopy(registry); bad["templates"][1]["id"] = bad["templates"][0]["id"]
    reject("duplicate template ID", reg=bad)
    bad = deepcopy(registry); bad["templates"][0]["id"] = "july-report"
    reject("past report registered as template", reg=bad)
    bad = deepcopy(run); bad["copy_source_id"] = "reference"
    reject("reference selected for copy", pre=bad)
    for field, value in (("mimeType", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
                         ("parents", ["2026"]), ("owners", [{"emailAddress": "other@example.test"}]),
                         ("trashed", True), ("link_id", "wrong-link"), ("run_id", "old-run"),
                         ("checked_at", "2026-07-01T09:01:00+03:00"), ("native_path", "../escape.json")):
        bad = deepcopy(run); bad["files"][0][field] = value
        reject(field, pre=bad)
    bad = deepcopy(native); bad["docs"]["revisionId"] = "r2"
    reject("changed revision", snapshots=bad)
    bad = deepcopy(run); bad["files"][0]["checked_at"] = "2099-01-01T00:00:00+03:00"
    reject("future read timestamp", pre=bad)
    bad = deepcopy(native); bad["docs"] = []
    reject("malformed native read", snapshots=bad)
    bad = deepcopy(native); bad["monthly"]["sheetsChart"] = {"spreadsheetId": "july-source"}
    reject("inherited linked chart", snapshots=bad)
    try:
        inventory(bad["monthly"])
    except ValueError as error:
        assert "linked monthly data" in str(error)
    else:
        raise AssertionError("linked chart passed inventory")
    bad = deepcopy(native); bad["docs"]["body"]["content"][2]["textRun"]["content"] = "987 654"
    reject("stale monthly value", snapshots=bad)
    bad = deepcopy(native); bad["docs"]["body"]["content"][3]["embeddedObject"]["imageProperties"]["cropProperties"] = {"leftOffset": 0.5}
    reject("changed monthly image properties", snapshots=bad)
    (root / "wrong-month.png").write_bytes(b"wrong monthly image bytes")
    pre = deepcopy(run); pointer = next(iter(registry["templates"][0]["allowed_images"]))
    pre["files"][0]["image_paths"][pointer] = "wrong-month.png"
    reject("stale monthly PNG bytes", pre=pre)
    # Updating only the declared hash must not hide unmapped content or numeric slots.
    reg = deepcopy(registry); reg["templates"][0]["approved_sha256"] = native_digest(bad["docs"])
    approval_path = root / reg["templates"][0]["approval_path"]
    original_approval = approval_path.read_text(encoding="utf-8"); approval = json.loads(original_approval)
    approval["approved_sha256"] = reg["templates"][0]["approved_sha256"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    reject("changed image properties even with refreshed hash", reg=reg, snapshots=bad)
    approval_path.write_text(original_approval, encoding="utf-8")
    bad = deepcopy(registry); del bad["templates"][0]["static_text"][next(iter(bad["templates"][0]["static_text"]))]
    reject("incomplete text inventory mapping", reg=bad)
    bad = deepcopy(registry); pointer = next(iter(bad["templates"][0]["text_slots"]))
    bad["templates"][0]["text_slots"][pointer] = "Июль 2026"
    reject("old date declared as neutral slot", reg=bad)
    (root / registry["templates"][0]["approval_path"]).unlink()
    reject("missing approval")
    (root / "registry.json").unlink()
    assert check(root / "registry.json", root / "preflight.json", list(MIME))["status"] == "BLOCKED"
    cases.append("missing registry")
    print(json.dumps({"status": "PASS", "positive": "complete neutral set", "negative_cases": cases},
                     ensure_ascii=False, indent=2))
