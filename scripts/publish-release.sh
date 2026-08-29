#!/usr/bin/env bash
#
# publish-release.sh
#
# Publish a new pygeoweaver version to GitHub Releases + PyPI.
#
# Creating a GitHub release triggers `.github/workflows/publish-to-pypi.yml`,
# which builds the package and uploads it to PyPI (needs PYPI_API_TOKEN secret).
#
# Typical use after merging to main:
#   ./scripts/publish-release.sh 1.4.0 --bump
#   ./scripts/publish-release.sh 1.4.0 --bump --dry-run
#   ./scripts/publish-release.sh --bump-patch --bump   # auto next patch from pyproject
#   ./scripts/publish-release.sh 1.4.0 --skip-wait    # create release only
#
# Requirements: git, gh (authenticated), python3, curl
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORKFLOW_FILE="publish-to-pypi.yml"
PYPI_JSON_URL="https://pypi.org/pypi/pygeoweaver/json"
DRY_RUN=0
DO_BUMP=0
SKIP_WAIT=0
ALLOW_DIRTY=0
TARGET_BRANCH="main"
VERSION_ARG=""
AUTO_BUMP=""  # patch|minor|major
YES=0

usage() {
  cat <<'EOF'
Usage: ./scripts/publish-release.sh [VERSION] [options]

  VERSION             e.g. 1.4.0 (default: version in pyproject.toml)
                      Or omit VERSION and use --bump-patch / --bump-minor / --bump-major

Options:
  --bump              Write VERSION into pyproject.toml, commit, and push to --branch
  --bump-patch        Compute next patch version from pyproject.toml (e.g. 1.4.0 -> 1.4.1)
  --bump-minor        Compute next minor version (e.g. 1.4.0 -> 1.5.0)
  --bump-major        Compute next major version (e.g. 1.4.0 -> 2.0.0)
  --branch NAME       Release target branch (default: main)
  --allow-dirty       Allow unrelated local changes (still commits only pyproject.toml on --bump)
  --skip-wait         Create the GitHub release only; do not wait for PyPI workflow
  --yes               Skip interactive confirmation
  --dry-run           Print actions only
  -h, --help          Show help

What this does:
  1. Optionally bump pyproject.toml [project].version
  2. Push to the target branch
  3. Create GitHub release tag vVERSION (triggers PyPI publish workflow)
  4. Wait for the workflow and verify the version on PyPI
EOF
}

log() { printf '==> %s\n' "$*" >&2; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run]' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump) DO_BUMP=1; shift ;;
    --bump-patch) AUTO_BUMP="patch"; shift ;;
    --bump-minor) AUTO_BUMP="minor"; shift ;;
    --bump-major) AUTO_BUMP="major"; shift ;;
    --branch) TARGET_BRANCH="${2:?}"; shift 2 ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --skip-wait) SKIP_WAIT=1; shift ;;
    --yes|-y) YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      [[ -z "$VERSION_ARG" ]] || die "Unexpected extra argument: $1"
      VERSION_ARG="$1"
      shift
      ;;
  esac
done

command -v gh >/dev/null || die "gh CLI is required (https://cli.github.com/)"
command -v git >/dev/null || die "git is required"
command -v python3 >/dev/null || die "python3 is required"
command -v curl >/dev/null || die "curl is required"
if [[ "$DRY_RUN" -eq 0 ]]; then
  gh auth status >/dev/null 2>&1 || die "Run: gh auth login"
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
if [[ -z "$REPO" ]]; then
  REPO="$(git remote get-url origin 2>/dev/null | sed -E 's#.*github.com[:/](.+)(\.git)?$#\1#' | sed 's#\.git$##')"
fi
[[ -n "$REPO" ]] || die "Not inside a GitHub repo / gh cannot resolve remote"

read_pyproject_version() {
  python3 - <<'PY'
from pathlib import Path
import re
text = Path("pyproject.toml").read_text()
m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
if not m:
    raise SystemExit("Could not parse version from pyproject.toml")
print(m.group(1))
PY
}

