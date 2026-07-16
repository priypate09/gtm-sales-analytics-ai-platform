from pathlib import Path
from agents.crm_sync_agent import run as run_crm_sync
from agents.market_intel_agent import run as run_market_intel
from agents.competitive_intel_agent import run as run_competitive_intel
from agents.sales_director_agent import run as run_sales_director

crm = run_crm_sync()
print(f"CRM: {crm['success']} — {crm['message']}")

market = run_market_intel(crm_data=crm.get('data') if crm.get('success') else None)
print(f"Market: {market['success']} — {market['message']}")

competitive = run_competitive_intel()
print(f"Competitive: {competitive['success']} — {competitive['message']}")

if crm['success'] and market['success'] and competitive['success']:
    sales = run_sales_director(crm_result=crm, market_result=market, competitive_result=competitive)
    print(f"Sales Director: {sales['success']}")
    print(sales['data'].get('narrative', '')[:600])
else:
    print('FAILED — check above')
