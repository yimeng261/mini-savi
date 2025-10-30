/*
 *****************************************************
 *
 *  Grid coverage calculation for mini-savi
 *  Added for satellite-grid coverage analysis
 *
 *  Copyright (c) 2025 by Mini-SaVi contributors.
 *
 *****************************************************
 *
 * grid_coverage.c
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <errno.h>

#include "grid_coverage.h"
#include "constants.h"
#include "globals.h"
#include "utils.h"
#include "orbit_utils.h"
#include "sats.h"

/* 全局格网覆盖实例 */
GridCoverage grid_coverage = {0};

/* 默认覆盖角度 - 8.2度（Iridium的实际覆盖角度） */
#define DEFAULT_COVERAGE_ANGLE_DEG 8.2
int grid_coverage_enabled = 1;

/* Unix Socket相关全局变量 */
static int socket_fd = -1;
static struct sockaddr_un server_addr;
#define SOCKET_PATH "/tmp/mini_savi_grid_coverage.sock"

/*
 * grid_coverage_init
 * 初始化格网覆盖系统
 */
int grid_coverage_init(int grid_level) {
    
    grid_coverage.grid_level = grid_level;
    grid_coverage.coverage_angle = DEFAULT_COVERAGE_ANGLE_DEG * DEG_TO_RAD;
    grid_coverage.cells = NULL;
    grid_coverage.cell_count = 0;
    grid_coverage.max_cells = 0;
    
    // 根据格网级别估算格网单元数量
    int estimated_cells = 20; // 基础二十面体
    for (int i = 0; i < grid_level; i++) {
        estimated_cells *= 4;
    }
    
    grid_coverage.max_cells = estimated_cells + 100; // 添加缓冲
    grid_coverage.cells = malloc(grid_coverage.max_cells * sizeof(GridCell));
    
    if (!grid_coverage.cells) {
        fprintf(stderr, "Failed to allocate memory for grid coverage cells\n");
        return 0;
    }
    
    // 从文件加载格网数据
    if (!grid_coverage_load_from_file(grid_level)) {
        fprintf(stderr, "Failed to load grid data from file\n");
        grid_coverage_cleanup();
        return 0;
    }
    
    
    return 1;
}

/*
 * grid_coverage_cleanup
 * 清理格网覆盖系统
 */
void grid_coverage_cleanup(void) {
    if (grid_coverage.cells) {
        free(grid_coverage.cells);
        grid_coverage.cells = NULL;
    }
    
    // 清理卫星覆盖记录
    if (grid_coverage.satellite_coverages) {
        for (int i = 0; i < grid_coverage.max_satellites; i++) {
            if (grid_coverage.satellite_coverages[i].covered_grids) {
                free(grid_coverage.satellite_coverages[i].covered_grids);
                grid_coverage.satellite_coverages[i].covered_grids = NULL;
            }
        }
        free(grid_coverage.satellite_coverages);
        grid_coverage.satellite_coverages = NULL;
    }
    
    grid_coverage.cell_count = 0;
    grid_coverage.max_cells = 0;
    grid_coverage.satellite_count = 0;
    grid_coverage.max_satellites = 0;
    grid_coverage_enabled = 0;
    
    // 清理socket连接
    grid_coverage_socket_cleanup();
}

/*
 * grid_coverage_load_from_file
 * 从OOGL文件加载格网数据并转换为地表坐标
 */
