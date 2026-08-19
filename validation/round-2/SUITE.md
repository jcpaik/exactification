# Round 2 and combined-suite record

The context-isolated Round 2 run completed all three assigned cases. Each
attempt passed the generic exact verifier and the fresh manifest-aware harness
with status `EXACT_SDP_CERTIFICATE`.

| Case | Exact objective | Certificate SHA-256 |
| --- | ---: | --- |
| `obfuscated-rational-kernel` | `2224093617954365/48084958827` | `945f086744c3428413a607efa07943f52c152a54126952a0d0561d5399dc75b9` |
| `grzesik-pentagon` | `24/625` | `a0fbf43ad114dfea0cd4c943ce050c13c1d6f36adf2baab8c3929a93c7585a71` |
| `dlm-three-point-10` | `10` | `3bbf0fd32abc4f55012db3d0cb8f5997d9af95988b3d60a3dd0e0d30b7a6f40c` |

The full discovery record, including recovered faces, p/2p diagnostics,
rejected branches, operational events, exact ranks, and principal commands, is
in the [Round 2 executor report](executor-report-round-2.md).

## Frozen-workspace integrity

The post-run inventory check is:

```sh
python3 -B -m validation.check_blind_inventory \
  validation/round-2/blind-workspace \
  --allow-generated-attempts
```

It verifies 55 inventoried files and admits 93 generated attempt/report files
under the explicit post-run policy. The
`BLIND_WORKSPACE_INVENTORY.json` SHA-256 is
`c9a6277a0f1d334fc83d0d54c689c4e9a51cb1a1741c2cd0c00be52a4faba1c9`.

## Combined exact verification suite

Run the complete suite with:

```sh
python3 -B -m validation.run_suite --config validation/suite.json
```

The strict configuration has suite ID `round-1-and-2-complete`. It completes
the unit tests and all preflights, checks exact coverage of the four expected
case IDs, and accepts six attempts:

- immutable Round 1 DLM, Grzesik, and transparent rotated-control attempts;
- promoted Round 2 DLM, Grzesik, and obfuscated held-out attempts.

This is an exact-certificate validation result for the repository's rational
SDP models. It does not by itself claim a separately checked flag-algebra
theorem adapter or extremal sharpness witness.
