from typing import List

import dlt
from dlt.sources.credentials import ConnectionStringCredentials
from dlt.common import pendulum

from sql_database import sql_database, sql_table


def load_select_tables_from_database() -> None:
    """Use the sql_database source to reflect an entire database schema and load select tables from it.

    This example sources data from the public Rfam MySQL database.
    """
    # Create a pipeline
    pipeline = dlt.pipeline(
        import_schema_path="schemas/import",
        export_schema_path="schemas/export",
        pipeline_name="rfam",
        destination='bigquery', dataset_name="rfam_data"
    )

    # Credentials for the sample database.
    # Note: It is recommended to configure credentials in `.dlt/secrets.toml` under `sources.sql_database.credentials`
    credentials = ConnectionStringCredentials(
        "mysql+pymysql://rfamro@mysql-rfam-public.ebi.ac.uk:4497/Rfam"
    )

    source_3 = []
    test_table = sql_table(credentials=credentials, table="clan", columns=["description", "clan_acc"])
    source_3.append(test_table)
    info = pipeline.run(source_3, write_disposition="append", table_name="test")
    print(info)

    # Run the pipeline. The merge write disposition merges existing rows in the destination by primary key
    info = pipeline.run(source_3, write_disposition="merge")
    print(info)


if __name__ == "__main__":
    # Load selected tables with different settings
    load_select_tables_from_database()

    # Load tables with the standalone table resource
    # load_standalone_table_resource()

    # Load all tables from the database.
    # Warning: The sample database is very large
    # load_entire_database()
