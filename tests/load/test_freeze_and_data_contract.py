import dlt, os, pytest
from dlt.common.schema.typing import TSchemaContractSettings
from dlt.common.utils import uniq_id
from typing import Any, Union, Optional
from dlt.extract.source import DltSource, DltResource
import contextlib

from tests.load.pipeline.utils import load_table_counts
from tests.load.pipeline.utils import destinations_configs, DestinationTestConfiguration
from dlt.pipeline.exceptions import PipelineStepFailed
from dlt.common.schema.exceptions import SchemaFrozenException
from dlt.common.schema import utils

from tests.utils import skip_if_not_active

skip_if_not_active("duckdb")

schema_contract_settings = ["evolve", "discard_value", "discard_row", "freeze"]
LOCATIONS = ["source", "resource", "override"]
SCHEMA_ELEMENTS = ["table", "column", "data_type"]

@contextlib.contextmanager
def raises_frozen_exception(check_raise: bool = True) -> Any:
    if not check_raise:
        yield
        return
    with pytest.raises(PipelineStepFailed) as py_exc:
        print("yield")
        yield
        print("after")
    assert isinstance(py_exc.value.__context__, SchemaFrozenException)

def items(settings: TSchemaContractSettings) -> Any:

    @dlt.resource(name="items", write_disposition="append", schema_contract_settings=settings)
    def load_items():
        for _, index in enumerate(range(0, 10), 1):
            yield {
                "id": index,
                "some_int": 1,
                "name": f"item {index}"
            }

    return load_items

def items_with_variant(settings: TSchemaContractSettings) -> Any:

    @dlt.resource(name="items", write_disposition="append", schema_contract_settings=settings)
    def load_items():
        for _, index in enumerate(range(0, 10), 1):
            yield {
                "id": index,
                "name": f"item {index}",
                "some_int": "hello"
            }

    return load_items

def items_with_new_column(settings: TSchemaContractSettings) -> Any:

    @dlt.resource(name="items", write_disposition="append", schema_contract_settings=settings)
    def load_items():
        for _, index in enumerate(range(0, 10), 1):
            yield {
                "id": index,
                "name": f"item {index}",
                "new_col": "hello"
            }

    return load_items


def items_with_subtable(settings: TSchemaContractSettings) -> Any:

    @dlt.resource(name="items", write_disposition="append", schema_contract_settings=settings)
    def load_items():
        for _, index in enumerate(range(0, 10), 1):
            yield {
                "id": index,
                "name": f"item {index}",
                "sub_items": [{
                    "id": index + 1000,
                    "name": f"sub item {index + 1000}"
                }]
            }

    return load_items

def new_items(settings: TSchemaContractSettings) -> Any:

    @dlt.resource(name="new_items", write_disposition="append", schema_contract_settings=settings)
    def load_items():
        for _, index in enumerate(range(0, 10), 1):
            yield {
                "id": index,
                "some_int": 1,
                "name": f"item {index}"
            }

    return load_items

OLD_COLUMN_NAME = "name"
NEW_COLUMN_NAME = "new_col"
VARIANT_COLUMN_NAME = "some_int__v_text"
SUBITEMS_TABLE = "items__sub_items"
NEW_ITEMS_TABLE = "new_items"


def run_resource(pipeline, resource_fun, settings) -> DltSource:

    for item in settings.keys():
        assert item in LOCATIONS
        ev_settings = settings[item]
        if ev_settings in schema_contract_settings:
            continue
        for key, val in ev_settings.items():
            assert val in schema_contract_settings
            assert key in SCHEMA_ELEMENTS

    @dlt.source(name="freeze_tests", schema_contract_settings=settings.get("source"))
    def source() -> DltResource:
        return resource_fun(settings.get("resource"))

    # run pipeline
    pipeline.run(source(), schema_contract_settings=settings.get("override"))

    # check updated schema
    assert pipeline.default_schema._settings.get("schema_contract_settings", {}) == (settings.get("override") or settings.get("source"))

    # check items table settings
    assert pipeline.default_schema.tables["items"].get("schema_contract_settings", {}) == (settings.get("override") or settings.get("resource") or {})

def get_pipeline():
    import duckdb
    return dlt.pipeline(pipeline_name=uniq_id(), destination='duckdb', credentials=duckdb.connect(':memory:'), full_refresh=True)


