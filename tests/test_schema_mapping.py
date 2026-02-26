"""
Stage 4 — JSON Schema Mapping Specification Tests

Validates that:
1. ogc-mcp-mapping-instance.json is valid JSON
2. ogc-mcp-mapping.schema.json is valid JSON  
3. The instance validates against the schema
4. All 5 required mapping categories exist (common, features, records, edr, processes)
5. Every mapping rule has required fields (ogc_concept, mcp_primitive, rationale, mapping_details)
6. mcp_primitive values are only "Tool", "Resource", or "Prompt"
7. Mapping counts match expected totals (20 Tools, 5 Resources, 4 Prompts)

Run with: pytest tests/test_schema_mapping.py -v
"""

import json
import os
import pytest

# ─────────────────────────────────────────────
# Path setup — works from project root
# ─────────────────────────────────────────────

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'schemas')
SCHEMA_PATH = os.path.join(SCHEMAS_DIR, 'ogc-mcp-mapping.schema.json')
INSTANCE_PATH = os.path.join(SCHEMAS_DIR, 'ogc-mcp-mapping-instance.json')

VALID_MCP_PRIMITIVES = {"Tool", "Resource", "Prompt"}
REQUIRED_MAPPING_CATEGORIES = {"common", "features", "records", "edr", "processes"}
REQUIRED_RULE_FIELDS = {"ogc_concept", "mcp_primitive", "rationale", "mapping_details"}


