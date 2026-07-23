# Design: From `Topography` to a pluggable `Measurement` model

Status: **draft / proposal** — no implementation yet.

This document describes a planned architectural change: renaming the
`Topography` model to `Measurement`, moving all measurement-type-specific
metadata into a validated JSON field, and making the set of measurement types
pluggable so that non-topography data (e.g. an XPS spectrum) can be added by
external packages without touching the core.

## 1. Motivation and current state

`topobank.manager.models.Topography` currently plays four roles at once:

1. **Persistence & platform concerns** — identity, `surface` FK, permissions,
   ownership, tags, attachments, soft deletion, task state, file manifests
   (raw datafile, squeezed NetCDF, thumbnail, deep-zoom).
2. **Physical metadata schema** — typed columns that only make sense for
   height data: `size_x`, `size_y`, `unit`, `height_scale`, `is_periodic`,
   `detrend_mode`, `fill_undefined_data_mode`, `instrument_name`,
   `instrument_type`, `instrument_parameters`, plus the `*_editable` flags.
3. **File-derived cache** — `resolution_x/y`, `bandwidth_lower/upper`,
   `short_reliability_cutoff`, `has_undefined_data`, `channel_names`,
   `datafile_format`, `data_source`.
4. **Behavior** — `read()` (constructing a `SurfaceTopography`
   `Topography`/`UniformLineScan`/`NonuniformLineScan` instance),
   `refresh_cache()` (file inspection), thumbnail/deep-zoom/squeezed-file
   generation.

The three actual data kinds — **topography map**, **uniform line scan**,
**nonuniform line scan** — share one column set and are distinguished only
implicitly (`size_y IS NULL` ⇒ line scan; `is_periodic_editable == False` ⇒
nonuniform). Adding a measurement type whose data is not height data (an XPS
spectrum, a force curve, …) is impossible without schema changes and without
polluting every existing row with more nullable columns.

The codebase already contains the pattern we need, applied to analysis
workflows: `WorkflowImplementation` couples a stable `Meta.name`, a pydantic
`Parameters` model for validated JSON kwargs, and a decorator-based registry
(`topobank/analysis/registry.py`). This proposal applies the same pattern to
measurements.

## 2. Target architecture — three layers plus a plugin seam

```
┌────────────────────────────────────────────────────────────────────┐
│ Django model:  Measurement          (persistence, permissions,     │
│   kind = "topography-map"            files, task state, relations) │
│   metadata  = JSONField  ──────────┐                               │
│   file_info = JSONField            │ validated by                  │
└──────────────┬─────────────────────┼───────────────────────────────┘
               │ get_type()          ▼
┌──────────────▼─────────────────────────────────────────────────────┐
│ MeasurementType (registered plugin class, one per kind)            │
│   Meta.name = "topography-map"                                     │
│   Metadata  = TopographyMapMetadata   (pydantic; the schema)       │
│   read(measurement)  -> data object                                │
│   inspect(measurement) -> metadata defaults + file_info            │
│   capabilities: thumbnail / deepzoom / squeezed / bandwidth …      │
└──────────────┬─────────────────────────────────────────────────────┘
               │ constructs
┌──────────────▼─────────────────────────────────────────────────────┐
│ Data object (in-memory domain representation)                      │
│   SurfaceTopography.Topography / UniformLineScan /                 │
│   NonuniformLineScan today; xps_package.Spectrum tomorrow          │
└────────────────────────────────────────────────────────────────────┘
```

Terminology (answering "is *data class* the correct term?"): we suggest
calling the third layer the **data object** (or *domain object*): the
in-memory, computational representation of the measurement. The pydantic
model is the **metadata schema**; the Django model is the **record**. The
`MeasurementType` class is a strategy/adapter that binds the three together
for one kind of measurement. Avoid "data model", which collides with Django
terminology.

## 3. The `Measurement` Django model

Renamed from `Topography`. Keeps only fields that are (a) generic across all
measurement kinds and (b) needed for querying, ordering, joins, or platform
behavior:

