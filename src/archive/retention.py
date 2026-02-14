"""
Retention and soft-delete management for archive summaries.

Phase 8: Retention Management
"""

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ArchiveSource, SummaryStatus

logger = logging.getLogger(__name__)


@dataclass
class RetentionConfig:
    """Configuration for retention policies."""
    retention_days: Optional[int] = None  # None = keep forever
    soft_delete_grace_days: int = 30
    sync_deletes_to_drive: bool = False
    archive_before_delete: bool = True
    archive_format: str = "zip"  # "zip" or "tar.gz"


@dataclass
class DeletedSummaryInfo:
    """Information about a soft-deleted summary."""
    summary_id: str
    source_key: str
    period: str
    deleted_at: datetime
    reason: str
    permanent_delete_at: datetime
    backup_path: Optional[str] = None
    original_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "source_key": self.source_key,
            "period": self.period,
            "deleted_at": self.deleted_at.isoformat(),
            "reason": self.reason,
            "permanent_delete_at": self.permanent_delete_at.isoformat(),
            "backup_path": self.backup_path,
            "original_path": self.original_path,
        }


class RetentionManager:
    """
    Manages retention policies and soft deletion.

    Handles:
    - Soft deletion with grace period
    - Backup before permanent delete
    - Recovery of soft-deleted summaries
    - Automatic cleanup based on retention policy
    """

    def __init__(
        self,
        archive_root: Path,
        config: Optional[RetentionConfig] = None,
    ):
        """
        Initialize retention manager.

        Args:
            archive_root: Root path of the archive
            config: Retention configuration
        """
        self.archive_root = archive_root
        self.config = config or RetentionConfig()
        self.deleted_dir = archive_root / ".deleted"
        self.deleted_manifest_path = self.deleted_dir / "deleted-manifest.json"

    def soft_delete(
        self,
        md_path: Path,
        reason: str = "manual",
    ) -> DeletedSummaryInfo:
        """
        Soft delete a summary.

        Args:
            md_path: Path to the summary .md file
            reason: Reason for deletion

        Returns:
            Information about the deleted summary
        """
        meta_path = md_path.with_suffix(".meta.json")

        # Load metadata
        if meta_path.exists():
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            summary_id = meta.get("summary_id", "unknown")
            source_key = f"{meta['source']['source_type']}:{meta['source']['server_id']}"
            period = meta.get("period", {}).get("start", "unknown")[:10]
        else:
            summary_id = md_path.stem
            source_key = "unknown"
            period = md_path.stem[:10]

        # Create deleted directory structure
        now = datetime.utcnow()
        permanent_delete_at = now + timedelta(days=self.config.soft_delete_grace_days)

        # Destination path in .deleted/
        safe_source = source_key.replace(":", "_")
        dest_dir = self.deleted_dir / safe_source / period
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Move files
        dest_md = dest_dir / md_path.name
        shutil.move(str(md_path), str(dest_md))

        if meta_path.exists():
            dest_meta = dest_dir / meta_path.name
            shutil.move(str(meta_path), str(dest_meta))

            # Update metadata status
            with open(dest_meta, 'r') as f:
                meta = json.load(f)
            meta["status"] = SummaryStatus.DELETED.value
            meta["deleted_at"] = now.isoformat()
            with open(dest_meta, 'w') as f:
                json.dump(meta, f, indent=2)

        # Create info record
        info = DeletedSummaryInfo(
            summary_id=summary_id,
            source_key=source_key,
            period=period,
            deleted_at=now,
            reason=reason,
            permanent_delete_at=permanent_delete_at,
            original_path=str(md_path),
        )

        # Update manifest
        self._add_to_manifest(info)

        logger.info(f"Soft deleted summary: {md_path}")
        return info

    def recover(self, summary_id: str) -> bool:
        """
        Recover a soft-deleted summary.

        Args:
            summary_id: Summary ID to recover

        Returns:
            True if recovered successfully
        """
        manifest = self._load_manifest()

        # Find the deleted entry
        entry = None
        for item in manifest.get("deleted", []):
            if item["summary_id"] == summary_id:
                entry = item
                break

        if not entry:
            logger.warning(f"Summary not found in deleted manifest: {summary_id}")
            return False

        # Find files in .deleted/
        source_key = entry["source_key"]
        period = entry["period"]
        safe_source = source_key.replace(":", "_")
        deleted_dir = self.deleted_dir / safe_source / period

        if not deleted_dir.exists():
            logger.warning(f"Deleted directory not found: {deleted_dir}")
            return False

        # Find matching files
        md_files = list(deleted_dir.glob("*.md"))
        if not md_files:
            return False

        md_path = md_files[0]
        meta_path = md_path.with_suffix(".meta.json")

        # Restore to original location
        original_path = Path(entry["original_path"])
        original_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(md_path), str(original_path))
        if meta_path.exists():
            original_meta = original_path.with_suffix(".meta.json")
            shutil.move(str(meta_path), str(original_meta))

            # Update status
            with open(original_meta, 'r') as f:
                meta = json.load(f)
            meta["status"] = SummaryStatus.COMPLETE.value
            meta.pop("deleted_at", None)
            with open(original_meta, 'w') as f:
                json.dump(meta, f, indent=2)

        # Remove from manifest
        manifest["deleted"] = [
            item for item in manifest["deleted"]
            if item["summary_id"] != summary_id
        ]
        self._save_manifest(manifest)

        # Clean up empty directories
        if not list(deleted_dir.iterdir()):
            deleted_dir.rmdir()

        logger.info(f"Recovered summary: {summary_id}")
        return True

    def permanent_delete(self, summary_id: str) -> bool:
        """
        Permanently delete a soft-deleted summary.

        Args:
            summary_id: Summary ID to permanently delete

        Returns:
            True if deleted successfully
        """
        manifest = self._load_manifest()

        entry = None
        for item in manifest.get("deleted", []):
            if item["summary_id"] == summary_id:
                entry = item
                break

        if not entry:
            return False

        # Create backup if configured
        if self.config.archive_before_delete:
            self._create_backup(entry)

        # Delete files
        source_key = entry["source_key"]
        period = entry["period"]
        safe_source = source_key.replace(":", "_")
        deleted_dir = self.deleted_dir / safe_source / period

        if deleted_dir.exists():
            shutil.rmtree(deleted_dir)

        # Remove from manifest
        manifest["deleted"] = [
            item for item in manifest["deleted"]
            if item["summary_id"] != summary_id
        ]
        self._save_manifest(manifest)

        logger.info(f"Permanently deleted summary: {summary_id}")
        return True

    def cleanup_expired(self) -> int:
        """
        Clean up summaries past their grace period.

        Returns:
            Number of summaries permanently deleted
        """
        manifest = self._load_manifest()
        now = datetime.utcnow()
        deleted_count = 0

        expired = []
        for item in manifest.get("deleted", []):
            permanent_at = datetime.fromisoformat(item["permanent_delete_at"])
            if now >= permanent_at:
                expired.append(item["summary_id"])

        for summary_id in expired:
            if self.permanent_delete(summary_id):
                deleted_count += 1

        return deleted_count

    def apply_retention_policy(self) -> int:
        """
        Apply retention policy to the archive.

        Soft-deletes summaries older than retention_days.

        Returns:
            Number of summaries soft-deleted
        """
        if self.config.retention_days is None:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=self.config.retention_days)
        deleted_count = 0

        sources_dir = self.archive_root / "sources"
        if not sources_dir.exists():
            return 0

        for md_path in sources_dir.glob("**/*.md"):
            # Skip if already in .deleted
            if ".deleted" in str(md_path):
                continue

            meta_path = md_path.with_suffix(".meta.json")
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)

                generated_at = meta.get("generated_at")
                if generated_at:
                    gen_dt = datetime.fromisoformat(generated_at)
                    if gen_dt < cutoff:
                        self.soft_delete(md_path, reason="retention_policy")
                        deleted_count += 1

            except Exception as e:
                logger.warning(f"Failed to check retention for {md_path}: {e}")

        logger.info(f"Applied retention policy: {deleted_count} summaries soft-deleted")
        return deleted_count

    def list_deleted(self) -> List[DeletedSummaryInfo]:
        """List all soft-deleted summaries."""
        manifest = self._load_manifest()
        return [
            DeletedSummaryInfo(
                summary_id=item["summary_id"],
                source_key=item["source_key"],
                period=item["period"],
                deleted_at=datetime.fromisoformat(item["deleted_at"]),
                reason=item["reason"],
                permanent_delete_at=datetime.fromisoformat(item["permanent_delete_at"]),
                backup_path=item.get("backup_path"),
                original_path=item.get("original_path", ""),
            )
            for item in manifest.get("deleted", [])
        ]

    def _load_manifest(self) -> Dict:
        """Load the deleted manifest."""
        if self.deleted_manifest_path.exists():
            with open(self.deleted_manifest_path, 'r') as f:
                return json.load(f)
        return {"deleted": []}

    def _save_manifest(self, manifest: Dict) -> None:
        """Save the deleted manifest."""
        self.deleted_dir.mkdir(parents=True, exist_ok=True)
        with open(self.deleted_manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    def _add_to_manifest(self, info: DeletedSummaryInfo) -> None:
        """Add a deleted entry to the manifest."""
        manifest = self._load_manifest()
        manifest["deleted"].append(info.to_dict())
        self._save_manifest(manifest)

    def _create_backup(self, entry: Dict) -> Optional[str]:
        """Create a backup of a deleted summary before permanent deletion."""
        source_key = entry["source_key"]
        period = entry["period"]
        safe_source = source_key.replace(":", "_")
        deleted_dir = self.deleted_dir / safe_source / period

        if not deleted_dir.exists():
            return None

        backup_dir = self.archive_root / ".backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{safe_source}_{period}_{timestamp}"

        if self.config.archive_format == "zip":
            backup_path = backup_dir / f"{backup_name}.zip"
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file in deleted_dir.iterdir():
                    zf.write(file, file.name)
        else:
            import tarfile
            backup_path = backup_dir / f"{backup_name}.tar.gz"
            with tarfile.open(backup_path, "w:gz") as tf:
                for file in deleted_dir.iterdir():
                    tf.add(file, file.name)

        logger.info(f"Created backup: {backup_path}")
        return str(backup_path)
