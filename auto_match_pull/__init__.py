"""
Auto Match Pull - Automatic folder and Git repository matching and syncing tool
"""

__version__ = "1.0.0"
__author__ = "APE-147"
__description__ = "Automatic folder and Git repository matching and syncing tool"

from .core.matcher import FolderMatcher
from .core.database import DatabaseManager
from .services.git_service import GitService
from .services.scheduler import SchedulerService

__all__ = [
    "FolderMatcher",
    "DatabaseManager", 
    "GitService",
    "SchedulerService"
]