"""
FastAPI server for circular rail vehicle management system
"""
import logging
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from models import (
    CommandResponse, VehicleReport, CallRequest, InitializeRequest
)
from state_manager import StateManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Circular Rail Vehicle Management System",
    description="API server for managing vehicles on a circular rail with 4 stations",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for demo purposes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize state manager
state_manager = StateManager()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Circular Rail Vehicle Management System",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/v1/vehicles/{car_id}/command", response_model=CommandResponse)
async def get_vehicle_command(
    car_id: str = Path(..., pattern="^[a-c]$", description="Vehicle ID (a, b, or c)")
):
    """
    Get the next command for a vehicle (polled by ESP32)

    Args:
        car_id: Vehicle ID (a, b, or c)

    Returns:
        CommandResponse with action and expected station
    """
    logger.debug(f"Vehicle {car_id} polling for command")

    if not state_manager.state.initialized:
        logger.warning(f"Command requested but system not initialized")
        raise HTTPException(status_code=400, detail="System not initialized")

    command = state_manager.get_command(car_id)

    if command is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {car_id} not found")

    logger.debug(f"Command for {car_id}: {command.action.value}")
    return command


@app.post("/api/v1/vehicles/{car_id}/report")
async def report_vehicle_status(
    car_id: str = Path(..., pattern="^[a-c]$", description="Vehicle ID (a, b, or c)"),
    report: VehicleReport = None
):
    """
    Vehicle reports its status (called by ESP32 after arriving at station)

    Args:
        car_id: Vehicle ID (a, b, or c)
        report: Vehicle report data

    Returns:
        Success message
    """
    logger.info(
        f"Vehicle {car_id} report: event={report.event.value}, "
        f"station={report.detected_station}, command_id={report.command_id}"
    )

    success = state_manager.handle_report(car_id, report)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to handle report")

    return {
        "status": "ok",
        "message": f"Report from vehicle {car_id} processed successfully"
    }


@app.post("/api/v1/call")
async def call_vehicle(request: CallRequest):
    """
    Request a vehicle to move to a specific station

    Args:
        request: Call request with vehicle ID and target station

    Returns:
        Success message
    """
    logger.info(f"Call request: vehicle {request.vehicle} to station {request.station}")

    success = state_manager.add_call(request.vehicle, request.station)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to add call request. System may not be initialized."
        )

    return {
        "status": "ok",
        "message": f"Vehicle {request.vehicle} called to station {request.station}",
        "vehicle": request.vehicle,
        "target_station": request.station
    }


@app.post("/api/v1/initialize")
async def initialize_system(request: InitializeRequest):
    """
    Initialize the system with vehicle positions

    Args:
        request: Initial positions for each vehicle

    Returns:
        Success message with initialized positions
    """
    logger.info(f"Initializing system with positions: {request.positions}")

    success = state_manager.initialize(request.positions)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to initialize system. Check positions are valid and unique."
        )

    return {
        "status": "ok",
        "message": "System initialized successfully",
        "positions": request.positions
    }


@app.get("/api/v1/status")
async def get_status():
    """
    Get current system status (for debugging)

    Returns:
        Complete system state
    """
    return state_manager.get_state_summary()


@app.post("/api/v1/reset")
async def reset_system():
    """
    Reset the entire system

    Returns:
        Success message
    """
    logger.info("Resetting system")
    state_manager.state.initialized = False
    state_manager.state.pending_calls.clear()

    for vehicle in state_manager.state.vehicles.values():
        vehicle.current_station = None
        vehicle.status = "idle"
        vehicle.current_command_id = None

    for station in state_manager.state.stations.values():
        station.occupied_by = None

    return {
        "status": "ok",
        "message": "System reset successfully"
    }


@app.get("/api/v1/positions")
async def get_positions():
    """
    Get current positions of all vehicles (similar format to initialize)

    Returns:
        Dictionary with vehicle positions: {"a": 1, "b": 2, "c": 3}
    """
    if not state_manager.state.initialized:
        raise HTTPException(status_code=400, detail="System not initialized")

    positions = state_manager.get_positions()
    return {
        "positions": positions,
        "initialized": state_manager.state.initialized
    }


@app.get("/api/v1/sequences")
async def get_sequences():
    """
    Get movement sequences for all vehicles

    Returns:
        Dictionary mapping vehicle IDs to their planned movement sequence
        Example: {"a": [2, 3, 4], "b": [], "c": [4, 1]}
    """
    if not state_manager.state.initialized:
        raise HTTPException(status_code=400, detail="System not initialized")

    sequences = state_manager.get_movement_sequences()
    return {
        "sequences": sequences,
        "pending_calls": [
            {"vehicle": c.vehicle, "target_station": c.target_station}
            for c in state_manager.state.pending_calls
        ]
    }


@app.get("/api/v1/dashboard")
async def get_dashboard():
    """
    Get comprehensive dashboard data for management UI

    Returns:
        Complete data including:
        - Vehicle positions, statuses, targets, and movement sequences
        - Station occupancy
        - Pending calls
        - Movement plan (next 10 moves)
    """
    dashboard_data = state_manager.get_dashboard_data()
    return dashboard_data


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "initialized": state_manager.state.initialized
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
