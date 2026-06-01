# Vendors

The `/vendors/` page is being redesigned from a directory dump into a control
tower for vendor operations: who the vendor is, what folders and permissions
they live behind, who we know about on their side, what just happened, and what
needs attention next.

This document captures the redesign inputs, scope decisions, entity model, and
build order agreed for the next pass of work. It does not yet prescribe code.

## Scope decisions

- The page becomes a **hub at `/vendors/`** with sub-routes for detail work.
  The expanded `<details>` cards on the current page are removed.
- Operators of the dashboard are real **Django auth + session** users, with
  roles. Every pipeline view is `login_required`.
- **Vendor contacts** are a first-class entity. `Asset` carries a resolved
  `VendorContact` FK in addition to the raw `created_by_name/email` fields.
- **Permissions** are managed as a **local manifest** for this pass. A
  per-folder service-account probe is available as an ad-hoc action, but we
  do not mirror ShareFile's full ACL tree.
- **Notifications** are **read-only** this pass. The model exists and the
  page renders real rules and template previews, but no channel is wired.
- **Permission drift detection** uses a **lower bound per folder role**.
  Missing required levels are drift; extra levels are visible but not flagged.
- The hub's **attention feed** is a **central `AttentionItem` table** fed by
  sub-page services. Snooze and resolve are simple, not a workflow engine.

## Page map

```text
/vendors/                      hub: directory, health, attention feed
/vendors/<vendor_id>/          vendor profile
/vendors/permissions/          matrix + manifest
/vendors/permissions/<folder>/
/vendors/people/               operators, contacts, groups
/vendors/people/<contact_id>/
/vendors/activity/             global activity stream
/vendors/notifications/        read-only rule list
```

The hub stops being a directory dump. Anything dense lives on a sub-page.

## Entity areas

### 1. Users (operators)

Two kinds of "user" appear in the system; the redesign keeps them distinct.

- **Internal operators** of the dashboard. Modeled as a `PipelineUser` row
  linked one-to-one to `django.contrib.auth.models.User`, plus a `Role` and a
  `display_name`. Roles: `admin`, `reviewer`, `operator`, `viewer`. A small
  decorator `pipeline_role_required(...)` gates views; the rest of the system
  reads the current operator through a `current_pipeline_user(request)`
  helper.
- **Vendor contacts**. The people on the vendor side who upload files. Today
  these are denormalized strings on `Asset`; the redesign promotes them to
  `VendorContact(vendor, name, email, role, is_active, notes,
  linked_operator, observed)`. `observed=True` means we have inferred them
  from `Asset.created_by_email` and have not yet confirmed them. A one-click
  promote flow turns an observed contact into a confirmed one.

Asset identity uses the resolved contact when present, otherwise falls back to
the raw fields. Old `created_by_name/email` stay as the source of truth.

### 2. Vendors + folders

`Vendor` is thin today (`name`, `parser_key`, `is_active`, `notes`). Worth
extending with: a vendor code, a primary contact FK to `VendorContact`, an
expected reporting cadence, a parser version pin, contract/expiry metadata,
and a supported period type.

`ShareFileFolder → Vendor` is 1:N, which is right. The reverse M:N is not
needed. Two richer ideas that the page can expose:

- **Folder tree**: store parent/child or remote path so the UI can show a
  hierarchy, not a flat list of labels.
- **Expected vs observed patterns**: a folder declares what file patterns it
  expects; the catalogue flags files that match but are not in the expected
  set, and files that are expected but not seen this period.

UI: vendor profile with header (code, primary contact, parser version, health
badge), then folder list grouped by role, then a health subpanel (parser
present, recent runs, recurring failure pattern).

### 3. Rights (permissions)

This is the centerpiece for the rights work. Three sub-views:

- **Folder × principal matrix** for the ShareFile side. Principals are:
  service account, internal operators, vendor contacts, distribution groups.
  Cells show the effective `View | Download | Upload | Edit | Delete | Admin
  | Notify` level. The matrix highlights:
  - missing required permission (the lower bound from the role template);
  - service-account drift between folders;
  - excess permission (visible, not flagged as drift this pass).
