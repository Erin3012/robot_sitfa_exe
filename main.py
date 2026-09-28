import pandas as pd
import sys
import os
import shutil
import time
import threading
from datetime import datetime
import customtkinter as ctk # La nueva estrella
from tkinter import filedialog, messagebox
from config import RobotConfig, log, solicitar_detencion
import utils
import re
from gui_analisis import VentanaAnalisis # Importas el archivo que creaste
from wsp import enviar_notificacion
from sitfa_playwright import abrir_sesion_sitfa, PlaywrightSetupError
from actualizador import verificar_actualizacion_obligatoria

ventana_analisis_instancia = None
root = None  # Declaramos la variable root aquí arriba

# Configuración de apariencia global
ctk.set_appearance_mode("Light")  # Modos: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Temas: "blue", "green", "dark-blue"

def abrir_analizador():
    global ventana_analisis_instancia

    # 2. CREAR o MOSTRAR la ventana de análisis
    if ventana_analisis_instancia is None or not ventana_analisis_instancia.winfo_exists():
        ventana_analisis_instancia = VentanaAnalisis(parent=root)
    else:
        ventana_analisis_instancia.state('zoomed')
        ventana_analisis_instancia.deiconify()
        ventana_analisis_instancia.focus()

    # 3. Minimizar la ventana principal
    root.iconify()



# Variable global para rastrear la ventana (fuera de la función)


def mostrar_info(titulo, mensaje):
    if root and threading.current_thread() is not threading.main_thread():
        root.after(0, lambda: messagebox.showinfo(titulo, mensaje))
    else:
        messagebox.showinfo(titulo, mensaje)


def mostrar_error(titulo, mensaje):
    if root and threading.current_thread() is not threading.main_thread():
        root.after(0, lambda: messagebox.showerror(titulo, mensaje))
    else:
        messagebox.showerror(titulo, mensaje)


def ejecutar_en_hilo(func, *args):
    if RobotConfig.proceso_en_ejecucion:
        log("Ya hay un proceso del robot en ejecucion.")
        return

    RobotConfig.proceso_en_ejecucion = True

    def runner():
        try:
            func(*args)
        finally:
            RobotConfig.proceso_en_ejecucion = False

    threading.Thread(target=runner, daemon=True).start()


def abrir_modulo_analisis():
    global ventana_analisis_instancia, root

    if ventana_analisis_instancia is None or not ventana_analisis_instancia.winfo_exists():
        ventana_analisis_instancia = VentanaAnalisis(root)
    else:
        ventana_analisis_instancia.state('zoomed')
        ventana_analisis_instancia.focus_force()
        ventana_analisis_instancia.lift()

    # Minimizar la ventana principal después de abrir el analizador
    root.iconify()


