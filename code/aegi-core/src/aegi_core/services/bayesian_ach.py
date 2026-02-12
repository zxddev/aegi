"""贝叶斯 ACH 引擎 — 增量式假设概率更新。

在静态 ACH (hypothesis_engine.py) 之上叠加贝叶斯层。
不依赖外部贝叶斯库，直接用贝叶斯公式。
LLM 负责定性判断（关系 + 强度），数学负责定量更新。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.probability_update import ProbabilityUpdate
from aegi_core.infra.llm_client import LLMClient
from aegi_core.settings import settings

logger = logging.getLogger(__name__)


# ── 似然度映射 ────────────────────────────────────────────


def _parse_range(s: str) -> tuple[float, float]:
    lo, hi = s.split(",")
    return float(lo), float(hi)


def relation_strength_to_likelihood(
    relation: str,
    strength: float,
    *,
    support_range: tuple[float, float] | None = None,
    contradict_range: tuple[float, float] | None = None,
) -> float:
    """把 (relation, strength) 映射为 P(E|H)。

    - support:    线性插值 [support_lo, support_hi]
    - contradict: 线性插值 [contradict_hi, contradict_lo]（递减）
    - irrelevant: 固定 0.50
    """
    strength = max(0.0, min(1.0, strength))

    if support_range is None:
        support_range = _parse_range(settings.bayesian_likelihood_support_range)
    if contradict_range is None:
        contradict_range = _parse_range(settings.bayesian_likelihood_contradict_range)
    s_lo, s_hi = support_range
    c_lo, c_hi = contradict_range  # c_lo < c_hi (e.g. 0.05, 0.45)

    if relation == "support":
        return s_lo + (s_hi - s_lo) * strength
    elif relation == "contradict":
        return c_hi - (c_hi - c_lo) * strength
    else:  # irrelevant
        return 0.50


# ── LLM 结构化输出模型 ─────────────────────────────────


class EvidenceJudgment(BaseModel):
    """LLM 对单条证据-假设对的判断。"""

    hypothesis_uid: str
    relation: Literal["support", "contradict", "irrelevant"]
    strength: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class EvidenceAssessmentRequest(BaseModel):
    """LLM 批量评估的结构化输出。"""

    judgments: list[EvidenceJudgment]


# ── 返回值数据类 ────────────────────────────────────────────


@dataclass
class BayesianUpdateResult:
    """单次贝叶斯更新的结果。"""

    evidence_uid: str
    prior_distribution: dict[str, float]
    posterior_distribution: dict[str, float]
    likelihoods: dict[str, float]
    diagnosticity: dict[str, float]
    max_change: float
    most_affected_hypothesis_uid: str


@dataclass
class BayesianState:
    """某个 case 的贝叶斯 ACH 当前状态。"""

    case_uid: str
    hypotheses: list[dict] = field(default_factory=list)
    total_evidence_count: int = 0
    last_updated: datetime | None = None


# ── 评估 prompt ─────────────────────────────────────────────────

_ASSESS_PROMPT = """\
你是一名情报分析师。给定一条新证据和多个竞争性假设，
判断该证据与每个假设的关系。

证据：{evidence_text}

假设列表：
{hypotheses_text}

对每个假设，判断：
- relation: "support"（支持）/ "contradict"（反驳）/ "irrelevant"（无关）
- strength: 0.0~1.0 的强度值
  - 1.0 = 非常强的支持/反驳
  - 0.5 = 中等
  - 0.0 = 非常弱
- reason: 简短理由

