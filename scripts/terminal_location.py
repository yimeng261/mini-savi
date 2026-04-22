#!/usr/bin/env python3
"""
terminal_location.py — 终端位置管理模块

实现基于全球离散格网的终端位置管理：
- 终端位置区注册、查询、更新、保活
- 分布式锚点查询与同步
- 多星覆盖边界冲突处理
- 终端跨位置区移动时的切换逻辑

与 Mini-Savi 格网覆盖系统和 FRR 路由协议协同工作。
"""

import time
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum


class TerminalState(Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    HANDOVER = "handover"      # 正在切换
    EXPIRED = "expired"


@dataclass
class TerminalRecord:
    """终端注册记录"""
    terminal_id: str
    grid_code: str              # 当前所在格网编码
    satellite_id: int           # 接入卫星 ID
    state: TerminalState = TerminalState.REGISTERED
    register_time: float = 0.0
    last_update: float = 0.0
    last_keepalive: float = 0.0
    prev_grid_code: str = ""    # 上一个格网（用于切换追踪）
    prev_satellite_id: int = 0


@dataclass
class AnchorRecord:
    """锚点记录 — 存储终端的归属信息"""
    terminal_id: str
    home_grid: str              # 归属格网
    home_satellite: int         # 归属卫星
    current_grid: str           # 当前格网
    current_satellite: int      # 当前接入卫星
    timestamp: float = 0.0


class TerminalLocationManager:
    """终端位置管理器"""

    def __init__(self, keepalive_timeout: float = 60.0,
                 handover_threshold: float = 5.0):
        """
        Args:
            keepalive_timeout: 保活超时时间（秒）
            handover_threshold: 切换判定阈值（秒），连续在新格网停留超过此时间才确认切换
        """
        self.keepalive_timeout = keepalive_timeout
        self.handover_threshold = handover_threshold

        # 终端注册表: terminal_id -> TerminalRecord
        self.terminals: Dict[str, TerminalRecord] = {}

        # 格网到终端的反向索引: grid_code -> set of terminal_ids
        self.grid_terminals: Dict[str, Set[str]] = defaultdict(set)

        # 锚点表: terminal_id -> AnchorRecord
        self.anchors: Dict[str, AnchorRecord] = {}

        # 卫星覆盖映射: grid_code -> list of (satellite_id, priority)
        self.grid_coverage: Dict[str, List[Tuple[int, int]]] = defaultdict(list)

        # 统计
        self.stats = {
            "registrations": 0,
            "updates": 0,
            "handovers": 0,
            "expirations": 0,
            "queries": 0,
            "conflicts_resolved": 0,
        }

        self._lock = threading.RLock()

    # ==================== 终端注册 ====================

    def register(self, terminal_id: str, grid_code: str,
                 satellite_id: int) -> bool:
        """注册终端到指定格网和卫星"""
        now = time.time()
        with self._lock:
            if terminal_id in self.terminals:
                # 已注册，更新
                return self.update_location(terminal_id, grid_code, satellite_id)

            record = TerminalRecord(
                terminal_id=terminal_id,
                grid_code=grid_code,
                satellite_id=satellite_id,
                state=TerminalState.REGISTERED,
                register_time=now,
                last_update=now,
                last_keepalive=now,
            )
            self.terminals[terminal_id] = record
            self.grid_terminals[grid_code].add(terminal_id)

            # 创建锚点记录
            self.anchors[terminal_id] = AnchorRecord(
                terminal_id=terminal_id,
                home_grid=grid_code,
                home_satellite=satellite_id,
                current_grid=grid_code,
                current_satellite=satellite_id,
                timestamp=now,
            )

            self.stats["registrations"] += 1
            return True

    # ==================== 位置更新 ====================

    def update_location(self, terminal_id: str, new_grid: str,
                        new_satellite: int) -> bool:
        """更新终端位置（可能触发切换）"""
        now = time.time()
        with self._lock:
            record = self.terminals.get(terminal_id)
            if not record:
                return False

            record.last_update = now
            record.last_keepalive = now

            if record.grid_code == new_grid and record.satellite_id == new_satellite:
                # 位置未变，仅更新时间
                return True

            # 位置变化 → 判断是否需要切换
            old_grid = record.grid_code
            old_sat = record.satellite_id

            record.prev_grid_code = old_grid
            record.prev_satellite_id = old_sat
            record.grid_code = new_grid
            record.satellite_id = new_satellite
            record.state = TerminalState.HANDOVER

            # 更新格网索引
            self.grid_terminals[old_grid].discard(terminal_id)
            self.grid_terminals[new_grid].add(terminal_id)

            # 更新锚点
            anchor = self.anchors.get(terminal_id)
            if anchor:
                anchor.current_grid = new_grid
                anchor.current_satellite = new_satellite
                anchor.timestamp = now

            # 确认切换完成
            record.state = TerminalState.ACTIVE
            self.stats["handovers"] += 1
            self.stats["updates"] += 1
            return True

    # ==================== 查询 ====================

    def query_terminal(self, terminal_id: str) -> Optional[Dict]:
        """查询终端当前位置"""
        self.stats["queries"] += 1
        with self._lock:
            record = self.terminals.get(terminal_id)
            if not record:
                return None
            return {
                "terminal_id": record.terminal_id,
                "grid_code": record.grid_code,
                "satellite_id": record.satellite_id,
                "state": record.state.value,
                "last_update": record.last_update,
            }

    def query_grid(self, grid_code: str) -> List[str]:
        """查询某格网内的所有终端"""
        self.stats["queries"] += 1
        with self._lock:
            return list(self.grid_terminals.get(grid_code, set()))

    def query_anchor(self, terminal_id: str) -> Optional[Dict]:
        """查询终端的锚点信息"""
        self.stats["queries"] += 1
        with self._lock:
            anchor = self.anchors.get(terminal_id)
            if not anchor:
                return None
            return {
                "terminal_id": anchor.terminal_id,
                "home_grid": anchor.home_grid,
                "home_satellite": anchor.home_satellite,
                "current_grid": anchor.current_grid,
                "current_satellite": anchor.current_satellite,
            }

    # ==================== 保活 ====================

    def keepalive(self, terminal_id: str) -> bool:
        """终端保活"""
        with self._lock:
            record = self.terminals.get(terminal_id)
            if not record:
                return False
            record.last_keepalive = time.time()
            record.state = TerminalState.ACTIVE
            return True

    def expire_stale(self) -> List[str]:
        """清理超时终端"""
        now = time.time()
        expired = []
        with self._lock:
            for tid, record in list(self.terminals.items()):
                if now - record.last_keepalive > self.keepalive_timeout:
                    record.state = TerminalState.EXPIRED
                    self.grid_terminals[record.grid_code].discard(tid)
                    expired.append(tid)
                    self.stats["expirations"] += 1

            for tid in expired:
                del self.terminals[tid]
                self.anchors.pop(tid, None)

        return expired

    # ==================== 多星覆盖边界冲突处理 ====================

    def update_grid_coverage(self, grid_code: str,
                             covering_satellites: List[Tuple[int, int]]):
        """
        更新格网的覆盖卫星列表。

        Args:
            grid_code: 格网编码
            covering_satellites: [(satellite_id, priority), ...] 按优先级排序
        """
        with self._lock:
            self.grid_coverage[grid_code] = sorted(
                covering_satellites, key=lambda x: -x[1]  # 高优先级在前
            )

    def resolve_coverage_conflict(self, grid_code: str,
                                  terminal_id: str) -> Optional[int]:
        """
        解决多星覆盖冲突：为终端选择最佳接入卫星。

        选择策略：
        1. 优先级最高的卫星
        2. 优先级相同时，选择覆盖持续时间最长的
        3. 如果终端当前已接入某卫星且该卫星仍在覆盖列表中，保持不变（避免乒乓切换）
        """
        with self._lock:
            candidates = self.grid_coverage.get(grid_code, [])
            if not candidates:
                return None

            record = self.terminals.get(terminal_id)
            if record:
                # 当前卫星仍在覆盖列表中 → 保持不变
                for sat_id, prio in candidates:
                    if sat_id == record.satellite_id:
                        return sat_id

            # 选择优先级最高的
            self.stats["conflicts_resolved"] += 1
            return candidates[0][0]

    # ==================== 状态导出 ====================

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return {
                **self.stats,
                "active_terminals": len(self.terminals),
                "active_grids": len([g for g, t in self.grid_terminals.items() if t]),
                "anchors": len(self.anchors),
            }

    def export_state(self, filepath: str):
        """导出当前状态到 JSON 文件"""
        with self._lock:
            state = {
                "timestamp": time.time(),
                "statistics": self.get_statistics(),
                "terminals": {
                    tid: {
                        "grid_code": r.grid_code,
                        "satellite_id": r.satellite_id,
                        "state": r.state.value,
                    }
                    for tid, r in self.terminals.items()
                },
            }
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

