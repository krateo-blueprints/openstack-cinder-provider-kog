---
type: Log
title: openstack-cinder-provider-kog — log
description: Curated history of openstack-cinder-provider-kog — notable changes and decisions, not a generated changelog.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - log
  - history
timestamp: 2026-11-25T00:00:00Z
---

# Log

Release notes live in GitHub Releases.

## 2026-11-25: pre-releases

- **Why:** run B must install an untagged commit through the normal CompositionDefinition path, and release-oci cannot:
  its preflight and index gate refuse any version that is not plain `X.Y.Z`.
- **What:** `prerelease.yaml` (dispatch only) pushes `X.Y.Z-main.g<sha7>` or `-dev.g<sha7>` to GHCR and attaches the
  stamped CompositionDefinition and examples as a run artifact. `hack/release-version.sh` defines both shapes;
  `hack/release-preflight` now refuses a pre-release version. Adapted from rook-ceph-blueprint `2f4ce94`.
- **Gate:** `hack/validate-prerelease-channel.py`: no path to the index, a release or a tag; permissions exactly
  `contents: read` + `packages: write`; each check proven on a mutated copy.

## 2026-11-25: first version (0.1.0, unreleased)

- **Why:** krateo-openstack-blueprint #308 (Ceph storage) passed its first live run: cinder and glance
  store in Ceph on GKE. Its acceptance needs volumes created through KOG controllers, and Diego decided to
  build a cinder KOG. Run B will create a bootable Volume from an image, boot a nova-kog Instance from it
  and attach a second Volume.
- **What:** one kind, `Volume`, with create, get and delete over Cinder v3 `/volumes`. The OpenAPI subset
  was read from cinder stable/2026.1 and the api-ref. The auth-bridge script is glance-kog's, unchanged.
- **Decisions:** project-less URLs; service type `block-storage`; no update verb; no findby; Ready means
  "exists". Each is in [overview](overview.md) with its source.
- **Gates:** the create response must carry every status path a get or delete reads
  (`hack/validate-create-returns-get-id.py`, new); block-style YAML (`hack/check-yaml-block-style.py`,
  new); glance-kog's status-field and findby gates; a render through oasgen-render 0.80.0 and 0.93.0.
- **Not yet done:** any run on a cluster.
