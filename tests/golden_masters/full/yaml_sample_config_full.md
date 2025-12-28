# sample_config

## Document Overview

| Property | Value |
|----------|-------|
| File | examples/sample_config.yaml |
| Language | yaml |
| Total Lines | 82 |
| Total Elements | 68 |

## Documents

| Index | Lines | Children |
|-------|-------|----------|
| 0 | 1-72 | 14 |
| 1 | 74-83 | 1 |

## Mappings

| Key | Value Type | Nesting | Line |
|-----|------------|---------|------|
| app | mapping | 1 | 5 |
| name | string | 2 | 6 |
| version | number | 2 | 7 |
| debug | boolean | 2 | 8 |
| database | mapping | 1 | 10 |
| host | string | 2 | 11 |
| port | number | 2 | 12 |
| credentials | unknown | 2 | 13 |
| username | string | 3 | 14 |
| password | string | 3 | 15 |
| cache | mapping | 1 | 17 |
| enabled | boolean | 2 | 18 |
| credentials | alias | 2 | 19 |
| defaults | unknown | 1 | 22 |
| adapter | string | 2 | 23 |
| pool | number | 2 | 24 |
| development | mapping | 1 | 26 |
| << | alias | 2 | 27 |
| database | string | 2 | 28 |
| production | mapping | 1 | 30 |
| << | alias | 2 | 31 |
| database | string | 2 | 32 |
| pool | number | 2 | 33 |
| servers | sequence | 1 | 35 |
| name | string | 3 | 36 |
| port | number | 3 | 37 |
| name | string | 3 | 38 |
| port | number | 3 | 39 |
| features | sequence | 1 | 41 |
| settings | mapping | 1 | 46 |
| timeout | number | 2 | 47 |
| retries | number | 2 | 48 |
| nullable_value | null | 2 | 49 |
| empty_value | null | 2 | 50 |
| description | string | 1 | 53 |
| summary | string | 1 | 58 |
| flow_mapping | mapping | 1 | 64 |
| key1 | string | 2 | 64 |
| key2 | string | 2 | 64 |
| flow_sequence | sequence | 1 | 65 |
| nested | mapping | 1 | 68 |
| level1 | mapping | 2 | 69 |
| level2 | mapping | 3 | 70 |
| level3 | mapping | 4 | 71 |
| deep_value | string | 5 | 72 |
| metadata | mapping | 1 | 76 |
| created | string | 2 | 77 |
| author | null | 2 | 78 |
| tags | sequence | 2 | 79 |

## Sequences

| Items | Nesting | Line |
|-------|---------|------|
| 2 | 1 | 36 |
| 3 | 1 | 42 |
| 7 | 1 | 65 |
| 3 | 2 | 80 |

## Anchors

| Name | Line |
|------|------|
| &db_creds | 13 |
| &defaults | 22 |

## Aliases

| Target | Line |
|--------|------|
| *db_creds | 19 |
| *defaults | 27 |
| *defaults | 31 |

## Comments

| Content | Line |
|---------|------|
| Application configuration | 2 |
| This is a comprehensive YAML example for testing | 3 |
| pragma: allowlist secret | 15 |
| Merge key example (<<: *anchor) | 21 |
| Block scalar examples | 52 |
| Flow style examples | 63 |
| Nested structures | 67 |
| Second document - metadata | 75 |
