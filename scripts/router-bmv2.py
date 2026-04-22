#!/usr/bin/python3
"""
router-bmv2.py — BMv2 + FRR 混合拓扑

基于 router-host.py 改造，将纯 Linux 转发替换为 BMv2 软件交换机，
同时保留 FRR (zebra + isisd) 作为控制平面。

架构：
    每个卫星节点 = LinuxRouter (运行 FRR) + BMv2 Switch (运行 P4 程序)
    FRR 负责路由计算 → 通过 frr_to_p4_sync.py 下发转发表到 BMv2

依赖：
    - BMv2 (behavioral-model): simple_switch_grpc 或 simple_switch
    - p4c: P4 编译器
    - FRR: zebra + isisd
    - Mininet

使用方式：
    sudo python3 router-bmv2.py
"""

import os
import sys
import math
import time
import json
import subprocess
import threading
import socketserver
from pathlib import Path

from mininet.net import Mininet
from mininet.node import Node, Switch
from mininet.link import Link, TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI

from control_plane_utils import compute_link_state_updates

# 路径配置
SCRIPT_DIR = Path(__file__).resolve().parent
P4SRC_DIR = SCRIPT_DIR.parent / "p4src"
P4_PROGRAM = P4SRC_DIR / "lcsa_switch.p4"
P4_JSON = P4SRC_DIR / "lcsa_switch.json"
RUNTIME_OUTPUT_DIR = SCRIPT_DIR.parent / "outputs" / "runtime"

# BMv2 配置
BMV2_SWITCH = "simple_switch"  # 或 simple_switch_grpc
BMV2_LOG_DIR = Path("/tmp/bmv2_logs")

# 全局状态
sat_lines = {}
sat_coor_lines = {}
sats_str = {}
sats_coor_str = {}
net = None
ISLs = {}
ISLs_origin = {}
sats = {}
bmv2_switches = {}  # sat_idx -> BMv2Switch 实例
TOPOLOGY = {"num_sats": 0, "sats_per_plane": 0, "num_planes": 0}
LINK_STATES = {}


class LinuxRouter(Node):
    """带 IP 转发的 Mininet 节点（运行 FRR）"""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl net.ipv4.ip_forward=1")
        self.cmd("sysctl net.ipv6.conf.all.forwarding=1")

    def terminate(self):
        self.cmd("sysctl net.ipv4.ip_forward=0")
        self.cmd("sysctl net.ipv6.conf.all.forwarding=0")
        super().terminate()


class BMv2Switch(Switch):
    """BMv2 软件交换机节点"""

    device_id = 0

    def __init__(self, name, p4_json=None, thrift_port=None, **kwargs):
        Switch.__init__(self, name, **kwargs)
        self.p4_json = p4_json or str(P4_JSON)
        BMv2Switch.device_id += 1
        self.device_id = BMv2Switch.device_id
        self.thrift_port = thrift_port or (9090 + self.device_id)

    def start(self, controllers):
        """启动 BMv2 simple_switch"""
        BMV2_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = BMV2_LOG_DIR / f"{self.name}.log"

        ifaces = []
        for i, intf in enumerate(self.intfList()):
            if intf.name != "lo":
                ifaces.extend(["-i", f"{i}@{intf.name}"])

        cmd = [
            BMV2_SWITCH,
            "--device-id", str(self.device_id),
            "--thrift-port", str(self.thrift_port),
            "--log-file", str(log_file),
            self.p4_json,
        ] + ifaces

        info(f"Starting BMv2: {' '.join(cmd)}\n")
        self.cmd(" ".join(cmd) + " &")
        time.sleep(0.5)

    def stop(self, deleteIntfs=True):
        self.cmd(f"kill %{BMV2_SWITCH} 2>/dev/null")
        super().stop(deleteIntfs)

    def add_table_entry(self, table, match, action, action_params=""):
        """通过 simple_switch_CLI 添加表项"""
        cmd_str = f'table_add {table} {action} {match} => {action_params}'
        cli_cmd = (
            f'echo "{cmd_str}" | '
            f'simple_switch_CLI --thrift-port {self.thrift_port}'
        )
        return os.popen(cli_cmd).read()


