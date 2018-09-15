"""
Double-entry Bookkeeping System
"""

db = '/var/www/wsgi/debs/sql/debs.sql'
thousand_sep = ' '
decimal_sep = ','

from urllib.parse import parse_qs
import sqlite3
from datetime import date

def application(environ,start_response):
	"""entry point"""
	try:
		p = environ['PATH_INFO']
		qs = environ['QUERY_STRING']
		h = [('Content-type','text/html')]
		# Connect to the database
		cnx = None
		cnx = sqlite3.connect(db)
		crs = cnx.cursor()
		# Main selector
		if p=="/":
			c,r = main(crs)
		elif p=="/acct":
			c,r = acct(crs,qs)
		elif p=="/ins_xact":
			c,r,h = ins_xact(crs,environ)
		elif p=="/del_xact":
			c,r,h = del_xact(crs,qs)
		elif p=="/creat_acct":
			c,r,h = creat_acct(crs,qs)
		elif p=="/close_acct":
			c,r,h = close_acct(crs,qs)
		else:
			raise ValueError("Wrong access")
	except ValueError as e:
		c = '400 Bad Request'
		r = "<html><head></head><body><h1>Bad request</h1><h2>{}</h2></body></html>".format(e)
	except sqlite3.Error as e:
		c = '500 Internal Server Error'
		r = "<html><head></head><body><h1>Database error</h1><h2>{}</h2></body></html>".format(e)
	finally:
		if cnx:
			cnx.commit()
			cnx.close()
	start_response(c,h)
	return [r.encode()]

atypes = [('E','Equity'),('A','Assets'),('L','Liabilities'),('i','Income'),('e','Expenses')]

def cur2int(s):
	"""convert currency string to integer"""
	s = s.replace(" ","")
	r = ""
	i = 0
	for i,c in enumerate(s):
		if c in ",.":
			break
		r = r+c
	return int(r+s[i+1:i+3].ljust(2,'0'))

def arith(s):
	"""evaluate string as an arithmetic expression"""
	try:
		# normalize string
		s = s.replace(" ","") # drop spaces
		s = s.replace(decimal_sep,".") # use . as decimal point
		# check that string contains only numbers, operators, and brackets
		for c in s:
			if not c in "0123456789.+-*/()":
				raise ValueError
		# now it's safe to evaluate it
		return str(eval(s))
	except:
		raise ValueError

def int2cur(v):
	"""convert integer to currency string"""
	s = str(abs(v))
	r = ""
	for i,c in enumerate(s[::-1].ljust(3,'0'),1):
		if i==3:
			r = decimal_sep+r
		elif i%3==0:
			r = thousand_sep+r
		r = c+r
	if v<0:
		r = "&minus;"+r
	return r

def res(crs):
	"""return the only result of a transaction"""
	return crs.fetchone()[0]

def balance(crs,aid):
	"""returns the current balance of account aid"""
	crs.execute("SELECT max(xid) FROM xacts WHERE aid=?",[aid])
	maxxid = res(crs)
	if maxxid is not None:
		crs.execute("SELECT bal FROM xacts WHERE xid=? and aid=?",[maxxid,aid])
		return int(res(crs))
	else:
		return 0

def new_balance(atype,bal,dr,cr):
	"""computes the new balance after transaction"""
	if atype in ('E','L','i'):
		return bal+cr-dr
	elif atype in ('A','e'):
		return bal+dr-cr
	else:
		raise ValueError("Bad account type")

