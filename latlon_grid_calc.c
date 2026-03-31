// latlon_grid_calc.c : 经纬度格网生成程序
// 按照经度和纬度等间隔划分地球表面成规则矩形格网
#define _USE_MATH_DEFINES
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <errno.h>

#define DEFAULT_FILEPATH "./mini-savi/"

// 格网编码结构（与经纬度对应）
typedef struct {
    int lat_idx;    // 纬度索引 (0 到 lat_divisions-1)
    int lon_idx;    // 经度索引 (0 到 lon_divisions-1)
    char code_string[64]; // 编码字符串 "LAT##_LON###"
} LatLonCode;

// 存储格网顶点和面的结构
typedef struct {
    double (*vertices)[3];      // 顶点坐标 (x, y, z)
    int (*faces)[4];            // 矩形面的四个顶点索引
    LatLonCode *face_codes;     // 每个面的经纬度编码
    int vertex_count;
    int face_count;
    int max_vertices;
    int max_faces;
    int lat_divisions;          // 纬度划分数
    int lon_divisions;          // 经度划分数
} LatLonGridMesh;

LatLonGridMesh grid_mesh = {0};
static char output_dir[256] = DEFAULT_FILEPATH;

void write_grid_metadata(const char *base_filename);
int parse_args(int argc, char *argv[], int *lat_divisions, int *lon_divisions);
void print_usage(const char *progname);
unsigned int ensure_output_dir_exists(void);
unsigned int validate_rectangle_count(int lat_divisions, int lon_divisions);
unsigned int validate_unique_latlon_codes(void);
unsigned int validate_no_degenerate_faces(void);
unsigned int run_grid_validations(int lat_divisions, int lon_divisions);

// 初始化网格内存
int init_grid_mesh(int max_vertices, int max_faces) {
    grid_mesh.vertices = malloc(max_vertices * sizeof(double[3]));
    grid_mesh.faces = malloc(max_faces * sizeof(int[4]));
    grid_mesh.face_codes = malloc(max_faces * sizeof(LatLonCode));
    
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
    
    return 1;
}

// 释放网格内存
void free_grid_mesh() {
    if (grid_mesh.vertices) free(grid_mesh.vertices);
    if (grid_mesh.faces) free(grid_mesh.faces);
    if (grid_mesh.face_codes) free(grid_mesh.face_codes);
    grid_mesh.vertices = NULL;
    grid_mesh.faces = NULL;
    grid_mesh.face_codes = NULL;
}

// 将经纬度转换为笛卡尔坐标（单位球面）
void latlon_to_xyz(double lat_deg, double lon_deg, double *x, double *y, double *z) {
    double lat_rad = lat_deg * M_PI / 180.0;
    double lon_rad = lon_deg * M_PI / 180.0;
    
    *x = cos(lat_rad) * cos(lon_rad);
    *y = cos(lat_rad) * sin(lon_rad);
    *z = sin(lat_rad);
}

// 添加顶点（如果不存在则添加，返回索引）
int add_vertex(double x, double y, double z) {
    // 检查是否已存在（容差1e-9）
    for (int i = 0; i < grid_mesh.vertex_count; i++) {
        double dx = grid_mesh.vertices[i][0] - x;
        double dy = grid_mesh.vertices[i][1] - y;
        double dz = grid_mesh.vertices[i][2] - z;
        if (dx*dx + dy*dy + dz*dz < 1e-18) {
            return i; // 顶点已存在
        }
    }
    
    // 添加新顶点
    if (grid_mesh.vertex_count >= grid_mesh.max_vertices) {
        printf("警告：顶点数量超过最大值！\n");
        return -1;
    }
    
    int idx = grid_mesh.vertex_count;
    grid_mesh.vertices[idx][0] = x;
    grid_mesh.vertices[idx][1] = y;
    grid_mesh.vertices[idx][2] = z;
    grid_mesh.vertex_count++;
    
    return idx;
}

// 生成经纬度编码
void generate_latlon_code(int lat_idx, int lon_idx, LatLonCode *code) {
    code->lat_idx = lat_idx;
    code->lon_idx = lon_idx;
    snprintf(code->code_string, 64, "LAT%03d_LON%03d", lat_idx, lon_idx);
}

