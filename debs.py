"""
Double-entry Bookkeeping System
Copyright (c) 2019 Alexander Mukhin
MIT License
"""

thousand_sep=" "
decimal_sep=","

style="""
a.arr { text-decoration: none; }
a.red { color: red; }
a.x { color: red; font-weight: bold; text-decoration:none; }
div.center { text-align: center; }
div.form { background-color: #f0f0f0; }
div.indent { margin-left: 5ch; }
input.comm { width: 75%; }
input.w2 { width: 2ch; }
input.w4 { width: 4ch; }
input.w12 { width: 12ch; }
span.atype { color: #c0c0c0; }
span.err { color: red; }
table { border-spacing: 0; }
table td { padding: 2px; }
table.center { margin: auto; }
table.full { width: 100%; }
td.r { text-align: right; }
td.x { width: 2%; }
th.date,td.date { width: 15%; text-align: left; }
th.dr,td.dr { width: 10%; text-align: right; }
th.cr,td.cr { width: 10%; text-align: right; }
th.bal,td.bal { width: 15%; text-align: right; }
th.opp,td.opp { width: 25%; text-align: right; }
th.comm,td.comm { text-align: center; }
tr.hl { background-color: #ffff80; }
tr.line { white-space: nowrap; }
tr.sep td { border-top: 2px solid #f0f0f0; }
tr.sep_month td { border-top: 2px solid #c0c0c0; }
tr.sep_year td { border-top: 2px solid #808080; }
tr.sep_tot td { border-top: 2px solid #c0c0c0; }
"""

from urllib.parse import parse_qs,quote_plus,urlencode
import sqlite3
from datetime import date
from html import escape
from os.path import exists

class BadInput(Exception):
	"""invalid user input"""
	pass

def application(environ,start_response):
	"""entry point"""
	try:
		# Connect to the database
		cnx=None
		db=environ["DB"]
		if not exists(db):
			raise sqlite3.Error("file does not exist")
		cnx=sqlite3.connect(db)
		cnx.isolation_level=None # we manage transactions explicitly
		# Main selector
		crs=cnx.cursor()
		p=environ["PATH_INFO"]
		qs=environ["QUERY_STRING"]
		crs.execute("BEGIN") # execute each request in a transaction
		with cnx:
			if p=="/":
				c,r,h=main(crs)
			elif p=="/acct":
				c,r,h=acct(crs,qs)
			elif p=="/ins_xact":
				c,r,h=ins_xact(crs,environ)
			elif p=="/del_xact":
				c,r,h=del_xact(crs,qs)
			elif p=="/creat_acct":
				c,r,h=creat_acct(crs,environ)
			elif p=="/close_acct":
				c,r,h=close_acct(crs,environ)
			else:
				raise ValueError("Wrong access")
	except ValueError as e:
		c="400 Bad Request"
		r="{}".format(e)
		h=[("Content-type","text/plain")]
	except sqlite3.Error as e:
		c="500 Internal Server Error"
		r="Database error: {}".format(e)
		h=[("Content-type","text/plain")]
	except KeyError as e:
		c="400 Bad Request"
		r="Parameter expected: {}".format(e)
		h=[("Content-type","text/plain")]
	if cnx:
		cnx.close()
	h+=[("Cache-Control","max-age=0")]
	start_response(c,h)
	return [r.encode()]

atypes=[("E","Equity"),("A","Assets"),("L","Liabilities"),("i","Income"),("e","Expenses")]

def cur2int(s):
	"""convert currency string to integer"""
	s=s.replace(" ","") # drop spaces
	s=s.replace(",",decimal_sep) # always accept "," as a decimal separator
	s=s.replace(".",decimal_sep) # always accept "." as a decimal separator
	r=""
	i=0
	for i,c in enumerate(s):
		if c is decimal_sep:
			break
		r=r+c
	return int(r+s[i+1:i+3].ljust(2,"0"))

def arith(s):
	"""evaluate string as an arithmetic expression"""
	try:
		# normalize string
		s=s.replace(" ","") # drop spaces
		s=s.replace(decimal_sep,".") # use . as decimal point
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
	s=str(abs(v))
	r=""
	for i,c in enumerate(s[::-1].ljust(3,"0"),1):
		if i==3:
			r=decimal_sep+r
		elif i%3==0:
			r=thousand_sep+r
		r=c+r
	if v<0:
		r="&minus;"+r
	return r

