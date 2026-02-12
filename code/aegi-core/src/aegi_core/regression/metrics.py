# Author: msq
from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def extract_visible_text_from_html(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _selector_text_quote_exact(selector: dict) -> str | None:
    if selector.get("type") != "TextQuoteSelector":
        return None
    exact = selector.get("exact")
    return exact if isinstance(exact, str) and exact else None


def _is_grounded_text_quote(text: str, selectors: list[dict]) -> bool:
    for sel in selectors:
        exact = _selector_text_quote_exact(sel)
        if exact is not None and exact in text:
            return True
    return False


@dataclass(frozen=True)
class FixtureMetrics:
    anchor_locate_rate: float
    drift_rate: float
    claim_grounding_rate: float


def compute_metrics_for_fixture(fixtures_root: Path, manifest_item: dict) -> dict:
    artifact = manifest_item.get("artifact")
    if artifact is None:
        return {"anchor_locate_rate": 1.0, "claim_grounding_rate": 1.0}
    rel_artifact = artifact["path"]
    artifact_kind = artifact.get("kind")
    rel_chunks = manifest_item["chunks_path"]
    rel_source_claims = manifest_item["source_claims_path"]
    rel_assertions = manifest_item["assertions_path"]

    if artifact_kind == "html":
        artifact_html = (fixtures_root / rel_artifact).read_text(encoding="utf-8")
        text = extract_visible_text_from_html(artifact_html)
    elif artifact_kind == "pdf":
        rel_parsed_text = manifest_item.get("parsed_text_path")
        if not isinstance(rel_parsed_text, str) or not rel_parsed_text:
            text = ""
        else:
            text = (fixtures_root / rel_parsed_text).read_text(encoding="utf-8")
    else:
        text = ""

    chunks = json.loads((fixtures_root / rel_chunks).read_text(encoding="utf-8"))[
        "chunks"
    ]
    source_claims = json.loads(
        (fixtures_root / rel_source_claims).read_text(encoding="utf-8")
    )["source_claims"]
    assertions = json.loads(
        (fixtures_root / rel_assertions).read_text(encoding="utf-8")
    )["assertions"]

    # Anchor 定位率：TextQuoteSelector exact 能在原文中找到的 chunk 占比
    total_anchors = len(chunks)
    located = 0
    drifted = 0
    for ch in chunks:
        selectors = ch.get("anchor_set")
        if not isinstance(selectors, list):
            continue
        if _is_grounded_text_quote(text, selectors):
            located += 1
        else:
            # 有 anchor_set 但定位失败 → 漂移
            drifted += 1
    anchor_locate_rate = (located / total_anchors) if total_anchors else 0.0
    drift_rate = (drifted / total_anchors) if total_anchors else 0.0

    # Claim 落地率：至少有一个 grounded source claim 的 assertion 占比
    sc_by_uid = {
        sc["source_claim_uid"]: sc
        for sc in source_claims
        if isinstance(sc, dict) and isinstance(sc.get("source_claim_uid"), str)
    }

    total_assertions = len(assertions)
    grounded_assertions = 0
    for a in assertions:
        sc_uids = a.get("source_claim_uids")
        if not isinstance(sc_uids, list) or not sc_uids:
            continue
        grounded = False
        for uid in sc_uids:
            sc = sc_by_uid.get(uid)
            if sc is None:
                continue
            selectors = sc.get("selectors")
            if isinstance(selectors, list) and _is_grounded_text_quote(text, selectors):
                grounded = True
                break
        if grounded:
            grounded_assertions += 1

    claim_grounding_rate = (
        (grounded_assertions / total_assertions) if total_assertions else 0.0
    )

    metrics = FixtureMetrics(
        anchor_locate_rate=anchor_locate_rate,
        drift_rate=drift_rate,
        claim_grounding_rate=claim_grounding_rate,
    )

    return {
        "anchor_locate_rate": metrics.anchor_locate_rate,
        "drift_rate": metrics.drift_rate,
        "claim_grounding_rate": metrics.claim_grounding_rate,
    }
