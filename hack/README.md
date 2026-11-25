# hack/

CI gates and the release hook. `.github/workflows/lint.yaml` runs every gate on each pull request and
push to `main`. Each gate fails on an empty input, and each one that can bite is shown biting in the
same run.

| Script | What it refuses | Origin |
|---|---|---|
| `validate-create-returns-get-id.py` | a get, delete, update or findby parameter read from `status.<P>` when `P` is not a status field, or when any success response of the create lacks `P`. It then removes each `P` from the real create response and requires a refusal. | new here; the orphan shape nova-kog measured at oasgen 0.74.0 |
| `check-yaml-block-style.py` | inline `{ }` or `[ ]` in committed YAML, in the chart's render, in the OpenAPI asset, and in docs' yaml blocks | new here |
| `validate-status-fields.py` | an identifier or additionalStatusField the observe response cannot carry | openstack-glance-operator-kog `1b3ab13`, unchanged |
| `validate-findby-identifiers.py` | a findby that cannot match, and a spec-addressed get that cannot say "absent". Volume has no findby; it runs for the kind that gains one. It reads the oasgen-provider minimum from the README. | openstack-glance-operator-kog `1b3ab13`, unchanged |
| `render-check.py` | a generation error from oasgen-render, a missing CRD, a request envelope that is not an object in the spec (the Kind/property collision nova-kog met), a declared status field missing from the generated status | adapted from azuredevops-provider-kog |
| `check-retracted.py` | rendering against an oasgen-provider version its publisher retracted | azuredevops-provider-kog, unchanged |
| `preflight-refs.py` | a chart or image reference that does not resolve anonymously | azuredevops-provider-kog, unchanged |
| `release-preflight` + `validate-example-versions.py` | a release whose example Composition names another version (PUBLISHING.md rule 12) | openstack-neutron-operator-kog `9804a2e`, comments adapted |

The citations in `chart/assets/volume.yaml` say where each field comes from in Cinder. The gates check the
document, not Cinder: that the document is faithful to Cinder is what those citations are for.

Run them locally:

```console
$ export PYTHONDONTWRITEBYTECODE=1
$ cp -R chart /tmp/c && sed -i.bak 's/CHART_VERSION/0.0.0-ci/g' /tmp/c/Chart.yaml
$ python3 hack/validate-create-returns-get-id.py /tmp/c
$ python3 hack/validate-status-fields.py /tmp/c
$ helm template openstack-cinder-provider-kog /tmp/c -n openstack > /tmp/render.yaml
$ python3 hack/check-yaml-block-style.py /tmp/render.yaml .
```

`validate-findby-identifiers.py` walks up from the chart directory to find `README.md`, so run it on a
stamped chart inside the repository, as CI does.
