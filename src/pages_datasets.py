"""Administration — dataset manager (blueprint §4, §6, §9 SPRINT 9).

The page exists to make one distinction impossible to miss:

* the **deployed model dataset** is the dataset recorded in
  ``models/model_manifest.json`` — the bytes the artifact in service was trained on. Nothing on
  this page can change it;
* the **active dataset** is a pointer to the version a *future, explicit* retraining run would
  use. Uploading stages a version; pressing **Activate dataset** moves that pointer.

Uploading never retrains and never replaces the live artifact. The handler for the upload
button calls :func:`src.data_manager.stage_upload`, which validates, quarantines and writes one
``dataset_versions`` row; the activation button calls
:func:`src.data_manager.activate_version`, which writes one pointer change. Neither reaches
``models/``, and each writes an audit row stating ``retraining_triggered: false``.

The page is a thin view: every read and write re-checks the admin role inside the service
function, so a user who forced this page would collect a ``PermissionDenied`` and an audited
``auth.denied`` row rather than dataset metadata.

What is never shown: a raw row of the uploaded data, a cell value, the uploaded filename used
as a path, or any credential. The preview is aggregates only — counts, class balance and
per-column ranges.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src import data_manager, security
from src.config import load_settings

FLASH_KEY = "dataset_flash"

DEPLOYED_NOTICE = (
    "**Uploading does not retrain anything.** The model answering predictions keeps the "
    "artifact and the dataset recorded in `models/model_manifest.json` until an operator runs "
    "a rebuild and the artifact is verified again."
)

STAGING_NOTICE = (
    "A staged dataset is validated metadata plus a quarantined copy of its bytes. It is not "
    "used for predictions and it does not become the training data until an administrator "
    "activates it **and** a retraining run is explicitly started outside this page."
)

NO_RAW_ROWS_NOTICE = (
    "The preview shows aggregates only — counts, class balance and per-column ranges. No row "
    "of the uploaded file is rendered, so a demo never puts a customer record on screen."
)


def _guard(conn, token: str | None):
    """Server-side role check for this page. Returns ``None`` when the caller may not be here."""
    try:
        return security.require_role(conn, token, ("admin",), action="pages_datasets.render")
    except security.AuthError as error:
        st.error(error.public_message)
        return None


def _fact_table(facts: dict[str, object]) -> None:
    """A small two-column field/value table. Values are shown as text, None as an em dash."""
    st.dataframe(
        [
            {"field": field, "value": "—" if value is None else str(value)}
            for field, value in facts.items()
        ],
        width="stretch",
        hide_index=True,
    )


def _flash(message: str) -> None:
    st.session_state[FLASH_KEY] = message


def _show_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.success(message)


# ------------------------------------------------------------------- deployed vs active
def _comparison_panel(conn, token: str | None) -> None:
    """The two datasets, side by side, with the honest verdict between them."""
    try:
        facts = data_manager.comparison(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return

    deployed = facts["deployed"]
    active = facts["active"]

    st.markdown("#### Deployed model dataset vs active dataset")
    st.caption(DEPLOYED_NOTICE)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("##### In service — the deployed model")
            if not deployed.get("available"):
                st.warning(
                    "The model manifest could not be read, so the dataset behind the live "
                    "model cannot be quoted. That is a build problem, not an upload problem."
                )
            else:
                _fact_table(
                    {
                        "model version": deployed.get("model_version"),
                        "dataset path": deployed.get("dataset_path"),
                        "dataset sha256": deployed.get("dataset_sha256"),
                        "artifact sha256 (manifest)": deployed.get("artifact_sha256_recorded"),
                        "artifact sha256 (on disk now)": deployed.get("artifact_sha256_now"),
                        "trained at (UTC)": deployed.get("trained_at"),
                    }
                )
                if deployed.get("artifact_matches_manifest"):
                    st.caption(
                        "The artifact on disk still hashes to the value its manifest records, "
                        "so the model in service is the model that was evaluated."
                    )
                else:
                    st.warning(
                        "The artifact on disk does not match the hash in its manifest. Treat "
                        "the deployed model as unverified until the artifact gate passes."
                    )
    with right:
        with st.container(border=True):
            st.markdown("##### Pointer — the active dataset version")
            if active is None:
                st.info(
                    "No dataset version is active. With the seed registered this should not "
                    "happen; see the version table below."
                )
            else:
                _fact_table(
                    {
                        "version id": active["id"],
                        "file label": active["original_filename_safe"],
                        "sha256": active["sha256"],
                        "records × columns": f"{active['record_count']} × {active['column_count']}",
                        "class 0 / class 1": f"{active['class_zero']} / {active['class_one']}",
                        "activated at (UTC)": active["activated_at"],
                    }
                )

    if facts["active_built_the_model"]:
        st.success(
            "The active dataset version is the same bytes as the dataset that built the "
            "deployed model.",
            icon="✅",
        )
    else:
        st.warning(
            "The active dataset version is **not** the dataset that built the deployed model. "
            "It would be used only by a future retraining run; predictions in service still "
            "come from the deployed artifact. This is the expected state after an activation.",
            icon="⚠️",
        )


# ------------------------------------------------------------------------- active dataset
def _class_balance(version) -> None:
    columns = st.columns(3)
    columns[0].metric("records", f"{version.record_count:,}")
    columns[1].metric("class 0 · no default", f"{version.class_zero:,}")
    columns[2].metric("class 1 · default", f"{version.class_one:,}")
    st.caption(
        f"Column count {version.column_count}. Class 1 share {version.class_one_rate:.2%}. "
        "This imbalance is why the model is judged on F1 and recall, not accuracy alone."
    )


def _active_section(conn, token: str | None) -> None:
    try:
        version = data_manager.active_version(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return

    st.markdown("#### Active dataset")
    if version is None:
        st.info("No dataset version is active yet.")
        return
    _class_balance(version)
    st.dataframe(
        [
            {
                "version": version.id,
                "status": version.status,
                "file label": version.original_filename_safe,
                "sha256": version.sha256,
                "records": version.record_count,
                "columns": version.column_count,
                "class 0": version.class_zero,
                "class 1": version.class_one,
                "validated (UTC)": version.validated_at,
                "activated (UTC)": version.activated_at,
                "quarantined copy": version.quarantined_filename or "the seed file itself",
            }
        ],
        width="stretch",
        hide_index=True,
    )


def _schema_section() -> None:
    with st.expander("The 25-column schema this application accepts"):
        st.dataframe(
            data_manager.schema_rows(),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Column order is part of the contract: a file whose columns are correct but "
            "reordered is rejected with a column-order reason rather than silently reindexed."
        )


# ------------------------------------------------------------------------------- upload
def _upload_section(conn, token: str | None, quarantine_dir: str) -> None:
    st.markdown("#### Stage a new dataset version")
    st.caption(STAGING_NOTICE)
    uploaded = st.file_uploader(
        "Dataset CSV (25 columns, UTF-8, at most 10 MB)",
        type=["csv"],
        accept_multiple_files=False,
        key="dataset_file",
    )
    if st.button("Validate and stage dataset", key="dataset_stage_button", type="primary"):
        if uploaded is None:
            st.error("Choose a CSV file first. Nothing was staged.")
            return
        payload = uploaded.getvalue()
        try:
            staged = data_manager.stage_upload(
                conn,
                token,
                payload,
                getattr(uploaded, "name", None),
                quarantine_dir=quarantine_dir,
            )
        except data_manager.DatasetRejected as rejected:
            st.error(f"The upload was rejected and recorded: {rejected.reason}")
            st.caption(
                f"Rejection #{rejected.rejection_id} is in the rejection log below with the "
                "stable error codes "
                + ", ".join(f"`{code}`" for code in sorted(rejected.report.codes))
                + ". The quarantined copy of a rejected file is deleted after the reason is "
                "recorded; nothing was cleaned, coerced or partially loaded."
            )
            return
        except security.AuthError as error:
            st.error(error.public_message)
            return

        version = staged.version
        if staged.duplicate:
            st.info(
                f"Those exact bytes are already version #{version.id} "
                f"(`{version.short_sha256}…`); nothing new was staged and the duplicate copy "
                "was removed."
            )
        else:
            st.success(
                f"Staged as dataset version **#{version.id}**. It is validated and quarantined "
                "under a generated filename; it is **not** active and the deployed model has "
                "not changed."
            )
        _fact_table(
            {
                "records": version.record_count,
                "columns": version.column_count,
                "class 0 (no default)": version.class_zero,
                "class 1 (default)": version.class_one,
                "class 1 share": f"{version.class_one_rate:.2%}",
                "sha256": version.sha256,
                "validated at (UTC)": version.validated_at,
                "status": version.status,
            }
        )
        if staged.preview is not None:
            st.markdown("##### Aggregate preview (no rows)")
            st.dataframe(
                [
                    {
                        "column": column.name,
                        "role": column.kind,
                        "unit": column.unit,
                        "distinct values": column.distinct,
                        "min": column.minimum,
                        "max": column.maximum,
                        "mean": column.mean,
                    }
                    for column in staged.preview.columns
                ],
                width="stretch",
                hide_index=True,
            )
            st.caption(NO_RAW_ROWS_NOTICE)


# ------------------------------------------------------------------------------ versions
def _versions_section(conn, token: str | None) -> None:
    st.markdown("#### Dataset versions")
    st.caption(
        "One row per validated upload, newest first. Exactly one row can be active; the "
        "database enforces it with a partial unique index as well as inside the activation "
        "transaction."
    )
    try:
        versions = data_manager.list_versions(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return
    if not versions:
        st.info("No dataset version has been registered yet.")
        return
    st.dataframe(
        [
            {
                "version": version.id,
                "status": version.status,
                "active": version.is_active,
                "file label": version.original_filename_safe,
                "sha256": version.short_sha256 + "…",
                "records": version.record_count,
                "columns": version.column_count,
                "class 1": version.class_one,
                "validated (UTC)": version.validated_at,
                "activated (UTC)": version.activated_at,
                "uploaded by": (
                    f"user #{version.uploaded_by}"
                    if version.uploaded_by is not None
                    else "seed (startup)"
                ),
            }
            for version in versions
        ],
        width="stretch",
        hide_index=True,
    )

    staged = [version for version in versions if not version.is_active]
    if not staged:
        st.caption("Every registered version is the active one; there is nothing to activate.")
        return
    st.markdown("##### Activate a version")
    st.caption(
        "Activation moves the pointer a future retraining run would read. It does not train, "
        "does not reload the model and does not change the artifact — the panel at the top of "
        "this page will then show the two datasets as different, which is the truth."
    )
    for version in staged:
        if st.button(
            f"Activate dataset #{version.id} · {version.short_sha256}…",
            key=f"dataset_activate_{version.id}",
        ):
            try:
                activated = data_manager.activate_version(conn, token, version.id)
            except security.AuthError as error:
                st.error(error.public_message)
            else:
                _flash(
                    f"Dataset version **#{activated.id}** is now the active pointer "
                    f"(`{activated.short_sha256}…`). The deployed model is unchanged and was "
                    "not retrained."
                )
                st.rerun()


# ---------------------------------------------------------------------------- rejections
def _rejection_section(conn, token: str | None) -> None:
    st.markdown("#### Rejection log")
    st.caption(
        "Every refused upload with the reason the administrator saw. The reason names the "
        "column and how many rows offend, never a cell value, and nothing is repaired or "
        "partially loaded."
    )
    try:
        rejections = data_manager.list_rejections(conn, token, limit=25)
    except security.AuthError as error:
        st.error(error.public_message)
        return
    if not rejections:
        st.info("No upload has been rejected.")
        return
    st.dataframe(
        [
            {
                "when (UTC)": rejection["created_at"],
                "file label": rejection["original_filename_safe"],
                "sha256": str(rejection["sha256"])[:12] + "…",
                "bytes": rejection["size_bytes"],
                "codes": rejection["error_codes"],
                "reason": rejection["reason"],
                "uploaded by": (
                    f"user #{rejection['uploaded_by']}"
                    if rejection["uploaded_by"] is not None
                    else "—"
                ),
            }
            for rejection in rejections
        ],
        width="stretch",
        hide_index=True,
    )


def render(conn, token: str | None) -> None:
    """The Dataset manager page. Re-checks the role itself before it reads anything."""
    if _guard(conn, token) is None:
        return

    st.markdown("### Dataset manager")
    st.caption(
        "Validated uploads are staged with a checksum and an aggregate preview; nothing is "
        "retrained by an upload, and the deployed model keeps the dataset it was built on "
        "until an explicit rebuild."
    )
    _show_flash()

    quarantine_dir = load_settings().quarantine_dir
    _comparison_panel(conn, token)
    _active_section(conn, token)
    _schema_section()
    _upload_section(conn, token, quarantine_dir)
    _versions_section(conn, token)
    _rejection_section(conn, token)
    st.caption(
        "Staged copies are kept under the quarantine directory "
        f"(`{Path(quarantine_dir).as_posix()}`), git-ignored and on the writable volume. The "
        "seed `data/UCI_Credit_Card.csv` is never modified by this page."
    )


__all__ = ["DEPLOYED_NOTICE", "FLASH_KEY", "NO_RAW_ROWS_NOTICE", "STAGING_NOTICE", "render"]