def ejecutar_revision_integridad():
    log("⚙️ Solicitando carpeta para revisión de integridad...")
    ruta_raiz = filedialog.askdirectory(title="Seleccionar carpeta raíz para revisar")
    if not ruta_raiz:
        log("❌ Revisión cancelada por el usuario.")
        return

    log(f"🚀 Iniciando revisión de integridad en: {ruta_raiz}")
    carpetas_con_error = set()

    # Usamos os.scandir por ser más eficiente que listdir
    for entrada in os.scandir(ruta_raiz):
        if entrada.is_dir():
            ruta_carpeta = entrada.path
            nombre_carpeta = entrada.name

            archivos_a_revisar = ["01.txt", "02.txt"]
            for nombre_archivo in archivos_a_revisar:
                ruta_archivo = os.path.join(ruta_carpeta, nombre_archivo)

                if os.path.exists(ruta_archivo):
                    try:
                        with open(ruta_archivo, 'r', encoding='utf-8', errors='ignore') as f:
                            primera_linea = f.readline()
                        
                        # Buscamos el patrón "RIT" seguido de espacios/tabs y el valor
                        match = re.search(r"RIT\s+(.+)", primera_linea, re.IGNORECASE)
                        
                        if match:
                            rit_en_txt = match.group(1).strip()
                            # Comparamos el RIT del archivo con el nombre de la carpeta
                            if rit_en_txt != nombre_carpeta:
                                carpetas_con_error.add(nombre_carpeta)
                        else:
                            # Si la primera línea existe pero no tiene el formato esperado
                            carpetas_con_error.add(nombre_carpeta)

                    except Exception as e:
                        log(f"🛑 Error leyendo {ruta_archivo}: {e}")
                        carpetas_con_error.add(nombre_carpeta)
    
    if carpetas_con_error:
        log("--- 🚨 RESULTADO DE LA REVISIÓN: Se encontraron inconsistencias ---")
        lista_errores = sorted(list(carpetas_con_error))
        for carpeta in lista_errores:
            log(f"   - {carpeta}")
        
        mensaje = (f"Se encontraron inconsistencias en {len(lista_errores)} carpetas.\n\n"
                   "¿Deseas borrar estas carpetas y todo su contenido de forma permanente?\n\n"
                   "(Revisa la consola para ver la lista completa)")

        confirmacion = messagebox.askokcancel("Revisión Terminada", mensaje)

        if confirmacion:
            log("🔥 Usuario confirmó la eliminación. Procediendo a borrar carpetas...")
            borradas_count = 0
            for carpeta in lista_errores:
                ruta_a_borrar = os.path.join(ruta_raiz, carpeta)
                try:
                    if os.path.isdir(ruta_a_borrar):
                        shutil.rmtree(ruta_a_borrar)
                        log(f"   🗑️ Carpeta eliminada: {ruta_a_borrar}")
                        borradas_count += 1
                except Exception as e:
                    log(f"   🛑 Error al eliminar la carpeta {ruta_a_borrar}: {e}")
            
            messagebox.showinfo("Eliminación Completada", f"Se eliminaron {borradas_count} carpetas con inconsistencias.")
            log(f"✅ Proceso de borrado finalizado. {borradas_count} carpetas eliminadas.")
        else:
            log("👍 El usuario decidió no eliminar las carpetas.")
            messagebox.showinfo("Operación Cancelada", "No se eliminó ninguna carpeta.")
    else:
        log("✅ REVISIÓN FINALIZADA: No se encontraron inconsistencias de RIT.")
        messagebox.showinfo("Revisión Terminada", "No se encontraron inconsistencias en los archivos revisados.")



def _ejecutar_parte_1_worker():
    RobotConfig.detener_solicitado = False

    hoy = datetime.now().strftime("%d-%m-%Y")
    ruta_final = os.path.join(RobotConfig.ruta_destino_padre, hoy)

    if not os.path.exists(ruta_final):
        os.makedirs(ruta_final)
    log("Rutas elegidas:")
    log(f"   - Descargas: {RobotConfig.ruta_descargas}")
    log(f"   - Destino causas: {ruta_final}")

    log("Iniciando Parte 1 con Playwright...")
    try:
        with abrir_sesion_sitfa(parent=root) as sitfa:
            hay_mas_paginas = True
            num_p = 1
            while hay_mas_paginas:
                if RobotConfig.detener_solicitado:
                    break
                rits = sitfa.extraer_lista_rits()
                if not rits:
                    break

                log(f"--- PAGINA {num_p} ({len(rits)} causas) ---")
                for idx, rit in enumerate(rits, 1):
                    if RobotConfig.detener_solicitado:
                        break
                    log(f"[{idx}/{len(rits)}] Procesando: {rit}")

                    nombre_c = rit.replace("/", "-")
                    ruta_c = os.path.join(ruta_final, nombre_c)

                    if os.path.exists(ruta_c) and len(os.listdir(ruta_c)) >= 5:
                        log(f"Saltando {rit}")
                        continue

                    if os.path.exists(ruta_c):
                        shutil.rmtree(ruta_c)
                    os.makedirs(ruta_c, exist_ok=True)
                    utils.limpiar_descargas(RobotConfig.ruta_descargas)

                    if RobotConfig.auditar_litigantes:
                        log(f"Auditando litigantes para {rit}...")
                        if sitfa.auditar_litigantes(rit, ruta_c):
                            log("   Auditoria finalizada.")

                    if sitfa.descargar_pdf_01(rit, ruta_c):
                        log("   PDF 01 descargado correctamente.")

                    if sitfa.clic_rit(rit):
                        time.sleep(2)
                        sitfa.filtrar_y_guardar_csv(ruta_c, rit)

                        descarga_exitosa = False
                        for intento in range(3):
                            log(f"   Intentando descarga de PDF 02 (Intento {intento + 1}/3)...")
                            utils.limpiar_descargas(RobotConfig.ruta_descargas)
                            if sitfa.descargar_pdf_02(ruta_c):
                                descarga_exitosa = True
                                log("   PDF 02 descargado correctamente.")
                                break

                            log(f"   Fallo la descarga del PDF 02 en el intento {intento + 1}.")
                            if intento < 2:
                                log("   Recargando la causa para reintentar...")
                                sitfa.cerrar_dialogo()
                                sitfa.activar_pestana_automatica()
                                time.sleep(1)
                                if not sitfa.clic_rit(rit):
                                    log("   No se pudo volver a entrar en la causa. Abortando reintentos.")
                                    break
                                time.sleep(2)

                        if not descarga_exitosa:
                            log("   FALLO CRITICO: No se pudo descargar el PDF 02 despues de 3 intentos.")
                        sitfa.cerrar_dialogo()

                if RobotConfig.detener_solicitado:
                    break
                log(f"Finalizada pagina {num_p}. Navegando...")
                hay_mas_paginas = sitfa.cambiar_pagina()
                num_p += 1
    except PlaywrightSetupError as e:
        log(f"Error Playwright: {e}")
        mostrar_error("Playwright", str(e))
        return
    except Exception as e:
        log(f"Error en Parte 1 con Playwright: {e}")
        mostrar_error("Error", f"No se pudo completar Parte 1:\n{e}")
        return

    estado = "Detenido por el usuario" if RobotConfig.detener_solicitado else "Finalizado correctamente"
    mensaje_final = f"{estado}. La descarga de causas ha terminado."
    enviar_notificacion(mensaje_final, topic=RobotConfig.canal_secreto)
    mostrar_info("Proceso Terminado", mensaje_final)


