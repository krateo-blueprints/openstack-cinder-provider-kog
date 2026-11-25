---
type: Architecture
title: openstack-cinder-provider-kog — overview
description: How openstack-cinder-provider-kog works — a curated Cinder v3 OpenAPI subset and a RestDefinition that oasgen-provider turns into the Volume CRD and one controller, behind a Keystone auth-bridge — and why each part is shaped the way it is.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - oasgen-provider
  - rest-dynamic-controller
  - cinder
timestamp: 2026-11-25T00:00:00Z
---

# Overview

## How it works

```
Volume CR --> rest-dynamic-controller --HTTP--> auth-bridge --X-Auth-Token--> Cinder v3
                    ^                                 |
   RestDefinition --+-- oasgen-provider               +-- Keystone (clouds.yaml)
   + OpenAPI ConfigMap   (generates the CRDs, runs the controller)
```

1. The chart renders a `RestDefinition` and a ConfigMap with `chart/assets/volume.yaml`.
2. oasgen-provider generates two CRDs from them: `Volume` (`blockstorage.openstack.krateo.io/v3-0`)
   and `VolumeConfiguration` (`v1alpha1`). It runs one rest-dynamic-controller for `Volume`.
3. The controller calls the document's `servers[0].url`, which is the auth-bridge Service.
4. The auth-bridge logs in to Keystone with `clouds.yaml`, finds the block-storage endpoint in the
   catalog, adds a fresh `X-Auth-Token` and forwards the call.

## Where the OpenAPI subset comes from

Every field was read from cinder at `stable/2026.1` (commit `58f7ac750dba3648d0f5c8517dba5e8f529f26cd`)
and from the Block Storage API v3 reference (<https://docs.openstack.org/api-ref/block-storage/v3/>,
source `api-ref/source/v3/volumes-v3-volumes.inc`). The asset names the file for each schema.

| Field | Where | Source |
|---|---|---|
| request `volume` envelope, `required: volume` | create body | `cinder/api/schemas/volumes.py` `create` L25-72 |
| `size` (integer, min 1) | create body | same; `parameter_types.volume_size` L220-225 (integer or digits, min 1). Required here, see below |
| `name`, `description` (max 255) | create body | `schemas/volumes.py` `create`; `cinder/api/v3/volumes.py` create maps them to display_name/description |
| `imageRef` (max 255) | create body | `schemas/volumes.py` `create`; resolved by `_image_uuid_from_ref`, `volumes.py` L282-324; api-ref "Create a volume" (bootable) |
| `volume_type` (max 255) | create body | `parameter_types.name_allow_zero_min_length` L191-193; `get_by_name_or_id` in create |
| `availability_zone` (1-255) | create body | `parameter_types.availability_zone` L294-296 |
| create answers `202` with the volume | create response | `volumes.py` `@wsgi.response(HTTPStatus.ACCEPTED)` L350, `return self._view_builder.detail(...)` L474-475; api-ref "Create a volume" |
| `id`, `name`, `description`, `status`, `size`, `availability_zone`, `volume_type`, `created_at`, `updated_at`, `multiattach`, `encrypted`, `attachments` | get and create response | `cinder/api/v3/views/volumes.py` `legacy_detail` L134-178 |
| `bootable` is the string `"true"`/`"false"` | response | `views/volumes.py` L152, `str(volume.get('bootable')).lower()` |
| `volume_type` is the type's name | response | `views/volumes.py` `_get_volume_type` L85-100 |
| attachment items: `id`, `attachment_id`, `volume_id`, `server_id`, `host_name`, `device`, `attached_at` | response | `views/volumes.py` `_get_attachments` L106-132 |
| get answers `200`; a missing volume `404` | get | `volumes.py` `show` L97-107; `cinder/volume/api.py` `get` L594-605 raises `VolumeNotFound`; `cinder/exception.py` L321-336 (`code = 404`); `cinder/api/openstack/wsgi.py` L603-605 |
| delete answers `202`, no body | delete | `volumes.py` `delete` L68-95; api-ref "Delete a volume" |

No microversion header is sent, so Cinder answers at 3.0, its minimum
(`cinder/api/openstack/api_version_request.py` `_MIN_API_VERSION`). Every field above exists at 3.0.

## Decisions

### The `Volume` Kind and the `volume` envelope

