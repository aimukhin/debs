"""
Double-entry Bookkeeping System
Copyright (c) 2022 Alexander Mukhin
MIT License
"""

from collections import namedtuple
from urllib.parse import parse_qs
from datetime import date
from html import escape
import os
try:
    from pysqlcipher3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
from math import ceil

THOUSAND_SEP=" "
DECIMAL_SEP=","
LIMIT=100
ATYPES=[("E","Equity"),("A","Assets"),("L","Liabilities"),("i","Income"),("e","Expenses")]
STYLE="""
body { background-color: #fff1e5; }
div.center { text-align: center; }
div.indent { margin-left: 5ch; }
form.inline { display: inline; }
input.comm { width: 75%; }
input.w2 { width: 2ch; }
input.w4 { width: 4ch; }
input.w12 { width: 12ch; }
span.atype { color: #b0b0b0; }
table { border-spacing: 0; }
table td { padding: 2px; }
table.center { margin: auto; }
table.full { width: 100%; }
td.r { text-align: right; }
th.date,td.date { width: 15%; text-align: left; }
th.dr,td.dr { width: 10%; text-align: right; }
th.cr,td.cr { width: 10%; text-align: right; }
th.bal,td.bal { width: 15%; text-align: right; }
th.opp,td.opp { width: 20%; text-align: right; }
th.comm,td.comm { text-align: center; }
tr.line { white-space: nowrap; }
tr.sep td { border-top: 2px solid #e0e0e0; }
tr.sep_month td { border-top: 2px solid #b0b0b0; }
tr.sep_year td { border-top: 2px solid #808080; }
tr.sep_tot td { border-top: 2px solid #b0b0b0; }
"""

# a named tuple for storing HTML response components
HTMLResponse=namedtuple("HTMLResponse",["status","headers","body"])

class BadInput(Exception):
    """invalid user input"""

def application(environ,start_response):
    """entry point"""
    try:
        # connect to the database
        cnx=None
        if "DB" in os.environ:
            # try OS environment
            db=os.environ["DB"]
        elif "DB" in environ:
            # try request environment
            db=environ["DB"]
        else:
            raise sqlite3.Error("No file given")
        if not os.path.exists(db):
            raise sqlite3.Error("File does not exist")
        cnx=sqlite3.connect(db)
        cnx.isolation_level=None # we manage transactions explicitly
        crs=cnx.cursor()
        crs.execute("BEGIN") # execute each request in a transaction
        # main selector
        p=environ["PATH_INFO"]
        qs=environ.get("QUERY_STRING")
        with cnx:
            if p=="/ask_dbkey":
                r=ask_dbkey()
            elif p=="/set_dbkey":
                application.dbkey=get_dbkey(environ)
                r=HTMLResponse("303 See Other",[("Location",".")],"")
            elif p=="/clr_dbkey":
                application.dbkey=None
                r=HTMLResponse("303 See Other",[("Location","ask_dbkey")],"")
            elif not valid_dbkey(crs,application.dbkey):
                r=HTMLResponse("303 See Other",[("Location","ask_dbkey")],"")
            elif p=="/":
                r=main(crs)
            elif p=="/acct":
                r=acct(crs,qs)
            elif p=="/ins_xact":
                r=ins_xact(crs,environ)
            elif p=="/del_xact":
                r=del_xact(crs,environ)
            elif p=="/creat_acct":
                r=creat_acct(crs,environ)
            elif p=="/close_acct":
                r=close_acct(crs,environ)
            else:
                raise ValueError("Wrong access")
    except sqlite3.Error as e:
        r=HTMLResponse("500 Internal Server Error",[("Content-type","text/plain")],"Database error: {}".format(e))
    except ValueError as e:
        r=HTMLResponse("400 Bad Request",[("Content-type","text/plain")],"{}".format(e))
    except KeyError as e:
        r=HTMLResponse("400 Bad Request",[("Content-type","text/plain")],"Parameter expected: {}".format(e))
    except BadInput as e:
        r=HTMLResponse("400 Bad Request",[("Content-type","text/plain")],"Error: {}".format(e))
    if cnx:
        cnx.close()
    start_response(r.status,r.headers+[("Cache-Control","max-age=0")])
    return [r.body.encode()]

