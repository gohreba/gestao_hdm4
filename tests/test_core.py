from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from dataclasses import replace
import unittest
from hdm4_core.excel_reader import read_excel
from hdm4_core.workspace import inspect_zip,network_bytes
from hdm4_core.validation import build_validation,attach_old_values
from hdm4_core.package import build_import_package

ROOT=Path(__file__).resolve().parents[1]
EXCEL=ROOT/'examples'/'Modelo_Ficticio_NAO_USAR_PARA_ESTUDO.xlsx'
ZIP=Path('/mnt/data/HDM4.zip')

class TestPilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=read_excel(EXCEL.read_bytes())
    def test_excel_sheets_and_values(self):
        self.assertEqual(len(self.doc.sheets),5)
        self.assertAlmostEqual(self.doc.cell('Características das rodovias','C7'),9.4)
        self.assertAlmostEqual(self.doc.cell('Características das rodovias','H7'),3.1)
        self.assertEqual(self.doc.cell('Taxas de crescimento e VMD','I25'),1111)
        self.assertEqual(self.doc.cell('Taxas de crescimento e VMD','I33'),1222)
    def test_validate(self):
        changes,errors,details=build_validation(self.doc)
        self.assertEqual(errors,[])
        self.assertEqual(len(changes),12)
        self.assertAlmostEqual(details['resumo']['extensao_modelo_km'],12.5)
        self.assertEqual(details['resumo']['vmd_S1_2024'],1111)
    def test_bind_fail_closed_on_missing_section(self):
        changes,_,_=build_validation(self.doc,sections=['S1'])
        with self.assertRaises(ValueError):
            attach_old_values(changes,[{'SECT_ID':'OTHER'}])
    def test_updated_mdb_needs_distinct_bytes(self):
        changes,_,_=build_validation(self.doc,sections=['S1'])
        changes[0].antes=7.5
        changes[0].valor_chave='S1'
        changes[0].status='alterar'
        with self.assertRaises(ValueError):
            build_import_package(b'fakeMDB',b'fakeMDB','HDM4/Exports/SC-110.mdb',EXCEL.read_bytes(),changes,{}, {})
    @unittest.skipUnless(ZIP.exists(),'ZIP do usuário não foi incluído no repositório')
    def test_source_zip(self):
        b=ZIP.read_bytes()
        info=inspect_zip(b)
        self.assertEqual(len(info['exports']),11)
        self.assertEqual(len(network_bytes(b,info['network'])),262144)

if __name__=='__main__':
    unittest.main()

class TestEdgeCases(unittest.TestCase):
    def test_deselect_every_field_does_not_reenable_them(self):
        excel=read_excel(EXCEL.read_bytes())
        changes,errors,_=build_validation(excel,fields=[])
        self.assertFalse(errors)
        self.assertEqual(changes,[])
    def test_dangerous_zip_path_rejected(self):
        stream=BytesIO()
        with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
            archive.writestr('../evil.txt','bad')
        with self.assertRaises(ValueError):
            inspect_zip(stream.getvalue())
