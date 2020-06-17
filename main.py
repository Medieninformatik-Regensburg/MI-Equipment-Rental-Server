#!/usr/bin/env python3

from fastapi import FastAPI
from pydantic import BaseModel
from pydantic import BaseSettings
from datetime import date, datetime
from dokuwiki import DokuWiki, DokuWikiError, Dataentry
from typing import Dict, List
from typing import Optional
import ldap


class Settings(BaseSettings):
    app_name: str = "MI Rental"
    admin_email: str = "raphael.wimmer@ur.de"
    wiki_server: str = "https://wiki.mi.ur.de"
    wiki_path: str = "lab:ausstattung:"
    wiki_user: str 
    wiki_pw: str
    ldap_server: str = "ldaps://ldapauth2.uni-regensburg.de:636"
    ldap_base_dn: str = "o=uni-regensburg,c=de"
    ldap_scope: int = ldap.SCOPE_SUBTREE
    groups_with_edit_rights: List[str] = ["mi-staff.mi.sprachlit.uni-regensburg.de", "mi-shk.mi.sprachlit.uni-regensburg.de"] 



settings = Settings()
app = FastAPI()
dw = DokuWiki(settings.wiki_server, settings.wiki_user, settings.wiki_pw, cookieAuth=True)
l = ldap.initialize(settings.ldap_server)

last_checked_ts = None
cache = {}

class Item(BaseModel):
    uid : Optional[int]
    typ : Optional[List[str]]
    name: Optional[str]
    standort: Optional[str]
    os: Optional[str]
    zubehoer: Optional[str]
    seriennummern: Optional[str]
    status: Optional[str]
    ausleiher: Optional[str]
    von: Optional[date]
    bis: Optional[date]
    anmerkungen: Optional[str]
    url: Optional[str]

DW_TO_I = {'ID': 'uid', # DW → item
           'Name' : 'name', 
           'Typ_devicetypes': 'typ',
           'Standort': 'standort',
           'OS': 'os',
           'Zubehör': 'zubehoer',
           'Seriennummern': 'seriennummern', 
           'Status_devicestat' : 'status',
           'Ausleiher' : 'ausleiher',
           'Von_dt': 'von',
           'Bis_dt': 'bis',
           'Anmerkungen' : 'anmerkungen'
           }
I_TO_DW = {value: key for key, value in DW_TO_I.items()}


def _dw_to_item(dataentry : Dict[str, str]):
    item_fields = {}
    for k in dataentry.keys():
        try:
            target_field = DW_TO_I[k]
            if dataentry[k] != "":
                item_fields[target_field] = dataentry[k]
            else: 
                item_fields[target_field] = None

        except KeyError:
            pass
    # Special cases
    if 'typ' in item_fields.keys():
        if type(item_fields['typ']) is str:
            item_fields['typ'] = [item_fields['typ']]
    else:
        if 'uid' in item_fields.keys():
            print(f"Item {item_fields['uid']} has no type!")
        else:
            print(f"Item has no type and no id!")
            print(item_fields)
    #print(item_fields)
    item = Item(**item_fields)
    return item

def _item_to_dw(item: Item):
    dataentry = {}
    for k in item.__fields__.keys():
        try:
            target_field = I_TO_DW[k]
            dataentry[target_field] = item.__fields__[k]
        except KeyError:
            pass
    return dataentry

def get_dataentry(uid: int):
    page = settings.wiki_path + f"{uid:03d}"
    if dw.pages.info(page) == {}:
        print(f"ERROR - {page} does not exist. Skipping it.")
        return {}
    content = dw.pages.get(page)
    data = Dataentry.get(content)
    return data

def update_cache(since_ts=None):
    global cache
    if not since_ts: # no cache, retrieve all
        cache = {}
        changed_item_pages = dw.pages.list(settings.wiki_path)
    else:
        changed_pages = dw.pages.changes(last_checked_ts)
        changed_item_pages = []
        for page in changed_pages:
            print(page)
            if page['name'].startswith(settings.wiki_path): # yes, here it is 'name'
                page['id'] = page['name']
                changed_item_pages.append(page)
        print(f"Changed items since last check: {len(changed_item_pages)}")
    for page in changed_item_pages:
        #print(page)
        uid = page['id'].split(":")[-1]
        try:
            uid = int(uid)
        except ValueError:
            print(f"Not an item: {uid} - skipping")
            continue # a page that is not an item
        cache[uid] = get_dataentry(uid)
    print(f"Cache: {len(cache)}")
    return int(datetime.now().timestamp()) # use local timestamps, not utc




@app.on_event("startup")
async def startup_event():
    #update_cache_now() # not for now
    pass




@app.get("/")
def read_root():
    return {"Hello": "World"}

