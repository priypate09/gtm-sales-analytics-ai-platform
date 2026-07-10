from agents.crm_sync_agent import run as crm_run
from agents.market_intel_agent import run as intel_run

crm = crm_run()
result = intel_run(crm_data=crm["data"])
for seg, data in result["data"]["segments"].items():
    internal = data.get("internal_yoy_growth_pct", "n/a")
    benchmark = data["benchmark_growth_pct"]
    gap = data.get("gap_pp", "n/a")
    flagged = data.get("flagged", "n/a")
    print(f"{seg}: internal={internal} benchmark={benchmark} gap={gap} flagged={flagged}")
