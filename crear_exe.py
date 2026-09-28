import os
import re

import PyInstaller.__main__
import customtkinter


ARCHIVO_VERSION = "build_version.txt"
VERSION_FORZADA = os.environ.get("SITFA_RELEASE_VERSION", "").strip()

if VERSION_FORZADA:
    if not re.fullmatch(r"\d+", VERSION_FORZADA):
        raise ValueError("SITFA_RELEASE_VERSION debe ser un numero, por ejemplo 9")
    version = int(VERSION_FORZADA)
elif os.path.exists(ARCHIVO_VERSION):
    try:
        with open(ARCHIVO_VERSION, "r", encoding="utf-8") as archivo:
            version = int(archivo.read().strip()) + 1
    except ValueError:
        version = 1
else:
    version = 1

with open(ARCHIVO_VERSION, "w", encoding="utf-8") as archivo:
    archivo.write(str(version))

with open("version.py", "w", encoding="utf-8") as archivo:
    archivo.write('"""Version generada durante el build."""\n')
    archivo.write(f"APP_VERSION = {version}\n")

nombre_exe = f"Robot_SITFA_v{version}"
ctk_path = os.path.dirname(customtkinter.__file__)
sep = ";" if os.name == "nt" else ":"

print(f"Iniciando proceso de empaquetado de {nombre_exe}...")

PyInstaller.__main__.run([
    "updater_helper.py",
    "--name=updater_helper",
    "--onefile",
    "--windowed",
    "--clean",
    "--noconfirm",
])

PyInstaller.__main__.run([
    "main.py",
    f"--name={nombre_exe}",
    "--onefile",
    "--windowed",
    "--icon=robot.ico",
    f"--add-data={ctk_path}{sep}customtkinter/",
    f"--add-data=filtros.json{sep}.",
    f"--add-data=robot.ico{sep}.",
    "--clean",
    "--noconfirm",
    "--hidden-import=win32timezone",
    "--hidden-import=win32gui",
    "--hidden-import=playwright.sync_api",
    "--hidden-import=greenlet",
    "--hidden-import=fitz",
    "--hidden-import=pymupdf",
    "--collect-all=fitz",
    "--collect-all=pymupdf",
    "--hidden-import=PIL._tkinter_finder",
])

print("Proceso finalizado con exito.")
print(f"Busca los ejecutables en: {os.path.join(os.getcwd(), 'dist')}")
