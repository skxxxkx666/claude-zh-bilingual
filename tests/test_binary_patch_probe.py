import struct
import tempfile
import unittest
from pathlib import Path

from scripts.probe.binary_patch_probe import (
    create_probe,
    parse_pe_sections,
    plan_patch,
)


def pe_with_bun_payload(payload: bytes) -> bytes:
    pe_offset = 0x80
    raw_start = 0x200
    data = bytearray(raw_start + len(payload))
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_offset)
    data[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe_offset + 6, 1)
    struct.pack_into("<H", data, pe_offset + 20, 0)

    section = pe_offset + 24
    data[section : section + 8] = b".bun\0\0\0\0"
    struct.pack_into(
        "<IIII",
        data,
        section + 8,
        len(payload),
        0x1000,
        len(payload),
        raw_start,
    )
    struct.pack_into("<I", data, section + 36, 0x40000040)
    data[raw_start:] = payload
    return bytes(data)


class BinaryPatchProbeTests(unittest.TestCase):
    def test_parses_bun_section(self) -> None:
        sections = parse_pe_sections(pe_with_bun_payload(b"payload"))
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].name, ".bun")
        self.assertEqual(sections[0].raw_start, 0x200)
        self.assertEqual(sections[0].raw_size, 7)

    def test_accepts_only_length_prefixed_bun_occurrences(self) -> None:
        header = struct.pack("<II", 9, 8)
        payload = header + b"Thinking" + b"\0" + b"Thinking"
        plan = plan_patch(
            pe_with_bun_payload(payload),
            "Thinking",
            "Thnkng!!",
        )
        self.assertEqual(plan["matches"], 2)
        self.assertEqual(len(plan["accepted"]), 1)
        self.assertEqual(len(plan["skipped"]), 1)
        self.assertEqual(plan["skipped"][0]["reason"], "Bun string header mismatch")

    def test_creates_isolated_equal_length_probe(self) -> None:
        header = struct.pack("<II", 9, 8)
        original = pe_with_bun_payload(header + b"Thinking")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "claude.exe"
            output_path = root / "claude-probe.exe"
            input_path.write_bytes(original)

            report = create_probe(
                input_path,
                output_path,
                "Thinking",
                "Thnkng!!",
            )

            self.assertEqual(input_path.read_bytes(), original)
            self.assertEqual(
                output_path.read_bytes().count(b"Thnkng!!"),
                1,
            )
            self.assertEqual(report["patched_occurrences"], 1)
            self.assertEqual(report["input_bytes"], report["output_bytes"])
            self.assertNotEqual(report["input_sha256"], report["output_sha256"])

    def test_rejects_unequal_length_probe(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly the same byte length"):
            plan_patch(
                pe_with_bun_payload(b"Thinking"),
                "Thinking",
                "Short",
            )

    def test_nul_padding_updates_length_prefix(self) -> None:
        header = struct.pack("<II", 9, 8)
        original = pe_with_bun_payload(header + b"Thinking")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "claude.exe"
            output_path = root / "claude-probe.exe"
            input_path.write_bytes(original)

            create_probe(
                input_path,
                output_path,
                "Thinking",
                "Think",
                "nul",
            )

            patched = output_path.read_bytes()
            offset = patched.index(b"Think\0\0\0")
            self.assertEqual(
                struct.unpack_from("<II", patched, offset - 8),
                (9, 5),
            )

    def test_space_padding_preserves_length_prefix(self) -> None:
        header = struct.pack("<II", 9, 8)
        original = pe_with_bun_payload(header + b"Thinking")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "claude.exe"
            output_path = root / "claude-probe.exe"
            input_path.write_bytes(original)

            create_probe(
                input_path,
                output_path,
                "Thinking",
                "Think",
                "space",
            )

            patched = output_path.read_bytes()
            offset = patched.index(b"Think   ")
            self.assertEqual(
                struct.unpack_from("<II", patched, offset - 8),
                (9, 8),
            )


if __name__ == "__main__":
    unittest.main()
