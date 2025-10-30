#!/usr/bin/env python3
"""
Unix Socket接收器：监听Unix socket接收格网覆盖数据
实现贪心算法选择卫星覆盖
"""

import socket
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Set, Tuple

class GridCoverageAnalyzer:
    """格网覆盖分析器 - 实现贪心算法"""
    
    def __init__(self, time_step=1.0, target_coverage_ratio=0.8):
        """
        初始化
        Args:
            time_step: 时间步长（秒）
            target_coverage_ratio: 目标覆盖率（0-1之间）
        """
        self.time_step = time_step
        self.target_coverage_ratio = target_coverage_ratio
        
        # 原始覆盖数据：grid_id -> {sat_id -> [timestamps]}
        self.original_coverage: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        
        # 贪心选择后的覆盖：grid_id -> [(sat_id, timestamps)]
        self.greedy_coverage: Dict[str, List[Tuple[str, List[float]]]] = defaultdict(list)
        
        # 记录开始时间
        self.start_time = None
        self.current_time = None
        
        # 统计信息
        self.total_messages = 0
        self.unique_grids: Set[str] = set()
        self.unique_sats: Set[str] = set()
    
    def add_coverage_data(self, sat_id: str, grid_list: List[str], timestamp: float):
        """添加覆盖数据"""
        self.total_messages += 1
        self.unique_sats.add(sat_id)
        
        for grid_id in grid_list:
            self.unique_grids.add(grid_id)
            self.original_coverage[grid_id][sat_id].append(timestamp)
    
    def calculate_coverage_duration(self, time_series: List[Tuple[str, List[float]]]) -> float:
        """
        计算覆盖时长函数 c(Ai)
        Args:
            time_series: 卫星时间序列列表 [(sat_id, [timestamps])]
        Returns:
            总覆盖时长（秒）
        """
        if not time_series:
            return 0.0
        
        # 合并所有时间点
        all_times = set()
        for sat_id, timestamps in time_series:
            all_times.update(timestamps)
        
        # 按时间排序
        sorted_times = sorted(all_times)
        
        # 计算覆盖时长（考虑时间步长）
        if len(sorted_times) == 0:
            return 0.0
        
        # 简单方法：每个时间点代表一个时间步长
        coverage_duration = len(sorted_times) * self.time_step
        
        return coverage_duration
    
    def greedy_select_for_grid(self, grid_id: str, target_duration: float) -> List[Tuple[str, List[float]]]:
        """
        对单个格网应用贪心算法选择卫星覆盖
        
        Args:
            grid_id: 格网ID
            target_duration: 目标覆盖时长（秒）
        
        Returns:
            选中的卫星时间序列 [(sat_id, [timestamps])]
        """
        Mi = self.original_coverage[grid_id].copy()  # 候选卫星时间序列集合
        Ai = []  # 选中的卫星时间序列
        Ci = 0.0  # 当前总覆盖时长
        
        while Ci < target_duration and Mi:
            best_sat = None
            best_improvement = 0.0
            Ctemp = Ci
            
            # 遍历所有候选卫星时间序列
            for sat_id, timestamps in Mi.items():
                # 尝试添加这个卫星
                Ai_temp = Ai + [(sat_id, timestamps)]
                C_new = self.calculate_coverage_duration(Ai_temp)
                
                # 如果改进更大，记录下来
                improvement = C_new - Ci
                if improvement > best_improvement:
                    best_sat = sat_id
                    best_improvement = improvement
                    Ctemp = C_new
            
            # 如果找到了改进的卫星
            if best_sat:
                Ai.append((best_sat, Mi[best_sat]))
                del Mi[best_sat]
                Ci = Ctemp
            else:
                # 没有更多改进，退出
                break
        
        return Ai
    
    def apply_greedy_algorithm(self):
        """对所有格网应用贪心算法"""
        print("\n" + "="*60)
        print("开始应用贪心算法...")
        print("="*60)
        
        # 估算总仿真时长
        if self.start_time and self.current_time:
            total_duration = self.current_time - self.start_time
        else:
            total_duration = 100.0  # 默认值
        
        # 目标覆盖时长 = 总时长 * 目标覆盖率
        target_duration = total_duration * self.target_coverage_ratio
        
        print(f"总仿真时长: {total_duration:.1f}秒")
        print(f"目标覆盖率: {self.target_coverage_ratio*100:.0f}%")
        print(f"目标覆盖时长: {target_duration:.1f}秒")
        print(f"处理格网总数: {len(self.unique_grids)}")
        print()
        
        # 对每个格网应用贪心算法
        for idx, grid_id in enumerate(sorted(self.unique_grids), 1):
            selected = self.greedy_select_for_grid(grid_id, target_duration)
            self.greedy_coverage[grid_id] = selected
            
            # 计算统计信息
            original_sats = len(self.original_coverage[grid_id])
            selected_sats = len(selected)
            original_duration = self.calculate_coverage_duration(
                [(s, t) for s, t in self.original_coverage[grid_id].items()]
            )
            selected_duration = self.calculate_coverage_duration(selected)
            
            if idx <= 10 or idx % 100 == 0:  # 只打印前10个和每100个
                print(f"格网 {grid_id}:")
                print(f"  原始: {original_sats}个卫星, 覆盖{original_duration:.1f}秒")
                print(f"  贪心: {selected_sats}个卫星, 覆盖{selected_duration:.1f}秒")
                print(f"  节省: {original_sats - selected_sats}个卫星 ({(1-selected_sats/original_sats)*100:.1f}%)")
                print()
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("数据收集统计")
        print("="*60)
        print(f"接收消息总数: {self.total_messages}")
        print(f"唯一格网数: {len(self.unique_grids)}")
        print(f"唯一卫星数: {len(self.unique_sats)}")
        print(f"数据收集时长: {self.current_time - self.start_time:.1f}秒" if self.start_time else "N/A")
        
        # 原始覆盖统计
        total_original_pairs = sum(len(sats) for sats in self.original_coverage.values())
        avg_sats_per_grid = total_original_pairs / len(self.unique_grids) if self.unique_grids else 0
        
        print(f"\n原始覆盖:")
        print(f"  总卫星-格网对: {total_original_pairs}")
        print(f"  平均每格网卫星数: {avg_sats_per_grid:.1f}")
        
        # 贪心选择统计
        if self.greedy_coverage:
            total_greedy_pairs = sum(len(sats) for sats in self.greedy_coverage.values())
            avg_greedy_per_grid = total_greedy_pairs / len(self.greedy_coverage) if self.greedy_coverage else 0
            reduction_rate = (1 - total_greedy_pairs/total_original_pairs) * 100 if total_original_pairs > 0 else 0
            
            print(f"\n贪心选择后:")
            print(f"  总卫星-格网对: {total_greedy_pairs}")
            print(f"  平均每格网卫星数: {avg_greedy_per_grid:.1f}")
            print(f"  卫星数量减少: {reduction_rate:.1f}%")
        
        print("="*60)
    
    def export_data(self, original_file="original_coverage.txt", greedy_file="greedy_coverage.txt"):
        """导出数据到文件"""
        print(f"\n导出原始覆盖数据到: {original_file}")
        with open(original_file, 'w') as f:
            f.write("# 原始覆盖数据\n")
            f.write("# 格式: GRID_ID SAT_ID TIMESTAMP1,TIMESTAMP2,...\n")
            for grid_id in sorted(self.unique_grids):
                for sat_id, timestamps in sorted(self.original_coverage[grid_id].items()):
                    times_str = ','.join(f"{t:.1f}" for t in sorted(timestamps))
                    f.write(f"{grid_id} {sat_id} {times_str}\n")
        
        print(f"导出贪心选择数据到: {greedy_file}")
        with open(greedy_file, 'w') as f:
            f.write("# 贪心选择后的覆盖数据\n")
            f.write("# 格式: GRID_ID SAT_ID TIMESTAMP1,TIMESTAMP2,...\n")
            for grid_id in sorted(self.greedy_coverage.keys()):
                for sat_id, timestamps in self.greedy_coverage[grid_id]:
                    times_str = ','.join(f"{t:.1f}" for t in sorted(timestamps))
                    f.write(f"{grid_id} {sat_id} {times_str}\n")
        
        print("数据导出完成！")

