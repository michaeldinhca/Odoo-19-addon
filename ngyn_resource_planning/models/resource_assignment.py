# -*- coding: utf-8 -*-
from odoo import api, fields, models


class NgynTaskAssignment(models.Model):
    """One row per (task, employee): how many hours that person has been given
    on that task. The weekly breakdown of *when* those hours happen lives in
    ngyn.task.assignment.week, below.
    """
    _name = 'ngyn.task.assignment'
    _description = 'Resource Planning: Task Assignment'
    _rec_name = 'employee_id'

    task_id = fields.Many2one(
        'project.task', string='Task', required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        'project.project', related='task_id.project_id', store=True, index=True, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Team Member', required=True, ondelete='cascade', index=True)

    alloc_hours = fields.Float(
        string='Allocated Hours', default=0.0,
        help='Total hours given to this person on this task.')

    week_line_ids = fields.One2many(
        'ngyn.task.assignment.week', 'assignment_id', string='Weekly Hours')

    scheduled_hours = fields.Float(
        compute='_compute_scheduled_hours', store=True,
        help='Sum of hours this person has placed into specific weeks.')
    unscheduled_hours = fields.Float(
        compute='_compute_scheduled_hours', store=True,
        help='Allocated hours not yet placed into a specific week.')

    _task_employee_uniq = models.Constraint(
        'unique(task_id, employee_id)',
        'This person is already assigned to this task.',
    )

    @api.depends('alloc_hours', 'week_line_ids.hours')
    def _compute_scheduled_hours(self):
        for rec in self:
            scheduled = sum(rec.week_line_ids.mapped('hours'))
            rec.scheduled_hours = scheduled
            rec.unscheduled_hours = rec.alloc_hours - scheduled

    @api.model
    def _ensure_assignments(self, pairs):
        """pairs: iterable of (task_id, employee_id). Creates any missing rows
        for these pairs at alloc_hours=0 -- so anyone connected to a task via
        native Assignees or logged time shows up in Resource Planning even
        before they're given hours there. Called from project.task (Assignees
        changing) and account.analytic.line (a timesheet logged), plus once as
        a backfill on install/upgrade -- see __init__.py.
        """
        pairs = {(t, e) for t, e in pairs if t and e}
        if not pairs:
            return
        # sudo: this runs from project.task/account.analytic.line writes made by
        # whoever touched the task/timesheet, not necessarily someone with
        # Resource Planning access themselves -- the sync must not depend on the
        # acting user's own group membership.
        self = self.sudo()
        existing = {
            (a.task_id.id, a.employee_id.id)
            for a in self.search([('task_id', 'in', list({t for t, _e in pairs}))])
        }
        to_create = [
            {'task_id': t, 'employee_id': e, 'alloc_hours': 0}
            for t, e in pairs if (t, e) not in existing
        ]
        if to_create:
            self.create(to_create)


class NgynTaskAssignmentWeek(models.Model):
    """A single (assignment, week) cell — the hour value the Resource Planning
    grid shows and edits. week_start_date is always a Monday.
    """
    _name = 'ngyn.task.assignment.week'
    _description = 'Resource Planning: Weekly Hours'
    _order = 'week_start_date'

    assignment_id = fields.Many2one(
        'ngyn.task.assignment', string='Assignment', required=True,
        ondelete='cascade', index=True)
    week_start_date = fields.Date(string='Week Of (Monday)', required=True, index=True)
    hours = fields.Float(string='Hours', default=0.0)

    _assignment_week_uniq = models.Constraint(
        'unique(assignment_id, week_start_date)',
        'There is already an hour entry for this person on this task for that week.',
    )