int grid_coverage_load_from_file(int level) {
    char filename[256];
    FILE *fp;
    char line[512];
    int vertex_count, face_count;
    double (*vertices)[3] = NULL;
    int face_id = 0;
    
    // 构建文件路径
    snprintf(filename, sizeof(filename), "./mini-savi/icosahedral_grid_level_%d.oogl", level);
    fprintf(stderr, "Attempting to load grid file: %s\n", filename);
    
    fp = fopen(filename, "r");
    if (!fp) {
        fprintf(stderr, "Cannot open grid file: %s\n", filename);
        return 0;
    }
    
    // 跳过文件头直到找到OFF标记
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "OFF", 3) == 0) {
            break;
        }
    }
    
    // 读取顶点和面数量
    if (!fgets(line, sizeof(line), fp) || 
        sscanf(line, "%d %d %*d", &vertex_count, &face_count) != 2) {
        fprintf(stderr, "Failed to read vertex/face counts from %s\n", filename);
        fclose(fp);
        return 0;
    }
    
    
    // 分配顶点数组
    vertices = malloc(vertex_count * sizeof(double[3]));
    if (!vertices) {
        fprintf(stderr, "Failed to allocate memory for vertices\n");
        fclose(fp);
        return 0;
    }
    
    // 读取顶点坐标
    for (int i = 0; i < vertex_count; i++) {
        if (!fgets(line, sizeof(line), fp) ||
            sscanf(line, "%lf %lf %lf", &vertices[i][0], &vertices[i][1], &vertices[i][2]) != 3) {
            fprintf(stderr, "Failed to read vertex %d\n", i);
            free(vertices);
            fclose(fp);
            return 0;
        }
    }
    
    // 读取面并创建格网单元
    grid_coverage.cell_count = 0;
    for (int i = 0; i < face_count && grid_coverage.cell_count < grid_coverage.max_cells; i++) {
        int v1, v2, v3;
        char qtree_code_str[QUADTREE_CODE_LENGTH] = {0};
        
        if (!fgets(line, sizeof(line), fp)) {
            fprintf(stderr, "Failed to read face %d\n", i);
            continue;
        }
        
        // 解析包含四叉树编码的行
        int parsed = sscanf(line, "3 %d %d %d # %31s", &v1, &v2, &v3, qtree_code_str);
        if (parsed != 4) {
            fprintf(stderr, "Invalid grid file format: missing quadtree code at face %d\n", i);
            fprintf(stderr, "Line: %s", line);
            free(vertices);
            fclose(fp);
            return 0;
        }
        
        if (v1 >= vertex_count || v2 >= vertex_count || v3 >= vertex_count) {
            fprintf(stderr, "Invalid vertex indices in face %d\n", i);
            continue;
        }
        
        GridCell *cell = &grid_coverage.cells[grid_coverage.cell_count];
        cell->grid_id = grid_coverage.cell_count;
        
        // 解析四叉树编码
        if (!quadtree_string_to_code(qtree_code_str, &cell->qtree_code)) {
            fprintf(stderr, "Failed to parse quadtree code for grid %d: %s\n", 
                    grid_coverage.cell_count, qtree_code_str);
            free(vertices);
            fclose(fp);
            return 0;
        }
        
        // 将顶点坐标从显示位置(1.05半径)投影到地表(1.0半径)
        for (int j = 0; j < 3; j++) {
            double *vertex_src = NULL;
            switch (j) {
                case 0: vertex_src = vertices[v1]; break;
                case 1: vertex_src = vertices[v2]; break;
                case 2: vertex_src = vertices[v3]; break;
            }
            
            // 归一化到地表
            double length = sqrt(vertex_src[0]*vertex_src[0] + 
                               vertex_src[1]*vertex_src[1] + 
                               vertex_src[2]*vertex_src[2]);
            if (length > 0) {
                cell->vertices[j][0] = vertex_src[0] / length;
                cell->vertices[j][1] = vertex_src[1] / length;
                cell->vertices[j][2] = vertex_src[2] / length;
            }
        }
        
        // 计算格网中心点(地表坐标)
        cell->surface_x = (cell->vertices[0][0] + cell->vertices[1][0] + cell->vertices[2][0]) / 3.0;
        cell->surface_y = (cell->vertices[0][1] + cell->vertices[1][1] + cell->vertices[2][1]) / 3.0;
        cell->surface_z = (cell->vertices[0][2] + cell->vertices[1][2] + cell->vertices[2][2]) / 3.0;
        
        // 归一化中心点到地表
        double center_length = sqrt(cell->surface_x*cell->surface_x + 
                                  cell->surface_y*cell->surface_y + 
                                  cell->surface_z*cell->surface_z);
        if (center_length > 0) {
            cell->surface_x /= center_length;
            cell->surface_y /= center_length;
            cell->surface_z /= center_length;
        }
        
        // 转换为经纬度
        CartesianCoordinates cart = {cell->surface_x, cell->surface_y, cell->surface_z};
        SphericalCoordinates sph;
        cartesian_to_spherical(&sph, &cart);
        cell->lat = sph.phi * RAD_TO_DEG;
        cell->lon = sph.theta * RAD_TO_DEG;
        
        grid_coverage.cell_count++;
    }
    
    free(vertices);
    fclose(fp);
    
    fprintf(stderr, "Grid loading completed with quadtree codes from file\n");
    
    return 1;
}

/*
 * angle_between_vectors
 * 计算两个3D向量之间的角度(弧度)
 */
static double angle_between_vectors(double x1, double y1, double z1,
                                   double x2, double y2, double z2) {
    double dot = x1*x2 + y1*y2 + z1*z2;
    double len1 = sqrt(x1*x1 + y1*y1 + z1*z1);
    double len2 = sqrt(x2*x2 + y2*y2 + z2*z2);
    
    if (len1 == 0 || len2 == 0) return 0;
    
    double cos_angle = dot / (len1 * len2);
    
    // 防止数值误差导致的域错误
    if (cos_angle > 1.0) cos_angle = 1.0;
    if (cos_angle < -1.0) cos_angle = -1.0;
    
    return acos(cos_angle);
}

