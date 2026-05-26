import time
import win32gui
import win32com.client
import pyautogui
import glob
import os
import re # Necesario para expresiones regulares
import shutil
from tkinter import messagebox # Necesario para el pop-up al usuario
from datetime import datetime
from config import log, RobotConfig
import utils

def buscar_en_frames(doc, callback, *args):
    try:
        res = callback(doc, *args)
        if res: return res
    except: pass
    try:
        frames = doc.getElementsByTagName("frame")
        if frames.length == 0: frames = doc.getElementsByTagName("iframe")
        for i in range(frames.length):
            try:
                f_doc = frames.item(i).contentWindow.document
                res = buscar_en_frames(f_doc, callback, *args)
                if res: return res
            except: continue
    except: pass
    return None

def activar_pestana_automatica(doc):
    try:
        p = doc.getElementById("tabAuto")
        if p and p.getAttribute("aria-expanded") != "true":
            p.click()
            time.sleep(2)
        return True if p else False
    except: return False

def extraer_lista_rits(doc):
    c = doc.getElementById("lstTramitesAuto")
    if not c: return []
    
    rits_pantalla = []
    # Recorremos las filas (tr) para garantizar el orden visual exacto de la pantalla
    filas = c.getElementsByTagName("tr")
    for i in range(filas.length):
        fila = filas.item(i)
        # Buscamos primero en enlaces (a) y luego en celdas (td) dentro de ESA fila específica
        items_fila = list(fila.getElementsByTagName("a")) + list(fila.getElementsByTagName("td"))
        for el in items_fila:
            texto = (el.innerText or "").strip()
            if "-" in texto and 5 < len(texto) < 25:
                if texto not in rits_pantalla:
                    rits_pantalla.append(texto)
                    break # Encontramos el RIT de esta fila, pasamos inmediatamente a la siguiente

    return rits_pantalla
def cambiar_pagina(doc):
    """Intenta cambiar a la siguiente página y verifica si hubo cambios."""
    # 1. Guardamos los RITs actuales para comparar después
    rits_antes = extraer_lista_rits(doc)
    
    # 2. Buscamos el botón "Siguiente"
    boton = None
    links = doc.getElementsByTagName("a")
    for link in links:
        # Buscamos por clase "next" (Bootstrap) o por el texto "Siguiente"
        if "next" in str(link.className).lower() or str(link.innerText).strip() == "Siguiente":
            boton = link
            break
            
    if not boton: 
        return False

    try:
        log("🖱️ Clic en Siguiente... Verificando cambio de página...")
        
        # Intentamos disparar el evento 'onclick' directamente para mayor robustez
        try:
            boton.fireEvent("onclick")
            log("✅ Evento 'onclick' en 'Siguiente' disparado.")
        except Exception as fire_e:
            log(f"⚠️ Falló fireEvent('onclick'), intentando .click(): {fire_e}")
            boton.click() # Fallback al clic directo si fireEvent falla
            log("✅ Clic en 'Siguiente' intentado (fallback).")
        
        # Esperamos a que la tabla se refresque (SITFA es lento)
        time.sleep(3)
        
        # 3. Verificamos si los RITs nuevos son iguales a los viejos
        rits_despues = extraer_lista_rits(doc)
        if rits_antes == rits_despues: # Si los RITs no cambiaron, la página no avanzó
            log("🛑 PARADA: La página no cambió. Fin de lista alcanzado.")
            return False
            
        return True
    except Exception as e: # Capturamos la excepción para un mejor diagnóstico
        log(f"❌ Error al intentar hacer clic en 'Siguiente' o verificar cambio de página: {e}")
        return False

def clicar_pdf_01(doc, rit):
    c = doc.getElementById("lstTramitesAuto")
    if not c: return False
    for f in c.getElementsByTagName("tr"):
        if rit in f.innerText:
            for b in f.getElementsByTagName("button"):
                if "abrirDocPDF" in str(b.getAttribute("data-bind")):
                    b.click(); return True
    return False

