import PyInstaller.__main__
import customtkinter
import os

# --- LÓGICA DE AUTOINCREMENTO DE VERSIÓN ---
archivo_version = 'build_version.txt'

if os.path.exists(archivo_version):
    with open(archivo_version, 'r') as f:
        try:
            version = int(f.read().strip())
        except ValueError:
            version = 0
else:
    version = 0

version += 1

with open(archivo_version, 'w') as f:
    f.write(str(version))

nombre_exe = f'Robot_SITFA_v{version}'
# -------------------------------------------

# 1. Obtener la ruta de instalación de customtkinter para incluir sus recursos
ctk_path = os.path.dirname(customtkinter.__file__)

# 2. Definir separador de sistema (Windows usa ';')
sep = ';' if os.name == 'nt' else ':'

print(f"🚀 Iniciando proceso de empaquetado de {nombre_exe}...")

# 3. Configuración de PyInstaller
PyInstaller.__main__.run([
    'main.py',                       # Tu script principal
    f'--name={nombre_exe}',          # Nombre del archivo final .exe
    '--onefile',                     # Empaquetar todo en un solo archivo
    '--windowed',                    # No mostrar consola negra (GUI mode)
    '--icon=robot.ico',              # Icono de la aplicación
    
    # -- INCLUSIÓN DE ARCHIVOS Y CARPETAS --
    
    # CustomTkinter (Necesario para que la interfaz se vea bien)
    f'--add-data={ctk_path}{sep}customtkinter/',
    
    # Archivos de recursos del proyecto
    f'--add-data=filtros.json{sep}.',
    f'--add-data=robot.ico{sep}.',
    
    # Incluimos config_rutas.txt si existe, para tener una configuración base
    # (Si no existe, el script funcionará igual pero el usuario deberá configurar rutas al abrir)
    # f'--add-data=config_rutas.txt{sep}.', 
    
    # -- OPCIONES DE LIMPIEZA Y OPTIMIZACIÓN --
    '--clean',                       # Limpiar caché de compilaciones previas
    '--noconfirm',                   # Sobrescribir sin preguntar
    
    # -- IMPORTS OCULTOS (A veces necesarios para win32 o pandas) --
    '--hidden-import=babel.numbers',
    '--hidden-import=win32timezone',
    '--hidden-import=win32gui',
    '--hidden-import=playwright.sync_api',
    '--hidden-import=greenlet',
    '--hidden-import=fitz',
    '--hidden-import=pymupdf',
    '--collect-all=fitz',
    '--collect-all=pymupdf',
    '--hidden-import=PIL._tkinter_finder',
])

print("\n✅ ¡Proceso finalizado con éxito!")
print(f"Busca tu ejecutable en la carpeta: {os.path.join(os.getcwd(), 'dist')}")
