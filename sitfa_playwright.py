import os
import re
import time
import base64
import csv
import json
from tkinter import messagebox

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import RobotConfig, log
import utils


LOGIN_URL = "http://www.familia.pjud/SITFAWEB/jsp/Login/Login.jsp"
BANDEJA_LTE_URL = "http://www.familia.pjud/SITFAWEB/jsp/BandejaKO/BandejaJuezFirma.html#lstTramitesAuto"
POST_LOGIN_SETTLE_SECONDS = 0
BANDEJA_REINTENTOS = 3
BANDEJA_ESPERA_ENTRE_INTENTOS = 10
BANDEJA_SELECTORES = {
    "auto": ["#lstTramitesAuto", "#lstTramitesAutomaticos", "[id*='TramitesAuto']"],
    "manual": ["#lstTramites", "#lstTramitesManual", "#lstTramitesManuales", "[id*='TramitesManual']", "[id*='TramitesManuales']"],
}

# Excepción equivalente a agregar el sitio en:
# edge://settings/content/insecureContent
SITIO_CONTENIDO_NO_SEGURO = "https://familia.pjud.cl"


def configurar_contenido_no_seguro_edge(user_data_dir):
    """Permite contenido no seguro únicamente para el sitio SITFA en el perfil de Edge."""
    preferencias_dir = os.path.join(user_data_dir, "Default")
    preferencias_path = os.path.join(preferencias_dir, "Preferences")
    os.makedirs(preferencias_dir, exist_ok=True)

    preferencias = {}
    if os.path.exists(preferencias_path):
        try:
            with open(preferencias_path, "r", encoding="utf-8") as archivo:
                preferencias = json.load(archivo)
        except (OSError, json.JSONDecodeError) as error:
            log(f"No se pudieron leer las preferencias de Edge: {error}")
            return

    excepciones = (
        preferencias.setdefault("profile", {})
        .setdefault("content_settings", {})
        .setdefault("exceptions", {})
        .setdefault("insecure_content", {})
    )
    excepciones[f"{SITIO_CONTENIDO_NO_SEGURO},*"] = {
        "setting": 1,
        # Edge espera una marca de tiempo Unix en milisegundos para mostrar
        # correctamente la excepción en edge://settings.
        "last_modified": str(int(time.time() * 1000)),
    }

    try:
        with open(preferencias_path, "w", encoding="utf-8") as archivo:
            json.dump(preferencias, archivo, ensure_ascii=False)
    except OSError as error:
        log(f"No se pudieron guardar las preferencias de Edge: {error}")


class PlaywrightSetupError(Exception):
    pass


