# sample_config.yaml

| Element | Type | Lines | Details |
|---------|------|-------|---------|
| app | mapping | 5-8 | 4 keys |
| database | mapping | 10-15 | 4 keys |
| cache | mapping | 17-19 | 2 keys |
| defaults | mapping | 22-24 | 2 keys, anchor: &defaults |
| development | mapping | 26-28 | 2 keys |
| production | mapping | 30-33 | 3 keys |
| servers | sequence | 35-39 | 2 items |
| features | sequence | 41-44 | 3 items |
| settings | mapping | 46-50 | 4 keys |
| description | scalar | 53-56 | block literal |
| summary | scalar | 58-61 | block folded |
| flow_mapping | mapping | 64 | 2 keys, flow style |
| flow_sequence | sequence | 65 | 7 items, flow style |
| nested | mapping | 68-72 | 5 levels deep |
| metadata | mapping | 76-82 | 3 keys |

## Anchors & Aliases

| Name | Type | Line |
|------|------|------|
| &db_creds | anchor | 13 |
| &defaults | anchor | 22 |
| *db_creds | alias | 19 |
| *defaults | alias | 27, 31 |

## Documents

| Index | Lines |
|-------|-------|
| 0 | 1-72 |
| 1 | 74-83 |
