import socket
from time import sleep
from django.core.management.base import BaseCommand
from zeroconf import ServiceInfo, Zeroconf

def get_local_ip():
    """Obtiene la IP local de la interfaz de red conectada."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Intenta conectar con un destino no ruteable para forzar al SO a elegir la interfaz correcta
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class Command(BaseCommand):
    help = 'Inicia el servidor mDNS/Zeroconf para transmitir perfectline.local en la red local.'

    def handle(self, *args, **options):
        ip_address = get_local_ip()
        
        if ip_address == '127.0.0.1':
            self.stdout.write(self.style.ERROR('No se pudo detectar una conexión a la red local. Asegúrate de estar conectado al WiFi.'))
            return

        service_type = "_http._tcp.local."
        service_name = "PerfectLine._http._tcp.local."
        server_hostname = "perfectline.local."
        port = 8000
        
        # Se convierte la IP a formato de bytes como lo requiere zeroconf
        info = ServiceInfo(
            service_type,
            service_name,
            addresses=[socket.inet_aton(ip_address)],
            port=port,
            server=server_hostname,
        )

        self.stdout.write(self.style.WARNING("Iniciando servicio mDNS (Zeroconf)..."))
        self.stdout.write(self.style.SUCCESS(f"Transmitiendo host: {server_hostname} -> {ip_address}:{port}"))
        
        zeroconf = Zeroconf()
        try:
            zeroconf.register_service(info)
            self.stdout.write(self.style.SUCCESS("Servicio registrado exitosamente. Presiona Ctrl+C para detener."))
            
            # Mantiene el proceso vivo mientras transmite por el puerto 5353 en segundo plano
            while True:
                sleep(1)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nDeteniendo transmisor mDNS..."))
        finally:
            # Buena práctica: darse de baja de la red local al cerrar
            zeroconf.unregister_service(info)
            zeroconf.close()
            self.stdout.write(self.style.SUCCESS("Servicio mDNS cerrado de forma segura."))
