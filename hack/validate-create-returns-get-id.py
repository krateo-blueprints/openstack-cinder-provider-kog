#!/usr/bin/env python3
"""Fail if a kind addressed from status could be created without the value that addresses it.

WHY THIS EXISTS. A Volume's get and delete paths take the volume id from status.volume.id. Nothing
writes that status field except the controller, from a response body: rest-dynamic-controller copies
every identifier and additionalStatusField out of the CREATE response (populateStatusFields, 0.80.0
internal/controllers/restResources.go Create) and later out of the get response. A path absent from the
body is skipped without a word. So if a create can succeed with a body that lacks the id, the CR has no
id, the get cannot be built, and on delete nothing reaches the vendor: the volume is orphaned.
nova-kog's owner measured exactly that at oasgen-provider 0.74.0 (rd-volume-attachment.yaml there).

WHAT IT CHECKS, for every rendered RestDefinition. Each request-direction mapping (`fieldMapping` and the
deprecated `requestFieldMapping`, inPath or inQuery) on get, delete, update or findby whose source is
`status.<P>` is one case. For each case:
  1. P is an identifier or an additionalStatusField. Only those are copied into status, so any other
     status path is never written and the call can never be built.
  2. There is a create verb, and EVERY response code it accepts as success carries P in its
     application/json schema. The accepted codes are the 2xx codes the OpenAPI document declares for the
     operation plus the verb's `successCodes`, which is how rest-dynamic-controller builds its success set
     (0.80.0 internal/tools/client/clienttools.go getValidResponseCode; restclient.go merges successCodes).
     A success code with no declared body, or one not declared at all, could carry anything: refused.
     A response-direction fieldMapping on create (inResponse -> status.P) resolves P through its source.

THE GATE MUST BITE. After checking the real chart it removes, one case at a time, P from the create
response schema of the rendered document and requires the check to fail. A self-test on synthetic
definitions runs first. A render with no RestDefinition, or with no status-addressed case at all, fails:
every kind in this repository is addressed from status, so zero cases means the gate read nothing.

The subject is the curated OpenAPI document. That it is faithful to Cinder is what the citations in
chart/assets/*.yaml are for (cinder/api/v3/volumes.py create returns the full volume, id included).

Usage: validate-create-returns-get-id.py [chart-dir]   (default: chart)
"""
import contextlib
import copy
import io
import subprocess
import sys

import yaml

OBSERVE_AND_MUTATE = ("get", "delete", "update", "findby")