normalize_version() {
  local v="$1"
  v="${v#v}"
  [[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] || die "Invalid version: $1"
  printf '%s' "$v"
}

compute_auto_version() {
  local current="$1"
  local kind="$2"
  python3 - "$current" "$kind" <<'PY'
import sys
cur, kind = sys.argv[1], sys.argv[2]
base = cur.split("-", 1)[0].split("+", 1)[0]
parts = base.split(".")
if len(parts) < 3:
    raise SystemExit(f"Need X.Y.Z version, got: {cur}")
major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
if kind == "patch":
    patch += 1
elif kind == "minor":
    minor += 1
    patch = 0
elif kind == "major":
    major += 1
    minor = 0
    patch = 0
else:
    raise SystemExit(f"Unknown bump kind: {kind}")
print(f"{major}.{minor}.{patch}")
PY
}

bump_pyproject_version() {
  local ver="$1"
  python3 - "$ver" <<'PY'
from pathlib import Path
import re
import sys

ver = sys.argv[1]
path = Path("pyproject.toml")
text = path.read_text()
new, n = re.subn(
    r'(?m)^(version\s*=\s*")[^"]+(")',
    rf"\g<1>{ver}\2",
    text,
    count=1,
)
if n != 1:
    raise SystemExit("Failed to update version in pyproject.toml")
path.write_text(new)
print(f"Updated pyproject.toml version to {ver}")
PY
}

assert_clean_enough() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  local dirty
  dirty="$(git status --porcelain)"
  if [[ -z "$dirty" ]]; then
    return 0
  fi
  if [[ "$ALLOW_DIRTY" -eq 1 ]]; then
    warn "Working tree is dirty (--allow-dirty set):"
    printf '%s\n' "$dirty" >&2
    return 0
  fi
  # Allow only pyproject.toml dirty when we are about to bump it.
  if [[ "$DO_BUMP" -eq 1 ]]; then
    local other
    other="$(printf '%s\n' "$dirty" | awk '{print $NF}' | grep -v '^pyproject.toml$' || true)"
    if [[ -z "$other" ]]; then
      return 0
    fi
  fi
  die "Working tree has uncommitted changes. Commit/stash them, merge to ${TARGET_BRANCH}, or pass --allow-dirty.

$(git status --short)"
}

ensure_on_target_branch() {
  # Always release from a fast-forward of origin/TARGET_BRANCH — never push a
  # feature-branch tip onto main (non-fast-forward / rewrite risk).
  run git fetch origin "$TARGET_BRANCH" --tags >/dev/null 2>&1 || true

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] would checkout and update ${TARGET_BRANCH} from origin"
    return 0
  fi

  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$current_branch" != "$TARGET_BRANCH" ]]; then
    warn "Checking out '${TARGET_BRANCH}' (was on '${current_branch}') for release."
    if git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH}"; then
      git checkout "$TARGET_BRANCH"
    else
      git checkout -B "$TARGET_BRANCH" "origin/${TARGET_BRANCH}"
    fi
  fi

  git pull --ff-only "origin" "$TARGET_BRANCH" \
    || die "Could not fast-forward ${TARGET_BRANCH} to origin/${TARGET_BRANCH}. Resolve locally, then re-run."

  # Refresh version after checkout — pyproject may differ from previous branch.
  CURRENT_VERSION="$(read_pyproject_version)"
  if [[ -n "$AUTO_BUMP" && -z "$VERSION_ARG" ]]; then
    VERSION="$(normalize_version "$(compute_auto_version "$CURRENT_VERSION" "$AUTO_BUMP")")"
    TAG="v${VERSION}"
    log "Recomputed version on ${TARGET_BRANCH}: $VERSION"
  fi
}

