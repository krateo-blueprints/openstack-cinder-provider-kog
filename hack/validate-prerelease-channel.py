#!/usr/bin/env python3
"""A pre-release never reaches the Marketplace index, and a release is never a pre-release version.

    hack/validate-prerelease-channel.py [repo-root]

Adapted from krateo-blueprints/rook-ceph-blueprint hack/validate-prerelease-channel.py at 2f4ce94.

prerelease.yaml publishes a commit's chart to GHCR at X.Y.Z-main.g<sha7>, with the stamped CompositionDefinition and
examples as a run artifact, so a live test (krateo-openstack-blueprint #308 run B) installs a commit through its
CompositionDefinition before any tag. That is safe only while these hold, and each is a one-line edit away from
breaking, so each is checked on every pull request:

  1. THE PRE-RELEASE CANNOT WRITE THE INDEX, A RELEASE OR A TAG. prerelease.yaml: triggered by workflow_dispatch only,
     with a required `ref` input; permissions exactly `contents: read` and `packages: write`, with no job-level
     override; no reusable workflow called; no secret but GITHUB_TOKEN; only the checkout (keeping no credential),
     Helm and upload-artifact actions and the organisation's chart-push action pinned by commit
     (krateo-platformops/.github, charts PUBLISHING.md rule 14); no step that writes the index, pushes git, tags or
     creates a release. No workflow calls krateo-blueprints/charts publish-chart.yaml directly, and none but
     release-oci.yaml calls the shared release-oci (which is what indexes).
  2. IT PUBLISHES A PRE-RELEASE, STAMPED AND AGREEING. It derives its version with hack/release-version.sh, checks the
     pre-release shape before the step that stamps and pushes, and inside that step before it runs
     `bash "${CHART_PUSH}"`, the push.sh of an earlier chart-push step; it stamps CHART_VERSION in chart/Chart.yaml and
     compositiondefinition.yaml; it restamps examples/composition to the served apiVersion and checks that the
     CompositionDefinition's version serves exactly that; it uploads the artifact.
  3. THE SHAPES ARE RIGHT. hack/release-version.sh `check` accepts and refuses a table of versions per channel; `derive`
     runs in a throwaway git repository: a commit on main gets -main.g<sha7>, one off it -dev.g<sha7>; the base comes
     from examples/composition; a base not newer than the newest tag is refused; a missing origin/main is refused,
     never taken for "dev". hack/release-preflight refuses a pre-release version for its shape.
  4. THE CHECKS FIRE. The table runs against copies of release-version.sh with each pattern loosened, and the
     workflow checks against mutated copies of prerelease.yaml; a mutation not caught fails the gate.

(The SHA pinning of every `uses:` is the shared pinned-uses check, over every workflow.)

Fails when PyYAML or git is missing, and when a file it needs is missing.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("FAILED MEASUREMENT: PyYAML unavailable, so nothing was read")
    sys.exit(2)

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
WF = os.path.join(ROOT, ".github", "workflows")
PRE = os.path.join(WF, "prerelease.yaml")
RV = os.path.join(ROOT, "hack", "release-version.sh")
PUBLISHER = "krateo-blueprints/charts/.github/workflows/publish-chart.yaml"
ALLOWED_ACTIONS = ("actions/checkout@", "azure/setup-helm@", "actions/upload-artifact@")
RELEASE_OCI = "krateo-platformops/.github/.github/workflows/release-oci.yaml"
# The one chart push (charts PUBLISHING.md rule 14): allowed only pinned to a commit.
CHART_PUSH_ACTION = re.compile(r"^krateo-platformops/\.github/\.github/actions/chart-push@[0-9a-f]{40}$")
PUSH_CALL = 'bash "${CHART_PUSH}"'
FORBIDDEN = ("publish-chart", "krateo-blueprints.github.io/charts", "gh-pages", "gh release", "git tag", "git push",
             "CHARTS_PUBLISH_TOKEN", "/releases/", "releases/download", "release-oci", "index_channel",
             "charts_publish_token", "/git/refs")


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


for need in (PRE, RV, os.path.join(ROOT, "hack", "release-preflight")):
    if not os.path.isfile(need):
        measurement_failed("%s is missing" % os.path.relpath(need, ROOT))
if shutil.which("git") is None:
    measurement_failed("git not on PATH, so derive cannot be run")

failures = []


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def workflow_problems(text):
    """Every reason prerelease.yaml (as text) breaks parts 1 and 2. Empty: it holds."""
    out = []
    try:
        wf = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return ["does not parse: %s" % e]
    on = wf.get("on", wf.get(True))
    if not isinstance(on, dict) or set(on) != {"workflow_dispatch"}:
        out.append("triggers %s; only workflow_dispatch is allowed" % (sorted(on) if isinstance(on, dict) else on))
    else:
        ref = ((on.get("workflow_dispatch") or {}).get("inputs") or {}).get("ref") or {}
        if not ref.get("required"):
            out.append("has no required `ref` input")
    if wf.get("permissions") != {"contents": "read", "packages": "write"}:
        out.append("permissions %s, want exactly contents: read and packages: write" % wf.get("permissions"))
    jobs = wf.get("jobs") or {}
    if not jobs:
        out.append("has no job")
    for name, job in jobs.items():
        if "permissions" in job:
            out.append("job %s overrides permissions" % name)
        if "uses" in job:
            out.append("job %s calls a reusable workflow (%s)" % (name, job["uses"]))
    for s in strings(wf):
        for m in re.finditer(r"secrets\.([A-Za-z0-9_]+)", s):
            if m.group(1) != "GITHUB_TOKEN":
                out.append("references secrets.%s; only GITHUB_TOKEN is allowed" % m.group(1))
        for f in FORBIDDEN:
            if f in s:
                out.append("contains %r, which writes the index, git or a release" % f)
    steps = [st for job in jobs.values() for st in job.get("steps") or []]
    for st in steps:
        if str(st.get("uses") or "").startswith("actions/checkout@") and \
                (st.get("with") or {}).get("persist-credentials") is not False:
            out.append("checks out with persist-credentials not false, leaving a token in .git for a later step")
        u = st.get("uses")
        if u and not u.startswith(ALLOWED_ACTIONS) and not CHART_PUSH_ACTION.match(u):
            out.append("uses %s; only checkout, setup-helm, upload-artifact and chart-push pinned by commit are allowed" % u)
    locators = [i for i, st in enumerate(steps) if CHART_PUSH_ACTION.match(str(st.get("uses") or "")) and st.get("id")]
    runs = [str(st.get("run") or "") for st in steps]
    derive = [i for i, r in enumerate(runs) if "hack/release-version.sh derive" in r]
    checks = [i for i, r in enumerate(runs) if "hack/release-version.sh check prerelease" in r]
    pushes = [i for i, r in enumerate(runs) if PUSH_CALL in r]
    if not derive:
        out.append("never derives its version with hack/release-version.sh derive")
    if not pushes:
        out.append("never pushes a chart")
    for i in pushes:
        r = runs[i]
        want = ["${{ steps.%s.outputs.path }}" % steps[k]["id"] for k in locators if k < i]
        if str((steps[i].get("env") or {}).get("CHART_PUSH")) not in want:
            out.append("step %d runs ${CHART_PUSH} without CHART_PUSH set from an earlier chart-push step's path output" % i)
        if not any(c < i for c in checks) or "check prerelease" not in r \
                or r.index("check prerelease") > r.index(PUSH_CALL):
            out.append("step %d pushes without checking the pre-release shape first, in an earlier step and in the step "
                       "itself" % i)
        if not re.search(r"CHART_VERSION/\$\{VERSION\}/g\"? chart/Chart\.yaml compositiondefinition\.yaml", r):
            out.append("step %d does not stamp CHART_VERSION in chart/Chart.yaml and compositiondefinition.yaml" % i)
    # The restamp itself: a sed that rewrites the composition.krateo.io apiVersion to ${SERVED}, in a step that loops
    # over examples/composition. A step that only greps for ${SERVED} afterwards is not one.
    restamp = [i for i, r in enumerate(runs) if "examples/composition/*.yaml" in r and re.search(
        r'sed -E "s#\^apiVersion: composition\\\.krateo\\\.io/v[^#]*#apiVersion: \$\{SERVED\}#"', r)]
    agree = [i for i, r in enumerate(runs) if 'composition.krateo.io/v${cd_version//./-}" = "${SERVED}"' in r]
    if not restamp:
        out.append("never restamps examples/composition to the served apiVersion ${SERVED}")
    if not agree:
        out.append("never checks that the stamped CompositionDefinition's version serves ${SERVED}")
    uploads = [i for i, st in enumerate(steps) if str(st.get("uses", "")).startswith("actions/upload-artifact@")]
    if uploads and (restamp + agree) and max(restamp + agree) > min(uploads):
        out.append("uploads the artifact before the examples are restamped and checked")
    if not any(str(st.get("uses", "")).startswith("actions/upload-artifact@") for st in steps):
        out.append("uploads no artifact, so the stamped CompositionDefinitions and examples are nowhere")
    return out


# --- 1 and 2 -------------------------------------------------------------------------------------------------------
pre_text = open(PRE).read()
for p in workflow_problems(pre_text):
    failures.append("1/2: prerelease.yaml " + p)
for fn in sorted(os.listdir(WF)):
    if not fn.endswith((".yaml", ".yml")):
        continue
    text = open(os.path.join(WF, fn)).read()
    if PUBLISHER in text:
        failures.append("1: %s calls %s; only the shared release-oci may, from release-oci.yaml" % (fn, PUBLISHER))
    if fn != "release-oci.yaml" and RELEASE_OCI in text:
        failures.append("1: %s calls %s; only release-oci.yaml may" % (fn, RELEASE_OCI))

# --- 3 -------------------------------------------------------------------------------------------------------------
TABLE = [
    ("release", "0.1.0", True), ("release", "10.20.30", True),
    ("release", "0.1.0-main.gabc1234", False), ("release", "v0.1.0", False), ("release", "0.1", False),
    ("release", "01.1.0", False), ("release", "0.1.0 ", False),
    ("prerelease", "0.1.0-main.gabc1234", True), ("prerelease", "0.1.0-dev.g0123456", True),
    ("prerelease", "0.1.0", False), ("prerelease", "0.1.0-main.abc1234", False),
    ("prerelease", "0.1.0-main.gabc123", False), ("prerelease", "0.1.0-main.gabc12345", False),
    ("prerelease", "0.1.0-feature.gabc1234", False), ("prerelease", "0.1.0-main.gABC1234", False),
    ("prerelease", "v0.1.0-main.gabc1234", False), ("prerelease", "0.1.0-main.gabc1234x", False),
]


def table_misses(script):
    miss = []
    for channel, version, ok in TABLE:
        r = subprocess.run(["bash", script, "check", channel, version], capture_output=True, text=True)
        if (r.returncode == 0) != ok:
            miss.append("check %s %r %s" % (channel, version, "refused" if ok else "accepted"))
    return miss


for m in table_misses(RV):
    failures.append("3: hack/release-version.sh " + m)


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=gate", "-c", "user.email=gate@example.invalid", *a], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def derive_cases():
    """[(label, ok, stdout, stderr)] of derive in a throwaway repository with this tree's examples and blueprints."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "r")
        os.makedirs(os.path.join(repo, "hack"))
        shutil.copy(RV, os.path.join(repo, "hack", "release-version.sh"))
        shutil.copytree(os.path.join(ROOT, "examples"), os.path.join(repo, "examples"))
        shutil.copy(os.path.join(ROOT, "compositiondefinition.yaml"), repo)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "one")
        main_sha = git(repo, "rev-parse", "HEAD")

        def run(*a):
            r = subprocess.run(["bash", "hack/release-version.sh", "derive", *a], cwd=repo, capture_output=True, text=True)
            return r.returncode, r.stdout.strip(), r.stderr.strip()

        out.append(("no origin/main", *run(main_sha)))
        git(repo, "update-ref", "refs/remotes/origin/main", main_sha)
        out.append(("on main", *run(main_sha)))
        git(repo, "checkout", "-q", "-b", "topic")
        open(os.path.join(repo, "x"), "w").write("x")
        git(repo, "add", "x")
        git(repo, "commit", "-q", "-m", "two")
        out.append(("off main", *run(git(repo, "rev-parse", "HEAD"))))
        out.append(("explicit base", *run(main_sha, "0.2.0")))
        served = re.search(r"composition\.krateo\.io/v(\d+)-(\d+)-(\d+)",
                           open(sorted(os.path.join(repo, "examples", "composition", f) for f in
                                       os.listdir(os.path.join(repo, "examples", "composition")) if f.endswith(".yaml"))[0]
                                ).read())
        base = ".".join(served.groups())
        git(repo, "tag", base, main_sha)
        out.append(("base already tagged", *run(main_sha)))
        return main_sha, base, out


