// grid_calc.cpp : Defines the entry point for the console application.
//
#define _USE_MATH_DEFINES
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define FILEPATH "./mini-savi/"

const char *pos[3]={"top","left","right"};
char code[100];

// 四叉树编码相关定义
#define MAX_QUADTREE_DEPTH 10
#define QUADTREE_CODE_LENGTH 32

typedef struct {
    int base_face_id;               /* 基础二十面体面ID (0-19) */
    int level;                      /* 细分级别 */
    unsigned int path_code;         /* 路径编码 (每2位表示一个四叉树分支: 00,01,10,11) */
    char code_string[QUADTREE_CODE_LENGTH]; /* 人类可读的编码字符串 */
} QuadtreeCode;

// 存储格网顶点和面的结构
typedef struct {
    double (*vertices)[3];      // 动态分配的顶点坐标 (x, y, z)
    int (*faces)[3];            // 动态分配的三角面顶点索引
    QuadtreeCode *face_codes;   // 每个面的四叉树编码
    int vertex_count;
    int face_count;
    int max_vertices;           // 最大顶点数
    int max_faces;              // 最大面数
    int grid_level;             // 当前格网级别
} GridMesh;
// 标准二十面体的12个顶点（3D坐标）
const double icosahedron_vertices[12][3] = {
    // 上顶点
    { 0.000000,  0.000000,  1.000000},
    
    // 上环（5个顶点）
    { 0.894427,  0.000000,  0.447214},
    { 0.276393,  0.850651,  0.447214},
    {-0.723607,  0.525731,  0.447214},
    {-0.723607, -0.525731,  0.447214},
    { 0.276393, -0.850651,  0.447214},
    
    // 下环（5个顶点）
    { 0.723607,  0.525731, -0.447214},
    {-0.276393,  0.850651, -0.447214},
    {-0.894427,  0.000000, -0.447214},
    {-0.276393, -0.850651, -0.447214},
    { 0.723607, -0.525731, -0.447214},
    
    // 下顶点
    { 0.000000,  0.000000, -1.000000}
};

// 二十面体的20个三角面（已调整顺序：v2、v3纬度相同，与赤道平行；v1指向不同纬度）
const int icosahedron_faces[20][3] = {
    // 上顶点连接的5个三角形（v1指向北极90°，v2、v3在上环26.6°）
    {0, 1, 2}, {0, 2, 3}, {0, 3, 4}, {0, 4, 5}, {0, 5, 1},
    
    // 上环和下环之间的10个三角形（v2、v3纬度相同）
    {6, 1, 2}, {7, 2, 3}, {8, 3, 4}, {9, 4, 5}, {10, 5, 1},
    {1, 10, 6}, {2, 6, 7}, {3, 7, 8}, {4, 8, 9}, {5, 9, 10},
    
    // 下顶点连接的5个三角形（v1指向南极-90°，v2、v3在下环-26.6°）
    {11, 6, 7}, {11, 7, 8}, {11, 8, 9}, {11, 9, 10}, {11, 10, 6}
};
const double offset[4][3][2]={
    {{0.5,1},{0.25,0.5},{0.75,0.5}},
    {{0.25,0.5},{0,0},{0.5,0}},
    {{0.5,0},{0.25,0.5},{0.75,0.5}},
    {{0.75,0.5},{0.5,0},{1,0}}
};

GridMesh grid_mesh = {0};

// 函数声明
int add_vertex_xyz(double x, double y, double z);

// 四叉树编码函数声明
void quadtree_encode_face(QuadtreeCode *code, int base_face_id, int level, int face_index_in_level);
void quadtree_code_to_string(const QuadtreeCode *code, char *output);
void assign_quadtree_codes_to_faces(int level);

// 初始化网格内存
int init_grid_mesh(int max_vertices, int max_faces) {
    grid_mesh.vertices = malloc(max_vertices * sizeof(double[3]));
    grid_mesh.faces = malloc(max_faces * sizeof(int[3]));
    grid_mesh.face_codes = malloc(max_faces * sizeof(QuadtreeCode));
    
    if (!grid_mesh.vertices || !grid_mesh.faces || !grid_mesh.face_codes) {
        printf("内存分配失败！\n");
        if (grid_mesh.vertices) free(grid_mesh.vertices);
        if (grid_mesh.faces) free(grid_mesh.faces);
        if (grid_mesh.face_codes) free(grid_mesh.face_codes);
        return 0;
    }
    
    grid_mesh.max_vertices = max_vertices;
    grid_mesh.max_faces = max_faces;
    grid_mesh.vertex_count = 0;
    grid_mesh.face_count = 0;
    grid_mesh.grid_level = 0;
    
    return 1;
}

