import pytest
from boto import route53
from moto import mock_route53

from nodereg.modules import HostedZone


def get_node():
    return {
        'metadata': {
            'local-ipv4': '10.0.0.123',
        },
        'region': 'eu-west-1',
    }


def get_config():
    return {
        'name': 'k8s.com.',
        'allow_cleaning': False,
    }


@mock_route53
def test_missing_zone():
    node = get_node()
    config = get_config()
    hosted_zone_module = HostedZone(node, config)
    with pytest.raises(Exception) as e_info:
        hosted_zone_module.run(hostname)


@mock_route53
def test_new_record():
    node = get_node()
    config = get_config()

    r53 = route53.connect_to_region(node['region'])
    zone = r53.create_zone(
        config['name'],
        private_zone=True,
        vpc_id='1',
        vpc_region=node['region'],
    )

    hosted_zone_module = HostedZone(node, config)
    hostname = 'master0-123'
    fqdn = hosted_zone_module.run(hostname)
    assert fqdn == '.'.join([hostname, zone.name.lower()])
    record = zone.get_a(fqdn)
    assert record.resource_records == [node['metadata']['local-ipv4']]


@mock_route53
def test_stale_record():
    node = get_node()
    config = get_config()

    r53 = route53.connect_to_region(node['region'])
    zone = r53.create_zone(
        config['name'],
        private_zone=True,
        vpc_id='1',
        vpc_region=node['region'],
    )
    stale_fqdn = '.'.join(['worker', zone.name.lower()])
    zone.add_a(stale_fqdn, node['metadata']['local-ipv4'], ttl=60)

    hosted_zone_module = HostedZone(node, config)
    hostname = 'master0-123'
    fqdn = hosted_zone_module.run(hostname)
    assert fqdn == '.'.join([hostname, zone.name.lower()])
    assert zone.get_a(stale_fqdn) == None
    record = zone.get_a(fqdn)
    assert record.resource_records == [node['metadata']['local-ipv4']]


@mock_route53
def test_present_record():
    node = get_node()
    config = get_config()

    r53 = route53.connect_to_region(node['region'])
    zone = r53.create_zone(
        config['name'],
        private_zone=True,
        vpc_id='1',
        vpc_region=node['region'],
    )
    hostname = 'master0-123'
    expected_fqdn = '.'.join([hostname, zone.name.lower()])
    zone.add_a(expected_fqdn, node['metadata']['local-ipv4'], ttl=60)
    expected_record = zone.get_a(expected_fqdn)

    hosted_zone_module = HostedZone(node, config)
    fqdn = hosted_zone_module.run(hostname)
    record = zone.get_a(fqdn)
    assert fqdn == expected_fqdn
    assert record.resource_records == expected_record.resource_records