class SitfaPlaywrightSession:
    def __init__(self):
        self._pw = None
        self.context = None
        self.page = None

    def __enter__(self):
        if not self._pw:
            self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def start(self):
        if self._pw:
            return

        self._pw = sync_playwright().start()
        user_data_dir = utils.obtener_ruta_externa("playwright_user_data")
        os.makedirs(user_data_dir, exist_ok=True)
        configurar_contenido_no_seguro_edge(user_data_dir)

        launch_args = [
            "--start-maximized",
            "--disable-features=msEdgeSidebarV2",
            # La política corporativa de Edge puede ignorar las excepciones
            # guardadas en Preferences. Este permiso aplica solo a la
            # instancia de Edge controlada por el robot.
            "--allow-running-insecure-content",
        ]
        launch_kwargs = {
            "headless": not RobotConfig.navegador_visible,
            "accept_downloads": True,
            "args": launch_args if RobotConfig.navegador_visible else [],
        }
        if RobotConfig.navegador_visible:
            launch_kwargs["no_viewport"] = True
        else:
            launch_kwargs["viewport"] = {"width": 1366, "height": 768}
        if RobotConfig.ruta_descargas:
            launch_kwargs["downloads_path"] = RobotConfig.ruta_descargas

        try:
            self.context = self._pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="msedge",
                **launch_kwargs,
            )
        except PlaywrightError as edge_error:
            log(f"No se pudo abrir Microsoft Edge con Playwright: {edge_error}")
            try:
                self.context = self._pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    **launch_kwargs,
                )
            except PlaywrightError as chromium_error:
                raise PlaywrightSetupError(
                    "No se pudo abrir Edge ni Chromium. Ejecuta: python -m playwright install chromium"
                ) from chromium_error

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            self.page = None
            if self._pw:
                self._pw.stop()
                self._pw = None

    def esperar_bandeja(self, parent=None):
        if RobotConfig.usuario_sitfa and RobotConfig.password_sitfa:
            self.iniciar_sesion_y_abrir_bandeja()
        else:
            messagebox.showinfo(
                "SITFA Playwright",
                "Se abrio el navegador controlado por Playwright.\n\n"
                "Ingresa usuario y clave en el menu principal o inicia sesion manualmente. "
                "Cuando la bandeja este lista, presiona Aceptar para continuar.",
                parent=parent,
            )
        self.page = self._buscar_pagina_sitfa() or self.page
        self.activar_pestana_automatica()

    def iniciar_sesion_y_abrir_bandeja(self):
        usuario = RobotConfig.usuario_sitfa.strip()
        password = RobotConfig.password_sitfa
        if not usuario or not password:
            raise PlaywrightSetupError("Debes ingresar usuario y clave SITFA antes de iniciar el robot.")

        log("Abriendo pagina de login SITFA...")
        self.page.goto(LOGIN_URL, wait_until="load", timeout=60000)

        datos_equipo = {
            "nomequipo": os.environ.get("COMPUTERNAME", "0") or "0",
            "usuequipo": os.environ.get("USERNAME", "0") or "0",
            "ipequipo": "0",
            "MAC_equipo": "0",
        }

        log("Enviando credenciales SITFA...")
        try:
            with self.page.expect_navigation(wait_until="load", timeout=60000):
                self.page.evaluate(
                    """
                    ({ usuario, password, datosEquipo }) => {
                        const form = document.forms["InicioAplicacionForm"];
                        if (!form) throw new Error("No se encontro el formulario de login SITFA");
                        form.username.value = usuario.padEnd(50, " ");
                        form.password.value = password;
                        for (const [name, value] of Object.entries(datosEquipo)) {
                            if (form[name]) form[name].value = value;
                        }
                        form.submit();
                    }
                    """,
                    {
                        "usuario": usuario,
                        "password": password,
                        "datosEquipo": datos_equipo,
                    },
                )
        except PlaywrightTimeoutError:
            log("El login no confirmo navegacion completa dentro del tiempo esperado; se continuara verificando la bandeja.")

        self._esperar_carga_completa()
        if not self._esperar_salida_login(timeout=30000):
            raise PlaywrightSetupError("SITFA sigue mostrando el login. Revisa usuario, clave o mensajes de validacion.")

        if POST_LOGIN_SETTLE_SECONDS > 0:
            log(f"Login enviado. Esperando {POST_LOGIN_SETTLE_SECONDS}s para que SITFA termine de crear la sesion...")
            time.sleep(POST_LOGIN_SETTLE_SECONDS)
        log(f"Pagina post-login actual: {self.page.url}")

        if self._abrir_bandeja_lte_desde_interfaz():
            return
        self._abrir_bandeja_lte_con_reintentos(BANDEJA_LTE_URL)

    def _buscar_pagina_sitfa(self):
        for page in self.context.pages:
            try:
                titulo = (page.title() or "").upper()
                url = (page.url or "").upper()
                if "SITFA" in titulo or "BANDEJA" in titulo or "JUEZ" in titulo or "SITFA" in url:
                    return page
            except PlaywrightError:
                continue
        return None

    def _frames(self):
        return list(self.page.frames)

    def _frame_con_selector(self, selector):
        for frame in self._frames():
            try:
                locator = frame.locator(selector)
                if locator.count() > 0:
                    return frame
            except PlaywrightError:
                continue
        return None

    def _frame_con_texto_en_tabla(self, texto):
        for frame in self._frames():
            try:
                tablas = frame.locator("table")
                for i in range(tablas.count()):
                    tabla = tablas.nth(i)
                    if texto in tabla.inner_text(timeout=3000):
                        return frame, tabla
            except PlaywrightError:
                continue
        return None, None

    def _wait_short(self):
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(0.3)

    def _pagina_tiene_error_sistema(self):
        try:
            texto = self.page.locator("body").inner_text(timeout=3000)
            return "Problema de Sistema" in texto or "NullPointerException" in texto
        except PlaywrightError:
            return False

    def _abrir_bandeja_lte_desde_interfaz(self):
        selectores = [
            "a[href*='BandejaJuezFirma']",
            "area[href*='BandejaJuezFirma']",
            "a:has-text('Bandeja')",
            "a:has-text('Firma')",
            "button:has-text('Bandeja')",
            "button:has-text('Firma')",
            "input[value*='Bandeja']",
            "input[value*='Firma']",
        ]

        for selector in selectores:
            for frame in self._frames():
                try:
                    elementos = frame.locator(selector)
                    if elementos.count() == 0:
                        continue
                    log(f"Intentando abrir bandeja desde la interfaz con selector: {selector}")
                    elementos.first.click(timeout=10000)
                    self._esperar_carga_completa()
                    if self._esperar_bandeja_activa(timeout=30000):
                        log("Bandeja LTE cargada desde la interfaz.")
                        return True
                    if self._pagina_tiene_error_sistema():
                        log("SITFA mostro error de sistema al abrir la bandeja desde la interfaz.")
                        return False
                except PlaywrightError:
                    continue
        return False

    def _esperar_salida_login(self, timeout=30000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            try:
                login_visible = self.page.locator("form[name='InicioAplicacionForm']").count() > 0
                url_login = "Login.jsp" in (self.page.url or "")
                if not login_visible and not url_login:
                    return True
            except PlaywrightError:
                return True
            time.sleep(0.5)
        return False

    def _abrir_bandeja_lte_con_reintentos(self, url_bandeja):
        ultimo_error = None
        for intento in range(1, BANDEJA_REINTENTOS + 1):
            log(f"Abriendo bandeja LTE (intento {intento}/{BANDEJA_REINTENTOS})...")
            try:
                self.page.goto(url_bandeja, wait_until="domcontentloaded", timeout=60000)
                self._esperar_carga_completa()
                if self._pagina_tiene_error_sistema():
                    ultimo_error = "SITFA mostro Problema de Sistema / NullPointerException"
                    raise PlaywrightTimeoutError(ultimo_error)
                if self._esperar_bandeja_activa(timeout=45000):
                    log("Bandeja LTE cargada correctamente.")
                    return
                ultimo_error = "No aparecio la bandeja configurada"
            except PlaywrightError as e:
                ultimo_error = str(e)

            if intento < BANDEJA_REINTENTOS:
                log(f"La bandeja aun no esta lista ({ultimo_error}). Esperando {BANDEJA_ESPERA_ENTRE_INTENTOS}s antes de reintentar...")
                time.sleep(BANDEJA_ESPERA_ENTRE_INTENTOS)

        raise PlaywrightSetupError(
            "No se encontro la bandeja LTE despues del login. "
            f"Ultimo resultado: {ultimo_error}. Revisa permisos o intenta aumentar la espera."
        )

    def _esperar_carga_completa(self):
        try:
            self.page.wait_for_load_state("load", timeout=60000)
        except PlaywrightTimeoutError:
            pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            pass

    def _esperar_selector_en_frames(self, selector, timeout=60000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            if self._frame_con_selector(selector):
                return True
            time.sleep(0.5)
        return False

    def _selectores_bandeja(self):
        tipo = getattr(RobotConfig, "tipo_bandeja", "auto")
        principales = BANDEJA_SELECTORES.get(tipo, BANDEJA_SELECTORES["auto"])
        secundarios = BANDEJA_SELECTORES["manual" if tipo == "auto" else "auto"]
        return principales + [s for s in secundarios if s not in principales]

    def _frame_y_selector_bandeja(self):
        for selector in self._selectores_bandeja():
            frame = self._frame_con_selector(selector)
            if frame:
                return frame, selector
        return None, None

    def _esperar_bandeja_activa(self, timeout=60000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            frame, selector = self._frame_y_selector_bandeja()
            if frame:
                log(f"Bandeja detectada con selector {selector}.")
                return True
            time.sleep(0.5)
        return False

    def activar_pestana_automatica(self):
        tipo = getattr(RobotConfig, "tipo_bandeja", "auto")
        tab_selectores = ["#tabAuto"] if tipo == "auto" else [
            "#tabTabla",
            "a[href='#lstTramites']",
            "#tabManual",
            "#tabManuales",
            "a:has-text('Manuales')",
            "a:has-text('Manual')",
        ]
        if tipo != "auto":
            tab_selectores.append("#tabAuto")

        for selector in tab_selectores:
            frame = self._frame_con_selector(selector)
            if frame:
                tab = frame.locator(selector).first
                try:
                    if tab.get_attribute("aria-expanded") != "true":
                        tab.click(timeout=10000)
                        self._wait_short()
                    return True
                except PlaywrightError as e:
                    log(f"No se pudo activar pestana {tipo}: {e}")
                    return False

        return False

    def _contenedor_bandeja(self):
        frame, selector = self._frame_y_selector_bandeja()
        if not frame:
            return None, None
        return frame, frame.locator(selector).first

    @staticmethod
    def _locator_existe(locator):
        try:
            return locator.count() > 0
        except PlaywrightError:
            return False

    def extraer_lista_rits(self):
        frame, contenedor = self._contenedor_bandeja()
        if not frame or not self._locator_existe(contenedor):
            return []

        rits = []
        filas = contenedor.locator("tr")
        total_filas = filas.count()
        for i in range(total_filas):
            fila = filas.nth(i)
            try:
                textos = fila.locator("a, td").all_inner_texts()
            except PlaywrightError:
                continue
            for texto in textos:
                texto = (texto or "").strip()
                if "-" in texto and 5 < len(texto) < 25 and texto not in rits:
                    rits.append(texto)
                    break
        return rits

    def cambiar_pagina(self):
        rits_antes = self.extraer_lista_rits()
        frame, contenedor = self._contenedor_bandeja()
        if not frame or not self._locator_existe(contenedor):
            return False

        candidatos = [
            "a.next",
            "a:has-text('Siguiente')",
            "button:has-text('Siguiente')",
        ]
        boton = None
        for selector in candidatos:
            loc = contenedor.locator(selector)
            if loc.count() == 0:
                loc = frame.locator(selector)
            for i in range(loc.count()):
                candidato = loc.nth(i)
                try:
                    clase = candidato.get_attribute("class") or ""
                    aria_disabled = candidato.get_attribute("aria-disabled") or ""
                    padre_clase = candidato.evaluate("node => node.parentElement ? node.parentElement.className : ''") or ""
                    deshabilitado = (
                        "disabled" in clase.lower()
                        or "disabled" in str(padre_clase).lower()
                        or aria_disabled.lower() == "true"
                    )
                    if not deshabilitado and candidato.is_visible(timeout=300):
                        boton = candidato
                        break
                except PlaywrightError:
                    continue
            if boton:
                break

        if not boton:
            log("No hay boton Siguiente visible. Fin de lista alcanzado.")
            return False

        try:
            log("Clic en Siguiente... verificando cambio de pagina...")
            boton.click(timeout=3000)
            self._wait_short()
            rits_despues = self.extraer_lista_rits()
            if not rits_despues or rits_antes == rits_despues:
                log("PARADA: la pagina no cambio. Fin de lista alcanzado.")
                return False
            return True
        except PlaywrightError as e:
            log(f"Error al cambiar de pagina: {e}")
            return False

    def _fila_rit(self, rit):
        frame, contenedor = self._contenedor_bandeja()
        if not frame or not self._locator_existe(contenedor):
            return None
        filas = contenedor.locator("tr")
        for i in range(filas.count()):
            fila = filas.nth(i)
            try:
                if rit in fila.inner_text(timeout=3000):
                    return fila
            except PlaywrightError:
                continue
        return None

    def descargar_pdf_01(self, rit, ruta_causa):
        fila = self._fila_rit(rit)
        if not fila:
            return False
        boton = fila.locator("button[data-bind*='abrirDocPDF']").first
        if boton.count() == 0:
            return False
        return self._click_y_guardar_descarga(lambda: boton.click(timeout=10000), ruta_causa, "01.pdf")

    def clic_rit(self, rit):
        frame, contenedor = self._contenedor_bandeja()
        if not frame or not self._locator_existe(contenedor):
            return False
        enlace = contenedor.locator("a").filter(has_text=re.compile(f"^{re.escape(rit)}$")).first
        if enlace.count() == 0:
            return False
        try:
            enlace.click(timeout=10000)
            self._wait_short()
            return True
        except PlaywrightError as e:
            log(f"No se pudo abrir la causa {rit}: {e}")
            return False

    def filtrar_y_guardar_csv(self, ruta_causa, rit):
        _, tabla = self._frame_con_texto_en_tabla("Desc.Tr")
        if not tabla:
            return False

        filas_csv = []
        filas = tabla.locator("tr")
        for i in range(filas.count()):
            try:
                celdas = filas.nth(i).locator("th, td").all_inner_texts()
                filas_csv.append([c.strip() for c in celdas])
            except PlaywrightError:
                continue
        return utils.procesar_tabla_a_csv_datos(filas_csv, ruta_causa, rit)

    def descargar_pdf_02(self, ruta_causa):
        _, tabla = self._frame_con_texto_en_tabla("Desc.Tr")
        if not tabla:
            return False

        filas = tabla.locator("tr")
        for i in range(1, filas.count()):
            fila = filas.nth(i)
            try:
                texto = fila.inner_text(timeout=3000)
                texto_normalizado = self._normalizar_texto(texto)
                if "liquidacion de deuda" not in texto_normalizado:
                    continue
                log(f"Fila PDF 02 encontrada: {texto.strip()[:120]}")
                img = fila.locator("img[src*='generarpdf.gif']").first
                if img.count() == 0:
                    continue
                return self._click_y_guardar_descarga(lambda: img.click(timeout=10000), ruta_causa, "02.pdf")
            except PlaywrightError:
                continue
        return False

    @staticmethod
    def _normalizar_texto(texto):
        reemplazos = {
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
            "Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u",
        }
        texto = texto or ""
        for origen, destino in reemplazos.items():
            texto = texto.replace(origen, destino)
        return " ".join(texto.lower().split())

    def marcar_revisado_por_rit(self, rit):
        fila = self._fila_rit(rit)
        if not fila:
            return False
        checkbox = fila.locator("input[type='checkbox'][data-bind*='flgRevisado']").first
        if checkbox.count() == 0:
            return False
        try:
            if checkbox.is_checked():
                return "Ya marcado"
            checkbox.check(timeout=10000)
            self._wait_short()
            return True
        except PlaywrightError as e:
            log(f"No se pudo marcar {rit}: {e}")
            return False

    def clicar_boton_litigantes(self, rit):
        fila = self._fila_rit(rit)
        if not fila:
            return False
        boton = fila.locator("button[data-bind*='modalLitigantes']").first
        if boton.count() == 0:
            return False
        try:
            boton.click(timeout=10000)
            self._wait_short()
            return True
        except PlaywrightError as e:
            log(f"No se pudo abrir litigantes para {rit}: {e}")
            return False

    def auditar_litigantes(self, rit, ruta_causa):
        if not self.clicar_boton_litigantes(rit):
            return False

        try:
            if not self._esperar_modal_litigantes(timeout=10000):
                log("No se abrio el modal de litigantes.")
                return False

            return self.extraer_tabla_litigantes(ruta_causa)
        finally:
            if not self.cerrar_modal_litigantes():
                log("No se pudo cerrar el modal de litigantes; se intentara continuar.")

    def _esperar_modal_litigantes(self, timeout=10000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            for frame in self._frames():
                try:
                    modal = frame.locator("#modalLitigantes").first
                    if modal.count() > 0 and modal.is_visible(timeout=500):
                        return True
                except PlaywrightError:
                    continue
            time.sleep(0.25)
        return False

    def extraer_tabla_litigantes(self, ruta_causa):
        datos_para_csv = []

        for frame in self._frames():
            try:
                modal = frame.locator("#modalLitigantes").first
                if modal.count() == 0:
                    continue

                tablas = modal.locator("table")
                for t in range(tablas.count()):
                    tabla = tablas.nth(t)
                    texto_tabla = tabla.inner_text(timeout=3000)
                    if "Sujeto" not in texto_tabla or "Rut/Pasaporte" not in texto_tabla:
                        continue

                    filas = tabla.locator("tr")
                    for i in range(1, filas.count()):
                        fila = filas.nth(i)
                        celdas = [c.strip() for c in fila.locator("td").all_inner_texts()]
                        if len(celdas) < 5:
                            continue

                        if not self._fila_litigante_confirmada(fila):
                            continue

                        sujeto = celdas[1] if len(celdas) > 1 else ""
                        rut_raw = celdas[2] if len(celdas) > 2 else ""
                        rut = rut_raw.split()[0] if rut_raw else "S/R"
                        nombre = celdas[4] if len(celdas) > 4 else ""
                        edad = celdas[11] if len(celdas) > 11 else ""
                        datos_para_csv.append([sujeto, rut, nombre, edad])
                    break
            except PlaywrightError:
                continue

        nombre_carpeta = os.path.basename(ruta_causa)
        path_csv_lit = os.path.join(ruta_causa, f"{nombre_carpeta}_2.csv")
        with open(path_csv_lit, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.writer(f, delimiter=";")
            escritor.writerow(["Sujeto", "RUT", "Nombre", "Edad"])
            escritor.writerows(datos_para_csv)

        log(f"   Litigantes guardados: {len(datos_para_csv)} registros.")
        return True

    def _fila_litigante_confirmada(self, fila):
        try:
            iconos = fila.locator("td").first.locator("i")
            for i in range(iconos.count()):
                icono = iconos.nth(i)
                clase = icono.get_attribute("class") or ""
                titulo = icono.get_attribute("title") or ""
                if "fa-check" in clase or "Confirmado" in titulo:
                    return True
            return False
        except PlaywrightError:
            return False

    def cerrar_modal_litigantes(self):
        selectores = [
            "#modalLitigantes button.close",
            "#modalLitigantes [data-dismiss='modal']",
            "#modalLitigantes button:has-text('Cerrar')",
            "#modalLitigantes input[value='Cerrar']",
            "#modalLitigantes input[value='Volver']",
        ]

        for frame in self._frames():
            for selector in selectores:
                try:
                    boton = frame.locator(selector).first
                    if boton.count() == 0 or not boton.is_visible(timeout=500):
                        continue

                    log("Cerrando modal de litigantes...")
                    boton.click(timeout=5000, force=True)
                    return self._esperar_modal_litigantes_cerrado()
                except PlaywrightError:
                    continue

        for frame in self._frames():
            try:
                frame.evaluate(
                    """
                    () => {
                        const modal = document.querySelector('#modalLitigantes');
                        if (!modal) return false;
                        if (window.jQuery) {
                            window.jQuery(modal).modal('hide');
                        }
                        modal.classList.remove('in', 'show');
                        modal.style.display = 'none';
                        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                        document.body.classList.remove('modal-open');
                        document.body.style.paddingRight = '';
                        return true;
                    }
                    """
                )
                if self._esperar_modal_litigantes_cerrado(timeout=3000):
                    return True
            except PlaywrightError:
                continue

        return False

    def _esperar_modal_litigantes_cerrado(self, timeout=5000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            abierto = False
            for frame in self._frames():
                try:
                    modal = frame.locator("#modalLitigantes").first
                    if modal.count() > 0 and modal.is_visible(timeout=300):
                        abierto = True
                        break
                except PlaywrightError:
                    continue
            if not abierto:
                self._wait_short()
                return True
            time.sleep(0.25)
        return False

    def cerrar_dialogo(self):
        selectores_volver = [
            "input[name='VolverBandeja']",
            "input[value='Volver']",
            "button:has-text('Volver')",
            "a:has-text('Volver')",
        ]

        for frame in self._frames():
            for selector in selectores_volver:
                try:
                    boton = frame.locator(selector).first
                    if boton.count() == 0 or not boton.is_visible(timeout=1000):
                        continue

                    t0 = time.perf_counter()
                    log("Clic en boton Volver...")
                    boton.click(timeout=10000)
                    t_click = time.perf_counter()
                    self._esperar_salida_detalle()
                    t_fin = time.perf_counter()
                    log(f"Volver tiempos: click={t_click - t0:.2f}s, espera={t_fin - t_click:.2f}s")
                    return True
                except PlaywrightError:
                    continue

        for frame in self._frames():
            try:
                existe_close_modal = frame.evaluate("() => typeof window.parent.closeModal === 'function'")
                if existe_close_modal:
                    t0 = time.perf_counter()
                    log("Cerrando modal con window.parent.closeModal()...")
                    frame.evaluate("() => window.parent.closeModal()")
                    t_click = time.perf_counter()
                    self._esperar_salida_detalle()
                    t_fin = time.perf_counter()
                    log(f"Volver tiempos: closeModal={t_click - t0:.2f}s, espera={t_fin - t_click:.2f}s")
                    return True
            except PlaywrightError:
                continue

        try:
            log("No se encontro boton Volver; usando Escape como respaldo.")
            t0 = time.perf_counter()
            self.page.keyboard.press("Escape")
            t_click = time.perf_counter()
            self._esperar_salida_detalle()
            t_fin = time.perf_counter()
            log(f"Volver tiempos: escape={t_click - t0:.2f}s, espera={t_fin - t_click:.2f}s")
            return True
        except PlaywrightError:
            return False

    def _esperar_salida_detalle(self, timeout=2000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            detalle_visible = False
            for frame in self._frames():
                try:
                    boton = frame.locator("input[name='VolverBandeja'], input[value='Volver']").first
                    if boton.count() > 0 and boton.is_visible(timeout=200):
                        detalle_visible = True
                        break
                except PlaywrightError:
                    continue

            if not detalle_visible:
                time.sleep(0.2)
                return True
            time.sleep(0.2)

        log("Volver: el detalle siguio visible tras 2s; se continuara igualmente.")
        return False

    def _click_y_guardar_descarga(self, accion_click, ruta_destino, nombre_archivo):
        paginas_antes = set(self.context.pages)
        url_antes = self.page.url
        os.makedirs(ruta_destino, exist_ok=True)
        ruta_pdf = os.path.join(ruta_destino, nombre_archivo)
        respuestas_pdf = []

        def capturar_respuesta(response):
            if self._url_parece_pdf(response.url):
                respuestas_pdf.append(response)

        try:
            self._instalar_captura_url_pdf()
            self.context.on("response", capturar_respuesta)
            accion_click()
            url_capturada = self._esperar_url_pdf_capturada()
            if url_capturada:
                log(f"URL PDF capturada: {url_capturada}")
                return self._guardar_pdf_por_request(url_capturada, ruta_pdf, nombre_archivo)

            respuesta = self._esperar_respuesta_pdf(respuestas_pdf)
            if respuesta:
                return self._guardar_pdf_desde_respuesta(respuesta, ruta_pdf, nombre_archivo)

            log(f"No se capturo respuesta DownloadFile.do; buscando PDF abierto en navegador para {nombre_archivo}...")
            return self._guardar_pdf_abierto(paginas_antes, url_antes, ruta_pdf, nombre_archivo)
        except Exception as e:
            log(f"Error guardando {nombre_archivo}: {e}")
            return False
        finally:
            try:
                self.context.remove_listener("response", capturar_respuesta)
            except Exception:
                pass

    def _instalar_captura_url_pdf(self):
        script = """
        () => {
            if (window.__sitfaPdfCaptureInstalled) {
                window.__sitfaPdfUrls = [];
                return;
            }

            window.__sitfaPdfCaptureInstalled = true;
            window.__sitfaPdfUrls = [];
            const originalOpen = window.open;
            window.__sitfaOriginalOpen = originalOpen;

            window.open = function(url, target, features) {
                try {
                    if (url) {
                        window.__sitfaPdfUrls.push(new URL(String(url), window.location.href).href);
                    }
                } catch (e) {}

                return {
                    closed: false,
                    focus: function() {},
                    close: function() { this.closed = true; }
                };
            };

            const originalSubmit = HTMLFormElement.prototype.submit;
            HTMLFormElement.prototype.submit = function() {
                try {
                    const action = this.action || "";
                    if (action.toLowerCase().includes("downloadfile.do")) {
                        const data = new URLSearchParams(new FormData(this)).toString();
                        const finalUrl = new URL(action, window.location.href);
                        if (data) {
                            const extra = new URLSearchParams(data);
                            extra.forEach((value, key) => finalUrl.searchParams.set(key, value));
                        }
                        window.__sitfaPdfUrls.push(finalUrl.href);
                        return;
                    }
                } catch (e) {}
                return originalSubmit.apply(this, arguments);
            };
        }
        """

        for frame in self._frames():
            try:
                frame.evaluate(script)
            except PlaywrightError:
                continue

    def _esperar_url_pdf_capturada(self, timeout=10000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            for frame in self._frames():
                try:
                    urls = frame.evaluate("() => window.__sitfaPdfUrls || []")
                    for url in urls:
                        if self._url_parece_pdf(url):
                            return url
                except PlaywrightError:
                    continue
            time.sleep(0.25)
        return None

    @staticmethod
    def _esperar_respuesta_pdf(respuestas_pdf, timeout=20000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            if respuestas_pdf:
                return respuestas_pdf[0]
            time.sleep(0.25)
        return None

    def _guardar_pdf_desde_respuesta(self, response, ruta_pdf, nombre_archivo):
        try:
            log(f"Respuesta PDF detectada: {response.url}")
            if not response.ok:
                log(f"No se pudo descargar {nombre_archivo}. HTTP {response.status}")
                return False

            contenido = response.body()
            if not contenido:
                log(f"La respuesta PDF para {nombre_archivo} no tenia contenido.")
                return False

            if os.path.exists(ruta_pdf):
                os.remove(ruta_pdf)
            with open(ruta_pdf, "wb") as f:
                f.write(contenido)
            utils.convertir_pdf_a_txt(ruta_pdf, nombre_archivo.replace(".pdf", ".txt"))
            return True
        except Exception as e:
            log(f"Error guardando respuesta PDF {nombre_archivo}: {e}")
            return False

    def _guardar_pdf_abierto(self, paginas_antes, url_antes, ruta_pdf, nombre_archivo):
        pagina_pdf = self._esperar_pagina_pdf(paginas_antes, url_antes)
        if not pagina_pdf:
            log(f"No se encontro pestana o URL PDF para {nombre_archivo}.")
            return False

        url_pdf = pagina_pdf.url
        log(f"PDF detectado en navegador: {url_pdf}")

        ok = False
        if url_pdf.startswith("blob:"):
            ok = self._guardar_blob_pdf(pagina_pdf, ruta_pdf, nombre_archivo)
        elif url_pdf and url_pdf != "about:blank":
            ok = self._guardar_pdf_por_request(url_pdf, ruta_pdf, nombre_archivo)

        if pagina_pdf is not self.page:
            try:
                pagina_pdf.close()
            except PlaywrightError:
                pass

        return ok

    def _esperar_pagina_pdf(self, paginas_antes, url_antes, timeout=15000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            for pagina in self.context.pages:
                try:
                    if pagina not in paginas_antes:
                        self._esperar_url_pdf_en_pagina(pagina, timeout=5000)
                        if self._pagina_parece_pdf(pagina):
                            return pagina
                    if pagina is self.page and pagina.url != url_antes and self._url_parece_pdf(pagina.url):
                        return pagina
                except PlaywrightError:
                    continue
            time.sleep(0.5)
        return None

    def _esperar_url_pdf_en_pagina(self, pagina, timeout=5000):
        limite = time.time() + (timeout / 1000)
        while time.time() < limite:
            try:
                if self._pagina_parece_pdf(pagina):
                    return True
                pagina.wait_for_load_state("domcontentloaded", timeout=500)
            except PlaywrightError:
                pass
            time.sleep(0.25)
        return False

    def _pagina_parece_pdf(self, pagina):
        try:
            if self._url_parece_pdf(pagina.url):
                return True
            titulo = (pagina.title() or "").lower()
            return "downloadfile.do" in titulo or "downloadfile" in titulo
        except PlaywrightError:
            return False

    @staticmethod
    def _url_parece_pdf(url):
        url = (url or "").lower()
        return (
            ".pdf" in url
            or "pdf" in url
            or "downloadfile.do" in url
            or "downloadfile" in url
            or url.startswith("blob:")
        )

    def _guardar_pdf_por_request(self, url_pdf, ruta_pdf, nombre_archivo):
        try:
            response = self.context.request.get(url_pdf, timeout=45000)
            if not response.ok:
                log(f"No se pudo descargar {nombre_archivo} desde URL PDF. HTTP {response.status}")
                return False
            if os.path.exists(ruta_pdf):
                os.remove(ruta_pdf)
            with open(ruta_pdf, "wb") as f:
                f.write(response.body())
            utils.convertir_pdf_a_txt(ruta_pdf, nombre_archivo.replace(".pdf", ".txt"))
            return True
        except Exception as e:
            log(f"Error descargando PDF abierto {nombre_archivo}: {e}")
            return False

    def _guardar_blob_pdf(self, pagina_pdf, ruta_pdf, nombre_archivo):
        try:
            contenido_b64 = pagina_pdf.evaluate(
                """
                async () => {
                    const response = await fetch(window.location.href);
                    const buffer = await response.arrayBuffer();
                    let binary = "";
                    const bytes = new Uint8Array(buffer);
                    const chunkSize = 0x8000;
                    for (let i = 0; i < bytes.length; i += chunkSize) {
                        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
                    }
                    return btoa(binary);
                }
                """
            )
            if os.path.exists(ruta_pdf):
                os.remove(ruta_pdf)
            with open(ruta_pdf, "wb") as f:
                f.write(base64.b64decode(contenido_b64))
            utils.convertir_pdf_a_txt(ruta_pdf, nombre_archivo.replace(".pdf", ".txt"))
            return True
        except Exception as e:
            log(f"Error guardando PDF blob {nombre_archivo}: {e}")
            return False


def abrir_sesion_sitfa(parent=None):
    sesion = SitfaPlaywrightSession()
    sesion.start()
    sesion.esperar_bandeja(parent=parent)
    return sesion