// 生成经纬度格网
// lat_divisions: 纬度方向划分数（-90到90度之间）
// lon_divisions: 经度方向划分数（-180到180度之间）
void generate_latlon_grid(int lat_divisions, int lon_divisions) {
    grid_mesh.lat_divisions = lat_divisions;
    grid_mesh.lon_divisions = lon_divisions;
    
    // 纬度间隔
    double lat_step = 180.0 / lat_divisions;  // 从-90到90度
    // 经度间隔
    double lon_step = 360.0 / lon_divisions;  // 从-180到180度
    
    printf("生成经纬度格网：\n");
    printf("  纬度划分数: %d (间隔: %.2f度)\n", lat_divisions, lat_step);
    printf("  经度划分数: %d (间隔: %.2f度)\n", lon_divisions, lon_step);
    printf("  总格网数: %d\n", lat_divisions * lon_divisions);
    
    // 为每个格网矩形生成面
    for (int lat_idx = 0; lat_idx < lat_divisions; lat_idx++) {
        for (int lon_idx = 0; lon_idx < lon_divisions; lon_idx++) {
            // 计算格网的四个角的经纬度
            double lat1 = -90.0 + lat_idx * lat_step;
            double lat2 = -90.0 + (lat_idx + 1) * lat_step;
            double lon1 = -180.0 + lon_idx * lon_step;
            double lon2 = -180.0 + (lon_idx + 1) * lon_step;
            
            // 转换为笛卡尔坐标
            double x1, y1, z1, x2, y2, z2, x3, y3, z3, x4, y4, z4;
            latlon_to_xyz(lat1, lon1, &x1, &y1, &z1);  // 左下
            latlon_to_xyz(lat2, lon1, &x2, &y2, &z2);  // 左上
            latlon_to_xyz(lat2, lon2, &x3, &y3, &z3);  // 右上
            latlon_to_xyz(lat1, lon2, &x4, &y4, &z4);  // 右下
            
            // 添加四个顶点
            int v1 = add_vertex(x1, y1, z1);
            int v2 = add_vertex(x2, y2, z2);
            int v3 = add_vertex(x3, y3, z3);
            int v4 = add_vertex(x4, y4, z4);
            
            if (v1 < 0 || v2 < 0 || v3 < 0 || v4 < 0) {
                printf("错误：无法添加顶点！\n");
                continue;
            }
            
            // 添加矩形面（存储为四个顶点，后续转换为两个三角形）
            if (grid_mesh.face_count >= grid_mesh.max_faces) {
                printf("警告：面数量超过最大值！\n");
                break;
            }
            
            grid_mesh.faces[grid_mesh.face_count][0] = v1;
            grid_mesh.faces[grid_mesh.face_count][1] = v2;
            grid_mesh.faces[grid_mesh.face_count][2] = v3;
            grid_mesh.faces[grid_mesh.face_count][3] = v4;
            
            // 生成编码
            generate_latlon_code(lat_idx, lon_idx, &grid_mesh.face_codes[grid_mesh.face_count]);
            
            grid_mesh.face_count++;
        }
    }
}

// 输出OOGL格式文件（将矩形转换为三角形）
void write_oogl_grid(const char *base_filename) {
    char path[256];
    snprintf(path, sizeof(path), "%s%s.oogl", output_dir, base_filename);
    
    FILE *fp = fopen(path, "w");
    if (!fp) {
        printf("无法创建文件: %s\n", path);
        return;
    }
    
    // OOGL文件头
    fprintf(fp, "appearance { +edge }\n");
    fprintf(fp, "COFF\n");
    
    // 将每个矩形分成两个三角形
    int triangle_count = grid_mesh.face_count * 2;
    
    // 顶点数 面数 边数
    fprintf(fp, "%d %d 0\n", grid_mesh.vertex_count, triangle_count);
    
    // 输出所有顶点坐标（放大1.05倍用于显示）
    for (int i = 0; i < grid_mesh.vertex_count; i++) {
        fprintf(fp, "%.6f %.6f %.6f 1.0 1.0 1.0 1.0\n", 
                grid_mesh.vertices[i][0] * 1.05, 
                grid_mesh.vertices[i][1] * 1.05, 
                grid_mesh.vertices[i][2] * 1.05);
    }
    
    // 输出三角形面（每个矩形分成两个三角形）
    for (int i = 0; i < grid_mesh.face_count; i++) {
        int v1 = grid_mesh.faces[i][0];
        int v2 = grid_mesh.faces[i][1];
        int v3 = grid_mesh.faces[i][2];
        int v4 = grid_mesh.faces[i][3];
        
        // 第一个三角形 (v1, v2, v3) - 带编码注释，添加T1后缀
        fprintf(fp, "3 %d %d %d # %s_T1\n", v1, v2, v3, 
                grid_mesh.face_codes[i].code_string);
        
        // 第二个三角形 (v1, v3, v4) - 带编码注释，添加T2后缀
        fprintf(fp, "3 %d %d %d # %s_T2\n", v1, v3, v4, 
                grid_mesh.face_codes[i].code_string);
    }
    
    fclose(fp);
    printf("生成OOGL格网文件: %s\n", path);
    printf("  顶点数: %d\n", grid_mesh.vertex_count);
    printf("  矩形数: %d\n", grid_mesh.face_count);
    printf("  三角形数: %d\n", triangle_count);
}

