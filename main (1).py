from fastapi import FastAPI, Request
from arcgis.gis import GIS
from arcgis.features import FeatureLayer
import os
import qrcode
from datetime import datetime

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# =========================
# APP INIT
# =========================
app = FastAPI()

# =========================
# AGOL AUTH
# =========================
AGOL_USERNAME = os.getenv("AGOL_USERNAME")
AGOL_PASSWORD = os.getenv("AGOL_PASSWORD")

if not AGOL_USERNAME or not AGOL_PASSWORD:
    raise Exception("AGOL credentials not set in environment variables")

gis = GIS("https://www.arcgis.com", AGOL_USERNAME, AGOL_PASSWORD)

# =========================
# FEATURE LAYER
# =========================
SURVEY_LAYER_URL = "https://services6.arcgis.com/345WScIubRHps95b/arcgis/rest/services/service_f42b703cdb24443ca50b30f44e9868bf/FeatureServer/0"
layer = FeatureLayer(SURVEY_LAYER_URL, gis=gis)

# =========================
# TEMPLATE
# =========================
TEMPLATE_PATH = "FORMAL_FOOD_PREMISES_INPECTION_REPORT.docx"

if not os.path.exists(TEMPLATE_PATH):
    raise Exception(f"{TEMPLATE_PATH} not found in project root")

# =========================
# TEMP PAYLOAD STORAGE
# =========================
LAST_PAYLOAD = {}
LAST_ERROR = None

# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "running"}

# =========================
# DEBUG ENDPOINT
# =========================
@app.get("/debug")
def debug():
    return {
        "template_exists": os.path.exists(TEMPLATE_PATH),
        "username_set": bool(AGOL_USERNAME),
        "password_set": bool(AGOL_PASSWORD),
        "layer_url": SURVEY_LAYER_URL
    }

# =========================
# LAST PAYLOAD
# =========================
@app.get("/last-payload")
def last_payload():
    return {
        "last_error": LAST_ERROR,
        "payload": LAST_PAYLOAD
    }

# =========================
# TEST QUERY
# =========================
@app.get("/test-query/{objectid}")
def test_query(objectid: int):
    result = layer.query(where=f"OBJECTID={objectid}", out_fields="*")
    return {
        "found": len(result.features),
        "attributes": result.features[0].attributes if result.features else None
    }

# =========================
# TEST UPDATE
# =========================
@app.get("/test-update/{objectid}")
def test_update(objectid: int):
    result = layer.edit_features(updates=[{
        "attributes": {
            "OBJECTID": objectid,
            "report_status": "test_ok",
            "report_url": "https://example.com/test.docx"
        }
    }])
    return {"edit_result": result}

# =========================
# HELPER: EXTRACT OBJECTID
# =========================
def extract_objectid(payload):
    if "submittedRecord" in payload:
        attrs = payload["submittedRecord"].get("attributes", {})
        if "OBJECTID" in attrs:
            return attrs["OBJECTID"]

    if "serverResponse" in payload:
        sr = payload["serverResponse"]
        if isinstance(sr, dict):
            if "objectId" in sr:
                return sr["objectId"]
            if "editResults" in sr and sr["editResults"]:
                first = sr["editResults"][0]
                if "objectId" in first:
                    return first["objectId"]

    if "feature" in payload:
        feature = payload["feature"]
        if isinstance(feature, dict):
            attrs = feature.get("attributes", {})
            if "OBJECTID" in attrs:
                return attrs["OBJECTID"]
            result = feature.get("result", {})
            if "objectId" in result:
                return result["objectId"]

    if "features" in payload and payload["features"]:
        first = payload["features"][0]
        attrs = first.get("attributes", {})
        if "OBJECTID" in attrs:
            return attrs["OBJECTID"]

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in ("OBJECTID", "objectId"):
                return value
            found = extract_objectid(value)
            if found is not None:
                return found

    if isinstance(payload, list):
        for item in payload:
            found = extract_objectid(item)
            if found is not None:
                return found

    return None

# =========================
# QR GENERATOR
# =========================
def generate_qr(url, path):
    img = qrcode.make(url)
    img.save(path)

# =========================
# UPLOAD REPORT TO AGOL
# =========================
def upload_report_to_agol(file_path, objectid):
    root_folder = gis.content.folders.get()

    item_properties = {
        "title": f"Report_{objectid}",
        "type": "Microsoft Word",
        "tags": ["survey123", "report", "automation"],
        "snippet": f"Automatically generated report for Survey123 submission {objectid}"
    }

    report_item = root_folder.add(
        item_properties=item_properties,
        file=file_path
    ).result()

    report_item.sharing.sharing_level = "EVERYONE"

    return f"https://www.arcgis.com/home/item.html?id={report_item.itemid}"

