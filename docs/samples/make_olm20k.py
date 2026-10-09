import random, zipfile
from xml.sax.saxutils import escape, quoteattr
random.seed(7)
P="OPFContactCopy"
first=["Ava","Marcus","Priya","Diego","Hannah","Kwame","Lena","Tomás","Grace","Olu","Zoë","Søren","Amélie","José","Chloé","Mei","Oliver","Fatima","Noah","Inés","Björn","Aisha","Liam","Renée","Yusuf"]
last=["Okafor","Bennett","Nakamura","Silva","Moreau","Lindqvist","Reyes","Adeyemi","Fischer","Park","Ñúñez","Østergård","Müller","García","Dvořák","Chen","Hughes","Al-Sayed","Smith","Łukasz","Jönsson","Brennan","O'Neil","Côté","Kowalski"]
cos=["Northwind Traders","Contoso Ltd","Fabrikam, Inc.","Tailspin Toys","Litware Labs","Café Müller & Söhne","Zürich Fintech AG","Ångström Optics"]
doms=["example.com","mail.example","fabrikam.example","café.example","münchen.example","alumni.example"]
types=["Work","Home","Other"]
def ph(): return f"({random.randint(200,989)}) 555-{random.randint(1000,9999)}"
def asc(s): return s.lower().replace("'","")
notes_pool=['=HYPERLINK("http://example.com","click")','=SUM(A1:A9)','+1 follow up','@channel ping','-adjust','Account ID: {id}',
 'Line one\nLine two\r\nLine three\n<b>Bold</b> &amp; <a href="https://example.com">link</a>, "quoted", commas, here',
 'Met at summit, Q3; prefers email.','Emoji 🙂, 東京, مرحبا, ©®°±','']
long_idx=12345
out=['<?xml version="1.0" encoding="UTF-8"?>\n<contacts>\n']
stats={"multi_email":0,"leading_zero":0,"long_id":0,"formula":0,"messy":0,"sparse":0,"nonascii":0}
for i in range(20000):
    f,l=random.choice(first),random.choice(last)
    fields={}
    sparse=random.random()<0.15
    if sparse:
        stats["sparse"]+=1
        for k,v in [("FirstName",f),("LastName",l),("DisplayName",f"{f} {l}"),("CellPhone",ph()),("BusinessCompany",random.choice(cos))]:
            if random.random()<0.4: fields[k]=v
        if not fields: fields["DisplayName"]=f
    else:
        fields={"FirstName":f,"LastName":l,"DisplayName":f"{f} {l}","CellPhone":ph(),"HomePhone":ph()}
        if random.random()<0.5: fields["HomePhone2"]=ph()
        if random.random()<0.8: fields["BusinessCompany"]=random.choice(cos)
        if random.random()<0.6: fields["Birthday"]=f"19{random.randint(50,99)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}T00:00:00"
    r=random.random()
    if r<0.05: fields["CellPhone"]=f"07{random.randint(100,999)} {random.randint(100000,999999)}"; stats["leading_zero"]+=1
    elif r<0.08: fields["HomePhone2"]=str(random.randint(10**15,10**19)); stats["long_id"]+=1
    roles=["procurement lead","regional pastor","volunteer coordinator","CFO","field engineer","donor relations manager","school principal","IT admin"]
    cities=["Tulsa","São Paulo","Zürich","Lagos","Nairobi","Manila","Kraków","Montréal"]
    base=f"{random.choice(roles).capitalize()} based in {random.choice(cities)}. Prefers {random.choice(['email','calls','text'])}; last spoke {random.randint(1,12)}/{random.randint(1,28)}."
    kind=random.random()
    if kind<0.55: n=base
    elif kind<0.75: n=base+" "+" ".join(random.choice(["Interested in the reading-plan partnership.","Asked for Q4 pricing, follow up.","Introduced by a mutual contact.","Needs invoice copy.","Out of office until next month."]) for _ in range(random.randint(3,12)))
    else: n=random.choice([p for p in notes_pool if p]).replace("{id}",str(random.randint(10**15,10**17)))+("\n"+base if random.random()<0.5 else "")
    if i==long_idx: n=("Long note filler sentence for cell-limit testing. "*800)[:40000]
    if True:
        n=n.replace("{id}",str(random.randint(10**15,10**17)))
        if n[0] in "=+-@": stats["formula"]+=1
        if "\n" in n: stats["messy"]+=1
        fields["NotesPlain"]=n
    br=random.random()
    if br<0.08: fields["BusinessPhone"]="0"+str(random.randint(10**9,10**10-1)); stats["biz_leading_zero"]=stats.get("biz_leading_zero",0)+1
    elif br<0.12: fields["BusinessPhone"]=str(random.randint(10**15,10**19)); stats["biz_long"]=stats.get("biz_long",0)+1
    elif br<0.20: fields["BusinessPhone"]=f"+44 20 {random.randint(1000,9999)} {random.randint(1000,9999)} ext. {random.randint(100,999)}"
    else: fields["BusinessPhone"]=ph()
    if any(ord(c)>127 for c in "".join(fields.values())): stats["nonascii"]+=1
    body="".join(f"    <{P}{k}>{escape(v)}</{P}{k}>\n" for k,v in fields.items())
    ne=0 if sparse and random.random()<0.5 else random.choices([1,2,3],[70,20,10])[0]
    if ne:
        if ne>1: stats["multi_email"]+=1
        body+=f"    <{P}EmailAddressList>\n"
        for t in random.sample(types,ne):
            a=f"{asc(f)}.{asc(l)}{random.randint(1,999)}@{random.choice(doms)}"
            body+=f"      <emailAddress OPFContactEmailAddressAddress={quoteattr(a)} OPFContactEmailAddressName={quoteattr(f+' '+l)} OPFContactEmailAddressType={quoteattr(t)}/>\n"
        body+=f"    </{P}EmailAddressList>\n"
    out.append("  <contact>\n"+body+"  </contact>\n")
out.append("</contacts>\n")
xml="".join(out)
with zipfile.ZipFile("sample.olm","w",zipfile.ZIP_DEFLATED) as z:
    z.writestr("Accounts/test@example.com/Address Book/Contacts.xml",xml)
import collections
print(stats, "xml_bytes",len(xml.encode()))
