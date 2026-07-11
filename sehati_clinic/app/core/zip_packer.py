"""
ZipPacker — in-memory ZIP file builder untuk Owner Export Pack.

Usage:
    packer = ZipPacker()
    packer.add_readme(metadata={...})
    packer.add_file("01_daily_summary.csv", csv_bytes)
    packer.add_file("02_visits_raw.csv", csv_bytes)
    packer.add_data_dictionary(dictionary_markdown_bytes)
    zip_bytes = packer.finalize()

ZIP dibangun di memory (BytesIO). Untuk pack < ~100MB ini OK.
Kalau dataset besar, future: pakai temp file di disk lalu stream.
"""

import io
import zipfile
from datetime import datetime
from typing import Optional


class ZipPacker:
    """In-memory ZIP file builder."""

    def __init__(self):
        self._buf = io.BytesIO()
        self._zf = zipfile.ZipFile(
            self._buf,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        )
        self._file_count = 0
        self._total_bytes = 0
        self._files_added: list[tuple[str, int]] = []  # (filename, size)

    def add_file(self, filename: str, content: bytes) -> None:
        """Append file ke ZIP."""
        self._zf.writestr(filename, content)
        self._file_count += 1
        self._total_bytes += len(content)
        self._files_added.append((filename, len(content)))

    def add_readme(
        self,
        title: str,
        metadata: dict,
        files_summary: Optional[list[dict]] = None,
    ) -> None:
        """
        Generate README.txt dengan metadata pack.

        Args:
            title: heading utama (e.g., "Sehati Clinic — Weekly Pack")
            metadata: dict berisi info pack (range, format, mask_pii, owner, dll)
            files_summary: optional list of {filename, row_count, description}
        """
        lines = []
        lines.append("=" * 70)
        lines.append(title)
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append("")

        lines.append("METADATA:")
        for k, v in metadata.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

        if files_summary:
            lines.append("DATASETS:")
            for f in files_summary:
                fname = f.get("filename", "?")
                rows = f.get("row_count", "?")
                desc = f.get("description", "")
                lines.append(f"  {fname} — {rows} rows — {desc}")
            lines.append("")

        lines.append("DATA DICTIONARY:")
        lines.append("  Lihat DATA_DICTIONARY.md di dalam ZIP ini untuk schema lengkap.")
        lines.append("")
        lines.append("=" * 70)
        lines.append("END OF README")
        lines.append("=" * 70)

        content = "\n".join(lines).encode("utf-8")
        self.add_file("README.txt", content)

    def add_data_dictionary(self, dictionary_bytes: bytes) -> None:
        """Append DATA_DICTIONARY.md."""
        self.add_file("DATA_DICTIONARY.md", dictionary_bytes)

    def finalize(self) -> bytes:
        """Close ZIP dan return bytes complete."""
        self._zf.close()
        self._buf.seek(0)
        return self._buf.getvalue()

    @property
    def file_count(self) -> int:
        return self._file_count

    @property
    def total_uncompressed_bytes(self) -> int:
        return self._total_bytes

    @property
    def files_added(self) -> list[tuple[str, int]]:
        return list(self._files_added)


__all__ = ["ZipPacker"]
