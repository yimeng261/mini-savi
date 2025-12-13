#!/usr/bin/env python3
"""
Unix Socket接收器：监听Unix socket接收格网覆盖数据
支持二十面体和经纬度两种格网类型
实现贪心算法选择卫星覆盖
将数据保存到文件供后续分析和绘图
"""

import socket
import os
import sys
import time
import json
import pickle
from collections import defaultdict
from typing import Dict, List, Set, Tuple
from enum import Enum

class GridType(Enum):
    """格网类型"""
    ICOSAHEDRAL = "Icosahedral"  # 二十面体格网（F##_xxx格式）
    LATLON = "LatLon"             # 经纬度格网（LAT###_LON###格式）
    UNKNOWN = "Unknown"

def identify_grid_type(grid_code: str) -> GridType:
    """识别格网类型"""
    if grid_code.startswith('F') and ('_' in grid_code or grid_code[1:3].isdigit()):
        return GridType.ICOSAHEDRAL
    elif grid_code.startswith('LAT') and 'LON' in grid_code:
        return GridType.LATLON
    else:
        return GridType.UNKNOWN

def estimate_icosahedral_level(grid_count: int) -> int:
    """
    根据二十面体格网数量估算细分等级
    
    二十面体细分规律：
    Level 0: 20个面（基础二十面体）
    Level 1: 80个面 (每个面分成4个)
    Level 2: 320个面
    Level 3: 1280个面
    Level 4: 5120个面
    Level 5: 20480个面
    
    公式: faces = 20 * 4^level
    """
    if grid_count <= 20:
        return 0
    elif grid_count <= 80:
        return 1
    elif grid_count <= 320:
        return 2
    elif grid_count <= 1280:
        return 3
    elif grid_count <= 5120:
        return 4
    elif grid_count <= 20480:
        return 5
    else:
        return 6  # Level 6+

def estimate_latlon_resolution(grid_count: int) -> str:
    """
    根据经纬度格网数量估算分辨率
    
    常见分辨率：
    36x72 = 2592
    72x144 = 10368
    180x360 = 64800
    """
    if grid_count <= 2592:
        return "36x72"
    elif grid_count <= 10368:
        return "72x144"
    elif grid_count <= 64800:
        return "180x360"
    else:
        return f"high_{grid_count}"

