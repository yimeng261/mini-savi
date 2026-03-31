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
int grid_coverage_enabled = 0;

/* Unix Socket相关全局变量 */
static int socket_fd = -1;
static struct sockaddr_un server_addr;
#define SOCKET_PATH "/tmp/mini_savi_grid_coverage.sock"
#define GRID_COVERAGE_MAX_DATAGRAM 60000
#define GRID_COVERAGE_HEADER_MARGIN 32

static unsigned int grid_coverage_socket_send_payload(const char *buffer,
                                                      size_t length);
static unsigned int grid_coverage_socket_send_codes(int satellite_id,
                                                    const int *grid_indices,
                                                    int grid_count,
                                                    const GridCell *cells,
                                                    int cell_count,
                                                    unsigned int use_icosahedral);
static unsigned int grid_coverage_validate_ico_metadata(const char *base_filename,
                                                        int level,
                                                        int vertex_count,
                                                        int face_count);
static unsigned int grid_coverage_validate_latlon_metadata(const char *base_filename,
                                                           int lat_divisions,
                                                           int lon_divisions,
                                                           int vertex_count,
                                                           int face_count);

typedef struct {
    double sat_x;
    double sat_y;
    double sat_z;
    double sat_distance;
    double nadir_x;
    double nadir_y;
    double nadir_z;
    double body_radius;
    double cos_coverage_angle;
    double horizon_cos_angle;
    unsigned int requires_horizon_check;
    unsigned int valid;
} SatelliteCoverageContext;

typedef struct {
    char grid_type[32];
    int grid_level;
    int lat_divisions;
    int lon_divisions;
    int vertex_count;
    int face_count;
    int rectangle_count;
    int triangle_count;
} GridMetadata;

static void satellite_coverage_context_init(const Satellite sat,
                                           double coverage_angle,
                                           const CentralBody *pcb,
                                           SatelliteCoverageContext *ctx);
static int satellite_covers_grid_with_context(const GridCell *cell,
                                              const SatelliteCoverageContext *ctx);
static unsigned int append_covered_grid(int **covered_grids,
                                        int *coverage_count,
                                        int *max_coverage,
                                        int grid_idx,
                                        const char *grid_kind,
                                        int satellite_id);
static int collect_coverage_for_cells(const GridCell *cells,
                                      int cell_count,
                                      const SatelliteCoverageContext *ctx,
                                      int **covered_grids,
                                      int *coverage_count,
                                      int *max_coverage,
                                      const char *grid_kind,
                                      int satellite_id);
static unsigned int load_grid_metadata_file(const char *metadata_path,
                                            GridMetadata *metadata);

/*
 * grid_coverage_init
 * 初始化格网覆盖系统（二十面体格网）
 */
