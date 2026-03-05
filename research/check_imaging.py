import importlib, sys
print('python', sys.version)
for m in ('PIL','cairosvg','svgwrite','svglib'):
    print(m, 'present' if importlib.util.find_spec(m) else 'missing')
