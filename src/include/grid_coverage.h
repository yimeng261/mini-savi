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
 * grid_coverage.h
 *
 */

#ifndef _GRID_COVERAGE_H_
#define _GRID_COVERAGE_H_

#include <stdint.h>
#include "Satellite.h"
#include "stats_utils.h"

/* 格网类型枚举 */
typedef enum {
    GRID_TYPE_ICOSAHEDRAL = 0,      /* 二十面体格网 */
    GRID_TYPE_LATLON = 1            /* 经纬度格网 */
} GridType;

/* 四叉树编码结构（用于二十面体格网） */
#define MAX_QUADTREE_DEPTH 10       /* 最大四叉树深度 */
#define QUADTREE_CODE_LENGTH 32     /* 四叉树编码字符串最大长度 */

typedef struct {
    int base_face_id;               /* 基础二十面体面ID (0-19) */
    int level;                      /* 细分级别 */
    unsigned int path_code;         /* 路径编码 (每2位表示一个四叉树分支: 00,01,10,11) */
    char code_string[QUADTREE_CODE_LENGTH]; /* 人类可读的编码字符串 */
} QuadtreeCode;

/* 经纬度编码结构（用于经纬度格网） */
typedef struct {
    int lat_idx;                    /* 纬度索引 */
    int lon_idx;                    /* 经度索引 */
    int triangle_idx;               /* 三角形索引 (0=无后缀, 1=T1, 2=T2) */
    char code_string[64];           /* 编码字符串 "LAT##_LON###_T#" */
} LatLonCode;

/* 格网单元结构 */
typedef struct {
    int grid_id;                    /* 原始顺序格网ID (保持兼容性) */
    GridType grid_type;             /* 格网类型 */
    union {
        QuadtreeCode qtree_code;    /* 四叉树编码（二十面体格网） */
        LatLonCode latlon_code;     /* 经纬度编码（经纬度格网） */
    };
    double lat;                     /* 格网中心纬度 (度) */
    double lon;                     /* 格网中心经度 (度) */
    double surface_x, surface_y, surface_z;  /* 地表位置 (笛卡尔坐标) */
    double vertices[3][3];          /* 三角形顶点在地表的坐标 */
} GridCell;

/* 卫星覆盖记录结构 */
typedef struct {
    int satellite_id;               /* 卫星ID */
    
    /* 二十面体格网覆盖（仅在icosahedral或both模式下使用） */
    int *covered_ico_grids;         /* 二十面体格网覆盖列表 */
    int ico_coverage_count;         /* 二十面体格网覆盖数量 */
    int max_ico_coverage;           /* 二十面体格网最大容量 */
    
    /* 经纬度格网覆盖（仅在latlon或both模式下使用） */
    int *covered_latlon_grids;      /* 经纬度格网覆盖列表 */
    int latlon_coverage_count;      /* 经纬度格网覆盖数量 */
    int max_latlon_coverage;        /* 经纬度格网最大容量 */
} SatelliteCoverage;

/* 空间索引：纬度带×经度带分桶 */
#define SPATIAL_INDEX_BANDS 18      /* 每10度一个桶，覆盖-90到+90 */
#define SPATIAL_INDEX_LON_BANDS 36  /* 每10度一个桶，覆盖-180到+180 */

typedef struct {
    int *cell_indices;              /* 该桶内的格网单元索引数组 */
    int count;                      /* 桶内格网数量 */
    int capacity;                   /* 桶容量 */
} LatBand;

typedef struct {
    LatBand bands[SPATIAL_INDEX_BANDS][SPATIAL_INDEX_LON_BANDS];
    double cell_margin_rad;         /* 格网单元角尺寸余量 (弧度) */
    int built;                      /* 是否已构建 */
} SpatialIndex;

/* 格网覆盖数据结构 */
typedef struct {
    /* 二十面体格网（icosahedral或both模式下使用） */
    GridCell *ico_cells;            /* 二十面体格网单元数组 */
    int ico_cell_count;             /* 二十面体格网单元数量 */
    int max_ico_cells;              /* 最大二十面体格网单元数 */

    /* 经纬度格网（latlon或both模式下使用） */
    GridCell *latlon_cells;         /* 经纬度格网单元数组 */
    int latlon_cell_count;          /* 经纬度格网单元数量 */
    int max_latlon_cells;           /* 最大经纬度格网单元数 */

    /* 空间索引 */
    SpatialIndex ico_spatial;       /* 二十面体格网空间索引 */
    SpatialIndex latlon_spatial;    /* 经纬度格网空间索引 */

    SatelliteCoverage *satellite_coverages; /* 卫星覆盖记录数组 */
    int satellite_count;            /* 卫星数量 */
    int max_satellites;             /* 最大卫星数量 */
    double coverage_angle;          /* 卫星覆盖角度 (弧度) */
    GridType grid_type;             /* 当前格网类型 */
    int grid_level;                 /* 格网细分级别（仅二十面体） */
    int lat_divisions;              /* 纬度划分数（仅经纬度） */
    int lon_divisions;              /* 经度划分数（仅经纬度） */
    int both_mode;                  /* 是否同时使用两种格网 (1=是, 0=否) */
} GridCoverage;

