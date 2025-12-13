#!/usr/bin/env python3
"""
格网覆盖数据绘图分析脚本
读取 receive_grid_coverage_data.py 保存的数据文件，生成统计图表
"""

import os
import sys
import pickle
import argparse
from enum import Enum
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非交互式后端
    import matplotlib.pyplot as plt
    import numpy as np
    
    # 配置matplotlib，避免字体警告
    import logging
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    
    # 使用默认字体，不依赖中文字体
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['axes.unicode_minus'] = False
    
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[错误] matplotlib未安装，无法生成统计图")
    print("安装方法: pip3 install matplotlib numpy")
    sys.exit(1)

class GridType(Enum):
    """格网类型"""
    ICOSAHEDRAL = "Icosahedral"
    LATLON = "LatLon"

def load_data(filename):
    """加载数据文件"""
    print(f"{'='*70}")
    print(f"加载数据文件: {filename}")
    print(f"{'='*70}")
    
    with open(filename, 'rb') as f:
        data = pickle.load(f)
    
    print(f"✓ 数据加载成功")
    print(f"\n数据概况:")
    print(f"  模拟时长: {data['metadata']['simulation_duration_minutes']} 分钟")
    print(f"  卫星数量: {data['metadata']['unique_satellite_count']}")
    print(f"  消息总数: {data['metadata']['total_messages']}")
    print(f"  格网类型: {', '.join(data['metadata']['grid_types_detected'])}")
    
    for grid_type_name, grid_info in data['grid_info'].items():
        print(f"\n  {grid_type_name}:")
        print(f"    格网数量: {grid_info['count']}")
        print(f"    检测等级: {grid_info['level']}")
    
    print(f"{'='*70}\n")
    
    return data

def calculate_grid_coverage_counts(data, grid_type_name, time_limit_minutes=None):
    """
    计算每个格网的覆盖次数
    
    Returns:
        (grids, original_counts, greedy_counts)
    """
    if grid_type_name not in data['grid_info']:
        return [], [], []
    
    grids = sorted(data['grid_info'][grid_type_name]['grids'])
    original_counts = []
    greedy_counts = []
    
    for grid_id in grids:
        # 原始覆盖次数
        original_count = 0
        if grid_id in data['original_coverage'][grid_type_name]:
            for sat_id, timestamps in data['original_coverage'][grid_type_name][grid_id].items():
                if time_limit_minutes:
                    original_count += sum(1 for ts in timestamps if ts < time_limit_minutes)
                else:
                    original_count += len(timestamps)
        original_counts.append(original_count)
        
        # 贪心选择后的覆盖次数
        greedy_count = 0
        if grid_id in data['greedy_coverage'][grid_type_name]:
            for sat_id, timestamps in data['greedy_coverage'][grid_type_name][grid_id]:
                if time_limit_minutes:
                    greedy_count += sum(1 for ts in timestamps if ts < time_limit_minutes)
                else:
                    greedy_count += len(timestamps)
        greedy_counts.append(greedy_count)
    
    return grids, original_counts, greedy_counts

def calculate_satellite_coverage_counts(data, grid_type_name, time_limit_minutes=None):
    """
    计算每颗卫星覆盖的格网数量
    
    Returns:
        (satellites, original_counts, greedy_counts)
    """
    if grid_type_name not in data['grid_info']:
        return [], [], []
    
    satellites = sorted(data['satellites'])
    unique_grids = set(data['grid_info'][grid_type_name]['grids'])
    original_counts = []
    greedy_counts = []
    
    for sat_id in satellites:
        # 原始覆盖数量
        original_grids = set()
        for grid_id in unique_grids:
            if grid_id in data['original_coverage'][grid_type_name]:
                if sat_id in data['original_coverage'][grid_type_name][grid_id]:
                    timestamps = data['original_coverage'][grid_type_name][grid_id][sat_id]
                    if time_limit_minutes:
                        if any(ts < time_limit_minutes for ts in timestamps):
                            original_grids.add(grid_id)
                    else:
                        original_grids.add(grid_id)
        original_counts.append(len(original_grids))
        
        # 贪心选择后覆盖数量
        greedy_grids = set()
        for grid_id in unique_grids:
            if grid_id in data['greedy_coverage'][grid_type_name]:
                for selected_sat_id, timestamps in data['greedy_coverage'][grid_type_name][grid_id]:
                    if selected_sat_id == sat_id:
                        if time_limit_minutes:
                            if any(ts < time_limit_minutes for ts in timestamps):
                                greedy_grids.add(grid_id)
                        else:
                            greedy_grids.add(grid_id)
                        break
        greedy_counts.append(len(greedy_grids))
    
    return satellites, original_counts, greedy_counts