注意：
- 不要输出概率数值，只判断关系和强度
- 同一条证据可以同时支持某些假设、反驳另一些假设
- 如果证据与假设无关，strength 值无意义，设为 0.5 即可
"""


class BayesianACH:
    """贝叶斯竞争性假设分析引擎。"""

    def __init__(self, db_session: AsyncSession, llm: LLMClient | None = None) -> None:
        self._db = db_session
        self._llm = llm

    # ── 初始化先验概率 ─────────────────────────────────────────

    async def initialize_priors(
        self,
        case_uid: str,
        priors: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """为 case 下所有假设设置均匀（或自定义）先验。"""
        rows = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return {}

        if priors:
            for hyp in rows:
                p = priors.get(hyp.uid, 0.0)
                hyp.prior_probability = p
                hyp.posterior_probability = p
        else:
            n = len(rows)
            uniform = 1.0 / n
            for hyp in rows:
                hyp.prior_probability = uniform
                hyp.posterior_probability = uniform

        await self._db.flush()
        return {h.uid: h.posterior_probability for h in rows}

    # ── LLM 评估证据 ────────────────────────────────────

    async def assess_evidence(
        self,
        case_uid: str,
        evidence_uid: str,
        evidence_text: str,
        evidence_type: str = "assertion",
    ) -> list[EvidenceAssessment]:
        """用 LLM 评估一条证据与所有假设的关系。"""
        hyps = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if not hyps or self._llm is None:
            return []

        hypotheses_text = "\n".join(f"- uid={h.uid}: {h.label}" for h in hyps)
        prompt = _ASSESS_PROMPT.format(
            evidence_text=evidence_text,
            hypotheses_text=hypotheses_text,
        )

        try:
            parsed = await self._llm.invoke_structured(
                prompt,
                EvidenceAssessmentRequest,
                max_tokens=4096,
                max_retries=2,
            )
        except Exception:
            logger.warning("贝叶斯 assess_evidence LLM 调用失败", exc_info=True)
            return []

        hyp_uids = {h.uid for h in hyps}
        judgment_map = {
            j.hypothesis_uid: j
            for j in parsed.judgments
            if j.hypothesis_uid in hyp_uids
        }

        results: list[EvidenceAssessment] = []
        for hyp in hyps:
            j = judgment_map.get(hyp.uid)
            relation = j.relation if j else "irrelevant"
            strength = j.strength if j else 0.5
            lk = relation_strength_to_likelihood(relation, strength)

            # Upsert：检查是否已存在
            existing = (
                await self._db.execute(
                    sa.select(EvidenceAssessment).where(
                        EvidenceAssessment.hypothesis_uid == hyp.uid,
                        EvidenceAssessment.evidence_uid == evidence_uid,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.relation = relation
                existing.strength = strength
                existing.likelihood = lk
                existing.assessed_by = "llm"
                results.append(existing)
            else:
                ea = EvidenceAssessment(
                    uid=uuid.uuid4().hex,
                    case_uid=case_uid,
                    hypothesis_uid=hyp.uid,
                    evidence_uid=evidence_uid,
                    evidence_type=evidence_type,
                    relation=relation,
                    strength=strength,
                    likelihood=lk,
                    assessed_by="llm",
                )
                self._db.add(ea)
                results.append(ea)

        await self._db.flush()
        return results

    # ── 贝叶斯更新 ──────────────────────────────────────────

    async def update(
        self,
        case_uid: str,
        evidence_uid: str,
    ) -> BayesianUpdateResult:
        """用已有的 evidence_assessments 执行贝叶斯定理更新。"""
        hyps = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )

        # 当前后验作为本次更新的先验
        prior_dist: dict[str, float] = {}
        for h in hyps:
            prior_dist[h.uid] = (
                h.posterior_probability or h.prior_probability or (1.0 / len(hyps))
            )

        # 加载这条证据的似然度
        eas = (
            (
                await self._db.execute(
                    sa.select(EvidenceAssessment).where(
                        EvidenceAssessment.case_uid == case_uid,
                        EvidenceAssessment.evidence_uid == evidence_uid,
                    )
                )
            )
            .scalars()
            .all()
        )
        lk_map: dict[str, float] = {ea.hypothesis_uid: ea.likelihood for ea in eas}

        # 缺失的用 0.5 填充（无关）
        likelihoods: dict[str, float] = {}
        for h in hyps:
            likelihoods[h.uid] = lk_map.get(h.uid, 0.5)

        # P(E) = Σ P(E|H_j) * P(H_j)
        p_evidence = sum(likelihoods[uid] * prior_dist[uid] for uid in prior_dist)
        if p_evidence == 0:
            p_evidence = 1e-10

        # 后验 = P(E|H) * P(H) / P(E)
        posterior_dist: dict[str, float] = {}
        for uid in prior_dist:
            posterior_dist[uid] = likelihoods[uid] * prior_dist[uid] / p_evidence

        # 归一化确保总和 = 1.0
        total = sum(posterior_dist.values())
        if total > 0:
            for uid in posterior_dist:
                posterior_dist[uid] /= total
        # 诊断性：与其他假设的最大似然比
        diagnosticity: dict[str, float] = {}
        uids = list(prior_dist.keys())
        for uid in uids:
            max_lr = 1.0
            for other in uids:
                if other == uid:
                    continue
                denom = likelihoods[other] if likelihoods[other] > 0 else 1e-10
                lr = likelihoods[uid] / denom
                if lr > max_lr:
                    max_lr = lr
            diagnosticity[uid] = max_lr

        # 找到变化最大的假设
        max_change = 0.0
        most_affected = uids[0] if uids else ""
        for uid in uids:
            change = abs(posterior_dist[uid] - prior_dist[uid])
            if change > max_change:
                max_change = change
                most_affected = uid

        # 持久化：更新假设 + 写 probability_updates 记录
        for h in hyps:
            old_post = prior_dist[h.uid]
            new_post = posterior_dist[h.uid]
            h.posterior_probability = new_post

            lk = likelihoods[h.uid]
            lr = lk / p_evidence

            self._db.add(
                ProbabilityUpdate(
                    uid=uuid.uuid4().hex,
                    hypothesis_uid=h.uid,
                    evidence_uid=evidence_uid,
                    prior=old_post,
                    posterior=new_post,
                    likelihood=lk,
                    likelihood_ratio=lr,
                )
            )

        await self._db.flush()

        return BayesianUpdateResult(
            evidence_uid=evidence_uid,
            prior_distribution=prior_dist,
            posterior_distribution=posterior_dist,
            likelihoods=likelihoods,
            diagnosticity=diagnosticity,
            max_change=max_change,
            most_affected_hypothesis_uid=most_affected,
        )

    # ── 查询：当前状态 ─────────────────────────────────────────

    async def get_state(self, case_uid: str) -> BayesianState:
        """返回 case 的当前概率分布和更新历史。"""
        hyps = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if not hyps:
            return BayesianState(case_uid=case_uid)

        ea_count = (
            await self._db.execute(
                sa.select(sa.func.count())
                .select_from(EvidenceAssessment)
                .where(EvidenceAssessment.case_uid == case_uid)
            )
        ).scalar_one()

        last_updated: datetime | None = None
        hyp_list: list[dict] = []
        for h in hyps:
            # 从 probability_updates 表获取历史
            updates = (
                (
                    await self._db.execute(
                        sa.select(ProbabilityUpdate)
                        .where(ProbabilityUpdate.hypothesis_uid == h.uid)
                        .order_by(ProbabilityUpdate.created_at)
                    )
                )
                .scalars()
                .all()
            )
            history = [
                {
                    "evidence_uid": u.evidence_uid,
                    "prior": u.prior,
                    "posterior": u.posterior,
                    "likelihood": u.likelihood,
                    "likelihood_ratio": u.likelihood_ratio,
                    "timestamp": u.created_at.isoformat() if u.created_at else None,
                }
                for u in updates
            ]
            if updates:
                ts = updates[-1].created_at
                if last_updated is None or (ts and ts > last_updated):
                    last_updated = ts

            hyp_list.append(
                {
                    "uid": h.uid,
                    "label": h.label,
                    "prior": h.prior_probability,
                    "posterior": h.posterior_probability,
                    "history": history,
                }
            )

        # 按唯一 evidence_uid 去重计数
        unique_ev = (
            await self._db.execute(
                sa.select(
                    sa.func.count(sa.distinct(EvidenceAssessment.evidence_uid))
                ).where(EvidenceAssessment.case_uid == case_uid)
            )
        ).scalar_one()

        return BayesianState(
            case_uid=case_uid,
            hypotheses=hyp_list,
            total_evidence_count=unique_ev,
            last_updated=last_updated,
        )

    # ── 查询：诊断性排名 ───────────────────────────────────

    async def get_diagnosticity_ranking(self, case_uid: str) -> list[dict]:
        """返回所有已评估证据，按诊断性降序排列。"""
        eas = (
            (
                await self._db.execute(
                    sa.select(EvidenceAssessment).where(
                        EvidenceAssessment.case_uid == case_uid
                    )
                )
            )
            .scalars()
            .all()
        )

        # 按 evidence_uid 分组
        ev_map: dict[str, dict[str, float]] = {}
        for ea in eas:
            ev_map.setdefault(ea.evidence_uid, {})[ea.hypothesis_uid] = ea.likelihood

        rankings: list[dict] = []
        for ev_uid, lk_map in ev_map.items():
            uids = list(lk_map.keys())
            if len(uids) < 2:
                continue
            max_diag = 1.0
            best_pair: list[str] = []
            for i, u1 in enumerate(uids):
                for u2 in uids[i + 1 :]:
                    d1 = lk_map[u1] / lk_map[u2] if lk_map[u2] > 0 else float("inf")
                    d2 = lk_map[u2] / lk_map[u1] if lk_map[u1] > 0 else float("inf")
                    d = max(d1, d2)
                    if d > max_diag:
                        max_diag = d
                        best_pair = [u1, u2]
            rankings.append(
                {
                    "evidence_uid": ev_uid,
                    "diagnosticity": max_diag,
                    "most_discriminated": best_pair,
                }
            )

        rankings.sort(key=lambda x: x["diagnosticity"], reverse=True)
        return rankings

    # ── 查询：证据缺口（规则版，不用 LLM）─

    async def get_evidence_gaps(self, case_uid: str) -> list[dict]:
        """用规则模板识别最有价值的信息缺口。"""
        hyps = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if len(hyps) < 2:
            return []

        # 找后验概率接近的假设对（差值 < 0.15）
        gaps: list[dict] = []
        for i, h1 in enumerate(hyps):
            for h2 in hyps[i + 1 :]:
                p1 = h1.posterior_probability or 0.0
                p2 = h2.posterior_probability or 0.0
                diff = abs(p1 - p2)
                if diff >= 0.15:
                    continue

                suggestions = [
                    f"需要能区分「{h1.label}」和「{h2.label}」的证据",
                    f"寻找支持「{h1.label}」但反驳「{h2.label}」的信息，或反之",
                ]

                # 检查是否缺少反驳评估
                for h in (h1, h2):
                    contra_count = (
                        await self._db.execute(
                            sa.select(sa.func.count())
                            .select_from(EvidenceAssessment)
                            .where(
                                EvidenceAssessment.hypothesis_uid == h.uid,
                                EvidenceAssessment.relation == "contradict",
                            )
                        )
                    ).scalar_one()
                    if contra_count == 0:
                        suggestions.append(
                            f"「{h.label}」尚未被任何证据反驳，建议寻找反面证据"
                        )

                gaps.append(
                    {
                        "hypothesis_pair": [h1.uid, h2.uid],
                        "labels": [h1.label, h2.label],
                        "posterior_diff": round(diff, 4),
                        "suggestions": suggestions,
                    }
                )

        gaps.sort(key=lambda x: x["posterior_diff"])
        return gaps

    # ── 专家覆盖 ──────────────────────────────────────────

    async def override_assessment(
        self,
        assessment_uid: str,
        relation: str,
        strength: float,
    ) -> EvidenceAssessment | None:
        """专家手动覆盖 LLM 的评估结果。"""
        ea = await self._db.get(EvidenceAssessment, assessment_uid)
        if ea is None:
            return None
        ea.relation = relation
        ea.strength = strength
        ea.likelihood = relation_strength_to_likelihood(relation, strength)
        ea.assessed_by = "expert"
        await self._db.flush()
        return ea

    # ── 从头重算 ───────────────────────────────────

    async def recalculate(self, case_uid: str) -> dict[str, float]:
        """从头重算所有后验（专家覆盖后调用）。

        从均匀先验开始，按 created_at 顺序重放所有 evidence_assessments。
        """
        hyps = (
            (
                await self._db.execute(
                    sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if not hyps:
            return {}

        n = len(hyps)
        posteriors = {h.uid: 1.0 / n for h in hyps}

        # 重置先验
        for h in hyps:
            h.prior_probability = 1.0 / n

        # 删除旧的 probability_updates 记录
        hyp_uids = [h.uid for h in hyps]
        await self._db.execute(
            sa.delete(ProbabilityUpdate).where(
                ProbabilityUpdate.hypothesis_uid.in_(hyp_uids)
            )
        )

        # 按时间顺序重放所有证据
        all_eas = (
            (
                await self._db.execute(
                    sa.select(EvidenceAssessment)
                    .where(EvidenceAssessment.case_uid == case_uid)
                    .order_by(EvidenceAssessment.created_at)
                )
            )
            .scalars()
            .all()
        )

        # 按 evidence_uid 分组，保持顺序
        seen: list[str] = []
        ev_groups: dict[str, list[EvidenceAssessment]] = {}
        for ea in all_eas:
            if ea.evidence_uid not in ev_groups:
                seen.append(ea.evidence_uid)
                ev_groups[ea.evidence_uid] = []
            ev_groups[ea.evidence_uid].append(ea)

        for ev_uid in seen:
            group = ev_groups[ev_uid]
            lk_map = {ea.hypothesis_uid: ea.likelihood for ea in group}
            likelihoods = {uid: lk_map.get(uid, 0.5) for uid in posteriors}

            priors = dict(posteriors)
            p_e = sum(likelihoods[uid] * priors[uid] for uid in priors)
            if p_e == 0:
                p_e = 1e-10

            for uid in posteriors:
                posteriors[uid] = likelihoods[uid] * priors[uid] / p_e

            total = sum(posteriors.values())
            if total > 0:
                for uid in posteriors:
                    posteriors[uid] /= total

            # 写 probability_update 记录
            for uid in posteriors:
                self._db.add(
                    ProbabilityUpdate(
                        uid=uuid.uuid4().hex,
                        hypothesis_uid=uid,
                        evidence_uid=ev_uid,
                        prior=priors[uid],
                        posterior=posteriors[uid],
                        likelihood=likelihoods[uid],
                    )
                )

        # 更新假设行
        for h in hyps:
            h.posterior_probability = posteriors[h.uid]

        await self._db.flush()
        return posteriors


# ── 事件处理器工厂 ─────────────────────────────────────────


def _format_update_summary(updates: list[dict]) -> str:
    lines = []
    for u in updates:
        uid = u.get("hypothesis_uid", "?")
        prior = u.get("prior", 0)
        post = u.get("posterior", 0)
        change = u.get("change", 0)
        sign = "+" if change >= 0 else ""
        lines.append(f"  {uid}: {prior:.1%} → {post:.1%} ({sign}{change:.1%})")
    return "假设概率更新：\n" + "\n".join(lines)


def create_bayesian_update_handler(
    *,
    llm: LLMClient | None = None,
) -> Any:
    """创建 claim.extracted 事件的贝叶斯更新处理器。"""
    from aegi_core.services.event_bus import AegiEvent, get_event_bus

    async def bayesian_update_handler(event: AegiEvent) -> None:
        if event.event_type != "claim.extracted":
            return

        case_uid = event.case_uid
        claim_uids = event.payload.get("claim_uids", [])
        if not claim_uids:
            return

        from aegi_core.db.session import ENGINE
        from aegi_core.db.models.source_claim import SourceClaim

        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            hyp_count = (
                await session.execute(
                    sa.select(sa.func.count())
                    .select_from(Hypothesis)
                    .where(Hypothesis.case_uid == case_uid)
                )
            ).scalar_one()
            if hyp_count == 0:
                return

            if llm is None:
                return

            engine = BayesianACH(session, llm)

            # 必须串行处理：每条 claim 的贝叶斯更新依赖前一条的 posterior 作为 prior。
            # 不要改成 asyncio.gather 并行，否则概率计算会出错。
            for claim_uid in claim_uids:
                claim = await session.get(SourceClaim, claim_uid)
                if not claim:
                    continue

                await engine.assess_evidence(
                    case_uid=case_uid,
                    evidence_uid=claim_uid,
                    evidence_text=claim.quote,
                    evidence_type="source_claim",
                )
                result = await engine.update(case_uid, claim_uid)

                if result.max_change >= settings.bayesian_update_threshold:
                    updates = [
                        {
                            "hypothesis_uid": uid,
                            "prior": result.prior_distribution[uid],
                            "posterior": result.posterior_distribution[uid],
                            "change": result.posterior_distribution[uid]
                            - result.prior_distribution[uid],
                        }
                        for uid in result.posterior_distribution
                    ]
                    bus = get_event_bus()
                    await bus.emit(
                        AegiEvent(
                            event_type="hypothesis.updated",
                            case_uid=case_uid,
                            payload={
                                "summary": _format_update_summary(updates),
                                "updates": updates,
                                "trigger_evidence_uid": claim_uid,
                                "trigger_evidence_text": claim.quote[:200],
                                "max_change": result.max_change,
                            },
                            severity="medium",
                            source_event_uid=f"bayes:{case_uid}:{claim_uid}",
                        )
                    )

            await session.commit()

    bayesian_update_handler.__name__ = "bayesian_update_handler"
    return bayesian_update_handler