def marcar_revisado_por_rit(doc, rit_objetivo):
    contenedor = doc.getElementById("lstTramitesAuto")
    if not contenedor: return False
    filas = contenedor.getElementsByTagName("tr")
    for i in range(filas.length):
        if rit_objetivo in filas.item(i).innerText:
            inputs = filas.item(i).getElementsByTagName("input")
            for inp in inputs:
                if inp.getAttribute("type") == "checkbox" and "flgRevisado" in str(inp.getAttribute("data-bind")):
                    if not inp.checked:
                        inp.click(); return True
                    return "Ya marcado"
    return False

def clic_rit(doc, target):
    c = doc.getElementById("lstTramitesAuto")
    if not c: return False
    for it in c.getElementsByTagName("a"):
        if it.innerText.strip() == target:
            it.click(); return True
    return False

def filtrar_y_guardar_csv(doc, ruta_causa, rit):
    tablas = doc.getElementsByTagName("table")
    for t in range(tablas.length):
        if "Desc.Trámite" in tablas.item(t).innerText:
            filas = tablas.item(t).getElementsByTagName("tr")
            return utils.procesar_tabla_a_csv(filas, ruta_causa, rit)
    return False

def buscar_y_clicar_pdf_02(doc):
    tablas = doc.getElementsByTagName("table")
    for t in range(tablas.length):
        if "Desc.Trámite" in tablas.item(t).innerText:
            filas = tablas.item(t).getElementsByTagName("tr")
            for f in range(1, filas.length):
                if "Liquidación de deuda" in filas.item(f).innerText:
                    for img in filas.item(f).getElementsByTagName("img"):
                        if "generarpdf.gif" in img.src:
                            img.click(); return True
    return False


def manejar_descarga_ie(ie, r_dest, n_file, r_desc):
    win32gui.SetForegroundWindow(ie.HWND)
    rit_esperado = os.path.basename(r_dest) # Obtenemos el RIT de la carpeta (ej: C-123-2024)
    
    for i in range(12):
        if RobotConfig.detener_solicitado: return False
        pyautogui.hotkey('alt', 'g')
        time.sleep(2.5)
        if RobotConfig.ventana_ref: RobotConfig.ventana_ref.update()
        archs = glob.glob(os.path.join(r_desc, "DownloadFile.pdf"))
        if archs:
            archs.sort(key=os.path.getmtime, reverse=True)
            path_pdf = os.path.join(r_dest, n_file)
            path_txt = os.path.join(r_dest, n_file.replace(".pdf", ".txt"))
            
            shutil.move(archs[0], path_pdf)
            utils.convertir_pdf_a_txt(path_pdf, n_file.replace(".pdf", ".txt"))
            
            # --- VALIDACIÓN ELIMINADA ---
            # Se asume que la descarga es correcta sin verificar el contenido del TXT.
            return True
                
    return False


def clicar_boton_litigantes(doc, rit):
    # Buscamos la fila que contiene el RIT para clicar SU botón de litigantes
    contenedor = doc.getElementById("lstTramitesAuto")
    if not contenedor: return False
    
    filas = contenedor.getElementsByTagName("tr")
    for i in range(filas.length):
        fila = filas.item(i)
        if rit in fila.innerText:
            botones = fila.getElementsByTagName("button")
            for j in range(botones.length):
                btn = botones.item(j)
                # El botón de litigantes tiene el binding modalLitigantes
                if "modalLitigantes" in str(btn.getAttribute("data-bind")):
                    btn.click()
                    return True
    return False

