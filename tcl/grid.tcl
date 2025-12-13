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
global latlon_grid_flag latlon_grid_wireframe_flag latlon_solid_file latlon_wireframe_file
global grid_coverage_flag grid_coverage_angle
global grid_type lat_divisions lon_divisions
set grid_flag 0
set grid_wireframe_flag 0
set latlon_grid_flag 0
set latlon_grid_wireframe_flag 0
set grid_level 0
set grid_coverage_flag 1
set grid_coverage_angle 8.2

# 格网类型：0=二十面体，1=经纬度，2=同时使用两种
set grid_type 0
set lat_divisions 36
set lon_divisions 72

# 格网文件路径
set grid_solid_file ""
set grid_wireframe_file ""
set latlon_solid_file ""
set latlon_wireframe_file ""

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

# ========== 经纬度格网显示功能 ==========

proc latlon_grid(on) {} {
    global latlon_grid_flag geomview_module latlon_solid_file lat_divisions lon_divisions
    
    puts stderr "SaVi: latlon_grid(on) 被调用"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过经纬度格网显示"
        return
    }
    
    set latlon_grid_flag 1
    
    # 确保经纬度格网文件已生成
    if {[latlon_grid(generate) $lat_divisions $lon_divisions] && $latlon_solid_file != ""} {
        puts stderr "SaVi: 开始显示经纬度实体格网: $latlon_solid_file"
        geomview(begin)
        geomview(puts) "(read geometry {define latlon_grid_solid_h < \"$latlon_solid_file\"})"
        geomview(puts) "(geometry latlon_grid_solid {: latlon_grid_solid_h})"
        geomview(end)
        puts stderr "SaVi: loaded latlon grid solid from $latlon_solid_file"
    } else {
        puts stderr "SaVi: failed to load latlon grid solid"
        set latlon_grid_flag 0
    }
}

proc latlon_grid(off) {} {
    global latlon_grid_flag geomview_module
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        return
    }
    
    set latlon_grid_flag 0
    
    geomview(begin)
    geomview(puts) "(delete latlon_grid_solid)"
    geomview(end)
    puts stderr "SaVi: unloaded latlon grid solid"
}

proc latlon_grid_wireframe(on) {} {
    global latlon_grid_wireframe_flag geomview_module latlon_wireframe_file lat_divisions lon_divisions
    
    puts stderr "SaVi: latlon_grid_wireframe(on) 被调用"
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        puts stderr "SaVi: geomview模块未启用，跳过经纬度格网线框显示"
        return
    }
    
    set latlon_grid_wireframe_flag 1
    
    if {[latlon_grid(generate) $lat_divisions $lon_divisions] && $latlon_wireframe_file != ""} {
        puts stderr "SaVi: 开始显示经纬度格网线框: $latlon_wireframe_file"
        geomview(begin)
        geomview(puts) "(read geometry {define latlon_grid_wireframe_h < \"$latlon_wireframe_file\"})"
        geomview(puts) "(geometry latlon_grid_wireframe {: latlon_grid_wireframe_h})"
        geomview(end)
        puts stderr "SaVi: loaded latlon grid wireframe from $latlon_wireframe_file"
    } else {
        puts stderr "SaVi: failed to load latlon grid wireframe"
        set latlon_grid_wireframe_flag 0
    }
}

proc latlon_grid_wireframe(off) {} {
    global latlon_grid_wireframe_flag geomview_module
    
    if {![info exists geomview_module] || $geomview_module != 1} {
        return
    }
    
    set latlon_grid_wireframe_flag 0
    
    geomview(begin)
    geomview(puts) "(delete latlon_grid_wireframe)"
    geomview(end)
    puts stderr "SaVi: unloaded latlon grid wireframe"
}