```python
class Measurement(PermissionMixin, TaskStateModel, SubjectMixin):
    # Relations & platform (unchanged)
    surface       = models.ForeignKey(Surface, related_name="measurements", ...)
    permissions, created_by, updated_by, owned_by
    name, description, tags, attachments
    created_at, updated_at, deletion_time
    measurement_date = models.DateField(...)   # stays a column: used in Meta.ordering

    # Files (unchanged, but see §6 on "squeezed")
    datafile, datafile_format, channel_names, data_source
    squeezed_datafile, thumbnail, deepzoom

    # NEW: type dispatch + typed JSON payloads
    kind      = models.CharField(max_length=64, db_index=True)  # registry key
    metadata  = models.JSONField(default=dict)   # user-facing physical metadata
    file_info = models.JSONField(default=dict)   # read-only, file-derived cache
```

Design decisions:

- **`kind` is a plain string column**, not an enum/choices: the set of valid
  values is defined by the registry at runtime (plugins can extend it), and a
  DB-level enum would defeat pluggability. It is the discriminator used for
  dispatch and for filtering (`Measurement.objects.filter(kind="topography-map")`).
  Stable, slug-like identifiers: `"topography-map"`, `"uniform-line-scan"`,
  `"nonuniform-line-scan"` (never rename once shipped — they end up in the
  DB, in exported containers, and in published datasets).
- **Two JSON fields, not one.** `metadata` and `file_info` have different
  owners and write paths: `metadata` is edited by the user through the API
  and validated against the kind's pydantic schema; `file_info` is written
  exclusively by the inspection task (Celery) and is never user-editable.
  Separating them keeps the "significant change → invalidate analyses" logic
  simple (only `metadata` changes are significant), avoids races between a
  user PATCH and a running inspection task, and gives `update_fields`
  granularity.
- **What lands where** (for the three current kinds):
  - `metadata`: `size_x`, `size_y`, `unit`, `height_scale`, `is_periodic`,
    `detrend_mode`, `fill_undefined_data_mode`, and an `instrument` sub-object
    (`name`, `type`, `parameters` — folding today's three instrument columns
    into the schema).
  - `file_info`: `resolution_x/y`, `bandwidth_lower/upper`,
    `short_reliability_cutoff`, `has_undefined_data`, and the editability
    flags `size_editable`, `unit_editable`, `height_scale_editable`,
    `is_periodic_editable` (these describe what the *file* provides, so they
    are file-derived facts, not user metadata).
- **Query performance escape hatch:** if a metadata key ever needs indexed
  filtering, Django 5 `GeneratedField` can expose a JSON key as a stored,
  indexable column (e.g. `size_x`) without a second write path. Postgres GIN
  indexes on the JSON column are the coarser alternative. Neither is needed
  on day one; today no view filters on `size_x`.

## 4. Pydantic metadata schemas

One pydantic model per measurement kind takes over the role the typed Django
columns played: field types, defaults, validators, editability semantics.

```python
# topobank/measurements/schemas.py  (core kinds; plugins ship their own)

class InstrumentMetadata(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    name: str = ""
    type: Literal["undefined", "microscope-based", "contact-based"] = "undefined"
    parameters: InstrumentParametersModel = InstrumentParametersModel()
    #            ^ already a pydantic model, from SurfaceTopography.Metadata

class MeasurementMetadata(pydantic.BaseModel):
    """Common base for all kinds."""
    model_config = pydantic.ConfigDict(extra="forbid")
    instrument: InstrumentMetadata = InstrumentMetadata()

class UniformLineScanMetadata(MeasurementMetadata):
    kind: Literal["uniform-line-scan"] = "uniform-line-scan"
    size_x: Optional[PositiveFloat] = None
    unit: Optional[LengthUnit] = None
    height_scale: float = 1.0
    is_periodic: bool = False
    detrend_mode: DetrendMode = "center"
    fill_undefined_data_mode: FillMode = "do-not-fill"

class NonuniformLineScanMetadata(MeasurementMetadata):
    kind: Literal["nonuniform-line-scan"] = "nonuniform-line-scan"
    size_x: Optional[PositiveFloat] = None
    unit: Optional[LengthUnit] = None
    height_scale: float = 1.0
    detrend_mode: DetrendMode = "center"
    # note: no is_periodic, no fill_undefined_data_mode — nonuniform scans
    # support neither; the schema now *encodes* what the editable-flag
    # machinery only hinted at
```

