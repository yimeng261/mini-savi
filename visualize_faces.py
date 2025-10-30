#!/usr/bin/env python3
"""
可视化二十面体面的几何特征
"""
import math

# 标准二十面体的12个顶点
icosahedron_vertices = [
    # 北极点
    (0.000000, 0.000000, 1.000000),
    
    # 上环（5个顶点）
    (0.894427, 0.000000, 0.447214),
    (0.276393, 0.850651, 0.447214),
    (-0.723607, 0.525731, 0.447214),
    (-0.723607, -0.525731, 0.447214),
    (0.276393, -0.850651, 0.447214),
    
    # 下环（5个顶点）
    (0.723607, 0.525731, -0.447214),
    (-0.276393, 0.850651, -0.447214),
    (-0.894427, 0.000000, -0.447214),
    (-0.276393, -0.850651, -0.447214),
    (0.723607, -0.525731, -0.447214),
    
    # 南极点
    (0.000000, 0.000000, -1.000000)
]

# 调整后的面定义
icosahedron_faces = [
    # 北极三角形（5个）
    (0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 1),
    
    # 上层斜向三角形（5个）
    (1, 6, 7), (2, 7, 8), (3, 8, 9), (4, 9, 10), (5, 10, 6),
    
    # 下层斜向三角形（5个）
    (1, 7, 6), (2, 8, 7), (3, 9, 8), (4, 10, 9), (5, 6, 10),
    
    # 南极三角形（5个）
    (11, 7, 6), (11, 8, 7), (11, 9, 8), (11, 10, 9), (11, 6, 10)
]

def xyz_to_lonlat(x, y, z):
    """转换3D坐标到经纬度"""
    lon = math.atan2(y, x) * 180.0 / math.pi
    lat = math.asin(z) * 180.0 / math.pi
    return lon, lat

def main():
    print("=" * 80)
    print("二十面体面的几何特征可视化")
    print("=" * 80)
    print()
    
    # 按类型分组
    face_groups = {
        "北极三角形": list(range(0, 5)),
        "上层斜向三角形": list(range(5, 10)),
        "下层斜向三角形": list(range(10, 15)),
        "南极三角形": list(range(15, 20))
    }
    
    for group_name, face_indices in face_groups.items():
        print(f"\n{group_name} (面 {face_indices[0]}-{face_indices[-1]})")
        print("-" * 80)
        
        for face_idx in face_indices:
            v1_idx, v2_idx, v3_idx = icosahedron_faces[face_idx]
            
            v1 = icosahedron_vertices[v1_idx]
            v2 = icosahedron_vertices[v2_idx]
            v3 = icosahedron_vertices[v3_idx]
            
            lon1, lat1 = xyz_to_lonlat(*v1)
            lon2, lat2 = xyz_to_lonlat(*v2)
            lon3, lat3 = xyz_to_lonlat(*v3)
            
            lat_diff_23 = abs(lat2 - lat3)
            
            # 创建可视化字符串
            status = "✓" if lat_diff_23 < 0.01 else "✗"
            
            print(f"  面{face_idx:2d}: ", end="")
            print(f"v1=顶点{v1_idx:2d}(纬度{lat1:6.1f}°) ", end="")
            print(f"v2=顶点{v2_idx:2d}(纬度{lat2:6.1f}°) ", end="")
            print(f"v3=顶点{v3_idx:2d}(纬度{lat3:6.1f}°) ", end="")
            print(f"{status}")
    
    print("\n" + "=" * 80)
    print("图例：")
    print("  ✓ = v2和v3在同一纬度（赤道平行）")
    print("  ✗ = v2和v3纬度不同")
    print("=" * 80)
    
    # 统计
    valid_count = 0
    for face_idx in range(20):
        v1_idx, v2_idx, v3_idx = icosahedron_faces[face_idx]
        v2 = icosahedron_vertices[v2_idx]
        v3 = icosahedron_vertices[v3_idx]
        lon2, lat2 = xyz_to_lonlat(*v2)
        lon3, lat3 = xyz_to_lonlat(*v3)
        if abs(lat2 - lat3) < 0.01:
            valid_count += 1
    
    print(f"\n总结：{valid_count}/20 个面满足 v2-v3 赤道平行特征")
    
    # 四叉树编码空间意义说明
    print("\n" + "=" * 80)
    print("四叉树编码的空间意义")
    print("=" * 80)
    print("""
四叉树细分模式：
    
    v1 (极地/纬度变化)
     /\\
    /  \\
   / 00 \\
  /______\\
 m31  m12
  /\\  /\\
 /10\\/01\\
/____\\/____\\
v3   m23   v2
(赤道平行) (赤道平行)

编码含义：
  - 00: 靠近v1（极地或纬度变化方向）
  - 01: 靠近v2（赤道平行线上）
  - 10: 靠近v3（赤道平行线上）
  - 11: 中心区域
""")

if __name__ == "__main__":
    main()