def plot_grid_coverage_comparison(data, time_limit_minutes=None, output_prefix="coverage_comparison"):
    """生成格网覆盖对比图"""
    print(f"{'='*70}")
    print(f"生成格网覆盖对比图 (time_limit={time_limit_minutes}min)...")
    print(f"{'='*70}")
    
    # 计算两种格网的覆盖次数
    ico_grids, ico_original, ico_greedy = calculate_grid_coverage_counts(
        data, 'Icosahedral', time_limit_minutes
    )
    ll_grids, ll_original, ll_greedy = calculate_grid_coverage_counts(
        data, 'LatLon', time_limit_minutes
    )
    
    if not ico_grids or not ll_grids:
        print("[警告] 格网数据不足，无法生成统计图")
        return
    
    # 创建图表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 11))
    
    # 图1: 二十面体格网 (DGD - Discrete Global Grid)
    ax1.plot(range(len(ico_grids)), ico_original, color='#1f77b4', linestyle='-', linewidth=2,
            label='DGD Original Coverage', alpha=0.8)
    ax1.plot(range(len(ico_grids)), ico_greedy, color='#ff7f0e', linestyle='-', linewidth=2,
            label='DGD with Greedy Selection', alpha=0.8)
    
    ax1.set_xlabel('Seq Num of Global Discrete Grids', fontsize=15)
    ax1.set_ylabel('Coverage Count', fontsize=15)
    ax1.tick_params(axis='both', which='major', labelsize=16)
    ax1.grid(True, alpha=0.3)
    # 去掉四周边框
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_visible(False)
    ax1.spines['bottom'].set_visible(False)
    
    # 添加统计信息
    ico_orig_avg = np.mean(ico_original) if ico_original else 0
    ico_greedy_avg = np.mean(ico_greedy) if ico_greedy else 0
    ax1.text(0.02, 0.98,
            f'DGD Grids: {len(ico_grids)}\n' +
            f'Avg Original: {ico_orig_avg:.1f}\n' +
            f'Avg Greedy: {ico_greedy_avg:.1f}',
            transform=ax1.transAxes, fontsize=16,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # 图例移到图上方，无边框，大字体
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, 1.08), ncol=2, fontsize=18, frameon=False)
    
    # 图2: 经纬度格网 (LLP - Long-Lat Partition)
    ax2.plot(range(len(ll_grids)), ll_original, color='#2ca02c', linestyle='-', linewidth=2,
            label='LLP Original Coverage', alpha=0.8)
    ax2.plot(range(len(ll_grids)), ll_greedy, color='#d62728', linestyle='-', linewidth=2,
            label='LLP with Greedy Selection', alpha=0.8)
    
    ax2.set_xlabel('Seq Num of Long-Lat Partition Unit', fontsize=15)
    ax2.set_ylabel('Coverage Count', fontsize=15)
    ax2.tick_params(axis='both', which='major', labelsize=16)
    ax2.grid(True, alpha=0.3)
    # 去掉四周边框
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.spines['left'].set_visible(False)
    ax2.spines['bottom'].set_visible(False)
    
    # 添加统计信息
    ll_orig_avg = np.mean(ll_original) if ll_original else 0
    ll_greedy_avg = np.mean(ll_greedy) if ll_greedy else 0
    ax2.text(0.02, 0.98,
            f'LLP Grids: {len(ll_grids)}\n' +
            f'Avg Original: {ll_orig_avg:.1f}\n' +
            f'Avg Greedy: {ll_greedy_avg:.1f}',
            transform=ax2.transAxes, fontsize=16,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
    
    # 图例移到图上方，无边框，大字体
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.08), ncol=2, fontsize=18, frameon=False)
    
    plt.tight_layout()
    
    # 保存图表
    if time_limit_minutes:
        filename = f"{output_prefix}_{time_limit_minutes}min.png"
    else:
        filename = f"{output_prefix}_full.png"
    
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"✓ 统计图已保存: {filename}")
    plt.close()

def plot_satellite_coverage_comparison(data, time_limit_minutes=None, output_prefix="satellite_coverage_comparison"):
    """生成单星覆盖对比图"""
    print(f"{'='*70}")
    print(f"生成单星覆盖对比图 (time_limit={time_limit_minutes}min)...")
    print(f"{'='*70}")
    
    # 计算两种格网下每颗卫星的覆盖数量
    ico_sats, ico_original, ico_greedy = calculate_satellite_coverage_counts(
        data, 'Icosahedral', time_limit_minutes
    )
    ll_sats, ll_original, ll_greedy = calculate_satellite_coverage_counts(
        data, 'LatLon', time_limit_minutes
    )
    
    if not ico_sats or not ll_sats:
        print("[警告] 卫星数据不足，无法生成统计图")
        return
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(16, 8))
    
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
    
    ax.set_xlabel('Seq Num of Satellite', fontsize=20)
    ax.set_ylabel('Coverage Count', fontsize=20)
    ax.tick_params(axis='both', which='major', labelsize=16)
    ax.grid(True, alpha=0.3)
    # 去掉四周边框
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    # 图例移到图上方，无边框，大字体
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.05), ncol=4, fontsize=18, frameon=False)
    
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
            transform=ax.transAxes, fontsize=16,
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

