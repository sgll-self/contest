#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare and validate the official case output contract without inventing answers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import parse_pdf as P
import verify as V


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=1)
    os.replace(temporary, path)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contract_fields(case):
    contract = case.get("output_contract", {})
    if isinstance(contract, list):
        return [str(item) for item in contract]
    if isinstance(contract, dict):
        if isinstance(contract.get("required"), list):
            return [str(item) for item in contract["required"]]
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"])
        return [str(key) for key in contract if not str(key).startswith("$")]
    return []


def _candidate_paths(value, case_dir):
    if not isinstance(value, str) or not value.lower().endswith(".pdf"):
        return []
    candidates = [value] if os.path.isabs(value) else [
        os.path.join(case_dir, value), os.path.join(case_dir, "materials", value),
        os.path.join("/input", value), os.path.join("/input/materials", value),
    ]
    return [os.path.abspath(path) for path in candidates if os.path.isfile(path)]


def resolve_pdfs(case, case_path):
    case_dir = os.path.dirname(os.path.abspath(case_path))
    found = []

    def walk(value):
        if isinstance(value, dict):
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        else:
            found.extend(_candidate_paths(value, case_dir))

    walk(case)
    if not found and os.path.isdir(case_dir):
        for directory, _, filenames in os.walk(case_dir):
            for filename in filenames:
                if filename.lower().endswith(".pdf"):
                    found.append(os.path.join(directory, filename))
    return list(dict.fromkeys(os.path.abspath(path) for path in found))


def _base_result(case, fields):
    result = {field: None for field in fields}
    result.update({
        "case_id": case.get("case_id", case.get("id", "")),
        "status": "failed", "sources": [], "uncertainty": [],
        "change_log": ["case_workflow initialized a contract-shaped result before parsing"],
    })
    return result


def prepare_case(case_path, task_path, output_dir, work_dir):
    with open(case_path, encoding="utf-8") as handle:
        case = json.load(handle)
    fields = _contract_fields(case)
    result = _base_result(case, fields)
    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, "result.json")
    _atomic_json(result_path, result)  # honest early checkpoint
    case_id = result["case_id"] or "case"
    case_work = os.path.join(work_dir, str(case_id))
    os.makedirs(case_work, exist_ok=True)
    task_text = ""
    if task_path and os.path.isfile(task_path):
        with open(task_path, encoding="utf-8") as handle:
            task_text = handle.read()
    pdfs = resolve_pdfs(case, case_path)
    evidence = {"schema": "sci-pdf-reading-parse/case-evidence/v1",
                "case_id": result["case_id"], "documents": [], "errors": []}
    if not pdfs:
        evidence["errors"].append("no declared or discoverable PDF material")
    combined_reading = [f"# Case {case_id}", "", "## Task", task_text, ""]
    for index, pdf_path in enumerate(pdfs):
        document_work = os.path.join(case_work, f"document_{index}")
        os.makedirs(document_work, exist_ok=True)
        record = {"input_path": pdf_path, "source": os.path.basename(pdf_path),
                  "sha256": _sha256(pdf_path), "status": "failed"}
        try:
            parsed, _ = P.parse(pdf_path, case_id=str(case_id))
            parsed_path = os.path.join(document_work, "parsed.json")
            _atomic_json(parsed_path, parsed)
            verification = V.verify(pdf_path, parsed_path)
            verify_path = os.path.join(document_work, "verify.json")
            _atomic_json(verify_path, verification)
            record.update({
                "status": "partial" if verification["unreadable_pages"] else "parsed",
                "parsed_path": parsed_path, "verify_path": verify_path,
                "stats": parsed["stats"], "warnings": parsed["warnings"],
                "verification": verification,
            })
            combined_reading.extend([f"## Document {index}: {record['source']}",
                                     f"SHA-256: `{record['sha256']}`", "",
                                     P.render_markdown(parsed), ""])
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            record["error"] = str(exc)
            evidence["errors"].append(f"{record['source']}: {exc}")
        evidence["documents"].append(record)
    evidence_path = os.path.join(case_work, "evidence.json")
    _atomic_json(evidence_path, evidence)
    reading_path = os.path.join(output_dir, "reading.md")
    temporary = reading_path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(combined_reading))
    os.replace(temporary, reading_path)
    parsed_count = sum(record["status"] in ("parsed", "partial") for record in evidence["documents"])
    result["status"] = "partial" if parsed_count else "failed"
    result["uncertainty"] = evidence["errors"] + [
        "Parser evidence is prepared; the Agent must answer task.md and then run result validation."
    ]
    result["change_log"].append(f"parsed {parsed_count} of {len(pdfs)} PDF documents; evidence.json and reading.md written")
    _atomic_json(result_path, result)
    return result, evidence


