import json
import hashlib
import sys
import os

SECRET_KEY = "perfectline_super_secreto_para_firmar_licencias_2026"

def generar_licencia(machine_id, nombre, output_path="license.dat"):
    mensaje = f"{machine_id}|{nombre}|{SECRET_KEY}"
    firma = hashlib.sha256(mensaje.encode()).hexdigest()
    
    licencia = {
        "machine_id": machine_id,
        "nombre": nombre,
        "signature": firma
    }
    
    with open(output_path, "w") as f:
        json.dump(licencia, f, indent=4)
        
    print(f"Licencia generada exitosamente en: {output_path}")
    print(f"   Gimnasio: {nombre}")
    print(f"   Machine ID: {machine_id}")

if __name__ == "__main__":
    print("--- Generador de Licencias Perfect Line ---")
    output_path = "license.dat"
    if len(sys.argv) >= 3:
        machine_id = sys.argv[1]
        nombre = sys.argv[2]
        if len(sys.argv) >= 4:
            output_path = sys.argv[3]
    else:
        nombre = input("Introduce el Nombre del gimnasio (ej. Gym Power): ")
        machine_id = input("Introduce el Machine ID de la computadora: ")
    
    if not machine_id or not nombre:
        print("Datos incompletos.")
        sys.exit(1)
        
    generar_licencia(machine_id, nombre, output_path)
