"""
Write the SVG diagram and optionally convert to PNG if CairoSVG is installed.
Run: python render_diagram.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SVG_PATH = os.path.join(HERE, "diagram.svg")
PNG_PATH = os.path.join(HERE, "diagram.png")

SVG_CONTENT = open(SVG_PATH, 'rb').read()
print('SVG written to:', SVG_PATH)

# Try to convert to PNG using cairosvg if available
try:
    import importlib
    if importlib.util.find_spec('cairosvg'):
        import cairosvg
        cairosvg.svg2png(bytestring=SVG_CONTENT, write_to=PNG_PATH, output_width=1000)
        print('PNG written to:', PNG_PATH)
    else:
        print('cairosvg not installed; skipping PNG conversion.')
except Exception as e:
    print('PNG conversion failed:', e)
