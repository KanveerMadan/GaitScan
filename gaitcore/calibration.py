"""Optional floor calibration: two points on the floor a known distance apart (audit B3).

Without it, distances are not reported at all: a single camera cannot tell a small near person
from a large far one. The two points should lie on (or parallel to) the walking line, at the same
distance from the camera as the walker, e.g. two tape marks on the walkway.
"""

import math
from dataclasses import dataclass

# A 1 px marking error must stay <= 1% of the scale.
MIN_PIXEL_DISTANCE = 100.0
MIN_METRES, MAX_METRES = 0.2, 50.0


class CalibrationError(ValueError):
    """User-facing reason the calibration can't be used."""


@dataclass(frozen=True)
class Calibration:
    x1: float
    y1: float
    x2: float
    y2: float
    distance_m: float

    @property
    def pixel_distance(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def metres_per_pixel(self) -> float:
        return self.distance_m / self.pixel_distance

    @property
    def axis(self) -> tuple[float, float]:
        d = self.pixel_distance
        return ((self.x2 - self.x1) / d, (self.y2 - self.y1) / d)

    def check(self, width: int, height: int) -> None:
        for x, y in ((self.x1, self.y1), (self.x2, self.y2)):
            if not (0 <= x <= width and 0 <= y <= height):
                raise CalibrationError(
                    f"Calibration points must be inside the {width}x{height} video frame (pixels)."
                )
        if self.pixel_distance < MIN_PIXEL_DISTANCE:
            raise CalibrationError(
                f"The calibration points are only {self.pixel_distance:.0f} px apart; mark points at least "
                f"{MIN_PIXEL_DISTANCE:.0f} px apart in the video (further apart is more accurate)."
            )
        if not (MIN_METRES <= self.distance_m <= MAX_METRES):
            raise CalibrationError(
                f"The calibration distance must be between {MIN_METRES} and {MAX_METRES} metres."
            )
