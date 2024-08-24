from flask import Flask, request, jsonify
import requests
import xmltodict
from requests_toolbelt.adapters.ssl import SSLAdapter
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import serialization
import tempfile
import os
import sys

app = Flask(__name__)

############# CAMBIA DIRECTORIO POR EL TUYO
CERT_PATH = 'cert.pfx' #CAMBIA DIRECTORIO
CERT_PASSWORD = 'sape'

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

    return (cert_file.name, key_file.name)

def make_soap_request(service_name, dni, sexo):
    url = SOAP_SERVICES[service_name]
    body = SOAP_BODIES[service_name].format(dni=dni, sexo=sexo)
    
    cert_path, key_path = get_cert(CERT_PATH, CERT_PASSWORD)
    
    try:
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
        os.remove(cert_path)
        os.remove(key_path)

    return response.text

def fetch_data(dni, sexo):
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
    dni = request.args.get('dni')
    sexo = request.args.get('sexo')

    if not dni or not sexo:
        return jsonify({'error': 'Faltan parámetros dni o sexo'}), 400

    try:
        data = fetch_data(dni, sexo)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

print(f"Python version: {sys.version}")