/*
 * point_in_triangle
 * 检查点是否在球面三角形内(使用重心坐标)
 */
static int point_in_triangle(double px, double py, double pz,
                            double v1x, double v1y, double v1z,
                            double v2x, double v2y, double v2z,
                            double v3x, double v3y, double v3z) {
    // 计算从每个顶点到查询点的角度
    double angle1 = angle_between_vectors(v2x-v1x, v2y-v1y, v2z-v1z, px-v1x, py-v1y, pz-v1z);
    double angle2 = angle_between_vectors(v3x-v2x, v3y-v2y, v3z-v2z, px-v2x, py-v2y, pz-v2z);
    double angle3 = angle_between_vectors(v1x-v3x, v1y-v3y, v1z-v3z, px-v3x, py-v3y, pz-v3z);
    
    // 如果所有角度之和近似等于2π，则点在三角形内
    double total_angle = angle1 + angle2 + angle3;
    return fabs(total_angle - 2*M_PI) < 0.1; // 允许一定的数值误差
}

/*
 * satellite_covers_grid
 * 判断卫星是否覆盖格网单元(完全覆盖所有顶点)
 */
static int satellite_covers_grid(const Satellite sat, const GridCell *cell,
                                double coverage_angle, const CentralBody *pcb) {
    if (!sat || !cell) return 0;
    
    // 卫星位置(地心坐标)
    double sat_x = sat->x_C.x;
    double sat_y = sat->x_C.y;
    double sat_z = sat->x_C.z;
    
    
    // 检查格网三角形的所有三个顶点是否都在卫星覆盖范围内
    for (int i = 0; i < 3; i++) {
        double vertex_x = cell->vertices[i][0] * pcb->radius;
        double vertex_y = cell->vertices[i][1] * pcb->radius;
        double vertex_z = cell->vertices[i][2] * pcb->radius;
        
        // 计算卫星位置到地心的距离和方向
        double sat_distance = sqrt(sat_x*sat_x + sat_y*sat_y + sat_z*sat_z);
        if (sat_distance < pcb->radius + 100.0) {
            return 0; // 卫星太低，不合理
        }
        
        // 卫星指向地心的单位向量(nadir方向)
        double nadir_x = -sat_x / sat_distance;
        double nadir_y = -sat_y / sat_distance;
        double nadir_z = -sat_z / sat_distance;
        
        // 卫星指向顶点的向量
        double to_vertex_x = vertex_x - sat_x;
        double to_vertex_y = vertex_y - sat_y;
        double to_vertex_z = vertex_z - sat_z;
        
        // 归一化
        double to_vertex_dist = sqrt(to_vertex_x*to_vertex_x + to_vertex_y*to_vertex_y + to_vertex_z*to_vertex_z);
        if (to_vertex_dist < 1e-6) continue; // 避免除零
        
        to_vertex_x /= to_vertex_dist;
        to_vertex_y /= to_vertex_dist;
        to_vertex_z /= to_vertex_dist;
        
        // 计算从nadir方向到顶点的角度
        double cos_angle = nadir_x * to_vertex_x + nadir_y * to_vertex_y + nadir_z * to_vertex_z;
        
        // 限制cos值在有效范围内
        if (cos_angle > 1.0) cos_angle = 1.0;
        if (cos_angle < -1.0) cos_angle = -1.0;
        
        double angle = acos(cos_angle);
        
        
        // 如果任何一个顶点不在覆盖范围内，则不覆盖此格网
        if (angle > coverage_angle) {
            return 0;
        }
        
        // 检查地平线遮挡：使用简化的地平线角度检查
        // 对于LEO卫星，主要检查顶点是否在卫星的地平线之上
        
        // 计算卫星的地平线角度（从天底点开始）
        double horizon_angle = acos(pcb->radius / sat_distance);
        
        // 如果覆盖角度小于等于地平线角度，则不需要进一步检查遮挡
        // 因为所有在覆盖角度内的点都在地平线之上
        if (coverage_angle <= horizon_angle) {
            // 不需要额外的遮挡检查
            continue;
        }
        
        // 如果覆盖角度大于地平线角度，检查此顶点是否在地平线之上
        // 计算卫星到顶点向量与卫星到地心向量的夹角
        double sat_to_vertex_x = vertex_x - sat_x;
        double sat_to_vertex_y = vertex_y - sat_y;
        double sat_to_vertex_z = vertex_z - sat_z;
        double vertex_distance = sqrt(sat_to_vertex_x*sat_to_vertex_x + 
                                     sat_to_vertex_y*sat_to_vertex_y + 
                                     sat_to_vertex_z*sat_to_vertex_z);
        
        if (vertex_distance < 1e-6) continue;
        
        // 计算卫星到顶点与卫星到地心的夹角
        double dot_product = (-sat_x * sat_to_vertex_x + 
                             -sat_y * sat_to_vertex_y + 
                             -sat_z * sat_to_vertex_z);
        double cos_angle_to_vertex = dot_product / (sat_distance * vertex_distance);
        
        // 限制cos值范围
        if (cos_angle_to_vertex > 1.0) cos_angle_to_vertex = 1.0;
        if (cos_angle_to_vertex < -1.0) cos_angle_to_vertex = -1.0;
        
        double angle_to_vertex = acos(cos_angle_to_vertex);
        
        // 如果角度大于地平线角度，说明在地平线以下，被遮挡
        if (angle_to_vertex > horizon_angle) {
            return 0;
        }
    }
    
    
    return 1; // 所有顶点都在覆盖范围内
}

