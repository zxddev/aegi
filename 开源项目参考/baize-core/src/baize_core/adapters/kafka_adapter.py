"""Kafka 消息队列适配器。

提供事件流处理能力：
- 事件发布
- 事件订阅
- 消费者组管理
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class KafkaConfig:
    """Kafka 配置。"""

    bootstrap_servers: str  # Kafka 服务器地址
    client_id: str = "baize-core"
    group_id: str = "baize-core-group"
    # 认证配置（可选）
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None
    security_protocol: str = "PLAINTEXT"


@dataclass
class Event:
    """事件。"""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """序列化为 JSON。"""
        return json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "payload": self.payload,
                "timestamp": self.timestamp.isoformat(),
                "metadata": self.metadata,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, data: str) -> Event:
        """从 JSON 反序列化。"""
        obj = json.loads(data)
        return cls(
            event_id=obj["event_id"],
            event_type=obj["event_type"],
            payload=obj["payload"],
            timestamp=datetime.fromisoformat(obj["timestamp"]),
            metadata=obj.get("metadata", {}),
        )


class EventPublisher(ABC):
    """事件发布者抽象。"""

    @abstractmethod
    async def publish(self, topic: str, event: Event) -> None:
        """发布事件。"""

    @abstractmethod
    async def publish_batch(self, topic: str, events: list[Event]) -> None:
        """批量发布事件。"""


class EventSubscriber(ABC):
    """事件订阅者抽象。"""

    @abstractmethod
    async def subscribe(
        self,
        topics: list[str],
        handler: Callable[[Event], None],
    ) -> None:
        """订阅主题。"""

    @abstractmethod
    async def unsubscribe(self) -> None:
        """取消订阅。"""


class KafkaEventPublisher(EventPublisher):
    """Kafka 事件发布者。"""

    def __init__(self, config: KafkaConfig) -> None:
        """初始化发布者。

        Args:
            config: Kafka 配置
        """
        self._config = config
        self._producer: Any = None

    async def connect(self) -> None:
        """建立连接。"""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._config.bootstrap_servers,
                client_id=self._config.client_id,
            )
            await self._producer.start()
            logger.info("Kafka 生产者已连接")
        except ImportError:
            logger.warning("aiokafka 未安装，使用模拟模式")

    async def close(self) -> None:
        """关闭连接。"""
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka 生产者已关闭")

    async def publish(self, topic: str, event: Event) -> None:
        """发布事件。"""
        if self._producer is None:
            logger.debug("模拟发布事件: %s -> %s", topic, event.event_type)
            return
        value = event.to_json().encode("utf-8")
        await self._producer.send_and_wait(topic, value)

    async def publish_batch(self, topic: str, events: list[Event]) -> None:
        """批量发布事件。"""
        for event in events:
            await self.publish(topic, event)


class KafkaEventSubscriber(EventSubscriber):
    """Kafka 事件订阅者。"""

    def __init__(self, config: KafkaConfig) -> None:
        """初始化订阅者。

        Args:
            config: Kafka 配置
        """
        self._config = config
        self._consumer: Any = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """建立连接。"""
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                bootstrap_servers=self._config.bootstrap_servers,
                group_id=self._config.group_id,
                client_id=self._config.client_id,
                auto_offset_reset="latest",
            )
            logger.info("Kafka 消费者已创建")
        except ImportError:
            logger.warning("aiokafka 未安装，使用模拟模式")

    async def close(self) -> None:
        """关闭连接。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka 消费者已关闭")

    async def subscribe(
        self,
        topics: list[str],
        handler: Callable[[Event], None],
    ) -> None:
        """订阅主题。"""
        if self._consumer is None:
            logger.debug("模拟订阅: %s", topics)
            return
        self._consumer.subscribe(topics)
        await self._consumer.start()
        self._running = True
        self._task = asyncio.create_task(self._consume_loop(handler))

    async def _consume_loop(self, handler: Callable[[Event], None]) -> None:
        """消费循环。"""
        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    event = Event.from_json(msg.value.decode("utf-8"))
                    handler(event)
                except Exception as e:
                    logger.warning("事件处理失败: %s", e)
        except asyncio.CancelledError:
            pass

    async def unsubscribe(self) -> None:
        """取消订阅。"""
        self._running = False
        if self._consumer:
            self._consumer.unsubscribe()