# database key
application.dbkey=None

def ask_dbkey():
    """ask for a database key"""
    b="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>Double-entry Bookkeeping System</title>
    </head>
    <body>
    <form action=set_dbkey method=post>
    Key: <input type=password name=dbkey> <input type=submit>
    </form>
    </body>
    </html>
    """
    # return success
    return HTMLResponse("200 OK",[("Content-type","text/html")],b)

def get_dbkey(environ):
    """get a database key submitted in a POST query"""
    q=parse_qs(environ["wsgi.input"].readline().decode())
    try:
        # get argument
        k=q["dbkey"][0]
        # sanitize: drop everything except hexadecimal digits
        return ''.join(filter(lambda x: x in "0123456789abcdefABCDEF",k))
    except KeyError:
        return None

def valid_dbkey(crs,key):
    """check the key"""
    try:
        if key is not None:
            crs.execute("PRAGMA key=\"x'{}'\"".format(key))
        crs.execute("SELECT COUNT(*) FROM sqlite_master")
    except sqlite3.Error:
        return False
    return True

def cur2int(s):
    """convert currency string to integer"""
    s=s.replace(" ","") # drop spaces
    s=s.replace(",",DECIMAL_SEP) # always accept "," as a decimal separator
    s=s.replace(".",DECIMAL_SEP) # always accept "." as a decimal separator
    r=""
    i=0
    for i,c in enumerate(s):
        if c is DECIMAL_SEP:
            break
        r=r+c
    return int(r+s[i+1:i+3].ljust(2,"0"))

def int2cur(v):
    """convert integer to currency string"""
    s=str(abs(v))
    r=""
    for i,c in enumerate(s[::-1].ljust(3,"0"),1):
        if i==3:
            r=DECIMAL_SEP+r
        elif i%3==0:
            r=THOUSAND_SEP+r
        r=c+r
    if v<0:
        r="&minus;"+r
    return r

def res(crs):
    """return the only result of a transaction"""
    return crs.fetchone()[0]

def balance(crs,aid):
    """return the current balance of account aid"""
    crs.execute("SELECT max(xid) FROM xacts WHERE aid=?",[aid])
    maxxid=res(crs)
    if maxxid is not None:
        crs.execute("SELECT bal FROM xacts WHERE xid=? and aid=?",[maxxid,aid])
        return int(res(crs))
    return 0

def new_balance(atype,bal,dr,cr):
    """compute the new balance after transaction"""
    if atype in ("E","L","i"):
        return bal+cr-dr
    if atype in ("A","e"):
        return bal+dr-cr
    raise ValueError("Bad account type")

def main(crs):
    """show main page"""
    # header
    b="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="format-detection" content="telephone=no">
    <style>
    {}
    </style>
    <title>Double-entry Bookkeeping System</title>
    </head>
    """.format(STYLE)
    # body
    b+="""
    <body>
    """
    # accounts
    totals={}
    for atc,atn in ATYPES:
        b+="""
        <strong>{}</strong>
        <div class=indent>
        <table>
        """.format(atn)
        totals[atc]=0
        crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
        for (aid,name) in crs.fetchall():
            bal=balance(crs,aid)
            totals[atc]+=bal
            b+="""
            <tr>
            <td><a href="acct?aid={}">{}</a></td>
            <td class=r>&nbsp; {}</td>
            </tr>
            """.format(aid,name,int2cur(bal))
        b+="""
        <tr class=sep_tot>
        <td>Total</td>
        <td class=r>&nbsp; {}</td>
        </tr>
        <tr><td colspan=2>&nbsp;</td></tr>
        </table>
        </div>
        """.format(int2cur(totals[atc]))
    # verify accounting equation
    d=0
    for atc in ("E","L","i"):
        d+=totals[atc]
    for atc in ("A","e"):
        d-=totals[atc]
    if d!=0:
        raise sqlite3.Error("Accounting equation doesn't hold")
    # new account
    b+="""
    <hr>
    <form action=creat_acct method=post>
    New account &nbsp;
    <select name=atype>
    <option value="">&nbsp;</option>
    """
    for atc,atn in ATYPES:
        b+="""
        <option value="{}">{}</option>
        """.format(atc,atn)
    b+="""
    </select>
    <input type=text name=aname>
    <input type=submit value=Create>
    </form>
    """
    # closed accounts
    b+="""
    <hr>
    <h3>Closed accounts</h3>
    """
    for atc,atn in ATYPES:
        b+="""
        <strong>{}</strong>
        <div class=indent>
        """.format(atn)
        crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt<>0 ORDER BY name",[atc])
        for aid,name in crs:
            b+="""
            <a href="acct?aid={}">{}</a><br>
            """.format(aid,name)
        b+="""
        </div>
        """
    # show clear key link
    if application.dbkey is not None:
        b+="""
        <hr>
        <a href="clr_dbkey">Close session</a>
        """
    # cellar
    b+="""
    </body>
    </html>
    """
    # return success
    return HTMLResponse("200 OK",[("Content-type","text/html")],b)

