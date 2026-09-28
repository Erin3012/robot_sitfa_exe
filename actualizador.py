import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from tkinter import Tk, messagebox, ttk

from version import APP_VERSION


REPOSITORIO = "Erin3012/robot_sitfa_exe"
API_RELEASE_LATEST = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
MINIMO_EXE_BYTES = 100 * 1024


class ErrorActualizacion(Exception):
    pass


class VentanaActualizacion:
    def __init__(self):
        self.root = Tk()
        self.root.title("Actualizando Robot SITFA")
        self.root.geometry("480x155")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._bloquear_cierre)
        ttk.Label(self.root, text="Comprobando actualizaciones obligatorias...", font=("Segoe UI", 11, "bold")).pack(pady=(18, 8))
        self.estado = ttk.Label(self.root, text="Conectando con GitHub...")
        self.estado.pack(pady=(0, 8))
        self.progreso = ttk.Progressbar(self.root, length=410, mode="determinate")
        self.progreso.pack(pady=(0, 5))
        self.porcentaje = ttk.Label(self.root, text="0%")
        self.porcentaje.pack()
        self.root.update_idletasks()

    def _bloquear_cierre(self):
        pass

    def mensaje(self, texto):
        self.estado.configure(text=texto)
        self.root.update_idletasks()

    def avance(self, actual, total):
        if total > 0:
            porcentaje = min(100, int(actual * 100 / total))
            self.progreso.configure(value=porcentaje)
            self.porcentaje.configure(text=f"{porcentaje}%")
        else:
            self.progreso.configure(mode="indeterminate")
            self.progreso.start(10)
        self.root.update_idletasks()

    def cerrar(self):
        try:
            self.root.destroy()
        except Exception:
            pass


def _solicitar_json(url):
    solicitud = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Robot-SITFA-Updater"})
    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
        raise ErrorActualizacion(f"No se pudo consultar GitHub: {error}") from error


def _version_desde_tag(tag):
    coincidencia = re.fullmatch(r"v(\d+)", str(tag or "").strip())
    if not coincidencia:
        raise ErrorActualizacion(f"El release de GitHub tiene un tag invalido: {tag!r}")
    return int(coincidencia.group(1))


def _descargar_exe(url, destino, ventana):
    solicitud = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "Robot-SITFA-Updater"})
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            total = int(respuesta.headers.get("Content-Length") or 0)
            descargado = 0
            with open(destino, "wb") as archivo:
                while True:
                    bloque = respuesta.read(1024 * 1024)
                    if not bloque:
                        break
                    archivo.write(bloque)
                    descargado += len(bloque)
                    ventana.avance(descargado, total)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as error:
        raise ErrorActualizacion(f"No se pudo descargar la actualizacion: {error}") from error
    if not os.path.isfile(destino) or os.path.getsize(destino) < MINIMO_EXE_BYTES:
        raise ErrorActualizacion("La descarga de la actualizacion esta incompleta o es invalida.")


def _asset_exe(release):
    candidatos = [asset for asset in release.get("assets") or [] if str(asset.get("name", "")).lower().endswith(".exe") and "updater_helper" not in str(asset.get("name", "")).lower()]
    if not candidatos:
        raise ErrorActualizacion("El release no contiene el EXE principal.")
    return candidatos[0]


def _iniciar_helper(helper, origen, destino):
    if not os.path.isfile(helper):
        raise ErrorActualizacion("Falta updater_helper.exe junto al programa. Instala la distribucion completa.")
    argumentos = [helper, "--pid", str(os.getpid()), "--source", origen, "--target", destino]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(argumentos, creationflags=flags, close_fds=True)


def verificar_actualizacion_obligatoria():
    """Devuelve True si la aplicacion puede continuar; False si debe terminar."""
    if not getattr(sys, "frozen", False):
        return True

    ventana = VentanaActualizacion()
    try:
        release = _solicitar_json(API_RELEASE_LATEST)
        version_remota = _version_desde_tag(release.get("tag_name"))
        if version_remota <= APP_VERSION:
            ventana.cerrar()
            return True

        asset = _asset_exe(release)
        ventana.mensaje(f"Descargando la version v{version_remota}...")
        carpeta_temp = tempfile.mkdtemp(prefix="robot_sitfa_update_")
        descarga = os.path.join(carpeta_temp, asset["name"])
        _descargar_exe(asset["browser_download_url"], descarga, ventana)
        destino = os.path.abspath(sys.executable)
        helper = os.path.join(os.path.dirname(destino), "updater_helper.exe")
        ventana.mensaje("Preparando la instalacion...")
        _iniciar_helper(helper, descarga, destino)
        ventana.mensaje("Reiniciando con la nueva version...")
        ventana.root.after(700, ventana.cerrar)
        return False
    except (ErrorActualizacion, OSError) as error:
        ventana.cerrar()
        messagebox.showerror("Actualizacion obligatoria", f"No se puede iniciar Robot SITFA hasta actualizarlo.\n\n{error}")
        return False
    except Exception as error:
        ventana.cerrar()
        messagebox.showerror("Actualizacion obligatoria", f"No se pudo verificar la version de Robot SITFA.\n\n{error}")
        return False

