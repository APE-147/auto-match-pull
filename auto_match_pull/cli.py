#!/usr/bin/env python3
"""
Auto Match Pull CLI
"""

import argparse
import sys
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from .core.matcher import FolderMatcher
from .core.database import DatabaseManager, FolderRepoMapping
from .services.git_service import GitService
from .services.scheduler import SchedulerService, SchedulerConfig


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def load_config(config_path: str = None) -> Dict:
    """加载配置文件，支持环境变量覆盖"""
    if config_path is None:
        config_path = os.path.expanduser("~/.auto-match-pull/config.json")
    
    # 从环境变量获取搜索路径
    env_search_paths = os.environ.get('AUTO_MATCH_PULL_SEARCH_PATHS')
    env_interval = os.environ.get('AUTO_MATCH_PULL_INTERVAL')
    
    if not os.path.exists(config_path):
        # 创建默认配置
        default_search_paths = [
            "~/Developer",
            "~/Documents", 
            "~/Projects"
        ]
        
        # 如果环境变量存在，使用环境变量的路径
        if env_search_paths:
            default_search_paths = [path.strip() for path in env_search_paths.split(',')]
        
        default_interval = 30
        if env_interval:
            try:
                default_interval = int(env_interval)
            except ValueError:
                default_interval = 30
        
        default_config = {
            "search_paths": default_search_paths,
            "github_username": "",
            "scheduler": {
                "pull_interval_minutes": default_interval,
                "max_concurrent_pulls": 3,
                "retry_failed_after_minutes": 120,
                "cleanup_logs_days": 30
            },
            "similarity_threshold": 0.8,
            "auto_resolve_conflicts": True
        }
        
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        print(f"创建默认配置文件: {config_path}")
        return default_config
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # 环境变量覆盖配置文件设置
    if env_search_paths:
        config["search_paths"] = [path.strip() for path in env_search_paths.split(',')]
    
    if env_interval:
        try:
            config["scheduler"]["pull_interval_minutes"] = int(env_interval)
        except (ValueError, KeyError):
            pass
    
    return config


def cmd_scan(args):
    """扫描GitHub仓库并匹配本地项目"""
    config = load_config(args.config)
    search_paths = config.get('search_paths', [])
    
    if args.paths:
        search_paths = args.paths
    
    # 获取GitHub配置
    github_username = args.github_username or config.get('github_username')
    github_token = args.github_token or os.environ.get('GITHUB_TOKEN')
    
    if not github_username:
        print("错误: 需要提供GitHub用户名")
        return
    
    print(f"扫描路径: {search_paths}")
    print(f"GitHub用户: {github_username}")
    
    # 创建匹配器
    matcher = FolderMatcher(search_paths, github_token)
    
    # 新的匹配流程：先获取GitHub仓库，再匹配本地项目
    print("从GitHub获取仓库列表...")
    matches = matcher.match_github_to_local(github_username)
    
    print(f"\n找到 {len(matches)} 个GitHub仓库匹配:")
    for repo_name, local_path, is_git_repo, has_remote in matches:
        github_url = f"https://github.com/{github_username}/{repo_name}"
        
        if has_remote:
            status = "✅ 已关联远程仓库"
        elif is_git_repo:
            status = "🔄 Git仓库但未关联远程"
        else:
            status = "📁 普通文件夹"
        
        print(f"  {repo_name} -> {local_path}")
        print(f"    状态: {status}")
        print(f"    GitHub: {github_url}")
    
    # 保存到数据库
    if args.save:
        print("\n保存到数据库...")
        db_manager = DatabaseManager()
        
        for repo_name, local_path, is_git_repo, has_remote in matches:
            github_url = f"https://github.com/{github_username}/{repo_name}"
            
            # 保存条件：只保存包含.git文件夹的项目（已Git化的项目）
            if is_git_repo:
                mapping = FolderRepoMapping(
                    folder_path=local_path,
                    folder_name=repo_name,
                    repo_path=local_path,
                    repo_name=repo_name,
                    remote_url=github_url if has_remote else None,
                    branch='main',
                    similarity_score=1.0,  # 精确匹配
                    auto_pull_enabled=has_remote,  # 只有已关联远程的才开启自动pull
                    github_url=github_url,
                    github_exists=True
                )
                mapping_id = db_manager.save_mapping(mapping)
                auto_pull_status = "✅" if has_remote else "❌"
                print(f"  保存映射 {mapping_id}: {repo_name} -> {github_url} (自动Pull: {auto_pull_status})")
        
        saved_count = sum(1 for _, _, is_git_repo, has_remote in matches if is_git_repo)
        print(f"共保存 {saved_count} 个映射")