int grid_coverage_init(int grid_level) {
    
    // 如果both_mode已开启，保留现有经纬度数据
    if (grid_coverage.both_mode == 0) {
        // 单模式：清理所有数据
        grid_coverage_cleanup();
    }
    
    grid_coverage.grid_type = GRID_TYPE_ICOSAHEDRAL;
    grid_coverage.grid_level = grid_level;
    if (grid_coverage.both_mode == 0) {
        grid_coverage.lat_divisions = 0;
        grid_coverage.lon_divisions = 0;
    }
    grid_coverage.coverage_angle = DEFAULT_COVERAGE_ANGLE_DEG * DEG_TO_RAD;
    
    // 根据格网级别估算格网单元数量
    int estimated_cells = 20; // 基础二十面体
    for (int i = 0; i < grid_level; i++) {
        estimated_cells *= 4;
    }
    
    grid_coverage.max_ico_cells = estimated_cells + 100; // 添加缓冲
    grid_coverage.ico_cells = malloc(grid_coverage.max_ico_cells * sizeof(GridCell));
    
    if (!grid_coverage.ico_cells) {
        fprintf(stderr, "Failed to allocate memory for icosahedral grid cells\n");
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
 * grid_coverage_init_latlon
 * 初始化格网覆盖系统（经纬度格网）
 */
int grid_coverage_init_latlon(int lat_divisions, int lon_divisions) {
    
    // 如果both_mode已开启，保留现有二十面体数据
    if (grid_coverage.both_mode == 0) {
        // 单模式：清理所有数据
        grid_coverage_cleanup();
    }
    
    grid_coverage.grid_type = GRID_TYPE_LATLON;
    if (grid_coverage.both_mode == 0) {
        grid_coverage.grid_level = 0;
    }
    grid_coverage.lat_divisions = lat_divisions;
    grid_coverage.lon_divisions = lon_divisions;
    grid_coverage.coverage_angle = DEFAULT_COVERAGE_ANGLE_DEG * DEG_TO_RAD;
    
    // 估算格网单元数量（每个矩形分成2个三角形）
    int estimated_cells = lat_divisions * lon_divisions * 2 + 100;
    
    grid_coverage.max_latlon_cells = estimated_cells;
    grid_coverage.latlon_cells = malloc(grid_coverage.max_latlon_cells * sizeof(GridCell));
    
    if (!grid_coverage.latlon_cells) {
        fprintf(stderr, "Failed to allocate memory for latlon grid cells\n");
        return 0;
    }
    
    // 从文件加载经纬度格网数据
    if (!grid_coverage_load_latlon_from_file(lat_divisions, lon_divisions)) {
        fprintf(stderr, "Failed to load latlon grid data from file\n");
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
    // 清理二十面体格网数据
    if (grid_coverage.ico_cells) {
        free(grid_coverage.ico_cells);
        grid_coverage.ico_cells = NULL;
    }
    
    // 清理经纬度格网数据
    if (grid_coverage.latlon_cells) {
        free(grid_coverage.latlon_cells);
        grid_coverage.latlon_cells = NULL;
    }
    
    // 清理卫星覆盖记录
    if (grid_coverage.satellite_coverages) {
        for (int i = 0; i < grid_coverage.max_satellites; i++) {
            if (grid_coverage.satellite_coverages[i].covered_ico_grids) {
                free(grid_coverage.satellite_coverages[i].covered_ico_grids);
                grid_coverage.satellite_coverages[i].covered_ico_grids = NULL;
            }
            if (grid_coverage.satellite_coverages[i].covered_latlon_grids) {
                free(grid_coverage.satellite_coverages[i].covered_latlon_grids);
                grid_coverage.satellite_coverages[i].covered_latlon_grids = NULL;
            }
        }
        free(grid_coverage.satellite_coverages);
        grid_coverage.satellite_coverages = NULL;
    }
    
    grid_coverage.ico_cell_count = 0;
    grid_coverage.max_ico_cells = 0;
    grid_coverage.latlon_cell_count = 0;
    grid_coverage.max_latlon_cells = 0;
    grid_coverage.satellite_count = 0;
    grid_coverage.max_satellites = 0;
    grid_coverage.both_mode = 0;
    grid_coverage_enabled = 0;
    
    // 清理socket连接
    grid_coverage_socket_cleanup();
}

/*
 * grid_coverage_load_from_file
 * 从OOGL文件加载格网数据并转换为地表坐标
 */
int grid_coverage_load_from_file(int level) {
    char base_filename[128];
    char filename[256];
    FILE *fp;
    char line[512];
    int vertex_count, face_count;
    double (*vertices)[3] = NULL;
    int face_id = 0;
    
    // 构建文件路径
    snprintf(base_filename, sizeof(base_filename), "icosahedral_grid_level_%d", level);
    snprintf(filename, sizeof(filename), "./generated/grids/%s.oogl", base_filename);
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

    if (!grid_coverage_validate_ico_metadata(base_filename, level,
                                             vertex_count, face_count)) {
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
    grid_coverage.ico_cell_count = 0;
    for (int i = 0; i < face_count && grid_coverage.ico_cell_count < grid_coverage.max_ico_cells; i++) {
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
        
        GridCell *cell = &grid_coverage.ico_cells[grid_coverage.ico_cell_count];
        cell->grid_id = grid_coverage.ico_cell_count;
        cell->grid_type = GRID_TYPE_ICOSAHEDRAL;  // 设置格网类型
        
        // 解析四叉树编码
        if (!quadtree_string_to_code(qtree_code_str, &cell->qtree_code)) {
            fprintf(stderr, "Failed to parse quadtree code for grid %d: %s\n", 
                    grid_coverage.ico_cell_count, qtree_code_str);
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
        
        grid_coverage.ico_cell_count++;
    }
    
    free(vertices);
    fclose(fp);
    
    fprintf(stderr, "Icosahedral grid loading completed: %d cells\n", grid_coverage.ico_cell_count);
    
    return 1;
}

/*
 * grid_coverage_load_latlon_from_file
 * 从OOGL文件加载经纬度格网数据
 */
int grid_coverage_load_latlon_from_file(int lat_divisions, int lon_divisions) {
    char base_filename[128];
    char filename[256];
    FILE *fp;
    char line[512];
    int vertex_count, face_count;
    double (*vertices)[3] = NULL;
    
    // 构建文件路径
    snprintf(base_filename, sizeof(base_filename), "latlon_grid_%dx%d",
             lat_divisions, lon_divisions);
    snprintf(filename, sizeof(filename), "./generated/grids/%s.oogl", 
             base_filename);
    fprintf(stderr, "Attempting to load latlon grid file: %s\n", filename);
    
    fp = fopen(filename, "r");
    if (!fp) {
        fprintf(stderr, "Cannot open latlon grid file: %s\n", filename);
        fprintf(stderr, "请先运行 latlon_grid_calc 生成经纬度格网文件\n");
        return 0;
    }
    
    // 跳过文件头直到找到OFF标记
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "OFF", 3) == 0 || strncmp(line, "COFF", 4) == 0) {
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

    if (!grid_coverage_validate_latlon_metadata(base_filename, lat_divisions,
                                                lon_divisions, vertex_count,
                                                face_count)) {
        fclose(fp);
        return 0;
    }
    
    fprintf(stderr, "Loading %d vertices and %d triangular faces\n", vertex_count, face_count);
    
    // 分配顶点数组
    vertices = malloc(vertex_count * sizeof(double[3]));
    if (!vertices) {
        fprintf(stderr, "Failed to allocate memory for vertices\n");
        fclose(fp);
        return 0;
    }
    
    // 读取顶点坐标
    for (int i = 0; i < vertex_count; i++) {
        if (!fgets(line, sizeof(line), fp)) {
            fprintf(stderr, "Failed to read vertex %d\n", i);
            free(vertices);
            fclose(fp);
            return 0;
        }
        
        // COFF格式包含颜色信息，需要处理
        double r, g, b, a;
        int parsed = sscanf(line, "%lf %lf %lf %lf %lf %lf %lf", 
                          &vertices[i][0], &vertices[i][1], &vertices[i][2],
                          &r, &g, &b, &a);
        
        if (parsed < 3) {
            fprintf(stderr, "Failed to parse vertex %d: %s\n", i, line);
            free(vertices);
            fclose(fp);
            return 0;
        }
    }
    
    // 读取面并创建格网单元
    grid_coverage.latlon_cell_count = 0;
    for (int i = 0; i < face_count && grid_coverage.latlon_cell_count < grid_coverage.max_latlon_cells; i++) {
        int v1, v2, v3;
        char code_str[128] = {0};
        
        if (!fgets(line, sizeof(line), fp)) {
            fprintf(stderr, "Failed to read face %d\n", i);
            continue;
        }
        
        // 解析包含经纬度编码的行: "3 v1 v2 v3 # LAT###_LON###_T#"
        int parsed = sscanf(line, "3 %d %d %d # %127s", &v1, &v2, &v3, code_str);
        if (parsed != 4) {
            fprintf(stderr, "Invalid latlon grid file format at face %d\n", i);
            fprintf(stderr, "Line: %s", line);
            free(vertices);
            fclose(fp);
            return 0;
        }
        
        if (v1 >= vertex_count || v2 >= vertex_count || v3 >= vertex_count) {
            fprintf(stderr, "Invalid vertex indices in face %d\n", i);
            continue;
        }
        
        GridCell *cell = &grid_coverage.latlon_cells[grid_coverage.latlon_cell_count];
        cell->grid_id = grid_coverage.latlon_cell_count;
        cell->grid_type = GRID_TYPE_LATLON;
        
        // 解析经纬度编码 (格式: LAT###_LON###_T# 或 LAT###_LON###)
        // 移除_T1或_T2后缀
        char *underscore_t = strrchr(code_str, '_');
        if (underscore_t && (strcmp(underscore_t, "_T1") == 0 || strcmp(underscore_t, "_T2") == 0)) {
            *underscore_t = '\0'; // 截断_T1/_T2后缀
        }
        
        if (!latlon_string_to_code(code_str, &cell->latlon_code)) {
            fprintf(stderr, "Failed to parse latlon code for grid %d: %s\n", 
                    grid_coverage.latlon_cell_count, code_str);
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
        
        grid_coverage.latlon_cell_count++;
    }
    
    free(vertices);
    fclose(fp);
    
    fprintf(stderr, "LatLon grid loading completed: %d cells\n", grid_coverage.latlon_cell_count);
    
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

static void
satellite_coverage_context_init(const Satellite sat, double coverage_angle,
                                const CentralBody *pcb,
                                SatelliteCoverageContext *ctx) {
    double sat_distance_sq;

    memset(ctx, 0, sizeof(*ctx));
    if (!sat || !pcb) {
        return;
    }

    ctx->sat_x = sat->x_C.x;
    ctx->sat_y = sat->x_C.y;
    ctx->sat_z = sat->x_C.z;
    ctx->body_radius = pcb->radius;

    sat_distance_sq = ctx->sat_x * ctx->sat_x +
                      ctx->sat_y * ctx->sat_y +
                      ctx->sat_z * ctx->sat_z;
    if (sat_distance_sq <= (pcb->radius + 100.0) * (pcb->radius + 100.0)) {
        return;
    }

    ctx->sat_distance = sqrt(sat_distance_sq);
    ctx->nadir_x = -ctx->sat_x / ctx->sat_distance;
    ctx->nadir_y = -ctx->sat_y / ctx->sat_distance;
    ctx->nadir_z = -ctx->sat_z / ctx->sat_distance;
    ctx->cos_coverage_angle = cos(coverage_angle);
    ctx->horizon_cos_angle = pcb->radius / ctx->sat_distance;
    ctx->requires_horizon_check =
        (ctx->cos_coverage_angle < ctx->horizon_cos_angle);
    ctx->valid = TRUE;
}

/*
 * satellite_covers_grid
 * 判断卫星是否覆盖格网单元(完全覆盖所有顶点)
 */
static int
satellite_covers_grid_with_context(const GridCell *cell,
                                   const SatelliteCoverageContext *ctx) {
    if (!cell || !ctx || !ctx->valid) return 0;

    for (int i = 0; i < 3; i++) {
        double vertex_x = cell->vertices[i][0] * ctx->body_radius;
        double vertex_y = cell->vertices[i][1] * ctx->body_radius;
        double vertex_z = cell->vertices[i][2] * ctx->body_radius;
        double to_vertex_x = vertex_x - ctx->sat_x;
        double to_vertex_y = vertex_y - ctx->sat_y;
        double to_vertex_z = vertex_z - ctx->sat_z;
        double to_vertex_dist = sqrt(to_vertex_x * to_vertex_x +
                                     to_vertex_y * to_vertex_y +
                                     to_vertex_z * to_vertex_z);
        double cos_angle;

        if (to_vertex_dist < 1e-6) continue;

        cos_angle = (ctx->nadir_x * to_vertex_x +
                     ctx->nadir_y * to_vertex_y +
                     ctx->nadir_z * to_vertex_z) / to_vertex_dist;
        if (cos_angle < ctx->cos_coverage_angle) {
            return 0;
        }

        if (!ctx->requires_horizon_check) {
            continue;
        }

        if (((-ctx->sat_x * to_vertex_x) +
             (-ctx->sat_y * to_vertex_y) +
             (-ctx->sat_z * to_vertex_z)) <
            (ctx->horizon_cos_angle * ctx->sat_distance * to_vertex_dist)) {
            return 0;
        }
    }

    return 1;
}

static unsigned int
append_covered_grid(int **covered_grids, int *coverage_count,
                    int *max_coverage, int grid_idx, const char *grid_kind,
                    int satellite_id) {
    if (*coverage_count >= *max_coverage) {
        int new_size = *max_coverage == 0 ? 16 : *max_coverage * 2;
        int *new_buffer = realloc(*covered_grids, new_size * sizeof(int));

        if (!new_buffer) {
            fprintf(stderr,
                    "Failed to allocate %s grid coverage array for satellite %d\n",
                    grid_kind, satellite_id);
            return FALSE;
        }

        *covered_grids = new_buffer;
        *max_coverage = new_size;
    }

    (*covered_grids)[*coverage_count] = grid_idx;
    (*coverage_count)++;
    return TRUE;
}

static int
collect_coverage_for_cells(const GridCell *cells, int cell_count,
                           const SatelliteCoverageContext *ctx,
                           int **covered_grids, int *coverage_count,
                           int *max_coverage, const char *grid_kind,
                           int satellite_id) {
    int added = 0;

    for (int i = 0; i < cell_count; i++) {
        if (!satellite_covers_grid_with_context(&cells[i], ctx)) {
            continue;
        }

        if (!append_covered_grid(covered_grids, coverage_count, max_coverage,
                                 i, grid_kind, satellite_id)) {
            break;
        }
        added++;
    }

    return added;
}

static unsigned int
load_grid_metadata_file(const char *metadata_path, GridMetadata *metadata) {
    FILE *fp;
    char line[256];

    memset(metadata, 0, sizeof(*metadata));
    fp = fopen(metadata_path, "r");
    if (!fp) {
        return FALSE;
    }

    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, " \"grid_type\": \"%31[^\"]\"", metadata->grid_type) == 1) {
            continue;
        }
        if (sscanf(line, " \"grid_level\": %d", &metadata->grid_level) == 1) {
            continue;
        }
        if (sscanf(line, " \"lat_divisions\": %d", &metadata->lat_divisions) == 1) {
            continue;
        }
        if (sscanf(line, " \"lon_divisions\": %d", &metadata->lon_divisions) == 1) {
            continue;
        }
        if (sscanf(line, " \"vertex_count\": %d", &metadata->vertex_count) == 1) {
            continue;
        }
        if (sscanf(line, " \"face_count\": %d", &metadata->face_count) == 1) {
            continue;
        }
        if (sscanf(line, " \"rectangle_count\": %d", &metadata->rectangle_count) == 1) {
            continue;
        }
        if (sscanf(line, " \"triangle_count\": %d", &metadata->triangle_count) == 1) {
            continue;
        }
    }

    fclose(fp);
    return TRUE;
}

static unsigned int
grid_coverage_validate_ico_metadata(const char *base_filename, int level,
                                    int vertex_count, int face_count) {
    char metadata_path[256];
    GridMetadata metadata;

    snprintf(metadata_path, sizeof(metadata_path), "./generated/grids/%s.json",
             base_filename);
    if (!load_grid_metadata_file(metadata_path, &metadata)) {
        fprintf(stderr, "Grid metadata missing for %s, continuing without validation\n",
                base_filename);
        return TRUE;
    }

    if (strcmp(metadata.grid_type, "icosahedral") != 0 ||
        metadata.grid_level != level ||
        metadata.vertex_count != vertex_count ||
        metadata.face_count != face_count) {
        fprintf(stderr, "Grid metadata mismatch for %s\n", base_filename);
        return FALSE;
    }

    return TRUE;
}

static unsigned int
grid_coverage_validate_latlon_metadata(const char *base_filename,
                                       int lat_divisions, int lon_divisions,
                                       int vertex_count, int face_count) {
    char metadata_path[256];
    GridMetadata metadata;

    snprintf(metadata_path, sizeof(metadata_path), "./generated/grids/%s.json",
             base_filename);
    if (!load_grid_metadata_file(metadata_path, &metadata)) {
        fprintf(stderr, "Grid metadata missing for %s, continuing without validation\n",
                base_filename);
        return TRUE;
    }

    if (strcmp(metadata.grid_type, "latlon") != 0 ||
        metadata.lat_divisions != lat_divisions ||
        metadata.lon_divisions != lon_divisions ||
        metadata.vertex_count != vertex_count ||
        metadata.triangle_count != face_count) {
        fprintf(stderr, "LatLon grid metadata mismatch for %s\n", base_filename);
        return FALSE;
    }

    return TRUE;
}

/*
 * grid_coverage_compute
 * 计算所有卫星对格网的覆盖
 */
void grid_coverage_compute(const Satellite_list satellites, const CentralBody *pcb) {
    
    // 检查是否有任何格网数据
    int has_grids = (grid_coverage.ico_cells && grid_coverage.ico_cell_count > 0) ||
                    (grid_coverage.latlon_cells && grid_coverage.latlon_cell_count > 0);
    
    if (!grid_coverage_enabled || !has_grids || !satellites) {
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
            grid_coverage.satellite_coverages[i].covered_ico_grids = NULL;
            grid_coverage.satellite_coverages[i].ico_coverage_count = 0;
            grid_coverage.satellite_coverages[i].max_ico_coverage = 0;
            grid_coverage.satellite_coverages[i].covered_latlon_grids = NULL;
            grid_coverage.satellite_coverages[i].latlon_coverage_count = 0;
            grid_coverage.satellite_coverages[i].max_latlon_coverage = 0;
        }
        
        grid_coverage.max_satellites = current_satellite_count;
    }
    
    // 清除之前的覆盖记录
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        grid_coverage.satellite_coverages[i].ico_coverage_count = 0;
        grid_coverage.satellite_coverages[i].latlon_coverage_count = 0;
    }
    
    // 遍历所有卫星，计算每个卫星覆盖的格网
    grid_coverage.satellite_count = 0;
    int total_coverage = 0;
    
    for (sl = satellites; sl != NULL; sl = sl->next) {
        SatelliteCoverageContext sat_ctx;
        int added = 0;

        if (!sl->s || !sl->s->can_display_satellite) continue;
        
        int satellite_id = sl->s->id;
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[grid_coverage.satellite_count];
        sat_cov->satellite_id = satellite_id;
        sat_cov->ico_coverage_count = 0;
        sat_cov->latlon_coverage_count = 0;
        satellite_coverage_context_init(sl->s, grid_coverage.coverage_angle,
                                        pcb, &sat_ctx);
        if (!sat_ctx.valid) {
            grid_coverage.satellite_count++;
            continue;
        }
        
        // 根据当前模式处理格网
        if (grid_coverage.both_mode) {
            added += collect_coverage_for_cells(
                grid_coverage.ico_cells, grid_coverage.ico_cell_count, &sat_ctx,
                &sat_cov->covered_ico_grids, &sat_cov->ico_coverage_count,
                &sat_cov->max_ico_coverage, "ico", satellite_id);
            added += collect_coverage_for_cells(
                grid_coverage.latlon_cells, grid_coverage.latlon_cell_count, &sat_ctx,
                &sat_cov->covered_latlon_grids, &sat_cov->latlon_coverage_count,
                &sat_cov->max_latlon_coverage, "latlon", satellite_id);
        } else if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
            added += collect_coverage_for_cells(
                grid_coverage.ico_cells, grid_coverage.ico_cell_count, &sat_ctx,
                &sat_cov->covered_ico_grids, &sat_cov->ico_coverage_count,
                &sat_cov->max_ico_coverage, "ico", satellite_id);
        } else {
            added += collect_coverage_for_cells(
                grid_coverage.latlon_cells, grid_coverage.latlon_cell_count, &sat_ctx,
                &sat_cov->covered_latlon_grids, &sat_cov->latlon_coverage_count,
                &sat_cov->max_latlon_coverage, "latlon", satellite_id);
        }
        total_coverage += added;
        
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
    int has_grids = (grid_coverage.ico_cells && grid_coverage.ico_cell_count > 0) ||
                    (grid_coverage.latlon_cells && grid_coverage.latlon_cell_count > 0);
    if (grid_coverage_enabled && has_grids) {
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
    
    if (!sat_cov) {
        *covered_grids = NULL;
        return 0;
    }
    
    // 根据当前模式返回相应的覆盖数据
    if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL && sat_cov->ico_coverage_count > 0) {
        *covered_grids = malloc(sat_cov->ico_coverage_count * sizeof(int));
        if (!*covered_grids) return 0;
        memcpy(*covered_grids, sat_cov->covered_ico_grids, sat_cov->ico_coverage_count * sizeof(int));
        return sat_cov->ico_coverage_count;
    } else if (grid_coverage.grid_type == GRID_TYPE_LATLON && sat_cov->latlon_coverage_count > 0) {
        *covered_grids = malloc(sat_cov->latlon_coverage_count * sizeof(int));
        if (!*covered_grids) return 0;
        memcpy(*covered_grids, sat_cov->covered_latlon_grids, sat_cov->latlon_coverage_count * sizeof(int));
        return sat_cov->latlon_coverage_count;
    }
    
    *covered_grids = NULL;
    return 0;
}

/*
 * grid_coverage_get_grid_coverage
 * 获取覆盖指定格网的卫星列表
 */
int grid_coverage_get_grid_coverage(int grid_id, int **covering_satellites) {
    if (!grid_coverage.satellite_coverages || !covering_satellites) {
        return 0;
    }
    
    // 根据当前模式检查grid_id有效性
    int max_grid_id = 0;
    if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
        max_grid_id = grid_coverage.ico_cell_count;
    } else if (grid_coverage.grid_type == GRID_TYPE_LATLON) {
        max_grid_id = grid_coverage.latlon_cell_count;
    }
    
    if (grid_id < 0 || grid_id >= max_grid_id) {
        return 0;
    }
    
    // 统计覆盖此格网的卫星数量
    int count = 0;
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        
        if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
            for (int j = 0; j < sat_cov->ico_coverage_count; j++) {
                if (sat_cov->covered_ico_grids[j] == grid_id) {
                    count++;
                    break;
                }
            }
        } else if (grid_coverage.grid_type == GRID_TYPE_LATLON) {
            for (int j = 0; j < sat_cov->latlon_coverage_count; j++) {
                if (sat_cov->covered_latlon_grids[j] == grid_id) {
                    count++;
                    break;
                }
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
        
        if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
            for (int j = 0; j < sat_cov->ico_coverage_count; j++) {
                if (sat_cov->covered_ico_grids[j] == grid_id) {
                    (*covering_satellites)[index++] = sat_cov->satellite_id;
                    break;
                }
            }
        } else if (grid_coverage.grid_type == GRID_TYPE_LATLON) {
            for (int j = 0; j < sat_cov->latlon_coverage_count; j++) {
                if (sat_cov->covered_latlon_grids[j] == grid_id) {
                    (*covering_satellites)[index++] = sat_cov->satellite_id;
                    break;
                }
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
    int has_grids = (grid_coverage.ico_cells && grid_coverage.ico_cell_count > 0) ||
                    (grid_coverage.latlon_cells && grid_coverage.latlon_cell_count > 0);
    
    if (!has_grids) {
        fprintf(stderr, "=== Grid Coverage Statistics ===\n");
        fprintf(stderr, "Grid coverage not initialized\n");
        fprintf(stderr, "================================\n");
        return;
    }
    
    fprintf(stderr, "\n=== Grid Coverage Statistics ===\n");
    
    if (grid_coverage.both_mode) {
        fprintf(stderr, "Mode: BOTH (Icosahedral + Lat-Lon)\n\n");
        
        // 统计二十面体格网
        fprintf(stderr, "--- Icosahedral Grid ---\n");
        fprintf(stderr, "Grid level: %d\n", grid_coverage.grid_level);
        fprintf(stderr, "Total cells: %d\n", grid_coverage.ico_cell_count);
        
        int ico_total = 0;
        for (int i = 0; i < grid_coverage.satellite_count; i++) {
            ico_total += grid_coverage.satellite_coverages[i].ico_coverage_count;
        }
        fprintf(stderr, "Total coverage instances: %d\n", ico_total);
        if (grid_coverage.satellite_count > 0) {
            fprintf(stderr, "Avg coverage per satellite: %.2f grids\n\n", 
                    (double)ico_total / grid_coverage.satellite_count);
        }
        
        // 统计经纬度格网
        fprintf(stderr, "--- Lat-Lon Grid ---\n");
        fprintf(stderr, "Grid divisions: %d x %d (lat x lon)\n", 
                grid_coverage.lat_divisions, grid_coverage.lon_divisions);
        fprintf(stderr, "Total cells: %d\n", grid_coverage.latlon_cell_count);
        
        int latlon_total = 0;
        for (int i = 0; i < grid_coverage.satellite_count; i++) {
            latlon_total += grid_coverage.satellite_coverages[i].latlon_coverage_count;
        }
        fprintf(stderr, "Total coverage instances: %d\n", latlon_total);
        if (grid_coverage.satellite_count > 0) {
            fprintf(stderr, "Avg coverage per satellite: %.2f grids\n", 
                    (double)latlon_total / grid_coverage.satellite_count);
        }
        
    } else if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
        fprintf(stderr, "Grid type: Icosahedral\n");
        fprintf(stderr, "Grid level: %d\n", grid_coverage.grid_level);
        fprintf(stderr, "Coverage angle: %.2f degrees\n", grid_coverage.coverage_angle * RAD_TO_DEG);
        fprintf(stderr, "Total grid cells: %d\n", grid_coverage.ico_cell_count);
        fprintf(stderr, "Active satellites: %d\n", grid_coverage.satellite_count);
        
        int total_coverage = 0;
        int max_coverage = 0;
        for (int i = 0; i < grid_coverage.satellite_count; i++) {
            int count = grid_coverage.satellite_coverages[i].ico_coverage_count;
            total_coverage += count;
            if (count > max_coverage) max_coverage = count;
        }
        
        fprintf(stderr, "Total coverage instances: %d\n", total_coverage);
        if (grid_coverage.satellite_count > 0) {
            fprintf(stderr, "Average coverage per satellite: %.2f grids\n", 
                    (double)total_coverage / grid_coverage.satellite_count);
        }
        fprintf(stderr, "Max coverage per satellite: %d grids\n", max_coverage);
        
        // 示例格网编码
        if (grid_coverage.ico_cell_count > 0) {
            fprintf(stderr, "\nSample grid codes (first 5):\n");
            int examples = grid_coverage.ico_cell_count < 5 ? grid_coverage.ico_cell_count : 5;
            for (int i = 0; i < examples; i++) {
                fprintf(stderr, "  Grid %d: %s\n", i, grid_coverage.ico_cells[i].qtree_code.code_string);
            }
        }
        
    } else {
        fprintf(stderr, "Grid type: Lat-Lon\n");
        fprintf(stderr, "Grid divisions: %d x %d (lat x lon)\n", 
                grid_coverage.lat_divisions, grid_coverage.lon_divisions);
        fprintf(stderr, "Coverage angle: %.2f degrees\n", grid_coverage.coverage_angle * RAD_TO_DEG);
        fprintf(stderr, "Total grid cells: %d\n", grid_coverage.latlon_cell_count);
        fprintf(stderr, "Active satellites: %d\n", grid_coverage.satellite_count);
        
        int total_coverage = 0;
        int max_coverage = 0;
        for (int i = 0; i < grid_coverage.satellite_count; i++) {
            int count = grid_coverage.satellite_coverages[i].latlon_coverage_count;
            total_coverage += count;
            if (count > max_coverage) max_coverage = count;
        }
        
        fprintf(stderr, "Total coverage instances: %d\n", total_coverage);
        if (grid_coverage.satellite_count > 0) {
            fprintf(stderr, "Average coverage per satellite: %.2f grids\n", 
                    (double)total_coverage / grid_coverage.satellite_count);
        }
        fprintf(stderr, "Max coverage per satellite: %d grids\n", max_coverage);
        
        // 示例格网编码
        if (grid_coverage.latlon_cell_count > 0) {
            fprintf(stderr, "\nSample grid codes (first 5):\n");
            int examples = grid_coverage.latlon_cell_count < 5 ? grid_coverage.latlon_cell_count : 5;
            for (int i = 0; i < examples; i++) {
                fprintf(stderr, "  Grid %d: %s\n", i, grid_coverage.latlon_cells[i].latlon_code.code_string);
            }
        }
    }
    
    fprintf(stderr, "================================\n\n");
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

/* 经纬度编码实现 */

/*
 * latlon_code_to_string
 * 将经纬度编码转换为字符串格式
 */
void latlon_code_to_string(const LatLonCode *code, char *output) {
    if (!code || !output) return;
    snprintf(output, 64, "LAT%03d_LON%03d", code->lat_idx, code->lon_idx);
}

/*
 * latlon_string_to_code
 * 将字符串格式的编码转换为LatLonCode结构
 */
int latlon_string_to_code(const char *code_string, LatLonCode *code) {
    if (!code_string || !code) return 0;
    
    // 解析格式: "LAT###_LON###"
    if (strncmp(code_string, "LAT", 3) != 0) return 0;
    
    // 提取纬度索引和经度索引
    int lat_idx, lon_idx;
    if (sscanf(code_string, "LAT%d_LON%d", &lat_idx, &lon_idx) != 2) {
        return 0;
    }
    
    code->lat_idx = lat_idx;
    code->lon_idx = lon_idx;
    strncpy(code->code_string, code_string, 63);
    code->code_string[63] = '\0';
    
    return 1;
}

/*
 * grid_coverage_get_type
 * 获取当前格网类型
 */
GridType grid_coverage_get_type(void) {
    return grid_coverage.grid_type;
}


/* TCL命令接口 */

/*
 * grid_coverage_on_cmd
 * 启用格网覆盖计算（二十面体格网）
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
    
    // 如果级别不同或格网类型不同，需要重新初始化
    if (grid_coverage.ico_cells && 
        (grid_coverage.grid_level != level || grid_coverage.grid_type != GRID_TYPE_ICOSAHEDRAL)) {
        grid_coverage_cleanup();
    }
    
    if (!grid_coverage.ico_cells) {
        if (!grid_coverage_init(level)) {
            return "Failed to initialize grid coverage";
        }
    }
    
    grid_coverage_enabled = 1;
    fprintf(stderr, "Grid coverage enabled (Icosahedral, level %d, %d cells)\n", 
            level, grid_coverage.ico_cell_count);
    
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
 * grid_coverage_on_latlon_cmd
 * 启用格网覆盖计算（经纬度格网）
 */
char *grid_coverage_on_latlon_cmd(int argc, char *argv[]) {
    int lat_divisions = 18; // 默认纬度划分数
    int lon_divisions = 36; // 默认经度划分数
    
    // 从参数中获取划分数 (argv[2] 是纬度划分, argv[3] 是经度划分)
    if (argc >= 3) {
        lat_divisions = atoi(argv[2]);
        if (lat_divisions < 1 || lat_divisions > 180) {
            fprintf(stderr, "Invalid lat_divisions %d, using default 18\n", lat_divisions);
            lat_divisions = 18;
        }
    }
    
    if (argc >= 4) {
        lon_divisions = atoi(argv[3]);
        if (lon_divisions < 1 || lon_divisions > 360) {
            fprintf(stderr, "Invalid lon_divisions %d, using default 36\n", lon_divisions);
            lon_divisions = 36;
        }
    }
    
    // 如果划分数不同或格网类型不同，需要重新初始化
    if (grid_coverage.latlon_cells && 
        (grid_coverage.lat_divisions != lat_divisions || 
         grid_coverage.lon_divisions != lon_divisions ||
         grid_coverage.grid_type != GRID_TYPE_LATLON)) {
        grid_coverage_cleanup();
    }
    
    if (!grid_coverage.latlon_cells) {
        if (!grid_coverage_init_latlon(lat_divisions, lon_divisions)) {
            return "Failed to initialize latlon grid coverage";
        }
    }
    
    grid_coverage_enabled = 1;
    fprintf(stderr, "Grid coverage enabled (LatLon, %dx%d, %d cells)\n", 
            lat_divisions, lon_divisions, grid_coverage.latlon_cell_count);
    
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
 * grid_coverage_on_both_cmd
 * 同时启用两种格网类型（二十面体+经纬度）
 */
char *grid_coverage_on_both_cmd(int argc, char *argv[]) {
    int ico_level = 2;           // 默认二十面体级别
    int lat_divisions = 18;      // 默认纬度划分数
    int lon_divisions = 36;      // 默认经度划分数
    
    // 解析参数
    if (argc >= 3) {
        ico_level = atoi(argv[2]);
        if (ico_level < 0 || ico_level > 6) {
            fprintf(stderr, "Invalid grid level %d, using default level 2\n", ico_level);
            ico_level = 2;
        }
    }
    
    if (argc >= 4) {
        lat_divisions = atoi(argv[3]);
        if (lat_divisions < 1 || lat_divisions > 180) {
            fprintf(stderr, "Invalid lat_divisions %d, using default 18\n", lat_divisions);
            lat_divisions = 18;
        }
    }
    
    if (argc >= 5) {
        lon_divisions = atoi(argv[4]);
        if (lon_divisions < 1 || lon_divisions > 360) {
            fprintf(stderr, "Invalid lon_divisions %d, using default 36\n", lon_divisions);
            lon_divisions = 36;
        }
    }
    
    fprintf(stderr, "\n=== Initializing BOTH grid types ===\n");
    fprintf(stderr, "Icosahedral: level %d\n", ico_level);
    fprintf(stderr, "Lat-Lon: %dx%d\n", lat_divisions, lon_divisions);
    
    // 清理旧数据
    grid_coverage_cleanup();
    
    // 设置both模式
    grid_coverage.both_mode = 1;
    grid_coverage.grid_level = ico_level;
    grid_coverage.lat_divisions = lat_divisions;
    grid_coverage.lon_divisions = lon_divisions;
    grid_coverage.coverage_angle = DEFAULT_COVERAGE_ANGLE_DEG * DEG_TO_RAD;
    
    // 步骤1: 加载二十面体格网到独立数组
    fprintf(stderr, "\nStep 1: Loading icosahedral grid...\n");
    
    // 估算格网单元数量
    int estimated_ico_cells = 20;
    for (int i = 0; i < ico_level; i++) {
        estimated_ico_cells *= 4;
    }
    estimated_ico_cells += 100;
    
    grid_coverage.max_ico_cells = estimated_ico_cells;
    grid_coverage.ico_cells = malloc(grid_coverage.max_ico_cells * sizeof(GridCell));
    
    if (!grid_coverage.ico_cells) {
        grid_coverage.both_mode = 0;
        return "Failed to allocate memory for icosahedral grid";
    }
    
    // 直接加载二十面体格网（使用ico_cells）
    if (!grid_coverage_load_from_file(ico_level)) {
        fprintf(stderr, "Failed to load icosahedral grid file\n");
        free(grid_coverage.ico_cells);
        grid_coverage.ico_cells = NULL;
        grid_coverage.both_mode = 0;
        return "Failed to load icosahedral grid";
    }
    
    fprintf(stderr, "Icosahedral grid loaded: %d cells\n", grid_coverage.ico_cell_count);
    
    // 步骤2: 加载经纬度格网到独立数组
    fprintf(stderr, "\nStep 2: Loading lat-lon grid...\n");
    
    int estimated_latlon_cells = lat_divisions * lon_divisions * 2 + 100;
    grid_coverage.max_latlon_cells = estimated_latlon_cells;
    grid_coverage.latlon_cells = malloc(grid_coverage.max_latlon_cells * sizeof(GridCell));
    
    if (!grid_coverage.latlon_cells) {
        free(grid_coverage.ico_cells);
        grid_coverage.ico_cells = NULL;
        grid_coverage.both_mode = 0;
        return "Failed to allocate memory for lat-lon grid";
    }
    
    // 直接加载经纬度格网（使用latlon_cells）
    if (!grid_coverage_load_latlon_from_file(lat_divisions, lon_divisions)) {
        fprintf(stderr, "Failed to load lat-lon grid file\n");
        free(grid_coverage.ico_cells);
        free(grid_coverage.latlon_cells);
        grid_coverage.ico_cells = NULL;
        grid_coverage.latlon_cells = NULL;
        grid_coverage.both_mode = 0;
        return "Failed to load lat-lon grid";
    }
    
    fprintf(stderr, "Lat-lon grid loaded: %d cells\n", grid_coverage.latlon_cell_count);
    
    grid_coverage_enabled = 1;
    
    fprintf(stderr, "\n=== Both grids enabled successfully ===\n");
    fprintf(stderr, "Icosahedral: %d cells\n", grid_coverage.ico_cell_count);
    fprintf(stderr, "Lat-Lon: %d cells\n", grid_coverage.latlon_cell_count);
    fprintf(stderr, "Both grid types will be sent simultaneously\n\n");
    
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
    grid_coverage.both_mode = 0;  // 重置both_mode标志
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
 * 查询格网编码命令
 */
char *grid_coverage_query_code_cmd(int argc, char *argv[]) {
    if (argc < 3) {
        return "Usage: grid_coverage_query_code <grid_id>";
    }
    
    int grid_id = atoi(argv[2]);
    GridCell *cell = NULL;
    
    // 根据当前模式查询
    if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL) {
        if (grid_id < 0 || grid_id >= grid_coverage.ico_cell_count) {
            return "Invalid grid ID for icosahedral grid";
        }
        cell = &grid_coverage.ico_cells[grid_id];
    } else if (grid_coverage.grid_type == GRID_TYPE_LATLON) {
        if (grid_id < 0 || grid_id >= grid_coverage.latlon_cell_count) {
            return "Invalid grid ID for lat-lon grid";
        }
        cell = &grid_coverage.latlon_cells[grid_id];
    } else {
        return "Grid not initialized";
    }
    
    fprintf(stderr, "Grid %d information:\n", grid_id);
    fprintf(stderr, "  Type: %s\n", 
            cell->grid_type == GRID_TYPE_ICOSAHEDRAL ? "Icosahedral" : "Lat-Lon");
    fprintf(stderr, "  Position: (%.2f°, %.2f°)\n", cell->lat, cell->lon);
    
    if (cell->grid_type == GRID_TYPE_ICOSAHEDRAL) {
        fprintf(stderr, "  Quadtree code: %s\n", cell->qtree_code.code_string);
        fprintf(stderr, "  Base face: %d\n", cell->qtree_code.base_face_id);
        fprintf(stderr, "  Level: %d\n", cell->qtree_code.level);
        fprintf(stderr, "  Path code: 0x%x\n", cell->qtree_code.path_code);
        
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
    } else {
        fprintf(stderr, "  Lat-Lon code: %s\n", cell->latlon_code.code_string);
        fprintf(stderr, "  Lat index: %d\n", cell->latlon_code.lat_idx);
        fprintf(stderr, "  Lon index: %d\n", cell->latlon_code.lon_idx);
    }
    
    return "OK";
}

/*
 * grid_coverage_socket_init
 * 初始化Unix Socket连接
 */
int grid_coverage_socket_init(void) {
    if (socket_fd >= 0) {
        return 1;
    }

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

static unsigned int
grid_coverage_socket_send_payload(const char *buffer, size_t length) {
    ssize_t sent;

    if (!buffer || length == 0 || socket_fd < 0) {
        return FALSE;
    }

    sent = sendto(socket_fd, buffer, length, 0,
                  (struct sockaddr*)&server_addr, sizeof(server_addr));
    if (sent < 0 || (size_t) sent != length) {
        fprintf(stderr, "Failed to send grid coverage payload: %s\n",
                strerror(errno));
        return FALSE;
    }

    return TRUE;
}

static unsigned int
grid_coverage_socket_send_codes(int satellite_id,
                                const int *grid_indices,
                                int grid_count,
                                const GridCell *cells,
                                int cell_count,
                                unsigned int use_icosahedral) {
    char buffer[GRID_COVERAGE_MAX_DATAGRAM];
    size_t max_codes_per_fragment = GRID_COVERAGE_MAX_DATAGRAM -
                                    GRID_COVERAGE_HEADER_MARGIN - 2;
    int fragment_count = 1;
    size_t fragment_usage = 0;
    int has_valid_codes = FALSE;
    int grid_pos;
    int current_fragment;

    for (grid_pos = 0; grid_pos < grid_count; grid_pos++) {
        int grid_idx = grid_indices[grid_pos];
        const char *code;
        size_t code_len;
        size_t add_len;

        if (grid_idx < 0 || grid_idx >= cell_count) {
            continue;
        }

        has_valid_codes = TRUE;
        code = use_icosahedral ? cells[grid_idx].qtree_code.code_string
                               : cells[grid_idx].latlon_code.code_string;
        code_len = strlen(code);
        add_len = fragment_usage ? code_len + 1 : code_len;

        if (fragment_usage && fragment_usage + add_len > max_codes_per_fragment) {
            fragment_count++;
            fragment_usage = code_len;
        } else {
            fragment_usage += add_len;
        }
    }

    if (!has_valid_codes) {
        return TRUE;
    }

    grid_pos = 0;
    current_fragment = 1;
    while (grid_pos < grid_count) {
        int pos;
        int appended_codes = FALSE;

        if (fragment_count > 1) {
            pos = snprintf(buffer, sizeof(buffer), "%d@%d/%d:",
                           satellite_id, current_fragment, fragment_count);
        } else {
            pos = snprintf(buffer, sizeof(buffer), "%d:", satellite_id);
        }

        if (pos < 0 || (size_t) pos >= sizeof(buffer) - 2) {
            fprintf(stderr, "Failed to build grid coverage message header\n");
            return FALSE;
        }

        while (grid_pos < grid_count) {
            int grid_idx = grid_indices[grid_pos];
            const char *code;
            size_t code_len;
            size_t required_len;

            grid_pos++;
            if (grid_idx < 0 || grid_idx >= cell_count) {
                continue;
            }

            code = use_icosahedral ? cells[grid_idx].qtree_code.code_string
                                   : cells[grid_idx].latlon_code.code_string;
            code_len = strlen(code);
            required_len = code_len + (appended_codes ? 1 : 0) + 1;

            if ((size_t) pos + required_len >= sizeof(buffer)) {
                grid_pos--;
                break;
            }

            if (appended_codes) {
                buffer[pos++] = ',';
            }
            memcpy(buffer + pos, code, code_len);
            pos += code_len;
            appended_codes = TRUE;
        }

        if (!appended_codes) {
            fprintf(stderr, "Grid coverage fragment had no encodable payload\n");
            return FALSE;
        }

        buffer[pos++] = '\n';
        if (!grid_coverage_socket_send_payload(buffer, (size_t) pos)) {
            return FALSE;
        }

        current_fragment++;
    }

    return TRUE;
}

/*
 * grid_coverage_socket_send_data
 * 发送卫星覆盖数据到Socket
 */
void grid_coverage_socket_send_data(void) {
    if (socket_fd < 0 || !grid_coverage_enabled || !grid_coverage.satellite_coverages) {
        return;
    }
    
    // 为每个卫星发送覆盖数据
    for (int i = 0; i < grid_coverage.satellite_count; i++) {
        SatelliteCoverage *sat_cov = &grid_coverage.satellite_coverages[i];
        
        // Both模式：分别发送两种格网的覆盖数据
        if (grid_coverage.both_mode) {
            // 发送二十面体格网覆盖
            if (sat_cov->ico_coverage_count > 0) {
                if (!grid_coverage_socket_send_codes(
                        sat_cov->satellite_id,
                        sat_cov->covered_ico_grids,
                        sat_cov->ico_coverage_count,
                        grid_coverage.ico_cells,
                        grid_coverage.ico_cell_count,
                        TRUE)) {
                    return;
                }
            }
            
            // 发送经纬度格网覆盖
            if (sat_cov->latlon_coverage_count > 0) {
                if (!grid_coverage_socket_send_codes(
                        sat_cov->satellite_id,
                        sat_cov->covered_latlon_grids,
                        sat_cov->latlon_coverage_count,
                        grid_coverage.latlon_cells,
                        grid_coverage.latlon_cell_count,
                        FALSE)) {
                    return;
                }
            }
        } else {
            // 单格网模式：根据grid_type判断使用哪个数组
            if (grid_coverage.grid_type == GRID_TYPE_ICOSAHEDRAL && sat_cov->ico_coverage_count > 0) {
                if (!grid_coverage_socket_send_codes(
                        sat_cov->satellite_id,
                        sat_cov->covered_ico_grids,
                        sat_cov->ico_coverage_count,
                        grid_coverage.ico_cells,
                        grid_coverage.ico_cell_count,
                        TRUE)) {
                    return;
                }
            } else if (grid_coverage.grid_type == GRID_TYPE_LATLON && sat_cov->latlon_coverage_count > 0) {
                if (!grid_coverage_socket_send_codes(
                        sat_cov->satellite_id,
                        sat_cov->covered_latlon_grids,
                        sat_cov->latlon_coverage_count,
                        grid_coverage.latlon_cells,
                        grid_coverage.latlon_cell_count,
                        FALSE)) {
                    return;
                }
            }
        }
    }
}
