from setuptools import Extension, setup
from Cython.Build import cythonize

# Compilar con la misma version de Python del deploy (3.8):
#   py -3.8 setup_licencia.py build_ext --inplace
#
# O desde el venv de desarrollo si es 3.8:
#   python setup_licencia.py build_ext --inplace

setup(
    name="PerfectLine License Module",
    ext_modules=cythonize(
        Extension("config.licencia", ["config/licencia.py"]),
        compiler_directives={"language_level": "3"},
    ),
    packages=[],
)
