import unittest
from copy import deepcopy
from pathlib import Path
from hdm4_core.excel_reader import read_excel
from hdm4_core.layout import discover_road_sections,discover_traffic_sections,discover_traffic_summary,audit_traffic,to_col
from hdm4_core.validation import build_validation
from hdm4_core.catalog import build_catalog
from hdm4_core.references import (build_reference_templates,compare_reference,export_archive,validate_archive)

ORIG=Path('/mnt/data/Dados de projeto HDM - SC-110, Pomerode - Pé da Serra.xlsx')
class DynamicSections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ORIG.exists():raise unittest.SkipTest('Planilha operacional só está disponível no ambiente de análise')
        cls.xls=read_excel(ORIG.read_bytes())

    def test_original_real_10_slots_only_two_active(self):
        a=audit_traffic(self.xls)
        self.assertEqual([s.id for s in a['secoes_rodovia']],['S1','S2'])
        self.assertEqual([(s.id,s.heading_row) for s in a['blocos']],[('S1',20),('S2',28)])
        self.assertEqual(a['vmd_2024'],{'S1':5378.,'S2':5644.})
        self.assertEqual(a['erros'],[])
        self.assertEqual(len(a['resumos']),2)

    def _third_section(self):
        x=deepcopy(self.xls)
        r=x.sheets['Características das rodovias ']
        for i in range(6,35):
            for target,source in [('K','A'),('L','B'),('M','C'),('N','D')]:
                if f'{source}{i}' in r:r[f'{target}{i}']=r[f'{source}{i}']
        r['K3']='S3 - TERCEIRO TRECHO DE TESTE'
        r['M7']=5.
        t=x.sheets['Taxas de crescimento e VMD']
        t['B36']='S3 - TERCEIRO TRECHO DE TESTE'
        for i,v in enumerate([101.,10.,20.,30.]):t[f'I{37+i}']=v
        t['I41']=161.
        for off,values in [(0,[50,5,10,15,80]),(1,[101,10,20,30,161]),(2,[0,0,0,0,0]),(3,[101,10,20,30,161])]:
            row=111+off
            for col,val in zip('EFGHI',values):t[f'{col}{row}']=float(val)
        t['B111']='S3 - TERCEIRO TRECHO DE TESTE'
        return x

    def test_s3_dynamic_no_hardcoded_limit(self):
        x=self._third_section()
        audit=audit_traffic(x)
        self.assertEqual(audit['erros'],[])
        self.assertEqual([r.id for r in audit['secoes_rodovia']],['S1','S2','S3'])
        self.assertEqual(audit['vmd_2024']['S3'],161)
        changes,errors,details=build_validation(x,sections=['S3'])
        self.assertEqual(errors,[])
        self.assertEqual(len(changes),6)
        self.assertEqual(changes[0].origem,'Características das rodovias!M7')
        catalog=build_catalog(x)
        self.assertTrue(any(r['Seção']=='S3' and r['Célula']=='M30' for r in catalog))
        self.assertTrue(any(r['Seção']=='S3' and r['Célula']=='I41' for r in catalog))

    def test_s3_total_mismatch_blocks(self):
        x=self._third_section()
        x.sheets['Taxas de crescimento e VMD']['I41']=999.
        a=audit_traffic(x)
        self.assertTrue(any('S3' in e for e in a['erros']))
        _,errors,_=build_validation(x)
        self.assertTrue(errors)

    def test_not_confuse_s3_summarized_without_label_as_s2(self):
        x=self._third_section()
        x.sheets['Taxas de crescimento e VMD']['B111']=0.0
        summary=discover_traffic_summary(x)
        self.assertEqual(summary['S3'][-1]['TOTAL'],161)
        self.assertEqual(len(summary['S2']),4)

    def test_column_steps(self):
        self.assertEqual([to_col(1+5*i) for i in range(10)],
             ['A','F','K','P','U','Z','AE','AJ','AO','AT'])

class MonetaryReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ORIG.exists():raise unittest.SkipTest('Planilha operacional só está disponível no ambiente de análise')
        cls.xls=read_excel(ORIG.read_bytes())

    def test_historical_months_and_diff(self):
        data=build_reference_templates(self.xls)
        self.assertEqual(list(data['referencias']),['2019-04','2021-07'])
        self.assertEqual(len(data['campos']),41)
        old=data['referencias']['2021-07']['valores']
        updated=dict(old)
        key=next(k for k,v in old.items() if v is not None)
        updated[key]=updated[key]*1.1
        diff,err=compare_reference(old,updated,data['campos'])
        self.assertFalse(err)
        self.assertEqual(len(diff),1)
        self.assertEqual(diff[0]['campo'],key)
        self.assertTrue(export_archive(data))
        self.assertEqual(validate_archive(data),data)

    def test_negative_value_rejected(self):
        data=build_reference_templates(self.xls)
        old=data['referencias']['2021-07']['valores']
        updated=dict(old)
        updated[next(iter(updated))]=-100
        _,err=compare_reference(old,updated,data['campos'])
        self.assertTrue(err)

if __name__=='__main__':unittest.main()