def cmd_list(args):
    """列出所有映射"""
    db_manager = DatabaseManager()
    mappings = db_manager.get_all_mappings()
    
    if not mappings:
        print("没有找到任何映射")
        return
    
    print(f"共有 {len(mappings)} 个映射:")
    print("-" * 80)
    
    for mapping in mappings:
        status_icon = "✅" if mapping.auto_pull_enabled else "❌"
        pull_status = mapping.pull_status or "未知"
        last_pull = mapping.last_pull_at or "从未"
        
        print(f"ID: {mapping.id}")
        print(f"  文件夹: {mapping.folder_name} ({mapping.folder_path})")
        print(f"  仓库: {mapping.repo_name} ({mapping.repo_path})")
        print(f"  分支: {mapping.branch}")
        print(f"  相似度: {mapping.similarity_score:.2f}")
        print(f"  自动Pull: {status_icon}")
        print(f"  Pull状态: {pull_status}")
        print(f"  最后Pull: {last_pull}")
        print("-" * 80)


def cmd_pull(args):
    """执行Pull操作"""
    db_manager = DatabaseManager()
    git_service = GitService()
    
    if args.id:
        # Pull指定ID的仓库
        mapping = db_manager.get_mapping_by_id(args.id)
        if not mapping:
            print(f"未找到ID为 {args.id} 的映射")
            return
        
        print(f"Pull仓库: {mapping.repo_name}")
        result = git_service.pull_repository(mapping.repo_path, mapping.branch)
        
        if result.success:
            print("✅ Pull成功")
            print(f"消息: {result.message}")
            db_manager.update_pull_status(mapping.id, 'success', result.message)
        else:
            print("❌ Pull失败")
            print(f"错误: {result.message}")
            status = 'conflict' if result.conflicts else 'failed'
            db_manager.update_pull_status(mapping.id, status, result.message)
    else:
        # Pull所有启用的仓库
        mappings = db_manager.get_auto_pull_mappings()
        print(f"Pull所有启用的仓库，共 {len(mappings)} 个")
        
        for mapping in mappings:
            print(f"\nPull: {mapping.repo_name}")
            result = git_service.pull_repository(mapping.repo_path, mapping.branch)
            
            if result.success:
                print("✅ 成功")
                db_manager.update_pull_status(mapping.id, 'success', result.message)
            else:
                print("❌ 失败")
                print(f"错误: {result.message}")
                status = 'conflict' if result.conflicts else 'failed'
                db_manager.update_pull_status(mapping.id, status, result.message)


def cmd_daemon(args):
    """启动守护进程"""
    config = load_config(args.config)
    
    # 创建服务
    db_manager = DatabaseManager()
    git_service = GitService()
    
    scheduler_config = SchedulerConfig(
        pull_interval_minutes=config['scheduler']['pull_interval_minutes'],
        max_concurrent_pulls=config['scheduler']['max_concurrent_pulls'],
        retry_failed_after_minutes=config['scheduler']['retry_failed_after_minutes'],
        cleanup_logs_days=config['scheduler']['cleanup_logs_days']
    )
    
    scheduler = SchedulerService(db_manager, git_service, scheduler_config)
    
    if args.stop:
        print("停止守护进程...")
        scheduler.stop()
        return
    
    print("启动守护进程...")
    print(f"Pull间隔: {scheduler_config.pull_interval_minutes}分钟")
    print(f"最大并发: {scheduler_config.max_concurrent_pulls}")
    print("按 Ctrl+C 停止")
    
    try:
        scheduler.start()
        
        # 保持运行
        while scheduler.is_running():
            import time
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n收到停止信号，正在停止...")
        scheduler.stop()
    
    print("守护进程已停止")


def cmd_config(args):
    """管理配置"""
    config_path = args.config or os.path.expanduser("~/.auto-match-pull/config.json")
    
    if args.show:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            print(json.dumps(config, indent=2, ensure_ascii=False))
        else:
            print(f"配置文件不存在: {config_path}")
    
    elif args.edit:
        import subprocess
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.call([editor, config_path])
    
    elif args.reset:
        if os.path.exists(config_path):
            os.remove(config_path)
        load_config(config_path)  # 重新创建默认配置
        print(f"已重置配置文件: {config_path}")