main_sha, base, cases = derive_cases()
want = {
    "no origin/main": (False, None),
    "on main": (True, "%s-main.g%s" % (base, main_sha[:7])),
    "off main": (True, r"%s-dev\.g[0-9a-f]{7}" % re.escape(base)),
    "explicit base": (True, "0.2.0-main.g%s" % main_sha[:7]),
    "base already tagged": (False, None),
}
for label, rc, outp, err in cases:
    ok, pattern = want[label]
    if ok and (rc != 0 or not re.fullmatch(pattern if label == "off main" else re.escape(pattern), outp)):
        failures.append("3: derive (%s) gives %r (rc %d, %s), want %s" % (label, outp, rc, err[-120:], pattern))
    if not ok and rc == 0:
        failures.append("3: derive (%s) succeeds with %r; it must refuse" % (label, outp))
r = subprocess.run([os.path.join(ROOT, "hack", "release-preflight"), "%s-main.g%s" % (base, main_sha[:7])],
                   capture_output=True, text=True, cwd=ROOT)
# The refusal must be the shape check's, not a side effect: a pre-release version also fails the examples comparison.
if r.returncode == 0 or "must be plain X.Y.Z" not in r.stdout + r.stderr:
    failures.append("3: hack/release-preflight does not refuse a pre-release version for its shape (rc %d); a tag must "
                    "never release one" % r.returncode)