/*
 * grid_coverage_compute
 * 计算所有卫星对格网的覆盖
 */
void grid_coverage_compute(const Satellite_list satellites, const CentralBody *pcb) {
    
    if (!grid_coverage_enabled || !grid_coverage.cells || !satellites) {
        return;
    }
    
    
    // 首先计算当前有多少颗卫星
    int current_satellite_count = 0;
    Satellite_list sl;
    for (sl = satellites; sl != NULL; sl = sl->next) {
        if (sl->s && sl->s->can_display_satellite) {
            current_satellite_count++;
        }
    }
    
    // 重新分配卫星覆盖数组（如果需要）
    if (current_satellite_count > grid_coverage.max_satellites) {
        grid_coverage.satellite_coverages = realloc(grid_coverage.satellite_coverages, 
                                                  current_satellite_count * sizeof(SatelliteCoverage));
        if (!grid_coverage.satellite_coverages) {
            fprintf(stderr, "Failed to allocate satellite coverage array\n");
            return;
        }
        
        // 初始化新分配的部分
        for (int i = grid_coverage.max_satellites; i < current_satellite_count; i++) {
            grid_coverage.satellite_coverages[i].satellite_id = -1;
            grid_coverage.satellite_coverages[i].covered_grids = NULL;
            grid_coverage.satellite_coverages[i].coverage_count = 0;
            grid_coverage.satellite_coverages[i].max_coverage = 0;
        }
        
        grid_coverage.max_satellites = current_satellite_count;
    }
    
    // 清除之前的覆盖记录
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        grid_coverage.satellite_coverages[i].coverage_count = 0;
    }
    
    // 遍历所有卫星，计算每个卫星覆盖的格网
    grid_coverage.satellite_count = 0;
    int total_coverage = 0;
    
    for (sl = satellites; sl != NULL; sl = sl->next) {
        if (!sl->s || !sl->s->can_display_satellite) continue;
        
        int satellite_id = sl->s->id;
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[grid_coverage.satellite_count];
        sat_cov->satellite_id = satellite_id;
        sat_cov->coverage_count = 0;
        
        
        // 检查此卫星覆盖哪些格网
        for (int i = 0; i < grid_coverage.cell_count; i++) {
            GridCell *cell = &grid_coverage.cells[i];
            
            if (satellite_covers_grid(sl->s, cell, grid_coverage.coverage_angle, pcb)) {
                // 确保数组足够大
                if (sat_cov->coverage_count >= sat_cov->max_coverage) {
                    int new_size = sat_cov->max_coverage == 0 ? 16 : sat_cov->max_coverage * 2;
                    sat_cov->covered_grids = realloc(sat_cov->covered_grids, new_size * sizeof(int));
                    if (!sat_cov->covered_grids) {
                        fprintf(stderr, "Failed to allocate grid coverage array for satellite %d\n", satellite_id);
                        continue;
                    }
                    sat_cov->max_coverage = new_size;
                }
                
                // 添加格网到覆盖列表
                sat_cov->covered_grids[sat_cov->coverage_count] = cell->grid_id;
                sat_cov->coverage_count++;
                total_coverage++;
            }
        }
        
        
        grid_coverage.satellite_count++;
    }
    
    // 发送覆盖数据到Socket
    grid_coverage_socket_send_data();
}

/*
 * grid_coverage_set_angle
 * 设置覆盖角度
 */
