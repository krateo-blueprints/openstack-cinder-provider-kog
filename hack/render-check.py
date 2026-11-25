#!/usr/bin/env python3
"""Render every RestDefinition through oasgen-provider's own generator and check the CRDs it makes.

oasgen-render ships in the oasgen-provider image (/bin/oasgen-render) and runs the controller's
generation code without a cluster. Feeding it the chart's RestDefinitions and their OpenAPI documents
gives the CRDs a cluster would get. Adapted from krateo-blueprints/azuredevops-provider-kog's
hack/render-check.py (the reference repository).

It fails on:
  1. any generation ERROR (severity "error": the controller would apply nothing);
  2. a RestDefinition with no CRD, or a CRD whose Kind is not the RestDefinition's;
  3. a CRD that does not have the spec property each verb's request body needs. For an enveloped
     API (Cinder wraps bodies in `volume`), the generated spec must hold that envelope as an object
     with properties: this is where a Kind colliding with the envelope's property name showed up on
     nova-kog (an empty-type node the apiserver rejects);
  4. a status field the RestDefinition declares that the generated status schema lacks;
  5. no VolumeConfiguration-style CRD for a document that declares a security scheme.

Warnings are printed, not fatal.

Usage: hack/render-check.py <rendered-chart.yaml> <render-url>
  rendered-chart.yaml   `helm template` output of the chart (with CHART_VERSION substituted)
  render-url            e.g. http://localhost:8081/render
Exit 1 on any failure, or when the render holds no RestDefinition (a gate with no input must fail).
"""
import json
import re
import sys
import urllib.request

import yaml


def schema_at(node, dotted):
    """Walk a CRD openAPIV3Schema node along a dotted path. Returns the node or None."""
    cur = node
    for seg in dotted.split("."):
        props = (cur or {}).get("properties") or {}
        if seg not in props:
            return None
        cur = props[seg]
    return cur


def main(rendered, url):
    docs = [d for d in yaml.safe_load_all(open(rendered)) if d]
    rds = [d for d in docs if d.get("kind") == "RestDefinition"]
    if not rds:
        print("FAIL: no RestDefinition in %s -- nothing was checked" % rendered)
        return 1
    cms = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "ConfigMap"}
    oas = {}
    for rd in rds:
        path = rd["spec"]["oasPath"]
        m = re.fullmatch(r"configmap://([^/]+)/([^/]+)/(.+)", path)
        if not m:
            print("FAIL: %s: oasPath %s is not a configmap:// path" % (rd["metadata"]["name"], path))
            return 1
        _, name, key = m.groups()
        cm = cms.get(name)
        if not cm or key not in cm.get("data", {}):
            print("FAIL: %s: %s has no matching ConfigMap/key in the render" % (rd["metadata"]["name"], path))
            return 1
        oas[path] = cm["data"][key]

    req = json.dumps({"restDefinitions": rds, "oas": oas}).encode()
    request = urllib.request.Request(url, data=req, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as r:
        res = json.load(r)

    failures = []
    for e in res.get("errors") or []:
        line = "%s: %s: %s" % (e.get("restDefinition"), e.get("field", ""), e.get("message"))
        if e.get("severity") == "error":
            failures.append("generation error: " + line)
        else:
            print("warning:", line)
    for s in res.get("skippedSecuritySchemes") or []:
        print("info: %s: skipped security scheme %s" % (s.get("restDefinition"), s.get("scheme")))

    crds = {c["spec"]["names"]["kind"]: c for c in res.get("crds") or []}
    ccrds = {c["spec"]["names"]["kind"]: c for c in res.get("configurationCrds") or []}
    for rd in rds:
        res_ = rd["spec"]["resource"]
        kind = res_["kind"]
        crd = crds.get(kind)
        if not crd:
            failures.append("%s: no CRD rendered (kinds rendered: %s)" % (kind, sorted(crds)))
            continue
        doc = yaml.safe_load(oas[rd["spec"]["oasPath"]])
        for v in crd["spec"]["versions"]:
            root = v["schema"]["openAPIV3Schema"]
            spec = schema_at(root, "spec")
            status = schema_at(root, "status")
            print("%s %s/%s: spec properties %s" % (kind, crd["spec"]["group"], v["name"],
                                                    sorted((spec or {}).get("properties", {}))))
            # 3. every top-level property of every verb's request body is an object spec field with
            #    properties of its own when the document says it is one.
            for verb in res_.get("verbsDescription", []):
                op = doc["paths"][verb["path"]][verb["method"].lower()]
                body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema")
                if not body:
                    continue
                while "$ref" in body:
                    body = doc["components"]["schemas"][body["$ref"].rsplit("/", 1)[1]]
                for prop, sch in (body.get("properties") or {}).items():
                    got = schema_at(root, "spec." + prop)
                    if got is None:
                        failures.append("%s %s: spec.%s (the %s body) is missing" % (kind, v["name"], prop, verb["action"]))
                        continue
                    while "$ref" in sch:
                        sch = doc["components"]["schemas"][sch["$ref"].rsplit("/", 1)[1]]
                    if sch.get("type") == "object" and (got.get("type") != "object" or not got.get("properties")):
                        failures.append("%s %s: spec.%s is %r, not an object with properties: the Kind may "
                                        "collide with the body's property name" % (kind, v["name"], prop, got))
                    else:
                        print("ok  %s %s: spec.%s is an object with %s" % (kind, v["name"], prop,
                                                                       sorted(got.get("properties", {}))))
            # 4. every declared status field is in the generated status schema.
            for field in list(res_.get("identifiers", [])) + list(res_.get("additionalStatusFields", [])):
                got = schema_at(status, field) if status else None
                if got is None:
                    failures.append("%s %s: status.%s is not in the generated status schema" % (kind, v["name"], field))
                else:
                    print("ok  %s %s: status.%s type=%s nullable=%s" % (kind, v["name"], field, got.get("type"),
                                                                     got.get("nullable", False)))
        # 5. a security scheme means a <Kind>Configuration CRD.
        if (doc.get("components") or {}).get("securitySchemes") and kind + "Configuration" not in ccrds:
            failures.append("%s: the document declares a security scheme but no %sConfiguration CRD was rendered"
                            % (kind, kind))

    print("rendered %d RestDefinition(s) -> %d CRD(s), %d Configuration CRD(s)"
          % (len(rds), len(crds), len(ccrds)))
    for f in failures:
        print("FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