def validate_result(case_path, result_path, work_dir):
    with open(case_path, encoding="utf-8") as handle:
        case = json.load(handle)
    with open(result_path, encoding="utf-8") as handle:
        result = json.load(handle)
    case_id = case.get("case_id", case.get("id", ""))
    evidence_path = os.path.join(work_dir, str(case_id or "case"), "evidence.json")
    errors = []
    required = _contract_fields(case) + ["case_id", "status", "sources", "uncertainty", "change_log"]
    for field in dict.fromkeys(required):
        if field not in result:
            errors.append(f"missing required field: {field}")
    if result.get("case_id") != case_id:
        errors.append("case_id does not match case.json")
    if result.get("status") not in ("success", "partial", "failed"):
        errors.append("status must be success, partial or failed")
    if result.get("status") == "success":
        for field in _contract_fields(case):
            if result.get(field) is None:
                errors.append(f"successful result has null contract field: {field}")
    anchors = {}
    if os.path.isfile(evidence_path):
        with open(evidence_path, encoding="utf-8") as handle:
            evidence = json.load(handle)
        for document in evidence.get("documents", []):
            parsed_path = document.get("parsed_path")
            if not parsed_path or not os.path.isfile(parsed_path):
                continue
            with open(parsed_path, encoding="utf-8") as handle:
                parsed = json.load(handle)
            for kind in ("blocks", "tables", "figures", "equations"):
                for item in parsed.get(kind, []):
                    anchors[item["id"]] = {"kind": kind, "page": item["page"], "bbox": item["bbox"],
                                           "document_sha256": document["sha256"]}
    else:
        errors.append("evidence.json is missing")
    sources = result.get("sources", [])
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source {index} is not an object")
            continue
        source_id = source.get("block_id") or source.get("table_id") or source.get(
            "figure_id") or source.get("equation_id") or source.get("id")
        if source_id and source_id not in anchors:
            errors.append(f"source {index} has unknown evidence id: {source_id}")
        if source_id and source_id in anchors and source.get("page") is not None and source["page"] != anchors[source_id]["page"]:
            errors.append(f"source {index} page does not match evidence")
    report = {"schema": "sci-pdf-reading-parse/result-validation/v1",
              "case_id": case_id, "valid": not errors, "errors": errors,
              "known_evidence_anchors": len(anchors), "sources_checked": len(sources)}
    validation_path = os.path.join(os.path.dirname(result_path), "validation.json")
    _atomic_json(validation_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare or validate an official PDF-parsing case")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--case", default="/input/case.json")
    prepare.add_argument("--task", default="/input/task.md")
    prepare.add_argument("--out", default="/app/output")
    prepare.add_argument("--work", default="/app/work")
    validate = subparsers.add_parser("validate")
    validate.add_argument("--case", default="/input/case.json")
    validate.add_argument("--result", default="/app/output/result.json")
    validate.add_argument("--work", default="/app/work")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result, evidence = prepare_case(args.case, args.task, args.out, args.work)
            print(json.dumps({"status": result["status"], "case_id": result["case_id"],
                              "documents": len(evidence["documents"]), "errors": evidence["errors"]},
                             ensure_ascii=False))
            return 0 if evidence["documents"] else 2
        report = validate_result(args.case, args.result, args.work)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["valid"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
