# sample.swift

## Imports
```swift
import Foundation
```

## Class Info
| Property | Value |
|----------|-------|
| Name | Greeter |
| Package | unknown |
| Type | protocol |
| Access | public |

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| Greeter | protocol | public | 3-5 | 1 | 0 |
| Greeting | struct | public | 7-19 | 2 | 2 |
| GreetingService | class | internal | 21-27 | 1 | 1 |

## Greeter (3-5)
### Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| greet | String | Any name | internal | 4 |

## Greeting (7-19)
### Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| init | - | Any prefix | public | 11 |
| greet | String | Any name | public | 15 |

### Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
| prefix | String | public | false | true | 8 |
| count | Int | private | false | false | 9 |

## GreetingService (21-27)
### Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| welcome | String | Any user | internal | 24 |

### Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
| greeting | None | private | false | false | 22 |