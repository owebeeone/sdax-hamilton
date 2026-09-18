# Releasing

Releases use the PyPI trusted publisher for `owebeeone/sdax-hamilton`, workflow
`publish.yml`, with no required GitHub environment. No API token is required.

1. Review changes and update README, changelog, documentation and the release notes
   in `gearu.toml`. Leave the package version for Gearu to update. Before 1.0,
   breaking API changes use a new minor version; patch versions preserve the
   documented API except for corrections to incorrect behavior.
2. Commit and push preparation changes on `main` using GWZ in this workspace.
   Require the Tests and Release artifacts workflows to pass before proceeding.
3. Read the repository's [Gearu instructions](https://github.com/owebeeone/sdax-hamilton/blob/main/RELEASE.md)
   and inspect `gearu plan VERSION`. It verifies branch/remote state and tag
   immutability without changing tracked files or publishing anything.
4. Run `gearu release VERSION --push --github-release`. Gearu updates the version,
   runs the configured checks in its temporary candidate, creates the local
   release commit and tag, atomically pushes both, and publishes the GitHub
   Release. Gearu owns these release operations; routine workspace changes use GWZ.
5. The GitHub `release.published` event starts package qualification. The workflow
   builds an sdist and its wheel, checks metadata, and tests the installed wheel
   on Python 3.11–3.13 plus all five optional profiles on Python 3.12. Only after
   every wheel job passes does a separate job publish those exact artifacts to
   PyPI using trusted publishing. Branch/manual runs do not upload packages;
   pushing a tag alone does not publish.
6. Verify PyPI artifact hashes against the workflow's distributions artifact,
   install the published version in a clean environment, and smoke-test it.
   Refresh the GWZ root checkpoint to record Gearu's final member commit.

Never move a published version tag or overwrite a release. A correction after
publication needs a new version. Publication cannot be fully rehearsed without
uploading; a successful build does not prove the PyPI publisher configuration.

Action dependencies are pinned to reviewed commits. Build and test tooling ranges
are declared in the workflow and package extras; dependency compatibility remains
the exact SDAX/Hamilton pair documented in [Compatibility](Compatibility.md).

## Documentation site

The public documentation is hosted at
[owebeeone.github.io/sdax-hamilton](https://owebeeone.github.io/sdax-hamilton/)
using MkDocs Material, matching the GWZ documentation layout. It follows `main`
and labels development coverage separately from the published alpha.

To build or preview it locally:

```sh
python -m pip install -r docs-requirements.txt
python -m mkdocs build --strict
python -m mkdocs serve
```

Generated `site/` output is ignored. In this GWZ workspace, place local generated
output outside the repository with `mkdocs build --strict --site-dir <output>`.
Only public files in `docs/` become site pages; design and review records in
`dev-docs/` remain in the repository and are linked where relevant.

The Documentation workflow builds changed docs on pull requests, then publishes
successful builds from `main` to the `github-pages` environment. It can also be
run manually on `main`. Configure the repository's Pages source as **GitHub
Actions**. Publishing documentation does not create a package release or a tag.