def main(crs):
	"""show main page"""
	# Caption
	r = """
	<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
	<html>
	<head>
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	<meta http-equiv="pragma" content="no-cache">
	<meta name="format-detection" content="telephone=no">
	<title>Double-entry Bookkeeping System</title>
	</head>
	<body>
	<dl>
	"""
	# Accounts
	totals = {}
	for atc,atn in atypes:
		r += """
		<dt><strong>{}</strong>
		<dd>
		<table>
		""".format(atn)
		totals[atc] = 0
		crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
		for (aid,name) in crs.fetchall():
			bal = balance(crs,aid)
			totals[atc] += bal
			r += """
			<tr>
			<td><a href='acct?aid={}'>{}</a></td>
			<td align='right'>&nbsp; {}</td>
			</tr>
			""".format(aid,name,int2cur(bal))
		r += """
		<tr><td colspan=2 bgcolor='#c0c0c0'></td></tr>
		<tr>
		<td>Total</td>
		<td align='right'>&nbsp; {}</td>
		</tr>
		<tr><td colspan=2>&nbsp;</td></tr>
		</table>
		""".format(int2cur(totals[atc]))
	r += """
	</dl>
	"""
	# Verify accounting equation
	v = 0
	for atc in ('E','L','i'):
		v += totals[atc]
	for atc in ('A','e'):
		v -= totals[atc]
	if v!=0:
		c = '200 OK'
		r = """
		<html><head></head><body>
		<h1>Accounting equation DOESN'T HOLD!</h1>
		<h2>Database is corrupted and inconsistent!</h2>
		</body></html>
		"""
		return c,r
	# New account
	r += """
	<hr>
	<form action="creat_acct" method="get">
	New account &nbsp;
	<select name='type'>
	<option></option>
	"""
	for atc,atn in atypes:
		r += """
		<option value='{}'>{}</option>
		""".format(atc,atn)
	r += """
	</select>
	<input type="text" name="name">
	<input type="submit" value="Create">
	</form>
	"""
	# Closed accounts
	r += """
	<hr>
	<h3>Closed accounts</h3>
	<dl>
	"""
	for atc,atn in atypes:
		r += """
		<dt>
		<strong>{}</strong>
		""".format(atn)
		crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt<>0 ORDER BY name",[atc])
		for aid,name in crs:
			r += """
			<dd><a href='acct?aid={}'>{}</a>
			""".format(aid,name)
	# Cellar
	r += """
	</dl>
	</body>
	</html>
	"""
	# Return success
	c = '200 OK'
	return c,r