def res(crs):
	"""return the only result of a transaction"""
	return crs.fetchone()[0]

def balance(crs,aid):
	"""returns the current balance of account aid"""
	crs.execute("SELECT max(xid) FROM xacts WHERE aid=?",[aid])
	maxxid=res(crs)
	if maxxid is not None:
		crs.execute("SELECT bal FROM xacts WHERE xid=? and aid=?",[maxxid,aid])
		return int(res(crs))
	else:
		return 0

def new_balance(atype,bal,dr,cr):
	"""computes the new balance after transaction"""
	if atype in ("E","L","i"):
		return bal+cr-dr
	elif atype in ("A","e"):
		return bal+dr-cr
	else:
		raise ValueError("Bad account type")

def v(kv,k):
	"""returns the value of key or empty string"""
	try:
		return kv[k]
	except:
		return ""

def main(crs,err=None):
	"""show main page"""
	# Header
	r="""
	<!DOCTYPE html>
	<html>
	<head>
	<meta charset="UTF-8">
	<meta name="format-detection" content="telephone=no">
	<style>
	{}
	</style>
	<title>Double-entry Bookkeeping System</title>
	</head>
	""".format(style)
	# Body
	r+="""
	<body>
	"""
	# Accounts
	totals={}
	for atc,atn in atypes:
		r+="""
		<strong>{}</strong>
		<div class=indent>
		<table>
		""".format(atn)
		totals[atc]=0
		crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
		for (aid,name) in crs.fetchall():
			bal=balance(crs,aid)
			totals[atc]+=bal
			r+="""
			<tr>
			<td><a href="acct?aid={}">{}</a></td>
			<td class=r>&nbsp; {}</td>
			</tr>
			""".format(aid,name,int2cur(bal))
		r+="""
		<tr class=sep_tot>
		<td>Total</td>
		<td class=r>&nbsp; {}</td>
		</tr>
		<tr><td colspan=2>&nbsp;</td></tr>
		</table>
		</div>
		""".format(int2cur(totals[atc]))
	# Verify accounting equation
	d=0
	for atc in ("E","L","i"):
		d+=totals[atc]
	for atc in ("A","e"):
		d-=totals[atc]
	if d!=0:
		c="500 Internal Server Error"
		r="Inconsistent database: accounting equation doesn't hold"
		h=[("Content-type","text/plain")]
		return c,r,h
	# New account
	r+="""
	<hr>
	<div class=form>
	<form action=creat_acct method=post>
	New account &nbsp;
	<select name=atype>
	<option value="">&nbsp;</option>
	"""
	for atc,atn in atypes:
		sel="selected" if atc==v(err,"atype") else ""
		r+="""
		<option value="{}" {}>{}</option>
		""".format(atc,sel,atn)
	r+="""
	</select>
	<input type=text name=aname value="{}">
	<input type=submit value=Create>
	</form>
	""".format(v(err,"aname"))
	# Show error message
	if err is not None:
		r+="""
		<span class=err>{}</span>
		""".format(err["msg"])
	# Close form area
	r+="""
	</div>
	"""
	# Closed accounts
	r+="""
	<hr>
	<h3>Closed accounts</h3>
	"""
	for atc,atn in atypes:
		r+="""
		<strong>{}</strong>
		<div class=indent>
		""".format(atn)
		crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt<>0 ORDER BY name",[atc])
		for aid,name in crs:
			r+="""
			<a href="acct?aid={}">{}</a><br>
			""".format(aid,name)
		r+="""
		</div>
		"""
	# Cellar
	r+="""
	</body>
	</html>
	"""
	# Return success
	c="200 OK"
	h=[("Content-type","text/html")]
	return c,r,h

