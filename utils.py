import os
import sys
import glob
import shutil
import pdfplumber
import csv
from datetime import datetime
from config import log
import tkinter as tk
from tkinter import filedialog



def convertir_pdf_a_txt(ruta_pdf, nombre_txt):
    try:
        if not os.path.exists(ruta_pdf):
            return False
            
        texto_final = []
        
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                # 1. Intentamos extraer tablas primero
                tablas = pagina.extract_tables()
                
                if tablas:
                    for tabla in tablas:
                        for fila in tabla:
                            # Limpiamos nulos y unimos con tabulaciones para mantener orden
                            fila_limpia = [str(celda).replace('\n', ' ').strip() if celda else "" for celda in fila]
                            texto_final.append("\t".join(fila_limpia))
                        texto_final.append("\n") # Espacio tras la tabla
                
                # 2. Extraemos el texto que no es tabla (o si prefieres, el layout general)
                # Si la tabla ya fue extraída, podrías querer evitar duplicados, 
                # pero para liquidaciones del PJUD, extraer el texto plano suele bastar:
                texto_plano = pagina.extract_text()
                if texto_plano and not tablas:
                    texto_final.append(texto_plano)
                    
        ruta_salida = os.path.join(os.path.dirname(ruta_pdf), nombre_txt)
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write("\n".join(texto_final))
            
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def limpiar_descargas(ruta):
    for f in glob.glob(os.path.join(ruta, "DownloadFile*")): # Modificado para incluir archivos parciales
        try: os.remove(f)
        except: pass

def procesar_tabla_a_csv(filas, ruta_causa, rit):
    try:
        datos = []
        for i in range(1, filas.length):
            celdas = filas.item(i).getElementsByTagName("td")
            if celdas.length >= 10:
                ref = celdas.item(8).innerText.strip().replace(",", ";")
                fec = celdas.item(9).innerText.strip()
                try:
                    f_dt = datetime.strptime(fec, "%d/%m/%Y")
                    datos.append({"F": f_dt, "FS": fec, "R": ref})
                except: continue
        
        f_corte = next((r["F"] for r in datos if "Liquidación de deuda" in r["R"]), None)
        final = [r for r in datos if r["F"] >= f_corte] if f_corte else datos
        
        path_csv = os.path.join(ruta_causa, f"{rit.replace('/','-')}.csv")
        with open(path_csv, "w", encoding="utf-8-sig", newline="") as f:
            esc = csv.writer(f)
            esc.writerow(["Fecha", "Referencia"])
            for r in final: esc.writerow([r["FS"], r["R"]])
        return True
    except: return False

def procesar_tabla_a_csv_datos(filas, ruta_causa, rit):
    try:
        datos = []
        for fila in filas[1:]:
            if len(fila) >= 10:
                ref = str(fila[8]).strip().replace(",", ";")
                fec = str(fila[9]).strip()
                try:
                    f_dt = datetime.strptime(fec, "%d/%m/%Y")
                    datos.append({"F": f_dt, "FS": fec, "R": ref})
                except:
                    continue

        f_corte = next((r["F"] for r in datos if "Liquidación de deuda" in r["R"] or "LiquidaciÃ³n de deuda" in r["R"]), None)
        final = [r for r in datos if r["F"] >= f_corte] if f_corte else datos

        path_csv = os.path.join(ruta_causa, f"{rit.replace('/','-')}.csv")
        with open(path_csv, "w", encoding="utf-8-sig", newline="") as f:
            esc = csv.writer(f)
            esc.writerow(["Fecha", "Referencia"])
            for r in final:
                esc.writerow([r["FS"], r["R"]])
        return True
    except:
        return False

def obtener_ruta_recurso(nombre_archivo):
    """Obtiene la ruta absoluta del recurso INTERNO, compatible con script y EXE."""
    if getattr(sys, 'frozen', False):
        # Carpeta temporal donde PyInstaller descomprime los recursos internos
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, nombre_archivo)

def obtener_ruta_externa(nombre_archivo):
    """Obtiene la ruta absoluta de un archivo EXTERNO, junto al ejecutable o script."""
    if getattr(sys, 'frozen', False):
        # El programa se está ejecutando como un archivo empaquetado (EXE).
        base_path = os.path.dirname(sys.executable)
    else:
        # El programa se está ejecutando como un script normal.
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, nombre_archivo)

def asegurar_recurso_externo(nombre_archivo):
    """Si el archivo no existe fuera del EXE, lo extrae desde el interior."""
    ruta_externa = obtener_ruta_recurso(nombre_archivo)
    if not os.path.exists(ruta_externa):
        if getattr(sys, 'frozen', False):
            return os.path.join(sys._MEIPASS, nombre_archivo)
        else:
            ruta_interna = obtener_ruta_recurso(nombre_archivo)
            if os.path.exists(ruta_interna):
                log(f"Copiando recurso interno '{nombre_archivo}' a '{ruta_externa}'")
                shutil.copy2(ruta_interna, ruta_externa)
    return ruta_externa
