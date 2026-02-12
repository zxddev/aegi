# Author: msq
"""DoWhy-based entity-level causal inference service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
import logging
from typing import Any

import anyio
import networkx as nx

from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services.event_bus import AegiEvent, get_event_bus
from aegi_core.settings import settings

logger = logging.getLogger(__name__)


class CausalInferenceError(RuntimeError):
    """Base error for causal inference service."""


class DoWhyUnavailableError(CausalInferenceError):
    """DoWhy is not installed."""


def _ensure_dowhy() -> Any:
    try:
        import dowhy

        return dowhy
    except ImportError as exc:
        raise DoWhyUnavailableError(
            "DoWhy not installed. Run: pip install 'aegi-core[analytics]'"
        ) from exc


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _extract_p_value(value: Any) -> float | None:
    direct = _as_float(value)
    if direct is not None:
        return direct

    if isinstance(value, dict):
        for key in ("p_value", "p-value", "pvalue", "significance", "p"):
            if key in value:
                p_value = _extract_p_value(value[key])
                if p_value is not None:
                    return p_value
        for nested in value.values():
            p_value = _extract_p_value(nested)
            if p_value is not None:
                return p_value
        return None

    if isinstance(value, (list, tuple, set)):
        for item in value:
            p_value = _extract_p_value(item)
            if p_value is not None:
                return p_value
        return None

    if hasattr(value, "to_dict"):
        try:
            return _extract_p_value(value.to_dict())
        except Exception:  # noqa: BLE001 - best-effort extraction
            return None
    return None


def _flatten_numbers(value: Any) -> list[float]:
    direct = _as_float(value)
    if direct is not None:
        return [direct]

    if isinstance(value, dict):
        numbers: list[float] = []
        for nested in value.values():
            numbers.extend(_flatten_numbers(nested))
        return numbers

    if isinstance(value, (list, tuple, set)):
        numbers: list[float] = []
        for item in value:
            numbers.extend(_flatten_numbers(item))
        return numbers

    if hasattr(value, "tolist"):
        try:
            return _flatten_numbers(value.tolist())
        except Exception:  # noqa: BLE001 - best-effort extraction
            return []
    if hasattr(value, "to_dict"):
        try:
            return _flatten_numbers(value.to_dict())
        except Exception:  # noqa: BLE001 - best-effort extraction
            return []
    return []


def _extract_confidence_interval(
    estimate: Any,
    *,
    fallback: float,
) -> tuple[float, float]:
    interval_raw = getattr(estimate, "confidence_intervals", None)
    if interval_raw is None:
        getter = getattr(estimate, "get_confidence_intervals", None)
        if callable(getter):
            try:
                interval_raw = getter()
            except Exception:  # noqa: BLE001 - best-effort extraction
                interval_raw = None

    values = _flatten_numbers(interval_raw)
    if len(values) < 2:
        return (fallback, fallback)
    low, high = values[0], values[1]
    if low <= high:
        return (low, high)
    return (high, low)


def _extract_effect_from_payload(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("new_effect", "effect", "value", "estimated_effect"):
            if key in value:
                candidate = _as_float(value[key])
                if candidate is not None:
                    return candidate
    numbers = _flatten_numbers(value)
    return numbers[0] if numbers else None


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OverflowError, ValueError):
            return None
    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_window(window: str) -> timedelta:
    normalized = window.strip().lower()
    if not normalized:
        raise ValueError("time_window cannot be empty.")
    if len(normalized) < 2:
        raise ValueError(
            f"Unsupported time_window: {window}. Expected values like 12h, 1d or 1w."
        )

    unit = normalized[-1]
    value = normalized[:-1]
    if not value.isdigit():
        raise ValueError(
            f"Unsupported time_window: {window}. Expected values like 12h, 1d or 1w."
        )
    amount = int(value)
    if amount <= 0:
        raise ValueError("time_window must be positive.")

    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    raise ValueError(f"Unsupported time_window: {window}. Expected units: h, d, w.")


def _bucket_time(timestamp: datetime, window_delta: timedelta) -> datetime:
    window_seconds = max(int(window_delta.total_seconds()), 1)
    epoch_seconds = int(timestamp.timestamp())
    bucket_seconds = (epoch_seconds // window_seconds) * window_seconds
    return datetime.fromtimestamp(bucket_seconds, tz=timezone.utc)


def _escape_gml(token: str) -> str:
    return token.replace("\\", "\\\\").replace('"', '\\"')


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


@dataclass(frozen=True)
class CausalGraphResult:
    treatment: str
    outcome: str
    confounders: list[str]
    mediators: list[str]
    gml_graph: str
    num_paths: int
    entity_names: dict[str, str]


@dataclass(frozen=True)
class RefutationResult:
    method: str
    estimated_effect: float
    new_effect: float
    p_value: float | None
    passed: bool


@dataclass(frozen=True)
class CausalEffectResult:
    treatment: str
    treatment_name: str
    outcome: str
    outcome_name: str
    effect_estimate: float
    confidence_interval: tuple[float, float]
    p_value: float | None
    method: str
    confounders: list[str]
    confounder_names: list[str]
    refutation_results: list[RefutationResult]
    is_significant: bool
    num_observations: int
    warning: str | None = None


class CausalInferenceEngine:
    """Entity-level causal inference from Neo4j subgraphs."""

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j

    async def _run_blocking(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))

    async def build_causal_graph(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
    ) -> CausalGraphResult:
        """Build a DoWhy-compatible DAG from case subgraph."""
        if treatment_entity_uid == outcome_entity_uid:
            raise ValueError("Treatment and outcome must be different entities.")

        subgraph_data = await self._neo4j.get_subgraph(case_uid)
        directed = nx.DiGraph()
        undirected = nx.Graph()
        entity_names: dict[str, str] = {}

        for node in subgraph_data.get("nodes", []):
            uid = str(node.get("uid") or "")
            if not uid:
                continue
            directed.add_node(uid)
            undirected.add_node(uid)
            name = str(node.get("name") or node.get("props", {}).get("label") or uid)
            entity_names[uid] = name

        for edge in subgraph_data.get("edges", []):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if not source or not target:
                continue
            directed.add_edge(source, target)
            undirected.add_edge(source, target)

        if not directed.has_node(treatment_entity_uid):
            raise ValueError(
                f"Treatment entity not found in case graph: {treatment_entity_uid}"
            )
        if not directed.has_node(outcome_entity_uid):
            raise ValueError(
                f"Outcome entity not found in case graph: {outcome_entity_uid}"
            )

        paths = list(
            nx.all_simple_paths(
                directed,
                source=treatment_entity_uid,
                target=outcome_entity_uid,
                cutoff=4,
            )
        )

        mediators: set[str] = set()
        path_nodes: set[str] = {treatment_entity_uid, outcome_entity_uid}
        for path in paths:
            path_nodes.update(path)
            if len(path) > 2:
                mediators.update(path[1:-1])

        treatment_neighbors = (
            set(undirected.neighbors(treatment_entity_uid))
            if undirected.has_node(treatment_entity_uid)
            else set()
        )
        outcome_neighbors = (
            set(undirected.neighbors(outcome_entity_uid))
            if undirected.has_node(outcome_entity_uid)
            else set()
        )
        confounders = treatment_neighbors & outcome_neighbors - path_nodes - {
            treatment_entity_uid,
            outcome_entity_uid,
        }

        mediator_list = sorted(mediators)
        confounder_list = sorted(confounders)
        selected_nodes = _unique_preserve_order(
            [
                treatment_entity_uid,
                outcome_entity_uid,
                *mediator_list,
                *confounder_list,
            ]
        )

        for uid in selected_nodes:
            entity_names.setdefault(uid, uid)

        gml_graph = self._build_gml_graph(
            selected_nodes=selected_nodes,
            treatment=treatment_entity_uid,
            outcome=outcome_entity_uid,
            confounders=confounder_list,
            paths=paths,
        )

        return CausalGraphResult(
            treatment=treatment_entity_uid,
            outcome=outcome_entity_uid,
            confounders=confounder_list,
            mediators=mediator_list,
            gml_graph=gml_graph,
            num_paths=len(paths),
            entity_names=entity_names,
        )

    @staticmethod
    def _build_gml_graph(
        *,
        selected_nodes: list[str],
        treatment: str,
        outcome: str,
        confounders: list[str],
        paths: list[list[str]],
    ) -> str:
        node_set = set(selected_nodes)
        edge_set: set[tuple[str, str]] = set()

        for path in paths:
            for source, target in zip(path, path[1:]):
                if source in node_set and target in node_set and source != target:
                    edge_set.add((source, target))

        for confounder in confounders:
            if confounder in node_set and confounder != treatment:
                edge_set.add((confounder, treatment))
            if confounder in node_set and confounder != outcome:
                edge_set.add((confounder, outcome))

        if treatment in node_set and outcome in node_set and treatment != outcome:
            edge_set.add((treatment, outcome))

        lines = ["graph [", "  directed 1"]
        for uid in selected_nodes:
            escaped = _escape_gml(uid)
            lines.append(f'  node [ id "{escaped}" label "{escaped}" ]')
        for source, target in sorted(edge_set):
            lines.append(
                '  edge [ source "%s" target "%s" ]'
                % (_escape_gml(source), _escape_gml(target))
            )
        lines.append("]")
        return "\n".join(lines)

    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
        time_window: str | None = None,
    ) -> CausalEffectResult:
        """Estimate entity-level causal effect using DoWhy."""
        dowhy = _ensure_dowhy()
        graph_result = await self.build_causal_graph(
            case_uid,
            treatment_entity_uid,
            outcome_entity_uid,
        )

        entity_uids = _unique_preserve_order(
            [
                treatment_entity_uid,
                outcome_entity_uid,
                *graph_result.confounders,
                *graph_result.mediators,
            ]
        )
        frame = await self._graph_to_dataframe(
            case_uid,
            entity_uids,
            window=time_window or settings.causal_time_window,
        )
        for uid in entity_uids:
            if uid not in frame.columns:
                frame[uid] = 0.0
        frame = frame[entity_uids]
        frame = frame.fillna(0.0)

        num_observations = int(frame.shape[0])
        treatment_name = graph_result.entity_names.get(
            treatment_entity_uid, treatment_entity_uid
        )
        outcome_name = graph_result.entity_names.get(
            outcome_entity_uid, outcome_entity_uid
        )
        confounder_names = [
            graph_result.entity_names.get(uid, uid) for uid in graph_result.confounders
        ]

        if num_observations < settings.causal_min_observations:
            warning = (
                f"观测数不足：{num_observations} < {settings.causal_min_observations}，"
                "已跳过 DoWhy 推断。"
            )
            return CausalEffectResult(
                treatment=treatment_entity_uid,
                treatment_name=treatment_name,
                outcome=outcome_entity_uid,
                outcome_name=outcome_name,
                effect_estimate=0.0,
                confidence_interval=(0.0, 0.0),
                p_value=None,
                method=method,
                confounders=graph_result.confounders,
                confounder_names=confounder_names,
                refutation_results=[],
                is_significant=False,
                num_observations=num_observations,
                warning=warning,
            )

        model = dowhy.CausalModel(
            data=frame,
            treatment=treatment_entity_uid,
            outcome=outcome_entity_uid,
            graph=graph_result.gml_graph,
        )
        identified_estimand = await self._run_blocking(
            model.identify_effect,
            proceed_when_unidentifiable=True,
        )
        estimate = await self._run_blocking(
            model.estimate_effect,
            identified_estimand,
            method_name=method,
            confidence_intervals=True,
            test_significance=True,
        )

        effect_estimate = _as_float(getattr(estimate, "value", None)) or 0.0
        confidence_interval = _extract_confidence_interval(
            estimate,
            fallback=effect_estimate,
        )
        p_value = await self._extract_estimate_p_value(estimate)

        refutation_results: list[RefutationResult] = []
        refutation_specs = [
            ("placebo_treatment", "placebo_treatment_refuter", {}),
            ("random_common_cause", "random_common_cause", {}),
            ("data_subset", "data_subset_refuter", {"subset_fraction": 0.8}),
        ]
        for public_name, refuter_method, kwargs in refutation_specs:
            try:
                refutation = await self._run_blocking(
                    model.refute_estimate,
                    identified_estimand,
                    estimate,
                    method_name=refuter_method,
                    **kwargs,
                )
                refutation_results.append(
                    self._build_refutation_result(
                        method=public_name,
                        refutation=refutation,
                        baseline_effect=effect_estimate,
                    )
                )
            except Exception:  # noqa: BLE001 - refutation failure should not kill inference
                logger.warning(
                    "DoWhy refutation failed: %s",
                    refuter_method,
                    exc_info=True,
                )
                refutation_results.append(
                    RefutationResult(
                        method=public_name,
                        estimated_effect=effect_estimate,
                        new_effect=effect_estimate,
                        p_value=None,
                        passed=False,
                    )
                )

        refutations_passed = sum(1 for item in refutation_results if item.passed)

        # 判断显著性：p_value 或置信区间（DoWhy 某些方法不返回 p_value）
        if p_value is not None:
            effect_is_significant = p_value < settings.causal_significance_level
        else:
            # p_value 不可用时，用置信区间是否排除 0 来判断
            ci_lo, ci_hi = confidence_interval
            effect_is_significant = (ci_lo > 0 and ci_hi > 0) or (ci_lo < 0 and ci_hi < 0)

        is_significant = effect_is_significant and refutations_passed >= 1

        result = CausalEffectResult(
            treatment=treatment_entity_uid,
            treatment_name=treatment_name,
            outcome=outcome_entity_uid,
            outcome_name=outcome_name,
            effect_estimate=effect_estimate,
            confidence_interval=confidence_interval,
            p_value=p_value,
            method=method,
            confounders=graph_result.confounders,
            confounder_names=confounder_names,
            refutation_results=refutation_results,
            is_significant=is_significant,
            num_observations=num_observations,
            warning=None,
        )

        if result.is_significant:
            bus = get_event_bus()
            await bus.emit(
                AegiEvent(
                    event_type="causal.effect_discovered",
                    case_uid=case_uid,
                    payload={
                        "summary": (
                            "发现因果关系："
                            f"{result.treatment_name} -> {result.outcome_name}，"
                            f"效应={result.effect_estimate:.3f}"
                        ),
                        "treatment": result.treatment_name,
                        "outcome": result.outcome_name,
                        "effect": result.effect_estimate,
                        "confidence_interval": list(result.confidence_interval),
                        "p_value": result.p_value,
                        "refutations_passed": refutations_passed,
                    },
                    severity="medium",
                    source_event_uid=(
                        f"causal:{case_uid}:{treatment_entity_uid}:{outcome_entity_uid}"
                    ),
                )
            )
        return result

    async def _extract_estimate_p_value(self, estimate: Any) -> float | None:
        p_value = _extract_p_value(getattr(estimate, "p_value", None))
        if p_value is not None:
            return p_value

        for attr in ("significance_test", "significance_tests"):
            p_value = _extract_p_value(getattr(estimate, attr, None))
            if p_value is not None:
                return p_value

        test_significance = getattr(estimate, "test_stat_significance", None)
        if callable(test_significance):
            try:
                tested = await self._run_blocking(test_significance)
            except Exception:  # noqa: BLE001 - best-effort extraction
                return None
            return _extract_p_value(tested)
        return None

    @staticmethod
    def _build_refutation_result(
        *,
        method: str,
        refutation: Any,
        baseline_effect: float,
    ) -> RefutationResult:
        estimated_effect = _as_float(getattr(refutation, "estimated_effect", None))
        if estimated_effect is None:
            estimated_effect = baseline_effect

        new_effect = _as_float(getattr(refutation, "new_effect", None))
        if new_effect is None:
            new_effect = _extract_effect_from_payload(
                getattr(refutation, "refutation_result", None)
            )
        if new_effect is None:
            new_effect = estimated_effect

        p_value = _extract_p_value(getattr(refutation, "refutation_result", None))
        if p_value is None:
            p_value = _extract_p_value(getattr(refutation, "p_value", None))

        tolerance = max(0.1, abs(estimated_effect) * 0.5)
        if method == "placebo_treatment":
            passed = abs(new_effect) <= tolerance
        else:
            passed = abs(new_effect - estimated_effect) <= tolerance

        return RefutationResult(
            method=method,
            estimated_effect=estimated_effect,
            new_effect=new_effect,
            p_value=p_value,
            passed=passed,
        )

    async def _graph_to_dataframe(
        self,
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> Any:
        """Convert graph observations to DoWhy tabular data."""
        import pandas as pd

        if not entity_uids:
            return pd.DataFrame()

        window_delta = _parse_window(window)
        query = (
            "MATCH (n {case_uid: $case_uid}) "
            "WHERE n.uid IN $entity_uids "
            "OPTIONAL MATCH (n)-[r]-(m {case_uid: $case_uid}) "
            "WHERE m.uid IN $entity_uids "
            "RETURN n.uid AS node_uid, "
            "       n.created_at AS node_created_at, "
            "       m.uid AS neighbor_uid, "
            "       r.created_at AS relation_created_at, "
            "       n.tone AS node_tone, "
            "       n.goldstein_scale AS node_goldstein_scale "
            "ORDER BY coalesce(r.created_at, n.created_at)"
        )
        rows = await self._neo4j.run_cypher(
            query,
            case_uid=case_uid,
            entity_uids=entity_uids,
        )

        if not rows:
            return pd.DataFrame(columns=entity_uids)

        bucket_rows: dict[datetime, dict[str, float]] = {}
        bucket_numeric: dict[datetime, dict[str, list[float]]] = {}
        fallback_counter = 0

        for row in rows:
            timestamp = _parse_timestamp(
                row.get("relation_created_at")
            ) or _parse_timestamp(row.get("node_created_at"))
            if timestamp is None:
                timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + (
                    fallback_counter * window_delta
                )
                fallback_counter += 1
            bucket = _bucket_time(timestamp, window_delta)
            observation = bucket_rows.setdefault(
                bucket, {uid: 0.0 for uid in entity_uids}
            )

            node_uid = str(row.get("node_uid") or "")
            if node_uid in observation:
                observation[node_uid] = 1.0
                numeric_values = [
                    value
                    for value in (
                        _as_float(row.get("node_tone")),
                        _as_float(row.get("node_goldstein_scale")),
                    )
                    if value is not None
                ]
                if numeric_values:
                    accumulator = bucket_numeric.setdefault(bucket, {}).setdefault(
                        node_uid, []
                    )
                    accumulator.extend(numeric_values)

            neighbor_uid = str(row.get("neighbor_uid") or "")
            if neighbor_uid in observation:
                observation[neighbor_uid] = 1.0

        for bucket, values_by_entity in bucket_numeric.items():
            observation = bucket_rows[bucket]
            for uid, values in values_by_entity.items():
                if values:
                    observation[uid] = sum(values) / len(values)

        ordered_buckets = sorted(bucket_rows)
        frame = pd.DataFrame(
            [bucket_rows[item] for item in ordered_buckets], index=ordered_buckets
        )
        for uid in entity_uids:
            if uid not in frame.columns:
                frame[uid] = 0.0
        return frame[entity_uids].fillna(0.0)