def acct(crs,qs,err=None):
	"""show account statement page"""
	# Get arguments
	q=parse_qs(qs,keep_blank_values=True)
	# Check the mandatory argument
	try:
		aid=q["aid"][0]
	except KeyError:
		raise ValueError("Wrong access")
	crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
	if res(crs)==0:
		raise ValueError("Bad aid")
	# Get optional argument
	hlxid=int(q["hlxid"][0]) if "hlxid" in q else None
	# Get commonly used account properties
	crs.execute("SELECT name,odt,cdt FROM accts WHERE aid=?",[aid])
	aname,odt,cdt=crs.fetchone()
	bal=balance(crs,aid)
	crs.execute("SELECT MAX(dt) FROM xacts WHERE aid=?",[aid])
	maxdt=res(crs)
	if maxdt is None:
		maxdt=0
	crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[aid])
	maxxid=res(crs)
	if maxxid is None:
		maxxid=0
	# Find the statement period
	try:
		# Try to get the statement period from the arguments
		sy=int(q["syyyy"][0])
		sm=int(q["smm"][0])
		sd=int(q["sdd"][0])
		sdt=date(sy,sm,sd).toordinal()
		ey=int(q["eyyyy"][0])
		em=int(q["emm"][0])
		ed=int(q["edd"][0])
		edt=date(ey,em,ed).toordinal()
		if sdt>edt:
			raise Exception
	except:
		# If fails, revert to the whole account's lifetime
		sdt=odt
		if cdt==0:
			edt=date.today().toordinal()
		else:
			edt=cdt
	# Header
	r="""
	<!DOCTYPE html>
	<html>
	<head>
	<meta charset="UTF-8">
	<meta name="format-detection" content="telephone=no">
	<style>
	{}
	</style>
	""".format(style)
	r+="""
	<script>
	function confirmCloseAccount(what) {
	return confirm("Are you sure to close account "+what+"?");
	}
	function confirmDeleteTransaction() {
	return confirm("Are you sure to delete this transaction?");
	}
	function hlCurDate() {
	var cur=new Date();
	var y=document.getElementById("y");
	var m=document.getElementById("m");
	var d=document.getElementById("d");
	var now=true;
	now=now&&(y.value==cur.getFullYear());
	y.style.color=(now)?"":"#808080";
	now=now&&(m.value==cur.getMonth()+1);
	m.style.color=(now)?"":"#808080";
	now=now&&(d.value==cur.getDate());
	d.style.color=(now)?"":"#808080";
	}
	function chgDate(delta) {
	var td=new Date();
	var y=document.getElementById("y");
	var m=document.getElementById("m");
	var d=document.getElementById("d");
	td.setFullYear(y.value);
	td.setMonth(m.value-1);
	td.setDate(d.value);
	td.setDate(td.getDate()+delta);
	y.value=td.getFullYear();
	m.value=td.getMonth()+1;
	d.value=td.getDate();
	hlCurDate();
	}
	</script>
	<title>Double-entry Bookkeeping System</title>
	</head>
	"""
	# Basic statement info: start and end balances, and turnovers
	sb=eb=tdr=tcr=0
	crs.execute("SELECT dt,dr,cr,bal FROM xacts WHERE aid=? ORDER BY xid ASC",[aid])
	for (dt,dr,cr,b) in crs.fetchall():
		if dt<sdt:
			sb=int(b)
		else:
			if dt<=edt:
				tdr+=int(dr)
				tcr+=int(cr)
				eb=int(b)
			else:
				break
	sdt_d=date.fromordinal(sdt)
	edt_d=date.fromordinal(edt)
	# Body
	r+="""
	<body>
	<div class=center>
	<form action=acct method=get>
	<input type=hidden name=aid value="{}">
	<h2>{}</h2>
	<h3>Account statement</h3> for the period from
	<input type=text name=syyyy size=4 maxlength=4 class=w4 value="{}">
	<input type=text name=smm size=2 maxlength=2 class=w2 value="{}">
	<input type=text name=sdd size=2 maxlength=2 class=w2 value="{}">
	to
	<input type=text name=eyyyy size=4 maxlength=4 class=w4 value="{}">
	<input type=text name=emm size=2 maxlength=2 class=w2 value="{}">
	<input type=text name=edd size=2 maxlength=2 class=w2 value="{}">
	<input type=submit value=Update>
	</form>
	</div>
	""".format(aid,aname,sdt_d.year,sdt_d.month,sdt_d.day,edt_d.year,edt_d.month,edt_d.day)
	r+="""
	<table class=center>
	<tr><td colspan=3>&nbsp;</td></tr>
	<tr><td>Starting balance</td><td>&nbsp;</td><td class=r>{}</td></tr>
	<tr><td>Debit turnovers</td><td>&nbsp;</td><td class=r>{}</td></tr>
	<tr><td>Credit turnovers</td><td>&nbsp;</td><td class=r>{}</td></tr>
	<tr><td>Ending balance</td><td>&nbsp;</td><td class=r>{}</td></tr>
	</table>
	<a href=".">Back to list</a>
	<hr>
	""".format(int2cur(sb),int2cur(tdr),int2cur(tcr),int2cur(eb))
	# Transactions
	r+="""
	<table class=full>
	<tr class=line>
	<th class=date>Date</th>
	<th class=dr>Dr</th>
	<th class=cr>Cr</th>
	<th class=bal>Balance</th>
	<th class=opp>Opposing account</th>
	<th class=comm>Comment</th>
	<th class=x></th>
	</tr>
	</table>
	"""
	# New transaction
	if cdt==0 and maxdt<=edt:
		d=date.today()
		yyyy=d.year if err is None else err["yyyy"]
		mm=d.month if err is None else err["mm"]
		dd=d.day if err is None else err["dd"]
		r+="""
		<div class=form>
		<form action=ins_xact method=post>
		<table class=full>
		<tr class=line>
		<td class=date>
		<a class=arr href="javascript:chgDate(-1)" title="day before">&larr;</a> 
		<input type=text name=yyyy size=4 maxlength=4 class=w4 value="{}" id=y onchange="hlCurDate()">
		<input type=text name=mm size=2 maxlength=2 class=w2 value="{}" id=m onchange="hlCurDate()">
		<input type=text name=dd size=2 maxlength=2 class=w2 value="{}" id=d onchange="hlCurDate()">
		<a class=arr href="javascript:chgDate(+1)" title="day after">&rarr;</a>
		</td>
		<td class=dr><input type=text size=12 class=w12 name=dr value="{}"></td>
		<td class=cr><input type=text size=12 class=w12 name=cr value="{}"></td>
		<td class=bal><input type=text size=12 class=w12 name=newbal value="{}"></td>
		<td class=opp>
		<input type=hidden name=aid value="{}">
		<select name=oaid>
		<option value="-1">&nbsp;</option>
		""".format(yyyy,mm,dd,v(err,"dr"),v(err,"cr"),v(err,"newbal"),aid)
		for atc,atn in atypes:
			r+="""
			<optgroup label="{}">
			""".format(atn)
			crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
			opts=crs.fetchall()
			for oaid,oaname in opts:
				sel="selected" if oaid==v(err,"oaid") else ""
				r+="""
				<option value="{}" {}>{}</option>
				""".format(oaid,sel,oaname)
			if len(opts)==0:
				r+="""
				<option>&nbsp;</option>
				"""
			r+="""
			</optgroup>
			"""
		r+="""
		</select>
		</td>
		<td class=comm>
		<input type=text name=comment size=20 class=comm maxlength=255 value="{}">
		<input type=submit value=Insert>
		</td>
		</tr>
		</table>
		</form>
		""".format(v(err,"comment"))
	# Show error message
	if err is not None:
		r+="""
		<div class=center><span class=err>{}</span></div>
		""".format(err["msg"])
	# Close form area
	r+="""
	</div>
	"""
	# Past transactions
	r+="""
	<table class=full>
	"""
	prev_year=None
	prev_month=None
	crs.execute("SELECT * FROM xacts WHERE aid=? AND ?<=dt AND dt<=? ORDER BY xid DESC",[aid,sdt,edt])
	for (xid,dt,aid,oaid,dr,cr,x_bal,comment) in crs.fetchall():
		dt_d=date.fromordinal(dt)
		dr=int2cur(int(dr)) if dr!="0" else ""
		cr=int2cur(int(cr)) if cr!="0" else ""
		x_bal=int2cur(int(x_bal))
		x_year=dt_d.year
		x_month=dt_d.month
		if prev_year is None and prev_month is None:
			sep_class=""
		elif x_year!=prev_year:
			sep_class="sep_year"
		elif x_month!=prev_month:
			sep_class="sep_month"
		else:
			sep_class="sep"
		hl_class="hl" if xid==hlxid else ""
		anchor="<a id=hl></a>" if xid==hlxid else ""
		prev_year=x_year
		prev_month=x_month
		crs.execute("SELECT type,name FROM accts WHERE aid=?",[oaid])
		oatype,oaname=crs.fetchone()
		r+="""
		<tr class="line {} {}">
		<td class=date>{}</td>
		<td class=dr>{}</td>
		<td class=cr>{}</td>
		<td class=bal>{}</td>
		<td class=opp><span class=atype>{}</span>&nbsp;<a href="acct?aid={}&amp;hlxid={}#hl">{}</a></td>
		<td class=comm>&nbsp;<small>{}</small>{}</td>
		<td class=x>
		""".format(sep_class,hl_class,dt_d,dr,cr,x_bal,oatype,oaid,xid,oaname,comment,anchor)
		# We can delete the transaction if it is the last one for both aid and oaid
		if xid==maxxid:
			crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[oaid])
			if xid==res(crs):
				r+="""
				<a class=x
				href="del_xact?xid={}&amp;aid={}"
				onClick="return confirmDeleteTransaction()"
				title="delete transaction">
				&times;
				</a>
				""".format(xid,aid)
		r+="""
		</td>
		</tr>
		"""
	r+="""
	</table>
	"""
	# Close the account
	if bal==0 and cdt==0:
		r+="""
		<hr>
		<div class="center form">
		<form action=close_acct method=post>
		<input type=hidden name=aid value="{}">
		<input type=submit value="Close account" onClick="return confirmCloseAccount(\'{}\')">
		</form>
		</div>
		""".format(aid,aname)
	# Cellar
	r+="""
	</body>
	</html>
	"""
	# Return success
	c="200 OK"
	h=[("Content-type","text/html")]
	return c,r,h

