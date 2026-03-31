#!/usr/bin/env python3
"""
格网编码转序列号工具
输入二十面体格网编码（如 F00_012），输出对应的序列号

编码格式：F##_path
- F## : 基础面ID (00-19)
- path: 四叉树路径，每位是0-3的数字
"""

import sys
import re


def parse_grid_code(code_string):
    """
    解析格网编码
    
    Args:
        code_string: 格网编码字符串，如 "F00_012" 或 "F5"
        
    Returns:
        (base_face_id, level, path_code) 或 None（解析失败）
    """
    # 移除空白字符
    code_string = code_string.strip()
    
    # 匹配格式: F##_path 或 F## 或 F#_path 或 F#
    match = re.match(r'^F(\d{1,2})(?:_(\d*))?$', code_string, re.IGNORECASE)
    
    if not match:
        return None
    
    base_face_id = int(match.group(1))
    path_str = match.group(2) if match.group(2) else ""
    
    # 验证基础面ID
    if base_face_id < 0 or base_face_id >= 20:
        return None
    
    # 验证路径字符串
    if path_str:
        if not all(c in '0123' for c in path_str):
            return None
    
    level = len(path_str)
    
    # 将路径字符串转换为序号（四进制转十进制）
    path_code = 0
    for i, c in enumerate(path_str):
        branch = int(c)
        path_code = path_code * 4 + branch
    
    return (base_face_id, level, path_code)


def grid_code_to_index(code_string):
    """
    将格网编码转换为序列号
    
    序列号计算规则：
    - 同一级别的格网按顺序排列
    - 先按基础面ID排序（0-19）
    - 再按四叉树路径排序（0-3的组合）
    
    Args:
        code_string: 格网编码字符串
        
    Returns:
        序列号（int）或 None（解析失败）
    """
    parsed = parse_grid_code(code_string)
    if parsed is None:
        return None
    
    base_face_id, level, path_code = parsed
    
    # 计算序列号
    # 对于n级格网：序列号 = 基础面ID * 4^n + 路径编码序号
    grids_per_face = 4 ** level if level > 0 else 1
    index = base_face_id * grids_per_face + path_code
    
    return index


def index_to_grid_code(index, level):
    """
    将序列号转换为格网编码（反向操作）
    
    Args:
        index: 序列号
        level: 细分级别
        
    Returns:
        格网编码字符串
    """
    if level < 0:
        return None
    
    grids_per_face = 4 ** level if level > 0 else 1
    total_grids = 20 * grids_per_face
    
    if index < 0 or index >= total_grids:
        return None
    
    # 计算基础面ID
    base_face_id = index // grids_per_face
    path_code = index % grids_per_face
    
    # 将路径编码转换为字符串（十进制转四进制）
    if level == 0:
        path_str = ""
    else:
        path_digits = []
        for _ in range(level):
            path_digits.append(str(path_code % 4))
            path_code //= 4
        path_str = ''.join(reversed(path_digits))
    
    # 构建编码字符串
    if path_str:
        return f"F{base_face_id:02d}_{path_str}"
    else:
        return f"F{base_face_id:02d}"


def print_level_info(level):
    """打印指定级别的格网信息"""
    grids_per_face = 4 ** level if level > 0 else 1
    total_grids = 20 * grids_per_face
    
    print(f"\n{'='*60}")
    print(f"Level {level} 格网信息:")
    print(f"{'='*60}")
    print(f"  每个面的格网数: {grids_per_face}")
    print(f"  总格网数: {total_grids}")
    print(f"  序列号范围: 0 ~ {total_grids - 1}")
    
    # 显示一些示例
    print(f"\n  示例编码:")
    examples = [0, grids_per_face - 1, grids_per_face, total_grids - 1]
    for idx in examples:
        if idx < total_grids:
            code = index_to_grid_code(idx, level)
            print(f"    序列号 {idx:5d} -> {code}")