Notes:

- The three current kinds get **three distinct models**, as requested. The
  differences that today live in imperative code (`is_periodic_editable =
  False` for nonuniform scans, `size_y` only for maps) become structural:
  a field that doesn't apply simply doesn't exist on that schema, and
  `extra="forbid"` rejects it at validation time.
- Each schema carries `kind` as a `Literal` discriminator. This is slightly
  redundant with the `kind` column, but it makes the JSON self-describing
  (important for exported containers and published datasets) and enables a
  pydantic discriminated union (`TypeAdapter(Annotated[Union[...],
  Field(discriminator="kind")])`) for code that must parse metadata without a
  DB row in hand (container import). The column remains the source of truth
  for queries; `save()` asserts the two agree.
- `file_info` gets its own pydantic model per kind (`TopographyMapFileInfo`
  etc.), for the same reasons — validation of what the inspection task writes,
  and typed access in Python.
- **Validation points:** (1) `Measurement.save()` validates `metadata`
  against `get_type().Metadata` (mirroring how `WorkflowImplementation.
  clean_kwargs` validates workflow kwargs); (2) the REST serializers
  (downstream, in the API layer) call the same schema so users get 400s with
  pydantic error details instead of 500s; (3) container import validates via
  the discriminated union.
- **Typed access:** a cached property `Measurement.meta` returns the parsed
  pydantic instance; mutation goes through
  `measurement.update_metadata(**changes)` which validates, detects
  significant changes, and saves. The current `_significant_fields` set
  becomes a comparison of pydantic instances (the mechanism already used for
  `instrument_parameters` today), optionally excluding fields the schema
  marks as non-significant via `json_schema_extra={"significant": False}`.

## 5. `MeasurementType`: the pluggable strategy class

```python
# topobank/measurements/types.py

class MeasurementType(abc.ABC):
    class Meta:
        name: str            # stable registry key == Measurement.kind
        display_name: str    # human-readable

    Metadata: type[MeasurementMetadata]
    FileInfo: type[pydantic.BaseModel]

    # --- reading -----------------------------------------------------
    @abc.abstractmethod
    def read(self, measurement, apply_filters=True):
        """Construct and return the data object (e.g. a SurfaceTopography
        UniformLineScan). This is where dependencies on the underlying
        data package (SurfaceTopography, an XPS library, ...) live."""

    @abc.abstractmethod
    def inspect(self, measurement, channel) -> tuple[Metadata, FileInfo]:
        """Extract initial metadata and file-derived cache values from the
        selected channel of the data file (the core of today's
        refresh_cache())."""

    def is_metadata_complete(self, metadata) -> bool: ...

    # --- derived artifacts (capabilities) -----------------------------
    # Default implementations may raise NotSupported; the task runner and
    # (downstream) the UI check hasattr/capability flags.
    def make_thumbnail(self, measurement, data) -> bytes | None: ...
    def make_deepzoom(self, measurement, data) -> None: ...        # maps only
    def make_squeezed(self, measurement, data) -> Manifest | None: ...
    def refresh_derived_cache(self, measurement, data) -> FileInfo: ...
```

The three built-in types share a common intermediate base
(`SurfaceTopographyTypeBase`) that owns everything that goes through
`SurfaceTopography.IO` — reader construction, channel handling, the squeezed
NetCDF representation, detrend/fill filters — so the concrete classes are
small:

