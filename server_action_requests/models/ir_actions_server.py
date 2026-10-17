# -*- coding: utf-8 -*-
import requests

from odoo import models
from odoo.tools.safe_eval import wrap_module

# Same surface Odoo Online exposes in practice: the HTTP verbs plus the
# exception classes so code can catch e.g. requests.exceptions.Timeout.
safe_requests = wrap_module(requests, {
    'request': None,
    'get': None,
    'post': None,
    'put': None,
    'patch': None,
    'delete': None,
    'head': None,
    'RequestException': None,
    'HTTPError': None,
    'ConnectionError': None,
    'Timeout': None,
    'exceptions': [
        'RequestException', 'HTTPError', 'ConnectionError', 'Timeout',
        'ConnectTimeout', 'ReadTimeout', 'TooManyRedirects', 'JSONDecodeError',
    ],
})


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def _get_eval_context(self, action=None):
        eval_context = super()._get_eval_context(action=action)
        eval_context.setdefault('requests', safe_requests)
        return eval_context
