import importlib
libs = ['svgwrite','PIL','cairosvg']
for lib in libs:
    spec = importlib.util.find_spec(lib)
    print(lib, 'present' if spec else 'missing')
