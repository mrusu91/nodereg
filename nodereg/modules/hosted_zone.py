import logging
from time import sleep

from boto import route53  # type: ignore

from .interfaces import AbstractModule

log = logging.getLogger(__name__)


class HostedZone(AbstractModule):

    def _get_zone(self) -> route53.zone.Zone:
        r53_connection = route53.connect_to_region(self.node['region'])
        zone = r53_connection.get_zone(self.config['name'])
        if not zone:
            raise Exception('Hosted Zone %s not found' % self.config['name'])
        return zone

    def _update_zone(
        self,
        zone: route53.zone.Zone,
        fqdn: str,
    ) -> None:
        ip_address = self.node['metadata']['local-ipv4']
        all_records = [r for r in zone.get_records()]
        record_exists = False
        for record in all_records:
            if ip_address in record.resource_records:
                log.info(
                    'Found record %s containing node IP address %s',
                    str(record),
                    ip_address,
                )
                if record.name != fqdn:
                    log.warning(
                        'Record %s with node IP address %s has wrong name',
                        str(record),
                        ip_address,
                    )
                    log.warning('Removing record %s', str(record))
                    # FIXME: handle records with multiple values
                    delete_request = zone.delete_record(
                        record,
                        'nodereg: stale name',
                    )
                    while delete_request.status != 'INSYNC':
                        log.info('Waiting for comfirmation...')
                        sleep(1)
                        delete_request.update()
                else:
                    record_exists = True
                    log.info(
                        'Record %s is up to date',
                        str(record),
                    )
        if not record_exists:
            zone.add_a(fqdn, ip_address, ttl=60)
            log.info(
                'Added A record (%s -> %s) to zone %s',
                fqdn, ip_address, zone.name,
            )

    def run(  # type: ignore # pylint: disable=arguments-differ
        self,
        hostname: str,
    ) -> str:
        zone = self._get_zone()
        fqdn = '.'.join([hostname.lower(), zone.name.lower()])
        self._update_zone(zone, fqdn)
        return fqdn