// 释放网格内存
void free_grid_mesh() {
    if (grid_mesh.vertices) {
        free(grid_mesh.vertices);
        grid_mesh.vertices = NULL;
    }
    if (grid_mesh.faces) {
        free(grid_mesh.faces);
        grid_mesh.faces = NULL;
    }
    if (grid_mesh.face_codes) {
        free(grid_mesh.face_codes);
        grid_mesh.face_codes = NULL;
    }
    grid_mesh.vertex_count = 0;
    grid_mesh.face_count = 0;
    grid_mesh.max_vertices = 0;
    grid_mesh.max_faces = 0;
    grid_mesh.grid_level = 0;
}

// 扩展网格内存（如果需要）
int expand_grid_mesh() {
    int new_max_vertices = grid_mesh.max_vertices * 2;
    int new_max_faces = grid_mesh.max_faces * 2;
    
    double (*new_vertices)[3] = realloc(grid_mesh.vertices, new_max_vertices * sizeof(double[3]));
    int (*new_faces)[3] = realloc(grid_mesh.faces, new_max_faces * sizeof(int[3]));
    QuadtreeCode *new_face_codes = realloc(grid_mesh.face_codes, new_max_faces * sizeof(QuadtreeCode));
    
    if (!new_vertices || !new_faces || !new_face_codes) {
        printf("内存扩展失败！\n");
        return 0;
    }
    
    grid_mesh.vertices = new_vertices;
    grid_mesh.faces = new_faces;
    grid_mesh.face_codes = new_face_codes;
    grid_mesh.max_vertices = new_max_vertices;
    grid_mesh.max_faces = new_max_faces;
    
    return 1;
}

// 将经纬度坐标转换为笛卡尔坐标（地球表面上方）
void lonlat_to_xyz(double lon, double lat, double *x, double *y, double *z) {
    double lon_rad = lon * M_PI / 180.0;
    double lat_rad = lat * M_PI / 180.0;
    
    // SaVi使用标准化坐标系统，地球半径为1.0
    // 格网显示在地球表面上方较远距离，确保完全可见
    double grid_radius = 1.05;  // 地球表面上方5%半径处
    
    *x = grid_radius * cos(lat_rad) * cos(lon_rad);
    *y = grid_radius * cos(lat_rad) * sin(lon_rad);
    *z = grid_radius * sin(lat_rad);
}

// 添加顶点到网格（通过经纬度），返回顶点索引
int add_vertex(double lon, double lat) {
    double x, y, z;
    lonlat_to_xyz(lon, lat, &x, &y, &z);
    return add_vertex_xyz(x, y, z);
}

// 添加顶点到网格（通过3D坐标），返回顶点索引
int add_vertex_xyz(double x, double y, double z) {
    // 检查是否已存在相同的顶点（避免重复）
    for (int i = 0; i < grid_mesh.vertex_count; i++) {
        double dx = grid_mesh.vertices[i][0] - x;
        double dy = grid_mesh.vertices[i][1] - y;
        double dz = grid_mesh.vertices[i][2] - z;
        if (dx*dx + dy*dy + dz*dz < 1e-10) {
            return i;
        }
    }
    
    // 检查是否需要扩展内存
    if (grid_mesh.vertex_count >= grid_mesh.max_vertices) {
        if (!expand_grid_mesh()) {
            printf("无法扩展顶点内存！\n");
            return -1;
        }
    }
    
    // 添加新顶点
    grid_mesh.vertices[grid_mesh.vertex_count][0] = x;
    grid_mesh.vertices[grid_mesh.vertex_count][1] = y;
    grid_mesh.vertices[grid_mesh.vertex_count][2] = z;
    return grid_mesh.vertex_count++;
}

// 向量归一化
void normalize_vector(double *x, double *y, double *z) {
    double length = sqrt(*x * *x + *y * *y + *z * *z);
    if (length > 0) {
        *x /= length;
        *y /= length;
        *z /= length;
    }
}

