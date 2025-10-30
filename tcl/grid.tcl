#
######################################################
#
#  Grid visualization for SaVi
#  Added for icosahedral grid display
#
######################################################
#
# grid.tcl
#

# 格网显示相关的全局变量
global grid_flag grid_wireframe_flag grid_level grid_solid_file grid_wireframe_file
global grid_coverage_flag grid_coverage_angle
set grid_flag 0
set grid_wireframe_flag 0
set grid_level 0
set grid_coverage_flag 1
set grid_coverage_angle 8.2

# 格网文件路径
set grid_solid_file ""
set grid_wireframe_file ""

proc grid(on) {} {
    global grid_flag geomview_module grid_solid_file grid_level

    puts stderr "SaVi: grid(on) 被调用，geomview_module=$geomview_module, grid_flag=$grid_flag"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过格网显示"
        return
    }

    set grid_flag 1

    # 确保格网文件已生成
    if {[grid(generate) $grid_level] && $grid_solid_file != ""} {
        puts stderr "SaVi: 开始显示实体格网: $grid_solid_file"
        geomview(begin)
        geomview(puts) "(read geometry {define grid_solid_h < \"$grid_solid_file\"})"
        geomview(puts) "(geometry grid_solid {: grid_solid_h})"
        geomview(end)
        puts stderr "SaVi: loaded grid solid from $grid_solid_file"
    } else {
        puts stderr "SaVi: failed to load grid solid - file not found or generation failed"
        set grid_flag 0
    }
}

proc grid(off) {} {
    global grid_flag geomview_module

    puts stderr "SaVi: grid(off) 被调用，geomview_module=$geomview_module, grid_flag=$grid_flag"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过格网关闭"
        return
    }

    set grid_flag 0

    puts stderr "SaVi: 开始关闭实体格网"
    geomview(begin)
    geomview(puts) "(geometry grid_solid {})"
    geomview(end)
    puts stderr "SaVi: 实体格网已关闭"
}

proc grid_wireframe(on) {} {
    global grid_wireframe_flag geomview_module grid_wireframe_file grid_level

    puts stderr "SaVi: grid_wireframe(on) 被调用，geomview_module=$geomview_module, grid_wireframe_flag=$grid_wireframe_flag"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过线框格网显示"
        return
    }

    set grid_wireframe_flag 1

    # 确保格网文件已生成
    if {[grid(generate) $grid_level] && $grid_wireframe_file != ""} {
        puts stderr "SaVi: 开始显示线框格网: $grid_wireframe_file"
        geomview(begin)
        geomview(puts) "(read geometry {define grid_wireframe_h < \"$grid_wireframe_file\"})"
        geomview(puts) "(geometry grid_wireframe {: grid_wireframe_h})"
        geomview(end)
        puts stderr "SaVi: loaded grid wireframe from $grid_wireframe_file"
    } else {
        puts stderr "SaVi: failed to load grid wireframe - file not found or generation failed"
        set grid_wireframe_flag 0
    }
}

proc grid_wireframe(off) {} {
    global grid_wireframe_flag geomview_module

    puts stderr "SaVi: grid_wireframe(off) 被调用，geomview_module=$geomview_module, grid_wireframe_flag=$grid_wireframe_flag"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过线框格网关闭"
        return
    }

    set grid_wireframe_flag 0

    puts stderr "SaVi: 开始关闭线框格网"
    geomview(begin)
    geomview(puts) "(geometry grid_wireframe {})"
    geomview(end)
    puts stderr "SaVi: 线框格网已关闭"
}

proc grid(generate) {level} {
    global grid_solid_file grid_wireframe_file

    # 设置文件路径
    set grid_solid_file "./mini-savi/icosahedral_grid_level_${level}.oogl"
    set grid_wireframe_file "./mini-savi/icosahedral_grid_level_${level}_wireframe.oogl"

    # 检查文件是否存在，如果不存在则生成
    if {![file exists $grid_solid_file] || ![file exists $grid_wireframe_file]} {
        puts stderr "SaVi: generating grid level $level..."
        
        # 调用格网生成程序
        if {[catch {exec echo "$level" | ./grid_calc} result]} {
            puts stderr "SaVi: error generating grid: $result"
            return 0
        }
        
        puts stderr "SaVi: grid generation completed"
    }

    return 1
}