# ─────────────────────────────────────────────
# Fixtures — load files once, reuse in all tests
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def schema():
    """Load the meta-schema."""
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def instance():
    """Load the concrete mapping instance."""
    with open(INSTANCE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_rules(instance):
    """Extract every mapping rule from the instance as (category, name, rule) tuples."""
    rules = []
    for category, category_mappings in instance["mappings"].items():
        for rule_name, rule in category_mappings.items():
            rules.append((category, rule_name, rule))
    return rules


# ─────────────────────────────────────────────
# Test 1: Files exist and are valid JSON
# ─────────────────────────────────────────────

def test_schema_file_exists():
    assert os.path.exists(SCHEMA_PATH), f"Schema file not found: {SCHEMA_PATH}"


def test_instance_file_exists():
    assert os.path.exists(INSTANCE_PATH), f"Instance file not found: {INSTANCE_PATH}"


def test_schema_is_valid_json(schema):
    assert isinstance(schema, dict), "Schema should parse as a JSON object"
    assert "$schema" in schema, "Schema should have a $schema field"


def test_instance_is_valid_json(instance):
    assert isinstance(instance, dict), "Instance should parse as a JSON object"
    assert "metadata" in instance, "Instance should have a metadata field"
    assert "mappings" in instance, "Instance should have a mappings field"


# ─────────────────────────────────────────────
# Test 2: Schema validates instance (if jsonschema is installed)
# ─────────────────────────────────────────────

def test_instance_validates_against_schema(schema, instance):
    """Validate the instance against the meta-schema using jsonschema."""
    try:
        import jsonschema
        jsonschema.validate(instance=instance, schema=schema)
    except ImportError:
        pytest.skip("jsonschema not installed — skipping formal validation")
    except jsonschema.ValidationError as e:
        pytest.fail(f"Instance failed schema validation: {e.message}")


# ─────────────────────────────────────────────
# Test 3: Metadata is complete
# ─────────────────────────────────────────────

def test_metadata_has_version(instance):
    assert "version" in instance["metadata"]
    assert instance["metadata"]["version"] == "1.0.0"


def test_metadata_has_mcp_version(instance):
    assert "mcp_version" in instance["metadata"]
    assert "2025" in instance["metadata"]["mcp_version"]


def test_metadata_has_license(instance):
    assert instance["metadata"]["license"] == "Apache-2.0"


def test_metadata_has_ogc_api_versions(instance):
    versions = instance["metadata"]["ogc_api_versions"]
    for api in ["common", "features", "records", "edr", "processes"]:
        assert api in versions, f"Missing OGC API version for: {api}"


# ─────────────────────────────────────────────
# Test 4: All required mapping categories exist
# ─────────────────────────────────────────────

def test_all_mapping_categories_present(instance):
    categories = set(instance["mappings"].keys())
    assert REQUIRED_MAPPING_CATEGORIES.issubset(categories), (
        f"Missing categories: {REQUIRED_MAPPING_CATEGORIES - categories}"
    )


@pytest.mark.parametrize("category", sorted(REQUIRED_MAPPING_CATEGORIES))
def test_category_is_not_empty(instance, category):
    mappings = instance["mappings"][category]
    assert len(mappings) > 0, f"Category '{category}' has no mapping rules"


# ─────────────────────────────────────────────
# Test 5: Every mapping rule has required fields
# ─────────────────────────────────────────────

def test_all_rules_have_required_fields(all_rules):
    errors = []
    for category, rule_name, rule in all_rules:
        missing = REQUIRED_RULE_FIELDS - set(rule.keys())
        if missing:
            errors.append(f"  {category}.{rule_name} missing: {missing}")

    assert len(errors) == 0, (
        f"{len(errors)} rules missing required fields:\n" + "\n".join(errors)
    )


def test_all_rules_have_nonempty_rationale(all_rules):
    errors = []
    for category, rule_name, rule in all_rules:
        rationale = rule.get("rationale", "")
        if len(rationale) < 10:
            errors.append(f"  {category}.{rule_name}: rationale too short ({len(rationale)} chars)")

    assert len(errors) == 0, (
        f"{len(errors)} rules have empty/short rationale:\n" + "\n".join(errors)
    )


# ─────────────────────────────────────────────
# Test 6: mcp_primitive values are valid
# ─────────────────────────────────────────────

def test_all_mcp_primitives_are_valid(all_rules):
    errors = []
    for category, rule_name, rule in all_rules:
        primitive = rule.get("mcp_primitive", "")
        if primitive not in VALID_MCP_PRIMITIVES:
            errors.append(f"  {category}.{rule_name}: '{primitive}' not in {VALID_MCP_PRIMITIVES}")

    assert len(errors) == 0, (
        f"{len(errors)} rules have invalid mcp_primitive:\n" + "\n".join(errors)
    )


# ─────────────────────────────────────────────
# Test 7: Mapping counts match expected totals
# ─────────────────────────────────────────────

def test_total_mapping_count(all_rules):
    assert len(all_rules) == 29, f"Expected 29 total mappings, got {len(all_rules)}"


def test_tool_count(all_rules):
    tools = [r for _, _, r in all_rules if r["mcp_primitive"] == "Tool"]
    assert len(tools) == 20, f"Expected 20 Tools, got {len(tools)}"


def test_resource_count(all_rules):
    resources = [r for _, _, r in all_rules if r["mcp_primitive"] == "Resource"]
    assert len(resources) == 5, f"Expected 5 Resources, got {len(resources)}"


def test_prompt_count(all_rules):
    prompts = [r for _, _, r in all_rules if r["mcp_primitive"] == "Prompt"]
    assert len(prompts) == 4, f"Expected 4 Prompts, got {len(prompts)}"


# ─────────────────────────────────────────────
# Test 8: Tools have input_schema where expected
# ─────────────────────────────────────────────

def test_tools_have_input_schemas(all_rules):
    """Tools that represent active operations should define an input_schema."""
    # Prompts and dynamic process tools don't need input_schema in the mapping
    exempt_rules = {"feature_analysis_prompt", "catalog_discovery_prompt",
                    "environmental_analysis_prompt", "process_execution_prompt",
                    "process_as_tool", "collection_metadata", "collection_as_resource",
                    "catalog_as_resource", "edr_collection_as_resource", "queryables"}

    errors = []
    for category, rule_name, rule in all_rules:
        if rule["mcp_primitive"] == "Tool" and rule_name not in exempt_rules:
            if "input_schema" not in rule:
                errors.append(f"  {category}.{rule_name}: Tool missing input_schema")

    assert len(errors) == 0, (
        f"{len(errors)} Tools missing input_schema:\n" + "\n".join(errors)
    )


# ─────────────────────────────────────────────
# Test 9: Resources have URI schemes
# ─────────────────────────────────────────────

def test_resources_have_uri_schemes(all_rules):
    errors = []
    for category, rule_name, rule in all_rules:
        if rule["mcp_primitive"] == "Resource":
            if "uri_scheme" not in rule:
                errors.append(f"  {category}.{rule_name}: Resource missing uri_scheme")

    assert len(errors) == 0, (
        f"{len(errors)} Resources missing uri_scheme:\n" + "\n".join(errors)
    )


# ─────────────────────────────────────────────
# Test 10: Category-specific minimum counts
# ─────────────────────────────────────────────

def test_common_has_minimum_mappings(instance):
    assert len(instance["mappings"]["common"]) >= 3, "Common should have at least 3 mappings"


def test_features_has_minimum_mappings(instance):
    assert len(instance["mappings"]["features"]) >= 4, "Features should have at least 4 mappings"


def test_records_has_minimum_mappings(instance):
    assert len(instance["mappings"]["records"]) >= 3, "Records should have at least 3 mappings"


def test_edr_has_minimum_mappings(instance):
    assert len(instance["mappings"]["edr"]) >= 5, "EDR should have at least 5 mappings"


def test_processes_has_minimum_mappings(instance):
    assert len(instance["mappings"]["processes"]) >= 5, "Processes should have at least 5 mappings"


# ─────────────────────────────────────────────
# Test 11: No hardcoded server URLs in mappings
# ─────────────────────────────────────────────

def test_no_hardcoded_urls(instance):
    """Verify the spec is generic — no specific server URLs baked in."""
    instance_str = json.dumps(instance)
    hardcoded_urls = [
        "demo.pygeoapi.io",
        "localhost",
        "127.0.0.1",
        "pygeoapi.io/master",
    ]
    for url in hardcoded_urls:
        assert url not in instance_str, (
            f"Found hardcoded URL '{url}' in mapping instance — spec must be generic"
        )