```python
@register_measurement_type
class TopographyMapType(SurfaceTopographyTypeBase):
    class Meta:
        name = "topography-map"
        display_name = "Topography map"
    Metadata = TopographyMapMetadata
    ...

@register_measurement_type
class UniformLineScanType(SurfaceTopographyTypeBase): ...

@register_measurement_type
class NonuniformLineScanType(SurfaceTopographyTypeBase): ...
```

A future XPS plugin would subclass `MeasurementType` directly and import its
own data package inside `read()`/`inspect()` — the core never imports it.

### Registry and discovery

Mirror the analysis-workflow registry (`register_implementation`):

```python
# topobank/measurements/registry.py
_types: dict[str, MeasurementType] = {}

def register_measurement_type(cls): ...          # decorator, raises on dup key
def get_measurement_type(name) -> MeasurementType: ...   # raises UnknownKind
def get_measurement_type_names() -> list[str]: ...
```

Discovery, two complementary mechanisms:

1. **Built-ins:** registered at import time from
   `topobank.measurements.apps.MeasurementsAppConfig.ready()` (same pattern as
   `ManagerAppConfig.ready()` importing `tasks`/`signals`).
2. **External packages:** a setuptools entry-point group
   `topobank.measurement_types`; each entry point resolves to a
   `MeasurementType` subclass (or a module whose import registers several).
   The core iterates the group in `ready()`. The dependency for this
   (`backports.entry-points-selectable`, annotated "Plugin handling") is
   already in `pyproject.toml`. Packages that are full Django plugin apps
   (like the existing analysis plugins) can instead register from their own
   `AppConfig.ready()` — both roads lead to the same registry.

`Measurement.get_type()` is then simply
`get_measurement_type(self.kind)`. A row whose kind is not registered (plugin
uninstalled) must degrade gracefully: the record stays visible/downloadable,
`read()` raises a clear `UnknownMeasurementKind` error, analyses are not
offered.

### Kind is a property of the *channel*, not the file

A single data file can contain multiple channels of different dimensionality
(one OPD file may hold a 2-D map and 1-D profiles). Therefore:

- The upload/inspection pipeline first opens the file with a **file reader**
  (today always `SurfaceTopography.IO`; the reader family used is recorded in
  `datafile_format`), enumerates channels, and derives the kind **per
  channel** (`dim == 2` → map; `dim == 1 and uniform` → uniform line scan;
  else nonuniform).
- `Measurement.kind` is set when a channel is selected (`data_source`), and
  **changing `data_source` may change `kind`** — inspection must re-derive
  the kind and re-validate/re-default `metadata` on channel switch. This is a
  real behavioral subtlety that today is handled implicitly by nullable
  columns; the plan makes it an explicit step in `refresh_cache`.
- To keep file opening pluggable too, the sniffing step iterates registered
  types via a classmethod `MeasurementType.sniff(manifest) ->
  list[ChannelInfo] | None` (first/best match wins). The three ST-based types
  share one sniffer in `SurfaceTopographyTypeBase`, so today there is exactly
  one file-opening code path, as now. If the ecosystem grows many readers,
  this can later be split into a separate `FileReader` registry without
  changing the `MeasurementType` API.

## 6. What moves out of `models.py`

`Topography.refresh_cache()` (~250 lines) is currently one monolith of
type-specific logic. After the change:

- **Stays on the model / task layer:** signal dispatch
  (`pre/post_refresh_cache`), task-state bookkeeping, manifest existence
  checks, the `TOPOBANK_REJECT_INCOMPLETE_METADATA` policy gate, saving.
- **Moves to `MeasurementType`:** channel enumeration and selection,
  populating `metadata` defaults from the file (first-read-only behavior),
  populating `file_info`, thumbnail/deep-zoom/squeezed generation, bandwidth
  computation. The "squeezed NetCDF" concept is topography-specific and
  becomes the ST base class's *canonical cached representation*; other kinds
  may have none, or a different one — the field name `squeezed_datafile`
  generalizes to something like `cache_datafile` in the rename phase.
