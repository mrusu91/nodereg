import argparse
import logging
from os import path
from time import sleep
from typing import Any, Dict, Optional

import yaml
from boto import ec2
from boto.utils import get_instance_identity, get_instance_metadata

from .modules import Etcd, HostedZone, Hostname, TinyCert

log = logging.getLogger(__name__)


class Registrator(object):

    def __init__(
        self,
        custom_config_file: Optional[str]=None,
    ) -> None:
        default_config_file = path.abspath(
            path.join(
                path.dirname(__file__),
                'config.yaml',
            ),
        )
        self.config = self._read_config(default_config_file)
        if custom_config_file:
            custom_config = self._read_config(custom_config_file)
            self.config.update(custom_config)
        self.node = self._get_node_metadata()

    def _read_config(self, config_file: str) -> Dict[str, Any]:
        with open(config_file) as _file:
            return yaml.load(_file)

    def _get_node_metadata(self) -> Dict[str, Any]:
        node = {
            'metadata': get_instance_metadata(),
            'region': get_instance_identity()['document']['region'],
        }
        ec2_connection = ec2.connect_to_region(node['region'])
        instance_id = node['metadata']['instance-id']
        instance_tags = ec2_connection.get_all_tags(
            filters={'resource-id': instance_id},
        )
        node['tags'] = {
            tag.name: tag.value
            for tag in instance_tags
        }
        return node

    def run(self) -> None:
        is_ami_build = self.node['tags'].get(
            self.config['base']['ami_build_tag'],
        )
        if is_ami_build:
            log.info('AMI build detected. Sleeping forever')
            while True:
                sleep(3600)

        chroot_path = self.config['base']['chroot_path']

        # Hostname
        hostname_module = Hostname(
            self.node,
            self.config['hostname'],
            chroot_path,
        )
        hostname = hostname_module.run()
        # Hosted Zone
        hosted_zone_module = HostedZone(
            self.node,
            self.config['hosted_zone'],
        )
        fqdn = hosted_zone_module.run(hostname)
        # TinyCert
        tinycert_module = TinyCert(
            self.node,
            self.config['tinycert'],
            chroot_path,
        )
        tinycert_module.run(fqdn)
        # Etcd
        etcd_module = Etcd(
            self.node,
            self.config['etcd'],
            chroot_path,
        )
        etcd_module.run()


def _get_args() -> argparse.Namespace:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '-c',
        '--config',
        dest='config',
        action='store',
        help='Path to config file',
    )
    args = arg_parser.parse_args()
    return args


def main() -> None:
    args = _get_args()
    custom_config_file = args.config
    registrator = Registrator(custom_config_file)
    registrator.run()


if __name__ == '__main__':
    main()
