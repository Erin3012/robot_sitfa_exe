import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import csv
import json
from tkinter import filedialog, ttk # Importamos ttk para la tabla
import re
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import Counter
import utils


class VisorPDFInterno(ctk.CTkToplevel):
    def __init__(self, parent, ruta_pdf):
        super().__init__(parent)
        self.parent = parent
        self.ruta_pdf = ruta_pdf
        self.doc = None
        self.pagina_actual = 0
        self.zoom = 1.35
        self.imagen_tk = None

        self.title(f"Visor PDF - {os.path.basename(ruta_pdf)}")
        self.geometry("1000x750")

        try:
            try:
                import fitz
            except ModuleNotFoundError:
                import pymupdf as fitz
            self.fitz = fitz
            from PIL import Image, ImageTk
            self.Image = Image
            self.ImageTk = ImageTk
            self.doc = fitz.open(ruta_pdf)
        except Exception as e:
            messagebox.showerror(
                "Error al abrir PDF",
                "No se pudo cargar el visor interno.\n\n"
                f"Detalle: {e}\n\n"
                "Debe estar instalado PyMuPDF en el mismo Python con que se ejecuta el bot.\n\n"
                f"Python actual:\n{sys.executable}"
            )
            self.destroy()
            return

        self.frame_toolbar = ctk.CTkFrame(self)
        self.frame_toolbar.pack(side="top", fill="x", padx=8, pady=8)

        self.btn_anterior = ctk.CTkButton(self.frame_toolbar, text="Anterior", width=90, command=self.pagina_anterior)
        self.btn_anterior.pack(side="left", padx=4)

        self.lbl_pagina = ctk.CTkLabel(self.frame_toolbar, text="")
        self.lbl_pagina.pack(side="left", padx=10)

        self.btn_siguiente = ctk.CTkButton(self.frame_toolbar, text="Siguiente", width=90, command=self.pagina_siguiente)
        self.btn_siguiente.pack(side="left", padx=4)

        self.btn_zoom_menos = ctk.CTkButton(self.frame_toolbar, text="-", width=42, command=lambda: self.cambiar_zoom(-0.15))
        self.btn_zoom_menos.pack(side="left", padx=(20, 4))

        self.btn_zoom_mas = ctk.CTkButton(self.frame_toolbar, text="+", width=42, command=lambda: self.cambiar_zoom(0.15))
        self.btn_zoom_mas.pack(side="left", padx=4)

        self.canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0)
        self.scroll_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)

        self.scroll_y.pack(side="right", fill="y")
        self.scroll_x.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Left>", lambda _e: self.pagina_anterior())
        self.bind("<Right>", lambda _e: self.pagina_siguiente())
        self.bind("<Control-plus>", lambda _e: self.cambiar_zoom(0.15))
        self.bind("<Control-minus>", lambda _e: self.cambiar_zoom(-0.15))

        self.renderizar_pagina()
        self.focus_force()

    def renderizar_pagina(self):
        if not self.doc:
            return

        pagina = self.doc.load_page(self.pagina_actual)
        matriz = self.fitz.Matrix(self.zoom, self.zoom)
        pix = pagina.get_pixmap(matrix=matriz, alpha=False)
        imagen = self.Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        self.imagen_tk = self.ImageTk.PhotoImage(imagen)

        self.canvas.delete("all")
        self.canvas.create_image(20, 20, anchor="nw", image=self.imagen_tk)
        self.canvas.configure(scrollregion=(0, 0, pix.width + 40, pix.height + 40))

        total = len(self.doc)
        self.lbl_pagina.configure(text=f"Pagina {self.pagina_actual + 1} de {total} - Zoom {int(self.zoom * 100)}%")
        self.btn_anterior.configure(state="normal" if self.pagina_actual > 0 else "disabled")
        self.btn_siguiente.configure(state="normal" if self.pagina_actual < total - 1 else "disabled")

    def pagina_anterior(self):
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.renderizar_pagina()

    def pagina_siguiente(self):
        if self.doc and self.pagina_actual < len(self.doc) - 1:
            self.pagina_actual += 1
            self.renderizar_pagina()

    def cambiar_zoom(self, delta):
        self.zoom = max(0.6, min(3.0, self.zoom + delta))
        self.renderizar_pagina()

    def cerrar(self):
        try:
            if self.doc:
                self.doc.close()
        finally:
            self.destroy()