def cmd_logs(args):
    """查看日志"""
    db_manager = DatabaseManager()
    
    if args.mapping_id:
        logs = db_manager.get_pull_logs(args.mapping_id, args.limit)
        print(f"映射 {args.mapping_id} 的日志:")
    else:
        logs = db_manager.get_pull_logs(limit=args.limit)
        print("所有日志:")
    
    if not logs:
        print("没有找到日志")
        return
    
    print("-" * 80)
    for log in logs:
        status_icon = "✅" if log['status'] == 'success' else "❌"
        print(f"{log['timestamp']} - {status_icon} {log['action']}")
        if log['message']:
            print(f"  消息: {log['message']}")
        print("-" * 80)


def cmd_delete(args):
    """删除映射"""
    db_manager = DatabaseManager()
    
    if args.id:
        # 删除指定ID的映射
        mapping = db_manager.get_mapping_by_id(args.id)
        if not mapping:
            print(f"未找到ID为 {args.id} 的映射")
            return
        
        print(f"确认删除映射: {mapping.folder_name} -> {mapping.github_url}")
        confirm = input("输入 'yes' 确认删除: ")
        if confirm.lower() == 'yes':
            if db_manager.delete_mapping(args.id):
                print("✅ 映射已删除")
            else:
                print("❌ 删除失败")
        else:
            print("取消删除")
    
    elif args.cleanup:
        # 清理无效路径的映射
        print("清理无效路径的映射...")
        mappings = db_manager.get_all_mappings()
        deleted_count = 0
        
        for mapping in mappings:
            if not os.path.exists(mapping.folder_path):
                print(f"删除无效映射: {mapping.folder_name} -> {mapping.folder_path}")
                db_manager.delete_mapping(mapping.id)
                deleted_count += 1
        
        print(f"共清理了 {deleted_count} 个无效映射")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Auto Match Pull - 自动匹配文件夹和Git仓库并定时同步')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细输出')
    parser.add_argument('-c', '--config', help='配置文件路径')
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 扫描命令
    scan_parser = subparsers.add_parser('scan', help='扫描文件夹和匹配GitHub仓库')
    scan_parser.add_argument('paths', nargs='*', help='扫描路径')
    scan_parser.add_argument('-s', '--save', action='store_true', help='保存匹配结果到数据库')
    scan_parser.add_argument('-u', '--github-username', help='GitHub用户名')
    scan_parser.add_argument('-t', '--github-token', help='GitHub访问令牌')
    
    # 列出命令
    list_parser = subparsers.add_parser('list', help='列出所有映射')
    
    # Pull命令
    pull_parser = subparsers.add_parser('pull', help='执行Pull操作')
    pull_parser.add_argument('id', nargs='?', type=int, help='映射ID（可选）')
    
    # 守护进程命令
    daemon_parser = subparsers.add_parser('daemon', help='启动守护进程')
    daemon_parser.add_argument('--stop', action='store_true', help='停止守护进程')
    
    # 配置命令
    config_parser = subparsers.add_parser('config', help='管理配置')
    config_parser.add_argument('--show', action='store_true', help='显示配置')
    config_parser.add_argument('--edit', action='store_true', help='编辑配置')
    config_parser.add_argument('--reset', action='store_true', help='重置配置')
    
    # 日志命令
    logs_parser = subparsers.add_parser('logs', help='查看日志')
    logs_parser.add_argument('mapping_id', nargs='?', type=int, help='映射ID（可选）')
    logs_parser.add_argument('-l', '--limit', type=int, default=50, help='日志数量限制')
    
    # 删除命令
    delete_parser = subparsers.add_parser('delete', help='删除映射')
    delete_parser.add_argument('id', nargs='?', type=int, help='要删除的映射ID')
    delete_parser.add_argument('--cleanup', action='store_true', help='清理无效路径的映射')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    setup_logging(args.verbose)
    
    try:
        if args.command == 'scan':
            cmd_scan(args)
        elif args.command == 'list':
            cmd_list(args)
        elif args.command == 'pull':
            cmd_pull(args)
        elif args.command == 'daemon':
            cmd_daemon(args)
        elif args.command == 'config':
            cmd_config(args)
        elif args.command == 'logs':
            cmd_logs(args)
        elif args.command == 'delete':
            cmd_delete(args)
        else:
            parser.print_help()
            
    except Exception as e:
        print(f"错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()