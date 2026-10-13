#!/usr/bin/env python3
"""se_events.py — Salesforce side of /se-notes.

  context  resolve user, SE Events record type, accounts, opps, existing
           coverage and picklists for a window; write them beside --out
  create   validate a plan.json against picklists, create one Event, read it
           back, then create the rest and verify the count

Stdlib only; talks to Salesforce through the `sf` CLI. Org alias comes from
--org, $SE_NOTES_SF_ORG, or the CLI's default target org.
"""
import argparse, csv, json, os, re, subprocess, sys
from datetime import datetime, timedelta

RT_DEVNAME = "FTSEvents"  # "SE Events"
REQUIRED_FIELDS = ["Meeting_Outcome__c", "Event_Location__c", "Primary_Solutions__c",
                   "Product_Tags__c", "Sales_Process_Stage__c", "Type"]
PICKLISTS = ["Type", "Primary_Solutions__c", "Product_Tags__c", "Event_Location__c",
             "Sales_Process_Stage__c", "Meeting_Outcome__c"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def sf(args, org):
    cmd = ["sf", *args, "--json"] + (["-o", org] if org else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        j = json.loads(p.stdout)
    except json.JSONDecodeError:
        die(f"sf {' '.join(args[:3])} returned non-JSON: {p.stderr.strip()[-300:]}")
    if j.get("status", 0) != 0:
        die(f"sf {' '.join(args[:3])}: {j.get('message')}")
    return j.get("result", {})


def query(soql, org):
    return sf(["data", "query", "-q", soql], org).get("records", [])


def resolve_org(arg):
    if arg:
        return arg
    if os.environ.get("SE_NOTES_SF_ORG"):
        return os.environ["SE_NOTES_SF_ORG"]
    return None  # let the CLI use its default target org


def nm(rec, key):
    v = rec.get(key)
    return (v or {}).get("Name", "") if isinstance(v, dict) else (v or "")


def write_tsv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def cmd_context(a):
    for d in (a.since, a.until):
        if not DATE_RE.match(d):
            die(f"dates must be YYYY-MM-DD, got {d!r}")
    org = resolve_org(a.org)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)

    username = sf(["org", "display"], org).get("username")
    if not username:
        die("could not resolve the org's username from `sf org display`")
    esc = username.replace("\\", "\\\\").replace("'", "\\'")
    users = query(f"SELECT Id, Name FROM User WHERE Username = '{esc}'", org)
    if not users:
        die("running user not found in org")
    uid, uname = users[0]["Id"], users[0]["Name"]

    rts = query("SELECT Id FROM RecordType WHERE SobjectType = 'Event' "
                f"AND DeveloperName = '{RT_DEVNAME}'", org)
    if not rts:
        die(f"Event record type {RT_DEVNAME} ('SE Events') not found in this org")
    rt = rts[0]["Id"]

    desc = sf(["sobject", "describe", "-s", "Event"], org)
    fields = {f["name"]: f for f in desc.get("fields", [])}
    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    if missing:
        die(f"Event is missing fields this skill relies on: {', '.join(missing)}")
    picklists = {k: sorted(p["value"] for p in fields[k]["picklistValues"] if p["active"])
                 for k in PICKLISTS}
    json.dump(picklists, open(os.path.join(out_dir, "picklists.json"), "w"), indent=1)

    accts = query("SELECT AccountId, Account.Name FROM AccountTeamMember "
                  f"WHERE UserId = '{uid}'", org)
    acct_ids = sorted({r["AccountId"] for r in accts})
    write_tsv(os.path.join(out_dir, "accounts.tsv"), ["account_name", "account_id"],
              sorted((nm(r, "Account"), r["AccountId"]) for r in accts))

    opps = []
    for i in range(0, len(acct_ids), 150):
        ids = ",".join(f"'{x}'" for x in acct_ids[i:i + 150])
        opps += query("SELECT Id, Name, AccountId, Account.Name, StageName, CloseDate, "
                      f"Owner.Name FROM Opportunity WHERE IsClosed = false AND AccountId IN ({ids})", org)
    write_tsv(os.path.join(out_dir, "opps.tsv"),
              ["opp_id", "account_id", "account_name", "opp_name", "stage", "close", "owner"],
              [(o["Id"], o["AccountId"], nm(o, "Account"), o["Name"], o["StageName"],
                o["CloseDate"], nm(o, "Owner")) for o in opps])

    s, u = a.since, a.until
    existing = []
    for r in query("SELECT Id, ActivityDate, Subject, Account.Name, RecordType.Name FROM Event "
                   f"WHERE OwnerId = '{uid}' AND ActivityDate >= {s} AND ActivityDate <= {u}", org):
        existing.append((r["ActivityDate"], "event-owned", nm(r, "Account"), r["Subject"], r["Id"]))
    for r in query("SELECT Event.Id, Event.ActivityDate, Event.Subject, Event.Account.Name "
                   f"FROM EventRelation WHERE RelationId = '{uid}' "
                   f"AND Event.ActivityDate >= {s} AND Event.ActivityDate <= {u}", org):
        e = r["Event"]
        existing.append((e["ActivityDate"], "event-invited", nm(e, "Account"), e["Subject"], e["Id"]))
    for r in query("SELECT Id, ActivityDate, Subject, Account.Name FROM Task "
                   f"WHERE OwnerId = '{uid}' AND ActivityDate >= {s} AND ActivityDate <= {u}", org):
        existing.append((r["ActivityDate"], "task", nm(r, "Account"), r["Subject"], r["Id"]))
    seen, dedup = set(), []
    for row in sorted(existing):
        if row[4] not in seen:
            seen.add(row[4]); dedup.append(row)
    write_tsv(os.path.join(out_dir, "existing.tsv"),
              ["date", "kind", "account_name", "subject", "id"], dedup)

    ctx = {"org": org, "user_id": uid, "user_name": uname, "record_type_id": rt,
           "since": s, "until": u, "accounts": len(acct_ids), "open_opps": len(opps),
           "existing_in_window": len(dedup), "dir": out_dir}
    json.dump(ctx, open(a.out, "w"), indent=1)
    print(f"{uname}: {len(acct_ids)} accounts, {len(opps)} open opps, "
          f"{len(dedup)} existing entries {s}..{u}. Files in {out_dir}")


def build(ctx, item, opp_stage):
    for k in ("account_id", "type", "start_utc", "minutes", "subject"):
        if not item.get(k):
            raise ValueError(f"missing {k}")
    what = item.get("opp_id") or item["account_id"]
    if not ID_RE.match(what):
        raise ValueError(f"bad Salesforce id {what!r}")
    st = datetime.fromisoformat(item["start_utc"].rstrip("Z"))
    en = st + timedelta(minutes=int(item["minutes"]))
    rec = {"RecordTypeId": ctx["record_type_id"], "OwnerId": ctx["user_id"],
           "Subject": item["subject"][:255], "Type": item["type"],
           "StartDateTime": st.strftime("%Y-%m-%dT%H:%M:00Z"),
           "EndDateTime": en.strftime("%Y-%m-%dT%H:%M:00Z"),
           "WhatId": what, "Event_Location__c": item.get("location") or "Virtual",
           "Meeting_Outcome__c": "Complete", "ShowAs": "Busy",
           "Description": item.get("description", "")[:4000]}
    if item.get("solutions"):
        rec["Primary_Solutions__c"] = item["solutions"]
    if item.get("tags"):
        rec["Product_Tags__c"] = item["tags"]
    if item.get("opp_id") and opp_stage.get(item["opp_id"]):
        rec["Sales_Process_Stage__c"] = opp_stage[item["opp_id"]]
    return rec


def validate(rec, picklists):
    bad = []
    for k in PICKLISTS:
        if k in rec:
            for v in str(rec[k]).split(";"):
                if v not in picklists[k]:
                    bad.append(f"{k}={v!r}")
    return bad


def create_one(rec, org):
    vals = " ".join(f"{k}='{str(v).replace(chr(92), chr(92) * 2).replace(chr(39), chr(92) + chr(39))}'"
                    for k, v in rec.items())
    return sf(["data", "create", "record", "-s", "Event", "-v", vals], org).get("id")


def cmd_create(a):
    ctx = json.load(open(a.context))
    org = ctx.get("org")
    picklists = json.load(open(os.path.join(ctx["dir"], "picklists.json")))
    opp_stage = {}
    with open(os.path.join(ctx["dir"], "opps.tsv")) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            opp_stage[row["opp_id"]] = row["stage"]
    plan = json.load(open(a.plan))
    recs, problems = [], []
    for i, item in enumerate(plan):
        try:
            r = build(ctx, item, opp_stage)
        except ValueError as e:
            problems.append(f"#{i} {item.get('subject', '?')[:40]}: {e}")
            continue
        bad = validate(r, picklists)
        if bad:
            problems.append(f"#{i} {r['Subject'][:40]}: {', '.join(bad)}")
        recs.append(r)
    if problems:
        print("Plan refused — fix these and rerun:")
        print("\n".join("  " + p for p in problems))
        sys.exit(2)
    print(f"Plan OK: {len(recs)} events validated against org picklists.")
    if a.dry_run:
        for r in recs:
            print(f"  {r['StartDateTime'][:10]} | {r['Type']:<18} | {r['Subject'][:70]}")
        return

    results = []
    first = create_one(recs[0], org)
    got = query("SELECT Id, RecordType.DeveloperName, Account.Name, FTS_Request_Number_FTS__c "
                f"FROM Event WHERE Id = '{first}'", org)
    if not got or got[0]["RecordType"]["DeveloperName"] != RT_DEVNAME:
        die(f"first record {first} did not read back as an SE Event — stopping")
    print(f"  {recs[0]['StartDateTime'][:10]} | {recs[0]['Subject'][:60]} | {first} "
          f"| {got[0].get('FTS_Request_Number_FTS__c')}")
    results.append({"subject": recs[0]["Subject"], "id": first})
    for r in recs[1:]:
        try:
            rid = create_one(r, org); err = None
        except SystemExit:
            rid, err = None, "create failed (see stderr)"
        print(f"  {r['StartDateTime'][:10]} | {r['Subject'][:60]} | {rid or 'ERR ' + err}")
        results.append({"subject": r["Subject"], "id": rid, "error": err})
    json.dump(results, open(os.path.join(ctx["dir"], "results.json"), "w"), indent=1)
    ids = ",".join(f"'{x['id']}'" for x in results if x["id"])
    n = len(query(f"SELECT Id FROM Event WHERE Id IN ({ids})", org)) if ids else 0
    print(f"Verified in Salesforce: {n}/{len(recs)} created.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("context"); c.add_argument("--out", required=True)
    c.add_argument("--since", required=True); c.add_argument("--until", required=True)
    c.add_argument("--org")
    k = sub.add_parser("create"); k.add_argument("--context", required=True)
    k.add_argument("--plan", required=True); k.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"context": cmd_context, "create": cmd_create}[a.cmd](a)


if __name__ == "__main__":
    main()
