# LeadFlow Frontend v0 — State Matrix

| Area | State | UI response | Recovery |
|---|---|---|---|
| Local API | offline | persistent empty/error state with command to start API | retry health check |
| Search | idle | search form + prior/empty workspace | start run |
| Search | queued/running | persistent run banner; cancel remains available | cancel or wait |
| Search | cancelling | banner explains safe cancellation | wait for terminal state |
| Search | failed | persistent message bar with backend-safe error | edit request and rerun |
| Search | partial budget | results remain visible; status explicitly says partial | change budget/request and rerun |
| Results | zero | specific no-eligible-leads state | adjust filters/pool |
| Results | populated | sortable dense grid | select lead |
| Lead | selected | contextual inspector without losing list context | close inspector / select another |
| Contact | preparing | button enters disabled/loading state | retry if API fails |
| Contact | ready | editable message + explicit channel action | edit/copy/open channel |