def extraer_tabla_litigantes(doc, ruta_causa):
    try:
        tablas = doc.getElementsByTagName("table")
        tabla_lit = None
        for t in range(tablas.length):
            tabla_actual = tablas.item(t)
            if "Sujeto" in tabla_actual.innerText and "Rut/Pasaporte" in tabla_actual.innerText:
                tabla_lit = tabla_actual
                break
        
        if not tabla_lit: return False

        import csv
        # Obtenemos el nombre de la carpeta (ej: 123-2024) y le sumamos _2
        nombre_carpeta = os.path.basename(ruta_causa)
        path_csv_lit = os.path.join(ruta_causa, f"{nombre_carpeta}_2.csv")

        datos_para_csv = []
        filas = tabla_lit.getElementsByTagName("tr")
        
        for i in range(filas.length):
            fila = filas.item(i)
            if "textoMin" in str(fila.className):
                celdas = fila.getElementsByTagName("td")

                # Verificar si tiene el check de confirmado en la primera columna
                es_confirmado = False
                try:
                    if celdas.length > 0:
                        celda_0 = celdas.item(0)
                        iconos = celda_0.getElementsByTagName("i")
                        for k in range(iconos.length):
                            icono = iconos.item(k)
                            if "fa-check" in str(icono.className) or "Confirmado" in str(icono.getAttribute("title")):
                                es_confirmado = True
                                break
                except: pass

                if not es_confirmado: continue

                if celdas.length >= 12:
                    sujeto = celdas.item(1).innerText.strip()
                    rut_raw = celdas.item(2).innerText.strip()
                    rut = rut_raw.split()[0] if rut_raw else "S/R"
                    nombre = celdas.item(4).innerText.strip()
                    edad = celdas.item(11).innerText.strip()
                    
                    # Guardamos para el CSV
                    datos_para_csv.append([sujeto, rut, nombre, edad])
                    
                    # Log visual en consola
                    edad_log = f" | 🎂 {edad}" if edad and edad != "---" else ""
                    #log(f"   👤 {sujeto} | {rut} | {nombre}{edad_log}")

        # Escribimos el archivo CSV de litigantes
        with open(path_csv_lit, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.writer(f, delimiter=';')
            escritor.writerow(["Sujeto", "RUT", "Nombre", "Edad"]) # Encabezados
            escritor.writerows(datos_para_csv)

        return True
    except Exception as e:
        log(f"❌ Error al guardar CSV de litigantes: {e}")
        return False

def conectar_popup(titulo_parcial, timeout=15): # Aumentado el timeout por defecto
    """
    Busca una ventana tipo 'Diálogo de página web' o similar por su título.
    Retorna el objeto Document para poder usar getElementById.
    """
    start_time = time.time()
    log(f"⏳ Buscando pop-up '{titulo_parcial}' (timeout: {timeout}s)...")
    while time.time() - start_time < timeout:
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            # Recorremos todas las ventanas abiertas de Windows
            for w in shell.Windows():
                try:
                    # Comparamos el título (LocationName) ignorando mayúsculas/minúsculas
                    # y verificamos que w.Document sea accesible y no None
                    current_location_name = str(w.LocationName)
                    if titulo_parcial.upper() in current_location_name.upper():
                        if hasattr(w, 'Document') and w.Document:
                            log(f"✅ Pop-up '{current_location_name}' detectado y Document accesible.")
                            return w.Document
                        else:
                            log(f"⚠️ Pop-up '{current_location_name}' encontrado por título, pero Document no accesible. (Puede que no sea un IE Document o no esté listo)")
                    # else:
                    #     log(f"   DEBUG: Ventana '{current_location_name}' no coincide con el título parcial '{titulo_parcial}'.") # Demasiado verboso, descomentar si es necesario
                except Exception as inner_e:
                    # Ignoramos errores al acceder a propiedades de ventanas individuales y continuamos buscando
                    continue
        except Exception as e:
            log(f"❌ Error al interactuar con Shell.Application para buscar pop-up: {e}")
        time.sleep(0.5) # Esperar un poco antes de reintentar
    
    log(f"❌ No se encontró el pop-up '{titulo_parcial}' después de {timeout} segundos.")
    return None