# 生成经纬度格网文件
proc latlon_grid(generate) {lat_div lon_div} {
    global latlon_solid_file latlon_wireframe_file
    
    # 检查文件是否已存在
    set solid_path "./mini-savi/latlon_grid_${lat_div}x${lon_div}.oogl"
    set wireframe_path "./mini-savi/latlon_grid_${lat_div}x${lon_div}_wireframe.oogl"
    
    if {[file exists $solid_path] && [file exists $wireframe_path]} {
        set latlon_solid_file $solid_path
        set latlon_wireframe_file $wireframe_path
        puts stderr "SaVi: 使用现有经纬度格网文件 ${lat_div}x${lon_div}"
        return 1
    } else {
        puts stderr "SaVi: 经纬度格网文件不存在: ${lat_div}x${lon_div}"
        puts stderr "SaVi: 请先运行: ./build_latlon_grid.sh"
        return 0
    }
}

# 经纬度格网切换函数
proc latlon_grid(toggle_solid) {} {
    global latlon_grid_flag
    puts stderr "SaVi: latlon_grid(toggle_solid) 被调用，latlon_grid_flag=$latlon_grid_flag"
    
    if {$latlon_grid_flag == 1} {
        latlon_grid(on)
    } else {
        latlon_grid(off)
    }
}

