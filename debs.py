"""
Double-entry Bookkeeping System
Copyright (c) 2020 Alexander Mukhin
MIT License
"""

from urllib.parse import parse_qs
from datetime import date
from html import escape
import os
import sys
try:
    from pysqlcipher3 import dbapi2 as sqlite3
except:
    import sqlite3
from math import ceil

thousand_sep=" "
decimal_sep=","
limit=100

style="""
div.center { text-align: center; }
div.indent { margin-left: 5ch; }
form.inline { display: inline; }
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
th.date,td.date { width: 15%; text-align: left; }
th.dr,td.dr { width: 10%; text-align: right; }
th.cr,td.cr { width: 10%; text-align: right; }
th.bal,td.bal { width: 15%; text-align: right; }
th.opp,td.opp { width: 20%; text-align: right; }
th.comm,td.comm { text-align: center; }
tr.line { white-space: nowrap; }
tr.sep td { border-top: 2px solid #f0f0f0; }
tr.sep_month td { border-top: 2px solid #c0c0c0; }
tr.sep_year td { border-top: 2px solid #808080; }
tr.sep_tot td { border-top: 2px solid #c0c0c0; }
"""

# database key
dbkey=None

class BadInput(Exception):
    """invalid user input"""
    pass

class BadDBKey(Exception):
    """bad database key"""
    pass

def application(environ,start_response):
    """entry point"""
    # global database key
    global dbkey
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
            raise sqlite3.Error("no file given")
        if not os.path.exists(db):
            raise sqlite3.Error("file does not exist")
        cnx=sqlite3.connect(db)
        cnx.isolation_level=None # we manage transactions explicitly
        crs=cnx.cursor()
        # deal with database key
        p=environ["PATH_INFO"]
        if "pysqlcipher3" in sys.modules:
            if p=="/ask_dbkey":
                # ask for a database key
                c,r,h=ask_dbkey()
                raise BadDBKey
            if p=="/set_dbkey":
                # set global database key
                dbkey=get_dbkey(environ)
                # try to show the main page with the new key
                c,r,h="303 See Other","",[("Location",".")]
                raise BadDBKey
            if p=="/clr_dbkey":
                # clear database key
                dbkey=None
                # redirect to ask key
                c,r,h="303 See Other","",[("Location","ask_dbkey")]
                raise BadDBKey
            if not valid_dbkey(crs,dbkey):
                # key is bad, ask for key
                c,r,h="303 See Other","",[("Location","ask_dbkey")]
                raise BadDBKey
        # main selector
        qs=environ.get("QUERY_STRING")
        crs.execute("BEGIN") # execute each request in a transaction
        with cnx:
            if p=="/":
                c,r,h=main(crs)
            elif p=="/acct":
                c,r,h=acct(crs,qs)
            elif p=="/ins_xact":
                c,r,h=ins_xact(crs,environ)
            elif p=="/del_xact":
                c,r,h=del_xact(crs,environ)
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
    except BadDBKey:
        pass
    if cnx:
        cnx.close()
    h+=[("Cache-Control","max-age=0")]
    start_response(c,h)
    return [r.encode()]