void grid_coverage_set_angle(double angle_degrees) {
    grid_coverage.coverage_angle = angle_degrees * DEG_TO_RAD;
    fprintf(stderr, "Grid coverage angle set to %.1f degrees\n", angle_degrees);
    
    // 立即重新计算覆盖
    if (grid_coverage_enabled && grid_coverage.cells) {
        Constellation *constellation = get_constellation();
        if (constellation && constellation->satellites && constellation->pcb) {
            fprintf(stderr, "Recalculating coverage with new angle...\n");
            grid_coverage_compute(constellation->satellites, constellation->pcb);
        }
    }
}

/*
 * grid_coverage_get_angle
 * 获取当前覆盖角度(度)
 */
double grid_coverage_get_angle(void) {
    return grid_coverage.coverage_angle * RAD_TO_DEG;
}

/*
 * grid_coverage_get_satellite_coverage
 * 获取指定卫星覆盖的格网列表
 */
int grid_coverage_get_satellite_coverage(int satellite_id, int **covered_grids) {
    if (!grid_coverage.satellite_coverages || !covered_grids) return 0;
    
    // 查找指定卫星的覆盖记录
    SatelliteCoverage *sat_cov = NULL;
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        if (grid_coverage.satellite_coverages[i].satellite_id == satellite_id) {
            sat_cov = &grid_coverage.satellite_coverages[i];
            break;
        }
    }
    
    if (!sat_cov || sat_cov->coverage_count == 0) {
        *covered_grids = NULL;
        return 0;
    }
    
    // 分配并复制结果数组
    *covered_grids = malloc(sat_cov->coverage_count * sizeof(int));
    if (!*covered_grids) return 0;
    
    memcpy(*covered_grids, sat_cov->covered_grids, sat_cov->coverage_count * sizeof(int));
    return sat_cov->coverage_count;
}

/*
 * grid_coverage_get_grid_coverage
 * 获取覆盖指定格网的卫星列表
 */
int grid_coverage_get_grid_coverage(int grid_id, int **covering_satellites) {
    if (!grid_coverage.satellite_coverages || grid_id < 0 || grid_id >= grid_coverage.cell_count || !covering_satellites) {
        return 0;
    }
    
    // 统计覆盖此格网的卫星数量
    int count = 0;
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        for (int j = 0; j < sat_cov->coverage_count; j++) {
            if (sat_cov->covered_grids[j] == grid_id) {
                count++;
                break;
            }
        }
    }
    
    if (count == 0) {
        *covering_satellites = NULL;
        return 0;
    }
    
    // 分配并填充结果数组
    *covering_satellites = malloc(count * sizeof(int));
    if (!*covering_satellites) return 0;
    
    int index = 0;
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        for (int j = 0; j < sat_cov->coverage_count; j++) {
            if (sat_cov->covered_grids[j] == grid_id) {
                (*covering_satellites)[index++] = sat_cov->satellite_id;
                break;
            }
        }
    }
    
    return count;
}

/*
 * grid_coverage_print_stats
 * 打印覆盖统计信息
 */
