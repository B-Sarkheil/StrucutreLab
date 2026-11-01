"""Auto Design - step 7: geometry of the reference structure (no Qt).

Joint coordinates and frame connectivity (which two joints each frame
connects), read from the SAP2000 database tables. Coordinates are global
Cartesian, in the model's present units (N-m-C, so meters).
"""
from __future__ import annotations

from src.core.sap_client import SapClient, SapError
from src.plugins.auto_design.services.sap_tables import pick_field

JOINT_TABLE = "Joint Coordinates"
FRAME_TABLE = "Connectivity - Frame"


def _number(text: str, key: str, table: str) -> float:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise SapError(
            f"Table '{table}': '{text}' in field '{key}' is not a number."
        ) from None


def read_joint_coordinates(client: SapClient) -> dict[str, tuple[float, float, float]]:
    """Joint name -> (x, y, z), in SAP table order."""

    result: dict[str, tuple[float, float, float]] = {}

    for row in client.read_table(JOINT_TABLE):
        joint = pick_field(row, "Joint", JOINT_TABLE)
        x, y, z = (
            _number(pick_field(row, key, JOINT_TABLE), key, JOINT_TABLE)
            for key in ("GlobalX", "GlobalY", "GlobalZ")
        )
        result[joint] = (x, y, z)

    return result


def read_frame_connectivity(client: SapClient) -> dict[str, tuple[str, str]]:
    """Frame name -> (joint I, joint J), in SAP table order."""

    result: dict[str, tuple[str, str]] = {}

    for row in client.read_table(FRAME_TABLE):
        frame = pick_field(row, "Frame", FRAME_TABLE)
        result[frame] = (
            pick_field(row, "JointI", FRAME_TABLE),
            pick_field(row, "JointJ", FRAME_TABLE),
        )

    return result