def acct(crs,qs):
	"""show account statement page"""
	# Get arguments
	q = parse_qs(qs)
	# Check the mandatory argument
	try:
		aid = q['aid'][0]
	except KeyError:
		raise ValueError("Wrong access")
	crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
	if res(crs)==0:
		raise ValueError("Bad aid")
	# Get optional argument
	if 'hlxid' in q:
		hlxid = int(q['hlxid'][0])
	else:
		hlxid = None
	# Get commonly used account properties
	crs.execute("SELECT name,odt,cdt FROM accts WHERE aid=?",[aid])
	name,odt,cdt = crs.fetchone()
	bal = balance(crs,aid)
	crs.execute("SELECT MAX(dt) FROM xacts WHERE aid=?",[aid])
	maxdt = res(crs)
	if maxdt is None:
		maxdt = 0
	crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[aid])
	maxxid = res(crs)
	if maxxid is None:
		maxxid = 0
	# Find the statement period
	try:
		# Try to get the statement period from the arguments
		sy=int(q['syyyy'][0])
		sm=int(q['smm'][0])
		sd=int(q['sdd'][0])
		sdt = date(sy,sm,sd).toordinal()
		ey=int(q['eyyyy'][0])
		em=int(q['emm'][0])
		ed=int(q['edd'][0])
		edt = date(ey,em,ed).toordinal()
		if sdt>edt:
			raise Exception
	except:
		# If fails, revert to the whole account's lifetime
		sdt = odt
		if cdt==0:
			edt = date.today().toordinal()
		else:
			edt = cdt
	# Caption
	r = """
	<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
	<html>
	<head>
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	<meta http-equiv="pragma" content="no-cache">
	<meta name="format-detection" content="telephone=no">
	<title>Double-entry Bookkeeping System</title>
	<script type="text/javascript">
	function confirmCloseAccount(what) {
	return confirm("Are you sure to close account " + what + "?");
	}
	function confirmDeleteTransaction() {
	return confirm("Are you sure to delete this transaction?");
	}
	function hlCurDate() {
	var cur = new Date();
	var y = document.getElementById("y");
	var m = document.getElementById("m");
	var d = document.getElementById("d");
	var now = true;
	now = now && (y.value == cur.getFullYear());
	y.style.color = (now) ? "" : "#808080";
	now = now && (m.value == cur.getMonth()+1);
	m.style.color = (now) ? "" : "#808080";
	now = now && (d.value == cur.getDate());
	d.style.color = (now) ? "" : "#808080";
	}
	function chgDate(delta) {
	var td = new Date();
	var y = document.getElementById("y");
	var m = document.getElementById("m");
	var d = document.getElementById("d");
	td.setFullYear(y.value);
	td.setMonth(m.value-1);
	td.setDate(d.value);
	td.setDate(td.getDate() + delta);
	y.value = td.getFullYear();
//	m.value = ("0" + (td.getMonth()+1)).slice(-2);
//	d.value = ("0" + td.getDate()).slice(-2);
	m.value = td.getMonth()+1;
	d.value = td.getDate();
	hlCurDate();
	}
	</script>
	</head>
	<body>
	"""
	# Basic statement info: start and end balances, and turnovers
	sb = eb = tdr = tcr = 0
	crs.execute("SELECT dt,dr,cr,bal FROM xacts WHERE aid=? ORDER BY xid ASC",[aid])
	for (dt,dr,cr,b) in crs.fetchall():
		if dt<sdt:
			sb = int(b)
		else:
			if dt<=edt:
				tdr += int(dr)
				tcr += int(cr)
				eb = int(b)
			else:
				break
	sdt_d = date.fromordinal(sdt)
	edt_d = date.fromordinal(edt)
	r += """
	<center>
	<form action="acct" method=get>
	<input type=hidden name=aid value="{}">
	<h2>{}</h2>
	<h3>Account statement</h3> for the period from
	<input type=text name=syyyy size=4 maxlength=4 style="width:4ch" value="{}">
	<input type=text name=smm size=2 maxlength=2 style="width:2ch" value="{}">
	<input type=text name=sdd size=2 maxlength=2 style="width:2ch" value="{}">
	to
	<input type=text name=eyyyy size=4 maxlength=4 style="width:4ch" value="{}">
	<input type=text name=emm size=2 maxlength=2 style="width:2ch" value="{}">
	<input type=text name=edd size=2 maxlength=2 style="width:2ch" value="{}">
	<input type=submit value=Update>
	</form>
	""".format(aid,name,sdt_d.year,sdt_d.month,sdt_d.day,edt_d.year,edt_d.month,edt_d.day)
	r += """
	<table>
	<tr><td colspan=3>&nbsp;</td></tr>
	<tr> <td align=left>Starting balance</td> <td>&nbsp;</td> <td align=right>{}</td> </tr>
	<tr> <td align=left>Debit turnovers</td> <td>&nbsp;</td> <td align=right>{}</td> </tr>
	<tr> <td align=left>Credit turnovers</td> <td>&nbsp;</td> <td align=right>{}</td> </tr>
	<tr> <td align=left>Ending balance</td> <td>&nbsp;</td> <td align=right>{}</td> </tr>
	</table>
	</center>
	<a href=".">Back to list</a>
	<hr>
	""".format(int2cur(sb),int2cur(tdr),int2cur(tcr),int2cur(eb))
	# Transactions
	r += """
	<table width="100%" cellspacing=0>
	<tr bgcolor="#f0f0f0">
	<th width="15%" align=left>Date</th>
	<th width="10%" align=right>Dr</th>
	<th width="10%" align=right>Cr</th>
	<th width="15%" align=right>Balance</th>
	<th width="25%" align=right>Opp acct</th>
	<th width="25%">Comment</th>
	</tr>
	</table>
	"""
	# New transaction
	if cdt==0 and maxdt<=edt:
		d = date.today()
		r += """
		<form action="ins_xact" method=post>
		<table width="100%" cellspacing=0>
		<tr bgcolor="#f0f0f0" style="white-space: nowrap;">
		<td width="15%" align=left>
		<a style="text-decoration:none" href='javascript:chgDate(-1)' title="day before">&larr;</a> 
		<input type=text name=yyyy size=4 maxlength=4 style="width:4ch" value="{}" id=y onchange="hlCurDate()">
		<input type=text name=mm size=2 maxlength=2 style="width:2ch" value="{}" id=m onchange="hlCurDate()">
		<input type=text name=dd size=2 maxlength=2 style="width:2ch" value="{}" id=d onchange="hlCurDate()">
		<a style="text-decoration:none" href="javascript:chgDate(+1)" title="day after">&rarr;</a>
		</td>
		<td width="10%" align=right><input type=text size=12 style="width:12ch" name=dr></td>
		<td width="10%" align=right><input type=text size=12 style="width:12ch" name=cr></td>
		<td width="15%" align=right><input type=text size=12 style="width:12ch" name=newbal></td>
		<td width="25%" align=right>
		<input type=hidden name=aid value="{}">
		<select name=oaid>
		<option></option>
		""".format(d.year,d.month,d.day,aid)
		for atc,atn in atypes:
			r += """
			<optgroup label='{}'>
			""".format(atn)
			crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
			opts = crs.fetchall()
			for oaid,oaname in opts:
				r += """
				<option value='{}'>{}</option>
				""".format(oaid,oaname)
			if len(opts)==0:
				r += """
				<option></option>
				"""
			r += """
			</optgroup>
			"""
		r += """
		</select>
		</td>
		<td width="25%" align=center>
		<input type=text name=comment size=20 style="width:75%" maxlength=255>
		<input type=submit value=Insert>
		</td>
		</tr>
		</table>
		</form>
		"""
	# Past transactions
	r += """
	<table width="100%" style="border-spacing: 0 2px;">
	<tr>
	<td width="15%"></td>
	<td width="10%"></td>
	<td width="10%"></td>
	<td width="15%"></td>
	<td width="25%"></td>
	<td width="23%"></td>
	<td width="2%"></td>
	</tr>
	"""
	prev_year = None
	prev_month = None
	crs.execute("SELECT * FROM xacts WHERE aid=? AND ?<=dt AND dt<=? ORDER BY xid DESC",[aid,sdt,edt])
	for (xid,dt,aid,oaid,dr,cr,x_bal,comment) in crs.fetchall():
		dt_d = date.fromordinal(dt)
		dr = int2cur(int(dr)) if dr!='0' else ""
		cr = int2cur(int(cr)) if cr!='0' else ""
		x_bal = int2cur(int(x_bal))
		x_year = dt_d.year
		x_month = dt_d.month
		if prev_year is None and prev_month is None:
			sep_bgcolor = "#ffffff"
		elif x_year!=prev_year:
			sep_bgcolor = "#808080"
		elif x_month!=prev_month:
			sep_bgcolor = "#c0c0c0"
		else:
			sep_bgcolor = "#f0f0f0"
		if xid==hlxid:
			hl_bgcolor = 'bgcolor="#ffff80"'
			anchor = "<a id=hl></a>"
		else:
			hl_bgcolor = ""
			anchor = ""
		prev_year = x_year
		prev_month = x_month
		crs.execute("SELECT type,name FROM accts WHERE aid=?",[oaid])
		oatype,oaname = crs.fetchone()
		r += """
		<tr>
		<td colspan=7 bgcolor="{}"></td>
		</tr>
		<tr style="white-space: nowrap;" {}>
		<td>{}</td>
		<td align=right>{}</td>
		<td align=right>{}</td>
		<td align=right>{}</td>
		<td align=right><font color="#c0c0c0">{}</font>&nbsp;<a href="acct?aid={}&amp;hlxid={}#hl">{}</a></td>
		<td align=left>&nbsp;<small>{}</small>{}</td>
		<td>
		""".format(sep_bgcolor,hl_bgcolor,dt_d,dr,cr,x_bal,oatype,oaid,xid,oaname,comment,anchor)
		# We can delete the transaction if it is the last one for both aid and oaid
		if xid==maxxid:
			crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[oaid])
			if xid==res(crs):
				r += """
				<a style='color:red; font-weight: bold; text-decoration:none'
				href='del_xact?xid={}&amp;aid={}'
				onClick='return confirmDeleteTransaction()'
				title='delete transaction'>
				&times;
				</a>
				""".format(xid,aid)
		r += """
		</td>
		</tr>
		"""
	r += """
	</table>
	<hr>
	"""
	# Close the account
	if bal==0 and cdt==0:
		r += """
		<center>
		<a href='close_acct?aid={}' onClick='return confirmCloseAccount(\"{}\")'>
		<font color=red>Close this account</font>
		</a>
		</center>
		""".format(aid,name)
	# Cellar
	r += """
	</body>
	</html>
	"""
	# Return success
	c = '200 OK'
	return c,r

