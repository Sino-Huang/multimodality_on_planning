# F2 ignored profile review reproduction

Run these commands from the repository root. They read the four ignored profiles and the F2 evidence only. No profile has been staged, and no launcher, generator, renderer, verifier, promotion, remote endpoint, or other pilot-facing command is part of this reproduction.

## Confirm ignore provenance and ignored status

```bash
GIT_MASTER=1 git check-ignore -v --no-index \
  data/pddl_instances/gripper/gripper_AP.pddl \
  data/pddl_instances/ferry/ap.pddl \
  data/pddl_instances/elevators/elevators_ap.pddl \
  data/pddl_instances/logistics/logistics_ap.pddl

GIT_MASTER=1 git status --short --ignored --untracked-files=all -- \
  data/pddl_instances/gripper/gripper_AP.pddl \
  data/pddl_instances/ferry/ap.pddl \
  data/pddl_instances/elevators/elevators_ap.pddl \
  data/pddl_instances/logistics/logistics_ap.pddl
```

The first command must report `.gitignore:153:data/` for every path. The second must report each path with the ignored `!!` status.

## Confirm whole-file hashes

```bash
sha256sum \
  data/pddl_instances/gripper/gripper_AP.pddl \
  data/pddl_instances/ferry/ap.pddl \
  data/pddl_instances/elevators/elevators_ap.pddl \
  data/pddl_instances/logistics/logistics_ap.pddl
```

Expected hashes, in command order:

```text
b549b24eb7f5fb699773d7c7f7e369488aa7826822faa049a351cb074918dbc4
9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4
ce32eb2e9edd007aeef9c93fada264202141b4e2b717752a0e5bd793ee9ef813
c9aaa88d16da3c53a3fb4f2b01dfbf507aeda509a92635a877a02ee5bf293f79
```

## Read current contracts without image payloads

```bash
for profile in \
  data/pddl_instances/gripper/gripper_AP.pddl \
  data/pddl_instances/ferry/ap.pddl \
  data/pddl_instances/elevators/elevators_ap.pddl \
  data/pddl_instances/logistics/logistics_ap.pddl
do
  printf '\n### %s\n' "$profile"
  sed '/(:image/,$d' "$profile"
done
```

This stops before the first `(:image` marker, so embedded image bytes aren't printed.

## Confirm image-section hashes

The historical task-2 evidence defines the image suffix as every byte strictly after the first literal `(:image` token.

```bash
for profile in \
  data/pddl_instances/gripper/gripper_AP.pddl \
  data/pddl_instances/ferry/ap.pddl \
  data/pddl_instances/elevators/elevators_ap.pddl \
  data/pddl_instances/logistics/logistics_ap.pddl
do
  match=$(LC_ALL=C rg --byte-offset -m1 -o '\(:image' "$profile")
  offset=${match%%:*}
  tail -c +$((offset + 8)) "$profile" | sha256sum
done
```

Expected hashes, in command order:

```text
9acbc33f9b0719cd4bb2e1f4e469a12d834e823719b180eab95165d0ca53216c
871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355
98eabfd7f6a20104385a146aee971c6331c00514a81254280fc7a1c1f8f39a19
4d7044a096d5c3203214644fc3869e41c99cc1f417614cccc22f9e6873c29fb5
```

## Reproduce the normalized no-index diff

The historical side comes only from the repair entries in `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-2-profile-contracts.json`. The current side normalizes the pre-image contracts recorded in `ignored-profile-contracts.json`. The command excludes image data by diffing these text projections, not raw profiles.

```bash
evidence=.omo/evidence/planimation-pilot-contract-and-render-recovery/f2-remediation/ignored-profile-contracts.json
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
jq -r '.review_projection.historical[]' "$evidence" > "$tmpdir/historical-contracts.txt"
jq -r '.review_projection.current[]' "$evidence" > "$tmpdir/current-contracts.txt"
set +e
GIT_MASTER=1 git -C "$tmpdir" diff --no-index -- \
  historical-contracts.txt \
  current-contracts.txt
rc=$?
set -e
test "$rc" -eq 1
```

Exit `1` is expected because the repairs intentionally changed the normalized contracts. Exit `0` means the expected differences disappeared. Any exit greater than `1` is a failure.

## Focused profile test

This is the focused non-pilot regression command. It isn't run as part of the read-only evidence reproduction described above.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_planimation_profile_regressions.py
```

## Assert no staged changes

```bash
GIT_MASTER=1 git diff --staged --quiet
```

The staged-state assertion must exit `0`. None of the four ignored profiles is staged or made reviewable by staging.
