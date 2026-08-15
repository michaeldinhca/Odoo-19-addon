# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import AccessError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    x_ngyn_locked = fields.Boolean(
        string='Resource Plan Locked',
        default=False,
        help='When set, weekly hours on this project\'s tasks cannot be changed in '
             'Resource Planning by anyone except this project\'s own Project Manager.',
    )

    def write(self, vals):
        # Guard the field itself, not just action_ngyn_toggle_lock below -- anyone with
        # ordinary project.project write access (any Project Manager, not just this
        # project's own) could otherwise flip the lock directly and bypass that method's
        # check entirely. ngyn_lock_authorized is set only by action_ngyn_toggle_lock,
        # after it has already confirmed the acting user against project.user_id itself.
        if 'x_ngyn_locked' in vals and not self.env.context.get('ngyn_lock_authorized'):
            for project in self:
                if vals['x_ngyn_locked'] != project.x_ngyn_locked and self.env.user != project.user_id:
                    raise AccessError(_(
                        "Only this project's Project Manager (%s) can lock or unlock its "
                        "resource plan.",
                        project.user_id.name or _("nobody assigned yet"),
                    ))
        return super().write(vals)

    def action_ngyn_toggle_lock(self):
        for project in self:
            if self.env.user != project.user_id:
                raise AccessError(_(
                    "Only this project's Project Manager (%s) can lock or unlock its "
                    "resource plan.",
                    project.user_id.name or _("nobody assigned yet"),
                ))
            new_state = not project.x_ngyn_locked
            # sudo, deliberately: project.group_project_user (what a project's own manager
            # normally has) only carries read access to project.project itself in stock
            # Odoo -- actually writing any field on a project needs Project/Administrator.
            # The identity check just above is the real authorization; this sudo only
            # covers the mechanical write once that's already confirmed, scoped narrowly
            # via ngyn_lock_authorized so it can't be reused to bypass the check elsewhere.
            project.sudo().with_context(ngyn_lock_authorized=True).write({'x_ngyn_locked': new_state})
            project.message_post(body=_(
                "Resource plan %(state)s by %(user)s.",
                state=_("locked") if new_state else _("unlocked"),
                user=self.env.user.name,
            ))

    def _ngyn_check_plan_unlocked(self):
        """Raise if any project in self has its resource plan locked. Called from
        ngyn.task.assignment / ngyn.task.assignment.week before an hours-changing
        write, not from the passive membership sync in _ensure_assignments (which
        runs with ngyn_skip_lock_check) -- locking the plan blocks planning edits,
        not everyday task/timesheet activity elsewhere in Odoo.
        """
        locked = self.filtered('x_ngyn_locked')
        if locked:
            raise AccessError(_(
                "The resource plan for %s is locked. Ask the project's Project "
                "Manager (%s) to unlock it before making changes.",
                ', '.join(locked.mapped('name')),
                ', '.join(locked.mapped('user_id.name')) or _("nobody assigned"),
            ))
