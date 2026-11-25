---
type: Runbook
title: openstack-cinder-provider-kog — release
description: How a release ships — one plain X.Y.Z tag runs the shared release-oci 2.1.0, which pushes the chart with its CompositionDefinition to GHCR and indexes the same bytes in the krateo-blueprints helm index, blueprints channel.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - release
  - oci
  - ghcr
  - chart
timestamp: 2026-11-25T00:00:00Z
---

# Release

One plain `X.Y.Z` tag (no `v`) on `main` releases the chart. `release-oci.yaml` and `release-notes.yaml`
trigger on it.

## Before the tag

1. Bump `examples/composition/composition.yaml` to `composition.krateo.io/v<X>-<Y>-<Z>`. Nothing stamps
   examples, and `hack/release-preflight` refuses the release when the example names another version.
2. Merge. The commit must have a successful `lint.yaml` run: the release refuses it otherwise
   (PUBLISHING.md rule 10).
3. Rehearse: dispatch `release-oci.yaml` on `main` with `chart_version` set and `dry_run` checked (the
   default). A dispatch without a version is refused, because its ref is a branch.

## What the tag does

1. **preflight** (this repository): the commit passed lint; `chart/Chart.yaml` has `version` and
   `appVersion` set to `CHART_VERSION`; the CompositionDefinition installs `CHART_VERSION`.
2. **release-oci 2.1.0** (krateo-platformops/.github, pinned by SHA):
   - runs the shared release preflight: a plain `X.Y.Z` (rule 13) and `hack/release-preflight <version>`;
   - checks `CHARTS_PUBLISH_TOKEN` for presence and shape;
   - stamps `CHART_VERSION`, copies `compositiondefinition.yaml` from the repository root into the chart
     and verifies it installs `oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog` at
     this version (`ship-cd.sh`);
   - runs the index content gate for channel `blueprints`;
   - pushes to GHCR, pulls the chart back and indexes those bytes through publish-chart.
3. **release-notes** writes the release body.

## The channel

`blueprints`. The package carries `values.schema.json` and a CompositionDefinition, and the index gate
puts such a chart there (PUBLISHING.md rule 2). Checked locally on 2026-11-25 with a copy of the
index gate (`.github/actions/index-gate/gate.sh` at krateo-blueprints/charts main, its GNU-tar member
pattern adapted to BSD tar): a stamped 0.1.0 package with the CompositionDefinition inside passes for
`blueprints` and is refused for `operators`.

## After the tag

- The CompositionDefinition to register is the one inside the released chart:
  `helm pull oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog --version X.Y.Z --untar`.
- There is no separate release asset for it.
