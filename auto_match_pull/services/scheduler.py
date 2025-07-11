import time
import threading
import signal
import sys
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
import logging
import os

from ..core.database import DatabaseManager, FolderRepoMapping
from .git_service import GitService, PullResult

logger = logging.getLogger(__name__)

@dataclass
class SchedulerConfig:
    pull_interval_minutes: int = 15
    max_concurrent_pulls: int = 3
    retry_failed_after_minutes: int = 120
    cleanup_logs_days: int = 30
    repo_manager_dependency: bool = True
    repo_manager_config_dir: str = "/Users/niceday/Developer/Code/Local/Script/desktop/repo-management/.repo-manager"

class SchedulerService:
    def __init__(self, db_manager: DatabaseManager, git_service: GitService, config: SchedulerConfig = None):
        self.db_manager = db_manager
        self.git_service = git_service
        self.config = config or SchedulerConfig()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pull_semaphore = threading.Semaphore(self.config.max_concurrent_pulls)
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start(self):
        """启动定时服务"""
        if self._running:
            logger.warning("调度服务已经在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # 启动主循环线程
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()
        
        logger.info(f"调度服务已启动 (间隔: {self.config.pull_interval_minutes}分钟)")
    
    def stop(self):
        """停止定时服务"""
        if not self._running:
            return
        
        logger.info("正在停止调度服务...")
        self._running = False
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        
        logger.info("调度服务已停止")
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在停止服务...")
        self.stop()
        sys.exit(0)
    
    def _main_loop(self):
        """主循环"""
        logger.info("调度服务主循环启动")
        
        while self._running:
            try:
                # 执行一轮Pull操作
                self._execute_pull_cycle()
                
                # 等待指定时间或停止信号
                if self._stop_event.wait(timeout=self.config.pull_interval_minutes * 60):
                    break
                    
            except Exception as e:
                logger.error(f"主循环异常: {e}")
                # 出错后短暂休息
                if self._stop_event.wait(timeout=60):
                    break
        
        logger.info("调度服务主循环结束")
    
    def _is_repo_manager_idle(self) -> bool:
        """检查repo-manager进程是否空闲"""
        if not self.config.repo_manager_dependency:
            return True
        
        try:
            # 检查repo-manager进程是否在运行
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.warning("无法检查repo-manager进程状态")
                return True
            
            # 检查是否有repo-manager monitor进程在运行
            lines = result.stdout.split('\n')
            for line in lines:
                if 'repo-manager' in line and 'monitor' in line and 'grep' not in line:
                    logger.debug("repo-manager monitor进程正在运行，等待其完成")
                    return False
            
            logger.debug("repo-manager进程空闲")
            return True
            
        except Exception as e:
            logger.error(f"检查repo-manager状态失败: {e}")
            # 如果检查失败，默认允许运行
            return True
    
    def _wait_for_repo_manager_idle(self, timeout_minutes: int = 30):
        """等待repo-manager进程变为空闲状态"""
        if not self.config.repo_manager_dependency:
            return
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while not self._is_repo_manager_idle():
            if time.time() - start_time > timeout_seconds:
                logger.warning(f"等待repo-manager空闲超时 ({timeout_minutes}分钟)")
                break
            
            if self._stop_event.wait(timeout=30):  # 每30秒检查一次
                logger.info("收到停止信号，停止等待repo-manager")
                break
        
        logger.info("repo-manager进程空闲，可以开始Pull操作")
    
    def _execute_pull_cycle(self):
        """执行一轮Pull操作"""
        try:
            # 等待repo-manager进程空闲
            self._wait_for_repo_manager_idle()
            
            # 获取需要Pull的映射
            mappings = self._get_pending_mappings()
            
            if not mappings:
                logger.debug("没有需要Pull的仓库")
                return
            
            logger.info(f"开始Pull操作，共 {len(mappings)} 个仓库")
            
            # 并发执行Pull操作
            threads = []
            for mapping in mappings:
                thread = threading.Thread(
                    target=self._pull_repository_thread,
                    args=(mapping,),
                    daemon=True
                )
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            # 清理旧日志
            self._cleanup_old_logs()
            
            logger.info("Pull操作循环完成")
            
        except Exception as e:
            logger.error(f"Pull循环执行失败: {e}")
    
    def _get_pending_mappings(self) -> List[FolderRepoMapping]:
        """获取需要Pull的映射"""
        try:
            all_mappings = self.db_manager.get_auto_pull_mappings()
            pending_mappings = []
            
            now = datetime.now()
            pull_interval = timedelta(minutes=self.config.pull_interval_minutes)
            retry_interval = timedelta(minutes=self.config.retry_failed_after_minutes)
            
            for mapping in all_mappings:
                if not mapping.auto_pull_enabled:
                    continue
                
                # 检查是否到了Pull时间
                should_pull = False
                
                if mapping.last_pull_at is None:
                    # 从未Pull过
                    should_pull = True
                else:
                    last_pull = datetime.fromisoformat(mapping.last_pull_at)
                    
                    if mapping.pull_status == 'success':
                        # 成功的，按正常间隔Pull
                        should_pull = now - last_pull >= pull_interval
                    elif mapping.pull_status in ['failed', 'conflict']:
                        # 失败的，按重试间隔Pull
                        should_pull = now - last_pull >= retry_interval
                    else:
                        # 其他状态，按正常间隔Pull
                        should_pull = now - last_pull >= pull_interval
                
                if should_pull:
                    pending_mappings.append(mapping)
            
            return pending_mappings
            
        except Exception as e:
            logger.error(f"获取待Pull映射失败: {e}")
            return []
    
    def _pull_repository_thread(self, mapping: FolderRepoMapping):
        """在线程中Pull仓库"""
        with self._pull_semaphore:
            try:
                logger.info(f"开始Pull: {mapping.repo_name} -> {mapping.repo_path}")
                
                # 检查仓库路径是否存在
                if not os.path.exists(mapping.repo_path):
                    logger.error(f"仓库路径不存在: {mapping.repo_path}")
                    self.db_manager.update_pull_status(
                        mapping.id, 
                        'failed', 
                        f"仓库路径不存在: {mapping.repo_path}"
                    )
                    return
                
                # 执行Pull操作
                result = self.git_service.pull_repository(mapping.repo_path, mapping.branch)
                
                if result.success:
                    logger.info(f"Pull成功: {mapping.repo_name}")
                    self.db_manager.update_pull_status(
                        mapping.id, 
                        'success', 
                        result.message
                    )
                else:
                    logger.error(f"Pull失败: {mapping.repo_name} - {result.message}")
                    status = 'conflict' if result.conflicts else 'failed'
                    self.db_manager.update_pull_status(
                        mapping.id, 
                        status, 
                        result.message
                    )
                
            except Exception as e:
                logger.error(f"Pull线程异常 {mapping.repo_name}: {e}")
                self.db_manager.update_pull_status(
                    mapping.id, 
                    'failed', 
                    f"Pull线程异常: {str(e)}"
                )
    
    def _cleanup_old_logs(self):
        """清理旧日志"""
        try:
            self.db_manager.cleanup_old_logs(self.config.cleanup_logs_days)
        except Exception as e:
            logger.error(f"清理旧日志失败: {e}")
    
    def force_pull_all(self):
        """强制Pull所有启用的仓库"""
        try:
            mappings = self.db_manager.get_auto_pull_mappings()
            logger.info(f"强制Pull所有仓库，共 {len(mappings)} 个")
            
            threads = []
            for mapping in mappings:
                thread = threading.Thread(
                    target=self._pull_repository_thread,
                    args=(mapping,),
                    daemon=True
                )
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            logger.info("强制Pull操作完成")
            
        except Exception as e:
            logger.error(f"强制Pull失败: {e}")
    
    def force_pull_repository(self, mapping_id: int):
        """强制Pull指定仓库"""
        try:
            mapping = self.db_manager.get_mapping_by_id(mapping_id)
            if not mapping:
                logger.error(f"未找到映射: {mapping_id}")
                return
            
            logger.info(f"强制Pull仓库: {mapping.repo_name}")
            self._pull_repository_thread(mapping)
            
        except Exception as e:
            logger.error(f"强制Pull仓库失败: {e}")
    
    def get_status(self) -> Dict:
        """获取调度器状态"""
        return {
            'running': self._running,
            'config': {
                'pull_interval_minutes': self.config.pull_interval_minutes,
                'max_concurrent_pulls': self.config.max_concurrent_pulls,
                'retry_failed_after_minutes': self.config.retry_failed_after_minutes,
                'cleanup_logs_days': self.config.cleanup_logs_days
            },
            'thread_alive': self._thread.is_alive() if self._thread else False
        }
    
    def update_config(self, new_config: SchedulerConfig):
        """更新配置"""
        self.config = new_config
        logger.info(f"更新调度器配置: {new_config}")
    
    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._running
    
    def run_once(self):
        """执行一次Pull操作（用于测试）"""
        logger.info("执行一次Pull操作")
        self._execute_pull_cycle()