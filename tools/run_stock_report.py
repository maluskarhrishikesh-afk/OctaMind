import importlib
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` imports work when run as a script
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

stock_orchestrator = importlib.import_module('src.agent.ui.stock_agent.orchestrator')


if __name__ == '__main__':
    tool_map = getattr(stock_orchestrator, '_build_all_tools')()
    gen = tool_map.get('generate_full_report')
    if not gen:
        print(json.dumps({'status':'error','message':'generate_full_report tool not available'}))
    else:
        companies = sys.argv[1:] or ['Intellect Design Arena']
        results = [gen(company, output_path='') for company in companies]
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