def render(chart):
    proc = subprocess.run(["helm", "template", "release", chart, "--namespace", "krateo-system"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit("FAIL: helm template %s failed -- nothing was checked" % chart)
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def resolve(doc, node, depth=0):
    while isinstance(node, dict) and "$ref" in node:
        if depth > 32:
            raise ValueError("$ref chain too deep")
        ref = node["$ref"]
        if not ref.startswith("#/"):
            raise ValueError("only local $refs are supported: %s" % ref)
        cur = doc
        for seg in ref[2:].split("/"):
            cur = cur[seg]
        node = cur
        depth += 1
    return node


def has_path(doc, schema, dotted):
    cur = resolve(doc, schema)
    for seg in dotted.split("."):
        props = (cur or {}).get("properties") or {}
        if seg not in props:
            return False
        cur = resolve(doc, props[seg])
    return True


def request_mappings(verb):
    for key in ("fieldMapping", "requestFieldMapping"):
        for m in verb.get(key) or []:
            if (m.get("inPath") or m.get("inQuery")) and m.get("inCustomResource"):
                yield m


def cases_of(rd):
    """(verb action, parameter, status path) for every request mapping sourced from status."""
    out = []
    for verb in rd["spec"]["resource"].get("verbsDescription") or []:
        if verb.get("action") not in OBSERVE_AND_MUTATE:
            continue
        for m in request_mappings(verb):
            src = m["inCustomResource"]
            if src.startswith("status."):
                out.append((verb["action"], m.get("inPath") or m.get("inQuery"), src[len("status."):]))
    return out


def create_success_schemas(doc, verb):
    """[(code, schema or None)] for every code the controller accepts as success on this create."""
    path_item = (doc.get("paths") or {}).get(verb["path"])
    if path_item is None:
        raise ValueError("create path %s is not in the document" % verb["path"])
    op = path_item.get(verb["method"].lower())
    if op is None:
        raise ValueError("%s %s is not in the document" % (verb["method"], verb["path"]))
    responses = op.get("responses") or {}
    codes = {str(c) for c in responses if str(c).startswith("2")}
    codes |= {str(c) for c in verb.get("successCodes") or []}
    out = []
    for code in sorted(codes):
        resp = responses.get(code, responses.get(int(code)) if code.isdigit() else None)
        if resp is None:
            out.append((code, None))
            continue
        content = (resolve(doc, resp).get("content") or {}).get("application/json") or {}
        out.append((code, resolve(doc, content["schema"]) if "schema" in content else None))
    return out


def check_rd(rd, doc):
    """Returns (failures, number of cases)."""
    name = rd["metadata"]["name"]
    res = rd["spec"]["resource"]
    cases = cases_of(rd)
    failures = []
    if not cases:
        return failures, 0
    declared = set(res.get("identifiers") or []) | set(res.get("additionalStatusFields") or [])
    creates = [v for v in res.get("verbsDescription") or [] if v.get("action") == "create"]
    for action, param, path in cases:
        where = "%s: %s parameter %s from status.%s" % (name, action, param, path)
        if path not in declared:
            failures.append("%s: status.%s is not an identifier or additionalStatusField, so the controller "
                            "never writes it and the %s call can never be built" % (where, path, action))
            continue
        if not creates:
            failures.append("%s: there is no create verb, so nothing ever writes status.%s" % (where, path))
            continue
        create = creates[0]
        source = path
        for m in create.get("fieldMapping") or []:
            if m.get("inResponse") and m.get("inCustomResource") == "status." + path:
                source = m["inResponse"]
        try:
            schemas = create_success_schemas(doc, create)
        except ValueError as e:
            failures.append("%s: %s" % (where, e))
            continue
        if not schemas:
            failures.append("%s: the create declares no success response at all" % where)
        for code, schema in schemas:
            if schema is None:
                failures.append("%s: create success %s has no declared application/json body, so it can answer "
                                "without %s and leave the CR unaddressable" % (where, code, source))
            elif not has_path(doc, schema, source):
                failures.append("%s: the create %s response schema does not carry %s, so a create can succeed "
                                "and leave the CR unaddressable (and the resource orphaned on delete)"
                                % (where, code, source))
            else:
                print("ok    %s: create %s carries %s" % (where, code, source))
    return failures, len(cases)


def oas_of(rd, configmaps):
    _, _, rest = rd["spec"]["oasPath"].partition("configmap://")
    _, cm_name, key = rest.split("/", 2)
    return yaml.safe_load(configmaps[cm_name]["data"][key])


def drop_path(doc, verb, dotted):
    """A copy of doc whose create success schemas lack the leaf of `dotted` (inlined, so the get's
    shared schema is untouched)."""
    doc = copy.deepcopy(doc)
    op = doc["paths"][verb["path"]][verb["method"].lower()]
    for code, resp in list((op.get("responses") or {}).items()):
        if not str(code).startswith("2"):
            continue
        content = (resolve(doc, resp).get("content") or {}).get("application/json")
        if not content or "schema" not in content:
            continue
        inlined = copy.deepcopy(inline(doc, content["schema"]))
        cur = inlined
        segs = dotted.split(".")
        for seg in segs[:-1]:
            cur = cur.get("properties", {}).get(seg, {})
        cur.get("properties", {}).pop(segs[-1], None)
        content["schema"] = inlined
    return doc


def inline(doc, node, depth=0):
    if depth > 32:
        raise ValueError("schema too deep to inline")
    node = resolve(doc, node)
    if isinstance(node, dict):
        return {k: inline(doc, v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [inline(doc, v, depth + 1) for v in node]
    return node


def synthetic(create_responses, ids=("thing.id",), get_source="status.thing.id", success_codes=None,
              create=True):
    item = {"type": "object", "properties": {"id": {"type": "string"}}}
    doc = {
        "paths": {
            "/things": {"post": {"responses": create_responses}},
            "/things/{id}": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {
                "type": "object", "properties": {"thing": item}}}}}}}},
        },
    }
    verbs = []
    if create:
        v = {"action": "create", "method": "POST", "path": "/things"}
        if success_codes:
            v["successCodes"] = success_codes
        verbs.append(v)
    verbs.append({"action": "get", "method": "GET", "path": "/things/{id}",
                  "fieldMapping": [{"inPath": "id", "inCustomResource": get_source}]})
    rd = {"metadata": {"name": "selftest"},
          "spec": {"resource": {"identifiers": list(ids), "verbsDescription": verbs}}}
    return rd, doc