proc grid(set_level) {level} {
    global grid_level grid_flag grid_wireframe_flag

    # 记住当前显示状态
    set was_grid_on $grid_flag
    set was_wireframe_on $grid_wireframe_flag

    # 先关闭当前显示
    if {$grid_flag == 1} {
        grid(off)
    }
    if {$grid_wireframe_flag == 1} {
        grid_wireframe(off)
    }

    # 设置新级别
    set grid_level $level

    # 生成新的格网文件
    if {[grid(generate) $level]} {
        # 如果之前有显示，重新显示
        if {$was_grid_on == 1} {
            grid(on)
        }
        if {$was_wireframe_on == 1} {
            grid_wireframe(on)
        }
        
        # 重新初始化格网覆盖系统以使用新级别
        global grid_coverage_flag
        if {$grid_coverage_flag == 1} {
            puts stderr "SaVi: 级别变更，重新初始化格网覆盖系统"
            grid_coverage(on)
        }
        
        puts stderr "SaVi: grid level set to $level"
    } else {
        puts stderr "SaVi: failed to set grid level to $level"
    }
}

# 初始化时生成默认级别的格网
proc grid(init) {} {
    global grid_level grid_coverage_flag
    puts stderr "SaVi: 初始化格网系统，级别 $grid_level"
    if {[grid(generate) $grid_level]} {
        puts stderr "SaVi: 格网系统初始化成功"
        
        # 如果格网覆盖默认启用，自动初始化覆盖系统
        if {$grid_coverage_flag == 1} {
            puts stderr "SaVi: 自动初始化格网覆盖系统"
            grid_coverage(on)
        }
    } else {
        puts stderr "SaVi: 格网系统初始化失败"
    }
}

# 格网控制对话框
proc grid(build) {} {
    global grid_level grid_coverage_angle FONT

    puts stderr "SaVi: grid(build) 被调用，准备打开格网控制对话框"
    
    if {[eval window(raise) grid]} {
        puts stderr "SaVi: 格网控制对话框已存在，提升窗口"
        return
    }

    puts stderr "SaVi: 创建格网控制对话框"
    
    # 确保格网覆盖系统已初始化
    global grid_coverage_flag
    if {$grid_coverage_flag == 1} {
        puts stderr "SaVi: 对话框创建时自动初始化格网覆盖系统，级别=$grid_level"
        # 直接调用，TCL会自动加载函数
        if {[catch {grid_coverage(on)} err]} {
            puts stderr "SaVi: 格网覆盖初始化失败: $err"
        } else {
            puts stderr "SaVi: 格网覆盖系统初始化成功"
        }
    }
    
    set grid_name [build_Toplevel grid]
    wm title $grid_name "Grid Control"

    set cmd [build_StdFrame $grid_name cmd]

    # 格网级别设置
    build_LabelEntryColumns $cmd le1 \
        {text "" "Grid Level:"} \
        {ientry "" grid_level}
    
    # 覆盖角度设置
    build_LabelEntryColumns $cmd le2 \
        {text "" "Coverage Angle (°):"} \
        {dentry "" grid_coverage_angle}
    
    # 按钮框架
    set button_frame [build_StdFrame $cmd buttons]
    button $button_frame.set_level -text "Set Level" -command {grid(set_level) $grid_level} -font $FONT(button)
    button $button_frame.set_angle -text "Set Angle" -command {grid(set_coverage_angle) $grid_coverage_angle} -font $FONT(button)
    button $button_frame.stats -text "Show Stats" -command "grid(show_stats)" -font $FONT(button)
    pack $button_frame.set_level $button_frame.set_angle $button_frame.stats -side left -padx 0.1c
    pack $button_frame -pady 0.1c
    
    # 绑定Enter键到输入框
    after idle [format {
        bind %s.le1.c1.0 <Return> {grid(set_level) $grid_level}
        bind %s.le2.c1.0 <Return> {grid(set_coverage_angle) $grid_coverage_angle}
    } $cmd $cmd]

    # 显示选项
    build_HOptionslist $cmd olist "grid(update_display)" \
        {"Show grid solid" grid_flag} \
        {"Show grid wireframe" grid_wireframe_flag} \
        {"Enable grid coverage" grid_coverage_flag}

    pack $cmd -fill both -expand 1

    # 延迟绑定，确保组件已创建
    after idle "
        if {\[winfo exists $cmd.le1.c1.0\]} {
            bind $cmd.le1.c1.0 <Return> {grid(set_level) \$grid_level}
            puts stderr \"SaVi: 绑定级别输入框事件成功\"
        } else {
            puts stderr \"SaVi: 级别输入框路径不存在: $cmd.le1.c1.0\"
        }
        
        if {\[winfo exists $cmd.le2.c1.0\]} {
            bind $cmd.le2.c1.0 <Return> {grid(set_coverage_angle) \$grid_coverage_angle}
            puts stderr \"SaVi: 绑定角度输入框事件成功\"
        } else {
            puts stderr \"SaVi: 角度输入框路径不存在: $cmd.le2.c1.0\"
        }
    "
    
    puts stderr "SaVi: 格网控制对话框创建完成"
}

