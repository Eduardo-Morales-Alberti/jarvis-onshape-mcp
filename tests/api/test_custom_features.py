"""Unit tests for custom-feature uploads: inputs from files, Feature Studio
reuse, and in-place update of an existing feature instance."""

import json

import pytest
from unittest.mock import AsyncMock, patch

from onshape_mcp.api.custom_features import (
    CustomFeatureManager,
    resolve_featurescript_inputs,
)
from onshape_mcp.api.feature_apply import FeatureApplyResult

SRC = 'FeatureScript 2909;\nexport const myFeat = defineFeature(function(context, id, definition) {});\n'


def _ok(feature_id="F1"):
    return FeatureApplyResult(ok=True, status="OK", feature_id=feature_id,
                              feature_name="n", feature_type="myFeat")


class TestResolveInputs:
    def test_inline(self):
        out = resolve_featurescript_inputs(feature_script=SRC, feature_type="myFeat")
        assert out == {"feature_script": SRC, "feature_type": "myFeat", "parameters": None}

    def test_from_files(self, tmp_path):
        fs = tmp_path / "part.fs"
        fs.write_text(SRC)
        params = tmp_path / "fs_params.json"
        params.write_text(json.dumps({"featureType": "myFeat",
                                      "parameters": [{"id": "w", "type": "quantity", "value": "20 mm"}]}))
        out = resolve_featurescript_inputs(feature_script_path=str(fs), parameters_path=str(params))
        assert out["feature_script"] == SRC
        assert out["feature_type"] == "myFeat"
        assert out["parameters"][0]["id"] == "w"

    def test_explicit_arguments_win_over_parameters_file(self, tmp_path):
        params = tmp_path / "p.json"
        params.write_text(json.dumps({"featureType": "fromFile", "parameters": [{"id": "a", "type": "real"}]}))
        out = resolve_featurescript_inputs(feature_script=SRC, feature_type="explicit",
                                           parameters=[], parameters_path=str(params))
        assert out["feature_type"] == "explicit"
        assert out["parameters"] == []

    @pytest.mark.parametrize("kwargs", [
        {},                                              # neither source
        {"feature_script": SRC, "feature_script_path": "/x.fs"},  # both
    ])
    def test_exactly_one_source(self, kwargs):
        with pytest.raises(ValueError, match="exactly one"):
            resolve_featurescript_inputs(feature_type="myFeat", **kwargs)

    def test_rejects_relative_or_non_fs_path(self, tmp_path):
        with pytest.raises(ValueError, match="absolute path"):
            resolve_featurescript_inputs(feature_script_path="part.fs", feature_type="t")
        other = tmp_path / "part.txt"
        other.write_text(SRC)
        with pytest.raises(ValueError, match="absolute path"):
            resolve_featurescript_inputs(feature_script_path=str(other), feature_type="t")

    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            resolve_featurescript_inputs(feature_script_path=str(tmp_path / "nope.fs"), feature_type="t")

    def test_feature_type_required(self):
        with pytest.raises(ValueError, match="featureType is required"):
            resolve_featurescript_inputs(feature_script=SRC)


class TestApplyReuse:
    @pytest.fixture
    def manager(self, onshape_client):
        m = CustomFeatureManager(onshape_client)
        m.create_feature_studio = AsyncMock(return_value="FS_NEW")
        m.upload_fs_source = AsyncMock(return_value={"microversionId": "mv1"})
        m.get_featurespecs = AsyncMock(return_value={
            "featureSpecs": [{"featureType": "myFeat", "sourceMicroversionId": "mv1"}],
            "libraryVersion": 3083})
        return m

    @pytest.mark.asyncio
    async def test_default_creates_studio_and_feature(self, manager, sample_document_ids):
        with patch("onshape_mcp.api.custom_features.apply_feature_and_check",
                   AsyncMock(return_value=_ok())) as apply:
            out = await manager.apply_featurescript_feature(
                sample_document_ids["document_id"], sample_document_ids["workspace_id"],
                sample_document_ids["element_id"],
                feature_type="myFeat", feature_script=SRC, feature_name="n")
        manager.create_feature_studio.assert_awaited_once()
        assert out["fs_element_id"] == "FS_NEW"
        assert apply.await_args.kwargs["operation"] == "create"
        assert "featureId" not in apply.await_args.args[4]["feature"]

    @pytest.mark.asyncio
    async def test_reuses_studio_and_updates_feature(self, manager, sample_document_ids):
        with patch("onshape_mcp.api.custom_features.apply_feature_and_check",
                   AsyncMock(return_value=_ok("F_OLD"))) as apply:
            out = await manager.apply_featurescript_feature(
                sample_document_ids["document_id"], sample_document_ids["workspace_id"],
                sample_document_ids["element_id"],
                feature_type="myFeat", feature_script=SRC, feature_name="n",
                fs_element_id="FS_OLD", feature_id="F_OLD")
        manager.create_feature_studio.assert_not_awaited()
        assert manager.upload_fs_source.await_args.args[2] == "FS_OLD"
        assert out["fs_element_id"] == "FS_OLD"
        kwargs = apply.await_args.kwargs
        assert kwargs["operation"] == "update" and kwargs["feature_id"] == "F_OLD"
        feature = apply.await_args.args[4]["feature"]
        assert feature["featureId"] == "F_OLD"
        assert feature["namespace"] == "eFS_OLD::mmv1"


class TestPostEval:
    def test_read_inline_and_path(self, tmp_path):
        from onshape_mcp.api.custom_features import read_post_eval_script
        assert read_post_eval_script("function(c, q) { return 1; }") == "function(c, q) { return 1; }"
        f = tmp_path / "validate.fs"
        f.write_text("function(c, q) { return 2; }")
        assert read_post_eval_script(script_path=str(f)) == "function(c, q) { return 2; }"
        assert read_post_eval_script() is None
        with pytest.raises(ValueError):
            read_post_eval_script("x", str(f))
        with pytest.raises(ValueError):
            read_post_eval_script(script_path="validate.fs")

    def test_fs_value_to_python(self):
        from onshape_mcp.api.custom_features import fs_value_to_python
        v = {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueMap", "value": [
            {"key": {"btType": "x.BTFSValueString", "value": "mass_g"},
             "value": {"btType": "x.BTFSValueNumber", "value": 891.754}},
            {"key": {"btType": "x.BTFSValueString", "value": "ok"},
             "value": {"btType": "x.BTFSValueBoolean", "value": True}},
            {"key": {"btType": "x.BTFSValueString", "value": "list"},
             "value": {"btType": "x.BTFSValueArray", "value": [{"btType": "x.BTFSValueNumber", "value": 1}]}}]}
        assert fs_value_to_python(v) == {"mass_g": 891.754, "ok": True, "list": [1]}