proc latlon_grid(toggle_wireframe) {} {
    global latlon_grid_wireframe_flag
    puts stderr "SaVi: latlon_grid(toggle_wireframe) 被调用，latlon_grid_wireframe_flag=$latlon_grid_wireframe_flag"
    
    if {$latlon_grid_wireframe_flag == 1} {
        latlon_grid_wireframe(on)
    } else {
        latlon_grid_wireframe(off)
    }
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
    global grid_level grid_coverage_angle grid_type lat_divisions lon_divisions FONT

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

    # ========== 格网类型选择 ==========
    set type_frame [frame $cmd.type_frame -relief groove -borderwidth 2]
    label $type_frame.label -text "Grid Type:" -font $FONT(label)
    radiobutton $type_frame.icosahedral -text "Icosahedral Only" -variable grid_type -value 0 \
        -command "grid(switch_type)" -font $FONT(button)
    radiobutton $type_frame.latlon -text "Lat-Lon Only" -variable grid_type -value 1 \
        -command "grid(switch_type)" -font $FONT(button)
    radiobutton $type_frame.both -text "Both (Comparison)" -variable grid_type -value 2 \
        -command "grid(switch_type)" -font $FONT(button) -fg "red"
    
    pack $type_frame.label -side top -anchor w -padx 0.2c -pady 0.1c
    pack $type_frame.icosahedral $type_frame.latlon $type_frame.both -side left -padx 0.2c -pady 0.1c
    pack $type_frame -fill x -pady 0.2c
    
    # ========== 二十面体格网参数 ==========
    set ico_frame [frame $cmd.ico_frame -relief groove -borderwidth 2]
    label $ico_frame.title -text "Icosahedral Grid Parameters:" -font $FONT(label) -fg blue
    
    build_LabelEntryColumns $ico_frame le1 \
        {text "" "Grid Level (0-6):"} \
        {ientry "" grid_level}
    
    pack $ico_frame.title -side top -anchor w -padx 0.2c -pady 0.1c
    pack $ico_frame.le1 -fill x -padx 0.2c -pady 0.1c
    pack $ico_frame -fill x -pady 0.2c
    
    # ========== 经纬度格网参数 ==========
    set latlon_frame [frame $cmd.latlon_frame -relief groove -borderwidth 2]
    label $latlon_frame.title -text "Lat-Lon Grid Parameters:" -font $FONT(label) -fg blue
    
    build_LabelEntryColumns $latlon_frame le1 \
        {text "" "Latitude Divisions:"} \
        {ientry "" lat_divisions}
    
    build_LabelEntryColumns $latlon_frame le2 \
        {text "" "Longitude Divisions:"} \
        {ientry "" lon_divisions}
    
    # 预设按钮
    set preset_frame [frame $latlon_frame.preset]
    label $preset_frame.label -text "Presets:" -font $FONT(label)
    button $preset_frame.p1 -text "18x36" -command {set lat_divisions 18; set lon_divisions 36} -font $FONT(button)
    button $preset_frame.p2 -text "36x72" -command {set lat_divisions 36; set lon_divisions 72} -font $FONT(button)
    button $preset_frame.p3 -text "72x144" -command {set lat_divisions 72; set lon_divisions 144} -font $FONT(button)
    
    pack $preset_frame.label -side left -padx 0.1c
    pack $preset_frame.p1 $preset_frame.p2 $preset_frame.p3 -side left -padx 0.05c
    
    pack $latlon_frame.title -side top -anchor w -padx 0.2c -pady 0.1c
    pack $latlon_frame.le1 -fill x -padx 0.2c -pady 0.1c
    pack $latlon_frame.le2 -fill x -padx 0.2c -pady 0.1c
    pack $latlon_frame.preset -side top -anchor w -padx 0.2c -pady 0.1c
    pack $latlon_frame -fill x -pady 0.2c
    
    # ========== 覆盖角度设置 ==========
    set angle_frame [frame $cmd.angle_frame -relief groove -borderwidth 2]
    label $angle_frame.title -text "Coverage Parameters:" -font $FONT(label) -fg blue
    
    build_LabelEntryColumns $angle_frame le1 \
        {text "" "Coverage Angle (°):"} \
        {dentry "" grid_coverage_angle}
    
    pack $angle_frame.title -side top -anchor w -padx 0.2c -pady 0.1c
    pack $angle_frame.le1 -fill x -padx 0.2c -pady 0.1c
    pack $angle_frame -fill x -pady 0.2c
    
    # ========== 控制按钮 ==========
    set button_frame [build_StdFrame $cmd buttons]
    button $button_frame.apply -text "Apply Grid" -command "grid(apply_grid_type)" \
        -font $FONT(button) -bg "#90EE90" -activebackground "#7CCD7C"
    button $button_frame.set_angle -text "Set Angle" -command {grid(set_coverage_angle) $grid_coverage_angle} \
        -font $FONT(button)
    button $button_frame.stats -text "Show Stats" -command "grid(show_stats)" \
        -font $FONT(button)
    
    pack $button_frame.apply $button_frame.set_angle $button_frame.stats -side left -padx 0.1c
    pack $button_frame -pady 0.2c
    
    # ========== 显示选项 ==========
    set display_frame [frame $cmd.display_frame -relief groove -borderwidth 2]
    label $display_frame.title -text "Display Options:" -font $FONT(label) -fg blue
    
    # 二十面体格网显示
    frame $display_frame.ico
    label $display_frame.ico.label -text "Icosahedral Grid:" -font $FONT(label)
    checkbutton $display_frame.ico.solid -text "Show Solid" -variable grid_flag \
        -command "grid(toggle_solid)" -font $FONT(button)
    checkbutton $display_frame.ico.wire -text "Show Wireframe" -variable grid_wireframe_flag \
        -command "grid(toggle_wireframe)" -font $FONT(button)
    pack $display_frame.ico.label -side left -padx 0.1c
    pack $display_frame.ico.solid $display_frame.ico.wire -side left -padx 0.05c
    
    # 经纬度格网显示
    frame $display_frame.latlon
    label $display_frame.latlon.label -text "Lat-Lon Grid:" -font $FONT(label)
    checkbutton $display_frame.latlon.solid -text "Show Solid" -variable latlon_grid_flag \
        -command "latlon_grid(toggle_solid)" -font $FONT(button)
    checkbutton $display_frame.latlon.wire -text "Show Wireframe" -variable latlon_grid_wireframe_flag \
        -command "latlon_grid(toggle_wireframe)" -font $FONT(button)
    pack $display_frame.latlon.label -side left -padx 0.1c
    pack $display_frame.latlon.solid $display_frame.latlon.wire -side left -padx 0.05c
    
    # 格网覆盖
    frame $display_frame.coverage
    checkbutton $display_frame.coverage.enable -text "Enable Grid Coverage" -variable grid_coverage_flag \
        -command "grid(update_display)" -font $FONT(button)
    pack $display_frame.coverage.enable -side left -padx 0.1c
    
    pack $display_frame.title -side top -anchor w -padx 0.2c -pady 0.1c
    pack $display_frame.ico -side top -anchor w -padx 0.2c -pady 0.05c
    pack $display_frame.latlon -side top -anchor w -padx 0.2c -pady 0.05c
    pack $display_frame.coverage -side top -anchor w -padx 0.2c -pady 0.05c
    pack $display_frame -fill x -pady 0.2c

    pack $cmd -fill both -expand 1

    # 初始化显示状态
    grid(switch_type)
    
    # 延迟绑定Enter键
    after idle "
        if {\[winfo exists $ico_frame.le1.c1.0\]} {
            bind $ico_frame.le1.c1.0 <Return> {grid(apply_grid_type)}
        }
        if {\[winfo exists $latlon_frame.le1.c1.0\]} {
            bind $latlon_frame.le1.c1.0 <Return> {grid(apply_grid_type)}
        }
        if {\[winfo exists $latlon_frame.le2.c1.0\]} {
            bind $latlon_frame.le2.c1.0 <Return> {grid(apply_grid_type)}
        }
        if {\[winfo exists $angle_frame.le1.c1.0\]} {
            bind $angle_frame.le1.c1.0 <Return> {grid(set_coverage_angle) \$grid_coverage_angle}
        }
    "
    
    puts stderr "SaVi: 格网控制对话框创建完成"
}

