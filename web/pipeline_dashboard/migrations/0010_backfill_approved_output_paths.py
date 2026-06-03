from __future__ import annotations

from django.db import migrations


def backfill_approved_output_paths(apps, schema_editor):
    """Rewrite ParsedOutput.output_path to the canonical final path.

    Background: until commit 7a6fe8b (2026-05-28), `approve_parsed_output` did
    not update ParsedOutput.output_path after promoting the staging copy to
    data/processed/. Rows approved before that fix still have an
    output_path pointing at the data/output/ staging file, which makes the
    /process/ History chapter and download endpoint serve the wrong file.

    All nine final files already exist on disk under
    data/processed/<Vendor>/<Vendor>_<Month_YYYY>.csv. This migration only
    rewrites the database pointer; no file movement is performed.

    Idempotent: rows whose output_path already matches the canonical path are
    left alone. Rows without a vendor (an invariant violation we still want to
    survive) are skipped with a printed warning.
    """
    parsed_output_model = apps.get_model("pipeline_dashboard", "ParsedOutput")
    # Reuse the live helper to compute the canonical path. The helper only
    # reads instance attributes (vendor, reporting_period, period_start) and
    # never touches the database, so it is safe to call from a data
    # migration against historical model state.
    from pipeline_dashboard.parser_workflow import final_processed_output_path
    from django.conf import settings

    repo_root = settings.REPO_ROOT

    updated = 0
    skipped = 0
    for parsed in parsed_output_model.objects.filter(comparison_status="approved"):
        if parsed.vendor_id is None:
            print(f"  skip id={parsed.id}: no vendor attached")
            skipped += 1
            continue
        try:
            final_path = final_processed_output_path(parsed)
        except Exception as exc:  # ParserWorkflowError or similar
            print(f"  skip id={parsed.id}: cannot compute final path ({exc})")
            skipped += 1
            continue
        canonical = str(final_path.relative_to(repo_root))
        if parsed.output_path == canonical:
            continue
        parsed.output_path = canonical
        parsed.save(update_fields=["output_path"])
        updated += 1
        print(f"  rewrote id={parsed.id}: {canonical}")
    print(f"approved_output_paths updated={updated} skipped={skipped}")


def noop_reverse(apps, schema_editor):
    """Reverse code is intentionally a no-op.

    This migration is a one-time pointer correction. Reverting it would
    re-expose the stale data/output/ paths in the History chapter, which is
    the very bug we are fixing. The original staging files may also have
    been removed by the new approve_parsed_output behaviour, so they cannot
    be restored.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0009_seed_s2_vendor"),
    ]

    operations = [
        migrations.RunPython(backfill_approved_output_paths, noop_reverse),
    ]
