---
type: Configuration
title: openstack-cinder-provider-kog — configuration
description: Every chart value of openstack-cinder-provider-kog (the Volume RestDefinition toggle and the auth-bridge), the VolumeConfiguration CR, and the settings for krateo-openstack-blueprint's KOG credentials.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - configuration
timestamp: 2026-11-25T00:00:00Z
---

# Configuration

`chart/values.schema.json` types every value. Through the CompositionDefinition, each value is also a
field of the Composition's `spec`.

## Chart values

| Value | Default | What it does |
|---|---|---|
| `restdefinitions.volume.enabled` | `true` | Render the Volume RestDefinition and its OpenAPI ConfigMap. |
| `restdefinitions.volume.resourceGroup` | `blockstorage.openstack.krateo.io` | API group of the generated CRDs. |
| `restdefinitions.volume.resourceKind` | `Volume` | Kind of the generated CRD. |
| `authBridge.enabled` | `true` | Deploy the proxy (Deployment, Service, script ConfigMap). The document's server URL points at it, so turning it off leaves the controller with nothing to call. |
| `authBridge.replicaCount` | `1` | Proxy replicas. It is stateless. |
| `authBridge.cloudsSecret` | `cinder-clouds` | Secret with key `clouds.yaml`, in the release namespace. |
| `authBridge.osCloud` | `openstack` | Cloud name in `clouds.yaml`. |
| `authBridge.serviceType` | `block-storage` | Catalog service type. Keep `block-storage`: it matches a `volumev3` entry, and `volumev3` itself triggers version discovery ([overview](overview.md)). |
| `authBridge.osInterface` | `internal` | Catalog interface: `internal`, `public` or `admin`. |
| `authBridge.upstreamEndpoint` | `""` | Skip the catalog and use this URL. It must end in `/v3`, with no project id; the schema refuses anything else. |
| `authBridge.image.repository` / `.tag` / `.pullPolicy` | `quay.io/airshipit/openstack-client` / `2026.1-ubuntu_noble` / `IfNotPresent` | The proxy image. It needs `python3` and openstacksdk. |
| `authBridge.service.type` / `.port` | `ClusterIP` / `8080` | The Service the controller calls. |
| `authBridge.resources` | 20m / 64Mi requests, 500m / 256Mi limits | Proxy resources. |
| `authBridge.podAnnotations`, `nodeSelector`, `tolerations`, `affinity` | unset | Pod placement and annotations. |
| `nameOverride`, `fullnameOverride` | `""` | Resource name overrides. |

## krateo-openstack-blueprint credentials

With `kogCredentials.enabled: true`, keystone renders in the Openstack release's namespace a Secret
`openstack-kog-clouds` (key `clouds.yaml`, cloud `openstack`, keystone's internal endpoint, interface
`internal`). This KOG reads it the way neutron- and glance-kog do. No new credential kind is needed:

| Value | Set it to |
|---|---|
| `authBridge.cloudsSecret` | `openstack-kog-clouds` |
| `authBridge.osCloud` | `openstack` (the default) |
| namespace | the Openstack release's namespace: a Pod mounts only a Secret in its own namespace |

The proxy reads `clouds.yaml` only when it starts. After the admin password rotates, restart it, as the
blueprint README says for neutron- and glance-kog:

```console
$ kubectl -n openstack rollout restart deployment openstack-cinder-provider-kog-auth-bridge
```

The Deployment name is `<release>-auth-bridge` when the release name contains the chart name, else
`<release>-openstack-cinder-provider-kog-auth-bridge`.

## VolumeConfiguration

oasgen-provider generates `VolumeConfiguration` (`v1alpha1`) because the document declares a bearer
scheme. Every Volume references one in `spec.configurationRef`. The auth-bridge drops the
`Authorization` header and sends its own Keystone token, so the referenced Secret holds a placeholder:

```yaml
apiVersion: blockstorage.openstack.krateo.io/v1alpha1
kind: VolumeConfiguration
metadata:
  name: cinder-config
  namespace: openstack
spec:
  authentication:
    bearer:
      tokenRef:
        name: cinder-kog-unused-token
        namespace: openstack
        key: token
```
