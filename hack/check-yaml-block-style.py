#!/usr/bin/env python3
"""Refuse YAML written in flow style: no inline { } mappings and no inline [ ] sequences.

The house style of the OpenStack blueprint and its KOGs is block style only, and every YAML must be
spec-compliant. A comment saying so is not a check, so this is one.

WHAT IT READS:
  - every committed *.yaml / *.yml file that is plain YAML (chart templates are Go templates, not YAML,
    so they are read through their render instead);
  - the chart's `helm template` output (the rendered file given as the first argument), and every YAML
    document embedded in a rendered ConfigMap's data (the OpenAPI assets);
  - every ```yaml fenced block in every Markdown file.

HOW: PyYAML composes each document and every mapping or sequence node records whether it was written in
flow style. A node with flow_style true is refused, with its file and line. A file that does not parse
is refused too (it is not spec-compliant YAML). Strings that contain braces or brackets are scalars, not
flow nodes, so they pass.

A self-test runs first: a flow mapping, a flow sequence and an empty {} must be refused, a block document
must pass. Exit 1 on any finding, on a self-test failure, or when nothing was read.

Usage: check-yaml-block-style.py <rendered-chart.yaml> [repo-root]
"""
import pathlib
import re
import sys

import yaml

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
FENCE = re.compile(r"^```ya?ml[ \t]*\n(.*?)^```", re.M | re.S)


def flow_nodes(text):
    """Yield (line, kind) for every flow-style collection in every document of text."""
    for doc in yaml.compose_all(text, Loader=yaml.SafeLoader):
        stack = [doc]
        while stack:
            node = stack.pop()
            if node is None:
                continue
            if isinstance(node, (yaml.MappingNode, yaml.SequenceNode)):
                if node.flow_style:
                    kind = "mapping { }" if isinstance(node, yaml.MappingNode) else "sequence [ ]"
                    yield node.start_mark.line + 1, kind
                if isinstance(node, yaml.MappingNode):
                    for k, v in node.value:
                        stack.extend((k, v))
                else:
                    stack.extend(node.value)


def check_text(text, where, findings):
    try:
        for line, kind in flow_nodes(text):
            findings.append("%s:%d: flow-style %s; write it in block style" % (where, line, kind))
    except yaml.YAMLError as e:
        findings.append("%s: does not parse as YAML: %s" % (where, str(e).splitlines()[0]))


def self_test():
    cases = [
        ("a: {b: 1}\n", False),
        ("a: [1, 2]\n", False),
        ("a: {}\n", False),
        ("a:\n  - b\n  - c\nd:\n  e: '{not a flow node}'\n", True),
    ]
    for text, want_ok in cases:
        findings = []
        check_text(text, "selftest", findings)
        if (not findings) != want_ok:
            raise SystemExit("FAIL: self-test on %r: expected %s, got %s -- the detector is broken"
                             % (text, "pass" if want_ok else "a finding", findings or "pass"))
    print("self-test: %d cases behave" % len(cases))


def main(rendered, root):
    self_test()
    root = pathlib.Path(root)
    findings, read = [], 0

    for path in sorted(list(root.rglob("*.yaml")) + list(root.rglob("*.yml"))):
        rel = path.relative_to(root)
        if SKIP_DIRS.intersection(rel.parts):
            continue
        if rel.parts[:2] == ("chart", "templates") or rel.parts[:2] == ("chart", "assets"):
            continue  # Go templates: read through the render below
        check_text(path.read_text(), str(rel), findings)
        read += 1

    rendered_text = pathlib.Path(rendered).read_text()
    check_text(rendered_text, "helm template output", findings)
    read += 1
    for doc in yaml.safe_load_all(rendered_text):
        if doc and doc.get("kind") == "ConfigMap":
            for key, value in (doc.get("data") or {}).items():
                if key.endswith((".yaml", ".yml")):
                    check_text(value, "rendered ConfigMap %s key %s" % (doc["metadata"]["name"], key), findings)
                    read += 1

    for md in sorted(root.rglob("*.md")):
        if SKIP_DIRS.intersection(md.relative_to(root).parts):
            continue
        for i, m in enumerate(FENCE.finditer(md.read_text())):
            check_text(m.group(1), "%s yaml block %d" % (md.relative_to(root), i + 1), findings)
            read += 1

    if read < 2:
        findings.append("read %d YAML source(s): nothing was checked" % read)
    print("checked %d YAML source(s)" % read)
    for f in findings:
        print("FAIL: " + f)
    return 1 if findings else 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else "."))