def ejecutar_parte_1():
    ejecutar_en_hilo(_ejecutar_parte_1_worker)


def _ejecutar_parte_2_worker(ruta_csv):
    RobotConfig.detener_solicitado = False
    try:
        df = pd.read_csv(ruta_csv, sep=';', header=None, names=["RIT", "Estado"], dtype=str)
        pendientes = df[df["Estado"].str.strip() == "Ok"]["RIT"].str.strip().tolist()
    except Exception as e:
        log(f"No se pudo leer el CSV: {e}")
        return

    log("Iniciando Parte 2 con Playwright...")
    marcados = 0

    try:
        with abrir_sesion_sitfa(parent=root) as sitfa:
            hay_mas = True
            while hay_mas and pendientes:
                if RobotConfig.detener_solicitado:
                    break

                rits_en_pantalla = sitfa.extraer_lista_rits()
                if not rits_en_pantalla:
                    log("No se detectaron RITs en esta pagina.")
                    break

                for rit_web in rits_en_pantalla:
                    if RobotConfig.detener_solicitado:
                        break
                    if rit_web in pendientes:
                        resultado = sitfa.marcar_revisado_por_rit(rit_web)
                        if resultado:
                            marcados += 1
                            log(f"Marcado en orden: {rit_web}")
                            pendientes.remove(rit_web)

                if pendientes and not RobotConfig.detener_solicitado:
                    if sitfa.cambiar_pagina():
                        log("Pasando a la siguiente pagina de la bandeja...")
                        hay_mas = True
                    else:
                        log("No hay mas paginas disponibles.")
                        hay_mas = False
                else:
                    hay_mas = False
    except PlaywrightSetupError as e:
        log(f"Error Playwright: {e}")
        mostrar_error("Playwright", str(e))
        return
    except Exception as e:
        log(f"Error en Parte 2 con Playwright: {e}")
        mostrar_error("Error", f"No se pudo completar Parte 2:\n{e}")
        return

    estado = "Detenido por el usuario" if RobotConfig.detener_solicitado else "Finalizado correctamente"
    mensaje_final = f"{estado}. Marcado terminado: {marcados} causas procesadas."
    enviar_notificacion(mensaje_final, topic=RobotConfig.canal_secreto)
    mostrar_info("Proceso Terminado", mensaje_final)


def ejecutar_parte_2():
    ruta_csv = filedialog.askopenfilename(title="Selecciona CSV de Estados", filetypes=[("CSV", "*.csv")])
    if not ruta_csv:
        return
    ejecutar_en_hilo(_ejecutar_parte_2_worker, ruta_csv)



CONFIG_FILE = utils.obtener_ruta_externa("config_rutas.txt")