def ins_xact(crs,environ):
	"""insert a new transaction"""
	# Get arguments
	try:
		qs=environ["wsgi.input"].readline().decode()
		q=parse_qs(qs,keep_blank_values=True)
		yyyy=q["yyyy"][0]
		mm=q["mm"][0]
		dd=q["dd"][0]
		dr=q["dr"][0]
		cr=q["cr"][0]
		newbal=q["newbal"][0]
		aid=q["aid"][0]
		oaid=q["oaid"][0]
		comment=escape(q["comment"][0])
	except KeyError:
		raise ValueError("Wrong access")
	# Check accounts
	try:
		aid=int(aid)
	except ValueError:
		raise ValueError("Bad aid")
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[aid])
	if res(crs)==0:
		raise ValueError("Non-existent aid")
	try:
		oaid=int(oaid)
	except ValueError:
		raise ValueError("Bad oaid")
	crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[oaid])
	if res(crs)==0 and oaid!=-1:
		raise ValueError("Non-existent oaid")
	# Validate user input
	try:
		if oaid==-1:
			raise BadInput("Please select the opposing account")
		if aid==oaid:
			raise BadInput("Transaction with the same account")
		# Check date
		try:
			dt=date(int(yyyy),int(mm),int(dd)).toordinal()
		except ValueError:
			raise BadInput("Bad date")
		# Check transaction values
		if dr=="":
			dr="0"
		try:
			dr=cur2int(arith(dr))
		except ValueError:
			raise BadInput("Bad Dr")
		if cr=="":
			cr="0"
		try:
			cr=cur2int(arith(cr))
		except ValueError:
			raise BadInput("Bad Cr")
		if dr<0:
			raise BadInput("Dr cannot be negative")
		if cr<0:
			raise BadInput("Cr cannot be negative")
		if dr!=0 and cr!=0:
			raise BadInput("Dr and Cr cannot both be set")
		if (dr!=0 or cr!=0) and newbal!="":
			raise BadInput("Dr or Cr and Balance cannot all be set")
		if dr==0 and cr==0:
			if newbal=="":
				raise BadInput("Set one of Dr, Cr, or Balance")
			try:
				newbal=cur2int(arith(newbal))
			except ValueError:
				raise BadInput("Bad Balance")
		# Check dates
		if dt>date.today().toordinal():
			raise BadInput("Date cannot be in the future")
		crs.execute("SELECT odt FROM accts WHERE aid=?",[aid])
		if dt<res(crs):
			raise BadInput("Date before the account's opening date")
		crs.execute("SELECT odt FROM accts WHERE aid=?",[oaid])
		if dt<res(crs):
			raise BadInput("Date before the opposing account's opening date")
		crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=? AND dt>?",[aid,dt])
		if res(crs)!=0:
			raise BadInput("Current account has newer transactions")
		crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=? AND dt>?",[oaid,dt])
		if res(crs)!=0:
			raise BadInput("Opposing account has newer transactions")
	except BadInput as e:
		# Fill error data
		err=dict()
		err["msg"]=str(e)
		err["yyyy"]=q["yyyy"][0]
		err["mm"]=q["mm"][0]
		err["dd"]=q["dd"][0]
		err["dr"]=q["dr"][0]
		err["cr"]=q["cr"][0]
		err["newbal"]=q["newbal"][0]
		err["aid"]=q["aid"][0]
		err["oaid"]=int(q["oaid"][0])
		err["comment"]=escape(q["comment"][0])
		# Return
		return acct(crs,"aid={}".format(aid),err)
	# Input data OK, prepare to insert transaction
	# Get account types
	crs.execute("SELECT type FROM accts WHERE aid=?",[aid])
	atype=res(crs)
	crs.execute("SELECT type FROM accts WHERE aid=?",[oaid])
	oatype=res(crs)
	# Get account balances
	bal=balance(crs,aid)
	obal=balance(crs,oaid)
	if dr==0 and cr==0:
		# Derive dr and cr from new and old balances
		if atype in ("E","L","i"):
			if newbal>bal:
				cr=newbal-bal
			else:
				dr=bal-newbal
		elif atype in ("A","e"):
			if newbal>bal:
				dr=newbal-bal
			else:
				cr=bal-newbal
		else:
			raise ValueError("Bad account type")
	else:
		newbal=new_balance(atype,bal,dr,cr)
	# Compute new balance of the opposing account, with dr and cr exchanged
	onewbal=new_balance(oatype,obal,cr,dr)
	# Insert transaction
	crs.execute("SELECT MAX(xid) FROM xacts")
	maxxid=res(crs)
	if maxxid is None:
		xid=0
	else:
		xid=maxxid+1
	crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,aid,oaid,str(dr),str(cr),str(newbal),comment])
	crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,oaid,aid,str(cr),str(dr),str(onewbal),comment])
	# Return
	return acct(crs,"aid={}".format(aid))

