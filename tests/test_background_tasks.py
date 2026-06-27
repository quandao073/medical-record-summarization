"""Tests for in-memory task store and background generation."""

from __future__ import annotations

import pytest

from src.tasks.store import TaskStore, TaskStatus, TaskRecord


class TestTaskRecord:
    def test_default_status_is_pending(self):
        task = TaskRecord(patient_id="P001")
        assert task.status == TaskStatus.PENDING

    def test_task_id_auto_generated(self):
        t1 = TaskRecord(patient_id="P001")
        t2 = TaskRecord(patient_id="P001")
        assert t1.task_id != t2.task_id

    def test_created_at_populated(self):
        task = TaskRecord(patient_id="P001")
        assert task.created_at is not None


class TestTaskStore:
    def test_create_returns_pending_task(self):
        store = TaskStore()
        task = store.create("P001")
        assert task.status == TaskStatus.PENDING
        assert task.patient_id == "P001"

    def test_get_returns_task(self):
        store = TaskStore()
        task = store.create("P001")
        fetched = store.get(task.task_id)
        assert fetched is not None
        assert fetched.task_id == task.task_id

    def test_get_missing_returns_none(self):
        store = TaskStore()
        assert store.get("nonexistent") is None

    def test_dedup_returns_existing_pending(self):
        store = TaskStore()
        t1 = store.create("P001")
        t2 = store.create("P001")
        assert t1.task_id == t2.task_id

    def test_dedup_allows_new_after_ready(self):
        store = TaskStore()
        t1 = store.create("P001")
        store.update(t1.task_id, status=TaskStatus.READY)
        t2 = store.create("P001")
        assert t1.task_id != t2.task_id

    def test_dedup_allows_new_after_failed(self):
        store = TaskStore()
        t1 = store.create("P001")
        store.update(t1.task_id, status=TaskStatus.FAILED)
        t2 = store.create("P001")
        assert t1.task_id != t2.task_id

    def test_update_status(self):
        store = TaskStore()
        task = store.create("P001")
        store.update(task.task_id, status=TaskStatus.PROCESSING)
        assert store.get(task.task_id).status == TaskStatus.PROCESSING

    def test_update_result(self):
        store = TaskStore()
        task = store.create("P001")
        result = {"sections": [], "patient_id": "P001"}
        store.update(task.task_id, status=TaskStatus.READY, result=result)
        fetched = store.get(task.task_id)
        assert fetched.status == TaskStatus.READY
        assert fetched.result == result

    def test_update_missing_returns_none(self):
        store = TaskStore()
        assert store.update("nonexistent", status=TaskStatus.READY) is None

    def test_eviction_when_full(self):
        store = TaskStore(max_tasks=2)
        store.create("P001")
        store.create("P002")
        store.create("P003")
        assert len(store._tasks) == 2

    def test_different_patients_get_different_tasks(self):
        store = TaskStore()
        t1 = store.create("P001")
        t2 = store.create("P002")
        assert t1.task_id != t2.task_id
