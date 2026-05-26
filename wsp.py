from config import log
import requests

def enviar_notificacion(mensaje, topic="robot_sitfa_alertas_99"):
    """
    Envía una notificación push al celular a través de ntfy.sh.
    Para recibirla, descarga la app 'ntfy' (Android/iOS) y suscríbete al tema especificado en 'topic'.
    """
    if not topic or topic.strip() == "":
        log("No se ha configurado un canal secreto. Omitiendo notificación.")
        return

    url = f"https://ntfy.sh/{topic}"
    try:
        # Codificamos el mensaje en utf-8 para soportar tildes, ñ y emojis
        respuesta = requests.post(url, data=mensaje.encode('utf-8'))
        if respuesta.status_code == 200:
            log("Notificación enviada con éxito.")
        else:
            log(f"Error al enviar la notificación. Código: {respuesta.status_code}")
    except Exception as e:
        log(f"Error de conexión: {e}")

if __name__ == "__main__":
    # Mensaje de prueba
    mensaje_prueba = "✅ ¡Hola! El Robot SITFA ha terminado de procesar los datos con éxito."
    
    # Recomiendo cambiar 'robot_sitfa_alertas_99' por un código secreto tuyo (letras y números sin espacios)
    tema_secreto = "robot_sitfa_alertas_99"
    
    log(f"Enviando notificación al tema: {tema_secreto}...")
    enviar_notificacion(mensaje_prueba, topic=tema_secreto)
