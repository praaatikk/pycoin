from flask import Flask, render_template, request, redirect, url_for
from Blockchain.client.sendBTC import SendBTC
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.core.database.database import BlockchainDB, AccountDB
from Blockchain.client.createWallet import CreateWallet

app = Flask(__name__)


# =========================
# DASHBOARD ROUTE
# =========================
@app.route("/")
def dashboard():
    blockchainDB = BlockchainDB()
    blocks = blockchainDB.read()

    last_block = blockchainDB.lastBlock()
    latest_hash = None
    block_height = 0

    if last_block:
        latest_hash = last_block["BlockHeader"]["blockHash"]
        block_height = last_block["Height"]

    return render_template(
        "dashboard.html",
        utxo_count=len(UTXOS),
        mempool_count=len(MEMPOOL),
        latest_hash=latest_hash,
        block_height=block_height,
        blocks=blocks[::-1]
    )


# =========================
# WALLET ROUTE
# =========================
@app.route("/wallet", methods=["GET", "POST"])
def wallet():
    message = ""
    status = ""

    # Load ALL accounts with their balances
    accounts = BLOCKCHAIN.get_all_accounts_with_balance()

    if not accounts:
        return "No accounts found. Please create a wallet first.", 400

    # Get selected address from form (POST) or default to first account (GET)
    selected_address = request.form.get("fromAddress") or request.args.get("address") or accounts[0]["PublicAddress"]

    # Find selected account
    selected_account = next((a for a in accounts if a["PublicAddress"] == selected_address), accounts[0])
    balance = selected_account["balance"]

    # Get transaction history for selected address
    tx_history = BLOCKCHAIN.get_transaction_history(selected_address)

    if request.method == "POST" and request.form.get("action") == "send":
        ToAddress = request.form.get("toAddress")
        Amount = request.form.get("Amount", type=float)

        if not ToAddress or not Amount:
            message = "Please fill in all fields"
            status = "error"
        else:
            sendCoin = SendBTC(selected_address, ToAddress, Amount, UTXOS)
            TxObj = sendCoin.prepareTransaction()

            verified = True

            if not TxObj:
                message = "Invalid Transaction — insufficient balance or bad address"
                status = "error"

            if isinstance(TxObj, Tx):
                for index, tx_in in enumerate(TxObj.tx_ins):
                    prev_tx_id = tx_in.prev_tx.hex().lower()
                    prev_index = tx_in.prev_index

                    if prev_tx_id not in UTXOS:
                        verified = False
                        break

                    prev_tx_obj = UTXOS[prev_tx_id]
                    scriptPubKey = prev_tx_obj.tx_outs[prev_index].script_pubkey

                    if not TxObj.verify_input(index, scriptPubKey):
                        verified = False
                        break

                if verified:
                    MEMPOOL[TxObj.TxId] = TxObj
                    message = "Transaction added to Memory Pool"
                    status = "success"
                else:
                    message = "Transaction Verification Failed"
                    status = "error"

    return render_template(
        "wallet.html",
        message=message,
        status=status,
        accounts=accounts,                      # ALL accounts with balances
        selected_address=selected_address,      # currently selected address
        balance=balance,                        # balance of selected account
        tx_history=tx_history                   # tx history of selected account
    )


# =========================
# CREATE WALLET ROUTE
# =========================
@app.route("/create-wallet", methods=["POST"])
def create_wallet():
    """
    Generates a new wallet and saves it to account.json.
    Redirects back to wallet page with new address selected.
    """
    wallet_creator = CreateWallet()
    new_account = wallet_creator.generate()

    # Redirect to wallet page with new address selected
    return redirect(url_for("wallet", address=new_account["PublicAddress"]))


# =========================
# BLOCKCHAIN EXPLORER ROUTE
# =========================
@app.route("/explorer")
def explorer():
    blockchainDB = BlockchainDB()
    blocks = blockchainDB.read()

    for block in blocks:
        if block["Txs"]:
            coinbase_amount = block["Txs"][0]["tx_outs"][0]["amount"]
            block_reward = 50 * 100000000
            fee = max(0, coinbase_amount - block_reward)
            block["fee_btc"] = fee / 100000000
        else:
            block["fee_btc"] = 0

    return render_template(
        "explorer.html",
        blocks=blocks[::-1]
    )


# =========================
# BLOCK DETAIL ROUTE
# =========================
@app.route("/block/<int:height>")
def block_detail(height):
    blockchainDB = BlockchainDB()
    blocks = blockchainDB.read()

    block = next((b for b in blocks if b["Height"] == height), None)

    if not block:
        return "Block not found", 404

    if block["Txs"]:
        coinbase_amount = block["Txs"][0]["tx_outs"][0]["amount"]
        block_reward = 50 * 100000000
        fee = max(0, coinbase_amount - block_reward)
        block["fee_btc"] = fee / 100000000
    else:
        block["fee_btc"] = 0

    return render_template("block_detail.html", block=block)


# =========================
# TRANSACTION HISTORY ROUTE
# =========================
@app.route("/transactions/<address>")
def transactions(address):
    tx_history = BLOCKCHAIN.get_transaction_history(address)

    return render_template(
        "transactions.html",
        address=address,
        tx_history=tx_history
    )


# =========================
# MAIN FUNCTION
# =========================
def main(utxos, MemPool, blockchain):
    global UTXOS, MEMPOOL, BLOCKCHAIN

    UTXOS = utxos
    MEMPOOL = MemPool
    BLOCKCHAIN = blockchain

    app.run(debug=False, use_reloader=False)