def ins_xact(crs,environ):
	"""insert a new transaction"""
	# Get arguments
	try:
		q = parse_qs(environ['wsgi.input'].readline().decode(),keep_blank_values=True)
		yyyy = q['yyyy'][0]
		mm = q['mm'][0]
		dd = q['dd'][0]
		dr = q['dr'][0]
		cr = q['cr'][0]
		newbal = q['newbal'][0]
		aid = q['aid'][0]
		oaid = q['oaid'][0]
		comment = q['comment'][0]
	except KeyError:
		raise ValueError("Wrong access")
	# Check date
	try:
		dt = date(int(yyyy),int(mm),int(dd)).toordinal()
	except ValueError:
		raise ValueError("Bad date")
	# Check transaction values
	if dr=='':
		dr = '0'
	try:
		dr = cur2int(arith(dr))
	except ValueError:
		raise ValueError("Bad Dr")
	if cr=='':
		cr = '0'
	try:
		cr = cur2int(arith(cr))
	except ValueError:
		raise ValueError("Bad Cr")
	if dr<0 or cr<0:
		raise ValueError("Dr and Cr cannot be negative")
	if dr!=0 and cr!=0:
		raise ValueError("Dr and Cr cannot both be set")
	if dr==0 and cr==0:
		if newbal=='':
			raise ValueError("Set either Dr or Cr, or Balance")
		try:
			newbal = cur2int(arith(newbal))
		except ValueError:
			raise ValueError("Bad Balance")
	# Check accounts
	if oaid=='':
		raise ValueError("Please select the opposing account")
	try:
		aid = int(aid)
	except ValueError:
		raise ValueError("Bad aid")
	try:
		oaid = int(oaid)
	except ValueError:
		raise ValueError("Bad oaid")
	if aid==oaid:
		raise ValueError("Transaction with the same account")
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[aid])
	if res(crs)==0:
		raise ValueError("Non-existent aid")
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[oaid])
	if res(crs)==0:
		raise ValueError("Non-existent oaid")
	if dt>date.today().toordinal():
		raise ValueError("Date cannot be in the future")
	crs.execute("SELECT odt FROM accts WHERE aid=?",[aid])
	if dt<res(crs):
		raise ValueError("Date before the account's opening date")
	crs.execute("SELECT odt FROM accts WHERE aid=?",[oaid])
	if dt<res(crs):
		raise ValueError("Date before the opposing account's opening date")
	crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=? AND dt>?",[aid,dt])
	if res(crs)!=0:
		raise ValueError("Current account has newer transactions")
	crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=? AND dt>?",[oaid,dt])
	if res(crs)!=0:
		raise ValueError("Opposing account has newer transactions")
	# Input data OK, prepare to insert transaction
	# Get account types
	crs.execute("SELECT type FROM accts WHERE aid=?",[aid])
	atype = res(crs)
	crs.execute("SELECT type FROM accts WHERE aid=?",[oaid])
	oatype = res(crs)
	# Get account balances
	bal = balance(crs,aid)
	obal = balance(crs,oaid)
	if dr==0 and cr==0:
		# Derive dr and cr from new and old balances
		if atype in ('E','L','i'):
			if newbal>bal:
				cr = newbal-bal
			else:
				dr = bal-newbal
		elif atype in ('A','e'):
			if newbal>bal:
				dr = newbal-bal
			else:
				cr = bal-newbal
		else:
			raise ValueError("Bad account type")
	else:
		newbal = new_balance(atype,bal,dr,cr)
	# Compute new balance of the opposing account, with dr and cr exchanged
	onewbal = new_balance(oatype,obal,cr,dr)
	# Insert transaction
	crs.execute("SELECT MAX(xid) FROM xacts")
	maxxid = res(crs)
	if maxxid is None:
		xid = 0
	else:
		xid = maxxid+1
	crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,aid,oaid,str(dr),str(cr),str(newbal),comment])
	crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,oaid,aid,str(cr),str(dr),str(onewbal),comment])
	# Return redirect
	c = '303 See Other'
	r = ""
	h = [('Location',"acct?aid={}".format(aid))]
	return c,r,h

