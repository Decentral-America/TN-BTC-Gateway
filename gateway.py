import json
import re
import secrets
from typing import List

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.templating import Jinja2Templates

from dbClass import dbCalls
from dbPGClass import dbPGCalls
from otherClass import otherCalls
from tnClass import tnCalls
from verification import verifier


class cHeights(BaseModel):
    TN: int
    Other: int


class cAdresses(BaseModel):
    sourceAddress: str
    targetAddress: str


class cExecResult(BaseModel):
    successful: int
    address: str


class cFullInfo(BaseModel):
    chainName: str
    assetID: str
    tn_gateway_fee: float
    tn_network_fee: float
    tn_total_fee: float
    other_gateway_fee: float
    other_network_fee: float
    other_total_fee: float
    fee: float
    company: str
    email: str
    telegram: str
    recovery_amount: float
    recovery_fee: float
    otherHeight: int
    tnHeight: int
    tnAddress: str
    tnColdAddress: str
    otherAddress: str
    otherNetwork: str
    disclaimer: str
    tn_balance: int
    other_balance: int
    minAmount: float
    maxAmount: float
    type: str
    usageinfo: str


class cDepositWD(BaseModel):
    status: str
    tx: str
    block: str
    error: str


class cTx(BaseModel):
    sourceAddress: str
    targetAddress: str
    tnTxId: str
    OtherTxId: str
    TNVerBlock: int = 0
    OtherVerBlock: int = 0
    amount: float
    TypeTX: str
    Status: str


class cTxs(BaseModel):
    transactions: List[cTx] = []
    error: str = ""


class cFees(BaseModel):
    totalFees: float


class cHealth(BaseModel):
    chainName: str
    assetID: str
    status: str
    connectionTN: bool
    connectionOther: bool
    blocksbehindTN: int
    blockbehindOther: int
    balanceTN: float
    balanceOther: float
    numberErrors: int


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

with open('config.json') as json_file:
    config = json.load(json_file)

if config['main']['use-pg']:
    dbc = dbPGCalls(config)
else:
    dbc = dbCalls(config)

checkit = verifier(config, dbc)


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, config["main"]["admin-username"])
    correct_password = secrets.compare_digest(credentials.password, config["main"]["admin-password"])
    if not (correct_username and correct_password):
        print("ERROR: invalid logon details")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_tnBalance():
    return tnCalls(config, dbc).currentBalance()


def get_otherBalance():
    return otherCalls(config, dbc).currentBalance()


@app.get("/")
async def index(request: Request):
    heights = await getHeights()
    index = config['main']['index-file']
    if index == "": index = "index.html"
    return templates.TemplateResponse(index, {"request": request,
                                              "chainName": config['main']['name'],
                                              "assetID": config['dcc']['assetId'],
                                              "tn_gateway_fee": config['dcc']['gateway_fee'],
                                              "tn_network_fee": config['dcc']['network_fee'],
                                              "tn_total_fee": config['dcc']['network_fee'] + config['dcc']['gateway_fee'],
                                              "eth_gateway_fee": config['other']['gateway_fee'],
                                              "eth_network_fee": config['other']['network_fee'],
                                              "eth_total_fee": config['other']['network_fee'] + config['other'][
                                                  'gateway_fee'],
                                              "fee": config['dcc']['fee'],
                                              "company": config['main']['company'],
                                              "email": config['main']['contact-email'],
                                              "telegram": config['main']['contact-telegram'],
                                              "recovery_amount": config['main']['recovery_amount'],
                                              "recovery_fee": config['main']['recovery_fee'],
                                              "ethHeight": heights['Other'],
                                              "tnHeight": heights['DCC'],
                                              "tnAddress": config['dcc']['gatewayAddress'],
                                              "ethAddress": config['other']['gatewayAddress'],
                                              "disclaimer": config['main']['disclaimer']})


@app.get('/heights', response_model=cHeights)
async def getHeights():
    result = dbc.getHeights()

    return {'DCC': result[0][1], 'Other': result[1][1]}


@app.get('/errors')
async def getErrors(request: Request, username: str = Depends(get_current_username)):
    if (config["main"]["admin-username"] == "admin" and config["main"]["admin-password"] == "admin"):
        return {"message": "change the default username and password please!"}

    if username == config["main"]["admin-username"]:
        print("INFO: displaying errors page")
        result = dbc.getErrors()
        return templates.TemplateResponse("errors.html", {"request": request, "errors": result})