def plot_grid_cell_coverage_timeline(data, grid_cells=None, time_limit_minutes=None, output_prefix="grid_cell_coverage_timeline"):
    """
    生成部分格网单元的卫星覆盖时间线图
    
    Args:
        data: 数据字典
        grid_cells: 要显示的格网单元列表，例如 ['F00_001', 'F00_010', 'F00_100', 'F01_000']
        time_limit_minutes: 时间限制（分钟），None表示使用全部数据
        output_prefix: 输出文件名前缀
    """
    print(f"{'='*70}")
    print(f"生成格网单元覆盖时间线图 (time_limit={time_limit_minutes}min)...")
    print(f"{'='*70}")
    
    # 默认选择一些格网单元
    if grid_cells is None:
        # 尝试使用默认的格网单元
        if 'Icosahedral' in data['grid_info']:
            all_grids = data['grid_info']['Icosahedral']['grids']
            # 选择前几个格网作为示例
            grid_cells = []
            for grid_id in ['F00_001', 'F00_010', 'F00_100', 'F01_000']:
                if grid_id in all_grids:
                    grid_cells.append(grid_id)
            
            # 如果没找到，就选前4个
            if len(grid_cells) < 4:
                grid_cells = sorted(all_grids)[:4]
        else:
            print("[警告] 没有二十面体格网数据")
            return
    
    if not grid_cells:
        print("[警告] 没有可用的格网单元")
        return
    
    print(f"选择的格网单元: {', '.join(grid_cells)}")
    
    # 为每个格网单元收集覆盖数据
    grid_coverage_events = {}
    satellite_name_to_id = {}  # 卫星名称到序号的映射
    
    # 创建卫星序号映射
    for idx, sat_name in enumerate(sorted(data['satellites'])):
        satellite_name_to_id[sat_name] = idx
    
    for grid_id in grid_cells:
        grid_coverage_events[grid_id] = []
        
        if grid_id in data['original_coverage']['Icosahedral']:
            for sat_name, timestamps in data['original_coverage']['Icosahedral'][grid_id].items():
                sat_id = satellite_name_to_id[sat_name]
                
                # 过滤时间限制
                if time_limit_minutes:
                    valid_timestamps = [ts for ts in timestamps if ts < time_limit_minutes]
                else:
                    valid_timestamps = timestamps
                
                # 为每个时间戳创建一个事件
                for ts in valid_timestamps:
                    grid_coverage_events[grid_id].append((ts, sat_id))
    
    # 创建图表 - 更宽的尺寸以便清晰显示时间线
    fig, ax = plt.subplots(figsize=(20, 8))
    
    # 定义颜色和标记
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    markers = ['o', 's', '^', 'v']
    
    # 绘制每个格网单元的覆盖事件
    for idx, grid_id in enumerate(grid_cells):
        if grid_id not in grid_coverage_events:
            continue
        
        events = grid_coverage_events[grid_id]
        if not events:
            continue
        
        # 按卫星ID分组
        satellite_tracks = {}
        for time, sat_id in events:
            if sat_id not in satellite_tracks:
                satellite_tracks[sat_id] = []
            satellite_tracks[sat_id].append(time)
        
        color = colors[idx % len(colors)]
        marker = markers[idx % len(markers)]
        
        # 为每颗卫星绘制连续的覆盖段
        for sat_id, times_list in satellite_tracks.items():
            times_sorted = sorted(times_list)
            
            # 将时间点分组为连续的覆盖段
            # 如果两个时间点之间间隔 > 2分钟，认为是不同的覆盖段
            max_gap = 2  # 最大间隔（分钟）
            
            coverage_segments = []
            current_segment = [times_sorted[0]]
            
            for i in range(1, len(times_sorted)):
                if times_sorted[i] - times_sorted[i-1] <= max_gap:
                    # 连续覆盖，加入当前段
                    current_segment.append(times_sorted[i])
                else:
                    # 间隔太大，开始新的覆盖段
                    coverage_segments.append(current_segment)
                    current_segment = [times_sorted[i]]
            
            # 添加最后一段
            coverage_segments.append(current_segment)
            
            # 绘制每个连续覆盖段
            for segment in coverage_segments:
                if len(segment) >= 2:
                    # 只有至少2个点才绘制线条
                    sat_ids_segment = [sat_id] * len(segment)
                    ax.plot(segment, sat_ids_segment,
                           color=color, linewidth=1.5, alpha=0.4)
        
        # 绘制采样后的点（叠加在线条上）- 减少密集度
        all_times = [e[0] for e in events]
        all_sat_ids = [e[1] for e in events]
        
        # 对点进行采样以减少密集度
        max_points_per_grid = 500  # 每个格网单元最多显示的点数
        if len(all_times) > max_points_per_grid:
            # 均匀采样
            step = len(all_times) // max_points_per_grid
            sampled_indices = list(range(0, len(all_times), step))
            sampled_times = [all_times[i] for i in sampled_indices]
            sampled_sat_ids = [all_sat_ids[i] for i in sampled_indices]
        else:
            sampled_times = all_times
            sampled_sat_ids = all_sat_ids
        
        ax.scatter(sampled_times, sampled_sat_ids,
                  color=color, marker=marker,
                  s=12, alpha=0.6, label=grid_id, zorder=3)
    
    ax.set_xlabel('Test Duration (minutes)', fontsize=20)
    ax.set_ylabel('Seq Num of Satellite', fontsize=20)
    ax.tick_params(axis='both', which='major', labelsize=16)
    ax.grid(True, alpha=0.3)
    # 去掉四周边框
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    # 图例移到图上方，无边框，大字体
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.05), ncol=4, fontsize=18, frameon=False)
    
    # 添加统计信息
    stats_lines = [f'Total Satellites: {len(data["satellites"])}']
    for grid_id in grid_cells:
        if grid_id in grid_coverage_events:
            event_count = len(grid_coverage_events[grid_id])
            unique_sats = len(set([e[1] for e in grid_coverage_events[grid_id]]))
            stats_lines.append(f'{grid_id}: {event_count} events, {unique_sats} satellites')
    
    stats_text = '\n'.join(stats_lines)
    ax.text(0.02, 0.98, stats_text,
            transform=ax.transAxes, fontsize=16,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
    
    plt.tight_layout()
    
    # 保存图表
    if time_limit_minutes:
        filename = f"{output_prefix}_{time_limit_minutes}min.png"
    else:
        filename = f"{output_prefix}_full.png"
    
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"✓ 格网单元覆盖时间线图已保存: {filename}")
    plt.close()

