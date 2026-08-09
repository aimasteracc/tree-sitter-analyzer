# NO1-006A complete native qualification evidence

This directory preserves the successful `develop` qualification from
[workflow run 31288611024, attempt 1](https://github.com/aimasteracc/tree-sitter-analyzer/actions/runs/31288611024/attempts/1)
for source commit `c91b026a9a11d044f1f67fda9e060db45aebd7f3`.

Reassemble and verify:

```bash
cat evidence.tar.gz.part-* > evidence.tar.gz
printf "%s  evidence.tar.gz\n" f90c4b124b2b6d570754317d759efb7c51ddf00b253f9e6f1a6380e0a4449ea7 | sha256sum -c -
tar -xzf evidence.tar.gz
```

The archive contains the exact built wheel, package/MCP reports and sidecars for
all three native axes, the exact package and outdated-uv aggregates, all
non-redistributable runtime sidecars needed to audit the causal chain, the
trusted verification receipt, and pinned GitHub attestation-verification JSON.
`evidence-manifest.json` binds every archived payload except the manifest itself; the outer archive SHA-256 above binds the manifest and the complete tar stream.

Only the five large official uv release archives are omitted to avoid duplicating
~109 MiB of upstream release payloads in Git. Their release URL, filename, size,
and SHA-256 are recorded under `external_content_addressed_fixtures` in the
manifest and independently bound by each verified axis report and trusted
receipt. SHA-256 pins content identity and rejects a replaced asset, but the URL
does not guarantee future availability: this bundle durably preserves the
qualification decision and its attested evidence, not a standalone offline
archive-extraction replay. No mutable bootstrap payload is qualified.

This evidence proves the attested source ref and run identity, not a branch-protection snapshot.

Qualification boundary:

- package -> install -> official MCP client initialize/list/call: qualified on
  native Linux, macOS, and Windows;
- real outdated uv fail-closed + manual content-bound recovery: qualified on
  native Linux and macOS;
- Windows installer recovery: `NOT_APPLICABLE_NO_NATIVE_INSTALLER`, while its
  real old `uv.exe` and package/MCP axis remain preserved;
- automatic mutable bootstrap: explicitly not qualified.