# 更新格网显示状态
proc grid(update_display) {} {
    global grid_flag grid_wireframe_flag grid_coverage_flag geomview_module
    
    puts stderr "SaVi: grid(update_display) 被调用，grid_flag=$grid_flag, grid_wireframe_flag=$grid_wireframe_flag, grid_coverage_flag=$grid_coverage_flag"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过格网显示更新"
        return
    }
    
    # 根据标志状态控制格网显示
    if {$grid_flag == 1} {
        grid(on)
    } else {
        grid(off)
    }
    
    if {$grid_wireframe_flag == 1} {
        grid_wireframe(on)
    } else {
        grid_wireframe(off)
    }
    
    # 控制格网覆盖计算
    if {$grid_coverage_flag == 1} {
        grid_coverage(on)
    } else {
        grid_coverage(off)
    }
}

# 用于菜单的开关函数
proc grid_off_cmd {} {
    grid(off)
    return "OK"
}

proc grid_wireframe_off_cmd {} {
    grid_wireframe(off)
    return "OK"
}

# 菜单中的格网切换函数
proc grid(toggle_solid) {} {
    global grid_flag
    puts stderr "SaVi: grid(toggle_solid) 被调用，grid_flag=$grid_flag"
    
    if {$grid_flag == 1} {
        grid(on)
    } else {
        grid(off)
    }
}

proc grid(toggle_wireframe) {} {
    global grid_wireframe_flag
    puts stderr "SaVi: grid(toggle_wireframe) 被调用，grid_wireframe_flag=$grid_wireframe_flag"
    
    if {$grid_wireframe_flag == 1} {
        grid_wireframe(on)
    } else {
        grid_wireframe(off)
    }
}

# 格网覆盖功能
proc grid_coverage(on) {} {
    global grid_level
    
    puts stderr "SaVi: grid_coverage(on) 被调用"
    
    # 初始化格网覆盖系统
    set result [satellites GRID_COVERAGE_ON $grid_level]
    if {$result != "OK"} {
        puts stderr "SaVi: failed to enable grid coverage: $result"
        return 0
    }
    
    puts stderr "SaVi: 格网覆盖计算已启用"
    return 1
}

proc grid_coverage(off) {} {
    puts stderr "SaVi: grid_coverage(off) 被调用"
    
    set result [satellites GRID_COVERAGE_OFF]
    if {$result != "OK"} {
        puts stderr "SaVi: failed to disable grid coverage: $result"
        return 0
    }
    
    puts stderr "SaVi: 格网覆盖计算已禁用"
    return 1
}

proc grid(set_coverage_angle) {angle} {
    global grid_coverage_angle
    
    puts stderr "SaVi: grid(set_coverage_angle) 被调用，angle=$angle"
    
    # 验证输入是否为有效数字
    if {![string is double $angle]} {
        puts stderr "SaVi: 无效的角度值: $angle"
        return 0
    }
    
    if {$angle < 0 || $angle > 180} {
        puts stderr "SaVi: 覆盖角度必须在0-180度之间"
        return 0
    }
    
    set grid_coverage_angle $angle
    set result [satellites GRID_COVERAGE_SET_ANGLE $angle]
    if {$result != "OK"} {
        puts stderr "SaVi: failed to set coverage angle: $result"
        return 0
    }
    
    puts stderr "SaVi: 覆盖角度已设置为 $angle 度"
    return 1
}

proc grid(show_stats) {} {
    global grid_coverage_flag
    
    puts stderr "SaVi: grid(show_stats) 被调用"
    
    
    set result [satellites GRID_COVERAGE_STATS]
    puts stderr "SaVi: 格网覆盖统计信息已输出到终端"
}