def del_xact(crs,qs):
	"""delete transaction"""
	# Get arguments
	q = parse_qs(qs)
	try:
		xid = q['xid'][0]
		aid = q['aid'][0]
	except KeyError:
		raise ValueError("Wrong access")
	# Check accounts
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[aid])
	if res(crs)==0:
		raise ValueError("Bad aid")
	crs.execute("SELECT COUNT(*) FROM xacts WHERE xid=? AND aid=?",[xid,aid])
	if res(crs)==0:
		raise ValueError("Bad xid")
	crs.execute("SELECT oaid FROM xacts WHERE xid=? AND aid=?",[xid,aid])
	oaid = res(crs)
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[oaid])
	if res(crs)==0:
		raise ValueError("Bad oaid")
	crs.execute("SELECT COUNT(*) FROM xacts WHERE xid>? AND aid=?",[xid,aid])
	if res(crs)!=0:
		raise ValueError("Current account has newer transactions")
	crs.execute("SELECT COUNT(*) FROM xacts WHERE xid>? AND aid=?",[xid,oaid])
	if res(crs)!=0:
		raise ValueError("Opposing account has newer transactions")
	# Delete transaction
	crs.execute("DELETE FROM xacts WHERE xid=?",[xid])
	# Return redirect
	c = '303 See Other'
	r = ""
	h = [('Location',"acct?aid={}".format(aid))]
	return c,r,h

