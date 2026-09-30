"""Small synthetic tests; no installed or user CAD files are modified."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from portable_models import normalize_library_models


class PortableModelsTest(unittest.TestCase):
    def test_variables_collision_transform_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'project'
            lib = output / 'Test.pretty'
            lib.mkdir(parents=True)
            for source, content in [('core', b'core STEP'), ('vendor', b'vendor STEP')]:
                (root / source).mkdir()
                (root / source / 'same.step').write_bytes(content)
            footprint = lib / 'Test.kicad_mod'
            text = ('(footprint "Test"\r\n'
                    ' (model "${KICAD10_3DMODEL_DIR}/same.step"\r\n'
                    '  (offset (xyz 1 2 3)) (scale (xyz 2 3 4)) (rotate (xyz 90 0 45)))\r\n'
                    ' (model "${KICAD8_3RD_PARTY}/same.step"\r\n'
                    '  (offset (xyz 0 0 0)) (hide yes)))\r\n')
            footprint.write_bytes(text.encode())
            report = normalize_library_models(output, variable_roots={
                'KICAD10_3DMODEL_DIR': root/'core', 'KICAD8_3RD_PARTY': root/'vendor'})
            self.assertEqual(report['unique_models'], 2)
            self.assertEqual(report['modified_footprints'], 1)
            expected = text
            for old, source in [('${KICAD10_3DMODEL_DIR}/same.step', 'core'),
                                ('${KICAD8_3RD_PARTY}/same.step', 'vendor')]:
                digest = hashlib.sha256((root/source/'same.step').read_bytes()).hexdigest()
                expected = expected.replace(old, '${KIPRJMOD}/models/same-'+digest[:12]+'.step')
            self.assertEqual(footprint.read_bytes(), expected.encode())
            second = normalize_library_models(output)
            self.assertEqual(second['modified_footprints'], 0)
            self.assertEqual(second['unique_models'], 2)

    def test_absolute_missing_is_transactional(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lib = root / 'Test.pretty'
            lib.mkdir()
            source = root / 'source.stp'
            source.write_bytes(b'step')
            a = lib / 'A.kicad_mod'
            a.write_text(f'(footprint "A" (model "{source.as_posix()}"))', encoding='utf-8')
            b = lib / 'B.kicad_mod'
            b.write_text('(footprint "B" (model "${UNKNOWN}/notthere.stp"))', encoding='utf-8')
            before = a.read_bytes()
            with self.assertRaises(FileNotFoundError):
                normalize_library_models(root)
            self.assertEqual(a.read_bytes(), before)
            b.write_text('(footprint "B")', encoding='utf-8')
            result = normalize_library_models(root)
            self.assertEqual(result['model_references'], 1)
            self.assertEqual(result['footprints_without_models'], ['Test.pretty/B.kicad_mod'])
            self.assertTrue(source.exists())

    def test_missing_model_omission_preserves_other_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lib = root / 'Test.pretty'
            lib.mkdir()
            footprint = lib / 'Test.kicad_mod'
            text = ('(footprint "Test" (pad "1" smd rect (at 0 0)) '
                    '(model "${UNKNOWN}/no (model).step" (offset (xyz 1 2 3))) '
                    '(property "Value" "Test"))')
            footprint.write_text(text, encoding='utf-8')
            result = normalize_library_models(root, omit_missing=True)
            self.assertEqual(len(result['omitted_missing']), 1)
            self.assertEqual(footprint.read_text(encoding='utf-8'),
                             '(footprint "Test" (pad "1" smd rect (at 0 0))  (property "Value" "Test"))')

    def test_supplemental_exact_package_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lib = root / 'Test.pretty'
            lib.mkdir()
            source = root / 'manufacturer.stp'
            source.write_bytes(b'manufacturer exact package CAD')
            fp = lib / 'KnownPackage.kicad_mod'
            fp.write_text('(footprint "KnownPackage" (pad "1" smd rect (at 0 0)))', encoding='utf-8')
            result = normalize_library_models(root, project_model_sources={'KnownPackage':source})
            self.assertEqual(len(result['supplemental_package_models']), 1)
            self.assertEqual(result['model_references'], 1)


if __name__ == '__main__':
    unittest.main()
