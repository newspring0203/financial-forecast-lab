"""Tests shipped with the final release; legacy audit tests stay local."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from forecast_lab.data import Facts,bounds
from forecast_lab.models import revenue_forecast,conditional_profit,metrics
from forecast_lab.cashflow import bridge
from forecast_lab.integrity import verify_source,guard_origin
from run_final import choose

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=Facts.load('data/raw/ti_companyfacts.json');cls.rows,cls.sources=cls.f.snapshot('2026-02-06',2025)
    def test_complete_history(self):
        self.assertEqual(len(self.rows),56);self.assertEqual(self.rows[-1]['period'],'2025Q4')
        self.assertEqual(len(set(x['period'] for x in self.rows)),56)
    def test_official_annual_controls(self):
        for year,revenue,profit in [(2024,15641,5465),(2025,17682,6023)]:
            rows=[x for x in self.rows if x['year']==year]
            self.assertEqual(sum(x['revenue'] for x in rows),revenue);self.assertEqual(sum(x['operating_profit'] for x in rows),profit)
    def test_lineage_rebuilds_values(self):
        for row in self.sources:self.assertAlmostEqual(row['value_usd_million'],sum(x['sign']*x['value_usd'] for x in row['sources'])/1e6)
    def test_cf_difference(self):
        v,method,sources=self.f.quarter('capex',2025,2,'2026-02-06')
        self.assertEqual(method,'ytd_difference');self.assertEqual(v,(sources[0]['value_usd']-sources[1]['value_usd'])/1e6)
    def test_future_data_cannot_change_past(self):
        before=self.f.snapshot('2024-02-02',2023)[0];raw=copy.deepcopy(self.f.raw)
        for tag in raw['facts']['us-gaap'].values():
            for units in tag.get('units',{}).values():
                for fact in units:
                    if fact['filed']>'2024-02-02':fact['val']=999999999999
        self.assertEqual(before,Facts(raw).snapshot('2024-02-02',2023)[0])
    def test_source_tamper_rejected(self):
        verify_source('data/raw/ti_companyfacts.json','data/raw/manifest.json')
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'bad';p.write_text('bad')
            with self.assertRaises(ValueError):verify_source(p,'data/raw/manifest.json')
    def test_origin_guards(self):
        with self.assertRaises(ValueError):guard_origin([{'end':'2024-03-31'}],[{'sources':[{'filed':'2024-02-02'}]}],'2024-02-02','2023-12-31','2024-03-31')
        with self.assertRaises(ValueError):guard_origin([{'end':'2023-12-31'}],[{'sources':[{'filed':'2024-04-24'}]}],'2024-02-02','2023-12-31','2024-03-31')
    def test_boolean_quarter_rejected(self):
        with self.assertRaises(ValueError):bounds(2024,True)
    def test_seasonal_recursion(self):
        p,_=revenue_forecast(np.arange(1.,21.),'seasonal_naive',6);np.testing.assert_array_equal(p,[17,18,19,20,17,18])
    def test_blend_is_equal_weight(self):
        y=[x['revenue'] for x in self.rows]
        a,_=revenue_forecast(y,'lagged_ols',4);b,_=revenue_forecast(y,'holt_winters',4);c,_=revenue_forecast(y,'equal_blend',4)
        np.testing.assert_allclose(c,.5*a+.5*b)
    def test_delta_profit_known_linear_case(self):
        rows=[dict(revenue=100+t*t,operating_profit=2*(100+t*t)+5) for t in range(13)]
        p,_=conditional_profit(rows,[300,400],'delta_ols_12');np.testing.assert_allclose(p,[605,805],atol=1e-10)
    def test_margin_hand_calculation(self):
        rows=[dict(revenue=100,operating_profit=20) for _ in range(13)]
        p,_=conditional_profit(rows,[120,150],'trailing_margin_4');np.testing.assert_allclose(p,[24,30])
    def test_negative_profit_not_clipped(self):
        rows=[dict(revenue=100+t*t,operating_profit=-2*(100+t*t)) for t in range(13)]
        p,_=conditional_profit(rows,[300],'delta_ols_12');self.assertAlmostEqual(p[0],-600)
    def test_bad_profit_input(self):
        for future in [[],[float('nan')],[-1],[[100]]]:
            with self.assertRaises(ValueError):conditional_profit(self.rows,future,'delta_ols_12')
        with self.assertRaises(ValueError):conditional_profit(self.rows,[100],'bad')
    def test_degenerate_delta_regression(self):
        rows=[dict(revenue=100,operating_profit=20) for _ in range(13)]
        with self.assertRaises(ValueError):conditional_profit(rows,[100],'delta_ols_12')
    def test_selection_ignores_evaluation(self):
        rows=[dict(stage='validation',model='a',error=1),dict(stage='validation',model='b',error=2),dict(stage='evaluation',model='a',error=1e9),dict(stage='evaluation',model='b',error=0)]
        self.assertEqual(choose(rows,'model'),'a')
        rows[-2]['error']=0;rows[-1]['error']=1e9;self.assertEqual(choose(rows,'model'),'a')
    def test_metric_by_hand(self):self.assertEqual(metrics([100,200],[110,180])['mae'],15)
    def test_bridge_change_and_tax(self):
        prior=[dict(revenue=100,capex=10,depreciation=5,core_working_capital=80) for _ in range(4)]
        a=bridge(440,100,prior);b=bridge(440,100,prior,tax_rate=.30)
        self.assertAlmostEqual(a['simplified_fcff'],45);self.assertAlmostEqual(b['simplified_fcff'],40)
    def test_monitor_kept_separate(self):
        r=json.loads(Path('outputs/final_results.json').read_text())
        for s in r['scores']:self.assertEqual(s['n'],{'validation':20,'evaluation':8,'monitor_2026':3}[s['stage']])
        self.assertEqual(r['default_pipeline'],'original')
    def test_fcff_identity(self):
        r=json.loads(Path('outputs/final_results.json').read_text())
        for row in r['final_fcff']:self.assertAlmostEqual(row['simplified_fcff'],row['nopat']+row['depreciation']-row['capex']-row['change_core_wc'])

if __name__=='__main__':unittest.main()
