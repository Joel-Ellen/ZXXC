# -*- coding: utf-8 -*-
"""
课程持久化存储
=============
JSON 文件持久化 + 线程安全读写。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional

from .models import CourseRecord


class CourseStore:
    """JSON 文件持久化课程存储。

    线程安全 (RLock)，支持按 ID 查找和关键词搜索。
    """

    DEFAULT_STORE_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_courses.json"
    )

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file_path = file_path or self.DEFAULT_STORE_PATH
        self._lock = threading.RLock()
        self._courses: Dict[str, CourseRecord] = {}
        self._load()
        self._ensure_seed()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_courses(self, search: Optional[str] = None) -> List[CourseRecord]:
        """列出所有课程，支持关键词搜索。

        Args:
            search: 可选搜索词，匹配 title / title_cn / tags。

        Returns:
            匹配的课程列表。
        """
        with self._lock:
            courses = list(self._courses.values())
            if search:
                keyword = search.lower().strip()
                courses = [
                    c for c in courses
                    if keyword in c.title.lower()
                    or keyword in c.title_cn.lower()
                    or any(keyword in t.lower() for t in c.tags)
                ]
            return sorted(courses, key=lambda c: c.difficulty)

    def get_by_id(self, course_id: str) -> Optional[CourseRecord]:
        """按课程 ID 查找。"""
        with self._lock:
            return self._courses.get(course_id)

    def count(self) -> int:
        with self._lock:
            return len(self._courses)

    def add_course(self, record: CourseRecord) -> CourseRecord:
        """添加新课程。"""
        with self._lock:
            self._courses[record.course_id] = record
            self._save()
            return record

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            self._courses = {}
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._courses = {
                cid: CourseRecord(**rec) for cid, rec in data.items()
            }
        except (json.JSONDecodeError, KeyError):
            self._courses = {}

    def _save(self) -> None:
        data = {cid: rec.model_dump() for cid, rec in self._courses.items()}
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _ensure_seed(self) -> None:
        """确保预设课程存在（首次启动时自动创建）。"""
        if self._courses:
            return
        from .seed import SEED_COURSES
        for data in SEED_COURSES:
            record = CourseRecord(**data)
            self._courses[record.course_id] = record
        self._save()
