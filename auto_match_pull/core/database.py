import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class FolderRepoMapping:
    id: Optional[int] = None
    folder_path: str = ""
    folder_name: str = ""
    repo_path: str = ""
    repo_name: str = ""
    remote_url: Optional[str] = None
    branch: str = "main"
    similarity_score: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_pull_at: Optional[str] = None
    pull_status: str = "pending"  # pending, success, failed, conflict
    auto_pull_enabled: bool = True
    github_url: Optional[str] = None  # GitHub仓库URL
    github_exists: bool = False  # GitHub仓库是否存在

class DatabaseManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认存储在项目文件夹的data目录下
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(project_dir, "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "mappings.db")
        
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建映射表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS folder_repo_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_path TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    repo_name TEXT NOT NULL,
                    remote_url TEXT,
                    branch TEXT DEFAULT 'main',
                    similarity_score REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_pull_at TEXT,
                    pull_status TEXT DEFAULT 'pending',
                    auto_pull_enabled INTEGER DEFAULT 1,
                    github_url TEXT,
                    github_exists INTEGER DEFAULT 0,
                    UNIQUE(folder_path, repo_path)
                )
            ''')
            
            # 为已有表添加新字段（如果不存在）
            try:
                cursor.execute('ALTER TABLE folder_repo_mappings ADD COLUMN github_url TEXT')
            except sqlite3.OperationalError:
                pass  # 字段已存在
            
            try:
                cursor.execute('ALTER TABLE folder_repo_mappings ADD COLUMN github_exists INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # 字段已存在
            
            # 创建日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pull_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mapping_id INTEGER,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mapping_id) REFERENCES folder_repo_mappings (id)
                )
            ''')
            
            # 创建配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configurations (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info(f"数据库初始化完成: {self.db_path}")
    
    def save_mapping(self, mapping: FolderRepoMapping) -> int:
        """保存或更新文件夹与仓库的映射关系"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if mapping.id is None:
                # 新增
                cursor.execute('''
                    INSERT OR REPLACE INTO folder_repo_mappings 
                    (folder_path, folder_name, repo_path, repo_name, remote_url, 
                     branch, similarity_score, auto_pull_enabled, github_url, github_exists)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    mapping.folder_path, mapping.folder_name, 
                    mapping.repo_path, mapping.repo_name, 
                    mapping.remote_url, mapping.branch,
                    mapping.similarity_score, mapping.auto_pull_enabled,
                    mapping.github_url, mapping.github_exists
                ))
                mapping.id = cursor.lastrowid
            else:
                # 更新
                cursor.execute('''
                    UPDATE folder_repo_mappings 
                    SET folder_path=?, folder_name=?, repo_path=?, repo_name=?, 
                        remote_url=?, branch=?, similarity_score=?, 
                        auto_pull_enabled=?, github_url=?, github_exists=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                ''', (
                    mapping.folder_path, mapping.folder_name, 
                    mapping.repo_path, mapping.repo_name, 
                    mapping.remote_url, mapping.branch,
                    mapping.similarity_score, mapping.auto_pull_enabled,
                    mapping.github_url, mapping.github_exists,
                    mapping.id
                ))
            
            conn.commit()
            logger.info(f"保存映射: {mapping.folder_name} -> {mapping.repo_name}")
            return mapping.id
    
    def get_all_mappings(self) -> List[FolderRepoMapping]:
        """获取所有映射关系"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM folder_repo_mappings ORDER BY created_at DESC')
            rows = cursor.fetchall()
            
            mappings = []
            for row in rows:
                mapping = FolderRepoMapping(
                    id=row[0], folder_path=row[1], folder_name=row[2],
                    repo_path=row[3], repo_name=row[4], remote_url=row[5],
                    branch=row[6], similarity_score=row[7],
                    created_at=row[8], updated_at=row[9], last_pull_at=row[10],
                    pull_status=row[11], auto_pull_enabled=bool(row[12]),
                    github_url=row[13] if len(row) > 13 else None,
                    github_exists=bool(row[14]) if len(row) > 14 else False
                )
                mappings.append(mapping)
            
            return mappings
    
    def get_mapping_by_id(self, mapping_id: int) -> Optional[FolderRepoMapping]:
        """根据ID获取映射关系"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM folder_repo_mappings WHERE id=?', (mapping_id,))
            row = cursor.fetchone()
            
            if row:
                return FolderRepoMapping(
                    id=row[0], folder_path=row[1], folder_name=row[2],
                    repo_path=row[3], repo_name=row[4], remote_url=row[5],
                    branch=row[6], similarity_score=row[7],
                    created_at=row[8], updated_at=row[9], last_pull_at=row[10],
                    pull_status=row[11], auto_pull_enabled=bool(row[12]),
                    github_url=row[13] if len(row) > 13 else None,
                    github_exists=bool(row[14]) if len(row) > 14 else False
                )
            return None
    
    def get_auto_pull_mappings(self) -> List[FolderRepoMapping]:
        """获取启用自动Pull的映射关系"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM folder_repo_mappings 
                WHERE auto_pull_enabled=1 
                ORDER BY last_pull_at ASC
            ''')
            rows = cursor.fetchall()
            
            mappings = []
            for row in rows:
                mapping = FolderRepoMapping(
                    id=row[0], folder_path=row[1], folder_name=row[2],
                    repo_path=row[3], repo_name=row[4], remote_url=row[5],
                    branch=row[6], similarity_score=row[7],
                    created_at=row[8], updated_at=row[9], last_pull_at=row[10],
                    pull_status=row[11], auto_pull_enabled=bool(row[12]),
                    github_url=row[13] if len(row) > 13 else None,
                    github_exists=bool(row[14]) if len(row) > 14 else False
                )
                mappings.append(mapping)
            
            return mappings
    
    def update_pull_status(self, mapping_id: int, status: str, message: str = None):
        """更新Pull状态"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 更新映射表
            cursor.execute('''
                UPDATE folder_repo_mappings 
                SET pull_status=?, last_pull_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            ''', (status, mapping_id))
            
            # 记录日志
            cursor.execute('''
                INSERT INTO pull_logs (mapping_id, action, status, message)
                VALUES (?, ?, ?, ?)
            ''', (mapping_id, 'pull', status, message))
            
            conn.commit()
    
    def get_pull_logs(self, mapping_id: int = None, limit: int = 50) -> List[Dict]:
        """获取Pull日志"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if mapping_id:
                cursor.execute('''
                    SELECT * FROM pull_logs 
                    WHERE mapping_id=? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (mapping_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM pull_logs 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            logs = []
            for row in rows:
                log = {
                    'id': row[0],
                    'mapping_id': row[1],
                    'action': row[2],
                    'status': row[3],
                    'message': row[4],
                    'timestamp': row[5]
                }
                logs.append(log)
            
            return logs
    
    def delete_mapping(self, mapping_id: int) -> bool:
        """删除映射关系"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 删除相关日志
            cursor.execute('DELETE FROM pull_logs WHERE mapping_id=?', (mapping_id,))
            
            # 删除映射
            cursor.execute('DELETE FROM folder_repo_mappings WHERE id=?', (mapping_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def set_config(self, key: str, value: str):
        """设置配置"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO configurations (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()
    
    def get_config(self, key: str, default: str = None) -> str:
        """获取配置"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM configurations WHERE key=?', (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    
    def cleanup_old_logs(self, keep_days: int = 30):
        """清理旧日志"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM pull_logs 
                WHERE timestamp < datetime('now', '-{} days')
            '''.format(keep_days))
            conn.commit()
            logger.info(f"清理了 {cursor.rowcount} 条旧日志")