def compile_p4():
    """编译 P4 程序"""
    if P4_JSON.exists():
        p4_mtime = P4_PROGRAM.stat().st_mtime
        json_mtime = P4_JSON.stat().st_mtime
        if json_mtime > p4_mtime:
            info("P4 JSON is up to date, skipping compilation.\n")
            return True

    info(f"Compiling P4 program: {P4_PROGRAM}\n")
    result = subprocess.run(
        ["p4c-bm2-ss", "--p4v", "16", "-o", str(P4_JSON), str(P4_PROGRAM)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        info(f"P4 compilation failed:\n{result.stderr}\n")
        return False
    info("P4 compilation successful.\n")
    return True


def get_latitude(x, y, z):
    d = math.sqrt(x ** 2 + y ** 2)
    lat = math.atan2(z, d) * 180 / math.pi
    return lat


class Myserver(socketserver.StreamRequestHandler):
    """处理 SaVi 发来的星座和 ISL 数据"""

    sat_line_str = ""
    sat_coor_line_str = ""
    num = 0
    ISL_delays = {}

    def _parse_satellite_tokens(self, line):
        tokens = [t for t in line.split(" ") if t]
        if not tokens or tokens[-1] == "sunlight":
            return None
        return tokens

    def _update_topology(self):
        global TOPOLOGY
        if self.num <= 0:
            TOPOLOGY = {"num_sats": 0, "sats_per_plane": 0, "num_planes": 0}
            return
        last_sat = sats_str.get(self.num - 1, {})
        if len(last_sat) < 10:
            TOPOLOGY = {"num_sats": self.num, "sats_per_plane": 1, "num_planes": self.num}
            return
        spp = int(last_sat[9][0:-1]) + 1
        TOPOLOGY = {"num_sats": self.num, "sats_per_plane": spp,
                     "num_planes": int(self.num / spp) if spp else 0}

    def calc_sat_num(self):
        sats_str.clear()
        i = 0
        for line in self.sat_line_str.split("\r\n"):
            if line in ("constellation import end", ""):
                continue
            tokens = self._parse_satellite_tokens(line)
            if tokens is None:
                continue
            sats_str[i] = {j: t for j, t in enumerate(tokens)}
            i += 1
        self.num = i
        self._update_topology()
        build_network(self.num)

    def modify_ISL_para(self):
        global LINK_STATES
        self.num = TOPOLOGY["num_sats"]
        spp = TOPOLOGY["sats_per_plane"]
        if self.num <= 0 or spp <= 0:
            return
        updates, LINK_STATES = compute_link_state_updates(
            ISLs_origin, self.ISL_delays, spp, LINK_STATES
        )
        for i, j, new_state in updates:
            sats[i].cmd(f"ifconfig eth-r{i+1}r{j+1} {new_state}")
            sats[j].cmd(f"ifconfig eth-r{j+1}r{i+1} {new_state}")

    def calc_ISL_delay(self):
        c, r = 300000, 6371.0
        self.ISL_delays = {}
        spp = TOPOLOGY["sats_per_plane"]
        entries = []
        for key in sats_coor_str:
            e = sats_coor_str[key]
            entries.append({"id": int(e[0]), "x": float(e[1]),
                            "y": float(e[2]), "z": float(e[3])})
        entries.sort(key=lambda s: s["id"])
        for s in entries:
            s["lat"] = get_latitude(s["x"], s["y"], s["z"])
            self.ISL_delays[s["id"] - 1] = {}
        for s in entries:
            for s2 in entries:
                self.ISL_delays[s["id"]-1][s2["id"]-1] = 0
        for ia, sa in enumerate(entries):
            ida = sa["id"] - 1
            for ib in range(ia + 1, len(entries)):
                sb = entries[ib]
                idb = sb["id"] - 1
                if spp > 0 and (abs(sa["lat"]) > 60 or abs(sb["lat"]) > 60) \
                        and (ida // spp) != (idb // spp):
                    continue
                dx, dy, dz = sa["x"]-sb["x"], sa["y"]-sb["y"], sa["z"]-sb["z"]
                dsq = dx**2 + dy**2 + dz**2
                if dsq == 0:
                    continue
                t = (sa["x"]*dx + sa["y"]*dy + sa["z"]*dz) / dsq
                d_ab = math.sqrt(dsq)
                if t < 0 or t > 1:
                    delay = d_ab / c
                else:
                    xm = sa["x"] + t*(sb["x"]-sa["x"])
                    ym = sa["y"] + t*(sb["y"]-sa["y"])
                    zm = sa["z"] + t*(sb["z"]-sa["z"])
                    delay = d_ab / c if r < math.sqrt(xm**2+ym**2+zm**2) else 0
                self.ISL_delays[ida][idb] = delay
                self.ISL_delays[idb][ida] = delay

    def parse_ISL_info(self):
        sats_coor_str.clear()
        i = 0
        for line in self.sat_coor_line_str.split("\r\n"):
            if line in ("ISL info start", "ISL info end", ""):
                continue
            arrs = [a for a in line.split(", ") if a]
            if len(arrs) < 5 or arrs[4] == "sunlight":
                continue
            sats_coor_str[i] = {j: a for j, a in enumerate(arrs)}
            i += 1
        self.sat_coor_line_str = ""
        self.calc_ISL_delay()
        self.modify_ISL_para()

    def handle(self):
        start_import = False
        start_isl = False
        for raw_line in self.rfile:
            try:
                content = raw_line.decode("utf-8").strip()
                if not content:
                    continue
                if content == "constellation import start":
                    start_import = True
                    self.sat_line_str = ""
                elif content == "constellation import end":
                    start_import = False
                    self.calc_sat_num()
                elif content == "ISL info start":
                    start_isl = True
                    self.sat_coor_line_str = ""
                elif content == "ISL info end":
                    start_isl = False
                    self.parse_ISL_info()
                else:
                    if start_import:
                        self.sat_line_str += content + "\r\n"
                    if start_isl:
                        self.sat_coor_line_str += content + "\r\n"
            except (ConnectionResetError, UnicodeDecodeError):
                break


def build_network(num):
    """构建 BMv2 + FRR 混合网络拓扑"""
    global net, ISLs, ISLs_origin, LINK_STATES

    ISLs.clear()
    ISLs_origin.clear()
    sats.clear()
    bmv2_switches.clear()
    LINK_STATES.clear()

    if net is not None:
        net.stop()
        for h in net.hosts:
            net.delHost(h)
        for s in net.switches:
            net.delSwitch(s)

    if len(sats_str.get(num - 1, {})) < 9:
        return

    M = int(sats_str[num - 1][9][0:-1]) + 1
    N = int(num / M)
    TOPOLOGY.update({"num_sats": num, "sats_per_plane": M, "num_planes": N})
    info(f"Building BMv2+FRR topology: {num} sats, {N} planes x {M} per plane\n")

    # 创建节点：每个卫星 = LinuxRouter (FRR)
    for n in range(num):
        s = net.addHost(f"r{n+1}", ip="", cls=LinuxRouter)
        sats[n] = s

    # 创建 ISL 链路
    for n in range(N):
        for m in range(M):
            idx = n * M + m
            ISLs[idx] = {}
            ISLs_origin[idx] = {}

    for n in range(N):
        for m in range(M):
            idx = n * M + m
            nxt = n * M + (m + 1) % M
            isl1 = net.addLink(
                sats[idx], sats[nxt],
                intfName1=f"eth-r{idx+1}r{nxt+1}",
                intfName2=f"eth-r{nxt+1}r{idx+1}",
                bw=10, delay="1ms"
            )
            ISLs[idx][nxt] = isl1
            ISLs_origin[idx][nxt] = isl1
            if n != N - 1:
                cross = (n + 1) * M + m
                isl2 = net.addLink(
                    sats[idx], sats[cross],
                    intfName1=f"eth-r{idx+1}r{cross+1}",
                    intfName2=f"eth-r{cross+1}r{idx+1}",
                    bw=10, delay="1ms"
                )
                ISLs[idx][cross] = isl2
                ISLs_origin[idx][cross] = isl2

    net.start()
    info("Network started. Configuring FRR on each node...\n")

    # 配置 FRR（与 router-host.py 相同逻辑，简化版）
    for n in range(N):
        for m in range(M):
            idx = n * M + m
            rid = idx + 1
            tmp_dir = f"/tmp/r{rid}"
            sats[idx].cmd(f"mkdir -p {tmp_dir}")

            # 生成 isisd.conf
            write_isisd_conf(n, m, N, M, tmp_dir, rid)
            # 生成 zebra.conf
            write_zebra_conf(n, m, N, M, tmp_dir, rid)

            # 启动 FRR
            sats[idx].cmd("export PATH=/usr/lib/frr:$PATH")
            sats[idx].cmd(
                f"zebra -f {tmp_dir}/r{rid}zebra.conf -d "
                f"-z {tmp_dir}zebra.api -i {tmp_dir}zebra.interface "
                f"--vty_socket {tmp_dir} -u root"
            )
            time.sleep(0.1)
            sats[idx].cmd(
                f"isisd -f {tmp_dir}/r{rid}isisd.conf -d "
                f"-z {tmp_dir}zebra.api -i {tmp_dir}isisd.interface "
                f"--vty_socket {tmp_dir} -u root"
            )
            time.sleep(0.1)

    # 保存拓扑文件
    RUNTIME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_OUTPUT_DIR / "topology.savi", "w") as f:
        for n in range(num):
            f.write(f"node r{n+1}\n")
        for i in ISLs_origin:
            for j in ISLs_origin[i]:
                f.write(f"link r{i+1}-r{j+1}\n")

    info("BMv2+FRR topology ready.\n")


def write_isisd_conf(n, m, N, M, tmp_dir, rid):
    """生成 isisd 配置文件"""
    with open(f"{tmp_dir}/r{rid}isisd.conf", "w") as f:
        f.write(f"hostname r{rid}\npassword foo\nenable password foo\nlog stdout\n")
        f.write("router isis DEAD\n")
        net_id = f"{rid:04d}"
        f.write(f"    net 47.0023.0000.0000.0000.0000.0000.0000.{net_id}.00\n")
        f.write("interface lo\n    ip router isis DEAD\n")
        # 同面内环形链路
        nxt = n * M + (m + 1) % M + 1
        f.write(f"interface eth-r{rid}r{nxt}\n    ip router isis DEAD\n")
        # 反向链路
        for n1 in range(N):
            for m1 in range(M):
                if (n1 * M + (m1 + 1) % M) == (n * M + m):
                    f.write(f"interface eth-r{rid}r{n1*M+m1+1}\n    ip router isis DEAD\n")
        # 跨面链路
        if n != N - 1:
            cross = (n + 1) * M + m + 1
            f.write(f"interface eth-r{rid}r{cross}\n    ip router isis DEAD\n")
        for n2 in range(N):
            for m2 in range(M):
                if n2 != N - 1 and (n2 + 1) * M + m2 == n * M + m:
                    f.write(f"interface eth-r{rid}r{n2*M+m2+1}\n    ip router isis DEAD\n")


def write_zebra_conf(n, m, N, M, tmp_dir, rid):
    """生成 zebra 配置文件"""
    with open(f"{tmp_dir}/r{rid}zebra.conf", "w") as f:
        f.write(f"hostname r{rid}\nlog stdout\n")
        f.write(f"interface lo\n    ip address {rid}.{rid}.{rid}.{rid}/32\n")
        # 同面内链路
        nxt = n * M + (m + 1) % M + 1
        lo, hi = min(rid, nxt), max(rid, nxt)
        f.write(f"interface eth-r{rid}r{nxt}\n    ip address 192.{lo}.{hi}.{rid}/24\n")
        # 反向链路
        for n1 in range(N):
            for m1 in range(M):
                if (n1 * M + (m1 + 1) % M) == (n * M + m):
                    peer = n1 * M + m1 + 1
                    lo, hi = min(rid, peer), max(rid, peer)
                    f.write(f"interface eth-r{rid}r{peer}\n    ip address 192.{lo}.{hi}.{rid}/24\n")
        # 跨面链路
        if n != N - 1:
            cross = (n + 1) * M + m + 1
            lo, hi = min(rid, cross), max(rid, cross)
            f.write(f"interface eth-r{rid}r{cross}\n    ip address 192.{lo}.{hi}.{rid}/24\n")
        for n2 in range(N):
            for m2 in range(M):
                if n2 != N - 1 and (n2 + 1) * M + m2 == n * M + m:
                    peer = n2 * M + m2 + 1
                    lo, hi = min(rid, peer), max(rid, peer)
                    f.write(f"interface eth-r{rid}r{peer}\n    ip address 192.{lo}.{hi}.{rid}/24\n")
        f.write("ip forwarding\nline vty\n")


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    setLogLevel("info")
    info("*** BMv2 + FRR Satellite Network Topology ***\n")

    # 编译 P4 程序（如果 p4c 可用）
    if P4_PROGRAM.exists():
        compile_p4()

    net = Mininet(controller=None, link=Link)

    def start_server():
        server = ReusableThreadingTCPServer(("127.0.0.1", 12345), Myserver)
        server.serve_forever()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    def start_geomview():
        time.sleep(5)
        subprocess.run(["sudo", "geomview", "-run", "./savi"])

    geomview_thread = threading.Thread(target=start_geomview)
    geomview_thread.start()

    CLI(net)
    net.stop()