// 球面线性插值（SLERP）
void slerp_3d(double *result_x, double *result_y, double *result_z,
              double x1, double y1, double z1,
              double x2, double y2, double z2,
              double t) {
    // 计算两个向量的点积
    double dot = x1 * x2 + y1 * y2 + z1 * z2;
    
    // 处理点积接近1的情况（向量几乎相同）
    if (dot > 0.9995) {
        // 使用线性插值
        *result_x = (1.0 - t) * x1 + t * x2;
        *result_y = (1.0 - t) * y1 + t * y2;
        *result_z = (1.0 - t) * z1 + t * z2;
        normalize_vector(result_x, result_y, result_z);
        return;
    }
    
    // 确保点积在有效范围内
    if (dot < -1.0) dot = -1.0;
    if (dot > 1.0) dot = 1.0;
    
    // 计算角度
    double theta = acos(dot);
    double sin_theta = sin(theta);
    
    if (sin_theta == 0) {
        // 向量平行，使用线性插值
        *result_x = (1.0 - t) * x1 + t * x2;
        *result_y = (1.0 - t) * y1 + t * y2;
        *result_z = (1.0 - t) * z1 + t * z2;
    } else {
        // 球面线性插值
        double factor1 = sin((1.0 - t) * theta) / sin_theta;
        double factor2 = sin(t * theta) / sin_theta;
        
        *result_x = factor1 * x1 + factor2 * x2;
        *result_y = factor1 * y1 + factor2 * y2;
        *result_z = factor1 * z1 + factor2 * z2;
    }
    
    normalize_vector(result_x, result_y, result_z);
}

// 三角形结构用于迭代细分
typedef struct {
    double v1[3], v2[3], v3[3];
    int level;
} TriangleTask;

// 迭代细分三角形（避免递归导致的栈溢出）
void subdivide_triangle_iterative(double v1[3], double v2[3], double v3[3], int level) {
    // 使用动态分配的栈来模拟递归
    int max_tasks = 1000000; // 足够大的任务队列
    TriangleTask *task_stack = malloc(max_tasks * sizeof(TriangleTask));
    if (!task_stack) {
        printf("无法分配任务栈内存！\n");
        return;
    }
    
    int stack_top = 0;
    
    // 初始任务
    memcpy(task_stack[0].v1, v1, sizeof(double) * 3);
    memcpy(task_stack[0].v2, v2, sizeof(double) * 3);
    memcpy(task_stack[0].v3, v3, sizeof(double) * 3);
    task_stack[0].level = level;
    stack_top = 1;
    
    while (stack_top > 0) {
        // 弹出任务
        stack_top--;
        TriangleTask current = task_stack[stack_top];
        
        if (current.level == 0) {
            // 基础情况：添加三角形
            double grid_radius = 1.05;
            
            // 归一化并缩放到正确半径
            double nv1[3] = {current.v1[0], current.v1[1], current.v1[2]};
            double nv2[3] = {current.v2[0], current.v2[1], current.v2[2]};
            double nv3[3] = {current.v3[0], current.v3[1], current.v3[2]};
            
            normalize_vector(&nv1[0], &nv1[1], &nv1[2]);
            normalize_vector(&nv2[0], &nv2[1], &nv2[2]);
            normalize_vector(&nv3[0], &nv3[1], &nv3[2]);
            
            nv1[0] *= grid_radius; nv1[1] *= grid_radius; nv1[2] *= grid_radius;
            nv2[0] *= grid_radius; nv2[1] *= grid_radius; nv2[2] *= grid_radius;
            nv3[0] *= grid_radius; nv3[1] *= grid_radius; nv3[2] *= grid_radius;
            
            int i1 = add_vertex_xyz(nv1[0], nv1[1], nv1[2]);
            int i2 = add_vertex_xyz(nv2[0], nv2[1], nv2[2]);
            int i3 = add_vertex_xyz(nv3[0], nv3[1], nv3[2]);
            
            if (i1 < 0 || i2 < 0 || i3 < 0) continue;
            
            // 检查是否需要扩展面内存
            if (grid_mesh.face_count >= grid_mesh.max_faces) {
                if (!expand_grid_mesh()) {
                    printf("无法扩展面内存！\n");
                    break;
                }
            }
            
            grid_mesh.faces[grid_mesh.face_count][0] = i1;
            grid_mesh.faces[grid_mesh.face_count][1] = i2;
            grid_mesh.faces[grid_mesh.face_count][2] = i3;
            grid_mesh.face_count++;
            
        } else {
            // 细分情况：计算边的中点并投影到球面
            double m12[3] = {(current.v1[0] + current.v2[0]) / 2, (current.v1[1] + current.v2[1]) / 2, (current.v1[2] + current.v2[2]) / 2};
            double m23[3] = {(current.v2[0] + current.v3[0]) / 2, (current.v2[1] + current.v3[1]) / 2, (current.v2[2] + current.v3[2]) / 2};
            double m31[3] = {(current.v3[0] + current.v1[0]) / 2, (current.v3[1] + current.v1[1]) / 2, (current.v3[2] + current.v1[2]) / 2};
            
            // 将中点投影到单位球面
            normalize_vector(&m12[0], &m12[1], &m12[2]);
            normalize_vector(&m23[0], &m23[1], &m23[2]);
            normalize_vector(&m31[0], &m31[1], &m31[2]);
            
            // 检查栈空间
            if (stack_top + 4 >= max_tasks) {
                printf("任务栈空间不足！\n");
                break;
            }
            
            // 添加4个子三角形到栈中
            // 注意：添加顺序与递归调用顺序相反，确保处理顺序一致
            memcpy(task_stack[stack_top].v1, m12, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v2, m23, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v3, m31, sizeof(double) * 3);
            task_stack[stack_top].level = current.level - 1;
            stack_top++;
            
            memcpy(task_stack[stack_top].v1, current.v3, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v2, m31, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v3, m23, sizeof(double) * 3);
            task_stack[stack_top].level = current.level - 1;
            stack_top++;
            
            memcpy(task_stack[stack_top].v1, current.v2, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v2, m23, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v3, m12, sizeof(double) * 3);
            task_stack[stack_top].level = current.level - 1;
            stack_top++;
            
            memcpy(task_stack[stack_top].v1, current.v1, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v2, m12, sizeof(double) * 3);
            memcpy(task_stack[stack_top].v3, m31, sizeof(double) * 3);
            task_stack[stack_top].level = current.level - 1;
            stack_top++;
        }
    }
    
    free(task_stack);
}

