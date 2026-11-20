# Agent mail

## ADDED Requirements

### Requirement: Draft-safe delivery

Enrolled sessions SHALL exchange mail without terminal input or impersonating operator messages.

#### Scenario: Concurrent arrivals

- **WHEN** peers send messages while an operator edits a draft
- **THEN** the recipient processes both without an operator prompt or editor mutation

### Requirement: Safe retention

Cleanup SHALL preserve pending messages and reject delivery to stale recipients.

#### Scenario: Abandoned work

- **WHEN** a run stops before recipients acknowledge their messages
- **THEN** records remain available for explicit recovery
