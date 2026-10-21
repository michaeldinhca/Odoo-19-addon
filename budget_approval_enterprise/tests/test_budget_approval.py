from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'budget_approval_enterprise')
class TestBudgetApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': "Budget Co B"})
        both = (cls.company | cls.company_b).ids
        cls.accountant = cls._user('bae_accountant', cls.company, both)
        cls.fin_mgr = cls._user('bae_fin_mgr', cls.company)
        cls.fin_mgr2 = cls._user('bae_fin_mgr2', cls.company)
        cls.cfo = cls._user('bae_cfo', cls.company)
        cls.user_b = cls._user('bae_user_b', cls.company_b)

        Job = cls.env['hr.job']
        cls.job_fin = Job.create({'name': "Finance Manager", 'company_id': cls.company.id})
        cls.job_cfo = Job.create({'name': "CFO", 'company_id': cls.company.id})
        cls.job_ctrl = Job.create({'name': "Controller", 'company_id': cls.company.id})
        cls.job_b = Job.create({'name': "Finance Manager", 'company_id': cls.company_b.id})
        cls._give_job(cls.fin_mgr, cls.job_fin, cls.company)
        cls._give_job(cls.fin_mgr2, cls.job_fin, cls.company)
        cls._give_job(cls.cfo, cls.job_cfo, cls.company)
        cls._give_job(cls.user_b, cls.job_b, cls.company_b)
        # a position with three holders, used by the "all" / "at least N" tests
        cls.job_rev = Job.create({'name': "Reviewer", 'company_id': cls.company.id})
        cls.rev1, cls.rev2, cls.rev3 = (cls._user('bae_rev%s' % i, cls.company) for i in (1, 2, 3))
        for user in (cls.rev1, cls.rev2, cls.rev3):
            cls._give_job(user, cls.job_rev, cls.company)

        cls.analytic_plan = cls.env['account.analytic.plan'].create({'name': "BAE Plan"})
        cls.analytic = cls.env['account.analytic.account'].create({
            'name': "BAE Account", 'plan_id': cls.analytic_plan.id, 'company_id': False})
        cls.rule = cls._make_rule(cls.company, [cls.job_fin, cls.job_cfo], min_amount=1000)

    @classmethod
    def _user(cls, login, company, company_ids=None):
        return mail_new_test_user(
            cls.env, login=login, groups='account.group_account_user',
            company_ids=[(6, 0, company_ids or company.ids)], company_id=company.id)

    @classmethod
    def _give_job(cls, user, job, company):
        employee = cls.env['hr.employee'].search(
            [('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1)
        if not employee:
            employee = cls.env['hr.employee'].create({
                'name': user.name, 'user_id': user.id, 'company_id': company.id})
        employee.job_id = job
        return employee

    @classmethod
    def _make_rule(cls, company, jobs_per_step, min_amount=0.0, **vals):
        """jobs_per_step: a list of hr.job recordsets (or single jobs), one per step."""
        return cls.env['budget.approval.rule'].create({
            'name': "Rule %s" % company.name,
            'company_id': company.id,
            'min_amount': min_amount,
            'step_ids': [(0, 0, {'sequence': 10 * i, 'job_ids': [(6, 0, jobs.ids)]})
                         for i, jobs in enumerate(jobs_per_step, start=1)],
            **vals,
        })

    def _budget(self, amount=5000.0, company=None, **vals):
        company = company or self.company
        return self.env['budget.analytic'].with_company(company).create({
            'name': "Budget %s" % amount,
            'company_id': company.id,
            'budget_type': 'expense',
            'date_from': '2029-01-01',
            'date_to': '2029-12-31',
            'budget_line_ids': [(0, 0, {'account_id': self.analytic.id, 'budget_amount': amount})],
            **vals,
        })

    def _request(self, budget, user=None):
        budget.with_user(user or self.accountant).action_request_approval()

    def _decide(self, budget, user, approve=True, note=None):
        budget.with_user(user).approval_id.action_decide(approve, note)

    def _full_approval(self, budget):
        self._request(budget)
        self._decide(budget, self.fin_mgr)
        self._decide(budget, self.cfo)

    # ------------------------------------------------------------------
    def test_rule_threshold_and_type(self):
        self.assertTrue(self._budget(5000).approval_required)
        self.assertFalse(self._budget(500).approval_required)
        self.rule.budget_type = 'revenue'
        self.assertFalse(self._budget(5000).approval_required)

    def test_first_rule_by_sequence_wins(self):
        high = self._make_rule(self.company, [self.job_cfo], min_amount=1000, sequence=1)
        budget = self._budget(5000)
        self.assertEqual(self.env['budget.approval.rule']._get_matching_rule(budget), high)

    def test_open_blocked_until_approved(self):
        budget = self._budget(5000)
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})
        self._request(budget)
        self.assertEqual(budget.approval_state, 'to_approve')
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})
        self._decide(budget, self.fin_mgr)
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})
        self._decide(budget, self.cfo)
        self.assertEqual(budget.approval_state, 'approved')
        budget.write({'state': 'confirmed'})
        self.assertEqual(budget.state, 'confirmed')

    def test_small_budget_opens_without_approval(self):
        budget = self._budget(500)
        with self.assertRaises(UserError):
            budget.action_request_approval()
        budget.write({'state': 'confirmed'})
        self.assertEqual(budget.state, 'confirmed')

    # ------------------------------------------------------------------ job positions
    def test_any_holder_of_the_position_can_approve(self):
        budget = self._budget(5000)
        self._request(budget)
        step = budget.approval_id.step_ids.sorted('sequence')[0]
        self.assertEqual(step.approver_ids, self.fin_mgr | self.fin_mgr2)
        # the second holder decides, not the first
        self._decide(budget, self.fin_mgr2)
        self.assertEqual(step.decided_by, self.fin_mgr2)
        self.assertEqual(step.state, 'approved')

    def test_can_approve_column_lists_holders_for_every_step(self):
        budget = self._budget(5000)
        self._request(budget)
        steps = budget.approval_id.step_ids.sorted('sequence')
        # waiting step already shows who will be able to approve it, from the job position
        self.assertEqual(steps[0].eligible_approver_ids, self.fin_mgr | self.fin_mgr2)
        self.assertEqual(steps[1].state, 'waiting')
        self.assertEqual(steps[1].eligible_approver_ids, self.cfo)
        # a later holder of the waiting step's position shows up, but not the requester
        self._give_job(self.accountant, self.job_cfo, self.company)
        steps.invalidate_recordset()
        self.assertEqual(steps[1].eligible_approver_ids, self.cfo)
        # once active the list is the snapshot
        self._decide(budget, self.fin_mgr)
        self.assertEqual(steps[1].eligible_approver_ids, steps[1].approver_ids)

    def test_several_positions_on_one_step(self):
        rule = self._make_rule(self.company, [self.job_fin | self.job_cfo], min_amount=100000, sequence=1)
        budget = self._budget(200000)
        self.assertEqual(self.env['budget.approval.rule']._get_matching_rule(budget), rule)
        self._request(budget)
        step = budget.approval_id.step_ids
        self.assertEqual(step.approver_ids, self.fin_mgr | self.fin_mgr2 | self.cfo)
        self._decide(budget, self.cfo)
        self.assertEqual(budget.approval_state, 'approved')

    def test_activity_per_holder_cleared_when_one_decides(self):
        budget = self._budget(5000)
        self._request(budget)
        step = budget.approval_id.step_ids.sorted('sequence')[0]
        self.assertEqual(step.activity_ids.user_id, self.fin_mgr | self.fin_mgr2)
        activities = step.activity_ids
        self._decide(budget, self.fin_mgr)
        self.assertFalse(activities.exists())
        self.assertEqual(budget.approval_id.step_ids.sorted('sequence')[1].activity_ids.user_id, self.cfo)

    def test_non_holder_cannot_decide(self):
        budget = self._budget(5000)
        self._request(budget)
        # CFO belongs to step 2, the accountant holds no position, admin is not a holder
        for user in (self.cfo, self.accountant, self.env.ref('base.user_admin')):
            with self.assertRaises(UserError):
                budget.approval_id.with_user(user).action_decide(True)
        self.assertTrue(budget.with_user(self.fin_mgr).can_decide_approval)
        self.assertTrue(budget.with_user(self.fin_mgr2).can_decide_approval)
        self.assertFalse(budget.with_user(self.cfo).can_decide_approval)

    def test_requester_holding_the_position_cannot_approve(self):
        budget = self._budget(5000)
        self._request(budget, user=self.fin_mgr)
        step = budget.approval_id.step_ids.sorted('sequence')[0]
        self.assertEqual(step.approver_ids, self.fin_mgr2)
        with self.assertRaises(UserError):
            budget.approval_id.with_user(self.fin_mgr).action_decide(True)

    def test_request_refused_when_nobody_else_holds_the_position(self):
        self._make_rule(self.company, [self.job_cfo], min_amount=100000, sequence=1)
        budget = self._budget(200000)
        with self.assertRaises(UserError):
            self._request(budget, user=self.cfo)
        self.assertFalse(budget.approval_ids)

    def test_request_refused_when_position_has_no_holder(self):
        self._make_rule(self.company, [self.job_ctrl], min_amount=100000, sequence=1)
        budget = self._budget(200000)
        with self.assertRaises(UserError):
            self._request(budget)

    def test_holders_of_another_company_do_not_count(self):
        # a Finance Manager of company B must not be an approver for company A
        self._give_job(self.user_b, self.job_fin, self.company_b)
        budget = self._budget(5000)
        self._request(budget)
        step = budget.approval_id.step_ids.sorted('sequence')[0]
        self.assertNotIn(self.user_b, step.approver_ids)

    def test_position_snapshot_survives_rule_edit(self):
        budget = self._budget(5000)
        self._request(budget)
        self.rule.step_ids.unlink()
        steps = budget.approval_id.step_ids.sorted('sequence')
        self.assertEqual(steps.job_ids, self.job_fin | self.job_cfo)
        self._decide(budget, self.fin_mgr)
        self._decide(budget, self.cfo)
        self.assertEqual(budget.approval_state, 'approved')

    def test_step_requires_a_position(self):
        with self.assertRaises(ValidationError):
            self.env['budget.approval.rule.step'].create({'rule_id': self.rule.id})

    def test_position_of_another_company_refused_on_rule(self):
        with self.assertRaises(ValidationError):
            self._make_rule(self.company, [self.job_b])

    # ------------------------------------------------------------------ flow
    def test_steps_are_sequential(self):
        budget = self._budget(5000)
        self._request(budget)
        steps = budget.approval_id.step_ids.sorted('sequence')
        self.assertEqual(steps.mapped('state'), ['pending', 'waiting'])
        self.assertFalse(steps[1].activity_ids)
        self._decide(budget, self.fin_mgr)
        self.assertEqual(steps.mapped('state'), ['approved', 'pending'])

    def test_reject_returns_to_requester_and_can_resubmit(self):
        budget = self._budget(5000)
        self._request(budget)
        self._decide(budget, self.fin_mgr, approve=False, note="Too high")
        self.assertEqual(budget.approval_state, 'rejected')
        self.assertFalse(budget.approval_id.step_ids.activity_ids)
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})
        self._request(budget)
        self.assertEqual(budget.approval_state, 'to_approve')
        self.assertEqual(len(budget.approval_ids), 2)

    def test_reject_wizard_requires_reason(self):
        budget = self._budget(5000)
        self._request(budget)
        wizard = self.env['budget.approval.decision.wizard'].with_user(self.fin_mgr).create({
            'budget_ids': [(6, 0, budget.ids)], 'decision': 'reject'})
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.note = "No funds"
        wizard.action_confirm()
        self.assertEqual(budget.approval_state, 'rejected')

    # ------------------------------------------------------------------ automations must keep working
    def test_zero_amount_line_can_be_added_while_pending(self):
        """Sky style automation: a PO line adds a zero-amount budget line to the project budget."""
        budget = self._budget(5000)
        self._request(budget)
        line = self.env['budget.line'].sudo().create({
            'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 0.0})
        self.assertTrue(line.exists())
        self.assertEqual(budget.approval_state, 'to_approve')

    def test_zero_amount_line_does_not_void_an_approval(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        self.env['budget.line'].sudo().create({
            'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 0.0})
        self.assertEqual(budget.approval_state, 'approved')
        budget.write({'state': 'confirmed'})
        self.assertEqual(budget.state, 'confirmed')

    def test_expense_line_can_be_added_but_not_funded_while_approved_or_pending(self):
        """A new line (spend on something not budgeted) is fine, assigning it a budget is not."""
        for approved in (False, True):
            budget = self._budget(5000)
            self._request(budget)
            if approved:
                self._decide(budget, self.fin_mgr)
                self._decide(budget, self.cfo)
            line = self.env['budget.line'].sudo().create({
                'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 0.0})
            with self.assertRaises(UserError):
                line.write({'budget_amount': 250.0})

    def test_zero_amount_line_can_be_added_through_the_budget_while_pending(self):
        budget = self._budget(5000)
        self._request(budget)
        budget.sudo().write({'budget_line_ids': [(0, 0, {'account_id': self.analytic.id, 'budget_amount': 0.0})]})
        self.assertEqual(len(budget.budget_line_ids), 2)

    def test_rewriting_the_same_amount_is_not_a_change(self):
        budget = self._budget(5000)
        self._request(budget)
        budget.budget_line_ids.write({'budget_amount': 5000.0, 'sequence': 7})
        self.assertEqual(budget.approval_state, 'to_approve')

    def test_zero_amount_line_can_be_removed_while_pending(self):
        budget = self._budget(5000)
        zero = self.env['budget.line'].sudo().create({
            'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 0.0})
        self._request(budget)
        zero.unlink()
        self.assertFalse(zero.exists())

    def test_amount_change_still_blocked_through_the_budget_commands(self):
        budget = self._budget(5000)
        self._request(budget)
        line = budget.budget_line_ids
        with self.assertRaises(UserError):
            budget.write({'budget_line_ids': [(1, line.id, {'budget_amount': 9999.0})]})

    # ------------------------------------------------------------------ approvals needed per step
    def _multi_rule(self, mode, count=2):
        """Rule above 100k: step 1 = the three Reviewers with the given mode, step 2 = CFO."""
        return self.env['budget.approval.rule'].create({
            'name': "Multi %s" % mode, 'company_id': self.company.id, 'sequence': 1, 'min_amount': 100000,
            'step_ids': [
                (0, 0, {'sequence': 10, 'name': "Review", 'job_ids': [(6, 0, self.job_rev.ids)],
                        'approval_mode': mode, 'required_count': count}),
                (0, 0, {'sequence': 20, 'name': "Final", 'job_ids': [(6, 0, self.job_cfo.ids)]}),
            ]})

    def _review_step(self, budget):
        return budget.approval_id.step_ids.sorted('sequence')[0]

    def test_mode_any_one_approval_completes_the_step(self):
        self._multi_rule('any')
        budget = self._budget(200000)
        self._request(budget)
        step = self._review_step(budget)
        self.assertEqual(step.required_approvals, 1)
        self._decide(budget, self.rev2)
        self.assertEqual(step.state, 'approved')
        self.assertFalse(step.activity_ids)

    def test_mode_all_needs_every_holder(self):
        self._multi_rule('all')
        budget = self._budget(200000)
        self._request(budget)
        step = self._review_step(budget)
        self.assertEqual(step.required_approvals, 3)
        self._decide(budget, self.rev1)
        self.assertEqual(step.state, 'pending')
        self.assertEqual(step.approved_by_ids, self.rev1)
        # only the first reviewer's To-Do is gone, the other two stay
        self.assertEqual(step.activity_ids.user_id, self.rev2 | self.rev3)
        self.assertEqual(budget.pending_approver_ids, self.rev2 | self.rev3)
        self.assertFalse(budget.with_user(self.rev1).can_decide_approval)
        self.assertTrue(budget.with_user(self.rev2).can_decide_approval)
        self._decide(budget, self.rev2)
        self.assertEqual(step.state, 'pending')
        self._decide(budget, self.rev3)
        self.assertEqual(step.state, 'approved')
        self.assertEqual(budget.approval_id.step_ids.sorted('sequence')[1].state, 'pending')

    def test_mode_count_two_of_three(self):
        self._multi_rule('count', 2)
        budget = self._budget(200000)
        self._request(budget)
        step = self._review_step(budget)
        self.assertEqual(step.required_approvals, 2)
        self._decide(budget, self.rev3)
        self.assertEqual(step.state, 'pending')
        self._decide(budget, self.rev1)
        self.assertEqual(step.state, 'approved')
        self.assertEqual(step.approved_by_ids, self.rev3 | self.rev1)
        # the third reviewer's To-Do is cleaned up and they can no longer act on the step
        self.assertFalse(step.activity_ids)
        with self.assertRaises(UserError):
            budget.approval_id.with_user(self.rev2).action_decide(True)

    def test_same_person_cannot_approve_twice(self):
        self._multi_rule('all')
        budget = self._budget(200000)
        self._request(budget)
        self._decide(budget, self.rev1)
        with self.assertRaises(UserError):
            self._decide(budget, self.rev1)
        self.assertEqual(len(self._review_step(budget).approved_by_ids), 1)

    def test_one_rejection_rejects_the_step_in_any_mode(self):
        self._multi_rule('all')
        budget = self._budget(200000)
        self._request(budget)
        self._decide(budget, self.rev1)
        self._decide(budget, self.rev2, approve=False, note="No")
        self.assertEqual(budget.approval_state, 'rejected')
        self.assertEqual(self._review_step(budget).state, 'rejected')
        self.assertFalse(budget.approval_id.step_ids.activity_ids)

    def test_request_refused_when_fewer_holders_than_required(self):
        self._multi_rule('count', 4)
        budget = self._budget(200000)
        with self.assertRaises(UserError):
            self._request(budget)

    def test_count_below_one_refused(self):
        with self.assertRaises(ValidationError):
            self._multi_rule('count', 0)

    def test_needs_label(self):
        self._multi_rule('count', 2)
        budget = self._budget(200000)
        self._request(budget)
        steps = budget.approval_id.step_ids.sorted('sequence')
        self.assertEqual(steps[0].needs_label, "2 of 3")
        self.assertEqual(steps[1].needs_label, "Any 1 of 1")
        self._decide(budget, self.rev1)
        self.assertEqual(steps[0].needs_label, "2 of 3 (1 approved)")

    def test_mass_approve_skips_a_budget_the_user_already_approved(self):
        self._multi_rule('all')
        done = self._budget(200000)
        self._request(done)
        self._decide(done, self.rev1)
        fresh = self._budget(300000)
        self._request(fresh)
        self._wizard(done | fresh, self.rev1).action_confirm()
        self.assertEqual(self._review_step(done).approved_by_ids, self.rev1)  # untouched, not doubled
        self.assertEqual(self._review_step(fresh).approved_by_ids, self.rev1)

    def test_activity_done_by_an_approver_opens_the_dialog_and_approves_only_for_them(self):
        self._multi_rule('all')
        budget = self._budget(200000)
        self._request(budget)
        activity = self._my_activity(budget, self.rev2)
        action = activity.with_user(self.rev2).action_done()
        self.assertEqual(action['res_model'], 'budget.approval.decision.wizard')
        self._wizard(budget, self.rev2).action_confirm()
        self.assertEqual(self._review_step(budget).approved_by_ids, self.rev2)
        self.assertFalse(activity.exists())
        self.assertEqual(self._review_step(budget).activity_ids.user_id, self.rev1 | self.rev3)

    # ------------------------------------------------------------------ activity tied to the approval
    def _my_activity(self, budget, user):
        return budget.approval_id.step_ids.activity_ids.filtered(lambda a: a.user_id == user)

    def test_mark_done_opens_decision_dialog_and_leaves_approval_pending(self):
        budget = self._budget(5000)
        self._request(budget)
        activity = self._my_activity(budget, self.fin_mgr)
        action = activity.with_user(self.fin_mgr).action_done()
        self.assertEqual(action['res_model'], 'budget.approval.decision.wizard')
        self.assertEqual(action['context']['default_budget_ids'], budget.ids)
        # nothing happened yet: activity still there, step still pending
        self.assertTrue(activity.exists() and activity.active)
        self.assertEqual(budget.approval_id.step_ids.sorted('sequence')[0].state, 'pending')

    def test_deciding_in_the_dialog_started_from_the_activity_completes_the_step(self):
        budget = self._budget(5000)
        self._request(budget)
        activity = self._my_activity(budget, self.fin_mgr)
        action = activity.with_user(self.fin_mgr).action_done()
        wizard = self.env['budget.approval.decision.wizard'].with_user(self.fin_mgr).with_context(
            **{k: v for k, v in action['context'].items() if k.startswith('default_')}).create({})
        self.assertEqual(wizard.decision, 'approve')
        wizard.action_confirm()
        self.assertEqual(budget.approval_id.step_ids.sorted('sequence')[0].state, 'approved')
        self.assertFalse(activity.exists())

    def test_inline_feedback_done_is_blocked(self):
        budget = self._budget(5000)
        self._request(budget)
        activity = self._my_activity(budget, self.fin_mgr)
        with self.assertRaises(UserError):
            activity.with_user(self.fin_mgr).action_feedback(feedback="done")
        self.assertEqual(budget.approval_id.step_ids.sorted('sequence')[0].state, 'pending')

    def test_approval_activity_cannot_be_deleted_directly(self):
        budget = self._budget(5000)
        self._request(budget)
        with self.assertRaises(UserError):
            self._my_activity(budget, self.fin_mgr).with_user(self.fin_mgr).unlink()

    def test_unrelated_activity_still_completes_normally(self):
        budget = self._budget(5000)
        todo = budget.activity_schedule('mail.mail_activity_data_todo', user_id=self.fin_mgr.id, summary="Other")
        todo.with_user(self.fin_mgr).action_feedback(feedback="ok")
        self.assertFalse(todo.exists() and todo.active)

    def test_deleting_a_budget_with_pending_approval_works(self):
        budget = self._budget(5000)
        self._request(budget)
        activities = budget.approval_id.step_ids.activity_ids
        self.assertTrue(activities)
        budget.unlink()
        self.assertFalse(activities.exists())

    # ------------------------------------------------------------------ mass approval, filters
    def _wizard(self, budgets, user, decision='approve', note=None):
        return self.env['budget.approval.decision.wizard'].with_user(user).create({
            'budget_ids': [(6, 0, budgets.ids)], 'decision': decision, 'note': note})

    def test_mass_approve_many_budgets_in_one_go(self):
        budgets = self._budget(5000) | self._budget(7000) | self._budget(9000)
        for budget in budgets:
            self._request(budget)
        self._wizard(budgets, self.fin_mgr).action_confirm()
        # step 1 done on all three, each now waits for the CFO
        for budget in budgets:
            self.assertEqual(budget.approval_id.step_ids.sorted('sequence').mapped('state'),
                             ['approved', 'pending'])
        self._wizard(budgets, self.cfo).action_confirm()
        self.assertEqual(budgets.mapped('approval_state'), ['approved'] * 3)

    def test_mass_approve_skips_budgets_not_waiting_for_the_user(self):
        waiting_fin = self._budget(5000)
        self._request(waiting_fin)
        waiting_cfo = self._budget(6000)
        self._full_approval_to_step2(waiting_cfo)
        self._wizard(waiting_fin | waiting_cfo, self.fin_mgr).action_confirm()
        self.assertEqual(waiting_fin.approval_id.step_ids.sorted('sequence')[0].state, 'approved')
        # the budget waiting for the CFO is untouched by the Finance Manager
        self.assertEqual(waiting_cfo.approval_id.step_ids.sorted('sequence')[1].state, 'pending')

    def _full_approval_to_step2(self, budget):
        self._request(budget)
        self._decide(budget, self.fin_mgr)

    def test_mass_approve_with_nothing_for_the_user_raises(self):
        budget = self._budget(5000)
        self._request(budget)
        with self.assertRaises(UserError):
            self._wizard(budget, self.cfo).action_confirm()

    def test_mass_approve_one_failure_does_not_block_the_others(self):
        # budget A's step 2 job (Controller) has no holder when step 1 completes
        a_rule = self._make_rule(self.company, [self.job_fin], min_amount=100000, sequence=1)
        a_rule.step_ids.create({'rule_id': a_rule.id, 'sequence': 99, 'job_ids': [(6, 0, self.job_ctrl.ids)]})
        budget_a = self._budget(200000)
        self.job_ctrl.company_id = self.company
        holder = self._user('bae_ctrl', self.company)
        emp = self._give_job(holder, self.job_ctrl, self.company)
        self._request(budget_a)
        emp.job_id = False  # the only Controller leaves before step 2 starts
        budget_b = self._budget(5000)
        self._request(budget_b)
        wizard = self._wizard(budget_a | budget_b, self.fin_mgr)
        wizard.action_confirm()
        self.assertEqual(budget_b.approval_id.step_ids.sorted('sequence')[0].state, 'approved')
        self.assertEqual(budget_a.approval_id.step_ids.sorted('sequence')[0].state, 'pending')

    def test_mass_reject_requires_reason(self):
        budgets = self._budget(5000) | self._budget(6000)
        for budget in budgets:
            self._request(budget)
        with self.assertRaises(UserError):
            self._wizard(budgets, self.fin_mgr, 'reject').action_confirm()
        self._wizard(budgets, self.fin_mgr, 'reject', note="Over plan").action_confirm()
        self.assertEqual(budgets.mapped('approval_state'), ['rejected'] * 2)

    def test_step_list_buttons_open_the_wizard_for_the_budgets(self):
        budgets = self._budget(5000) | self._budget(6000)
        for budget in budgets:
            self._request(budget)
        steps = budgets.approval_id.step_ids.filtered(lambda s: s.state == 'pending')
        action = steps.with_user(self.fin_mgr).action_approve_selected()
        self.assertEqual(action['res_model'], 'budget.approval.decision.wizard')
        self.assertEqual(set(action['context']['default_budget_ids']), set(budgets.ids))

    def test_filters_find_what_the_user_must_approve(self):
        mine = self._budget(5000)
        self._request(mine)
        other = self._budget(6000)
        self._full_approval_to_step2(other)  # now waits for the CFO, not for the Finance Manager
        Budget = self.env['budget.analytic']
        to_approve = [('approval_step_ids', 'any', [
            ('state', '=', 'pending'), ('approver_ids', 'in', [self.fin_mgr.id])])]
        self.assertEqual(Budget.search(to_approve) & (mine | other), mine)
        to_approve_cfo = [('approval_step_ids', 'any', [
            ('state', '=', 'pending'), ('approver_ids', 'in', [self.cfo.id])])]
        self.assertEqual(Budget.search(to_approve_cfo) & (mine | other), other)
        requests = Budget.search([('approval_ids.submitted_by', '=', self.accountant.id)])
        self.assertEqual(requests & (mine | other), mine | other)
        self.assertFalse(Budget.search([('approval_ids.submitted_by', '=', self.fin_mgr.id)]) & (mine | other))

    def test_locked_while_pending(self):
        budget = self._budget(5000)
        self._request(budget)
        with self.assertRaises(UserError):
            budget.budget_line_ids[0].write({'budget_amount': 9000})
        with self.assertRaises(UserError):
            budget.write({'budget_line_ids': [(0, 0, {'account_id': self.analytic.id, 'budget_amount': 1})]})
        with self.assertRaises(UserError):
            budget.budget_line_ids.unlink()

    def test_withdraw_unlocks_and_cleans_activities(self):
        budget = self._budget(5000)
        self._request(budget)
        activities = budget.approval_id.step_ids.activity_ids
        self.assertTrue(activities)
        budget.with_user(self.accountant).action_withdraw_approval()
        self.assertEqual(budget.approval_state, 'none')
        self.assertFalse(activities.exists())
        budget.budget_line_ids[0].write({'budget_amount': 9000})

    def test_withdraw_denied_to_unrelated_user(self):
        budget = self._budget(5000)
        self._request(budget)
        with self.assertRaises(UserError):
            budget.with_user(self.fin_mgr).action_withdraw_approval()

    def test_amounts_are_frozen_once_approved(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        with self.assertRaises(UserError):
            budget.budget_line_ids[0].write({'budget_amount': 9000})
        with self.assertRaises(UserError):
            self.env['budget.line'].create({
                'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 100.0})
        self.assertEqual(budget.approval_state, 'approved')  # nothing silently voided
        budget.write({'state': 'confirmed'})  # and the approval still opens it

    def test_reset_approval_allows_editing_then_needs_a_new_request(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        budget.with_user(self.accountant).action_withdraw_approval()  # Reset Approval button
        self.assertEqual(budget.approval_state, 'none')
        self.assertEqual(budget.approval_ids.state, 'voided')
        budget.budget_line_ids[0].write({'budget_amount': 9000})
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})
        self._request(budget)
        self.assertEqual(budget.approval_state, 'to_approve')

    def test_reset_denied_to_unrelated_user(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        with self.assertRaises(UserError):
            budget.with_user(self.fin_mgr).action_withdraw_approval()

    def test_no_reset_once_the_budget_is_open(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        budget.write({'state': 'confirmed'})
        with self.assertRaises(UserError):
            budget.with_user(self.accountant).action_withdraw_approval()

    def test_open_budget_lines_are_not_touched_by_the_module(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        budget.write({'state': 'confirmed'})
        budget.budget_line_ids[0].write({'budget_amount': 9000})
        self.env['budget.line'].create({
            'budget_analytic_id': budget.id, 'account_id': self.analytic.id, 'budget_amount': 100.0})
        self.assertEqual(len(budget.budget_line_ids), 2)

    def test_back_to_draft_expires_approval(self):
        budget = self._budget(5000)
        self._full_approval(budget)
        budget.write({'state': 'confirmed'})
        budget.write({'state': 'draft'})
        self.assertEqual(budget.approval_ids.state, 'expired')
        with self.assertRaises(UserError):
            budget.write({'state': 'confirmed'})

    def test_cancel_voids_pending_approval(self):
        budget = self._budget(5000)
        self._request(budget)
        activities = budget.approval_id.step_ids.activity_ids
        budget.write({'state': 'canceled'})
        self.assertEqual(budget.approval_ids.state, 'voided')
        self.assertFalse(activities.exists())

    # ------------------------------------------------------------------ multi-company and security
    def test_multi_company_rule_matching(self):
        self._make_rule(self.company_b, [self.job_b], min_amount=100)
        budget_b = self._budget(300, company=self.company_b)
        budget_a = self._budget(300)
        self.assertTrue(budget_b.approval_required)
        self.assertFalse(budget_a.approval_required)
        # a second Finance Manager in company B so the requester (accountant) is not the only holder
        budget_b.with_user(self.accountant).with_company(self.company_b).action_request_approval()
        self.assertEqual(budget_b.approval_id.step_ids.approver_ids, self.user_b)

    def test_multi_company_record_isolation(self):
        self._make_rule(self.company_b, [self.job_b], min_amount=100)
        budget_b = self._budget(300, company=self.company_b)
        budget_b.with_user(self.accountant).with_company(self.company_b).action_request_approval()
        approval_b = budget_b.approval_id
        outsider = self.fin_mgr  # no access to company B
        self.assertFalse(self.env['budget.approval'].with_user(outsider).search([('id', '=', approval_b.id)]))
        self.assertFalse(self.env['budget.approval.step'].with_user(outsider).search(
            [('approval_id', '=', approval_b.id)]))
        self.assertFalse(self.env['budget.approval.rule'].with_user(outsider).search(
            [('id', '=', approval_b.rule_id.id)]))

    def test_no_write_access_to_runtime_models(self):
        budget = self._budget(5000)
        self._request(budget)
        with self.assertRaises(AccessError):
            budget.approval_id.with_user(self.fin_mgr).write({'state': 'approved'})
        with self.assertRaises(AccessError):
            budget.approval_id.step_ids.with_user(self.fin_mgr).write({'state': 'approved'})

    def test_only_manager_edits_rules(self):
        with self.assertRaises(AccessError):
            self.rule.with_user(self.accountant).write({'min_amount': 1})
        manager = mail_new_test_user(
            self.env, login='bae_manager', groups='account.group_account_manager',
            company_ids=[(6, 0, self.company.ids)], company_id=self.company.id)
        self.rule.with_user(manager).write({'min_amount': 2000})
