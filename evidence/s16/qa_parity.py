import json, subprocess, sys, hashlib
import joblib, pandas as pd
demo = {"LIMIT_BAL": 120000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 2, "AGE": 34,
        "PAY_0": 2, "PAY_2": 2, "PAY_3": 0, "PAY_4": 0, "PAY_5": -1, "PAY_6": -1,
        "BILL_AMT1": 35000, "BILL_AMT2": 33500, "BILL_AMT3": 30000, "BILL_AMT4": 28000,
        "BILL_AMT5": 26500, "BILL_AMT6": 25000,
        "PAY_AMT1": 2000, "PAY_AMT2": 2500, "PAY_AMT3": 3000, "PAY_AMT4": 3000,
        "PAY_AMT5": 3500, "PAY_AMT6": 4000}
r = json.loads(subprocess.run([sys.executable,"-m","src.inference","--input","-"],
    input=json.dumps(demo), capture_output=True, text=True).stdout)
man = json.load(open("models/model_manifest.json"))
feats = man["features"]["order"]; art = man["artifact"]["path"]
sha = hashlib.sha256(open(art,"rb").read()).hexdigest()
print("artifact             :", art, "| sha256", sha[:16]+"…", "| matches manifest:", sha == man["artifact"]["sha256"])
print("features             :", man["features"]["count"], "| order == 23 names:", len(feats) == 23)
m = joblib.load(art)
X = pd.DataFrame([[demo[f] for f in feats]], columns=feats)
p = float(m.predict_proba(X)[0][1])
print("CLI   P(class1)      :", repr(r["probability"]), "| class", r["predicted_class"], "| tier", r["risk_tier"])
print("bare  P(class1)      :", repr(p))
print("abs delta            :", abs(p - float(r["probability"])))
print("PARITY               :", "PASS" if abs(p-float(r["probability"])) < 1e-12 else "FAIL")
