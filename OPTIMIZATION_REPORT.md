# Mini-SaVi 格网划分与编码优化报告

## 概述

本次优化针对格网划分、编码、覆盖计算和渲染显示系统，共完成 10 项优化，涵盖运行时热路径性能、格网生成工具效率、Geomview 线框渲染开销和 UI 侧重复加载问题。

---

## 优化 1：消除覆盖判断中的 sqrt 调用（高优先级）

**文件：** `src/grid_coverage.c`

**问题：** `satellite_covers_grid_with_context()` 在每个格网单元的每个顶点上调用 `sqrt()` 计算距离。每帧每颗卫星需检查数百个格网，`sqrt` 调用量巨大。

**方案：** 利用数学等价变换，将除法比较转换为平方比较：

- 原始：`dot / sqrt(dist_sq) >= cos_threshold`
- 优化：`dot > 0 && dot * dot >= cos_threshold² * dist_sq`

在 `SatelliteCoverageContext` 中预计算 `cos_coverage_angle_sq`、`horizon_cos_angle_sq`、`sat_distance_sq`，覆盖角度检查和地平线检查均改为平方比较。

**效果：** 对于 level-3 格网（1280 单元）+ 66 颗卫星的典型场景，每帧消除约 25 万次 `sqrt` 调用。

---

## 优化 2：空间索引增加经度维度（高优先级）

**文件：** `src/include/grid_coverage.h`, `src/grid_coverage.c`

**问题：** 原空间索引仅按纬度分 18 个桶（每 10°），同一纬度带内所有经度方向的格网都会被逐一检查。对于覆盖角度仅 8.2° 的卫星，大量不可能被覆盖的格网仍被遍历。

**方案：** 将一维纬度索引扩展为二维（18 纬度带 × 36 经度带 = 648 桶）：

- `LatBand bands[18]` → `LatBand bands[18][36]`
- 构建索引时同时计算纬度和经度桶
- 查询时计算卫星足迹的经度范围：`delta_lon = asin(sin(footprint) / cos(lat))`
- 支持经度环绕（跨越 ±180° 子午线的模运算处理）

**效果：** 典型 Iridium 卫星覆盖约 2-3 个纬度带 × 2-4 个经度带，候选格网数量减少约 10 倍。

---

## 优化 3：顶点去重哈希表（中优先级）

**文件：** `tools/grid_calc.c`, `tools/latlon_grid_calc.c`

**问题：** `add_vertex_xyz()` / `add_vertex()` 使用线性扫描去重，复杂度 O(n²)。level-5 格网有约 10242 个顶点，需约 5200 万次比较。

**方案：** 引入空间哈希表（开放寻址法）：

- 将坐标量化为整数（乘以 1e5 后四舍五入）
- 使用三素数异或哈希：`ix * 73856093 ^ iy * 19349663 ^ iz * 83492791`
- 哈希表容量为预估顶点数的 4 倍（2 的幂），线性探测解决冲突
- 保留线性扫描作为回退路径

**效果：** 顶点去重从 O(n²) 降至 O(n) 摊还。

---

## 优化 4：保留经纬度格网三角形标识（中优先级）

**文件：** `src/include/grid_coverage.h`, `src/grid_coverage.c`

**问题：** 经纬度格网每个矩形拆成两个三角形（`_T1` / `_T2`），但加载时后缀被截断，两个三角形共享同一编码，无法区分具体哪个三角形被覆盖。

**方案：**

- `LatLonCode` 结构新增 `int triangle_idx` 字段（0=无后缀, 1=T1, 2=T2）
- 加载时不再截断 `_T1`/`_T2` 后缀
- `latlon_string_to_code()` 支持解析 `LAT###_LON###_T#` 完整格式
- `latlon_code_to_string()` 在 `triangle_idx > 0` 时输出完整后缀

**效果：** 覆盖分析精确到三角形级别，编码信息无损传递。

---

## 优化 5：移除死代码 quadtree_codes_are_neighbors（低优先级）

**文件：** `src/include/grid_coverage.h`, `src/grid_coverage.c`

**问题：** `quadtree_codes_are_neighbors()` 从未被调用，且其实现逻辑不正确（用 path_code 数值差判断空间邻接关系，数学上不成立）。

**方案：** 从头文件和实现文件中完全删除该函数。

---

## 优化 6：排序优化校验算法（低优先级）

**文件：** `tools/grid_calc.c`, `tools/latlon_grid_calc.c`

**问题：**

- `validate_unique_quadtree_codes()` / `validate_unique_latlon_codes()`：O(n²) 双重循环 strcmp
- `write_oogl_wireframe()` 中边去重：O(n²) 线性扫描

**方案：**

- 编码唯一性校验：复制编码数组 → qsort → 线性扫描相邻元素，O(n log n)
- 边去重：收集所有边 → qsort 按 (min_vertex, max_vertex) 排序 → 线性去重，O(n log n)

**效果：** level-4 格网（5120 面）的校验从约 1300 万次 strcmp 降至约 6 万次。

---

## 优化 7：修复 strncat 字符串拼接（低优先级）

**文件：** `src/grid_coverage.c`, `tools/grid_calc.c`

**问题：** `quadtree_code_to_string()` 中使用 `strncat(&branch_char, 1)` 逐字符拼接路径字符串。`strncat` 的源参数必须是合法 C 字符串（以 `\0` 结尾），传入单个 `char` 的地址属于未定义行为。

