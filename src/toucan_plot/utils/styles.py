import matplotlib as mpl
import matplotlib.pyplot as plt
import scienceplots
from cycler import cycler


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

_DARK_PALETTES = {
    'Default': ['#56B4E9', '#E69F00', '#009E73', '#F06A6A', '#CC79A7', '#F0E442'],
    'Style 1': ['#7DB6FF', '#FF8A80', '#E6A3FF', '#80DEEA'],
    'Style 2': ['#82AAFF', '#F07178', '#C792EA', '#89DDFF', '#FFCB6B', '#C3E88D'],
    'IEEE': ['#E8EAED', '#FF8A80', '#82B1FF', '#B9F6CA'],
}


def apply_plot_theme(theme: str, preset: str) -> None:
    """Apply canvas colors after a preset, keeping its non-color properties."""
    dark_colors = {
        'figure.facecolor': '#202124',
        'figure.edgecolor': '#202124',
        'axes.facecolor': '#202124',
        'axes.edgecolor': '#9AA0A6',
        'axes.labelcolor': '#E8EAED',
        'text.color': '#E8EAED',
        'xtick.color': '#E8EAED',
        'ytick.color': '#E8EAED',
        'grid.color': '#4A4C50',
        'legend.facecolor': '#292A2D',
        'legend.edgecolor': '#5F6368',
    }
    if theme == 'dark':
        mpl.rcParams.update(dark_colors)
        palette = _DARK_PALETTES.get(preset, _DARK_PALETTES['Default'])
        cycle_props = mpl.rcParams['axes.prop_cycle'].by_key()
        count = len(next(iter(cycle_props.values())))
        cycle_props['color'] = [palette[idx % len(palette)] for idx in range(count)]
        mpl.rcParams['axes.prop_cycle'] = cycler(**cycle_props)
    else:
        mpl.rcParams.update({key: mpl.rcParamsDefault[key] for key in dark_colors})