def generate_all_plots(data, time_limits=None):
    """生成所有统计图"""
    print(f"\n{'='*70}")
    print("开始生成统计图表")
    print(f"{'='*70}\n")
    
    sim_duration = data['metadata']['simulation_duration_minutes']
    
    # 确定时间限制
    if time_limits is None:
        if sim_duration < 100:
            time_limits = [int(sim_duration * 0.5), int(sim_duration)]
            print(f"[自适应] 模拟时长不足100分钟，使用时间段: {time_limits}")
        else:
            time_limits = [100, 1440]  # 100分钟和24小时
    
    # 生成格网覆盖对比图
    print("\n[1/3] 生成格网覆盖对比图...")
    for time_limit in time_limits:
        plot_grid_coverage_comparison(data, time_limit_minutes=time_limit)
    
    # 生成单星覆盖对比图
    print("\n[2/3] 生成单星覆盖对比图...")
    for time_limit in time_limits:
        plot_satellite_coverage_comparison(data, time_limit_minutes=time_limit)
    
    # 生成格网单元覆盖时间线图
    print("\n[3/3] 生成格网单元覆盖时间线图...")
    for time_limit in time_limits:
        plot_grid_cell_coverage_timeline(data, time_limit_minutes=time_limit)
    
    print(f"\n{'='*70}")
    print("✓ 所有统计图生成完成！")
    print(f"{'='*70}")
    print("\n格网覆盖对比图:")
    for time_limit in time_limits:
        print(f"  - coverage_comparison_{time_limit}min.png")
    print("\n单星覆盖对比图:")
    for time_limit in time_limits:
        print(f"  - satellite_coverage_comparison_{time_limit}min.png")
    print("\n格网单元覆盖时间线图:")
    for time_limit in time_limits:
        print(f"  - grid_cell_coverage_timeline_{time_limit}min.png")
    print(f"{'='*70}\n")

def main():
    parser = argparse.ArgumentParser(description='格网覆盖数据绘图分析工具')
    parser.add_argument('data_file', help='数据文件路径 (.pkl)')
    parser.add_argument('--time-limits', nargs='+', type=int, 
                        help='时间限制（分钟），例如: --time-limits 100 1440')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.data_file):
        print(f"[错误] 文件不存在: {args.data_file}")
        sys.exit(1)
    
    # 加载数据
    data = load_data(args.data_file)
    
    # 生成统计图
    generate_all_plots(data, time_limits=args.time_limits)

if __name__ == "__main__":
    main()

