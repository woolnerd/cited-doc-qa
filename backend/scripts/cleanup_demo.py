#!/usr/bin/env python3
"""Automated cleanup script for demo environment.

Deletes documents and associated data older than 24 hours.
This keeps the demo clean and prevents database bloat.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.services.database import db

logger = get_logger(__name__)


async def cleanup_old_documents(
    hours: int = 24, dry_run: bool = False, exclude_global: bool = True
) -> dict:
    """Delete documents older than specified hours.

    Args:
        hours: Age threshold in hours (default: 24)
        dry_run: If True, show what would be deleted without deleting
        exclude_global: If True, don't delete global documents (default: True)

    Returns:
        Dictionary with cleanup statistics
    """
    # Ensure database is connected
    if not db.pool:
        await db.connect()

    try:
        # Calculate cutoff time
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        print(f"🧹 Starting cleanup for documents older than {hours} hours...")
        print(f"   Cutoff time: {cutoff.isoformat()}")
        print(f"   Dry run: {'Yes' if dry_run else 'No'}")
        print(f"   Exclude global docs: {'Yes' if exclude_global else 'No'}\n")

        # Build query to find old documents
        if exclude_global:
            query = """
                SELECT id, filename, upload_date, session_id
                FROM documents
                WHERE upload_date < $1
                  AND session_id != 'global'
                ORDER BY upload_date
            """
        else:
            query = """
                SELECT id, filename, upload_date, session_id
                FROM documents
                WHERE upload_date < $1
                ORDER BY upload_date
            """

        old_docs = await db.fetch(query, cutoff)

        if not old_docs:
            print("✅ No documents to clean up")
            return {
                "documents_found": 0,
                "documents_deleted": 0,
                "chunks_deleted": 0,
                "sessions_affected": 0,
            }

        print(f"📋 Found {len(old_docs)} documents to delete:\n")

        # Track statistics
        deleted_count = 0
        total_chunks_deleted = 0
        sessions = set()

        for doc in old_docs:
            doc_id = doc["id"]
            filename = doc["filename"]
            upload_date = doc["upload_date"]
            session_id = doc["session_id"]

            sessions.add(session_id)

            age_hours = (datetime.now(UTC) - upload_date).total_seconds() / 3600

            try:
                # Count chunks before deletion
                chunk_count_query = """
                    SELECT COUNT(*) as count FROM chunks WHERE document_id = $1
                """
                chunk_result = await db.fetchrow(chunk_count_query, doc_id)
                chunk_count = chunk_result["count"] if chunk_result else 0

                if dry_run:
                    print(
                        f"   [DRY RUN] Would delete: {filename} "
                        f"(age: {age_hours:.1f}h, {chunk_count} chunks, "
                        f"session: {session_id[:8]}...)"
                    )
                else:
                    # Delete document (chunks cascade delete automatically)
                    doc_query = "DELETE FROM documents WHERE id = $1"
                    await db.execute(doc_query, doc_id)

                    print(
                        f"   ✓ Deleted: {filename} "
                        f"(age: {age_hours:.1f}h, {chunk_count} chunks, "
                        f"session: {session_id[:8]}...)"
                    )

                deleted_count += 1
                total_chunks_deleted += chunk_count

            except Exception as e:
                print(f"   ✗ Failed to delete {filename}: {e}")
                logger.error(f"Failed to delete document {doc_id}: {e}", exc_info=True)
                continue

        # Print summary
        print(f"\n{'=' * 60}")
        if dry_run:
            print("🔍 DRY RUN SUMMARY")
            print(f"Would delete: {deleted_count} documents")
        else:
            print("🎉 CLEANUP COMPLETE")
            print(f"Deleted: {deleted_count}/{len(old_docs)} documents")

        print(f"Total chunks: {total_chunks_deleted}")
        print(f"Sessions affected: {len(sessions)}")
        print(f"{'=' * 60}\n")

        return {
            "documents_found": len(old_docs),
            "documents_deleted": deleted_count if not dry_run else 0,
            "chunks_deleted": total_chunks_deleted if not dry_run else 0,
            "sessions_affected": len(sessions),
        }

    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise


async def main():
    """Main entry point for cleanup script."""
    parser = argparse.ArgumentParser(
        description="Clean up old demo documents from the database"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Delete documents older than this many hours (default: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--include-global",
        action="store_true",
        help="Include global documents in cleanup (default: exclude them)",
    )

    args = parser.parse_args()

    try:
        stats = await cleanup_old_documents(
            hours=args.hours,
            dry_run=args.dry_run,
            exclude_global=not args.include_global,
        )

        print("📊 Final Statistics:")
        print(f"   Documents found: {stats['documents_found']}")
        print(f"   Documents deleted: {stats['documents_deleted']}")
        print(f"   Chunks deleted: {stats['chunks_deleted']}")
        print(f"   Sessions affected: {stats['sessions_affected']}")

        if args.dry_run:
            print("\n💡 Run without --dry-run to actually delete documents")

    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        logger.error(f"Cleanup error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
