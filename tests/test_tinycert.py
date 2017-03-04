from os import path
from unittest import mock

from nodereg.modules import TinyCert


def get_node():
    return {
        'metadata': {
            'local-ipv4': '10.0.0.123',
        },
    }


def get_config(node_certificate=False, certificates=[]):
    return {
        'api_key': 'test_key',
        'email': 'test@test.com',
        'passphrase': 'test_passphrase',
        'ca_id': 1000,
        'ca_path': '/tmp/ca',
        'certificates_path': '/tmp/certs/',
        'node_certificate': node_certificate,
        'certificates': certificates,
    }


class CertDB:

    def __init__(self):
        self.certs = []

    def ca_details(self, ca_id):
        return {
            'id': ca_id,
            'C': 'US',
            'ST': 'Washington',
            'L': 'Seattle',
            'O': 'Acme, Inc.',
            'OU': 'Secure Digital Certificate Signing',
            'CN': 'acme.com',
            'E': 'admin@acme.com',
            'hash_alg': 'SHA256',
        }

    def ca_get(self, ca_id):
        return {
            'pem': 'CACERTCONTENT',
        }

    def cert_list(self, ca_id):
        return [summary for summary, details in self.certs]

    def cert_details(self, cert_id):
        for summary, details in self.certs:
            if summary['id'] == cert_id:
                return details
        return None

    def cert_create(self, ca_id, csr):
        safe_csr = csr.copy()
        cert_id = 1001
        summary = {
            'id': cert_id,
            'name': safe_csr['CN'],
            'status': 'good',
            'expires': 987654321,
        }
        details = {
            'id': cert_id,
            'status': 'good',
            'Alt': safe_csr.pop('SANs'),
            'hash_alg': 'SHA256',
        }
        details.update(safe_csr)
        self.certs.append((summary, details))
        return {'cert_id': cert_id}

    def cert_get(self, cert_id, what):
        return {
            'pem': what,
        }


@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('nodereg.modules.tinycert.makedirs')
@mock.patch('nodereg.modules.tinycert.path')
@mock.patch('subprocess.run')
@mock.patch('nodereg.modules.tinycert.Session')
def test_missing_ca(
    tinycert_session,
    subprocess_run,
    os_path,
    os_makedirs,
    builtins_open,
):
    node = get_node()
    config = get_config()
    cert_db = CertDB()
    ca_details = cert_db.ca_details(config['ca_id'])
    ca_file = path.join(
        config['ca_path'],
        ca_details['CN'].lower() + '.pem',
    )

    tinycert_session().ca.details.side_effect = cert_db.ca_details
    tinycert_session().ca.get.side_effect = cert_db.ca_get
    os_path.join.return_value = ca_file
    os_path.dirname.return_value = config['ca_path']
    os_path.isfile.return_value = False

    tinycert_module = TinyCert(node, config, False)
    tinycert_module.run('')

    os_path.join.assert_called_once_with(
        config['ca_path'],
        ca_details['CN'].lower() + '.pem',
    )
    os_path.isfile.assert_called_once_with(ca_file)
    os_path.dirname.assert_called_once_with(ca_file)
    os_makedirs.assert_called_with(config['ca_path'], exist_ok=True)
    builtins_open.assert_called_once_with(ca_file, 'w')
    builtins_open().write.assert_called_once_with(cert_db.ca_get(config['ca_id'])['pem'])
    subprocess_run.assert_called_once_with(
        ['update-ca-certificates'],
        check=True,
        stdout=-1,
    )


@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('nodereg.modules.tinycert.path')
@mock.patch('subprocess.run')
@mock.patch('nodereg.modules.tinycert.Session')
def test_present_ca(
    tinycert_session,
    subprocess_run,
    os_path,
    builtins_open,
):
    node = get_node()
    config = get_config()
    cert_db = CertDB()
    ca_details = cert_db.ca_details(config['ca_id'])
    ca_file = path.join(
        config['ca_path'],
        ca_details['CN'].lower() + '.pem',
    )

    tinycert_session().ca.details.side_effect = cert_db.ca_details
    tinycert_session().ca.get.side_effect = cert_db.ca_get
    os_path.join.return_value = ca_file
    os_path.isfile.return_value = True

    tinycert_module = TinyCert(node, config, False)
    tinycert_module.run('')

    os_path.join.assert_called_once_with(
        config['ca_path'],
        ca_details['CN'].lower() + '.pem',
    )
    os_path.isfile.assert_called_once_with(ca_file)
    builtins_open.assert_not_called()
    subprocess_run.assert_not_called()


