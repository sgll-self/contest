#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration checks for document memory and official-case safety workflow."""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time

import case_workflow as W
from document_memory import DocumentMemory
import parse_pdf as P


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=1)


def run_integration_tests(gt_pdf, structure_pdf, workdir, outdir):
    test_root = tempfile.mkdtemp(prefix="integration-", dir=workdir)
    memory = DocumentMemory(os.path.join(test_root, "memory"))

    direct_times, direct_outputs = [], []
    for _ in range(3):
        started = time.perf_counter()
        parsed, _ = P.parse(gt_pdf, case_id="stateless-baseline")
        direct_times.append(time.perf_counter() - started)
        direct_outputs.append(parsed)
    deterministic = all(parsed == direct_outputs[0] for parsed in direct_outputs[1:])

    first = memory.ingest(gt_pdf)
    warm_times = []
    warm = None
    for _ in range(3):
        warm = memory.ingest(gt_pdf)
        warm_times.append(warm["seconds"])
    second_document = memory.ingest(structure_pdf)
    matches = memory.query("Evidence-Anchored Reading Order")
    greek_matches = memory.query("α")
    collection_path = os.path.join(outdir, "document_collection.json")
    collection = memory.merge(collection_path)
    global_ids = [block["global_id"] for block in collection["blocks"]]
    with open(memory.index_path, encoding="utf-8") as handle:
        index_count = len(json.load(handle)["documents"])

    # Valid official-case contract and a real evidence anchor.
    case_dir = os.path.join(test_root, "case")
    os.makedirs(case_dir, exist_ok=True)
    case = {
        "case_id": "workflow-smoke", "materials": [{"path": gt_pdf}],
        "output_contract": {"required": ["answer"]},
    }
    case_path = os.path.join(case_dir, "case.json")
    task_path = os.path.join(case_dir, "task.md")
    _save(case_path, case)
    with open(task_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("Parse the controlled PDF and provide a source-anchored answer.")
    case_out = os.path.join(test_root, "case_output")
    case_work = os.path.join(test_root, "case_work")
    prepared, evidence = W.prepare_case(case_path, task_path, case_out, case_work)
    evidence_doc = evidence["documents"][0]
    with open(evidence_doc["parsed_path"], encoding="utf-8") as handle:
        parsed_for_anchor = json.load(handle)
    anchor = next(block for block in parsed_for_anchor["blocks"]
                  if block["role"] not in ("header", "footer", "table_text"))
    result_path = os.path.join(case_out, "result.json")
    with open(result_path, encoding="utf-8") as handle:
        result = json.load(handle)
    result.update({"answer": "Controlled smoke answer", "status": "success",
                   "sources": [{"block_id": anchor["id"], "page": anchor["page"]}],
                   "uncertainty": []})
    _save(result_path, result)
    valid_report = W.validate_result(case_path, result_path, case_work)
    invalid_out = os.path.join(test_root, "case_output_invalid")
    os.makedirs(invalid_out, exist_ok=True)
    invalid_result = dict(result)
    invalid_result["sources"] = [{"block_id": "p999_b999", "page": 999}]
    invalid_path = os.path.join(invalid_out, "result.json")
    _save(invalid_path, invalid_result)
    invalid_report = W.validate_result(case_path, invalid_path, case_work)

    missing_case = dict(case)
    missing_case["case_id"] = "workflow-missing"
    missing_case["materials"] = [{"path": os.path.join(case_dir, "absent.pdf")}]
    missing_path = os.path.join(case_dir, "missing_case.json")
    _save(missing_path, missing_case)
    missing_result, missing_evidence = W.prepare_case(
        missing_path, task_path, os.path.join(test_root, "missing_output"),
        os.path.join(test_root, "missing_work"))

    direct_median = statistics.median(direct_times)
    warm_median = statistics.median(warm_times)
    checks = {
        "repeat_parse_deterministic": deterministic,
        "memory_cache_hit": first["cache_hit"] is False and warm["cache_hit"] is True,
        "memory_idempotent_two_documents": index_count == 2,
        "exact_query_has_source_anchor": bool(matches) and all(
            match.get("document_sha256") and match.get("page") and match.get("bbox") for match in matches),
        "greek_query_reaches_recovered_equation": any(
            match["document_sha256"] == second_document["entry"]["sha256"] and match["kind"] == "equation"
            for match in greek_matches),
        "cross_document_merge_provenance": (
            len(collection["documents"]) == 2 and len(global_ids) == len(set(global_ids)) and
            all(block.get("document_sha256") and block.get("source_id") for block in collection["blocks"])),
        "workflow_valid_result": valid_report["valid"],
        "workflow_rejects_unknown_anchor": not invalid_report["valid"] and any(
            "unknown evidence id" in error for error in invalid_report["errors"]),
        "workflow_missing_material_honest": (missing_result["status"] == "failed" and
            not missing_evidence["documents"] and bool(missing_evidence["errors"])),
    }
    report = {
        "schema": "sci-pdf-reading-parse/integration-checks/v1",
        "checks": checks,
        "all_passed": all(checks.values()),
        "performance": {
            "comparison": "same controlled PDF; three direct cold parses versus three content-hash cache hits",
            "direct_parse_median_s": round(direct_median, 6),
            "memory_first_ingest_s": round(first["seconds"], 6),
            "memory_warm_hit_median_s": round(warm_median, 6),
            "warm_cache_speedup_x": round(direct_median / warm_median, 3) if warm_median > 0 else None,
            "scope": "repeated-document efficiency only; first ingestion still performs a full parse",
        },
        "artifacts": ["execution/results/document_collection.json", "execution/results/document_collection.md"],
    }
    _save(os.path.join(outdir, "integration_checks.json"), report)
    return report
