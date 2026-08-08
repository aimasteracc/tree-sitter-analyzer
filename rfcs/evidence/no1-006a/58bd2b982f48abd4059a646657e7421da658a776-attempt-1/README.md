# NO1-006A durable native qualification evidence

Source: protected `develop` commit `58bd2b982f48abd4059a646657e7421da658a776`, workflow run `31272226364`, attempt `1`.

The split archive preserves the exact qualified wheel, wheel manifest, three native
axis reports, aggregate, trusted verification marker, pinned GitHub attestation
verification results, and an internal per-file digest manifest. Reassemble and
verify it with:

```bash
cat evidence.tar.gz.part* > evidence.tar.gz
sha256sum evidence.tar.gz
# expected: 9c7aa722ecf790a62b7f43d0609ee1eb08e0542d6545be01239535a8b2707410
tar -xzf evidence.tar.gz
```

Archive SHA-256: `9c7aa722ecf790a62b7f43d0609ee1eb08e0542d6545be01239535a8b2707410`. <!-- pragma: allowlist secret -->
Qualified wheel SHA-256: `c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8`. <!-- pragma: allowlist secret -->
Aggregate SHA-256: `7ecae9be0e0bbc6bd54f319aff2eee97e34774888fb0820abd759eee4f5551e2`. <!-- pragma: allowlist secret -->

The attestation verification records pin signer workflow
`aimasteracc/tree-sitter-analyzer/.github/workflows/native-install-qualification.yml`,
source digest `58bd2b982f48abd4059a646657e7421da658a776`, and source ref `refs/heads/develop`.
