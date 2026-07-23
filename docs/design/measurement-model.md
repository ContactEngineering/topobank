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
  spectrum. **Decision:** keep one implementation per subject model and add a
  declarative gate:

  ```python
  class Meta:
      implementations = {
          Measurement: "measurement_implementation",
          Surface: "surface_implementation",
      }
      supported_kinds = {
          "topography-map", "uniform-line-scan", "nonuniform-line-scan",
      }
  ```

  This matches current reality — today a single `topography_implementation`
  already handles maps and both line-scan flavors by branching on the data
  object's `dim` — and minimizes churn for plugin workflows.
  `has_implementation(subject)` checks membership of `subject.kind` in
  `supported_kinds` (and powers "which workflows does this measurement
  offer" in the UI, so unsupported kinds simply show nothing);
  `eval()` refuses to run on unsupported kinds with
  `WorkflowNotImplementedException`. A missing `supported_kinds` on a
  workflow is an error, not a wildcard — existing workflows must declare the
  three height kinds explicitly so they don't silently claim future kinds.
  If a workflow ever genuinely needs different code paths per kind,
  per-kind implementation keys can be added later as a purely additive
  extension; we deliberately do not ship that now.

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

## 9. Migration & rollout plan

**Decision:** topobank, the UI/API repository, and the analysis plugins are
deployed in lockstep as one coordinated release, with **no compatibility
shims** — no dual-write property shims for the old columns, no
`Topography = Measurement` import alias, no `topography_set` shim. Anything
out of tree that imports `Topography` breaks at the coordinated release and
must be updated with it. This trades deploy risk for a clean cut: no shim
code to write, test, and later remove, and no release where both data paths
are live.

The work still splits into two steps, but only the second one is a release
boundary:

**Step 1 — extract behavior, no schema change (independent, revertible PR).**
Create `topobank/measurements/` (registry, schemas, type classes). The type
classes initially read/write the *existing columns* through a small adapter,
so `read()`, thumbnail/deep-zoom/squeezed generation, and the inspection core
move behind the `MeasurementType` interface while the DB is untouched.
Pydantic schemas exist and are exercised by tests, but validate data
assembled from columns. Pure refactor; deployable on its own; fully
revertible. Doing this first keeps the breaking release small and mostly
mechanical.

**Step 2 — the coordinated breaking release.**
One release containing, in this order within the migration sequence:

1. Additive migration: add `kind`, `metadata`, `file_info` (with defaults),
   plus the CHECK constraint `kind = metadata->>'kind'` (§10).
2. Data migration backfilling every row (**decision: heuristic only, no mass
   re-inspection**): `resolution_y IS NOT NULL or size_y IS NOT NULL` →
   `topography-map`; else `is_periodic_editable == False` →
   `nonuniform-line-scan`; else `uniform-line-scan`. The heuristic is sound
   for rows that completed inspection; uninspected rows
   (`data_source IS NULL`) get kind assigned on their next `refresh_cache`
   anyway. Backfill validates each row through the pydantic schema and logs
   (not fails) on rows that don't validate. A report-only management command
   flags rows whose backfilled kind disagrees with a later inspection, so a
   full re-inspection sweep (one S3 read per measurement) is only ever run
   if that report shows a real problem.
3. `RenameModel` migration `Topography → Measurement`, staying in the
   `manager` app (moving apps changes `app_label` and therefore content
   types, permissions and every migration reference; the rename alone is
   enough churn). `related_name="measurements"` on the surface FK;
   `num_topographies()` → `num_measurements()`.
4. Data migration updating `django_content_type` rows
   (`model="topography"` → `"measurement"`) — Django's `RenameModel` does
   *not* do this, and `SubjectMixin.get_content_type()` and stored generic
   references depend on it.
5. Analysis app: `RenameField` `subject_topography` → `subject_measurement`
   (and the composite index names). The `"topography:"` prefix inside stored
   `subject_hash` strings stays as an opaque tag forever (§7) — no row
   rewrite.
6. Drop the legacy columns (`size_x` … `instrument_parameters`,
   `resolution_*`, `bandwidth_*`, editability flags) and flip all readers to
   the JSON path; `_significant_fields` logic moves to pydantic comparison.
   Existing workflows gain explicit `supported_kinds` declarations.

Operational notes for that release:
- `db_table` is renamed by `RenameModel` automatically
  (`manager_topography` → `manager_measurement`). Since the release is not
  zero-downtime anyway (see next point), let the rename happen; pinning
  `Meta.db_table` buys nothing under lockstep.
- Storage prefix `topographies/{id}` for existing files must **not** change
  (S3 objects live there). Keep the old prefix forever — cheapest and
  safest; making it kind-agnostic for new uploads is optional polish.
- Celery: drain task queues before the deploy and take the site into
  maintenance for the migration window. In-flight task payloads reference
  model paths that will not survive the rename, and there is deliberately no
  compatibility alias to catch them.
- Rehearse the full migration sequence against a production DB snapshot; the
  backfill touches every measurement row.

### Coordination with downstream repositories

This repo has no serializers/views — the REST API and frontend live in the
UI repository, and analysis plugins import `Topography` and its fields
directly. Under lockstep, both are updated and released together with
Step 2. API strategy remains a downstream decision, but note that without
dual-write in the model, keeping the **v1 endpoints' flat field layout**
means the v1 serializers map flat fields into `metadata` themselves (entirely
possible — serializer-level translation, no model support needed); **v2
exposes `kind` + `metadata`/`file_info` verbatim**, with per-kind JSON
schemas (`Metadata.model_json_schema()`) served for form generation — the
same trick `list_workflow_schemas` already uses for workflow parameters.

## 10. Resolved decisions and remaining open questions

The following were discussed and decided (2026-07-23):

- **Workflow dispatch:** `Meta.supported_kinds` gate on a single
  implementation per subject model (§7). Per-kind implementation keys are a
  possible later additive extension, not shipped now.
- **Schema home:** the pydantic schemas for the three built-in height kinds
  live in **topobank**, next to their `MeasurementType` classes. Only
  `InstrumentParametersModel` keeps coming from `SurfaceTopography.Metadata`.
  This decouples web-app schema evolution (defaults, editability semantics)
  from SurfaceTopography releases. Plugin packages are still free to ship
  data class and schema together — the contract only requires that the
  registered `MeasurementType` points at *a* schema.
- **Rollout:** lockstep coordinated release, no compatibility shims (§9).
- **Backfill:** heuristic only; report-only disagreement command instead of a
  mass re-inspection sweep (§9).
- **DB-level typing:** rely on pydantic at every write path. Single
  kind-agnostic CHECK constraint `kind = metadata->>'kind'` to catch
  column/JSON drift; no per-kind DB constraints, no GIN index or
  `GeneratedField` until a real query needs one.
- **Unregistered kinds** (plugin removed): rows stay listable, downloadable,
  and deletable; `read()` raises `UnknownMeasurementKind`; analyses are not
  offered; metadata editing is blocked (no schema to validate against).
  `save()` skips metadata validation when the kind is unregistered and
  `metadata` is not among the changed fields, so unrelated bulk operations
  keep working. Each of these behaviors needs an explicit test.
- **`channel_names`/`data_source`:** stay as real columns. `data_source` is
  user-selected state (not file-derived cache), and `kind` is derived from
  the selected channel. Kinds without a channel notion report a single
  default channel.
- **Thumbnails:** expected for every kind, not optional. Core provides a
  generic 1-D curve renderer (the existing matplotlib path) that
  spectrum-like types get nearly for free; the ST base provides the 2-D
  colormap path; a type that truly cannot render gets a static per-kind icon
  served by the registry, so the grid UI never special-cases. Deep zoom
  remains a capability only maps implement.
- **`bandwidth_*`:** move into `file_info`. All known reads are per surface
  (small N); the fields are meaningless for non-height kinds. Revisit only
  if a cross-dataset bandwidth query (e.g. search facet) appears.

Still open:

- **Publishing datasets that contain an unknown-kind measurement:** leaning
  *allow* (the raw file and its self-describing metadata JSON are immutable
  and archivable regardless of installed plugins), but this is a policy call
  to be confirmed before implementation.
- **Universality of the channel model:** the design assumes every instrument
  file fits "a file contains N named channels". No counterexample known;
  flag during review of the first non-height plugin.