// 输出OOGL线框格式
void write_oogl_wireframe(const char *base_filename) {
    char path[256];
    snprintf(path, sizeof(path), "%s%s_wireframe.oogl", output_dir, base_filename);
    
    FILE *fp = fopen(path, "w");
    if (!fp) {
        printf("无法创建文件: %s\n", path);
        return;
    }
    
    // OOGL线框文件头
    fprintf(fp, "VECT\n");
    
    // 统计边的数量（每个矩形有4条边，但边会被共享）
    // 简化处理：每个矩形输出4条边
    int edge_count = grid_mesh.face_count * 4;
    
    // 边的数量 顶点总数 颜色数
    fprintf(fp, "%d %d 0\n", edge_count, edge_count * 2);
    
    // 每条边的顶点数（都是2）
    for (int i = 0; i < edge_count; i++) {
        fprintf(fp, "2 ");
        if ((i + 1) % 20 == 0) fprintf(fp, "\n");
    }
    if (edge_count % 20 != 0) fprintf(fp, "\n");
    
    // 每条边的颜色数（都是0，使用默认颜色）
    for (int i = 0; i < edge_count; i++) {
        fprintf(fp, "0 ");
        if ((i + 1) % 20 == 0) fprintf(fp, "\n");
    }
    if (edge_count % 20 != 0) fprintf(fp, "\n");
    
    // 输出边的顶点坐标和索引
    for (int i = 0; i < grid_mesh.face_count; i++) {
        int v1 = grid_mesh.faces[i][0];
        int v2 = grid_mesh.faces[i][1];
        int v3 = grid_mesh.faces[i][2];
        int v4 = grid_mesh.faces[i][3];
        
        // 四条边: v1-v2, v2-v3, v3-v4, v4-v1
        // 边1: v1-v2
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v1][0] * 1.05,
                grid_mesh.vertices[v1][1] * 1.05,
                grid_mesh.vertices[v1][2] * 1.05);
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v2][0] * 1.05,
                grid_mesh.vertices[v2][1] * 1.05,
                grid_mesh.vertices[v2][2] * 1.05);
        
        // 边2: v2-v3
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v2][0] * 1.05,
                grid_mesh.vertices[v2][1] * 1.05,
                grid_mesh.vertices[v2][2] * 1.05);
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v3][0] * 1.05,
                grid_mesh.vertices[v3][1] * 1.05,
                grid_mesh.vertices[v3][2] * 1.05);
        
        // 边3: v3-v4
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v3][0] * 1.05,
                grid_mesh.vertices[v3][1] * 1.05,
                grid_mesh.vertices[v3][2] * 1.05);
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v4][0] * 1.05,
                grid_mesh.vertices[v4][1] * 1.05,
                grid_mesh.vertices[v4][2] * 1.05);
        
        // 边4: v4-v1
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v4][0] * 1.05,
                grid_mesh.vertices[v4][1] * 1.05,
                grid_mesh.vertices[v4][2] * 1.05);
        fprintf(fp, "%.6f %.6f %.6f\n", 
                grid_mesh.vertices[v1][0] * 1.05,
                grid_mesh.vertices[v1][1] * 1.05,
                grid_mesh.vertices[v1][2] * 1.05);
    }
    
    fclose(fp);
    printf("生成OOGL线框文件: %s\n", path);
}

