# sample/sample.go

## Package Info
| Property | Value |
|----------|-------|
| Package | sample |
| Functions | 0 |
| Types | 10 |
| Variables | 0 |

## Imports
```go
import ""context""
import ""errors""
import ""fmt""
import ""sync""
import ""time""
```

## Structs
| Name | Visibility | Lines | Embedded | Doc |
|------|------------|-------|----------|-----|
| Config | exported | 44-50 | - | - |
| Service | exported | 71-77 | - | - |
| WorkerPool | exported | 206-210 | - | - |

## Interfaces
| Name | Visibility | Lines | Doc |
|------|------------|-------|-----|
| Reader | exported | 53-56 | - |
| Writer | exported | 59-62 | - |
| ReadWriter | exported | 65-68 | - |

## Type Aliases
| Name | Visibility | Lines |
|------|------------|-------|
| Status | exported | 33-33 |
| StringSlice | exported | 248-248 |
| Handler | exported | 251-251 |
| Middleware | exported | 254-254 |

## Functions
| Func | Signature | Vis | Lines | Doc |
|------|-----------|-----|-------|-----|
| NewService | ({'name': 'string', 'type': 'name'}, {'name': '*Config', 'type': 'config'}) *Service | exported | 80-86 | - |
| Name | () string | exported | 89-91 | - |
| IsRunning | () bool | exported | 94-98 | - |
| Start | ({'name': 'context.Context', 'type': 'ctx'}) error | exported | 101-114 | - |
| run | ({'name': 'context.Context', 'type': 'ctx'}) | unexported | 117-132 | - |
| tick | ({'name': 'time.Time', 'type': 't'}) | unexported | 135-139 | - |
| Stop | () error | exported | 142-153 | - |
| stop | () | unexported | 156-160 | - |
| ProcessData | ({'name': 'context.Context', 'type': 'ctx'}, {'name': '[]byte', 'type': 'input <-chan'}) (<-chan []byte, <-chan error) | exported | 163-193 | - |
| process | ({'name': '[]byte', 'type': 'data'}) []byte | unexported | 196-203 | - |
| NewWorkerPool | ({'name': 'int', 'type': 'workers'}) *WorkerPool | exported | 213-218 | - |
| Start | () | exported | 221-226 | - |
| worker | () | unexported | 229-234 | - |
| Submit | ({'name': 'func()', 'type': 'job'}) | exported | 237-239 | - |
| Shutdown | () | exported | 242-245 | - |
| Chain | () Middleware | exported | 257-264 | - |
| WithTimeout | ({'name': 'time.Duration', 'type': 'timeout'}) Middleware | exported | 267-275 | - |
| WithRetry | ({'name': 'int', 'type': 'maxRetries'}) Middleware | exported | 278-293 | - |

## Variables
| Name | Type | Vis | Line |
|------|------|-----|------|
| ErrNotFound | - | exported | 21 |
| DefaultTimeout | - | exported | 24 |
| MaxRetries | - | exported | 28 |
| RetryInterval | - | exported | 29 |
| StatusPending | Status | exported | 37 |
| StatusRunning | - | exported | 38 |
| StatusCompleted | - | exported | 39 |
| StatusFailed | - | exported | 40 |
| Host | string | exported | 45 |
| Port | int | exported | 46 |
| Timeout | time.Duration | exported | 47 |
| Debug | bool | exported | 48 |
| metadata | map[string]string | unexported | 49 |
| name | string | unexported | 72 |
| config | *Config | unexported | 73 |
| running | bool | unexported | 74 |
| mu | sync.RWMutex | unexported | 75 |
| done | chan struct{} | unexported | 76 |
| workers | int | unexported | 207 |
| jobs | chan func() | unexported | 208 |
| wg | sync.WaitGroup | unexported | 209 |
| middlewares | - | unexported | 257 |
| lastErr | error | unexported | 281 |