# openstack-cinder-provider-kog

## What is this

A Krateo KOG provider for **OpenStack Cinder** (block storage v3). It turns Cinder volumes into
Kubernetes custom resources. The chart ships:

- one curated OpenAPI 3.0 subset, `chart/assets/volume.yaml`, with the source of every field;
- one `RestDefinition` and the ConfigMap that holds the document;
- a stateless Keystone **auth-bridge** proxy, the same script as openstack-glance-operator-kog's.

oasgen-provider reads the RestDefinition, generates the CRDs, and runs one rest-dynamic-controller
for the kind. There is no hand-written controller and no image of its own.

| Kind | Cinder API | Verbs |
|------|------------|-------|
| `Volume` (`blockstorage.openstack.krateo.io/v3-0`) | `POST /volumes`, `GET` and `DELETE /volumes/{volume_id}` | create, get, delete |

- **Spec:** `spec.volume.size` (GiB, required), `name`, `description`, `imageRef` (makes the volume
  bootable), `volume_type`, `availability_zone`.
- **Status:** `status.volume.id`, `status`, `size`, `bootable`, `attachments`, `volume_type`,
  `availability_zone`, `name`.
- **No update verb.** Cinder's update accepts only name, description and metadata, and the controller
  would send the whole `spec.volume`. [docs/overview.md](docs/overview.md) explains it.
- **Ready means the volume exists**, not that it is `available`. Wait for
  `status.volume.status == available` before you boot from it or attach it.

Built for krateo-openstack-blueprint #308: cinder stores volumes in Ceph, and volumes must be created
through KOG controllers.

## Install

Requires **oasgen-provider >= 0.80.0 except 0.83.0, 0.85.0, 0.85.1, 0.91.0** (the versions above 0.80.0
that oasgen-provider has retracted, read 2026-11-25). CI renders the chart with 0.80.0, the version
krateo-openstack-blueprint installs, and with 0.93.0. `hack/validate-findby-identifiers.py` reads this
line, so keep it the one place the minimum is stated.

On krateo-openstack-blueprint, set `kogCredentials.enabled: true`. Keystone then renders the Secret
`openstack-kog-clouds` in the Openstack release's namespace. Install the KOG in that namespace:

```bash
helm upgrade --install openstack-cinder-provider-kog \
  oci://ghcr.io/krateo-blueprints/charts/openstack-cinder-provider-kog --version 0.1.0 \
  -n openstack --set authBridge.cloudsSecret=openstack-kog-clouds
```

Elsewhere, put an admin `clouds.yaml` in a Secret first:

```bash
kubectl -n openstack create secret generic cinder-clouds --from-file=clouds.yaml=clouds.yaml
```

Or install through Krateo with the `CompositionDefinition`: see
[examples/composition](examples/composition/README.md). Full walkthrough:
[docs/usage.md](docs/usage.md).

## Configure

The values are typed by `chart/values.schema.json`. See [docs/configuration.md](docs/configuration.md).

```yaml
restdefinitions:
  volume:
    enabled: true
    resourceGroup: blockstorage.openstack.krateo.io
    resourceKind: Volume
authBridge:
  cloudsSecret: openstack-kog-clouds
  osCloud: openstack
  serviceType: block-storage
  upstreamEndpoint: ""
```

## Project-less URLs: `/v3/volumes`, not `/v3/{project_id}/volumes`

The document's paths are `/volumes` and `/volumes/{volume_id}`, relative to the block-storage endpoint,
and that endpoint is the v3 root with **no project id**. Chosen on purpose:

- **Cinder 2026.1 accepts both forms, for every microversion.** Its router registers each resource twice,
  with a `/{project_id}` prefix and without one (cinder stable/2026.1 `cinder/api/v3/router.py`
  `ProjectMapper.resource` L57-97, and `cinder/api/openstack/wsgi.py` `create_route` L1289-1307). The
  project comes from the Keystone token either way; a project id in the URL must match it
  (`wsgi.py` L897-901). Microversion 3.67 only announces this. The Block Storage API v3 reference says
  so in its opening note: <https://docs.openstack.org/api-ref/block-storage/v3/> (source:
  `api-ref/source/v3/index.rst`).
- **The blueprint's catalog is project-less.** Its cinder registers `volumev3` at path `/v3`
  (krateo-openstack-blueprint `blueprints/cinder/chart/values.yaml`, `endpoints.volumev3.path.default`).
  The auth-bridge forwards to the catalog URL as it is, so `/volumes` reaches `.../v3/volumes`.
- **The proxy has no project id to add.** It holds a Keystone session, not a project id, and a project id
  in the OpenAPI path would become a spec field on every Volume.
- **The readiness probe needs it.** The probe is `GET /` through the proxy, which Cinder answers with
  its v3 version document only at the v3 root.

`values.schema.json` refuses an `upstreamEndpoint` that does not end in `/v3`. A cloud whose catalog
carries `/v3/<project_id>` still works for the API calls, but set `upstreamEndpoint` to its `/v3` root
so the readiness probe passes.

## Examples

- [examples/composition](examples/composition/README.md): install the KOG through its
  CompositionDefinition, with the blueprint's credentials.
- [examples/bootable-volume](examples/bootable-volume/README.md): a bootable Volume from a Glance
  image and an empty data Volume, the shape of #308's run B.
- `chart/samples/volume-resources.yaml`: ready-to-edit CRs.

## Docs

- [docs/index.md](docs/index.md): the map of the bundle
- [docs/overview.md](docs/overview.md): how it works and why it is shaped this way
- [docs/usage.md](docs/usage.md): install and drive it
- [docs/configuration.md](docs/configuration.md): every value
- [docs/api.md](docs/api.md): the generated CRDs
- [docs/examples.md](docs/examples.md): the examples
- [docs/release.md](docs/release.md): how a release ships
- [docs/log.md](docs/log.md): history
- [docs/llms.txt](docs/llms.txt): the LLM index

## Develop & release

`lint.yaml` runs on every pull request and push to `main`: the shared `pinned-uses`,
`repository-standard` and `lint-docs` checks, `helm lint` and `helm template`, the `hack/` gates
(block-style YAML, the create response carries the get id, status fields, findby identifiers, the release
hook), and a render through oasgen-provider's own generator at two versions. `security.yml` and
`preflight-refs.yaml` run beside it. [hack/README.md](hack/README.md) lists the gates.

A plain `X.Y.Z` tag releases through the shared `release-oci` 2.1.0, index channel `blueprints`. Bump
`examples/composition/composition.yaml` to the new version first: the release refuses it otherwise.
See [docs/release.md](docs/release.md). To test a commit before its tag, `prerelease.yaml` pushes
`X.Y.Z-main.g<sha7>` to GHCR only, with the stamped CompositionDefinition and examples as a run artifact
([docs/release.md](docs/release.md), "Pre-releases").

## License

Apache-2.0. See [LICENSE](LICENSE).