# =========================
# REPORT GENERATION
# =========================
def generate_report(attributes, objectid):
    os.makedirs("output", exist_ok=True)

    docx_file = os.path.join("output", f"report_{objectid}.docx")
    qr_file = os.path.join("output", f"qr_{objectid}.png")

    # Temporary QR target for first render
    temp_url = f"https://www.arcgis.com/home/item.html?id=temp-{objectid}"
    generate_qr(temp_url, qr_file)

    edit_date = attributes.get("EditDate")
    if edit_date:
        edit_date = datetime.fromtimestamp(edit_date / 1000).strftime("%Y-%m-%d %H:%M:%S")
    else:
        edit_date = "N/A"

    doc = DocxTemplate(TEMPLATE_PATH)
    qr_image = InlineImage(doc, qr_file, width=Mm(25))

    context = {
        "premise_name": attributes.get("premise_name", "N/A"),
        "Name": attributes.get("Name", "N/A"),
        "address": attributes.get("address", "N/A"),
        "Surname": attributes.get("Surname", "N/A"),
        "ID_no": attributes.get("ID_no", "N/A"),
        "tel_no": attributes.get("tel_not", "N/A"),
        "inspection_date": edit_date,
        "cell_no": attributes.get("cell_no", "N/A"),

        "males": attributes.get("males", "N/A"),
        "female": attributes.get("female", "N/A"),
        "A1": attributes.get("A1", "N/A"),
        "S1": attributes.get("S1", "N/A"),
        "A3": attributes.get("A3", "N/A"),
        "S3": attributes.get("S3", "N/A"),
        "A4": attributes.get("A4", "N/A"),
        "S4": attributes.get("S4", "N/A"),
        "A5": attributes.get("A5", "N/A"),
        "S5": attributes.get("S5", "N/A"),

        "A6": attributes.get("A6", "N/A"),
        "S6": attributes.get("S6", "N/A"),
        "A7": attributes.get("A7", "N/A"),
        "S7": attributes.get("S7", "N/A"),
        "municname": attributes.get("municname", "N/A"),
        "Q1": attributes.get("Q1", "N/A"),
        "comm1": attributes.get("comm1", "N/A"),
        "Q2": attributes.get("Q2", "N/A"),
        "comm2": attributes.get("comm2", "N/A"),
        "Q3": attributes.get("Q30", "N/A"),

        "comm3": attributes.get("comm3", "N/A"),
        "Q4": attributes.get("Q4", "N/A"),
        "comm4": attributes.get("comm4", "N/A"),
        "Q5": attributes.get("Q5", "N/A"),
        "comm5": attributes.get("comm5", "N/A"),
        "Q6": attributes.get("Q6", "N/A"),
        "comm6": attributes.get("comm6", "N/A"),
        "Q7": attributes.get("Q7", "N/A"),
        "comm7": attributes.get("comm7", "N/A"),

        "Q8": attributes.get("Q8", "N/A"),
        "comm8": attributes.get("comm8", "N/A"),
        "Q9": attributes.get("Q9", "N/A"),
        "comm9": attributes.get("comm9", "N/A"),
        "Q10": attributes.get("Q10", "N/A"),
        "comm10": attributes.get("comm10", "N/A"),
        "Q11": attributes.get("Q11", "N/A"),
        "comm11": attributes.get("comm11", "N/A"),

        "Q12": attributes.get("Q12", "N/A"),
        "comm12": attributes.get("comm12", "N/A"),
        "Q13": attributes.get("Q13", "N/A"),
        "comm13": attributes.get("comm13", "N/A"),
        "Q14": attributes.get("Q14", "N/A"),
        "comm14": attributes.get("comm14", "N/A"),
        "Q15": attributes.get("Q15", "N/A"),
        "comm16": attributes.get("comm16", "N/A"),

        "Q17": attributes.get("Q17", "N/A"),
        "comm17": attributes.get("comm17", "N/A"),
        "Q18": attributes.get("Q18", "N/A"),
        "comm18": attributes.get("comm18", "N/A"),
        "Q19": attributes.get("Q19", "N/A"),
        "comm19": attributes.get("comm19", "N/A"),
        "Q20": attributes.get("Q20", "N/A"),
        "comm20": attributes.get("comm20", "N/A"),

        "Q21": attributes.get("Q21", "N/A"),
        "comm21": attributes.get("comm21", "N/A"),
        "Q22": attributes.get("Q22", "N/A"),
        "comm22": attributes.get("comm22", "N/A"),
        "Q23": attributes.get("Q23", "N/A"),
        "comm23": attributes.get("comm23", "N/A"),
        "Q24": attributes.get("Q24", "N/A"),
        "comm24": attributes.get("comm24", "N/A"),

        "Q25": attributes.get("Q25", "N/A"),
        "comm25": attributes.get("comm25", "N/A"),
        "Q26": attributes.get("Q26", "N/A"),
        "comm26": attributes.get("comm26", "N/A"),
        "Q27": attributes.get("Q27", "N/A"),
        "comm27": attributes.get("comm27", "N/A"),
        "Q28": attributes.get("Q28", "N/A"),
        "comm28": attributes.get("comm28", "N/A"),

        "Q29": attributes.get("Q20", "N/A"),
        "comm29": attributes.get("comm29", "N/A"),
        "Q30": attributes.get("Q30", "N/A"),
        "comm30": attributes.get("comm30", "N/A"),
        "Q31": attributes.get("Q31", "N/A"),
        "comm31": attributes.get("comm31", "N/A"),
        "Q32": attributes.get("Q32", "N/A"),
        "comm32": attributes.get("commm32", "N/A"),

         "Q33": attributes.get("Q33", "N/A"),
        "comm33": attributes.get("comm33", "N/A"),
        "Q34": attributes.get("Q34", "N/A"),
        "comm34": attributes.get("comm34", "N/A"),
        "Q35": attributes.get("Q35", "N/A"),
        "comm35": attributes.get("comm35", "N/A"),
        "Q36": attributes.get("Q36", "N/A"),
        "comm36": attributes.get("commm36", "N/A"),

        "Q40": attributes.get("Q40", "N/A"),
        "Rem40": attributes.get("Rem40", "N/A"),
        "Q41": attributes.get("Q41", "N/A"),
        "Rem41": attributes.get("Rem41", "N/A"),
        "Q42": attributes.get("Q42", "N/A"),
        "Rem42": attributes.get("Rem42", "N/A"),
        "Q43": attributes.get("Q43", "N/A"),
        "Rem43": attributes.get("Rem43", "N/A"),

        "Q44": attributes.get("Q44", "N/A"),
        "Rem44": attributes.get("Rem44", "N/A"),
        "Q45": attributes.get("Q45", "N/A"),
        "Rem45": attributes.get("Rem45", "N/A"),
        "Q46": attributes.get("Q46", "N/A"),
        "Rem46": attributes.get("Rem46", "N/A"),

        "Non_compliances": attributes.get("Non_compliances", "N/A"),
        "Corrective_action": attributes.get("Corrective_action", "N/A"),
        "Overall_compliance_status": attributes.get("Overall_compliance_status", "N/A"),
        "ehp_signature": attributes.get("ehp_signature", "N/A"),
        "HI_number": attributes.get("HI_number", "N/A"),
        "Owner_Manager_signatures": attributes.get("Owner_Manager_signatures", "N/A"),

        "qr_code": qr_image
    }

    doc.render(context)
    doc.save(docx_file)

    real_url = upload_report_to_agol(docx_file, objectid)
    return real_url

