"""Simplified FCFF input bridge, USD million."""
import numpy as np

def bridge(revenue,profit,prior,tax_rate=.25):
    if not np.isfinite([revenue,profit,tax_rate]).all() or revenue<=0 or not 0<=tax_rate<=1:
        raise ValueError("Invalid bridge revenue, profit or tax rate")
    if len(prior)!=4:raise ValueError("Exactly four prior quarters required")
    for row in prior:
        if not np.isfinite([row[k] for k in ["revenue","capex","depreciation","core_working_capital"]]).all():raise ValueError("Nonfinite bridge inputs")
        if row["revenue"]<=0 or row["capex"]<0 or row["depreciation"]<0:raise ValueError("Invalid historical flow sign")
    annual_revenue=sum(x['revenue'] for x in prior)
    capex_ratio=sum(x['capex'] for x in prior)/annual_revenue
    depreciation_ratio=sum(x['depreciation'] for x in prior)/annual_revenue
    core_wc=prior[-1]['core_working_capital'];wc_ratio=core_wc/annual_revenue
    projected_wc=revenue*wc_ratio;change_wc=projected_wc-core_wc
    capex=revenue*capex_ratio;depreciation=revenue*depreciation_ratio
    nopat=profit*(1-tax_rate)
    return dict(revenue=revenue,operating_profit=profit,assumed_tax_rate=tax_rate,nopat=nopat,
                depreciation=depreciation,capex=capex,core_wc_begin=core_wc,core_wc_end=projected_wc,
                change_core_wc=change_wc,simplified_fcff=nopat+depreciation-capex-change_wc,
                capex_ratio=capex_ratio,depreciation_ratio=depreciation_ratio,core_wc_ratio=wc_ratio)

