#!/bin/bash


echo "=== SaVi 格网可视化测试 ==="

echo "1. 生成格网文件..."

cd /home/dreamcat/Desktop/mini-savi
rm -f ./mini-savi/*.oogl

# 生成二十面体格网
echo "生成二十面体格网 (level 1)..."
echo "1" | ./grid_calc
echo "生成二十面体格网 (level 2)..."
echo "2" | ./grid_calc
echo "生成二十面体格网 (level 3)..."
echo "3" | ./grid_calc
echo "生成二十面体格网 (level 4)..."
echo "4" | ./grid_calc
echo "生成二十面体格网 (level 5)..."
echo "5" | ./grid_calc

# 生成经纬度格网
echo "生成经纬度格网 (36x72)..."
if [ -f ./latlon_grid_calc ]; then
    echo -e "36\n72" | ./latlon_grid_calc
else
    echo "编译 latlon_grid_calc..."
    gcc -o latlon_grid_calc latlon_grid_calc.c -lm
    echo -e "36\n72" | ./latlon_grid_calc
fi

echo "生成的格网文件："
ls -la mini-savi/*.oogl



echo "启动 router-host.py 服务..."
# python3 router-host.py & ROUTER_PID=$!

sleep 1  # 等待服务启动

# 启动geomview和savi
echo "启动geomview和SaVi..."
geomview -run ./savi & GEOMVIEW_PID=$!

echo "SaVi已启动，请在界面中测试格网显示功能"
echo "按Ctrl+C停止所有服务"

trap 'echo "正在停止服务..."; kill $GEOMVIEW_PID 2>/dev/null; kill $ROUTER_PID 2>/dev/null; exit' INT
wait
