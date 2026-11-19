from pathlib import Path
import unittest
from hdm4_core.excel_reader import read_excel
from hdm4_core.catalog import build_catalog, catalog_csv, catalog_summary
from hdm4_core.validation import build_validation, REVIEW_FIELDS

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/mnt/data/Dados de projeto HDM - SC-110, Pomerode - Pé da Serra.xlsx')
FICT=ROOT/'examples'/'Modelo_Ficticio_NAO_USAR_PARA_ESTUDO.xlsx'

class TestMapping(unittest.TestCase):
    def test_read_only_catalog_never_turns_post_obra_into_direct_sections(self):
        src=read_excel(FICT.read_bytes())
        records=build_catalog(src)
        self.assertTrue(records)
        for r in records:
            if r['Cenário']=='PÓS-OBRA':
                self.assertNotEqual(r['Situação'],'VALIDADO_IRI_NO_HDM4')
                self.assertNotEqual(r['Situação'],'HABILITADO_PILOTO')
                self.assertIn('Prj_sectOptImp',r['Destino candidato'])

    def test_catalog_has_traceability(self):
        src=read_excel(FICT.read_bytes())
        records=build_catalog(src)
        csv=catalog_csv(records)
        self.assertIn('Célula',csv)
        self.assertIn('Destino candidato',csv)
        self.assertIn('BASE',csv)

    def test_review_fields_are_off_by_default(self):
        src=read_excel(FICT.read_bytes())
        safe,errors,_=build_validation(src,sections=['S1'])
        self.assertFalse(errors)
        review={f[0] for f in REVIEW_FIELDS}
        self.assertFalse({c.campo for c in safe}&review)
        selected,errors,_=build_validation(src,sections=['S1'],fields=['CWAY_WIDTH'])
        self.assertEqual(selected,[])
        self.assertTrue(errors)

    @unittest.skipUnless(SOURCE.exists(),'Planilha original não publicada no repositório')
    def test_original_5_sheets_and_statuses(self):
        src=read_excel(SOURCE.read_bytes())
        rows=build_catalog(src)
        summary=catalog_summary(rows)
        self.assertGreater(summary['itens_total'],550)
        self.assertEqual(set(summary['por_grupo']) & {'Rede / pavimento','Frota','Manutenção','Tráfego','Orçamento'},
                         {'Rede / pavimento','Frota','Manutenção','Tráfego','Orçamento'})
        iri=[r for r in rows if r['Célula']=='C30' and r['Aba'].startswith('Características')]
        self.assertEqual(len(iri),1)
        self.assertEqual(iri[0]['Situação'],'VALIDADO_IRI_NO_HDM4')
        self.assertEqual(iri[0]['Valor na planilha'],3.6)
        pos=[r for r in rows if r['Célula']=='D30' and r['Aba'].startswith('Características')]
        self.assertEqual(pos[0]['Valor na planilha'],2.)
        self.assertEqual(pos[0]['Situação'],'ESTRUTURA_PENDENTE')

    @unittest.skipUnless(SOURCE.exists(),'Planilha original não publicada no repositório')
    def test_explicit_lane_width_conversion(self):
        src=read_excel(SOURCE.read_bytes())
        changes,errors,_=build_validation(src,sections=['S1','S2'],fields=['CWAY_WIDTH','MTLANES'])
        self.assertFalse(errors)
        self.assertEqual(len(changes),4)
        widths=[c for c in changes if c.campo=='CWAY_WIDTH']
        self.assertTrue(all(c.valor==7 for c in widths))
        self.assertTrue(all('×' in c.origem for c in widths))

if __name__=='__main__': unittest.main()
