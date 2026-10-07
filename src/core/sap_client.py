"""Connection to the SAP2000 OAPI through its .NET assembly (SAP2000v1.dll).

This mirrors the MATLAB reference (connectToSAP.m / openSapModel.m):
the assembly is loaded directly, an already running SAP2000 instance is
used when there is one, otherwise a new instance is started.

The assembly is NOT taken from the user's SAP2000 installation: a copy
of the supported version ships with the application (BUNDLED_DLL), so
the method signatures we code against never change under us. Only
SUPPORTED_VERSION is supported; the version of the SAP2000 program that
answers is checked right after connecting.

Requires `pythonnet` (the .NET Framework runtime, "netfx", because
SAP2000v1.dll is a .NET Framework assembly). It is imported lazily so
the rest of the application starts without it.

NOTE: the Python binding of `ref` / `out` parameters (see
`frame_section_names` and `_check_version`) is the part most worth
verifying against a real SAP2000 installation.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_VERSION = 23

# src/core/vendor/sap2000_v23/SAP2000v1.dll
BUNDLED_DLL = (
    Path(__file__).parent / "vendor" / f"sap2000_v{SUPPORTED_VERSION}" / "SAP2000v1.dll"
)

_PROG_ID = "CSI.SAP2000.API.SapObject"


class SapError(RuntimeError):
    """Any failure while talking to SAP2000."""


def _load_api(dll_path: Path):
    """Load SAP2000v1.dll and return the `SAP2000v1` .NET namespace."""

    if not dll_path.is_file():
        raise SapError(
            f"The bundled SAP2000 v{SUPPORTED_VERSION} assembly is missing: {dll_path}"
        )

    try:
        import pythonnet
    except ImportError as exc:
        raise SapError("The 'pythonnet' package is required to talk to SAP2000.") from exc

    try:
        pythonnet.load("netfx")
    except Exception:  # already loaded in this process
        logger.debug("pythonnet runtime was already loaded", exc_info=True)

    import clr  # noqa: F401  (registers the .NET import hook)

    clr.AddReference(str(dll_path))

    import SAP2000v1  # type: ignore[import-not-found]

    return SAP2000v1


class SapClient:
    """A live connection to one SAP2000 instance."""

    def __init__(self, api, sap_object, sap_model, started_new: bool):
        self.api = api
        self.sap_object = sap_object
        self.model = sap_model
        self.started_new = started_new

    @classmethod
    def connect(cls, dll_path: str | Path | None = None) -> SapClient:
        """Attach to the running SAP2000, or start one if none is open."""

        api = _load_api(Path(dll_path) if dll_path else BUNDLED_DLL)

        helper = api.cHelper(api.Helper())

        try:
            sap_object = helper.GetObject(_PROG_ID)
        except Exception:  # no running instance
            sap_object = None

        if sap_object is None:
            sap_object = helper.CreateObjectProgID(_PROG_ID)
            sap_object.ApplicationStart()
            started_new = True
        else:
            started_new = False

        logger.info(
            "SAP2000: %s",
            "started new instance" if started_new else "using existing instance",
        )

        client = cls(api, sap_object, sap_object.SapModel, started_new)
        client._check_version()

        return client

    def _check_version(self) -> None:
        """Refuse to work with a SAP2000 other than SUPPORTED_VERSION."""

        try:
            result = self.model.GetVersion("", 0.0)
            version_text = str(result[1])
            major = int(float(result[2]))
        except Exception:
            # Could not read the version: do not block, but leave a trace.
            logger.warning("Could not read the SAP2000 version", exc_info=True)
            return

        logger.info("SAP2000 version: %s", version_text)

        if major != SUPPORTED_VERSION:
            raise SapError(
                f"SAP2000 v{version_text} is running, but only "
                f"v{SUPPORTED_VERSION} is supported."
            )

    def open_model(self, sdb_path: str | Path) -> None:
        """Open a .sdb file and switch to N-m-C units (as in openSapModel.m)."""

        ret = self.model.File.OpenFile(str(sdb_path))

        if ret != 0:
            raise SapError(f"SAP2000 could not open the file: {sdb_path}")

        ret = self.model.SetPresentUnits(self.api.eUnits.N_m_C)

        if ret != 0:
            raise SapError("Could not set SAP2000 units to N-m-C.")

    def frame_section_names(self) -> list[str]:
        """Names of all frame sections defined in the open model."""

        result = self.model.PropFrame.GetNameList(0, None)

        # pythonnet returns (ret, NumberNames, MyName) for ref parameters.
        if not isinstance(result, tuple) or len(result) < 3:
            raise SapError(f"Unexpected result of PropFrame.GetNameList: {result!r}")

        ret, count, names = result[0], result[1], result[2]

        if ret != 0:
            raise SapError("PropFrame.GetNameList failed.")

        return [str(name) for name in list(names or [])[: int(count)]]
