---
type: Component
title: openstack-cinder-provider-kog — index
description: The map of the openstack-cinder-provider-kog doc bundle — a Krateo KOG provider that exposes OpenStack Cinder block-storage v3 volumes as the Volume kind through oasgen-provider and a Keystone auth-bridge proxy.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - openstack
  - cinder
timestamp: 2026-11-25T00:00:00Z
---

# openstack-cinder-provider-kog

A Krateo KOG provider for OpenStack Cinder (block storage v3). One kind in 0.1.0: `Volume`, with
create, get and delete. oasgen-provider generates the CRD from a curated OpenAPI subset and runs the
controller. A Keystone auth-bridge proxy adds the token.

| Page | What it covers |
|---|---|
| [overview](overview.md) | the pipeline, the auth-bridge, and every design decision with its source |
| [usage](usage.md) | install, create volumes, wait for them, delete them |
| [configuration](configuration.md) | every chart value and the VolumeConfiguration |
| [api](api.md) | the generated CRDs, field by field |
| [examples](examples.md) | the runnable examples |
| [release](release.md) | how a release ships |
| [log](log.md) | history |

## Layout

- `chart/`: the chart, named after the repository (REPOSITORY.md R2, R3).
  - `assets/volume.yaml`: the curated OpenAPI 3.0 subset.
  - `templates/rd-volume.yaml`, `templates/configmap-volume.yaml`: the RestDefinition and its document.
  - `templates/auth-bridge-*.yaml`, `scripts/openstack-auth-proxy.py`: the proxy.
  - `samples/`: example CRs, not packaged.
- `compositiondefinition.yaml`: registers the chart with Krateo. The release ships it inside the chart.
- `examples/`: runnable examples, each with a README.
- `hack/`: the CI gates and the release hook.
