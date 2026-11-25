---
type: Example
title: composition — install the Cinder KOG through its CompositionDefinition
description: Install the OpenStack Cinder KOG operator layer (the Volume RestDefinition and the auth-bridge) as a Krateo Composition, using the credentials krateo-openstack-blueprint renders.
resource: oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog
tags:
  - krateo
  - kog
  - cinder
  - composition
  - example
timestamp: 2026-11-25T00:00:00Z
---

# composition

`composition.yaml` installs the Cinder KOG through Krateo instead of `helm install`. It deploys:

- the `Volume` RestDefinition and the ConfigMap with its OpenAPI document;
- the auth-bridge proxy, which adds a Keystone token to every call.

It creates no volume. Create volumes with `Volume` CRs: see [bootable-volume](../bootable-volume/README.md).

## Before you apply it

1. oasgen-provider runs in the cluster (see [usage](../../docs/usage.md)).
2. The CompositionDefinition is registered:

   The file in the repository carries the `CHART_VERSION` placeholder. The released chart carries a
   stamped copy:

   ```console
   $ helm pull oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog --version 0.1.0 --untar
   $ kubectl apply -f openstack-cinder-provider-kog/compositiondefinition.yaml
   ```
3. A Secret with key `clouds.yaml` exists in the namespace. On krateo-openstack-blueprint, set
   `kogCredentials.enabled: true`. Keystone then renders `openstack-kog-clouds` in the Openstack
   release's namespace. Install the KOG in that namespace too: a Pod can mount only a Secret in its
   own namespace.

## The Composition

The apiVersion follows the chart version: chart `0.1.0` serves `composition.krateo.io/v0-1-0`. The
Kind is the CompositionDefinition's name without hyphens. The `spec` is the chart's values
([configuration](../../docs/configuration.md)).

```yaml
apiVersion: composition.krateo.io/v0-1-0
kind: OpenstackCinderProviderKog
metadata:
  name: openstack-cinder-provider-kog
  namespace: openstack
spec:
  authBridge:
    cloudsSecret: openstack-kog-clouds
    osCloud: openstack
    upstreamEndpoint: ""
  restdefinitions:
    volume:
      enabled: true
```

## Run it

```console
$ kubectl apply -f examples/composition/composition.yaml
$ kubectl -n openstack get restdefinitions
$ kubectl get crd volumes.blockstorage.openstack.krateo.io
```

`upstreamEndpoint` empty means the proxy finds the endpoint in the Keystone catalog. Set it only to
bypass the catalog, to the v3 root without a project id.
