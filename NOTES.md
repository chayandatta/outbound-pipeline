# Outbound Message Processing Pipeline — Technical Notes

## 1. Key Design Decisions

- **Database-Level Unique Constraints**: `(order, message_type)` uniqueness is enforced at the PostgreSQL database level (`UniqueConstraint`). API POST requests catch `IntegrityError` to safely perform idempotent creation/retrieval without race conditions.
- **FSM State Machine**: Strict state validation implemented via `can_transition_to()` and `transition_to()` on `OutboundMessageRequest`. Every transition automatically emits an immutable `AuditLog` generic model entry recording the transition, actor, and metadata.
- **Service Layer Architecture**: Clean separation between DRF views and business logic. Core workflows (`process_message_request`, `retry_failed_request`, `bulk_process_pending`, `deliver_message`) live in `outbound/services.py`.

## 2. Concurrency Strategy Chosen

**Chosen Behavior**: **`AlreadyProcessingError` (Immediate Rejection)**
- `process_message_request(request_id)` acquires a row-level lock using `select_for_update(nowait=True)`.
- If a concurrent worker attempts to process the exact same message request ID while locked, `OperationalError` / `DatabaseError` is caught and translated to `AlreadyProcessingError`.
- **Rationale**: Immediate rejection prevents workers from blocking and bottlenecking worker threads under high throughput. In a distributed processing architecture, skipping or rejecting already-locked tasks allows queue workers to move on to other pending messages immediately.

## 3. Bulk Processing & Skip Locked

- `bulk_process_pending` uses `select_for_update(skip_locked=True)` on candidate `RECEIVED` records.
- Multiple worker nodes or management command instances running `process_pending` concurrently can safely execute without lock contention or duplicate deliveries.

## 4. Time Abstraction & Testability

- `time_since_update` uses `django.utils.timezone.now()` and a testable helper function `format_time_since()`.
- Verified in tests using `freezegun` time freezing without flaky dependencies on `datetime.now()`.

## 5. Intentionally Skipped Edge Case

- **Skipped Case**: Automatic dynamic exponential backoff delay calculation between retries.
- **Why Skipped**: The specification requires enforcing a hard retry ceiling (`retry_count < 3`) and distinguishing retryable `TransientError` from fatal `PermanentError`. Adding dynamic backoff scheduling queues (e.g. Celery / Redis task delays) was out of scope for the required architecture and deadline.

## 6. AI Assistance

- AI was utilized to draft boilerplate DRF serializer fields, generate initial pytest fixture layouts, and speed up edge-case test suite generation. All business rules, locking semantics, and database constraint logic were hand-tuned and verified.