@mock.patch('nodereg.modules.tinycert.Session')
@mock.patch('nodereg.modules.tinycert.TinyCert._ensure_ca')
@mock.patch('nodereg.modules.tinycert.TinyCert._ensure_certificate')
def test_generate_node_certificate(
    ensure_certificate,
    ensure_ca,
    tinycert_session,
):
    node = get_node()
    config = get_config(node_certificate=True)
    cert_db = CertDB()
    ca_details = cert_db.ca_details(config['ca_id'])

    ensure_ca.return_value = ca_details
    tinycert_session().cert.list.side_effect = cert_db.cert_list
    tinycert_session().cert.details.side_effect = cert_db.cert_details
    tinycert_session().cert.create.side_effect = cert_db.cert_create

    fqdn = 'abc.acme.com'
    tinycert_module = TinyCert(node, config, False)
    tinycert_module.run(fqdn)

    tinycert_session().cert.list.assert_called_once_with(ca_details['id'])
    csr = {
        'CN': fqdn,
        'SANs': [
            {'DNS': fqdn},
            {'DNS': fqdn.split('.')[0]},
            {'IP': node['metadata']['local-ipv4']},
        ],
    }
    for field in ['C', 'L', 'O', 'OU', 'ST']:
        csr[field] = ca_details[field]
    tinycert_session().cert.create.assert_called_once_with(
        ca_details['id'],
        csr,
    )
    tinycert_session().cert.details.assert_called_once_with(1001)
    assert ensure_certificate.called


@mock.patch('nodereg.modules.tinycert.Session')
@mock.patch('nodereg.modules.tinycert.TinyCert._ensure_ca')
@mock.patch('nodereg.modules.tinycert.TinyCert._ensure_certificate')
@mock.patch('nodereg.modules.tinycert.TinyCert._generate_certificate')
def test_find_node_certificate(
    generate_certificate,
    ensure_certificate,
    ensure_ca,
    tinycert_session,
):
    node = get_node()
    config = get_config(node_certificate=True)
    cert_db = CertDB()
    ca_details = cert_db.ca_details(config['ca_id'])

    fqdn = 'abc.acme.com'
    cert_summary = {
        'id': 1001,
        'name': fqdn,
        'status': 'good',
        'expires': 987654321,
    }
    cert_details = {
        'id': 1001,
        'CN': fqdn,
        'status': 'good',
        'Alt': [{'DNS': fqdn}],
        'hash_alg': 'SHA256',
    }
    for field in ['C', 'L', 'O', 'OU', 'ST']:
        cert_details[field] = ca_details[field]

    ensure_ca.return_value = ca_details
    tinycert_session().cert.list.return_value = [cert_summary]
    tinycert_session().cert.details.return_value = cert_details

    tinycert_module = TinyCert(node, config, False)
    tinycert_module.run(fqdn)

    tinycert_session().cert.list.assert_called_once_with(ca_details['id'])
    tinycert_session().cert.details.assert_called_once_with(1001)
    generate_certificate.assert_not_called()
    assert ensure_certificate.called


@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('nodereg.modules.tinycert.makedirs')
@mock.patch('nodereg.modules.tinycert.path.isfile')
@mock.patch('nodereg.modules.tinycert.Session')
@mock.patch('nodereg.modules.tinycert.TinyCert._ensure_ca')
def test_ensure_certificates(
    ensure_ca,
    tinycert_session,
    os_path_isfile,
    os_makedirs,
    builtins_open,
):
    node = get_node()
    config = get_config(certificates=[1001])
    cert_db = CertDB()
    ca_details = cert_db.ca_details(config['ca_id'])
    cert_details = {
        'id': 1001,
        'CN': 'abc.acme.com',
        'status': 'good',
        'Alt': [{'DNS': 'abc.acme.com'}],
        'hash_alg': 'SHA256',
    }
    for field in ['C', 'L', 'O', 'OU', 'ST']:
        cert_details[field] = ca_details[field]
    cert_file = path.join(
        config['certificates_path'],
        cert_details['CN'].lower() + '.pem',
    )
    key_file = path.join(
        config['certificates_path'],
        cert_details['CN'].lower() + '-key.pem',
    )

    tinycert_session().cert.details.return_value = cert_details
    tinycert_session().cert.get.side_effect = cert_db.cert_get
    os_path_isfile.return_value = False

    tinycert_module = TinyCert(node, config, False)
    tinycert_module.run('')

    os_path_isfile.assert_any_call(cert_file)
    builtins_open.assert_any_call(cert_file, 'w')
    builtins_open().write.assert_any_call(
        cert_db.cert_get(cert_details['id'], 'cert')['pem'],
    )

    os_path_isfile.assert_any_call(key_file)
    builtins_open.assert_any_call(key_file, 'w')
    builtins_open().write.assert_any_call(
        cert_db.cert_get(cert_details['id'], 'key.dec')['pem'],
    )