**方案：** 改为直接数组索引赋值：

```c
int pos = 0;
for (int i = code->level - 1; i >= 0; i--) {
    path_str[pos++] = '0' + ((code->path_code >> (i * 2)) & 0x3);
}
path_str[pos] = '\0';
```

---

## 优化 8：经纬度线框边去重并切换为 SKEL 输出（高优先级）

**文件：** `tools/latlon_grid_calc.c`

**问题：** 经纬度线框生成器原先按“每个矩形输出 4 条边”的方式直接写 `VECT`，共享边没有去重，且每条边都重复输出两端坐标。随着格网变密，Geomview 需要解析和绘制大量重复线段。

**方案：**

- 引入 `Edge` 结构收集所有矩形边
- 统一边方向为 `(min_vertex, max_vertex)` 以便识别共享边
- 使用 `qsort` 排序后线性去重，跳过极区退化边
- 输出格式从 `VECT` 切换为 `SKEL`，复用顶点表而不是重复写坐标

**效果：**

- `15x30` 线框：3782 行 → 1299 行，110237 B → 20352 B（下降 81.5%）
- `18x36` 线框：5446 行 → 1881 行，158397 B → 29678 B（下降 81.3%）
- `36x72` 线框：21776 行 → 7641 行，633513 B → 128625 B（下降 79.7%）

对于大量格网显示，这一项是当前最直接的渲染减负手段。

---

## 优化 9：Geomview 句柄缓存，避免重复 read geometry（高优先级）

**文件：** `tcl/grid.tcl`

**问题：** `grid(on)` / `grid_wireframe(on)` / `latlon_grid(on)` / `latlon_grid_wireframe(on)` 每次执行都会重新发送：

- `read geometry {define ... < "file"}`
- `geometry ... {: handle}`

即使同一个文件已经加载过，也会再次从磁盘读取并重新定义句柄。对于大型 OOGL 文件，这会造成明显的交互卡顿，尤其是在勾选覆盖开关、刷新显示状态或多次切换显示模式时。

**方案：**

- 为四类几何体分别记录上一次已加载的文件路径
- 新增 `grid(attach_geometry)` 辅助过程
- 仅当目标文件发生变化时才重新执行 `read geometry`
- 句柄已缓存时只执行轻量的 `(geometry name {:handle})` 重新挂接

**效果：** 避免了同一路径格网文件的重复磁盘读取和 Geomview 句柄重建，显著降低了“切一下开关就重新卡一下”的概率。

---

## 优化 10：实体格网与线框格网互斥显示（中优先级）

**文件：** `tcl/grid.tcl`

**问题：** 当前 UI 允许 `Show Solid` 与 `Show Wireframe` 同时开启。实体格网文件本身已包含边信息或面片边界效果，再叠加线框会导致重复绘制，放大 Geomview 的图元数量和混合开销。

**方案：**

- 在 `grid(on)` / `grid_wireframe(on)` 中增加互斥控制
- 在 `latlon_grid(on)` / `latlon_grid_wireframe(on)` 中增加相同互斥控制
- 当用户开启一种显示模式时，自动关闭另一种模式，避免双份格网同时驻留

**效果：** 防止用户无意中叠加实体与线框两套几何体，降低渲染面数、线段数和透明混合负担。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/include/grid_coverage.h` | 2D 空间索引结构、LatLonCode 新增 triangle_idx、删除 neighbors 声明 |
| `src/grid_coverage.c` | sqrt 消除、2D 空间索引、三角形标识保留、删除 neighbors、strncat 修复 |
| `tools/grid_calc.c` | 顶点哈希表、排序校验、排序边去重、strncat 修复 |
| `tools/latlon_grid_calc.c` | 顶点哈希表、排序校验、经纬度线框边去重、SKEL 输出 |
| `tcl/grid.tcl` | Geomview 句柄缓存、实体/线框互斥显示 |
| `generated/grids/latlon_grid_15x30_wireframe.oogl` | 按新 SKEL 线框格式重生成 |
| `generated/grids/latlon_grid_18x36_wireframe.oogl` | 按新 SKEL 线框格式重生成 |
| `generated/grids/latlon_grid_36x72_wireframe.oogl` | 按新 SKEL 线框格式重生成 |

## 验证

- `gcc -Wall -Wextra -o tools/latlon_grid_calc tools/latlon_grid_calc.c -lm` 编译通过
- `tclsh` 可成功 `source tcl/grid.tcl`
- `python3 -m unittest tests/test_grid_tools.py` 通过（2/2）
- `./tools/latlon_grid_calc --lat 15 --lon 30` 生成 450 矩形 / 900 三角形，校验通过，唯一边数 870
- `./tools/latlon_grid_calc --lat 18 --lon 36` 生成 648 矩形 / 1296 三角形，校验通过，唯一边数 1260
- `./tools/latlon_grid_calc --lat 36 --lon 72` 生成 2592 矩形 / 5184 三角形，校验通过，唯一边数 5112

## 后续建议

- 如果仍然感觉 Geomview 在高密度格网下交互吃力，可以继续为二十面体格网增加类似的“显示级别上限 / 交互时降级显示”策略。
- `src/sats.c` 中主循环每个 tick 都会调用 `grid_coverage_compute()`；如果瓶颈更多来自播放过程而不是静态显示，可继续做“降频计算”和“覆盖结果变更后再发送”的优化。