/* 全局格网覆盖实例 */
extern GridCoverage grid_coverage;
extern int grid_coverage_enabled;

/* 函数声明 */
int grid_coverage_init(int grid_level);
int grid_coverage_init_latlon(int lat_divisions, int lon_divisions);
void grid_coverage_cleanup(void);
int grid_coverage_load_from_file(int level);
int grid_coverage_load_latlon_from_file(int lat_divisions, int lon_divisions);
void grid_coverage_compute(const Satellite_list satellites, const CentralBody *pcb);
void grid_coverage_set_angle(double angle_degrees);
double grid_coverage_get_angle(void);
int grid_coverage_get_satellite_coverage(int satellite_id, int **covered_grids);
int grid_coverage_get_grid_coverage(int grid_id, int **covering_satellites);
void grid_coverage_print_stats(void);
GridType grid_coverage_get_type(void);

/* 四叉树编码相关函数（二十面体格网） */
void quadtree_code_to_string(const QuadtreeCode *code, char *output);
int quadtree_string_to_code(const char *code_string, QuadtreeCode *code);
int quadtree_get_parent_code(const QuadtreeCode *code, QuadtreeCode *parent);
int quadtree_get_children_codes(const QuadtreeCode *code, QuadtreeCode children[4]);

/* 经纬度编码相关函数 */
void latlon_code_to_string(const LatLonCode *code, char *output);
int latlon_string_to_code(const char *code_string, LatLonCode *code);

/* Unix Socket功能 */
int grid_coverage_socket_init(void);
void grid_coverage_socket_cleanup(void);
void grid_coverage_socket_send_data(void);

/* Geomview 格网几何体显示 */
void write_grid_geom(const void *);
void grid_geom_gv_delete(void);
void grid_geom_invalidate(void);
void grid_geom_set_solid(const char *path);
void grid_geom_set_wireframe(const char *path);
char *grid_geom_on_cmd(int argc, char *argv[]);
char *grid_geom_off_cmd(int argc, char *argv[]);

/* 增量更新与二进制协议 */

/* 二进制消息类型 */
#define GCOV_MSG_FULL    0x01   /* 全量覆盖数据 */
#define GCOV_MSG_DELTA   0x02   /* 增量更新（diff） */

/* 二进制消息头 */
typedef struct __attribute__((packed)) {
    uint8_t  msg_type;          /* GCOV_MSG_FULL 或 GCOV_MSG_DELTA */
    uint16_t satellite_id;      /* 卫星标识 */
    uint32_t sequence;          /* 序列号（用于丢包检测） */
    uint32_t timestamp;         /* 时间戳（epoch秒） */
    uint16_t add_count;         /* 新增格网数量 */
    uint16_t remove_count;      /* 移除格网数量（仅 DELTA 模式） */
    /* 后跟 add_count 个 uint32_t（新增格网编码）
     * 再跟 remove_count 个 uint32_t（移除格网编码） */
} GridCoverageBinaryHeader;

#define GCOV_BINARY_HDR_SIZE sizeof(GridCoverageBinaryHeader)

/* 增量追踪状态（每颗卫星一份） */
typedef struct {
    uint32_t *prev_grid_codes;  /* 上一帧的格网编码数组（已排序） */
    int prev_count;             /* 上一帧格网数量 */
    int prev_capacity;          /* 数组容量 */
    uint32_t sequence;          /* 当前序列号 */
} SatelliteDeltaTracker;

/* 增量追踪全局状态 */
void grid_coverage_delta_init(int satellite_count);
void grid_coverage_delta_cleanup(void);
void grid_coverage_socket_send_data_binary(void);

/* TCL命令接口 */
char *grid_coverage_on_cmd(int argc, char *argv[]);
char *grid_coverage_on_latlon_cmd(int argc, char *argv[]);
char *grid_coverage_on_both_cmd(int argc, char *argv[]);
char *grid_coverage_off_cmd(int argc, char *argv[]);
char *grid_coverage_set_angle_cmd(int argc, char *argv[]);
char *grid_coverage_stats_cmd(int argc, char *argv[]);
char *grid_coverage_query_code_cmd(int argc, char *argv[]);

#endif
/* !_GRID_COVERAGE_H_ */
