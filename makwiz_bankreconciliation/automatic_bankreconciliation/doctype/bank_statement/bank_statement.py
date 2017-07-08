# -*- coding: utf-8 -*-
# Copyright (c) 2015, MAKWIZ TECHNOLOGIES and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt, getdate, nowdate, fmt_money
from frappe import msgprint, _
from frappe.model.document import Document

class BankStatement(Document):
	def view_clearance_date(self):
		if not (self.bank_account and self.from_date and self.to_date):
			msgprint("Bank Account, From Date and To Date are Mandatory")
			return
		if not (self.bank_statement_detail):
			msgprint("Upload Bank Statement, Bank Statement is Mandatory")	
			return

		condition = ""
		journal_entries = frappe.db.sql("""
			select 
				"Journal Entry" as payment_document, t1.name as payment_entry, 
				t1.cheque_no as cheque_number, t1.cheque_date, 
				t2.debit_in_account_currency as debit, t2.credit_in_account_currency as credit, 
				t1.posting_date, t2.against_account, t1.clearance_date, t2.account_currency 
			from
				`tabJournal Entry` t1, `tabJournal Entry Account` t2
			where
				t2.parent = t1.name and t2.account = %s and t1.docstatus=1
				and t1.posting_date >= %s and t1.posting_date <= %s 
				and ifnull(t1.is_opening, 'No') = 'No' {0}
			order by t1.posting_date ASC, t1.name DESC
		""".format(condition), (self.bank_account, self.from_date, self.to_date), as_dict=1)

		payment_entries = frappe.db.sql("""
			select 
				"Payment Entry" as payment_document, name as payment_entry, 
				reference_no as cheque_number, reference_date as cheque_date, 
				if(paid_from=%(account)s, paid_amount, "") as credit, 
				if(paid_from=%(account)s, "", received_amount) as debit, 
				posting_date, ifnull(party,if(paid_from=%(account)s,paid_to,paid_from)) as against_account, clearance_date,
				if(paid_to=%(account)s, paid_to_account_currency, paid_from_account_currency) as account_currency
			from `tabPayment Entry`
			where
				(paid_from=%(account)s or paid_to=%(account)s) and docstatus=1
				and posting_date >= %(from)s and posting_date <= %(to)s {0}
			order by 
				posting_date ASC, name DESC
		""".format(condition), 
		        {"account":self.bank_account, "from":self.from_date, "to":self.to_date}, as_dict=1)
		
		entries = sorted(list(payment_entries)+list(journal_entries), 
			key=lambda k: k['posting_date'] or getdate(nowdate()))
				
		self.set('payment_entries', [])		
		for d in entries:
			row = self.append('payment_entries', {})			
			d.amount = fmt_money(d.debit if d.debit else d.credit, 2, d.account_currency) + " " + (_("Dr") if d.debit else _("Cr"))			
			d.transaction_type = (("DR") if d.debit else ("CR"))
			d.transaction_amount = (d.debit if d.debit else d.credit)
			for dd in self.get('bank_statement_detail'):		
				if(dd.transaction_type.upper() == d.transaction_type.upper() and round(float(dd.transaction_amount),2) == round(float(d.transaction_amount),2) ):
					d.clearance_date = dd.clearance_date		
			row.update(d)			

	def update_clearance_date(self):
		if not (self.bank_statement_detail):
			msgprint("Upload Bank Statement, Bank Statement is Mandatory")	
			return
		clearance_date_updated = False
		for d in self.get('payment_entries'):
			if d.clearance_date:
				if not d.payment_document:
					frappe.throw(_("Row #{0}: Payment document is required to complete the trasaction"))

				if d.cheque_date and getdate(d.clearance_date) < getdate(d.cheque_date):
					frappe.throw(_("Row #{0}: Clearance date {1} cannot be before Cheque Date {2}")
						.format(d.idx, d.clearance_date, d.cheque_date))
						
				frappe.db.set_value(d.payment_document, d.payment_entry, "clearance_date", d.clearance_date)
				frappe.db.sql("""update `tab{0}` set clearance_date = %s, modified = %s 
					where name=%s""".format(d.payment_document), 
				(d.clearance_date, nowdate(), d.payment_entry))
				
				clearance_date_updated = True

		if clearance_date_updated:
			self.view_clearance_date()		
			msgprint(_("Clearance Date updated"))
		else:
			msgprint(_("Clearance Date not mentioned"))			