def ask_dbkey():
    """ask for a database key"""
    r="""
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
    c="200 OK"
    h=[("Content-type","text/html")]
    return c,r,h

def get_dbkey(environ):
    """get a database key submitted in a POST query"""
    q=parse_qs(environ["wsgi.input"].readline().decode())
    try:
        # get argument
        k=q["dbkey"][0]
        # sanitize: drop everything except hexadecimal digits
        return ''.join(filter(lambda x: x in "0123456789abcdefABCDEF",k))
    except:
        return None

def valid_dbkey(crs,key):
    """check the key"""
    try:
        if key is not None:
            crs.execute("PRAGMA key=\"x'{}'\"".format(key))
        crs.execute("SELECT COUNT(*) FROM sqlite_master")
    except sqlite3.Error as e:
        return False
    return True

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
    """return the current balance of account aid"""
    crs.execute("SELECT max(xid) FROM xacts WHERE aid=?",[aid])
    maxxid=res(crs)
    if maxxid is not None:
        crs.execute("SELECT bal FROM xacts WHERE xid=? and aid=?",[maxxid,aid])
        return int(res(crs))
    else:
        return 0

def new_balance(atype,bal,dr,cr):
    """compute the new balance after transaction"""
    if atype in ("E","L","i"):
        return bal+cr-dr
    elif atype in ("A","e"):
        return bal+dr-cr
    else:
        raise ValueError("Bad account type")

def v(kv,k):
    """return the value of key or empty string"""
    try:
        return kv[k]
    except:
        return ""

def main(crs,err=None):
    """show main page"""
    # header
    r="""
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
    """.format(style)
    # body
    r+="""
    <body>
    """
    # accounts
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
    # verify accounting equation
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
    # new account
    r+="""
    <hr>
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
    # show error message
    if err is not None:
        r+="""
        <span class=err>{}</span>
        """.format(err["msg"])
    # closed accounts
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
    # show clear key link
    if dbkey is not None:
        r+="""
        <hr>
        <a href="clr_dbkey">Close session</a>
        """
    # cellar
    r+="""
    </body>
    </html>
    """
    # return success
    c="200 OK"
    h=[("Content-type","text/html")]
    return c,r,h