- **Effective vs required**: declare a "role template" per folder role and
  diff actual principals against it. Templates are seeded from
  `docs/intro/SKILL.md`: `Input` requires service-account
  `View+Download+Upload`, vendor-contact `Upload+View`, operator
  `View+Download`. `Output` requires service-account `View+Upload`,
  vendor-contact `View+Download`, operator `View+Download`. `Both` is the
  union. Templates are editable in the manifest view.
- **Local app rights**: page-level capability flags per operator role (create
  vendor, assign folder, approve parse, force re-upload). The role on
  `PipelineUser` is the single source of truth; capability checks live next
  to views, not in templates.

The supporting model is small: a `PermissionTemplate` table seeded by data
migration, and a `FolderPermission` table that records what is declared per
folder. We do not mirror ShareFile's full ACL tree; we mirror the role rules
plus the local overrides.

### 4. Activities

`AssetEvent` is the base. The redesign adds:

- **Stream scope**: vendor, contact, folder, asset. Today the per-vendor card
  is the only consumer; the redesign promotes a top-level filterable stream
  with type chips (`discovered`, `status_change`, `parse`, `approval`,
  `upload`, `config_change`, `permission_change`).
- **Audit vs telemetry split**: configuration and permission changes are
  audit-grade (who, when, before/after). File events are telemetry
  (high volume). Audit entries render with more detail and a longer
  retention feel.
- **Attention queue**: a derived view of items needing human action (parse
  failed, approval pending, permission drift detected, contact unlinked,
  vendor with no activity for N days). Implemented as a central
  `AttentionItem` table fed by sub-page services.

`AssetEvent.actor` is a nullable FK to `PipelineUser`. A small
`record_event(...)` helper in `services.py` resolves the actor from the
request and falls back to "system" if anonymous.

### 5. Managing folders, users, groups, notifications

Four panels, one per operational area:

- **Folders**: add by id or by browsing; edit label/role/patterns;
  activate/deactivate; reassign vendor; bulk re-scan; "expected files this
  period" checklist.
- **Users/contacts**: list, link observed → contact, deactivate, set primary
  contact per vendor. Operators and contacts are distinct tabs.
- **Groups**: a `DistributionGroup` (a mirror of ShareFile's distribution
  list / group concept) of contacts and operators, used both for notification
  targeting and for permission grants. Membership is its own table so a
  person can be in multiple groups.
- **Notifications**: rules = `(trigger, scope, target, channel)`. Triggers:
  `new_file`, `status_change`, `parse_error`, `approval_pending`,
  `upload_done`, `permission_drift`, `vendor_quiet`. Channels: `email`,
  `in_app`, `webhook`. Targets: `operator`, `contact`, `group`. Per-vendor
  opt-in/opt-out with a default template. Read-only this pass; the page
  renders real rules and a "preview template" affordance for a chosen asset.

## Data model

Additive only. Existing models (`Vendor`, `ShareFileFolder`, `Asset`,
`AssetEvent`, `ParsedOutput`) stay as-is.

```text
PipelineUser
    user                 OneToOne auth.User
    role                 admin | reviewer | operator | viewer
    display_name
    is_active

VendorContact
    vendor               FK Vendor
    name
    email
    role                 free text, e.g. "Media Buyer"
    is_active
    notes
    linked_operator      FK PipelineUser, nullable
    observed             bool, default=False

Asset.resolved_contact   FK VendorContact, nullable
    (added to existing Asset)

DistributionGroup
    name
    kind                 internal | vendor
    description
    is_active

GroupMembership
    group                FK DistributionGroup
    contact              FK VendorContact, nullable
    operator             FK PipelineUser, nullable
    (check: exactly one of contact/operator set)

PermissionTemplate
    role                 FolderRole
    principal_kind       service_account | vendor_contact | operator | group
    level                View | Download | Upload | Edit | Delete | Admin | Notify
    is_required          bool

FolderPermission
    folder               FK ShareFileFolder
    principal_kind       as above
    principal_ref        CharField (FK target by kind; sentinel for service_account)
    level                as above
    source               role_default | explicit
    declared_by          FK PipelineUser, nullable
    declared_at          datetime

NotificationRule
    name
    trigger              new_file | status_change | parse_error | approval_pending
                         | upload_done | permission_drift | vendor_quiet
    scope_kind           vendor | folder | contact | operator | all
    scope_ref            nullable, polymorphic by scope_kind
    target_kind          operator | contact | group
    target_ref           nullable, polymorphic by target_kind
    channel              email | in_app | webhook
    template_key         CharField
    is_active            bool

AttentionItem
    kind                 vendor | folder | contact | operator
    scope_kind           as above
    scope_ref            CharField
    summary              CharField
    severity             info | warn | critical
    first_seen_at        datetime
    last_seen_at         datetime
    resolved_at          datetime, nullable
    resolved_by          FK PipelineUser, nullable
    (indexes: (scope_kind, scope_ref), (resolved_at, severity))

AssetEvent.actor         FK PipelineUser, nullable
    (added to existing AssetEvent)
```