void write_grid_metadata(const char *base_filename) {
    char path[256];
    FILE *fp;

    snprintf(path, sizeof(path), "%s%s.json", output_dir, base_filename);
    fp = fopen(path, "w");
    if (!fp) {
        printf("无法创建元数据文件: %s\n", path);
        return;
    }

    fprintf(fp, "{\n");
    fprintf(fp, "  \"grid_type\": \"latlon\",\n");
    fprintf(fp, "  \"lat_divisions\": %d,\n", grid_mesh.lat_divisions);
    fprintf(fp, "  \"lon_divisions\": %d,\n", grid_mesh.lon_divisions);
    fprintf(fp, "  \"vertex_count\": %d,\n", grid_mesh.vertex_count);
    fprintf(fp, "  \"rectangle_count\": %d,\n", grid_mesh.face_count);
    fprintf(fp, "  \"triangle_count\": %d,\n", grid_mesh.face_count * 2);
    fprintf(fp, "  \"display_radius\": 1.05,\n");
    fprintf(fp, "  \"solid_file\": \"%s.oogl\",\n", base_filename);
    fprintf(fp, "  \"wireframe_file\": \"%s_wireframe.oogl\"\n", base_filename);
    fprintf(fp, "}\n");

    fclose(fp);
    printf("生成元数据文件: %s\n", path);
}

int main(int argc, char* argv[]) {
    int lat_divisions, lon_divisions;
    if (!parse_args(argc, argv, &lat_divisions, &lon_divisions)) {
        return 1;
    }
    if (!ensure_output_dir_exists()) {
        return 1;
    }
    
    if (lat_divisions < 1 || lat_divisions > 180 || 
        lon_divisions < 1 || lon_divisions > 360) {
        printf("错误：划分数超出有效范围！\n");
        printf("  纬度划分数应在 1-180 之间\n");
        printf("  经度划分数应在 1-360 之间\n");
        return 1;
    }
    
    // 估算内存需求
    // 顶点数约为 (lat_divisions+1) * (lon_divisions+1)
    // 面数为 lat_divisions * lon_divisions
    int estimated_vertices = (lat_divisions + 1) * (lon_divisions + 1) + 100;
    int estimated_faces = lat_divisions * lon_divisions + 100;
    
    printf("\n估算内存需求：\n");
    printf("  顶点数: 约 %d\n", estimated_vertices);
    printf("  矩形数: %d\n", lat_divisions * lon_divisions);
    printf("  三角形数: %d\n", lat_divisions * lon_divisions * 2);
    
    if (!init_grid_mesh(estimated_vertices, estimated_faces)) {
        printf("内存初始化失败！\n");
        return 1;
    }
    
    printf("\n正在生成格网...\n");
    generate_latlon_grid(lat_divisions, lon_divisions);
    if (!run_grid_validations(lat_divisions, lon_divisions)) {
        free_grid_mesh();
        return 1;
    }
    
    printf("\n生成完成！\n");
    printf("实际使用：\n");
    printf("  顶点数: %d\n", grid_mesh.vertex_count);
    printf("  矩形数: %d\n", grid_mesh.face_count);
    printf("  三角形数: %d\n", grid_mesh.face_count * 2);
    
    // 生成文件名
    char filename[128];
    snprintf(filename, sizeof(filename), "latlon_grid_%dx%d", 
             lat_divisions, lon_divisions);
    
    // 输出OOGL格式文件
    write_oogl_grid(filename);
    write_oogl_wireframe(filename);
    write_grid_metadata(filename);
    
    // 清理内存
    free_grid_mesh();
    
    printf("\n完成！文件保存在 %s 目录下\n", output_dir);
    printf("  - %s.oogl (格网文件)\n", filename);
    printf("  - %s_wireframe.oogl (线框文件)\n", filename);
    printf("  - %s.json (元数据文件)\n", filename);
    
    return 0;
}