# 切换格网类型时更新界面显示
proc grid(switch_type) {} {
    global grid_type
    
    set grid_win ".grid"
    if {![winfo exists $grid_win]} {
        return
    }
    
    set cmd "$grid_win.cmd"
    
    if {$grid_type == 0} {
        # 二十面体格网
        if {[winfo exists $cmd.ico_frame]} {
            $cmd.ico_frame configure -relief groove -borderwidth 2
        }
        if {[winfo exists $cmd.latlon_frame]} {
            $cmd.latlon_frame configure -relief flat -borderwidth 1
        }
        puts stderr "SaVi: 切换到二十面体格网参数"
    } elseif {$grid_type == 1} {
        # 经纬度格网
        if {[winfo exists $cmd.ico_frame]} {
            $cmd.ico_frame configure -relief flat -borderwidth 1
        }
        if {[winfo exists $cmd.latlon_frame]} {
            $cmd.latlon_frame configure -relief groove -borderwidth 2
        }
        puts stderr "SaVi: 切换到经纬度格网参数"
    } else {
        # 同时使用两种格网
        if {[winfo exists $cmd.ico_frame]} {
            $cmd.ico_frame configure -relief groove -borderwidth 2
        }
        if {[winfo exists $cmd.latlon_frame]} {
            $cmd.latlon_frame configure -relief groove -borderwidth 2
        }
        puts stderr "SaVi: 切换到同时使用两种格网模式"
    }
}

