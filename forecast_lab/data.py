"""SEC companyfacts: period types, tags, filing dates and source lineage."""
import calendar
from datetime import date
import json
import math
from pathlib import Path

TAGS={
 'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet'],
 'operating_profit':['OperatingIncomeLoss'],
 'capex':['PaymentsToAcquirePropertyPlantAndEquipment'],
 'depreciation':['Depreciation'],
 'receivables':['AccountsReceivableNetCurrent'],
 'inventory':['InventoryNet'],
 'payables':['AccountsPayableCurrent'],
}
FLOWS=['revenue','operating_profit','capex','depreciation']
STOCKS=['receivables','inventory','payables']

def bounds(year,quarter):
    if type(quarter) is not int or quarter not in (1,2,3,4):raise ValueError('quarter must be integer 1..4')
    m=quarter*3
    return f'{year}-{m-2:02d}-01',f'{year}-{m:02d}-{calendar.monthrange(year,m)[1]}'

class Facts:
    def __init__(self,raw):
        self.raw=raw
        if raw['cik']!=97476:raise ValueError('Unexpected CIK')
        self.facts=raw['facts']['us-gaap']
    @classmethod
    def load(cls,path):return cls(json.loads(Path(path).read_text()))
    def candidates(self,metric,start,end,asof):
        found=[]
        for rank,tag in enumerate(TAGS[metric]):
            for fact in self.facts.get(tag,{}).get('units',{}).get('USD',[]):
                if fact['end']!=end or fact.get('start')!=start:continue
                if fact['filed']>asof or fact['form'] not in ['10-Q','10-K']:continue
                if not math.isfinite(fact['val']):raise ValueError('Nonfinite reported value')
                found.append(dict(fact,tag=tag,rank=rank))
        return found
    def fact(self,metric,start,end,asof):
        candidates=self.candidates(metric,start,end,asof)
        if not candidates:raise LookupError(f'{metric} {start} {end} unavailable at {asof}')
        first=min(x['filed'] for x in candidates)
        candidates=[x for x in candidates if x['filed']==first]
        if len({x['val'] for x in candidates})!=1:
            raise ValueError('Conflicting values or tags on first filing date; manual review required')
        rank=min(x['rank'] for x in candidates)
        candidates=[x for x in candidates if x['rank']==rank]
        if len({x['val'] for x in candidates})!=1:raise ValueError('Conflicting facts on same filing date')
        return sorted(candidates,key=lambda x:x['accn'])[-1]
    @staticmethod
    def lineage(fact,sign=1):
        accession=fact['accn']
        return dict(tag=fact['tag'],start=fact.get('start'),end=fact['end'],value_usd=fact['val'],
                    sign=sign,filed=fact['filed'],accession=accession,
                    filing_url=f'https://www.sec.gov/Archives/edgar/data/97476/{accession.replace("-", "")}/{accession}-index.htm')
    def quarter(self,metric,year,q,asof):
        start,end=bounds(year,q)
        try:
            direct=self.fact(metric,start,end,asof)
            return direct['val']/1e6,'reported_quarter',[self.lineage(direct)]
        except LookupError:pass
        current=self.fact(metric,f'{year}-01-01',end,asof)
        if q==1:return current['val']/1e6,'reported_quarter',[self.lineage(current)]
        previous=self.fact(metric,f'{year}-01-01',bounds(year,q-1)[1],asof)
        return (current['val']-previous['val'])/1e6,'ytd_difference',[self.lineage(current),self.lineage(previous,-1)]
    def first_release(self,year,q):
        start,end=bounds(year,q)
        # For Q4 the annual filing provides annual flows and the missing quarter.
        candidates=self.candidates('revenue',start,end,'9999-12-31')
        candidates+=self.candidates('revenue',f'{year}-01-01',end,'9999-12-31')
        if not candidates:raise LookupError('Missing release')
        return min(x['filed'] for x in candidates)
    def snapshot(self,asof,through_year,through_q=4,first_year=2012):
        rows=[];lineage=[]
        for y in range(first_year,through_year+1):
            for q in range(1,5):
                if y==through_year and q>through_q:break
                row=dict(period=f'{y}Q{q}',year=y,quarter=q,end=bounds(y,q)[1],asof=asof)
                for metric in FLOWS:
                    value,method,sources=self.quarter(metric,y,q,asof)
                    row[metric]=value
                    lineage.append(dict(period=row['period'],metric=metric,method=method,value_usd_million=value,sources=sources))
                for metric in STOCKS:
                    fact=self.fact(metric,None,row['end'],asof)
                    row[metric]=fact['val']/1e6
                    lineage.append(dict(period=row['period'],metric=metric,method='reported_balance',value_usd_million=row[metric],sources=[self.lineage(fact)]))
                if row['revenue']<=0:raise ValueError('Revenue must be positive')
                if row['capex']<0:raise ValueError('Negative capex: review sign convention')
                row['operating_margin']=row['operating_profit']/row['revenue']
                row['core_working_capital']=row['receivables']+row['inventory']-row['payables']
                rows.append(row)
        return rows,lineage
