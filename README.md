# DearPyGui + Matplotlib Example (Light theme)

This small example demonstrates embedding a Matplotlib plot inside a PyQt6 application.

Files added
- `src/main.py` — the app. Creates a light-background window and shows a sine wave. Use the spin box or the Randomize button to update the plot.
- `requirements.txt` — dependencies (PyQt6, matplotlib, numpy).

How to run
1. Create a Python virtual environment (recommended):

```pwsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```pwsh
pip install -r requirements.txt
```

3. Run the GUI:

```pwsh
python src\main.py
```

Notes and compatibility
- The app uses a simple stylesheet to provide a light background for widgets and a white Matplotlib figure background.
- Depending on platform and PyQt6 packaging, you may need to install additional Qt plugins (usually pip installs the necessary wheels on Windows).
- For heavy update rates, consider optimizing by preallocating numpy buffers and minimizing redraws.

If you'd like, I can:
- Add a packaged CLI to toggle themes.
- Add a unit test that validates the plot-updating logic.
- Wire a small example that saves snapshots of the figure to disk.