def guardar_configuracion():
    """Guarda las rutas actuales de RobotConfig en un archivo de texto."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(f"{RobotConfig.ruta_descargas}\n")
        f.write(f"{RobotConfig.ruta_destino_padre}\n")
        f.write(f"{RobotConfig.canal_secreto}\n")
        f.write(f"{RobotConfig.usuario_sitfa}\n")
        f.write(f"{RobotConfig.tipo_bandeja}\n")
        f.write("1" if RobotConfig.navegador_visible else "0")

def cargar_configuracion():
    """Lee el archivo si existe y carga las rutas en RobotConfig. Si no existe, lo crea."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            lineas = f.read().splitlines()
            if len(lineas) >= 1:
                RobotConfig.ruta_descargas = lineas[0]
            if len(lineas) >= 2:
                RobotConfig.ruta_destino_padre = lineas[1]
            if len(lineas) >= 3:
                RobotConfig.canal_secreto = lineas[2]
            offset = 1 if len(lineas) >= 4 and lineas[3].startswith("http") else 0
            if len(lineas) >= 4 + offset:
                RobotConfig.usuario_sitfa = lineas[3 + offset]
            if len(lineas) >= 5 + offset:
                RobotConfig.tipo_bandeja = lineas[4 + offset] if lineas[4 + offset] in ("auto", "manual") else "auto"
            if len(lineas) >= 6 + offset:
                RobotConfig.navegador_visible = lineas[5 + offset].strip() not in ("0", "false", "False", "no", "No")
    else:
        log(f"'{os.path.basename(CONFIG_FILE)}' no encontrado. Creando archivo con rutas por defecto.")
        guardar_configuracion()

