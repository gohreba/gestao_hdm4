"""Testes reproduzíveis no GitHub (sem os arquivos operacionais da SIE)."""
from pathlib import Path
from copy import deepcopy
import unittest
from hdm4_core.excel_reader import read_excel
from hdm4_core.layout import discover_road_sections,audit_traffic
from hdm4_core.validation import build_validation
from hdm4_core.catalog import build_catalog
from hdm4_core.references import compare_reference,validate_archive,export_archive

FILE=Path(__file__).resolve().parents[1]/'examples'/'Modelo_Ficticio_NAO_USAR_PARA_ESTUDO.xlsx'

class TestDynamicFixture(unittest.TestCase):
    def test_three_sections_without_real_data(self):
        x=read_excel(FILE.read_bytes())
        a=x.sheets['Características das rodovias']
        a['K3']='S3 - EXEMPLO FICTÍCIO'
        for row in [7,30,31,32,33,34]:
            a[f'M{row}']=a[f'C{row}']
        t=x.sheets['Taxas de crescimento e VMD']
        t['B36']='S3 - EXEMPLO FICTÍCIO'
        t['I36']='2024 novo'
        for row,vehicle,value in [(37,'VL',150),(38,'ON',10),(39,'VC1',20),(40,'VC2',30)]:
            t[f'B{row}']=vehicle
            t[f'I{row}']=value
        t['B41']='Total';t['I41']=210
        roads=discover_road_sections(x)
        self.assertEqual([r.base_col for r in roads],['C','H','M'])
        audit=audit_traffic(x)
        self.assertEqual(audit['erros'],[])
        self.assertEqual(audit['vmd_2024']['S3'],210)
        changes,errors,summary=build_validation(x)
        self.assertEqual(errors,[])
        self.assertEqual(summary['resumo']['quantidade_secoes'],3)
        self.assertEqual(len(changes),18)
        rows=build_catalog(x)
        self.assertTrue(any(r['Seção']=='S3' and r['Célula']=='M30' for r in rows))
        self.assertTrue(any(r['Seção']=='S3' and r['Célula']=='I41' for r in rows))

    def test_inconsistent_third_section_blocks(self):
        x=read_excel(FILE.read_bytes())
        x.sheets['Características das rodovias']['K3']='S3 FICTÍCIO'
        t=x.sheets['Taxas de crescimento e VMD'];t['B36']='S3 FICTÍCIO';t['I36']='2024 novo'
        for row,veh,num in [(37,'VL',100),(38,'ON',10),(39,'VC1',20),(40,'VC2',30)]:
            t[f'B{row}']=veh;t[f'I{row}']=num
        t['I41']=99
        a=audit_traffic(x)
        self.assertTrue(any('S3' in e for e in a['erros']))

if __name__=='__main__':unittest.main()