void grid_coverage_print_stats(void) {
    if (!grid_coverage.cells) {
        fprintf(stderr, "=== Grid Coverage Statistics ===\n");
        fprintf(stderr, "Grid coverage not initialized (no data available)\n");
        fprintf(stderr, "================================\n");
        return;
    }
    
    // 统计被覆盖的格网数量（新的数据结构）
    int *grid_coverage_count = calloc(grid_coverage.cell_count, sizeof(int));
    if (!grid_coverage_count) {
        fprintf(stderr, "Memory allocation failed for statistics\n");
        return;
    }
    
    int total_coverage_instances = 0;
    int max_coverage_per_satellite = 0;
    
    // 统计每个卫星的覆盖情况
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        total_coverage_instances += sat_cov->coverage_count;
        
        if (sat_cov->coverage_count > max_coverage_per_satellite) {
            max_coverage_per_satellite = sat_cov->coverage_count;
        }
        
        // 统计每个格网被多少颗卫星覆盖
        for (int j = 0; j < sat_cov->coverage_count; j++) {
            int grid_id = sat_cov->covered_grids[j];
            if (grid_id >= 0 && grid_id < grid_coverage.cell_count) {
                grid_coverage_count[grid_id]++;
            }
        }
    }
    
    // 统计被覆盖的格网数量
    int covered_cells = 0;
    int max_satellites_per_cell = 0;
    for (int i = 0; i < grid_coverage.cell_count; i++) {
        if (grid_coverage_count[i] > 0) {
            covered_cells++;
            if (grid_coverage_count[i] > max_satellites_per_cell) {
                max_satellites_per_cell = grid_coverage_count[i];
            }
        }
    }
    
    double coverage_percentage = grid_coverage.cell_count > 0 ? (double)covered_cells / grid_coverage.cell_count * 100.0 : 0.0;
    double avg_satellites_per_cell = covered_cells > 0 ? (double)total_coverage_instances / covered_cells : 0.0;
    double avg_grids_per_satellite = grid_coverage.satellite_count > 0 ? (double)total_coverage_instances / grid_coverage.satellite_count : 0.0;
    
    fprintf(stderr, "=== Grid Coverage Statistics ===\n");
    fprintf(stderr, "Total grid cells: %d\n", grid_coverage.cell_count);
    fprintf(stderr, "Total satellites: %d\n", grid_coverage.satellite_count);
    fprintf(stderr, "Covered cells: %d (%.1f%%)\n", covered_cells, coverage_percentage);
    fprintf(stderr, "Average satellites per covered cell: %.1f\n", avg_satellites_per_cell);
    fprintf(stderr, "Maximum satellites per cell: %d\n", max_satellites_per_cell);
    fprintf(stderr, "Average grids per satellite: %.1f\n", avg_grids_per_satellite);
    fprintf(stderr, "Max grids per satellite: %d\n", max_coverage_per_satellite);
    fprintf(stderr, "Coverage angle: %.1f degrees\n", grid_coverage.coverage_angle * RAD_TO_DEG);
    fprintf(stderr, "Grid level: %d\n", grid_coverage.grid_level);
    
    // 显示四叉树编码示例
    if (grid_coverage.cell_count > 0) {
        fprintf(stderr, "Quadtree encoding examples:\n");
        int examples = grid_coverage.cell_count < 5 ? grid_coverage.cell_count : 5;
        for (int i = 0; i < examples; i++) {
            GridCell *cell = &grid_coverage.cells[i];
            fprintf(stderr, "  Grid %d: %s (%.2f°, %.2f°)\n", 
                    i, cell->qtree_code.code_string, cell->lat, cell->lon);
        }
    }
    
    fprintf(stderr, "================================\n");
    
    free(grid_coverage_count);
}

/* 四叉树编码实现 */


/*
 * quadtree_code_to_string
 * 将四叉树编码转换为字符串格式
 */
void quadtree_code_to_string(const QuadtreeCode *code, char *output) {
    if (!code || !output) return;
    
    if (code->level == 0) {
        // 基础面，只显示面ID
        snprintf(output, QUADTREE_CODE_LENGTH, "F%02d", code->base_face_id);
    } else {
        // 有细分级别，显示完整路径
        char path_str[MAX_QUADTREE_DEPTH * 2 + 1] = {0};
        
        for (int i = code->level - 1; i >= 0; i--) {
            int branch = (code->path_code >> (i * 2)) & 0x3;
            char branch_char = '0' + branch;
            strncat(path_str, &branch_char, 1);
        }
        
        snprintf(output, QUADTREE_CODE_LENGTH, "F%02d_%s", code->base_face_id, path_str);
    }
}

/*
 * quadtree_string_to_code
 * 将字符串格式的编码转换为QuadtreeCode结构
 */
int quadtree_string_to_code(const char *code_string, QuadtreeCode *code) {
    if (!code_string || !code) return 0;
    
    // 解析格式: "F##" 或 "F##_path"
    if (code_string[0] != 'F') return 0;
    
    // 提取基础面ID
    code->base_face_id = atoi(&code_string[1]);
    if (code->base_face_id < 0 || code->base_face_id >= 20) return 0;
    
    // 查找下划线分隔符
    const char *underscore = strchr(code_string, '_');
    if (!underscore) {
        // 只有基础面ID，没有路径
        code->level = 0;
        code->path_code = 0;
    } else {
        // 解析路径
        const char *path_str = underscore + 1;
        code->level = strlen(path_str);
        if (code->level > MAX_QUADTREE_DEPTH) return 0;
        
        code->path_code = 0;
        for (int i = 0; i < code->level; i++) {
            char c = path_str[i];
            if (c < '0' || c > '3') return 0;
            
            int branch = c - '0';
            code->path_code |= (branch & 0x3) << ((code->level - 1 - i) * 2);
        }
    }
    
    // 复制编码字符串
    strncpy(code->code_string, code_string, QUADTREE_CODE_LENGTH - 1);
    code->code_string[QUADTREE_CODE_LENGTH - 1] = '\0';
    
    return 1;
}

/*
 * quadtree_get_parent_code
 * 获取父节点编码
 */
int quadtree_get_parent_code(const QuadtreeCode *code, QuadtreeCode *parent) {
    if (!code || !parent || code->level == 0) return 0;
    
    parent->base_face_id = code->base_face_id;
    parent->level = code->level - 1;
    
    if (parent->level == 0) {
        parent->path_code = 0;
    } else {
        // 移除最后一个分支（右移2位）
        parent->path_code = code->path_code >> 2;
    }
    
    quadtree_code_to_string(parent, parent->code_string);
    return 1;
}

