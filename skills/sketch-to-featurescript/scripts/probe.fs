FeatureScript 2909;
import(path : "onshape/std/geometry.fs", version : "2909.0");

// API probe for sketch-to-featurescript. Seeds are deliberately wrong: the
// solver must move them for the expected volumes to come out exact.
//   A (NEW, then ADD + REMOVE): 20x10x5 box, +Ø6 symmetric 10, -Ø4 through all
//        -> 1000 + 25*pi = 1078.540 mm3, Z -5..5
//   B (NEW, symmetric 6): annulus OD10 / ID4 -> 126*pi = 395.841 mm3, Z -3..3
//   C (NEW, blind 8): slot, arcs R3 at 10 apart -> (60 + 9*pi)*8 = 706.195 mm3

const W_BOUNDS = { (millimeter) : [0.1, 20, 1000] } as LengthBoundSpec;

annotation { "Feature Type Name" : "Sketchgen probe" }
export const sketchgenProbe = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "w" }
        isLength(definition.w, W_BOUNDS);
    }
    {
        const top = plane(vector(0, 0, 0) * meter, vector(0, 0, 1), vector(1, 0, 0));
        const mm = millimeter;

        // ---- A: lines, FIX, COINCIDENT, HORIZONTAL, VERTICAL, PARALLEL, ANGLE, LENGTH, DISTANCE(vertical)
        const a = newSketchOnPlane(context, id + "A", { "sketchPlane" : top });
        skPoint(a, "pO", { "position" : vector(0, 0) * mm });
        skLineSegment(a, "b", { "start" : vector(0, 0) * mm, "end" : vector(18, 1) * mm });
        skLineSegment(a, "r", { "start" : vector(18, 1) * mm, "end" : vector(19, 9) * mm });
        skLineSegment(a, "t", { "start" : vector(19, 9) * mm, "end" : vector(1, 11) * mm });
        skLineSegment(a, "l", { "start" : vector(1, 11) * mm, "end" : vector(0, 0) * mm });
        skConstraint(a, "c1", { "constraintType" : ConstraintType.FIX, "localFirst" : "pO" });
        skConstraint(a, "c2", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "b.start", "localSecond" : "pO" });
        skConstraint(a, "c3", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "b.end", "localSecond" : "r.start" });
        skConstraint(a, "c4", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "r.end", "localSecond" : "t.start" });
        skConstraint(a, "c5", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "t.end", "localSecond" : "l.start" });
        skConstraint(a, "c6", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "l.end", "localSecond" : "b.start" });
        skConstraint(a, "c7", { "constraintType" : ConstraintType.HORIZONTAL, "localFirst" : "b" });
        skConstraint(a, "c8", { "constraintType" : ConstraintType.VERTICAL, "localFirst" : "l" });
        skConstraint(a, "c9", { "constraintType" : ConstraintType.PARALLEL, "localFirst" : "t", "localSecond" : "b" });
        skConstraint(a, "c10", { "constraintType" : ConstraintType.ANGLE, "localFirst" : "b", "localSecond" : "r", "angle" : 90 * degree });
        skConstraint(a, "c11", { "constraintType" : ConstraintType.LENGTH, "localFirst" : "b", "length" : definition.w });
        skConstraint(a, "c12", { "constraintType" : ConstraintType.DISTANCE, "localFirst" : "pO", "localSecond" : "t.end",
                    "length" : 10 * mm, "direction" : DimensionDirection.VERTICAL });
        // extra circles for the ADD / REMOVE tests
        skCircle(a, "hole", { "center" : vector(5.5, 4.5) * mm, "radius" : 1 * mm });
        skCircle(a, "boss", { "center" : vector(14, 6) * mm, "radius" : 2 * mm });
        skConstraint(a, "c13", { "constraintType" : ConstraintType.DIAMETER, "localFirst" : "hole", "length" : 4 * mm });
        skConstraint(a, "c14", { "constraintType" : ConstraintType.DIAMETER, "localFirst" : "boss", "length" : 6 * mm });
        skConstraint(a, "c15", { "constraintType" : ConstraintType.DISTANCE, "localFirst" : "pO", "localSecond" : "hole.center",
                    "length" : 5 * mm, "direction" : DimensionDirection.HORIZONTAL });
        skConstraint(a, "c16", { "constraintType" : ConstraintType.DISTANCE, "localFirst" : "pO", "localSecond" : "hole.center",
                    "length" : 5 * mm, "direction" : DimensionDirection.VERTICAL });
        skConstraint(a, "c17", { "constraintType" : ConstraintType.DISTANCE, "localFirst" : "pO", "localSecond" : "boss.center",
                    "length" : 15 * mm, "direction" : DimensionDirection.HORIZONTAL });
        skConstraint(a, "c18", { "constraintType" : ConstraintType.DISTANCE, "localFirst" : "pO", "localSecond" : "boss.center",
                    "length" : 5 * mm, "direction" : DimensionDirection.VERTICAL });
        skSolve(a);

        // ---- B: circles, CONCENTRIC, RADIUS, symmetric extrude
        const b = newSketchOnPlane(context, id + "B", { "sketchPlane" : top });
        skPoint(b, "pB", { "position" : vector(40, 0) * mm });
        skCircle(b, "outer", { "center" : vector(41, 1) * mm, "radius" : 3 * mm });
        skCircle(b, "inner", { "center" : vector(40.5, 0.3) * mm, "radius" : 1 * mm });
        skConstraint(b, "c1", { "constraintType" : ConstraintType.FIX, "localFirst" : "pB" });
        skConstraint(b, "c2", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "outer.center", "localSecond" : "pB" });
        skConstraint(b, "c3", { "constraintType" : ConstraintType.DIAMETER, "localFirst" : "outer", "length" : 10 * mm });
        skConstraint(b, "c4", { "constraintType" : ConstraintType.CONCENTRIC, "localFirst" : "inner", "localSecond" : "outer" });
        skConstraint(b, "c5", { "constraintType" : ConstraintType.RADIUS, "localFirst" : "inner", "length" : 2 * mm });
        skSolve(b);

        // ---- C: arcs, TANGENT, EQUAL, MIDPOINT, PERPENDICULAR, construction
        const c = newSketchOnPlane(context, id + "C", { "sketchPlane" : top });
        skPoint(c, "pm", { "position" : vector(20, 30) * mm });
        skLineSegment(c, "axis", { "start" : vector(14, 30.5) * mm, "end" : vector(26, 29.5) * mm, "construction" : true });
        skLineSegment(c, "perp", { "start" : vector(20, 30) * mm, "end" : vector(21, 36) * mm, "construction" : true });
        skArc(c, "left", { "start" : vector(15, 33) * mm, "mid" : vector(12, 30) * mm, "end" : vector(15, 27) * mm });
        skArc(c, "right", { "start" : vector(25, 27) * mm, "mid" : vector(28.5, 30) * mm, "end" : vector(25, 33.5) * mm });
        skLineSegment(c, "top", { "start" : vector(25, 33.5) * mm, "end" : vector(15, 33) * mm });
        skLineSegment(c, "bot", { "start" : vector(15, 27) * mm, "end" : vector(25, 27) * mm });
        skConstraint(c, "c1", { "constraintType" : ConstraintType.FIX, "localFirst" : "pm" });
        skConstraint(c, "c2", { "constraintType" : ConstraintType.MIDPOINT, "localFirst" : "pm", "localSecond" : "axis" });
        skConstraint(c, "c3", { "constraintType" : ConstraintType.HORIZONTAL, "localFirst" : "axis" });
        skConstraint(c, "c4", { "constraintType" : ConstraintType.LENGTH, "localFirst" : "axis", "length" : 10 * mm });
        skConstraint(c, "c5", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "left.center", "localSecond" : "axis.start" });
        skConstraint(c, "c6", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "right.center", "localSecond" : "axis.end" });
        skConstraint(c, "c7", { "constraintType" : ConstraintType.RADIUS, "localFirst" : "left", "length" : 3 * mm });
        skConstraint(c, "c8", { "constraintType" : ConstraintType.EQUAL, "localFirst" : "right", "localSecond" : "left" });
        skConstraint(c, "c9", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "left.start", "localSecond" : "top.end" });
        skConstraint(c, "c10", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "left.end", "localSecond" : "bot.start" });
        skConstraint(c, "c11", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "right.start", "localSecond" : "bot.end" });
        skConstraint(c, "c12", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "right.end", "localSecond" : "top.start" });
        skConstraint(c, "c13", { "constraintType" : ConstraintType.TANGENT, "localFirst" : "top", "localSecond" : "left" });
        skConstraint(c, "c14", { "constraintType" : ConstraintType.TANGENT, "localFirst" : "top", "localSecond" : "right" });
        skConstraint(c, "c15", { "constraintType" : ConstraintType.TANGENT, "localFirst" : "bot", "localSecond" : "left" });
        skConstraint(c, "c16", { "constraintType" : ConstraintType.TANGENT, "localFirst" : "bot", "localSecond" : "right" });
        skConstraint(c, "c17", { "constraintType" : ConstraintType.COINCIDENT, "localFirst" : "perp.start", "localSecond" : "pm" });
        skConstraint(c, "c18", { "constraintType" : ConstraintType.PERPENDICULAR, "localFirst" : "perp", "localSecond" : "axis" });
        skSolve(c);

        // ---- extrudes (std extrude called from a custom feature)
        const regionA = qContainsPoint(qSketchRegion(id + "A", false), planeToWorld(top, vector(2, 8) * mm));
        extrude(context, id + "eA", { "entities" : regionA, "operationType" : NewBodyOperationType.NEW,
                    "endBound" : BoundingType.BLIND, "depth" : 5 * mm });
        const bossA = qContainsPoint(qSketchRegion(id + "A", false), planeToWorld(top, vector(15, 5) * mm));
        extrude(context, id + "eBoss", { "entities" : bossA, "operationType" : NewBodyOperationType.ADD,
                    "endBound" : BoundingType.BLIND, "depth" : 10 * mm, "symmetric" : true, "defaultScope" : true });
        const holeA = qContainsPoint(qSketchRegion(id + "A", false), planeToWorld(top, vector(5, 5) * mm));
        extrude(context, id + "eHole", { "entities" : holeA, "operationType" : NewBodyOperationType.REMOVE,
                    "endBound" : BoundingType.THROUGH_ALL, "symmetric" : true, "defaultScope" : true });
        const annulus = qContainsPoint(qSketchRegion(id + "B", false), planeToWorld(top, vector(43.5, 0) * mm));
        extrude(context, id + "eB", { "entities" : annulus, "operationType" : NewBodyOperationType.NEW,
                    "endBound" : BoundingType.BLIND, "depth" : 6 * mm, "symmetric" : true });
        const slot = qContainsPoint(qSketchRegion(id + "C", false), planeToWorld(top, vector(20, 31) * mm));
        extrude(context, id + "eC", { "entities" : slot, "operationType" : NewBodyOperationType.NEW,
                    "endBound" : BoundingType.BLIND, "depth" : 8 * mm });

        setProperty(context, { "entities" : qCreatedBy(id, EntityType.BODY),
                    "propertyType" : PropertyType.MATERIAL,
                    "value" : material("Steel", 7850 * kilogram / meter ^ 3) });
    });
