---
type: API
title: openstack-cinder-provider-kog — api
description: The CRDs openstack-cinder-provider-kog makes oasgen-provider generate — Volume at blockstorage.openstack.krateo.io/v3-0 and VolumeConfiguration at v1alpha1 — and the CompositionDefinition's Composition kind.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - crd
  - api
timestamp: 2026-11-25T00:00:00Z
---

# API

Use fully qualified names with kubectl: `volumes.blockstorage.openstack.krateo.io`. Another CRD may
also be called `volumes`.

What follows is the output of oasgen-render 0.80.0 and 0.93.0 for this chart, read on 2026-11-25
(`hack/render-check.py`). A cluster has not admitted these CRDs yet.

## Volume

- **Group, version, kind:** `blockstorage.openstack.krateo.io`, `v3-0`, `Volume`. The version comes from
  the document's `info.version`, `"3.0"`.
- **Scope:** Namespaced. Plural `volumes`, singular `volume`.

### spec

| Field | Type | Required | Notes |
|---|---|---|---|
| `configurationRef.name` | string | yes | the `VolumeConfiguration` |
| `configurationRef.namespace` | string | no | defaults to the Volume's namespace |
| `volume.size` | integer, minimum 1 | yes | GiB |
| `volume.name` | string, max 255 | no | |
| `volume.description` | string, max 255 | no | |
| `volume.imageRef` | string, max 255 | no | a Glance image id; makes the volume bootable |
| `volume.volume_type` | string, max 255 | no | give the name; Cinder reports the type by name |
| `volume.availability_zone` | string, 1-255 | no | |

`spec.volume` is sent whole as the create body, `{"volume": {...}}`.

### status

Filled from the create response, then from every get.

| Field | Type | Notes |
|---|---|---|
| `volume.id` | string | the get and delete paths read it |
| `volume.name` | string, nullable | null when created without a name |
| `volume.status` | string | `creating`, `downloading`, `available`, `in-use`, `error`, ... |
| `volume.size` | integer | GiB |
| `volume.bootable` | string | `"true"` or `"false"` |
| `volume.attachments` | array | items: `id`, `attachment_id`, `volume_id`, `server_id`, `host_name`, `device`, `attached_at` |
| `volume.volume_type` | string, nullable | the type's name |
| `volume.availability_zone` | string, nullable | |

These lists are fixed once installed: oasgen-provider makes `identifiers` immutable and
`additionalStatusFields` append-only. A later version can add a status field, never remove one.

### Verbs

| Action | Request | Success |
|---|---|---|
| create | `POST /volumes` with `{"volume": spec.volume}` | `202` with the volume |
| get | `GET /volumes/{status.volume.id}` | `200`; `404` means absent |
| delete | `DELETE /volumes/{status.volume.id}` | `202`; the CR stays until the get answers `404` |

## VolumeConfiguration

`blockstorage.openstack.krateo.io/v1alpha1`. `spec.authentication.bearer.tokenRef` (`name`, `namespace`,
`key`, all required). The auth-bridge replaces the header, so the token is never used
([configuration](configuration.md)).

## The Composition kind

Registering `compositiondefinition.yaml` serves `composition.krateo.io/v<version with dashes>`, Kind
`OpenstackCinderProviderKog` (chart 0.1.0 serves `v0-1-0`). Its `spec` is the chart's values.