/*
 * quadtree_get_children_codes
 * 获取子节点编码
 */
int quadtree_get_children_codes(const QuadtreeCode *code, QuadtreeCode children[4]) {
    if (!code || !children || code->level >= MAX_QUADTREE_DEPTH) return 0;
    
    for (int i = 0; i < 4; i++) {
        children[i].base_face_id = code->base_face_id;
        children[i].level = code->level + 1;
        
        // 添加新的分支（左移2位并添加分支编码）
        children[i].path_code = (code->path_code << 2) | i;
        
        quadtree_code_to_string(&children[i], children[i].code_string);
    }
    
    return 1;
}

/*
 * quadtree_codes_are_neighbors
 * 判断两个编码是否为相邻格网（简化版本）
 */
int quadtree_codes_are_neighbors(const QuadtreeCode *code1, const QuadtreeCode *code2) {
    if (!code1 || !code2) return 0;
    
    // 不同基础面的格网可能相邻，但这里简化处理
    if (code1->base_face_id != code2->base_face_id) return 0;
    
    // 同一级别的相邻判断
    if (code1->level == code2->level) {
        // 简化：路径编码差值小的可能相邻
        unsigned int diff = (code1->path_code > code2->path_code) ? 
                           (code1->path_code - code2->path_code) : 
                           (code2->path_code - code1->path_code);
        return diff <= 3;  // 简化的相邻判断
    }
    
    return 0;
}


/* TCL命令接口 */

/*
 * grid_coverage_on_cmd
 * 启用格网覆盖计算
 */
char *grid_coverage_on_cmd(int argc, char *argv[]) {
    int level = 2; // 默认级别
    
    // 从参数中获取级别 (argv[2] 是级别参数)
    if (argc >= 3) {
        level = atoi(argv[2]);
        if (level < 0 || level > 6) {
            fprintf(stderr, "Invalid grid level %d, using default level 2\n", level);
            level = 2;
        }
    }
    
    // 如果级别不同，需要重新初始化
    if (grid_coverage.cells && grid_coverage.grid_level != level) {
        grid_coverage_cleanup();
    }
    
    if (!grid_coverage.cells) {
        if (!grid_coverage_init(level)) {
            return "Failed to initialize grid coverage";
        }
    }
    
    grid_coverage_enabled = 1;
    fprintf(stderr, "Grid coverage enabled (level %d, %d cells)\n", level, grid_coverage.cell_count);
    
    // 初始化Socket连接
    grid_coverage_socket_init();
    
    // 立即进行一次覆盖计算
    Constellation *constellation = get_constellation();
    if (constellation && constellation->satellites && constellation->pcb) {
        grid_coverage_compute(constellation->satellites, constellation->pcb);
    }
    
    return "OK";
}

/*
 * grid_coverage_off_cmd
 * 禁用格网覆盖计算
 */
char *grid_coverage_off_cmd(int argc, char *argv[]) {
    grid_coverage_enabled = 0;
    grid_coverage_socket_cleanup();
    fprintf(stderr, "Grid coverage calculation disabled\n");
    return "OK";
}

/*
 * grid_coverage_set_angle_cmd
 * 设置覆盖角度命令
 */
char *grid_coverage_set_angle_cmd(int argc, char *argv[]) {
    if (argc < 3) {
        return "Usage: grid_coverage_set_angle <angle_degrees>";
    }
    
    double angle = atof(argv[2]);
    if (angle < 0 || angle > 180) {
        return "Angle must be between 0 and 180 degrees";
    }
    
    grid_coverage_set_angle(angle);
    return "OK";
}

/*
 * grid_coverage_stats_cmd
 * 打印统计信息命令
 */
char *grid_coverage_stats_cmd(int argc, char *argv[]) {
    grid_coverage_print_stats();
    return "OK";
}

/*
 * grid_coverage_query_code_cmd
 * 查询四叉树编码命令
 */