// 保留原递归函数作为备用（重命名）
void subdivide_triangle_recursive(double v1[3], double v2[3], double v3[3], int level) {
    if (level == 0) {
        // 基础情况：添加三角形
        double grid_radius = 1.05;
        
        // 归一化并缩放到正确半径
        double nv1[3] = {v1[0], v1[1], v1[2]};
        double nv2[3] = {v2[0], v2[1], v2[2]};
        double nv3[3] = {v3[0], v3[1], v3[2]};
        
        normalize_vector(&nv1[0], &nv1[1], &nv1[2]);
        normalize_vector(&nv2[0], &nv2[1], &nv2[2]);
        normalize_vector(&nv3[0], &nv3[1], &nv3[2]);
        
        nv1[0] *= grid_radius; nv1[1] *= grid_radius; nv1[2] *= grid_radius;
        nv2[0] *= grid_radius; nv2[1] *= grid_radius; nv2[2] *= grid_radius;
        nv3[0] *= grid_radius; nv3[1] *= grid_radius; nv3[2] *= grid_radius;
        
        int i1 = add_vertex_xyz(nv1[0], nv1[1], nv1[2]);
        int i2 = add_vertex_xyz(nv2[0], nv2[1], nv2[2]);
        int i3 = add_vertex_xyz(nv3[0], nv3[1], nv3[2]);
        
        if (i1 < 0 || i2 < 0 || i3 < 0) return;
        
        // 检查是否需要扩展面内存
        if (grid_mesh.face_count >= grid_mesh.max_faces) {
            if (!expand_grid_mesh()) {
                printf("无法扩展面内存！\n");
                return;
            }
        }
        
        grid_mesh.faces[grid_mesh.face_count][0] = i1;
        grid_mesh.faces[grid_mesh.face_count][1] = i2;
        grid_mesh.faces[grid_mesh.face_count][2] = i3;
        grid_mesh.face_count++;
        
    } else {
        // 递归情况：计算边的中点并投影到球面
        double m12[3] = {(v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2, (v1[2] + v2[2]) / 2};
        double m23[3] = {(v2[0] + v3[0]) / 2, (v2[1] + v3[1]) / 2, (v2[2] + v3[2]) / 2};
        double m31[3] = {(v3[0] + v1[0]) / 2, (v3[1] + v1[1]) / 2, (v3[2] + v1[2]) / 2};
        
        // 将中点投影到单位球面
        normalize_vector(&m12[0], &m12[1], &m12[2]);
        normalize_vector(&m23[0], &m23[1], &m23[2]);
        normalize_vector(&m31[0], &m31[1], &m31[2]);
        
        // 递归细分4个子三角形
        subdivide_triangle_recursive(v1, m12, m31, level - 1);
        subdivide_triangle_recursive(v2, m23, m12, level - 1);
        subdivide_triangle_recursive(v3, m31, m23, level - 1);
        subdivide_triangle_recursive(m12, m23, m31, level - 1);
    }
}

// 简单三角面添加函数（保留用于线框）
void add_simple_triangle(double v1_lon, double v1_lat, double v2_lon, double v2_lat, double v3_lon, double v3_lat) {
    int i1 = add_vertex(v1_lon, v1_lat);
    int i2 = add_vertex(v2_lon, v2_lat);
    int i3 = add_vertex(v3_lon, v3_lat);
    
    if (i1 < 0 || i2 < 0 || i3 < 0) return; // 内存分配失败
    
    // 检查是否需要扩展面内存
    if (grid_mesh.face_count >= grid_mesh.max_faces) {
        if (!expand_grid_mesh()) {
            printf("无法扩展面内存！\n");
            return;
        }
    }
    
    grid_mesh.faces[grid_mesh.face_count][0] = i1;
    grid_mesh.faces[grid_mesh.face_count][1] = i2;
    grid_mesh.faces[grid_mesh.face_count][2] = i3;
    grid_mesh.face_count++;
}

// 输出OOGL格式的网格文件
void write_oogl_grid(const char* filename) {
    char path[200];
    sprintf(path, "%s%s.oogl", FILEPATH, filename);
    
    FILE *fp = fopen(path, "w");
    if (!fp) {
        printf("无法创建文件: %s\n", path);
        return;
    }
    
    // OOGL文件头
    fprintf(fp, "# Grid mesh generated from icosahedral subdivision\n");
    fprintf(fp, "# SaVi geomview format\n");
    fprintf(fp, "appearance {\n");
    fprintf(fp, "    material { diffuse 0.3 0.9 0.3 alpha 0.8 }\n");
    fprintf(fp, "    linewidth 1\n");
    fprintf(fp, "    shading flat\n");
    fprintf(fp, "    transparent\n");
    fprintf(fp, "    +edge\n");
    fprintf(fp, "}\n");
    fprintf(fp, "OFF\n");
    fprintf(fp, "%d %d %d\n", grid_mesh.vertex_count, grid_mesh.face_count, 0);
    
    // 输出顶点坐标
    for (int i = 0; i < grid_mesh.vertex_count; i++) {
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[i][0], 
                grid_mesh.vertices[i][1], 
                grid_mesh.vertices[i][2]);
    }
    
    // 输出三角面和四叉树编码
    for (int i = 0; i < grid_mesh.face_count; i++) {
        fprintf(fp, "3 %d %d %d", 
                grid_mesh.faces[i][0], 
                grid_mesh.faces[i][1], 
                grid_mesh.faces[i][2]);
        
        // 添加四叉树编码作为注释
        if (grid_mesh.face_codes && i < grid_mesh.face_count) {
            fprintf(fp, " # %s", grid_mesh.face_codes[i].code_string);
        }
        fprintf(fp, "\n");
    }
    
    fclose(fp);
    printf("生成OOGL格网文件: %s\n", path);
}