def iniciar_gui():
    global root
    root = ctk.CTk() # Ahora usamos CTk
    RobotConfig.ventana_ref = root
    root.title("SITFA BOT")
    
    # Cargar y aplicar el icono
    ruta_icono = utils.obtener_ruta_recurso("robot.ico")
    if os.path.exists(ruta_icono):
        root.iconbitmap(ruta_icono)

    root.geometry("800x500")

    # Configurar cuadrícula (Grid)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(0, weight=1)

    # --- Sidebar (Barra Lateral) ---
    sidebar = ctk.CTkFrame(root, width=200, corner_radius=0)
    sidebar.grid(row=0, column=0, sticky="nsew")
    
    label_title = ctk.CTkLabel(sidebar, text="MENU", font=ctk.CTkFont(size=20, weight="bold"))
    label_title.pack(pady=20, padx=10)

    btn_p1 = ctk.CTkButton(sidebar, text="PASO 1: Descargas", command=ejecutar_parte_1, height=40)
    btn_p1.pack(pady=10, padx=20)

    btn_revision = ctk.CTkButton(sidebar, text="Revisar Integridad", command=ejecutar_revision_integridad, height=40, fg_color="#5f6a6b", hover_color="#798587")
    btn_revision.pack(pady=10, padx=20)

    # --- BOTÓN DE ANÁLISIS (CORREGIDO) ---
    btn_analisis = ctk.CTkButton(
        sidebar, 
        text="📊 ANALIZAR DATOS", 
        fg_color="#2c3e50", 
        hover_color="#34495e",
        command=abrir_modulo_analisis, # <--- Sin 'self.'
        height=40
    )
    btn_analisis.pack(pady=10, padx=20)

    btn_p2 = ctk.CTkButton(sidebar, text="PASO 2: Marcado", command=ejecutar_parte_2, height=40)
    btn_p2.pack(pady=10, padx=20)

    # Desactivado temporalmente el checkbox de auditoría de litigantes
    def actualizar_valor_check():
        RobotConfig.auditar_litigantes = check_var.get()
        log(f"⚙️ Auditoría: {'Habilitada' if RobotConfig.auditar_litigantes else 'Deshabilitada'}")

    check_var = ctk.BooleanVar(value=False) # Valor por defecto a True, pero no se usará si está oculto
    check_auditoria = ctk.CTkCheckBox(sidebar, text="Auditar Litigantes", 
                                       variable=check_var, command=actualizar_valor_check)
    check_auditoria.pack(pady=20, padx=20)


    btn_stop = ctk.CTkButton(sidebar, text="DETENER ROBOT", fg_color="#c0392b", hover_color="#e74c3c", 
                             command=solicitar_detencion, height=40)
    btn_stop.pack(side="bottom", pady=20, padx=20)

    # --- Main Content (Consola y Rutas) ---
    console_frame = ctk.CTkFrame(root, corner_radius=10)
    console_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
    console_frame.grid_columnconfigure(0, weight=1)
    
    # Configuramos las filas de rutas y dejamos la consola expandible
    console_frame.grid_rowconfigure(7, weight=1)

    usuario_sitfa_var = ctk.StringVar(value=RobotConfig.usuario_sitfa)
    password_sitfa_var = ctk.StringVar(value="")
    tipo_bandeja_var = ctk.StringVar(value=RobotConfig.tipo_bandeja)
    navegador_visible_var = ctk.StringVar(value="Si" if RobotConfig.navegador_visible else "No")

    def actualizar_credenciales_sitfa(*_):
        RobotConfig.usuario_sitfa = usuario_sitfa_var.get().strip()
        RobotConfig.password_sitfa = password_sitfa_var.get()

    def actualizar_tipo_bandeja(valor=None):
        RobotConfig.tipo_bandeja = tipo_bandeja_var.get()
        guardar_configuracion()
        log(f"Bandeja seleccionada: {'Manual' if RobotConfig.tipo_bandeja == 'manual' else 'Automatica'}")

    def actualizar_navegador_visible(valor=None):
        RobotConfig.navegador_visible = navegador_visible_var.get() == "Si"
        guardar_configuracion()
        log(f"Navegador visible: {'Si' if RobotConfig.navegador_visible else 'No'}")

    usuario_sitfa_var.trace_add("write", actualizar_credenciales_sitfa)
    password_sitfa_var.trace_add("write", actualizar_credenciales_sitfa)

    def seleccionar_ruta_descargas():
        ruta = filedialog.askdirectory(title="Seleccionar carpeta de Descargas")
        if ruta:
            RobotConfig.ruta_descargas = ruta
            txt_ruta_descargas.delete(0, "end")
            txt_ruta_descargas.insert(0, ruta)
            guardar_configuracion()
            log(f"📥 Descargas configurada en: {ruta}")

    def seleccionar_ruta_destino():
        ruta = filedialog.askdirectory(title="Seleccionar carpeta de Destino (Escritorio/Procesados)")
        if ruta:
            RobotConfig.ruta_destino_padre = ruta
            txt_ruta_destino.delete(0, "end")
            txt_ruta_destino.insert(0, ruta)
            guardar_configuracion()
            log(f"📁 Destino configurado en: {ruta}")

    def guardar_canal_secreto(event=None):
        canal = txt_canal_secreto.get().strip()
        RobotConfig.canal_secreto = canal
        guardar_configuracion()
        log(f"🔔 Canal secreto guardado: {canal if canal else '(Vacío, notificaciones desactivadas)'}")

    def guardar_usuario_sitfa(event=None):
        actualizar_credenciales_sitfa()
        guardar_configuracion()
        log(f"Usuario SITFA guardado: {RobotConfig.usuario_sitfa if RobotConfig.usuario_sitfa else '(vacio)'}")

    # --- Seccion de Rutas dentro de console_frame ---
    # Fila 0: Descargas
    lbl_descargas = ctk.CTkLabel(console_frame, text="Ruta Descargas:", font=("Arial", 12, "bold"))
    lbl_descargas.grid(row=0, column=0, padx=(20, 10), pady=(15, 5), sticky="w")
    
    txt_ruta_descargas = ctk.CTkEntry(console_frame, height=30)
    txt_ruta_descargas.grid(row=0, column=1, padx=5, pady=(15, 5), sticky="ew")
    
    btn_sel_descargas = ctk.CTkButton(console_frame, text="📁", width=40, command=seleccionar_ruta_descargas)
    btn_sel_descargas.grid(row=0, column=2, padx=(5, 20), pady=(15, 5))

    # Fila 1: Destino
    lbl_escritorio = ctk.CTkLabel(console_frame, text="Ruta Destino:", font=("Arial", 12, "bold"))
    lbl_escritorio.grid(row=1, column=0, padx=(20, 10), pady=5, sticky="w")
    
    txt_ruta_destino = ctk.CTkEntry(console_frame, height=30)
    txt_ruta_destino.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
    
    btn_sel_destino = ctk.CTkButton(console_frame, text="📁", width=40, command=seleccionar_ruta_destino)
    btn_sel_destino.grid(row=1, column=2, padx=(5, 20), pady=5)

    # Fila 2: Canal Secreto
    lbl_canal = ctk.CTkLabel(console_frame, text="Canal Secreto (ntfy):", font=("Arial", 12, "bold"))
    lbl_canal.grid(row=2, column=0, padx=(20, 10), pady=5, sticky="w")
    
    txt_canal_secreto = ctk.CTkEntry(console_frame, height=30, placeholder_text="Ej: mis_alertas_99")
    txt_canal_secreto.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
    txt_canal_secreto.bind("<FocusOut>", guardar_canal_secreto)
    txt_canal_secreto.bind("<Return>", guardar_canal_secreto)
    
    btn_guardar_canal = ctk.CTkButton(console_frame, text="💾", width=40, command=guardar_canal_secreto)
    btn_guardar_canal.grid(row=2, column=2, padx=(5, 20), pady=5)

    # Fila 3: Usuario SITFA
    lbl_usuario_sitfa = ctk.CTkLabel(console_frame, text="Usuario SITFA:", font=("Arial", 12, "bold"))
    lbl_usuario_sitfa.grid(row=3, column=0, padx=(20, 10), pady=5, sticky="w")

    txt_usuario_sitfa = ctk.CTkEntry(console_frame, height=30, textvariable=usuario_sitfa_var)
    txt_usuario_sitfa.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
    txt_usuario_sitfa.bind("<FocusOut>", guardar_usuario_sitfa)
    txt_usuario_sitfa.bind("<Return>", guardar_usuario_sitfa)

    btn_guardar_usuario = ctk.CTkButton(console_frame, text="Guardar", width=70, command=guardar_usuario_sitfa)
    btn_guardar_usuario.grid(row=3, column=2, padx=(5, 20), pady=5)

    # Fila 4: Clave SITFA
    lbl_password_sitfa = ctk.CTkLabel(console_frame, text="Clave SITFA:", font=("Arial", 12, "bold"))
    lbl_password_sitfa.grid(row=4, column=0, padx=(20, 10), pady=5, sticky="w")

    txt_password_sitfa = ctk.CTkEntry(console_frame, height=30, show="*", textvariable=password_sitfa_var)
    txt_password_sitfa.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

    # Fila 5: Tipo de Bandeja
    lbl_tipo_bandeja = ctk.CTkLabel(console_frame, text="Bandeja:", font=("Arial", 12, "bold"))
    lbl_tipo_bandeja.grid(row=5, column=0, padx=(20, 10), pady=5, sticky="w")

    opt_tipo_bandeja = ctk.CTkSegmentedButton(
        console_frame,
        values=["auto", "manual"],
        variable=tipo_bandeja_var,
        command=actualizar_tipo_bandeja,
    )
    opt_tipo_bandeja.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

    # Fila 6: Visibilidad del navegador
    lbl_navegador_visible = ctk.CTkLabel(console_frame, text="Navegador visible:", font=("Arial", 12, "bold"))
    lbl_navegador_visible.grid(row=6, column=0, padx=(20, 10), pady=5, sticky="w")

    opt_navegador_visible = ctk.CTkSegmentedButton(
        console_frame,
        values=["Si", "No"],
        variable=navegador_visible_var,
        command=actualizar_navegador_visible,
    )
    opt_navegador_visible.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

    console_frame.grid_columnconfigure(1, weight=1)


    

    # [PASO 3: LA FUNCIÓN DE REFRESCO]
    def refrescar_rutas_ui():
        # Borra lo que haya y escribe lo que está en RobotConfig
        txt_ruta_descargas.delete(0, "end")
        txt_ruta_descargas.insert(0, RobotConfig.ruta_descargas)
        
        txt_ruta_destino.delete(0, "end")
        txt_ruta_destino.insert(0, RobotConfig.ruta_destino_padre)
        
        txt_canal_secreto.delete(0, "end")
        txt_canal_secreto.insert(0, RobotConfig.canal_secreto)

        usuario_sitfa_var.set(RobotConfig.usuario_sitfa)
        password_sitfa_var.set("")
        tipo_bandeja_var.set(RobotConfig.tipo_bandeja)
        navegador_visible_var.set("Si" if RobotConfig.navegador_visible else "No")

    # [MUY IMPORTANTE] 
    # Llamamos a la función inmediatamente para que se llenen los cuadros al abrir
    refrescar_rutas_ui()
    
    # --- La Consola (ahora en la fila 7) ---
    RobotConfig.txt_consola = ctk.CTkTextbox(console_frame, fg_color="#ffffff", text_color="#000000", 
                                            font=("Consolas", 12))
    RobotConfig.txt_consola.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=20, pady=(10, 20))

    log("SITFA BOT iniciado correctamente.")
    root.mainloop() 

if __name__ == "__main__":
    if not verificar_actualizacion_obligatoria():
        sys.exit(0)
    cargar_configuracion()
    iniciar_gui()

    #prueba de git
    #prueba commit
