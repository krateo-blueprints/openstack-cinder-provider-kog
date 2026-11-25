---
type: Usage
title: openstack-cinder-provider-kog — usage
description: How to install openstack-cinder-provider-kog on a cluster with oasgen-provider, feed it krateo-openstack-blueprint's KOG credentials, create and wait for volumes, and delete them in the right order.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - usage
  - install
timestamp: 2026-11-25T00:00:00Z
---

# Usage

Status on 2026-11-25: the chart renders, and oasgen-provider's generator (0.80.0 and 0.93.0) turns it
into valid-looking CRDs. **No cluster has run it yet.** The first live run is krateo-openstack-blueprint
#308's run B.

## Prerequisites

- **oasgen-provider** in the cluster, at a version the README allows. krateo-openstack-blueprint
  installs 0.80.0 from OCI, with its CRDs in step (that README's "Driving this OpenStack with Krateo KOG
  operators"). Before you pick another version, read oasgen-provider's
  [retracted-versions.yaml](https://github.com/krateo-platformops/oasgen-provider/blob/main/retracted-versions.yaml).
- **A Cinder** reachable from the cluster, registered in Keystone's catalog.
- **A Secret with `clouds.yaml`** in the namespace you install into. On krateo-openstack-blueprint, set
  `kogCredentials.enabled: true` and use `openstack-kog-clouds` in the Openstack release's namespace.

## Install with helm

```console
$ helm upgrade --install openstack-cinder-provider-kog \
    oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog --version 0.1.0 \
    -n openstack --set authBridge.cloudsSecret=openstack-kog-clouds
```

## Install through Krateo

Register the CompositionDefinition, then apply a Composition: see
[examples/composition](../examples/composition/README.md). The portal shows a CompositionDefinition only
to users who may list CompositionDefinitions in its namespace (PUBLISHING.md rule 11); grant that where
you register it.

## Check the install

```console
$ kubectl -n openstack get deploy openstack-cinder-provider-kog-auth-bridge
$ kubectl -n openstack logs deploy/openstack-cinder-provider-kog-auth-bridge | head -1
[proxy] cloud=openstack service=block-storage endpoint=http://cinder-api.openstack.svc.cluster.local:8776/v3
$ kubectl -n openstack get restdefinitions
$ kubectl get crd volumes.blockstorage.openstack.krateo.io volumeconfigurations.blockstorage.openstack.krateo.io
```

The log line's format is the proxy's (`openstack-auth-proxy.py`); the endpoint shown is what the
blueprint's catalog holds. If the endpoint ends in `/v3/<project id>`, set `authBridge.upstreamEndpoint`
to the `/v3` root.

## Create volumes

```console
$ kubectl -n openstack create secret generic cinder-kog-unused-token \
    --from-literal=token=unused-the-auth-bridge-sends-the-keystone-token
$ kubectl apply -f examples/bootable-volume/volumes.yaml
```

The token is a placeholder: the auth-bridge sends its own Keystone token
([configuration](configuration.md#volumeconfiguration)).

## Wait for `available`

`Ready` means the volume exists. Wait on Cinder's own status before you boot from or attach a volume:

```console
$ kubectl -n openstack wait volumes.blockstorage.openstack.krateo.io/boot-volume \
    --for=jsonpath='{.status.volume.status}'=available --timeout=15m
```

If it stops at `error`, Cinder failed to create it (no space, the image could not be copied). The CR
stays `Ready`: it reports that the volume exists. Read `cinder-volume`'s log, delete the CR and fix the
cause.

## Change a volume

There is no update verb. After create, a changed `spec.volume` field shows as a not-up-to-date condition
naming the field, and nothing is sent to Cinder. To change a volume, delete and recreate it, or change it
in Cinder and bring the spec back in line.

## Delete

```console
$ kubectl -n openstack delete volumes.blockstorage.openstack.krateo.io data-volume
```

The CR stays until Cinder's get answers `404`. Cinder refuses to delete an attached volume, one with
snapshots or one in migration; the CR then stays and the delete is retried. Detach first: delete the nova
attachment, then the Instance, then the Volume.

## Troubleshooting

- **The auth-bridge is not Ready:** its probe is `GET /` through the proxy. Cinder answers it at the `/v3`
  root. Check the proxy log for the endpoint and for Keystone errors.
- **A Volume shows a not-up-to-date condition on `volume_type`:** the spec names the type by ID, and
  Cinder reports it by name. Use the name.
- **A Volume came back after it was deleted in Cinder:** expected while its CR exists. The get answered
  `404`, and the controller read that as "create it".
