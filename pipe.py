import dlt

data = [
    {'id': 1, 'name': 'Alice'},
    {'id': 2, 'name': 'Bob'}
]

pipeline = dlt.pipeline(
            pipeline_name="some_pipeline",
            dataset_name="some_dataset",
            staging="filesystem",
            destination="bigquery",
        )

load_info = pipeline.run(data, table_name="users", write_disposition="replace")
print(load_info)