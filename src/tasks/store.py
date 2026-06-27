"""In-memory task store for background summary generation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    patient_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: dict | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None


class TaskStore:
    """Simple in-memory task store. NOT for production (no persistence, no cleanup)."""

    def __init__(self, max_tasks: int = 100):
        self._tasks: dict[str, TaskRecord] = {}
        self._max_tasks = max_tasks
        self._patient_tasks: dict[str, str] = {}

    def create(self, patient_id: str) -> TaskRecord:
        existing_id = self._patient_tasks.get(patient_id)
        if existing_id and existing_id in self._tasks:
            existing = self._tasks[existing_id]
            if existing.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                return existing

        if len(self._tasks) >= self._max_tasks:
            oldest_key = next(iter(self._tasks))
            del self._tasks[oldest_key]

        task = TaskRecord(patient_id=patient_id)
        self._tasks[task.task_id] = task
        self._patient_tasks[patient_id] = task.task_id
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for k, v in kwargs.items():
            setattr(task, k, v)
        return task
