import matplotlib.pyplot as plt
from cycler import cycler
import scienceplots

def set_default_style() -> None:
    """Configure matplotlib for screen viewing."""
    plt.style.use(['default','no-latex'])
    plt.rcParams.update(
        {
            "axes.prop_cycle": cycler("color", ["blue", "orange", "green", "red", "purple", "brown"]),
            "lines.linewidth": 1,
            "axes.grid": True,
            "text.usetex": False,
            "axes3d.grid": True,
            "figure.constrained_layout.use": True,
        }
    )

def set_style1_style() -> None:
    """Configure matplotlib for screen viewing."""
    plt.style.use(['default','no-latex'])
    plt.rcParams.update(
        {
            "axes.prop_cycle": cycler("color", ["b", "r", "m", "c"]),
            "lines.linewidth": 1,
            "axes.grid": True,
            "text.usetex": False,
            "axes3d.grid": True,
            "figure.constrained_layout.use": True,
        }
    )

def set_style2_style() -> None:
    """Configure matplotlib for Style 2."""
    plt.style.use(['default','no-latex'])
    plt.rcParams.update(
        {
            "axes.prop_cycle": cycler("color", ["#2962FF", "r", "#AA00FF", "#00B8D4", "#FF6D00", "#00C853"]),
            "lines.linewidth": 1,
            "axes.grid": True,
            "axes3d.grid": True,
            "figure.constrained_layout.use": True,
        }
    )

def set_ieee_style() -> None:
    """Configure matplotlib for IEEE style."""
    plt.style.use(['science','ieee','grid','no-latex'])
    plt.rcParams.update(
        {
            "axes3d.grid": True,
            "figure.dpi": 150,
            "figure.constrained_layout.use": True,
        }
    )