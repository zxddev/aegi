"""SpiderFoot OSINT 适配器。

提供开源情报枚举能力：
- 实体枚举（域名、IP、邮箱等）
- 结果转换为 Evidence
- 限额与人工确认（高风险/高成本）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import aiohttp

logger = logging.getLogger(__name__)


class ScanType(str, Enum):
    """扫描类型。"""

    ALL = "ALL"  # 全量扫描
    FOOTPRINT = "FOOTPRINT"  # 足迹扫描
    INVESTIGATE = "INVESTIGATE"  # 调查扫描
    PASSIVE = "PASSIVE"  # 被动扫描


class EntityType(str, Enum):
    """实体类型。"""

    DOMAIN = "DOMAIN"
    IP_ADDRESS = "IP_ADDRESS"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    PERSON_NAME = "PERSON_NAME"
    BITCOIN_ADDRESS = "BITCOIN_ADDRESS"
    NETBLOCK = "NETBLOCK"
    USERNAME = "USERNAME"


@dataclass
class SpiderFootConfig:
    """SpiderFoot 配置。"""

    base_url: str = "http://localhost:5001"
    api_key: str = ""
    timeout: int = 60
    # 限额配置
    max_scans_per_hour: int = 5
    require_confirmation: bool = True  # 高风险操作需确认


@dataclass
class ScanTarget:
    """扫描目标。"""

    target: str
    entity_type: EntityType
    scan_type: ScanType = ScanType.PASSIVE
    modules: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    """扫描结果。"""

    scan_id: str
    target: str
    status: str  # RUNNING, FINISHED, FAILED
    started_at: datetime
    finished_at: datetime | None
    findings: list[Finding]


@dataclass
class Finding:
    """发现的情报。"""

    finding_id: str
    data_type: str  # 数据类型（IP_ADDRESS, EMAIL, etc.）
    data: str  # 发现的数据
    module: str  # 发现该数据的模块
    source: str  # 数据来源
    confidence: float  # 置信度
    metadata: dict[str, Any] = field(default_factory=dict)


class SpiderFootClient:
    """SpiderFoot API 客户端。"""

    def __init__(self, config: SpiderFootConfig) -> None:
        """初始化客户端。

        Args:
            config: 配置
        """
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._scan_count = 0
        self._last_scan_hour: int | None = None

    async def connect(self) -> None:
        """建立连接。"""
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        timeout = aiohttp.ClientTimeout(total=self._config.timeout)
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
        )
        logger.info("SpiderFoot 客户端已连接: %s", self._config.base_url)

    async def close(self) -> None:
        """关闭连接。"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("SpiderFoot 客户端已关闭")

    async def __aenter__(self) -> SpiderFootClient:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    # ============ 扫描管理 ============

    async def start_scan(
        self,
        target: ScanTarget,
        confirmed: bool = False,
    ) -> str:
        """启动扫描。

        Args:
            target: 扫描目标
            confirmed: 是否已确认（用于高风险操作）

        Returns:
            扫描 ID

        Raises:
            RuntimeError: 限额超出或需要确认
        """
        # 检查限额
        self._check_rate_limit()

        # 检查是否需要确认
        if self._config.require_confirmation and not confirmed:
            if target.scan_type != ScanType.PASSIVE:
                raise RuntimeError(
                    f"扫描类型 {target.scan_type} 需要人工确认，"
                    "请设置 confirmed=True 以继续"
                )

        payload = {
            "scanname": f"scan_{uuid4().hex[:8]}",
            "scantarget": target.target,
            "usecase": target.scan_type.value,
        }

        if target.modules:
            payload["modulelist"] = ",".join(target.modules)

        result = await self._post("/startscan", payload)
        scan_id = result.get("scanId", "")

        self._increment_scan_count()
        logger.info("启动扫描: %s -> %s", target.target, scan_id)
        return scan_id

    async def get_scan_status(self, scan_id: str) -> str:
        """获取扫描状态。"""
        result = await self._get(f"/scanstatus?id={scan_id}")
        return result.get("status", "UNKNOWN")

    async def get_scan_results(self, scan_id: str) -> ScanResult:
        """获取扫描结果。"""
        # 获取基本信息
        info = await self._get(f"/scaninfo?id={scan_id}")
        # 获取发现
        data = await self._get(f"/scanresults?id={scan_id}")

        findings = []
        for item in data:
            findings.append(
                Finding(
                    finding_id=str(uuid4()),
                    data_type=item.get("type", ""),
                    data=item.get("data", ""),
                    module=item.get("module", ""),
                    source=item.get("source", ""),
                    confidence=self._estimate_confidence(item),
                    metadata=item,
                )
            )

        started_at = datetime.fromisoformat(
            info.get("started", datetime.now(UTC).isoformat())
        )
        finished_str = info.get("finished")
        finished_at = datetime.fromisoformat(finished_str) if finished_str else None

        return ScanResult(
            scan_id=scan_id,
            target=info.get("target", ""),
            status=info.get("status", "UNKNOWN"),
            started_at=started_at,
            finished_at=finished_at,
            findings=findings,
        )

    async def stop_scan(self, scan_id: str) -> None:
        """停止扫描。"""
        await self._get(f"/stopscan?id={scan_id}")
        logger.info("停止扫描: %s", scan_id)

    async def delete_scan(self, scan_id: str) -> None:
        """删除扫描。"""
        await self._get(f"/scandelete?id={scan_id}")
        logger.info("删除扫描: %s", scan_id)

    async def list_scans(self) -> list[dict[str, Any]]:
        """列出所有扫描。"""
        return await self._get("/scanlist")

    # ============ 模块管理 ============

    async def list_modules(self) -> list[dict[str, Any]]:
        """列出可用模块。"""
        return await self._get("/modules")

    async def get_passive_modules(self) -> list[str]:
        """获取被动模块列表（低风险）。"""
        modules = await self.list_modules()
        return [
            m.get("name", "")
            for m in modules
            if m.get("cats", {}).get("passive", False)
        ]

    # ============ Evidence 转换 ============

    def findings_to_evidence(
        self,
        findings: list[Finding],
        task_id: str,
    ) -> list[dict[str, Any]]:
        """将 Finding 转换为 Evidence 格式。

        Args:
            findings: 发现列表
            task_id: 关联任务 ID

        Returns:
            Evidence 格式的字典列表
        """
        evidence_list = []
        for finding in findings:
            evidence_list.append(
                {
                    "evidence_uid": str(uuid4()),
                    "chunk_uid": None,  # 需要后续关联
                    "summary": f"{finding.data_type}: {finding.data}",
                    "confidence": finding.confidence,
                    "extraction_method": f"spiderfoot/{finding.module}",
                    "uri": finding.source,
                    "metadata": {
                        "spiderfoot_data_type": finding.data_type,
                        "spiderfoot_module": finding.module,
                        "task_id": task_id,
                    },
                }
            )
        return evidence_list

    # ============ 内部方法 ============

    def _check_rate_limit(self) -> None:
        """检查限额。"""
        current_hour = datetime.now(UTC).hour

        # 重置计数器
        if self._last_scan_hour != current_hour:
            self._scan_count = 0
            self._last_scan_hour = current_hour

        if self._scan_count >= self._config.max_scans_per_hour:
            raise RuntimeError(
                f"扫描限额已用完：每小时最多 {self._config.max_scans_per_hour} 次扫描"
            )

    def _increment_scan_count(self) -> None:
        """增加扫描计数。"""
        self._scan_count += 1

    def _estimate_confidence(self, item: dict[str, Any]) -> float:
        """估算置信度。"""
        # 根据模块和数据类型估算置信度
        module = item.get("module", "").lower()
        # 直接来源（如 DNS 查询）置信度高
        high_confidence_modules = ["sfp_dns", "sfp_whois", "sfp_certificate"]
        if any(m in module for m in high_confidence_modules):
            return 0.9

        # 第三方数据库置信度中等
        medium_confidence_modules = ["sfp_shodan", "sfp_censys", "sfp_virustotal"]
        if any(m in module for m in medium_confidence_modules):
            return 0.7

        # 其他来源置信度较低
        return 0.5

    async def _get(self, path: str) -> Any:
        """发送 GET 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"SpiderFoot API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"SpiderFoot API 错误: {resp.status} - {text}")
            return await resp.json()


def get_spiderfoot_config_from_env() -> SpiderFootConfig:
    """从环境变量获取配置。"""
    import os

    return SpiderFootConfig(
        base_url=os.getenv("SPIDERFOOT_URL", "http://localhost:5001"),
        api_key=os.getenv("SPIDERFOOT_API_KEY", ""),
        timeout=int(os.getenv("SPIDERFOOT_TIMEOUT", "60")),
        max_scans_per_hour=int(os.getenv("SPIDERFOOT_MAX_SCANS_PER_HOUR", "5")),
        require_confirmation=os.getenv(
            "SPIDERFOOT_REQUIRE_CONFIRMATION", "true"
        ).lower()
        == "true",
    )