int parse_args(int argc, char *argv[], int *lat_divisions, int *lon_divisions) {
    int lat_set = 0;
    int lon_set = 0;

    for (int i = 1; i < argc; i++) {
        if ((strcmp(argv[i], "--lat") == 0 || strcmp(argv[i], "-a") == 0) &&
            i + 1 < argc) {
            *lat_divisions = atoi(argv[++i]);
            lat_set = 1;
        } else if ((strcmp(argv[i], "--lon") == 0 || strcmp(argv[i], "-o") == 0) &&
                   i + 1 < argc) {
            *lon_divisions = atoi(argv[++i]);
            lon_set = 1;
        } else if (strcmp(argv[i], "--output-dir") == 0 && i + 1 < argc) {
            snprintf(output_dir, sizeof(output_dir), "%s", argv[++i]);
            if (output_dir[strlen(output_dir) - 1] != '/') {
                strncat(output_dir, "/", sizeof(output_dir) - strlen(output_dir) - 1);
            }
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (!lat_set) {
            *lat_divisions = atoi(argv[i]);
            lat_set = 1;
        } else if (!lon_set) {
            *lon_divisions = atoi(argv[i]);
            lon_set = 1;
        } else {
            fprintf(stderr, "Unknown argument: %s\n", argv[i]);
            print_usage(argv[0]);
            return 0;
        }
    }

    if (!lat_set) {
        printf("请输入纬度划分数（建议: 18, 36, 72等）: ");
        scanf("%d", lat_divisions);
    }
    if (!lon_set) {
        printf("请输入经度划分数（建议: 36, 72, 144等）: ");
        scanf("%d", lon_divisions);
    }

    if (*lat_divisions < 1 || *lat_divisions > 180 ||
        *lon_divisions < 1 || *lon_divisions > 360) {
        fprintf(stderr, "错误：划分数超出有效范围！\n");
        return 0;
    }

    return 1;
}

void print_usage(const char *progname) {
    printf("Usage: %s [--lat N] [--lon N] [--output-dir DIR]\n", progname);
}

unsigned int ensure_output_dir_exists(void) {
    struct stat st;

    if (stat(output_dir, &st) == 0) {
        return S_ISDIR(st.st_mode);
    }

    if (mkdir(output_dir, 0755) == 0) {
        return 1;
    }

    fprintf(stderr, "无法创建输出目录 %s: %s\n", output_dir, strerror(errno));
    return 0;
}

unsigned int validate_rectangle_count(int lat_divisions, int lon_divisions) {
    int expected_rectangles = lat_divisions * lon_divisions;
    if (grid_mesh.face_count != expected_rectangles) {
        fprintf(stderr, "校验失败：矩形数不匹配，期望 %d，实际 %d\n",
                expected_rectangles, grid_mesh.face_count);
        return 0;
    }

    return 1;
}

unsigned int validate_unique_latlon_codes(void) {
    for (int i = 0; i < grid_mesh.face_count; i++) {
        for (int j = i + 1; j < grid_mesh.face_count; j++) {
            if (strcmp(grid_mesh.face_codes[i].code_string,
                       grid_mesh.face_codes[j].code_string) == 0) {
                fprintf(stderr, "校验失败：发现重复编码 %s\n",
                        grid_mesh.face_codes[i].code_string);
                return 0;
            }
        }
    }

    return 1;
}

unsigned int validate_no_degenerate_faces(void) {
    for (int i = 0; i < grid_mesh.face_count; i++) {
        int quads[4];
        double areas[2] = {0.0, 0.0};

        for (int j = 0; j < 4; j++) {
            quads[j] = grid_mesh.faces[i][j];
        }

        /* Polar caps collapse one edge into a single pole vertex. */
        if (quads[0] == quads[3] || quads[1] == quads[2]) {
            continue;
        }

        for (int tri = 0; tri < 2; tri++) {
            int i1 = quads[0];
            int i2 = tri == 0 ? quads[1] : quads[2];
            int i3 = tri == 0 ? quads[2] : quads[3];
            double ax = grid_mesh.vertices[i2][0] - grid_mesh.vertices[i1][0];
            double ay = grid_mesh.vertices[i2][1] - grid_mesh.vertices[i1][1];
            double az = grid_mesh.vertices[i2][2] - grid_mesh.vertices[i1][2];
            double bx = grid_mesh.vertices[i3][0] - grid_mesh.vertices[i1][0];
            double by = grid_mesh.vertices[i3][1] - grid_mesh.vertices[i1][1];
            double bz = grid_mesh.vertices[i3][2] - grid_mesh.vertices[i1][2];
            double cx = ay * bz - az * by;
            double cy = az * bx - ax * bz;
            double cz = ax * by - ay * bx;
            areas[tri] = cx * cx + cy * cy + cz * cz;
        }

        if (areas[0] < 1e-18 || areas[1] < 1e-18) {
            fprintf(stderr, "校验失败：发现退化面，索引 %d\n", i);
            return 0;
        }
    }

    return 1;
}

unsigned int run_grid_validations(int lat_divisions, int lon_divisions) {
    if (!validate_rectangle_count(lat_divisions, lon_divisions)) {
        return 0;
    }
    if (!validate_unique_latlon_codes()) {
        return 0;
    }
    if (!validate_no_degenerate_faces()) {
        return 0;
    }

    printf("格网校验通过：矩形数、编码唯一性、退化面检查均正常\n");
    return 1;
}
