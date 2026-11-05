"""Reproduce the final exploratory TXN forecasting comparison, offline."""
import csv
import hashlib
import json
from pathlib import Path
import platform
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from forecast_lab.data import Facts,FLOWS,bounds
from forecast_lab.models import revenue_forecast,conditional_profit,metrics
from forecast_lab.cashflow import bridge
from forecast_lab.integrity import verify_source,guard_origin
ROOT=Path(__file__).resolve().parent


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def choose(rows,field):
    # Only validation rows decide; the test/monitor values cannot affect selection.
    candidates=sorted(set(x[field] for x in rows))
    scores={m:float(np.mean([abs(x['error']) for x in rows if x['stage']=='validation' and x[field]==m])) for m in candidates}
    if not all(np.isfinite(list(scores.values()))):raise ValueError('Missing validation scores')
    return min(scores,key=lambda m:(scores[m],m))


def main():
    plan=json.loads((ROOT/'release_plan.json').read_text());out=ROOT/'outputs';out.mkdir(exist_ok=True)
    verify_source(ROOT/'data/raw/ti_companyfacts.json',ROOT/'data/raw/manifest.json')
    facts=Facts.load(ROOT/'data/raw/ti_companyfacts.json')
    revenue_models=plan['revenue_candidates'];profit_models=plan['profit_candidates']
    cache=[];predictions=[]
    for year in range(2019,2027):
        for q in range(1,5):
            if year==2026 and q==4:break
            oy,oq=(year-1,4) if q==1 else (year,q-1)
            origin_date=facts.first_release(oy,oq);target_date=facts.first_release(year,q)
            train,sources=facts.snapshot(origin_date,oy,oq)
            actual=facts.snapshot(target_date,year,q)[0][-1]
            guard_origin(train,sources,origin_date,bounds(oy,oq)[1],actual['end'])
            stage='validation' if year<=2023 else ('evaluation' if year<=2025 else 'monitor_2026')
            cache.append(dict(year=year,q=q,origin_date=origin_date,train=train,actual=actual,stage=stage))
            for method in revenue_models:
                p,_=revenue_forecast([x['revenue'] for x in train],method,1)
                predictions.append(dict(stage=stage,period=actual['period'],origin_date=origin_date,actual_filed=target_date,
                    revenue_model=method,actual=actual['revenue'],prediction=float(p[0]),error=float(p[0]-actual['revenue'])))
    selected_r=choose(predictions,'revenue_model')
    profit_predictions=[]
    for origin in cache:
        row=next(x for x in predictions if x['period']==origin['actual']['period'] and x['revenue_model']==selected_r)
        for method in profit_models:
            p,_=conditional_profit(origin['train'],[row['prediction']],method)
            profit_predictions.append(dict(stage=origin['stage'],period=row['period'],profit_model=method,actual=origin['actual']['operating_profit'],prediction=float(p[0]),error=float(p[0]-origin['actual']['operating_profit'])))
    selected_p=choose(profit_predictions,'profit_model')
    scores=[]
    for target,rows,field in [('revenue',predictions,'revenue_model'),('operating_profit',profit_predictions,'profit_model')]:
        for stage in ['validation','evaluation','monitor_2026']:
            for method in sorted(set(x[field] for x in rows)):
                sample=[x for x in rows if x['stage']==stage and x[field]==method]
                scores.append(dict(target=target,stage=stage,model=method,**metrics([x['actual'] for x in sample],[x['prediction'] for x in sample])))
    annual=[]
    for year in range(2019,2026):
        origin_date=facts.first_release(year-1,4);train,_=facts.snapshot(origin_date,year-1)
        actual=facts.snapshot(facts.first_release(year,4),year)[0]
        current=actual[-4:]
        proxy=sum(x['operating_profit'] for x in current)*.75+sum(x['depreciation'] for x in current)-sum(x['capex'] for x in current)-(current[-1]['core_working_capital']-actual[-5]['core_working_capital'])
        for label,rm,pm in [('original','holt_winters','level_ols_12'),('revised',selected_r,selected_p)]:
            r,_=revenue_forecast([x['revenue'] for x in train],rm,4);p,_=conditional_profit(train,r,pm)
            b=bridge(float(r.sum()),float(p.sum()),train[-4:])
            annual.append(dict(stage='validation' if year<=2023 else 'evaluation',year=year,pipeline=label,revenue_model=rm,profit_model=pm,
                actual_revenue=sum(x['revenue'] for x in current),predicted_revenue=float(r.sum()),
                predicted_operating_profit=float(p.sum()),actual_operating_profit=sum(x['operating_profit'] for x in current),
                predicted_simplified_fcff=b['simplified_fcff'],reported_input_fcff_proxy=proxy,fcff_error=b['simplified_fcff']-proxy))
    final,lineage=facts.snapshot('2026-02-06',2025)
    forecasts=[];final_bridges=[]
    for label,rm,pm in [('original','holt_winters','level_ols_12'),('revised',selected_r,selected_p)]:
        r,r_info=revenue_forecast([x['revenue'] for x in final],rm,4);p,p_info=conditional_profit(final,r,pm)
        for q in range(1,5):forecasts.append(dict(pipeline=label,asof='2026-02-06',period=f'2026Q{q}',revenue=float(r[q-1]),operating_profit=float(p[q-1])))
        final_bridges.append(dict(pipeline=label,revenue_model=rm,profit_model=pm,**bridge(float(r.sum()),float(p.sum()),final[-4:])))
    annual_scores=[]
    for stage in ['validation','evaluation']:
        for pipeline in ['original','revised']:
            rows=[x for x in annual if x['stage']==stage and x['pipeline']==pipeline]
            e=np.array([x['fcff_error'] for x in rows])
            annual_scores.append(dict(stage=stage,pipeline=pipeline,n=len(rows),fcff_mae=float(np.abs(e).mean()),fcff_rmse=float(np.sqrt((e**2).mean()))))
    reconciliation=[]
    for year in range(2012,2026):
        for metric in FLOWS:
            actual=facts.fact(metric,f'{year}-01-01',f'{year}-12-31','2026-02-06')['val']/1e6
            total=sum(x[metric] for x in final if x['year']==year)
            reconciliation.append(dict(year=year,metric=metric,quarter_sum=total,annual_reported=actual,difference=total-actual))
    write_csv(out/'final_quarterly_financials.csv',final)
    write_csv(out/'final_revenue_backtest.csv',predictions);write_csv(out/'final_profit_backtest.csv',profit_predictions)
    write_csv(out/'final_metrics.csv',scores);write_csv(out/'final_annual_bridge_backtest.csv',annual)
    write_csv(out/'final_forecast_2026.csv',forecasts);write_csv(out/'final_fcff_2026.csv',final_bridges)
    write_csv(out/'final_annual_reconciliation.csv',reconciliation)
    (out/'final_lineage.json').write_text(json.dumps(lineage,indent=2))
    summary=dict(revision='v2 exploratory',default_pipeline='original',candidate_status='Not promoted: quarterly gains do not carry consistently into annual FCFF or 2026 monitoring',selected_revenue_model=selected_r,selected_profit_model=selected_p,
        selection_uses='2019-2023 one-quarter validation MAE only; revised candidates introduced after prior evaluation was inspected',
        main_sample='2012Q1-2025Q4, 56 quarters',monitor='2026Q1-Q3, separately reported, 3 observations',asof='2026-02-06',
        scores=scores,annual_fcff_scores=annual_scores,forecast_2026=forecasts,final_fcff=final_bridges,
        reconciliation_issues=[x for x in reconciliation if x['difference']!=0],unit='USD million',
        plan_sha256=hashlib.sha256((ROOT/'release_plan.json').read_bytes()).hexdigest(),source_sha256=hashlib.sha256((ROOT/'data/raw/ti_companyfacts.json').read_bytes()).hexdigest(),
        environment=dict(python=platform.python_version(),numpy=np.__version__),
        scope='Simplified FCFF uses depreciation and core AR+inventory-AP only. Tax 25% is assumed. CAPEX ratios unchanged. No enterprise/share valuation here.')
    (out/'final_results.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    plt.rcParams.update({'font.family':'DejaVu Sans','figure.dpi':150,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for i,(target,stage) in enumerate([('revenue','evaluation'),('operating_profit','evaluation')]):
        rows=[x for x in scores if x['target']==target and x['stage']==stage]
        axes[i].bar([x['model'] for x in rows],[x['mae'] for x in rows],color='#176B87');axes[i].set(title=f'{target} | 2024-2025 MAE',ylabel='USD million');axes[i].tick_params(axis='x',rotation=20)
    fig.tight_layout();fig.savefig(out/'final_model_comparison.png');plt.close(fig)
    print(json.dumps(dict(selected=[selected_r,selected_p],scores=scores,annual_fcff_scores=annual_scores,final_fcff=final_bridges),indent=2))

if __name__=='__main__':main()