// 创建线框格网的OOGL文件
void write_oogl_wireframe(const char* filename) {
    char path[200];
    sprintf(path, "%s%s_wireframe.oogl", FILEPATH, filename);
    
    FILE *fp = fopen(path, "w");
    if (!fp) {
        printf("无法创建文件: %s\n", path);
        return;
    }
    
    // 计算所有边 - 使用动态内存分配避免栈溢出
    int max_edges = grid_mesh.face_count * 3; // 每个面最多3条边
    int (*edges)[2] = malloc(max_edges * sizeof(int[2]));
    if (!edges) {
        printf("无法分配边数组内存！\n");
        fclose(fp);
        return;
    }
    int edge_count = 0;
    
    for (int i = 0; i < grid_mesh.face_count; i++) {
        for (int j = 0; j < 3; j++) {
            int v1 = grid_mesh.faces[i][j];
            int v2 = grid_mesh.faces[i][(j+1)%3];
            
            // 确保边的顶点按升序排列，避免重复边
            if (v1 > v2) {
                int temp = v1; v1 = v2; v2 = temp;
            }
            
            // 检查边是否已存在
            int exists = 0;
            for (int k = 0; k < edge_count; k++) {
                if (edges[k][0] == v1 && edges[k][1] == v2) {
                    exists = 1;
                    break;
                }
            }
            
            if (!exists) {
                edges[edge_count][0] = v1;
                edges[edge_count][1] = v2;
                edge_count++;
            }
        }
    }
    
    // 输出SKEL格式（线框）
    fprintf(fp, "# Grid wireframe mesh\n");
    fprintf(fp, "appearance {\n");
    fprintf(fp, "    material { diffuse 0.8 0.8 0.2 alpha 0.9 }\n");
    fprintf(fp, "    linewidth 3\n");
    fprintf(fp, "}\n");
    fprintf(fp, "SKEL\n");
    fprintf(fp, "%d %d\n", grid_mesh.vertex_count, edge_count);
    
    // 输出所有顶点坐标
    for (int i = 0; i < grid_mesh.vertex_count; i++) {
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[i][0], 
                grid_mesh.vertices[i][1], 
                grid_mesh.vertices[i][2]);
    }
    
    // 输出边（顶点索引）
    for (int i = 0; i < edge_count; i++) {
        fprintf(fp, "2 %d %d\n", edges[i][0], edges[i][1]);
    }
    
    fclose(fp);
    free(edges);  // 释放边数组内存
    printf("生成OOGL线框文件: %s\n", path);
}