- `Measurement.read()` becomes a thin delegation:
  `self.get_type().read(self, ...)`; the aliases `lazy_read` and the
  deprecated `topography` alias stay for compatibility.
- `TopobankLazySurfaceContainer` / `Surface.lazy_read()` must filter to kinds
  whose data objects are `SurfaceTopography` instances (a `SurfaceContainer`
  of XPS spectra is meaningless). Suggested: a capability flag on the type
  (`yields_surface_topography = True` on the ST base) and
  `surface.measurements.filter(kind__in=...)` in the container.

## 7. Analysis app integration

- `WorkflowResult.subject_topography` FK → `subject_measurement` (plus the
  composite index names and the `"topography:"` prefix inside stored
  `subject_hash` strings — the latter needs a data migration or, cheaper, the
  prefix constant simply stays `"topography"` forever as an opaque tag; the
  hash prefix never surfaces to users. Recommendation: keep the stored prefix
  stable, avoid rewriting millions of rows).
- **Dispatch must become kind-aware.** Today `WorkflowImplementation`
  dispatches on the Django model class of the subject
  (`Meta.implementations = {Topography: ..., Surface: ...}`). With one
  `Measurement` model for many kinds, that is no longer discriminating: a
  roughness workflow must run on the three height kinds but not on an XPS
  spectrum. Extend the implementation table to optional per-kind keys, with
  the model class as wildcard:

  ```python
  class Meta:
      implementations = {
          (Measurement, "topography-map"): "topography_implementation",
          (Measurement, "uniform-line-scan"): "line_scan_implementation",
          Surface: "surface_implementation",     # unchanged wildcard form
      }
  ```

  `get_implementation(subject)` resolves `(model, subject.kind)` first, then
  `(model, None)`. `has_implementation()` powers "which workflows does this
  measurement offer" in the UI, so unsupported kinds simply show nothing.
  This is additive and backwards compatible for existing plugin workflows
  (bare-model keys keep working, meaning "all kinds" — existing height
  workflows should be migrated to explicit kind keys as part of the rollout
  so they don't accidentally claim future kinds).

## 8. Import/export, publication

- `container_schema.py` (`index.json`) gains `kind` and a `metadata`
  passthrough per measurement, bumping the container format version. Import
  must keep accepting legacy containers: absent `kind`, infer it exactly like
  the DB backfill (§9) and map the legacy flat keys (`size`, `unit`,
  `height_scale`, `instrument`, …) into the new `metadata` dict.
- Published datasets are immutable — publication export/import paths must be
  able to round-trip both formats indefinitely.
- `to_dict()` on the model (used by export) reduces to mostly
  `self.metadata` + generic fields.

## 9. Migration & rollout plan (staged, four PR-sized phases)

The rename and the schema change are independently risky; do **not** combine
them in one release.

**Phase A — extract behavior, no schema change.**
Create `topobank/measurements/` (registry, schemas, type classes). The type
classes initially read/write the *existing columns* through a small adapter,
so `read()`, thumbnail/deep-zoom/squeezed generation, and the inspection core
move behind the `MeasurementType` interface while the DB is untouched.
Pydantic schemas exist and are exercised by tests, but validate data
assembled from columns. Pure refactor; fully revertible.

**Phase B — JSON schema migration.**
1. Add `kind`, `metadata`, `file_info` (all with defaults) — additive
   migration.
2. Data migration backfills every row: kind inference
   `resolution_y IS NOT NULL or size_y IS NOT NULL` → `topography-map`;
   else `is_periodic_editable == False` → `nonuniform-line-scan`; else
   `uniform-line-scan`. The heuristic is sound for rows that have been
   inspected; uninspected rows (`data_source IS NULL`) get kind assigned on
   their next `refresh_cache` anyway. Backfill validates each row through the
   pydantic schema and logs (not fails) on rows that don't validate.
3. Dual-write window: model property shims keep `size_x` & friends readable
   and writable (writing updates the JSON), so downstream code and the API
   keep working unmodified for one release.
4. Flip all core readers to the JSON path; `_significant_fields` logic moves
   to pydantic comparison.

**Phase C — the rename.**
`RenameModel` migration `Topography → Measurement` in `manager` (or move to
the new `measurements` app — recommendation: **keep it in `manager`**, moving
apps changes `app_label` and therefore content types, permissions and every
migration reference; the rename alone is enough churn). Details that need
explicit handling:
- `related_name="measurements"` on the surface FK, with a deprecated
  `Surface.topography_set` property shim for one release;
  `num_topographies()` likewise.
- `ContentType` rows: Django's `RenameModel` does *not* update the
  `django_content_type` table; add a small data migration updating
  `model="topography"` → `"measurement"` so `SubjectMixin.get_content_type()`
  and any stored generic references stay valid.
- Analysis app: rename `subject_topography` → `subject_measurement`
  (`RenameField`), keep the `subject_hash` prefix string stable (§7).
- Compatibility aliases for one minor release:
  `Topography = Measurement` in `manager/models.py` (with a
  `DeprecationWarning` on import via `__getattr__`), since the downstream
  UI/API repo and analysis plugins import it by name.
- `db_table` is renamed by `RenameModel` automatically
  (`manager_topography` → `manager_measurement`); if zero-downtime deploys
  matter, pin `Meta.db_table = "manager_topography"` in phase C and rename
  the table in a later, trivial migration once old code is gone.
- Storage prefix `topographies/{id}` for existing files must **not** change
  (S3 objects live there); new uploads may use `measurements/{id}` if the
  prefix is made kind-agnostic, or simply keep the old prefix forever —
  cheapest and safest.
- Celery deploy sequencing: in-flight task payloads reference model paths;
  drain queues or deploy workers and web in lockstep for this release.

**Phase D — cleanup.**
Drop the legacy columns (`size_x` … `instrument_parameters`,
`resolution_*`, `bandwidth_*`, editability flags), remove the property shims
and the `Topography` alias, rename `squeezed_datafile` if desired, migrate
existing workflow `Meta.implementations` to explicit per-kind keys, update
docs and `CHANGELOG.md`.

### Coordination with downstream repositories

This repo has no serializers/views — the REST API and frontend live in the
UI repository, and analysis plugins import `Topography` and its fields
directly. Sequencing: downstream repos can absorb Phase A/B with zero changes
(shims), must adapt imports and field access during the Phase C release
window (the alias keeps them running), and must be fully migrated before
Phase D. API strategy: **v1 endpoints keep the flat field layout** via
serializer methods mapping into `metadata` (so existing clients and the
published-dataset ecosystem see no change); **v2 exposes `kind` +
`metadata`/`file_info` verbatim**, with per-kind JSON schemas
(`Metadata.model_json_schema()`) served for form generation — the same trick
`list_workflow_schemas` already uses for workflow parameters.

## 10. Risks and open questions

- **Kind inference on backfill** is heuristic for rows never inspected;
  mitigated by re-inspection on next touch. Consider a management command to
  re-inspect all rows lacking `file_info` after Phase B.
- **Losing DB-level typing** on metadata: mitigated by pydantic validation on
  every write path; optionally a `CHECK (metadata ? 'kind')`-style constraint
  or GIN index later. Aggregations over metadata (if ever needed) use
  Postgres JSON operators or `GeneratedField`s.
- **Unregistered kinds** (plugin removed): rows must stay listable and
  deletable; only `read()`/analysis is blocked. Needs an explicit test.
- **`channel_names`/`data_source` generality:** the channel concept is
  currently assumed universal. It probably is (most instrument formats have
  channels), but a kind with no channel notion should be able to report a
  single default channel — keep these columns generic rather than moving them
  into `file_info`.
- **Thumbnails for arbitrary kinds:** rendering is a type capability; the
  grid UI needs a fallback tile for kinds without thumbnails.
- Should `bandwidth_*` stay queryable columns? The bandwidth plot reads them
  per surface (small N) — JSON is fine; revisit only if a cross-dataset query
  appears.
