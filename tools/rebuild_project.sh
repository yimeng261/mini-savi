#!/bin/bash

# SaVi 项目完整重构建脚本
# 包含格网可视化功能的完整构建过程

echo "======================================"
echo "    SaVi 项目完整重构建脚本"
echo "    包含格网可视化功能"
echo "======================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 错误处理函数
error_exit() {
    echo -e "${RED}错误: $1${NC}" >&2
    exit 1
}

success_msg() {
    echo -e "${GREEN}✓ $1${NC}"
}

warning_msg() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

info_msg() {
    echo -e "${BLUE}ℹ $1${NC}"
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 检查是否在正确的目录
if [[ ! -f "savi" ]] || [[ ! -d "src" ]] || [[ ! -d "tcl" ]]; then
    error_exit "请在 mini-savi 项目根目录下运行此脚本"
fi

echo ""
info_msg "开始重构建过程..."
echo ""

# 步骤1: 清理旧的构建文件
echo "1. 清理旧的构建文件..."
if make clean; then
    success_msg "清理完成"
else
    error_exit "清理失败"
fi

# 步骤2: 重新编译格网计算程序
echo ""
echo "2. 编译格网计算程序..."
if gcc -o tools/grid_calc tools/grid_calc.c -lm; then
    success_msg "格网计算程序编译完成"
else
    error_exit "格网计算程序编译失败"
fi

# 步骤3: 生成格网文件
echo ""
echo "3. 生成格网文件..."

# 创建输出目录
mkdir -p generated/grids

# 生成不同级别的格网
for level in 0 1 2; do
    info_msg "生成 $level 级格网..."
    if echo "$level" | ./tools/grid_calc > /dev/null 2>&1; then
        success_msg "$level 级格网生成完成"
    else
        warning_msg "$level 级格网生成失败，但继续构建"
    fi
done

# 步骤4: 重新生成TCL索引
echo ""
echo "4. 重新生成TCL自动加载索引..."
cd tcl

# 首先创建包含grid.tcl的mkindex.tcl文件
echo "auto_mkindex . init.tcl main.tcl utils.tcl load.tcl run_mininet.tcl save.tcl coverage_frames.tcl coverage.tcl coverage_size.tcl edit.tcl fisheye.tcl params.tcl geomview.tcl random.tcl about.tcl oe.tcl constellations.tcl no_frames.tcl snapshot.tcl rosette.tcl star.tcl empty.tcl sunlight.tcl equator.tcl details.tcl helpfile.tcl load_url_tle.tcl grid.tcl" > mkindex.tcl

if tclsh mkindex.tcl; then
    success_msg "TCL索引生成完成"
else
    error_exit "TCL索引生成失败"
fi
cd ..

# 验证grid.tcl是否在索引中
if grep -q "grid(" tcl/tclIndex; then
    success_msg "格网函数已添加到TCL索引"
else
    error_exit "格网函数未添加到TCL索引"
fi

# 步骤5: 编译SaVi主程序
echo ""
echo "5. 编译SaVi主程序..."
if make ARCH=linux; then
    success_msg "SaVi主程序编译完成"
else
    error_exit "SaVi主程序编译失败"
fi

# 步骤6: 验证构建结果
echo ""
echo "6. 验证构建结果..."

# 检查关键文件
files_to_check=(
    "./savi"
    "./tools/grid_calc"
    "./tcl/grid.tcl"
    "./tcl/tclIndex"
    "./generated/grids/icosahedral_grid_level_0.oogl"
    "./generated/grids/icosahedral_grid_level_1.oogl"
    "./generated/grids/icosahedral_grid_level_2.oogl"
)

all_files_ok=true
for file in "${files_to_check[@]}"; do
    if [[ -f "$file" ]]; then
        success_msg "$file 存在"
    else
        warning_msg "$file 不存在"
        all_files_ok=false
    fi
done

# 检查TCL函数
grid_functions=("grid(on)" "grid(off)" "grid(build)" "grid_wireframe(on)" "grid_wireframe(off)")
for func in "${grid_functions[@]}"; do
    if grep -q "$func" tcl/tclIndex; then
        success_msg "函数 $func 在索引中"
    else
        warning_msg "函数 $func 不在索引中"
        all_files_ok=false
    fi
done

echo ""
echo "======================================"
if [[ "$all_files_ok" == true ]]; then
    success_msg "构建完成！所有组件都已就绪"
    echo ""
    echo "🎉 项目重构建成功！"
    echo ""
    echo "📋 使用说明："
    echo "1. 启动SaVi:"
    echo "   geomview -run ./savi"
    echo ""
    echo "2. 或者非geomview模式:"
    echo "   ./savi"
    echo ""
    echo "3. 测试格网功能:"
    echo "   - 加载一个星座配置（如 Iridium-66）"
    echo "   - 在 Rendering 菜单中勾选:"
    echo "     • 'Show grid solid' - 显示实体格网"
    echo "     • 'Show grid wireframe' - 显示线框格网"
    echo "   - 点击 'Grid control...' 打开控制对话框"
    echo ""
    echo "📊 格网级别说明:"
    echo "   • 级别 0: 20个三角面（基础二十面体）"
    echo "   • 级别 1: 80个三角面"
    echo "   • 级别 2: 320个三角面"
    echo "   • 级别越高，格网越密集"
    echo ""
    echo "🔧 调试信息:"
    echo "   启动时会在终端显示详细的调试信息"
    echo "   包括格网初始化和显示状态"
else
    error_exit "构建过程中发现问题，请检查上述警告信息"
fi
echo "======================================"

# 步骤7: 创建快速测试脚本
echo ""
info_msg "创建快速测试脚本..."

cat > tools/quick_test.sh << 'EOF'
#!/bin/bash
echo "快速格网测试..."
echo "检查格网文件:"
ls -la generated/grids/icosahedral_grid_level_*.oogl
echo ""
echo "检查坐标范围（应该在6000-7000km范围内）:"
head -15 generated/grids/icosahedral_grid_level_0.oogl | tail -5
echo ""
echo "启动SaVi进行测试:"
echo "geomview -run ./savi"
EOF

chmod +x tools/quick_test.sh
success_msg "创建了 tools/quick_test.sh 快速测试脚本"

echo ""
success_msg "重构建脚本执行完成！"