# --- 4 -------------------------------------------------------------------------------------------------------------
LOOSEN = [
    ("PRERELEASE_RE end anchor", r'-(main|dev)\.g[0-9a-f]{7}\$"', r'-(main|dev)\.g[0-9a-f]{7}"'),
    ("any pre-release label", "(main|dev)", "[a-z]+"),
    ("any sha length", "g[0-9a-f]{7}", "g[0-9a-f]+"),
    ("RELEASE_RE end anchor", 'RELEASE_RE="^${CORE}\\$"', 'RELEASE_RE="^${CORE}"'),
    ("leading zeros", "(0|[1-9][0-9]*)", "[0-9]+"),
]
src = open(RV).read()
with tempfile.TemporaryDirectory() as tmp:
    for label, a, b in LOOSEN:
        if a not in src:
            failures.append("4: cannot loosen %s: %r is not in hack/release-version.sh" % (label, a))
            continue
        p = os.path.join(tmp, "rv.sh")
        open(p, "w").write(src.replace(a, b))
        if not table_misses(p):
            failures.append("4: the table does not notice hack/release-version.sh with %s loosened" % label)

MUTATE = [
    ("contents: write", "permissions:\n  contents: read\n  packages: write\n",
     "permissions:\n  contents: write\n  packages: write\n"),
    ("an extra permission", "permissions:\n  contents: read\n  packages: write\n",
     "permissions:\n  contents: read\n  packages: write\n  id-token: write\n"),
    ("a missing packages: write", "permissions:\n  contents: read\n  packages: write\n",
     "permissions:\n  contents: read\n"),
    ("a push trigger", "on:\n  workflow_dispatch:\n", "on:\n  push:\n    branches:\n      - main\n  workflow_dispatch:\n"),
    ("a tag trigger", "on:\n  workflow_dispatch:\n", "on:\n  push:\n    tags:\n      - '*'\n  workflow_dispatch:\n"),
    ("a job-level permission", "  publish:\n    runs-on: ubuntu-latest\n",
     "  publish:\n    permissions:\n      contents: write\n    runs-on: ubuntu-latest\n"),
    ("a call to the publisher", "jobs:\n",
     "jobs:\n  index:\n    uses: %s@5825f8963e30193120c0460f6c6f31b596bf1ed8 # 1.13.2\n" % PUBLISHER),
    ("a call to release-oci", "jobs:\n",
     "jobs:\n  release:\n    uses: %s@aa90d48e1a101d5e9b3e547bca116b97c49513b5 # 2.1.0\n" % RELEASE_OCI),
    ("the publish token", "          GH_TOKEN: ${{ github.token }}\n",
     "          GH_TOKEN: ${{ github.token }}\n          T: ${{ secrets.CHARTS_PUBLISH_TOKEN }}\n"),
    ("a git tag", '          echo "pre-release ${version} of ${sha}"\n',
     '          echo "pre-release ${version} of ${sha}"\n          git tag "${version}"\n'),
    ("a GitHub release", '          echo "pushed ${OCI_REPO}/${name}:${VERSION}"\n',
     '          echo "pushed ${OCI_REPO}/${name}:${VERSION}"\n          gh release create "${VERSION}" --prerelease\n'),
    ("a tag through the API", '          echo "pushed ${OCI_REPO}/${name}:${VERSION}"\n',
     '          echo "pushed ${OCI_REPO}/${name}:${VERSION}"\n'
     '          gh api "repos/${GITHUB_REPOSITORY}/git/refs" -f ref="refs/tags/${VERSION}" -f sha="${SHA}"\n'),
    ("a gh-pages push", "      - name: Summary\n",
     "      - name: Index\n        run: git push origin HEAD:gh-pages\n      - name: Summary\n"),
    ("a persisted checkout credential", "          fetch-depth: 0\n          persist-credentials: false\n",
     "          fetch-depth: 0\n"),
    ("no shape check before push",
     '          hack/release-version.sh check prerelease "${VERSION}"\n          name=openstack-cinder-provider-kog\n',
     "          name=openstack-cinder-provider-kog\n"),
    ("no stamping", 'sed -i "s/CHART_VERSION/${VERSION}/g" chart/Chart.yaml compositiondefinition.yaml', "true"),
    ("no CompositionDefinition stamping", 'sed -i "s/CHART_VERSION/${VERSION}/g" chart/Chart.yaml compositiondefinition.yaml',
     'sed -i "s/CHART_VERSION/${VERSION}/g" chart/Chart.yaml'),
    ("no example restamp", '            sed -E "s#^apiVersion: composition\\.krateo\\.io/v[0-9]+-[0-9]+-[0-9]+[[:space:]]*\\$#apiVersion: ${SERVED}#" "$f" \\\n',
     '            cat "$f" \\\n'),
    ("no agreement check", '[ "composition.krateo.io/v${cd_version//./-}" = "${SERVED}" ]', "true"),
    ("no artifact", "        uses: actions/upload-artifact@", "        uses: actions/cache@"),
    ("an upload before the restamp", "      - name: Stage the files a live test applies\n",
     "      - name: Early upload\n        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2\n"
     "        with:\n          name: early\n          path: dist/\n"
     "      - name: Stage the files a live test applies\n"),
    # The pin as the workflow has it, whatever commit it names, so a bump of the pin does not break the mutant.
    ("the chart push at @main", (re.search(r"actions/chart-push@[0-9a-f]{40}", pre_text) or re.match("", "")).group(0) or
     "actions/chart-push@<no pinned chart-push in prerelease.yaml>", "actions/chart-push@main"),
    ("CHART_PUSH from nowhere", "          CHART_PUSH: ${{ steps.chart-push.outputs.path }}\n",
     "          CHART_PUSH: /tmp/push.sh\n"),
    ("a bare helm push", 'bash "${CHART_PUSH}" "pkg/${name}-${VERSION}.tgz" "${OCI_REPO}"',
     'helm push "pkg/${name}-${VERSION}.tgz" "${OCI_REPO}"'),
    ("a literal version", 'version=$(hack/release-version.sh derive "$sha" "$BASE")', 'version="0.1.0"'),
    ("an optional ref", "        required: true\n        default: main\n", "        required: false\n        default: main\n"),
]
caught = 0
for label, a, b in MUTATE:
    if a not in pre_text:
        failures.append("4: cannot plant %s: its anchor is not in prerelease.yaml" % label)
        continue
    if not workflow_problems(pre_text.replace(a, b, 1)):
        failures.append("4: the workflow check does not notice prerelease.yaml with %s" % label)
    else:
        caught += 1

if failures:
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: prerelease.yaml can publish only a pre-release to GHCR (dispatch only, contents: read + packages: write, no "
      "reusable workflow, no secret but GITHUB_TOKEN, no persisted credential, shape checked before push, stamped, "
      "examples agreeing with the CompositionDefinition, artifact); %d version(s) in "
      "the table; derive measured in 5 cases (%s-main.g<sha7> on main); %d loosened pattern(s) and %d workflow "
      "mutation(s) all caught" % (len(TABLE), base, len(LOOSEN), caught))
