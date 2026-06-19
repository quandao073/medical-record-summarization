"""Health-check endpoints for liveness, readiness, and circuit-breaker status."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.llm.circuit_breaker import CircuitState

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"


@router.get("/health")
def liveness():
    """Liveness probe — returns 200 if the process is alive."""
    return {"status": "alive", "timestamp": datetime.now().isoformat()}


@router.get("/health/ready")
def readiness():
    """Readiness probe — returns 200 only when the service can serve traffic."""
    checks: dict[str, dict] = {}
    overall_healthy = True

    # Check 1: LLM circuit breaker
    try:
        from src.c4_llm_draft.summarizer import get_circuit_breaker

        cb = get_circuit_breaker()
        cb_state = cb.get_state()
        if cb.state == CircuitState.OPEN:
            checks["llm"] = {"status": "degraded", "detail": cb_state}
        else:
            checks["llm"] = {"status": "healthy", "detail": cb_state}
    except Exception as e:
        checks["llm"] = {"status": "unknown", "error": str(e)}

    # Check 2: disk space
    try:
        stat = shutil.disk_usage(ROOT)
        free_gb = stat.free / (1024 ** 3)
        if free_gb < 0.5:
            checks["disk"] = {"status": "critical", "free_gb": round(free_gb, 2)}
            overall_healthy = False
        elif free_gb < 2:
            checks["disk"] = {"status": "warning", "free_gb": round(free_gb, 2)}
        else:
            checks["disk"] = {"status": "healthy", "free_gb": round(free_gb, 2)}
    except Exception as e:
        checks["disk"] = {"status": "unknown", "error": str(e)}

    # Check 3: data directory
    if ASSEMBLED_DIR.exists():
        patient_count = len(list(ASSEMBLED_DIR.glob("*.json")))
        checks["data"] = {"status": "healthy", "patients": patient_count}
    else:
        checks["data"] = {"status": "warning", "message": "No assembled data directory"}

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if overall_healthy else "not_ready",
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
        },
    )


@router.get("/health/circuit-breakers")
def circuit_breaker_status():
    """Admin view of all circuit-breaker states."""
    try:
        from src.c4_llm_draft.summarizer import get_circuit_breaker

        cb = get_circuit_breaker()
        return {"circuit_breakers": [cb.get_state()]}
    except Exception as e:
        return {"circuit_breakers": [], "error": str(e)}


@router.post("/health/circuit-breakers/reset")
def reset_circuit_breaker():
    """Manually reset the LLM circuit breaker."""
    from src.c4_llm_draft.summarizer import get_circuit_breaker

    cb = get_circuit_breaker()
    cb.reset()
    return {"status": "reset", "name": cb.name}