@app.get('/executed')
async def getExecuted(request: Request, username: str = Depends(get_current_username)):
    if (config["main"]["admin-username"] == "admin" and config["main"]["admin-password"] == "admin"):
        return {"message": "change the default username and password please!"}

    if username == config["main"]["admin-username"]:
        print("INFO: displaying executed page")
        result = dbc.getExecutedAll()
        result2 = dbc.getVerifiedAll()
        return templates.TemplateResponse("tx.html", {"request": request, "txs": result, "vtxs": result2})


@app.get('/tnAddress/{address}', response_model=cAdresses)
async def checkTunnel(address: str):
    address = re.sub('[\W_]+', '', address)

    result = dbc.getSourceAddress(address)
    if len(result) == 0:
        targetAddress = ""
    else:
        targetAddress = result[0]

    return cAdresses(sourceAddress=targetAddress, targetAddress=address[0][0])


# TODO: rewrite to post
@app.get('/tunnel/{targetAddress}', response_model=cExecResult)
async def createTunnel(targetAddress: str):
    targetAddress = re.sub('[\W_]+', '', targetAddress)

    if not tnCalls(config, dbc).validateaddress(targetAddress):
        return cExecResult(successful=0, address='')

    if targetAddress == config['dcc']['gatewayAddress']:
        return {'successful': '0'}

    result = dbc.getSourceAddress(targetAddress)
    if len(result) == 0:
        sourceAddress = otherCalls(config, dbc).getNewAddress()

        dbc.insTunnel("created", sourceAddress, targetAddress)
        print("INFO: tunnel created")
        return cExecResult(successful=1, address=sourceAddress)
    else:
        return cExecResult(successful=2, address=result[0][0])


@app.get("/api/fullinfo", response_model=cFullInfo)
async def api_fullinfo():
    heights = await getHeights()
    tnBalance = get_tnBalance()
    otherBalance = get_otherBalance()
    return {"chainName": config['main']['name'],
            "assetID": config['dcc']['assetId'],
            "tn_gateway_fee": config['dcc']['gateway_fee'],
            "tn_network_fee": config['dcc']['network_fee'],
            "tn_total_fee": config['dcc']['network_fee'] + config['dcc']['gateway_fee'],
            "other_gateway_fee": config['other']['gateway_fee'],
            "other_network_fee": config['other']['network_fee'],
            "other_total_fee": config['other']['network_fee'] + config['other']['gateway_fee'],
            "fee": config['dcc']['fee'],
            "company": config['main']['company'],
            "email": config['main']['contact-email'],
            "telegram": config['main']['contact-telegram'],
            "recovery_amount": config['main']['recovery_amount'],
            "recovery_fee": config['main']['recovery_fee'],
            "otherHeight": heights['Other'],
            "tnHeight": heights['DCC'],
            "tnAddress": config['dcc']['gatewayAddress'],
            "tnColdAddress": config['dcc']['coldwallet'],
            "otherAddress": config['other']['gatewayAddress'],
            "otherNetwork": config['other']['network'],
            "disclaimer": config['main']['disclaimer'],
            "tn_balance": tnBalance,
            "other_balance": otherBalance,
            "minAmount": config['main']['min'],
            "maxAmount": config['main']['max'],
            "type": "deposit",
            "usageinfo": ""}


@app.get("/api/deposit/{tnAddress}", response_model=cDepositWD)
async def api_depositCheck(tnAddress: str):
    result = checkit.checkTX(targetAddress=tnAddress)

    return result


@app.get("/api/wd/{tnAddress}", response_model=cDepositWD)
async def api_wdCheck(tnAddress: str):
    result = checkit.checkTX(sourceAddress=tnAddress)

    return result


@app.get("/api/checktxs/{tnAddress}", response_model=cTxs)
async def api_checktxs(tnAddress: str):
    if not tnCalls(config, dbc).validateaddress(tnAddress):
        temp = cTxs(error='invalid address')
    else:
        result = dbc.checkTXs(address=tnAddress)

        if 'error' in result:
            temp = cTxs(error=result['error'])
        else:
            temp = cTxs(transactions=result)

    return temp


@app.get("/api/checktxs", response_model=cTxs)
async def api_checktxs():
    result = dbc.checkTXs(address='')

    if 'error' in result:
        temp = cTxs(error=result['error'])
    else:
        temp = cTxs(transactions=result)

    return temp


@app.get('/api/fees/{fromdate}/{todate}', response_model=cFees)
async def api_getFees(fromdate: str, todate: str):
    return dbc.getFees(fromdate, todate)


@app.get('/api/fees/{fromdate}', response_model=cFees)
async def api_getFees(fromdate: str):
    return dbc.getFees(fromdate, '')


@app.get('/api/fees', response_model=cFees)
async def api_getFees():
    return dbc.getFees('', '')


@app.get('/api/health', response_model=cHealth)
async def api_getHealth():
    return checkit.checkHealth()
