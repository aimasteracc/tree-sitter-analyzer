# NO1-006A native-package qualification evidence

Source: `refs/heads/develop` commit `58bd2b982f48abd4059a646657e7421da658a776`, workflow run `31272226364`, attempt `1`.

The split archive preserves every file consumed by the no-checkout verifier: the
exact wheel/build manifest, all axis reports and sidecars (installed-byte ZIP,
MCP transcript/stderr, install output, and dependency manifest), aggregate,
trusted marker, job results, pinned GitHub attestation verification records, and
an internal per-file digest manifest.

```bash
cat evidence.tar.gz.part* > evidence.tar.gz
sha256sum evidence.tar.gz
# expected: 2e7acb71dc972c43def014d0fb0998d05c68136d79543b5048536bdd43467fd4
tar -xzf evidence.tar.gz
```

Archive SHA-256: `2e7acb71dc972c43def014d0fb0998d05c68136d79543b5048536bdd43467fd4`. <!-- pragma: allowlist secret -->
Qualified wheel SHA-256: `c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8`. <!-- pragma: allowlist secret -->
Aggregate SHA-256: `7ecae9be0e0bbc6bd54f319aff2eee97e34774888fb0820abd759eee4f5551e2`. <!-- pragma: allowlist secret -->

The attestation verification records pin signer workflow
`aimasteracc/tree-sitter-analyzer/.github/workflows/native-install-qualification.yml`,
source digest `58bd2b982f48abd4059a646657e7421da658a776`, and source ref `refs/heads/develop`. The evidence proves
that source ref and push event; it does not preserve or assert a branch-protection
configuration snapshot.
