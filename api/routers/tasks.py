"""Background task status endpoint."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """Poll background task status. Returns result when ready."""
    from api.routers.summary import _task_store

    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    response = {
        "task_id": task.task_id,
        "status": task.status,
        "patient_id": task.patient_id,
        "created_at": task.created_at,
    }
    if task.status == "ready":
        response["data"] = task.result
        response["completed_at"] = task.completed_at
    elif task.status == "failed":
        response["error"] = task.error
        response["completed_at"] = task.completed_at
    return response