# Debugging
@app.get("/update_cache")
def update_cache_now():
    global last_checked_ts
    last_checked_ts = update_cache(last_checked_ts)
    return {"last checked": last_checked_ts, "cache size": len(cache)}

@app.get("/purge_cache")
def purge_cache():
    global last_checked_ts
    last_checked_ts = update_cache()
    return {"last checked": last_checked_ts, "cache size": len(cache)}


@app.get("/locations")
def read_suggested_locations():
    locations = ["Schwind/Rzayev (PT 3.0.30)", "Böhm/Böhm (PT 3.0.31)", "Brockelmann/Schmidt (PT 3.0.41)", "FIL Besprechungsraum (PT 3.0.28)", "FIL Besprechungsraum (Sideboard)", "FIL Besprechungsraum (Schrank)", "FIL Besprechungsraum (Tresor)", "FIL Usability-Labor (PT 3.0.26)", "FIL Usability-Labor (Laboratories Sideboard)", "FIL Usability-Labor (Extras Sideboard)", "FIL Werkstatt (PT 3.0.27)", "FIL Werkstatt (Schrank unten)", "FIL Werkstatt (Schrank oben)", "FIL Werkstatt (Sideboard)", "Bazo/Kocur (PT 3.0.32)", "TB-Besprechungsraum (TB 1.101)", "TB-Labor (TB VR4)", "TB-Studio (TB VR4)", "TB-Werkstatt (TB VR4)", "Wimmer (TB 1.102)", "Hahn (TB 1.103)", "Bockes (TB 1.104)", "Projekt (TB 1.105)", "Schwappach/Lohmüller (TB 1.106)", "Safe", "anderer Ort", "unbekannt"]
    return locations

@app.get("/statuses")
def read_accepted_statuses():
    statuses = ["defekt", "entliehen", "geblockt", "reserviert", "verbaut", "verfügbar", "verloren"]
    return statuses

@app.get("/types")
def read_accepted_types():
    types = ["Adapter", "Audio", "Beamer", "Display", "Diverse", "Eingabegerät", "Kabel", "Kamera", "Laptop", "PC", "Prototyping", "Sensor", "Smartphone", "Smartwatch", "Software", "Spielkonsole", "Stativ", "Tablet", "Werkzeug"]
    return types


@app.get("/items")
def list_items(item_type = None, location = None, status = None):
    global last_checked_ts
    last_checked_ts = update_cache(last_checked_ts)
    if cache:
        return [_dw_to_item(cache[i]) for i in cache.keys() ]
    else: #dead code
        assert False
        items = []
        for item_id in range(600): # TODO
            dataentry = get_dataentry(item_id)
            item = _dw_to_item(dataentry)
            items.append(item)
        return items

@app.get("/items/{item_id}")
def read_item(item_id: int, purge_cache: bool = False):
    if purge_cache or (item_id not in cache.keys()):
        dataentry = get_dataentry(item_id)
        cache[item_id] = dataentry
    else:
        dataentry = cache[item_id]
    item = _dw_to_item(dataentry)
    print("item generated")
    return item


@app.get("/users/{user_id}")
def read_user_data(user_id: str):
    global l
    query = f"(&(cn={user_id})(objectClass=urrzUser))"
    try:
        results = l.search_ext_s(settings.ldap_base_dn, settings.ldap_scope, query, timeout=5)
    except ldap.TIMEOUT as err:
        return None
    assert len(results) == 1
    result = results[0][1]
    print(result)
    groups = []
    for g in result['groupMembership']:
        groups.append(g.decode('utf-8').replace("cn=", "").replace(",ou=", ".").replace(",o=", ".").replace(",c=", "."))
    allowed = ["read_item", "list_items"]
    if set(settings.groups_with_edit_rights).intersection(set(groups)):  # at least one group matches
        allowed.append("update_item")
    return {"user_id": user_id,
            "name": result['fullName'][0].decode('utf-8'),
            "e-mail": result['mail'][0].decode('utf-8'),
            "groups": groups,
            "allowed": allowed
            }

@app.get("/search")
def read_item(q: str = None):
    if not q:
        q = "TEST"
    return [{"item_id": 123,
            "name": q}]


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_name": item.name, "item_id": item_id}


@app.put("/items/{item_id}/rent")
def rent_item(item_id: int, user_name: str, from_date: date, to_date: date = None, comment: str = None):
    return None


@app.put("/items/{item_id}/return")
def return_item(item_id: int, user_name: str, comment: str = None):
    # item = Item()
    item = {"item_id": item_id, "name": "TEST"}
    return ({"status": "success"}, item)


# @app.put("/items/{item_id}/confirm_existence")
# def confirm_existence(item_id: int, location: str = None):
#     return None


