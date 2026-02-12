#!/usr/bin/env python3
"""端到端真实测试：调用 live FastAPI + 真实 LLM，验证全链路。

Usage: cd code/aegi-core && uv run python tests/run_e2e_real.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from uuid import uuid4

import httpx

BASE = "http://localhost:8700"
TIMEOUT = httpx.Timeout(600.0)


# ── 辅助 ──────────────────────────────────────────────────────────


class E2ERunner:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT)
        self.case_uid: str = ""
        # fixture import 返回的 UID
        self.source_claim_uids: list[str] = []
        self.assertion_uids: list[str] = []
        self.judgment_uid: str = ""
        self.artifact_version_uid: str = ""
        self.chunk_uids: list[str] = []
        self.evidence_uids: list[str] = []
        # 后续阶段产出
        self.hypothesis_uids: list[str] = []
        self.narrative_uids: list[str] = []
        self.forecast_scenario_ids: list[str] = []
        # source_claims 完整对象（从 DB 读取）
        self.source_claims_v1: list[dict] = []
        self.assertions_v1: list[dict] = []
        self.results: dict[str, dict] = {}

    async def close(self) -> None:
        await self.client.aclose()

    def _report(self, stage: str, ok: bool, detail: str = "", duration: float = 0):
        status = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        dur = f" ({duration:.1f}s)" if duration else ""
        print(f"  [{status}] {stage}{dur}")
        if detail:
            lines = detail.split("\n")
            for line in lines[:8]:
                print(f"         {line[:140]}")
            if len(lines) > 8:
                print(f"         ... ({len(lines) - 8} more lines)")
        self.results[stage] = {"ok": ok, "detail": detail, "duration": duration}

    # ── Stage 0: Health ──────────────────────────────────────────

    async def check_health(self) -> bool:
        t0 = time.time()
        resp = await self.client.get("/health")
        ok = resp.status_code == 200 and resp.json().get("ok")
        self._report("health", ok, json.dumps(resp.json()), time.time() - t0)
        return ok

    # ── Stage 1: Create Case ─────────────────────────────────────

    async def create_case(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            "/cases",
            json={
                "title": "E2E 南海军事态势分析",
                "actor_id": "e2e-test",
                "rationale": "端到端真实测试",
            },
        )
        ok = resp.status_code == 201
        if ok:
            self.case_uid = resp.json()["case_uid"]
            self._report(
                "create_case", True, f"case_uid={self.case_uid}", time.time() - t0
            )
        else:
            self._report("create_case", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 2: Import Fixture (defgeo-001) ─────────────────────

    async def import_fixture(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/fixtures/import",
            json={
                "fixture_id": "defgeo-001",
                "actor_id": "e2e-test",
                "rationale": "导入 defgeo-001 fixture",
            },
        )
        ok = resp.status_code == 201
        if ok:
            data = resp.json()
            self.source_claim_uids = data["source_claim_uids"]
            self.assertion_uids = data["assertion_uids"]
            self.judgment_uid = data["judgment_uid"]
            self.artifact_version_uid = data["artifact_version_uid"]
            self.chunk_uids = data["chunk_uids"]
            self.evidence_uids = data["evidence_uids"]
            detail = (
                f"claims={len(self.source_claim_uids)}, "
                f"assertions={len(self.assertion_uids)}, "
                f"chunks={len(self.chunk_uids)}"
            )
            self._report("import_fixture(defgeo-001)", True, detail, time.time() - t0)
        else:
            self._report(
                "import_fixture(defgeo-001)", False, resp.text, time.time() - t0
            )
        return ok

    # ── Stage 2b: Import second fixture for richer data ──────────

    async def import_fixture_002(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/fixtures/import",
            json={
                "fixture_id": "defgeo-002",
                "actor_id": "e2e-test",
                "rationale": "导入 defgeo-002 fixture (PDF)",
            },
        )
        ok = resp.status_code == 201
        if ok:
            data = resp.json()
            self.source_claim_uids.extend(data["source_claim_uids"])
            self.assertion_uids.extend(data["assertion_uids"])
            detail = (
                f"+claims={len(data['source_claim_uids'])}, "
                f"+assertions={len(data['assertion_uids'])}, "
                f"total_claims={len(self.source_claim_uids)}, "
                f"total_assertions={len(self.assertion_uids)}"
            )
            self._report("import_fixture(defgeo-002)", True, detail, time.time() - t0)
        else:
            self._report(
                "import_fixture(defgeo-002)", False, resp.text, time.time() - t0
            )
        return ok

    # ── Stage 3: Read back source claims & assertions from API ───

    async def load_objects(self) -> bool:
        """Read individual source_claims and assertions from API, map to V1 schema."""
        t0 = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 读取 source claims — API 返回 source_claim_uid, 需要映射到 uid
        for uid in self.source_claim_uids:
            resp = await self.client.get(f"/source_claims/{uid}")
            if resp.status_code == 200:
                raw = resp.json()
                self.source_claims_v1.append(
                    {
                        "uid": raw.get("source_claim_uid", uid),
                        "case_uid": raw.get("case_uid", self.case_uid),
                        "artifact_version_uid": raw.get("artifact_version_uid", ""),
                        "chunk_uid": raw.get("chunk_uid", ""),
                        "evidence_uid": raw.get("evidence_uid", ""),
                        "quote": raw.get("quote", ""),
                        "selectors": raw.get("selectors", []),
                        "attributed_to": raw.get("attributed_to"),
                        "created_at": raw.get("created_at", now_iso),
                    }
                )

        # 读取 assertions — API 返回 assertion_uid, 需要映射到 uid
        for uid in self.assertion_uids:
            resp = await self.client.get(f"/assertions/{uid}")
            if resp.status_code == 200:
                raw = resp.json()
                self.assertions_v1.append(
                    {
                        "uid": raw.get("assertion_uid", uid),
                        "case_uid": raw.get("case_uid", self.case_uid),
                        "kind": raw.get("kind", "event"),
                        "value": raw.get("value", {}),
                        "source_claim_uids": raw.get("source_claim_uids", []),
                        "confidence": raw.get("confidence"),
                        "created_at": raw.get("created_at", now_iso),
                    }
                )

        ok = len(self.source_claims_v1) > 0 and len(self.assertions_v1) > 0
        detail = f"loaded {len(self.source_claims_v1)} claims, {len(self.assertions_v1)} assertions"
        self._report("load_objects", ok, detail, time.time() - t0)
        return ok

    # ── Stage 4: Assertion Fusion (re-fuse from source claims) ───

    async def assertion_fuse(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/pipelines/assertion_fuse",
            json={"source_claim_uids": self.source_claim_uids},
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            assertions = data.get("assertions", [])
            new_uids = [a["uid"] for a in assertions]
            detail_lines = [f"fused {len(assertions)} assertions:"]
            for a in assertions[:5]:
                detail_lines.append(
                    f"  - [{a.get('kind', '?')}] {str(a.get('value', '?'))[:80]}"
                )
            self._report(
                "assertion_fuse", True, "\n".join(detail_lines), time.time() - t0
            )
            # 追加新 assertion UIDs
            self.assertion_uids.extend(new_uids)
        else:
            self._report("assertion_fuse", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 5: Detect Language ─────────────────────────────────

    async def detect_language(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/pipelines/detect_language",
            json={
                "claim_uids": [sc["uid"] for sc in self.source_claims_v1],
                "claims": self.source_claims_v1,
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            results = data.get("results", [])
            langs = [r.get("detected_language", "?") for r in results]
            self._report(
                "detect_language", True, f"languages: {langs}", time.time() - t0
            )
        else:
            self._report("detect_language", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 6: Translate Claims ────────────────────────────────

    async def translate_claims(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/pipelines/translate_claims",
            json={
                "claims": self.source_claims_v1,
                "target_language": "en",
                "budget_context": {"max_tokens": 4096, "max_cost_usd": 1.0},
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            results = data.get("results", [])
            detail_lines = [f"translated {len(results)} claims:"]
            for r in results[:3]:
                t_text = str(r.get("translation", ""))[:80]
                detail_lines.append(f"  - {t_text}")
            self._report(
                "translate_claims", True, "\n".join(detail_lines), time.time() - t0
            )
        else:
            self._report("translate_claims", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 7: Hypothesis Generation (LLM) ─────────────────────

    async def generate_hypotheses(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/hypotheses/generate",
            json={
                "assertion_uids": self.assertion_uids,
                "source_claim_uids": self.source_claim_uids,
            },
        )
        ok = resp.status_code == 201
        if ok:
            data = resp.json()
            hypotheses = data.get("hypotheses", [])
            self.hypothesis_uids = [h["hypothesis_uid"] for h in hypotheses]
            detail_lines = [f"generated {len(hypotheses)} hypotheses:"]
            for h in hypotheses[:5]:
                detail_lines.append(
                    f"  - [{h.get('hypothesis_uid', '?')[:16]}] "
                    f"conf={h.get('confidence', '?')} "
                    f"{h.get('hypothesis_text', '?')[:60]}"
                )
            self._report(
                "generate_hypotheses", True, "\n".join(detail_lines), time.time() - t0
            )
        else:
            self._report("generate_hypotheses", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 8: Hypothesis Scoring (ACH + Adversarial) ──────────

    async def score_hypothesis(self) -> bool:
        if not self.hypothesis_uids:
            self._report("score_hypothesis", False, "no hypotheses to score")
            return False

        t0 = time.time()
        h_uid = self.hypothesis_uids[0]
        resp = await self.client.post(
            f"/cases/{self.case_uid}/hypotheses/{h_uid}/score",
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            detail = (
                f"hypothesis={h_uid[:20]}... "
                f"confidence={data.get('confidence', '?')} "
                f"coverage={data.get('coverage_score', '?')} "
                f"gaps={len(data.get('gap_list', []))} "
                f"adversarial_grounding={data.get('adversarial', {}).get('grounding_level', '?')}"
            )
            self._report("score_hypothesis", True, detail, time.time() - t0)
        else:
            self._report("score_hypothesis", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 9: Hypothesis Explain ──────────────────────────────

    async def explain_hypothesis(self) -> bool:
        if not self.hypothesis_uids:
            self._report("explain_hypothesis", False, "no hypotheses")
            return False

        t0 = time.time()
        h_uid = self.hypothesis_uids[0]
        resp = await self.client.get(
            f"/cases/{self.case_uid}/hypotheses/{h_uid}/explain",
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            detail = (
                f"hypothesis_text={data.get('hypothesis_text', '?')[:60]} "
                f"supporting={len(data.get('supporting_assertion_uids', []))} "
                f"contradicting={len(data.get('contradicting_assertion_uids', []))} "
                f"provenance={len(data.get('provenance', []))}"
            )
            self._report("explain_hypothesis", True, detail, time.time() - t0)
        else:
            self._report("explain_hypothesis", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 10: Narrative Build ────────────────────────────────

    async def build_narratives(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/narratives/build",
            json={
                "source_claims": self.source_claims_v1,
                "time_window_hours": 168.0,
                "similarity_threshold": 0.35,
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            narratives = data.get("narratives", [])
            self.narrative_uids = [n["uid"] for n in narratives]
            detail_lines = [f"built {len(narratives)} narratives:"]
            for n in narratives[:5]:
                detail_lines.append(
                    f"  - [{n.get('uid', '?')[:16]}] {n.get('title', '?')[:80]}"
                )
            self._report(
                "build_narratives", True, "\n".join(detail_lines), time.time() - t0
            )
        else:
            self._report("build_narratives", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 11: Detect Coordination ────────────────────────────

    async def detect_coordination(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/narratives/detect_coordination",
            json={
                "source_claims": self.source_claims_v1,
                "burst_window_hours": 24.0,
                "min_cluster_size": 2,
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            signals = data.get("signals", [])
            detail = f"coordination signals: {len(signals)}"
            if signals:
                for s in signals[:3]:
                    detail += f"\n  - {s.get('explanation', '?')[:80]}"
            self._report("detect_coordination", True, detail, time.time() - t0)
        else:
            self._report("detect_coordination", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 12: KG Build (LLM + Neo4j) ────────────────────────

    async def build_kg(self) -> bool:
        if not self.assertions_v1:
            self._report("build_kg", False, "no assertions for KG")
            return False

        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/kg/build_from_assertions",
            json={
                "assertions": self.assertions_v1,
                "ontology_version": "v1.0",
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            if "error" in data:
                ok = False
                self._report(
                    "build_kg", False, f"error: {data['error']}", time.time() - t0
                )
            else:
                entities = data.get("entities", [])
                events = data.get("events", [])
                relations = data.get("relations", [])
                detail_lines = [
                    f"entities={len(entities)}, events={len(events)}, relations={len(relations)}"
                ]
                for e in entities[:3]:
                    detail_lines.append(
                        f"  entity: {e.get('name', '?')} ({e.get('entity_type', '?')})"
                    )
                for ev in events[:3]:
                    detail_lines.append(f"  event: {ev.get('name', '?')}")
                for r in relations[:3]:
                    detail_lines.append(
                        f"  rel: {r.get('source_uid', '?')[:12]} --{r.get('relation_type', '?')}--> {r.get('target_uid', '?')[:12]}"
                    )
                self._report(
                    "build_kg", True, "\n".join(detail_lines), time.time() - t0
                )
        else:
            self._report("build_kg", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 13: Forecast Generation (LLM) ──────────────────────

    async def generate_forecasts(self) -> bool:
        if not self.hypothesis_uids:
            self._report("generate_forecasts", False, "no hypotheses for forecasting")
            return False

        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/forecast/generate",
            json={
                "hypothesis_uids": self.hypothesis_uids[:3],
                "assertion_uids": self.assertion_uids,
            },
        )
        ok = resp.status_code == 201
        if ok:
            data = resp.json()
            scenarios = data.get("scenarios", [])
            self.forecast_scenario_ids = [s.get("scenario_id", "") for s in scenarios]
            detail_lines = [f"generated {len(scenarios)} scenarios:"]
            for s in scenarios[:5]:
                detail_lines.append(
                    f"  - [{s.get('scenario_id', '?')[:16]}] "
                    f"prob={s.get('probability', '?')} "
                    f"status={s.get('status', '?')}"
                )
            self._report(
                "generate_forecasts", True, "\n".join(detail_lines), time.time() - t0
            )
        else:
            self._report("generate_forecasts", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 14: Forecast Explain ───────────────────────────────

    async def explain_forecast(self) -> bool:
        if not self.forecast_scenario_ids:
            self._report("explain_forecast", False, "no scenarios to explain")
            return False

        t0 = time.time()
        sid = self.forecast_scenario_ids[0]
        resp = await self.client.get(
            f"/cases/{self.case_uid}/forecast/{sid}/explain",
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            detail = (
                f"scenario={sid[:16]}... "
                f"triggers={len(data.get('trigger_conditions', []))} "
                f"citations={len(data.get('evidence_citations', []))} "
                f"causal_links={len(data.get('causal_links', []))}"
            )
            self._report("explain_forecast", True, detail, time.time() - t0)
        else:
            self._report("explain_forecast", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 15: Quality Scoring ────────────────────────────────

    async def score_quality(self) -> bool:
        t0 = time.time()
        judgment_uid = f"j_{uuid4().hex[:8]}"
        resp = await self.client.post(
            f"/cases/{self.case_uid}/quality/score_judgment",
            json={
                "judgment_uid": judgment_uid,
                "title": "南海态势分析质量评估",
                "assertion_uids": self.assertion_uids,
                "assertions": self.assertions_v1,
                "source_claims": self.source_claims_v1,
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            detail = (
                f"status={data.get('status', '?')} "
                f"confidence={data.get('confidence_score', '?')} "
                f"bias_flags={len(data.get('bias_flags', []))} "
                f"blindspots={len(data.get('blindspots', []))}"
            )
            self._report("score_quality", True, detail, time.time() - t0)
        else:
            self._report("score_quality", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 16: Chat QA (LLM) ─────────────────────────────────

    async def chat_qa(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/analysis/chat",
            json={
                "question": "What are the key military developments near the strait? What are the potential risks?",
                "language": "en",
            },
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            answer = data.get("answer", "")
            citations = data.get("citations", [])
            trace_id = data.get("trace_id", "")
            detail_lines = [
                f"trace_id={trace_id[:20]}...",
                f"citations={len(citations)}",
                f"answer: {answer[:200]}...",
            ]
            self._report("chat_qa", True, "\n".join(detail_lines), time.time() - t0)

            # 验证 trace 可回放
            if trace_id:
                resp2 = await self.client.get(
                    f"/cases/{self.case_uid}/analysis/chat/{trace_id}"
                )
                trace_ok = resp2.status_code == 200
                self._report(
                    "chat_trace_replay",
                    trace_ok,
                    f"trace replay {'OK' if trace_ok else 'FAILED'}",
                )
        else:
            self._report("chat_qa", False, resp.text, time.time() - t0)
        return ok

    # ── Stage 17: Full Pipeline Orchestration (LLM) ──────────────

    async def full_pipeline(self) -> bool:
        t0 = time.time()
        resp = await self.client.post(
            f"/cases/{self.case_uid}/pipelines/full_analysis",
            json={"source_claim_uids": self.source_claim_uids},
        )
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            stages = data.get("stages", [])
            detail_lines = [f"pipeline completed with {len(stages)} stages:"]
            all_ok = True
            for s in stages:
                status = s.get("status", "?")
                tag = "OK" if status == "ok" else "ERR"
                dur = s.get("duration_ms", 0)
                err = s.get("error", "")
                detail_lines.append(
                    f"  [{tag}] {s.get('stage', '?'):25s} {dur:6d}ms {err[:60] if err else ''}"
                )
                if status == "error":
                    all_ok = False
            self._report(
                "full_pipeline", all_ok, "\n".join(detail_lines), time.time() - t0
            )
            return all_ok
        else:
            self._report("full_pipeline", False, resp.text, time.time() - t0)
        return ok


# ── Main ──────────────────────────────────────────────────────────


async def main() -> int:
    print("=" * 70)
    print("  AEGI 端到端真实测试 (Live API + Real LLM)")
    print("=" * 70)
    print()

    runner = E2ERunner()
    total_t0 = time.time()

    try:
        # 基础检查
        if not await runner.check_health():
            print("\n服务不可用，终止测试。")
            return 1

        # 创建 Case
        if not await runner.create_case():
            print("\n创建 Case 失败，终止测试。")
            return 1

        print(f"\n  Case: {runner.case_uid}")
        print(f"  {'─' * 55}")

        # 导入 fixture 数据
        print(f"\n  ── 数据准备 ──")
        if not await runner.import_fixture():
            print("\n导入 fixture 失败，终止测试。")
            return 1
        await runner.import_fixture_002()
        await runner.load_objects()

        # 分析流水线
        print(f"\n  ── 分析流水线 ──")
        await runner.assertion_fuse()
        await runner.detect_language()
        await runner.translate_claims()

        print(f"\n  ── 假设分析 (LLM) ──")
        await runner.generate_hypotheses()
        await runner.score_hypothesis()
        await runner.explain_hypothesis()

        print(f"\n  ── 叙事检测 ──")
        await runner.build_narratives()
        await runner.detect_coordination()

        print(f"\n  ── 知识图谱 (LLM + Neo4j) ──")
        await runner.build_kg()

        print(f"\n  ── 预测生成 (LLM) ──")
        await runner.generate_forecasts()
        await runner.explain_forecast()

        print(f"\n  ── 质量评估 ──")
        await runner.score_quality()

        print(f"\n  ── 对话式问答 (LLM) ──")
        await runner.chat_qa()

        print(f"\n  ── 全流水线编排 (LLM) ──")
        await runner.full_pipeline()

    except Exception:
        print(f"\n  !! 未捕获异常:")
        traceback.print_exc()
    finally:
        await runner.close()

    # 汇总
    total_dur = time.time() - total_t0
    passed = sum(1 for r in runner.results.values() if r["ok"])
    failed = sum(1 for r in runner.results.values() if not r["ok"])
    total = len(runner.results)

    print(f"\n{'=' * 70}")
    print(
        f"  总计: {total} 阶段 | \033[32m{passed} 通过\033[0m | \033[31m{failed} 失败\033[0m | 耗时 {total_dur:.1f}s"
    )
    print(f"{'=' * 70}")

    if failed:
        print("\n  失败阶段:")
        for name, r in runner.results.items():
            if not r["ok"]:
                print(f"    - {name}: {r['detail'][:120]}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
