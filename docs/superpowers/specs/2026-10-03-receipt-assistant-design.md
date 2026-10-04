# Receipt assistant — design

Date: 2026-10-03

Status: amended to align with the merged foundation and product core specs; awaiting review

Tracking: [issue #1](https://github.com/CrmWare/propware-agentimo/issues/1)

Builds on:

- `2026-10-03-foundation-design.md` ([issue #2](https://github.com/CrmWare/propware-agentimo/issues/2))
- `2026-10-03-product-core-design.md` ([issue #3](https://github.com/CrmWare/propware-agentimo/issues/3))

## 1. Purpose

When an agency pays a commission, the independent agent (IRS Categoria B) must issue a fatura-recibo eletrónica on the Portal das Finanças. Today the agent retypes figures Agentimo already knows.

The receipt assistant prepares every Portal field from a received payment, lets the agent issue on the Portal themselves, and then records the issued receipt in Agentimo, either typed or extracted from the uploaded PDF.

Success for the paid pilot:

- An agent can go from a received payment to a recorded receipt without typing an amount twice.
- The agent can see which received commissions still lack a receipt.
- The receipt records show how many pilot agents used the assistant to the end, which informs the post-pilot decision on a certified provider API integration.

## 2. Scope

In scope:

- Receipt draft (copy sheet) for a received payment.
- Recording an issued receipt by hand or by PDF upload with extraction and document verification.
- Storing the uploaded PDF.
- Missing-receipts list.
- Correcting and deleting a receipt.

Out of scope:

- Certified provider API integration (post-pilot, see issue #1).
- Any automation of, or direct integration with, the Portal das Finanças.
- Holding AT credentials of any kind.
- OCR and LLM-based extraction.
- Document types other than fatura-recibo.
- Automatic changes to a negócio, a payment part or a settlement from receipt data.
- Suggesting fiscal regimes or rates. Agentimo applies the agent's own settings and gives no tax advice.
- Any arithmetic of its own. Every figure comes from the product core's calculation engine.

This spec is built after the foundation and the product core.

## 3. What it uses from the other specs

From the product core:

- **Settlement:** the append-only record that a payment part was received, with its `actual_base` and its frozen engine inputs and outputs (IVA, retenção, bank inflow, and the IVA setting's legal mention when exempt).
- **Negócio:** the agency name and NIF copied onto it.
- **Financial profile:** the agent's NIF.
- **Calculation engine:** the only source of amounts. The receipt assistant never recomputes them.

From the foundation:

- Both isolation layers, the access phases and the phase guard, export, erasure and the audit and retention rules.

The agent's NIF and the agency NIF are optional in the product core. The receipt assistant requires them and asks for them when missing.

## 4. Components

### 4.1 Receipt draft

A read-only view with no storage and no arithmetic. It exists for each current valid settlement.

Fields, all taken from the settlement and its negócio:

- Agency NIF and name.
- Description.
- Base: the settlement's `actual_base`.
- IVA and retenção: the settlement's frozen outputs, with the legal mention when IVA is exempt.
- Amount to receive: the settlement's frozen bank inflow.

Because the settlement is frozen, the draft does not change when the profile changes later. If a settlement is corrected by replacement, the draft follows the current valid settlement.

Receipts across a replacement chain:

- For a current valid settlement, the assistant surfaces every receipt associated with any settlement in its replacement chain, not only with the current one.
- When such a receipt exists, the assistant shows it beside the current figures and flags any difference. It does not present the draft as a receipt still to be issued, and it never implies that a new fiscal document is automatically required.
- A receipt keeps its original settlement association. Only the agent can change it, explicitly.

### 4.2 Receipt record

The persisted fact that a fatura-recibo was issued. Created only when the agent confirms.

| Field | Notes |
| --- | --- |
| Owner | The agent. |
| Negócio | One negócio can have several receipts. |
| Settlement | Optional association with the settlement it was issued for. |
| Issuing channel | `portal_manual` is the only value in the pilot. |
| Number | Optional when typed. Unique per agent when present. |
| Issue date | Optional when typed. |
| Agency NIF and name | As on the receipt. |
| Base, IVA, retenção, total | Integer cents. |
| Data origin | `typed`, `extracted` or `extracted_edited`. |
| Edited fields | For `extracted_edited`: which fields the agent changed. |
| Document verification | `none`, `verified` or `unverified` (section 6.1). |
| File reference | Optional. |

Payments and fiscal documents are separate concepts. A receipt can be associated with a settlement, but "one receipt per settlement" is not an invariant, and nothing in the product core depends on receipts.

A receipt record is the agent's own note of a document that lives on the Portal. It is editable and deletable, unlike a settlement.

- Editing or deleting it changes only Agentimo's record. It never changes or annuls the document on the Portal, and the interface says so at both actions.
- Deletion is labelled as removing the Agentimo record, not as annulling the receipt.
- An uploaded PDF is stored unchanged. No edit to the record alters it.

### 4.3 Receipt document store

Private file storage for uploaded PDFs.

- No public URLs. Downloads go through an authenticated endpoint that checks the owner and serves the file as an attachment.
- Each agent has an opaque storage prefix. Storage keys are random under that prefix and never built from user input. The original filename is not trusted.

Every stored file has an owner-scoped **file record**, which is agent data. The record, not the storage, is the source of truth for a file's lifecycle:

| State | Meaning |
| --- | --- |
| `uploading` | The record exists; the object is being written |
| `pending` | Uploaded, not yet attached to a receipt; expires 24 hours after upload |
| `attached` | Attached to exactly one receipt record |
| `pending_deletion` | To be removed from storage; the record keeps the storage key until removal succeeds |

Protocol:

- **Upload:** the file record is created in state `uploading`, in a transaction that verifies the agent is not in the erasing state, before the object is written. After the write, a second transaction moves it to `pending`. If that transaction fails, or finds the agent erasing, the request deletes the object it wrote.
- **Closing an upload:** a request timeout does not prove that a storage write has stopped. A worker can crash, and a storage operation can complete after the request has timed out. An `uploading` record is therefore never discarded on elapsed time alone. It is discarded only after the upload is **proven closed**: storage has confirmed that the write was completed or cancelled and that no further write under that key can succeed. Only then is any object under the key removed, its absence verified, and the record deleted.
- **Implementation gate:** how an upload is proven closed depends on the storage used. The completion and cancellation protocol for the chosen storage is defined and validated before this component is built. If the chosen storage cannot give that proof, the plan stops and the storage choice or this section is revised.
- **Attachment is single-use:** confirmation locks the file record, requires it to be `pending` and not expired, and moves it to `attached` in the same transaction that creates the receipt. A file record can be attached once, to one receipt.
- **Expiry:** a `pending` record older than 24 hours cannot be attached, whether or not the cleanup has run yet.
- **Deletion:** deleting a receipt, or expiring a pending upload, moves the file record to `pending_deletion` in a database transaction. The object is removed afterwards by the cleanup job. The record, with its storage key, is deleted only after storage confirms removal, so a failed removal is retried and no file is orphaned.
- **Shared locking:** confirmation and cleanup both lock the file record and act only on the state they find. Cleanup never selects an `attached` record, and a record that confirmation has locked is skipped. A confirmed file can therefore never be removed by the cleanup.

### 4.4 Receipt extractor

Input: a PDF. Output: the receipt record fields, or a named failure. Deterministic, runs on our server, sends nothing to third parties.

- Accepted input: a PDF under a size cap of 5 MB. File type is checked by content.
- Processing is bounded independently of file size: at most 5 pages, 5 seconds and 128 MB of memory per document, enforced by running the parser in an isolated worker process. A document that exceeds any limit is rejected. The budgets are initial values, validated against the supplied Portal fixture.
- Method: read the AT QR code if present and parse its field string; otherwise parse the text layer by the Portal's labels.
- Output: number, issue date, issuer NIF, agency NIF and name, base, IVA, retenção, total.

Implementation gate: a real Portal fatura-recibo PDF, supplied by the product owner, confirms which of the two methods the Portal's PDFs support. The method the sample supports is the one implemented; the other is dropped. The same PDF is the rounding fixture for the product core's calculation engine.

### 4.5 Assistant UI

- Copy sheet for a received payment, with one copy action per field and a link to "Faturas e Recibos" on the Portal.
- Confirm step: by hand or by upload.
- Missing-receipts list.

## 5. Flows

### 5.1 Prepare

For a current valid settlement the assistant shows the copy sheet. If the agent's NIF or the negócio's agency NIF is missing, the assistant asks for it first and shows no draft.

### 5.2 Confirm by hand

The agent marks the receipt as issued. Number and date are optional. Amounts default to the draft and can be edited. The record is saved with origin `typed`.

### 5.3 Confirm by upload

1. The agent uploads the PDF.
2. Agentimo validates and extracts.
3. Extracted fields are shown beside the draft, with differences highlighted.
4. The agent can correct fields and confirms.
5. The record is saved and the file attached, in one transaction.

- With no corrections, the origin is `extracted` and the record holds exactly what the document says.
- Corrections at step 4 are agent-confirmed transcription corrections: the origin is `extracted_edited`, and the changed fields are recorded. The PDF is unchanged.
- Nothing is persisted as a receipt before step 5. An upload that is not confirmed expires after 24 hours. From that moment it cannot be attached or downloaded. Its removal from storage follows (section 8).

### 5.4 Missing receipts

A list of negócios whose receipted base is below their received base:

- received base: the sum of `actual_base` over the negócio's current valid settlements;
- receipted base: the sum of the base of the negócio's receipt records.

The comparison is per negócio, because a receipt's association with a settlement is optional.

### 5.5 Correct or delete

The agent can edit a receipt record, or remove it, for example after annulling the receipt on the Portal themselves.

- Editing a record whose origin is `extracted` changes the origin to `extracted_edited` and records the changed fields.
- Removing a record moves its file to `pending_deletion` in the same transaction; the cleanup job removes the object (section 4.3).

## 6. Rules and failures

### 6.1 Document verification

An uploaded document ends in exactly one of three outcomes. Two mandatory checks decide it: the issuer NIF equals the agent's NIF, and the document type is fatura-recibo. Each check is read as a match, read as a mismatch, or unreadable.

The outcomes are evaluated in this order, and the first that applies is the outcome:

1. **Rejected (known mismatch):** either check was read and does not match. This applies even when the other check is unreadable. The upload cannot be attached.
2. **Verified:** both checks were read and both match. The file can be attached, and the receipt's document verification is `verified`.
3. **Unverifiable:** anything else, that is, no known mismatch and at least one check unreadable, for example a document with no text layer or a failed extraction. The file can be attached only as an explicitly unverified attachment: the receipt's document verification is `unverified`, the fields are typed by the agent, the origin is `typed`, and the interface labels the document "Documento não verificado".

- `verified` means only that the issuer NIF and the document type on the PDF match. It is not proof that the document is authentic or fiscally valid, and the interface does not present it as such.
- Typing the fields by hand never turns an unverified document into a verified one. Only a successful reading of both checks produces `verified`.
- A receipt with no file has document verification `none`.

### 6.2 Other rules

| Case | Behaviour |
| --- | --- |
| Not a PDF, over the size cap, or over a processing limit | Rejected with the reason. Nothing is attached; the agent can confirm by hand without a file. |
| Number already recorded for this agent | Rejected, pointing to the existing record. |
| Extracted values differ from the draft | The document's values are what an untouched extraction stores. The settlement is not changed. The difference is shown, and the agent decides whether to correct the settlement through the product core's replacement flow. |
| The agent changes extracted values | An agent-confirmed transcription correction: origin `extracted_edited`, changed fields recorded, PDF unchanged. |
| Repeated confirmation request | Handled by the idempotency rule in section 7. |

## 7. Isolation and integrity

- Receipt records and file records are agent data. Both foundation layers apply: the owner trait and forced row-level security, with a `NOT NULL` owner column that the application role cannot change.
- A receipt's negócio and settlement must belong to the same owner, and the settlement must belong to that negócio. This is enforced in the database by composite foreign keys.
- Every receipt operation resolves the negócio through its owner. Another agent's identifier returns "not found".
- The per-agent uniqueness of the receipt number is a database constraint.
- Confirmation carries a client-generated idempotency key, unique per agent and operation, with a payload fingerprint. The same key and payload return the existing record; the same key with a different payload returns a conflict.
- The PDF is parsed, never rendered as HTML.
- Logs contain no NIFs, amounts or file content.

### 7.1 Access phases

- Every mutation service in this spec calls the foundation's phase guard.
- In the read-only phase, recording, editing and deleting receipts, uploads, and file downloads are all refused. The copy sheet and the lists remain viewable.
- In the locked and marked phases, nothing in this spec is served.

### 7.2 File cleanup job

File cleanup is the only non-HTTP writer in this spec.

- It runs hourly as a named system job on the system role, because it works across agents. Hourly is its schedule under normal operation.
- It expires `pending` file records older than 24 hours, removes the objects of records in `pending_deletion`, and deletes each record once storage confirms removal.
- It closes stalled uploads: for an `uploading` record past the upload request timeout, it proves the upload closed (section 4.3), removes any object under its key, and only then deletes the record. A record whose upload cannot yet be proven closed is kept and retried.
- It never touches an `attached` record or a receipt record.
- It is not subject to the phase guard: cleanup must run whatever the agent's phase.

### 7.3 Erasure

- Pending and uploading files are included in account erasure, like attached ones: the foundation's stored-files step deletes everything under the agent's storage prefix.
- From the moment the agent enters the erasing state, no new upload can start, because the upload's first transaction refuses it.
- An upload already in flight finds the agent erasing or gone at its second transaction and deletes the object it wrote. Erasure does not rely on this: the worker may have crashed.
- The stored-files step proves every upload of the agent closed before it deletes, and erasure is not marked complete until the agent's storage prefix is verified empty after that proof. Elapsed time is never the proof.
- The agent's opaque storage prefix is recorded in the independent erasure operation, so the deletion and the verification can be retried after the agent's rows, including the file records, are gone.

## 8. Retention and data protection

- A receipt and its file are kept while the account exists, or until the agent removes them. Removing a receipt removes the file itself, with retries until storage confirms.
- Unconfirmed uploads expire after 24 hours. Expiry is immediate and unconditional: an expired upload cannot be attached or downloaded, whether or not it has been removed yet.
- Removal from storage within the following hour is the target under normal operation, not a guaranteed maximum. Scheduler downtime or a storage failure can delay it.
- Removal is retried until storage confirms it. File records overdue for removal are reported in operational monitoring, with their number and age.
- Lapse, the deletion mark and erasure follow the foundation. This spec adds no retention rule of its own.
- Receipt records and PDFs are added to the agent's data export.
- Erasure removes every file under the agent's storage prefix in the foundation's stored-files step, and the receipt and file records in its database step (section 7.3).
- The agent is told that Agentimo's copy is a convenience: the original stays on the Portal and the legal duty to keep fiscal documents remains theirs.

## 9. Testing

Tests are written before implementation.

- Draft: every figure equals the settlement's frozen output; a later profile change does not alter it; after a settlement replacement the draft follows the current valid settlement. No arithmetic is tested here; engine tests live in the product core.
- Extractor: fixtures from real Portal PDFs; corrupt file; oversized file; a document over the page, time or memory limit is rejected.
- Verification: a verified match attaches as `verified`; a wrong issuer and a wrong document type are each rejected and cannot be attached; a document with no text layer, and one whose extraction fails, attach only as `unverified` with typed fields; typing fields never produces `verified`.
- Verification precedence, mixed outcomes: wrong issuer with unreadable type is rejected; unreadable issuer with wrong type is rejected; matching issuer with unreadable type is unverifiable; unreadable issuer with matching type is unverifiable.
- Origin: an untouched extraction is `extracted` and equals the document; a correction at confirmation, and a later edit of an extracted record, are `extracted_edited` with the changed fields recorded; the PDF is byte-identical after any edit.
- Replacement chain: after a settlement is replaced, the receipt associated with its predecessor is surfaced for the current settlement, differences are flagged, the association is unchanged, and no new receipt is presented as required.
- Isolation, both layers: agent B cannot read, change, delete or download agent A's receipts or files. The same number is accepted across agents and rejected within one. A receipt cannot reference a settlement of another negócio or another owner.
- Idempotency: a repeated confirmation returns the same record; the same key with a different payload returns a conflict.
- Phases: in read-only, every receipt mutation, upload and download is refused; in locked and marked, nothing is served.
- Flows: confirm by hand, confirm by upload, correct, delete.
- Cleanup: an unconfirmed upload older than 24 hours is removed in every phase; attached files and receipt records are never touched.
- Expiry without cleanup: with the cleanup job stopped, an upload older than 24 hours cannot be attached or downloaded, and is reported as overdue for removal.
- Upload closure: a storage write that completes after the request timed out leaves no object once the upload is closed; a worker that fails before finalisation leaves a record that is kept until the upload is proven closed, never discarded on time alone.
- Concurrency: confirmation racing with cleanup on the same upload ends with either an attached, intact file or a refused confirmation, never a receipt pointing to a removed file.
- Single use: a file record cannot be attached to two receipts; an expired pending upload cannot be attached even before cleanup has run.
- Deletion recovery: when storage removal fails, the file record and its key remain and the removal is retried until it succeeds.
- Erasure: pending and uploading files are removed; an upload in flight when erasure starts, including one whose worker crashed, leaves no file behind; a new upload is refused once the agent is erasing; the stored-files step can be retried from the erasure operation's recorded prefix after the agent's rows are deleted.
- Missing receipts: none received; received and not receipted; partly receipted; fully receipted across two settlements; a settlement correction that changes the received base.
- Export and erasure: receipts and PDFs are in the export, and none remain after erasure.

## 10. Dependencies and follow-ups

- **Foundation spec:** two narrow amendments, made in the same pull request as this spec: "receipt file cleanup" joins the named system jobs (section 7.2), and the erasure stored-files step proves uploads closed, deletes by the agent's storage prefix, and verifies it empty before completion, with the prefix recorded in the erasure operation (section 7.3).
- **`docs/mvp-analysis.md`:** §6 currently excludes "Faturação e recibos" and must be amended to reflect the decision in issue #1.
- **Portal PDF:** a real fatura-recibo is needed before the extractor is planned (section 4.4).
- **Storage protocol:** the completion and cancellation protocol that proves an upload closed is an implementation gate (section 4.3).

## 11. Pilot signal

No analytics are added. The receipt records show how many agents recorded receipts and whether by typing or by upload.
