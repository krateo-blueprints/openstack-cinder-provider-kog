---
type: ExampleIndex
title: openstack-cinder-provider-kog — examples
description: Index of the runnable examples under examples/ and the sample CRs in chart/samples.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - examples
timestamp: 2026-11-25T00:00:00Z
---

# Examples

- [composition](../examples/composition/README.md): install the KOG through its CompositionDefinition,
  with krateo-openstack-blueprint's `openstack-kog-clouds`. `hack/release-preflight` refuses a release
  whose version this example does not name.
- [bootable-volume](../examples/bootable-volume/README.md): a bootable Volume from a Glance image and an
  empty data Volume, how to wait for them, and how to hand their ids to nova-kog. The shape of
  krateo-openstack-blueprint #308's run B.
- `chart/samples/volume-resources.yaml`: a VolumeConfiguration and two Volumes to edit. Not packaged.

None of these has run on a cluster yet (2026-11-25).
