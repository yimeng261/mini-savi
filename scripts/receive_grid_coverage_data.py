#!/usr/bin/env python3
"""
Unix Socket接收器：监听Unix socket接收格网覆盖数据
支持二十面体和经纬度两种格网类型
实现贪心算法选择卫星覆盖
将数据保存到文件供后续分析
"""

import socket
import os
import sys
import time
import json
import pickle
import re
from pathlib import Path
from datetime import datetime
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

def detect_grid_level(grid_count: int, grid_type: GridType) -> str:
    """
    根据格网数量检测划分等级
    
    公式：
    - 二十面体格网数量 = 20 × (4^level)
    - 经纬度格网数量 = 2 × (level^2)
    
    等级对应：
    - 二十面体: Level 0: 20, Level 1: 80, Level 2: 320, Level 3: 1280, Level 4: 5120, Level 5: 20480
    - 经纬度: Level 1: 2, Level 36: 2592, Level 180: 64800
    """
    import math
    
    if grid_type == GridType.ICOSAHEDRAL:
        # N = 20 * (4^level)
        # level = log4(N/20) = log(N/20) / log(4)
        if grid_count < 20:
            return f"Level0_Partial({grid_count}/20)"
        
        level_float = math.log(grid_count / 20) / math.log(4)
        level = round(level_float)
        
        # 计算理论格网数
        theoretical_count = 20 * (4 ** level)
        
        # 检查是否接近理论值（允许10%误差）
        if abs(grid_count - theoretical_count) / theoretical_count < 0.1:
            return f"Level{level}"
        else:
            # 不完全匹配，显示实际数量
            return f"Level{level}_Approx({grid_count}/{theoretical_count})"
    
    elif grid_type == GridType.LATLON:
        # N = 2 * level^2
        # level = sqrt(N / 2)
        if grid_count < 2:
            return f"Invalid({grid_count})"
        
        level_float = math.sqrt(grid_count / 2)
        level = round(level_float)
        
        # 计算理论格网数
        theoretical_count = 2 * (level ** 2)
        
        # 检查是否接近理论值（允许5%误差）
        if abs(grid_count - theoretical_count) / theoretical_count < 0.05:
            return f"{level}x{level*2}"
        else:
            # 不完全匹配，显示近似值
            return f"{level}x{level*2}_Approx({grid_count}/{theoretical_count})"
    
    return "Unknown"

FRAGMENT_RE = re.compile(r"^(?P<sat_id>[^@]+)@(?P<index>\d+)/(?P<total>\d+)$")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "experiments"


