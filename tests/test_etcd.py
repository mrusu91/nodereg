import copy
from unittest import mock

import requests
from boto import ec2
from boto.ec2 import autoscale
from moto import mock_autoscaling, mock_ec2

from nodereg.modules import Etcd


def get_node(instance_id='i-123', ip_address='10.0.0.123'):
    return {
        'metadata': {
            'local-ipv4': ip_address,
            'instance-id': instance_id,
        },
        'region': 'eu-west-1',
    }


def get_config():
    return {
        'client_schema': 'http',
        'client_port': 2379,
        'peer_schema': 'http',
        'peer_port': 2380,
        'drop_in_file': 'drop-in.conf',
    }


class MockResponse:

    def __init__(self, config, ec2_instances):
        self.etcd_instances = [
            {
                'id': instance.id,
                'name': instance.id,
                'clientURLs': [
                    '%s://%s:%d' % (
                        config['client_schema'],
                        instance.private_ip_address,
                        config['client_port'],
                    ),
                ],
                'peerURLs': [
                    '%s://%s:%d' % (
                        config['peer_schema'],
                        instance.private_ip_address,
                        config['peer_port'],
                    ),
                ],
            }
            for instance in ec2_instances
        ]

    def get(self, url, *args, **kwargs):
        mocked_response = mock.MagicMock()
        if url.endswith('health'):
            mocked_response.json.return_value = {'health': 'true'}
        elif url.endswith('members'):
            mocked_response.json.return_value = {'members': self.etcd_instances}
        return mocked_response

    def post_or_delete(self, *args, **kwargs):
        mocked_response = mock.MagicMock()
        return mocked_response


def get_asg_instance_ids(region):
    asg_conn = autoscale.connect_to_region(region)
    launch_config = autoscale.LaunchConfiguration(name='test_lc')
    asg_conn.create_launch_configuration(launch_config)
    asg = autoscale.AutoScalingGroup(
        name='test_asg',
        min_size=3,
        max_size=3,
        launch_config=launch_config,
    )
    asg_conn.create_auto_scaling_group(asg)
    asg = asg_conn.get_all_groups([asg.name])[0]
    instance_ids = [instance.instance_id for instance in asg.instances]
    return instance_ids


def get_instances(region, instance_ids):
    ec2_conn = ec2.connect_to_region(region)
    instances = [
        instance
        for r in ec2_conn.get_all_instances(instance_ids=instance_ids)
        for instance in r.instances
    ]
    return instances


def build_initial_cluster(config, instances):
    peers = []
    for instance in instances:
        peer_url = '%s://%s:%s' % (
            config['peer_schema'],
            instance.private_ip_address,
            config['peer_port'],
        )
        peers.append('%s=%s' % (instance.id, peer_url))
    return ','.join(peers)


def get_file_content(initial_cluster, state):
    file_content = '\n'.join([
        '[Service]',
        'Environment=ETCD_INITIAL_CLUSTER=%s' % initial_cluster,
        'Environment=ETCD_INITIAL_CLUSTER_STATE=%s' % state,
    ])
    return file_content


@mock_ec2
@mock_autoscaling
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('subprocess.run')
@mock.patch('requests.get')
def test_new_cluster(
    requests_get,
    subprocess_run,
    builtins_open,
):
    node = get_node()
    instance_ids = get_asg_instance_ids(node['region'])
    instances = get_instances(node['region'], instance_ids)
    myself = instances[0]
    node = get_node(
        instance_id=myself.id,
        ip_address=myself.private_ip_address,
    )
    config = get_config()
    initial_cluster = build_initial_cluster(config, instances)

    requests_get.side_effect = requests.exceptions.ConnectTimeout()

    etcd_module = Etcd(node, config, False)
    etcd_module.run()

    builtins_open.assert_called_once_with(config['drop_in_file'], 'w')
    builtins_open().write.assert_called_once_with(
        get_file_content(initial_cluster, 'new'),
    )
    subprocess_run.assert_called_once_with(
        ['systemctl', 'daemon-reload'],
        check=True,
        stdout=-1,
    )


@mock_ec2
@mock_autoscaling
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('subprocess.run')
@mock.patch('requests.get')
@mock.patch('requests.post')
@mock.patch('requests.delete')
def test_new_member_existing_cluster(
    requests_delete,
    requests_post,
    requests_get,
    subprocess_run,
    builtins_open,
):
    node = get_node()
    instance_ids = get_asg_instance_ids(node['region'])
    instances = get_instances(node['region'], instance_ids)
    config = get_config()
    initial_cluster = build_initial_cluster(config, instances)
    # set myself as first instance
    myself = instances[0]
    node = get_node(
        instance_id=myself.id,
        ip_address=myself.private_ip_address,
    )
    # make etcd return first instance with a stale id
    # to simulate a stale member
    bad_instance = copy.copy(instances[0])
    bad_instance.id += '_'
    mock_response = MockResponse(
        config,
        [bad_instance] + instances[1:],
    )
    requests_get.side_effect = mock_response.get
    requests_post.side_effect = mock_response.post_or_delete
    requests_delete.side_effect = mock_response.post_or_delete

    etcd_module = Etcd(node, config, False)
    etcd_module.run()

    # we assume first instance is will be the healthy one
    healthy_member_url = '%s://%s:%d' % (
            config['client_schema'],
            myself.private_ip_address,
            config['client_port'],
    )
    requests_get.assert_any_call(
        '%s/health' % healthy_member_url,
        timeout=5,
    )
    requests_get.assert_any_call(
        '%s/v2/members' % healthy_member_url,
        timeout=5,
    )
    requests_delete.assert_called_once_with(
        '%s/v2/members/%s' % (healthy_member_url, bad_instance.id),
        timeout=5,
    )
    post_data = {
        'name': myself.id,
        'peerURLs': ['%s://%s:%d' % (
            config['peer_schema'],
            myself.private_ip_address,
            config['peer_port'],
        )],
    }
    requests_post.assert_called_once_with(
        '%s/v2/members' % healthy_member_url,
        json=post_data,
        timeout=5,
    )
    builtins_open.assert_called_once_with(config['drop_in_file'], 'w')
    builtins_open().write.assert_called_once_with(
        get_file_content(initial_cluster, 'existing'),
    )
    subprocess_run.assert_called_once_with(
        ['systemctl', 'daemon-reload'],
        check=True,
        stdout=-1,
    )
