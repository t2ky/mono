"""
Data models for the circular rail vehicle management system
"""
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class Action(str, Enum):
    """Vehicle action commands"""
    FORWARD = "forward"
    BACKWARD = "backward"
    STOP = "stop"


class VehicleStatus(str, Enum):
    """Vehicle status states"""
    IDLE = "idle"
    MOVING = "moving"
    WAITING = "waiting"


class ReportEvent(str, Enum):
    """Events that can be reported by vehicles"""
    ARRIVED = "arrived"
    ERROR = "error"


# API Request/Response Models

class CommandResponse(BaseModel):
    """Response for GET /api/v1/vehicles/{car_id}/command"""
    command_id: int
    action: Action
    expected_station: Optional[int] = Field(None, description="Expected next station number")


class VehicleReport(BaseModel):
    """Request body for POST /api/v1/vehicles/{car_id}/report"""
    command_id: int
    event: ReportEvent
    expected_station: int
    detected_station: int
    pattern_confident: bool = False
    mismatch: bool = Field(False, description="True if expected != detected")


class CallRequest(BaseModel):
    """Request body for POST /api/v1/call"""
    station: int = Field(..., ge=1, le=4, description="Target station number (1-4)")
    vehicle: str = Field(..., pattern="^[a-c]$", description="Vehicle ID (a, b, or c)")


class InitializeRequest(BaseModel):
    """Request body for POST /api/v1/initialize"""
    positions: dict[str, int] = Field(
        ...,
        description="Initial positions: {'a': 1, 'b': 2, 'c': 3}",
        example={"a": 1, "b": 2, "c": 3}
    )


# Internal State Models

class VehicleState(BaseModel):
    """Internal state for each vehicle"""
    current_station: Optional[int] = None
    status: VehicleStatus = VehicleStatus.IDLE
    current_command_id: Optional[int] = None


class StationState(BaseModel):
    """Internal state for each station"""
    occupied_by: Optional[str] = None


class PendingCall(BaseModel):
    """Pending vehicle call request"""
    vehicle: str
    target_station: int


class SystemState(BaseModel):
    """Complete system state"""
    vehicles: dict[str, VehicleState] = Field(
        default_factory=lambda: {
            "a": VehicleState(),
            "b": VehicleState(),
            "c": VehicleState()
        }
    )
    stations: dict[int, StationState] = Field(
        default_factory=lambda: {
            1: StationState(),
            2: StationState(),
            3: StationState(),
            4: StationState()
        }
    )
    pending_calls: list[PendingCall] = Field(default_factory=list)
    next_command_id: int = 1
    initialized: bool = False
