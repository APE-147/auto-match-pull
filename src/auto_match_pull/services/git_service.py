import subprocess
import os
import re
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class GitStatus:
    is_clean: bool
    has_conflicts: bool
    ahead_commits: int
    behind_commits: int
    untracked_files: List[str]
    modified_files: List[str]
    staged_files: List[str]

@dataclass
class PullResult:
    success: bool
    message: str
    conflicts: List[str]
    auto_resolved: bool = False

class GitService:
    def __init__(self, timeout: int = 30, conflict_strategy: str = 'smart_merge'):
        self.timeout = timeout
        self.conflict_strategy = conflict_strategy
    
    def check_git_available(self) -> bool:
        """检查Git是否可用"""
        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_repo_status(self, repo_path: str) -> GitStatus:
        """获取仓库状态"""
        if not os.path.exists(repo_path):
            raise ValueError(f"仓库路径不存在: {repo_path}")
        
        try:
            # 检查是否为Git仓库
            result = subprocess.run(
                ['git', 'rev-parse', '--is-inside-work-tree'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode != 0:
                raise ValueError(f"不是Git仓库: {repo_path}")
            
            # 获取状态信息
            status_result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # 解析状态
            untracked_files = []
            modified_files = []
            staged_files = []
            has_conflicts = False
            
            for line in status_result.stdout.splitlines():
                if line.startswith('??'):
                    untracked_files.append(line[3:])
                elif line.startswith(' M'):
                    modified_files.append(line[3:])
                elif line.startswith('M '):
                    staged_files.append(line[3:])
                elif line.startswith('UU') or line.startswith('AA'):
                    has_conflicts = True
                    modified_files.append(line[3:])
            
            # 检查远程同步状态
            ahead_commits, behind_commits = self._get_sync_status(repo_path)
            
            return GitStatus(
                is_clean=len(untracked_files) == 0 and len(modified_files) == 0,
                has_conflicts=has_conflicts,
                ahead_commits=ahead_commits,
                behind_commits=behind_commits,
                untracked_files=untracked_files,
                modified_files=modified_files,
                staged_files=staged_files
            )
            
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Git操作超时: {repo_path}")
        except Exception as e:
            logger.error(f"获取仓库状态失败 {repo_path}: {e}")
            raise
    
    def _get_sync_status(self, repo_path: str) -> Tuple[int, int]:
        """获取与远程的同步状态"""
        try:
            # 先fetch最新信息
            subprocess.run(
                ['git', 'fetch', '--quiet'],
                cwd=repo_path,
                capture_output=True,
                timeout=self.timeout
            )
            
            # 获取ahead/behind信息
            result = subprocess.run(
                ['git', 'rev-list', '--count', '--left-right', 'HEAD...@{u}'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                counts = result.stdout.strip().split('\t')
                if len(counts) == 2:
                    return int(counts[0]), int(counts[1])
            
            return 0, 0
            
        except Exception as e:
            logger.debug(f"获取同步状态失败 {repo_path}: {e}")
            return 0, 0
    
    def pull_repository(self, repo_path: str, branch: str = None) -> PullResult:
        """拉取仓库更新"""
        if not os.path.exists(repo_path):
            return PullResult(False, f"仓库路径不存在: {repo_path}", [])
        
        try:
            # 检查仓库状态
            status = self.get_repo_status(repo_path)
            
            # 如果有冲突，先尝试解决
            if status.has_conflicts:
                logger.info(f"检测到冲突，尝试自动解决: {repo_path}")
                conflicts = self._resolve_conflicts(repo_path)
                if conflicts:
                    return PullResult(False, f"存在无法自动解决的冲突: {', '.join(conflicts)}", conflicts)
            
            # 如果有未提交的更改，先暂存
            stashed = False
            if not status.is_clean:
                logger.info(f"发现未提交更改，先暂存: {repo_path}")
                stash_result = subprocess.run(
                    ['git', 'stash', 'push', '-m', 'Auto-stash before pull'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                if stash_result.returncode == 0:
                    stashed = True
                else:
                    logger.warning(f"暂存失败: {stash_result.stderr}")
            
            # 执行pull
            pull_cmd = ['git', 'pull']
            if branch:
                pull_cmd.extend(['origin', branch])
            
            pull_result = subprocess.run(
                pull_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # 检查pull结果
            if pull_result.returncode == 0:
                message = pull_result.stdout.strip()
                
                # 如果之前有暂存，尝试恢复
                if stashed:
                    subprocess.run(
                        ['git', 'stash', 'pop'],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=self.timeout
                    )
                
                return PullResult(True, message, [])
            else:
                # Pull失败，检查是否是冲突
                if 'conflict' in pull_result.stderr.lower():
                    conflicts = self._parse_conflicts(pull_result.stderr)
                    return PullResult(False, f"Pull冲突: {pull_result.stderr}", conflicts)
                else:
                    return PullResult(False, f"Pull失败: {pull_result.stderr}", [])
                    
        except subprocess.TimeoutExpired:
            return PullResult(False, f"Pull操作超时: {repo_path}", [])
        except Exception as e:
            logger.error(f"Pull操作失败 {repo_path}: {e}")
            return PullResult(False, f"Pull操作异常: {str(e)}", [])
    
    def _resolve_conflicts(self, repo_path: str) -> List[str]:
        """尝试自动解决冲突"""
        try:
            # 获取冲突文件列表
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--diff-filter=U'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            conflict_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
            unresolved_conflicts = []
            
            for file_path in conflict_files:
                if not file_path:
                    continue
                    
                full_path = os.path.join(repo_path, file_path)
                if self._try_resolve_conflict(full_path, self.conflict_strategy):
                    # 标记为已解决
                    subprocess.run(
                        ['git', 'add', file_path],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=self.timeout
                    )
                    logger.info(f"自动解决冲突: {file_path}")
                else:
                    unresolved_conflicts.append(file_path)
            
            return unresolved_conflicts
            
        except Exception as e:
            logger.error(f"解决冲突失败: {e}")
            return conflict_files if 'conflict_files' in locals() else []
    
    def _try_resolve_conflict(self, file_path: str, strategy: str = 'keep_both') -> bool:
        """尝试自动解决单个文件的冲突
        
        Args:
            file_path: 冲突文件路径
            strategy: 解决策略 ('keep_both', 'keep_local', 'keep_remote', 'smart_merge')
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否有冲突标记
            if '<<<<<<< HEAD' not in content:
                return True
            
            if strategy == 'smart_merge':
                return self._smart_merge_conflict(file_path, content)
            elif strategy == 'keep_both':
                return self._resolve_keep_both(file_path, content)
            elif strategy == 'keep_local':
                return self._resolve_keep_local(file_path, content)
            elif strategy == 'keep_remote':
                return self._resolve_keep_remote(file_path, content)
            else:
                logger.warning(f"未知的冲突解决策略: {strategy}, 使用keep_both")
                return self._resolve_keep_both(file_path, content)
            
        except Exception as e:
            logger.error(f"解决文件冲突失败 {file_path}: {e}")
            return False
    
    def _resolve_keep_both(self, file_path: str, content: str) -> bool:
        """保留双方更改的冲突解决策略"""
        lines = content.split('\n')
        resolved_lines = []
        in_conflict = False
        local_lines = []
        remote_lines = []
        in_remote_section = False
        
        for line in lines:
            if line.startswith('<<<<<<< HEAD'):
                in_conflict = True
                in_remote_section = False
                local_lines = []
                remote_lines = []
                resolved_lines.append("# ============ 合并冲突 ============")
                resolved_lines.append("# 本地版本:")
                continue
            elif line.startswith('======='):
                in_remote_section = True
                resolved_lines.extend(local_lines)
                resolved_lines.append("# 远程版本:")
                continue
            elif line.startswith('>>>>>>> '):
                resolved_lines.extend(remote_lines)
                resolved_lines.append("# ================================")
                in_conflict = False
                in_remote_section = False
                continue
            elif not in_conflict:
                resolved_lines.append(line)
            elif in_conflict and not in_remote_section:
                local_lines.append(line)
            elif in_conflict and in_remote_section:
                remote_lines.append(line)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(resolved_lines))
        
        logger.info(f"自动解决冲突，保留双方更改: {file_path}")
        return True
    
    def _resolve_keep_local(self, file_path: str, content: str) -> bool:
        """保留本地版本的冲突解决策略"""
        lines = content.split('\n')
        resolved_lines = []
        in_conflict = False
        in_remote_section = False
        
        for line in lines:
            if line.startswith('<<<<<<< HEAD'):
                in_conflict = True
                in_remote_section = False
                continue
            elif line.startswith('======='):
                # 切换到远程版本区域，开始跳过
                in_remote_section = True
                continue
            elif line.startswith('>>>>>>> '):
                in_conflict = False
                in_remote_section = False
                continue
            elif not in_conflict:
                resolved_lines.append(line)
            elif in_conflict and not in_remote_section:
                # 在冲突区域内且在本地版本部分
                resolved_lines.append(line)
            # 跳过远程版本（in_conflict and in_remote_section的情况）
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(resolved_lines))
        
        logger.info(f"自动解决冲突，保留本地版本: {file_path}")
        return True
    
    def _resolve_keep_remote(self, file_path: str, content: str) -> bool:
        """保留远程版本的冲突解决策略"""
        lines = content.split('\n')
        resolved_lines = []
        in_conflict = False
        in_remote_section = False
        
        for line in lines:
            if line.startswith('<<<<<<< HEAD'):
                in_conflict = True
                in_remote_section = False
                continue
            elif line.startswith('======='):
                in_remote_section = True
                continue
            elif line.startswith('>>>>>>> '):
                in_conflict = False
                in_remote_section = False
                continue
            elif not in_conflict:
                resolved_lines.append(line)
            elif in_conflict and in_remote_section:
                resolved_lines.append(line)
            # 跳过本地版本
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(resolved_lines))
        
        logger.info(f"自动解决冲突，保留远程版本: {file_path}")
        return True
    
    def _smart_merge_conflict(self, file_path: str, content: str) -> bool:
        """智能合并冲突（根据文件类型和内容特征）"""
        # 根据文件扩展名决定策略
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 配置文件倾向于保留本地
        config_files = {'.json', '.yaml', '.yml', '.conf', '.ini', '.toml'}
        if file_ext in config_files:
            logger.info(f"配置文件冲突，保留本地版本: {file_path}")
            return self._resolve_keep_local(file_path, content)
        
        # 文档文件保留双方
        doc_files = {'.md', '.txt', '.rst', '.doc'}
        if file_ext in doc_files:
            logger.info(f"文档文件冲突，保留双方更改: {file_path}")
            return self._resolve_keep_both(file_path, content)
        
        # 代码文件需要更谨慎，默认保留双方供手动review
        logger.info(f"代码文件冲突，保留双方更改: {file_path}")
        return self._resolve_keep_both(file_path, content)
    
    def _parse_conflicts(self, error_message: str) -> List[str]:
        """解析冲突文件列表"""
        conflicts = []
        lines = error_message.split('\n')
        
        for line in lines:
            if 'CONFLICT' in line:
                # 提取文件名
                match = re.search(r'CONFLICT.*?in (.+)', line)
                if match:
                    conflicts.append(match.group(1))
        
        return conflicts
    
    def get_remote_url(self, repo_path: str) -> Optional[str]:
        """获取远程仓库URL"""
        try:
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"获取远程URL失败 {repo_path}: {e}")
        return None
    
    def get_current_branch(self, repo_path: str) -> Optional[str]:
        """获取当前分支"""
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"获取当前分支失败 {repo_path}: {e}")
        return None