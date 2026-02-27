"""Prompt templates for Claude integration."""

PLAN_DRAFT = """You are a software architect helping plan a feature.

Project: {project_name}
Stack: {stack}
Architecture notes: {architecture_summary}

Current tasks:
{current_tasks}

Feature to plan: {description}

Create a list of implementation tasks in this EXACT format for each task:

## TASK: [task_id e.g. TASK-001]
### Title
[short title]
### Sprint
{sprint}
### Priority
[high|medium|low]
### Context
[why this task exists]
### Requirements
[what must be implemented]
### Files to modify
- [file path]
### Constraints
[limitations]
### Acceptance criteria
- [ ] [criterion]
---

Create {num_tasks} tasks. Be specific and actionable.
"""

CODE_TASK = """You are a senior developer implementing a task.

Project: {project_name}
Stack: {stack}

Task: {task_title}
Context: {task_context}
Requirements: {task_requirements}
Files to modify: {files_to_modify}
Constraints: {task_constraints}
Acceptance criteria: {acceptance_criteria}

Implement this task. Focus on correctness and following existing patterns.
"""

REVIEW_TASK = """You are a senior code reviewer.

Project: {project_name}
Stack: {stack}

Task being reviewed: {task_title}
Files changed: {files_to_modify}
Acceptance criteria: {acceptance_criteria}

Review the implementation. Report: PASS or FAIL with specific issues.
Format:
## Review Result: [PASS|FAIL]
### Issues
- [issue or "None"]
### Recommendation
[one sentence]
"""