# 应用选择的格网类型
proc grid(apply_grid_type) {} {
    global grid_type grid_level lat_divisions lon_divisions grid_coverage_flag
    
    # 先关闭当前格网覆盖
    if {$grid_coverage_flag == 1} {
        puts stderr "SaVi: 关闭当前格网覆盖"
        grid_coverage(off)
    }
    
    # 等待一小段时间确保关闭完成
    after 500
    
    # 根据类型应用新格网
    if {$grid_type == 0} {
        # 二十面体格网
        puts stderr "SaVi: 应用二十面体格网，级别 $grid_level"
        
        # 验证级别
        if {$grid_level < 0 || $grid_level > 6} {
            puts stderr "SaVi: ✗ 无效的格网级别：$grid_level（必须在0-6之间）"
            return
        }
        
        # 设置级别并初始化
        grid(set_level) $grid_level
        
        if {$grid_coverage_flag == 1} {
            if {[grid_coverage(on)]} {
                puts stderr "SaVi: ✓ 二十面体格网已成功应用（级别 $grid_level）"
            } else {
                puts stderr "SaVi: ✗ 二十面体格网应用失败"
            }
        }
    } elseif {$grid_type == 1} {
        # 经纬度格网
        puts stderr "SaVi: 应用经纬度格网，${lat_divisions}x${lon_divisions}"
        
        # 验证参数
        if {$lat_divisions < 1 || $lat_divisions > 180} {
            puts stderr "SaVi: ✗ 无效的纬度划分数：$lat_divisions（必须在1-180之间）"
            return
        }
        if {$lon_divisions < 1 || $lon_divisions > 360} {
            puts stderr "SaVi: ✗ 无效的经度划分数：$lon_divisions（必须在1-360之间）"
            return
        }
        
        if {$grid_coverage_flag == 1} {
            if {[grid_coverage_latlon(on) $lat_divisions $lon_divisions]} {
                puts stderr "SaVi: ✓ 经纬度格网已成功应用（${lat_divisions}x${lon_divisions}）"
            } else {
                puts stderr "SaVi: ✗ 经纬度格网应用失败"
                puts stderr "SaVi: 请先运行 ./build_latlon_grid.sh 生成格网文件"
            }
        }
    } else {
        # 同时使用两种格网
        puts stderr "SaVi: 应用两种格网进行对比"
        
        # 验证参数
        if {$grid_level < 0 || $grid_level > 6} {
            puts stderr "SaVi: ✗ 无效的格网级别：$grid_level（必须在0-6之间）"
            return
        }
        if {$lat_divisions < 1 || $lat_divisions > 180} {
            puts stderr "SaVi: ✗ 无效的纬度划分数：$lat_divisions（必须在1-180之间）"
            return
        }
        if {$lon_divisions < 1 || $lon_divisions > 360} {
            puts stderr "SaVi: ✗ 无效的经度划分数：$lon_divisions（必须在1-360之间）"
            return
        }
        
        if {$grid_coverage_flag == 1} {
            if {[grid_coverage_both(on) $grid_level $lat_divisions $lon_divisions]} {
                puts stderr "SaVi: ✓ 两种格网已成功应用："
                puts stderr "SaVi:   - 二十面体格网（级别 $grid_level）"
                puts stderr "SaVi:   - 经纬度格网（${lat_divisions}x${lon_divisions}）"
                puts stderr "SaVi:   - 覆盖数据将同时发送"
            } else {
                puts stderr "SaVi: ✗ 两种格网应用失败"
                puts stderr "SaVi: 请确保已生成两种格网文件"
            }
        }
    }
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

# 格网覆盖功能（二十面体格网）
proc grid_coverage(on) {} {
    global grid_level
    
    puts stderr "SaVi: grid_coverage(on) 被调用 - 使用二十面体格网"
    
    # 初始化格网覆盖系统（二十面体）
    set result [satellites GRID_COVERAGE_ON $grid_level]
    if {$result != "OK"} {
        puts stderr "SaVi: failed to enable grid coverage: $result"
        return 0
    }
    
    puts stderr "SaVi: 格网覆盖计算已启用（二十面体格网，级别 $grid_level）"
    return 1
}

# 格网覆盖功能（经纬度格网）
proc grid_coverage_latlon(on) {lat_div lon_div} {
    puts stderr "SaVi: grid_coverage_latlon(on) 被调用 - 使用经纬度格网"
    puts stderr "SaVi: 纬度划分: $lat_div, 经度划分: $lon_div"
    
    # 初始化格网覆盖系统（经纬度）
    set result [satellites GRID_COVERAGE_ON_LATLON $lat_div $lon_div]
    if {$result != "OK"} {
        puts stderr "SaVi: failed to enable latlon grid coverage: $result"
        return 0
    }
    
    puts stderr "SaVi: 格网覆盖计算已启用（经纬度格网，${lat_div}x${lon_div}）"
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

# 同时使用两种格网的覆盖功能
proc grid_coverage_both(on) {ico_level lat_div lon_div} {
    puts stderr "SaVi: grid_coverage_both(on) 被调用"
    puts stderr "SaVi: 二十面体级别: $ico_level"
    puts stderr "SaVi: 经纬度划分: ${lat_div}x${lon_div}"
    
    # 直接调用GRID_COVERAGE_ON_BOTH命令，一次性加载两种格网
    set result [satellites GRID_COVERAGE_ON_BOTH $ico_level $lat_div $lon_div]
    if {$result != "OK"} {
        puts stderr "SaVi: ✗ 启用两种格网覆盖失败: $result"
        return 0
    }
    
    puts stderr "SaVi: ✓ 两种格网覆盖已成功启用"
    puts stderr "SaVi:   - 二十面体格网（级别 $ico_level）"
    puts stderr "SaVi:   - 经纬度格网（${lat_div}x${lon_div}）"
    puts stderr "SaVi:   - 两种格网覆盖数据将同时发送"
    
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
