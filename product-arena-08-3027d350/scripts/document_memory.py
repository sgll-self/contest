#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent, content-addressed document memory for parsed scientific PDFs.

Memory stores parsed evidence, not invented summaries. Repeated ingestion of the
same bytes reuses the cache; cross-document merge prefixes every source ID and
never performs unsupported semantic deduplication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import parse_pdf as P


INDEX_SCHEMA = "sci-pdf-reading-parse/memory-index/v1"
COLLECTION_SCHEMA = "sci-pdf-reading-parse/document-collection/v1"


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


class DocumentMemory:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.documents_dir = os.path.join(self.root, "documents")
        self.index_path = os.path.join(self.root, "index.json")
        os.makedirs(self.documents_dir, exist_ok=True)

    def _load_index(self):
        if not os.path.isfile(self.index_path):
            return {"schema": INDEX_SCHEMA, "documents": []}
        with open(self.index_path, encoding="utf-8") as handle:
            index = json.load(handle)
        if index.get("schema") != INDEX_SCHEMA or not isinstance(index.get("documents"), list):
            raise ValueError("unsupported or corrupt memory index schema")
        return index

    def _parsed_path(self, digest):
        return os.path.join(self.documents_dir, digest + ".json")

    def ingest(self, pdf_path, max_pages=None):
        started = time.perf_counter()
        digest = _sha256(pdf_path)
        index = self._load_index()
        existing = next((entry for entry in index["documents"] if entry["sha256"] == digest), None)
        if existing and os.path.isfile(self._parsed_path(digest)):
            with open(self._parsed_path(digest), encoding="utf-8") as handle:
                parsed = json.load(handle)
            if parsed.get("schema") == "sci-pdf-reading-parse/parsed/v3":
                return {
                    "entry": existing, "parsed": parsed, "cache_hit": True,
                    "seconds": time.perf_counter() - started,
                }
        parsed, _ = P.parse(pdf_path, case_id="memory:" + digest[:12], max_pages=max_pages)
        _atomic_json(self._parsed_path(digest), parsed)
        entry = {
            "sha256": digest, "source": os.path.basename(pdf_path),
            "parsed_path": os.path.join("documents", digest + ".json"),
            "parser_schema": parsed["schema"], "n_pages": parsed["stats"]["n_pages"],
            "n_blocks": parsed["stats"]["n_blocks"], "n_tables": parsed["stats"]["n_tables"],
            "n_figures": parsed["stats"]["n_figures"], "n_equations": parsed["stats"]["n_equations"],
            "warnings": parsed["warnings"],
        }
        index["documents"] = [item for item in index["documents"] if item["sha256"] != digest]
        index["documents"].append(entry)
        _atomic_json(self.index_path, index)
        return {"entry": entry, "parsed": parsed, "cache_hit": False,
                "seconds": time.perf_counter() - started}

    def query(self, text, case_sensitive=False):
        if not text:
            raise ValueError("query text must not be empty")
        index = self._load_index()
        needle = text if case_sensitive else text.casefold()
        matches = []
        for entry in index["documents"]:
            path = os.path.join(self.root, entry["parsed_path"])
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as handle:
                parsed = json.load(handle)
            collections = [("block", parsed.get("blocks", [])),
                           ("equation", parsed.get("equations", [])),
                           ("figure", parsed.get("figures", []))]
            for kind, items in collections:
                for item in items:
                    haystack = item.get("text", item.get("unicode_text", ""))
                    candidate = haystack if case_sensitive else haystack.casefold()
                    if needle in candidate:
                        matches.append({
                            "kind": kind, "id": item["id"], "document_sha256": entry["sha256"],
                            "source": entry["source"], "page": item["page"], "bbox": item["bbox"],
                            "text": haystack,
                        })
            for table in parsed.get("tables", []):
                for cell in table.get("cells", []):
                    candidate = cell["text"] if case_sensitive else cell["text"].casefold()
                    if needle in candidate:
                        matches.append({
                            "kind": "table_cell", "id": table["id"], "document_sha256": entry["sha256"],
                            "source": entry["source"], "page": table["page"], "bbox": cell.get("bbox"),
                            "row": cell["row"], "col": cell["col"], "text": cell["text"],
                        })
        return matches

    def merge(self, output_path, document_hashes=None):
        index = self._load_index()
        selected = index["documents"]
        if document_hashes:
            by_hash = {entry["sha256"]: entry for entry in selected}
            missing = [digest for digest in document_hashes if digest not in by_hash]
            if missing:
                raise ValueError("documents not present in memory: " + ",".join(missing))
            selected = [by_hash[digest] for digest in document_hashes]
        if not selected:
            raise ValueError("no documents available to merge")
        collection = {
            "schema": COLLECTION_SCHEMA,
            "merge_rule": "ordered concatenation with source-prefixed IDs; no semantic deduplication",
            "documents": selected, "blocks": [], "tables": [], "equations": [], "figures": [],
        }
        markdown = ["# Evidence-preserving document collection", ""]
        for entry in selected:
            path = os.path.join(self.root, entry["parsed_path"])
            with open(path, encoding="utf-8") as handle:
                parsed = json.load(handle)
            prefix = entry["sha256"][:12]
            markdown.extend([f"## {entry['source']}", f"SHA-256: `{entry['sha256']}`", ""])
            for kind, target in (("blocks", "blocks"), ("tables", "tables"),
                                 ("equations", "equations"), ("figures", "figures")):
                for original in parsed.get(kind, []):
                    item = dict(original)
                    item["document_sha256"] = entry["sha256"]
                    item["source_id"] = original["id"]
                    item["global_id"] = prefix + ":" + original["id"]
                    item["id"] = item["global_id"]
                    collection[target].append(item)
            for item in parsed.get("reading_items", []):
                item = dict(item)
                item["source_id"] = item["id"]
                item["id"] = prefix + ":" + item["id"]
                item["document_sha256"] = entry["sha256"]
                if item["kind"] == "block":
                    block = next(block for block in parsed["blocks"] if block["id"] == item["source_id"])
                    markdown.append(block["text"])
                elif item["kind"] == "table":
                    table = next((table for table in parsed["tables"] if table["id"] == item["source_id"]), None)
                    if table:
                        markdown.append(table["markdown"])
                markdown.append("")
        _atomic_json(output_path, collection)
        markdown_path = os.path.splitext(output_path)[0] + ".md"
        temporary = markdown_path + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(markdown))
        os.replace(temporary, markdown_path)
        return collection


def main(argv=None):
    parser = argparse.ArgumentParser(description="Content-addressed scientific document memory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("pdf")
    ingest_parser.add_argument("--memory", required=True)
    ingest_parser.add_argument("--max-pages", type=int)
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("text")
    query_parser.add_argument("--memory", required=True)
    query_parser.add_argument("--case-sensitive", action="store_true")
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--memory", required=True)
    merge_parser.add_argument("--documents", nargs="*")
    merge_parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        memory = DocumentMemory(args.memory)
        if args.command == "ingest":
            result = memory.ingest(args.pdf, args.max_pages)
            output = {"status": "ok", "cache_hit": result["cache_hit"],
                      "seconds": round(result["seconds"], 6), **result["entry"]}
        elif args.command == "query":
            output = {"status": "ok", "matches": memory.query(args.text, args.case_sensitive)}
        else:
            collection = memory.merge(args.out, args.documents)
            output = {"status": "ok", "documents": len(collection["documents"]),
                      "blocks": len(collection["blocks"]), "out": args.out}
        print(json.dumps(output, ensure_ascii=False, indent=1))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
