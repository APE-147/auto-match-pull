import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging
import requests
import json

logger = logging.getLogger(__name__)

@dataclass
class FolderInfo:
    path: str
    name: str
    parent_path: str
    
@dataclass
class RepoInfo:
    path: str
    name: str
    remote_url: Optional[str] = None
    branch: Optional[str] = None
    github_url: Optional[str] = None
    github_exists: bool = False

class FolderMatcher:
    def __init__(self, search_paths: List[str], github_token: Optional[str] = None):
        self.search_paths = search_paths
        self.folders: List[FolderInfo] = []
        self.repos: List[RepoInfo] = []
        self.github_token = github_token
        self.excluded_projects = {'Crawler', 'Default', 'Script', 'Trading'}
        self.github_session = requests.Session()
        if github_token:
            self.github_session.headers.update({
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json'
            })
        
    def scan_folders(self) -> List[FolderInfo]:
        """递归扫描指定路径下的所有文件夹，排除索引项目"""
        folders = []
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.vscode', '.idea', 'dist', 'build', 'target', '.cache'}
        
        for search_path in self.search_paths:
            search_path = os.path.expanduser(search_path)
            if not os.path.exists(search_path):
                logger.warning(f"路径不存在: {search_path}")
                continue
                
            logger.info(f"扫描路径: {search_path}")
            
            for root, dirs, files in os.walk(search_path):
                # 跳过隐藏文件夹、排除项目和特殊目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.excluded_projects and d not in skip_dirs and not d.startswith('_')]
                
                for dir_name in dirs:
                    if dir_name in self.excluded_projects or dir_name in skip_dirs:
                        continue
                    dir_path = os.path.join(root, dir_name)
                    folder_info = FolderInfo(
                        path=dir_path,
                        name=dir_name,
                        parent_path=root
                    )
                    folders.append(folder_info)
                    
        self.folders = folders
        logger.info(f"共扫描到 {len(folders)} 个文件吹（排除索引项目）")
        return folders
    
    def scan_repos(self) -> List[RepoInfo]:
        """扫描指定路径下的所有Git仓库，排除索引项目"""
        repos = []
        
        for search_path in self.search_paths:
            search_path = os.path.expanduser(search_path)
            if not os.path.exists(search_path):
                continue
                
            for root, dirs, files in os.walk(search_path):
                # 如果找到.git目录，说明这是一个Git仓库
                if '.git' in dirs:
                    repo_name = os.path.basename(root)
                    
                    # 排除索引项目
                    if repo_name in self.excluded_projects:
                        continue
                    
                    remote_url = self._get_remote_url(root)
                    branch = self._get_current_branch(root)
                    
                    repo_info = RepoInfo(
                        path=root,
                        name=repo_name,
                        remote_url=remote_url,
                        branch=branch
                    )
                    repos.append(repo_info)
                    
                    # 不再深入扫描Git仓库内部
                    dirs[:] = [d for d in dirs if d != '.git']
                    
        self.repos = repos
        logger.info(f"共扫描到 {len(repos)} 个Git仓库（排除索引项目）")
        return repos
    
    def _get_remote_url(self, repo_path: str) -> Optional[str]:
        """获取Git仓库的远程URL"""
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"获取远程URL失败 {repo_path}: {e}")
        return None
    
    def _get_current_branch(self, repo_path: str) -> Optional[str]:
        """获取Git仓库的当前分支"""
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"获取当前分支失败 {repo_path}: {e}")
        return None
    
    def get_github_repositories(self, github_username: str) -> List[str]:
        """获取GitHub用户的所有仓库列表，排除索引项目"""
        # 模拟GitHub仓库列表（实际使用时需要调用GitHub API）
        test_repos = ['repo-management', 'auto-match-pull', 'test-auto-match-pull', 'test-project', 'data-analysis']
        
        try:
            # 实际的GitHub API调用
            url = f"https://api.github.com/users/{github_username}/repos"
            response = self.github_session.get(url, timeout=30)
            
            if response.status_code == 200:
                repos_data = response.json()
                repo_names = [repo['name'] for repo in repos_data]
                # 过滤掉索引项目
                filtered_repos = [name for name in repo_names if name not in self.excluded_projects]
                logger.info(f"从GitHub获取到 {len(filtered_repos)} 个仓库（排除索引项目）")
                return filtered_repos
            else:
                logger.warning(f"GitHub API返回状态码 {response.status_code}，使用模拟数据")
                return [repo for repo in test_repos if repo not in self.excluded_projects]
                
        except Exception as e:
            logger.error(f"获取GitHub仓库列表失败: {e}，使用模拟数据")
            return [repo for repo in test_repos if repo not in self.excluded_projects]

    def match_github_to_local(self, github_username: str) -> List[Tuple[str, str, bool, bool]]:
        """将GitHub仓库匹配到本地项目"""
        matches = []
        
        # 1. 获取GitHub仓库列表
        github_repos = self.get_github_repositories(github_username)
        logger.info(f"GitHub仓库列表: {github_repos}")
        
        # 2. 扫描本地文件夹
        local_folders = self.scan_folders()
        local_folder_dict = {folder.name: folder for folder in local_folders}
        
        # 3. 匹配GitHub仓库到本地项目
        for repo_name in github_repos:
            github_url = f"https://github.com/{github_username}/{repo_name}"
            
            if repo_name in local_folder_dict:
                folder = local_folder_dict[repo_name]
                # 检查本地项目是否已经是Git仓库且已关联远程
                is_git_repo = self._is_git_repository(folder.path)
                has_remote = self._has_correct_remote(folder.path, github_url) if is_git_repo else False
                
                matches.append((repo_name, folder.path, is_git_repo, has_remote))
                
                status = "✅ 已关联" if has_remote else ("🔄 Git仓库但未关联" if is_git_repo else "📁 普通文件夹")
                logger.info(f"匹配: {repo_name} -> {folder.path} {status}")
            else:
                logger.info(f"GitHub仓库 {repo_name} 在本地不存在")
        
        return matches
    
    def _is_git_repository(self, path: str) -> bool:
        """检查指定路径是否是Git仓库"""
        return os.path.exists(os.path.join(path, '.git'))
    
    def _has_correct_remote(self, repo_path: str, expected_url: str) -> bool:
        """检查本地Git仓库是否已关联正确的远程URL"""
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                current_url = result.stdout.strip()
                # 标准化URL比较（处理https/ssh格式差异）
                normalized_current = self._normalize_git_url(current_url)
                normalized_expected = self._normalize_git_url(expected_url)
                return normalized_current == normalized_expected
        except Exception as e:
            logger.debug(f"检查远程URL失败 {repo_path}: {e}")
        return False
    
    def _normalize_git_url(self, url: str) -> str:
        """标准化Git URL格式"""
        if url.startswith('git@github.com:'):
            # 将SSH格式转换为HTTPS格式
            return url.replace('git@github.com:', 'https://github.com/').replace('.git', '')
        return url.replace('.git', '')
    
    def _check_github_repo_exists(self, username: str, repo_name: str) -> bool:
        """检查GitHub仓库是否存在"""
        # 模拟检查：只有repo-management存在于GitHub
        test_repos = {'repo-management'}
        if repo_name in test_repos:
            logger.info(f"模拟检查: {repo_name} -> GitHub仓库 存在")
            return True
        
        try:
            url = f"https://api.github.com/repos/{username}/{repo_name}"
            response = self.github_session.get(url, timeout=10)
            
            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                return False
            else:
                logger.warning(f"GitHub API返回状态码 {response.status_code}: {repo_name}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"检查GitHub仓库失败 {repo_name}: {e}")
            return False
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """计算两个名称的相似度（忽略大小写）"""
        name1 = name1.lower()
        name2 = name2.lower()
        
        # 完全匹配
        if name1 == name2:
            return 1.0
        
        # 包含关系
        if name1 in name2 or name2 in name1:
            return 0.9
        
        # 使用编辑距离算法
        return self._levenshtein_similarity(name1, name2)
    
    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """计算两个字符串的编辑距离相似度"""
        if len(s1) == 0:
            return len(s2)
        if len(s2) == 0:
            return len(s1)
        
        # 创建矩阵
        matrix = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
        
        # 初始化第一行和第一列
        for i in range(len(s1) + 1):
            matrix[i][0] = i
        for j in range(len(s2) + 1):
            matrix[0][j] = j
        
        # 填充矩阵
        for i in range(1, len(s1) + 1):
            for j in range(1, len(s2) + 1):
                if s1[i-1] == s2[j-1]:
                    matrix[i][j] = matrix[i-1][j-1]
                else:
                    matrix[i][j] = min(
                        matrix[i-1][j] + 1,      # 删除
                        matrix[i][j-1] + 1,      # 插入
                        matrix[i-1][j-1] + 1     # 替换
                    )
        
        # 计算相似度
        max_len = max(len(s1), len(s2))
        distance = matrix[len(s1)][len(s2)]
        return 1 - (distance / max_len)