def self_test():
    body = {"content": {"application/json": {"schema": {
        "type": "object", "properties": {"thing": {"type": "object", "properties": {"id": {"type": "string"}}}}}}}}
    no_id = {"content": {"application/json": {"schema": {
        "type": "object", "properties": {"thing": {"type": "object", "properties": {"name": {"type": "string"}}}}}}}}
    cases = [
        ("a 202 carrying the id", synthetic({"202": body}), True),
        ("a 201 without the id", synthetic({"201": no_id}), False),
        ("a 202 with no body", synthetic({"202": {"description": "Accepted"}}), False),
        ("a good 201 plus a bodiless 204", synthetic({"201": body, "204": {"description": "none"}}), False),
        ("a successCode the document does not declare", synthetic({"201": body}, success_codes=[202]), False),
        ("a status path that is not a status field", synthetic({"201": body}, ids=("thing.name",)), False),
        ("no create verb", synthetic({"201": body}, create=False), False),
    ]
    for label, (rd, doc), want_ok in cases:
        with contextlib.redirect_stdout(io.StringIO()):
            failures, n = check_rd(rd, doc)
        if n != 1 or (not failures) != want_ok:
            raise SystemExit("FAIL: self-test %r: expected %s, got %s -- the detector is broken, so a pass "
                             "here would mean nothing" % (label, "pass" if want_ok else "refusal",
                                                          failures or "pass"))
    print("self-test: %d synthetic cases behave" % len(cases))


def main():
    self_test()
    chart = sys.argv[1] if len(sys.argv) > 1 else "chart"
    docs = render(chart)
    configmaps = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "ConfigMap"}
    rds = [d for d in docs if d.get("kind") == "RestDefinition"]
    if not rds:
        print("FAIL: no RestDefinition rendered from %s -- nothing was checked" % chart)
        return 1
    failures, total = [], 0
    bites = 0
    for rd in rds:
        doc = oas_of(rd, configmaps)
        f, n = check_rd(rd, doc)
        failures += f
        total += n
        if f or not n:
            continue
        # The gate must bite on this real definition: without each path in the create response, refuse.
        create = next(v for v in rd["spec"]["resource"]["verbsDescription"] if v["action"] == "create")
        for _, _, path in cases_of(rd):
            with contextlib.redirect_stdout(io.StringIO()):
                bitten, _ = check_rd(rd, drop_path(doc, create, path))
            if not bitten:
                failures.append("%s: with %s removed from the create response the check still passes -- it "
                                "does not bite" % (rd["metadata"]["name"], path))
            else:
                bites += 1
    if total == 0:
        failures.append("no get, delete, update or findby parameter is read from status in %d RestDefinition(s): "
                        "every kind here is addressed from status, so the gate read nothing" % len(rds))
    print("checked %d RestDefinition(s), %d status-addressed parameter(s); the check bit on %d mutation(s)"
          % (len(rds), total, bites))
    for f in failures:
        print("FAIL: " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