# 预定义的主题
class KafkaTopics:
    """预定义 Kafka 主题。"""

    # 情报事件
    INTEL_NEW = "intel.new"  # 新情报
    INTEL_UPDATE = "intel.update"  # 情报更新
    INTEL_ALERT = "intel.alert"  # 情报告警

    # 任务事件
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # 审计事件
    AUDIT_TOOL_CALL = "audit.tool_call"
    AUDIT_MODEL_CALL = "audit.model_call"
    AUDIT_POLICY_DECISION = "audit.policy_decision"

    # 系统事件
    SYSTEM_HEALTH = "system.health"
    SYSTEM_ERROR = "system.error"

    # 证据链事件
    EVIDENCE_CREATED = "evidence.created"
    ARTIFACT_STORED = "artifact.stored"


class KafkaEventManager:
    """Kafka 事件管理器。

    提供统一的事件发布/订阅接口，支持：
    - 任务生命周期事件
    - 审计事件
    - 情报事件
    """

    def __init__(self, config: KafkaConfig) -> None:
        """初始化事件管理器。

        Args:
            config: Kafka 配置
        """
        self._config = config
        self._publisher: KafkaEventPublisher | None = None
        self._subscriber: KafkaEventSubscriber | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """是否已连接。"""
        return self._connected

    async def connect(self) -> None:
        """建立连接。"""
        if self._connected:
            return

        self._publisher = KafkaEventPublisher(self._config)
        self._subscriber = KafkaEventSubscriber(self._config)

        await self._publisher.connect()
        await self._subscriber.connect()
        self._connected = True
        logger.info("Kafka 事件管理器已连接")

    async def close(self) -> None:
        """关闭连接。"""
        if not self._connected:
            return

        if self._publisher:
            await self._publisher.close()
        if self._subscriber:
            await self._subscriber.close()

        self._connected = False
        logger.info("Kafka 事件管理器已关闭")

    async def __aenter__(self) -> KafkaEventManager:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    # ============ 任务事件 ============

    async def publish_task_created(
        self,
        task_id: str,
        task_type: str,
        query: str,
        user_id: str | None = None,
    ) -> None:
        """发布任务创建事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="task.created",
            payload={
                "task_id": task_id,
                "task_type": task_type,
                "query": query,
                "user_id": user_id,
            },
        )
        await self._publish(KafkaTopics.TASK_CREATED, event)

    async def publish_task_started(
        self,
        task_id: str,
        phase: str,
    ) -> None:
        """发布任务开始事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="task.started",
            payload={
                "task_id": task_id,
                "phase": phase,
            },
        )
        await self._publish(KafkaTopics.TASK_STARTED, event)

    async def publish_task_progress(
        self,
        task_id: str,
        phase: str,
        progress: float,
        message: str = "",
    ) -> None:
        """发布任务进度事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="task.progress",
            payload={
                "task_id": task_id,
                "phase": phase,
                "progress": progress,
                "message": message,
            },
        )
        await self._publish(KafkaTopics.TASK_PROGRESS, event)

    async def publish_task_completed(
        self,
        task_id: str,
        result_summary: str,
        duration_ms: int,
    ) -> None:
        """发布任务完成事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="task.completed",
            payload={
                "task_id": task_id,
                "result_summary": result_summary,
                "duration_ms": duration_ms,
            },
        )
        await self._publish(KafkaTopics.TASK_COMPLETED, event)

    async def publish_task_failed(
        self,
        task_id: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """发布任务失败事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="task.failed",
            payload={
                "task_id": task_id,
                "error_type": error_type,
                "error_message": error_message,
            },
        )
        await self._publish(KafkaTopics.TASK_FAILED, event)

    # ============ 审计事件 ============

    async def publish_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        task_id: str,
        success: bool,
        duration_ms: int,
        error_message: str | None = None,
    ) -> None:
        """发布工具调用审计事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="audit.tool_call",
            payload={
                "trace_id": trace_id,
                "tool_name": tool_name,
                "task_id": task_id,
                "success": success,
                "duration_ms": duration_ms,
                "error_message": error_message,
            },
        )
        await self._publish(KafkaTopics.AUDIT_TOOL_CALL, event)

    async def publish_model_call(
        self,
        trace_id: str,
        model: str,
        stage: str,
        task_id: str,
        success: bool,
        duration_ms: int,
        token_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """发布模型调用审计事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="audit.model_call",
            payload={
                "trace_id": trace_id,
                "model": model,
                "stage": stage,
                "task_id": task_id,
                "success": success,
                "duration_ms": duration_ms,
                "token_count": token_count,
                "error_message": error_message,
            },
        )
        await self._publish(KafkaTopics.AUDIT_MODEL_CALL, event)

    async def publish_policy_decision(
        self,
        decision_id: str,
        request_id: str,
        action: str,
        allow: bool,
        reason: str,
        task_id: str,
    ) -> None:
        """发布策略决策审计事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="audit.policy_decision",
            payload={
                "decision_id": decision_id,
                "request_id": request_id,
                "action": action,
                "allow": allow,
                "reason": reason,
                "task_id": task_id,
            },
        )
        await self._publish(KafkaTopics.AUDIT_POLICY_DECISION, event)

    # ============ 情报事件 ============

    async def publish_intel_new(
        self,
        evidence_uid: str,
        source: str,
        summary: str,
        confidence: float,
    ) -> None:
        """发布新情报事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="intel.new",
            payload={
                "evidence_uid": evidence_uid,
                "source": source,
                "summary": summary,
                "confidence": confidence,
            },
        )
        await self._publish(KafkaTopics.INTEL_NEW, event)

    async def publish_intel_alert(
        self,
        alert_id: str,
        severity: str,
        title: str,
        description: str,
        related_evidence: list[str],
    ) -> None:
        """发布情报告警事件。"""
        from uuid import uuid4

        event = Event(
            event_id=str(uuid4()),
            event_type="intel.alert",
            payload={
                "alert_id": alert_id,
                "severity": severity,
                "title": title,
                "description": description,
                "related_evidence": related_evidence,
            },
        )
        await self._publish(KafkaTopics.INTEL_ALERT, event)

    # ============ 内部方法 ============

    async def _publish(self, topic: str, event: Event) -> None:
        """内部发布方法。"""
        if not self._publisher:
            logger.debug("Kafka 未连接，跳过事件发布: %s", event.event_type)
            return
        try:
            await self._publisher.publish(topic, event)
        except Exception as exc:
            logger.warning("事件发布失败: %s - %s", topic, exc)

    async def subscribe(
        self,
        topics: list[str],
        handler: Callable[[Event], None],
    ) -> None:
        """订阅主题。"""
        if not self._subscriber:
            logger.debug("Kafka 未连接，跳过订阅: %s", topics)
            return
        await self._subscriber.subscribe(topics, handler)

    async def unsubscribe(self) -> None:
        """取消订阅。"""
        if self._subscriber:
            await self._subscriber.unsubscribe()


# 全局事件管理器实例（延迟初始化）
_global_event_manager: KafkaEventManager | None = None


def get_kafka_config_from_env() -> KafkaConfig:
    """从环境变量获取 Kafka 配置。"""
    import os

    return KafkaConfig(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        client_id=os.getenv("KAFKA_CLIENT_ID", "baize-core"),
        group_id=os.getenv("KAFKA_GROUP_ID", "baize-core-group"),
        sasl_mechanism=os.getenv("KAFKA_SASL_MECHANISM"),
        sasl_username=os.getenv("KAFKA_SASL_USERNAME"),
        sasl_password=os.getenv("KAFKA_SASL_PASSWORD"),
        security_protocol=os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
    )


async def get_event_manager() -> KafkaEventManager:
    """获取全局事件管理器。"""
    global _global_event_manager
    if _global_event_manager is None:
        config = get_kafka_config_from_env()
        _global_event_manager = KafkaEventManager(config)
        await _global_event_manager.connect()
    return _global_event_manager


async def close_event_manager() -> None:
    """关闭全局事件管理器。"""
    global _global_event_manager
    if _global_event_manager is not None:
        await _global_event_manager.close()
        _global_event_manager = None