@pytest.mark.parametrize("contract_setting", schema_contract_settings)
@pytest.mark.parametrize("setting_location", LOCATIONS)
def test_freeze_new_tables(contract_setting: str, setting_location: str) -> None:

    pipeline = get_pipeline()

    full_settings = {
        setting_location: {
        "table": contract_setting
    }}
    run_resource(pipeline, items, {})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10
    assert OLD_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    run_resource(pipeline, items_with_new_column, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20
    assert NEW_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    run_resource(pipeline, items_with_variant, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 30
    assert VARIANT_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    # test adding new subtable
    with raises_frozen_exception(contract_setting == "freeze"):
        run_resource(pipeline, items_with_subtable, full_settings)

    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 30 if contract_setting in ["freeze"] else 40
    assert table_counts.get(SUBITEMS_TABLE, 0) == (10 if contract_setting in ["evolve"] else 0)

    # test adding new table
    with raises_frozen_exception(contract_setting == "freeze"):
        run_resource(pipeline, new_items, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts.get("new_items", 0) == (10 if contract_setting in ["evolve"] else 0)


@pytest.mark.parametrize("contract_setting", schema_contract_settings)
@pytest.mark.parametrize("setting_location", LOCATIONS)
def test_freeze_new_columns(contract_setting: str, setting_location: str) -> None:

    full_settings = {
        setting_location: {
        "column": contract_setting
    }}

    pipeline = get_pipeline()
    run_resource(pipeline, items, {})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10
    assert OLD_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    # subtable should work
    run_resource(pipeline, items_with_subtable, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20
    assert table_counts[SUBITEMS_TABLE] == 10

    # new should work
    run_resource(pipeline, new_items, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20
    assert table_counts[NEW_ITEMS_TABLE] == 10

    # test adding new column
    with raises_frozen_exception(contract_setting == "freeze"):
        run_resource(pipeline, items_with_new_column, full_settings)

    if contract_setting == "evolve":
        assert NEW_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]
    else:
        assert NEW_COLUMN_NAME not in pipeline.default_schema.tables["items"]["columns"]
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == (30 if contract_setting in ["evolve", "discard_value"] else 20)

    # test adding variant column
    with raises_frozen_exception(contract_setting == "freeze"):
        run_resource(pipeline, items_with_variant, full_settings)

    if contract_setting == "evolve":
        assert VARIANT_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]
    else:
        assert VARIANT_COLUMN_NAME not in pipeline.default_schema.tables["items"]["columns"]
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == (40 if contract_setting in ["evolve", "discard_value"] else 20)


@pytest.mark.parametrize("contract_setting", schema_contract_settings)
@pytest.mark.parametrize("setting_location", LOCATIONS)
def test_freeze_variants(contract_setting: str, setting_location: str) -> None:

    full_settings = {
        setting_location: {
        "data_type": contract_setting
    }}
    pipeline = get_pipeline()
    run_resource(pipeline, items, {})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10
    assert OLD_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    # subtable should work
    run_resource(pipeline, items_with_subtable, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20
    assert table_counts[SUBITEMS_TABLE] == 10

    # new should work
    run_resource(pipeline, new_items, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20
    assert table_counts[NEW_ITEMS_TABLE] == 10

    # test adding new column
    run_resource(pipeline, items_with_new_column, full_settings)
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 30
    assert NEW_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]

    # test adding variant column
    with raises_frozen_exception(contract_setting == "freeze"):
        run_resource(pipeline, items_with_variant, full_settings)

    if contract_setting == "evolve":
        assert VARIANT_COLUMN_NAME in pipeline.default_schema.tables["items"]["columns"]
    else:
        assert VARIANT_COLUMN_NAME not in pipeline.default_schema.tables["items"]["columns"]
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == (40 if contract_setting in ["evolve", "discard_value"] else 30)


def test_settings_precedence() -> None:
    pipeline = get_pipeline()

    # load some data
    run_resource(pipeline, items, {})

    # trying to add new column when forbidden on resource will fail
    run_resource(pipeline, items_with_new_column, {"resource": {
        "column": "discard_row"
    }})

    # when allowed on override it will work
    run_resource(pipeline, items_with_new_column, {
        "resource": {"column": "freeze"},
        "override": {"column": "evolve"}
    })


def test_settings_precedence_2() -> None:
    pipeline = get_pipeline()

    # load some data
    run_resource(pipeline, items, {"source": {
        "data_type": "discard_row"
    }})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # trying to add variant when forbidden on source will fail
    run_resource(pipeline, items_with_variant, {"source": {
        "data_type": "discard_row"
    }})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # if allowed on resource it will pass
    run_resource(pipeline, items_with_variant, {
        "resource": {"data_type": "evolve"},
        "source": {"data_type": "discard_row"}
    })
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20

    # if allowed on override it will also pass
    run_resource(pipeline, items_with_variant, {
        "resource": {"data_type": "discard_row"},
        "source": {"data_type": "discard_row"},
        "override": {"data_type": "evolve"},
    })
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 30

@pytest.mark.parametrize("setting_location", LOCATIONS)
def test_change_mode(setting_location: str) -> None:
    pipeline = get_pipeline()

    # load some data
    run_resource(pipeline, items, {})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # trying to add variant when forbidden will fail
    run_resource(pipeline, items_with_variant, {setting_location: {
        "data_type": "discard_row"
    }})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # now allow
    run_resource(pipeline, items_with_variant, {setting_location: {
        "data_type": "evolve"
    }})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 20

@pytest.mark.parametrize("setting_location", LOCATIONS)
def test_single_settings_value(setting_location: str) -> None:
    pipeline = get_pipeline()

    run_resource(pipeline, items, {})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # trying to add variant when forbidden will fail
    run_resource(pipeline, items_with_variant, {setting_location: "discard_row"})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # trying to add new column will fail
    run_resource(pipeline, items_with_new_column, {setting_location: "discard_row"})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10

    # trying to add new table will fail
    run_resource(pipeline, new_items, {setting_location: "discard_row"})
    table_counts = load_table_counts(pipeline, *[t["name"] for t in pipeline.default_schema.data_tables()])
    assert table_counts["items"] == 10
    assert "new_items" not in table_counts


def test_data_contract_interaction() -> None:
    """
    ensure data contracts with pydantic are enforced properly
    """
    from pydantic import BaseModel

    class Items(BaseModel):
        id: int  # noqa: A003
        name: Optional[str]
        amount: Optional[int]

    @dlt.resource(name="items", columns=Items)
    def get_items_simple():
        yield from [{
            "id": 5
        }]

    @dlt.resource(name="items", columns=Items)
    def get_items():
        yield from [{
            "id": 5,
            "name": "dave",
        }]

    @dlt.resource(name="items")
    def get_items_variant():
        yield from [{
            "id": 5,
            "name": "dave",
            "amount": "HELLO"
        }]

    @dlt.resource(name="items")
    def get_items_new_col():
        yield from [{
            "id": 5,
            "name": "dave",
            "amount": 6,
            "new_col": "hello"
        }]

    @dlt.resource(name="items")
    def get_items_subtable():
        yield from [{
            "id": 5,
            "name": "dave",
            "amount": 6,
            "sub": [{"hello": "dave"}]
        }]

    # test variants
    pipeline = get_pipeline()
    pipeline.run([get_items_simple()])
    pipeline.run([get_items()], schema_contract_settings={"data_type": "discard_row"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1
    pipeline.run([get_items_variant()], schema_contract_settings={"data_type": "discard_row"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 0
    pipeline.run([get_items_variant()], schema_contract_settings={"data_type": "evolve"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1

    # test new column
    pipeline = get_pipeline()
    pipeline.run([get_items_simple()])
    pipeline.run([get_items()], schema_contract_settings={"column": "discard_row"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1
    pipeline.run([get_items_new_col()], schema_contract_settings={"column": "discard_row"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 0
    pipeline.run([get_items_new_col()], schema_contract_settings={"column": "evolve"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1

    # test new subtable
    pipeline = get_pipeline()
    pipeline.run([get_items_simple()])
    pipeline.run([get_items_subtable()], schema_contract_settings={"table": "discard_row"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1
    assert pipeline.last_trace.last_normalize_info.row_counts.get("items__sub", 0) == 0

    pipeline.run([get_items_subtable()], schema_contract_settings={"table": "evolve"})
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 1
    assert pipeline.last_trace.last_normalize_info.row_counts.get("items__sub", 0) == 1


def test_different_objects_in_one_load() -> None:

    pipeline = get_pipeline()

    @dlt.resource(name="items", schema_contract_settings={"column": "freeze", "table":"evolve"})
    def get_items():
        yield {
            "id": 1,
            "name": "dave",
            "amount": 50
        }
        yield {
            "id": 2,
            "name": "dave",
            "amount": 50,
            "new_column": "some val"
        }

    pipeline.run([get_items()])
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 2


@pytest.mark.parametrize("table_mode", ["discard_row", "evolve", "freeze"])
def test_dynamic_tables(table_mode: str) -> None:

    pipeline = get_pipeline()

    # adding columns with a data type makes this columns complete which makes this table complete -> it fails in the normalize because
    #   the tables is NOT new according to normalizer so the row is not discarded
    # remove that and it will pass because the table contains just one incomplete column so it is incomplete so it is treated as new
    # if you uncomment update code in the extract the problem probably goes away
    @dlt.resource(name="items", table_name=lambda i: i["table"], schema_contract_settings={"table": table_mode}, columns={"id": {}})
    def get_items():
        yield {
            "id": 1,
            "table": "one",
        }
        yield {
            "id": 2,
            "table": "two",
            "new_column": "some val"
        }
    with raises_frozen_exception(table_mode == "freeze"):
        pipeline.run([get_items()])
    assert pipeline.last_trace.last_normalize_info.row_counts.get("one", 0) == (1 if table_mode == "evolve" else 0)
    assert pipeline.last_trace.last_normalize_info.row_counts.get("two", 0) == (1 if table_mode == "evolve" else 0)


@pytest.mark.parametrize("column_mode", ["discard_row", "evolve", "freeze"])
def test_defined_column_in_new_table(column_mode: str) -> None:
    pipeline = get_pipeline()

    @dlt.resource(name="items", columns=[{"name": "id", "data_type": "bigint", "nullable": False}], schema_contract_settings={"column": column_mode})
    def get_items():
        yield {
            "id": 1,
            "key": "value",
        }
    pipeline.run([get_items()])
    assert pipeline.last_trace.last_normalize_info.row_counts.get("items", 0) == 1


@pytest.mark.parametrize("column_mode", ["freeze", "discard_row", "evolve"])
def test_new_column_from_hint_and_data(column_mode: str) -> None:

    pipeline = get_pipeline()

    # we define complete column on id, this creates a complete table
    # normalizer does not know that it is a new table and discards the row
    # and it also excepts on column freeze

    @dlt.resource(
        name="items",
        schema_contract_settings={"column": column_mode},
        columns=[{"name": "id", "data_type": "bigint", "nullable": False}])
    def get_items():
        yield {
            "id": 1,
            "key": "value",
        }

    pipeline.run([get_items()])
    assert pipeline.last_trace.last_normalize_info.row_counts.get("items", 0) == 1


@pytest.mark.parametrize("column_mode", ["freeze", "discard_row", "evolve"])
def test_two_new_columns_from_two_rows(column_mode: str) -> None:

    pipeline = get_pipeline()

    # this creates a complete table in first row
    # and adds a new column to complete tables in 2nd row
    # the test does not fail only because you clone schema in normalize

    @dlt.resource(
        schema_contract_settings={"column": column_mode}
    )
    def items():
        yield {
            "id": 1,
        }
        yield {
            "id": 1,
            "key": "value",
        }
    pipeline.run([items()])
    assert pipeline.last_trace.last_normalize_info.row_counts["items"] == 2


@pytest.mark.parametrize("column_mode", ["freeze", "discard_row", "evolve"])
def test_dynamic_new_columns(column_mode: str) -> None:

    pipeline = get_pipeline()

    # fails because dlt is not able to add _dlt_load_id to tables. I think we should do an exception for those
    # 1. schema.dlt_tables() - everything evolve
    # 2. is_dlt_column (I hope we have helper) - column evolve, data_type freeze

    def columns(item):
        if item["id"] == 1:
            return [{"name": "key", "data_type": "text", "nullable": True}]
        if item["id"] == 2:
            return [{"name": "id", "data_type": "bigint", "nullable": True}]

    @dlt.resource(name="items", table_name=lambda i: "items", schema_contract_settings={"column": column_mode})
    def get_items():
        yield {
            "id": 1,
            "key": "value",
        }
        yield {
            "id": 2,
            "key": "value",
        }

    items = get_items()
    items.apply_hints(columns=columns)
    # apply hints apply to `items` not the original resource, so doing get_items() below removed them completely
    pipeline.run(items)
    assert pipeline.last_trace.last_normalize_info.row_counts.get("items", 0) == 2