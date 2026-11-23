
"""Detecta módulos ausentes ou incompatíveis antes do Streamlit iniciar."""
from pathlib import Path
import importlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "hdm4_core.excel_reader": ("read_excel",),
    "hdm4_core.validation": ("build_validation", "attach_old_values", "SAFE_FIELDS", "REVIEW_FIELDS"),
    "hdm4_core.workspace": ("inspect_zip", "network_bytes"),
    "hdm4_core.mdb_bridge": ("MDBError", "snapshot", "update_and_verify", "inspect_tables"),
    "hdm4_core.package": ("build_import_package",),
    "hdm4_core.catalog": ("build_catalog", "catalog_csv", "catalog_summary"),
}

class TestDeployImportContract(unittest.TestCase):
    def test_required_python_module_files(self):
        for name in MODULES:
            with self.subTest(name=name):
                self.assertTrue((ROOT / (name.replace('.', '/') + '.py')).is_file(), f"Ausente: {name}")

    def test_import_names_expected_by_app(self):
        for name, names in MODULES.items():
            module = importlib.import_module(name)
            for symbol in names:
                with self.subTest(name=name, symbol=symbol):
                    self.assertTrue(hasattr(module, symbol), f"{symbol} ausente em {name}")

    def test_deployment_essential_files(self):
        for rel in ('app.py', 'java/HdmMdbBridge.java', 'requirements.txt', 'packages.txt'):
            with self.subTest(rel=rel):
                self.assertTrue((ROOT / rel).is_file(), f"Ausente: {rel}")
