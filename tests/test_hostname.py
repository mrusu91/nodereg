from unittest import mock

from nodereg.modules import Hostname


def get_node():
    return {
        'metadata': {
            'local-ipv4': '10.0.0.123',
        },
        'tags': {
            'Role': 'master',
        },
    }


def get_config():
    return {
        'asg_name': False,
        'tag_name': 'Role',
        'ip_address': {
            'octets': 2,
            'glue': '-',
        },
        'glue': '',
    }


@mock.patch('subprocess.run')
def test_hostname(subprocess_run):
    node = get_node()
    config = get_config()
    expected_hostname = 'master0-123'
    hostname_module = Hostname(node, config, False)
    assert hostname_module.run() == expected_hostname
    subprocess_run.assert_called_with(
        [
            'hostnamectl',
            'set-hostname',
            expected_hostname,
        ],
        check=True,
        stdout=-1,
    )


@mock.patch('subprocess.run')
def test_chroot(subprocess_run):
    node = get_node()
    config = get_config()
    expected_hostname = 'master0-123'
    hostname_module = Hostname(node, config, '/media/root')
    assert hostname_module.run() == expected_hostname
    subprocess_run.assert_called_with(
        [
            'chroot',
            '/media/root',
            'hostnamectl',
            'set-hostname',
            expected_hostname,
        ],
        check=True,
        stdout=-1,
    )
