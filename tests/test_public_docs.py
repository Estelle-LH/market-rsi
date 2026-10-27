"""Portable public-document navigation checks; no live/research imports."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def local_link_paths(body):
    """Yield local Markdown link paths, excluding fenced examples and anchors."""
    visible = []
    fenced = False
    for line in body.splitlines():
        if line.lstrip().startswith(chr(96) * 3):
            fenced = not fenced
            continue
        if not fenced:
            visible.append(line)
    for target in re.findall(r"\]\(([^)\s]+)\)", "\n".join(visible)):
        if target.startswith(("https://", "http://", "mailto:", "#")):
            continue
        yield target.split("#", 1)[0]


class PublicDocsTests(unittest.TestCase):
    def test_readme_routes_new_readers_to_setup_evidence_and_reproduction(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for relative in (
            "docs/README.md",
            "docs/QUICKSTART.md",
            "docs/REPRODUCIBILITY.md",
            "docs/experiments/README.md",
        ):
            with self.subTest(path=relative):
                self.assertIn("](" + relative + ")", readme)
                self.assertTrue((ROOT / relative).is_file())

    def test_link_parser_checks_paths_but_ignores_remote_and_fenced_examples(self):
        fence = chr(96) * 3
        body = "\n".join([
            "[local](docs/README.md#route)",
            "[remote](https://example.invalid/file)",
            "[heading](#route)",
            fence + "text",
            "[example](not-a-real-file.md)",
            fence,
        ])
        self.assertEqual(list(local_link_paths(body)), ["docs/README.md"])

    def test_public_document_local_link_paths_exist_inside_checkout(self):
        paths = [
            ROOT / "README.md",
            ROOT / "benchmarks/earnings/README.md",
            *sorted((ROOT / "docs").rglob("*.md")),
        ]
        checked = 0
        for path in paths:
            body = path.read_text(encoding="utf-8")
            for target in local_link_paths(body):
                destination = (path.parent / target).resolve()
                with self.subTest(document=str(path.relative_to(ROOT)), target=target):
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.exists(), str(destination))
                checked += 1
        self.assertGreater(checked, 20, "The link check must inspect real navigation.")


if __name__ == "__main__":
    unittest.main()