def creat_acct(crs,qs):
	"""create a new account"""
	# Get arguments
	q = parse_qs(qs,keep_blank_values=True)
	try:
		type = q['type'][0]
		name = q['name'][0]
	except KeyError:
		raise ValueError("Wrong access")
	# Check arguments
	if type=='':
		raise ValueError("Please select the account type")
	if not type in [x for x,_ in atypes]:
		raise ValueError("Wrong account type")
	if name=='':
		raise ValueError("Please set the account name")
	crs.execute("SELECT COUNT(*) FROM accts WHERE name=?",[name])
	if res(crs)!=0:
		raise ValueError("Account with the same name already exists")
	# Create account
	odt = date.today().toordinal()
	crs.execute("INSERT INTO accts VALUES (NULL,?,?,?,0)",[type,name,odt])
	# Return redirect
	c = '303 See Other'
	r = ""
	h = [('Location',".")]
	return c,r,h

def close_acct(crs,qs):
	"""close account"""
	# Get argument
	q = parse_qs(qs)
	try:
		aid = q['aid'][0]
	except KeyError:
		raise ValueError("Wrong access")
	# Check argument
	crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
	if res(crs)==0:
		raise ValueError("Wrong aid")
	crs.execute("SELECT cdt FROM accts WHERE aid=?",[aid])
	if res(crs)!=0:
		raise ValueError("Account already closed")
	if balance(crs,aid)!=0:
		raise ValueError("Non-zero balance")
	# Close account
	now = date.today().toordinal()
	crs.execute("UPDATE accts SET cdt=? WHERE aid=?",[now,aid])
	# Return redirect
	c = '303 See Other'
	r = ""
	h = [('Location',"acct?aid={}".format(aid))]
	return c,r,h