confirm() {
  local msg="$1"
  if [[ "$YES" -eq 1 || "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  printf '%s [y/N] ' "$msg" >&2
  local ans
  read -r ans
  [[ "$ans" == "y" || "$ans" == "Y" || "$ans" == "yes" ]] || die "Aborted"
}

create_github_release() {
  local ver="$1"
  local tag="v${ver}"

  if gh release view "$tag" >/dev/null 2>&1; then
    die "GitHub release already exists: $tag"
  fi
  if git ls-remote --tags origin "refs/tags/${tag}" | grep -q .; then
    die "Git tag already exists on origin: $tag"
  fi

  local notes
  notes="$(cat <<EOF
## PyGeoWeaver ${ver}

Published via \`scripts/publish-release.sh\`.

- PyPI: https://pypi.org/project/pygeoweaver/${ver}/
- Install: \`pip install -U pygeoweaver==${ver}\`

### Java / Geoweaver notes
- Latest Geoweaver (2.2+) needs **Java 17+**
- Unmanaged JDK &lt; 17 → auto-selects Geoweaver **2.1.x** legacy jar
- Managed \`~/jdk\` &lt; 17 → bumps JDK to 17 before start
EOF
)"

  log "Creating GitHub release $tag on branch '$TARGET_BRANCH' (triggers $WORKFLOW_FILE)"
  run gh release create "$tag" \
    --target "$TARGET_BRANCH" \
    --title "v${ver}" \
    --notes "$notes" \
    --latest

  printf '%s\n' "$tag"
}

wait_for_publish_workflow() {
  local tag="$1"
  log "Waiting for workflow '$WORKFLOW_FILE' for release $tag …"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] would wait for Actions run"
    return 0
  fi
  sleep 5

  local run_id="" status="" i
  for i in $(seq 1 60); do
    run_id="$(
      gh run list --workflow "$WORKFLOW_FILE" --limit 20 \
        --json databaseId,headBranch,status,event,displayTitle \
        --jq "map(select(.event == \"release\" and ((.headBranch == \"${tag}\") or (.displayTitle | tostring | contains(\"${tag}\"))))) | .[0].databaseId // empty"
    )"
    if [[ -n "$run_id" ]]; then
      status="$(gh run view "$run_id" --json status,conclusion -q .status)"
      log "Found run $run_id (status=$status)"
      if [[ "$status" == "completed" ]]; then
        local conclusion
        conclusion="$(gh run view "$run_id" --json conclusion -q .conclusion)"
        [[ "$conclusion" == "success" ]] || die "Workflow $run_id concluded: $conclusion
See: https://github.com/${REPO}/actions/runs/${run_id}"
        log "Workflow already completed successfully"
        return 0
      fi
      gh run watch "$run_id" --exit-status
      log "Workflow finished successfully"
      return 0
    fi
    sleep 5
  done

  die "Could not find Actions run for $tag — check https://github.com/${REPO}/actions"
}

wait_for_pypi_version() {
  local ver="$1"
  log "Waiting for PyPI to serve pygeoweaver==${ver} …"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  local i remote
  for i in $(seq 1 60); do
    remote="$(
      curl -fsSL "$PYPI_JSON_URL" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('info',{}).get('version',''))" \
        || true
    )"
    if [[ "$remote" == "$ver" ]]; then
      log "PyPI latest version is ${ver}"
      return 0
    fi
    # Also accept when the version exists even if not "latest" yet (yank/race)
    if curl -fsSL "https://pypi.org/pypi/pygeoweaver/${ver}/json" >/dev/null 2>&1; then
      log "Found https://pypi.org/project/pygeoweaver/${ver}/ (PyPI latest currently: ${remote:-unknown})"
      return 0
    fi
    sleep 10
  done
  die "Timed out waiting for PyPI version ${ver}. Check the publish workflow and https://pypi.org/project/pygeoweaver/"
}

# ----- main -----

CURRENT_VERSION="$(read_pyproject_version)"

if [[ -n "$AUTO_BUMP" ]]; then
  [[ -z "$VERSION_ARG" ]] || die "Pass either VERSION or --bump-${AUTO_BUMP}, not both"
  VERSION="$(normalize_version "$(compute_auto_version "$CURRENT_VERSION" "$AUTO_BUMP")")"
  DO_BUMP=1
elif [[ -n "$VERSION_ARG" ]]; then
  VERSION="$(normalize_version "$VERSION_ARG")"
else
  VERSION="$(normalize_version "$CURRENT_VERSION")"
fi

TAG="v${VERSION}"

log "Repository: $REPO"
log "Current pyproject version: $CURRENT_VERSION"
log "Release version: $VERSION (tag $TAG)"
log "Target branch: $TARGET_BRANCH"

if [[ "$VERSION" == "$CURRENT_VERSION" && "$DO_BUMP" -eq 0 ]]; then
  log "Using existing pyproject.toml version $VERSION (no --bump)"
elif [[ "$VERSION" == "$CURRENT_VERSION" && "$DO_BUMP" -eq 1 ]]; then
  log "pyproject.toml already at $VERSION; --bump will still commit if needed"
fi

assert_clean_enough
confirm "Publish pygeoweaver ${VERSION} to GitHub + PyPI from branch ${TARGET_BRANCH}?"

ensure_on_target_branch

if [[ "$DO_BUMP" -eq 1 ]]; then
  log "Bumping pyproject.toml to $VERSION on ${TARGET_BRANCH}"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    bump_pyproject_version "$VERSION"
    # Re-read in case bump was a no-op string rewrite
    CURRENT_VERSION="$(read_pyproject_version)"
    git add pyproject.toml
    if git diff --cached --quiet; then
      log "pyproject.toml already at $VERSION (nothing to commit)"
    else
      git commit -m "Release pygeoweaver ${VERSION}"
    fi
    # Only push the current TARGET_BRANCH tip (must be FF to remote).
    if git merge-base --is-ancestor "origin/${TARGET_BRANCH}" HEAD 2>/dev/null \
      || [[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/${TARGET_BRANCH}")" ]]; then
      run git push origin "refs/heads/${TARGET_BRANCH}:${TARGET_BRANCH}"
    else
      die "Local ${TARGET_BRANCH} is not a fast-forward of origin/${TARGET_BRANCH}; refusing to push."
    fi
  else
    log "[dry-run] would bump pyproject.toml, commit, and push ${TARGET_BRANCH}"
  fi
else
  remote_ver="$(
    git show "origin/${TARGET_BRANCH}:pyproject.toml" 2>/dev/null \
      | python3 -c "
import sys, re
text = sys.stdin.read()
m = re.search(r'(?m)^version\s*=\s*\"([^\"]+)\"', text)
print(m.group(1) if m else '')
" || true
  )"
  if [[ -n "$remote_ver" && "$remote_ver" != "$VERSION" ]]; then
    die "origin/${TARGET_BRANCH} has version '$remote_ver', but you asked to release '$VERSION'.
Re-run with --bump, e.g.:
  ./scripts/publish-release.sh ${VERSION} --bump
Or merge the version bump to ${TARGET_BRANCH} first."
  fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  cat <<EOF >&2

[dry-run] Planned next steps:
  1. Create GitHub release ${TAG} targeting ${TARGET_BRANCH}
  2. Wait for workflow ${WORKFLOW_FILE}
  3. Verify PyPI https://pypi.org/project/pygeoweaver/${VERSION}/
EOF
  exit 0
fi

create_github_release "$VERSION" >/dev/null
log "Created release: https://github.com/${REPO}/releases/tag/${TAG}"

if [[ "$SKIP_WAIT" -eq 1 ]]; then
  warn "--skip-wait set. Monitor: https://github.com/${REPO}/actions"
  warn "PyPI page: https://pypi.org/project/pygeoweaver/${VERSION}/"
  exit 0
fi

wait_for_publish_workflow "$TAG"
wait_for_pypi_version "$VERSION"

cat <<EOF

PyGeoWeaver ${VERSION} published.

GitHub release:
  https://github.com/${REPO}/releases/tag/${TAG}

PyPI:
  https://pypi.org/project/pygeoweaver/${VERSION}/

Install:
  pip install -U pygeoweaver==${VERSION}
EOF
