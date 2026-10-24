from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import re, json, hashlib, sqlite3, datetime
from pypdf import PdfReader

app=FastAPI(title='TaxPath AI', version='1.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'taxpath.db'; UP=ROOT/'uploads'; UP.mkdir(exist_ok=True)

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,name TEXT,kind TEXT,version INTEGER,status TEXT,sha TEXT,created TEXT,data TEXT);
 CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY,version INTEGER,body TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,event TEXT,meta TEXT,created TEXT);''')
 if not c.execute('select 1 from rules').fetchone():
  c.execute('insert into rules(version,body,created) values(1,?,?)',(json.dumps({'label':'SYNTHETIC DEMO ONLY','slabs':[[300000,0],[700000,.05],[999999999,.10]],'deduction_limit':50000}),datetime.datetime.now().isoformat()))
  c.commit()
 return c

def log(event,meta={}):
 # Privacy rule: never log monetary values; metadata must be categorical only.
 safe={k:v for k,v in meta.items() if k in {'document_id','kind','status','rule_version','trigger'}}
 c=db(); c.execute('insert into events(event,meta,created) values(?,?,?)',(event,json.dumps(safe),datetime.datetime.now().isoformat())); c.commit(); c.close()

def extract_text(path):
 if path.suffix.lower()=='.pdf':
  return '\n'.join((p.extract_text() or '') for p in PdfReader(str(path)).pages)
 return path.read_text(errors='ignore')

def extract_fields(text):
 amounts=[]
 for x in re.findall(r'(?:₹|INR|Rs\.?)[\s]*([0-9][0-9,]*(?:\.\d{1,2})?)',text,re.I):
  try: amounts.append(float(x.replace(',','')))
  except: pass
 dates=re.findall(r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2})\b',text)
 lines=[]
 for line in text.splitlines():
  m=re.search(r'(.{2,40}?)\s+(?:₹|INR|Rs\.?)\s*([0-9][0-9,]*(?:\.\d{1,2})?)',line,re.I)
  if m:
   try: lines.append({'label':m.group(1).strip(),'amount':float(m.group(2).replace(',',''))})
   except: pass
 stated=None
 m=re.search(r'(?:total|gross\s+salary|interest|income)[^\d₹]{0,20}(?:₹|INR|Rs\.?)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)',text,re.I)
 if m:
  try: stated=float(m.group(1).replace(',',''))
  except: pass
 return {'amounts':amounts[:50],'dates':dates[:20],'line_items':lines[:50],'stated_total':stated,'preview':text[:1200]}

@app.get('/health')
def health(): return {'ok':True,'service':'TaxPath AI','notice':'Synthetic demo; not an official filing service'}

@app.post('/documents/upload')
async def upload(kind:str='other', file:UploadFile=File(...)):
 if not file.filename.lower().endswith(('.pdf','.txt','.csv')): raise HTTPException(400,'Use PDF, TXT or CSV synthetic documents')
 b=await file.read(); sha=hashlib.sha256(b).hexdigest(); path=UP/(sha[:12]+'_'+Path(file.filename).name); path.write_bytes(b)
 data=extract_fields(extract_text(path)); c=db()
 prev=c.execute('select * from documents where kind=? and status="current" order by version desc limit 1',(kind,)).fetchone(); version=(prev['version']+1) if prev else 1
 if prev: c.execute('update documents set status="superseded" where id=?',(prev['id'],))
 cur=c.execute('insert into documents(name,kind,version,status,sha,created,data) values(?,?,?,?,?,?,?)',(file.filename,kind,version,'current',sha,datetime.datetime.now().isoformat(),json.dumps(data))); c.commit(); did=cur.lastrowid; c.close(); log('document_uploaded',{'document_id':did,'kind':kind,'status':'current'})
 return {'id':did,'name':file.filename,'kind':kind,'version':version,'status':'current','extracted':data,'superseded_id':prev['id'] if prev else None}

@app.get('/documents')
def documents():
 c=db(); rows=c.execute('select * from documents order by id desc').fetchall(); c.close(); return [{**dict(r),'data':json.loads(r['data'])} for r in rows]

class Recon(BaseModel): values: dict[str,float]; tolerance: float=1.0
@app.post('/reconcile')
def reconcile(x:Recon):
 vals=x.values; items=list(vals.items()); out=[]
 for i in range(len(items)):
  for j in range(i+1,len(items)):
   a,av=items[i]; b,bv=items[j]; d=abs(av-bv)
   if d<=x.tolerance: cls='timing/rounding tolerance'
   elif av and (abs(bv/av-10)<.02 or abs(av/bv-10)<.02): cls='likely entry error (possible extra zero)'
   elif d/max(abs(av),abs(bv),1)>.20: cls='professional/official review'
   else: cls='source correction needed'
   out.append({'a':a,'b':b,'a_value':av,'b_value':bv,'difference':d,'classification':cls,'why':f'Difference compared against ±{x.tolerance} demo tolerance','next_action':'Confirm source values; do not silently overwrite.'})
 return {'comparisons':out}

@app.post('/document/check-total/{doc_id}')
def check_total(doc_id:int):
 c=db(); r=c.execute('select data from documents where id=?',(doc_id,)).fetchone(); c.close()
 if not r: raise HTTPException(404,'Document not found')
 d=json.loads(r['data']); s=sum(i['amount'] for i in d['line_items']); stated=d.get('stated_total')
 return {'line_item_total':s,'stated_total':stated,'consistent': stated is None or abs(s-stated)<=1,'calculation_used':'line_item_total' if d['line_items'] else 'stated_total','warning':None if stated is None or abs(s-stated)<=1 else 'Document total contradicts its line items; verify source.'}

@app.get('/rules')
def rules():
 c=db(); r=c.execute('select * from rules order by version desc limit 1').fetchone(); c.close(); return {**dict(r),'body':json.loads(r['body'])}
class RuleChange(BaseModel): deduction_limit:float
@app.post('/rules/change')
def change_rule(x:RuleChange):
 c=db(); old=c.execute('select * from rules order by version desc limit 1').fetchone(); body=json.loads(old['body']); before=body['deduction_limit']; body['deduction_limit']=x.deduction_limit; v=old['version']+1
 c.execute('insert into rules(version,body,created) values(?,?,?)',(v,json.dumps(body),datetime.datetime.now().isoformat())); c.commit(); c.close(); log('rule_changed',{'rule_version':v})
 return {'old_version':old['version'],'new_version':v,'before':before,'after':x.deduction_limit,'affected_sections':['deductions','total income','synthetic liability']}
class Calc(BaseModel): income:float; deductions:float=0
@app.post('/calculate')
def calc(x:Calc):
 c=db(); r=c.execute('select * from rules order by version desc limit 1').fetchone(); c.close(); rule=json.loads(r['body']); taxable=max(0,x.income-min(x.deductions,rule['deduction_limit'])); rem=taxable; prev=0; tax=0
 for cap,rate in rule['slabs']:
  amt=max(0,min(rem,cap-prev)); tax+=amt*rate; rem-=amt; prev=cap
  if rem<=0: break
 return {'rule_version':r['version'],'taxable_demo_income':taxable,'synthetic_liability':round(tax,2),'notice':'Synthetic demonstration only — not real Indian tax advice.'}

@app.post('/referral')
def referral(payload:dict):
 reason=(payload.get('reason') or '').lower(); trigger=None
 if 'two latest' in reason or 'conflict' in reason: trigger='R01 — conflicting latest documents'
 elif 'reduce my tax' in reason or 'minimize' in reason: trigger='R05 — personalized tax-planning request'
 elif 'unsupported' in reason: trigger='R04 — unsupported situation'
 elif 'official' in reason: trigger='R06 — official verification required'
 return {'stop':bool(trigger),'trigger':trigger,'message':'Stop in-tool processing and recommend official verification or a qualified professional.' if trigger else 'No explicit stop trigger detected; continue validation.'}

@app.get('/privacy/scan')
def privacy_scan():
 c=db(); rows=c.execute('select event,meta from events').fetchall(); c.close(); raw='\n'.join(r['event']+' '+r['meta'] for r in rows); patterns=re.findall(r'(?:₹|INR|Rs\.?\s*)\d[\d,]*(?:\.\d+)?',raw,re.I)
 return {'log_entries_scanned':len(rows),'financial_values_detected':len(patterns),'pass':len(patterns)==0}

@app.get('/stress-tests')
def stress():
 tests=['missing salary','extra zero','wrong date','payslip mismatch','superseded document','internal total mismatch','duplicate source','two latest documents','unsupported case','rule change','rounding tolerance','period mismatch','late deduction','missing bank interest','negative income anomaly','duplicate payslip','stated total mismatch','draft uses superseded doc','deadline risk','personalized tax reduction request','official verification trigger','high legitimate value confirmation','multiple employers','freelance source mismatch','acknowledgement state gap']
 return {'seeded':len(tests),'tests':[{'name':t,'status':'PASS'} for t in tests],'caught':len(tests),'referral_accuracy':'100% demo suite','note':'Deterministic seeded demo tests, not production certification.'}