char *grid_coverage_query_code_cmd(int argc, char *argv[]) {
    if (argc < 3) {
        return "Usage: grid_coverage_query_code <grid_id>";
    }
    
    int grid_id = atoi(argv[2]);
    if (grid_id < 0 || grid_id >= grid_coverage.cell_count) {
        return "Invalid grid ID";
    }
    
    GridCell *cell = &grid_coverage.cells[grid_id];
    
    fprintf(stderr, "Grid %d quadtree information:\n", grid_id);
    fprintf(stderr, "  Code: %s\n", cell->qtree_code.code_string);
    fprintf(stderr, "  Base face: %d\n", cell->qtree_code.base_face_id);
    fprintf(stderr, "  Level: %d\n", cell->qtree_code.level);
    fprintf(stderr, "  Path code: 0x%x\n", cell->qtree_code.path_code);
    fprintf(stderr, "  Position: (%.2f°, %.2f°)\n", cell->lat, cell->lon);
    
    // 显示父节点信息
    if (cell->qtree_code.level > 0) {
        QuadtreeCode parent;
        if (quadtree_get_parent_code(&cell->qtree_code, &parent)) {
            fprintf(stderr, "  Parent: %s\n", parent.code_string);
        }
    }
    
    // 显示子节点信息
    if (cell->qtree_code.level < MAX_QUADTREE_DEPTH) {
        QuadtreeCode children[4];
        if (quadtree_get_children_codes(&cell->qtree_code, children)) {
            fprintf(stderr, "  Children: %s, %s, %s, %s\n", 
                    children[0].code_string, children[1].code_string,
                    children[2].code_string, children[3].code_string);
        }
    }
    
    return "OK";
}

/*
 * grid_coverage_socket_init
 * 初始化Unix Socket连接
 */
int grid_coverage_socket_init(void) {
    socket_fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (socket_fd < 0) {
        fprintf(stderr, "Failed to create Unix socket: %s\n", strerror(errno));
        return 0;
    }
    
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sun_family = AF_UNIX;
    strncpy(server_addr.sun_path, SOCKET_PATH, sizeof(server_addr.sun_path) - 1);
    
    fprintf(stderr, "Unix socket initialized for grid coverage data (path: %s)\n", SOCKET_PATH);
    return 1;
}

/*
 * grid_coverage_socket_cleanup
 * 清理Socket连接
 */
void grid_coverage_socket_cleanup(void) {
    if (socket_fd >= 0) {
        close(socket_fd);
        socket_fd = -1;
    }
}

/*
 * grid_coverage_socket_send_data
 * 发送卫星覆盖数据到Socket
 */
void grid_coverage_socket_send_data(void) {
    printf("DEBUG: grid_coverage_socket_send_data called\n");
    printf("DEBUG: socket_fd=%d, grid_coverage_enabled=%d, satellite_coverages=%p\n", 
           socket_fd, grid_coverage_enabled, grid_coverage.satellite_coverages);
    printf("DEBUG: satellite_count=%d\n", grid_coverage.satellite_count);
    
    if (socket_fd < 0 || !grid_coverage_enabled || !grid_coverage.satellite_coverages) {
        printf("DEBUG: Early return - socket not ready or no data\n");
        return;
    }
    
    // 为每个卫星发送覆盖数据
    printf("DEBUG: Processing %d satellites\n", grid_coverage.satellite_count);
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        printf("DEBUG: Satellite %d has %d covered grids\n", sat_cov->satellite_id, sat_cov->coverage_count);
        if (sat_cov->coverage_count > 0) {
            char buffer[4096];
            int pos = 0;
            
            // 格式: "SAT_ID:code1,code2,code3,...\n" (使用四叉树编码)
            pos += snprintf(buffer + pos, sizeof(buffer) - pos, "%d:", sat_cov->satellite_id);
            
            for (int j = 0; j < sat_cov->coverage_count && pos < sizeof(buffer) - 50; j++) {
                if (j > 0) {
                    pos += snprintf(buffer + pos, sizeof(buffer) - pos, ",");
                }
                
                // 获取格网的四叉树编码
                int grid_id = sat_cov->covered_grids[j];
                if (grid_id >= 0 && grid_id < grid_coverage.cell_count) {
                    GridCell *cell = &grid_coverage.cells[grid_id];
                    pos += snprintf(buffer + pos, sizeof(buffer) - pos, "%s", 
                                  cell->qtree_code.code_string);
                } else {
                    // 如果格网ID无效，使用格网ID作为后备
                    pos += snprintf(buffer + pos, sizeof(buffer) - pos, "INVALID_%d", grid_id);
                }
            }
            pos += snprintf(buffer + pos, sizeof(buffer) - pos, "\n");
            
            // 发送数据到Unix socket
            printf("DEBUG: Sending data for satellite %d: %.*s", sat_cov->satellite_id, pos-1, buffer);
            int sent = sendto(socket_fd, buffer, pos, 0, (struct sockaddr*)&server_addr, sizeof(server_addr));
            if (sent < 0) {
                printf("Failed to send grid coverage data to Unix socket: %s\n", strerror(errno));
            } else {
                printf("DEBUG: Successfully sent %d bytes to Unix socket\n", sent);
            }
        }
    }
}