### Seeded data

`PermissionTemplate` is seeded by a **data migration** so it is idempotent
and version-controlled. The seed mirrors the rules in
`skills/intro/SKILL.md`:

```text
Input
    service_account   View   required
    service_account   Download required
    service_account   Upload required
    vendor_contact    View   required
    vendor_contact    Upload required
    operator          View   required
    operator          Download required

Output
    service_account   View   required
    service_account   Upload required
    vendor_contact    View   required
    vendor_contact    Download required
    operator          View   required
    operator          Download required

Both
    union of Input and Output
```

`Delete` and `Admin` are intentionally not required anywhere. They are shown
in the matrix when present, so we can spot excess permission by eye, but they
do not trigger drift.

## Hub page (`/vendors/`)

What stays, what changes.

- **Top metrics strip**: vendors, folders, contacts, permission drift count,
  attention items, events today. The first three are reused; the last three
  are new. Attention items drive the rest of the page.
- **Vendor directory**: same rows, but with two derived badges. `Health`
  (parser present, recent activity in window, contact linked, permissions
  complete). `Attention` (one of: parse failing repeatedly, no activity in
  N days, primary contact missing, permission drift). Clicking a vendor goes
  to `/vendors/<id>/`, not a `<details>` expansion.
- **Folder ownership + permission status** (collapsed summary): the existing
  reassign UI moves here as a compact table. Each row gets a permission
  status cell (`ok`, `drift`, `unknown` if no template for the role).
- **Recent attention items** (new, top-right or below metrics): the 10 most
  recent unresolved `AttentionItem` rows, each linking to the relevant
  sub-page. This is the new "what should I look at first" surface.
- **Recent activity preview**: a five-row slice of the global activity
  stream, with a "see all" link.

## Sub-pages

### Vendor profile (`/vendors/<id>/`)

- Header: name, code, primary contact, parser key + version, role summary
  (input/output folders), health and attention badges.
- Folders panel: grouped by role, with permission status and link to folder
  detail.
- People panel: contacts, observed uploaders, with promote/link actions.
- Parser panel: schema and parser path, plus a "last parse outcome" feed.
- Files panel: paginated recent assets with their status.
- Events panel: vendor-scoped activity stream.

### Permissions (`/vendors/permissions/`)

- **Manifest editor** (top): the small table of `PermissionTemplate` rows.
  Editable. Lets you say "folders with role=input get Upload+View+Download
  for vendor contacts".
- **Matrix** (main): rows = folders, columns = principal kinds and groups.
  Each cell shows the effective level and whether it is declared, default, or
  drift. Colored: green (matches template), amber (declared but does not
  match), red (template expected level not present), grey (no template for
  this role).
- **Drift list** (right rail or section): rows like "Folder X is missing
  Upload for the vendor contact group". Each entry links to a fix-it action:
  declare the missing permission, or note that this folder is intentionally
  different.
- **Folder detail** (`/vendors/permissions/<folder>/`): principals list, the
  role template that applies, and the diff. A "service-account probe" button
  calls the existing `src/testifize_pipeline/sharefile/client.py` to ask
  ShareFile what the service account can do on this folder, and renders the
  result for one-shot comparison. The probe result is not persisted unless
  the user clicks "save as declared".

### People (`/vendors/people/`)

