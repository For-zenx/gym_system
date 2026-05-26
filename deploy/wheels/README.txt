Wheel del paquete Python "dlib" (NO "dlib-bin" / dlib_bin de PyPI)
====================================================================

face_recognition necesita:  import dlib

NO SIRVE:
  - dlib_bin-19.21.0-cp38-...  (otro paquete; renombrar el archivo no ayuda)
  - dlib-*-cp311-*.whl         (solo para Python 3.11 en desarrollo)

SI SIRVE (Python 3.8 x64), copiar UNO a esta carpeta antes de setup_venv o build_release:

  dlib-19.22.99-cp38-cp38-win_amd64.whl
  https://github.com/z-mahmud22/Dlib_Windows_Python3.x/raw/main/dlib-19.22.99-cp38-cp38-win_amd64.whl

  dlib-19.24.1-cp38-cp38-win_amd64.whl  (alternativa)
  https://github.com/sachadee/Dlib/raw/main/dlib-19.24.1-cp38-cp38-win_amd64.whl

El nombre del archivo debe ser el original (dlib-...-cp38-...). No renombres wheels.

Si no hay .whl local, setup_venv.bat intenta descargar el de z-mahmud22 (internet).

Los .whl no se versionan en git (ver .gitignore del repo).