def process_coverage_message(message: str, analyzer, pending_fragments: Dict[str, Dict]) -> bool:
    """解析单条覆盖消息；若形成完整记录则写入分析器并返回True。"""
    parts = message.split(':', 1)
    if len(parts) != 2:
        return False

    sat_token = parts[0]
    grid_codes = parts[1].split(',') if parts[1] else []

    fragment_match = FRAGMENT_RE.match(sat_token)
    if fragment_match:
        sat_id = fragment_match.group("sat_id")
        fragment_index = int(fragment_match.group("index"))
        fragment_total = int(fragment_match.group("total"))

        pending = pending_fragments.get(sat_id)
        if (
            pending is None
            or pending["total"] != fragment_total
            or fragment_index == 1
        ):
            pending = {"total": fragment_total, "parts": {}}
            pending_fragments[sat_id] = pending

        pending["parts"][fragment_index] = grid_codes

        if len(pending["parts"]) != fragment_total:
            return False

        merged_codes: List[str] = []
        for idx in range(1, fragment_total + 1):
            if idx not in pending["parts"]:
                return False
            merged_codes.extend(pending["parts"][idx])

        del pending_fragments[sat_id]
        if merged_codes:
            analyzer.add_coverage_data(sat_id, merged_codes)
            return True
        return False

    if grid_codes:
        analyzer.add_coverage_data(sat_token, grid_codes)
        return True

    return False

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
            time_series: [(satellite_id, [timestamps])] 格式的时间序列
        
        Returns:
            float: 覆盖时长（唯一时间点的数量）
        """
        # 收集所有时间戳
        all_times = set()
        for sat_id, timestamps in time_series:
            all_times.update(timestamps)
        
        # 返回唯一时间点的数量（分钟数）
        return len(all_times)
    
    def apply_greedy_algorithm_for_type(self, grid_type: GridType):
        """
        为指定格网类型应用贪心算法
        
        Args:
            grid_type: 格网类型（ICOSAHEDRAL 或 LATLON）
        """
        if grid_type not in self.grid_types_detected:
            print(f"[跳过] {grid_type.value} 格网未检测到数据")
            return
        
        print(f"\n{'='*70}")
        print(f"开始对 {grid_type.value} 格网应用贪心算法...")
        print(f"{'='*70}")
        
        # 总模拟时长（分钟）
        total_duration = self.get_simulation_duration()
        
        # 目标覆盖时长 = 总时长 * 目标覆盖率
        target_duration = total_duration * self.target_coverage_ratio
        
        print(f"格网类型: {grid_type.value}")
        print(f"目标覆盖率: {self.target_coverage_ratio*100:.0f}%")
        print(f"总模拟时长: {total_duration} 分钟")
        print(f"目标覆盖时长: {target_duration:.1f} 分钟")
        
        # 统计信息
        processed_grids = 0
        total_grids = len(self.unique_grids[grid_type])
        
        # 对每个格网应用贪心算法
        for grid_id in sorted(self.unique_grids[grid_type]):
            processed_grids += 1
            if processed_grids % 100 == 0:
                print(f"[进度] 处理了 {processed_grids}/{total_grids} 个格网...")
            
            # 准备该格网的时间序列数据
            time_series = []
            for sat_id, timestamps in self.original_coverage[grid_type][grid_id].items():
                if timestamps:  # 只包含有覆盖记录的卫星
                    time_series.append((sat_id, timestamps))
            
            if not time_series:
                continue
            
            # 应用贪心算法
            selected_satellites = []
            covered_duration = 0
            covered_times = set()
            
            while covered_duration < target_duration and time_series:
                # 找到能增加最多覆盖时长的卫星
                best_sat = None
                best_增益 = 0
                best_new_times = set()
                
                for sat_id, timestamps in time_series:
                    new_times = set(timestamps) - covered_times
                    增益 = len(new_times)
                    
                    if 增益 > best_增益:
                        best_增益 = 增益
                        best_sat = sat_id
                        best_new_times = new_times
                
                if best_sat is None or best_增益 == 0:
                    break  # 无法再增加覆盖
                
                # 选择该卫星
                selected_timestamps = [t for t in self.original_coverage[grid_type][grid_id][best_sat]]
                selected_satellites.append((best_sat, selected_timestamps))
                covered_times.update(best_new_times)
                covered_duration = len(covered_times)
                
                # 从候选列表中移除已选择的卫星
                time_series = [(s, t) for s, t in time_series if s != best_sat]
            
            # 保存贪心选择结果
            self.greedy_coverage[grid_type][grid_id] = selected_satellites
        
        print(f"\n✓ {grid_type.value} 格网贪心算法完成")
        print(f"  处理格网数: {processed_grids}")
    
    def apply_greedy_algorithm(self):
        """对所有检测到的格网类型应用贪心算法"""
        print(f"\n{'='*70}")
        print("应用贪心算法优化卫星选择")
        print(f"{'='*70}")
        
        for grid_type in self.grid_types_detected:
            self.apply_greedy_algorithm_for_type(grid_type)
        
        print(f"\n{'='*70}")
        print("✓ 所有格网类型贪心算法处理完成")
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
            print(f"真实数据收集时长: {real_duration:.2f}秒 ({real_duration/60:.2f}分钟)")
        
        print(f"\n按格网类型统计:")
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            if grid_type in self.grid_types_detected:
                grid_count = len(self.unique_grids[grid_type])
                grid_level = detect_grid_level(grid_count, grid_type)
                print(f"  {grid_type.value}:")
                print(f"    唯一格网数: {grid_count}")
                print(f"    检测等级: {grid_level}")
                
                # 统计贪心选择后的卫星数量
                if self.greedy_coverage[grid_type]:
                    total_selected_sats = set()
                    for selected_list in self.greedy_coverage[grid_type].values():
                        for sat_id, _ in selected_list:
                            total_selected_sats.add(sat_id)
                    
                    reduction = (1 - len(total_selected_sats) / len(self.unique_sats)) * 100
                    print(f"    原始卫星数: {len(self.unique_sats)}")
                    print(f"    贪心选择后: {len(total_selected_sats)}")
                    print(f"    节省率: {reduction:.1f}%")
        
        print(f"{'='*70}")
    
    def generate_filename(self) -> str:
        """
        生成智能文件名，基于格网等级和卫星数量
        
        格式: ico<level>_ll<level>_<sat_count>sats.pkl
        例如: icolevel3_ll36x72_110sats.pkl
        """
        # 检测各格网类型的等级
        ico_level = "none"
        latlon_level = "none"
        
        if GridType.ICOSAHEDRAL in self.grid_types_detected:
            ico_count = len(self.unique_grids[GridType.ICOSAHEDRAL])
            ico_level_raw = detect_grid_level(ico_count, GridType.ICOSAHEDRAL)
            # 只保留主要等级信息，去掉 Approx 等后缀
            if '_Approx' in ico_level_raw:
                ico_level_raw = ico_level_raw.split('_Approx')[0]
            elif '_Partial' in ico_level_raw:
                ico_level_raw = ico_level_raw.split('_Partial')[0]
            ico_level = ico_level_raw.lower()
        
        if GridType.LATLON in self.grid_types_detected:
            latlon_count = len(self.unique_grids[GridType.LATLON])
            latlon_level_raw = detect_grid_level(latlon_count, GridType.LATLON)
            # 只保留主要等级信息
            if '_Approx' in latlon_level_raw:
                latlon_level_raw = latlon_level_raw.split('_Approx')[0]
            latlon_level = latlon_level_raw.lower()
        
        sat_count = len(self.unique_sats)
        
        filename = f"ico{ico_level}_ll{latlon_level}_{sat_count}sats.pkl"
        return filename
    
    def save_data(self, filename=None, output_dir=DEFAULT_OUTPUT_DIR):
        """
        保存数据到文件
        
        Args:
            filename: 指定文件名，如果为None则自动生成
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = output_dir / self.generate_filename()
        else:
            filename = Path(filename)
            if not filename.is_absolute():
                filename = output_dir / filename
        
        print(f"\n{'='*70}")
        print("保存数据到文件...")
        print(f"{'='*70}")
        
        # 准备要保存的数据
        data = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'time_step': self.time_step,
                'target_coverage_ratio': self.target_coverage_ratio,
                'simulation_duration_minutes': self.get_simulation_duration(),
                'total_messages': self.total_messages,
                'unique_satellite_count': len(self.unique_sats),
                'grid_types_detected': [gt.value for gt in self.grid_types_detected],
                'real_collection_duration': self.real_current_time - self.real_start_time if self.real_start_time else 0,
            },
            'grid_info': {},
            'satellites': list(self.unique_sats),
            'satellite_message_count': dict(self.satellite_message_count),
            'original_coverage': {},
            'greedy_coverage': {},
        }
        
        # 添加格网信息
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            if grid_type in self.grid_types_detected:
                grid_count = len(self.unique_grids[grid_type])
                data['grid_info'][grid_type.value] = {
                    'count': grid_count,
                    'level': detect_grid_level(grid_count, grid_type),
                    'grids': list(self.unique_grids[grid_type])
                }
        
        # 转换原始覆盖数据（将defaultdict转换为普通dict）
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            if grid_type in self.grid_types_detected:
                data['original_coverage'][grid_type.value] = {}
                for grid_id, sat_dict in self.original_coverage[grid_type].items():
                    data['original_coverage'][grid_type.value][grid_id] = dict(sat_dict)
        
        # 转换贪心覆盖数据
        for grid_type in [GridType.ICOSAHEDRAL, GridType.LATLON]:
            if grid_type in self.grid_types_detected:
                data['greedy_coverage'][grid_type.value] = {}
                for grid_id, selected_list in self.greedy_coverage[grid_type].items():
                    data['greedy_coverage'][grid_type.value][grid_id] = selected_list
        
        # 保存为pickle文件（保留完整数据结构）
        with open(filename, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        file_size = os.path.getsize(filename) / (1024 * 1024)  # MB
        print(f"✓ 数据已保存: {filename}")
        print(f"  文件大小: {file_size:.2f} MB")
        
        # 同时生成一个JSON元数据文件（便于查看）
        meta_filename = filename.with_name(filename.stem + '_meta.json')
        with open(meta_filename, 'w', encoding='utf-8') as f:
            json.dump(data['metadata'], f, indent=2, ensure_ascii=False)
            f.write('\n\n')
            json.dump(data['grid_info'], f, indent=2, ensure_ascii=False)
        
        print(f"✓ 元数据已保存: {meta_filename}")
        print(f"{'='*70}")
        
        return str(filename)

def receive_grid_coverage_data():
    """主函数：接收数据并保存"""
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
        print("按 Ctrl+C 停止接收并保存数据")
        print(f"{'='*70}\n")
        
        last_print_time = time.time()
        pending_fragments: Dict[str, Dict] = {}
        
        while True:
            # 接收数据（最大64KB）
            data, addr = sock.recvfrom(65536)
            
            # 记录真实开始时间
            if analyzer.real_start_time is None:
                analyzer.real_start_time = time.time()
            analyzer.real_current_time = time.time()
            
            try:
                # 解析数据
                message = data.decode('utf-8').strip()
                if not message:
                    continue
                
                if not process_coverage_message(message, analyzer, pending_fragments):
                    parts = message.split(':', 1)
                    if len(parts) == 2 and parts[1]:
                        continue
                    print(f"[警告] 无效消息格式: {message[:50]}")
                    continue
                
                # 定期打印进度
                current_time = time.time()
                if current_time - last_print_time >= 5.0:  # 每5秒打印一次
                    elapsed = current_time - analyzer.real_start_time
                    sim_duration = analyzer.get_simulation_duration()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"收到 {analyzer.total_messages} 条消息, "
                          f"模拟时长: {sim_duration}分钟, "
                          f"卫星数: {len(analyzer.unique_sats)}, "
                          f"耗时: {elapsed:.1f}秒")
                    last_print_time = current_time
                
            except UnicodeDecodeError as e:
                print(f"[错误] Unicode解码失败: {e}")
                continue
            except Exception as e:
                print(f"[错误] 处理消息时出错: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    except KeyboardInterrupt:
        print(f"\n\n{'='*70}")
        print("收到停止信号，准备保存数据...")
        print(f"{'='*70}")
        
        # 打印统计信息
        analyzer.print_statistics()
        
        # 应用贪心算法
        if analyzer.total_messages > 0:
            analyzer.apply_greedy_algorithm()
            
            # 打印贪心算法后的统计
            analyzer.print_statistics()
            
            # 保存数据
            filename = analyzer.save_data()
            
            print(f"\n{'='*70}")
            print("数据接收完成")
            print(f"{'='*70}")
            print(f"✓ 数据文件: {filename}")
            print(f"✓ 后续可使用 scripts/plot_grid_coverage.py 进行绘图分析")
            print(f"{'='*70}\n")
        else:
            print("\n[警告] 未收到任何数据，跳过保存")
    
    except Exception as e:
        print(f"\n[错误] 发生异常: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理
        sock.close()
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        print("Unix socket已关闭")

if __name__ == "__main__":
    receive_grid_coverage_data()