- **Tabs**: Operators, Contacts, Groups.
- **Operators**: list of `PipelineUser`s, with role and last-seen. Add/edit/
  remove. Wired to Django auth on save (create `auth.User` with unusable
  password plus a `PipelineUser` row).
- **Contacts**: list of `VendorContact`s, filterable by vendor. Each shows
  upload count, last activity, and a "linked?" indicator. The list also
  surfaces observed uploaders that are not yet contacts, with a "create
  contact" action.
- **Groups**: `DistributionGroup` list with members and the folders they
  appear in.
- **Promote flow**: on a contact row, "Promote to operator" creates a
  `PipelineUser`; "Link to existing operator" links the contact to a known
  operator.

### Activity (`/vendors/activity/`)

- Filters: time window, vendor, folder, event type, audit vs telemetry.
- **Audit** rendering (config_change, permission_change, vendor_create,
  vendor_update, assign, etc.): card with before/after diff, actor,
  timestamp.
- **Telemetry** rendering (discovered, status_change, parse, approval,
  upload): compact list grouped by day.
- Saved filters per operator (later).

### Notifications (`/vendors/notifications/`)

- List of `NotificationRule` rows with trigger, scope, target, channel,
  active state, and a "last fired" placeholder.
- A "preview template" affordance that renders a sample payload against a
  chosen asset.
- Empty state explains that triggers and channels are configured but not
  wired; this is intentional so reviewers know the page is real, not stubbed.

## Cross-cutting

- **Service account probe** lives as a small button on folder detail, not a
  global job. The probe calls existing `src/testifize_pipeline/sharefile/`
  modules; it never calls ShareFile from a Django template.
- **Health and attention** are derived, not stored. Computation lives in
  `pipeline_dashboard/services.py`. They are recomputed per request; cache
  only when a profile page gets slow.
- **Operator identity on actions**: every form in the new pages carries the
  current `PipelineUser` into the view, which writes it onto
  `AssetEvent.actor`. This is the smallest change that makes "who approved
  this" a real question.
- **Permissions on the rights matrix are advisory**, not enforced. The
  pipeline already gates vendor assignment and parser upload in the
  workflow. The matrix is for visibility and planning, which matches "local
  manifest only" and avoids pretending we mirror ShareFile.
- **No data leaks**: tokens, app passwords, and `.env` values are never
  rendered. The probe page confirms presence of the service account, not
  its secret.

## Build order

1. **Auth foundation**: add `PipelineUser`, login/logout views,
   `login_required` on pipeline views, a small `current_pipeline_user(
   request)` helper. Add `actor` to `AssetEvent`. Internal `record_event(
   ...)` writes through the helper. The only visible change is the login
   screen; the existing UI keeps working.
2. **Vendor profile page**: introduce `/vendors/<id>/` with the new layout
   (header, folders, people, parser, files, events). Trim `/vendors/` to
   summary + directory table.
3. **People page**: `VendorContact`, `DistributionGroup`, `GroupMembership`.
   Auto-create observed contacts at ingest. `Asset.resolved_contact`
   populated on next scan. Promote-to-operator flow.
4. **Permissions page**: `PermissionTemplate` (with data migration),
   `FolderPermission`, matrix view, folder detail, lower-bound drift
   detection, service-account probe button (calls existing
   `sharefile.client`).
5. **Activity stream**: filters, audit/telemetry split, attention feed
   source. Each sub-page emits attention items as a side effect of its
   services.
6. **Notifications page**: read-only rule list, template preview, empty
   state that explains it's a stub.
7. **Hub attention feed**: central `AttentionItem` table, snooze/resolve
   actions, link from hub to the source page.

Each step is shippable on its own and keeps the existing tests green, which
matters because `pipeline_dashboard/tests/` is the safety net for the
parser/upload path.

## Open follow-ups

- A management command to backfill `Asset.resolved_contact` for historical
  rows. On-demand (next scan) is fine for new assets; the command is more
  honest for old data.
- Whether to keep the existing `Asset.created_by_name/email` fields
  unchanged (recommended) or migrate to a `created_by` polymorphic ref.
- A "snooze for N days" affordance on `AttentionItem`, persisted and
  respected by the hub feed.
- An opt-in `email` channel for `NotificationRule` once a delivery queue
  exists; this is out of scope for the read-only pass.
