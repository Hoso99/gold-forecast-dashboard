"""Static parity audit for the first isolated historical V9.5 technical-entry replay.
This checks implementation differences without running or modifying production.
"""
import ast
import json
from pathlib import Path

replay=Path('research/historical/v95_entry_replay.py').read_text()
root=Path('/home/ubuntu/v95-research/research/active_position_monitor')
paper=(root/'v95_paper_monitor.py').read_text()
checks={
 'paper_evaluates_each_new_m1': 'if state.get("last_bar")==last:' in paper,
 'replay_entry_m15_only': 'if 15 in completed and not active and not pending' in replay,
 'paper_has_indicator_based_early_exit': 'EXIT_SELL_NOW' in paper,
 'replay_has_only_sl_tp_timeout': "outcome='TIMEOUT'" in replay and "outcome='SL'" in replay and "outcome='TP'" in replay,
 'paper_has_daily_loss_lock': 'DAILY_PAPER_LOCK' in paper,
 'replay_omits_daily_loss_lock': "'paper_risk_daily_lock':'NOT_TESTED'" in replay,
 'paper_has_news_gate': 'NEWS_BLOCKED' in paper,
 'replay_omits_news_gate': "'news_gate':'NOT_TESTED" in replay,
 'paper_uses_signal_close_for_paper_entry': '"entry":price' in paper,
 'replay_uses_next_m1_open': "'entry':o" in replay,
 'paper_has_protective_gap_probe': 'check_protective_levels' in paper,
 'replay_censors_on_gaps': "CENSORED_GAP" in replay,
}
for file in [root/'v95_paper_monitor.py',Path('research/historical/v95_entry_replay.py')]:
 ast.parse(file.read_text())
report={'audit':'V9.5 original vs technical-entry baseline',
         'checks':checks,
         'baseline_valid_for_live_parity':False,
         'holdout_note':'2026 already examined in baseline; not pristine for any decisions informed by those results',
         'next_step':'Create independent minute-by-minute parity replay, then add historical news and paper risk/exit semantics'}
Path('v95-parity-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not all(checks.values()): raise SystemExit('AUDIT INCOMPLETE')