def test_unix_socket_receiver():
    # Unix socket路径
    socket_path = "/tmp/mini_savi_grid_coverage.sock"
    
    # 如果socket文件已存在，先删除
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    
    # 创建Unix socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    
    # 创建分析器
    analyzer = GridCoverageAnalyzer(time_step=1.0, target_coverage_ratio=0.8)
    
    try:
        # 绑定到Unix socket路径
        sock.bind(socket_path)
        print(f"Unix Socket监听器已启动，正在监听: {socket_path}")
        print("等待接收格网覆盖数据...")
        print("数据格式: SAT_ID:grid1,grid2,grid3,...")
        print("按Ctrl+C退出并进行贪心算法分析")
        print("-" * 60)
        
        # 接收数据
        while True:
            data = sock.recv(4096)
            message = data.decode('utf-8').strip()
            
            if message:
                # 解析数据
                if ':' in message:
                    sat_id, grids = message.split(':', 1)
                    grid_list = grids.split(',') if grids else []
                    
                    # 记录时间戳
                    current_timestamp = time.time()
                    if analyzer.start_time is None:
                        analyzer.start_time = current_timestamp
                    analyzer.current_time = current_timestamp
                    
                    # 添加覆盖数据
                    analyzer.add_coverage_data(sat_id, grid_list, current_timestamp)
                    
                    # 打印接收信息
                    print(f"[{analyzer.total_messages}] 卫星 {sat_id} 覆盖 {len(grid_list)} 个格网", end='')
                    if len(grid_list) <= 5:
                        print(f": {grids}")
                    else:
                        print(f": {','.join(grid_list[:3])}...{','.join(grid_list[-2:])}")
                else:
                    print(f"未知格式: {message}")
                
    except KeyboardInterrupt:
        print("\n\n用户中断，开始数据分析...")
        
        # 打印统计信息
        analyzer.print_statistics()
        
        # 应用贪心算法
        if analyzer.unique_grids:
            analyzer.apply_greedy_algorithm()
            
            # 导出数据
            analyzer.export_data()
            
            # 再次打印统计
            analyzer.print_statistics()
        else:
            print("没有接收到任何数据")
            
    except OSError as e:
        print(f"Unix Socket错误: {e}")
        print("可能socket文件权限不足或路径问题")
    finally:
        sock.close()
        # 清理socket文件
        if os.path.exists(socket_path):
            os.unlink(socket_path)

if __name__ == "__main__":
    test_unix_socket_receiver()
