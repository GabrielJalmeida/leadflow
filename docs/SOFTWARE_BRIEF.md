# LeadFlow — Software Interface Brief

## Product
LeadFlow is a local-first opportunity discovery and prospecting workspace. It discovers businesses, qualifies identity and website opportunity, prepares contact, and will evolve into a controlled CRM/follow-up system.

## Primary user
A freelancer, agency owner or sales operator who repeatedly researches and works business leads. Experience ranges from beginner to power user; repeated daily use is expected.

## Job to be done
When I need new commercial opportunities, I want LeadFlow to discover and qualify businesses, preserve evidence and context, and move the strongest leads toward contact and follow-up with minimum repetitive work.

## Primary domain objects
- research run
- lead / company
- identity evidence
- opportunity assessment
- contact route
- future: activity, lifecycle state, follow-up, deal

## Highest-frequency tasks
1. start a targeted research run;
2. compare qualified leads;
3. inspect one lead without losing the result list;
4. prepare/open the best contact channel;
5. later: update lifecycle and follow-up.

## Critical errors to prevent
- associating evidence with the wrong business;
- claiming a website is absent when it is merely unknown;
- treating opening a contact channel as confirmed contact;
- sending outreach automatically without approval;
- losing list/filter/selection context while inspecting records.

## Platform and input
Desktop-first web application on Windows initially, mouse + keyboard, adaptive window sizes. Local API and local-first core today; cloud/control-plane features later.

## Success metric for this slice
A user can go from a search definition to a qualified lead and an editable prepared contact without using the CLI or copying phone numbers manually.
