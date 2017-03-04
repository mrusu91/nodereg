=======
NodeReg
=======

A tool that helps bootstrapping nodes based on dynamic variables.

The usecase that gave birth to this tool:

    Kubernetes cluster in AWS,
    all nodes run CoreOS Container Linux,
    2 AMI, one for master and one for workers,
    2 autoscalling groups, one master and one workers
    
    NodeReg runs as a systemd one shot before any kubernetes components, this way
    we ensures it has the right certificates and any other dependencies
    
Supported Cloud Providers
--------------------------
Currently only AWS is supported

How to run
----------
- :code:`nodereg -c /path/to/custom/config`

There is also a docker image available:

- :code:`docker run -v my.config:/my.config viruxel/nodereg -c /my.config`

For developing:

- :code:`docker build -f Dockerfile.dev -t nodereg-dev . && docker run -it --entrypoint tox nodereg-dev`


Modules
-------
Base
^^^^
    Detect if instance is running to build the AMI, if so loops forever.

Hostname
^^^^^^^^
    Builds a hostname based on node tags and ip address.
    Updates the host with the new hostname.

Hosted Zone
^^^^^^^^^^^
    Builds a FQDN based on hostname and hosted zone name.
    Updates the hosted zone with A record.

AWS Instance IAM Role policy needed:

 .. code:: json

  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Action": [
                  "route53:ChangeResourceRecordSets",
                  "route53:GetHostedZone",
                  "route53:ListResourceRecordSets"
              ],
              "Effect": "Allow",
              "Resource": [
                  "arn:aws:route53:::hostedzone/{{ hosted_zone }}"
              ]
          }
      ]
  }

TinyCert.org
^^^^^^^^^^^^
    Downloads a CA and makes it available system wide.
    Generates a certificate for node FQDN and IP Address.
    Allow downloads other certificates.
    **NOTE:** This module downloads private keys as well.

Etcd
^^^^
    It generates a Systemd drop-in file that sets environment variables used by Etcd to
    either join or create a new cluster.
    Remove stale members.
    This works well with how Etcd is run in CoreOS

AWS Instance IAM Role policy needed:

 .. code:: json

  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Effect": "Allow",
              "Action": "autoscaling:Describe*",
              "Resource": "*"
          }
      ]
  }
  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Effect": "Allow",
              "Action": "ec2:Describe*",
              "Resource": "*"
          }
      ]
  }


Default Config
--------------

.. code:: yaml

  base:
    # The tag used to detect if node is running build an AMI from it.
    ami_build_tag: is_ami_build
    # Chroot to this path. Usefull if nodereg runs
    # in a container and you want to change the host.
    # Set it to false if no chroot required
    chroot_path: /media/root
  
  hostname:
    # The glue between hostname components
    glue: ''
    # Consider node tag value
    tag_name: Role
    # Consider IP address
    ip_address:
      # The last N octets of the IP address
      octets: 2
      # The glue between octets
      glue: '-'
  
  hosted_zone:
    # The name of the hosted zone
    name: k8s.com.
  
  # Get certificates from tinycert.org
  tinycert:
    email: test
    passphrase: test
    api_token: test
    # Make sure the CA cert is present and recognized system-wide
    # tinycert CA id
    # NOTE: the common name of the certificate is used as filename
    ca_id: 100
    ca_path: /media/root/etc/ssl/certs
    certificates_path: /media/root/etc/ssl/node_certs
    # Make sure the node has a certificate/key for it's FQDN and IP Address
    node_certificate: yes
    # Download other certificate/keys by tinycert id
    # NOTE: the common name of the certificate is used as filename
    certificates: []
  
  etcd:
    client_schema: http
    client_port: 2379
    peer_schema: http
    peer_port: 2380
    drop_in_file: /media/root/etc/systemd/system/etcd.service.d/70-initial-cluster.conf