// 生成二十面体格网
void generate_icosahedral_grid(int subdivision_level) {
    // 对每个二十面体的面进行细分
    for (int face = 0; face < 20; face++) {
        // 获取三角形的三个顶点
        double v1[3] = {
            icosahedron_vertices[icosahedron_faces[face][0]][0],
            icosahedron_vertices[icosahedron_faces[face][0]][1],
            icosahedron_vertices[icosahedron_faces[face][0]][2]
        };
        double v2[3] = {
            icosahedron_vertices[icosahedron_faces[face][1]][0],
            icosahedron_vertices[icosahedron_faces[face][1]][1],
            icosahedron_vertices[icosahedron_faces[face][1]][2]
        };
        double v3[3] = {
            icosahedron_vertices[icosahedron_faces[face][2]][0],
            icosahedron_vertices[icosahedron_faces[face][2]][1],
            icosahedron_vertices[icosahedron_faces[face][2]][2]
        };
        
        // 使用迭代细分这个三角形（避免栈溢出）
        subdivide_triangle_iterative(v1, v2, v3, subdivision_level);
    }
}

// 估算所需内存大小
void estimate_memory_requirements(int level, int *vertices, int *faces) {
    // 标准二十面体细分：每个级别将每个三角形分成4个
    int base_faces = 20;
    
    // 计算细分后的面数：20 * 4^level
    *faces = base_faces;
    for (int i = 0; i < level; i++) {
        *faces *= 4;
    }
    
    // 顶点数的估算（欧拉公式 V - E + F = 2，对于球面网格 E ≈ 3V/2）
    // 因此 V ≈ F/2 + 2，但由于顶点共享，实际更少
    *vertices = *faces / 2 + 10;
    
    // 添加安全边际
    *vertices = (int)(*vertices * 1.2);
    *faces = (int)(*faces * 1.1);
}