class VisorPDFComparador(ctk.CTkToplevel):
    def __init__(self, parent, ruta_pdf_01, ruta_pdf_02):
        super().__init__(parent)
        self.withdraw()
        self.parent = parent
        self.rutas = [ruta_pdf_01, ruta_pdf_02]
        self.docs = [None, None]
        self.pagina_actual = 0
        self.zoom = 1.25
        self.imagen_tk = None
        self.imagenes_tk = []
        self._scrollregion_width = 1
        self._scrollregion_height = 1
        self._redibujar_centrado_job = None
        self._centrado_habilitado = False
        self.fitz = None
        self.Image = None
        self.ImageTk = None
        self.ImageDraw = None

        self.title("Comparar PDF 1 y PDF 2")
        self.geometry("1400x820")
        self.transient(parent)

        try:
            try:
                import fitz
            except ModuleNotFoundError:
                import pymupdf as fitz
            from PIL import Image, ImageTk, ImageDraw

            self.fitz = fitz
            self.Image = Image
            self.ImageTk = ImageTk
            self.ImageDraw = ImageDraw
            self.docs = [fitz.open(ruta_pdf_01), fitz.open(ruta_pdf_02)]
        except Exception as e:
            messagebox.showerror(
                "Error al abrir PDF",
                "No se pudo cargar el comparador interno.\n\n"
                f"Detalle: {e}\n\n"
                f"Python actual:\n{sys.executable}"
            )
            self.destroy()
            return

        self.frame_toolbar = ctk.CTkFrame(self)
        self.frame_toolbar.pack(side="top", fill="x", padx=8, pady=8)

        self.lbl_pagina = ctk.CTkLabel(self.frame_toolbar, text="")
        self.lbl_pagina.pack(side="left", padx=10)

        self.btn_zoom_menos = ctk.CTkButton(self.frame_toolbar, text="-", width=42, command=lambda: self.cambiar_zoom(-0.15))
        self.btn_zoom_menos.pack(side="left", padx=(20, 4))

        self.btn_zoom_mas = ctk.CTkButton(self.frame_toolbar, text="+", width=42, command=lambda: self.cambiar_zoom(0.15))
        self.btn_zoom_mas.pack(side="left", padx=4)

        self.lbl_info = ctk.CTkLabel(self.frame_toolbar, text="")
        self.lbl_info.pack(side="left", padx=16)

        self.canvas = tk.Canvas(self, bg="#303030", highlightthickness=0)
        self.scroll_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)

        self.scroll_y.pack(side="right", fill="y")
        self.scroll_x.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._al_redimensionar_canvas)

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Control-plus>", lambda _e: self.cambiar_zoom(0.15))
        self.bind("<Control-minus>", lambda _e: self.cambiar_zoom(-0.15))
        self.canvas.bind("<MouseWheel>", self._scroll_mouse)
        self.bind("<MouseWheel>", self._scroll_mouse)
        self.canvas.bind("<Shift-MouseWheel>", self._scroll_mouse_horizontal)
        self.bind("<Shift-MouseWheel>", self._scroll_mouse_horizontal)

        self.after(10, self._mostrar_en_primer_plano)

    def _total_paginas(self):
        return max(len(doc) for doc in self.docs if doc)

    def _mostrar_en_primer_plano(self):
        self.deiconify()
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry("1400x820")

        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.canvas.focus_set()
        self.update_idletasks()
        self.renderizar_pagina()
        self._centrado_habilitado = True
        self.after(300, lambda: self.attributes("-topmost", False))

    def _renderizar_doc(self, indice_doc, pagina_indice):
        doc = self.docs[indice_doc]
        if not doc or pagina_indice >= len(doc):
            return None

        pagina = doc.load_page(pagina_indice)
        matriz = self.fitz.Matrix(self.zoom, self.zoom)
        pix = pagina.get_pixmap(matrix=matriz, alpha=False)
        return self.Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def _pagina_vacia(self, width, height, texto):
        imagen = self.Image.new("RGB", (width, height), "white")
        draw = self.ImageDraw.Draw(imagen)
        draw.rectangle((0, 0, width - 1, height - 1), outline="#bbbbbb", width=2)
        draw.text((40, 40), texto, fill="#555555")
        return imagen

    def _normalizar_palabra_pdf(self, texto):
        texto = str(texto or "").lower().strip()
        texto = texto.replace("\u00a0", " ")
        texto = re.sub(r"\s+", " ", texto)
        texto = re.sub(r"^[^\wáéíóúüñ]+|[^\wáéíóúüñ]+$", "", texto, flags=re.IGNORECASE)
        return texto

    def _palabras_pagina(self, indice_doc, pagina_indice):
        doc = self.docs[indice_doc]
        if not doc or pagina_indice >= len(doc):
            return []

        pagina = doc.load_page(pagina_indice)
        palabras = []
        for item in pagina.get_text("words"):
            x0, y0, x1, y1, texto = item[:5]
            normalizado = self._normalizar_palabra_pdf(texto)
            if normalizado:
                palabras.append({
                    "texto": normalizado,
                    "bbox": (x0, y0, x1, y1),
                })
        return palabras

    def _indices_texto_distinto(self, palabras_01, palabras_02):
        import difflib

        secuencia_01 = [p["texto"] for p in palabras_01]
        secuencia_02 = [p["texto"] for p in palabras_02]
        matcher = difflib.SequenceMatcher(None, secuencia_01, secuencia_02, autojunk=False)
        distintos_01 = set()
        distintos_02 = set()

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("replace", "delete"):
                distintos_01.update(range(i1, i2))
            if tag in ("replace", "insert"):
                distintos_02.update(range(j1, j2))

        return distintos_01, distintos_02

    def _dibujar_resaltado_texto(self, imagen, palabras, indices):
        if not indices:
            return imagen, 0

        base = imagen.convert("RGBA")
        overlay = self.Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = self.ImageDraw.Draw(overlay)

        for indice in indices:
            x0, y0, x1, y1 = palabras[indice]["bbox"]
            rect = (
                int(x0 * self.zoom) - 2,
                int(y0 * self.zoom) - 2,
                int(x1 * self.zoom) + 2,
                int(y1 * self.zoom) + 2,
            )
            draw.rectangle(rect, fill=(255, 235, 59, 95), outline=(220, 40, 40, 220), width=2)

        return self.Image.alpha_composite(base, overlay).convert("RGB"), len(indices)

    def _resaltar_diferencias_texto(self, imagen_01, imagen_02, pagina_indice):
        palabras_01 = self._palabras_pagina(0, pagina_indice)
        palabras_02 = self._palabras_pagina(1, pagina_indice)
        distintos_01, distintos_02 = self._indices_texto_distinto(palabras_01, palabras_02)

        imagen_01, cambios_01 = self._dibujar_resaltado_texto(imagen_01, palabras_01, distintos_01)
        imagen_02, cambios_02 = self._dibujar_resaltado_texto(imagen_02, palabras_02, distintos_02)
        return imagen_01, imagen_02, cambios_01 + cambios_02

    def renderizar_pagina(self):
        if not all(self.docs):
            return

        margen = 24
        cabecera = 38
        separacion = 24
        espacio_paginas = 34
        y_actual = 0
        ancho_maximo = 0
        cambios_total = 0
        filas_renderizadas = []

        self.canvas.delete("all")
        self.imagenes_tk = []

        total = self._total_paginas()
        for pagina_indice in range(total):
            imagen_01 = self._renderizar_doc(0, pagina_indice)
            imagen_02 = self._renderizar_doc(1, pagina_indice)

            ancho_base = max((imagen_01.width if imagen_01 else 0), (imagen_02.width if imagen_02 else 0), 700)
            alto_base = max((imagen_01.height if imagen_01 else 0), (imagen_02.height if imagen_02 else 0), 900)

            if imagen_01 is None:
                imagen_01 = self._pagina_vacia(ancho_base, alto_base, "PDF 1 sin pagina")
            if imagen_02 is None:
                imagen_02 = self._pagina_vacia(ancho_base, alto_base, "PDF 2 sin pagina")

            imagen_01, imagen_02, cambios = self._resaltar_diferencias_texto(imagen_01, imagen_02, pagina_indice)
            cambios_total += cambios

            ancho_fila = imagen_01.width + imagen_02.width + margen * 2 + separacion
            alto_fila = max(imagen_01.height, imagen_02.height) + margen * 2 + cabecera
            ancho_maximo = max(ancho_maximo, ancho_fila)

            fila = self.Image.new("RGB", (ancho_fila, alto_fila), "#303030")
            draw = self.ImageDraw.Draw(fila)
            x1 = margen
            x2 = margen + imagen_01.width + separacion
            y = margen + cabecera

            draw.text((x1, margen), f"Pagina {pagina_indice + 1} - PDF 1 - 01.pdf", fill="white")
            draw.text((x2, margen), f"Pagina {pagina_indice + 1} - PDF 2 - 02.pdf", fill="white")
            fila.paste(imagen_01, (x1, y))
            fila.paste(imagen_02, (x2, y))

            filas_renderizadas.append((fila, y_actual, ancho_fila))
            y_actual += alto_fila + espacio_paginas

        self.update_idletasks()
        ancho_visible = max(self.canvas.winfo_width(), 1)
        ancho_scroll = max(ancho_visible, ancho_maximo)

        for fila, y_fila, ancho_fila in filas_renderizadas:
            imagen_tk = self.ImageTk.PhotoImage(fila)
            self.imagenes_tk.append(imagen_tk)
            x_fila = max((ancho_scroll - ancho_fila) // 2, 0)
            self.canvas.create_image(x_fila, y_fila, anchor="nw", image=imagen_tk)

        self._scrollregion_width = max(ancho_scroll, 1)
        self._scrollregion_height = max(y_actual, 1)
        self.canvas.configure(scrollregion=(0, 0, self._scrollregion_width, self._scrollregion_height))
        self.lbl_pagina.configure(text=f"{total} paginas - Zoom {int(self.zoom * 100)}%")
        self.lbl_info.configure(text=f"Palabras distintas resaltadas: {cambios_total}")

    def _scroll_mouse(self, event):
        if not event.delta:
            return

        alto_visible = max(self.canvas.winfo_height(), 1)
        max_scroll = max(self._scrollregion_height - alto_visible, 1)
        actual = self.canvas.yview()[0] * self._scrollregion_height
        desplazamiento = -event.delta / 120 * 34
        nuevo = min(max(actual + desplazamiento, 0), max_scroll)
        self.canvas.yview_moveto(nuevo / self._scrollregion_height)

    def _scroll_mouse_horizontal(self, event):
        if not event.delta:
            return

        ancho_visible = max(self.canvas.winfo_width(), 1)
        max_scroll = max(self._scrollregion_width - ancho_visible, 1)
        actual = self.canvas.xview()[0] * self._scrollregion_width
        desplazamiento = -event.delta / 120 * 34
        nuevo = min(max(actual + desplazamiento, 0), max_scroll)
        self.canvas.xview_moveto(nuevo / self._scrollregion_width)

    def _al_redimensionar_canvas(self, _event):
        if not self._centrado_habilitado:
            return
        if self._redibujar_centrado_job:
            self.after_cancel(self._redibujar_centrado_job)
        self._redibujar_centrado_job = self.after(150, self._redibujar_por_cambio_tamano)

    def _redibujar_por_cambio_tamano(self):
        self._redibujar_centrado_job = None
        self.renderizar_pagina()

    def cambiar_zoom(self, delta):
        self.zoom = max(0.6, min(3.0, self.zoom + delta))
        self.renderizar_pagina()

    def cerrar(self):
        try:
            for doc in self.docs:
                if doc:
                    doc.close()
        finally:
            self.destroy()


class VentanaAnalisis(ctk.CTkToplevel):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.start_time = datetime.now()
        self._timer_job = None

        # --- Carga de Filtros ---
        self.filtro_valores = set()
        self.ruta_filtros = utils.asegurar_recurso_externo('filtros.json')
        try:
            with open(self.ruta_filtros, 'r', encoding='utf-8') as f:
                # Convertimos todo a minúsculas al cargar para comparación insensible
                self.filtro_valores = {str(item).lower() for item in json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            messagebox.showwarning("Archivo no encontrado", 
                                   f"No se pudo cargar 'filtros.json'. La función de coloreado no estará activa.\nError: {e}")

        from config import RobotConfig
        
        # Calculamos la carpeta de hoy por defecto
        hoy = datetime.now().strftime("%d-%m-%Y")
        ruta_hoy = os.path.join(RobotConfig.ruta_destino_padre, hoy)
        self.rit_var = ctk.StringVar(value="-")

        # Lógica: Si la carpeta de hoy ya existe, empezamos ahí. 
        # Si no, empezamos en la carpeta raíz de causas.
        if os.path.exists(ruta_hoy):
            self.ruta_seleccionada = ruta_hoy
        else:
            self.ruta_seleccionada = RobotConfig.ruta_destino_padre
        
        self.title("📊 Analizador de Causas (Estilo VBA)")
        self.geometry("1350x600")
        self.state('zoomed')
        
        # --- Main Scrollable Frame ---
        self.scrollable_frame = ctk.CTkScrollableFrame(self)
        self.scrollable_frame.pack(side="top", fill="both", expand=True)
        
        # Variables de control
        
        self.carpetas = []
        self.indice_actual = 0

        # --- Interfaz ---
        # Frame para el botón de cambiar carpeta y el menú desplegable
        self.frame_superior = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        self.frame_superior.pack(pady=15, fill="x", padx=20)

        # Mantenemos el botón, pero le damos un color sutil
        self.btn_ruta = ctk.CTkButton(self.frame_superior, text="📁 Cambiar Carpeta de Análisis",
                                    command=self.seleccionar_ruta,
                                    fg_color="#e7eef7",
                                    hover_color="#d7e3f3",
                                    text_color="#1f2d3d")
        self.btn_ruta.pack(side="left", padx=(0, 10))

        # Lista de opciones para el menú desplegable
        opciones_desplegable = [str(i) for i in range(2, 37)]
        self.variable_desplegable = ctk.StringVar(value=opciones_desplegable[4]) # Valor por defecto

        self.menu_desplegable = ctk.CTkOptionMenu(self.frame_superior,
                                                  values=opciones_desplegable,
                                                  variable=self.variable_desplegable)
        self.menu_desplegable.pack(side="left", padx=(0, 10))

        # Checkbox para validación
        self.check_validacion_var = ctk.BooleanVar(value=True)
        self.check_validacion = ctk.CTkCheckBox(self.frame_superior, text="Validar Meses",
                                                 variable=self.check_validacion_var,
                                                 command=self.actualizar_vista)
        self.check_validacion.pack(side="left")

        # --- Temporizador ---
        self.lbl_temporizador = ctk.CTkLabel(self.frame_superior, text="00:00", font=("Arial", 16, "bold"))
        self.lbl_temporizador.pack(side="right")

       
        # Añadimos una etiqueta que nos diga QUÉ día estamos viendo
        self.lbl_ruta_actual = ctk.CTkLabel(self.scrollable_frame, text=f"Viendo: {os.path.basename(self.ruta_seleccionada)}",
                                            font=("Arial", 11, "italic"))
        self.lbl_ruta_actual.pack(pady=(0, 10), anchor="w", fill="x") # Aseguramos anclaje a la izquierda y relleno horizontal

        # Carga inicial automática de lo que haya en la ruta actual
        self.after(200, self.cargar_causas_automatico)

        # --- Contenedor para RIT de Carpeta y Estado ---
        self.frame_cabecera = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        self.frame_cabecera.pack(pady=5, padx=40, fill="x")
        
        # {{ INICIO DE MODIFICACIÓN PARA TÍTULOS DE TEXTBOX }}

        # --- Contenedor para el RIT de Carpeta ---
        self.frame_rit_carpeta = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_rit_carpeta.pack(side="left", padx=(0, 20), anchor="w") # Empaqueta este frame a la izquierda

        # Título para el RIT de la Carpeta
        self.lbl_rit_carpeta_titulo = ctk.CTkLabel(self.frame_rit_carpeta, text="RIT de Carpeta:", font=("Arial", 10, "bold"))
        self.lbl_rit_carpeta_titulo.pack(pady=(0,2), anchor="w") # Etiqueta arriba del Entry

        # NUEVO: StringVar para el textbox del RIT de navegación de la carpeta
        # Lo iniciamos vacío o con un placeholder para que la función actualizar_vista lo llene
        self.rit_carpeta_entry_var = ctk.StringVar(value="Cargando...")

        # Entry para el RIT de navegación
        self.txt_rit_carpeta_actual = ctk.CTkEntry(self.frame_rit_carpeta, font=("Arial", 16, "bold"),
                                                    justify="center", height=40, width=100,
                                                    textvariable=self.rit_carpeta_entry_var) # Quitamos placeholder_text
        self.txt_rit_carpeta_actual.pack(anchor="w") # Empaquetado dentro de su frame

        # Guardamos el color original una sola vez para usarlo en los reseteos
        self.default_entry_color = self.txt_rit_carpeta_actual.cget("fg_color")

        # --- Contenedor para el Estado ---
        self.frame_estado_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_estado_container.pack(side="left", padx=(0, 20), anchor="w")

        # Título para el Estado
        self.lbl_estado_titulo = ctk.CTkLabel(self.frame_estado_container, text="Estado:", font=("Arial", 10, "bold"))
        self.lbl_estado_titulo.pack(pady=(0,2), anchor="w")

        # Entry del ESTADO - Existente
        self.txt_estado = ctk.CTkEntry(self.frame_estado_container, font=("Arial", 16, "bold"), 
                                        justify="center", height=40, width=100,
                                        placeholder_text="Sin Estado")
        self.txt_estado.pack(anchor="w")
        
        # --- Contenedor para el Último Periodo (01.txt) ---
        self.frame_ultimo_periodo_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        # Mantener un padx para separar del "Estado"
        self.frame_ultimo_periodo_container.pack(side="left", padx=(0, 20), anchor="w") 

        # Título para el Último Periodo (01.txt)
        self.lbl_ultimo_periodo_titulo = ctk.CTkLabel(self.frame_ultimo_periodo_container, text="Periodo actual:", font=("Arial", 10, "bold")) # Modificado texto de etiqueta
        self.lbl_ultimo_periodo_titulo.pack(pady=(0,2), anchor="w")

        # StringVar para el nuevo textbox
        self.ultimo_periodo_entry_var = ctk.StringVar(value="N/D")

        # Nuevo Entry para el Último Periodo (01.txt)
        self.txt_ultimo_periodo = ctk.CTkEntry(self.frame_ultimo_periodo_container, font=("Arial", 16, "bold"),
                                                justify="center", height=40, width=90,
                                                textvariable=self.ultimo_periodo_entry_var)
        self.txt_ultimo_periodo.pack(anchor="w")

        

        # {{ INICIO MODIFICACIÓN: Nuevo contenedor para el Último Periodo de 02.txt a la derecha }}
        # --- Contenedor para el Último Periodo (02.txt) ---
        self.frame_ultimo_periodo_02_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_ultimo_periodo_02_container.pack(side="left", anchor="w") # Empaquetado a la derecha del anterior

        # Título para el Último Periodo de 02.txt
        self.lbl_ultimo_periodo_02_titulo = ctk.CTkLabel(self.frame_ultimo_periodo_02_container, text="Periodo anterior:", font=("Arial", 10, "bold"))
        self.lbl_ultimo_periodo_02_titulo.pack(pady=(0,2), anchor="w")

        # StringVar para el nuevo textbox
        self.ultimo_periodo_entry_var_02 = ctk.StringVar(value="N/D")

        # Nuevo Entry para el Último Periodo de 02.txt
        self.txt_ultimo_periodo_02 = ctk.CTkEntry(self.frame_ultimo_periodo_02_container, font=("Arial", 16, "bold"),
                                                justify="center", height=40, width=90,
                                                textvariable=self.ultimo_periodo_entry_var_02)
        self.txt_ultimo_periodo_02.pack(anchor="w")

        # --- Contenedor para la Última Pensión (01.txt) ---
        self.frame_ultima_pension_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_ultima_pension_container.pack(side="left", padx=(0, 20), anchor="w")

        self.lbl_ultima_pension_titulo = ctk.CTkLabel(self.frame_ultima_pension_container, text="Pensión actual:", font=("Arial", 10, "bold"))
        self.lbl_ultima_pension_titulo.pack(pady=(0,2), anchor="w")

        self.ultima_pension_entry_var = ctk.StringVar(value="N/D")
        self.txt_ultima_pension = ctk.CTkEntry(self.frame_ultima_pension_container, font=("Arial", 16, "bold"),
                                                justify="center", height=40, width=90,
                                                textvariable=self.ultima_pension_entry_var)
        self.txt_ultima_pension.pack(anchor="w")


        # --- Contenedor para la Última Pensión (02.txt) ---
        self.frame_ultima_pension_02_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_ultima_pension_02_container.pack(side="left", anchor="w", padx=(0, 20))

        self.lbl_ultima_pension_02_titulo = ctk.CTkLabel(self.frame_ultima_pension_02_container, text="Pensión (02.txt):", font=("Arial", 10, "bold"))
        self.lbl_ultima_pension_02_titulo.pack(pady=(0,2), anchor="w")

        self.ultima_pension_entry_var_02 = ctk.StringVar(value="N/D")
        self.txt_ultima_pension_02 = ctk.CTkEntry(self.frame_ultima_pension_02_container, font=("Arial", 16, "bold"),
                                                justify="center", height=40, width=90,
                                                textvariable=self.ultima_pension_entry_var_02)
        self.txt_ultima_pension_02.pack(anchor="w")

        # --- Contenedor para Total UTM (01.txt) ---
        self.frame_total_utm_01_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_total_utm_01_container.pack(side="left", padx=(0, 20), anchor="w")

        self.lbl_total_utm_01_titulo = ctk.CTkLabel(self.frame_total_utm_01_container, text="Total UTM (01):", font=("Arial", 10, "bold"))
        self.lbl_total_utm_01_titulo.pack(pady=(0,2), anchor="w")

        self.total_utm_01_var = ctk.StringVar(value="N/D")
        self.txt_total_utm_01 = ctk.CTkEntry(self.frame_total_utm_01_container, font=("Arial", 16, "bold"),
                                               justify="center", height=40, width=90,
                                               textvariable=self.total_utm_01_var)
        self.txt_total_utm_01.pack(anchor="w")


        

        # --- Contenedor para Total UTM (02.txt) ---
        self.frame_total_utm_02_container = ctk.CTkFrame(self.frame_cabecera, fg_color="transparent")
        self.frame_total_utm_02_container.pack(side="left", anchor="w", padx=(20, 0))

        self.lbl_total_utm_02_titulo = ctk.CTkLabel(self.frame_total_utm_02_container, text="Total UTM (02):", font=("Arial", 10, "bold"))
        self.lbl_total_utm_02_titulo.pack(pady=(0,2), anchor="w")

        self.total_utm_02_var = ctk.StringVar(value="N/D")
        self.txt_total_utm_02 = ctk.CTkEntry(self.frame_total_utm_02_container, font=("Arial", 16, "bold"),
                                               justify="center", height=40, width=90,
                                               textvariable=self.total_utm_02_var)
        self.txt_total_utm_02.pack(anchor="w")


        # --- TREEVIEW (EL LISTBOX ESTILO VBA) ---
        # 1. Primero creamos el frame que contendrá AMBAS tablas
        self.frame_tabla = ctk.CTkFrame(self.scrollable_frame)
        self.frame_tabla.pack(pady=10, padx=20, fill="both", expand=True)

        # 2. Configuramos el estilo
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Treeview", background="#ffffff", foreground="#1f2937", fieldbackground="#ffffff", rowheight=25)
        self.style.configure("Treeview.Heading", background="#e5e7eb", foreground="#111827")
        self.style.map("Treeview", background=[('selected', '#cfe3ff')])

        # Nuevo estilo para tablas validadas en verde
        self.style.configure("Valid.Treeview", background="#e9f8ee", foreground="#1f2937", fieldbackground="#e9f8ee", rowheight=25)
        self.style.map("Valid.Treeview", background=[('selected', '#cfe3ff')])
        
        # Nuevo estilo para tablas NO validadas (rojo)
        self.style.configure("Invalid.Treeview", background="#fcebea", foreground="#1f2937", fieldbackground="#fcebea", rowheight=25)
        self.style.map("Invalid.Treeview", background=[('selected', '#cfe3ff')])

        # --- Contenedor para la PRIMERA tabla (principal) ---
        self.frame_tabla_principal = ctk.CTkFrame(self.frame_tabla, fg_color="transparent") # Nuevo frame
        # Empaquetamos a la izquierda, expandiendo y rellenando, con un padx para separar de la siguiente tabla
        self.frame_tabla_principal.pack(side="left", fill="both", expand=True, padx=(0, 10)) 

        # 3. CREAMOS LA TABLA PRINCIPAL (El padre debe ser self.frame_tabla_principal)
        self.tabla = ttk.Treeview(self.frame_tabla_principal, columns=("Fecha", "Referencia"), show="headings")
        self.tabla.heading("Fecha", text="FECHA")
        self.tabla.heading("Referencia", text="REFERENCIA / TRÁMITE")
        
        self.tabla.column("Fecha", width=100, anchor="w")
        self.tabla.column("Referencia", width=300, anchor="w") # Ajustado para dejar espacio a la derecha

        # Scrollbar para la tabla principal
        scrollbar_principal = ttk.Scrollbar(self.frame_tabla_principal, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scrollbar_principal.set)

        # Configuramos el tag para pintar filas de verde si coinciden con el filtro
        self.tabla.tag_configure('en_filtro', background='#e9f8ee')
        self.tabla.tag_configure('fuera_filtro', background='#fcebea') # Rojo suave

        self.tabla.pack(side="left", fill="both", expand=True)
        scrollbar_principal.pack(side="right", fill="y")


        # --- Frame para los nuevos botones al lado de la tabla principal ---
        self.frame_botones_filtro = ctk.CTkFrame(self.frame_tabla, fg_color="transparent")
        self.frame_botones_filtro.pack(side="left", fill="y", padx=5, anchor="n")

        self.btn_agregar_filtro = ctk.CTkButton(self.frame_botones_filtro, text="Filtrar", command=self.accion_filtrar, width=80)
        self.btn_agregar_filtro.pack(pady=(0, 5), padx=5)

        self.btn_revisar_filtros = ctk.CTkButton(self.frame_botones_filtro, text="Revisar", command=self.accion_revisar_filtros, width=80)
        self.btn_revisar_filtros.pack(pady=5, padx=5)

        # Botón para ocultar/mostrar la tabla secundaria
        self.tabla_secundaria_visible = True
        self.btn_toggle_tabla = ctk.CTkButton(self.frame_botones_filtro, text="Ocultar\nLitigantes", command=self.toggle_tabla_secundaria, width=80)
        self.btn_toggle_tabla.pack(pady=5, padx=5)

        # {{ INICIO DEL NUEVO CÓDIGO PARA LA SEGUNDA TABLA }}
        # --- Contenedor para la SEGUNDA tabla (a la derecha) ---
        self.frame_tabla_secundaria = ctk.CTkFrame(self.frame_tabla, fg_color="transparent") # Nuevo frame
        # Empaquetamos a la izquierda, a la derecha de la tabla principal
        self.frame_tabla_secundaria.pack(side="left", fill="both", expand=True)

        # Columnas para la nueva tabla: Sujeto, RUT, Nombre, Edad
        columnas_secundaria = ("Sujeto", "RUT", "Nombre", "Edad") # <--- MODIFICADO
        self.tabla_secundaria = ttk.Treeview(self.frame_tabla_secundaria, columns=columnas_secundaria, show="headings")
        
        for col in columnas_secundaria:
            self.tabla_secundaria.heading(col, text=col.upper())
            # Ajusta anchos para las nuevas columnas
            if col == "Sujeto":
                self.tabla_secundaria.column(col, width=60, anchor="center")
            elif col == "RUT":
                self.tabla_secundaria.column(col, width=100, anchor="w")
            elif col == "Nombre":
                self.tabla_secundaria.column(col, width=150, anchor="w")
            elif col == "Edad":
                self.tabla_secundaria.column(col, width=50, anchor="center")
        
        # Elimina esta línea si no necesitas un ajuste específico para 'Comentarios'
        # self.tabla_secundaria.column("Comentarios", width=200, anchor="w") 

        # Scrollbar para la tabla secundaria
        scrollbar_secundaria = ttk.Scrollbar(self.frame_tabla_secundaria, orient="vertical", command=self.tabla_secundaria.yview)
        self.tabla_secundaria.configure(yscrollcommand=scrollbar_secundaria.set)

        # Tag para colorear filas de la tabla secundaria
        self.tabla_secundaria.tag_configure('verde_secundaria', background='#e9f8ee')
        self.tabla_secundaria.tag_configure('rojo_secundaria', background='#fcebea')
        
        self.tabla_secundaria.pack(side="left", fill="both", expand=True)
        scrollbar_secundaria.pack(side="right", fill="y")
        # {{ FIN DEL NUEVO CÓDIGO PARA LA SEGUNDA TABLA }}

        # --- CONTENEDOR PARA TABLAS DE TEXTO (01.txt vs 02.txt) ---
        # Definimos el contenedor principal para las dos columnas
        self.frame_txt_horizontal = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        self.frame_txt_horizontal.pack(pady=10, padx=20, fill="both", expand=True)

        self.frame_txt_horizontal.grid_columnconfigure(0, weight=1)
        self.frame_txt_horizontal.grid_columnconfigure(1, weight=1)

        # --- COLUMNA IZQUIERDA (Otros Cargos 1 - 01.txt) ---
        self.col_izq = ctk.CTkFrame(self.frame_txt_horizontal)
        self.col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # 1. Título y Entry para el RIT de 01.txt
        ctk.CTkLabel(self.col_izq, text="RIT (01.txt):", font=("Arial", 10, "bold")).pack(pady=(5, 0), anchor="w", padx=20)
        self.txt_rit_01 = ctk.CTkEntry(
            self.col_izq, 
            textvariable=self.rit_var, 
            font=("Arial", 16, "bold"),
            justify="center",
            height=40,
            width=150
        )
        self.txt_rit_01.pack(pady=(2, 0), anchor="w", padx=20)
        
        # 3. TÍTULO DE LA TABLA
        ctk.CTkLabel(self.col_izq, text="III. OTROS CARGOS (01.txt)", font=("Arial", 11, "bold")).pack(pady=(5, 0))
        
        # 4. LA TABLA (Al final de la columna)
        columnas_txt = ("Fecha", "Movimiento", "Tipo", "UTM")
        self.tabla_txt1 = ttk.Treeview(self.col_izq, columns=columnas_txt, show="headings")
        
        for col in columnas_txt:
            self.tabla_txt1.heading(col, text=col.upper())
            self.tabla_txt1.column(col, width=80, anchor="center")
        
        self.tabla_txt1.column("Movimiento", width=120, anchor="w")

        # Scrollbar y empaquetado de la tabla
        scroll1 = ttk.Scrollbar(self.col_izq, orient="vertical", command=self.tabla_txt1.yview)
        self.tabla_txt1.configure(yscrollcommand=scroll1.set)
        
        self.tabla_txt1.pack(side="left", fill="both", expand=True)
        scroll1.pack(side="right", fill="y")

        # --- COLUMNA DERECHA (Otros Cargos 2 - 02.txt) ---
        self.col_der = ctk.CTkFrame(self.frame_txt_horizontal)
        self.col_der.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Título y Entry para el RIT de 02.txt
        self.rit_var_2 = ctk.StringVar(value="-")
        ctk.CTkLabel(self.col_der, text="RIT (02.txt):", font=("Arial", 10, "bold")).pack(pady=(5, 0), anchor="w", padx=20)
        self.txt_rit_02 = ctk.CTkEntry(
            self.col_der, 
            textvariable=self.rit_var_2, 
            font=("Arial", 16, "bold"), 
            justify="center",
            height=40,
            width=150
        )
        self.txt_rit_02.pack(pady=(2, 0), anchor="w", padx=20)

        # Título de la tabla Otros Cargos 2
        ctk.CTkLabel(self.col_der, text="III. OTROS CARGOS (02.txt)", font=("Arial", 11, "bold")).pack(pady=(5, 0))
        
        # --- TABLA 02.txt ---
        self.tabla_txt2 = ttk.Treeview(self.col_der, columns=columnas_txt, show="headings")
        # Configurar encabezados
        for col in columnas_txt:
            self.tabla_txt2.heading(col, text=col.upper())
            self.tabla_txt2.column(col, width=80, anchor="center")
            
        self.tabla_txt2.column("Movimiento", width=120, anchor="w")
        self.tabla_txt2.pack(side="left", fill="both", expand=True)

        # Scrollbar para Tabla 2 (El padre debe ser self.col_der)
        scroll2 = ttk.Scrollbar(self.col_der, orient="vertical", command=self.tabla_txt2.yview)
        self.tabla_txt2.configure(yscrollcommand=scroll2.set)
        
        self.tabla_txt2.pack(side="left", fill="both", expand=True)
        scroll2.pack(side="right", fill="y")

        # --- CONTENEDOR PARA TABLAS DE ABONOS ---
        self.frame_abonos_horizontal = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        self.frame_abonos_horizontal.pack(pady=10, padx=20, fill="both", expand=True)

        self.frame_abonos_horizontal.grid_columnconfigure(0, weight=1)
        self.frame_abonos_horizontal.grid_columnconfigure(1, weight=1)
        
        # --- COLUMNA IZQUIERDA (Otros Abonos 1 - 01.txt) ---
        self.col_abonos_izq = ctk.CTkFrame(self.frame_abonos_horizontal)
        self.col_abonos_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(self.col_abonos_izq, text="IV. OTROS ABONOS (01.txt)", font=("Arial", 11, "bold")).pack(pady=(5, 0))
        
        columnas_txt = ("Fecha", "Movimiento", "Tipo", "UTM")
        self.tabla_abonos1 = ttk.Treeview(self.col_abonos_izq, columns=columnas_txt, show="headings")
        
        for col in columnas_txt:
            self.tabla_abonos1.heading(col, text=col.upper())
            self.tabla_abonos1.column(col, width=80, anchor="center")
        
        self.tabla_abonos1.column("Movimiento", width=120, anchor="w")

        scroll_abonos1 = ttk.Scrollbar(self.col_abonos_izq, orient="vertical", command=self.tabla_abonos1.yview)
        self.tabla_abonos1.configure(yscrollcommand=scroll_abonos1.set)
        
        self.tabla_abonos1.pack(side="left", fill="both", expand=True)
        scroll_abonos1.pack(side="right", fill="y")

        # --- COLUMNA DERECHA (Otros Abonos 2 - 02.txt) ---
        self.col_abonos_der = ctk.CTkFrame(self.frame_abonos_horizontal)
        self.col_abonos_der.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ctk.CTkLabel(self.col_abonos_der, text="IV. OTROS ABONOS (02.txt)", font=("Arial", 11, "bold")).pack(pady=(5, 0))
        
        self.tabla_abonos2 = ttk.Treeview(self.col_abonos_der, columns=columnas_txt, show="headings")
        
        for col in columnas_txt:
            self.tabla_abonos2.heading(col, text=col.upper())
            self.tabla_abonos2.column(col, width=80, anchor="center")
        
        self.tabla_abonos2.column("Movimiento", width=120, anchor="w")

        scroll_abonos2 = ttk.Scrollbar(self.col_abonos_der, orient="vertical", command=self.tabla_abonos2.yview)
        self.tabla_abonos2.configure(yscrollcommand=scroll_abonos2.set)
        
        self.tabla_abonos2.pack(side="left", fill="both", expand=True)
        scroll_abonos2.pack(side="right", fill="y")

        # 5. AHORA creamos el frame de los botones (más abajo)
        self.frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botones.pack(side="bottom", pady=10)


        # Evento de selección (Como el ListBox_Click en VBA)
        self.tabla.bind("<<TreeviewSelect>>", self.al_seleccionar_fila)

        self.btn_volver = ctk.CTkButton(self.frame_botones, text="◀ Volver", width=90, command=self.anterior)
        self.btn_volver.pack(side="left", padx=5)

        self.btn_confirmar = ctk.CTkButton(self.frame_botones, text="Confirmar", width=90, fg_color="#27ae60", command=self.accion_confirmar)
        self.btn_confirmar.pack(side="left", padx=5)

        self.btn_revisar = ctk.CTkButton(self.frame_botones, text="Revisar", width=90, 
                                         fg_color="#e7eef7", hover_color="#d7e3f3",
                                         text_color="#1f2d3d",
                                         command=self.accion_revisar)
        self.btn_revisar.pack(side="left", padx=5)

        self.btn_pdf_comparar = ctk.CTkButton(self.frame_botones, text="Comparar PDFs", width=115,
                                              fg_color="#8e44ad", hover_color="#7d3c98",
                                              command=self.abrir_comparador_pdfs)
        self.btn_pdf_comparar.pack(side="left", padx=5)

        self.btn_sig = ctk.CTkButton(self.frame_botones, text="Siguiente ▶", width=90, command=self.siguiente)
        self.btn_sig.pack(side="left", padx=5)

        self.lbl_conteo = ctk.CTkLabel(self, text="Esperando datos...")
        self.lbl_conteo.pack(side="bottom", pady=5)

        self.lift()

        self.protocol("WM_DELETE_WINDOW", self.al_cerrar_ventana)

        # Iniciar temporizador
        self.actualizar_temporizador()

    def al_cerrar_ventana(self):
        """Hace que el Formulario 1 vuelva a ser visible y destruye el actual."""
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        self.parent.deiconify() # Vuelve a mostrar la ventana principal
        self.destroy()           # Destruye la ventana de análisis

    def actualizar_temporizador(self):
        """Actualiza el contador de tiempo cada segundo."""
        elapsed_time = datetime.now() - self.start_time
        minutes, seconds = divmod(int(elapsed_time.total_seconds()), 60)
        
        # Formateamos a mm:ss
        tiempo_formateado = f"{minutes:02d}:{seconds:02d}"
        
        self.lbl_temporizador.configure(text=tiempo_formateado)
        
        # Lo volvemos a llamar en 1 segundo
        self._timer_job = self.after(1000, self.actualizar_temporizador)

    def leer_csv_carpeta(self, nombre_carpeta):
        """Carga el CSV en el Treeview separando por la primera coma."""
        ruta_csv = os.path.join(self.ruta_seleccionada, nombre_carpeta, f"{nombre_carpeta}.csv")
        
        # Limpiar tabla (Borrar items anteriores)
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        
        if os.path.exists(ruta_csv):
            try:
                # Abrimos el archivo en modo texto plano para controlar la separación manualmente
                with open(ruta_csv, mode='r', encoding='utf-8-sig') as f:
                    lineas = f.readlines()
                    
                    # Saltamos la primera línea si es el encabezado (Fecha,Referencia)
                    for i, linea in enumerate(lineas):
                        if i == 0 and "Fecha" in linea:
                            continue
                        
                        linea = linea.strip()
                        if not linea:
                            continue
                        
                        # split(',', 1) separa solo en la primera coma que encuentre
                        partes = linea.split(',', 1)
                        
                        if len(partes) == 2:
                            fecha = partes[0].strip()
                            referencia = partes[1].strip()
                            # Si está en el filtro: verde, si no: rojo
                            tags = ('en_filtro',) if referencia.lower() in self.filtro_valores else ('fuera_filtro',)
                            self.tabla.insert("", "end", values=(fecha, referencia), tags=tags)
                        else:
                            referencia = linea.strip()
                            tags = ('en_filtro',) if referencia.lower() in self.filtro_valores else ('fuera_filtro',)
                            self.tabla.insert("", "end", values=(referencia, ""), tags=tags)
                            
            except Exception as e:
                print(f"Error al leer el CSV '{ruta_csv}': {e}")
        
        self.ajustar_altura_tabla(self.tabla)

    def validar_y_colorear_periodos(self):
        """
        Valida que la diferencia entre los dos campos de 'Último Periodo' 
        sea de exactamente un mes y los colorea si la validación es exitosa.
        """
        # Primero, reseteamos el color a su valor por defecto del tema
        # Usamos el color de otro Entry como referencia para el color por defecto
        self.txt_ultimo_periodo.configure(fg_color=self.default_entry_color)
        self.txt_ultimo_periodo_02.configure(fg_color=self.default_entry_color)
        color_rojo = "#fcebea"

        periodo1_str = self.ultimo_periodo_entry_var.get()
        periodo2_str = self.ultimo_periodo_entry_var_02.get()

        if periodo1_str == "N/D" or periodo2_str == "N/D":
            return # No hacer nada si no hay fechas

        try:
            fecha1 = datetime.strptime(periodo1_str, '%m-%Y')
            fecha2 = datetime.strptime(periodo2_str, '%m-%Y')
            
            delta = relativedelta(fecha1, fecha2)
            
            # La diferencia absoluta debe ser de 1 mes
            if abs(delta.months + delta.years * 12) == 1:
                color_verde = "#e9f8ee" # Verde suave
                self.txt_ultimo_periodo.configure(fg_color=color_verde)
                self.txt_ultimo_periodo_02.configure(fg_color=color_verde)
            else:
                self.txt_ultimo_periodo.configure(fg_color=color_rojo)
                self.txt_ultimo_periodo_02.configure(fg_color=color_rojo)

        except (ValueError, TypeError):
            self.txt_ultimo_periodo.configure(fg_color=color_rojo)
            self.txt_ultimo_periodo_02.configure(fg_color=color_rojo)
            # print(f"Error al parsear fechas de periodo: {periodo1_str}, {periodo2_str}")

    def validar_y_colorear_rits(self):
        """
        Compara los RITs de la carpeta y de los archivos 01.txt y 02.txt.
        Si los tres son idénticos, los colorea de verde.
        """
        # 1. Resetear colores a los valores por defecto
        self.txt_rit_carpeta_actual.configure(fg_color=self.default_entry_color)
        self.txt_rit_01.configure(fg_color=self.default_entry_color)
        self.txt_rit_02.configure(fg_color=self.default_entry_color)

        # 2. Obtener valores
        rit_carpeta = self.rit_carpeta_entry_var.get().strip()
        rit_1 = self.rit_var.get().strip()
        rit_2 = self.rit_var_2.get().strip()

        # 3. Comparar y colorear
        if rit_carpeta and rit_1 and rit_2 and (rit_carpeta == rit_1 == rit_2):
            color_verde = "#e9f8ee"
            self.txt_rit_carpeta_actual.configure(fg_color=color_verde)
            self.txt_rit_01.configure(fg_color=color_verde)
            self.txt_rit_02.configure(fg_color=color_verde)
        else:
            color_rojo = "#fcebea"
            self.txt_rit_carpeta_actual.configure(fg_color=color_rojo)
            self.txt_rit_01.configure(fg_color=color_rojo)
            self.txt_rit_02.configure(fg_color=color_rojo)

    def toggle_tabla_secundaria(self):
        """Alterna la visibilidad de la tabla de litigantes (secundaria)."""
        if self.tabla_secundaria_visible:
            self.frame_tabla_secundaria.pack_forget()
            self.btn_toggle_tabla.configure(text="Mostrar\nLitigantes")
            self.tabla_secundaria_visible = False
        else:
            self.frame_tabla_secundaria.pack(side="left", fill="both", expand=True)
            self.btn_toggle_tabla.configure(text="Ocultar\nLitigantes")
            self.tabla_secundaria_visible = True

    def validar_y_colorear_pensiones(self):
        """
        Compara las pensiones extraídas de 01.txt y 02.txt.
        Si son idénticas y válidas, colorea los campos de verde.
        """
        self.txt_ultima_pension.configure(fg_color=self.default_entry_color)
        self.txt_ultima_pension_02.configure(fg_color=self.default_entry_color)

        p1 = self.ultima_pension_entry_var.get()
        p2 = self.ultima_pension_entry_var_02.get()

        if p1 != "N/D" and p1 == p2:
            color_verde = "#e9f8ee"
            self.txt_ultima_pension.configure(fg_color=color_verde)
            self.txt_ultima_pension_02.configure(fg_color=color_verde)
        else:
            color_rojo = "#fcebea"
            self.txt_ultima_pension.configure(fg_color=color_rojo)
            self.txt_ultima_pension_02.configure(fg_color=color_rojo)

    def verificar_todo_verde(self):
        """
        Verifica si todos los indicadores visuales están en verde.
        Si se cumple, la causa es elegible para estado 'Ok' automático.
        """
        verde_hex = "#e9f8ee"
        
        # 1. Validar Textboxes (RIT, Periodos, Pensiones)
        entries = [
            self.txt_rit_carpeta_actual, self.txt_ultimo_periodo, 
            self.txt_ultimo_periodo_02, self.txt_ultima_pension, self.txt_ultima_pension_02
        ]
        if any(e.cget("fg_color") != verde_hex for e in entries):
            return False

        # 2. Validar Tablas de "Otros Cargos" y "Otros Abonos"
        if self.tabla_txt1.cget("style") != "Valid.Treeview" or self.tabla_txt2.cget("style") != "Valid.Treeview":
            return False
        if self.tabla_abonos1.cget("style") != "Valid.Treeview" or self.tabla_abonos2.cget("style") != "Valid.Treeview":
            return False

        # 3. Validar Tabla Principal (Todas las filas deben tener el tag 'en_filtro')
        filas_p = self.tabla.get_children()
        if not filas_p: return False
        for f in filas_p:
            if 'en_filtro' not in self.tabla.item(f, 'tags'):
                return False

        # 4. Validar Tabla Secundaria (Solo si es visible)
        if self.tabla_secundaria_visible:
            filas_s = self.tabla_secundaria.get_children()
            # Si está visible, exigimos que haya al menos un litigante validado (verde)
            if not filas_s: return False
            for f in filas_s:
                if 'verde_secundaria' not in self.tabla_secundaria.item(f, 'tags'):
                    return False
        
        return True

    def al_seleccionar_fila(self, event):
        """Se activa cuando el usuario hace clic en una fila (Como ListBox_Click)"""
        seleccion = self.tabla.selection()
        if seleccion:
            item = self.tabla.item(seleccion[0])
            valores = item['values']
            #print(f"Fila seleccionada: {valores}") # Aquí podrás aplicar tu función futura

    def validar_cargos(self):
        """
        Valida que las tablas de otros cargos sean iguales (independiente del orden) 
        y que sus fechas sean menores a la cantidad de meses especificada.
        Retorna True si es válido, False si no.
        """
        # 1. Obtener datos de las tablas
        filas1_ids = self.tabla_txt1.get_children()
        filas2_ids = self.tabla_txt2.get_children()

        # 2. Comparar número de filas
        if len(filas1_ids) != len(filas2_ids):
            #print("Validación fallida: Las tablas 'Otros Cargos' no tienen el mismo número de filas.")
            return False

        # Si ambas tablas están vacías, la validación es exitosa.
        if not filas1_ids and not filas2_ids:
            return True

        # 3. Comparar contenido de filas usando Counter para ignorar el orden
        rows1 = [tuple(self.tabla_txt1.item(item_id, 'values')) for item_id in filas1_ids]
        rows2 = [tuple(self.tabla_txt2.item(item_id, 'values')) for item_id in filas2_ids]

        if Counter(rows1) != Counter(rows2):
            #print("Validación fallida: El contenido de las tablas no es idéntico.")
            return False

        # 4. Validar fechas (ya que el contenido es el mismo, solo necesitamos iterar una tabla)
        try:
            meses_atras = int(self.variable_desplegable.get())
            fecha_limite = datetime.now() - relativedelta(months=meses_atras)
        except (ValueError, TypeError):
            print("Error de validación: El valor de meses no es un número válido.")
            return False

        for row_values in rows1:
            # Validar fecha en la primera columna
            try:
                fecha_fila = datetime.strptime(str(row_values[0]), '%d-%m-%Y')
                if fecha_fila >= fecha_limite:
                    #print(f"Validación fallida: La fecha '{row_values[0]}' no es válida (debe ser anterior a {meses_atras} meses).")
                    return False
            except ValueError:
                print(f"Validación fallida: La fecha '{row_values[0]}' no tiene el formato 'dd-mm-yyyy'.")
                return False
        
        return True

    def validar_abonos(self):
        """
        Valida que las tablas de otros abonos sean iguales (independiente del orden) 
        y que sus fechas sean menores a la cantidad de meses especificada.
        Retorna True si es válido, False si no.
        """
        # 1. Obtener datos de las tablas
        filas1_ids = self.tabla_abonos1.get_children()
        filas2_ids = self.tabla_abonos2.get_children()

        # 2. Comparar número de filas
        if len(filas1_ids) != len(filas2_ids):
            return False

        # Si ambas tablas están vacías, la validación es exitosa.
        if not filas1_ids and not filas2_ids:
            return True

        # 3. Comparar contenido de filas usando Counter para ignorar el orden
        rows1 = [tuple(self.tabla_abonos1.item(item_id, 'values')) for item_id in filas1_ids]
        rows2 = [tuple(self.tabla_abonos2.item(item_id, 'values')) for item_id in filas2_ids]

        if Counter(rows1) != Counter(rows2):
            return False

        # 4. Validar fechas (ya que el contenido es el mismo, solo necesitamos iterar una tabla)
        try:
            meses_atras = int(self.variable_desplegable.get())
            fecha_limite = datetime.now() - relativedelta(months=meses_atras)
        except (ValueError, TypeError):
            print("Error de validación: El valor de meses no es un número válido.")
            return False

        for row_values in rows1:
            # Validar fecha en la primera columna
            try:
                fecha_fila = datetime.strptime(str(row_values[0]), '%d-%m-%Y')
                if fecha_fila >= fecha_limite:
                    return False
            except ValueError:
                print(f"Validación fallida: La fecha '{row_values[0]}' no tiene el formato 'dd-mm-yyyy'.")
                return False
        
        return True

    def accion_confirmar(self):
        self.gestionar_estado("Ok")
        self.ir_a_proxima_pendiente()

    # ... (Mantener funciones seleccionar_ruta, actualizar_vista, siguiente y anterior igual que antes) ...

    def seleccionar_ruta(self):
        from config import RobotConfig
        # Abrimos el explorador partiendo desde la base de causas para no perdernos
        nueva_ruta = filedialog.askdirectory(initialdir=RobotConfig.ruta_destino_padre, 
                                            title="Seleccionar carpeta de otro día")
        if nueva_ruta:
            self.ruta_seleccionada = nueva_ruta
            self.lbl_ruta_actual.configure(text=f"Viendo: {os.path.basename(nueva_ruta)}")
            self.cargar_causas_automatico()

    def abrir_pdf_causa(self, nombre_pdf):
        if not self.carpetas:
            messagebox.showwarning("Sin causa", "No hay una causa cargada.")
            return

        nombre_carpeta = self.carpetas[self.indice_actual]
        ruta_pdf = os.path.join(self.ruta_seleccionada, nombre_carpeta, nombre_pdf)

        if not os.path.exists(ruta_pdf):
            messagebox.showwarning("PDF no encontrado", f"No existe el archivo:\n{ruta_pdf}")
            return

        try:
            VisorPDFInterno(self, ruta_pdf)
        except Exception as e:
            messagebox.showerror("Error al abrir PDF", f"No se pudo abrir el archivo:\n{ruta_pdf}\n\n{e}")

    def abrir_comparador_pdfs(self):
        if not self.carpetas:
            messagebox.showwarning("Sin causa", "No hay una causa cargada.")
            return

        nombre_carpeta = self.carpetas[self.indice_actual]
        ruta_causa = os.path.join(self.ruta_seleccionada, nombre_carpeta)
        ruta_pdf_01 = os.path.join(ruta_causa, "01.pdf")
        ruta_pdf_02 = os.path.join(ruta_causa, "02.pdf")

        faltantes = [ruta for ruta in (ruta_pdf_01, ruta_pdf_02) if not os.path.exists(ruta)]
        if faltantes:
            messagebox.showwarning("PDF no encontrado", "No existe el archivo:\n" + "\n".join(faltantes))
            return

        try:
            VisorPDFComparador(self, ruta_pdf_01, ruta_pdf_02)
        except Exception as e:
            messagebox.showerror(
                "Error al comparar PDF",
                f"No se pudieron abrir los archivos:\n{ruta_pdf_01}\n{ruta_pdf_02}\n\n{e}"
            )

    def cargar_causas_automatico(self):
        """Esta es la función que faltaba"""
        if not self.ruta_seleccionada or not os.path.exists(self.ruta_seleccionada):
            print("Ruta no válida o vacía")
            return

        # Escaneamos las subcarpetas (RITs)
        self.carpetas = [f for f in os.listdir(self.ruta_seleccionada) 
                         if os.path.isdir(os.path.join(self.ruta_seleccionada, f))]
        
        if self.carpetas:
            self.indice_actual = 0
            self.actualizar_vista() # Asegúrate de tener esta función para mostrar el primer RIT
        else:
            print("No se encontraron carpetas en la ruta.")


    def actualizar_vista(self):
        if not self.carpetas: return

        # Reseteamos el estilo de las tablas de texto a su valor por defecto
        self.tabla_txt1.configure(style="Treeview")
        self.tabla_txt2.configure(style="Treeview")
        self.tabla_abonos1.configure(style="Treeview")
        self.tabla_abonos2.configure(style="Treeview")
    
        nombre_carpeta = self.carpetas[self.indice_actual]
        ruta_carpeta = os.path.join(self.ruta_seleccionada, nombre_carpeta)

        # Actualiza el label de la ruta de la carpeta (ej: "Viendo: 18-06-2024")
        self.lbl_ruta_actual.configure(text=f"Viendo: {os.path.basename(self.ruta_seleccionada)}")
        
        # Actualiza el nuevo textbox con el RIT de la carpeta actual (ej: "RIT Carpeta: C-123-2024")
        self.rit_carpeta_entry_var.set(f"{nombre_carpeta}")

        # --- Lógica para 01.txt ---
        ruta_txt_01 = os.path.join(ruta_carpeta, "01.txt")
        rit_01 = self.obtener_rit_desde_txt(ruta_txt_01)
        self.rit_var.set(rit_01)
        
        # Obtener RIT de 02.txt
        ruta_txt_02 = os.path.join(ruta_carpeta, "02.txt")
        rit_02 = self.obtener_rit_desde_txt(ruta_txt_02)
        self.rit_var_2.set(rit_02)

        # 2. Cargar tabla principal (CSV)
        self.leer_csv_carpeta(nombre_carpeta)
        
        # {{ NUEVA LLAMADA: Cargar tabla secundaria (CSV _2.csv) }}
        self.leer_csv_secundaria_carpeta(nombre_carpeta)

        # 3. Cargar las tablas de texto (01 y 02)
        headers = ("Fecha movimiento", "Tipo movimiento", "Referencia", "Monto UTM")
        self.leer_txt_especifico(nombre_carpeta, "01.txt", self.tabla_txt1, headers, 1)
        self.leer_txt_especifico(nombre_carpeta, "02.txt", self.tabla_txt2, headers, 1)
        self.leer_txt_especifico(nombre_carpeta, "01.txt", self.tabla_abonos1, headers, 2)
        self.leer_txt_especifico(nombre_carpeta, "02.txt", self.tabla_abonos2, headers, 2)

        # {{ MODIFICADO: Extraer solo la ÚLTIMA fila de la tabla de Periodos }}
        self.extraer_ultima_periodo_txt(nombre_carpeta, "01.txt")

        if self.ultima_periodo_data:
            self.ultimo_periodo_entry_var.set(self.ultima_periodo_data[0])
            if len(self.ultima_periodo_data) > 1:
                self.ultima_pension_entry_var.set(self.ultima_periodo_data[1])
            else: self.ultima_pension_entry_var.set("N/D")
        else:
            self.ultimo_periodo_entry_var.set("N/D")
            self.ultima_pension_entry_var.set("N/D")

        # {{ INICIO MODIFICACIÓN: Extraer y actualizar para el 02.txt }}
        self.extraer_ultima_periodo_txt_02(nombre_carpeta, "02.txt")

        if self.ultima_periodo_data_02:
            self.ultimo_periodo_entry_var_02.set(self.ultima_periodo_data_02[0])
            if len(self.ultima_periodo_data_02) > 1:
                self.ultima_pension_entry_var_02.set(self.ultima_periodo_data_02[1])
            else: self.ultima_pension_entry_var_02.set("N/D")
        else:
            self.ultimo_periodo_entry_var_02.set("N/D")
            self.ultima_pension_entry_var_02.set("N/D")
        
        # Extraer y actualizar Totales UTM
        self.total_utm_01_var.set(self.extraer_total_liq_txt(nombre_carpeta, "01.txt"))
        self.total_utm_02_var.set(self.extraer_total_liq_txt(nombre_carpeta, "02.txt"))

        
        # 4. Actualizar etiquetas de conteo
        self.lbl_conteo.configure(text=f"Causa {self.indice_actual + 1} de {len(self.carpetas)}")
        self.btn_volver.configure(state="normal" if self.indice_actual > 0 else "disabled")
        self.btn_sig.configure(state="normal" if self.indice_actual < len(self.carpetas) - 1 else "disabled")

        # Lógica de validación de diferencia de periodo
        self.validar_y_colorear_periodos()

        # Lógica de validación de RITs
        self.validar_y_colorear_rits()

        # Lógica de validación de pensiones
        self.validar_y_colorear_pensiones()

        # Lógica de validación de tablas
        if self.check_validacion_var.get():
            if self.validar_cargos():
                self.tabla_txt1.configure(style="Valid.Treeview")
                self.tabla_txt2.configure(style="Valid.Treeview")
            else:
                self.tabla_txt1.configure(style="Invalid.Treeview")
                self.tabla_txt2.configure(style="Invalid.Treeview")

            if self.validar_abonos():
                self.tabla_abonos1.configure(style="Valid.Treeview")
                self.tabla_abonos2.configure(style="Valid.Treeview")
            else:
                self.tabla_abonos1.configure(style="Invalid.Treeview")
                self.tabla_abonos2.configure(style="Invalid.Treeview")

        # 5. Gestión de Estado (Honrando estados previos)
        # Primero leemos el estado actual del archivo para no sobreescribir algo manual
        estado_existente = self.gestionar_estado() 
        if not estado_existente and self.verificar_todo_verde():
            self.gestionar_estado("Ok")

        # LÓGICA: Si el último periodo O la pensión está en rojo y no hay estado, se marca como "Revisar"
        red_color = "#fcebea"
        is_period_red = (self.txt_ultimo_periodo.cget("fg_color") == red_color or
                         self.txt_ultimo_periodo_02.cget("fg_color") == red_color)
        is_pension_red = (self.txt_ultima_pension.cget("fg_color") == red_color or
                          self.txt_ultima_pension_02.cget("fg_color") == red_color)

        # Si el periodo O la pensión está en rojo Y no hay un estado ya asignado (ni "Ok" ni "Revisar" manual)
        if (is_period_red or is_pension_red) and not estado_existente:
            self.gestionar_estado("Revisar") # Asigna el estado "Revisar"


    def ir_a_proxima_pendiente(self):
        """
        Navega hacia adelante saltando causas que ya tienen estado
        o que cumplen con la validación automática 'Todo Verde'.
        """
        encontrada = False
        while self.indice_actual < len(self.carpetas) - 1:
            self.indice_actual += 1
            self.actualizar_vista()
            
            # Si después de actualizar_vista (que incluye el auto-Ok) el campo 
            # de estado sigue vacío, es que esta causa requiere atención.
            if not self.txt_estado.get().strip():
                encontrada = True
                break
            # Si tiene estado (Ok o Revisar), el bucle continúa (salto automático)
        
        if not encontrada:
            # Si recorrimos todo y no hay pendientes, mostrar mensaje
            messagebox.showinfo("Fin de lista", "No se encontraron más causas pendientes de revisión.")
            # Nos quedamos en la última cargada
            self.actualizar_vista()

    # {{ NUEVO MÉTODO PARA EXTRAER SOLO LA ÚLTIMA FILA DE LA TABLA DE PERIODOS CON VALIDACIÓN }}
    def extraer_ultima_periodo_txt(self, nombre_carpeta, nombre_archivo):
        """
        Lee el archivo .txt para extraer la última fila válida de la tabla de 'PERIODOS'
        y la guarda en self.ultima_periodo_data.
        Valida que la primera columna ('Periodo') tenga formato 'MM-AAAA'.
        """
        ruta_txt = os.path.join(self.ruta_seleccionada, nombre_carpeta, nombre_archivo)
        # {{ MODIFICADO: Variable para almacenar la última fila de Periodos de 01.txt }}
        self.ultima_periodo_data = None 
        # {{ NUEVO: Variable para almacenar la última fila de Periodos de 02.txt }}
        self.ultima_periodo_data_02 = None
        # {{ FIN MODIFICACIÓN }}

        # Evento de selección (Como el ListBox_Click en VBA)
        self.tabla.bind("<<TreeviewSelect>>", self.al_seleccionar_fila)

        if not os.path.exists(ruta_txt):
            return

        try:
            with open(ruta_txt, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
            
            capturar_periodos = False
            last_valid_row = None # Variable temporal para guardar la última fila válida encontrada

            for linea in lineas:
                texto = linea.strip()
                if not texto: continue

                # Detectar el inicio de la tabla de PERIODOS
                if ("Periodo" in texto and "Pensión" in texto and 
                    "Pago adic." in texto and "Adeudado" in texto):
                    capturar_periodos = True
                    continue # Saltar la línea de encabezados

                # Detectar el final de la tabla de PERIODOS (ej. línea "Total" o inicio de nueva sección)
                # Esta lógica debe ser precisa para tus archivos.
                if capturar_periodos and ("Total" in texto or ("V." in texto and "Otros elementos" in texto)): 
                    break # Detener la captura si se encuentra el final de la tabla
                
                if capturar_periodos:
                    # Separar por tabuladores o 2+ espacios
                    partes = [p.strip() for p in re.split(r'\t|\s{2,}', texto) if p.strip()]
                    
                    # Se esperan 7 columnas para Periodos
                    if len(partes) >= 7:
                        periodo_str = partes[0]
                        # --- VALIDACIÓN DE FORMATO MES-AÑO (MM-AAAA) ---
                        if re.match(r'^\d{2}-\d{4}$', periodo_str):
                            last_valid_row = tuple(partes[:7]) # Guardar esta como la última fila válida
                        else:
                            print(f"Saltando fila por formato 'Periodo' inválido: '{periodo_str}' en {nombre_carpeta}/{nombre_archivo}")
            
            self.ultima_periodo_data = last_valid_row # Asignar la última fila válida encontrada
                            
        except Exception as e:
            print(f"Error extrayendo la última fila de 'PERIODOS' en '{ruta_txt}': {e}")
        
    # {{ FIN NUEVO MÉTODO }}

    # {{ NUEVO MÉTODO PARA EXTRAER SOLO LA ÚLTIMA FILA DE LA TABLA DE PERIODOS DE 02.TXT }}
    def extraer_ultima_periodo_txt_02(self, nombre_carpeta, nombre_archivo):
        """
        Lee el archivo .txt (02.txt) para extraer la última fila válida de la tabla de 'PERIODOS'
        y la guarda en self.ultima_periodo_data_02.
        Valida que la primera columna ('Periodo') tenga formato 'MM-AAAA'.
        """
        ruta_txt = os.path.join(self.ruta_seleccionada, nombre_carpeta, nombre_archivo)
        self.ultima_periodo_data_02 = None # Reiniciar la variable en cada actualización

        if not os.path.exists(ruta_txt):
            return

        try:
            with open(ruta_txt, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
            
            capturar_periodos = False
            last_valid_row = None 

            for linea in lineas:
                texto = linea.strip()
                if not texto: continue

                # Detectar el inicio de la tabla de PERIODOS
                if ("Periodo" in texto and "Pensión" in texto and 
                    "Pago adic." in texto and "Adeudado" in texto):
                    capturar_periodos = True
                    continue 

                # Detectar el final de la tabla de PERIODOS (ajusta según tus archivos 02.txt)
                if capturar_periodos and ("Total" in texto or ("V." in texto and "Otros elementos" in texto)): 
                    break 
                
                if capturar_periodos:
                    partes = [p.strip() for p in re.split(r'\t|\s{2,}', texto) if p.strip()]
                    
                    if len(partes) >= 7:
                        periodo_str = partes[0]
                        if re.match(r'^\d{2}-\d{4}$', periodo_str):
                            last_valid_row = tuple(partes[:7]) 
                        else:
                            print(f"Saltando fila por formato 'Periodo' inválido: '{periodo_str}' en {nombre_carpeta}/{nombre_archivo} (02.txt)")
            
            self.ultima_periodo_data_02 = last_valid_row
                            
        except Exception as e:
            print(f"Error extrayendo la última fila de 'PERIODOS' en '{ruta_txt}' (02.txt): {e}")
        
    # {{ FIN NUEVO MÉTODO }}

    def extraer_total_liq_txt(self, nombre_carpeta, nombre_archivo):
        """
        Busca la tabla 'ABONOS CARGOS PERIODOS ADEUDADOS TOTAL LIQUIDACIÓN UTM' 
        y extrae el último valor de la siguiente fila de datos.
        """
        ruta_txt = os.path.join(self.ruta_seleccionada, nombre_carpeta, nombre_archivo)
        if not os.path.exists(ruta_txt): return "N/D"

        try:
            with open(ruta_txt, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
            
            for i, linea in enumerate(lineas):
                texto = linea.strip()
                # Identificamos el encabezado de la tabla de liquidación total
                if "ABONOS" in texto and "TOTAL LIQUIDACIÓN UTM" in texto:
                    # Buscamos en las líneas inmediatamente siguientes la fila con los valores
                    for j in range(i + 1, min(i + 6, len(lineas))):
                        posible_fila = lineas[j].strip()
                        if not posible_fila: continue
                        partes = [p.strip() for p in re.split(r'\t|\s{2,}', posible_fila) if p.strip()]
                        if len(partes) >= 4:
                            return partes[-1] # El último valor es el TOTAL LIQUIDACIÓN UTM
        except Exception as e:
            print(f"Error extrayendo Total UTM en {nombre_archivo}: {e}")
        return "N/D"

    def obtener_rit_desde_txt(self, ruta_archivo):
        # ... tu código existente ...
        """
        Lee la primera línea del archivo .txt y extrae el valor del RIT.
        Ejemplo de línea: 'RIT\tC-241-2025'
        """
        try:
            if not os.path.exists(ruta_archivo):
                return "S/R" # Sin RIT
                
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                primera_linea = f.readline()
                if not primera_linea:
                    return "S/R"
                
                # Dividimos por el tabulador
                partes = primera_linea.split('\t')
                
                if len(partes) >= 2:
                    # El RIT es la segunda parte, quitamos espacios o saltos de línea
                    rit = partes[1].strip()
                    return rit
            return "S/R"
        except Exception as e:
            print(f"Error al leer RIT: {e}")
            return "Error"

    def siguiente(self):
        if self.indice_actual < len(self.carpetas) - 1:
            self.indice_actual += 1
            self.actualizar_vista()

    def anterior(self):
        if self.indice_actual > 0:
            self.indice_actual -= 1
            self.actualizar_vista()

    def accion_revisar(self):
        self.gestionar_estado("Revisar")
        self.ir_a_proxima_pendiente()

    def accion_filtrar(self):
        """Agrega la referencia de la fila seleccionada (en minúsculas) al archivo de filtros."""
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Sin selección", "Por favor, selecciona una fila de la tabla principal para filtrar.")
            return

        item = self.tabla.item(seleccion[0])
        valores = item['values']
        if len(valores) < 2:
            return

        referencia = str(valores[1])
        referencia_lower = referencia.lower()

        if referencia_lower in self.filtro_valores:
            self.tabla.item(seleccion[0], tags=('en_filtro',))
            return

        self.filtro_valores.add(referencia_lower)
        
        lista_para_guardar = sorted(list(self.filtro_valores))
        try:
            with open(self.ruta_filtros, 'w', encoding='utf-8') as f:
                json.dump(lista_para_guardar, f, ensure_ascii=False, indent=4)
        except Exception as e:
            messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo 'filtros.json'.\nError: {e}")
            self.filtro_valores.remove(referencia_lower)
            return

        self.tabla.item(seleccion[0], tags=('en_filtro',))

    def accion_revisar_filtros(self):
        """Muestra una ventana con la lista de todos los filtros guardados."""
        win_filtros = ctk.CTkToplevel(self)
        win_filtros.title("Filtros Guardados")
        win_filtros.geometry("400x500")
        win_filtros.attributes('-topmost', True)

        txt_filtros = ctk.CTkTextbox(win_filtros, wrap="word", state="disabled")
        txt_filtros.pack(expand=True, fill="both", padx=10, pady=10)

        # Usamos el set en memoria (self.filtro_valores) como la fuente de verdad para evitar inconsistencias
        if self.filtro_valores:
            lista_filtros = sorted(list(self.filtro_valores))
            contenido = "\n".join(lista_filtros)
        else:
            contenido = "No hay filtros guardados."

        txt_filtros.configure(state="normal")
        txt_filtros.delete("1.0", "end")
        txt_filtros.insert("1.0", contenido)
        txt_filtros.configure(state="disabled")

        btn_cerrar = ctk.CTkButton(win_filtros, text="Cerrar", command=win_filtros.destroy)
        btn_cerrar.pack(pady=10)
        
        

    def leer_otros_cargos_txt(self, nombre_carpeta):
        ruta_txt = os.path.join(self.ruta_seleccionada, nombre_carpeta, "01.txt")
        
        # Limpiar la tabla antes de cargar
        for item in self.tabla_txt.get_children():
            self.tabla_txt.delete(item)
            
        if os.path.exists(ruta_txt):
            try:
                with open(ruta_txt, "r", encoding="utf-8") as f:
                    lineas = f.readlines()
                
                capturar = False
                for linea in lineas:
                    if "III." in linea and "Otros cargos" in linea: 
                        capturar = True
                        continue
                    if "IV." in linea and "Otros abonos" in linea:
                        capturar = False
                        break
                    
                    if capturar:
                        texto = linea.strip()
                        # Filtramos encabezados y la fila Total 
                        if texto and "Fecha movimiento" not in texto and "Total" not in texto:
                            # El archivo usa espacios múltiples como separador 
                            partes = [p.strip() for p in texto.split("  ") if p.strip()]
                            
                            # Según el archivo: Fecha | Tipo | Referencia | Monto 
                            if len(partes) >= 4:
                                self.tabla_txt.insert("", "end", values=(partes[0], partes[1], partes[2], partes[3]))
                            elif len(partes) == 3:
                                # Caso donde Tipo y Referencia vengan pegados
                                self.tabla_txt.insert("", "end", values=(partes[0], "Cargo", partes[1], partes[2]))
                                
            except Exception as e:
                print(f"Error procesando 01.txt: {e}")

    def leer_txt_especifico(self, nombre_carpeta, nombre_archivo, tabla_destino, headers, occurrence=1):
        ruta_txt = os.path.join(self.ruta_seleccionada, nombre_carpeta, nombre_archivo)
        
        for item in tabla_destino.get_children():
            tabla_destino.delete(item)
            
        if os.path.exists(ruta_txt):
            try:
                with open(ruta_txt, "r", encoding="utf-8", errors="replace") as f:
                    lineas = f.readlines()
                
                capturando = False
                header_found_count = 0
                for linea in lineas:
                    texto = linea.strip()
                    if not texto: continue

                    is_header = all(h in texto for h in headers)

                    if is_header:
                        header_found_count += 1
                        if header_found_count == occurrence:
                            capturando = True
                            continue

                    if capturando and texto.startswith("Total"):
                        break

                    if capturando and "Fecha movimiento" not in texto:
                        partes = [p.strip() for p in re.split(r'\t|\s{2,}', texto) if p.strip()]
                        
                        if len(partes) >= 3:
                            fecha = partes[0]
                            movimiento = partes[1]
                            referencia = partes[2] if len(partes) > 2 else "---"
                            monto_utm = partes[-1]
                            
                            tabla_destino.insert("", "end", values=(fecha, movimiento, referencia, monto_utm))
                                
            except Exception as e:
                print(f"Error procesando {nombre_archivo} con headers {headers}: {e}")
        
        self.ajustar_altura_tabla(tabla_destino, max_height=6)



    def ajustar_altura_tabla(self, tabla, max_height=10):
        """Ajusta la altura de una tabla Treeview al número de filas, con un tope máximo."""
        num_filas = len(tabla.get_children())
        # La altura es el mínimo entre el número de filas y el máximo permitido
        altura = min(num_filas, max_height)
        # Si no hay filas, podemos poner una altura de 1 para que se vea el encabezado
        altura_final = altura if altura > 0 else 1
        tabla.configure(height=altura_final)

    def gestionar_estado(self, nuevo_estado=None):
        """Lee o actualiza el estado de la causa en el archivo maestro."""
        if not self.ruta_seleccionada or not self.carpetas:
            return ""
            
        archivo_maestro = os.path.join(self.ruta_seleccionada, "estado_causas.csv")
        rit_actual = self.carpetas[self.indice_actual]
        estados = {}

        # 1. Leer estados existentes si el archivo existe
        if os.path.exists(archivo_maestro):
            try:
                with open(archivo_maestro, "r", encoding="utf-8") as f:
                    lector = csv.reader(f, delimiter=";")
                    estados = {fila[0]: fila[1] for fila in lector if len(fila) >= 2}
            except Exception as e:
                print(f"Error al leer estados: {e}")

        # 2. Si venimos de un botón (Confirmar/Revisar), actualizamos el diccionario
        if nuevo_estado:
            estados[rit_actual] = nuevo_estado
            try:
                with open(archivo_maestro, "w", encoding="utf-8", newline="") as f:
                    escritor = csv.writer(f, delimiter=";")
                    for rit, est in estados.items():
                        escritor.writerow([rit, est])
            except Exception as e:
                print(f"Error al guardar estado: {e}")

        # 3. Mostrar el estado en el textbox
        estado_actual = estados.get(rit_actual, "")
        self.txt_estado.delete(0, "end")
        self.txt_estado.insert(0, estado_actual)
        
        # Color visual opcional según el estado
        if estado_actual == "Ok":
            self.txt_estado.configure(text_color="#2ecc71") # Verde
        elif estado_actual == "Revisar":
            self.txt_estado.configure(text_color="#e67e22") # Naranja
        else:
            self.txt_estado.configure(text_color="white")

        return estado_actual

    def leer_csv_secundaria_carpeta(self, nombre_carpeta):
        """Carga, filtra y colorea el CSV '..._2.csv' en la tabla secundaria."""
        ruta_csv = os.path.join(self.ruta_seleccionada, nombre_carpeta, f"{nombre_carpeta}_2.csv")
        
        for item in self.tabla_secundaria.get_children():
            self.tabla_secundaria.delete(item)
        
        if not os.path.exists(ruta_csv):
            return

        all_rows_data = []
        try:
            with open(ruta_csv, mode='r', encoding='utf-8-sig') as f:
                lineas = f.readlines()
                
                for i, linea in enumerate(lineas):
                    if i == 0 and ("Sujeto" in linea or "sujeto" in linea):
                        continue
                    linea = linea.strip()
                    if not linea:
                        continue
                    
                    partes = linea.split(';', 3)
                    sujeto = partes[0].strip() if len(partes) > 0 else ""
                    rut = partes[1].strip() if len(partes) > 1 else ""
                    nombre = partes[2].strip() if len(partes) > 2 else ""
                    edad = partes[3].strip() if len(partes) > 3 else ""
                    all_rows_data.append((sujeto, rut, nombre, edad))
        except Exception as e:
            print(f"Error al leer el CSV '{ruta_csv}': {e}")
            return

        if not all_rows_data:
            return

        nna_keywords = ["niño", "niña", "adolescente"]
        nna_rows = [row for row in all_rows_data if any(keyword in row[0].lower() for keyword in nna_keywords)]

        filas_a_mostrar = []
        if nna_rows:
            filas_a_mostrar = nna_rows
        else:
            solicitante_keywords = ["dte.", "solicitante"]
            filas_a_mostrar = [row for row in all_rows_data if row[0].lower() in solicitante_keywords]

        for row_data in filas_a_mostrar:
            tags_to_apply = ()
            sujeto, _, _, edad_str = row_data
            
            age = -1
            if isinstance(edad_str, str):
                match = re.search(r'\d+', edad_str)
                if match:
                    age = int(match.group(0))

            # Pintar en verde si la edad está en el rango (0-28), sin importar si es NNA o Solicitante
            if (0 <= age < 28) or (edad_str == "---"):
                tags_to_apply = ('verde_secundaria',)
            else:
                tags_to_apply = ('rojo_secundaria',)
                
            self.tabla_secundaria.insert("", "end", values=row_data, tags=tags_to_apply)

        self.ajustar_altura_tabla(self.tabla_secundaria, max_height=5)
