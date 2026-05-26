import os
import threading
from datetime import datetime
from tkinter import END

class RobotConfig:
    ruta_descargas = ""
    ruta_destino_padre = ""
    canal_secreto = ""
    usuario_sitfa = ""
    password_sitfa = ""
    tipo_bandeja = "auto"
    navegador_visible = True
    proceso_en_ejecucion = False
    txt_consola = None
    detener_solicitado = False
    ventana_ref = None 
    auditar_litigantes = False # Desactivado por defecto

def solicitar_detencion():
    """Función centralizada para detener el robot"""
    RobotConfig.detener_solicitado = True
    log("⏳ Detención solicitada... Cerrando proceso actual.")

def log(mensaje):
    timestamp = datetime.now().strftime("%H:%M:%S")
    msg_formateado = f"[{timestamp}] {mensaje}\n"
    if RobotConfig.txt_consola:
        def escribir():
            RobotConfig.txt_consola.insert(END, msg_formateado)
            RobotConfig.txt_consola.see(END)

        if RobotConfig.ventana_ref and threading.current_thread() is not threading.main_thread():
            RobotConfig.ventana_ref.after(0, escribir)
        else:
            escribir()



#prueba de commit
