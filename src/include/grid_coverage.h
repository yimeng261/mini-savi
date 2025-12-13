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
    char code_string[64];           /* 编码字符串 "LAT##_LON###" */
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
int quadtree_codes_are_neighbors(const QuadtreeCode *code1, const QuadtreeCode *code2);

/* 经纬度编码相关函数 */
void latlon_code_to_string(const LatLonCode *code, char *output);
int latlon_string_to_code(const char *code_string, LatLonCode *code);

/* Unix Socket功能 */
int grid_coverage_socket_init(void);
void grid_coverage_socket_cleanup(void);
void grid_coverage_socket_send_data(void);

/* 辅助函数 */
static int point_in_triangle(double px, double py, double pz,
                            double v1x, double v1y, double v1z,
                            double v2x, double v2y, double v2z,
                            double v3x, double v3y, double v3z);
static double angle_between_vectors(double x1, double y1, double z1,
                                   double x2, double y2, double z2);
static int satellite_covers_grid(const Satellite sat, const GridCell *cell,
                                double coverage_angle, const CentralBody *pcb);

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
