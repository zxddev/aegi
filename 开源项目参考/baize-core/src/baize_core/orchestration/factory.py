"""编排器工厂。"""

from __future__ import annotations

import importlib
from typing import cast

from minio import Minio

from baize_core.agents.crew import CrewCoordinator
from baize_core.audit.db_sink import DbAuditSink
from baize_core.audit.recorder import AuditRecorder
from baize_core.config.model_config import load_model_config
from baize_core.config.settings import AppConfig
from baize_core.graph.graphrag_pipeline import GraphRagPipeline
from baize_core.graph.neo4j_store import Neo4jStore
from baize_core.llm.router import ModelRouter
from baize_core.llm.runner import LlmConfig, LlmRunner
from baize_core.orchestration.langgraph_graph import build_review_graph
from baize_core.orchestration.ooda_graph import build_ooda_graph
from baize_core.orchestration.review import ReviewAgent
from baize_core.orchestration.runner import AsyncGraph, Orchestrator
from baize_core.orchestration.storm_graph import StormContext, build_storm_graph
from baize_core.policy.engine import PolicyEngine
from baize_core.storage.database import create_engine, create_session_factory
from baize_core.storage.minio_store import MinioArtifactStore
from baize_core.storage.postgres import PostgresStore
from baize_core.modules.registry import ModuleRegistry
from baize_core.modules.parser import UserInputParser
from baize_core.tools.mcp_client import McpClient
from baize_core.tools.runner import ToolRunner


def build_orchestrator(config: AppConfig) -> Orchestrator:
    """构建编排器实例。"""

    engine = create_engine(config.database.dsn)
    session_factory = create_session_factory(engine)
    store = PostgresStore(session_factory)
    audit_sink = DbAuditSink(store)
    audit_recorder = AuditRecorder(audit_sink)
    policy_engine = PolicyEngine(config.policy)
    reviewer = ReviewAgent()
    mcp_client = McpClient(
        base_url=config.mcp.base_url,
        api_key=config.mcp.api_key,
        tls_verify=config.mcp.tls_verify,
    )
    tool_runner = ToolRunner(policy_engine, audit_recorder, mcp_client, store)
    if config.llm.provider not in {"openai", "litellm"}:
        raise ValueError("仅支持 OpenAI/LiteLLM LLM")
    model_config = load_model_config()
    if model_config.default_model == "default":
        model_config.default_model = config.llm.model
    model_router = ModelRouter(model_config)
    if config.policy.allowed_models:
        missing = [
            model
            for model in model_router.list_models()
            if model not in config.policy.allowed_models
        ]
        if missing:
            raise ValueError(f"模型不在允许列表: {sorted(missing)}")
    llm_runner = LlmRunner(
        policy_engine=policy_engine,
        recorder=audit_recorder,
        config=LlmConfig(
            provider=config.llm.provider,
            model=config.llm.model,
            api_key=config.llm.openai_api_key,
            api_base=config.llm.openai_api_base,
        ),
        model_router=model_router,
        review_store=store,
    )
    minio_client = Minio(
        config.minio.endpoint,
        access_key=config.minio.access_key,
        secret_key=config.minio.secret_key,
        secure=config.minio.secure,
    )
    artifact_store = MinioArtifactStore(client=minio_client, bucket=config.minio.bucket)
    graph_pipeline: GraphRagPipeline | None = None
    try:
        importlib.import_module("neo4j")
        graph_pipeline = GraphRagPipeline(
            llm_runner=llm_runner,
            store=store,
            neo4j_store=Neo4jStore(
                uri=config.neo4j.uri,
                user=config.neo4j.user,
                password=config.neo4j.password,
            ),
        )
    except ModuleNotFoundError:
        graph_pipeline = None
    review_graph: AsyncGraph | None = None
    ooda_graph: AsyncGraph | None = None
    storm_graph: AsyncGraph | None = None
    try:
        review_graph = cast(AsyncGraph, build_review_graph(reviewer))
    except RuntimeError:
        review_graph = None
    try:
        crew_agent = None
        try:
            importlib.import_module("crewai")
            crew_agent = CrewCoordinator(llm_runner)
        except ModuleNotFoundError:
            crew_agent = None
        ooda_graph = cast(AsyncGraph, build_ooda_graph(reviewer, crew_agent))
    except RuntimeError:
        ooda_graph = None
    try:
        storm_graph = cast(
            AsyncGraph,
            build_storm_graph(
                StormContext(
                    store=store,
                    artifact_store=artifact_store,
                    tool_runner=tool_runner,
                    reviewer=reviewer,
                    llm_runner=llm_runner,
                    module_registry=ModuleRegistry(session_factory),
                    input_parser=UserInputParser(),
                    graph_pipeline=graph_pipeline,
                    skip_review_validation=config.storm.skip_review_validation,
                )
            ),
        )
    except RuntimeError:
        storm_graph = None

    return Orchestrator(
        policy_engine=policy_engine,
        audit_recorder=audit_recorder,
        reviewer=reviewer,
        store=store,
        artifact_store=artifact_store,
        tool_runner=tool_runner,
        review_graph=review_graph,
        ooda_graph=ooda_graph,
        storm_graph=storm_graph,
    )
