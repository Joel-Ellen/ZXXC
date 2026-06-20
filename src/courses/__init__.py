# -*- coding: utf-8 -*-
"""
EduAgent Course Management Layer
=================================
课程数据模型、持久化存储与注册管理。
"""

from .models import CourseRecord
from .store import CourseStore

__all__ = ["CourseRecord", "CourseStore"]