Cinder wraps every body in `{"volume": {...}}`. So the generated spec has one property, `volume`, and
the status fields are dotted (`status.volume.id`), as in nova-kog's `Instance`. nova-kog found that a
Kind named after its envelope (`Server` with `server`) made an invalid CRD in an older generator. Here
`Volume` with `volume` renders cleanly: `hack/render-check.py` ran it through oasgen-render 0.80.0 and
0.93.0 on 2026-11-25, and both gave `spec.volume` as an object with its six properties. That is the
generator's output; a real apiserver has not admitted it yet. CI repeats the render on every change.

### Paths without a project id

See the README's "Project-less URLs" section: Cinder 2026.1 routes both forms for every microversion,
and the blueprint's catalog is project-less.

### The service type is `block-storage`, not `volumev3`

The blueprint registers cinder in the catalog as type `volumev3`. The proxy asks keystoneauth for the
endpoint of `SERVICE_TYPE`. Measured on 2026-11-25 in the proxy's own image
(`quay.io/airshipit/openstack-client:2026.1-ubuntu_noble`):

- `discover._normalize_version_args(None, None, None, service_type=...)` gives `(None, None)` for
  `block-storage`, and `((3, 0), (3, inf))` for `volumev3`. An implied version makes keystoneauth run
  version discovery instead of returning the catalog URL (`BaseIdentityPlugin.get_endpoint`'s comment).
- A catalog with one `volumev3` entry at `http://cinder-api.openstack.svc.cluster.local:8776/v3`
  returns that URL unchanged for both `block-storage` and `volumev3` (`ServiceCatalogV3.url_for`).

So `block-storage` finds the blueprint's entry and returns it as it is. Not measured: the full session
path against a live Keystone.

### The auth-bridge is glance-kog's, unchanged

`chart/scripts/openstack-auth-proxy.py` is byte-identical to openstack-glance-operator-kog's at
`1b3ab13` (sha256 `33c2db8d…2b97c9`). Cinder needs nothing else from it: no microversion header (3.0 is
enough), and the same `X-Auth-Token`. The templates differ only in names, comments and block-style
YAML. The values differ in their Cinder defaults (`serviceType`, `cloudsSecret`), and the schema refuses an
`upstreamEndpoint` that does not end in `/v3`.

### No update verb

Cinder's `PUT /volumes/{id}` takes only `name`, `description`, `display_name`, `display_description`
and `metadata`, with `additionalProperties: false` (`cinder/api/schemas/volumes.py` `update` L86-115).
rest-dynamic-controller sends a top-level spec property whole, so an update would carry `size` and
`imageRef` and be refused with 400. A changed size is also drift that no update could fix. Without an
update verb, a spec change after create shows as a not-up-to-date condition naming the field, and
nothing is sent (0.80.0 `restResources.go` Update logs "API action update not found" and returns).

### No findby

Like glance-kog's `Image` and nova-kog's `Instance`. Cinder volume names are not unique, so a findby by
name could adopt another volume. The get is addressed by `status.volume.id`.

### The create must return the id

The get and delete paths read `status.volume.id`. Only a response writes it: the create's, then the
get's. A create that succeeded without the id would leave the CR unaddressable and the volume orphaned
on delete; nova-kog's owner measured that at oasgen 0.74.0. Cinder's create returns the whole volume.
`hack/validate-create-returns-get-id.py` fails CI if any success response of the create stops carrying
every status path a get or delete parameter reads.

### Ready means "exists"

The create answers `202`, which the controller records as `Pending` (0.80.0
`internal/tools/client/restclient.go` `IsPending`). The next get that answers `200` sets `Ready` when the
spec matches (`restResources.go` L1066-1075). Cinder's status can still be `creating` or `downloading`
then, or `error`. So consumers wait on `status.volume.status`.

### Deleting

Cinder deletes asynchronously (`202`, then `deleting`). It refuses an attached volume, one in migration,
or one with snapshots (api-ref "Delete a volume"). The controller asks the get before it releases the
finalizer and holds it while the volume still exists (0.80.0 `restResources.go` `Delete`, then
`resolveDeleteOutcome`; read in source). So the CR stays until Cinder answers `404`, and a refused delete
is retried. Detach first.
If something else deletes the volume while its CR exists, the get answers `404` and the controller
creates it again. That is the KOG model for every get-observed kind.
