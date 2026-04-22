#!/usr/bin/env python3
"""
coverage_injector.py — 覆盖状态注入器

将 Mini-Savi 的格网覆盖数据通过 vtysh 注入到 FRR isisd，
打通 "覆盖计算 → 路由协议" 的数据通路。

使用方式：
    作为模块被 receive_grid_coverage_data.py 导入调用，
    或独立运行进行手动注入测试。

注入原理：
    通过 Mininet 节点的 network namespace 执行 vtysh 命令，
    将覆盖状态写入 isisd 的 LCSA 本地缓存。
    由于 vtysh 命令需要 FRR 侧先实现 LCSA CLI（第2项任务），
    当前阶段先通过写入临时文件的方式传递覆盖状态，
    供 isisd 轮询读取。
"""

import os
import json
import time
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict


# 覆盖状态文件目录（每个卫星节点一个文件）
COVERAGE_STATE_DIR = Path("/tmp/lcsa_coverage")

# 节流参数
DEFAULT_THROTTLE_INTERVAL = 2.0  # 最小注入间隔（秒）
DEFAULT_BATCH_SIZE = 10          # 批量注入的最大卫星数


class CoverageInjector:
    """覆盖状态注入器 — 将格网覆盖数据传递给 FRR isisd"""

    def __init__(
        self,
        state_dir: Path = COVERAGE_STATE_DIR,
        throttle_interval: float = DEFAULT_THROTTLE_INTERVAL,
        use_vtysh: bool = False,
        vtysh_socket_dir: str = "/tmp",
    ):
        """
        Args:
            state_dir: 覆盖状态文件存放目录
            throttle_interval: 最小注入间隔（秒），防止高频震荡
            use_vtysh: 是否使用 vtysh 直接注入（需要 FRR LCSA CLI 支持）
            vtysh_socket_dir: vtysh socket 目录前缀
        """
        self.state_dir = state_dir
        self.throttle_interval = throttle_interval
        self.use_vtysh = use_vtysh
        self.vtysh_socket_dir = vtysh_socket_dir

        # 节流状态
        self._last_inject_time: Dict[str, float] = {}
        self._pending_updates: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.Lock()

        # 统计
        self.inject_count = 0
        self.throttled_count = 0
        self.error_count = 0

        # 初始化目录
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def inject_coverage(
        self, satellite_id: str, grid_codes: List[str], timestamp: Optional[float] = None
    ) -> bool:
        """
        注入单颗卫星的覆盖状态。

        Args:
            satellite_id: 卫星标识（如 "1", "2"）
            grid_codes: 该卫星当前覆盖的格网编码列表
            timestamp: 覆盖数据时间戳，默认当前时间

        Returns:
            True 表示成功注入，False 表示被节流或出错
        """
        now = time.time()
        if timestamp is None:
            timestamp = now

        # 节流检查
        with self._lock:
            last_time = self._last_inject_time.get(satellite_id, 0)
            if now - last_time < self.throttle_interval:
                self._pending_updates[satellite_id] = grid_codes
                self.throttled_count += 1
                return False
            self._last_inject_time[satellite_id] = now

        # 执行注入
        try:
            if self.use_vtysh:
                return self._inject_via_vtysh(satellite_id, grid_codes, timestamp)
            else:
                return self._inject_via_file(satellite_id, grid_codes, timestamp)
        except Exception as e:
            self.error_count += 1
            print(f"[CoverageInjector] 注入失败 sat={satellite_id}: {e}")
            return False

    def _inject_via_file(
        self, satellite_id: str, grid_codes: List[str], timestamp: float
    ) -> bool:
        """
        通过文件传递覆盖状态。

        每颗卫星对应一个 JSON 文件：/tmp/lcsa_coverage/sat_<id>.json
        isisd 可通过轮询或 inotify 读取这些文件。
        """
        state = {
            "satellite_id": satellite_id,
            "grid_codes": grid_codes,
            "grid_count": len(grid_codes),
            "timestamp": timestamp,
            "coverage_state": "current",  # current / predicted / none
        }

        state_file = self.state_dir / f"sat_{satellite_id}.json"
        tmp_file = state_file.with_suffix(".tmp")

        # 原子写入：先写临时文件再 rename
        with open(tmp_file, "w") as f:
            json.dump(state, f, separators=(",", ":"))
        os.rename(tmp_file, state_file)

        self.inject_count += 1
        return True

    def _inject_via_vtysh(
        self, satellite_id: str, grid_codes: List[str], timestamp: float
    ) -> bool:
        """
        通过 vtysh 直接注入覆盖状态到 isisd。

        需要 FRR 侧实现以下 CLI 命令（第2项任务）：
            isis lcsa coverage <satellite_id> grids <grid_code_list>
        """
        router_name = f"r{satellite_id}"
        vty_socket = f"{self.vtysh_socket_dir}/{router_name}"

        # 构造 vtysh 命令
        grid_str = ",".join(grid_codes[:50])  # 限制单次注入数量
        cmd = [
            "vtysh",
            "--vty_socket", vty_socket,
            "-c", "configure terminal",
            "-c", f"router isis DEAD",
            "-c", f"lcsa coverage satellite {satellite_id} grids {grid_str}",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            self.error_count += 1
            print(f"[CoverageInjector] vtysh 失败 sat={satellite_id}: {result.stderr}")
            return False

        self.inject_count += 1
        return True

    def flush_pending(self):
        """刷新所有被节流的待处理更新。"""
        with self._lock:
            pending = dict(self._pending_updates)
            self._pending_updates.clear()

        for sat_id, grid_codes in pending.items():
            self.inject_coverage(sat_id, grid_codes)

    def write_summary_file(self):
        """
        写入汇总状态文件，供 isisd 一次性读取所有卫星的覆盖状态。
        文件路径：/tmp/lcsa_coverage/summary.json
        """
        summary = {}
        for state_file in self.state_dir.glob("sat_*.json"):
            try:
                with open(state_file) as f:
                    data = json.load(f)
                summary[data["satellite_id"]] = data
            except (json.JSONDecodeError, KeyError):
                continue

        summary_file = self.state_dir / "summary.json"
        tmp_file = summary_file.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        os.rename(tmp_file, summary_file)

    def get_statistics(self) -> Dict:
        """返回注入统计信息。"""
        return {
            "inject_count": self.inject_count,
            "throttled_count": self.throttled_count,
            "error_count": self.error_count,
            "tracked_satellites": len(self._last_inject_time),
            "pending_updates": len(self._pending_updates),
        }

    def cleanup(self):
        """清理所有覆盖状态文件。"""
        for f in self.state_dir.glob("sat_*.json"):
            f.unlink(missing_ok=True)
        summary = self.state_dir / "summary.json"
        if summary.exists():
            summary.unlink()