int main(int argc, char* argv[])
{
    int n;
    printf("请输入划分级数：");
    scanf("%d", &n);
    
    // 估算并初始化内存
    int estimated_vertices, estimated_faces;
    estimate_memory_requirements(n, &estimated_vertices, &estimated_faces);
    
    printf("估算内存需求：顶点 %d，面 %d\n", estimated_vertices, estimated_faces);
    
    if (!init_grid_mesh(estimated_vertices, estimated_faces)) {
        printf("内存初始化失败！\n");
        return 1;
    }
    
    printf("正在生成%d级二十面体格网...\n", n);
    
    // 设置格网级别
    grid_mesh.grid_level = n;
    
    // 生成二十面体格网
    generate_icosahedral_grid(n);
    
    // 分配四叉树编码
    printf("分配四叉树编码...\n");
    assign_quadtree_codes_to_faces(n);
    
    printf("生成完成！\n");
    printf("实际使用：顶点数 %d，三角面数 %d\n", grid_mesh.vertex_count, grid_mesh.face_count);
    printf("内存效率：顶点 %.1f%%，面 %.1f%%\n", 
           100.0 * grid_mesh.vertex_count / grid_mesh.max_vertices,
           100.0 * grid_mesh.face_count / grid_mesh.max_faces);
    
    // 生成文件名
    char filename[50];
    sprintf(filename, "icosahedral_grid_level_%d", n);
    
    // 输出OOGL格式文件
    write_oogl_grid(filename);
    write_oogl_wireframe(filename);
    
    printf("\n格网文件已生成到 %s 目录\n", FILEPATH);
    printf("实体格网文件：%s.oogl\n", filename);
    printf("线框格网文件：%s_wireframe.oogl\n", filename);
    
    // 释放内存
    free_grid_mesh();
    
    return 0;
}

// 四叉树编码实现函数

/*
 * quadtree_encode_face
 * 为格网面分配四叉树编码
 */
void quadtree_encode_face(QuadtreeCode *code, int base_face_id, int level, int face_index_in_level) {
    if (!code || base_face_id < 0 || base_face_id >= 20 || level < 0) {
        return;
    }
    
    code->base_face_id = base_face_id;
    code->level = level;
    code->path_code = 0;
    
    // 计算路径编码：将face_index_in_level转换为四叉树路径
    if (level > 0) {
        unsigned int path = 0;
        int temp_index = face_index_in_level;
        
        // 从最高级别开始，逐级计算四叉树分支
        for (int i = level - 1; i >= 0; i--) {
            int faces_at_level = 1;
            for (int j = 0; j < i; j++) {
                faces_at_level *= 4;
            }
            
            int branch = temp_index / faces_at_level;
            path |= (branch & 0x3) << (i * 2);  // 每个分支用2位表示
            temp_index %= faces_at_level;
        }
        
        code->path_code = path;
    }
    
    // 生成人类可读的编码字符串
    quadtree_code_to_string(code, code->code_string);
}

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
 * assign_quadtree_codes_to_faces
 * 为所有格网面分配四叉树编码
 */
void assign_quadtree_codes_to_faces(int level) {
    if (grid_mesh.face_count == 0) {
        printf("没有格网面需要编码\n");
        return;
    }
    
    int faces_per_base = 1;
    
    // 计算每个基础面在当前级别的面数
    for (int i = 0; i < level; i++) {
        faces_per_base *= 4;
    }
    
    printf("分配四叉树编码: 级别=%d, 每个基础面的格网数=%d\n", 
           level, faces_per_base);
    
    // 为每个格网面分配编码
    for (int i = 0; i < grid_mesh.face_count; i++) {
        QuadtreeCode *code = &grid_mesh.face_codes[i];
        
        // 计算此格网属于哪个基础面
        int base_face_id = i / faces_per_base;
        int face_index_in_level = i % faces_per_base;
        
        // 确保基础面ID在有效范围内
        if (base_face_id >= 20) {
            base_face_id = base_face_id % 20;
        }
        
        quadtree_encode_face(code, base_face_id, level, face_index_in_level);
        
        // 调试输出前几个编码
        if (i < 10) {
            printf("面 %d: %s (基础面=%d, 级别=%d, 路径=0x%x)\n", 
                   i, code->code_string, 
                   code->base_face_id, 
                   code->level, 
                   code->path_code);
        }
    }
    
    printf("四叉树编码分配完成，共 %d 个格网面\n", grid_mesh.face_count);
}