def acct(crs,qs):
    """show account statement page"""
    # get arguments
    q=parse_qs(qs,keep_blank_values=True)
    # get and check aid
    try:
        aid=q["aid"][0]
    except KeyError as e:
        raise ValueError("Wrong access") from e
    crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
    if res(crs)==0:
        raise ValueError("Bad aid")
    # get and check the page number
    crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=?",[aid])
    lastpage=ceil(res(crs)/LIMIT)
    if lastpage==0:
        lastpage=1
    try:
        page=int(q["page"][0])
        if page<1 or page>lastpage:
            raise ValueError
    except (KeyError,ValueError):
        page=1
    # get commonly used account properties
    crs.execute("SELECT name,cdt FROM accts WHERE aid=?",[aid])
    aname,cdt=crs.fetchone()
    bal=balance(crs,aid)
    crs.execute("SELECT MAX(dt) FROM xacts WHERE aid=?",[aid])
    maxdt=res(crs)
    if maxdt is None:
        maxdt=0
    crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[aid])
    maxxid=res(crs)
    if maxxid is None:
        maxxid=0
    # header
    b="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="format-detection" content="telephone=no">
    <style>
    {}
    </style>
    <title>Double-entry Bookkeeping System</title>
    </head>
    """.format(STYLE)
    # body
    b+="""
    <body>
    <div class=center>
    <h2>{}</h2>
    </div>
    <a href=".">Back to list</a>
    <hr>
    """.format(aname)
    # transactions
    b+="""
    <table class=full>
    <tr class=line>
    <th class=date>Date</th>
    <th class=dr>Dr</th>
    <th class=cr>Cr</th>
    <th class=bal>Balance</th>
    <th class=opp>Opposing account</th>
    <th class=comm>Comment</th>
    </tr>
    """
    # new transaction
    if cdt==0:
        d=date.today()
        yyyy=d.year
        mm=d.month
        dd=d.day
        b+="""
        <tr class=line><td colspan=6>
        <form action=ins_xact method=post>
        <table class=full>
        <tr class=line>
        <td class=date>
        <input type=text name=yyyy size=4 maxlength=4 class=w4 value="{}">
        <input type=text name=mm size=2 maxlength=2 class=w2 value="{}">
        <input type=text name=dd size=2 maxlength=2 class=w2 value="{}">
        </td>
        <td class=dr><input type=text size=12 class=w12 name=dr></td>
        <td class=cr><input type=text size=12 class=w12 name=cr></td>
        <td class=bal><input type=text size=12 class=w12 name=newbal></td>
        <td class=opp>
        <input type=hidden name=aid value="{}">
        <select name=oaid>
        <option value="-1">&nbsp;</option>
        """.format(yyyy,mm,dd,aid)
        for atc,atn in ATYPES:
            b+="""
            <optgroup label="{}">
            """.format(atn)
            crs.execute("SELECT aid,name FROM accts WHERE type=? AND cdt=0 ORDER BY name",[atc])
            opts=crs.fetchall()
            for oaid,oaname in opts:
                b+="""
                <option value="{}">{}</option>
                """.format(oaid,oaname)
            if len(opts)==0:
                b+="""
                <option>&nbsp;</option>
                """
            b+="""
            </optgroup>
            """
        b+="""
        </select>
        </td>
        <td class=comm>
        <input type=text name=comment size=20 class=comm maxlength=255>
        <input type=submit value=Insert>
        </td>
        </tr>
        </table>
        </form>
        </td></tr>
        """
    # past transactions
    prev_year=None
    prev_month=None
    crs.execute("SELECT * FROM xacts WHERE aid=? ORDER BY xid DESC LIMIT ? OFFSET ?",
    [aid,LIMIT,(page-1)*LIMIT])
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
        prev_year=x_year
        prev_month=x_month
        crs.execute("SELECT type,name,cdt FROM accts WHERE aid=?",[oaid])
        oatype,oaname,oacdt=crs.fetchone()
        b+="""
        <tr class="line {}">
        <td class=date>{}</td>
        <td class=dr>{}</td>
        <td class=cr>{}</td>
        <td class=bal>{}</td>
        <td class=opp><span class=atype>{}</span>&nbsp;{}</td>
        <td class=comm>&nbsp;<small>{}</small>
        """.format(sep_class,dt_d,dr,cr,x_bal,oatype,oaname,comment)
        # we can delete the transaction if it is the last one for both aid and oaid
        # and both accounts are still open
        if xid==maxxid and cdt==0 and oacdt==0:
            crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[oaid])
            if xid==res(crs):
                b+="""
                <form class=inline action=del_xact method=post>
                <input type=hidden name=xid value="{}">
                <input type=hidden name=aid value="{}">
                <input type=submit value="Delete">
                </form>
                """.format(xid,aid)
        b+="""
        </td>
        </tr>
        """
    b+="""
    </table>
    """
    # links to pages
    b+="""
    <hr>
    Page
    """
    for p in range(1,lastpage+1):
        if p!=page:
            b+="""
            <a href="acct?aid={0}&amp;page={1}">{1}</a>&nbsp;
            """.format(aid,p)
        else:
            b+="""
            {}&nbsp;
            """.format(p)
    # close the account
    if bal==0 and cdt==0:
        b+="""
        <hr>
        <div class="center form">
        <form action=close_acct method=post>
        <input type=hidden name=aid value="{}">
        <input type=submit value="Close account">
        </form>
        </div>
        """.format(aid)
    # cellar
    b+="""
    </body>
    </html>
    """
    # return success
    return HTMLResponse("200 OK",[("Content-type","text/html")],b)

def ins_xact(crs,environ):
    """insert a new transaction"""
    # get arguments
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
    except KeyError as e:
        raise ValueError("Wrong access") from e
    # check accounts
    try:
        aid=int(aid)
    except ValueError as e:
        raise ValueError("Bad aid") from e
    crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[aid])
    if res(crs)==0:
        raise ValueError("Non-existent aid")
    try:
        oaid=int(oaid)
    except ValueError as e:
        raise ValueError("Bad oaid") from e
    crs.execute("SELECT COUNT(aid) FROM accts WHERE aid=? AND cdt=0",[oaid])
    if res(crs)==0 and oaid!=-1:
        raise ValueError("Non-existent oaid")
    if oaid==-1:
        raise BadInput("Please select the opposing account")
    if aid==oaid:
        raise BadInput("Transaction with the same account")
    # check date
    try:
        dt=date(int(yyyy),int(mm),int(dd)).toordinal()
    except ValueError as e:
        raise BadInput("Bad date") from e
    # check transaction values
    if dr=="":
        dr="0"
    try:
        dr=cur2int(dr)
    except ValueError as e:
        raise BadInput("Bad Dr") from e
    if cr=="":
        cr="0"
    try:
        cr=cur2int(cr)
    except ValueError as e:
        raise BadInput("Bad Cr") from e
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
            newbal=cur2int(newbal)
        except ValueError as e:
            raise BadInput("Bad Balance") from e
    # check dates
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
    # input data OK, prepare to insert transaction
    # get account types
    crs.execute("SELECT type FROM accts WHERE aid=?",[aid])
    atype=res(crs)
    crs.execute("SELECT type FROM accts WHERE aid=?",[oaid])
    oatype=res(crs)
    # get account balances
    bal=balance(crs,aid)
    obal=balance(crs,oaid)
    if dr==0 and cr==0:
        # derive dr and cr from new and old balances
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
    # compute new balance of the opposing account, with dr and cr exchanged
    onewbal=new_balance(oatype,obal,cr,dr)
    # insert transaction
    crs.execute("SELECT MAX(xid) FROM xacts")
    maxxid=res(crs)
    if maxxid is None:
        xid=0
    else:
        xid=maxxid+1
    crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",
    [xid,dt,aid,oaid,str(dr),str(cr),str(newbal),comment])
    crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",
    [xid,dt,oaid,aid,str(cr),str(dr),str(onewbal),comment])
    # return redirect
    return HTMLResponse("303 See Other",[("Location","acct?aid={}".format(aid))],"")

def del_xact(crs,environ):
    """delete transaction"""
    # get arguments
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs)
    try:
        xid=q["xid"][0]
        aid=q["aid"][0]
    except KeyError as e:
        raise ValueError("Wrong access") from e
    # check accounts
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
    # delete transaction
    crs.execute("DELETE FROM xacts WHERE xid=?",[xid])
    # return redirect
    return HTMLResponse("303 See Other",[("Location","acct?aid={}".format(aid))],"")

def creat_acct(crs,environ):
    """create a new account"""
    # get arguments
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs,keep_blank_values=True)
    try:
        atype=q["atype"][0]
        aname=escape(q["aname"][0])
    except KeyError as e:
        raise ValueError("Wrong access") from e
    # check argument
    if not atype in [x for x,_ in ATYPES]+[""]:
        raise ValueError("Wrong account type")
    # validate user input
    if atype=="":
        raise BadInput("Please select the account type")
    if aname=="":
        raise BadInput("Please set the account name")
    crs.execute("SELECT COUNT(*) FROM accts WHERE name=?",[aname])
    if res(crs)!=0:
        raise BadInput("Account with the same name already exists")
    # create account
    odt=date.today().toordinal()
    crs.execute("INSERT INTO accts VALUES (NULL,?,?,?,0)",[atype,aname,odt])
    # return redirect
    return HTMLResponse("303 See Other",[("Location",".")],"")

def close_acct(crs,environ):
    """close account"""
    # get argument
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs)
    try:
        aid=q["aid"][0]
    except KeyError as e:
        raise ValueError("Wrong access") from e
    # check argument
    crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
    if res(crs)==0:
        raise ValueError("Wrong aid")
    crs.execute("SELECT cdt FROM accts WHERE aid=?",[aid])
    if res(crs)!=0:
        raise ValueError("Account already closed")
    if balance(crs,aid)!=0:
        raise ValueError("Non-zero balance")
    # close account
    now=date.today().toordinal()
    crs.execute("UPDATE accts SET cdt=? WHERE aid=?",[now,aid])
    # return redirect
    return HTMLResponse("303 See Other",[("Location","acct?aid={}".format(aid))],"")
