"""
State management for the circular rail system
"""
import logging
from typing import Optional
from models import (
    SystemState, VehicleStatus, Action, PendingCall,
    CommandResponse, VehicleReport, ReportEvent
)

logger = logging.getLogger(__name__)


class StateManager:
    """Manages the complete system state"""

    def __init__(self):
        self.state = SystemState()

    def initialize(self, positions: dict[str, int]) -> bool:
        """
        Initialize vehicle positions

        Args:
            positions: Dictionary mapping vehicle IDs to station numbers

        Returns:
            True if initialization successful
        """
        # Validate positions
        if set(positions.keys()) != {"a", "b", "c"}:
            logger.error(f"Invalid vehicle IDs: {positions.keys()}")
            return False

        for vehicle_id, station in positions.items():
            if station not in [1, 2, 3, 4]:
                logger.error(f"Invalid station {station} for vehicle {vehicle_id}")
                return False

        # Check for duplicate positions
        station_values = list(positions.values())
        if len(station_values) != len(set(station_values)):
            logger.error(f"Duplicate station positions: {positions}")
            return False

        # Clear all stations
        for station in self.state.stations.values():
            station.occupied_by = None

        # Set vehicle positions
        for vehicle_id, station_num in positions.items():
            self.state.vehicles[vehicle_id].current_station = station_num
            self.state.vehicles[vehicle_id].status = VehicleStatus.IDLE
            self.state.stations[station_num].occupied_by = vehicle_id

        self.state.initialized = True
        self.state.pending_calls.clear()
        logger.info(f"System initialized with positions: {positions}")
        return True

    def add_call(self, vehicle: str, target_station: int) -> bool:
        """
        Add a vehicle call request

        Args:
            vehicle: Vehicle ID
            target_station: Target station number

        Returns:
            True if call added successfully
        """
        if not self.state.initialized:
            logger.error("System not initialized")
            return False

        # Check if vehicle is already at target
        current = self.state.vehicles[vehicle].current_station
        if current == target_station:
            logger.info(f"Vehicle {vehicle} already at station {target_station}")
            return True

        # Check if call already exists
        for call in self.state.pending_calls:
            if call.vehicle == vehicle:
                logger.warning(f"Vehicle {vehicle} already has pending call, updating target")
                call.target_station = target_station
                return True

        # Add new call
        self.state.pending_calls.append(PendingCall(
            vehicle=vehicle,
            target_station=target_station
        ))
        logger.info(f"Added call: vehicle {vehicle} to station {target_station}")
        return True

    def get_command(self, vehicle_id: str) -> Optional[CommandResponse]:
        """
        Get next command for a vehicle

        Args:
            vehicle_id: Vehicle ID

        Returns:
            CommandResponse or None if no command
        """
        if not self.state.initialized:
            return None

        vehicle = self.state.vehicles.get(vehicle_id)
        if not vehicle:
            return None

        # If vehicle is already moving, return current command
        if vehicle.status == VehicleStatus.MOVING and vehicle.current_command_id:
            # Find the target for this vehicle
            target_station = None
            for call in self.state.pending_calls:
                if call.vehicle == vehicle_id:
                    target_station = call.target_station
                    break

            if target_station:
                next_station = self._get_next_station(vehicle.current_station)
                return CommandResponse(
                    command_id=vehicle.current_command_id,
                    action=Action.FORWARD,
                    expected_station=next_station
                )

        # Calculate next move
        next_move = self._calculate_next_move()

        if next_move and next_move["vehicle"] == vehicle_id:
            # Issue new command
            command_id = self.state.next_command_id
            self.state.next_command_id += 1

            vehicle.status = VehicleStatus.MOVING
            vehicle.current_command_id = command_id

            return CommandResponse(
                command_id=command_id,
                action=next_move["action"],
                expected_station=next_move["expected_station"]
            )

        # No command for this vehicle
        return CommandResponse(
            command_id=vehicle.current_command_id or 0,
            action=Action.STOP,
            expected_station=None
        )

    def handle_report(self, vehicle_id: str, report: VehicleReport) -> bool:
        """
        Handle a vehicle report

        Args:
            vehicle_id: Vehicle ID
            report: Vehicle report

        Returns:
            True if report handled successfully
        """
        vehicle = self.state.vehicles.get(vehicle_id)
        if not vehicle:
            logger.error(f"Unknown vehicle: {vehicle_id}")
            return False

        if report.event == ReportEvent.ARRIVED:
            # Determine actual station
            actual_station = report.detected_station

            if report.pattern_confident and report.mismatch:
                logger.warning(
                    f"Vehicle {vehicle_id} position mismatch: "
                    f"expected={report.expected_station}, detected={actual_station}"
                )
            elif not report.pattern_confident:
                logger.warning(
                    f"Vehicle {vehicle_id} pattern detection failed, "
                    f"using expected station {report.expected_station}"
                )
                actual_station = report.expected_station

            # Update vehicle position
            old_station = vehicle.current_station
            vehicle.current_station = actual_station
            vehicle.status = VehicleStatus.IDLE

            # Update station occupancy
            if old_station:
                self.state.stations[old_station].occupied_by = None
            self.state.stations[actual_station].occupied_by = vehicle_id

            logger.info(
                f"Vehicle {vehicle_id} arrived at station {actual_station} "
                f"(command_id={report.command_id})"
            )

            # Check if vehicle reached its target
            for call in self.state.pending_calls:
                if call.vehicle == vehicle_id and call.target_station == actual_station:
                    self.state.pending_calls.remove(call)
                    logger.info(f"Vehicle {vehicle_id} reached target station {actual_station}")
                    break

            return True

        elif report.event == ReportEvent.ERROR:
            logger.error(f"Vehicle {vehicle_id} reported error (command_id={report.command_id})")
            vehicle.status = VehicleStatus.IDLE
            return True

        return False

    def _get_next_station(self, current: Optional[int]) -> int:
        """Get next station in circular order"""
        if current is None:
            return 1
        return (current % 4) + 1

    def _calculate_next_move(self) -> Optional[dict]:
        """
        Calculate the next vehicle move

        Returns:
            Dictionary with vehicle, action, and expected_station, or None
        """
        if not self.state.pending_calls:
            return None

        # Process first pending call
        call = self.state.pending_calls[0]
        vehicle = self.state.vehicles[call.vehicle]

        # Check if already at target
        if vehicle.current_station == call.target_station:
            self.state.pending_calls.pop(0)
            return self._calculate_next_move()

        # Calculate next station
        current = vehicle.current_station
        if current is None:
            logger.error(f"Vehicle {call.vehicle} has no current position")
            return None

        next_station = self._get_next_station(current)

        # Check if next station is available
        if self.state.stations[next_station].occupied_by is None:
            return {
                "vehicle": call.vehicle,
                "action": Action.FORWARD,
                "expected_station": next_station
            }
        else:
            # Next station is blocked, try to move the blocking vehicle
            blocking_vehicle = self.state.stations[next_station].occupied_by
            if blocking_vehicle:
                return self._calculate_move_for_vehicle(blocking_vehicle)

        return None

    def _calculate_move_for_vehicle(self, vehicle_id: str) -> Optional[dict]:
        """
        Calculate move for a specific vehicle to make space

        Args:
            vehicle_id: Vehicle to move

        Returns:
            Move dictionary or None
        """
        vehicle = self.state.vehicles[vehicle_id]
        current = vehicle.current_station

        if current is None:
            return None

        next_station = self._get_next_station(current)

        # If next station is free, move forward
        if self.state.stations[next_station].occupied_by is None:
            return {
                "vehicle": vehicle_id,
                "action": Action.FORWARD,
                "expected_station": next_station
            }
        else:
            # Recursively try to move the blocking vehicle
            blocking_vehicle = self.state.stations[next_station].occupied_by
            if blocking_vehicle and blocking_vehicle != vehicle_id:
                return self._calculate_move_for_vehicle(blocking_vehicle)

        return None

    def get_state_summary(self) -> dict:
        """Get a summary of the current state"""
        return {
            "initialized": self.state.initialized,
            "vehicles": {
                vid: {
                    "current_station": v.current_station,
                    "status": v.status.value,
                    "current_command_id": v.current_command_id
                }
                for vid, v in self.state.vehicles.items()
            },
            "stations": {
                sid: {"occupied_by": s.occupied_by}
                for sid, s in self.state.stations.items()
            },
            "pending_calls": [
                {"vehicle": c.vehicle, "target_station": c.target_station}
                for c in self.state.pending_calls
            ],
            "next_command_id": self.state.next_command_id
        }

    def get_positions(self) -> dict[str, Optional[int]]:
        """
        Get current positions of all vehicles

        Returns:
            Dictionary mapping vehicle IDs to station numbers
        """
        return {
            vid: v.current_station
            for vid, v in self.state.vehicles.items()
        }

    def get_movement_sequences(self) -> dict[str, list[int]]:
        """
        Calculate movement sequences for all vehicles with pending calls

        Returns:
            Dictionary mapping vehicle IDs to list of station numbers they will visit
        """
        sequences = {"a": [], "b": [], "c": []}

        if not self.state.initialized:
            return sequences

        # Create a simulation state
        sim_vehicles = {
            vid: {
                "current": v.current_station,
                "target": None
            }
            for vid, v in self.state.vehicles.items()
        }

        # Set targets from pending calls
        for call in self.state.pending_calls:
            sim_vehicles[call.vehicle]["target"] = call.target_station

        # Simulate movements for each vehicle with a target
        for vid in ["a", "b", "c"]:
            current = sim_vehicles[vid]["current"]
            target = sim_vehicles[vid]["target"]

            if current is None or target is None:
                continue

            if current == target:
                continue

            # Calculate path from current to target (circular)
            path = []
            pos = current
            while pos != target:
                pos = self._get_next_station(pos)
                path.append(pos)

            sequences[vid] = path

        return sequences

    def get_dashboard_data(self) -> dict:
        """
        Get comprehensive data for dashboard UI

        Returns:
            Complete dashboard data including positions, sequences, and next moves
        """
        if not self.state.initialized:
            return {
                "initialized": False,
                "vehicles": {},
                "stations": {},
                "pending_calls": [],
                "movement_plan": []
            }

        # Get next few moves
        movement_plan = self._simulate_next_moves(max_moves=10)

        # Get vehicle details with targets
        vehicles_detail = {}
        for vid, vehicle in self.state.vehicles.items():
            target = None
            for call in self.state.pending_calls:
                if call.vehicle == vid:
                    target = call.target_station
                    break

            # Get next station if moving
            next_station = None
            if vehicle.status == VehicleStatus.MOVING and vehicle.current_station:
                next_station = self._get_next_station(vehicle.current_station)

            vehicles_detail[vid] = {
                "current_station": vehicle.current_station,
                "status": vehicle.status.value,
                "target_station": target,
                "next_station": next_station,
                "sequence": self.get_movement_sequences()[vid]
            }

        return {
            "initialized": True,
            "vehicles": vehicles_detail,
            "stations": {
                sid: {"occupied_by": s.occupied_by}
                for sid, s in self.state.stations.items()
            },
            "pending_calls": [
                {"vehicle": c.vehicle, "target_station": c.target_station}
                for c in self.state.pending_calls
            ],
            "movement_plan": movement_plan
        }

    def _simulate_next_moves(self, max_moves: int = 10) -> list[dict]:
        """
        Simulate the next N moves without changing actual state

        Args:
            max_moves: Maximum number of moves to simulate

        Returns:
            List of move dictionaries with step number
        """
        # Create a deep copy of current state
        sim_vehicles = {
            vid: {
                "station": v.current_station,
                "status": v.status
            }
            for vid, v in self.state.vehicles.items()
        }

        sim_stations = {
            sid: s.occupied_by
            for sid, s in self.state.stations.items()
        }

        sim_calls = [
            {"vehicle": c.vehicle, "target": c.target_station}
            for c in self.state.pending_calls
        ]

        moves = []
        step = 1

        while len(moves) < max_moves and sim_calls:
            # Get first pending call
            call = sim_calls[0]
            vehicle_id = call["vehicle"]
            target = call["target"]
            current = sim_vehicles[vehicle_id]["station"]

            if current == target:
                sim_calls.pop(0)
                continue

            # Find which vehicle needs to move to make progress
            move_chain = self._find_move_chain(sim_vehicles, sim_stations, vehicle_id)

            if not move_chain:
                # Can't find a valid move, break
                break

            # Execute the first move in the chain
            first_move = move_chain[0]
            vid = first_move["vehicle"]
            from_station = first_move["from_station"]
            to_station = first_move["to_station"]

            # Determine if this is the target vehicle moving
            is_target_vehicle = (vid == vehicle_id)

            moves.append({
                "step": step,
                "vehicle": vid,
                "from_station": from_station,
                "to_station": to_station,
                "reason": "moving_to_target" if is_target_vehicle else "making_space"
            })

            # Update simulation state
            sim_stations[from_station] = None
            sim_stations[to_station] = vid
            sim_vehicles[vid]["station"] = to_station

            # Check if target vehicle reached its destination
            if is_target_vehicle and to_station == target:
                sim_calls.pop(0)

            step += 1

        return moves

    def _find_move_chain(self, sim_vehicles: dict, sim_stations: dict, target_vehicle: str) -> list[dict]:
        """
        Find the chain of moves needed to move the target vehicle forward

        4駅に3台なので、必ず1つの空き駅がある。
        目的の車両が動きたい方向に空き駅があるかチェックし、
        なければ他の車両を動かして空きを作る。

        Args:
            sim_vehicles: Simulated vehicle states
            sim_stations: Simulated station occupancy
            target_vehicle: The vehicle that needs to move

        Returns:
            List of move dictionaries in order of execution (first move to execute)
        """
        # Target vehicle's current position and next desired position
        current = sim_vehicles[target_vehicle]["station"]
        next_desired = self._get_next_station(current)

        # If the next station is already empty, target vehicle can move
        if sim_stations[next_desired] is None:
            return [{
                "vehicle": target_vehicle,
                "from_station": current,
                "to_station": next_desired
            }]

        # Next station is blocked. Find the empty station
        empty_station = None
        for station_id, occupant in sim_stations.items():
            if occupant is None:
                empty_station = station_id
                break

        if empty_station is None:
            return []

        # Move the vehicle just before the empty station to create a chain reaction
        # The vehicle at (empty_station - 1) can move to empty_station
        prev_station = self._get_prev_station(empty_station)
        vehicle_to_move = sim_stations[prev_station]

        if vehicle_to_move is None:
            return []

        return [{
            "vehicle": vehicle_to_move,
            "from_station": prev_station,
            "to_station": empty_station
        }]

    def _get_prev_station(self, current: int) -> int:
        """Get previous station in circular order"""
        return ((current - 2) % 4) + 1
