"""Batch feature builder — run a whole Part Studio's feature tree from one MCP call.

Solves the per-feature round-trip tax that makes reproducing a known design
slow: 11 sequential MCP calls (sketch, extrude, sketch, ...) cost ~30-60s of
LLM thinking plus network latency stacked on top of the actual Onshape
regens. With `build_features`, the caller passes a list of feature specs
with NAMED REFS (`ref: "base"`) and the dispatcher chains them server-side,
resolving sketchRefs into the feature IDs Onshape minted as we go.

Supported ops (covers the Resultado pillow-block test case):
  sketch_rect / sketch_rounded_rect / sketch — produce sketches
  extrude — accepts `sketchRef` instead of `sketchFeatureId`
  fillet  — accepts `edgeFilter` (geometryType + lengthRangeMm etc.) so the
            caller does not need a list_entities round-trip first

Error policy: fail-fast. The first feature with `status != OK/INFO` halts
the batch; prior features stay (so caller can inspect via describe). The
return body lists every step's status so a re-run can pick up where it
broke. INFO is treated as success (matches the rest of the MCP).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..builders.sketch import SketchBuilder, SketchPlane
from ..builders.extrude import ExtrudeBuilder, ExtrudeEndType, ExtrudeType
from ..builders.fillet import FilletBuilder
from .feature_apply import apply_feature_and_check, FeatureApplyResult
from .entities import EntityManager
from .partstudio import PartStudioManager


class BuildContext:
    """Holds doc/workspace/element ids + the running ref→feature_id map."""

    def __init__(self, doc_id: str, ws_id: str, el_id: str, client: Any) -> None:
        self.doc_id = doc_id
        self.ws_id = ws_id
        self.el_id = el_id
        self.client = client
        self.refs: Dict[str, str] = {}
        self.results: List[Dict[str, Any]] = []
        self._entity_mgr = EntityManager(client)
        self._partstudio_mgr = PartStudioManager(client)
        self._plane_id_cache: Dict[str, str] = {}

    async def resolve_plane(
        self, spec: Dict[str, Any]
    ) -> tuple[str, SketchPlane]:
        """Resolve plane / faceId to (plane_id, SketchPlane enum).

        Caches standard plane IDs per part studio — they don't change once
        the Part Studio exists, so one fetch per plane name per batch is
        enough.
        """
        face_id = spec.get("faceId")
        if face_id:
            return face_id, SketchPlane.FRONT
        plane_name = spec.get("plane", "Front")
        cached = self._plane_id_cache.get(plane_name)
        if cached is None:
            cached = await self._partstudio_mgr.get_plane_id(
                self.doc_id, self.ws_id, self.el_id, plane_name
            )
            self._plane_id_cache[plane_name] = cached
        return cached, SketchPlane[plane_name.upper()]

    def register(self, ref: Optional[str], feature_id: str) -> None:
        if ref:
            if ref in self.refs:
                raise ValueError(f"duplicate ref {ref!r}")
            self.refs[ref] = feature_id

    def resolve_sketch(self, spec: Dict[str, Any]) -> str:
        ref = spec.get("sketchRef")
        fid = spec.get("sketchFeatureId")
        if fid:
            return fid
        if not ref:
            raise ValueError("extrude needs `sketchRef` or `sketchFeatureId`")
        if ref not in self.refs:
            raise ValueError(
                f"sketchRef {ref!r} not found; known refs: {list(self.refs)}"
            )
        return self.refs[ref]

    async def list_edges(self, edge_filter: Dict[str, Any]) -> List[str]:
        """Resolve an edge-filter spec into a deterministic edge-ID list.

        Filter keys mirror `list_entities` so callers don't need to learn a
        second vocabulary. Returns the edge IDs in body-order; callers can
        further narrow by passing tighter filters.
        """
        result = await self._entity_mgr.list_entities(
            self.doc_id,
            self.ws_id,
            self.el_id,
            kinds=["edges"],
            geometry_type=edge_filter.get("geometryType"),
            outward_axis=edge_filter.get("outwardAxis"),
            at_z_mm=edge_filter.get("atZmm"),
            at_z_tol_mm=edge_filter.get("atZtolMm", 0.5),
            radius_range_mm=edge_filter.get("radiusRangeMm"),
            length_range_mm=edge_filter.get("lengthRangeMm"),
        )
        edge_ids: List[str] = []
        for body in result.get("bodies", []) or []:
            for edge in body.get("edges", []) or []:
                eid = edge.get("id")
                if eid:
                    edge_ids.append(eid)
        return edge_ids


def _record(
    ctx: BuildContext,
    index: int,
    op: str,
    result: FeatureApplyResult,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    entry = {
        "index": index,
        "op": op,
        "ok": result.ok,
        "status": result.status,
        "feature_id": result.feature_id,
        "feature_name": result.feature_name,
    }
    if result.error_message:
        entry["error_message"] = result.error_message
    if extra:
        entry.update(extra)
    ctx.results.append(entry)


# ---------- per-op handlers ----------


async def _op_sketch_rect(ctx: BuildContext, spec: Dict[str, Any]) -> FeatureApplyResult:
    plane_id, plane_enum = await ctx.resolve_plane(spec)
    sketch = SketchBuilder(
        name=spec.get("name", "Sketch"), plane=plane_enum, plane_id=plane_id
    )
    sketch.add_rectangle(
        corner1=tuple(spec["corner1"]),
        corner2=tuple(spec["corner2"]),
    )
    return await apply_feature_and_check(
        ctx.client, ctx.doc_id, ctx.ws_id, ctx.el_id, sketch.build()
    )


async def _op_sketch_rounded_rect(
    ctx: BuildContext, spec: Dict[str, Any]
) -> FeatureApplyResult:
    plane_id, plane_enum = await ctx.resolve_plane(spec)
    sketch = SketchBuilder(
        name=spec.get("name", "Sketch"), plane=plane_enum, plane_id=plane_id
    )
    sketch.add_rounded_rectangle(
        corner1=tuple(spec["corner1"]),
        corner2=tuple(spec["corner2"]),
        corner_radius=spec["cornerRadius"],
    )
    return await apply_feature_and_check(
        ctx.client, ctx.doc_id, ctx.ws_id, ctx.el_id, sketch.build()
    )


async def _op_sketch(ctx: BuildContext, spec: Dict[str, Any]) -> FeatureApplyResult:
    plane_id, plane_enum = await ctx.resolve_plane(spec)
    sketch = SketchBuilder(
        name=spec.get("name", "Sketch"), plane=plane_enum, plane_id=plane_id
    )
    entities = spec.get("entities") or []
    if not entities:
        raise ValueError("sketch op requires non-empty `entities`")
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            raise ValueError(f"entities[{i}] must be an object")
        if ent.get("id"):
            sketch.add_entity_spec(ent)
            continue
        etype = (ent.get("type") or "").lower()
        if etype == "rectangle":
            sketch.add_rectangle(
                corner1=tuple(ent["corner1"]), corner2=tuple(ent["corner2"])
            )
        elif etype == "rounded_rectangle":
            sketch.add_rounded_rectangle(
                corner1=tuple(ent["corner1"]),
                corner2=tuple(ent["corner2"]),
                corner_radius=ent["cornerRadius"],
            )
        elif etype == "circle":
            sketch.add_circle(center=tuple(ent["center"]), radius=ent["radius"])
        elif etype == "line":
            sketch.add_line(start=tuple(ent["start"]), end=tuple(ent["end"]))
        elif etype == "arc":
            sketch.add_arc(
                center=tuple(ent["center"]),
                radius=ent["radius"],
                start_angle=ent.get("startAngle", 0),
                end_angle=ent.get("endAngle", 180),
            )
        else:
            raise ValueError(f"entities[{i}].type unsupported: {ent.get('type')!r}")
    for cspec in spec.get("constraints") or []:
        sketch.add_constraint_spec(cspec)
    return await apply_feature_and_check(
        ctx.client, ctx.doc_id, ctx.ws_id, ctx.el_id, sketch.build()
    )


async def _op_extrude(ctx: BuildContext, spec: Dict[str, Any]) -> FeatureApplyResult:
    sketch_fid = ctx.resolve_sketch(spec)
    raw_op = spec.get("operationType", "NEW")
    raw_end = spec.get("endType", "BLIND")
    try:
        op_type = ExtrudeType[raw_op]
    except KeyError as e:
        raise ValueError(
            f"operationType must be NEW|ADD|REMOVE|INTERSECT, got {raw_op!r}"
        ) from e
    try:
        end_type = ExtrudeEndType[raw_end]
    except KeyError as e:
        raise ValueError(f"endType must be BLIND|SYMMETRIC, got {raw_end!r}") from e
    builder = ExtrudeBuilder(
        name=spec.get("name", "Extrude"),
        sketch_feature_id=sketch_fid,
        operation_type=op_type,
        opposite_direction=bool(spec.get("oppositeDirection", False)),
        end_type=end_type,
    )
    builder.set_depth(spec["depth"])
    return await apply_feature_and_check(
        ctx.client,
        ctx.doc_id,
        ctx.ws_id,
        ctx.el_id,
        builder.build(),
        track_changes=False,
    )


async def _op_fillet(
    ctx: BuildContext, spec: Dict[str, Any]
) -> tuple[FeatureApplyResult, Dict[str, Any]]:
    edge_ids = spec.get("edgeIds")
    extra: Dict[str, Any] = {}
    if not edge_ids:
        edge_filter = spec.get("edgeFilter")
        if not edge_filter:
            raise ValueError("fillet needs `edgeIds` or `edgeFilter`")
        edge_ids = await ctx.list_edges(edge_filter)
        if not edge_ids:
            raise ValueError(
                f"edgeFilter {edge_filter} matched zero edges in current part state"
            )
        extra["resolved_edge_ids"] = edge_ids
    builder = FilletBuilder(name=spec.get("name", "Fillet"), radius=spec["radius"])
    for eid in edge_ids:
        builder.add_edge(eid)
    result = await apply_feature_and_check(
        ctx.client,
        ctx.doc_id,
        ctx.ws_id,
        ctx.el_id,
        builder.build(),
        track_changes=False,
    )
    return result, extra


# ---------- top-level dispatcher ----------


async def build_features(
    client: Any,
    document_id: str,
    workspace_id: str,
    element_id: str,
    features: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply features in order. Returns one dict with every step's outcome.

    Fail-fast: stops at the first step that returns status ERROR or that
    raises during dispatch. Prior features are NOT rolled back — they stay
    in the part studio so the caller can inspect, fix the failing spec, and
    re-run with the remaining suffix.
    """
    ctx = BuildContext(document_id, workspace_id, element_id, client)

    if not isinstance(features, list) or not features:
        raise ValueError("`features` must be a non-empty list")

    for i, spec in enumerate(features):
        if not isinstance(spec, dict):
            raise ValueError(f"features[{i}] must be an object")
        op = spec.get("op")
        ref = spec.get("ref")
        try:
            if op == "sketch_rect":
                result = await _op_sketch_rect(ctx, spec)
                extra = None
            elif op == "sketch_rounded_rect":
                result = await _op_sketch_rounded_rect(ctx, spec)
                extra = None
            elif op == "sketch":
                result = await _op_sketch(ctx, spec)
                extra = None
            elif op == "extrude":
                result = await _op_extrude(ctx, spec)
                extra = None
            elif op == "fillet":
                result, extra = await _op_fillet(ctx, spec)
            else:
                raise ValueError(
                    f"unknown op {op!r}; supported: sketch_rect, sketch_rounded_rect, "
                    "sketch, extrude, fillet"
                )
        except Exception as e:
            ctx.results.append(
                {
                    "index": i,
                    "op": op,
                    "ref": ref,
                    "ok": False,
                    "status": "ERROR",
                    "error_message": f"{type(e).__name__}: {e}",
                }
            )
            return {
                "ok": False,
                "completed_steps": i,
                "total_steps": len(features),
                "failed_at_index": i,
                "refs": ctx.refs,
                "results": ctx.results,
            }

        _record(ctx, i, op, result, extra)
        if result.ok:
            ctx.register(ref, result.feature_id)
        else:
            return {
                "ok": False,
                "completed_steps": i,
                "total_steps": len(features),
                "failed_at_index": i,
                "refs": ctx.refs,
                "results": ctx.results,
            }

    return {
        "ok": True,
        "completed_steps": len(features),
        "total_steps": len(features),
        "refs": ctx.refs,
        "results": ctx.results,
    }
