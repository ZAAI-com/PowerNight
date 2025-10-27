"""
PowerNight Planner Module

Provides task planning and automation functionality for PowerNight.
"""

from .planner import Planner, get_planner
from .task_executor import TaskExecutor, TaskManager, get_task_manager

# Backwards compatibility aliases (will be removed in future version)
from .task_executor import TaskExecutor, TaskManager, get_task_manager

__all__ = [
    # V2 Planner components
    'Planner',
    'get_planner',
    'TaskExecutor',
    'TaskManager',
    'get_task_manager',

    # Backwards compatibility (deprecated)
    'TaskExecutor',
    'TaskManager',
    'get_task_manager',
]
