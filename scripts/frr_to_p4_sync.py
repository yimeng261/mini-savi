#!/usr/bin/env python3
"""
frr_to_p4_sync.py — FRR 路由表到 P4 转发表的同步脚本

功能：
    1. 从 FRR vtysh 读取路由表和 LCSA 覆盖状态
    2. 转换为 P4 match-action 表项
    3. 通过 simple_switch_CLI 下发到 BMv2

使用方式：
    # 单次同步
    python3 frr_to_p4_sync.py --once

    # 持续同步（每 interval 秒）
    python3 frr_to_p4_sync.py --interval 5

    # 指定节点范围
    python3 frr_to_p4_sync.py --nodes 1-66 --interval 5
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# BMv2 thrift 端口基址
BMV2_THRIFT_BASE = 9090

# LCSA 覆盖状态文件目录
LCSA_STATE_DIR = Path("/tmp/lcsa_coverage")


class FRRRouteEntry:
    """FRR 路由表条目"""

    def __init__(self, prefix: str, nexthop: str, interface: str, metric: int = 0):
        self.prefix = prefix
        self.nexthop = nexthop
        self.interface = interface
        self.metric = metric

    def __repr__(self):
        return f"Route({self.prefix} via {self.nexthop} dev {self.interface})"


class P4TableEntry:
    """P4 表项"""

    def __init__(self, table: str, match: str, action: str, params: str):
        self.table = table
        self.match = match
        self.action = action
        self.params = params

    def to_cli_command(self) -> str:
        return f"table_add {self.table} {self.action} {self.match} => {self.params}"


def run_vtysh(node_id: int, commands: List[str]) -> str:
    """在指定节点上执行 vtysh 命令"""
    vty_socket = f"/tmp/r{node_id}"
    cmd = ["vtysh", "--vty_socket", vty_socket]
    for c in commands:
        cmd.extend(["-c", c])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def parse_isis_routes(vtysh_output: str) -> List[FRRRouteEntry]:
    """解析 vtysh 'show ip route isis' 输出"""
    routes = []
    # 匹配格式: I>* prefix [metric] via nexthop, interface
    pattern = re.compile(
        r'[Ii]\S*\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+'
        r'\[(\d+)/(\d+)\]\s+via\s+(\d+\.\d+\.\d+\.\d+),\s+(\S+)'
    )
    for line in vtysh_output.splitlines():
        m = pattern.search(line)
        if m:
            routes.append(FRRRouteEntry(
                prefix=m.group(1),
                nexthop=m.group(4),
                interface=m.group(5).rstrip(","),
                metric=int(m.group(3))
            ))
    return routes


def parse_isis_database_lcsa(vtysh_output: str) -> List[Dict]:
    """解析 vtysh 'show isis database detail' 中的 LCSA 条目"""
    lcsa_entries = []
    pattern = re.compile(
        r'LCSA:\s+sat=(\d+)\s+state=(\w+)\s+prio=(\d+)\s+'
        r'dur=(\d+)\s+ts=(\d+)\s+grids=(\d+)'
    )
    for line in vtysh_output.splitlines():
        m = pattern.search(line)
        if m:
            lcsa_entries.append({
                "satellite_id": int(m.group(1)),
                "state": m.group(2),
                "priority": int(m.group(3)),
                "duration": int(m.group(4)),
                "timestamp": int(m.group(5)),
                "grid_count": int(m.group(6)),
            })
    return lcsa_entries


def ip_to_mac(ip: str) -> str:
    """将 IP 地址转换为伪 MAC 地址（用于 P4 表项）"""
    parts = ip.split(".")
    return f"00:00:{int(parts[0]):02x}:{int(parts[1]):02x}:{int(parts[2]):02x}:{int(parts[3]):02x}"


def prefix_to_lpm(prefix: str) -> str:
    """将 CIDR 前缀转换为 P4 LPM 匹配格式"""
    ip, mask_len = prefix.split("/")
    parts = ip.split(".")
    hex_ip = "0x" + "".join(f"{int(p):02x}" for p in parts)
    return f"{hex_ip}/{mask_len}"


def interface_to_port(intf: str) -> int:
    """从接口名推断 BMv2 端口号（简化映射）"""
    # eth-r1r2 → 端口号基于接口在节点上的顺序
    # 这里用简单的 hash 映射，实际部署需要根据拓扑精确映射
    m = re.match(r'eth-r(\d+)r(\d+)', intf)
    if m:
        return int(m.group(2)) % 256
    return 1


def routes_to_p4_entries(routes: List[FRRRouteEntry]) -> List[P4TableEntry]:
    """将 FRR 路由转换为 P4 ipv4_lpm 表项"""
    entries = []
    for route in routes:
        mac = ip_to_mac(route.nexthop)
        port = interface_to_port(route.interface)
        entries.append(P4TableEntry(
            table="MyIngress.ipv4_lpm",
            match=prefix_to_lpm(route.prefix),
            action="MyIngress.ipv4_forward",
            params=f"{mac} {port}"
        ))
    return entries


def lcsa_to_p4_entries(lcsa_entries: List[Dict]) -> List[P4TableEntry]:
    """将 LCSA 覆盖状态转换为 P4 satellite_forwarding 表项"""
    entries = []
    for lcsa in lcsa_entries:
        sat_id = lcsa["satellite_id"]
        # 卫星 ID → 伪 MAC 和端口（简化映射）
        mac = f"00:00:00:00:00:{sat_id:02x}"
        port = sat_id % 256
        entries.append(P4TableEntry(
            table="MyIngress.satellite_forwarding",
            match=str(sat_id),
            action="MyIngress.ipv4_forward",
            params=f"{mac} {port}"
        ))
    return entries


def apply_p4_entries(node_id: int, entries: List[P4TableEntry],
                     clear_first: bool = True) -> int:
    """将表项下发到 BMv2"""
    thrift_port = BMV2_THRIFT_BASE + node_id
    applied = 0

    commands = []
    if clear_first:
        # 收集需要清空的表
        tables = set(e.table for e in entries)
        for t in tables:
            commands.append(f"table_clear {t}")

    for entry in entries:
        commands.append(entry.to_cli_command())

    if not commands:
        return 0

    cmd_input = "\n".join(commands) + "\n"
    try:
        result = subprocess.run(
            ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
            input=cmd_input, capture_output=True, text=True, timeout=10
        )
        # 统计成功的条目
        for line in result.stdout.splitlines():
            if "Entry has been added" in line:
                applied += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return applied


def sync_node(node_id: int) -> Dict:
    """同步单个节点的路由表到 P4"""
    stats = {"node": node_id, "routes": 0, "lcsa": 0, "applied": 0}

    # 读取 FRR 路由表
    route_output = run_vtysh(node_id, ["show ip route isis"])
    routes = parse_isis_routes(route_output)
    stats["routes"] = len(routes)

    # 读取 LCSA 状态
    db_output = run_vtysh(node_id, ["show isis database detail"])
    lcsa = parse_isis_database_lcsa(db_output)
    stats["lcsa"] = len(lcsa)

    # 转换为 P4 表项
    p4_entries = routes_to_p4_entries(routes) + lcsa_to_p4_entries(lcsa)

    # 下发到 BMv2
    stats["applied"] = apply_p4_entries(node_id, p4_entries)

    return stats


def sync_all(node_range: Tuple[int, int]) -> List[Dict]:
    """同步所有节点"""
    results = []
    for node_id in range(node_range[0], node_range[1] + 1):
        stats = sync_node(node_id)
        results.append(stats)
        if stats["applied"] > 0:
            print(f"  r{node_id}: {stats['routes']} routes, "
                  f"{stats['lcsa']} LCSA entries, "
                  f"{stats['applied']} P4 entries applied")
    return results


def parse_node_range(s: str) -> Tuple[int, int]:
    """解析节点范围字符串，如 '1-66'"""
    if "-" in s:
        parts = s.split("-")
        return int(parts[0]), int(parts[1])
    return int(s), int(s)


def main():
    parser = argparse.ArgumentParser(description="FRR → P4 转发表同步")
    parser.add_argument("--once", action="store_true", help="单次同步后退出")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="同步间隔（秒），默认 5")
    parser.add_argument("--nodes", type=str, default="1-66",
                        help="节点范围，如 '1-66'")
    args = parser.parse_args()

    node_range = parse_node_range(args.nodes)
    print(f"FRR → P4 同步器")
    print(f"节点范围: r{node_range[0]} - r{node_range[1]}")
    print(f"同步间隔: {args.interval}s")
    print("=" * 50)

    if args.once:
        results = sync_all(node_range)
        total = sum(r["applied"] for r in results)
        print(f"\n同步完成: 共下发 {total} 条 P4 表项")
    else:
        try:
            cycle = 0
            while True:
                cycle += 1
                print(f"\n[Cycle {cycle}] 同步中...")
                results = sync_all(node_range)
                total = sum(r["applied"] for r in results)
                print(f"[Cycle {cycle}] 完成: {total} 条表项")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n同步器已停止")


if __name__ == "__main__":
    main()
