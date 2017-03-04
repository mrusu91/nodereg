import logging
import subprocess
from typing import Any, Dict, List, Optional

import requests
from boto import ec2  # type: ignore
from boto.ec2 import autoscale  # type: ignore

from .interfaces import AbstractModule

log = logging.getLogger(__name__)


class Etcd(AbstractModule):

    def _member_from_node(self) -> Dict[str, Any]:
        return {
            'id': None,
            'name': self.node['metadata']['instance-id'],
            'client_url': '%s://%s:%d' % (
                self.config['client_schema'],
                self.node['metadata']['local-ipv4'],
                self.config['client_port'],
            ),
            'peer_url': '%s://%s:%d' % (
                self.config['peer_schema'],
                self.node['metadata']['local-ipv4'],
                self.config['peer_port'],
            ),
        }

    def _members_from_instance_ids(
        self,
        instance_ids: List[str],
    ) -> List[Dict[str, Any]]:
        ec2_conn = ec2.connect_to_region(self.node['region'])
        members = [
            {
                'id': None,
                'name': instance.id,
                'client_url': '%s://%s:%d' % (
                    self.config['client_schema'],
                    instance.private_ip_address,
                    self.config['client_port'],
                ),
                'peer_url': '%s://%s:%d' % (
                    self.config['peer_schema'],
                    instance.private_ip_address,
                    self.config['peer_port'],
                ),
            }
            for r in ec2_conn.get_all_instances(instance_ids=instance_ids)
            for instance in r.instances
        ]
        return members

    def _members_from_etcd_members(
        self,
        etcd_members: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        members = [
            {
                'id': etcd_member['id'],
                'name': etcd_member['name'],
                'client_url': next(
                    iter(etcd_member.get('clientURLs', [])),
                    '',
                ),
                'peer_url': etcd_member['peerURLs'],
            }
            for etcd_member in etcd_members
        ]
        return members

    def _get_asg_instances(self) -> List[str]:
        asg_conn = autoscale.connect_to_region(self.node['region'])
        asg_name = asg_conn.get_all_autoscaling_instances(
            [self.node['metadata']['instance-id']],
        )[0].group_name
        log.info('Instance is part of ASG %s', asg_name)
        asg = asg_conn.get_all_groups([asg_name])[0]
        instance_ids = [
            instance.instance_id
            for instance in asg.instances
            if instance.lifecycle_state == 'InService'
        ]
        return instance_ids

    def _get_expected_members(self) -> List[Dict[str, Any]]:
        instance_ids = self._get_asg_instances()
        members = self._members_from_instance_ids(instance_ids)
        return members

    def _find_healthy_member(
        self,
        members: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for member in members:
            url = '%s/health' % member['client_url']
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
            except requests.exceptions.RequestException:
                continue
            else:
                if response.json().get('health') == 'true':
                    log.info('Found healthy member at %s', url)
                    return member
        return None

    def _get_existing_members(
        self,
        healthy_member: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        url = '%s/v2/members' % healthy_member['client_url']
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        etcd_members = response.json()['members']
        members = self._members_from_etcd_members(etcd_members)
        return members

    def _remove_bad_members(
        self,
        healthy_member: Dict[str, Any],
        expected_members: List[Dict[str, Any]],
        existing_members: List[Dict[str, Any]],
    ) -> None:
        base_url = '%s/v2/members' % healthy_member['client_url']
        expected_names = [member['name'] for member in expected_members]
        members_to_remove = [
            member
            for member in existing_members
            if member['name'] not in expected_names
        ]
        for member in members_to_remove:
            log.info('Removing bad member %r', member)
            url = '%s/%s' % (base_url, member['id'])
            try:
                requests.delete(url, timeout=5)
            except requests.exceptions.RequestException:
                log.exception('Error while removing member %r', member)

    def _build_initial_cluster(
        self,
        expected_members: List[Dict[str, Any]],
    ) -> str:
        return ','.join([
            '%s=%s' % (member['name'], member['peer_url'])
            for member in expected_members
        ])

    def _add_member_to_cluster(
        self,
        healthy_member: Dict[str, Any],
        member_to_add: Dict[str, Any],
    ) -> None:
        url = '%s/v2/members' % healthy_member['client_url']
        post_data = {
            'name': member_to_add['name'],
            'peerURLs': [member_to_add['peer_url']],
        }
        log.info('Adding member %r to cluster at %s', member_to_add, url)
        response = requests.post(url, json=post_data, timeout=5)
        response.raise_for_status()

    def _create_systemd_dropin(self, initial_cluster: str, state: str) -> None:
        file_content = '\n'.join([
            '[Service]',
            'Environment=ETCD_INITIAL_CLUSTER="%s"' % initial_cluster,
            'Environment=ETCD_INITIAL_CLUSTER_STATE="%s"' % state,
        ])
        with open(self.config['drop_in_file'], 'w') as _file:
            _file.write(file_content)
        daemon_reload_cmd = ['systemctl', 'daemon-reload']
        if self.chroot_path:
            daemon_reload_cmd = [
                'chroot',
                self.chroot_path,
            ] + daemon_reload_cmd
        subprocess.run(
            daemon_reload_cmd,
            stdout=subprocess.PIPE,
            check=True,
        )

    def run(self) -> None:
        expected_members = self._get_expected_members()
        healthy_member = self._find_healthy_member(expected_members)
        if healthy_member:
            existing_members = self._get_existing_members(healthy_member)
        else:
            existing_members = []
        myself = self._member_from_node()
        initial_cluster = self._build_initial_cluster(expected_members)
        if not existing_members:
            self._create_systemd_dropin(initial_cluster, state='new')
        else:
            self._remove_bad_members(
                healthy_member,
                expected_members,
                existing_members,
            )
            myself_in_existing_members = any([
                True
                for member in existing_members
                if member['name'] == myself['name']
            ])
            if not myself_in_existing_members:
                self._add_member_to_cluster(healthy_member, myself)
            self._create_systemd_dropin(initial_cluster, state='existing')