# =========================
# UPDATE FEATURE
# =========================
def update_feature(objectid, url, status):
    result = layer.edit_features(updates=[{
        "attributes": {
            "OBJECTID": objectid,
            "report_url": url,
            "report_status": status
        }
    }])
    return result

# =========================
# WEBHOOK ENDPOINT
# =========================
@app.post("/webhook/survey123")
async def survey_webhook(request: Request):
    global LAST_PAYLOAD, LAST_ERROR

    payload = await request.json()
    LAST_PAYLOAD = payload
    LAST_ERROR = None
    objectid = None

    try:
        objectid = extract_objectid(payload)

        if objectid is None:
            LAST_ERROR = f"OBJECTID not found. Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not a dict'}"
            return {
                "status": "failed",
                "error": LAST_ERROR
            }

        update_feature(objectid, "webhook_received", "received")

        result = layer.query(where=f"OBJECTID={objectid}", out_fields="*")

        if not result.features:
            update_feature(objectid, "query_failed", "failed")
            LAST_ERROR = f"No feature found for OBJECTID {objectid}"
            return {
                "status": "failed",
                "error": LAST_ERROR
            }

        attributes = result.features[0].attributes

        update_feature(objectid, "query_ok", "queried")

        report_url = generate_report(attributes, objectid)

        edit_result = update_feature(objectid, report_url, "completed")

        return {
            "status": "success",
            "objectid": objectid,
            "report_url": report_url,
            "edit_result": str(edit_result)
        }

    except Exception as e:
        LAST_ERROR = str(e)
        if objectid is not None:
            try:
                update_feature(objectid, f"ERROR: {str(e)}", "failed")
            except Exception:
                pass

        return {
            "status": "failed",
            "objectid": objectid,
            "error": str(e)
        }