def del_xact(crs,qs):
	"""delete transaction"""
	# Get arguments
	q=parse_qs(qs)
	try:
		xid=q["xid"][0]
		aid=q["aid"][0]
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
	oaid=res(crs)
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
	# Return
	return acct(crs,"aid={}".format(aid))

def creat_acct(crs,environ):
	"""create a new account"""
	# Get arguments
	qs=environ["wsgi.input"].readline().decode()
	q=parse_qs(qs,keep_blank_values=True)
	try:
		atype=q["atype"][0]
		aname=escape(q["aname"][0])
	except KeyError:
		raise ValueError("Wrong access")
	# Check argument
	if not atype in [x for x,_ in atypes]+[""]:
		raise ValueError("Wrong account type")
	# Validate user input
	try:
		if atype=="":
			raise BadInput("Please select the account type")
		if aname=="":
			raise BadInput("Please set the account name")
		crs.execute("SELECT COUNT(*) FROM accts WHERE name=?",[aname])
		if res(crs)!=0:
			raise BadInput("Account with the same name already exists")
	except BadInput as e:
		# Fill error data
		err=dict()
		err["msg"]=str(e)
		err["atype"]=atype
		err["aname"]=aname
		# Return
		return main(crs,err)
	except:
		# Re-raise other exceptions
		raise
	# Create account
	odt=date.today().toordinal()
	crs.execute("INSERT INTO accts VALUES (NULL,?,?,?,0)",[atype,aname,odt])
	# Return
	return main(crs)

def close_acct(crs,environ):
	"""close account"""
	# Get argument
	qs=environ["wsgi.input"].readline().decode()
	q=parse_qs(qs)
	try:
		aid=q["aid"][0]
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
	now=date.today().toordinal()
	crs.execute("UPDATE accts SET cdt=? WHERE aid=?",[now,aid])
	# Return
	return acct(crs,"aid={}".format(aid))