def interactive_mode():
    """交互式查询模式"""
    print("="*60)
    print("二十面体格网编码 <-> 序列号 转换工具")
    print("="*60)
    print("\n编码格式: F##_path")
    print("  F## : 基础面ID (00-19)")
    print("  path: 四叉树路径 (0-3的数字组合)")
    print("\n示例:")
    print("  F00     -> 0级格网，面0")
    print("  F00_0   -> 1级格网，面0，子单元0")
    print("  F00_012 -> 3级格网，面0，路径0->1->2")
    print("\n输入命令:")
    print("  直接输入格网编码 -> 查询序列号")
    print("  输入 'r 序列号 级别' -> 反向查询编码")
    print("  输入 'info 级别' -> 显示级别信息")
    print("  输入 'q' 或 'quit' -> 退出")
    print("="*60)
    
    while True:
        try:
            user_input = input("\n请输入> ").strip()
            
            if not user_input:
                continue
            
            # 退出命令
            if user_input.lower() in ['q', 'quit', 'exit']:
                print("再见！")
                break
            
            # 反向查询命令: r 序列号 级别
            if user_input.lower().startswith('r '):
                parts = user_input.split()
                if len(parts) != 3:
                    print("❌ 用法: r <序列号> <级别>")
                    print("   例如: r 100 2")
                    continue
                
                try:
                    index = int(parts[1])
                    level = int(parts[2])
                    code = index_to_grid_code(index, level)
                    
                    if code is None:
                        print(f"❌ 无效的序列号或级别")
                    else:
                        print(f"\n✓ 序列号 {index} (Level {level}) -> {code}")
                except ValueError:
                    print("❌ 请输入有效的数字")
                continue
            
            # 显示级别信息命令: info 级别
            if user_input.lower().startswith('info '):
                parts = user_input.split()
                if len(parts) != 2:
                    print("❌ 用法: info <级别>")
                    print("   例如: info 3")
                    continue
                
                try:
                    level = int(parts[1])
                    if level < 0 or level > 10:
                        print("❌ 级别应在 0-10 之间")
                    else:
                        print_level_info(level)
                except ValueError:
                    print("❌ 请输入有效的级别数字")
                continue
            
            # 默认：解析为格网编码
            index = grid_code_to_index(user_input)
            
            if index is None:
                print(f"❌ 无效的格网编码: {user_input}")
                print("   格式应为: F##_path (如 F00_012)")
            else:
                parsed = parse_grid_code(user_input)
                base_face_id, level, path_code = parsed
                
                print(f"\n✓ 格网编码: {user_input}")
                print(f"  ├─ 序列号: {index}")
                print(f"  ├─ 基础面ID: {base_face_id}")
                print(f"  ├─ 细分级别: {level}")
                if level > 0:
                    print(f"  └─ 路径编码: {path_code} (四进制)")
                
                # 显示同级别的范围信息
                grids_per_face = 4 ** level if level > 0 else 1
                total_grids = 20 * grids_per_face
                print(f"\n  Level {level} 信息:")
                print(f"    总格网数: {total_grids}")
                print(f"    序列号范围: 0 ~ {total_grids - 1}")
                
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except EOFError:
            print("\n\n再见！")
            break


def main():
    """主函数"""
    if len(sys.argv) > 1:
        # 命令行模式
        code_string = sys.argv[1]
        
        # 检查是否是反向查询
        if sys.argv[1] == '-r' and len(sys.argv) == 4:
            try:
                index = int(sys.argv[2])
                level = int(sys.argv[3])
                code = index_to_grid_code(index, level)
                
                if code is None:
                    print(f"错误: 无效的序列号或级别")
                    sys.exit(1)
                else:
                    print(code)
                    sys.exit(0)
            except ValueError:
                print("错误: 序列号和级别必须是整数")
                sys.exit(1)
        
        # 正常查询
        index = grid_code_to_index(code_string)
        
        if index is None:
            print(f"错误: 无效的格网编码 '{code_string}'")
            print("格式应为: F##_path (如 F00_012)")
            sys.exit(1)
        else:
            print(index)
            sys.exit(0)
    else:
        # 交互式模式
        interactive_mode()


if __name__ == "__main__":
    main()