def acct(crs,qs,err=None):
    """show account statement page"""
    # get arguments
    q=parse_qs(qs,keep_blank_values=True)
    # get and check aid
    try:
        aid=q["aid"][0]
    except KeyError:
        raise ValueError("Wrong access")
    crs.execute("SELECT COUNT(*) FROM accts WHERE aid=?",[aid])
    if res(crs)==0:
        raise ValueError("Bad aid")
    # get and check the page number
    crs.execute("SELECT COUNT(*) FROM xacts WHERE aid=?",[aid])
    lastpage=ceil(res(crs)/limit)
    if lastpage==0:
        lastpage=1
    try:
        page=int(q["page"][0])
        if page<1 or page>lastpage:
            raise
    except:
        page=1
    # get commonly used account properties
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
    # header
    r="""
    <!DOCTYPE html>
    <html lang="en">
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
    </script>
    <title>Double-entry Bookkeeping System</title>
    </head>
    """
    # body
    r+="""
    <body>
    <div class=center>
    <h2>{}</h2>
    </div>
    <a href=".">Back to list</a>
    <hr>
    """.format(aname)
    # transactions
    r+="""
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
        yyyy=d.year if err is None else err["yyyy"]
        mm=d.month if err is None else err["mm"]
        dd=d.day if err is None else err["dd"]
        r+="""
        <tr class=line><td colspan=6>
        <form action=ins_xact method=post>
        <table class=full>
        <tr class=line>
        <td class=date>
        <input type=text name=yyyy size=4 maxlength=4 class=w4 value="{}">
        <input type=text name=mm size=2 maxlength=2 class=w2 value="{}">
        <input type=text name=dd size=2 maxlength=2 class=w2 value="{}">
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
        </td></tr>
        """.format(v(err,"comment"))
    # show error message
    if err is not None:
        r+="""
        <tr class=line><td colspan=6>
        <div class=center><span class=err>{}</span></div>
        </td></tr>
        """.format(err["msg"])
    # past transactions
    prev_year=None
    prev_month=None
    crs.execute("SELECT * FROM xacts WHERE aid=? ORDER BY xid DESC LIMIT ? OFFSET ?",[aid,limit,(page-1)*limit])
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
        crs.execute("SELECT type,name FROM accts WHERE aid=?",[oaid])
        oatype,oaname=crs.fetchone()
        r+="""
        <tr class="line {}">
        <td class=date>{}</td>
        <td class=dr>{}</td>
        <td class=cr>{}</td>
        <td class=bal>{}</td>
        <td class=opp><span class=atype>{}</span>&nbsp;{}</td>
        <td class=comm>&nbsp;<small>{}</small>
        """.format(sep_class,dt_d,dr,cr,x_bal,oatype,oaname,comment)
        # we can delete the transaction if it is the last one for both aid and oaid
        if xid==maxxid:
            crs.execute("SELECT MAX(xid) FROM xacts WHERE aid=?",[oaid])
            if xid==res(crs):
                r+="""
                <form class=inline action=del_xact method=post>
                <input type=hidden name=xid value="{}">
                <input type=hidden name=aid value="{}">
                <input type=submit value="Delete" onClick="return confirmDeleteTransaction()">
                </form>
                """.format(xid,aid)
        r+="""
        </td>
        </tr>
        """
    r+="""
    </table>
    """
    # links to pages
    r+="""
    <hr>
    Page
    """
    for p in range(1,lastpage+1):
        if p!=page:
            r+="""
            <a href="acct?aid={}&amp;page={}">{}</a>&nbsp;
            """.format(aid,p,p)
        else:
            r+="""
            {}&nbsp;
            """.format(p)
    # close the account
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
    # cellar
    r+="""
    </body>
    </html>
    """
    # return success
    c="200 OK"
    h=[("Content-type","text/html")]
    return c,r,h

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
    except KeyError:
        raise ValueError("Wrong access")
    # check accounts
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
    # validate user input
    try:
        if oaid==-1:
            raise BadInput("Please select the opposing account")
        if aid==oaid:
            raise BadInput("Transaction with the same account")
        # check date
        try:
            dt=date(int(yyyy),int(mm),int(dd)).toordinal()
        except ValueError:
            raise BadInput("Bad date")
        # check transaction values
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
    except BadInput as e:
        # fill error data
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
        # return
        return acct(crs,"aid={}".format(aid),err)
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
    crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,aid,oaid,str(dr),str(cr),str(newbal),comment])
    crs.execute("INSERT INTO xacts VALUES(?,?,?,?,?,?,?,?)",[xid,dt,oaid,aid,str(cr),str(dr),str(onewbal),comment])
    # return
    return acct(crs,"aid={}".format(aid))

def del_xact(crs,environ):
    """delete transaction"""
    # get arguments
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs)
    try:
        xid=q["xid"][0]
        aid=q["aid"][0]
    except KeyError:
        raise ValueError("Wrong access")
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
    # return
    return acct(crs,"aid={}".format(aid))

def creat_acct(crs,environ):
    """create a new account"""
    # get arguments
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs,keep_blank_values=True)
    try:
        atype=q["atype"][0]
        aname=escape(q["aname"][0])
    except KeyError:
        raise ValueError("Wrong access")
    # check argument
    if not atype in [x for x,_ in atypes]+[""]:
        raise ValueError("Wrong account type")
    # validate user input
    try:
        if atype=="":
            raise BadInput("Please select the account type")
        if aname=="":
            raise BadInput("Please set the account name")
        crs.execute("SELECT COUNT(*) FROM accts WHERE name=?",[aname])
        if res(crs)!=0:
            raise BadInput("Account with the same name already exists")
    except BadInput as e:
        # fill error data
        err=dict()
        err["msg"]=str(e)
        err["atype"]=atype
        err["aname"]=aname
        # return
        return main(crs,err)
    except:
        # re-raise other exceptions
        raise
    # create account
    odt=date.today().toordinal()
    crs.execute("INSERT INTO accts VALUES (NULL,?,?,?,0)",[atype,aname,odt])
    # return
    return main(crs)

def close_acct(crs,environ):
    """close account"""
    # get argument
    qs=environ["wsgi.input"].readline().decode()
    q=parse_qs(qs)
    try:
        aid=q["aid"][0]
    except KeyError:
        raise ValueError("Wrong access")
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
    # return
    return acct(crs,"aid={}".format(aid))
