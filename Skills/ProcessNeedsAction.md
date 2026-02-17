# Agent Skill: ProcessNeedsAction

## Purpose
This skill processes all files in the /Needs_Action folder, creates a plan in /Plans/, updates the Dashboard, and moves completed files to /Done.

## Instructions
1. Read all files in the /Needs_Action folder
2. Analyze each file to determine its content and required actions
3. Create a Plan.md in the /Plans/ folder with checkboxes for each required action
4. Update the Dashboard.md with current status information
5. Move completed files to the /Done folder
6. Continue working until all pending tasks are addressed (Ralph Wiggum persistence)

## Detailed Steps
- Scan /Needs_Action folder for .md files
- For each file, extract action items and requirements
- Create a comprehensive plan with checkboxes in /Plans/Plan.md
- Update Dashboard.md counters and status fields
- After completing actions, move processed files to /Done folder
- Log completion status and timestamps

## Examples
Input: New file appears in /Needs_Action titled "Invoice_Request.md"
Process: Extract payment details, create plan with payment steps, update dashboard
Output: Plan.md with payment checklist, updated dashboard, moved to /Done when paid

## Prompts
When encountering a file in /Needs_Action, ask:
- What specific actions are required?
- Are there any deadlines or priorities?
- What resources are needed to complete the task?
- How should success be measured?

## Persistence Rule
Keep working on tasks until they are fully completed. If blocked, document the issue and try alternative approaches rather than giving up.