"""Emit OpenLineage events from code that runs outside dbt.

dbt-ol reports what dbt builds. Everything else that reads or writes the
warehouse (ingestion, scripts, reports) reports itself through this helper, so
Marquez sees one graph across tool boundaries.

Dataset naming must match dbt-ol exactly, or the graph splits in two:
  namespace  duckdb://<path in profiles.yml>     e.g. duckdb://warehouse/monitoring.duckdb
  name       <database>.<schema>.<table>          e.g. monitoring.marts.fct_alerts

Where events go is OpenLineage's own configuration: openlineage.yml in the
working directory, or OPENLINEAGE_CONFIG / OPENLINEAGE_URL. If the backend is
unreachable the script still does its job and prints a warning.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import InputDataset, Job, OutputDataset, Run, RunEvent, RunState
from openlineage.client.facet_v2 import column_lineage_dataset, job_type_job, schema_dataset

PRODUCER = "urn:data-quality-and-lineage:scripts"
JOB_NAMESPACE = os.environ.get("OPENLINEAGE_NAMESPACE", "monitoring")

_DB_PATH = os.environ.get("DUCKDB_PATH", "warehouse/monitoring.duckdb")   # same expression as profiles.yml
WAREHOUSE_NAMESPACE = f"duckdb://{_DB_PATH}"
_DATABASE = Path(_DB_PATH).stem


def table(schema: str, name: str) -> tuple[str, str]:
    """A warehouse table, named exactly as dbt-ol names it."""
    return WAREHOUSE_NAMESPACE, f"{_DATABASE}.{schema}.{name}"


def file(path: str) -> tuple[str, str]:
    """A file in this repo, by repo-relative path."""
    return "file", path


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _emit(client: OpenLineageClient, event: RunEvent) -> None:
    try:
        client.emit(event)
    except Exception as e:  # lineage must never break the job it describes
        print(f"[lineage] could not emit {event.eventType.value} for {event.job.name}: {e}")


@contextmanager
def lineage_run(job_name: str, inputs: list[tuple[str, str]], description: str = ""):
    """Wrap a job: START on entry, COMPLETE (or FAIL) on exit.

    Inside the block, declare outputs with
        run.output(dataset, columns={"out_col": [(input_dataset, "in_col"), ...]})
    Column mappings become OpenLineage columnLineage facets.
    """
    client = OpenLineageClient()
    run = _Run(job_name, inputs)
    _emit(client, run.event(RunState.START))
    try:
        yield run
    except Exception:
        _emit(client, run.event(RunState.FAIL))
        raise
    _emit(client, run.event(RunState.COMPLETE))


class _Run:
    def __init__(self, job_name: str, inputs: list[tuple[str, str]]):
        self.id = str(uuid.uuid4())
        self.job_name = job_name
        self.inputs = inputs
        self.outputs: list[OutputDataset] = []

    def output(self, dataset: tuple[str, str], columns: dict[str, list[tuple[tuple[str, str], str]]]) -> None:
        ns, name = dataset
        facets = {
            "schema": schema_dataset.SchemaDatasetFacet(
                fields=[schema_dataset.SchemaDatasetFacetFields(name=c) for c in columns]),
            "columnLineage": column_lineage_dataset.ColumnLineageDatasetFacet(fields={
                out_col: column_lineage_dataset.Fields(inputFields=[
                    column_lineage_dataset.InputField(namespace=src[0], name=src[1], field=in_col)
                    for src, in_col in sources
                ])
                for out_col, sources in columns.items()
            }),
        }
        self.outputs.append(OutputDataset(namespace=ns, name=name, facets=facets))

    def event(self, state: RunState) -> RunEvent:
        return RunEvent(
            eventType=state,
            eventTime=_now(),
            producer=PRODUCER,
            run=Run(runId=self.id),
            job=Job(
                namespace=JOB_NAMESPACE,
                name=self.job_name,
                facets={"jobType": job_type_job.JobTypeJobFacet(
                    processingType="BATCH", integration="PYTHON", jobType="SCRIPT")},
            ),
            inputs=[self._input(ns, n, with_schema=state != RunState.START) for ns, n in self.inputs],
            outputs=self.outputs if state != RunState.START else [],
        )

    def _input(self, ns: str, name: str, with_schema: bool) -> InputDataset:
        """Inputs carry a schema listing every column the outputs read from them.

        Marquez only keeps a column-lineage edge if both ends are columns it knows,
        and for files nobody else reports a schema.
        """
        fields = sorted({
            src.field
            for out in self.outputs
            for col in out.facets["columnLineage"].fields.values()
            for src in col.inputFields
            if (src.namespace, src.name) == (ns, name)
        }) if with_schema else []
        facets = {"schema": schema_dataset.SchemaDatasetFacet(
            fields=[schema_dataset.SchemaDatasetFacetFields(name=f) for f in fields])} if fields else {}
        return InputDataset(namespace=ns, name=name, facets=facets)