class GridCoverageAnalyzer:
    """格网覆盖分析器 - 支持两种格网类型，实现贪心算法"""
    
    def __init__(self, time_step=1.0, target_coverage_ratio=0.8):
        """
        初始化
        Args:
            time_step: 时间步长（分钟，每次数据发送代表的模拟时间）
            target_coverage_ratio: 目标覆盖率（0-1之间）
        """
        self.time_step = time_step  # 每次数据发送 = 1分钟模拟时间
        self.target_coverage_ratio = target_coverage_ratio
        
        # 追踪每个卫星收到的消息次数（用于计算模拟时间）
        self.satellite_message_count = defaultdict(int)  # sat_id -> 消息次数
        
        # 按格网类型分开存储原始覆盖数据：grid_id -> {sat_id -> [timestamps]}
        self.original_coverage = {
            GridType.ICOSAHEDRAL: defaultdict(lambda: defaultdict(list)),
            GridType.LATLON: defaultdict(lambda: defaultdict(list))
        }
        
        # 按格网类型分开存储贪心选择后的覆盖
        self.greedy_coverage = {
            GridType.ICOSAHEDRAL: defaultdict(list),
            GridType.LATLON: defaultdict(list)
        }
        
        # 记录真实时间（用于统计接收速率等）
        self.real_start_time = None
        self.real_current_time = None
        
        # 按格网类型统计
        self.total_messages = 0
        self.unique_grids = {
            GridType.ICOSAHEDRAL: set(),
            GridType.LATLON: set()
        }
        self.unique_sats: Set[str] = set()
        
        # 格网类型使用情况
        self.grid_types_detected = set()
    
    def add_coverage_data(self, sat_id: str, grid_list: List[str]):
        """
        添加覆盖数据，自动识别并分类格网类型
        
        在both模式下，每个时间步每颗卫星会发送2条消息（ico + latlon）
        我们统计每个卫星的消息次数来推算模拟时间
        """
        self.total_messages += 1
        self.unique_sats.add(sat_id)
        
        # 记录该卫星的消息次数
        self.satellite_message_count[sat_id] += 1
        
        # 当前模拟时刻 = 该卫星收到的消息次数 - 1（从0开始）
        current_sim_minute = self.satellite_message_count[sat_id] - 1
        
        # 按格网类型分类
        for grid_id in grid_list:
            grid_type = identify_grid_type(grid_id)
            
            if grid_type != GridType.UNKNOWN:
                self.grid_types_detected.add(grid_type)
                self.unique_grids[grid_type].add(grid_id)
                # 使用模拟时间（分钟）作为时间戳
                self.original_coverage[grid_type][grid_id][sat_id].append(current_sim_minute)
    
    def get_simulation_duration(self):
        """
        获取当前模拟时长（分钟）
        
        在both模式下，每颗卫星每分钟发送2条消息
        在single模式下，每颗卫星每分钟发送1条消息
        
        返回所有卫星中最大的消息次数（即最长的模拟时间）
        """
        if not self.satellite_message_count:
            return 0
        
        # 检测是否是both模式（看是否有卫星发送了2种格网类型）
        is_both_mode = len(self.grid_types_detected) >= 2
        
        # 获取任意一个卫星的消息数作为模拟时长
        # （所有卫星应该收到相同次数的消息）
        max_count = max(self.satellite_message_count.values())
        
        if is_both_mode:
            # Both模式：每颗卫星每分钟发2条消息
            sim_minutes = max_count // 2
        else:
            # Single模式：每颗卫星每分钟发1条消息
            sim_minutes = max_count
        
        return sim_minutes
    
    def calculate_coverage_duration(self, time_series: List[Tuple[str, List[float]]]) -> float:
        """
        计算覆盖时长函数 c(Ai)
        Args:
            time_series: 卫星时间序列列表 [(sat_id, [timestamps_in_minutes])]
        Returns:
            总覆盖时长（分钟）
        """
        if not time_series:
            return 0.0
        
        # 合并所有时间点（模拟分钟数）
        all_times = set()
        for sat_id, timestamps in time_series:
            all_times.update(timestamps)
        
        # 覆盖时长 = 唯一时间点（分钟）的数量
        coverage_duration = len(all_times)
        
        return coverage_duration
    
    def greedy_select_for_grid(self, grid_id: str, target_duration: float, 
                               coverage_data: Dict) -> List[Tuple[str, List[float]]]:
        """
        对单个格网应用贪心算法选择卫星覆盖
        
        Args:
            grid_id: 格网ID
            target_duration: 目标覆盖时长（秒）
            coverage_data: 该格网的覆盖数据
        
        Returns:
            选中的卫星时间序列 [(sat_id, [timestamps])]
        """
        Mi = coverage_data.copy()  # 候选卫星时间序列集合
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
    
    def apply_greedy_algorithm_for_type(self, grid_type: GridType):
        """对指定类型的所有格网应用贪心算法"""
        if grid_type not in self.grid_types_detected:
            return
        
        grids = self.unique_grids[grid_type]
        if not grids:
            return
        
        print(f"\n{'='*70}")
        print(f"开始对 {grid_type.value} 格网应用贪心算法...")
        print(f"{'='*70}")
        
        # 总模拟时长（分钟）
        total_duration = self.get_simulation_duration()
        
        # 目标覆盖时长 = 总时长 * 目标覆盖率
        target_duration = total_duration * self.target_coverage_ratio
        
        print(f"格网类型: {grid_type.value}")
        print(f"总模拟时长: {total_duration:.1f}分钟")
        print(f"目标覆盖率: {self.target_coverage_ratio*100:.0f}%")
        print(f"目标覆盖时长: {target_duration:.1f}分钟")
        print(f"处理格网总数: {len(grids)}")
        print()
        
        # 对每个格网应用贪心算法
        for idx, grid_id in enumerate(sorted(grids), 1):
            coverage_data = self.original_coverage[grid_type][grid_id]
            selected = self.greedy_select_for_grid(grid_id, target_duration, coverage_data)
            self.greedy_coverage[grid_type][grid_id] = selected
            
            # 计算统计信息
            original_sats = len(coverage_data)
            selected_sats = len(selected)
            original_duration = self.calculate_coverage_duration(
                [(s, t) for s, t in coverage_data.items()]
            )
            selected_duration = self.calculate_coverage_duration(selected)
            
            if idx <= 5 or idx % 50 == 0:  # 只打印前5个和每50个
                print(f"格网 {grid_id}:")
                print(f"  原始: {original_sats}个卫星, 覆盖{original_duration:.1f}秒")
                print(f"  贪心: {selected_sats}个卫星, 覆盖{selected_duration:.1f}秒")
                if original_sats > 0:
                    print(f"  节省: {original_sats - selected_sats}个卫星 ({(1-selected_sats/original_sats)*100:.1f}%)")
                print()
    
    def apply_greedy_algorithm(self):
        """对所有类型的格网应用贪心算法"""
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            self.apply_greedy_algorithm_for_type(grid_type)
    
    def print_statistics_for_type(self, grid_type: GridType):
        """打印指定类型格网的统计信息"""
        if grid_type not in self.grid_types_detected:
            return
        
        grids = self.unique_grids[grid_type]
        if not grids:
            return
        
        print(f"\n{'='*70}")
        print(f"{grid_type.value} 格网统计")
        print(f"{'='*70}")
        print(f"唯一格网数: {len(grids)}")
        
        # 原始覆盖统计
        total_original_pairs = sum(
            len(sats) for sats in self.original_coverage[grid_type].values()
        )
        avg_sats_per_grid = total_original_pairs / len(grids) if grids else 0
        
        print(f"\n原始覆盖:")
        print(f"  总卫星-格网对: {total_original_pairs}")
        print(f"  平均每格网卫星数: {avg_sats_per_grid:.2f}")
        
        # 贪心选择统计
        if self.greedy_coverage[grid_type]:
            total_greedy_pairs = sum(
                len(sats) for sats in self.greedy_coverage[grid_type].values()
            )
            avg_greedy_per_grid = (
                total_greedy_pairs / len(self.greedy_coverage[grid_type]) 
                if self.greedy_coverage[grid_type] else 0
            )
            reduction_rate = (
                (1 - total_greedy_pairs/total_original_pairs) * 100 
                if total_original_pairs > 0 else 0
            )
            
            print(f"\n贪心选择后:")
            print(f"  总卫星-格网对: {total_greedy_pairs}")
            print(f"  平均每格网卫星数: {avg_greedy_per_grid:.2f}")
            print(f"  卫星数量减少: {reduction_rate:.1f}%")
        
        # 显示格网编码示例
        print(f"\n格网编码示例 (前5个):")
        for idx, grid_id in enumerate(sorted(grids)[:5], 1):
            print(f"  {idx}. {grid_id}")
        
        print(f"{'='*70}")
    
    def print_statistics(self):
        """打印总体统计信息"""
        print(f"\n{'='*70}")
        print("总体数据收集统计")
        print(f"{'='*70}")
        sim_duration = self.get_simulation_duration()
        is_both_mode = len(self.grid_types_detected) >= 2
        
        print(f"接收消息总数: {self.total_messages}")
        if is_both_mode:
            print(f"模式: Both (两种格网)")
            print(f"模拟时长: {sim_duration} 分钟 (每分钟{len(self.unique_sats)}颗卫星×2条消息 = {len(self.unique_sats)*2}条)")
        else:
            print(f"模式: Single (单一格网)")
            print(f"模拟时长: {sim_duration} 分钟 (每分钟{len(self.unique_sats)}颗卫星×1条消息 = {len(self.unique_sats)}条)")
        print(f"检测到的格网类型: {', '.join(gt.value for gt in self.grid_types_detected)}")
        print(f"唯一卫星数: {len(self.unique_sats)}")
        
        if self.real_start_time and self.real_current_time:
            real_duration = self.real_current_time - self.real_start_time
            print(f"真实数据收集时长: {real_duration:.1f}秒 ({real_duration/60:.2f}分钟)")
            print(f"消息接收速率: {self.total_messages/real_duration:.2f} msg/s")
        
        # 按类型统计
        total_grids = sum(len(grids) for grids in self.unique_grids.values())
        print(f"\n格网类型分布:")
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            count = len(self.unique_grids[grid_type])
            if count > 0:
                percentage = (count / total_grids * 100) if total_grids > 0 else 0
                print(f"  {grid_type.value}: {count} ({percentage:.1f}%)")
        
        print(f"{'='*70}")
        
        # 分别打印每种格网类型的详细统计
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            self.print_statistics_for_type(grid_type)
        
        # 如果同时使用了两种格网，打印对比分析
        if len(self.grid_types_detected) == 2:
            self.print_comparison_analysis()
    
    def print_comparison_analysis(self):
        """打印两种格网类型的对比分析"""
        print(f"\n{'='*70}")
        print("格网类型对比分析 (Icosahedral vs Lat-Lon)")
        print(f"{'='*70}")
        
        # 对比格网数量
        ico_count = len(self.unique_grids[GridType.ICOSAHEDRAL])
        latlon_count = len(self.unique_grids[GridType.LATLON])
        
        print(f"\n格网数量对比:")
        print(f"  二十面体: {ico_count}")
        print(f"  经纬度:   {latlon_count}")
        print(f"  比率:     1 : {latlon_count/ico_count:.2f}" if ico_count > 0 else "")
        
        # 对比平均覆盖卫星数
        ico_total_pairs = sum(
            len(sats) for sats in self.original_coverage[GridType.ICOSAHEDRAL].values()
        )
        latlon_total_pairs = sum(
            len(sats) for sats in self.original_coverage[GridType.LATLON].values()
        )
        
        ico_avg = ico_total_pairs / ico_count if ico_count > 0 else 0
        latlon_avg = latlon_total_pairs / latlon_count if latlon_count > 0 else 0
        
        print(f"\n平均每格网覆盖卫星数:")
        print(f"  二十面体: {ico_avg:.2f}")
        print(f"  经纬度:   {latlon_avg:.2f}")
        
        # 对比贪心算法效果
        if self.greedy_coverage[GridType.ICOSAHEDRAL] and self.greedy_coverage[GridType.LATLON]:
            ico_greedy_pairs = sum(
                len(sats) for sats in self.greedy_coverage[GridType.ICOSAHEDRAL].values()
            )
            latlon_greedy_pairs = sum(
                len(sats) for sats in self.greedy_coverage[GridType.LATLON].values()
            )
            
            ico_reduction = ((1 - ico_greedy_pairs/ico_total_pairs) * 100 
                           if ico_total_pairs > 0 else 0)
            latlon_reduction = ((1 - latlon_greedy_pairs/latlon_total_pairs) * 100 
                              if latlon_total_pairs > 0 else 0)
            
            print(f"\n贪心算法卫星节省率:")
            print(f"  二十面体: {ico_reduction:.1f}%")
            print(f"  经纬度:   {latlon_reduction:.1f}%")
        
        print(f"{'='*70}")
    
    
    def calculate_coverage_counts(self, grid_type: GridType, time_limit_minutes=None):
        """
        计算每个格网的覆盖次数
        
        Args:
            grid_type: 格网类型
            time_limit_minutes: 时间限制（分钟），None表示使用所有数据
            
        返回: (grid_ids_sorted, original_counts, greedy_counts)
        """
        grids = sorted(self.unique_grids[grid_type])
        original_counts = []
        greedy_counts = []
        
        # 计算模拟时间上限（分钟）
        if time_limit_minutes:
            time_limit = time_limit_minutes  # 直接使用分钟数
            
            # 调试信息：显示实际过滤了多少数据
            if grid_type == GridType.ICOSAHEDRAL and grids:
                total_count = 0
                filtered_count = 0
                for grid_id in grids[:1]:  # 只检查第一个格网作为样本
                    for timestamps in self.original_coverage[grid_type][grid_id].values():
                        total_count += len(timestamps)
                        filtered_count += sum(1 for ts in timestamps if ts < time_limit)
                
                if total_count > 0:
                    filter_ratio = filtered_count / total_count * 100
                    print(f"[调试] {grid_type.value} - 时间限制 {time_limit_minutes}分钟")
                    print(f"       样本格网保留了 {filtered_count}/{total_count} 个时间戳 ({filter_ratio:.1f}%)")
        else:
            time_limit = None
        
        for grid_id in grids:
            # 原始覆盖次数 = 所有卫星覆盖该格网的时间戳总数（在时间限制内）
            original_count = 0
            for timestamps in self.original_coverage[grid_type][grid_id].values():
                if time_limit:
                    # 只统计模拟时间限制内的时间戳（分钟 < time_limit）
                    original_count += sum(1 for ts in timestamps if ts < time_limit)
                else:
                    # 统计所有时间戳
                    original_count += len(timestamps)
            original_counts.append(original_count)
            
            # 贪心选择后的覆盖次数（在时间限制内）
            greedy_count = 0
            if grid_id in self.greedy_coverage[grid_type]:
                for sat_id, timestamps in self.greedy_coverage[grid_type][grid_id]:
                    if time_limit:
                        # 只统计模拟时间限制内的时间戳（分钟 < time_limit）
                        greedy_count += sum(1 for ts in timestamps if ts < time_limit)
                    else:
                        # 统计所有时间戳
                        greedy_count += len(timestamps)
            greedy_counts.append(greedy_count)
        
        return grids, original_counts, greedy_counts
    
    def calculate_satellite_coverage_counts(self, grid_type: GridType, time_limit_minutes=None):
        """
        计算每颗卫星覆盖的格网数量
        
        Args:
            grid_type: 格网类型
            time_limit_minutes: 时间限制（分钟），None表示使用全部数据
        
        Returns:
            (satellites, original_counts, greedy_counts)
            - satellites: 卫星ID列表（排序后）
            - original_counts: 每颗卫星原始覆盖的格网数量
            - greedy_counts: 每颗卫星贪心选择后覆盖的格网数量
        """
        satellites = sorted(self.unique_sats)
        original_counts = []
        greedy_counts = []
        
        # 计算模拟时间上限（分钟）
        time_limit = time_limit_minutes if time_limit_minutes else None
        
        for sat_id in satellites:
            # 原始覆盖数量 = 该卫星覆盖了多少个不同的格网（在时间限制内有覆盖）
            original_grids = set()
            for grid_id in self.unique_grids[grid_type]:
                if sat_id in self.original_coverage[grid_type][grid_id]:
                    timestamps = self.original_coverage[grid_type][grid_id][sat_id]
                    if time_limit:
                        # 检查是否有时间戳在限制内
                        if any(ts < time_limit for ts in timestamps):
                            original_grids.add(grid_id)
                    else:
                        original_grids.add(grid_id)
            original_counts.append(len(original_grids))
            
            # 贪心选择后覆盖数量 = 该卫星被选中覆盖了多少个格网（在时间限制内）
            greedy_grids = set()
            for grid_id in self.unique_grids[grid_type]:
                if grid_id in self.greedy_coverage[grid_type]:
                    # 检查该格网的贪心选择列表中是否包含该卫星
                    for selected_sat_id, timestamps in self.greedy_coverage[grid_type][grid_id]:
                        if selected_sat_id == sat_id:
                            if time_limit:
                                # 检查是否有时间戳在限制内
                                if any(ts < time_limit for ts in timestamps):
                                    greedy_grids.add(grid_id)
                            else:
                                greedy_grids.add(grid_id)
                            break
            greedy_counts.append(len(greedy_grids))
        
        return satellites, original_counts, greedy_counts
    
    def generate_filename(self) -> str:
        """
        生成覆盖次数对比统计图（分开显示DGD和LLP）
        
        Args:
            time_limit_minutes: 时间限制（分钟），None表示使用全部数据
            output_prefix: 输出文件名前缀
        """
        if not MATPLOTLIB_AVAILABLE:
            print("[警告] matplotlib未安装，跳过统计图生成")
            return
        
        if len(self.grid_types_detected) < 2:
            print("[警告] 需要两种格网类型才能生成对比图")
            return
        
        # 计算两种格网的覆盖次数（应用时间限制）
        ico_grids, ico_original, ico_greedy = self.calculate_coverage_counts(
            GridType.ICOSAHEDRAL, time_limit_minutes
        )
        ll_grids, ll_original, ll_greedy = self.calculate_coverage_counts(
            GridType.LATLON, time_limit_minutes
        )
        
        if not ico_grids or not ll_grids:
            print("[警告] 格网数据不足，无法生成统计图")
            return
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        title = 'Grid Coverage Count Comparison'
        if time_limit_minutes:
            title += f' (First {time_limit_minutes} min)'
        fig.suptitle(title, fontsize=16, fontweight='bold')
        
        # 图1: 二十面体格网 (DGD - Discrete Global Grid)
        ax1.plot(range(len(ico_grids)), ico_original, color='#1f77b4', linestyle='-', linewidth=2, 
                label='DGD Original Coverage', alpha=0.8)
        ax1.plot(range(len(ico_grids)), ico_greedy, color='#ff7f0e', linestyle='-', linewidth=2, 
                label='DGD with Greedy Selection', alpha=0.8)
        
        ax1.set_xlabel('Seq Num of Global Discrete Grids', fontsize=12)
        ax1.set_ylabel('Coverage Count', fontsize=12)
        ax1.set_title('Icosahedral Grid (DGD) Coverage Comparison', fontsize=14)
        ax1.legend(loc='upper right', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # 添加统计信息
        ico_orig_avg = np.mean(ico_original) if ico_original else 0
        ico_greedy_avg = np.mean(ico_greedy) if ico_greedy else 0
        ax1.text(0.02, 0.98, 
                f'DGD Grids: {len(ico_grids)}\n' +
                f'Avg Original: {ico_orig_avg:.1f}\n' +
                f'Avg Greedy: {ico_greedy_avg:.1f}',
                transform=ax1.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # 图2: 经纬度格网 (LLP - Long-Lat Partition)
        ax2.plot(range(len(ll_grids)), ll_original, color='#2ca02c', linestyle='-', linewidth=2, 
                label='LLP Original Coverage', alpha=0.8)
        ax2.plot(range(len(ll_grids)), ll_greedy, color='#d62728', linestyle='-', linewidth=2, 
                label='LLP with Greedy Selection', alpha=0.8)
        
        ax2.set_xlabel('Seq Num of Long-Lat Partition Unit', fontsize=12)
        ax2.set_ylabel('Coverage Count', fontsize=12)
        ax2.set_title('Latitude-Longitude Grid (LLP) Coverage Comparison', fontsize=14)
        ax2.legend(loc='upper right', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        # 添加统计信息
        ll_orig_avg = np.mean(ll_original) if ll_original else 0
        ll_greedy_avg = np.mean(ll_greedy) if ll_greedy else 0
        ax2.text(0.02, 0.98,
                f'LLP Grids: {len(ll_grids)}\n' +
                f'Avg Original: {ll_orig_avg:.1f}\n' +
                f'Avg Greedy: {ll_greedy_avg:.1f}',
                transform=ax2.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
        
        plt.tight_layout()
        
        # 保存图表
        if time_limit_minutes:
            filename = f"{output_prefix}_{time_limit_minutes}min.png"
        else:
            filename = f"{output_prefix}_full.png"
        
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        print(f"✓ 统计图已保存: {filename}")
        plt.close()
    
    def plot_satellite_coverage_comparison(self, time_limit_minutes=None, output_prefix="satellite_coverage_comparison"):
        """
        生成单星覆盖数量对比统计图（对比DGD和LLP）
        
        Args:
            time_limit_minutes: 时间限制（分钟），None表示使用全部数据
            output_prefix: 输出文件名前缀
        """
        if not MATPLOTLIB_AVAILABLE:
            print("[警告] matplotlib未安装，跳过统计图生成")
            return
        
        if len(self.grid_types_detected) < 2:
            print("[警告] 需要两种格网类型才能生成单星对比图")
            return
        
        # 计算两种格网下每颗卫星的覆盖数量
        ico_sats, ico_original, ico_greedy = self.calculate_satellite_coverage_counts(
            GridType.ICOSAHEDRAL, time_limit_minutes
        )
        ll_sats, ll_original, ll_greedy = self.calculate_satellite_coverage_counts(
            GridType.LATLON, time_limit_minutes
        )
        
        if not ico_sats or not ll_sats:
            print("[警告] 卫星数据不足，无法生成统计图")
            return
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(16, 8))
        title = 'Satellite Coverage Count Comparison (DGD vs LLP)'
        if time_limit_minutes:
            title += f' (First {time_limit_minutes} min)'
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        
        # 绘制4条折线
        x = range(len(ico_sats))
        
        # DGD 原始覆盖 - 蓝色
        ax.plot(x, ico_original, color='#1f77b4', linestyle='-', linewidth=2, 
                label='Original DGD', alpha=0.8, marker='o', markersize=3, markevery=max(1, len(x)//20))
        
        # DGD 贪心选择 - 橙色
        ax.plot(x, ico_greedy, color='#ff7f0e', linestyle='-', linewidth=2, 
                label='DGD with Greedy Selection', alpha=0.8, marker='s', markersize=3, markevery=max(1, len(x)//20))
        
        # LLP 原始覆盖 - 绿色
        ax.plot(x, ll_original, color='#2ca02c', linestyle='-', linewidth=2, 
                label='Original LLP', alpha=0.8, marker='^', markersize=3, markevery=max(1, len(x)//20))
        
        # LLP 贪心选择 - 红色
        ax.plot(x, ll_greedy, color='#d62728', linestyle='-', linewidth=2, 
                label='LLP with Greedy Selection', alpha=0.8, marker='v', markersize=3, markevery=max(1, len(x)//20))
        
        ax.set_xlabel('Seq Num of Satellite', fontsize=12)
        ax.set_ylabel('Coverage Count', fontsize=12)
        ax.legend(loc='upper right', fontsize=11, framealpha=0.9)
        ax.grid(True, alpha=0.3)
        
        # 添加统计信息
        ico_orig_avg = np.mean(ico_original) if ico_original else 0
        ico_greedy_avg = np.mean(ico_greedy) if ico_greedy else 0
        ll_orig_avg = np.mean(ll_original) if ll_original else 0
        ll_greedy_avg = np.mean(ll_greedy) if ll_greedy else 0
        
        stats_text = (
            f'Total Satellites: {len(ico_sats)}\n\n'
            f'DGD Statistics:\n'
            f'  Avg Original: {ico_orig_avg:.1f}\n'
            f'  Avg Greedy: {ico_greedy_avg:.1f}\n\n'
            f'LLP Statistics:\n'
            f'  Avg Original: {ll_orig_avg:.1f}\n'
            f'  Avg Greedy: {ll_greedy_avg:.1f}'
        )
        
        ax.text(0.02, 0.98, stats_text,
                transform=ax.transAxes, fontsize=10,
                verticalalignment='top', 
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存图表
        if time_limit_minutes:
            filename = f"{output_prefix}_{time_limit_minutes}min.png"
        else:
            filename = f"{output_prefix}_full.png"
        
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        print(f"✓ 单星覆盖统计图已保存: {filename}")
        plt.close()
    
    def generate_all_plots(self):
        """生成所有统计图"""
        if not MATPLOTLIB_AVAILABLE:
            print("\n[警告] matplotlib未安装，无法生成统计图")
            print("安装方法: pip3 install matplotlib numpy")
            return
        
        print("\n" + "="*70)
        print("生成统计图表...")
        print("="*70)
        
        # 计算模拟时长
        sim_duration_minutes = self.get_simulation_duration()
        is_both_mode = len(self.grid_types_detected) >= 2
        
        print(f"\n模拟时长: {sim_duration_minutes} 分钟 ({sim_duration_minutes/60:.2f} 小时)")
        if is_both_mode:
            expected_messages = sim_duration_minutes * len(self.unique_sats) * 2
            print(f"模式: Both - 预期消息数: {sim_duration_minutes}分钟 × {len(self.unique_sats)}卫星 × 2格网 = {expected_messages}")
            print(f"实际收到消息: {self.total_messages} (差异: {self.total_messages - expected_messages})")
        
        if sim_duration_minutes < 100:
            print(f"[警告] 模拟时长不足100分钟，两张图可能相同")
            print(f"[建议] 至少运行100分钟以上的模拟才能看到差异")
        
        # 根据模拟时长动态调整时间限制
        actual_duration_minutes = sim_duration_minutes
        
        if actual_duration_minutes < 100:
            # 数据不足100分钟，使用更短的时间段对比
            time_limit_1 = int(actual_duration_minutes * 0.5)  # 前50%
            time_limit_2 = int(actual_duration_minutes)         # 全部数据
            print(f"\n[自适应] 模拟时长不足100分钟，调整对比时间段：")
            print(f"         图1: 前 {time_limit_1} 分钟")
            print(f"         图2: 前 {time_limit_2} 分钟")
        else:
            time_limit_1 = 100
            time_limit_2 = 1440
        
        # 生成格网覆盖对比图
        print(f"\n[1/2] 生成格网覆盖对比图...")
        print(f"\n生成前{time_limit_1}分钟格网覆盖统计图...")
        self.plot_coverage_comparison(time_limit_minutes=time_limit_1, output_prefix="coverage_comparison")
        
        print(f"\n生成前{time_limit_2}分钟格网覆盖统计图...")
        self.plot_coverage_comparison(time_limit_minutes=time_limit_2, output_prefix="coverage_comparison")
        
        # 生成单星覆盖对比图
        print(f"\n[2/2] 生成单星覆盖对比图...")
        print(f"\n生成前{time_limit_1}分钟单星覆盖统计图...")
        self.plot_satellite_coverage_comparison(time_limit_minutes=time_limit_1, output_prefix="satellite_coverage_comparison")
        
        print(f"\n生成前{time_limit_2}分钟单星覆盖统计图...")
        self.plot_satellite_coverage_comparison(time_limit_minutes=time_limit_2, output_prefix="satellite_coverage_comparison")
        
        print("\n" + "="*70)
        print("✓ 所有统计图生成完成！")
        print("="*70)
        print("\n格网覆盖对比图:")
        print(f"  - coverage_comparison_{time_limit_1}min.png")
        print(f"  - coverage_comparison_{time_limit_2}min.png")
        print("\n单星覆盖对比图:")
        print(f"  - satellite_coverage_comparison_{time_limit_1}min.png")
        print(f"  - satellite_coverage_comparison_{time_limit_2}min.png")

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
        print(f"{'='*70}")
        print("Mini-SaVi 格网覆盖数据接收器")
        print(f"{'='*70}")
        print(f"Unix Socket监听器已启动")
        print(f"监听路径: {socket_path}")
        print(f"支持格网类型:")
        print(f"  - Icosahedral (二十面体格网): F##_xxx 格式")
        print(f"  - Lat-Lon (经纬度格网): LAT###_LON### 格式")
        print()
        print("等待接收格网覆盖数据...")
        print("数据格式: SAT_ID:grid1,grid2,grid3,...")
        print()
        print("按 Ctrl+C 退出并进行数据分析")
        print(f"{'='*70}\n")
        
        message_count = 0
        last_print_time = time.time()
        
        # 接收数据
        while True:
            data = sock.recv(8192)  # 增加缓冲区大小
            try:
                message = data.decode('utf-8').strip()
            except UnicodeDecodeError as e:
                print(f"[警告] UTF-8解码失败: {e}")
                print(f"[警告] 原始数据 (hex): {data.hex()[:200]}")
                continue
            
            if message:
                # 解析数据
                if ':' in message:
                    sat_id, grids = message.split(':', 1)
                    grid_list = grids.split(',') if grids else []
                    
                    # 记录真实时间（用于统计）
                    current_real_time = time.time()
                    if analyzer.real_start_time is None:
                        analyzer.real_start_time = current_real_time
                    analyzer.real_current_time = current_real_time
                    
                    # 添加覆盖数据（自动累加模拟时间）
                    analyzer.add_coverage_data(sat_id, grid_list)
                    message_count += 1
                    
                    # 识别格网类型（用于显示）
                    grid_types_in_msg = set()
                    for grid_id in grid_list[:3]:  # 只检查前几个
                        gt = identify_grid_type(grid_id)
                        if gt != GridType.UNKNOWN:
                            grid_types_in_msg.add(gt.value)
                    
                    types_str = '+'.join(grid_types_in_msg) if grid_types_in_msg else "?"
                    
                    # 每秒打印一次或前10条消息
                    current_time = time.time()
                    if message_count <= 10 or (current_time - last_print_time) >= 1.0:
                        print(f"[{message_count:4d}] 卫星{sat_id:3s} [{types_str:15s}] "
                              f"覆盖{len(grid_list):4d}格网", end='')
                        
                        if len(grid_list) <= 3:
                            print(f" | {grids}")
                        else:
                            sample = f"{','.join(grid_list[:2])}...{grid_list[-1]}"
                            print(f" | {sample}")
                        
                        last_print_time = current_time
                else:
                    print(f"[警告] 未知格式: {message}")
                
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("用户中断，开始数据分析...")
        print("="*70)
        
        # 打印统计信息
        analyzer.print_statistics()
        
        # 应用贪心算法并生成统计图
        if any(analyzer.unique_grids[gt] for gt in [GridType.ICOSAHEDRAL, GridType.LATLON]):
            analyzer.apply_greedy_algorithm()
            
            # 生成统计图
            analyzer.generate_all_plots()
            
            # 打印统计（包含贪心算法结果）
            analyzer.print_statistics()
        else:
            print("\n没有接收到任何有效的格网数据")
            
    except OSError as e:
        print(f"\nUnix Socket错误: {e}")
        print("可能原因:")
        print("  - Socket文件权限不足")
        print("  - 路径问题")
        print("  - 另一个进程正在使用该socket")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sock.close()
        # 清理socket文件
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        print("\nSocket已关闭，清理完成")

if __name__ == "__main__":
    test_unix_socket_receiver()
