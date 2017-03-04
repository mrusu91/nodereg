import logging
import subprocess

from .interfaces import AbstractModule

log = logging.getLogger(__name__)


class Hostname(AbstractModule):

    def _tag_to_hostname(self) -> str:
        tag_name = self.config['tag_name']
        return str(self.node['tags'].get(tag_name)).lower()

    def _ip_to_hostname(self) -> str:
        octets = self.config['ip_address']['octets']
        glue = self.config['ip_address']['glue']
        private_ip = self.node['metadata']['local-ipv4'].split('.')
        return glue.join(str(n) for n in private_ip[-octets:])

    def _build_hostname(self) -> str:
        values = []
        if self.config.get('tag_name'):
            values.append(self._tag_to_hostname())
        if self.config.get('ip_address'):
            values.append(self._ip_to_hostname())
        glue = self.config['glue']
        return glue.join(values)

    def run(self) -> str:  # type: ignore
        hostname = self._build_hostname()
        log.info('Setting hostname: %s', hostname)
        hostname_cmd = ['hostnamectl', 'set-hostname', hostname]
        if self.chroot_path:
            hostname_cmd = ['chroot', self.chroot_path] + hostname_cmd
        subprocess.run(
            hostname_cmd,
            stdout=subprocess.PIPE,
            check=True,
        )
        return hostname
