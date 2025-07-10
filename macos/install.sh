#!/bin/bash

# Auto Match Pull - macOS Service Installer
# 用于在macOS上安装和管理自动匹配Pull服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_FILE="com.ape147.auto-match-pull.plist"
SERVICE_PLIST="$SCRIPT_DIR/$PLIST_FILE"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/$PLIST_FILE"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/data/logs"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印彩色信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否已安装
check_installed() {
    if [ -f "$LAUNCHD_PLIST" ]; then
        return 0
    else
        return 1
    fi
}

# 检查服务状态
check_status() {
    if launchctl list | grep -q "com.ape147.auto-match-pull"; then
        return 0
    else
        return 1
    fi
}

# 创建个人配置
create_personal_config() {
    local template_file="$SCRIPT_DIR/com.ape147.auto-match-pull.plist.template"
    local personal_file="$SCRIPT_DIR/com.ape147.auto-match-pull.plist"
    
    if [ ! -f "$template_file" ]; then
        print_error "找不到模板文件: $template_file"
        return 1
    fi
    
    if [ -f "$personal_file" ]; then
        print_info "个人配置文件已存在，跳过创建"
        return 0
    fi
    
    print_info "创建个人配置文件..."
    
    # 提示用户输入搜索路径
    echo ""
    print_info "请输入您的项目搜索路径（用逗号分隔）:"
    print_info "例如: $HOME/Developer/Projects,$HOME/Documents/Code"
    read -p "搜索路径: " search_paths
    
    if [ -z "$search_paths" ]; then
        print_warning "使用默认路径: $HOME/Developer,$HOME/Documents"
        search_paths="$HOME/Developer,$HOME/Documents"
    fi
    
    # 从模板创建个人配置
    sed "s|\$HOME/path/to/your/projects1,\$HOME/path/to/your/projects2|$search_paths|g" "$template_file" > "$personal_file"
    
    print_success "个人配置文件已创建: $personal_file"
    print_warning "注意: 此文件包含个人路径信息，不会被git跟踪"
}

# 安装服务
install_service() {
    print_info "开始安装Auto Match Pull服务..."
    
    # 检查是否已经安装
    if check_installed; then
        print_warning "服务已经安装，请先卸载再重新安装"
        return 1
    fi
    
    # 检查auto-match-pull命令是否可用
    if ! command -v auto-match-pull &> /dev/null; then
        print_error "未找到auto-match-pull命令，请先安装包: pip install auto-match-pull"
        return 1
    fi
    
    # 创建个人配置
    create_personal_config
    
    # 检查个人配置文件是否存在
    if [ ! -f "$SERVICE_PLIST" ]; then
        print_error "个人配置文件不存在，无法安装服务"
        return 1
    fi
    
    # 创建日志目录
    mkdir -p "$LOG_DIR"
    
    # 复制plist文件
    cp "$SERVICE_PLIST" "$LAUNCHD_PLIST"
    
    # 设置权限
    chmod 644 "$LAUNCHD_PLIST"
    
    # 加载服务
    launchctl load "$LAUNCHD_PLIST"
    
    print_success "服务安装成功！"
    print_info "服务将在后台运行，日志位置: $LOG_DIR"
    print_info "使用 '$0 status' 检查服务状态"
}

# 卸载服务
uninstall_service() {
    print_info "开始卸载Auto Match Pull服务..."
    
    # 停止服务
    if check_status; then
        launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
        print_info "服务已停止"
    fi
    
    # 删除plist文件
    if [ -f "$LAUNCHD_PLIST" ]; then
        rm "$LAUNCHD_PLIST"
        print_success "服务已卸载"
    else
        print_warning "服务未安装"
    fi
}

# 启动服务
start_service() {
    if ! check_installed; then
        print_error "服务未安装，请先安装"
        return 1
    fi
    
    if check_status; then
        print_warning "服务已在运行"
        return 0
    fi
    
    launchctl load "$LAUNCHD_PLIST"
    print_success "服务已启动"
}

# 停止服务
stop_service() {
    if ! check_installed; then
        print_error "服务未安装"
        return 1
    fi
    
    if ! check_status; then
        print_warning "服务未运行"
        return 0
    fi
    
    launchctl unload "$LAUNCHD_PLIST"
    print_success "服务已停止"
}

# 重启服务
restart_service() {
    print_info "重启服务..."
    stop_service
    sleep 2
    start_service
}

# 显示服务状态
show_status() {
    print_info "检查服务状态..."
    
    if ! check_installed; then
        print_error "服务未安装"
        return 1
    fi
    
    if check_status; then
        print_success "服务正在运行"
        
        # 显示进程信息
        if ps aux | grep -q "[a]uto-match-pull daemon"; then
            print_info "进程信息:"
            ps aux | grep "[a]uto-match-pull daemon"
        fi
        
        # 显示最近的日志
        if [ -f "$LOG_DIR/daemon.log" ]; then
            print_info "最近的日志 (最后10行):"
            tail -n 10 "$LOG_DIR/daemon.log"
        fi
    else
        print_warning "服务未运行"
    fi
}

# 查看日志
show_logs() {
    if [ -f "$LOG_DIR/daemon.log" ]; then
        print_info "查看日志: $LOG_DIR/daemon.log"
        tail -f "$LOG_DIR/daemon.log"
    else
        print_warning "日志文件不存在"
    fi
}

# 清理日志
clean_logs() {
    if [ -d "$LOG_DIR" ]; then
        rm -rf "$LOG_DIR"/*
        print_success "日志已清理"
    else
        print_warning "日志目录不存在"
    fi
}

# 显示帮助
show_help() {
    echo "Auto Match Pull - macOS Service Manager"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  install     安装服务"
    echo "  uninstall   卸载服务"
    echo "  start       启动服务"
    echo "  stop        停止服务"
    echo "  restart     重启服务"
    echo "  status      显示服务状态"
    echo "  logs        查看日志"
    echo "  clean       清理日志"
    echo "  help        显示帮助"
    echo ""
    echo "安装后，服务将在系统启动时自动运行"
    echo "日志位置: $LOG_DIR"
}

# 主程序
main() {
    case "$1" in
        install)
            install_service
            ;;
        uninstall)
            uninstall_service
            ;;
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        clean)
            clean_logs
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 检查参数
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# 运行主程序
main "$@"