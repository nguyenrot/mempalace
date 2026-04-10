"""
room_detector_local.py — Local room detection (Compat Namespace)
===============================================================

Thin re-export wrapper for the actual implementation in _legacy_room_detector.
"""

from mempalace.compat._legacy_room_detector import (
    FOLDER_ROOM_MAP,
    detect_rooms_local,
)

__all__ = [
    "FOLDER_ROOM_MAP",
    "detect_rooms_local",
]
