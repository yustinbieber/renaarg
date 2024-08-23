from flask import Flask, request, jsonify
import requests
import xmltodict
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import serialization
import tempfile
import os
import base64

app = Flask(__name__)

# Lee la variable de entorno para el certificado y la contraseña
CERT_PFX_BASE64 = os.getenv('CERT_PFX_BASE64')
CERT_PASSWORD = os.getenv('CERT_PASSWORD', 'sape')

def decode_cert(cert_base64):
    """Decodifica el archivo PFX desde Base64 y guarda el contenido en un archivo temporal."""
    cert_data = base64.b64decode(cert_base64)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pfx') as cert_file:
        cert_file.write(cert_data)
        cert_file.close()  # Asegúrate de cerrar el archivo para que pueda ser leído más tarde
        return cert_file.name


SOAP_SERVICES = {
    'padres': 'https://renaperdatosc.idear.gov.ar:8446/WSpadres.php',
    'hijos': 'https://renaperdatosc.idear.gov.ar:8446/WShijos.php',
    'fiscal': 'https://renaperdatosc.idear.gov.ar:8446/DATOSCMPFISCAL.php'
}

SOAP_BODIES = {
    'padres': '''<x:Envelope
        xmlns:x="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:padreswsdl">
        <x:Header/>
        <x:Body>
            <urn:obtenerDatosPadres>
                <urn:DatosEntrada>
                    <dni>{dni}</dni>
                    <sexo>{sexo}</sexo>
                </urn:DatosEntrada>
            </urn:obtenerDatosPadres>
        </x:Body>
    </x:Envelope>''',
    'hijos': '''<x:Envelope
        xmlns:x="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:hijoswsdl">
        <x:Header/>
        <x:Body>
            <urn:obtenerDatosHijos>
                <urn:DatosEntrada>
                    <dni>{dni}</dni>
                    <sexo>{sexo}</sexo>
                </urn:DatosEntrada>
            </urn:obtenerDatosHijos>
        </x:Body>
    </x:Envelope>''',
    'fiscal': '''<x:Envelope
        xmlns:x="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn1="urn:miniteriorwsdl"
        xmlns:urn="urn:mininteriorwsdl">
        <x:Header/>
        <x:Body>
            <urn1:obtenerUltimoEjemplar>
                <urn1:DatosEntrada>
                    <urn:dni>{dni}</urn:dni>
                    <urn:sexo>{sexo}</urn:sexo>
                </urn1:DatosEntrada>
            </urn1:obtenerUltimoEjemplar>
        </x:Body>
    </x:Envelope>'''
}

def get_cert(cert_path, password):
    """Convierte el archivo PFX a PEM y guarda las claves en archivos temporales."""
    if not os.path.exists(cert_path):
        raise FileNotFoundError(f"El archivo {cert_path} no existe")
    
    with open(cert_path, 'rb') as f:
        p12_data = f.read()
    
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        p12_data,
        password.encode(),
        backend=None
    )
    
    cert_pem = certificate.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
    key_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')

    cert_file.write(cert_pem)
    cert_file.close()

    key_file.write(key_pem)
    key_file.close()

    # Verificar existencia de los archivos creados
    if not os.path.exists(cert_file.name):
        raise FileNotFoundError(f"El archivo {cert_file.name} no se creó correctamente")
    if not os.path.exists(key_file.name):
        raise FileNotFoundError(f"El archivo {key_file.name} no se creó correctamente")

    return (cert_file.name, key_file.name)

def make_soap_request(service_name, dni, sexo):
    """Realiza una solicitud SOAP usando el certificado y clave."""
    url = SOAP_SERVICES[service_name]
    body = SOAP_BODIES[service_name].format(dni=dni, sexo=sexo)
    
    # Decodifica el certificado desde Base64 y obtiene el archivo temporal
    cert_path = decode_cert(CERT_PFX_BASE64)
    
    try:
        cert_path, key_path = get_cert(cert_path, CERT_PASSWORD)
        
        response = requests.post(
            url,
            data=body,
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': f"urn:{service_name}wsdl#obtenerDatos{service_name.capitalize()}"
            },
            cert=(cert_path, key_path),
            verify=False  # Desactiva la verificación del certificado
        )
    finally:
        os.remove(cert_path)  # Elimina el archivo PFX temporal
        os.remove(cert_path)  # Elimina el archivo PEM temporal del certificado
        os.remove(key_path)  # Elimina el archivo PEM temporal de la clave

    return response.text

def fetch_data(dni, sexo):
    """Obtiene datos de varios servicios SOAP."""
    results = {}
    for service in ['padres', 'hijos']:
        xml_response = make_soap_request(service, dni, sexo)
        # Convierte el XML a JSON
        results[service] = xmltodict.parse(xml_response)
    # Incluye la nueva consulta fiscal
    xml_response_fiscal = make_soap_request('fiscal', dni, sexo)
    results['fiscal'] = xmltodict.parse(xml_response_fiscal)
    return results

@app.route('/api/fetch_data', methods=['GET'])
def api_fetch_data():
    """Maneja la solicitud GET para obtener datos."""
    dni = request.args.get('dni')
    sexo = request.args.get('sexo')

    if not dni or not sexo:
        return jsonify({'error': 'Faltan parámetros dni o sexo'}), 400

    try:
        data = fetch_data(dni, sexo)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
