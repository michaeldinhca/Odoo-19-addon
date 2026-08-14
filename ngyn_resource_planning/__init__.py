from . import models


def _backfill_ngyn_assignments(env):
    """One-time sweep on install/upgrade: give a real ngyn.task.assignment
    row (at 0h) to every existing task-assignee and every employee who's
    already logged time against a task, for tasks that predate this sync
    logic. Going forward, project_task.py / account_analytic_line.py keep
    this current on every create/write instead.
    """
    tasks = env['project.task'].search([('user_ids', '!=', False)])
    pairs = [
        (task.id, user.employee_id.id)
        for task in tasks for user in task.user_ids if user.employee_id
    ]
    lines = env['account.analytic.line'].search([
        ('task_id', '!=', False), ('employee_id', '!=', False),
    ])
    pairs += [(line.task_id.id, line.employee_id.id) for line in lines]
    env['ngyn.task.assignment']._ensure_assignments(pairs)
