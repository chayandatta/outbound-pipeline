from django.core.management.base import BaseCommand
from outbound.models import OutboundMessageRequest, OutboundStatus
from outbound.services import bulk_process_pending


class Command(BaseCommand):
    help = "Process pending outbound message requests in batches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Maximum number of records to process (default: 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate execution without modifying database records.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if dry_run:
            pending_count = OutboundMessageRequest.objects.filter(
                status=OutboundStatus.RECEIVED
            )[:batch_size].count()
            self.stdout.write(
                f"[DRY RUN] Pending records found: {pending_count} (batch_size: {batch_size})"
            )
            self.stdout.write("Processed: 0 | Delivered: 0 | Failed: 0 | Skipped: 0")
            return

        stats = bulk_process_pending(batch_size=batch_size)
        summary = (
            f"Processed: {stats['processed']} | "
            f"Delivered: {stats['delivered']} | "
            f"Failed: {stats['failed']} | "
            f"Skipped: {stats['skipped']}"
        )
        self.stdout.write(summary)
