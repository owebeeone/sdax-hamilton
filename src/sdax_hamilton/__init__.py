"""Checked Hamilton declarations and resource lifecycles over SDAX."""

from importlib.metadata import PackageNotFoundError, version

from .declarations import Acquisition, execution, shutdown
from .driver import Driver
from .errors import failures
from .plan import PreparedPlan

try:
    __version__ = version("sdax-hamilton")
except PackageNotFoundError:
    __version__ = "0+uninstalled"
__all__ = ["Acquisition", "Driver", "PreparedPlan", "execution", "failures", "shutdown"]
