# Deploying Gateway

Push to `main` — CI builds and pushes `ghcr.io/awfulwoman/gateway:latest`. Then run the
Ansible role on the storage host to pull and restart the container:

```
playbook: playbooks/hosts/server-64gb-storage/core.yaml
tags: composition-gateway
```
