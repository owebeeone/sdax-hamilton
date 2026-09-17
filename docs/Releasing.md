# Releasing

Releases use the PyPI trusted publisher for `owebeeone/sdax-hamilton`, workflow
`publish.yml`, with no required GitHub environment. No API token is required.

1. Review changes, update `pyproject.toml`, README, release notes and qualification
   records. Before 1.0, breaking API changes use a new minor version; patch versions
   preserve the documented API except for corrections to incorrect behavior.
2. Commit and push the release candidate on `main`. In a GWZ workspace, use GWZ
   with the `sdax-hamilton` target for staging, committing and pushing.
3. Require both the Tests and Release artifacts workflows to pass. The latter
   builds an sdist, builds the wheel from that sdist, checks distribution metadata,
   and tests the installed wheel on Python 3.11, 3.12 and 3.13. Branch runs and
   manual runs validate artifacts but do not publish.
4. Create and push `v<version>` at that reviewed commit. The tag must exactly match
   the package version. In GWZ use `gwz --target sdax-hamilton tag v<version>` and
   `gwz --target sdax-hamilton tag --push v<version>`.
5. The tag workflow rebuilds and requalifies the release artifacts. A separate
   publishing job downloads those exact artifacts only after every wheel test
   succeeds, then uploads them to PyPI using OIDC and attestations. It neither
   checks out the repository nor runs package build scripts with publishing rights.
6. Verify PyPI artifact hashes against the workflow's distributions artifact,
   install the published version in a clean environment, and smoke-test it.
   Create a GitHub release pointing at the existing tag with the release notes.

Never move a published version tag or overwrite a release. A correction after
publication needs a new version. Publication cannot be fully rehearsed without
uploading; a successful build does not prove the PyPI publisher configuration.

Action dependencies are pinned to reviewed commits. Build and test tooling ranges
are declared in the workflow and package extras; dependency compatibility remains
the exact SDAX/Hamilton pair documented in [Compatibility](Compatibility.md).
