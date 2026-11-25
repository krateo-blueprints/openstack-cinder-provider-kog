---
type: Example
title: bootable-volume — a bootable Volume from an image, and a data Volume
description: Create a bootable Cinder volume from a Glance image and an empty data volume with the Volume kind, wait for them to be available, and hand their ids to nova-kog.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - cinder
  - volume
  - example
timestamp: 2026-11-25T00:00:00Z
---

# bootable-volume

`volumes.yaml` creates:

- `cinder-config`, the `VolumeConfiguration` both volumes reference;
- `boot-volume`, 2 GiB, copied from a Glance image (`imageRef`), so Cinder marks it bootable;
- `data-volume`, 1 GiB and empty.

This is the shape of krateo-openstack-blueprint #308's run B. It has not run yet: no live run of this
KOG exists at the time of writing (2026-11-25).

## Run it

The KOG must be installed (see [composition](../composition/README.md)). Fill in the image id, then:

```console
$ kubectl -n openstack create secret generic cinder-kog-unused-token \
    --from-literal=token=unused-the-auth-bridge-sends-the-keystone-token
$ kubectl apply -f examples/bootable-volume/volumes.yaml
```

The token Secret is a placeholder. The OpenAPI document declares a bearer scheme, so oasgen-provider
generates a `VolumeConfiguration` that needs one. The auth-bridge drops that header and sends its own
Keystone token.

## Wait for `available`, not for Ready

`Ready` means the volume exists in Cinder. It does not mean the volume is usable. Cinder answers the
create with `202` and status `creating`, and a bootable volume then spends time in `downloading`. Wait
on the status field:

```console
$ kubectl -n openstack wait volumes.blockstorage.openstack.krateo.io/boot-volume \
    --for=jsonpath='{.status.volume.status}'=available --timeout=15m
$ kubectl -n openstack get volumes.blockstorage.openstack.krateo.io boot-volume \
    -o jsonpath='{.status.volume.id} {.status.volume.bootable}{"\n"}'
```

`bootable` is the string `"true"` or `"false"`, as Cinder returns it.

## Hand the ids to nova-kog

- **Boot from the volume:** a nova-kog `Instance` with `block_device_mapping_v2`, one entry with
  `source_type: volume`, `destination_type: volume`, `boot_index: 0` and `uuid` set to
  `boot-volume`'s `status.volume.id`.
- **Attach the data volume:** nova-kog's volume attachment kind with `data-volume`'s
  `status.volume.id`. It ships disabled in nova-kog 0.1.10 (`restdefinitions.volume_attachment.enabled`).
- **Check the attachment from this side:** `status.volume.attachments` lists the server id and the
  device, and `status.volume.status` becomes `in-use`.

## Delete in the right order

Cinder refuses to delete an attached volume (400). Delete the attachment, then the Instance, then the
Volume CRs.

Keep `delete_on_termination` false (Nova's default) on the boot volume's mapping. If Nova deletes the
volume while its Volume CR still exists, the next get answers 404, and the controller reads 404 as
"absent" and creates the volume again (rest-dynamic-controller 0.80.0
`internal/controllers/restResources.go` Observe, read in source).
