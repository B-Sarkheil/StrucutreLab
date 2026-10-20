"""Collected errors and warnings (nothing stops at the first error)."""
from __future__ import annotations

from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    code: str  # S01.., M01.., W01.. (docs section 8)
    message: str
    file: str = ""
    index: int | None = None  # `Index` column of the CSV row
    cad: tuple[float, float] | None = None  # CAD coordinates (mm) to find it in AutoCAD
    severity: str = ERROR

    def __str__(self) -> str:
        where = self.file
        if self.index is not None:
            where += f" [Index {self.index}]"
        if self.cad is not None:
            where += f" (CAD {self.cad[0]:.3f}, {self.cad[1]:.3f})"
        where = where.strip()
        return f"{self.code} {where}: {self.message}" if where else f"{self.code}: {self.message}"
